"""Effect-centric resource discovery with explicit provenance.

A filename family is a discovery hint, never proof that the effect loads that file.
Native dispatch, cinematic interpreter profiles and data location are independent facts.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER


@dataclass(frozen=True)
class EffectResource:
    key: str
    name: str
    source: str
    evidence: str
    kind: str = "file"
    note: str = ""
    address: int = 0
    size: int = 0


def filename_effect(name):
    match = re.fullmatch(r"mag(\d{3})(?:[_.-].*)?", Path(name).name, re.IGNORECASE)
    return int(match[1]) + 1 if match else None


class EffectCatalog:
    def __init__(self, resource_folder=None):
        folder = Path(resource_folder or RESOURCES_JSON_FOLDER)
        self._folder = folder
        self._code = None        # address -> pseudocode, read from the gzip on first use
        self.names = {e["id"]: e["name"] for e in json.loads(
            (folder / "attack_animation.json").read_text(encoding="utf-8"))["attack_animation"]}
        self.dump = json.loads((folder / "magic_effect.json").read_text(encoding="utf-8"))
        self.research = json.loads((folder / "effect_native_research.json").read_text(encoding="utf-8"))["effects"]
        self.camera = json.loads((folder / "effect_camera.json").read_text(encoding="utf-8"))
        self.profiles = json.loads((folder / "mag_cinematic_profiles.json").read_text(encoding="utf-8"))["effects"]
        self.native = json.loads((folder / "effect_resources.json").read_text(encoding="utf-8"))
        self.facts = json.loads((folder / "effect_runtime.json").read_text(encoding="utf-8"))["effects"]
        self.files = json.loads((folder / "mag_file_catalog.json").read_text(encoding="utf-8"))["files"]
        # effect id -> catalog file names of its mag family, sorted (built once: resources() is
        # asked for every effect, and matching the whole catalog each time made that slow)
        self._families = {}
        for name in sorted(set(self.files), key=str.lower):
            self._families.setdefault(filename_effect(name), []).append(name)

    def effect_ids(self):
        return sorted({int(k) for k in self.dump if k.isdigit()} | {i for i in self.names if i > 0})

    def snapshot(self):
        """Where magic_effect.json's native functions come from ({} for a snapshot without it)."""
        return self.dump.get("_snapshot", {})

    def name(self, effect):
        return self.names.get(effect, "Free slot" if self.info(effect).get("free") else "Unidentified effect")

    def info(self, effect):
        return self.dump.get(str(effect), {})

    def functions(self, effect):
        return self.info(effect).get("functions", []) + self.research.get(str(effect), [])

    def pseudocode(self, function):
        """A function's decompiled code: inline (research entries) or from magic_effect_code.json.gz,
        which is opened the first time some code is shown."""
        if "pseudocode" in function:
            return function["pseudocode"]
        if self._code is None:
            import gzip
            path = self._folder / self.snapshot().get("code", "magic_effect_code.json.gz")
            try:
                self._code = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
            except (OSError, ValueError):
                self._code = {}
        return self._code.get(function.get("addr", ""), "No decompiled source available.")

    def runtime(self, effect):
        if str(effect) in self.profiles:
            return "MAG cinematic interpreter"
        return self.facts.get(str(effect), {}).get("runtime", "Native effect code")

    def notes(self, effect):
        return self.facts.get(str(effect), {}).get("note", "")

    def camera_entry(self, effect):
        return next((t for t in self.camera["tracks"] if t["effect_id"] == effect), None)

    def aliases(self, effect):
        address = self.info(effect).get("logic_addr")
        return [int(k) for k, v in self.dump.items() if k.isdigit() and int(k) != effect and address
                and v.get("logic_addr") == address and not v.get("free")]

    def resources(self, effect, extra_names=()):
        result = {}
        # String extraction is partial and can contain unrelated constants (e.g. "V").
        # Keep only resource-like filenames; an empty loader is not an unused slot.
        for name in self.info(effect).get("files_loaded", []):
            if re.fullmatch(r"[\w.-]+\.[\w]+", name):
                result[name.lower()] = EffectResource(name.lower(), name, "File", "Loader reference")
        for entry in self.facts.get(str(effect), {}).get("files", []):
            name = entry["name"]
            result[name.lower()] = EffectResource(name.lower(), name, "File", "Verified runtime resource",
                                                  entry.get("kind", "file"), entry.get("note", ""))
        family = self._families.get(effect, [])
        extra = [name for name in extra_names if filename_effect(name) == effect]
        for name in sorted(set(family) | set(extra), key=str.lower):
            if name.lower() not in result:
                result[name.lower()] = EffectResource(name.lower(), name, "File", "Filename family only",
                                                      note="Association is a discovery hint; loading by this effect is not proven.")
        for entry in self.native["resources"]:
            if effect in entry["effect_ids"]:
                result[entry["id"]] = EffectResource(entry["id"], entry.get("label", entry["id"]), "Executable",
                    "IDA resource binding / validated bytes", entry["kind"],
                    entry.get("note", "English 2013 Steam data; exported as Hext. Separate copies remain independent."),
                    int(entry["address"], 16), entry["size"])
        return list(result.values())
