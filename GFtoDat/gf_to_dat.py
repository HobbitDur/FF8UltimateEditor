"""Convert every GF summon model that has no battle .dat into a c0m-style monster file.

Generalization of the Shiva pipeline (shiva_build_initial/convert/add_idle_seq_camera/
add_sound/match_slot_layout) into one pass per GF:

  1. Initial 11-section container: summon model sections 1-3 (skeleton/geometry/
     animation) + donor sound sections 9/10 (c0m071, never-empty AKAO rule) + donor
     section 11 placeholder (c0m001, replaced by the texture import).
  2. Texture import through FF8GameData.dat.summontexture logic, extended with a
     MultiTim resolver: the geometry's (tpage, CLUT) references are looked up across
     ALL the TIM files of the GF's mag group, so models whose texture blocks live in
     several files convert too.
  3. Battle-ready shape (the proven crash-free recipe): idle copy at anim 0, pad to
     20 animations, all 13 sequence slots filled (only 2 & 7 empty), camera section
     from c0m001, everything 4-byte aligned by the writer.
  4. Monster name = GF name, file = GFtoDat/<Name>.dat.

Summon model sources (identified by silhouette render, effect_id = mag number + 1):
  Quezacotl mag115_h.07 | Siren mag094_b.2e0 | Pandemona mag290_h.03
  Doomtrain mag190_b.dat | Odin mag186_b.dat | Gilgamesh mag326_g.dat

Not convertible: Ifrit/Bahamut/Cerberus/Alexander/Brothers/Eden/Leviathan (shared
cinematic engine: opcode-VM animation, no keyframes), Carbuncle/Cactuar/Tonberry
(no standard model container in the mag files; they already have c0m dats anyway
except Carbuncle).

Run from the repo root:  .venv/Scripts/python gf_to_dat.py [GFName|all]
"""
import copy
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE = Path(__file__).parent
if not (BASE / "FF8GameData").is_dir():          # script lives in GFtoDat/
    BASE = BASE.parent
OUT_DIR = BASE / "GFtoDat"
BATTLE = BASE / "extracted_files" / "battle"
SOUND_DONOR = BATTLE / "c0m071.dat"
CAMERA_DONOR = BATTLE / "c0m001.dat"

GFS = {
    "Quezacotl": {"model": "mag115_h.07", "tims": "mag115_h.*"},
    "Siren": {"model": "mag094_b.2e0", "tims": "mag094_b.*"},
    "Pandemona": {"model": "mag290_h.03", "tims": "mag290_h.*"},
    "Doomtrain": {"model": "mag190_b.dat", "tims": "mag190_*.dat"},
    "Odin": {"model": "mag186_b.dat", "tims": "mag186_*.dat"},
    # mag217_b (effect 218) and mag326_g (Gilgamesh weapon effects) hold the SAME
    # 69-bone Gilgamesh model (identical skeleton+geometry); mag217_b carries the
    # richer animation set (6 anims vs one 50-frame), so it is the source.
    # There is NO Griever summon model in the extractable data (boss fight only).
    "Gilgamesh": {"model": "mag217_b.dat", "tims": "mag217_*.dat"},
    # The other copy (single 50-frame animation) for comparison.
    "gilgamesh_less_anim": {"model": "mag326_g.dat", "tims": "mag326_*.dat"},
    # Carbuncle's creature is embedded in FF8_EN.exe .data at VA 0x10B6F94
    # (extracted to GFtoDat/carbuncle_model.bin); the body atlas is the second
    # TIM inside magic/Mag277.tim (the pack MAG_278_UNKNOWN_FL loads).
    "Carbuncle": {"model": "carbuncle_model.bin", "tims": "magic/Mag277.tim"},
    # More EXE-embedded creatures (same MAG_089_sub_6EC060 / sub_8DD0F0 spawn
    # patterns; each <name>_model.bin extracted from the .data VA in memory notes):
    "Phoenix": {"model": "phoenix_model.bin",           # VA 0x11B537C, effect 140
                "tims": ["magic/Mag139.tim", "mag139_h.*"]},
    "Moomba": {"model": "moomba_model.bin",             # VA 0x136BB30, effect 338 Friendship
               "tims": [],                              # body fur TIM is EXE-embedded
               "tims_exe": [0x1776698]},
    "MiniMog": {"model": "minimog_model.bin",           # VA 0x152BC04, effect 96 Moogle Dance
                "tims": ["magic/mag095.tim", "mag095*"]},
    # Boko = the 34-bone quartet owned by the ChocoFire/Flare/Meteor/Bocle code
    # (RVA 0x1656de4 xref'd from ChocoBocle's creature setup); body TIM embedded.
    "Boko": {"model": "boko_model.bin",
             "tims": [],
             "tims_exe": [0x1A5BCCC]},
}

# EXE-embedded TIM addresses are in the TIM-scan address space (imagebase 0x400000
# included): file offset = 0x76D000 + (va - 0xF6D000).
EXE_PATH = None  # resolved in load_exe_tims


def load_exe_tims(vas):
    from FF8GameData.dat.summontexture import RawTim
    if not vas:
        return []
    exe = (BASE / "extracted_files" / "FF8_EN.exe").read_bytes()
    return [RawTim(exe[0x76D000 + (va - 0xF6D000):0x76D000 + (va - 0xF6D000) + 0x40000])
            for va in vas]

SEQUENCES = {  # same 13-slot layout that fixed the Shiva ATB crash (anims patched in)
    1: "a3 00 e6 ff",
    3: "00 b8 0d 02 08 b8 0e 02 10 a8 06 a9 e6 ff",
    4: "c3 08 d8 00 01 e5 08 00 a2",
    5: "c3 08 d8 00 01 e5 08 00 a2",
    6: "00 a2",
    8: "a8 01 a0 00 c3 0c e1 23 e5 7f ba c3 7f c5 ff e5 7f e7 f9 c3 08 d9 08 e5 08 a1 a2",
    9: "00 a2",
    10: "bb {atk:02x} a2",
    11: "bb {atk:02x} a2",
    12: "bb {alt:02x} a2",
    13: "00 e6 ff",
}
NB_SEQ = 13
NB_ANIMATIONS = 20


def read_sections(data: bytes):
    nb = struct.unpack_from("<I", data, 0)[0]
    pos = [struct.unpack_from("<I", data, 4 + i * 4)[0] for i in range(nb)]
    fsize = struct.unpack_from("<I", data, 4 + nb * 4)[0]
    bounds = pos + [min(fsize, len(data))]
    return [data[bounds[i]:bounds[i + 1]] for i in range(nb)]


def build_initial(model_path: Path, out_path: Path):
    mag_secs = read_sections(model_path.read_bytes())
    donor_cam = read_sections(CAMERA_DONOR.read_bytes())
    donor_snd = read_sections(SOUND_DONOR.read_bytes())
    sections = [
        mag_secs[0], mag_secs[1], mag_secs[2],   # skeleton / geometry / animation
        b"", b"", b"", b"", b"",                 # dyn-tex / seq / camera / stat / AI
        donor_snd[8], donor_snd[9],              # sound (never-empty AKAO rule)
        donor_cam[10],                           # texture placeholder
    ]
    for i, sec in enumerate(sections):
        if len(sec) % 4:
            raise ValueError(f"section {i + 1} length {len(sec)} not 4-byte aligned")
    out = bytearray()
    out += struct.pack("<I", 11)
    position = 4 + 11 * 4 + 4
    for sec in sections:
        out += struct.pack("<I", position)
        position += len(sec)
    out += struct.pack("<I", position)
    for sec in sections:
        out += sec
    out_path.write_bytes(bytes(out))


class MultiTim:
    """RawTim-compatible resolver over several TIM files: each VRAM request is
    served by whichever TIM actually covers that VRAM location."""

    def __init__(self, raw_tims):
        self.tims = raw_tims

    def pixel_block(self, vram_x_hw, vram_y, w_px, h):
        from FF8GameData.dat.summontexture import SummonTextureError
        for tim in self.tims:
            col = (vram_x_hw - tim.image_x) * 2
            row = vram_y - tim.image_y
            if 0 <= col and 0 <= row and col + w_px <= tim.image_w and row + h <= tim.image_h:
                return tim.pixel_block(vram_x_hw, vram_y, w_px, h)
        raise SummonTextureError(
            f"No TIM in this mag group covers VRAM ({vram_x_hw},{vram_y}) "
            f"({w_px}x{h}) referenced by the geometry.")

    def clut_row(self, clut_id):
        from FF8GameData.dat.summontexture import SummonTextureError, clut_id_to_vram
        x, y = clut_id_to_vram(clut_id)
        for tim in self.tims:
            if x == tim.clut_x and 0 <= y - tim.clut_y < len(tim.clut_rows):
                return tim.clut_rows[y - tim.clut_y]
        raise SummonTextureError(
            f"No TIM in this mag group holds CLUT id 0x{clut_id:04x} = VRAM ({x},{y}).")


def import_summon_multi(enemy, raw_tims) -> int:
    """import_summon_tim with a MultiTim source instead of a single file."""
    from FF8GameData.dat import summontexture as st
    tim = MultiTim(raw_tims)
    groups = st._collect_texture_groups(enemy.geometry_data)
    plan = st._build_conversion_plan(groups)
    tims = []
    id_mapping = {}
    for i, entry in enumerate(plan):
        tpage, clut, half, col = entry["tpage"], entry["clut"], entry["half"], entry["col"]
        page_x_hw = (tpage & 0xF) * st.PAGE_WIDTH_HW
        page_y = ((tpage >> 4) & 1) * st.PAGE_HEIGHT
        pixels = tim.pixel_block(page_x_hw, page_y + half * st.TIM_HEIGHT,
                                 st.TIM_HEIGHT, st.TIM_HEIGHT)
        clut_raw = tim.clut_row(clut)
        new_clut_id = st.vram_to_clut_id(0, st.MONSTER_CLUT_VRAM_Y + i)
        new_tpage = (tpage & 0xFFE0) | ((st.MONSTER_IMAGE_VRAM_X // st.PAGE_WIDTH_HW) + col)
        id_mapping[(tpage, clut)] = (new_clut_id, new_tpage)
        tims.append(st.build_tim_8bpp(
            clut_raw, 0, st.MONSTER_CLUT_VRAM_Y + i, pixels,
            st.MONSTER_IMAGE_VRAM_X + col * st.PAGE_WIDTH_HW, half * st.TIM_HEIGHT,
            st.TIM_HEIGHT, st.TIM_HEIGHT))
    st._patch_geometry_tex_ids(enemy, id_mapping)
    offset = 4 + len(tims) * 4 + 4
    tim_offsets = []
    for t in tims:
        tim_offsets.append(offset)
        offset += len(t)
    enemy.texture_data["nb_texture"] = len(tims)
    enemy.texture_data["tim_offset"] = tim_offsets
    enemy.texture_data["eof_texture"] = offset
    enemy.texture_data["texture_data"] = [{"id": i, "data": bytearray(t)}
                                          for i, t in enumerate(tims)]
    return len(tims)


def load_group_tims(patterns):
    """Load every TIM matched by the pattern(s). Patterns with a '/' resolve from
    extracted_files (e.g. 'magic/Mag277.tim'); others from battle/. Files holding
    several concatenated TIMs (the PC Magxxx.tim packs) yield each of them."""
    from FF8GameData.dat.summontexture import RawTim, SummonTextureError
    if isinstance(patterns, str):
        patterns = [patterns]
    tims = []
    for pattern in patterns:
        root = BASE / "extracted_files" if "/" in pattern else BATTLE
        for f in sorted(root.glob(pattern)):
            data = f.read_bytes()
            offset = 0
            while data[offset:offset + 4] == b"\x10\x00\x00\x00":
                try:
                    tim = RawTim(data[offset:])
                    tims.append(tim)
                    offset += 20 + sum(len(r) for r in tim.clut_rows) \
                        + 12 + tim.image_w * tim.image_h
                except SummonTextureError:
                    break  # 4bpp / paletteless effect textures are never atlases
    return tims


def convert(name: str, game_data) -> Path:
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    cfg = GFS[name]
    out_path = OUT_DIR / f"{name}.dat"
    model_path = OUT_DIR / cfg["model"]
    if not model_path.exists():
        model_path = BATTLE / cfg["model"]
    build_initial(model_path, out_path)

    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(str(out_path), game_data)
    enemy.analyse_loaded_data(game_data)

    nb_tims = import_summon_multi(enemy, load_group_tims(cfg["tims"])
                                  + load_exe_tims(cfg.get("tims_exe")))

    # Idle at 0 = copy of the shortest loop-ish anim (>= 4 frames when possible);
    # showcase (attack) = the longest original animation.
    anims = enemy.animation_data.animations
    frames = [a.get_nb_frame() for a in anims]
    loopish = [i for i, n in enumerate(frames) if n >= 4] or list(range(len(anims)))
    idle_src = min(loopish, key=lambda i: frames[i])
    showcase = 1 + max(range(len(frames)), key=lambda i: frames[i])
    alt = 1 + idle_src
    new_anims = [copy.deepcopy(anims[idle_src])] + anims
    # Pad with a tiny 2-frame stub (not a full idle copy: a 217-frame single-anim
    # GF would otherwise triple the file size for slots nothing should ever play).
    stub = copy.deepcopy(new_anims[0])
    stub.frames = stub.frames[:2]
    stub._recompute_frame_storage_types()
    while len(new_anims) < NB_ANIMATIONS:
        new_anims.append(copy.deepcopy(stub))
    enemy.animation_data.animations = new_anims
    enemy.animation_data.nb_animations = len(new_anims)

    enemy.seq_animation_data['nb_anim_seq'] = NB_SEQ
    enemy.seq_animation_data['seq_animation_data'] = [
        {"id": i,
         "data": bytearray(bytes.fromhex(
             SEQUENCES[i].format(atk=showcase, alt=alt).replace(" ", "")))
         if i in SEQUENCES else bytearray()}
        for i in range(1, NB_SEQ + 1)]

    enemy.section_raw_data[6] = read_sections(CAMERA_DONOR.read_bytes())[5]
    enemy.info_stat_data['monster_name'].set_str(name)

    enemy.write_data_to_file(game_data, str(out_path))
    print(f"{name}: {out_path.name} written ({out_path.stat().st_size} B) — "
          f"{nb_tims} TIMs, anims {frames} -> idle=src{idle_src}, "
          f"attack seq -> anim {showcase}, 20 anims / 13 seqs")
    return out_path


def main():
    sys.path.insert(0, str(BASE))
    from PyQt6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])
    from FF8GameData.gamedata import GameData
    game_data = GameData(str(BASE / "FF8GameData"))
    game_data.load_all()

    targets = sys.argv[1:] or ["all"]
    names = list(GFS) if targets == ["all"] else targets
    failed = []
    for name in names:
        try:
            convert(name, game_data)
        except Exception as ex:
            failed.append(name)
            print(f"{name}: FAILED — {type(ex).__name__}: {ex}")
    if failed:
        sys.exit(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
