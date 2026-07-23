"""Composite character rendering: a character body (dXcYYY) can show its weapon (dXwYYY) in the
SAME 3D viewer, both played on the same animation index. See the CompositeCharacterWeaponAnimation
wiki. The two models are merged into one mesh pushed to the GL widget (weapon vertex indices
offset past the body's, weapon texture ids offset above the body's), reusing the single-model
render path. These tests cover the data merge + the selector wiring (the GL paint itself needs a
real context and is verified visually).
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from FF8GameData.monsterdata import EntityType
from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
BODY = os.path.join(BATTLE, "d0c000.dat")   # Squall body
WEAPON = os.path.join(BATTLE, "d0w000.dat")  # Squall's Revolver gunblade

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(BODY) and os.path.isfile(WEAPON) and os.path.getsize(WEAPON) > 0),
    reason="d0c000.dat / d0w000.dat not available")


def test_character_slot_correspondence():
    assert IfritManager.character_slot_of("d0c000.dat") == "0"
    assert IfritManager.character_slot_of("d0w000.dat") == "0"
    assert IfritManager.character_slot_of("d1c003.dat") == "1"      # Zell
    assert IfritManager.character_slot_of("c0m000.dat") is None      # monster
    # a body and weapon correspond iff their slot digit matches
    assert IfritManager.character_slot_of("d0c000.dat") == IfritManager.character_slot_of("d0w006.dat")
    assert IfritManager.character_slot_of("d0c000.dat") != IfritManager.character_slot_of("d1w008.dat")


@pytest.fixture(scope="module")
def session():
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "weapon_overlay"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda *a: True
    w._build_session([BODY, WEAPON])
    names = [os.path.basename(f['path']) for f in w._files]
    w._activate_index(names.index("d0c000.dat"))
    pane = w._files[names.index("d0c000.dat")]['pane']
    return w, pane


def test_weapon_auto_paired_and_listed(session):
    _, pane = session
    sel = pane._3d_widget.weapon_selector
    labels = [sel.itemText(i) for i in range(sel.count())]
    assert labels[0].startswith("None")
    assert "d0w000.dat" in labels
    # auto-defaults to the character's first weapon, not None
    assert sel.currentText() == "d0w000.dat"
    assert pane._3d_widget._weapon_manager is not None
    assert pane._3d_widget._weapon_manager.enemy.entity_type == EntityType.WEAPON


def test_merged_mesh_is_body_plus_weapon(session):
    _, pane = session
    w3d = pane._3d_widget
    gl = w3d.gl_widget
    nb_body_v = len(pane.ifrit_manager.enemy.geometry_data.get_vertices())
    nb_weap_v = len(w3d._weapon_manager.enemy.geometry_data.get_vertices())
    assert len(gl.vertices) == nb_body_v + nb_weap_v
    # the weapon's faces reference vertices past the body's block
    max_idx = max(i for tri in gl.triangles for i in tri)
    assert max_idx >= nb_body_v
    # texture atlas covers both models with no out-of-range index
    assert gl._tex_id_to_index
    assert max(gl._tex_id_to_index.values()) < len(gl._pending_qpixmaps)


def test_selector_toggles_body_only_and_back(session):
    _, pane = session
    w3d = pane._3d_widget
    gl = w3d.gl_widget
    nb_body_v = len(pane.ifrit_manager.enemy.geometry_data.get_vertices())

    w3d.weapon_selector.setCurrentIndex(0)               # None (body only)
    assert w3d._weapon_manager is None
    assert len(gl.vertices) == nb_body_v

    w3d.weapon_selector.setCurrentIndex(1)               # back to the weapon
    assert w3d._weapon_manager is not None
    assert len(gl.vertices) > nb_body_v


def test_weapon_is_placed_by_its_own_animation_root(session):
    """The game's placement rule (ProcessFieldEntitiesTransformation @0x508C90): each model's
    root bone world translation = model_scale * its OWN per-frame root_pos >> 8. The weapon's
    clip carries a different root track than the body's - that difference IS the in-hand offset
    (no hand-bone attach exists in the files). The viewer applies only the body's root globally,
    so the merged weapon vertices are shifted by (weapon_root - body_root) * 1.6 (get_pos_world is
    raw/204.8, vertices are raw/128 - calibrated on full attack swings of Squall/Seifer/Irvine,
    grip-to-hand-bone std 0.004). The Z mirror between the two spaces is no longer applied here:
    it lives in PositionType.AXIS_SCALE, so get_pos_world already returns vertex-space signs and
    the three axes scale alike. The placement is the same either way - only where the sign
    comes from changed."""
    _, pane = session
    w3d = pane._3d_widget
    w3d.weapon_selector.setCurrentIndex(1)      # make sure the weapon is shown
    gl = w3d.gl_widget
    nb_body = w3d._body_vertex_count

    wm = w3d._weapon_manager
    raw = wm.get_animated_vertices(anim_id=0, frame_id=0, next_frame_id=1, step=0.0)
    raw_centroid = [sum(v[i] for v in raw) / len(raw) for i in range(3)]

    def root(mgr):
        fr = mgr.enemy.animation_data.animations[0].frames[0]
        return [fr.position[i].get_pos_world() for i in range(3)]

    d = [w - b for w, b in zip(root(wm), root(pane.ifrit_manager))]
    s = w3d._ROOT_DELTA_TO_VERTEX_SCALE
    expected = [s * d[axis] for axis in range(3)]
    shown = gl.vertices[nb_body:]
    shown_centroid = [sum(v[i] for v in shown) / len(shown) for i in range(3)]
    for axis in range(3):
        assert abs(shown_centroid[axis] - (raw_centroid[axis] + expected[axis])) < 0.05
    # And the offset is real - Squall never holds the gunblade at his root.
    assert max(abs(x) for x in expected) > 0.5


def test_weapon_grip_tracks_the_hand_through_a_swing(session):
    """The decisive property of the calibrated mapping: through a full attack swing, some grip
    vertex of the placed weapon stays at a near-constant offset from the body's hand bone (the
    weapon rides the hand). With a wrong axis mapping or scale this cannot hold - the best std
    across a 5-unit arc degrades by an order of magnitude."""
    _, pane = session
    w3d = pane._3d_widget
    w3d.weapon_selector.setCurrentIndex(1)
    gl = w3d.gl_widget
    nb_body = w3d._body_vertex_count
    hand_bone = 22                       # Squall right-hand tip
    w3d.set_animation(30)                # the widest swing (root-delta range ~4.9 units)

    # Per frame, per weapon vertex: scalar DISTANCE to the hand bone. The wrist rotates through
    # the swing, so the hand->grip offset vector rotates with it - but its LENGTH stays constant
    # for the vertex actually riding the hand. (A vector-offset variance test would fail even for
    # a perfect grip.)
    per_frame = []
    mats_of = pane.ifrit_manager._get_bone_matrices
    nf = pane.ifrit_manager.enemy.animation_data.animations[30].get_nb_frame()
    for f in range(0, nf, 4):
        w3d.set_frame(f)
        m = mats_of(30, f)[hand_bone]
        hand = (m.M41, m.M42, m.M43)
        per_frame.append([((v[0] - hand[0]) ** 2 + (v[1] - hand[1]) ** 2
                           + (v[2] - hand[2]) ** 2) ** 0.5 for v in gl.vertices[nb_body:]])
    nverts = len(per_frame[0])
    best = None
    for v in range(nverts):
        ds = [fr[v] for fr in per_frame]
        mean = sum(ds) / len(ds)
        std = (sum((d - mean) ** 2 for d in ds) / len(ds)) ** 0.5
        best = std if best is None or std < best else best
    assert best < 0.05, f"no weapon vertex rides the hand (best distance-std {best:.3f})"


def test_zell_reduced_weapon_rides_the_body_hand_bones():
    """Zell/Kiros use the reduced weapon form (WEAPON_NO_ANIM): no skeleton or animation of its
    own - the glove/blade mesh is skinned directly to the CHARACTER BODY's bones (d1w008: all 62
    verts on body hand bones 21/22, one glove per hand), so it is posed by the body's own
    animation with no root delta and no independent movement. In-game these characters draw no
    separate weapon model (initWeaponAnim NULLs weaponAnimHeader) precisely because the mesh
    belongs to the body's skeleton."""
    body = os.path.join(BATTLE, "d1c003.dat")
    glove = os.path.join(BATTLE, "d1w008.dat")
    if not (os.path.isfile(body) and os.path.isfile(glove)):
        pytest.skip("Zell files not available")
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "zell_overlay"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda *a: True
    w._build_session([body, glove])
    names = [os.path.basename(f['path']) for f in w._files]
    zi = names.index("d1c003.dat")
    w._activate_index(zi)
    pane = w._files[zi]['pane']
    w3d = pane._3d_widget
    # offered and auto-selected
    items = [w3d.weapon_selector.itemText(i) for i in range(w3d.weapon_selector.count())]
    assert "d1w008.dat" in items
    assert w3d.weapon_selector.currentText() == "d1w008.dat"
    # merged, and the glove hugs BOTH hand bones (one glove per hand)
    gl = w3d.gl_widget
    nbb = w3d._body_vertex_count
    glove_verts = gl.vertices[nbb:]
    assert len(glove_verts) == 62
    mats = pane.ifrit_manager._get_bone_matrices(0, 0)
    for b in (21, 22):
        hand = (mats[b].M41, mats[b].M42, mats[b].M43)
        dmin = min(((v[0] - hand[0]) ** 2 + (v[1] - hand[1]) ** 2 + (v[2] - hand[2]) ** 2) ** 0.5
                   for v in glove_verts)
        assert dmin < 1.2, f"glove should hug hand bone {b} (nearest vert {dmin:.2f})"


def test_monster_has_no_weapon_selector():
    """A monster/weapon body must not get the composite selector (character bodies only)."""
    monster = os.path.join(BATTLE, "c0m000.dat")
    if not os.path.isfile(monster):
        pytest.skip("c0m000.dat not available")
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "weapon_overlay_monster"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda *a: True
    w._build_session([monster])
    pane = w._files[0]['pane']
    # no options populated -> single-model viewer, weapon manager stays None
    assert pane._3d_widget._weapon_manager is None
