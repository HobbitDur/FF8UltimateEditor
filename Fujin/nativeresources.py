"""Bounded native data documents. Executable bytes are exported as Hext, never overwritten."""
import hashlib
import re

from Laguna.lagunamanager import LagunaManager
from Fujin.cameraeffectmanager import CameraTrack
from FF8GameData.magcine.magfile import MagField


class NativeDocument(LagunaManager):
    def __init__(self, entry):
        self.entry = entry
        super().__init__()

    def analyse(self):
        super().analyse()
        if self.entry["kind"] == "camera_parameter":
            self.document.format = "Native camera parameter"
            section = self.document.sections[0]
            section.name = self.entry["label"]
            section.fields = [MagField(self.entry["label"], 0, self.entry["fmt"])]
            section.note = self.entry["note"]


def changed_runs(original, current):
    if len(original) != len(current):
        raise ValueError("A native resource must keep its byte size")
    start = None
    for i in range(len(current) + 1):
        differs = i < len(current) and current[i] != original[i]
        if differs and start is None:
            start = i
        elif not differs and start is not None:
            yield start, bytes(current[start:i])
            start = None


class NativeResourceStore:
    def __init__(self, manifest, game_data_folder="FF8GameData"):
        self.manifest = manifest
        self.game_data_folder = game_data_folder
        self.managers = {}
        self.unavailable = {}
        self.entries = {entry["id"]: entry for entry in manifest["resources"]}

    def close(self):
        self.managers.clear()
        self.unavailable.clear()

    def load(self, exe, language):
        self.close()
        for key, entry in self.entries.items():
            if language != "EN":
                self.unavailable[key] = "This resource address is verified for the English 2013 Steam exe only."
                continue
            offset, size = entry["file_offset"], entry["size"]
            raw = exe[offset:offset + size]
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                self.unavailable[key] = "The bytes do not match the audited resource at this address."
                continue
            if "instruction_hex" in entry:
                guard = bytes.fromhex(entry["instruction_hex"])
                guard_at = int(entry["instruction_address"], 16) - 0x400000
                if exe[guard_at:guard_at+len(guard)] != guard:
                    self.unavailable[key] = "The native instruction surrounding this camera operand does not match."
                    continue
            manager = NativeDocument(entry)
            manager.game_data_folder = self.game_data_folder
            manager.load_bytes(raw, name=key)
            self.managers[key] = manager

    def hext_lines(self):
        lines = []
        for key, manager in self.managers.items():
            if not manager.modified:
                continue
            entry = self.entries[key]
            lines.append(f"#Native {key} at {entry['address']}")
            for offset, data in changed_runs(manager.original, manager.data):
                for i in range(0, len(data), 16):
                    lines.append(f"{entry['file_offset'] + offset + i:X} = {data[i:i+16].hex(' ').upper()}")
            lines.append("")
        return lines


def apply_effect_hext(text, cameras, native):
    """All-or-nothing import into owned resources; reject unrelated addresses and headers.

    Only the explicit +400000/file-offset form emitted by this workspace is accepted.
    Parsing and validation complete before any editable document changes.
    """
    for language in re.findall(r"for the (EN|FR|DE|IT|ES) FF8 exe", text):
        if language != cameras.language_name:
            raise ValueError(f"This patch targets the {language} executable; the loaded exe is {cameras.language_name}")
    images, owners = {}, {}
    for effect, track in cameras.tracks.items():
        key = ("camera", effect)
        images[key] = bytearray(track.to_bytes())
        owners[key] = (track.address - 0x400000, len(track.original))
    for key, manager in native.managers.items():
        images[("native", key)] = bytearray(manager.data)
        owners[("native", key)] = (native.entries[key]["file_offset"], len(manager.data))
    touched, base_seen = set(), False
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("+"):
            if line.upper() != "+400000":
                raise ValueError(f"Line {line_no}: only the +400000 base is supported")
            base_seen = True
            continue
        match = re.fullmatch(r"([0-9A-Fa-f]+)\s*=\s*((?:[0-9A-Fa-f]{2}\s*)+)", line)
        if not match or not base_seen:
            raise ValueError(f"Line {line_no}: unsupported Hext syntax or missing +400000 base")
        address, data = int(match[1], 16), bytes.fromhex(match[2])
        owner = next((key for key, (start, size) in owners.items()
                      if start <= address and address + len(data) <= start + size), None)
        if owner is None:
            raise ValueError(f"Line {line_no}: address 0x{address:X} is outside loaded effect resources")
        offset = address - owners[owner][0]
        images[owner][offset:offset + len(data)] = data
        touched.add(owner)
    parsed_tracks = {}
    for kind, key in touched:
        if kind == "camera":
            track = cameras.tracks[key]
            parsed_tracks[key] = CameraTrack.from_bytes(cameras.vm, images[(kind, key)],
                effect_id=key, name=track.name, label=track.label, address=track.address,
                push_operand=track.push_operand)
            if images[(kind, key)][:8] != track.original[:8]:
                raise ValueError(f"Effect {key}: Hext cannot change the camera layout header")
    for kind, key in touched:
        if kind == "camera":
            current, parsed = cameras.tracks[key], parsed_tracks[key]
            current.header, current.script, current.padding, current.collection = (
                parsed.header, parsed.script, parsed.padding, parsed.collection)
        else:
            native.managers[key].patch_bytes(0, images[(kind, key)])
    return len(touched)
