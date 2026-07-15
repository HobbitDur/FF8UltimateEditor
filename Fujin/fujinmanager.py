r"""Data side of Fujin, the magic-animation explorer.

FF8 spell animations are code compiled in FF8_EN.exe (2013 Steam): each effect_id (the
kernel magic entry field +0x04) selects an init function in MagicList_Logic (0xC81774) and a
texture loader in MagicList_TextureLoad (0xC81DB8). The only external files of a regular
spell are its textures in magic.fs (\FF8\Data\Magic\, e.g. magNNN.tim).

Everything Fujin displays comes from a single pre-generated file,
FF8GameData/Resources/json/magic_effect.json, produced in IDA by
Fujin/ResearchScript/dump_magic_effects.py. That file holds, per effect_id: the handler
addresses, the file names each effect loads, and the decompiled pseudocode of the effect's
functions. Fujin does not read the exe itself (the JSON already carries the extracted data,
and pseudocode cannot be recovered from the exe without a decompiler). The effect display
names come from the bundled effect_table.csv.
"""

import csv
import json
import os
import struct

SLOT_COUNT = 400
# Fallback status when magic_effect.json is not present yet (fresh checkout). The JSON, once
# loaded, is authoritative and overrides these.
DEFAULT_FREE_SLOTS = {224, 225} | set(range(346, SLOT_COUNT + 1))
UNDOCUMENTED_SLOTS = set(range(226, 346))


class EffectEntry:
    def __init__(self, effect_id, name):
        self.effect_id = effect_id
        self.name = name                 # friendly name from effect_table.csv
        self.free = effect_id in DEFAULT_FREE_SLOTS
        self.has_data = False            # set once the JSON dump has filled this entry
        self.logic_addr = ""
        self.logic_name = ""
        self.fl_addr = ""
        self.fl_name = ""
        self.files_loaded = []
        self.functions = []             # list of {"addr", "name", "pseudocode"}

    def files_text(self):
        if self.files_loaded:
            return ", ".join(self.files_loaded)
        if self.free:
            return ""
        return "(none / not in data)"


class FujinManager:
    def __init__(self, tool_folder=None, game_data_folder="FF8GameData"):
        if tool_folder is None:
            tool_folder = os.path.dirname(os.path.abspath(__file__))
        self.entries = []
        self.data_loaded = False
        self.data_path = ""
        self.imported_files = {}  # lower-case file name -> full path picked by the user
        self._load_effect_table(os.path.join(tool_folder, "effect_table.csv"))
        self.default_dump_path = os.path.join(game_data_folder, "Resources", "json", "magic_effect.json")
        if os.path.exists(self.default_dump_path):
            try:
                self.load_dump(self.default_dump_path)
            except (ValueError, KeyError, OSError):
                pass

    def _load_effect_table(self, csv_path):
        names = {}
        with open(csv_path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, delimiter=";")
            next(reader)  # header
            for row in reader:
                names[int(row[0])] = row[1]
        for effect_id in range(1, SLOT_COUNT + 1):
            if effect_id in DEFAULT_FREE_SLOTS:
                name = "(free slot)"
            elif effect_id in UNDOCUMENTED_SLOTS:
                name = "Unknown (monster attack / cinematic)"
            else:
                name = names.get(effect_id, "Unknown")
            self.entries.append(EffectEntry(effect_id, name))

    # --- Data (magic_effect.json) --------------------------------------------------------

    def load_dump(self, json_path):
        """Load the effect data produced in IDA by Fujin/ResearchScript/dump_magic_effects.py.
        This is the authoritative source: it fills addresses, files and pseudocode, and marks
        the real free/used state of every slot."""
        with open(json_path, encoding="utf-8") as handle:
            dump = json.load(handle)
        for effect_id_text, data in dump.items():
            effect_id = int(effect_id_text)
            if not 1 <= effect_id <= SLOT_COUNT:
                continue
            entry = self.entries[effect_id - 1]
            entry.has_data = True
            entry.free = bool(data.get("free"))
            if entry.free:
                entry.logic_addr = entry.fl_addr = ""
                entry.files_loaded = []
                entry.functions = []
                continue
            entry.logic_addr = data.get("logic_addr", "")
            entry.logic_name = data.get("logic_name", "")
            entry.fl_addr = data.get("fl_addr", "")
            entry.fl_name = data.get("fl_name", "")
            entry.files_loaded = data.get("files_loaded", [])
            entry.functions = data.get("functions", [])
        self.data_loaded = True
        self.data_path = json_path

    # --- Imported magic files -------------------------------------------------------------

    def import_files(self, paths):
        """Register files picked by the user (from a de-archived magic.fs)."""
        for path in paths:
            self.imported_files[os.path.basename(path).lower()] = path

    def find_imported_tim(self, entry):
        """Full path of the imported TIM of this effect, or empty string. Uses the exact file
        names from the data; falls back to the mag(effect_id-1) rule only if unknown."""
        candidates = [name for name in entry.files_loaded if name.lower().endswith(".tim")]
        if not candidates:
            candidates = ["mag%03d.tim" % (entry.effect_id - 1)]
        for name in candidates:
            path = self.imported_files.get(name.lower())
            if path and os.path.exists(path):
                return path
        return ""

    # --- TIM decoding -----------------------------------------------------------------------

    @staticmethod
    def decode_tim(file_path):
        """Decode a PSX TIM file to (width, height, rgb_bytes). Handles 4/8/16 bpp,
        using the first CLUT when present. Raises ValueError on anything else."""
        with open(file_path, "rb") as handle:
            data = handle.read()
        if len(data) < 8 or struct.unpack_from("<I", data, 0)[0] != 0x10:
            raise ValueError("Not a TIM file (bad magic)")
        flags = struct.unpack_from("<I", data, 4)[0]
        bpp_mode = flags & 3
        has_clut = bool(flags & 8)
        offset = 8

        clut_colors = []
        if has_clut:
            clut_size = struct.unpack_from("<I", data, offset)[0]
            clut_w, clut_h = struct.unpack_from("<HH", data, offset + 8)
            clut_data_offset = offset + 12
            for i in range(clut_w):  # first CLUT row only
                color = struct.unpack_from("<H", data, clut_data_offset + 2 * i)[0]
                clut_colors.append(color)
            offset += clut_size

        struct.unpack_from("<I", data, offset)[0]  # pixel block size
        width_units, height = struct.unpack_from("<HH", data, offset + 8)
        pixels_offset = offset + 12

        def color_to_rgb(color15):
            red = (color15 & 0x1F) << 3
            green = ((color15 >> 5) & 0x1F) << 3
            blue = ((color15 >> 10) & 0x1F) << 3
            return bytes((red, green, blue))

        rgb = bytearray()
        if bpp_mode == 0:  # 4 bpp, width in 16-bit units = 4 pixels each
            width = width_units * 4
            for pixel_index in range(width * height):
                byte = data[pixels_offset + pixel_index // 2]
                palette_index = byte & 0xF if pixel_index % 2 == 0 else byte >> 4
                rgb += color_to_rgb(clut_colors[palette_index]) if clut_colors else bytes((palette_index * 16,) * 3)
        elif bpp_mode == 1:  # 8 bpp, 2 pixels per 16-bit unit
            width = width_units * 2
            for pixel_index in range(width * height):
                palette_index = data[pixels_offset + pixel_index]
                rgb += color_to_rgb(clut_colors[palette_index]) if clut_colors else bytes((palette_index,) * 3)
        elif bpp_mode == 2:  # 16 bpp direct color
            width = width_units
            for pixel_index in range(width * height):
                color = struct.unpack_from("<H", data, pixels_offset + 2 * pixel_index)[0]
                rgb += color_to_rgb(color)
        else:
            raise ValueError("24 bpp TIM not supported")
        return width, height, bytes(rgb)
