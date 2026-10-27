"""The shared sequence preview: the sequence RUN, on the real model, next to its timeline.

One panel is docked on the right of the Sequence tab and reused for every sequence -
clicking a sequence's ▶ Preview loads it here (same pattern as the camera tab's
CameraPreviewPanel). Top to bottom: the 3D model playing the sequence, the transport
(play/pause, step, speed, loop), the graphical timeline (which is also the scrub bar),
what runs on the current frame, and the bake's summary/assumptions. A "Text" toggle shows
the same timeline as the readable HTML table, for when order matters more than timing.

The 3D playback is driven by sequencebake, not by re-reading the byte-code here: each
battle frame of the BakeResult says which animation frame the model draws and what the
sequence has done to the entity's own transform - position (95, E5 0D/0E/0F), Y rotation
(E5 17), scale (E5 24-27), hidden model parts (E5 20). _SequencePosedViewer applies that
pose on top of the ordinary Ifrit3D frame, so what plays here is what the interpreter
says happens, on the frame it says it happens.

What the pose is exact about and what it approximates:
  - animation frame timing is exact (it IS the bake's timing);
  - position/rotation/scale come from the interpreter's state. Raw position units map to
    viewer units through PositionType.AXIS_SCALE, the same convention the per-frame root
    position uses - the sequence writes the same entity fields the root animation feeds;
  - the Y rotation is applied about the entity origin in the viewer's mirrored axes
    (engine yaw Ry(-θ) conjugated through AXIS_SCALE's X mirror comes out as Ry(+θ) here);
    the animation's own root offset is translated but not rotated with it - exact for the
    monsters that turn in place (root at the origin), approximate for the few that don't;
  - hidden parts collapse the part's vertices (a zero-area face draws nothing), which
    needs no change to the static index lists pushed at load.
"""
import math
import os
import re

from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QBuffer, QByteArray, QUrl,
                          QLoggingCategory)
from PyQt6.QtGui import QKeySequence, QShortcut, QBrush, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QCheckBox, QScrollArea, QSizePolicy, QTextEdit,
                             QTreeWidget, QTreeWidgetItem)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.monsterdata import PositionType
from FF8GameData.dat.sequencetimeline import (format_timeline_html, assumption_list,
                                              COLOUR_BY_KIND)
from FF8GameData.dat.sequencebake import (BattleContext, EVENT_EFFECT,
                                          SPECIAL_VAR_GLOSSARY, special_var_name,
                                          state_flags_text, STATE_FLAG_NAME)
from FF8GameData.dat.sequencesound import SequenceSoundResolver, SOUND_OP_CODES
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Ifrit.IfritSeq.seqtimelinewidget import SequenceTimelineWidget
from Julia.juliamanager import JuliaManager

# Sound playback is optional: without the Qt multimedia plugin the preview still runs,
# only its sound toggle is disabled (same soft dependency Julia has).
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    # Keep debug/info chatter quiet (see Julia), retaining warnings and errors.
    # QT_LOGGING_RULES still overrides this for debugging.
    QLoggingCategory.setFilterRules("qt.multimedia.ffmpeg*.debug=false\nqt.multimedia.ffmpeg*.info=false")
    _MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the installed Qt build
    _MULTIMEDIA_AVAILABLE = False

_PSX_ONE = 4096   # the engine's fixed-point 1.0: a full turn, and the neutral scale


def pose_vertices(vertex_list, frame, object_range_list, neutral_scale=_PSX_ONE):
    """Apply a SequenceFrame's pose to the model's posed vertices (see the module doc).

    Pure on purpose (list in, list out, no Qt/GL): this is the one piece of 3D math the
    preview adds, so it is the piece worth testing headless.
    """
    hidden_mask = frame.hidden_part_mask
    if hidden_mask:
        vertex_list = list(vertex_list)
        for part_index, (start, end) in enumerate(object_range_list):
            if hidden_mask & (1 << part_index):
                # Zero-area faces draw nothing: collapsing the part's vertices hides it
                # without touching the constant triangle/quad index lists.
                vertex_list[start:end] = [(0.0, 0.0, 0.0)] * (end - start)

    model_factor = frame.scale[0] / neutral_scale if neutral_scale else 1.0
    factor_x = model_factor * (frame.scale[1] / neutral_scale if neutral_scale else 1.0)
    factor_y = model_factor * (frame.scale[2] / neutral_scale if neutral_scale else 1.0)
    factor_z = model_factor * (frame.scale[3] / neutral_scale if neutral_scale else 1.0)

    angle = (frame.rotation_y & 0xFFF) * 2.0 * math.pi / _PSX_ONE
    if factor_x == 1.0 and factor_y == 1.0 and factor_z == 1.0 and angle == 0.0:
        return vertex_list
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    posed = []
    for x, y, z in vertex_list:
        x *= factor_x
        y *= factor_y
        z *= factor_z
        posed.append((x * cos_a + z * sin_a, y, -x * sin_a + z * cos_a))
    return posed


def sequence_position_world(position_raw):
    """The sequence-written entity position, raw engine units -> viewer units, through the
    same per-axis mapping the animation root position uses (PositionType.AXIS_SCALE)."""
    return tuple(position_raw[axis] * PositionType.AXIS_SCALE[axis] for axis in range(3))


def _consumer_destination(command):
    """The value's destination as a short name: the E5 target, or None for a jump."""
    if command.op_code != 0xE5:
        return None
    if command.parameters:
        return special_var_name(command.parameters[0])
    return "an E5 write"


def find_value_consumer(result, frame_index):
    """(command, when) for what consumes the value standing at the end of `frame_index`,
    from the run's own dataflow. `when` is "past" (an E5/conditional jump AFTER the
    frame's last C0-C3 assignment already used exactly this value), "future" (the next
    executed consumer, the bake having followed every jump), "replaced" (an assignment
    overwrites it unused) or "unused"; command is None for the last two."""
    consumer = None
    for command in result.frame_list[frame_index].command_list:
        if command.is_background:
            continue
        op_code = command.op_code
        if 0xC0 <= op_code <= 0xC3:
            consumer = None   # a new value starts; earlier consumers took the old one
        elif op_code == 0xE5 or (0xE6 <= op_code <= 0xF3
                                 and (op_code - 0xE6) % 7 != 0):
            consumer = command
    if consumer is not None:
        return consumer, "past"
    for frame in result.frame_list[frame_index + 1:]:
        for command in frame.command_list:
            if command.is_background:
                continue
            op_code = command.op_code
            if 0xC0 <= op_code <= 0xC3:
                return None, "replaced"
            if op_code == 0xE5 or (0xE6 <= op_code <= 0xF3
                                   and (op_code - 0xE6) % 7 != 0):
                return command, "future"
    return None, "unused"


def current_value_story(result, frame_index) -> str:
    """current_value as a story, not a number: the FORMULA that built it (battle reads
    shown as name(value)) and what it is for - `pos_y ← e5[2](-2400) * anim_frame(3) /
    anim_total(5) = -1440` explains a jump arc where `current_value = -1440` explains
    nothing."""
    frame = result.frame_list[frame_index]
    value = frame.current_value
    expression = frame.value_expression
    # "5 = 5" says nothing: only show the formula when it computes something.
    formula = (f"{expression} = {value}" if expression and expression != str(value)
               else str(value))
    consumer, when = find_value_consumer(result, frame_index)
    if when == "past":
        # The consuming command's own value note already tells this story in the
        # command list: no separate register line needed.
        return ""
    if when == "future":
        destination = _consumer_destination(consumer)
        target = (f"will go to {destination}" if destination is not None
                  else "decides the next conditional jump")
        return f"value = {formula} — {target}"
    # Dead register: nothing downstream reads this value (every write that mattered is
    # already told on its own command line above).
    return f"value = {formula} — leftover, nothing reads it"


def frame_anim_text(frame) -> str:
    """The one-line animation state of a frame, for the label above the chain tree."""
    if frame.anim_id is None:
        return ""
    text = f"anim {frame.anim_id}"
    if frame.anim_total:
        text += f" [{frame.anim_frame}/{frame.anim_total}]"
    if frame.is_waiting_animation:
        text += " (waiting for it to end)"
    return text


class FrameChain:
    """One OUTCOME of a frame, folded from the raw command stream: an action (sound,
    anim, effect...), or a value chain - the arithmetic ops that built a value, headed
    by what it became ("pos_y ← formula = v", "if > 0 → taken"). The raw ops live in
    op_lines, shown only when the user expands the chain."""

    __slots__ = ("kind", "headline", "target_frame", "op_lines")

    def __init__(self, kind, headline, target_frame=None, op_lines=()):
        self.kind = kind                  # a bake event kind, or "value"
        self.headline = headline
        self.target_frame = target_frame  # frame a stored slot is next read on, or None
        self.op_lines = list(op_lines)


_TARGET_FRAME_PATTERN = re.compile(r"used from frame (\d+)")


def build_frame_chains(frame, sound_resolver=None, value_story="") -> list:
    """Fold a frame's commands into FrameChains (see the class doc).

    The plumbing (scratch writes, intermediate arithmetic) accumulates until a command
    with a value note closes the chain; action commands pass through as their own
    chains, in order. Ops left pending at the end of the frame - a value still in the
    register - close on the register's own story (value_story)."""
    chain_list = []
    pending_ops = []
    for command in frame.command_list:
        if command.is_background:
            continue
        if command.op_code >= 0xC0:   # the VM: arithmetic, writes, jumps
            op_line = (f"{command.op_code:02X} "
                       f"{command.description or ''}").strip()
            pending_ops.append(op_line)
            if command.value_note:
                match = _TARGET_FRAME_PATTERN.search(command.value_note)
                chain_list.append(FrameChain(
                    "value", command.value_note,
                    int(match.group(1)) if match else None, pending_ops))
                pending_ops = []
        else:                          # an action: its own line, like before
            description = command.description or f"op {command.op_code:02X}"
            if sound_resolver is not None and command.op_code in SOUND_OP_CODES:
                audio_id = sound_resolver.resolve(command.op_code, command.parameters)
                description += (f" → audio {audio_id}" if audio_id is not None
                                else " → empty sound slot")
            chain_list.append(FrameChain(command.kind, description))
    if pending_ops:
        headline = value_story or f"value = {frame.current_value}"
        chain_list.append(FrameChain("value", headline, None, pending_ops))
    return chain_list


def ability_name(game_data, type_id, ability_id) -> str:
    """The name of a monster ability entry ({type, id}), resolved through the json the
    type points at (2 = kernel magic, 4 = item, 8 = the monster special-ability list)."""
    try:
        if type_id == 2:
            entry_list = game_data.magic_data_json.get("magic", [])
        elif type_id == 4:
            entry_list = game_data.item_data_json.get("items", [])
        elif type_id == 8:
            entry_list = game_data.enemy_abilities_data_json.get("abilities", [])
        else:
            return ""
        for entry in entry_list:
            if entry.get("id") == ability_id:
                return entry.get("name", "")
    except (AttributeError, TypeError):
        pass
    return ""


def sequence_attack_names(game_data, enemy, seq_id) -> list:
    """What BB ("print attack name") would display while sequence `seq_id` plays: the
    names of the monster abilities whose `animation` field queues this sequence."""
    name_list = []
    info = getattr(enemy, "info_stat_data", None) or {}
    for key in ("abilities_low", "abilities_med", "abilities_high"):
        for entry in info.get(key) or []:
            if not isinstance(entry, dict) or entry.get("animation") != seq_id:
                continue
            name = ability_name(game_data, entry.get("type"), entry.get("id"))
            if name and name not in name_list:
                name_list.append(name)
    return name_list


def monster_battle_text(enemy, text_index) -> str:
    """The monster's own battle text `text_index` (section 8), what 0x91 displays."""
    try:
        text_list = enemy.battle_script_data.get("battle_text") or []
        return text_list[text_index].get_str().strip("\x00")
    except (AttributeError, IndexError, TypeError):
        return ""


def fire_signal_command(frame):
    """The E5 08 write that raised the 0x20 "fire" bit the parallel effect code waits
    on - the missile/beam launches here even though no effect op ran (c0m001 seq 12).
    Only the frame's LAST flags write counts: the end-of-frame value (all this frame
    exposes) belongs to it, and a frame often also carries the handshake's XOR-off
    write just before it."""
    if not frame.current_value & 0x20:
        return None
    last = None
    for command in frame.command_list:
        if (not command.is_background and command.op_code == 0xE5
                and command.parameters[:1] == b"\x08"):
            last = command
    return last


def build_overlay_texts(result, attack_name_of_seq, battle_text_of,
                        effect_hold_frames=8) -> list:
    """One (banner, effect notice) pair per battle frame: the readable side of the run.

    - BB shows the attack name (banner semantics: it stays up once printed);
    - 0x91 shows the monster's battle text (replacing the banner);
    - an effect command - or the flag-0x20 fire signal - sets a transient notice.
    Precomputed for the WHOLE bake so scrubbing anywhere shows the right state, instead
    of an accumulator that only playback keeps consistent.
    """
    overlay_list = []
    banner = ""
    effect_line = ""
    effect_left = 0
    for frame in result.frame_list:
        fire_command = fire_signal_command(frame)
        for command in frame.command_list:
            if command.is_background:
                continue
            if command.op_code == 0xBB:
                name_list = attack_name_of_seq(command.seq_id)
                banner = " / ".join(name_list) if name_list else "(attack name)"
            elif command.op_code == 0x91 and command.parameters:
                text = battle_text_of(command.parameters[0])
                banner = text or f"(monster text {command.parameters[0]})"
            elif command.kind == EVENT_EFFECT:
                effect_line = "✦ effect playing: " + (command.description or
                                                      f"op {command.op_code:02X}")
                effect_left = effect_hold_frames
            elif command is fire_command:
                effect_line = "✦ effect fire signal (flag 0x20)"
                effect_left = effect_hold_frames
        overlay_list.append((banner, effect_line if effect_left > 0 else ""))
        if effect_left > 0:
            effect_left -= 1
    return overlay_list


def relevant_watch_variables(result) -> list:
    """The variables worth a watch row for THIS bake: (name, extractor) pairs, keeping
    only what is ever non-zero or changes - most sequences touch a handful of the 16
    slots, and 16 rows of constant zeros would bury them."""
    candidate_list = [("state_flags", lambda frame: frame.state_flags)]
    for slot in range(8):
        candidate_list.append((f"e5[{slot}]",
                               lambda frame, s=slot: frame.local_value_list[s]))
    for slot in range(8):
        candidate_list.append((f"save[{slot}]",
                               lambda frame, s=slot: frame.saved_value_list[s]))
    candidate_list += [("current_value", lambda frame: frame.current_value),
                       ("offset lat/vert/fwd", lambda frame: frame.position),
                       ("move x/z", lambda frame: (frame.move_position[0],
                                                   frame.move_position[2])),
                       ("rotation_y", lambda frame: frame.rotation_y),
                       ("scale", lambda frame: frame.scale),
                       ("hidden parts", lambda frame: frame.hidden_part_mask)]
    kept = []
    for name, extract in candidate_list:
        value_list = [extract(frame) for frame in result.frame_list]
        first = value_list[0] if value_list else 0
        if any(value != first for value in value_list) or (
                first not in (0, (0, 0, 0), (0, 0))
                and name not in ("scale",)):   # neutral scale is constant noise
            kept.append((name, extract))
    return kept


def build_watch_rows(result, frame_index, variable_list) -> list:
    """[(name, value text, changed since the previous frame)] for the watch panel.

    The flags render with their bit names (state_flags_text); everything else as-is.
    `changed` drives the highlight that makes a scrub READ as a flow of changes.
    """
    frame = result.frame_list[frame_index]
    previous = result.frame_list[frame_index - 1] if frame_index > 0 else None
    row_list = []
    for name, extract in variable_list:
        value = extract(frame)
        text = state_flags_text(value) if name == "state_flags" else str(value)
        changed = previous is not None and extract(previous) != value
        row_list.append((name, text, changed))
    return row_list


class _GameFontBanner:
    """The overlay banner drawn with the game's OWN font (sysfnt.TEX glyphs at the
    engine's metrics) in a menu-style gradient box - the closest the preview can get to
    the in-game attack-name window. The font is loaded from the folder the caller names
    (the panel derives it from a registry-opened file, never from a guessed layout);
    without one, render() returns None and the overlay stays a plain label."""

    _SCALE = 2            # sysfnt glyphs are 12px, tiny at modern sizes
    _PAD_X, _PAD_Y = 10, 6

    def __init__(self, game_data):
        self._game_data = game_data
        self._atlas_by_folder = {}    # menu folder -> FontAtlas or None (load failed)
        self._metrics = None
        self._cache = {}              # (folder, text) -> QPixmap or None

    def _atlas_for(self, folder):
        if folder not in self._atlas_by_folder:
            try:
                from FF8GameData.font.atlas import FontAtlas
                from FF8GameData.font.textlayout import FontMetrics
                self._atlas_by_folder[folder] = FontAtlas.from_folder(folder)
                self._metrics = FontMetrics.from_folder(folder)
            except Exception:
                self._atlas_by_folder[folder] = None
        return self._atlas_by_folder[folder]

    def render(self, text, menu_folder):
        """QPixmap of `text` in the game's font and window style, or None."""
        if not menu_folder or self._game_data is None:
            return None
        self._atlas = self._atlas_for(menu_folder)
        if self._atlas is None:
            return None
        key = (menu_folder, text)
        if key in self._cache:
            return self._cache[key]
        try:
            pixmap = self._render_uncached(text)
        except Exception:   # a banner is a convenience, never a reason to fail a frame
            pixmap = None
        self._cache[key] = pixmap
        return pixmap

    def _render_uncached(self, text):
        from PIL import Image
        from PyQt6.QtGui import QImage, QPixmap
        from FF8GameData.font.textlayout import layout_text
        layout = layout_text(text, self._game_data, self._metrics)
        width = max(layout.max_width, 1) + 2 * self._PAD_X
        height = layout.height + 2 * self._PAD_Y
        image = Image.new("RGBA", (width, height))
        # The menu window look: a vertical dark blue-gray gradient under a light border.
        for row in range(height):
            shade = 1.0 - 0.55 * row / max(height - 1, 1)
            image.paste((int(24 * shade + 8), int(24 * shade + 8),
                         int(64 * shade + 24), 235), (0, row, width, row + 1))
        border = (140, 140, 168, 255)
        image.paste(border, (0, 0, width, 1))
        image.paste(border, (0, height - 1, width, height))
        image.paste(border, (0, 0, 1, height))
        image.paste(border, (width - 1, 0, width, height))
        self._atlas.draw_layout(image, layout, origin_x=self._PAD_X,
                                origin_y=self._PAD_Y)
        image = image.resize((width * self._SCALE, height * self._SCALE),
                             Image.Resampling.NEAREST)
        qt_image = QImage(image.tobytes("raw", "RGBA"), image.width, image.height,
                          QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qt_image.copy())


class _SequencePosedViewer(Ifrit3DWidget):
    """Ifrit3D's viewer plus the pose a sequence gives the entity on one battle frame,
    and optionally a COMPANION model (a party character standing where the target is,
    for real distance reading). The companion rides the weapon-overlay machinery - the
    one path that already merges a second model's faces and textures - but posed
    statically (its idle frame 0) at the target spot instead of following the body."""

    def __init__(self, ifrit_manager):
        super().__init__(ifrit_manager, show_controls=False)
        self._pose_frame = None
        self._object_range_list = None
        self._companion = None            # IfritManager of the stand-in character
        self._companion_offset = (0.0, 0.0, 0.0)   # viewer units, the target spot

    def set_companion(self, manager):
        """Show `manager`'s model as the target stand-in (None clears it)."""
        self._companion = manager
        if manager is not None:
            manager._ensure_matrices()
        self._weapon_manager = manager     # reuse the merge machinery
        self._refresh_static_geometry()
        self.update_animated_mesh()

    def set_companion_offset(self, offset):
        self._companion_offset = tuple(offset)
        if self._companion is not None:
            self.update_animated_mesh()

    def _current_weapon_verts(self):
        if self._companion is None:
            return super()._current_weapon_verts()
        enemy = self._companion.enemy
        if getattr(enemy.animation_data, "nb_animations", 0):
            vertex_list = self._companion.get_animated_vertices(anim_id=0, frame_id=0)
        else:
            vertex_list = enemy.geometry_data.get_vertices()
        offset_x, offset_y, offset_z = self._companion_offset
        # Turned half a circle so it faces the monster it stands against.
        return [(-x + offset_x, y + offset_y, -z + offset_z)
                for (x, y, z) in vertex_list]

    def set_pose_frame(self, frame):
        """The SequenceFrame whose pose to draw (None = plain viewer behaviour)."""
        self._pose_frame = frame

    def _object_ranges(self):
        if self._object_range_list is None:
            range_list = []
            start = 0
            for object_data in self.ifrit_manager.enemy.geometry_data.object_data:
                nb_vertex = len(object_data.get_vertices())
                range_list.append((start, start + nb_vertex))
                start += nb_vertex
            self._object_range_list = range_list
        return self._object_range_list

    def update_animated_mesh(self):
        if self.gl_widget is None:
            return
        vertex_list = self._current_body_verts()
        self.current_animated_vertices = vertex_list
        if self._pose_frame is not None:
            vertex_list = pose_vertices(vertex_list, self._pose_frame,
                                        self._object_ranges())
        if self._weapon_manager is not None:
            vertex_list = list(vertex_list) + list(self._current_weapon_verts())
        self.gl_widget.set_vertices(vertex_list)
        self.gl_widget.update()

    def _update_model_translation(self):
        if self.gl_widget is None:
            return
        super()._update_model_translation()
        if self._pose_frame is None:
            return
        base = self.gl_widget.model_translation
        # Two layers, like the engine keeps them: the VM's position vector (E5 0D/0E/0F)
        # on top of the 9E transport. The VM vector is ENTITY-LOCAL (the engine rotates
        # it by the entity's own matrix before applying - see sequencebake), so it turns
        # with the yaw exactly as the vertices do; the 9E transport is world-frame.
        offset = sequence_position_world(self._pose_frame.position)
        angle = ((self._pose_frame.rotation_y & 0xFFF) * 2.0 * math.pi / _PSX_ONE)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        offset = (offset[0] * cos_a + offset[2] * sin_a, offset[1],
                  -offset[0] * sin_a + offset[2] * cos_a)
        move = sequence_position_world(self._pose_frame.move_position)
        self.gl_widget.set_model_translation(base[0] + offset[0] + move[0],
                                             base[1] + offset[1] + move[1],
                                             base[2] + offset[2] + move[2])


class SequencePreviewPanel(QWidget):
    """Shared preview panel; call preview(seq_id) to run one sequence here.

    `bake_provider(seq_id) -> BakeResult` is handed in by the tab that owns the file -
    running a sequence needs every sequence of the file (A7/A2 chain into the others) and
    the animation lengths, which this panel does not hold. The provider reads the widgets'
    CURRENT bytes, so the preview follows the edit being typed, not the last save.
    """

    closed = pyqtSignal()

    _BATTLE_FPS = 15   # the rate the engine runs sequence frames at
    _SPEED_LIST = [("0.25×", 0.25), ("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0)]

    def __init__(self, ifrit_manager, bake_provider, parent=None, file_registry=None):
        super().__init__(parent)
        self.ifrit_manager = ifrit_manager
        self._bake_provider = bake_provider
        # The shared file bank. Side files go THROUGH it, never around it: an audio.fmt
        # opened here shows in the Opened-files panel and loads into Julia too, and one
        # Julia already opened is picked up here - no guessed folder layout anywhere.
        self._file_registry = file_registry if file_registry is not None else FileRegistry()
        self.setMinimumWidth(340)
        self._view = None          # _SequencePosedViewer, created lazily on first preview
        self._needs_model_reload = True
        self._seq_id = None
        self._result = None
        self._frame_index = 0
        # Real-battle placement: the shared battle setup (an encounter of the bank's
        # scene.out, the party, the model the sequence walks to) and the context override
        # built from it (None = the plain defaults). Read by the tab's bake provider, so
        # the whole run uses the real distance.
        self.battle_context = None
        # Sound: the archive (audio.fmt/audio.dat via JuliaManager) is shared by every
        # sound; the resolver maps THIS entity's B5/B6 local ids to archive entries.
        self._julia = None             # JuliaManager once an archive is open
        self._sound_resolver = None    # rebuilt per previewed file
        self._sound_player_list = []   # (player, output) pool so close sounds can overlap
        self._sound_buffer_list = []   # the QBuffer each player streams from (same index)
        self._next_sound_player = 0
        self._sound_auto_tried = False  # auto-enable 🔊 once, when the archive is nearby
        # Effect commands get a symbolic burst in the 3D view (the real particles are
        # procedural exe code): [position, remaining life in frames].
        self._effect_flash = None
        self._EFFECT_FLASH_FRAMES = 4
        # In-render text overlay: the attack-name banner (BB), monster battle text (91)
        # and "effect playing" notices, precomputed per frame at bake time. The banner
        # renders with the game's own font when the menu assets are found.
        self._overlay = None               # banner QLabel over the GL view
        self._overlay_effect = None        # effect-notice QLabel under it
        self._overlay_text_by_frame = []   # [(banner, effect notice)] per frame
        self._banner_renderer = _GameFontBanner(getattr(ifrit_manager, "game_data", None))

        # ── Header ────────────────────────────────────────────────────
        self._title = QLabel("Sequence preview")
        self._title.setStyleSheet("font-weight: bold;")
        self._variables_button = QPushButton("Variables")
        self._variables_button.setCheckable(True)
        self._variables_button.setToolTip(
            "Watch panel: the entity's VM variables (control flags with their bit "
            "names, e5/save slots, position, the working value) at the playhead frame, "
            "highlighting what changed since the previous frame. Only the variables "
            "this sequence actually touches are listed.")
        self._variables_button.toggled.connect(self.__toggle_variables)
        self._text_button = QPushButton("Frame list")
        self._text_button.setCheckable(True)
        self._text_button.setToolTip("Also show this run as a readable frame-by-frame "
                                     "table (what the timeline shows, in words)")
        self._text_button.toggled.connect(self.__toggle_text)
        close_button = QPushButton("✕")
        close_button.setFixedWidth(28)
        close_button.setToolTip("Close the preview")
        close_button.clicked.connect(self.close_panel)
        header_layout = QHBoxLayout()
        header_layout.addWidget(self._title)
        header_layout.addStretch(1)
        header_layout.addWidget(self._variables_button)
        header_layout.addWidget(self._text_button)
        header_layout.addWidget(close_button)

        # ── 3D view (lazy) ────────────────────────────────────────────
        self._placeholder = QLabel("Click a sequence's ▶ Preview to run it here.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: gray")
        self._placeholder.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Expanding)

        # ── Transport ─────────────────────────────────────────────────
        self._play_button = QPushButton("▶ Play")
        self._play_button.clicked.connect(self.__toggle_play)
        restart_button = QPushButton("⏮")
        restart_button.setFixedWidth(34)
        restart_button.setToolTip(
            "Replay from frame 0 (with its sounds). An endlessly looping sequence wraps "
            "to its loop frame, not to the start - a sound before the loop point plays "
            "once per run, exactly as in game; this is how you hear it again.")
        restart_button.clicked.connect(self.__restart)
        step_back_button = QPushButton("−1")
        step_back_button.setFixedWidth(34)
        step_back_button.setToolTip("One battle frame back")
        step_back_button.clicked.connect(
            lambda: self.__seek(self._frame_index - 1, play_sounds=True))
        step_forward_button = QPushButton("+1")
        step_forward_button.setFixedWidth(34)
        step_forward_button.setToolTip("One battle frame forward")
        step_forward_button.clicked.connect(
            lambda: self.__seek(self._frame_index + 1, play_sounds=True))
        self._frame_label = QLabel("frame 0 / 0")
        self._speed_selector = QComboBox()
        for label, _factor in self._SPEED_LIST:
            self._speed_selector.addItem(label)
        self._speed_selector.setCurrentIndex(2)   # 1× = the engine's own 15 fps
        self._speed_selector.setToolTip("Playback speed (1× = the battle's 15 frames "
                                        "per second)")
        self._speed_selector.currentIndexChanged.connect(self.__apply_speed)
        # Real-battle placement: the battle setup every battle preview shares - an
        # encounter of the bank's scene.out, the party and the model the sequence walks to
        # (Other model), all from the loaded files. The distance from this model's slot
        # to the other one feeds the bake (BattleContext); the other one stands there.
        from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
        self._battle_setup = BattlePreviewSetup(ifrit_manager, file_registry=self._file_registry,
                                                model_view=True)
        self._battle_setup.set_manual_position_visible(False)   # no encounter: the assumed distance
        self._battle_setup.group.remember(getattr(self._file_registry, "settings", None),
                                          "sequence preview/battle setup expanded")
        self._battle_setup.changed.connect(self.__on_battle_setup_changed)
        self._loop_checkbox = QCheckBox("Loop")
        self._loop_checkbox.setToolTip("Start over when the end is reached (checked "
                                       "automatically for a sequence that loops in game)")
        self._sound_checkbox = QCheckBox("🔊")
        self._sound_checkbox.setToolTip(
            "Play each sound command (B5/B6/B8/97/98) on the frame it lands, from the "
            "game's sound archive. The first use looks for audio.fmt next to the battle "
            "files and asks for it when it is not there.")
        if not _MULTIMEDIA_AVAILABLE:
            self._sound_checkbox.setEnabled(False)
            self._sound_checkbox.setToolTip("Sound playback needs the Qt multimedia "
                                            "plugin (PyQt6.QtMultimedia)")
        self._sound_checkbox.toggled.connect(self.__on_sound_toggled)
        transport_layout = QHBoxLayout()
        transport_layout.addWidget(self._play_button)
        transport_layout.addWidget(restart_button)
        transport_layout.addWidget(step_back_button)
        transport_layout.addWidget(step_forward_button)
        transport_layout.addWidget(self._frame_label)
        transport_layout.addStretch(1)
        transport_layout.addWidget(self._sound_checkbox)
        transport_layout.addWidget(self._speed_selector)
        transport_layout.addWidget(self._loop_checkbox)

        # ── Timeline (in a scroll area: long sequences overflow sideways) ──
        self._timeline = SequenceTimelineWidget()
        self._timeline.frame_selected.connect(self.__seek)
        self._timeline_scroll = QScrollArea()
        self._timeline_scroll.setWidgetResizable(True)
        self._timeline_scroll.setWidget(self._timeline)
        self._timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Sized to the CONTENT on every rebake (__fit_heights): every lane and the curve
        # band visible at once, never a hidden part to wheel-scroll to. This default
        # only covers the moment before the first bake.
        self._timeline_scroll.setFixedHeight(150)

        # ── Current frame detail + bake summary ───────────────────────
        # FIXED heights, not growing labels: their content changes every frame of
        # playback, and a height change would re-lay the whole panel out (the timeline
        # visibly jumps). The frame is shown as CHAINS: one line per outcome (an
        # action, or "pos_y ← formula = v"), the raw ops folded under an expander;
        # double-clicking a stored-slot chain jumps to the frame that reads it.
        self._detail_anim = QLabel()
        self._detail_anim.setStyleSheet("color: gray")
        self._detail_tree = QTreeWidget()
        self._detail_tree.setHeaderHidden(True)
        self._detail_tree.setFixedHeight(132)
        self._detail_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._detail_tree.itemDoubleClicked.connect(self.__on_chain_activated)
        # The watch panel ("Variables" header button): name/value rows of the VM state
        # at the playhead, the flags expanded bit by bit, changes highlighted. Beside
        # the chain tree so both read at once; hidden until asked for.
        self._watch_tree = QTreeWidget()
        self._watch_tree.setColumnCount(2)
        self._watch_tree.setHeaderHidden(True)
        self._watch_tree.setFixedWidth(230)
        self._watch_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._watch_variable_list = []
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("color: gray")

        # ── Text view of the same run (hidden until toggled) ──────────
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setMinimumHeight(140)
        self._text_view.hide()

        self._layout = QVBoxLayout(self)
        self._layout.addLayout(header_layout)
        self._layout.addWidget(self._placeholder, 1)
        self._layout.addLayout(transport_layout)
        self._layout.addWidget(self._battle_setup)
        # The watch column runs down the RIGHT of everything under the transport -
        # timeline included - so it gets real height for its ~20 rows; the timeline and
        # the detail tree don't need that width anyway.
        lower_left_layout = QVBoxLayout()
        lower_left_layout.addWidget(self._timeline_scroll)
        lower_left_layout.addWidget(self._detail_anim)
        lower_left_layout.addWidget(self._detail_tree)
        lower_left_layout.addWidget(self._summary)
        lower_left_layout.addWidget(self._text_view)
        lower_layout = QHBoxLayout()
        lower_layout.addLayout(lower_left_layout, 1)
        lower_layout.addWidget(self._watch_tree)
        self._layout.addLayout(lower_layout)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.__advance)
        self.__apply_speed()

        # Bound like any other tool's file: the binding publishes what this panel opens
        # and reloads when another tool (Julia) opens a different archive.
        self._audio_binding = FileBinding("audio.fmt", self._file_registry,
                                          load_callback=self.__on_audio_opened,
                                          read_only=True)
        self._audio_binding.load_opened_file()   # an archive may already be in the bank
        # mngrp.bin only matters here for what sits NEXT to it (sysfnt.*, the game font);
        # binding it means an mngrp opened anywhere (Ifrit's header Import complementary)
        # upgrades the banner live.
        self._mngrp_binding = FileBinding("mngrp.bin", self._file_registry,
                                          load_callback=self.__on_mngrp_opened,
                                          read_only=True)
        self._mngrp_binding.load_opened_file()

        # Watch panel on by default. Checked HERE, not where the button is built: the
        # toggle slot touches the watch tree, and a slot raising during construction is
        # a hard abort under PyQt (unhandled-exception-in-slot policy).
        self._variables_button.setChecked(True)

        # ← / → step one battle frame (like the 3D tab's frame arrows), Space toggles
        # play/pause. Scoped to the panel and its children so they never steal the keys
        # from another tool.
        for key, delta in ((Qt.Key.Key_Left, -1), (Qt.Key.Key_Right, 1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(
                lambda step=delta: self.__seek(self._frame_index + step,
                                               play_sounds=True))
        space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        space_shortcut.activated.connect(self.__toggle_play)

    # ── Called by the tab ─────────────────────────────────────────────
    def preview(self, seq_id):
        """Load sequence `seq_id` into the panel, show it, and start playing."""
        self._seq_id = seq_id
        self.__rebuild_sound_resolver()
        self._battle_setup.encounters.refresh_model()   # this file's encounters
        if self.battle_context is None:
            self.__on_battle_setup_changed(rebake=False)   # stand the battle now it is shown
        self.show()
        self.__ensure_model()
        # Sound on by default when the file bank already holds an archive (opened here
        # before, or in Julia) - no dialog, no click. The checkbox stays the off switch;
        # with no archive in the bank, the summary says to import one.
        if (_MULTIMEDIA_AVAILABLE and not self._sound_auto_tried
                and not self._sound_checkbox.isChecked()):
            self._sound_auto_tried = True
            if self._julia is not None:
                self._sound_checkbox.blockSignals(True)
                self._sound_checkbox.setChecked(True)
                self._sound_checkbox.blockSignals(False)
        if self.__rebake(keep_frame=False):
            # Frame 0 is REACHED when playback starts: its sounds and effects belong to
            # the run (a monster's entrance roar sits on frame 0) - the rebake's own
            # seek suppressed them, as it does for scrubbing.
            self.__seek(0, play_sounds=True)
            self.__play()

    def refresh(self):
        """The sequence bytes changed under the preview (a keystroke, an undo): re-run
        the bake, keeping the playhead where it was. No-op while the panel is closed."""
        # isHidden(), not isVisible(): the panel counts as open even when the whole tab is
        # currently in the background (its bake must stay in step with the bytes for when
        # the tab comes back), and a headless test can exercise it without a real screen.
        if self._seq_id is None or self.isHidden():
            return
        if self._needs_model_reload and self._view is not None:
            self.__ensure_model()   # an undo may have changed the mesh too
        self.__rebake(keep_frame=True)

    def invalidate_model(self):
        """The MODEL may have changed (another file loaded into the pane, an undo of a 3D
        edit): reload the mesh on the next preview."""
        self._needs_model_reload = True
        if self._view is not None:
            self._view._object_range_list = None
        self.__rebuild_sound_resolver()   # the actor (com id) may have changed too

    def close_panel(self):
        self.__pause()
        self.hide()
        self.closed.emit()

    def current_seq_id(self):
        return self._seq_id if not self.isHidden() else None

    def hideEvent(self, event):
        self.__pause()   # the tab was switched away or the panel closed: stop the timer
        for player, _output in self._sound_player_list:
            player.stop()
        super().hideEvent(event)

    # ── Model ─────────────────────────────────────────────────────────
    def __ensure_model(self):
        try:
            if self._view is None:
                self._view = _SequencePosedViewer(self.ifrit_manager)
                self._layout.insertWidget(1, self._view, 1)   # where the placeholder sits
                # In-render text (attack name, battle text, effect notices): labels ON
                # the GL surface, like the game draws its banner over the scene. Mouse
                # events pass through so they never block orbiting the camera.
                self._overlay = QLabel(self._view.gl_widget)
                self._overlay.setStyleSheet(
                    "background: rgba(18, 18, 26, 200); color: white; "
                    "padding: 3px 10px; border: 1px solid #8c8ca8;")
                self._overlay.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self._overlay.hide()
                self._overlay_effect = QLabel(self._view.gl_widget)
                self._overlay_effect.setStyleSheet(
                    "background: rgba(18, 18, 26, 150); color: #e8b46a; "
                    "padding: 2px 6px; border-radius: 3px;")
                self._overlay_effect.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self._overlay_effect.hide()
            if self._needs_model_reload:
                if hasattr(self.ifrit_manager, "_ensure_matrices"):
                    self.ifrit_manager._ensure_matrices()
                self._view.load_file()
                self._view.timer.stop()   # this panel drives the frames, not the viewer
                self._needs_model_reload = False
                # Spatial reference: without something fixed in the scene, a sequence
                # translating the model (a jump, a 9E run) reads as nothing happening.
                # Ground at the entity's resting spot, marker (and the stand-in, when
                # one is loaded) where the target stands - the picked encounter's real
                # distance, or the documented default.
                cast = self._battle_setup.cast
                self._view.set_companion(cast.actor_model(cast.other_key()))
                self.__place_companion()
            self._placeholder.hide()
            self._view.show()
        except Exception as error:
            # A file the 3D viewer cannot render (or a test double without geometry):
            # the timeline is still worth having, so only the 3D area degrades.
            if self._view is not None:
                self._view.hide()
            self._placeholder.setText(f"3D preview unavailable: {error}")
            self._placeholder.show()

    # ── Bake ──────────────────────────────────────────────────────────
    def __rebake(self, keep_frame) -> bool:
        self.__pause()
        try:
            self._result = self._bake_provider(self._seq_id)
        except Exception as error:   # a preview must never take the editor down with it
            self._result = None
            self._title.setText(f"Sequence {self._seq_id} preview")
            self._summary.setText(f"Preview unavailable: {error}")
            self._timeline.set_result(None)
            self._detail_anim.setText("")
            self._detail_tree.clear()
            self._text_view.setHtml("")
            self._frame_label.setText("frame 0 / 0")
            self._overlay_text_by_frame = []
            if self._overlay is not None:
                self._overlay.hide()
            if self._overlay_effect is not None:
                self._overlay_effect.hide()
            return False
        result = self._result
        game_data = getattr(self.ifrit_manager, "game_data", None)
        enemy = getattr(self.ifrit_manager, "enemy", None)
        self._overlay_text_by_frame = build_overlay_texts(
            result,
            attack_name_of_seq=lambda sid: sequence_attack_names(game_data, enemy, sid),
            battle_text_of=lambda index: monster_battle_text(enemy, index))
        self._title.setText(f"Sequence {self._seq_id} preview")
        self._timeline.set_result(result, self.__sound_duration_frames)
        self._watch_variable_list = relevant_watch_variables(result)
        self.__fit_heights(result)
        summary = result.summary()
        assumed = assumption_list(result)
        if assumed:
            summary += ("   —   assumed from the battle: "
                        + ", ".join(f"{what} = {value}" for what, value in assumed))
        self._summary.setText(summary)
        if self._text_button.isChecked():
            self._text_view.setHtml(format_timeline_html(result))
        # A sequence that runs forever plays in a loop by default; a one-shot stops.
        self._loop_checkbox.setChecked(result.is_endless()
                                       or result.loop_from is not None)
        frame = self._frame_index if keep_frame else 0
        self.__seek(frame)
        return bool(result.frame_list)

    # ── Transport ─────────────────────────────────────────────────────
    def __nb_frame(self) -> int:
        return len(self._result.frame_list) if self._result is not None else 0

    def __seek(self, frame_index, play_sounds=False):
        """Show battle frame `frame_index`. play_sounds is True only when the frame is
        REACHED (playback tick, ±1 step), never when it is merely pointed at (a drag
        across the timeline would machine-gun every sound it crosses)."""
        nb_frame = self.__nb_frame()
        if nb_frame == 0:
            self._frame_index = 0
            self._frame_label.setText("frame 0 / 0")
            return
        self._frame_index = max(0, min(frame_index, nb_frame - 1))
        frame = self._result.frame_list[self._frame_index]
        self._frame_label.setText(f"frame {self._frame_index} / {nb_frame - 1}")
        self._timeline.set_current_frame(self._frame_index)
        self._timeline_scroll.ensureVisible(self._timeline.playhead_x(), 0, 60, 0)
        self.__update_detail(frame)
        if not self._watch_tree.isHidden():
            self.__update_watch()
        self.__apply_frame_to_view(frame)
        self.__apply_overlay()
        if play_sounds:
            self.__play_frame_sounds(frame)
            self.__advance_effect_flash(frame)
        else:
            self.__clear_effect_flash()   # scrubbing: no stale burst hanging around

    _CHAIN_COLOUR_VALUE = "#7f9ec0"   # same hue as the timeline's value lane

    def __fit_heights(self, result):
        """Size the timeline and the detail tree to THIS bake, once per rebake: every
        lane and curve visible without wheel-scrolling, the tree exactly tall enough
        for the busiest frame (stable during playback - per-frame resizing is the
        layout-jump bug all over again)."""
        scrollbar_height = self._timeline_scroll.horizontalScrollBar().sizeHint().height()
        self._timeline_scroll.setFixedHeight(
            self._timeline.minimumSizeHint().height() + scrollbar_height + 6)
        nb_chain = max((len(build_frame_chains(frame))
                        for frame in result.frame_list), default=1)
        row_height = self._detail_tree.fontMetrics().height() + 7
        nb_row = max(2, min(nb_chain, 9))   # past 9 the tree scrolls
        self._detail_tree.setFixedHeight(nb_row * row_height + 10)

    def __update_detail(self, frame):
        """Rebuild the chain tree for this frame: one top line per outcome, raw ops
        under the expander, double-click a stored slot to jump to where it is read."""
        self._detail_anim.setText(frame_anim_text(frame)
                                  or "no animation queued yet")
        tree = self._detail_tree
        tree.clear()
        chain_list = build_frame_chains(
            frame, self._sound_resolver,
            current_value_story(self._result, self._frame_index))
        if not chain_list:
            item = QTreeWidgetItem([f"nothing runs on this frame   "
                                    f"(value = {frame.current_value})"])
            item.setForeground(0, QBrush(QColor("gray")))
            tree.addTopLevelItem(item)
            return
        for chain in chain_list:
            colour = COLOUR_BY_KIND.get(chain.kind, self._CHAIN_COLOUR_VALUE)
            item = QTreeWidgetItem([chain.headline])
            item.setForeground(0, QBrush(QColor(colour)))
            tooltip_lines = []
            if chain.target_frame is not None:
                item.setData(0, Qt.ItemDataRole.UserRole, chain.target_frame)
                tooltip_lines.append(f"Double-click to jump to frame "
                                     f"{chain.target_frame}, where this value is read.")
            if chain.kind == "value":
                glossary = [f"{name} = {meaning}"
                            for name, meaning in SPECIAL_VAR_GLOSSARY.items()
                            if name in chain.headline]
                if glossary:
                    tooltip_lines.append("name(value) reads a battle/animation "
                                         "variable, shown with the value it had:")
                    tooltip_lines.extend("  " + line for line in glossary)
            if tooltip_lines:
                item.setToolTip(0, "\n".join(tooltip_lines))
            for op_line in chain.op_lines:
                child = QTreeWidgetItem([op_line])
                child.setForeground(0, QBrush(QColor("gray")))
                item.addChild(child)
            tree.addTopLevelItem(item)

    def __on_chain_activated(self, item, _column):
        target_frame = item.data(0, Qt.ItemDataRole.UserRole)
        if target_frame is not None:
            self.__seek(int(target_frame))

    # ── Watch panel ───────────────────────────────────────────────────
    _WATCH_CHANGED_COLOUR = "#e8b46a"   # what just changed, while scrubbing/playing

    def __toggle_variables(self, shown):
        self._watch_tree.setVisible(shown)
        if shown:
            self.__update_watch()

    def __update_watch(self):
        """Rebuild the watch rows for the playhead frame: every variable this bake
        touches, the flags with one child row per named bit, changes highlighted."""
        tree = self._watch_tree
        tree.clear()
        if self._result is None or not self._result.frame_list:
            return
        frame = self._result.frame_list[self._frame_index]
        previous = (self._result.frame_list[self._frame_index - 1]
                    if self._frame_index > 0 else None)
        changed_brush = QBrush(QColor(self._WATCH_CHANGED_COLOUR))
        quiet_brush = QBrush(QColor("gray"))
        for name, text, changed in build_watch_rows(
                self._result, self._frame_index, self._watch_variable_list):
            if name == "state_flags":
                item = QTreeWidgetItem([name, f"0x{frame.state_flags:X}"])
                known_mask = 0
                for bit, bit_name in STATE_FLAG_NAME.items():
                    known_mask |= bit
                    bit_set = bool(frame.state_flags & bit)
                    child = QTreeWidgetItem([bit_name, "set" if bit_set else "·"])
                    if not bit_set:
                        child.setForeground(0, quiet_brush)
                        child.setForeground(1, quiet_brush)
                    if previous is not None and bit_set != bool(
                            previous.state_flags & bit):
                        child.setForeground(0, changed_brush)
                        child.setForeground(1, changed_brush)
                    item.addChild(child)
                unknown = frame.state_flags & ~known_mask
                if unknown:
                    item.addChild(QTreeWidgetItem(["unknown bits", f"0x{unknown:X}"]))
            else:
                item = QTreeWidgetItem([name, text])
            if changed:
                item.setForeground(0, changed_brush)
                item.setForeground(1, changed_brush)
            tree.addTopLevelItem(item)
            item.setExpanded(True)
        tree.resizeColumnToContents(0)

    def __menu_folder(self):
        """The menu folder holding sysfnt.TEX/.tdw, derived from the file bank the same
        way Zone and Moomba do: sysfnt.* sit next to the registry-opened mngrp.bin. No
        folder-layout guessing - if no mngrp.bin is open, the banner stays a plain label
        (open mngrp.bin in any tool and it upgrades to the game font)."""
        mngrp_path = self._file_registry.get_path("mngrp.bin")
        if mngrp_path and os.path.isfile(
                os.path.join(os.path.dirname(mngrp_path), "sysfnt.TEX")):
            return os.path.dirname(mngrp_path)
        return None

    def __apply_overlay(self):
        """Show this frame's banner (game font when available) and effect notice, the
        banner top-centred like the in-game window."""
        if self._overlay is None:
            return
        banner, effect = (self._overlay_text_by_frame[self._frame_index]
                          if self._frame_index < len(self._overlay_text_by_frame)
                          else ("", ""))
        gl = self._view.gl_widget if self._view is not None else None
        if banner and gl is not None:
            pixmap = self._banner_renderer.render(banner, self.__menu_folder())
            if pixmap is not None:
                self._overlay.setStyleSheet("")   # the pixmap IS the window
                self._overlay.setText("")
                self._overlay.setPixmap(pixmap)
            else:                                 # no menu assets: plain styled label
                from PyQt6.QtGui import QPixmap as _QPixmap
                self._overlay.setPixmap(_QPixmap())
                self._overlay.setStyleSheet(
                    "background: rgba(18, 18, 26, 200); color: white; "
                    "padding: 3px 10px; border: 1px solid #8c8ca8;")
                self._overlay.setText(banner)
            self._overlay.adjustSize()
            self._overlay.move(max((gl.width() - self._overlay.width()) // 2, 0), 8)
            self._overlay.show()
        else:
            self._overlay.hide()
        if self._overlay_effect is not None:
            if effect and gl is not None:
                self._overlay_effect.setText(effect)
                self._overlay_effect.adjustSize()
                below = (8 + self._overlay.height() + 4) if banner else 8
                self._overlay_effect.move(8, below)
                self._overlay_effect.show()
            else:
                self._overlay_effect.hide()

    def __apply_frame_to_view(self, frame):
        view = self._view
        if view is None or view.gl_widget is None or view.isHidden():
            return
        animation_data = getattr(self.ifrit_manager.enemy, "animation_data", None)
        animation_list = getattr(animation_data, "animations", [])
        if frame.anim_id is not None and frame.anim_id < len(animation_list):
            view.current_anim_id = frame.anim_id
            nb_anim_frame = animation_list[frame.anim_id].get_nb_frame()
            view.current_frame = min(frame.anim_frame, max(nb_anim_frame - 1, 0))
            view.next_frame_index = ((view.current_frame + 1) % nb_anim_frame
                                     if nb_anim_frame else 0)
        view.interp_step = 0.0
        view.set_pose_frame(frame)
        view.update_animated_mesh()
        view.update_skeleton()

    def __restart(self):
        """Back to frame 0 - reached, so its sounds fire - and keep playing."""
        if self.__nb_frame() == 0:
            return
        self.__seek(0, play_sounds=True)
        self.__play()

    def __toggle_play(self):
        if self._timer.isActive():
            self.__pause()
        else:
            if self._frame_index >= self.__nb_frame() - 1:
                # Replay from the start rather than one dead frame - and frame 0 is
                # reached, so its sounds play (the entrance-roar-on-frame-0 case).
                self.__seek(0, play_sounds=True)
            self.__play()

    def __play(self):
        if self.__nb_frame() == 0:
            return
        self._timer.start()
        self._play_button.setText("⏸ Pause")

    def __pause(self):
        self._timer.stop()
        self._play_button.setText("▶ Play")

    def __advance(self):
        next_index = self._frame_index + 1
        if next_index >= self.__nb_frame():
            if self._loop_checkbox.isChecked():
                # Come back to where the run actually loops from, like the engine does -
                # frame 0 only when the whole thing repeats.
                loop_from = (self._result.loop_from
                             if self._result is not None and self._result.loop_from
                             else 0)
                self.__seek(loop_from, play_sounds=True)
                return
            self.__pause()
            return
        self.__seek(next_index, play_sounds=True)

    def __apply_speed(self):
        factor = self._SPEED_LIST[self._speed_selector.currentIndex()][1]
        self._timer.setInterval(int(1000 / (self._BATTLE_FPS * factor)))

    def __toggle_text(self, shown):
        self._text_view.setVisible(shown)
        if shown and self._result is not None:
            self._text_view.setHtml(format_timeline_html(self._result))

    # ── Effect flashes ────────────────────────────────────────────────
    # Where a symbolic burst appears: hit particles (B0/B4) and screen effects aimed at
    # the victim (A5) land at the assumed target; walk dust (99/B1), self effects (84)
    # and fades (A8) at the entity itself.
    _EFFECT_AT_SELF_OPS = (0x99, 0xB1, 0x84, 0xA8, 0x96)

    def __advance_effect_flash(self, frame):
        """One battle frame of the burst's life: a new effect command re-arms it at full
        size, otherwise the previous one expands and fades over a few frames."""
        gl = self._view.gl_widget if self._view is not None else None
        if gl is None:
            return
        spawned = None
        fire_command = fire_signal_command(frame)
        for command in frame.command_list:
            if command.is_background:
                continue
            if command.kind == EVENT_EFFECT:
                if command.op_code in self._EFFECT_AT_SELF_OPS:
                    translation = gl.model_translation
                    spawned = [translation[0], translation[1] + 2.0, translation[2]]
                else:
                    spawned = list(sequence_position_world(
                        BattleContext().target_position))
                    spawned[1] += 2.0
            elif command is fire_command:
                # The 0x20 "fire" signal to the parallel effect code: the projectile
                # leaves the entity here, so the burst does too.
                translation = gl.model_translation
                spawned = [translation[0], translation[1] + 2.0, translation[2]]
        if spawned is not None:
            self._effect_flash = [spawned, self._EFFECT_FLASH_FRAMES]
        elif self._effect_flash is not None:
            self._effect_flash[1] -= 1
            if self._effect_flash[1] <= 0:
                self._effect_flash = None
        if self._effect_flash is not None:
            gl.set_effect_flash(tuple(self._effect_flash[0]),
                                self._effect_flash[1] / self._EFFECT_FLASH_FRAMES)
        else:
            gl.set_effect_flash(None, 0.0)

    def __clear_effect_flash(self):
        self._effect_flash = None
        if self._view is not None and self._view.gl_widget is not None:
            self._view.gl_widget.set_effect_flash(None, 0.0)

    # ── Sound ─────────────────────────────────────────────────────────
    _NB_SOUND_PLAYER = 3   # a hit + its impact sound one frame apart must overlap

    def __sound_duration_frames(self, op_code, parameters):
        """How many battle frames a sound command's audio actually plays, from the
        archive's own byte rate - None when the archive (or the sound) is not known,
        in which case its timeline bar stays a mark."""
        if self._julia is None or self._sound_resolver is None:
            return None
        audio_id = self._sound_resolver.resolve(op_code, parameters)
        if audio_id is None or not 0 <= audio_id < len(self._julia.sounds):
            return None
        sound = self._julia.sounds[audio_id]
        bytes_per_second = sound.wave_format[3]   # nAvgBytesPerSec
        if not sound.data_length or not bytes_per_second:
            return None
        return max(1, round(sound.data_length / bytes_per_second * self._BATTLE_FPS))

    def __rebuild_sound_resolver(self):
        """Map THIS entity's sound commands to archive entries (B5/B6 go through the
        actor's 7-slot row of BattleActorSoundTable, keyed by the file's com id)."""
        game_data = getattr(self.ifrit_manager, "game_data", None)
        file_name = getattr(getattr(self.ifrit_manager, "enemy", None),
                            "origin_file_name", "")
        try:
            self._sound_resolver = SequenceSoundResolver(game_data, file_name)
        except Exception:
            self._sound_resolver = None

    def __on_sound_toggled(self, checked):
        if not checked:
            return
        if not self.__ensure_sound_archive():
            self._sound_checkbox.blockSignals(True)
            self._sound_checkbox.setChecked(False)
            self._sound_checkbox.blockSignals(False)

    def __on_audio_opened(self, fmt_path):
        """The bank's audio.fmt (opened here or by Julia): (re)load the archive."""
        try:
            julia = JuliaManager(getattr(self.ifrit_manager, "game_data", None))
            julia.load(fmt_path)
            self._julia = julia
        except Exception as error:
            self._julia = None
            self._summary.setText(f"Sound archive could not be opened: {error}")

    # ── Real-battle placement (the shared battle setup) ──────────────
    # scene.out coordinates are battle world units on the same scale as the sequence's
    # own position writes, so the distance feeds BattleContext directly and the
    # stand-in is placed with the shared raw->viewer mapping.

    def set_model_paths(self, paths):
        """The models the user loaded (callable -> paths): the battle setup's party and
        other model are only these."""
        self._battle_setup.set_model_paths(paths)

    def __on_battle_setup_changed(self, rebake=True):
        """Build the battle context from the setup: in an encounter, this model stands at
        its scene.out slot and the other model where the encounter or the battle formation
        puts it, so the distance the sequence walks is the real one. The other model is the
        stand-in at the target (a party character: the only honest scale reference). Only
        while the preview shows a sequence: a hidden preview reads no model."""
        if self._seq_id is None:
            return
        setup = self._battle_setup
        try:
            setup.build(0, False)
        except Exception as error:
            self._summary.setText(f"Battle setup: {error}")
            return
        main, other = setup._main, getattr(setup, "_other", None)
        slot = setup.encounters.selected_slot
        if setup.encounters.selected is None or main is None or other is None or other is main:
            self.battle_context = None
        else:
            dx = other.position[0] - main.position[0]
            dz = other.position[2] - main.position[2]
            distance = max(int(round(math.hypot(dx, dz))), 1)
            self.battle_context = BattleContext(
                target_distance=distance,
                target_position=(0, 0, -distance),
                own_slot=slot.slot_index if slot is not None and setup.encounters.is_monster else 4,
                target_slot=setup.target_slot.value())
        if self._view is not None:
            self._view.set_companion(setup.cast.actor_model(setup.cast.other_key()))
        self.__place_companion()
        if rebake:
            self.__rebake(keep_frame=True)

    def __place_companion(self):
        """Put the stand-in (and the target marker) where the current context says the
        target is."""
        if self._view is None or self._view.gl_widget is None:
            return
        context = self.battle_context or BattleContext()
        target = sequence_position_world(context.target_position)
        self._view.gl_widget.set_preview_markers(ground_y=0.0, target=target)
        self._view.set_companion_offset(target)

    def __on_mngrp_opened(self, _path):
        """mngrp.bin landed in the bank: the game font may now be available - redraw
        the banner of the current frame with it."""
        self.__apply_overlay()

    def __ensure_sound_archive(self) -> bool:
        """The archive comes from the shared file bank (Ifrit's header Import complementary,
        or Julia): without one, the summary says to import it."""
        if self._julia is None:
            self._summary.setText("No sound archive: import audio.fmt with the header's Import "
                                  "complementary to hear the sounds.")
        return self._julia is not None

    def __play_frame_sounds(self, frame):
        if (not self._sound_checkbox.isChecked() or self._julia is None
                or self._sound_resolver is None):
            return
        for command in frame.command_list:
            if command.is_background or command.op_code not in SOUND_OP_CODES:
                continue
            audio_id = self._sound_resolver.resolve(command.op_code, command.parameters)
            if audio_id is not None and 0 <= audio_id < len(self._julia.sounds):
                self.__play_audio(audio_id)

    def __play_audio(self, audio_id):
        try:
            wav = self._julia.get_wav(audio_id)
        except Exception:
            return  # a sound the archive cannot serve must not stop the playback
        if not self._sound_player_list:
            # Julia's exact construction (its playback is proven on this machine):
            # unparented player + output, references held by the pool lists. Errors are
            # asynchronous, so they surface through errorOccurred - shown in the
            # summary, since a silent failure is indistinguishable from a quiet sound.
            for _ in range(self._NB_SOUND_PLAYER):
                output = QAudioOutput()
                player = QMediaPlayer()
                player.setAudioOutput(output)
                player.errorOccurred.connect(self.__on_player_error)
                self._sound_player_list.append((player, output))
                self._sound_buffer_list.append(None)
        index = self._next_sound_player
        self._next_sound_player = (index + 1) % self._NB_SOUND_PLAYER
        player, _output = self._sound_player_list[index]
        player.stop()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(wav))
        buffer.open(QBuffer.OpenModeFlag.ReadOnly)
        # Same lifetime rule as Julia's player: hand the player the new buffer before
        # dropping the old one, so it is never left streaming from a closed buffer.
        previous = self._sound_buffer_list[index]
        self._sound_buffer_list[index] = buffer
        player.setSourceDevice(buffer, QUrl(f"seq_audio_{audio_id}.wav"))
        if previous is not None:
            previous.close()
            previous.deleteLater()
        player.play()

    def __on_player_error(self, _error, error_string):
        """Playback failures are asynchronous (Julia surfaces them the same way)."""
        self._summary.setText(f"Sound playback error: {error_string}")
