from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QComboBox, QSpinBox, QLineEdit, QListWidget, QGroupBox, QScrollArea, QCheckBox
)

from SolomonRing.kernelentry import KernelEntry


def _prettify(name: str) -> str:
    return name.replace("_", " ").strip().title()


class KernelSectionTab(QWidget):
    """Generic list + form editor for one kernel data section, driven by JSON field defs.

    ``config`` keys:
      * ``section_id``   : kernel section id (index into ``KernelManager.section_list``)
      * ``text_labels``  : labels for the section's text offsets, e.g. ``["Name", "Description"]``
      * ``entry_names``  : optional static labels when the section has no names
      * ``fields``       : list of field defs (see ``kernel_bin_data.json`` -> ``section_fields``)
    """

    def __init__(self, game_data, registry, config, game_data_folder="FF8GameData"):
        super().__init__()
        self.game_data = game_data
        self.registry = registry
        self.config = config
        self.section_id = config["section_id"]
        self.text_labels = config.get("text_labels", [])
        self.entry_names = config.get("entry_names")
        self.fields = config.get("fields", [])

        self._entries = []
        self._current_index = -1
        self._text_widgets = []          # list of QLineEdit, one per text offset
        self._field_widgets = {}         # field name -> widget descriptor

        layout = QHBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(180)
        self.list_widget.setStyleSheet("font-size: 11pt;")
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._form_host = QWidget()
        self._form_layout = QVBoxLayout(self._form_host)
        self._build_form()
        self._form_layout.addStretch()
        scroll.setWidget(self._form_host)
        layout.addWidget(scroll, 1)

        self.setEnabled(False)

    # --------------------------------------------------------------------- build
    def _field_tooltip(self, field):
        parts = []
        if field.get("help"):
            parts.append(field["help"])
        size = field["size"]
        offset = field["offset"]
        max_value = (1 << (8 * size)) - 1
        meta = (f"Offset 0x{offset:02X} · {size} byte{'s' if size > 1 else ''} · "
                f"range 0–{max_value} (0x{max_value:X})")
        lookup_name = field.get("lookup")
        if lookup_name:
            lookup = self.registry.resolve(lookup_name)
            if lookup:
                kind = "flags" if lookup["type"] == "flags" else "options"
                meta += f" · {len(lookup['entries'])} {kind}"
        parts.append(meta)
        return "\n".join(parts)

    def _build_form(self):
        # Text (name / description) editors
        if self.text_labels:
            box = QGroupBox("Text")
            box.setToolTip("Name / description strings. Text offsets are recomputed automatically "
                           "on save; use the toolbar to (un)compress all kernel text.")
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
            for label in self.text_labels:
                edit = QLineEdit()
                edit.setToolTip(f"{label} string for this entry.")
                # Names are short; descriptions a bit longer, but neither needs full width.
                edit.setFixedWidth(200 if label == "Name" else 380)
                self._text_widgets.append(edit)
                form.addRow(QLabel(label), edit)
            self._form_layout.addWidget(box)

        # Group fields by their optional "group" key, preserving order of appearance.
        groups = []
        group_map = {}
        for field in self.fields:
            gname = field.get("group", "Data")
            if gname not in group_map:
                group_map[gname] = []
                groups.append(gname)
            group_map[gname].append(field)

        for gname in groups:
            box = QGroupBox(gname)
            vbox = QVBoxLayout(box)
            vbox.setSpacing(4)
            pending = []  # (label, widget) pairs waiting to be placed on a row

            # Label column width = this group's longest title, so every value/editor in
            # the group lines up in a column (left-aligned labels keep them flush-left).
            metrics = self.fontMetrics()
            label_width = 0
            for field in group_map[gname]:
                if self._is_flags(field):
                    continue
                text = field.get("label", _prettify(field["name"]))
                label_width = max(label_width, metrics.horizontalAdvance(text))
            label_width += 6

            def flush_row():
                if not pending:
                    return
                row = QHBoxLayout()
                row.setSpacing(6)
                for lbl, wdg in pending:
                    lbl.setFixedWidth(label_width)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    row.addWidget(lbl)
                    row.addWidget(wdg)
                    row.addSpacing(24)
                row.addStretch(1)
                vbox.addLayout(row)
                pending.clear()

            for field in group_map[gname]:
                tooltip = self._field_tooltip(field)
                widget = self._make_field_widget(field)
                widget.setToolTip(tooltip)
                if isinstance(widget, QGroupBox):  # flags: own full-width row, left-hugged
                    flush_row()
                    row = QHBoxLayout()
                    row.setSpacing(6)
                    row.addWidget(widget)
                    row.addStretch(1)
                    vbox.addLayout(row)
                    continue
                label = QLabel(field.get("label", _prettify(field["name"])))
                label.setToolTip(tooltip)
                pending.append((label, widget))
                if len(pending) == 2:
                    flush_row()
            flush_row()
            self._form_layout.addWidget(box)

    def _is_flags(self, field):
        lookup_name = field.get("lookup")
        if not lookup_name:
            return False
        lookup = self.registry.resolve(lookup_name)
        return bool(lookup) and lookup["type"] == "flags"

    def _make_field_widget(self, field):
        name = field["name"]
        readonly = field.get("readonly", False)
        lookup_name = field.get("lookup")
        lookup = self.registry.resolve(lookup_name) if lookup_name else None

        if lookup and lookup["type"] == "flags":
            box = QGroupBox(field.get("label", _prettify(name)))
            grid = QGridLayout(box)
            checks = []
            for i, entry in enumerate(lookup["entries"]):
                cb = QCheckBox(entry["name"])
                # Individual bits proven unused are shown but not editable.
                if readonly or entry["name"].lower().startswith(("unused", "padding")):
                    cb.setEnabled(False)
                grid.addWidget(cb, i // 4, i % 4)
                checks.append((entry["mask"], cb))
            self._field_widgets[name] = ("flags", field, checks)
            return box

        if lookup and lookup["type"] == "enum":
            combo = QComboBox()
            for entry in lookup["entries"]:
                combo.addItem(entry["name"], entry["value"])
            # Size the closed combo to its longest entry (plus arrow/frame), capped so a
            # few very long names don't blow up the row; the dropdown list always gets
            # the full width of the longest entry.
            metrics = combo.fontMetrics()
            widest = max((metrics.horizontalAdvance(e["name"]) for e in lookup["entries"]),
                         default=60)
            combo.setFixedWidth(min(widest + 40, 320))
            combo.view().setMinimumWidth(widest + 40)
            if readonly:
                combo.setEnabled(False)
            self._field_widgets[name] = ("enum", field, combo)
            return combo

        # Plain integer
        max_value = (1 << (8 * field["size"])) - 1
        if max_value <= 0x7FFFFFFF:
            spin = QSpinBox()
            spin.setRange(0, max_value)
            # Size the spinbox to its biggest possible value (plus buttons/frame).
            spin.setFixedWidth(spin.fontMetrics().horizontalAdvance(str(max_value)) + 36)
            if readonly:
                spin.setReadOnly(True)
                spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
                spin.setEnabled(False)
            self._field_widgets[name] = ("int", field, spin)
            return spin
        # 32-bit values overflow QSpinBox -> hex line edit
        edit = QLineEdit()
        edit.setFixedWidth(edit.fontMetrics().horizontalAdvance("0x" + "F" * 2 * field["size"]) + 16)
        if readonly:
            edit.setReadOnly(True)
            edit.setEnabled(False)
        self._field_widgets[name] = ("hex", field, edit)
        return edit

    # ---------------------------------------------------------------- load/save
    def load_section(self, section, text_section):
        """Bind this tab to a freshly loaded section + its linked text section."""
        self._current_index = -1
        self._entries = []
        nb_text = len(self.text_labels)
        subsections = section.get_subsection_list()
        for i, subsection in enumerate(subsections):
            self._entries.append(
                KernelEntry(subsection, text_section, nb_text, i, self.fields, self.game_data))

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for i, entry in enumerate(self._entries):
            self.list_widget.addItem(self._entry_label(i, entry))
        self.list_widget.blockSignals(False)

        self.setEnabled(True)
        if self._entries:
            self.list_widget.setCurrentRow(0)
            self._load_entry(0)
            self._current_index = 0

    def _entry_label(self, index, entry):
        if self.text_labels and entry.has_text(0):
            name = entry.get_text(0).strip()
            if name:
                return f"{index}: {name}"
        if self.entry_names and index < len(self.entry_names):
            return f"{index}: {self.entry_names[index]}"
        return f"#{index}"

    def _on_row_changed(self, index):
        if index < 0 or index >= len(self._entries):
            return
        if self._current_index >= 0:
            self._save_entry(self._current_index)
        self._load_entry(index)
        self._current_index = index

    def _load_entry(self, index):
        entry = self._entries[index]
        for i, edit in enumerate(self._text_widgets):
            edit.blockSignals(True)
            edit.setEnabled(entry.has_text(i))
            edit.setText(entry.get_text(i))
            edit.blockSignals(False)
        for name, (kind, field, widget) in self._field_widgets.items():
            value = entry.get(name)
            if kind == "int":
                widget.setValue(value)
            elif kind == "hex":
                widget.setText(f"0x{value:X}")
            elif kind == "enum":
                pos = widget.findData(value)
                if pos < 0:
                    widget.addItem(f"0x{value:X} (raw)", value)
                    pos = widget.findData(value)
                widget.setCurrentIndex(pos)
            elif kind == "flags":
                for mask, cb in widget:
                    cb.setChecked(bool(value & mask))

    def _save_entry(self, index):
        entry = self._entries[index]
        for i, edit in enumerate(self._text_widgets):
            if entry.has_text(i):
                entry.set_text(i, edit.text())
        for name, (kind, field, widget) in self._field_widgets.items():
            if kind == "int":
                entry.set(name, widget.value())
            elif kind == "hex":
                text = widget.text().strip()
                try:
                    value = int(text, 16) if text.lower().startswith("0x") else int(text or "0")
                except ValueError:
                    value = entry.get(name)
                entry.set(name, value)
            elif kind == "enum":
                entry.set(name, widget.currentData())
            elif kind == "flags":
                value = 0
                for mask, cb in widget:
                    if cb.isChecked():
                        value |= mask
                entry.set(name, value)
        # Refresh the list label in case the name changed.
        self.list_widget.item(index).setText(self._entry_label(index, entry))

    def commit(self):
        """Flush the currently selected entry back to the underlying data."""
        if self._current_index >= 0:
            self._save_entry(self._current_index)
