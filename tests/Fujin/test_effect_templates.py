"""An effect built part by part (Fujin/effecttemplates.py, Choreography's + tab): from an empty
effect in a free slot, the parts Fujin knows added one after the other - Cure's all together are
Cure exactly, whatever order they come in; some of them a smaller effect that still runs."""
import itertools
import re
import subprocess
from pathlib import Path

import pytest

from Fujin.effectprogram import compile_program, effect_file_text, load_description, new_effect, read_effect_file, write_program
from Fujin.effecttemplates import STARTS, TEMPLATES, addable, build_effect, dependents, empty_effect

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
CURE_ORDER = ["emitter", "ring", "overlay", "glow", "sparkles", "motes", "glints", "files"]


def test_the_parts_and_what_they_need():
    assert addable([]) == ["emitter", "main", "anchor_layout", "cycle_layout", "turned_glyph",
                           "clock", "flash_ring", "aura", "wind", "blind", "stare", "zombie", "flare", "reflect", "berserk", "fire", "thunder", "double", "revive"]   # a start first
    assert addable(["emitter"]) == ["ring", "files"]
    assert set(addable(["emitter", "ring"])) == {"overlay", "glow", "sparkles", "motes", "glints", "files"}
    assert addable(["main"]) == ["main_layout", "rings", "targets", "sprites"]
    assert addable(["anchor_layout"]) == ["anchor_timing"]
    assert dependents(["emitter", "ring", "sparkles", "files"], "ring") == ["ring", "sparkles"]
    assert dependents(["emitter", "ring", "files"], "emitter") == ["emitter", "ring", "files"]
    empty = empty_effect(224, "By hand")
    assert empty["template_parts"] == [] and build_effect(224, "By hand", []) == empty
    with pytest.raises(ValueError):
        build_effect(224, "x", ["emitter", "rings"])                         # two families
    with pytest.raises(ValueError):
        build_effect(224, "x", ["ring"])                                      # no start


def test_every_combination_compiles_and_all_of_a_family_is_its_effect():
    combinations = {"heal_ring": 66, "layouts": 16, "on_target": 2, "per_action_target": 1,
                    "per_action_turned": 2, "per_action_clock": 2, "per_action_ring": 4, "per_action_aura": 4, "per_action_wind": 2,
                    "per_action_flash": 2, "per_action_stare": 2,
                    "per_action_sway": 2, "per_action_burst": 8,
                    "per_action_barrier": 4, "per_action_rays": 64, "per_action_chain": 4, "per_action_bolt": 8, "per_action_runes": 44, "per_action_revive": 8}
    for kind, start in STARTS.items():
        others = [key for key, template in TEMPLATES.items() if template[2] == kind and key != start]
        built = 0
        for n in range(len(others) + 1):
            for combo in itertools.combinations(others, n):
                parts = [start, *combo]
                if all(set(TEMPLATES[part][7]) <= set(parts) for part in parts):
                    compile_program(build_effect(224, "x", parts))
                    built += 1
        assert built == combinations[kind]
        source = TEMPLATES[start][3]
        full = compile_program(build_effect(224, "x", list(reversed([start, *others]))))   # any order
        assert full == compile_program(new_effect(load_description(source), 224, "x"))
    small = build_effect(224, "x", ["emitter", "ring", "sparkles"])
    assert [task["key"] for task in small["tasks"]] == ["emitter", "ring", "sparkle"]
    assert [pool["key"] for pool in small["pools"]] == ["emitters", "particles"]
    assert {param["part"] for param in small["params"]} == {"emitter", "ring", "sparkles"}
    assert "overlay_start" not in compile_program(small) and "param files.texture" not in compile_program(small)
    silent = build_effect(224, "x", ["anchor_layout"])                         # Antidote's layout, no sound
    assert "events" not in silent["director"] and "director_event" not in compile_program(silent)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
def test_cure_rebuilt_by_hand_records_cure_and_a_smaller_one_runs(tmp_path):
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(1) is None:
        pytest.skip("the recorder is not built with FFNx's effect sources")
    exe = EXE.read_bytes()

    def record(effect, tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines()

    drawn = lambda lines: [re.sub(r"^(P|Q \d+) \d+ ", r"\1 0 ", l) for l in lines if l.startswith(("P ", "R "))]
    cure = record(1, "cure")
    by_hand = build_effect(224, "By hand", ["files", "glints", "motes", "sparkles", "glow", "overlay", "ring", "emitter"], exe)
    rebuilt = record(224, "by_hand", f"program={write_program(by_hand, tmp_path / 'by_hand.fxprog')}")
    assert drawn(rebuilt) == drawn(cure) and len(cure) > 10000
    small = build_effect(224, "Ring and sparkles", ["emitter", "ring", "sparkles"], exe)
    lines = record(224, "small", f"program={write_program(small, tmp_path / 'small.fxprog')}")
    assert {int(line.split()[1]) for line in lines if line.startswith("P ")} - {0} == {1, 4}     # the ring, its sparkles


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_built_in_fujin_from_an_empty_slot(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    fujin.select_effect(1)
    assert fujin.create_button.isHidden() and not fujin.choreography.isTabVisible(fujin.choreography.indexOf(fujin.plus_tab))
    assert not fujin.copy_button.isHidden() and fujin.copy_here_button.isHidden()   # New effect from this…
    fujin.select_effect(224)                                                   # a free slot
    assert not fujin.create_button.isHidden() and not fujin.copy_here_button.isHidden() and fujin.copy_button.isHidden()
    assert fujin.create_effect_here("By hand") == 224
    assert fujin.create_button.isHidden() and fujin.tabs.isTabEnabled(2)      # Choreography un-greyed
    assert fujin.choreography.isTabVisible(fujin.choreography.indexOf(fujin.plus_tab))
    assert fujin.effect_list.currentItem().text().endswith("224 — By hand (new effect)")
    # + names the parts as their tabs: one submenu per kind first, a part bringing what it needs
    kinds = [a.menu() for a in fujin.parts_menu().actions() if a.menu()]
    assert [m.title() for m in kinds] == ["Around one target at a time (Cure's kind)",
                                          "Over the whole cast at once (Hypnotize's kind)",
                                          "One layout on the target (Antidote's kind)",
                                          "One per action, on its target (Silence's kind)",
                                          "One per action, turned with its target (Float's kind)",
                                          "One per action, a clock on its target (Haste's kind)",
                                          "One per action, a flash and a ring (Dispel's kind)",
                                          "One per action, at its target's feet (Aura's kind)",
                                          "One per action, a wind on its target (Aero's kind)",
                                          "One per action, left on its target (Blind's kind)",
                                          "From the caster, then on its target (Petrify Stare's kind)",
                                          "One per action, its target swaying (Zombie's kind)",
                                          "One per action, a burst on its target (Flare's kind)",
                                          "One per action, a wall around its target (Reflect's kind)",
                                          "One per action, rays around its target (Berserk's kind)",
                                          "One director per action, flames around its targets (Fire's kind)",
                                          "One per action, a bolt on its target (Thunder's kind)",
                                          "Around one target at a time, runes (Double's kind)",
                                          "Around one target at a time, sparkles rising (Phoenix Down's kind)"]
    names = [a.text().split("\t")[0] for a in kinds[0].actions() if not a.isSeparator()]
    assert names[:4] == ["How the effect starts", "Emitter", "Moving parts", "Ring (with Emitter)"]   # group headers
    assert "Sparkles (with Emitter, Ring)" in names
    assert "Timing" in [a.text().split("\t")[0] for a in kinds[1].actions()]
    assert fujin.effect_program(224) is None                                   # nothing to run yet
    for key in CURE_ORDER:
        assert fujin.add_part(key)
    assert fujin.effect_parts() == CURE_ORDER
    assert compile_program(fujin.descriptions[224]) == compile_program(new_effect(load_description(1), 224, "By hand"))
    assert [tab.part["key"] for tab in fujin.part_tabs] == [part["key"] for part in load_description(1)["parts"]]
    plus = fujin.choreography.indexOf(fujin.plus_tab)
    assert plus == fujin.choreography.count() - 1                              # + stays the last tab
    # a part's tab removes it (right click), with the parts that need it
    ring = fujin.choreography.indexOf(next(tab for tab in fujin.part_tabs if tab.part["key"] == "ring"))
    labels = [action.text() for action in fujin.part_tab_menu(ring).actions()]
    assert labels == ["Remove Ring (and Overlay, Ground glow, Sparkles, Motes, Glints)"]
    assert [tab.part["title"] for tab in fujin.part_tabs][:2] == ["Emitter", "Ring"]   # the tabs' names
    assert fujin.part_tab_menu(fujin.choreography.indexOf(fujin.description_view)) is None
    actions = [a for a in fujin.parts_menu().actions() if not a.isSeparator()]
    sparkles = next(a for a in actions if a.text().startswith("Sparkles\t"))
    assert sparkles.isChecked() and not sparkles.isEnabled()                  # added: ticked
    assert not any(a.menu() for a in actions) and not any(a.text().startswith("Timing") for a in actions)  # one kind
    assert not any("Remove" in a.text() for a in actions)                     # + only adds
    # a part's edited value stays while the part does, goes with it
    fujin.effect_params[224] = {"sparkle.size": 9, "ring.size": 5}
    assert fujin.remove_part("ring", confirm=False)
    assert fujin.effect_parts() == ["emitter", "files"] and fujin.effect_params[224] == {}
    assert fujin.add_part("sparkles") and fujin.effect_parts() == ["emitter", "ring", "sparkles", "files"]   # with the ring
    assert fujin.effect_program(224)
    assert fujin.choreography.indexOf(fujin.plus_tab) == fujin.choreography.count() - 1
    # a free slot can also take a copy of a described effect
    fujin.select_effect(346)
    assert fujin.copy_effect_here(1, "Cure copy") == 346 and fujin.copy_here_button.isHidden()
    assert compile_program(fujin.descriptions[346]) == compile_program(new_effect(load_description(1), 346, "Cure copy"))
    assert not fujin.copy_button.isHidden()                                   # a new effect copies too
    # an effect with no part yet is saved too (the game finds no program in it)
    fujin.select_effect(225)
    assert fujin.create_effect_here("Later") == 225
    assert fujin.save_files(str(tmp_path))
    folder = tmp_path / "FujinEffects"
    later = (folder / "effect_225.fxprog").read_text(encoding="ascii")
    assert later.startswith("# incomplete") and read_effect_file(later)[1]["template_parts"] == []
    other = FujinWidget()
    assert sorted(other.import_effects([str(folder / "effect_224.fxprog"), str(folder / "effect_225.fxprog")])) == [224, 225]
    assert other.effect_parts(224) == ["emitter", "ring", "sparkles", "files"] and other.effect_name(225) == "Later"
    assert effect_file_text(other.descriptions[224], edited=True) == effect_file_text(fujin.descriptions[224], edited=True)


def test_dispel_parts_share_their_particle_task():
    """Dispel's sparkles and circle are one particle task: it stays while either does."""
    ring = build_effect(224, "x", ["flash_ring"])
    assert [task["key"] for task in ring["tasks"]] == ["target"] and not ring["tasks"][0].get("spawns")
    sparkles = build_effect(224, "x", ["flash_ring", "ring_sparkles"])
    assert [task["key"] for task in sparkles["tasks"]] == ["target", "particle"]
    assert [spawn["place"][0] for spawn in sparkles["tasks"][0]["spawns"]] == ["random_around"]
    compile_program(ring)
    compile_program(sparkles)


def test_blind_without_its_flash_keeps_no_flash():
    """Blind without its flash part: no flash level raised, no fades, no director events setting
    the screen flash; its layout, sound and result stay."""
    from Fujin.effectprogram import compile_program
    program = compile_program(build_effect(224, "Blinding", ["blind"]))
    assert "flash_level_raise" not in program and "screen_fade_at" not in program and "director_event" not in program
    assert "layout_engine_at_anchor " in program and "sound_3d_at_position " in program and "heal_action_at " in program
    program = compile_program(build_effect(224, "Blinding", ["blind", "blind_flash"]))
    assert program.count("screen_fade_at ") == 3 and "director_event_first flash_level_clear" in program
