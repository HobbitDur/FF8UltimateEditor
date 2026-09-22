import os

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon, QColor, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTabWidget,
                             QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QSplitter,
                             QHeaderView, QAbstractItemView, QGroupBox, QFormLayout, QSpinBox,
                             QPushButton, QMessageBox, QScrollArea, QCheckBox, QLineEdit)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Laguna.lagunamanager import LagunaManager, CINEMATIC_GFS
from Laguna.timelinewidget import TimelineCanvas, MotionCanvas, CATEGORY_COLORS, TICKS_PER_SECOND
from Laguna.meshpreview import MeshPreview
from FF8GameData.magcine.magcontainer import MagContainer, PRIM_NAME, HEADER_FIELDS

_KIND_COLORS = {"code": None, "spawn": QColor(15, 157, 88), "particle": QColor(244, 160, 0),
                "data": QColor(120, 120, 120)}


class _NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class LagunaWidget(QWidget):
    """GF cinematic script editor: the byte-code choreography of the seven summons that share
    Ifrit's engine (Ifrit, Leviathan, Bahamut, Cerberus, Alexander, Brothers, Eden), stored in
    their MAGxxx_B.00 mag file.

    - Script: every script reachable from the root program (bone programs, subroutines, jump
      targets) disassembled with named opcodes, plus the unreached bytes (particle scripts, dead
      code); an instruction's modifier bits and operands are edited in place.
    - Timeline: the scripts replayed tick by tick without the game (who spawns when, camera cuts,
      sounds, draw setup, particles) and each bone's motion curves.
    - Resources: the meshes, embedded creature model and sprite lists of the .00 and of the
      companion .01 (read-only), with an untextured 3D preview of the meshes.
    - Opcodes: the decoded instruction set.

    Named after Laguna Loire, who made his film debut as the hero of a cinematic."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.setWindowTitle("Laguna")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.managers = {}          # gf -> LagunaManager (one per loaded file)
        self.companions = {}        # gf -> MagContainer of its .01 (read-only)
        self.current_gf = ""
        self._labels = {}
        self._simulation = None
        self._row_of_offset = {}
        self._editing_offset = -1

        # One binding per GF file: they have fixed names, so each is shared like any FF8 file.
        self.bindings = {}
        for gf, (_effect, file_name) in CINEMATIC_GFS.items():
            binding = FileBinding(file_name, file_registry, save_callback=lambda g=gf: self.save_file(g))
            binding.file_opened.connect(lambda path, g=gf: self.load_file(path, g))
            binding.file_closed.connect(lambda _path, g=gf: self._close_gf(g))
            self.bindings[gf] = binding
        # The .01 carries most meshes and textures: shown in Resources, never written.
        self.companion_bindings = {}
        for gf, (_effect, file_name) in CINEMATIC_GFS.items():
            binding = FileBinding(file_name[:-2] + "01", file_registry, read_only=True)
            binding.file_opened.connect(lambda path, g=gf: self._load_companion(path, g))
            binding.file_closed.connect(lambda _path, g=gf: self._close_companion(g))
            self.companion_bindings[gf] = binding

        # ---- top bar
        self.gf_selector = QComboBox()
        self.gf_selector.setToolTip("Which loaded GF mag file is shown (import them with the toolbar)")
        self.gf_selector.activated.connect(lambda _i: self._show_gf(self.gf_selector.currentData()))
        self.file_label = QLabel("No file loaded: import MAG200_B.00 (Ifrit), MAG005_B.00 (Leviathan), "
                                 "MAG201-205_B.00 (Bahamut, Cerberus, Alexander, Brothers, Eden)")
        top = QHBoxLayout()
        top.addWidget(QLabel("GF:"))
        top.addWidget(self.gf_selector)
        top.addWidget(self.file_label, 1)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_script_tab(), "Script")
        self.tabs.addTab(self._build_timeline_tab(), "Timeline")
        self.tabs.addTab(self._build_resource_tab(), "Resources")
        self.tabs.addTab(self._build_opcode_tab(), "Opcodes")

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        self.setLayout(layout)
        self._set_enabled(False)

        for binding in self.file_bindings():
            binding.load_opened_file()  # Another tool may have opened these files already

    def file_bindings(self):
        return list(self.bindings.values()) + list(self.companion_bindings.values())

    @property
    def manager(self):
        return self.managers.get(self.current_gf)

    # ------------------------------------------------------------------ building
    def _build_script_tab(self):
        self.block_tree = QTreeWidget()
        self.block_tree.setHeaderLabels(["Script", "Offset", "Instr."])
        self.block_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.block_tree.itemClicked.connect(self._on_block_clicked)
        self.block_filter = QLineEdit()
        self.block_filter.setPlaceholderText("Filter (label or offset)...")
        self.block_filter.textChanged.connect(self._filter_blocks)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.block_filter)
        left_layout.addWidget(self.block_tree)

        self.listing = QTableWidget(0, 5)
        self.listing.setHorizontalHeaderLabels(["Label", "Offset", "Bytes", "Instruction", "Meaning"])
        self.listing.verticalHeader().setVisible(False)
        self.listing.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listing.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.listing.horizontalHeader()
        # Interactive, sized once per fill: ResizeToContents re-measures on every setItem (slow)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.listing.setFont(mono)
        self.listing.itemSelectionChanged.connect(self._on_row_selected)
        self.listing.cellDoubleClicked.connect(self._on_row_double_clicked)

        # instruction editor
        self.editor_group = QGroupBox("Instruction")
        self.editor_title = QLabel("")
        self.editor_title.setWordWrap(True)
        self.editor_doc = QLabel("")
        self.editor_doc.setWordWrap(True)
        self.editor_doc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.modifier_spin = _NoWheelSpinBox()
        self.modifier_spin.setRange(0, 127)
        self.modifier_spin.setDisplayIntegerBase(16)
        self.modifier_spin.setPrefix("0x")
        self.modifier_spin.setToolTip("High 7 bits of the opcode word (op >> 9): component mask, wait, sub-op...")
        self.operand_form = QFormLayout()
        self.operand_spins = []
        self.apply_button = QPushButton("Apply (in place)")
        self.apply_button.clicked.connect(self._apply_instruction)
        self.follow_button = QPushButton("Go to target")
        self.follow_button.clicked.connect(self._follow_reference)
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.follow_button)
        buttons.addStretch(1)
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.editor_title)
        form = QFormLayout()
        form.addRow("Modifier (op >> 9):", self.modifier_spin)
        editor_layout.addLayout(form)
        editor_layout.addLayout(self.operand_form)
        editor_layout.addLayout(buttons)
        editor_layout.addWidget(self.editor_doc)
        editor_layout.addStretch(1)
        self.editor_group.setLayout(editor_layout)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(self.editor_group)
        editor_scroll.setMinimumWidth(320)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.listing)
        splitter.addWidget(editor_scroll)
        splitter.setSizes([260, 800, 340])
        self.summary_label = QLabel("")
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(self.summary_label)
        tab_layout.addWidget(splitter, 1)
        self.script_tab = tab
        return tab

    def _build_timeline_tab(self):
        self.seed_spin = _NoWheelSpinBox()
        self.seed_spin.setRange(0, 9999)
        self.seed_spin.setToolTip("Seed of the random opcodes (random branch/wait/offsets): "
                                  "another seed shows another possible run")
        self.target_spin = _NoWheelSpinBox()
        self.target_spin.setRange(1, 8)
        self.target_spin.setToolTip("Number of targets of the summon (per-target spawns and target loops)")
        run_button = QPushButton("Run simulation")
        run_button.clicked.connect(self._run_simulation)
        self.sim_label = QLabel("")
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Seed:"))
        controls.addWidget(self.seed_spin)
        controls.addWidget(QLabel("Targets:"))
        controls.addWidget(self.target_spin)
        controls.addWidget(run_button)
        controls.addWidget(self.sim_label, 1)
        legend = QHBoxLayout()
        self.category_checks = {}
        for category, color in CATEGORY_COLORS.items():
            check = QCheckBox(category)
            check.setChecked(category not in ("flag", "file"))
            check.setStyleSheet(f"QCheckBox {{ color: {color.name()}; font-weight: bold; }}")
            check.toggled.connect(self._update_hidden_categories)
            self.category_checks[category] = check
            legend.addWidget(check)
        legend.addStretch(1)
        legend.addWidget(QLabel("Ctrl+wheel: zoom - click a marker: show it in Script"))

        self.timeline = TimelineCanvas()
        self.timeline.event_clicked.connect(self._goto_offset_from_timeline)
        self.timeline.bone_clicked.connect(self._on_bone_clicked)
        scroll = QScrollArea()
        scroll.setWidget(self.timeline)
        scroll.setWidgetResizable(False)
        self.motion = MotionCanvas()
        motion_group = QGroupBox("Selected bone motion (simulated outAngle / outPos)")
        motion_layout = QVBoxLayout(motion_group)
        self.motion_label = QLabel("")
        motion_layout.addWidget(self.motion_label)
        motion_layout.addWidget(self.motion)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(scroll)
        splitter.addWidget(motion_group)
        splitter.setSizes([600, 220])
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addLayout(controls)
        layout.addLayout(legend)
        layout.addWidget(splitter, 1)
        self._update_hidden_categories()
        return tab

    def _build_opcode_tab(self):
        from FF8GameData.magcine.cinescript import CineOpcodeTable
        table = CineOpcodeTable.default()
        opcodes = [opcode for _code, opcode in sorted(table.opcodes.items()) if opcode.valid]
        widget = QTableWidget(len(opcodes), 6)
        widget.setHorizontalHeaderLabels(["Op", "Name", "Length (bytes)", "Operands", "GFs", "Meaning"])
        widget.verticalHeader().setVisible(False)
        widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, opcode in enumerate(opcodes):
            operands = ", ".join(f"{o['name']}:{o['type']}" for o in opcode.operands)
            values = [f"0x{opcode.code:03X}", opcode.name, opcode.length_expr, operands,
                      ", ".join(opcode.gfs) if opcode.gfs else "all",
                      opcode.semantics + (f"\nModifier: {opcode.high_bits}" if opcode.high_bits
                                          not in ("", "unused", "ignored") else "")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                widget.setItem(row, column, item)
        header = widget.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setMaximumSectionSize(420)
        return widget

    def _build_resource_tab(self):
        self.resource_tree = QTreeWidget()
        self.resource_tree.setHeaderLabels(["Resource", "Offset", "Details"])
        self.resource_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.resource_tree.itemClicked.connect(self._on_resource_clicked)
        self.mesh_preview = MeshPreview()
        self.wireframe_check = QCheckBox("Wireframe")
        self.wireframe_check.toggled.connect(self._toggle_wireframe)
        self.resource_info = QLabel("The .01 companion file (most meshes and textures) is read-only here: "
                                    "import it with the toolbar next to the .00.")
        self.resource_info.setWordWrap(True)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.wireframe_check)
        right_layout.addWidget(self.mesh_preview, 1)
        right_layout.addWidget(self.resource_info)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.resource_tree)
        splitter.addWidget(right)
        splitter.setSizes([520, 700])
        return splitter

    def _toggle_wireframe(self, checked):
        self.mesh_preview.wireframe = checked
        self.mesh_preview.update()

    def _fill_resources(self):
        self.resource_tree.clear()
        self.mesh_preview.set_mesh(None)
        manager = self.manager
        if manager is None:
            return
        file_name = CINEMATIC_GFS[self.current_gf][1]
        files = [(file_name, MagContainer(bytes(manager.data)))]
        if self.current_gf in self.companions:
            files.append((file_name[:-2] + "01", self.companions[self.current_gf]))
        for name, container in files:
            root = QTreeWidgetItem([name, "", f"{len(container.data)} bytes"])
            self.resource_tree.addTopLevelItem(root)
            header = QTreeWidgetItem(["Header", "00000", ""])
            root.addChild(header)
            for offset, label in HEADER_FIELDS:
                value = container.header[offset // 4]
                header.addChild(QTreeWidgetItem([label, f"+{offset:02X}", f"0x{value:X}" if value else "-"]))
            for obj in container.objects:
                item = QTreeWidgetItem([f"object {obj.index} ({obj.kind})", f"{obj.offset:05X}",
                                        self._object_details(obj)])
                item.setToolTip(2, item.text(2))
                item.setData(0, Qt.ItemDataRole.UserRole, obj)
                root.addChild(item)
            textures, cluts = container.texture_entries(), container.clut_entries()
            if textures or cluts:
                root.addChild(QTreeWidgetItem([f"{len(textures)} textures, {len(cluts)} CLUTs", "",
                                               "texture ids " + ", ".join(str(i) for i, _o in textures)]))
            root.setExpanded(True)
        self.resource_tree.resizeColumnToContents(1)

    @staticmethod
    def _object_details(obj):
        if obj.error:
            return "PARSE ERROR: " + obj.error
        if obj.kind == "mesh":
            mesh = obj.mesh
            if mesh.is_morph_target:
                return f"morph target, {len(mesh.vertices)} vertices"
            prims = ", ".join(f"{count} {PRIM_NAME.get(t, t)}" for t, count in sorted(mesh.prim_counts.items()))
            return f"{len(mesh.vertices)} vertices, {prims}"
        if obj.kind == "model":
            return (f"embedded battle model: {obj.info['bones']} bones, "
                    f"{obj.info['geometry objects']} geometry objects, {obj.info['animations']} animations")
        return f"sprite frame list, {len(obj.info.get('frames', []))} entries"

    def _on_resource_clicked(self, item, _column):
        obj = item.data(0, Qt.ItemDataRole.UserRole)
        if obj is None:
            return
        self.mesh_preview.set_mesh(obj.mesh if obj.kind == "mesh" else None)
        if obj.kind == "model":
            self.resource_info.setText("The creature: a standard battle model (skeleton = .dat section 1, geometry = "
                                       "section 2, animation = section 3), placed and moved by its cinematic bone "
                                       "(draw handler 3).")
        elif obj.kind == "sprite":
            codes = {0: "next", 1: "end", 2: "loop"}
            self.resource_info.setText("Sprite frames (duration in ticks / then): " + ", ".join(
                f"{f['duration']}/{codes.get(f['code'], f['code'])}" for f in obj.info.get("frames", [])[:24]))
        else:
            self.resource_info.setText("Untextured preview (the texture VRAM rectangles are in FF8_EN.exe). "
                                       "Drag to rotate, wheel to zoom.")

    def _load_companion(self, path, gf):
        try:
            with open(path, "rb") as f:
                self.companions[gf] = MagContainer(f.read())
        except OSError as error:
            QMessageBox.critical(self, "Laguna", f"Cannot read {path}:\n{error}")
            return
        if gf == self.current_gf:
            self._fill_resources()

    def _close_companion(self, gf):
        self.companions.pop(gf, None)
        if gf == self.current_gf:
            self._fill_resources()

    # ------------------------------------------------------------------ files
    def load_file(self, path, gf):
        manager = LagunaManager()
        try:
            manager.load_file(path, gf)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Laguna", f"Cannot load {path}:\n{error}")
            return
        self.managers[gf] = manager
        self._refresh_gf_selector()
        self._show_gf(gf)

    def save_file(self, gf):
        manager = self.managers.get(gf)
        if manager is None:
            return
        try:
            manager.save_file()
        except OSError as error:
            QMessageBox.critical(self, "Laguna", f"Cannot save {manager.file_path}:\n{error}")

    def _close_gf(self, gf):
        self.managers.pop(gf, None)
        self._refresh_gf_selector()
        if self.current_gf == gf:
            self.current_gf = ""
            self._show_gf(next(iter(self.managers), ""))

    def _refresh_gf_selector(self):
        with QSignalBlocker(self.gf_selector):
            self.gf_selector.clear()
            for gf in CINEMATIC_GFS:
                if gf in self.managers:
                    effect, file_name = CINEMATIC_GFS[gf]
                    self.gf_selector.addItem(f"{gf} ({file_name}, effect {effect})", gf)
            index = self.gf_selector.findData(self.current_gf)
            if index >= 0:
                self.gf_selector.setCurrentIndex(index)

    def _set_enabled(self, enabled):
        self.tabs.setEnabled(enabled)

    def _show_gf(self, gf):
        self.current_gf = gf or ""
        manager = self.manager
        self._simulation = None
        self.timeline.set_simulation(None)
        self.motion.set_bone(None, 1)
        self.sim_label.setText("")
        if manager is None:
            self._set_enabled(False)
            self.block_tree.clear()
            self.listing.setRowCount(0)
            return
        index = self.gf_selector.findData(gf)
        if index >= 0:
            with QSignalBlocker(self.gf_selector):
                self.gf_selector.setCurrentIndex(index)
        self._set_enabled(True)
        self.file_label.setText(manager.file_path)
        self._refresh_program()
        self._run_simulation()
        self._fill_resources()

    # ------------------------------------------------------------------ script view
    def _refresh_program(self, keep_offset=None):
        manager = self.manager
        self._labels = manager.labels()
        program = manager.program
        unreached = manager.unreached_ranges()
        unreached_bytes = sum(end - start for start, end in unreached)
        self.summary_label.setText(
            f"Root program at 0x{manager.root:X}, script region 0x{manager.root:X}-0x{manager.script_end:X}: "
            f"{len(program.instructions)} reachable instructions, {len(program.particle_scripts)} particle "
            f"scripts, {unreached_bytes} bytes not reached"
            + (f" - {len(program.errors)} DECODE ERRORS" if program.errors else ""))
        self._fill_block_tree(unreached)
        self._fill_listing()
        if keep_offset is not None:
            self._select_offset(keep_offset)

    def _fill_block_tree(self, unreached):
        self.block_tree.clear()
        program = self.manager.program
        groups = {}
        for title in ("Root program", "Bone programs (spawned)", "Subroutines (called)",
                      "Jump targets", "Particle scripts", "Not reached (particle scripts, data, dead code)"):
            groups[title] = QTreeWidgetItem([title])
            self.block_tree.addTopLevelItem(groups[title])
        instruction_count = {block.start: len(block.instructions) for block in program.blocks()}
        for offset in sorted(set(self._labels) | program.particle_scripts):
            label = self._labels.get(offset, f"{offset:04X}")
            if label.startswith("root"):
                group = "Root program"
            elif label.startswith("bone"):
                group = "Bone programs (spawned)"
            elif label.startswith("sub"):
                group = "Subroutines (called)"
            elif label.startswith("pfx"):
                group = "Particle scripts"
            elif label.startswith("loc"):
                group = "Jump targets"
            else:
                continue
            item = QTreeWidgetItem([label, f"{offset:05X}", str(instruction_count.get(offset, ""))])
            item.setData(0, Qt.ItemDataRole.UserRole, offset)
            groups[group].addChild(item)
        for start, end in unreached:
            item = QTreeWidgetItem([f"{end - start} bytes", f"{start:05X}", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, start)
            groups["Not reached (particle scripts, data, dead code)"].addChild(item)
        for title, item in groups.items():
            item.setText(2, str(item.childCount()))
        groups["Root program"].setExpanded(True)
        groups["Bone programs (spawned)"].setExpanded(True)

    def _filter_blocks(self, text):
        text = text.strip().lower()
        for index in range(self.block_tree.topLevelItemCount()):
            group = self.block_tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                child.setHidden(bool(text) and text not in child.text(0).lower() and text not in child.text(1).lower())

    def _fill_listing(self):
        """The whole script region in address order: reachable code, then unreached ranges shown
        as a tentative straight disassembly (greyed)."""
        manager = self.manager
        rows = []
        for instruction in manager.program.sorted_instructions():
            rows.append((instruction, True))
        for start, end in manager.unreached_ranges():
            decoded, stop = manager.linear_disassembly(start, end)
            rows.extend((instruction, False) for instruction in decoded)
            if stop < end:
                rows.append((("raw", stop, end), False))
        rows.sort(key=lambda row: row[0][1] if isinstance(row[0], tuple) else row[0].offset)

        self._row_of_offset = {}
        self.listing.setUpdatesEnabled(False)
        self.listing.setRowCount(len(rows))
        grey = QColor(140, 140, 140)
        for row, (instruction, reached) in enumerate(rows):
            if isinstance(instruction, tuple):
                _raw, start, end = instruction
                chunk = bytes(manager.data[start:min(end, start + 16)])
                values = [self._labels.get(start, ""), f"{start:05X}", chunk.hex(" ") + (" ..." if end - start > 16 else ""),
                          f"(raw {end - start} bytes)", "Not decodable as instructions (particle script / data)"]
                offset = start
            else:
                offset = instruction.offset
                raw = instruction.raw()
                values = [self._labels.get(offset, ""), f"{offset:05X}",
                          raw[:12].hex(" ") + (" ..." if len(raw) > 12 else ""),
                          manager.format(instruction, self._labels),
                          (instruction.error + " " if instruction.error else "") + manager.describe(instruction)]
            self._row_of_offset.setdefault(offset, row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 4:
                    item.setToolTip(value)
                if not reached:
                    item.setForeground(grey)
                elif column == 3 and not isinstance(instruction, tuple):
                    kinds = {kind for kind, _t, _w in instruction.refs}
                    for kind in ("spawn", "particle", "data"):
                        if kind in kinds and _KIND_COLORS[kind] is not None:
                            item.setForeground(_KIND_COLORS[kind])
                            break
                item.setData(Qt.ItemDataRole.UserRole, offset)
                self.listing.setItem(row, column, item)
        for column in range(4):
            self.listing.resizeColumnToContents(column)
        self.listing.setColumnWidth(3, min(self.listing.columnWidth(3), 420))
        self.listing.setUpdatesEnabled(True)

    def _on_block_clicked(self, item, _column):
        offset = item.data(0, Qt.ItemDataRole.UserRole)
        if offset is not None:
            self._select_offset(offset)

    def _select_offset(self, offset):
        row = self._row_of_offset.get(offset)
        if row is None:  # inside an instruction or a raw range: nearest row before it
            candidates = [o for o in self._row_of_offset if o <= offset]
            if not candidates:
                return
            row = self._row_of_offset[max(candidates)]
        self.listing.selectRow(row)
        self.listing.scrollToItem(self.listing.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    def _selected_offset(self):
        items = self.listing.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _on_row_selected(self):
        offset = self._selected_offset()
        manager = self.manager
        if offset is None or manager is None:
            return
        self._editing_offset = offset
        instruction = manager.instruction_at(offset)
        opcode = instruction.opcode
        for spin in self.operand_spins:
            self.operand_form.removeRow(spin)
        self.operand_spins = []
        xrefs = manager.program.xrefs.get(offset, [])
        xref_text = ("Referenced from: " + ", ".join(f"{source:05X} ({kind})" for source, kind in xrefs[:12])
                     + (" ..." if len(xrefs) > 12 else "")) if xrefs else ""
        if opcode is None or instruction.error and not instruction.words:
            self.editor_title.setText(f"{offset:05X}: {instruction.error or 'not an instruction'}")
            self.editor_doc.setText(xref_text)
            self.apply_button.setEnabled(False)
            self.follow_button.setEnabled(False)
            self.modifier_spin.setEnabled(False)
            return
        self.editor_title.setText(f"<b>{offset:05X}: {opcode.name}</b> (opcode 0x{opcode.code:03X}, "
                                  f"{instruction.length} bytes)")
        with QSignalBlocker(self.modifier_spin):
            self.modifier_spin.setValue(instruction.modifier)
        self.modifier_spin.setEnabled(True)
        refs = {word: (kind, target) for kind, target, word in instruction.refs}
        for index, word in enumerate(instruction.words):
            spin = _NoWheelSpinBox()
            spin.setRange(-32768, 32767)
            with QSignalBlocker(spin):
                spin.setValue(word)
            name = opcode.operands[index]["name"] if index < len(opcode.operands) else f"word {index}"
            if index in refs:
                kind, target = refs[index]
                name += f" -> {self._labels.get(target, f'{target:05X}')} ({kind}, relative)"
            spin.setToolTip(name)
            self.operand_form.addRow(name[:48] + ":", spin)
            self.operand_spins.append(spin)
        doc = [manager.describe(instruction)]
        if opcode.high_bits and opcode.high_bits not in ("unused", "ignored"):
            doc.append(f"<i>Modifier bits:</i> {opcode.high_bits}")
        if opcode.notes:
            doc.append(f"<i>Notes:</i> {opcode.notes}")
        doc.append(f"<i>Length rule:</i> {opcode.length_expr} - confidence {opcode.confidence}")
        if xref_text:
            doc.append(xref_text)
        self.editor_doc.setText("<br><br>".join(doc))
        self.apply_button.setEnabled(True)
        self.follow_button.setEnabled(bool(instruction.refs))

    def _apply_instruction(self):
        manager = self.manager
        if manager is None or self._editing_offset < 0:
            return
        old = manager.instruction_at(self._editing_offset)
        op = (self.modifier_spin.value() << 9) | old.code
        words = [spin.value() for spin in self.operand_spins]
        try:
            manager.replace_instruction(self._editing_offset, op, words)
        except ValueError as error:
            QMessageBox.warning(self, "Laguna", str(error))
            return
        self._mark_dirty()
        self._refresh_program(keep_offset=self._editing_offset)
        self._simulation = None
        self.sim_label.setText("Script changed: run the simulation again")

    def _follow_reference(self):
        instruction = self.manager.instruction_at(self._editing_offset) if self.manager else None
        if instruction and instruction.refs:
            self._select_offset(instruction.refs[0][1])

    def _on_row_double_clicked(self, row, _column):
        item = self.listing.item(row, 0)
        if item is None:
            return
        instruction = self.manager.instruction_at(item.data(Qt.ItemDataRole.UserRole))
        if instruction.refs:
            self._select_offset(instruction.refs[0][1])

    # ------------------------------------------------------------------ timeline
    def _run_simulation(self):
        manager = self.manager
        if manager is None:
            return
        self._simulation = manager.simulate(seed=self.seed_spin.value(), target_count=self.target_spin.value())
        sim = self._simulation
        end = sim.finished_tick if sim.finished_tick >= 0 else sim.tick
        state = "ends (op 0x01)" if sim.finished_tick >= 0 else "did not end (stopped)"
        self.sim_label.setText(f"{len(sim.bones)} bones, sequence {state} at tick {end} "
                               f"= {end / TICKS_PER_SECOND:.1f} s at 15 ticks/s"
                               + (f" - {len(sim.warnings)} warnings (first: {sim.warnings[0][2]} at "
                                  f"{sim.warnings[0][1]:05X})" if sim.warnings else ""))
        self.timeline.set_simulation(sim, self._labels)
        self.motion.set_bone(None, 1)

    def _update_hidden_categories(self):
        self.timeline.hidden_categories = {c for c, check in self.category_checks.items() if not check.isChecked()}
        self.timeline.update()

    def _on_bone_clicked(self, index):
        if self._simulation is None:
            return
        bone = self._simulation.bones[index]
        self.motion.set_bone(bone, self._simulation.tick)
        self.motion_label.setText(f"{self.timeline.bone_label(bone)} - spawn tick {bone.spawn_tick}, "
                                  f"{len(bone.track)} motion samples")

    def _goto_offset_from_timeline(self, offset):
        if offset is None or offset < 0:
            return
        self.tabs.setCurrentWidget(self.script_tab)
        self._select_offset(offset)

    # ------------------------------------------------------------------ undo / dirty
    def _mark_dirty(self):
        state = getattr(self, "dirty_state", None)
        if state is not None:
            state.mark()

    def undo(self):
        if self.manager and self.manager.undo():
            self._mark_dirty()
            self._refresh_program(keep_offset=self._editing_offset)

    def redo(self):
        if self.manager and self.manager.redo():
            self._mark_dirty()
            self._refresh_program(keep_offset=self._editing_offset)
