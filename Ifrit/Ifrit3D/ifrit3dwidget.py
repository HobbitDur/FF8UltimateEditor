import gc
import pathlib

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QFontMetrics, QAction
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QCheckBox, QPushButton, QSlider, QSpinBox,
                             QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
                             QFileDialog, QComboBox, QToolButton, QMenu, QToolBar,
                             QSizePolicy, QDialog, QDialogButtonBox, QFormLayout)


class _PlaybackTimer(QTimer):
    """A QTimer that suspends Python's cyclic garbage collector while it is running.

    Animation playback allocates a little per frame. Automatic GC pauses scale with the TOTAL
    live-object count across EVERY loaded file, not just the active one - so opening many files
    makes gen1/gen2 collections stutter the 3D player even though the active file's per-frame work
    is unchanged (measured: worst-frame time 3 ms at 2 files -> 33 ms at 16 files, mean flat). This
    is the "flawless with two files, unbearable with many" lag. Pausing GC for the duration of
    playback removes those pauses entirely; a single collect() when playback stops reclaims the
    playback garbage. Ref-counted on each timer's real active state so nested/among-viewers
    start/stop (and harmless double start()s) balance correctly, and it only re-enables GC if it
    was the one that disabled it (never fights external gc.disable())."""
    _running = 0
    _we_disabled = False

    def start(self, *args):
        if not self.isActive():
            _PlaybackTimer._running += 1
            _PlaybackTimer._sync()
        super().start(*args)

    def stop(self):
        if self.isActive():
            _PlaybackTimer._running -= 1
        super().stop()
        _PlaybackTimer._sync()

    @classmethod
    def _sync(cls):
        if cls._running > 0:
            if gc.isenabled():
                gc.disable()
                cls._we_disabled = True
        elif cls._we_disabled:
            cls._we_disabled = False
            gc.enable()
            gc.collect()


class _HoverMenuButton(QToolButton):
    """A tool button that drops its menu on hover (not just click) - used to hang a small
    options submenu off the Skeleton toggle so extra skeleton options stay out of the toolbar
    until the user hovers to reveal them."""
    def enterEvent(self, event):
        super().enterEvent(event)
        menu = self.menu()
        if menu is not None and not menu.isVisible():
            self.showMenu()

from FF8GameData.monsterdata import AnimationFrame, AnimationSection, Animation, EntityType
from FF8GameData.dat.animloopdetector import (is_looping, analyse_animation_usage,
                                              find_character_weapon_file_list,
                                              get_animation_usage_from_weapon_file,
                                              ANIM_LOOP, ANIM_ONE_SHOT, ANIM_BOTH, ANIM_UNUSED)
from FF8GameData.dat.animsplitter import (split_and_convert_animation, get_nb_part_needed,
                                          get_max_frame_for_animation,
                                          MAX_SLOW_SAFE_ANIMATION_FRAME)
from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.boneeditorwidget import AnimEditor
from Ifrit.Ifrit3D.ff8openwidget import FF8OpenGLWidget
from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Ifrit.Ifrit3D.gltfimporter import GltfImporter


ANIM_KIND_TEXT = {ANIM_LOOP: "a looping animation",
                  ANIM_ONE_SHOT: "a one-shot animation",
                  ANIM_BOTH: "looping and played once depending on the sequence",
                  ANIM_UNUSED: "never played by any sequence of this file"}


class Ifrit3DWidget(QWidget):
    frame_changed = pyqtSignal(int)
    animation_finished = pyqtSignal(int)  # Emitted when an animation in playlist finishes
    animation_changed = pyqtSignal()
    def __init__(self, ifrit_manager:IfritManager, show_controls=True):
        super().__init__()
        self.ifrit_manager = ifrit_manager

        # Animation variables
        self.current_anim_id = 0
        self.current_frame = 0
        self.animating = False
        self.fps = 15
        self.interp_step = 0.0
        self.next_frame_index = 1

        # Some files (e.g. Lion Heart/d0w006) have most of their mesh flagged "hidden" via the
        # TPage 0xFE00 bit the real renderer also skips - a legitimate per-face flag, but one
        # some files use so heavily that the visible mesh alone looks broken/incomplete in this
        # static viewer (it can't simulate whatever dynamically reveals those faces in-game). On
        # by default so a file opens whole rather than looking damaged; see _refresh_static_geometry.
        self._show_hidden_faces = True

        # Loop detection of a character body needs its weapon file, keep what was read
        # so the file is not searched again on every conversion.
        self._animation_usage_cache = {}
        self.weapon_file_used = ""

        # Composite character rendering: a character body can display its weapon in the SAME
        # viewer (see the CompositeCharacterWeaponAnimation wiki). The weapon is a second model
        # (its own IfritManager) merged into the one mesh pushed to the GL widget - offset its
        # vertex indices past the body's and its texture ids above the body's, then reuse the
        # single-model render path unchanged. Both play the same animation index in one space.
        self._weapon_manager = None      # sibling IfritManager whose enemy is the weapon, or None
        self._weapon_options = []        # [(label, manager_or_None)] shown in the Weapon selector
        self._body_vertex_count = 0      # #verts in the body mesh; weapon indices start here
        # Weapon placement is automatic: the weapon's own animation carries a per-frame root
        # position that traces the hand (the game applies each model's own root - see
        # _current_weapon_verts), so no user-picked attach bone is needed.

        # Playlist variables
        self.playlist = []  # List of animation IDs in order
        self.current_playlist_index = 0
        self.playlist_mode = False
        self.loop_playlist = False
        self.playlist_expanded = False  # Start collapsed

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._main_layout = layout       # for release/restore of the GL surface (see below)
        self._gl_layout_index = None      # where the GL widget sits in the vbox (set after addWidget)

        # Create OpenGL widget. It is destroyable and rebuildable (release_gl_widget /
        # restore_gl_widget) so only the ACTIVE file's viewer keeps a live OpenGL context: the
        # graphics driver slows every viewer down as live contexts pile up, so the multi-file
        # shell releases a pane's GL surface when it's switched away from.
        self.gl_widget = FF8OpenGLWidget(self)
        self._configure_gl_widget()
        self._length_drag_start_size = None
        self._length_drag_sign = -1.0
        self._rot_drag_start_deg = None
        self._rot_drag_start_raw = None

        # Setup animation timer. _PlaybackTimer pauses Python's GC while playing so gen1/gen2
        # collection pauses (which scale with the total objects of ALL loaded files) don't stutter
        # the 3D player - this is the many-files-open playback lag.
        self.timer = _PlaybackTimer()
        self.timer.timeout.connect(self.next_frame)

        if show_controls:
            # Main toolbar. A real QToolBar (not a plain QWidget+QHBoxLayout) so it gets Qt's
            # built-in overflow handling for free: when there isn't room for every control, the
            # ones that don't fit are hidden behind a small "»" button at the end instead of being
            # clipped or forcing the whole pane to stay wide (see the QSplitter note below).
            toolbar = QToolBar()
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setStyleSheet(
                "QToolBar{background:#2a2a2f; padding:5px; spacing:4px; border:none;}"
                "QToolBar::separator{background:#444; width:1px; margin:2px 4px;}")
            toolbar_layout = toolbar   # every earlier `toolbar_layout.addWidget(x)` below still
                                       # works unchanged: QToolBar.addWidget has the same signature

            # Left side controls
            self.cb_texture = QCheckBox("Texture")
            self.cb_texture.setChecked(True)
            self.cb_texture.setStyleSheet("color:white;")
            self.cb_texture.toggled.connect(self._on_texture_toggle)
            toolbar_layout.addWidget(self.cb_texture)

            self.cb_wire = QCheckBox("Wireframe")
            self.cb_wire.setChecked(False)
            self.cb_wire.setStyleSheet("color:white;")
            self.cb_wire.toggled.connect(self._on_wire_toggle)
            toolbar_layout.addWidget(self.cb_wire)

            self.cb_hidden_faces = QCheckBox("Show hidden faces")
            self.cb_hidden_faces.setChecked(self._show_hidden_faces)
            self.cb_hidden_faces.setStyleSheet("color:white;")
            self.cb_hidden_faces.setToolTip(
                "Some faces are flagged 'hidden' in the file (a TPage bit the real renderer also\n"
                "skips), but a few files use it so heavily the visible mesh alone looks broken\n"
                "(e.g. Lion Heart/d0w006). Checked shows the full mesh anyway.")
            self.cb_hidden_faces.toggled.connect(self._on_hidden_faces_toggle)
            toolbar_layout.addWidget(self.cb_hidden_faces)

            self.cb_axis = QCheckBox("Axis")
            self.cb_axis.setChecked(False)
            self.cb_axis.setStyleSheet("color:white;")
            self.cb_axis.toggled.connect(self._on_axis_toggle)
            toolbar_layout.addWidget(self.cb_axis)

            self.cb_skeleton = QCheckBox("Skeleton")
            self.cb_skeleton.setChecked(False)
            self.cb_skeleton.setStyleSheet("color:white;")
            self.cb_skeleton.toggled.connect(self._on_skeleton_toggle)
            toolbar_layout.addWidget(self.cb_skeleton)

            # Skeleton options submenu (hover the little arrow next to "Skeleton" to reveal it).
            # Keeps extra skeleton toggles out of the toolbar until wanted. First entry: show the
            # rotation rings ("sphere") around the selected joint - uncheck for a clean skeleton.
            self._skeleton_menu = QMenu(self)
            self._gizmo_action = QAction("Rotation handle", self, checkable=True)
            self._gizmo_action.setChecked(True)
            self._gizmo_action.setToolTip("Rings around the selected bone, for dragging to rotate it.")
            self._gizmo_action.toggled.connect(self._on_gizmo_toggle)
            self._skeleton_menu.addAction(self._gizmo_action)
            self.skeleton_opts_btn = _HoverMenuButton()
            self.skeleton_opts_btn.setText("▾")           # small down triangle
            self.skeleton_opts_btn.setMenu(self._skeleton_menu)
            self.skeleton_opts_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.skeleton_opts_btn.setAutoRaise(True)
            self.skeleton_opts_btn.setToolTip("Skeleton options")
            self.skeleton_opts_btn.setStyleSheet(
                "QToolButton{color:white; padding:0 4px;} QToolButton::menu-indicator{image:none;}")
            self.skeleton_opts_btn.setEnabled(False)           # enabled with the skeleton
            toolbar_layout.addWidget(self.skeleton_opts_btn)

            # Animation controls
            self.play_btn = QPushButton("Play")
            self.play_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.play_btn.clicked.connect(self.toggle_animation)
            toolbar_layout.addWidget(self.play_btn)

            self.reset_anim_btn = QPushButton("Reset Anim")
            self.reset_anim_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.reset_anim_btn.clicked.connect(self.reset_animation)
            toolbar_layout.addWidget(self.reset_anim_btn)

            self.fps_label = QLabel(f"FPS: {self.fps}")
            self.fps_label.setStyleSheet("color:white; padding:4px 4px;")
            toolbar_layout.addWidget(self.fps_label)

            self.fps_slider = QSlider(Qt.Orientation.Horizontal)
            self.fps_slider.setRange(15, 60)
            self.fps_slider.setValue(self.fps)
            self.fps_slider.setMaximumWidth(80)
            self.fps_slider.setToolTip("Playback speed of the viewer (frames per second).\n"
                                       "15 fps for original animations, 30 or 60 fps for converted ones.")
            self.fps_slider.valueChanged.connect(self.set_fps)
            toolbar_layout.addWidget(self.fps_slider)

            self.frame_label = QLabel("Frame: 0")
            self.frame_label.setStyleSheet("color:white; padding:4px 8px;")
            # Reserve room for the widest value up front (left-aligned) so the number growing
            # from 1 to 3-4 digits during playback doesn't widen the label and shove the rest of
            # the toolbar sideways. 4 digits covers any frame count (255 max in a .dat, ~4x that
            # once interpolated to 60 fps).
            self.frame_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.frame_label.setFixedWidth(
                QFontMetrics(self.frame_label.font()).horizontalAdvance("Frame: 8888") + 20)
            toolbar_layout.addWidget(self.frame_label)

            # Frame slider
            self.frame_slider = QSlider(Qt.Orientation.Horizontal)
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
            self.frame_slider.setStyleSheet("color:white;")
            self.frame_slider.valueChanged.connect(self.set_frame)
            toolbar_layout.addWidget(self.frame_slider)

            self.anim_label = QLabel("Anim:")
            self.anim_label.setStyleSheet("color:white; padding:4px 4px;")
            toolbar_layout.addWidget(self.anim_label)

            self.anim_selector = QSpinBox()
            self.anim_selector.setValue(0)
            self.anim_selector.setStyleSheet("color:white; background:#333; padding:2px;")
            self.anim_selector.valueChanged.connect(self.set_animation)
            toolbar_layout.addWidget(self.anim_selector)

            # Frame / animation authoring tools. Grouped under one small dropdown so the
            # already-busy toolbar gains a single button rather than four: create a new
            # animation from a frame range of the current one, add or delete a frame.
            self._anim_tools_menu = QMenu(self)
            act_add_frame = QAction("Add frame after current (copy)", self)
            act_add_frame.setToolTip("Insert a copy of the current frame right after it, ready\n"
                                     "to be posed into the next keyframe.")
            act_add_frame.triggered.connect(self._add_frame_after_current)
            self._anim_tools_menu.addAction(act_add_frame)
            act_del_frame = QAction("Delete current frame", self)
            act_del_frame.setToolTip("Remove the frame currently shown (keeps at least one).")
            act_del_frame.triggered.connect(self._delete_current_frame)
            self._anim_tools_menu.addAction(act_del_frame)
            self._anim_tools_menu.addSeparator()
            act_new_from_range = QAction("New animation from frame range…", self)
            act_new_from_range.setToolTip("Create a new animation (added at the end of the list)\n"
                                          "whose frames are a copy of a chosen frame range of the\n"
                                          "current animation.")
            act_new_from_range.triggered.connect(self._new_animation_from_range)
            self._anim_tools_menu.addAction(act_new_from_range)
            act_dup_anim = QAction("Duplicate current animation", self)
            act_dup_anim.setToolTip("Copy the whole current animation into a new one at the end\n"
                                    "of the list.")
            act_dup_anim.triggered.connect(self._duplicate_current_animation)
            self._anim_tools_menu.addAction(act_dup_anim)
            act_del_anim = QAction("Delete current animation", self)
            act_del_anim.setToolTip("Remove the whole animation currently shown (keeps at least\n"
                                    "one). Note: later animation ids shift down by one.")
            act_del_anim.triggered.connect(self._delete_current_animation)
            self._anim_tools_menu.addAction(act_del_anim)

            self.anim_tools_btn = QToolButton()
            self.anim_tools_btn.setText("Frames ▾")
            self.anim_tools_btn.setMenu(self._anim_tools_menu)
            self.anim_tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.anim_tools_btn.setToolTip("Create and edit animation frames")
            self.anim_tools_btn.setStyleSheet(
                "QToolButton{background:#4a6e8a; color:white; padding:4px 10px; border-radius:3px;}"
                "QToolButton::menu-indicator{image:none;}")
            toolbar_layout.addWidget(self.anim_tools_btn)

            # Weapon overlay selector - populated (and shown) only for character bodies via
            # set_weapon_options(); hidden for monsters/weapons. Lets the user pick which loaded
            # weapon model to display in the character's hand, or none.
            # NOTE: this toolbar is a QToolBar - addWidget() wraps each widget in a QAction, and
            # the TOOLBAR's layout obeys the ACTION's visibility, not the widget's. Calling
            # widget.setVisible(True) later is silently overridden, so the show/hide of the
            # weapon controls must go through these actions (set_weapon_options).
            self.weapon_label = QLabel("Weapon:")
            self.weapon_label.setStyleSheet("color:white; padding:4px 4px;")
            self._weapon_label_action = toolbar_layout.addWidget(self.weapon_label)
            self._weapon_label_action.setVisible(False)
            self.weapon_selector = QComboBox()
            self.weapon_selector.setStyleSheet("color:white; background:#333; padding:2px;")
            self.weapon_selector.setToolTip("Show a weapon model in the character's hand, played on\n"
                                            "the same animation. Lists the weapon files loaded in the\n"
                                            "session; defaults to this character's first weapon.")
            self.weapon_selector.currentIndexChanged.connect(self._on_weapon_selected)
            self._weapon_selector_action = toolbar_layout.addWidget(self.weapon_selector)
            self._weapon_selector_action.setVisible(False)

            self.export_gltf_btn = QPushButton("Export glTF")
            self.export_gltf_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.export_gltf_btn.setToolTip("Export the loaded model (mesh, skeleton, textures and all animations)\n"
                                            "to a .glb file, importable in Blender (File > Import > glTF 2.0)")
            self.export_gltf_btn.clicked.connect(self.export_gltf)
            toolbar_layout.addWidget(self.export_gltf_btn)

            self.import_gltf_btn = QPushButton("Import glTF")
            self.import_gltf_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.import_gltf_btn.setToolTip("Replace the mesh of the loaded model with the one from a .glb file\n"
                                            "(e.g. edited in Blender, then File > Export > glTF 2.0).\n"
                                            "Skeleton, animations and every other section are kept from the\n"
                                            "current file. Save afterwards to write the new mesh into the .dat.")
            self.import_gltf_btn.clicked.connect(self.import_gltf)
            toolbar_layout.addWidget(self.import_gltf_btn)

            self.fps60_btn = QPushButton("To 30/60 FPS")
            self.fps60_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.fps60_btn.setToolTip("Insert interpolated frames between each frame of the current animation,\n"
                                      "so the 15 fps animation becomes a 30 or a 60 fps one (asked on click).\n"
                                      "Save the file afterwards to write the new frames in the .dat file.")
            self.fps60_btn.clicked.connect(self.convert_current_anim_to_60fps)
            toolbar_layout.addWidget(self.fps60_btn)

            self.fps60_all_btn = QPushButton("All to 30/60 FPS")
            self.fps60_all_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            self.fps60_all_btn.setToolTip("Insert interpolated frames in every animation of the current file,\n"
                                          "so all 15 fps animations become 30 or 60 fps ones (asked on click).\n"
                                          "Save the file afterwards to write the new frames in the .dat file.")
            self.fps60_all_btn.clicked.connect(self.convert_all_anims_to_60fps)
            toolbar_layout.addWidget(self.fps60_all_btn)

            # Spacer: QToolBar has no addStretch, so push the remaining controls to the right with
            # an expanding empty widget instead (the standard Qt trick for a toolbar spacer).
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            toolbar_layout.addWidget(spacer)

            # Right side controls
            reset_btn = QPushButton("Reset View")
            reset_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            # via lambda, not the bound method, so it follows a rebuilt gl_widget (release/restore)
            reset_btn.clicked.connect(lambda: self.gl_widget.reset_view())
            toolbar_layout.addWidget(reset_btn)

            # The toolbar has grown a lot of controls (texture/wireframe/skeleton toggles, FPS +
            # frame + anim selectors, weapon overlay + hand-bone pickers, fps-conversion, gltf
            # import/export...) and no longer fits in a typical windowed (non-maximized) width. A
            # plain QWidget+QHBoxLayout propagated its full unwrapped minimumSizeHint (2700+ px) up
            # to whatever container held it - inside the multi-file shell's QSplitter, that became
            # a hard floor on the 3D pane's width, and the splitter could never shrink it below
            # that to give more room to the file list. QToolBar's own layout instead hides whatever
            # doesn't fit behind a small "»" overflow button (its minimumSizeHint stays tiny), so
            # the splitter is free to shrink the pane - nothing is ever clipped, just tucked behind
            # one click when the pane is narrower than every control laid out in a single row.
            layout.addWidget(toolbar)

            # Add the OpenGL widget (this is the 3D view!)
            layout.addWidget(self.gl_widget, 1)  # The 1 makes it stretch to fill available space
            self._gl_layout_index = layout.indexOf(self.gl_widget)

            # Collapsible Playlist Section
            self.playlist_container = QWidget()
            self.playlist_container.setStyleSheet("background:#2a2a2f; border-top: 1px solid #3a3a3f;")

            # Create bone editor (independent widget)
            self.bone_editor = AnimEditor()

            # Connect bone editor signals to handlers
            self.bone_editor.bone_selected.connect(self._on_bone_selected)
            self.bone_editor.bone_length_changed.connect(self._on_bone_length_changed)
            self.bone_editor.bone_parent_changed.connect(self._on_bone_parent_changed)
            self.bone_editor.add_bone_requested.connect(self._on_add_bone_requested)
            self.bone_editor.reset_skeleton_requested.connect(self._on_reset_skeleton_requested)
            self.bone_editor.animation_rotation_changed.connect(self._on_animation_rotation_changed)
            self.bone_editor.animation_position_changed.connect(self.on_frame_position_changed)
            self.bone_editor.animation_scale_changed.connect(self._on_animation_scale_changed)
            self.bone_editor.frame_scale_mode_changed.connect(self._on_frame_scale_mode_changed)

            # Connect signals to update bone editor
            self.frame_changed.connect(self._update_bone_editor_frame)
            self.animation_changed.connect(self._update_bone_editor_animation)

            # Direct manipulation in the 3D view
            self._connect_gl_signals()

            # B = add a child bone to the selected joint (works with focus
            # anywhere in the 3D tab, only while the skeleton is displayed)
            self._add_bone_shortcut = QShortcut(QKeySequence("B"), self)
            self._add_bone_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._add_bone_shortcut.activated.connect(self._on_add_bone_shortcut)

            # Add bone editor to layout
            layout.addWidget(self.bone_editor)

            playlist_main_layout = QVBoxLayout(self.playlist_container)
            playlist_main_layout.setContentsMargins(0, 0, 0, 0)
            playlist_main_layout.setSpacing(0)

            # Playlist header (always visible)
            playlist_header = QWidget()
            playlist_header.setStyleSheet("background:#2a2a2f; padding:5px;")
            playlist_header.setCursor(Qt.CursorShape.PointingHandCursor)
            header_layout = QHBoxLayout(playlist_header)
            header_layout.setContentsMargins(8, 4, 8, 4)

            # Expand/collapse arrow
            self.expand_arrow = QLabel("▶")
            self.expand_arrow.setStyleSheet("color:white; font-size:12px; font-weight:bold;")
            self.expand_arrow.setFixedWidth(20)
            header_layout.addWidget(self.expand_arrow)

            # Playlist title with count
            self.playlist_title = QLabel("Playlist (0 animations)")
            self.playlist_title.setStyleSheet("color:white; font-weight:bold;")
            header_layout.addWidget(self.playlist_title)

            # Quick action buttons (always visible)
            self.play_playlist_quick_btn = QPushButton("▶ Play")
            self.play_playlist_quick_btn.setStyleSheet("background:#6a8a4e; color:white; padding:2px 8px; border-radius:3px; font-size:10px;")
            self.play_playlist_quick_btn.clicked.connect(self.play_playlist)
            self.play_playlist_quick_btn.setMaximumWidth(60)
            header_layout.addWidget(self.play_playlist_quick_btn)

            self.stop_playlist_quick_btn = QPushButton("■ Stop")
            self.stop_playlist_quick_btn.setStyleSheet("background:#8a6e4a; color:white; padding:2px 8px; border-radius:3px; font-size:10px;")
            self.stop_playlist_quick_btn.clicked.connect(self.stop_playlist)
            self.stop_playlist_quick_btn.setMaximumWidth(60)
            header_layout.addWidget(self.stop_playlist_quick_btn)

            self.loop_quick_cb = QCheckBox("Loop")
            self.loop_quick_cb.setStyleSheet("color:white; font-size:10px;")
            self.loop_quick_cb.toggled.connect(self.set_loop_playlist)
            header_layout.addWidget(self.loop_quick_cb)

            header_layout.addStretch()

            # Make header clickable
            playlist_header.mousePressEvent = self.toggle_playlist

            playlist_main_layout.addWidget(playlist_header)

            # Expandable content (initially hidden)
            self.playlist_content = QWidget()
            self.playlist_content.setVisible(False)
            content_layout = QVBoxLayout(self.playlist_content)
            content_layout.setContentsMargins(8, 4, 8, 8)
            content_layout.setSpacing(4)

            # Playlist list
            self.playlist_list = QListWidget()
            self.playlist_list.setStyleSheet("background:#1a1a1f; color:white; border: 1px solid #3a3a3f;")
            self.playlist_list.setMaximumHeight(120)
            content_layout.addWidget(self.playlist_list)

            # Playlist management buttons
            playlist_buttons = QHBoxLayout()

            self.add_to_playlist_btn = QPushButton("Add Current")
            self.add_to_playlist_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px;")
            self.add_to_playlist_btn.clicked.connect(self.add_current_to_playlist)
            playlist_buttons.addWidget(self.add_to_playlist_btn)

            self.add_custom_btn = QPushButton("Add Custom")
            self.add_custom_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px;")
            self.add_custom_btn.clicked.connect(self.add_custom_to_playlist)
            playlist_buttons.addWidget(self.add_custom_btn)

            self.remove_playlist_btn = QPushButton("Remove")
            self.remove_playlist_btn.setStyleSheet("background:#8a4a6e; color:white; padding:4px;")
            self.remove_playlist_btn.clicked.connect(self.remove_from_playlist)
            playlist_buttons.addWidget(self.remove_playlist_btn)

            self.clear_playlist_btn = QPushButton("Clear All")
            self.clear_playlist_btn.setStyleSheet("background:#8a4a6e; color:white; padding:4px;")
            self.clear_playlist_btn.clicked.connect(self.clear_playlist)
            playlist_buttons.addWidget(self.clear_playlist_btn)

            content_layout.addLayout(playlist_buttons)

            # Playback controls
            playback_controls = QHBoxLayout()

            self.play_playlist_btn = QPushButton("Play Playlist")
            self.play_playlist_btn.setStyleSheet("background:#6a8a4e; color:white; padding:4px;")
            self.play_playlist_btn.clicked.connect(self.play_playlist)
            playback_controls.addWidget(self.play_playlist_btn)

            self.stop_playlist_btn = QPushButton("Stop Playlist")
            self.stop_playlist_btn.setStyleSheet("background:#8a6e4a; color:white; padding:4px;")
            self.stop_playlist_btn.clicked.connect(self.stop_playlist)
            playback_controls.addWidget(self.stop_playlist_btn)

            self.loop_playlist_cb = QCheckBox("Loop Playlist")
            self.loop_playlist_cb.setStyleSheet("color:white;")
            self.loop_playlist_cb.toggled.connect(self.set_loop_playlist)
            playback_controls.addWidget(self.loop_playlist_cb)

            playback_controls.addStretch()
            content_layout.addLayout(playback_controls)

            playlist_main_layout.addWidget(self.playlist_content)

            layout.addWidget(self.playlist_container)

            # Info label. Word-wrapped so its long single-line text doesn't become a hard minimum
            # width on the whole 3D pane - a QLabel with wrapping off reports its FULL unwrapped
            # text width as its minimumSizeHint, which propagates up through this pane into the
            # multi-file shell's QSplitter and pins the file list to a sliver in anything narrower
            # than that (see the toolbar_scroll fix just above for the same class of issue).
            self.info = QLabel(
                f"LMB: Rotate | RMB: Pan | Scroll: Zoom | Click joint: Select bone | "
                f"Drag ring: Rotate bone | Ctrl+Drag: Bone length"
            )
            self.info.setWordWrap(True)
            self.info.setStyleSheet("background:#1a1a1f; color:#aaa; padding:4px 8px; font-size:10px;")
            # RichText so the budget figures below can be coloured (green/orange/red) as they
            # approach the engine limits; the base #aaa colour still applies to the plain text.
            self.info.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(self.info)
        else:
            # Without controls, just show the OpenGL widget
            layout.addWidget(self.gl_widget, 1)

    def toggle_playlist(self, event=None):
        """Toggle playlist expand/collapse"""
        self.playlist_expanded = not self.playlist_expanded
        self.playlist_content.setVisible(self.playlist_expanded)

        # Update arrow direction
        if self.playlist_expanded:
            self.expand_arrow.setText("▼")
            # Adjust container height
            self.playlist_container.setMaximumHeight(300)
        else:
            self.expand_arrow.setText("▶")
            # Collapse to just header height
            self.playlist_container.setMaximumHeight(50)

    # Playlist management methods
    def add_current_to_playlist(self):
        """Add current animation to playlist"""
        self.playlist.append(self.current_anim_id)
        self._update_playlist_display()

    def add_custom_to_playlist(self):
        """Add custom animation ID to playlist"""
        anim_id, ok = QInputDialog.getInt(self, "Add Animation",
                                          "Enter animation ID:",
                                          value=0,
                                          min=0,
                                          max=len(self.ifrit_manager.enemy.animation_data.animations) - 1)
        if ok:
            self.playlist.append(anim_id)
            self._update_playlist_display()

    def remove_from_playlist(self):
        """Remove selected animation from playlist"""
        current_row = self.playlist_list.currentRow()
        if current_row >= 0 and current_row < len(self.playlist):
            self.playlist.pop(current_row)
            self._update_playlist_display()

    def clear_playlist(self):
        """Clear entire playlist"""
        self.playlist.clear()
        self._update_playlist_display()

    def _update_playlist_display(self):
        """Update the playlist display list"""
        self.playlist_list.clear()
        for i, anim_id in enumerate(self.playlist):
            item_text = f"{i + 1}. Animation {anim_id}"
            # Highlight current playing item
            if self.playlist_mode and i == self.current_playlist_index:
                item_text = f"▶ {item_text}"
            item = QListWidgetItem(item_text)
            self.playlist_list.addItem(item)

        # Update title with count
        count_text = f"Playlist ({len(self.playlist)} animation{'s' if len(self.playlist) != 1 else ''})"
        self.playlist_title.setText(count_text)

    def play_playlist(self):
        """Start playing the playlist"""
        if not self.playlist:
            QMessageBox.information(self, "Playlist Empty",
                                    "Please add animations to the playlist first.")
            return

        # Stop any current playlist playback
        self.stop_playlist()

        self.playlist_mode = True
        self.current_playlist_index = 0
        self.loop_playlist = self.loop_playlist_cb.isChecked()
        self.loop_quick_cb.setChecked(self.loop_playlist)

        # Start first animation in playlist
        self._play_playlist_item()

    def _play_playlist_item(self):
        """Play the current playlist item"""
        if self.current_playlist_index >= len(self.playlist):
            # Playlist finished
            if self.loop_playlist:
                # Loop back to start
                self.current_playlist_index = 0
                self._play_playlist_item()
            else:
                # Stop playlist
                self.playlist_mode = False
                self.stop_playlist()
            return

        # Set the animation
        anim_id = self.playlist[self.current_playlist_index]
        self.set_animation(anim_id)
        self.animation_changed.emit()

        # Reset frame
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        self.update_animated_mesh()
        self.update_skeleton()

        # Start animation if not already playing
        if not self.animating:
            self.timer.start(1000 // self.fps)
            self.play_btn.setText("Pause")
            self.animating = True

        self._update_playlist_display()

    def stop_playlist(self):
        """Stop playlist playback"""
        self.playlist_mode = False
        self.current_playlist_index = 0

        # Stop animation if playing
        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False

        self._update_playlist_display()
        if hasattr(self, 'bone_editor'):
            self._update_gizmo()

    def set_loop_playlist(self, checked):
        """Set whether playlist should loop"""
        self.loop_playlist = checked
        # Sync the quick checkbox
        if hasattr(self, 'loop_quick_cb'):
            self.loop_quick_cb.blockSignals(True)
            self.loop_quick_cb.setChecked(checked)
            self.loop_quick_cb.blockSignals(False)

    # ── GL surface lifecycle (only the active file's viewer keeps a live context) ──
    def _configure_gl_widget(self):
        """Apply the per-manager settings to self.gl_widget. Run on creation and on rebuild."""
        gl = self.gl_widget
        # Managers providing real texture alpha (Seed) disable black keying
        gl.black_is_transparent = getattr(self.ifrit_manager, 'texture_black_is_transparent', True)
        # Backface culling: 'all' = game-exact (default), 'duplicates', 'off'
        gl.backface_cull = getattr(self.ifrit_manager, 'backface_cull_mode', 'all')
        # Direct skeleton edits in the view are blocked during playback
        gl.is_edit_allowed = lambda: not self.animating

    def _connect_gl_signals(self):
        """Wire the GL widget's direct-manipulation signals to this widget's handlers. Run on
        creation and on rebuild (a rebuilt gl_widget needs its signals reconnected)."""
        self.gl_widget.bone_picked.connect(self._on_bone_picked_in_view)
        self.gl_widget.bone_length_dragged.connect(self._on_bone_length_dragged)
        self.gl_widget.bone_length_drag_finished.connect(self._on_bone_length_drag_finished)
        self.gl_widget.bone_rotation_dragged.connect(self._on_bone_rotation_dragged)
        self.gl_widget.bone_rotation_drag_finished.connect(self._on_bone_rotation_drag_finished)

    def release_gl_widget(self):
        """Destroy the OpenGL surface + its GL context, freeing the driver of one live context,
        when this viewer's file is switched away from. All the model data lives in the manager, so
        restore_gl_widget() rebuilds an identical view on demand. No-op if there's no controls
        toolbar (embedded viewers) or it's already released."""
        if self._gl_layout_index is None or getattr(self, 'gl_widget', None) is None:
            return
        if self.animating:
            self.timer.stop()
            self.animating = False
        self._main_layout.removeWidget(self.gl_widget)
        self.gl_widget.setParent(None)
        self.gl_widget.deleteLater()
        self.gl_widget = None

    def restore_gl_widget(self):
        """Rebuild the OpenGL surface after release_gl_widget() and re-push the model (its GL
        context is created lazily by Qt when the widget is next actually shown). No-op if the
        surface is already live."""
        if self._gl_layout_index is None or getattr(self, 'gl_widget', None) is not None:
            return
        self.gl_widget = FF8OpenGLWidget(self)
        self._configure_gl_widget()
        self._main_layout.insertWidget(self._gl_layout_index, self.gl_widget, 1)
        self._connect_gl_signals()
        self.load_file()          # re-push geometry + textures from the (still-loaded) manager

    def next_frame(self):
        """Advance to next frame with interpolation"""
        if self.gl_widget is None:          # surface released (this file isn't the active viewer)
            return
        max_frames = self.get_max_frames()

        if max_frames > 0:
            # Update interpolation step
            if self.animating:
                self.interp_step += 1.0  # One animation frame per timer tick
                if self.interp_step >= 1.0:
                    self.interp_step = 0.0
                    self.current_frame = (self.current_frame + 1) % max_frames
                    self.next_frame_index = (self.current_frame + 1) % max_frames
                    self._update_frame_position_selection()
                    # Check if animation finished (when we wrap around to frame 0)
                    if self.current_frame == 0 and self.playlist_mode:
                        # Current animation finished, move to next in playlist
                        self.current_playlist_index += 1
                        self._play_playlist_item()
                        self.animation_changed.emit()
                        return
            else:
                # When not animating, just update to current frame
                self.update_animated_mesh()
                self.update_skeleton()
                return

            # Update both mesh and skeleton
            self.update_animated_mesh()
            self.update_skeleton()

    def load_file(self):
        if self.animating:
            self.timer.stop()
            if hasattr(self, 'play_btn'):
                self.play_btn.setText("Play")
            self.animating = False

        self.current_anim_id = 0
        self.current_frame = 0
        self.interp_step = 0.0
        self.next_frame_index = 1
        # Constant index/UV/colored lists + textures (body, plus the weapon if one is overlaid);
        # this also pushes the textures. Colored (untextured) primitives are unused by monsters
        # but present in battle-stage groups and magic-effect models.
        self._refresh_static_geometry()
        # Then this frame's vertex positions (body + weapon).
        self.update_animated_mesh()
        self.gl_widget.reset_view()

        self._update_model_translation()
        self.update_skeleton()

        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
        if hasattr(self, 'anim_selector'):
            if self.ifrit_manager.enemy.animation_data.nb_animations:
                nb = len(self.ifrit_manager.enemy.animation_data.animations)
                self.anim_selector.setRange(0, nb - 1)
                self.anim_selector.setValue(0)
                self.anim_selector.setToolTip(f"Nb animation: {nb}")
            else:
                self.anim_selector.setRange(0, 0)
                self.anim_selector.setEnabled(False)
                self.anim_selector.setToolTip("No animation data")

        self._update_info_label()
        if hasattr(self, 'bone_editor'):
            if self.ifrit_manager.enemy.bone_data and self.ifrit_manager.enemy.bone_data.bones:
                # Re-enable in case the previous file had no bone data
                self.bone_editor.setEnabled(True)
                self.bone_editor.setVisible(True)
                bone_count = len(self.ifrit_manager.enemy.bone_data.bones) - 1
                self.bone_editor.set_bone_range(bone_count)
                # Set the initial bone ID to 0 and update
                self.bone_editor.bone_spin.setValue(0)
                self._update_bone_editor_selection()
                self._update_frame_position_selection()
            else:
                self.bone_editor.setEnabled(False)
                self.bone_editor.setVisible(False)

        self._set_reference_position()
        self.gl_widget.reset_view()

    # ── Vertex / primitive budget readout (info bar) ──────────────────
    # The engine limits these are checked against were measured in FF8_EN.exe:
    #   * 4096 verts per OBJECT - the 12-bit face index in the geometry format and in the
    #     game's ParsePolygons. Note an object is a group INSIDE a model; a model can hold
    #     several objects, so this is flagged per-object (the largest one), not per-model.
    #   * ~3584 primitives per FRAME for the whole battle scene - the per-frame primitive
    #     packet buffer is shared by every entity (all party + enemies) and every effect, so
    #     one model's prim count is only its share of that budget.
    _VERT_CAP_PER_OBJECT = 4096
    _SCENE_PRIM_BUDGET = 3584

    def _geometry_budget_html(self):
        """Raw-geometry vertex/primitive counts vs the engine limits, as coloured HTML.

        Sourced from geometry_data (the raw sections), NOT the culled GL lists, so the
        figures reflect what actually gets written into the engine buffers and don't wobble
        as the view rotates or the hidden-face toggle flips. Counts the overlaid weapon too
        (it is drawn in the same scene), since it shares the per-frame primitive budget."""
        managers = [self.ifrit_manager]
        if self._weapon_manager is not None:
            managers.append(self._weapon_manager)

        total_verts = worst_obj_verts = nb_objects = total_prims = 0
        for mgr in managers:
            geo = getattr(mgr.enemy, 'geometry_data', None)
            if geo is None:
                continue
            for obj in geo.object_data:
                nb_objects += 1
                v = len(obj.get_vertices())
                total_verts += v
                worst_obj_verts = max(worst_obj_verts, v)
                total_prims += (obj.nb_triangle + obj.nb_quad
                                + obj.nb_colored_triangle + obj.nb_colored_quad)

        # per-object vertex figure: warn as it nears the hard 4096 cap, red once over
        if worst_obj_verts > self._VERT_CAP_PER_OBJECT:
            vcol = "#ff5555"
        elif worst_obj_verts >= 3500:
            vcol = "#ffb000"
        else:
            vcol = "#7fd07f"

        pct = 100.0 * total_prims / self._SCENE_PRIM_BUDGET
        # this single model vs the SHARED scene budget: >33% means ~3 of them fill a frame
        if pct > 100.0:
            pcol = "#ff5555"
        elif pct > 33.0:
            pcol = "#ffb000"
        else:
            pcol = "#7fd07f"

        bd = getattr(self.ifrit_manager.enemy, 'bone_data', None)
        nb_bones = len(bd.bones) if bd and bd.bones else 0
        obj_note = f" in {nb_objects} objects" if nb_objects != 1 else ""
        return (f"Verts: {total_verts}{obj_note} "
                f"(largest object <span style='color:{vcol}'>{worst_obj_verts} / "
                f"{self._VERT_CAP_PER_OBJECT}</span>) | "
                f"Prims: <span style='color:{pcol}'>{total_prims}</span> "
                f"(~{pct:.0f}% of {self._SCENE_PRIM_BUDGET} scene budget) | "
                f"Bones: {nb_bones}")

    def _update_info_label(self):
        """Rebuild the info bar: geometry budget figures followed by the control hints."""
        if not hasattr(self, 'info'):
            return
        help_text = ("LMB: Rotate | RMB: Pan | Scroll: Zoom | Click joint: Select bone | "
                     "Drag ring: Rotate bone | Ctrl+Drag: Bone length")
        self.info.setText(self._geometry_budget_html() + " | " + help_text)

    def _push_textures_to_gl(self):
        """Send extracted texture PNGs to the GL widget.

        When a weapon is overlaid the atlas is body pixmaps followed by weapon pixmaps, and the
        face ids already carry _WEAPON_TEX_OFFSET on weapon faces (added in _refresh_static_
        geometry), so the two never collide. An EXPLICIT id->index map is used rather than the
        rank heuristic: it clamps when there are more distinct ids than pixmaps, which would cross
        the two models' textures."""
        # Refresh per loaded file: False when the manager rebuilt the images
        # with real CLUT-word alpha (see IfritManager._apply_clut_alpha)
        self.gl_widget.black_is_transparent = getattr(
            self.ifrit_manager, 'texture_black_is_transparent', True)

        body_pix = [td.texture_image for td in self.ifrit_manager.texture_data
                    if td.texture_image is not None]
        all_ids = ([raw_id for (_, _, raw_id, _b) in self.gl_widget.triangles_uv] +
                   [raw_id for (_, _, raw_id, _b) in self.gl_widget.quads_uv])
        WT = FF8OpenGLWidget._WEAPON_TEX_OFFSET

        if self._weapon_manager is None:
            if not body_pix:
                return
            self.gl_widget.set_texture_pixmaps(body_pix, all_ids)
            return

        weapon_pix = [td.texture_image for td in self._weapon_manager.texture_data
                      if td.texture_image is not None]
        # Split the merged face ids back into body (< offset) and weapon (>= offset), and map each
        # model's ids onto its own slice of the combined pixmap list.
        body_ids = [i for i in all_ids if i < WT]
        weapon_ids = [i for i in all_ids if i >= WT]
        tex_map = FF8OpenGLWidget._rank_texture_map(body_ids, len(body_pix), 0)
        tex_map.update(FF8OpenGLWidget._rank_texture_map(weapon_ids, len(weapon_pix), len(body_pix)))
        self.gl_widget.set_texture_pixmaps_explicit(body_pix + weapon_pix, tex_map)

    # ── Composite (body + weapon) rendering ───────────────────────────
    @staticmethod
    def _offset_uv(entry, vertex_offset, tex_offset):
        indices, uvs, tex_id, bias = entry
        return (tuple(i + vertex_offset for i in indices), uvs, tex_id + tex_offset, bias)

    @staticmethod
    def _offset_colored(entry, vertex_offset):
        indices, rgb, bias = entry
        return (tuple(i + vertex_offset for i in indices), rgb, bias)

    def _refresh_static_geometry(self):
        """(Re)send the per-model-constant geometry (triangles/quads/UV/colored faces) + textures.
        When a weapon is set, the body's lists are concatenated with the weapon's, with the
        weapon's vertex indices shifted past the body's and its texture ids shifted up by
        _WEAPON_TEX_OFFSET. Only the vertex POSITIONS change per animation frame (update_animated_
        mesh); these index/uv lists stay put, so this runs on load and on weapon change, not per
        frame."""
        ih = self._show_hidden_faces
        body = self.ifrit_manager.enemy.geometry_data
        self._body_vertex_count = len(body.get_vertices())
        tris = body.get_triangles(include_hidden=ih)
        quads = body.get_quads(include_hidden=ih)
        tri_uv = body.get_triangles_with_uv(include_hidden=ih)
        quad_uv = body.get_quads_with_uv(include_hidden=ih)
        col_tri = body.get_colored_triangles_with_color(include_hidden=ih)
        col_quad = body.get_colored_quads_with_color(include_hidden=ih)

        if self._weapon_manager is not None:
            wgeo = self._weapon_manager.enemy.geometry_data
            off = self._body_vertex_count
            wt = FF8OpenGLWidget._WEAPON_TEX_OFFSET
            tris = tris + [tuple(i + off for i in t) for t in wgeo.get_triangles(include_hidden=ih)]
            quads = quads + [tuple(i + off for i in q) for q in wgeo.get_quads(include_hidden=ih)]
            tri_uv = tri_uv + [self._offset_uv(e, off, wt)
                               for e in wgeo.get_triangles_with_uv(include_hidden=ih)]
            quad_uv = quad_uv + [self._offset_uv(e, off, wt)
                                 for e in wgeo.get_quads_with_uv(include_hidden=ih)]
            col_tri = col_tri + [self._offset_colored(e, off)
                                 for e in wgeo.get_colored_triangles_with_color(include_hidden=ih)]
            col_quad = col_quad + [self._offset_colored(e, off)
                                   for e in wgeo.get_colored_quads_with_color(include_hidden=ih)]

        self.gl_widget.set_triangles(tris)
        self.gl_widget.set_quads(quads)
        self.gl_widget.set_triangles_with_uv(tri_uv)
        self.gl_widget.set_quads_with_uv(quad_uv)
        self.gl_widget.set_colored_triangles(col_tri)
        self.gl_widget.set_colored_quads(col_quad)
        self._push_textures_to_gl()

    def _current_body_verts(self):
        """The body's vertices for the current frame - animated if it has animations, else the
        static mesh. Root translation is NOT baked in (paintGL applies it globally)."""
        en = self.ifrit_manager.enemy
        if not en.animation_data.nb_animations:
            return en.geometry_data.get_vertices()
        max_frames = self.get_max_frames()
        if max_frames == 0:
            return en.geometry_data.get_vertices()
        next_frame = (self.current_frame + 1) % max_frames
        return self.ifrit_manager.get_animated_vertices(
            anim_id=self.current_anim_id, frame_id=self.current_frame,
            next_frame_id=next_frame, step=self.interp_step)

    def _current_weapon_verts(self):
        """The weapon's vertices for the current frame, posed on the SAME animation index as the
        body (each model by its own frame count - see the composite-animation wiki), then
        translated by the weapon-root minus body-root delta - the game's actual placement rule.

        Verified in FF8_EN.exe (ProcessFieldEntitiesTransformation @0x508C90, root-bone case):
        the engine sets EACH model's root bone world translation to model_scale * root_pos >> 8,
        where root_pos is that model's OWN per-frame accumulated root position from its animation
        stream. The weapon's clip carries a different root track than the body's: the difference
        IS the in-hand offset (measured on d0w000: constant ~(-0.6,-0.2,1.6) during holds, arcing
        2-5 world units through attack swings - the root literally traces the hand). The viewer
        bakes no root into bone matrices and applies only the BODY's root globally (paintGL
        model_translation), so the weapon must be shifted by (weapon_root - body_root) here to
        land where the game puts it. No hand-bone attach exists in the files at all."""
        wm = self._weapon_manager
        en = wm.enemy
        if en.entity_type == EntityType.WEAPON_NO_ANIM:
            # Reduced weapon (Zell's gloves, Kiros's katals): no skeleton/animation of its own -
            # the mesh is skinned directly to the CHARACTER BODY's bones (one glove/blade per
            # hand, e.g. Zell verts bound to body bones 21/22), so it is posed by the BODY's
            # matrices at the body's frame and needs no root delta. "Two weapons, one per hand,
            # no independent movement" - by design.
            max_frames = self.get_max_frames()
            if max_frames == 0:
                return en.geometry_data.get_vertices()
            next_frame = (self.current_frame + 1) % max_frames
            return self.ifrit_manager.get_animated_vertices(
                anim_id=self.current_anim_id, frame_id=self.current_frame,
                next_frame_id=next_frame, step=self.interp_step,
                geometry=en.geometry_data)
        wm._ensure_matrices()          # re-expand the weapon anim (freed on multi-file load)
        if not en.animation_data.nb_animations:
            return en.geometry_data.get_vertices()
        wanim = self.current_anim_id if self.current_anim_id < en.animation_data.nb_animations else 0
        wmax = en.animation_data.animations[wanim].get_nb_frame()
        if wmax == 0:
            return en.geometry_data.get_vertices()
        wframe = self.current_frame % wmax
        wnext = (wframe + 1) % wmax
        verts = wm.get_animated_vertices(anim_id=wanim, frame_id=wframe,
                                         next_frame_id=wnext, step=self.interp_step)
        wroot = self._frame_root(wm, wanim, wframe, wnext, self.interp_step)
        broot = self._body_root_now()
        # Root-position units are NOT vertex units: get_pos_world() is raw/204.8 while the posed
        # vertices/bone matrices live in raw/128, and the two spaces mirror Z. So the delta maps
        # into vertex space as (x, y, -z) * (204.8/128 = 1.6). Calibrated empirically, not
        # guessed: sweeping (axis mapping x scale) over full attack swings of Squall/Seifer/
        # Irvine (model_scale 175/188/176), this mapping - and only this one - pins a weapon grip
        # vertex to the body's hand bone with a constant offset (std 0.004-0.005 world units over
        # 5-unit swing arcs, all three characters, best k = 1.60 exactly for each). k is
        # model_scale-independent.
        s = self._ROOT_DELTA_TO_VERTEX_SCALE
        dx = s * (wroot[0] - broot[0])
        dy = s * (wroot[1] - broot[1])
        dz = -s * (wroot[2] - broot[2])
        return [(x + dx, y + dy, z + dz) for (x, y, z) in verts]

    # get_pos_world (raw/204.8) -> vertex/bone-matrix units (raw/128): 204.8/128, exact.
    _ROOT_DELTA_TO_VERTEX_SCALE = 1.6

    @staticmethod
    def _frame_root(manager, anim_id, frame_id, next_frame_id=None, step=0.0):
        """A model's per-frame root position (world units, same convention set_model_translation
        uses), interpolated between frame and next like the vertices are."""
        ad = manager.enemy.animation_data
        if not ad.nb_animations or anim_id >= len(ad.animations):
            return (0.0, 0.0, 0.0)
        frames = ad.animations[anim_id].frames
        if not frames:
            return (0.0, 0.0, 0.0)

        def root_of(fid):
            fr = frames[min(fid, len(frames) - 1)]
            if len(fr.position) >= 3:
                return [fr.position[i].get_pos_world() for i in range(3)]
            return [0.0, 0.0, 0.0]

        pos = root_of(frame_id)
        if next_frame_id is not None and step:
            nxt = root_of(next_frame_id)
            pos = [a * (1.0 - step) + b * step for a, b in zip(pos, nxt)]
        return tuple(pos)

    def _body_root_now(self):
        """The body's root for the exact frame/interp state its vertices are posed at."""
        max_frames = self.get_max_frames()
        if max_frames == 0:
            return (0.0, 0.0, 0.0)
        next_frame = (self.current_frame + 1) % max_frames
        return self._frame_root(self.ifrit_manager, self.current_anim_id, self.current_frame,
                                next_frame, self.interp_step)

    def set_weapon_options(self, options, default_index=0):
        """Populate (and show) the Weapon selector for a character body. `options` is a list of
        (label, manager_or_None); a None manager is the 'body only' entry. default_index selects
        the entry to show first (the character's first weapon, per the caller). No-op without the
        controls (show_controls=False)."""
        self._weapon_options = list(options)
        if not hasattr(self, 'weapon_selector'):
            # No toolbar: still apply the default so a headless/embedded viewer can show a weapon.
            self._apply_weapon_option(default_index)
            return
        self.weapon_selector.blockSignals(True)
        self.weapon_selector.clear()
        for label, _ in self._weapon_options:
            self.weapon_selector.addItem(label)
        show = len(self._weapon_options) > 1
        # QToolBar-managed widgets show/hide through their wrapping QAction (see the toolbar
        # build) - setting the widget's own visibility does nothing there.
        self._weapon_label_action.setVisible(show)
        self._weapon_selector_action.setVisible(show)
        idx = default_index if 0 <= default_index < len(self._weapon_options) else 0
        self.weapon_selector.setCurrentIndex(idx)
        self.weapon_selector.blockSignals(False)
        self._apply_weapon_option(idx)

    def _on_weapon_selected(self, index):
        self._apply_weapon_option(index)

    def _apply_weapon_option(self, index):
        manager = (self._weapon_options[index][1]
                   if 0 <= index < len(self._weapon_options) else None)
        self._set_weapon_manager(manager)

    def _set_weapon_manager(self, manager):
        """Overlay `manager`'s weapon model (or clear it with None) and rebuild the merged mesh."""
        self._weapon_manager = manager
        if manager is not None:
            manager._ensure_matrices()
        self._refresh_static_geometry()
        self.update_animated_mesh()
        self.update_skeleton()
        self.gl_widget.reset_view()
        self._update_info_label()   # weapon overlay adds to the scene primitive total

    def get_max_frames(self):
        if not self.ifrit_manager.enemy.animation_data.nb_animations:
            return 0
        anim_section = self.ifrit_manager.enemy.animation_data
        if anim_section and self.current_anim_id < len(anim_section.animations):
            return anim_section.animations[self.current_anim_id].get_nb_frame()
        return 0

    def _set_reference_position(self):
        """Set the reference position from frame 0 of current animation"""
        pos_x, pos_y, pos_z = 0, 0, 0
        if self.current_anim_id < len(self.ifrit_manager.enemy.animation_data.animations):
            anim = self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id]
            if len(anim.frames) > 0 and len(anim.frames[0].position) >= 3:
                pos_x = anim.frames[0].position[0].get_pos_world()
                pos_y = anim.frames[0].position[1].get_pos_world()
                pos_z = anim.frames[0].position[2].get_pos_world()

        self.gl_widget.set_reference_position(pos_x, pos_y, pos_z)

    def set_animation(self, anim_id: int):
        """Switch to a different animation while preserving playback state."""
        # Store the current animation state
        was_animating = self.animating

        # Stop playback temporarily if it was running
        if was_animating:
            self.timer.stop()
            if hasattr(self, 'play_btn'):
                self.play_btn.setText("Play")
            self.animating = False

        # Switch animation and reset to frame 0
        self.current_anim_id = anim_id
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0

        # Update slider range for new animation
        max_frames = self.get_max_frames()
        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, max_frames - 1)

        self._set_reference_position()
        # Update the mesh and skeleton to the new animation's first frame
        self.update_animated_mesh()
        self.update_skeleton()
        self._update_model_translation()
        self.animation_changed.emit()

        # Restart animation if it was previously playing
        if was_animating:
            self.timer.start(1000 // self.fps)
            if hasattr(self, 'play_btn'):
                self.play_btn.setText("Pause")
            self.animating = True

    def _update_model_translation(self):
        """Update the model translation based on current frame position"""
        pos_x, pos_y, pos_z = 0, 0, 0
        if (self.current_anim_id < len(self.ifrit_manager.enemy.animation_data.animations) and
                self.current_frame < len(self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames)):
            frame = self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames[self.current_frame]
            if len(frame.position) >= 3:
                pos_x = frame.position[0].get_pos_world()
                pos_y = frame.position[1].get_pos_world()
                pos_z = frame.position[2].get_pos_world()


        self.gl_widget.set_model_translation(pos_x, pos_y, pos_z)

    def _update_frame_indicator(self):
        """Refresh the frame label and slider from current_frame. Kept separate from
        the skeleton so it still runs for models without bone data (e.g. seed field
        models), where update_skeleton returns early."""
        if hasattr(self, 'frame_label'):
            self.frame_label.setText(f"Frame: {self.current_frame}")
        if hasattr(self, 'frame_slider'):
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_frame)
            self.frame_slider.blockSignals(False)
        self.frame_changed.emit(self.current_frame)

    def update_skeleton(self):
        if not self.ifrit_manager or self.gl_widget is None:
            return
        # Reflect the current frame in the toolbar before any skeleton-only early return.
        self._update_frame_indicator()
        if not self.ifrit_manager.enemy.bone_data:
            self.gl_widget.set_skeleton_data([], [])
            self.gl_widget.set_show_skeleton(False)
            if hasattr(self, 'cb_skeleton'):
                self.cb_skeleton.setEnabled(False)
            return
        if hasattr(self, 'cb_skeleton'):
            self.cb_skeleton.setEnabled(True)

        skeleton_lines, bone_parents = self.ifrit_manager.get_skeleton_lines(
            anim_id=self.current_anim_id, frame_id=self.current_frame)

        # Set both lines and parents
        self.gl_widget.set_skeleton_data(skeleton_lines, bone_parents)
        self._update_gizmo()
        self._update_model_translation()
        self._update_frame_position_selection()
        self.gl_widget.update()

    def set_fps(self, fps: int):
        """Change the playback speed of the viewer."""
        self.fps = fps
        if hasattr(self, 'fps_label'):
            self.fps_label.setText(f"FPS: {fps}")
        if hasattr(self, 'fps_slider') and self.fps_slider.value() != fps:
            self.fps_slider.blockSignals(True)
            self.fps_slider.setValue(fps)
            self.fps_slider.blockSignals(False)
        # Apply the new speed immediately if an animation is playing
        if self.animating:
            self.timer.start(1000 // fps)

    def toggle_animation(self):
        """Start/stop animation"""
        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False
        else:
            self.timer.start(1000 // self.fps)
            self.play_btn.setText("Pause")
            self.animating = True
        # The gizmo hides during playback and comes back on pause
        if hasattr(self, 'bone_editor'):
            self._update_gizmo()

    def update_animated_mesh(self):
        """Push this frame's vertex positions to the GL widget. Only positions change per frame;
        the triangle/quad/UV index lists are constant and set by _refresh_static_geometry (on
        load and on weapon change). When a weapon is overlaid, its posed vertices are appended
        after the body's (indices in those lists already point past the body's vertex count)."""
        if self.gl_widget is None:          # surface released (not the active viewer)
            return
        body_verts = self._current_body_verts()
        self.current_animated_vertices = body_verts   # body only (used by gizmo/export)
        if self._weapon_manager is not None:
            verts = list(body_verts) + list(self._current_weapon_verts())
        else:
            verts = body_verts
        self.gl_widget.set_vertices(verts)
        self.gl_widget.update()

    def set_frame(self, value):
        """Jump to specific frame"""
        if not self.animating:
            self.current_frame = value
            self.next_frame_index = (self.current_frame + 1) % self.get_max_frames()
            self.interp_step = 0.0
            self.update_animated_mesh()
            self.update_skeleton()
            if hasattr(self, 'frame_slider'):
                self.frame_slider.blockSignals(True)
                self.frame_slider.setValue(self.current_frame)
                self.frame_slider.blockSignals(False)

    def reset_animation(self):
        """Reset to first frame"""
        if not self.ifrit_manager.enemy.animation_data.nb_animations:
            return
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        self.update_animated_mesh()
        self.update_skeleton()
        if self.animating:
            self.timer.stop()
            self.play_btn.setText("Play")
            self.animating = False
            # update_skeleton ran while still animating: bring the gizmo back
            if hasattr(self, 'bone_editor'):
                self._update_gizmo()

    def _on_texture_toggle(self, checked):
        """Toggle 3D mesh visibility"""
        self.gl_widget.set_show_texture(checked)

    def _on_wire_toggle(self, checked):
        self.gl_widget.set_show_wireframe(checked)

    def _on_hidden_faces_toggle(self, checked):
        """Unlike the other toggles this changes WHICH faces are in the mesh (not just a draw
        flag), so the triangle/quad/UV index lists must be rebuilt - re-run the same geometry
        refresh load_file() does, then repose this frame's vertices on top of it."""
        self._show_hidden_faces = checked
        self._refresh_static_geometry()
        self.update_animated_mesh()
        self.update_skeleton()

    def _on_axis_toggle(self, checked):
        self.gl_widget.set_show_axis(checked)

    def _on_skeleton_toggle(self, checked):
        self.gl_widget.set_show_skeleton(checked)
        if hasattr(self, 'skeleton_opts_btn'):
            self.skeleton_opts_btn.setEnabled(checked)   # options only apply with a skeleton

    def _on_gizmo_toggle(self, checked):
        self.gl_widget.set_show_gizmo(checked)

    def set_show_skeleton(self, show):
        self.gl_widget.set_show_skeleton(show)
        if hasattr(self, 'cb_skeleton'):
            self.cb_skeleton.setChecked(show)

    # Public methods for external control
    def reset_view(self):
        """Reset camera position"""
        self.gl_widget.reset_view()

    def set_show_wireframe(self, show):
        self.gl_widget.set_show_wireframe(show)
        if hasattr(self, 'cb_wire'):
            self.cb_wire.setChecked(show)

    def set_show_axis(self, show):
        self.gl_widget.set_show_axis(show)
        if hasattr(self, 'cb_axis'):
            self.cb_axis.setChecked(show)

    def get_gl_widget(self):
        """Return the underlying OpenGL widget for advanced control"""
        return self.gl_widget

    def export_gltf(self):
        """Export the loaded model to a glTF binary file (.glb), importable in Blender."""
        if not self.ifrit_manager.enemy.geometry_data.object_data:
            QMessageBox.warning(self, "Export glTF", "No model loaded in the 3D viewer.")
            return
        self.ifrit_manager._ensure_matrices()   # exporter reads frame.bone_matrices directly
        exporter = GltfExporter(self.ifrit_manager)
        default_name = exporter.model_name() + ".glb"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to glTF", default_name,
                                                   "glTF binary (*.glb)")
        if not file_path:
            return
        try:
            # Put the animation currently shown in the viewer first in the file,
            # so glTF players that auto-play show the same animation.
            exporter.export(file_path, first_animation_id=self.current_anim_id)
        except Exception as e:
            QMessageBox.critical(self, "Export glTF", f"Export failed: {e}")
            return
        QMessageBox.information(self, "Export glTF", f"Model exported to:\n{file_path}")

    def import_gltf(self):
        """Replace the mesh of the loaded model with the one from a .glb file.

        Only the geometry (section 2) is rebuilt; the skeleton, animations and
        every other section of the current file are preserved. The saved .dat is
        therefore a valid, animating monster whose only change is the mesh.
        """
        if not self.ifrit_manager.enemy.geometry_data.object_data:
            QMessageBox.warning(self, "Import glTF", "Load a .dat model first.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Import mesh from glTF", "",
                                                   "glTF binary (*.glb)")
        if not file_path:
            return
        try:
            stats = GltfImporter().import_into_enemy(file_path, self.ifrit_manager.enemy)
        except Exception as e:
            QMessageBox.critical(self, "Import glTF", f"Import failed: {e}")
            return
        # Refresh the viewer from the (now rebuilt) model.
        self.load_file()
        QMessageBox.information(
            self, "Import glTF",
            f"Mesh replaced from:\n{file_path}\n\n"
            f"Vertices: {stats['vertices']}   Triangles: {stats['triangles']}   "
            f"Bones used: {stats['bones_used']}\n\n"
            "Skeleton and animations were kept from the current file. "
            "Save the file to write the new mesh into the .dat.")

    def _get_slowable_animation_id_set(self):
        """Animations Slow status can reach: they have a lower frame limit.

        A character body has no sequence section, so this comes from its weapon file like
        the loop detection does — reading it from the body alone would find nothing and
        wrongly give its idle the full 255 frame limit.
        """
        return self._get_animation_usage()['slowable_set']

    def _get_animation_usage(self):
        """{'kind_dict', 'slowable_set', 'source'}, cached per loaded file."""
        origin_path = getattr(self.ifrit_manager.enemy, 'origin_path', "")
        if origin_path not in self._animation_usage_cache:
            usage = analyse_animation_usage(self.ifrit_manager.game_data, self.ifrit_manager.enemy)
            self._animation_usage_cache[origin_path] = usage
        usage = self._animation_usage_cache[origin_path]
        self.weapon_file_used = usage['source']
        return usage

    def _get_max_animation_frames(self, anim_id: int) -> int:
        """How long animation anim_id may be in this file.

        Battle .dat files store the frame count on one byte; other formats (e.g. field
        chara.one, uint16) can expose a higher limit. An animation the battle engine can
        play in slow motion has a lower limit still, since Slow doubles its frame count
        (see FF8GameData/dat/animsplitter.py).
        """
        max_frames = getattr(self.ifrit_manager, 'max_animation_frames', 255)
        slow_doubles = getattr(self.ifrit_manager, 'anim_slow_doubles_frame_count', True)
        can_be_slowed = anim_id in self._get_slowable_animation_id_set()
        return get_max_frame_for_animation(can_be_slowed, max_frames, slow_doubles)

    def _refresh_animation_count(self):
        """Splitting adds animations at the end of the section: show them in the selector."""
        if not hasattr(self, 'anim_selector'):
            return
        nb = len(self.ifrit_manager.enemy.animation_data.animations)
        if nb:
            self.anim_selector.setRange(0, nb - 1)
            self.anim_selector.setToolTip(f"Nb animation: {nb}")

    def _split_animation_to_fit(self, anim_id: int, factor: int, smooth_loop: bool, max_frames: int):
        """Cut an animation too long for the format in parts and chain them in the sequences.

        Returns the splitter report, or the reason it could not be done.
        """
        enemy = self.ifrit_manager.enemy
        try:
            return split_and_convert_animation(self.ifrit_manager.game_data,
                                               enemy.animation_data,
                                               getattr(enemy, 'seq_animation_data', None),
                                               enemy.bone_data.bones,
                                               anim_id, factor, smooth_loop, max_frames), ""
        except ValueError as e:
            return None, str(e)

    @staticmethod
    def _nb_frames_after_conversion(nb_frames: int, factor: int, smooth_loop: bool) -> int:
        """Frame count once (factor - 1) frames are inserted between each pair of frames.

        A smoothed loop also gets frames inserted between the last and the first one.
        """
        if smooth_loop:
            return nb_frames * factor
        return (nb_frames - 1) * factor + 1

    def _ask_target_fps(self, title: str):
        """Ask the frame rate to convert to. Returns None if the user cancels."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText("Convert to which frame rate?\n\n"
                       "60 fps: smoothest, but an animation gets 4x its frames and long ones\n"
                       "can go over the limit of the file format.\n"
                       "30 fps: 2x the frames only, so it stays under the limit more often.")
        button_60 = dialog.addButton("60 FPS", QMessageBox.ButtonRole.AcceptRole)
        button_30 = dialog.addButton("30 FPS", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        if dialog.clickedButton() == button_60:
            return 60
        if dialog.clickedButton() == button_30:
            return 30
        return None

    def _get_animation_kind_dict(self):
        """Which animations of the loaded file loop, read from the sequence section.

        A character body has no sequence section: its animations are driven by the
        program in its weapon file, so the weapon sitting next to it is read instead.
        Empty when nothing can be read, the caller then has to ask the user.
        """
        kind_dict = self._get_animation_usage()['kind_dict']
        if kind_dict:
            return kind_dict
        return self._ask_weapon_file_kind_dict()

    def _ask_weapon_file_kind_dict(self):
        """Last resort for a character whose weapon file is not next to it."""
        origin_path = getattr(self.ifrit_manager.enemy, 'origin_path', "")
        if not origin_path or find_character_weapon_file_list(origin_path):
            return {}  # not a character, or the weapons were there and unreadable
        answer = QMessageBox.question(
            self, "Weapon file needed",
            "This is a character model: the animations are driven by the program stored "
            "in its weapon file (dXwYYY.dat), which is not next to it.\n\n"
            "Select the weapon file of this character to detect the looping animations?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return {}
        weapon_path, _ = QFileDialog.getOpenFileName(self, "Select the weapon file",
                                                     str(pathlib.Path(origin_path).parent),
                                                     "Weapon file (*.dat);;All files (*)")
        if not weapon_path:
            return {}
        try:
            kind_dict, slowable_set = get_animation_usage_from_weapon_file(
                self.ifrit_manager.game_data, weapon_path,
                self.ifrit_manager.enemy.animation_data.nb_animations)
        except Exception:
            return {}
        if kind_dict:
            self.weapon_file_used = pathlib.Path(weapon_path).name
            self._animation_usage_cache[origin_path] = {
                'kind_dict': kind_dict, 'slowable_set': slowable_set,
                'source': self.weapon_file_used}
        return kind_dict

    def _ask_smooth_loop(self, title: str):
        """Fallback when the file has no sequence section to detect the loops from."""
        answer = QMessageBox.question(
            self, title,
            "The loops of this file cannot be detected (no animation sequence section).\n\n"
            "Smooth the transition from the last frame back to the first one?\n\n"
            "Yes: for looping animations (like the idle stance).\n"
            "No: for one-shot animations (like a death animation).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return None
        return answer == QMessageBox.StandardButton.Yes

    def convert_current_anim_to_60fps(self):
        """Insert interpolated frames in the current animation so it plays at 30 or 60 fps."""
        title = "To 30/60 FPS"
        anim_section = self.ifrit_manager.enemy.animation_data
        if not anim_section.nb_animations or self.current_anim_id >= len(anim_section.animations):
            QMessageBox.warning(self, title, "No animation loaded.")
            return
        if not self.ifrit_manager.enemy.bone_data:
            QMessageBox.warning(self, title, "No bone data loaded.")
            return

        anim = anim_section.animations[self.current_anim_id]
        nb_frames_before = len(anim.frames)
        if nb_frames_before < 2:
            QMessageBox.information(self, title, "The animation needs at least 2 frames to interpolate.")
            return

        target_fps = self._ask_target_fps(title)
        if target_fps is None:
            return

        # The sequence section says whether the game loops this animation, so the wrap
        # from the last frame back to the first one is only smoothed when it is played
        # in a loop. Files without that section still have to ask.
        kind_dict = self._get_animation_kind_dict()
        if kind_dict:
            kind = kind_dict.get(self.current_anim_id, ANIM_UNUSED)
            smooth_loop = is_looping(kind)
            detected_text = f"Detected as {ANIM_KIND_TEXT.get(kind, kind)} by the animation sequences"
            detected_text += f" of {self.weapon_file_used}.\n" if self.weapon_file_used else ".\n"
        else:
            smooth_loop = self._ask_smooth_loop(title)
            if smooth_loop is None:
                return
            detected_text = ""

        # native fps x factor = target fps (battle .dat: 15 fps, field chara.one: 30 fps)
        native_fps = getattr(self.ifrit_manager, 'anim_native_fps', 15)
        factor = max(1, target_fps // native_fps)
        if factor == 1:
            QMessageBox.information(self, title,
                                    f"The animations of this file already play at {native_fps} fps, "
                                    f"there is nothing to interpolate for {target_fps} fps.")
            return
        nb_frames_after = self._nb_frames_after_conversion(nb_frames_before, factor, smooth_loop)
        max_frames = self._get_max_animation_frames(self.current_anim_id)
        if nb_frames_after > max_frames:
            nb_part = get_nb_part_needed(nb_frames_before, factor, smooth_loop, max_frames)
            limit_text = (f"this animation is played by the base sequence (the idle stance), so Slow "
                          f"status can reach it: over {max_frames} frames the battle engine plays it "
                          f"wrong when the monster is slowed"
                          if max_frames == MAX_SLOW_SAFE_ANIMATION_FRAME
                          else f"the file format is limited to {max_frames} frames per animation")
            message = (f"The result would have {nb_frames_after} frames, but {limit_text}.\n\n")
            if nb_part > 1:
                message += (f"Split the animation in {nb_part} parts and chain them in the "
                            f"sequences?\n"
                            f"The animation keeps the same motion: the sequences play the parts "
                            f"one after the other, and the new parts are added at the end of the "
                            f"animation list.")
                answer = QMessageBox.question(self, title, message,
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                report, reason = self._split_animation_to_fit(self.current_anim_id, factor,
                                                              smooth_loop, max_frames)
                if report is None:
                    QMessageBox.warning(self, title,
                                        f"The animation cannot be split: {reason}.\n\n"
                                        + (f"Converting the file to 30 fps instead would keep it "
                                           f"under the limit." if target_fps == 60 and native_fps < 30 else ""))
                    return
                self._refresh_animation_count()
                self.current_frame = 0
                self.next_frame_index = 1
                self.interp_step = 0.0
                if hasattr(self, 'frame_slider'):
                    self.frame_slider.setRange(0, self.get_max_frames() - 1)
                self.update_animated_mesh()
                self.update_skeleton()
                self.animation_changed.emit()
                self.set_fps(target_fps)
                part_text = ', '.join(f"{part_id} ({nb}f)" for part_id, nb in
                                      zip([self.current_anim_id] + report['new_id_list'],
                                          report['frame_count_list']))
                QMessageBox.information(self, title,
                                        f"Animation {self.current_anim_id} ({nb_frames_before} frames) was "
                                        f"split in {report['nb_part']} parts converted to {target_fps} fps:\n"
                                        f"  {part_text}\n\n"
                                        f"{report['nb_rewritten']} place(s) in the sequences now play the "
                                        f"parts one after the other.\n"
                                        "Save the file to keep them.")
                return
            message += "It cannot be split in parts small enough either."
            QMessageBox.warning(self, title, message)
            return

        anim.create_interpolated_frames(self.ifrit_manager.enemy.bone_data.bones, factor, smooth_loop)

        # Refresh the viewer with the new frame count
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
        self.update_animated_mesh()
        self.update_skeleton()
        self.animation_changed.emit()
        self.set_fps(target_fps)

        QMessageBox.information(self, title,
                                f"Animation {self.current_anim_id} now has {len(anim.frames)} frames "
                                f"(was {nb_frames_before}).\n"
                                + detected_text +
                                ("The transition back to the first frame was smoothed.\n" if smooth_loop
                                 else "The transition back to the first frame was left as-is.\n") +
                                f"The viewer playback speed has been set to {target_fps} fps.\n"
                                "Save the file to keep the new frames.")

    def convert_all_anims_to_60fps(self):
        """Insert interpolated frames in every animation of the current file (30 or 60 fps)."""
        title = "All to 30/60 FPS"
        anim_section = self.ifrit_manager.enemy.animation_data
        if not anim_section.nb_animations or not anim_section.animations:
            QMessageBox.warning(self, title, "No animation loaded.")
            return
        if not self.ifrit_manager.enemy.bone_data:
            QMessageBox.warning(self, title, "No bone data loaded.")
            return

        answer = QMessageBox.question(
            self, title,
            f"Convert all {len(anim_section.animations)} animations of this file?\n\n"
            "The animation sequences of the file tell which animations are looping, so the\n"
            "transition back to the first frame is smoothed only on those.\n\n"
            "Note: only run this once per file — running it again would interpolate the "
            "already-interpolated frames.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return

        target_fps = self._ask_target_fps(title)
        if target_fps is None:
            return

        # A looping animation gets its last frame interpolated back to the first one, a
        # one-shot one does not. Without a sequence section, fall back on one answer for
        # the whole file.
        kind_dict = self._get_animation_kind_dict()
        default_smooth_loop = None
        if not kind_dict:
            default_smooth_loop = self._ask_smooth_loop(title)
            if default_smooth_loop is None:
                return

        # native fps x factor = target fps (battle .dat: 15 fps, field chara.one: 30 fps)
        native_fps = getattr(self.ifrit_manager, 'anim_native_fps', 15)
        factor = max(1, target_fps // native_fps)
        if factor == 1:
            QMessageBox.information(self, title,
                                    f"The animations of this file already play at {native_fps} fps, "
                                    f"there is nothing to interpolate for {target_fps} fps.")
            return
        bones = self.ifrit_manager.enemy.bone_data.bones
        converted, nb_smoothed, skipped_short, skipped_too_long = 0, 0, [], []

        def smooth_loop_of(anim_id):
            if default_smooth_loop is None:
                return is_looping(kind_dict.get(anim_id, ANIM_UNUSED))
            return default_smooth_loop

        # Animations too long to fit once converted can be cut in parts chained by the
        # sequences. Ask once, before touching anything.
        too_long_list = []
        for anim_id, anim in enumerate(anim_section.animations):
            if len(anim.frames) < 2:
                continue
            smooth_loop = smooth_loop_of(anim_id)
            if (self._nb_frames_after_conversion(len(anim.frames), factor, smooth_loop)
                    > self._get_max_animation_frames(anim_id)):
                too_long_list.append(anim_id)
        split_them = False
        if too_long_list:
            nb_slow_limited = sum(1 for anim_id in too_long_list
                                  if self._get_max_animation_frames(anim_id) == MAX_SLOW_SAFE_ANIMATION_FRAME)
            message = (f"{len(too_long_list)} animation(s) would be too long at {target_fps} fps: "
                       f"{', '.join(map(str, too_long_list))}.\n\n")
            if nb_slow_limited:
                message += (f"{nb_slow_limited} of them are played by the base sequence (the idle "
                            f"stance), so Slow status can reach them: those are limited to "
                            f"{MAX_SLOW_SAFE_ANIMATION_FRAME} frames, because over that the battle "
                            f"engine plays them wrong when the monster is slowed.\n\n")
            message += ("Split them in parts and chain them in the sequences?\n"
                        "The motion is kept: each animation is cut in parts played one after the "
                        "other, and the parts are added at the end of the animation list.\n\n"
                        "No: those animations are left untouched (not converted).")
            answer = QMessageBox.question(self, title, message,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            split_them = (answer == QMessageBox.StandardButton.Yes)

        split_done, split_refused = [], []
        if split_them:
            for anim_id in too_long_list:
                smooth_loop = smooth_loop_of(anim_id)
                nb_frames_before = len(anim_section.animations[anim_id].frames)
                report, reason = self._split_animation_to_fit(anim_id, factor, smooth_loop,
                                                              self._get_max_animation_frames(anim_id))
                if report is None:
                    split_refused.append((anim_id, reason))
                else:
                    split_done.append((anim_id, nb_frames_before, report))
                    converted += report['nb_part']
                    nb_smoothed += smooth_loop

        already_split = {anim_id for anim_id, _, report in split_done}
        already_split |= {new_id for _, _, report in split_done for new_id in report['new_id_list']}
        for anim_id, anim in enumerate(anim_section.animations):
            if anim_id in already_split:
                continue  # split + converted above
            nb_frames_before = len(anim.frames)
            if nb_frames_before < 2:
                skipped_short.append(anim_id)
                continue
            smooth_loop = smooth_loop_of(anim_id)
            nb_frames_after = self._nb_frames_after_conversion(nb_frames_before, factor, smooth_loop)
            if nb_frames_after > self._get_max_animation_frames(anim_id):
                skipped_too_long.append((anim_id, nb_frames_before, nb_frames_after))
                continue
            anim.create_interpolated_frames(bones, factor, smooth_loop)
            converted += 1
            nb_smoothed += smooth_loop

        # Refresh the viewer with the new frame count of the current animation
        self._refresh_animation_count()
        self.current_frame = 0
        self.next_frame_index = 1
        self.interp_step = 0.0
        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, self.get_max_frames() - 1)
        self.update_animated_mesh()
        self.update_skeleton()
        self.animation_changed.emit()
        self.set_fps(target_fps)

        report = [f"{converted} animation(s) converted to {target_fps} fps."]
        if kind_dict:
            source_text = (f" (read from the weapon file {self.weapon_file_used})"
                           if self.weapon_file_used else "")
            report.append(f"\n{nb_smoothed} of them are looping{source_text} (last frame interpolated "
                          f"back to the first one), the others are played once.")
        if split_done:
            report.append("\nSplit to fit the format limit (the sequences now play the parts one "
                          "after the other):")
            for anim_id, nb_before, split_report in split_done:
                part_text = ', '.join(str(part_id) for part_id in
                                      [anim_id] + split_report['new_id_list'])
                report.append(f"  animation {anim_id} ({nb_before} frames) -> {split_report['nb_part']} "
                              f"parts: {part_text} ({split_report['nb_rewritten']} place(s) rewritten)")
        if split_refused:
            report.append("\nCould not be split:")
            for anim_id, reason in split_refused:
                report.append(f"  animation {anim_id}: {reason}")
        if skipped_short:
            report.append(f"\nSkipped (fewer than 2 frames): {', '.join(map(str, skipped_short))}.")
        if skipped_too_long:
            details = ', '.join(f"{aid} ({before}->{after} frames)" for aid, before, after in skipped_too_long)
            report.append("\nSkipped (too long once converted): " + details + ".")
            if target_fps == 60 and native_fps < 30:
                report.append("Converting this file to 30 fps instead would keep them under the limit.")
        report.append(f"\nThe viewer playback speed has been set to {target_fps} fps.\n"
                      "Save the file to keep the new frames.")
        QMessageBox.information(self, title, "\n".join(report))

    # ── Frame / animation authoring ───────────────────────────────────
    def _current_animation_or_warn(self, title):
        """The Animation currently selected, or None (with a warning) if there is none."""
        anim_section = self.ifrit_manager.enemy.animation_data
        if not anim_section.nb_animations or self.current_anim_id >= len(anim_section.animations):
            QMessageBox.warning(self, title, "No animation loaded.")
            return None
        return anim_section.animations[self.current_anim_id]

    def _refresh_after_frame_count_change(self):
        """Re-range the frame slider and repose the view after a frame was added/removed."""
        max_frames = self.get_max_frames()
        self.current_frame = max(0, min(self.current_frame, max_frames - 1))
        self.next_frame_index = (self.current_frame + 1) % max_frames if max_frames else 0
        self.interp_step = 0.0
        if hasattr(self, 'frame_slider'):
            self.frame_slider.setRange(0, max(0, max_frames - 1))
        self.update_animated_mesh()
        self.update_skeleton()
        self.animation_changed.emit()

    def _add_frame_after_current(self):
        """Duplicate the current frame and insert the copy right after it."""
        title = "Add frame"
        if self._current_animation_or_warn(title) is None:
            return
        self._pause_playback()
        try:
            new_index = self.ifrit_manager.duplicate_animation_frame(
                self.current_anim_id, self.current_frame)
        except ValueError as e:
            QMessageBox.warning(self, title, f"Cannot add a frame: {e}.")
            return
        self.current_frame = new_index
        self._refresh_after_frame_count_change()

    def _delete_current_frame(self):
        """Remove the frame currently shown (an animation must keep at least one)."""
        title = "Delete frame"
        anim = self._current_animation_or_warn(title)
        if anim is None:
            return
        if len(anim.frames) <= 1:
            QMessageBox.information(self, title, "The animation must keep at least one frame.")
            return
        self._pause_playback()
        if not self.ifrit_manager.delete_animation_frame(self.current_anim_id, self.current_frame):
            return
        self._refresh_after_frame_count_change()

    def _ask_frame_range(self, title, src_anim_id, nb_frames):
        """Modal dialog with a Start and an End spin box; returns (start, end) inclusive, or None.

        End is kept >= Start (its minimum follows Start), so the pair is always a valid range;
        Start == End copies a single frame. A live label shows the resulting frame count.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        last = nb_frames - 1
        start_spin = QSpinBox()
        start_spin.setRange(0, last)
        start_spin.setValue(0)
        end_spin = QSpinBox()
        end_spin.setRange(0, last)
        end_spin.setValue(last)
        form.addRow(f"Start frame (0..{last}):", start_spin)
        form.addRow(f"End frame (0..{last}):", end_spin)
        layout.addLayout(form)

        count_label = QLabel()
        layout.addWidget(count_label)

        def refresh(_=None):
            # End can never fall below Start (same value = a single frame)
            if end_spin.value() < start_spin.value():
                end_spin.setValue(start_spin.value())
            end_spin.setMinimum(start_spin.value())
            nb = end_spin.value() - start_spin.value() + 1
            count_label.setText(f"Copies {nb} frame{'s' if nb != 1 else ''} of animation "
                                f"{src_anim_id} into a new animation.")

        start_spin.valueChanged.connect(refresh)
        end_spin.valueChanged.connect(refresh)
        refresh()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return start_spin.value(), end_spin.value()

    def _new_animation_from_range(self):
        """Create a new animation from a chosen frame range of the current one."""
        title = "New animation from frame range"
        anim = self._current_animation_or_warn(title)
        if anim is None:
            return
        src_anim_id = self.current_anim_id
        nb_frames = len(anim.frames)
        frame_range = self._ask_frame_range(title, src_anim_id, nb_frames)
        if frame_range is None:
            return
        start, end = frame_range
        self._pause_playback()
        try:
            new_id = self.ifrit_manager.create_animation_from_frame_range(src_anim_id, start, end)
        except ValueError as e:
            QMessageBox.warning(self, title, f"Cannot create the animation: {e}.")
            return
        self._refresh_animation_count()
        self._select_animation(new_id)
        QMessageBox.information(
            self, title,
            f"Animation {new_id} created with {end - start + 1} frame(s) copied from "
            f"animation {src_anim_id} (frames {start}–{end}).\n\n"
            "It is added at the end of the animation list. No sequence plays it yet — point one "
            "at it in the sequence/AI editor if you want the game to use it.\n"
            "Save the file to keep it.")

    def _duplicate_current_animation(self):
        """Copy the whole current animation into a new one at the end of the list."""
        title = "Duplicate animation"
        anim = self._current_animation_or_warn(title)
        if anim is None:
            return
        src_anim_id = self.current_anim_id
        nb_frames = len(anim.frames)
        self._pause_playback()
        try:
            new_id = self.ifrit_manager.create_animation_from_frame_range(
                src_anim_id, 0, nb_frames - 1)
        except ValueError as e:
            QMessageBox.warning(self, title, f"Cannot duplicate: {e}.")
            return
        self._refresh_animation_count()
        self._select_animation(new_id)
        QMessageBox.information(
            self, title,
            f"Animation {src_anim_id} duplicated as animation {new_id} ({nb_frames} frames), "
            "added at the end of the list.\nSave the file to keep it.")

    def _delete_current_animation(self):
        """Delete the whole animation currently shown (the file must keep at least one)."""
        title = "Delete animation"
        anim = self._current_animation_or_warn(title)
        if anim is None:
            return
        ad = self.ifrit_manager.enemy.animation_data
        if ad.nb_animations <= 1:
            QMessageBox.information(self, title, "The file must keep at least one animation.")
            return
        anim_id = self.current_anim_id
        is_last = anim_id == ad.nb_animations - 1
        warn = ("" if is_last else
                f"\n\nWARNING: this is not the last animation. Every animation after id {anim_id} "
                f"shifts down by one, so any battle sequence or AI that plays a higher id will then "
                f"play a different animation. Deleting the LAST animation avoids this.")
        if QMessageBox.question(
                self, title,
                f"Delete animation {anim_id} ({len(anim.frames)} frame"
                f"{'s' if len(anim.frames) != 1 else ''})?{warn}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._pause_playback()
        if not self.ifrit_manager.delete_animation(anim_id):
            return
        self._refresh_animation_count()
        new_count = self.ifrit_manager.enemy.animation_data.nb_animations
        # Show a still-valid neighbour: the anim that slid into this slot, or the new last one.
        # set_animation re-ranges the frame slider and reposes to frame 0 on its own.
        self._select_animation(min(anim_id, new_count - 1))

    def _select_animation(self, anim_id: int):
        """Switch the viewer to anim_id, driving the selector spin when it exists."""
        if hasattr(self, 'anim_selector'):
            if self.anim_selector.value() == anim_id:
                self.set_animation(anim_id)   # same value: no signal, switch explicitly
            else:
                self.anim_selector.setValue(anim_id)   # fires set_animation
        else:
            self.set_animation(anim_id)

    def _update_bone_editor_frame(self, frame):
        """Update bone editor when frame changes"""
        if hasattr(self, 'bone_editor'):
            self.bone_editor.set_animation_info(self.current_anim_id, frame)
            self._update_bone_editor_selection()
            self._update_frame_position_selection()

    def _update_bone_editor_animation(self):
        """Update bone editor when animation changes"""
        if hasattr(self, 'bone_editor'):
            self.bone_editor.set_animation_info(self.current_anim_id, self.current_frame)
            self._update_bone_editor_selection()
            self._update_frame_position_selection()

    def _update_bone_editor_selection(self):
        """Update the bone editor with current bone data"""
        if not hasattr(self, 'bone_editor') or not self.ifrit_manager.enemy.bone_data:
            return

        bone_id = self.bone_editor.bone_spin.value()
        if bone_id < 0 or bone_id >= len(self.ifrit_manager.enemy.bone_data.bones):
            return

        bone = self.ifrit_manager.enemy.bone_data.bones[bone_id]

        # Get animation rotation if available
        rot_x, rot_y, rot_z = 0, 0, 0
        rot_raw_x, rot_raw_y, rot_raw_z = 0, 0, 0
        scale_x, scale_y, scale_z = 1.0, 1.0, 1.0
        scale_raw_x = scale_raw_y = scale_raw_z = 1024
        mode_bit_enabled = False
        if (self.current_anim_id < len(self.ifrit_manager.enemy.animation_data.animations) and
                self.current_frame < len(self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames)):
            frame: AnimationFrame = self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames[self.current_frame]
            if bone_id < len(frame.rotation_vector_data):
                rot_x, rot_y, rot_z = frame.rotation_vector_data[bone_id][0].get_rotate_deg(), frame.rotation_vector_data[bone_id][1].get_rotate_deg(),frame.rotation_vector_data[bone_id][2].get_rotate_deg()
                rot_raw_x, rot_raw_y, rot_raw_z = frame.rotation_vector_data[bone_id][0].get_rotate_raw(), frame.rotation_vector_data[bone_id][1].get_rotate_raw(),frame.rotation_vector_data[bone_id][2].get_rotate_raw()
            mode_bit_enabled = (frame.mode_bit == 1)
            if bone_id < len(frame.rotation_vector_data_supp):
                supp = frame.rotation_vector_data_supp[bone_id]
                scale_x, scale_y, scale_z = supp.get_scale_factors()
                scale_raw_x, scale_raw_y, scale_raw_z = (supp.get_scale_raw(0), supp.get_scale_raw(1),
                                                         supp.get_scale_raw(2))

        self.bone_editor.set_bone_data(bone_id, bone.get_size(),bone.get_size_raw(),  bone.parent_id, rot_x, rot_y, rot_z, rot_raw_x, rot_raw_y, rot_raw_z)
        self.bone_editor.set_bone_scale(scale_x, scale_y, scale_z,
                                        scale_raw_x, scale_raw_y, scale_raw_z, mode_bit_enabled)

    def _update_frame_position_selection(self):
        if not hasattr(self, 'bone_editor'):
            return
        pos_x, pos_y, pos_z = 0, 0, 0
        pos_raw_x, pos_raw_y, pos_raw_z = 0, 0, 0
        if (self.current_anim_id < len(self.ifrit_manager.enemy.animation_data.animations) and
                self.current_frame < len(self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames)):
            frame: AnimationFrame = self.ifrit_manager.enemy.animation_data.animations[self.current_anim_id].frames[self.current_frame]
            pos_x, pos_y, pos_z = frame.position[0].get_pos_world(), frame.position[1].get_pos_world(), frame.position[2].get_pos_world()

            pos_raw_x, pos_raw_y, pos_raw_z = frame.position[0].get_pos_raw(), frame.position[1].get_pos_raw(), frame.position[2].get_pos_raw()

        self.bone_editor.set_frame_position(pos_x, pos_y, pos_z, pos_raw_x, pos_raw_y, pos_raw_z)


    def _on_bone_selected(self, bone_id: int):
        """Handle bone selection from editor"""
        self._update_bone_editor_selection()
        self.gl_widget.set_selected_bone(bone_id)
        self._update_gizmo()
        self.gl_widget.update()

    def _on_bone_picked_in_view(self, bone_id: int):
        """A joint was clicked in the 3D view: select that bone in the editor"""
        if not hasattr(self, 'bone_editor') or not self.bone_editor.isEnabled():
            return
        if self.bone_editor.bone_spin.value() != bone_id:
            # Triggers the whole selection chain (editor refresh + highlight)
            self.bone_editor.bone_spin.setValue(bone_id)
        else:
            self.gl_widget.set_selected_bone(bone_id)

    def _on_bone_length_dragged(self, total_delta: float):
        """Ctrl+drag in the 3D view: change the selected bone's length.
        During the drag only the displayed frame is recomputed (cheap); the
        full rebuild of every animation happens once, on release."""
        if self.animating or not hasattr(self, 'bone_editor'):
            return
        if not self.ifrit_manager.enemy.bone_data:
            return
        bone_id = self.bone_editor.bone_spin.value()
        bones = self.ifrit_manager.enemy.bone_data.bones
        if not (0 <= bone_id < len(bones)):
            return
        if self._length_drag_start_size is None:
            self._length_drag_start_size = bones[bone_id].get_size()
            # FF8 bone sizes are (nearly always) negative: a child joint sits
            # at parent + Z*size, so the visible bone points along -Z and
            # extending it means pushing the size AWAY from zero. Dragging
            # outward (along the drawn bone) must therefore follow the sign
            # of the current size, not always add.
            self._length_drag_sign = 1.0 if self._length_drag_start_size > 0 else -1.0
        # Bone size is a signed 16-bit raw value (world = raw / 2048)
        new_length = max(-15.99, min(15.99,
                                     self._length_drag_start_size + self._length_drag_sign * total_delta))

        # Show the value live in the panel without triggering the spinbox's
        # full-recompute chain
        self.bone_editor.length_spin.blockSignals(True)
        self.bone_editor.length_spin.setValue(new_length)
        self.bone_editor.length_spin.blockSignals(False)
        self.bone_editor.length_raw.setText(f"raw: {round(new_length * 2048):d}")

        self.ifrit_manager.set_bone_length_preview(bone_id, new_length,
                                                   self.current_anim_id, self.current_frame)
        self.update_skeleton()
        self.update_animated_mesh()

    def _on_bone_length_drag_finished(self):
        """Release after a length drag: apply the final value to every frame
        of every animation (the drag only refreshed the displayed one)."""
        if self._length_drag_start_size is None:
            return
        self._length_drag_start_size = None
        if not hasattr(self, 'bone_editor') or not self.ifrit_manager.enemy.bone_data:
            return
        bone_id = self.bone_editor.bone_spin.value()
        self.ifrit_manager.set_bone_length(bone_id, self.bone_editor.length_spin.value())
        self.update_skeleton()
        self.update_animated_mesh()

    def _rotation_drag_target(self):
        """(anim, frame, bone_id) currently being posed, or None."""
        if self.animating or not hasattr(self, 'bone_editor'):
            return None
        if not self.ifrit_manager.enemy.bone_data or not self.ifrit_manager.enemy.animation_data.nb_animations:
            return None
        anims = self.ifrit_manager.enemy.animation_data.animations
        if self.current_anim_id >= len(anims) or self.current_frame >= len(anims[self.current_anim_id].frames):
            return None
        bone_id = self.bone_editor.bone_spin.value()
        frame = anims[self.current_anim_id].frames[self.current_frame]
        if bone_id >= len(frame.rotation_vector_data) or len(frame.rotation_vector_data[bone_id]) < 3:
            return None
        return anims[self.current_anim_id], frame, bone_id

    def _on_bone_rotation_dragged(self, axis: int, total_deg: float):
        """A gizmo ring is being dragged: rotate the selected bone on that
        axis for the current frame.

        Only the displayed frame is recomputed here — propagation to the
        following frames and the delta storage types are done once, when the
        drag ends (none of it is visible during the drag anyway).
        """
        target = self._rotation_drag_target()
        if target is None:
            return
        _, frame, bone_id = target

        if self._rot_drag_start_deg is None:
            rot = frame.rotation_vector_data[bone_id]
            self._rot_drag_start_deg = [rot[0].get_rotate_deg(),
                                        rot[1].get_rotate_deg(),
                                        rot[2].get_rotate_deg()]
            self._rot_drag_start_raw = [int(rot[0].get_rotate_raw()),
                                        int(rot[1].get_rotate_raw()),
                                        int(rot[2].get_rotate_raw())]
        new_deg = list(self._rot_drag_start_deg)
        new_deg[axis] = ((new_deg[axis] + total_deg + 180.0) % 360.0) - 180.0

        self.ifrit_manager.set_animation_frame_bone_rotation_preview(
            self.current_anim_id, self.current_frame, bone_id,
            new_deg[0], new_deg[1], new_deg[2])
        self.update_animated_mesh()
        self.update_skeleton()
        self._update_bone_editor_selection()  # rotation spinboxes follow live

    def _on_bone_rotation_drag_finished(self):
        """Release after a ring drag: apply the drag's final pose for real —
        storage types, and the propagation to the following frames."""
        start_raw = self._rot_drag_start_raw
        self._rot_drag_start_deg = None
        self._rot_drag_start_raw = None
        target = self._rotation_drag_target()
        if start_raw is None or target is None:
            self._update_gizmo()
            return
        _, frame, bone_id = target

        rot = frame.rotation_vector_data[bone_id]
        final_deg = [rot[0].get_rotate_deg(), rot[1].get_rotate_deg(), rot[2].get_rotate_deg()]
        # Rewind to the pre-drag pose so the real setter sees the whole drag
        # as one edit (its propagation offsets the following frames by the
        # drag's total, and previews left the deltas untouched)
        for axis in range(3):
            rot[axis].rotate_raw(start_raw[axis])
        self.ifrit_manager.set_animation_frame_bone_rotation(
            self.current_anim_id, self.current_frame, bone_id,
            final_deg[0], final_deg[1], final_deg[2],
            propagate_to_next_frames=self._propagate_rotation_enabled())

        self.update_animated_mesh()
        self.update_skeleton()
        self._update_bone_editor_selection()
        self._update_gizmo()

    def _update_gizmo(self):
        """Recompute the rotation-gizmo rings for the selected bone at the
        current frame (hidden during playback and when there is no bone data)."""
        if (not hasattr(self, 'bone_editor') or not self.bone_editor.isEnabled()
                or self.animating or not self.ifrit_manager.enemy.bone_data):
            self.gl_widget.set_rotation_gizmo(None, None)
            return
        gizmo = self.ifrit_manager.get_bone_rotation_gizmo(
            self.current_anim_id, self.current_frame, self.bone_editor.bone_spin.value())
        if gizmo is None:
            self.gl_widget.set_rotation_gizmo(None, None)
        else:
            self.gl_widget.set_rotation_gizmo(gizmo[0], gizmo[1])

    def _on_bone_length_changed(self, bone_id: int, length: float):
        """Handle bone length change from editor"""
        self.ifrit_manager.set_bone_length(bone_id, length)
        self.update_skeleton()
        self.update_animated_mesh()

    def _on_bone_parent_changed(self, bone_id: int, parent_id: int):
        """Handle bone parent change from editor"""
        if parent_id == -1:
            parent_id = 0xFFFF
        self.ifrit_manager.set_bone_parent(bone_id, parent_id)
        self.update_skeleton()
        self.update_animated_mesh()

    def _pause_playback(self):
        """Stop animation playback before a structural skeleton edit."""
        if self.animating:
            self.toggle_animation()

    def _on_add_bone_shortcut(self):
        """B key: add a child bone to the selected joint."""
        if not hasattr(self, 'bone_editor') or not self.bone_editor.isEnabled():
            return
        if not self.gl_widget.show_skeleton:
            return  # only while actually working on the skeleton
        self._on_add_bone_requested(self.bone_editor.bone_spin.value())

    def _on_add_bone_requested(self, parent_id: int):
        """Create a new bone attached to the given joint and select it."""
        if not self.ifrit_manager.enemy.bone_data:
            return
        bones = self.ifrit_manager.enemy.bone_data.bones
        if not (0 <= parent_id < len(bones)):
            return
        self._pause_playback()
        new_id = self.ifrit_manager.add_bone(parent_id)
        self.bone_editor.set_bone_range(len(bones) - 1)
        self.bone_editor.bone_spin.setValue(new_id)  # select it (refresh chain)
        self.update_skeleton()
        self.update_animated_mesh()

    def _on_reset_skeleton_requested(self):
        """Start a skeleton from scratch: keep only the root joint."""
        if not self.ifrit_manager.enemy.bone_data:
            return
        nb_bones = len(self.ifrit_manager.enemy.bone_data.bones)
        answer = QMessageBox.question(
            self, "New skeleton",
            f"Delete all {nb_bones - 1} bones except the root joint?\n\n"
            "The whole mesh will be attached to the root (rigid), and the\n"
            "animations will keep only their positions and root rotation.\n"
            "Use 'Add child bone' to build the new skeleton.\n\n"
            "This cannot be undone (reload the file to go back).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pause_playback()
        self.ifrit_manager.reset_skeleton()
        self.bone_editor.set_bone_range(0)
        self.bone_editor.bone_spin.setValue(0)
        self._update_bone_editor_selection()
        self.update_skeleton()
        self.update_animated_mesh()

    def on_frame_position_changed(self, anim_id: int, frame_id: int, pos_x: float, pos_y: float, pos_z: float):
        """
        Handle frame position changes from the bone editor.
        """
        # Get the animation section
        anim_section: AnimationSection = self.ifrit_manager.enemy.animation_data

        # Validate animation exists
        if anim_id >= len(anim_section.animations):
            print(f"Animation {anim_id} not found")
            return

        anim: Animation = anim_section.animations[anim_id]

        # Validate frame exists
        if frame_id >= len(anim.frames):
            print(f"Frame {frame_id} not found in animation {anim_id}")
            return

        frame: AnimationFrame = anim.frames[frame_id]

        # Update the frame's position (global position of the entire skeleton)
        # Make sure position list has at least 3 elements
        if len(frame.position) < 3:
            # This shouldn't happen if properly initialized
            print(f"Frame {frame_id} doesn't have position data")
            return

        # Update position values
        # Using move_world or setting directly depending on your PositionType implementation
        frame.position[0].set_pos_world(pos_x)
        frame.position[1].set_pos_world(pos_y)
        frame.position[2].set_pos_world(pos_z)

        # Positions are delta-encoded on disk with per-value bit widths: refresh
        # them or the save truncates the new delta (see write_to_writer)
        anim._recompute_frame_storage_types()

        self._update_frame_position_selection()

        # Update the 3D view to show the new position
        if anim_id == self.current_anim_id and frame_id == self.current_frame:
            self.gl_widget.set_model_translation(pos_x, pos_y, pos_z)
            self.gl_widget.update()

    def _propagate_rotation_enabled(self) -> bool:
        """The 'Apply to all following frames' checkbox of the rotation tab"""
        return (hasattr(self, 'bone_editor')
                and self.bone_editor.propagate_rotation_cb.isChecked())

    def _on_animation_rotation_changed(self, anim_id: int, frame_id: int,
                                       bone_id: int, rx: float, ry: float, rz: float):
        """Handle animation rotation change from editor"""
        self.ifrit_manager.set_animation_frame_bone_rotation(
            anim_id, frame_id, bone_id, rx, ry, rz,
            propagate_to_next_frames=self._propagate_rotation_enabled())
        self.update_animated_mesh()

    def _on_animation_scale_changed(self, anim_id: int, frame_id: int,
                                    bone_id: int, sx: float, sy: float, sz: float):
        """Handle bone scale (squash-and-stretch) change from editor"""
        self.ifrit_manager.set_animation_frame_bone_scale(anim_id, frame_id, bone_id, sx, sy, sz)
        self.update_animated_mesh()
        self.update_skeleton()

    def _on_frame_scale_mode_changed(self, anim_id: int, frame_id: int, enabled: bool):
        """Handle the frame's scale mode-bit toggle from editor"""
        self.ifrit_manager.set_animation_frame_scale_mode(anim_id, frame_id, enabled)
        self.update_animated_mesh()
        self.update_skeleton()
        self.update_skeleton()