"""The user-friendly view of a battle camera script: one row per command, every parameter picked from
the values it can take (camera_script.json), like IfritAI's command rows.

A row edits a FF8GameData.dat.camerascriptsteps.ScriptStep: a command (grouped Camera / Flow / Value
/ Jump), then its parameters - the animation as set + slot (with the Keyframes tab's notes), a
battle value from its named list, an operation and its operand, a jump's test and the command it goes
to. Byte sizes and jump offsets are derived on write (script_bytes), so they never need typing.

Every edit emits script_edited(bytes): the camera track editor turns it into code and keeps it until
Apply, like an edit in the Code view.

A spell script has up to ~150 commands: the lists every row offers are models shared by all rows,
and the rows are only built while the view is on screen, a few at a time."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton,
                             QSizePolicy, QScrollArea)

from FF8GameData.dat.camerascript import animation_index_parts
from FF8GameData.dat.camerascriptsteps import (CameraScriptInfo, read_steps, script_bytes, jump_sources, new_step,
                                               reachable_steps)

END_OF_SCRIPT = -1
RAW_OFFSET = -2
ROWS_PER_PASS = 30   # rows built before the window gets to repaint (a row takes ~5 ms)


def _model(items, parent=None):
    """A combo model of (text, data, tooltip) items."""
    model = QStandardItemModel(parent)
    for text, data, tip in items:
        item = QStandardItem(text)
        item.setData(data, Qt.ItemDataRole.UserRole)
        if tip:
            item.setData(tip, Qt.ItemDataRole.ToolTipRole)
        model.appendRow(item)
    return model


def _combo(model, current, tooltip="", length=0):
    """A combo on `model` set on the item whose data is `current`; `length`: width in characters
    (0: its longest item)."""
    combo = QComboBox()
    _set_length(combo, length)   # before the model: a capped width does not measure every item
    combo.setModel(model)
    combo.setCurrentIndex(max(combo.findData(current), 0))
    combo.setToolTip(tooltip)
    return combo


def _set_length(combo, length):
    if length:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(length)
    else:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)


class ScriptStepRow(QWidget):
    edited = pyqtSignal()                       # the step changed in place
    action_requested = pyqtSignal(object, str)  # self, "insert" / "remove" / "up" / "down"

    def __init__(self, editor, step):
        super().__init__()
        self.editor = editor
        self.info = editor.info
        self.step = step
        self._target_combo = None
        self.line_label = QLabel()
        self.line_label.setFixedWidth(28)
        self.line_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.source_label = QLabel()   # where the jumps to this command come from
        self.source_label.setFixedWidth(52)
        self.command_combo = _combo(editor.command_model, step.command_id, length=20)
        self.command_combo.currentIndexChanged.connect(self._command_changed)
        self.param_layout = QHBoxLayout()
        self.param_layout.setSpacing(4)
        self.description_label = QLabel()   # the command as a sentence, under its controls
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        rows = QVBoxLayout(self)
        rows.setContentsMargins(2, 1, 2, 3)
        rows.setSpacing(0)
        layout = QHBoxLayout()
        rows.addLayout(layout)
        description_row = QHBoxLayout()
        description_row.addSpacing(28 + 4 * 22 + 52 + 6 * 6)   # under the command
        description_row.addWidget(self.description_label, 1)
        rows.addLayout(description_row)
        layout.addWidget(self.line_label)
        for text, action, tip in (("↑", "up", "Move this command up"), ("↓", "down", "Move this command down"),
                                  ("+", "insert", "Insert a command after this one"),
                                  ("−", "remove", "Remove this command")):
            button = QPushButton(text)
            button.setFixedSize(22, 22)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, a=action: self.action_requested.emit(self, a))
            layout.addWidget(button)
        layout.addWidget(self.source_label)
        layout.addWidget(self.command_combo)
        layout.addLayout(self.param_layout)
        layout.addStretch(1)
        self._build_params()

    # ------------------------------------------------------------------ parameters
    def _build_params(self):
        while self.param_layout.count():
            widget = self.param_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._target_combo = None
        step, info = self.step, self.info
        command = info.command_by_id.get(step.command_id)
        self.command_combo.setToolTip(command["help"] if command else
                                      "An op code the camera VM does not know: the engine stops here")
        if step.command_id == "raw":
            self._add(QLabel(f"bytes {bytes(step.raw).hex(' ').upper()}"))
        elif step.command_id == "play":
            self._add_animation()
        elif step.command_id == "play_var":
            self._add(self._variable_combo("read_variable"))
        elif step.command_id == "store":
            self._add(self._variable_combo("write_variable"))
        elif step.command_id in ("wobble", "nop"):
            self._add(self._spin(command["params"][0]))
        elif step.command_id == "value":
            self._add_value()
        elif step.command_id == "jump":
            self._add_jump()

    def _add(self, widget):
        self.param_layout.addWidget(widget)
        return widget

    def _spin(self, param_name):
        param = self.info.params[param_name]
        spin = QSpinBox()
        spin.setRange(param["min"], param["max"])
        spin.setValue(self.step.value)
        spin.setToolTip(f"{param['label']}: {param['help']}")
        spin.valueChanged.connect(self._set_value)
        return spin

    def _variable_combo(self, param_name):
        param = self.info.params[param_name]
        combo = _combo(self.editor.variable_model(param_name, self.step.value), self.step.value,
                       f"{param['label']}: {param['help']}", 16)
        combo.currentIndexChanged.connect(lambda _i, c=combo: self._set_value(c.currentData()))
        return combo

    def _add_animation(self):
        set_index, slot = animation_index_parts(self.step.value)
        help_text = self.info.params["camera_animation"]["help"]
        set_combo = self._add(_combo(self.editor.set_model(), set_index, help_text))
        slot_combo = self._add(_combo(self.editor.slot_model(set_index), slot, help_text, 14))

        def changed(_index):
            self.step.value = (self.step.value & 0x08) | set_combo.currentData() << 4 | slot_combo.currentData()
            if self.sender() is set_combo:   # the slot notes and empty marks follow the set
                self._build_params()
            self.edited.emit()
        set_combo.currentIndexChanged.connect(changed)
        slot_combo.currentIndexChanged.connect(changed)

    def _add_value(self):
        info, step, editor = self.info, self.step, self.editor
        operation_combo = self._add(_combo(editor.shared_model("operation"), step.operation,
                                           info.params["operation"]["help"]))
        operation_combo.setMinimumWidth(48)
        is_variable = step.operand == "variable"
        kind_combo = self._add(_combo(editor.shared_model("operand"), "variable" if is_variable else "number",
                                      info.params["operand"]["help"]))

        def operation_changed(_index):
            step.operation = operation_combo.currentData()
            self.edited.emit()

        def kind_changed(_index):
            if kind_combo.currentData() == "variable":
                step.operand, step.value = "variable", 0x11
            else:
                step.operand, step.value = "sbyte", 0
            self._build_params()
            self.edited.emit()
        operation_combo.currentIndexChanged.connect(operation_changed)
        kind_combo.currentIndexChanged.connect(kind_changed)
        if is_variable:
            self._add(self._variable_combo("read_variable"))
        else:
            spin = self._add(QSpinBox())
            spin.setRange(-32768, 32767)
            spin.setValue(step.value)
            spin.setToolTip("The number (its byte size is chosen for you)")
            spin.valueChanged.connect(self._set_value)

    def _add_jump(self):
        step = self.step
        condition_combo = self._add(_combo(self.editor.shared_model("condition"), step.condition,
                                           self.info.params["condition"]["help"]))

        def condition_changed(_index):
            step.condition = condition_combo.currentData()
            self.edited.emit()
        condition_combo.currentIndexChanged.connect(condition_changed)
        if step.raw_offset is not None:   # its own list: the shared one has no such entry
            model = _model([(f"line {i + 1}: {self.editor.short_text(s)}", i, "") for i, s in
                            enumerate(self.editor.steps)]
                           + [("the end of the script", END_OF_SCRIPT, ""),
                              (f"offset {step.raw_offset:+d} (not a command start)", RAW_OFFSET, "")], self)
        else:
            model = self.editor.target_model
        self._target_combo = self._add(_combo(model, None, self.info.params["jump_target"]["help"], 18))
        self._target_combo.currentIndexChanged.connect(self._target_changed)
        self.refresh_target()

    def refresh_target(self):
        """Point the jump's 'Go to' list at its command (which moves as commands are added or removed)."""
        combo = self._target_combo
        if combo is None:
            return
        steps = self.editor.steps
        if self.step.raw_offset is not None:
            data = RAW_OFFSET
        elif self.step.target is None or self.step.target not in steps:
            data = END_OF_SCRIPT
        else:
            data = self.editor.index_of(self.step.target)
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(data))
        combo.blockSignals(False)

    def _target_changed(self, _index):
        data = self._target_combo.currentData()
        if data == RAW_OFFSET or self.editor.updating_targets:
            return
        self.step.raw_offset = None
        self.step.target = None if data == END_OF_SCRIPT else self.editor.steps[data]
        self.edited.emit()

    def _set_value(self, value):
        self.step.value = value
        self.edited.emit()

    def _command_changed(self, _index):
        command_id = self.command_combo.currentData()
        if command_id is None or command_id == self.step.command_id:
            return
        fresh = new_step(self.info, command_id)
        for name in ("command_id", "op_code", "value", "operation", "operand", "condition", "target",
                     "raw_offset", "jump_int16", "raw"):
            setattr(self.step, name, getattr(fresh, name))   # same object: jumps to it stay on it
        self._build_params()
        self.edited.emit()

    # ------------------------------------------------------------------ text
    def refresh_text(self, line, sources, runs):
        self.line_label.setText(str(line + 1))
        lines = ", ".join(str(index + 1) for index in sources)
        self.source_label.setText(f"◀ {lines}" if sources else "")
        self.source_label.setToolTip(f"The jump on line {lines} comes here" if sources else "")
        text = self.editor.describe(self.step)
        if not runs:
            text = "never runs (filler) - " + text
        self.description_label.setText(text)
        self.description_label.setToolTip(text)
        self.description_label.setStyleSheet("color: gray;" + ("" if runs else " font-style: italic;"))


class CameraScriptStepsWidget(QWidget):
    """The rows of one camera script. set_script() shows a script, script_edited(bytes) gives back
    the script after each edit; set_collection() names the animations (sets, slots and their notes).
    `vm_source` gives the camera VM (with its script_json) when first needed: a host may load it lazily."""
    script_edited = pyqtSignal(bytes)

    def __init__(self, vm_source, context="", parent=None):
        super().__init__(parent)
        self._vm_source = vm_source
        self._info = None
        self._models = {}
        self._rows_stale = False
        self._build_pass = 0            # a newer build makes the passes of an older one stop
        self.updating_targets = False   # the shared "Go to" list is renumbered: its combos must not follow
        self.context = context
        self.collection = None
        self.slot_notes = {}
        self.steps = []
        self.rows = []
        self.target_model = QStandardItemModel(self)   # every jump's "Go to" list: the commands, then the end

        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(1)
        self.rows_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.rows_widget)
        self.add_button = QPushButton("Add a command at the end")
        self.add_button.clicked.connect(lambda: self._insert(len(self.steps)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, 1)
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_button)
        add_row.addStretch(1)
        layout.addLayout(add_row)

    @property
    def vm(self):
        return self._vm_source()

    @property
    def info(self) -> CameraScriptInfo:
        if self._info is None:
            self._info = CameraScriptInfo(self.vm.script_json)
        return self._info

    # ------------------------------------------------------------------ shared lists
    @property
    def command_model(self):
        """The command list, grouped (a disabled header per group)."""
        if "command" not in self._models:
            model = QStandardItemModel(self)
            groups = []
            for command in self.info.commands:
                if command["group"] not in groups:
                    groups.append(command["group"])
            for group in groups:
                header = QStandardItem(f"— {group} —")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                model.appendRow(header)
                for command in self.info.commands:
                    if command["group"] == group:
                        item = QStandardItem(command["label"])
                        item.setData(command["id"], Qt.ItemDataRole.UserRole)
                        item.setData(command["help"], Qt.ItemDataRole.ToolTipRole)
                        model.appendRow(item)
            unknown = QStandardItem("Unknown op code")
            unknown.setData("raw", Qt.ItemDataRole.UserRole)
            unknown.setFlags(Qt.ItemFlag.NoItemFlags)
            model.appendRow(unknown)
            self._models["command"] = model
        return self._models["command"]

    def shared_model(self, name):
        """The fixed lists: operations, operand kinds, jump tests."""
        if name not in self._models:
            info = self.info
            items = {
                "operation": [(operation["label"], operation["id"], operation["help"])
                              for operation in info.operations],
                "operand": [("number", "number", "A number written in the script"),
                            ("battle value", "variable", "A value read when the command runs")],
                "condition": [(condition["label"], condition["id"], "") for condition in info.conditions],
            }[name]
            self._models[name] = _model(items, self)
        return self._models[name]

    def variable_model(self, param_name, current):
        """The battle values a parameter takes; an id outside the list gets a list of its own with it."""
        info = self.info
        ids = list(info.read_variables) if param_name == "read_variable" else list(info.write_variables)
        key = (param_name, None if current in ids else current)
        if key not in self._models:
            if current not in ids:
                ids.append(current)
            self._models[key] = _model([(f"{info.variable_label(i)} (0x{i:02X})", i,
                                         info.variable_help(i, self.context)) for i in ids], self)
        return self._models[key]

    def set_model(self):
        if "set" not in self._models:
            count = len(self.collection.sets) if self.collection is not None else 0
            self._models["set"] = _model([(f"Set {i}" + ("" if i < count else " (missing)"), i,
                                           "" if i < count else "This track has no such set: nothing plays")
                                          for i in range(16)], self)
        return self._models["set"]

    def slot_model(self, set_index):
        key = ("slot", set_index)
        if key not in self._models:
            collection = self.collection
            items = []
            for slot in range(8):
                note = self.slot_notes.get((set_index, slot), "")
                empty = (collection is None or set_index >= len(collection.sets)
                         or collection.sets[set_index].animations[slot].empty)
                text = f"Slot {slot}" + (" (empty)" if empty else "") + (f" - {note}" if note else "")
                items.append((text, slot, "An empty slot plays nothing" if empty else note))
            self._models[key] = _model(items, self)
        return self._models[key]

    # ------------------------------------------------------------------ content
    def set_script(self, script):
        """Show `script` (None: nothing)."""
        self.steps = [] if script is None else read_steps(self.vm, self.info, bytes(script))
        self.add_button.setEnabled(script is not None)
        self._rebuild_rows()

    def set_collection(self, collection, slot_notes=None):
        self.collection = collection
        self.slot_notes = dict(slot_notes or {})
        for key in [key for key in self._models if key == "set" or isinstance(key, tuple) and key[0] == "slot"]:
            self._models.pop(key).deleteLater()   # the set and slot lists follow the collection
        self._rebuild_rows()

    def script(self) -> bytes:
        return script_bytes(self.info, self.steps)

    def index_of(self, step):
        return next(index for index, other in enumerate(self.steps) if other is step)

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_rows(in_passes=True)

    def _rebuild_rows(self):
        """The rows of self.steps - later if the view is not on screen (another view or tab)."""
        for row in self.rows:
            row.setParent(None)
            row.deleteLater()
        self.rows = []
        self._rows_stale = True
        self._build_pass += 1
        if self.isVisible():
            self.ensure_rows(in_passes=True)

    def ensure_rows(self, in_passes=False):
        """Build the rows if they wait for the view to be shown. `in_passes`: ROWS_PER_PASS now, the
        others in the next event loop passes (the window stays responsive); else all now (tests)."""
        if not self._rows_stale:
            return
        self._rows_stale = False
        self._build_pass += 1
        self._refresh_target_model()
        self._build_rows(self._build_pass, ROWS_PER_PASS if in_passes else len(self.steps))

    def _build_rows(self, build_pass, count):
        if build_pass != self._build_pass:   # the steps were shown again since
            return
        start = len(self.rows)
        for step in self.steps[start:start + count]:
            row = ScriptStepRow(self, step)
            row.edited.connect(self._on_edited)
            row.action_requested.connect(self._on_action)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows.append(row)
        self._refresh_rows()
        if len(self.rows) < len(self.steps):
            QTimer.singleShot(0, lambda: self._build_rows(build_pass, count))

    def _refresh_target_model(self):
        """One item per command then the end of the script, texts and indexes as they are now."""
        model = self.target_model
        wanted = len(self.steps) + 1
        self.updating_targets = True
        while model.rowCount() < wanted:
            model.insertRow(0, QStandardItem())
        while model.rowCount() > wanted:
            model.removeRow(0)
        self.updating_targets = False
        for index, step in enumerate(self.steps):
            item = model.item(index)
            item.setText(f"line {index + 1}: {self.short_text(step)}")
            item.setData(index, Qt.ItemDataRole.UserRole)
        end = model.item(wanted - 1)
        end.setText("the end of the script")
        end.setData(END_OF_SCRIPT, Qt.ItemDataRole.UserRole)

    def _refresh_rows(self):
        self._refresh_target_model()
        sources = jump_sources(self.steps)
        runs = reachable_steps(self.steps)
        for line, row in enumerate(self.rows):
            row.refresh_text(line, sources.get(id(row.step), []), id(row.step) in runs)
            row.refresh_target()

    def _on_edited(self):
        self._refresh_rows()
        self._emit()

    def _emit(self):
        try:
            script = self.script()
        except ValueError:
            return
        self.script_edited.emit(script)

    def _on_action(self, row, action):
        index = self.rows.index(row)
        if action == "insert":
            self._insert(index + 1)
            return
        if action == "remove":
            removed = self.steps.pop(index)
            following = self.steps[index] if index < len(self.steps) else None
            for step in self.steps:   # a jump to the removed command goes on at the one after it
                if step.is_jump and step.target is removed:
                    step.target = following
        elif action in ("up", "down"):
            other = index - 1 if action == "up" else index + 1
            if not 0 <= other < len(self.steps):
                return
            self.steps[index], self.steps[other] = self.steps[other], self.steps[index]
        self._rebuild_rows()
        self._emit()

    def _insert(self, index):
        self.steps.insert(index, new_step(self.info, "wait"))
        self._rebuild_rows()
        self._emit()

    # ------------------------------------------------------------------ text
    def short_text(self, step) -> str:
        command = self.info.command_by_id.get(step.command_id)
        return command["label"] if command else f"unknown op code 0x{step.op_code:02X}"

    def describe(self, step) -> str:
        """The step as a sentence, with what its values mean here."""
        info = self.info
        if step.command_id == "raw":
            return f"Unknown op code 0x{step.op_code:02X}: the engine stops here"
        command = info.command_by_id[step.command_id]
        if step.command_id == "play":
            set_index, slot = animation_index_parts(step.value)
            note = self.slot_notes.get((set_index, slot))
            missing = self.collection is not None and (
                set_index >= len(self.collection.sets) or self.collection.sets[set_index].animations[slot].empty)
            arguments = [f"set {set_index} slot {slot}" + (f" ({note})" if note else "")
                         + (" - plays nothing, no such animation" if missing else "")]
        elif step.command_id in ("play_var", "store"):
            arguments = [info.variable_label(step.value)]
        elif step.command_id == "value":
            operation = next(operation for operation in info.operations if operation["id"] == step.operation)
            operand = info.variable_label(step.value) if step.operand == "variable" else str(step.value)
            arguments = [operation["label"], operand]
        elif step.command_id == "jump":
            condition = next(condition for condition in info.conditions if condition["id"] == step.condition)
            if step.raw_offset is not None:
                where = f"offset {step.raw_offset:+d}"
            elif step.target is None or step.target not in self.steps:
                where = "the end of the script"
            else:
                where = f"line {self.index_of(step.target) + 1}"
            arguments = [condition["label"], where]
        else:
            arguments = [step.value]
        return command["text"].format(*arguments)
