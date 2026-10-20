"""Lossless, bounded section map for the MAG file family.

Names/extensions are hints, never a format signature. Unknown bytes are explicit sections;
the editor patches equal-sized ranges instead of reconstructing or relocating a container.
Packed texture/CLUT offsets use their low 24 bits relative to their own table. Object offsets
are relative to the object table. Header offsets are file-relative.
"""
import struct
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MagField:
    name: str
    offset: int
    fmt: str = "I"

    @property
    def size(self):
        return struct.calcsize("<" + self.fmt)


@dataclass
class MagSection:
    name: str
    start: int
    end: int
    kind: str = "raw"
    fields: list = field(default_factory=list)
    note: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def size(self):
        return self.end - self.start


HEADER_NAMES = ("Reserved / unknown", "Root script offset", "CLUT table offset", "Object table offset",
                "Sound table offset", "Texture table offset", "Music table offset", "End of tables / RAM offset",
                "Stage camera offset", "Voice bank offset", "Reserved / unknown", "Reserved / unknown")


class MagFile:
    """Read-only interpretation of a byte image; all spans stay inside that image."""
    def __init__(self, data, name=""):
        self.data = bytes(data)
        self.name = name
        self.format = "Raw / undecoded"
        self.sections = []
        self.warnings = []
        self.root = None
        self._marks = {}
        self.header = ()
        if self.data[:4] == b"\x10\0\0\0":
            self.format = "PlayStation TIM"
            self._tim()
        elif self._is_packed():
            self.format = "Packed MAG"
            self._packed()
        elif len(self.data) >= 8 and self.data[4:8] == b"SCOT":
            self.format = "SCOT sound"
            self._mark(0, "Sound header", "sound", [MagField("Sound ID", 0)])
            self._mark(0x10 if len(self.data) >= 0x10 else len(self.data), "Sound data", "sound")
        elif self.data[:4] == b"AKAO":
            self.format = "AKAO audio"
            self._mark(0, "AKAO audio", "audio", note="Audio stream; encoding is not decoded here.")
        elif not self._indexed():
            kind = "id" if len(self.data) == 4 else "raw"
            self.format = "Four-byte reference" if kind == "id" else self.format
            self._mark(0, "Reference" if kind == "id" else "Raw data", kind,
                       [MagField("Reference value (meaning depends on loader)", 0)] if kind == "id" else [],
                       "No validated section directory. Bytes are preserved without assuming a script or texture size.")
        self._finish()
        self._model_parts()

    def _u32(self, offset):
        return struct.unpack_from("<I", self.data, offset)[0]

    def _mark(self, start, name, kind="raw", fields=None, note="", **meta):
        if not 0 <= start <= len(self.data):
            self.warnings.append(f"{name}: offset 0x{start:X} is outside the file")
            return
        # Root/payload markers deliberately replace empty-table / RAM boundary markers.
        self._marks[start] = (name, kind, fields or [], note, meta)

    def _is_packed(self):
        if len(self.data) < 0x30:
            return False
        h = struct.unpack_from("<12I", self.data)
        if h[0] == 0 and h[5] == 0x30 and 0x30 <= h[2] <= h[6] <= h[7] <= len(self.data):
            self.header = h
            return True
        return False

    def _packed(self):
        h = self.header
        self._mark(0, "Header", "header", [MagField(n, 4*i) for i, n in enumerate(HEADER_NAMES)])
        self._mark(0x30, "Unassigned data", note="Includes padding or runtime workspace when present.")
        self._mark(h[7], "Workspace / unassigned data")
        for a, b, name, kind in ((h[5], h[2], "Texture table", "texture_table"),
                                  (h[2], h[6], "CLUT table", "clut_table"),
                                  (h[6], h[7], "Music table", "music_table")):
            if a < b:
                if (b-a) % 4:
                    self.warnings.append(f"{name}: size is not a multiple of four")
                fields = [MagField(f"Entry {i} (packed flags / relative offset)", p)
                          for i, p in enumerate(range(a, b-3, 4))]
                self._mark(a, name, kind, fields)
                if kind != "music_table":
                    for i, p in enumerate(range(a, b-3, 4)):
                        v = self._u32(p)
                        if v:
                            target = a + (v & 0xFFFFFF)
                            if target < h[7]:
                                self.warnings.append(f"{name} entry {i}: target overlaps the initial tables")
                            else:
                                self._mark(target, f"{'Texture' if kind == 'texture_table' else 'Palette'} {i}",
                                           "texture" if kind == "texture_table" else "palette", resource_id=i)
        for index, name, kind in ((4, "Sound effects", "sound"), (9, "Voice bank", "voice")):
            if h[index]:
                self._mark(h[index], name, kind,
                           note="Audio bytes and tables; use the field/byte editor or export a block.")
        if h[3] and h[3] + 4 <= len(self.data):
            table = h[3]
            count = self._u32(table)
            if count <= (len(self.data)-table-4)//4:
                fields = [MagField("Object count", table)]
                for i in range(count):
                    p = table + 4 + 4*i
                    fields.append(MagField(f"Object {i} relative offset", p))
                    v = self._u32(p)
                    if v:
                        target = table + v
                        if target < table + 4 + 4*count:
                            self.warnings.append(f"Object {i}: target overlaps its directory")
                        else:
                            self._mark(target, f"Object {i}", "object", object_id=i)
                self._mark(table, "Object table", "object_table", fields)
            else:
                self.warnings.append("Object count exceeds the file")
                self._mark(table, "Object table (invalid)")
        elif h[3]:
            self.warnings.append("Object table is outside the file")
        if h[1]:
            if h[7] <= h[1] < len(self.data):
                self.root = h[1]
                self._mark(h[1], "Cinematic script", "script")
            else:
                self.warnings.append("Root script is outside the payload")
        if h[8]:
            o = h[8]
            if o+8 <= len(self.data):
                count, script, keys, size = struct.unpack_from("<4H", self.data, o)
                if count == 2 and script == 8 and script < keys < size and o+size <= len(self.data):
                    self._mark(o+size, "Unassigned data") if o+size not in self._marks else None
                    self._mark(o, "Camera", "camera", [MagField(n, o+2*i, "H") for i, n in enumerate(
                        ("Pointer count", "Script offset", "Keyframe offset", "Track size"))], track_size=size)
                else:
                    self._mark(o, "Camera (invalid header)", note="Camera header failed bounds/layout validation.")
                    self.warnings.append("Invalid embedded camera track")
            else:
                self.warnings.append("Camera header is outside the file")

    def _tim(self):
        self._mark(0, "TIM header", "header", [MagField("Magic", 0), MagField("Flags / depth", 4)])
        if len(self.data) < 8:
            self.warnings.append("Truncated TIM header")
            return
        flags = self._u32(4)
        if flags & 7 > 3:
            self.warnings.append("Unsupported TIM depth")
        p = 8
        for kind in (("CLUT", "palette"), ("Image", "pixels")) if flags & 8 else (("Image", "pixels"),):
            name, typ = kind
            if p+12 > len(self.data):
                self._mark(p, f"{name} (truncated)")
                self.warnings.append(f"Truncated TIM {name} block")
                return
            size = self._u32(p)
            fields = [MagField("Block byte size", p)] + [MagField(n, p+4+2*i, "H") for i, n in enumerate(
                ("VRAM X", "VRAM Y", "Width (16-bit words)", "Height"))]
            self._mark(p, name + " header", "tim_block", fields)
            if size < 12 or p+size > len(self.data):
                self.warnings.append(f"Invalid TIM {name} block size")
                self._mark(p+12, name + " data (truncated)")
                return
            width, height = struct.unpack_from("<HH", self.data, p+8)
            if 12+width*height*2 != size:
                self.warnings.append(f"TIM {name}: dimensions and block length differ")
            self._mark(p+12, name + " data", typ, width=width, height=height, depth=flags & 7)
            p += size
        if p < len(self.data):
            self._mark(p, "Trailing data")

    def _indexed(self):
        """Validated count/directories, with an optional explicit end offset."""
        if len(self.data) < 8:
            return False
        n = self._u32(0)
        if not 1 <= n <= min(4096, (len(self.data)-4)//4):
            return False
        for variant in ("offsets_end", "end_offsets", "offsets"):
            head = 4*(n+1+(variant != "offsets"))
            if head > len(self.data):
                continue
            entries = [self._u32(4+4*i) for i in range(n+(variant != "offsets"))]
            if variant == "offsets":
                offsets, end = entries, len(self.data)
            else:
                offsets, end = (entries[:-1], entries[-1]) if variant == "offsets_end" else (entries[1:], entries[0])
            if offsets[0] != head or not head <= end <= len(self.data):
                continue
            if any(a > b for a, b in zip(offsets, offsets[1:])) or any(not head <= o <= end for o in offsets):
                continue
            self.format = "Indexed MAG container"
            names = ["Part count"] + (["End offset"] if variant == "end_offsets" else [])
            names += [f"Part {i} offset" for i in range(n)]
            if variant == "offsets_end":
                names.append("End offset")
            self._mark(0, "Directory", "directory", [MagField(label, 4*i) for i, label in enumerate(names)])
            for i, offset in enumerate(offsets):
                if offset < end:
                    self._mark(offset, f"Part {i}", "indexed_data",
                               note="Validated directory span; payload-specific semantics are not inferred.")
            if end < len(self.data):
                self._mark(end, "Trailing data")
            return True
        return False

    def _finish(self):
        starts = sorted(self._marks)
        if not starts or starts[0] != 0:
            self._mark(0, "Unassigned data")
            starts = sorted(self._marks)
        for i, start in enumerate(starts):
            end = starts[i+1] if i+1 < len(starts) else len(self.data)
            if end <= start:
                continue
            name, kind, fields, note, meta = self._marks[start]
            fields = [f for f in fields if start <= f.offset and f.offset+f.size <= end]
            self.sections.append(MagSection(name, start, end, kind, fields, note, meta))

    def _model_parts(self):
        """Embedded three-section battle models have a checked seven-word directory."""
        result = []
        for section in self.sections:
            if section.kind not in ("object", "indexed_data") or section.size < 28:
                result.append(section)
                continue
            size, skel, geom, anim, extra, flags, end = struct.unpack_from("<7I", self.data, section.start)
            if not (skel == 28 and geom-skel >= 2 and anim-geom >= 4
                    and size-anim >= 4 and size <= section.size and end == size-4):
                result.append(section)
                continue
            base = section.start
            fields = [MagField(n, base+4*i) for i, n in enumerate(("Model byte size", "Skeleton offset",
                      "Geometry offset", "Animation offset", "Extra / variant field", "Flags / variant field", "End offset"))]
            result.append(MagSection(section.name+" header", base, base+skel, "model_header", fields))
            for name, a, b, kind, fmt in (("Skeleton", skel, geom, "skeleton", "H"),
                                         ("Geometry", geom, anim, "geometry", "I"),
                                         ("Animation", anim, size, "animation", "I")):
                result.append(MagSection(section.name+" "+name, base+a, base+b, kind,
                              [MagField({"Skeleton": "Bone count", "Geometry": "Object count",
                                         "Animation": "Animation count"}[name], base+a, fmt)]))
            if size < section.size:
                result.append(MagSection(section.name+" trailing data", base+size, section.end))
        self.sections = result

    @property
    def script(self):
        return next((s for s in self.sections if s.kind == "script"), None)

    def fields_for(self, section):
        """Named numeric fields, generated only when a section is opened."""
        if section.fields:
            return section.fields
        if section.kind == "palette":
            return [MagField(f"Colour {i} (STP/BGR555)", o, "H")
                    for i, o in enumerate(range(section.start, section.end-1, 2))]
        if section.kind == "object" and section.size >= 0x30:
            h = struct.unpack_from("<12I", self.data, section.start)
            if h[1] == 1 and h[2] == 0x30:
                names = ("Flags", "Type", "Primitive offset", "Unknown", "Unknown", "Vertex offset",
                         "Vertex count", "Normal offset", "Normal count", "Unknown", "Unknown", "Unknown")
                fields = [MagField(n, section.start+4*i) for i, n in enumerate(names)]
                for label, offset, count in (("Vertex", h[5], h[6]), ("Normal", h[7], h[8])):
                    if offset >= 0x30 and offset+8*count <= section.size:
                        fields += [MagField(f"{label} {i} {axis}", section.start+offset+8*i+2*j, "h")
                                   for i in range(count) for j, axis in enumerate(("X", "Y", "Z", "Pad"))]
                return fields
            # Sprite lists are identified conservatively by their bounded end/loop code.
            frames = []
            for i, o in enumerate(range(section.start, section.end-7, 8)):
                relative, duration, code = struct.unpack_from("<ihb", self.data, o)
                if code not in (0, 1, 2):
                    break
                frames += [MagField(f"Frame {i} relative offset", o, "i"),
                           MagField(f"Frame {i} duration", o+4, "h"), MagField(f"Frame {i} control", o+6, "b")]
                if code in (1, 2):
                    return frames
        return []
