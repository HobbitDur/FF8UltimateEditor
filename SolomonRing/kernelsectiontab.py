import os
import textwrap

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QComboBox, QSpinBox, QLineEdit, QListWidget, QGroupBox, QScrollArea, QCheckBox,
    QPushButton, QToolButton, QFileDialog, QMessageBox
)

from SolomonRing.kernelentry import KernelEntry
from SolomonRing.menu_refine_reference import MenuRefineReference
from SolomonRing.formula_popup import FormulaPopup
from SmallWidget.nowheel import NoWheelComboBox, NoWheelSpinBox


def _prettify(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _wrap_tooltip(text: str, width: int = 62) -> str:
    """Word-wrap a tooltip so it grows in height, not width (Qt does not wrap
    plain-text tooltips itself). Existing line breaks are preserved; each logical
    line is wrapped to ``width`` columns."""
    lines = []
    for line in text.split("\n"):
        if len(line) <= width:
            lines.append(line)
        else:
            lines.append(textwrap.fill(line, width=width,
                                       break_long_words=False, break_on_hyphens=False))
    return "\n".join(lines)


class KernelSectionTab(QWidget):
    """Generic list + form editor for one kernel data section, driven by JSON field defs.

    ``config`` keys:
      * ``section_id``   : kernel section id (index into ``KernelManager.section_list``)
      * ``text_labels``  : labels for the section's text offsets, e.g. ``["Name", "Description"]``
      * ``entry_names``  : optional static labels when the section has no names
      * ``fields``       : list of field defs (see ``kernel_bin_data.json`` -> ``section_fields``)
    """

    def __init__(self, game_data, registry, config, game_data_folder="FF8GameData", jump_callback=None):
        super().__init__()
        self.game_data = game_data
        self.registry = registry
        self.config = config
        self.section_id = config["section_id"]
        self.text_labels = config.get("text_labels", [])
        self.entry_names = config.get("entry_names")
        self.fields = config.get("fields", [])
        # Optional callable(section_id, label) -> switch the app to another section's tab,
        # used by fields whose value only makes sense alongside another section's data
        # (e.g. the Slot array's set-id references the Selphie limit-break sets tab).
        self._jump_callback = jump_callback
        # Menu abilities' Refine data lives entirely outside kernel.bin (menu.fs's mngrp
        # files) - loaded on demand via a button, not part of the normal file-load flow.
        self._menu_refine_ref = None
        self._menu_refine_label = None
        self._menu_refine_button = None
        self._formula_popup = None       # single live formula preview window for this tab

        self._entries = []
        self._current_index = -1
        self._text_widgets = []          # list of QLineEdit, one per text offset
        self._field_widgets = {}         # field name -> widget descriptor
        self._embed_map = {}             # flags-field name -> [dependent field defs to nest inside it]

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
        self._wire_enable_when()
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
        mask = field.get("mask")
        meta = f"Offset 0x{offset:02X} · {size} byte{'s' if size > 1 else ''}"
        if field.get("bool"):
            meta += " · boolean (0/1 - the engine only ever checks this byte for zero/nonzero)"
        else:
            max_value = mask if mask is not None else (1 << (8 * size)) - 1
            meta += f" · range 0–{max_value}"
            if mask is not None:
                meta += f" (mask 0x{mask:02X})"
        lookup_name = field.get("lookup")
        if lookup_name:
            lookup = self.registry.resolve(lookup_name)
            if lookup:
                kind = "flags" if lookup["type"] == "flags" else "options"
                meta += f" · {len(lookup['entries'])} {kind}"
        parts.append(meta)
        return _wrap_tooltip("\n".join(parts))

    def _build_form(self):
        # Text (name / description) editors
        if self.text_labels:
            box = QGroupBox("Text")
            box.setToolTip(_wrap_tooltip(
                "Name / description strings. Text offsets are recomputed automatically "
                "on save; use the toolbar to (un)compress all kernel text."))
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

            # A field can opt into a named nested sub-box via "subgroup"; those fields (and
            # any button/panel their fields trigger) render inside that inner QGroupBox
            # instead of the main group flow. Order of first appearance is preserved.
            sub_order = []
            sub_map = {}
            main_fields = []
            for field in group_map[gname]:
                sg = field.get("subgroup")
                if sg:
                    if sg not in sub_map:
                        sub_map[sg] = []
                        sub_order.append(sg)
                    sub_map[sg].append(field)
                else:
                    main_fields.append(field)

            self._render_field_block(vbox, main_fields)
            for sg in sub_order:
                sub_box = QGroupBox(sg)
                sub_vbox = QVBoxLayout(sub_box)
                sub_vbox.setSpacing(4)
                # Inside a subgroup, lead with the combos (e.g. a "Refine table" selector
                # reads better above the offset spinboxes that pick rows within it).
                self._render_field_block(sub_vbox, sub_map[sg], combos_first=True)
                vbox.addWidget(sub_box)

            self._form_layout.addWidget(box)

    def _render_field_block(self, vbox, fields, combos_first=False):
        """Render a set of fields into ``vbox``: any reference button/panel their fields
        trigger, then the fields themselves grouped by editor kind (spinboxes, then combos,
        then bitfields; explicit ``row`` groups stay on one line). ``combos_first`` swaps the
        spinbox/combo order for the block."""
        if not fields:
            return

        # A field can name another section whose data it references but can't itself
        # display; a button jumps the app to that section's tab.
        jump_target = next((f["jump_to_section"] for f in fields if f.get("jump_to_section")), None)
        if jump_target is not None and self._jump_callback:
            jump_btn = QPushButton(f"Open {jump_target[1]} →")
            jump_btn.setToolTip(f"Switch to the {jump_target[1]} tab to see/edit what these "
                                f"values reference.")
            jump_btn.clicked.connect(lambda _, sid=jump_target[0]: self._jump_callback(sid))
            jump_row = QHBoxLayout()
            jump_row.addWidget(jump_btn)
            jump_row.addStretch(1)
            vbox.addLayout(jump_row)

        # The Refine reference button loads menu.fs's mngrp data for the WHOLE tab (all menu
        # abilities share it), so it sits at the top of the main group as a one-time action,
        # separate from the per-entry decoded panel (which lives in the Refine sub-box below).
        if any(f.get("menu_refine_button") for f in fields):
            load_btn = QPushButton("Load Refine reference (mngrp.bin)...")
            load_btn.setToolTip(
                "The item/magic/card conversions each Refine ability performs live in menu.fs, "
                "not kernel.bin. Pick mngrphd.bin (mngrp.bin must be alongside it) once to decode "
                "them for every Refine ability in this tab. Reference only - nothing here is saved.")
            load_btn.clicked.connect(self._load_menu_refine_reference)
            self._menu_refine_button = load_btn
            load_row = QHBoxLayout()
            load_row.addWidget(load_btn)
            load_row.addStretch(1)
            vbox.addLayout(load_row)

        # Fields with "enabled_unless_bit" are nested inside their referenced flags field's
        # box (e.g. a battle command's Submenu picker) instead of a separate block.
        embed_map = {}
        embedded_names = set()
        for field in fields:
            dep = field.get("enabled_unless_bit")
            if dep:
                embed_map.setdefault(dep["field"], []).append(field)
                embedded_names.add(field["name"])
        self._embed_map = embed_map

        # Group fields by editor kind so like-widgets line up: spinboxes, then combos, then
        # bitfields; fields sharing a "row" stay on one line together.
        row_order = []
        row_groups = {}
        spins, combos, flag_fields = [], [], []
        for field in fields:
            if field["name"] in embedded_names:
                continue
            rid = field.get("row")
            if rid is not None:
                if rid not in row_groups:
                    row_groups[rid] = []
                    row_order.append(rid)
                row_groups[rid].append(field)
            elif self._is_flags(field) or field.get("camera_selector"):
                flag_fields.append(field)
            elif field.get("lookup"):
                combos.append(field)
            else:
                spins.append(field)

        # Convention: Status 1 is always displayed before Status 2, regardless of their
        # physical byte order (some sections store Status 2 first).
        names = [f["name"] for f in flag_fields]
        if "status_1" in names and "status_2" in names and \
                names.index("status_2") < names.index("status_1"):
            s1 = flag_fields.pop(names.index("status_1"))
            flag_fields.insert([f["name"] for f in flag_fields].index("status_2"), s1)

        if combos_first:
            self._emit_aligned_rows(vbox, self._chunk(combos, 2))
            self._emit_aligned_rows(vbox, self._chunk(spins, 2))
        else:
            self._emit_aligned_rows(vbox, self._chunk(spins, 2))
            self._emit_aligned_rows(vbox, self._chunk(combos, 2))
        if row_order:
            self._emit_aligned_rows(vbox, [row_groups[rid] for rid in row_order])
        for field in flag_fields:
            self._emit_single_row(vbox, [field], flags=True)

        # Per-entry decoded Refine table for the current ability (the load button that fills
        # it lives at the top of the main group - it's shared by every menu ability).
        if any(f.get("menu_refine_reference") for f in fields):
            self._menu_refine_label = QLabel("(load the Refine reference above to see what this "
                                             "ability refines)")
            self._menu_refine_label.setStyleSheet("color: gray; font-size: 9pt;")
            self._menu_refine_label.setWordWrap(True)
            vbox.addWidget(self._menu_refine_label)

    @staticmethod
    def _chunk(items, n):
        return [items[i:i + n] for i in range(0, len(items), n)]

    def _labeled_widget(self, field):
        tooltip = self._field_tooltip(field)
        widget = self._make_field_widget(field)
        widget.setToolTip(tooltip)
        label = QLabel(field.get("label", _prettify(field["name"])))
        label.setToolTip(tooltip)
        return label, widget

    def _emit_aligned_rows(self, vbox, rows):
        """Render a set of rows (each a list of fields). Labels are aligned *per column*
        so a long label in one column never pushes a short label's editor away in another
        (fixes both the 'value far from title' gaps and the Ability 9→10 shift). Editor
        widgets are aligned per column too - a field with an extra 'f(x)' button or a
        seconds/percent hint is wider than a bare spinbox, and without this a column would
        drift left/right depending on which row it landed in (e.g. a lone field lacking a
        formula button next to siblings that all have one)."""
        rows = [r for r in rows if r]
        if not rows:
            return
        metrics = self.fontMetrics()
        ncol = max(len(r) for r in rows)
        col_w = [0] * ncol

        def _label_width(text):
            # A label may be multi-line ("\n"); size the column to its widest LINE, not the
            # whole string, so a two-line label stays narrow.
            return max(metrics.horizontalAdvance(line) for line in text.split("\n"))

        for r in rows:
            for i, f in enumerate(r):
                col_w[i] = max(col_w[i], _label_width(f.get("label", _prettify(f["name"]))))

        # Build every editor widget once (building twice would leave duplicate registered
        # widgets), measuring its natural width so the layout pass can equalize per column.
        built = []
        editor_w = [0] * ncol
        for r in rows:
            built_row = []
            for i, f in enumerate(r):
                lbl, wdg = self._labeled_widget(f)
                editor_w[i] = max(editor_w[i], wdg.sizeHint().width())
                built_row.append((lbl, wdg))
            built.append(built_row)

        for r in built:
            row = QHBoxLayout()
            row.setSpacing(6)
            for i, (lbl, wdg) in enumerate(r):
                lbl.setFixedWidth(col_w[i] + 6)
                lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                wdg.setMinimumWidth(editor_w[i])
                row.addWidget(lbl)
                row.addWidget(wdg)
                row.addSpacing(18)
            row.addStretch(1)
            vbox.addLayout(row)

    def _wire_enable_when(self):
        """Grey out a field's widget unless another (enum) field's current value is in a
        set, driven by ``enabled_when``: ``{"field": <enum name>, "values": [...]}``. Live -
        re-evaluates whenever the source combo changes (incl. each entry load). A field that
        also owns the per-entry Refine panel greys it too (so Start/End offset + the decoded
        panel dim together for a non-Refine ability); the load button stays enabled since it
        loads data for the whole tab, not the current entry."""
        for field in self.fields:
            dep = field.get("enabled_when")
            if not dep:
                continue
            target = self._field_widgets.get(field["name"])
            source = self._field_widgets.get(dep["field"])
            if not target or not source or source[0] != "enum":
                continue
            src_widget = source[2]
            values = set(dep["values"])
            targets = [target[2]]
            if field.get("menu_refine_reference") and self._menu_refine_label is not None:
                targets.append(self._menu_refine_label)

            def _sync(_=None, sw=src_widget, vals=values, tgts=targets):
                on = sw.currentData() in vals
                for t in tgts:
                    t.setEnabled(on)

            src_widget.currentIndexChanged.connect(_sync)
            _sync()

    def _emit_single_row(self, vbox, fields, flags=False):
        """One line holding all given fields (natural widths), left-hugged."""
        row = QHBoxLayout()
        row.setSpacing(6)
        for field in fields:
            if flags:
                tooltip = self._field_tooltip(field)
                widget = self._make_field_widget(field)
                widget.setToolTip(tooltip)
                row.addWidget(widget)
            else:
                lbl, wdg = self._labeled_widget(field)
                row.addWidget(lbl)
                row.addWidget(wdg)
                row.addSpacing(18)
        row.addStretch(1)
        vbox.addLayout(row)

    def _is_flags(self, field):
        lookup_name = field.get("lookup")
        if not lookup_name:
            return False
        lookup = self.registry.resolve(lookup_name)
        return bool(lookup) and lookup["type"] == "flags"

    def _with_formula_button(self, field, inner):
        """Wrap ``inner`` (the editor) with a small trailing 'f(x)' button that opens the
        live formula preview for ``field``."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(inner)
        btn = QToolButton()
        btn.setText("ƒ(x)")            # ƒ(x)
        btn.setAutoRaise(True)
        btn.setToolTip("Show this value plugged into its formula (with editable "
                       "battle assumptions).")
        btn.setStyleSheet("QToolButton { color: palette(highlight); font-style: italic; }")
        btn.clicked.connect(lambda _=False, f=field: self._open_formula_popup(f))
        row.addWidget(btn)
        row.addStretch(1)
        return container

    def _open_formula_popup(self, field):
        if self._formula_popup is None:
            self._formula_popup = FormulaPopup(self, self)
        self._formula_popup.show_for(field)

    def _make_camera_widget(self, field):
        """Composite editor for the enemy-attack Camera byte: a 'default (none)' checkbox
        that greys the rest, a 'force' checkbox (bit 0x80) and the animation index (bits
        0x7F). 0xFF = default/none. Registered as kind 'camera'; load/save (de)composes
        the single byte."""
        box = QGroupBox(field.get("label", "Camera"))
        box.setToolTip(_wrap_tooltip(field.get("help", "")))
        v = QVBoxLayout(box)
        v.setSpacing(3)
        unused = QCheckBox("No specific camera (default = 0xFF)")
        force = QCheckBox("Force this camera (bit 0x80) — play it even in the state that "
                          "would otherwise skip it")
        idx_row = QHBoxLayout()
        idx_lbl = QLabel("Camera animation index")
        idx = NoWheelSpinBox()
        idx.setRange(0, 0x7F)
        idx.setFixedWidth(idx.fontMetrics().horizontalAdvance("127") + 36)
        idx_row.addWidget(idx_lbl)
        idx_row.addWidget(idx)
        idx_row.addStretch(1)
        v.addWidget(unused)
        v.addWidget(force)
        v.addLayout(idx_row)

        def _sync(_=None):
            on = not unused.isChecked()
            force.setEnabled(on)
            idx.setEnabled(on)
            idx_lbl.setEnabled(on)
        unused.toggled.connect(_sync)

        box._cam_unused, box._cam_force, box._cam_index, box._cam_sync = unused, force, idx, _sync
        self._field_widgets[field["name"]] = ("camera", field, box)
        return box

    def _make_field_widget(self, field):
        name = field["name"]
        readonly = field.get("readonly", False)
        lookup_name = field.get("lookup")
        lookup = self.registry.resolve(lookup_name) if lookup_name else None

        if field.get("camera_selector"):
            return self._make_camera_widget(field)

        if lookup and lookup["type"] == "flags":
            box = QGroupBox(field.get("label", _prettify(name)))
            outer = QVBoxLayout(box)
            outer.setSpacing(4)

            # Checkboxes that gate an embedded field (e.g. "Instant" gates the Submenu
            # picker) are pulled out of the main grid into their own nested sub-box
            # together with what they gate, so the coupling reads as one unit rather
            # than being lost among the other independent flags.
            embedded = self._embed_map.get(name, [])
            coupling_masks = {dep_field["enabled_unless_bit"]["mask"] for dep_field in embedded}

            grid = QGridLayout()
            checks = []
            coupled_checks = {}
            grid_i = 0
            for entry in lookup["entries"]:
                cb = QCheckBox(entry["name"])
                # Individual bits proven unused/inert here are shown (so the current value is
                # visible) but not editable: "unused"/"padding" names, or an explicit
                # "disabled" flag on the lookup entry (e.g. the attack-flags 0x20 bit, which
                # does nothing outside the Battle Items tab).
                if readonly or entry.get("disabled") or \
                        entry["name"].lower().startswith(("unused", "padding")):
                    cb.setEnabled(False)
                checks.append((entry["mask"], cb))
                if entry["mask"] in coupling_masks:
                    coupled_checks[entry["mask"]] = cb
                else:
                    grid.addWidget(cb, grid_i // 4, grid_i % 4)
                    grid_i += 1
            outer.addLayout(grid)
            self._field_widgets[name] = ("flags", field, checks)

            for dep_field in embedded:
                dep = dep_field["enabled_unless_bit"]
                cb = coupled_checks.get(dep["mask"])
                sub_box = QGroupBox()
                sub_vbox = QVBoxLayout(sub_box)
                sub_vbox.setSpacing(4)
                if cb:
                    sub_vbox.addWidget(cb)
                lbl, wdg = self._labeled_widget(dep_field)
                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(lbl)
                row.addWidget(wdg)
                row.addStretch(1)
                sub_vbox.addLayout(row)
                outer.addWidget(sub_box)
                if cb:
                    def _sync(checked, widget=wdg):
                        widget.setEnabled(not checked)
                    cb.toggled.connect(_sync)
                    _sync(cb.isChecked())
            return box

        if lookup and lookup["type"] == "enum":
            combo = NoWheelComboBox()
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
            if field.get("formula") and not readonly:
                return self._with_formula_button(field, combo)
            return combo

        if field.get("bool"):
            cb = QCheckBox()
            if readonly:
                cb.setEnabled(False)
            self._field_widgets[name] = ("bool", field, cb)
            return cb

        # Plain integer. A mask (a sub-byte/sub-word field sharing its offset with a
        # sibling, or - as here - the meaningful low bits of a WORD whose high bits are
        # proven inert) caps the editable range to just those bits.
        mask = field.get("mask")
        max_value = mask if mask is not None else (1 << (8 * field["size"])) - 1
        if max_value <= 0x7FFFFFFF:
            spin = NoWheelSpinBox()
            spin.setRange(0, max_value)
            # Size the spinbox to its biggest possible value (plus buttons/frame).
            spin.setFixedWidth(spin.fontMetrics().horizontalAdvance(str(max_value)) + 36)
            if readonly:
                spin.setReadOnly(True)
                spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
                spin.setEnabled(False)
            self._field_widgets[name] = ("int", field, spin)
            # Optional live "≈ N <unit>" hint under the spinbox for a raw byte that's
            # actually value*factor in some other unit (seconds, percent, ...).
            unit = None
            if field.get("seconds_factor"):
                unit = (field["seconds_factor"], "s", 1, field.get("seconds_note"))
            elif field.get("percent_factor"):
                unit = (field["percent_factor"], "%", 2, field.get("percent_note"))
            inner = spin
            if unit:
                factor, suffix, decimals, note = unit
                container = QWidget()
                vbox = QVBoxLayout(container)
                vbox.setContentsMargins(0, 0, 0, 0)
                vbox.setSpacing(0)
                vbox.addWidget(spin)
                hint_label = QLabel()
                hint_label.setStyleSheet("color: gray; font-size: 8pt;")
                if note:
                    hint_label.setToolTip(_wrap_tooltip(note))
                hint_label.setFixedWidth(spin.width())

                def _update_hint(value, lbl=hint_label, fac=factor, sfx=suffix, dec=decimals):
                    lbl.setText(f"≈ {value * fac:.{dec}f}{sfx}")

                spin.valueChanged.connect(_update_hint)
                _update_hint(spin.value())
                vbox.addWidget(hint_label)
                inner = container
            # A field that feeds a runtime formula gets a small "f(x)" button that opens
            # a live formula preview (formula + this value + assumptions -> result).
            if field.get("formula") and not readonly:
                return self._with_formula_button(field, inner)
            return inner
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
        text_name = entry.get_text(0).strip() if (self.text_labels and entry.has_text(0)) else ""
        static = self.entry_names[index] if (self.entry_names and index < len(self.entry_names)) else ""
        # entry_name_primary: the static name (e.g. the GF name) is the identity; the
        # editable text (its attack name) is shown in parentheses.
        if self.config.get("entry_name_primary") and static:
            return f"{index}: {static}" + (f" ({text_name})" if text_name else "")
        if text_name:
            return f"{index}: {text_name}"
        if static:
            return f"{index}: {static}"
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
            elif kind == "bool":
                widget.setChecked(bool(value))
            elif kind == "camera":
                widget._cam_unused.setChecked(value == 0xFF)
                widget._cam_force.setChecked(bool(value & 0x80))
                widget._cam_index.setValue(value & 0x7F)
                widget._cam_sync()
        self._refresh_menu_refine_display(entry)

    def _load_menu_refine_reference(self):
        mngrphd_path, _ = QFileDialog.getOpenFileName(
            self, "Open mngrphd.bin (mngrp.bin must be alongside it)", "", "mngrphd.bin (mngrphd.bin)")
        if not mngrphd_path:
            return
        mngrp_path = os.path.join(os.path.dirname(mngrphd_path), "mngrp.bin")
        if not os.path.isfile(mngrp_path):
            QMessageBox.warning(self, "Refine reference",
                                f"Couldn't find mngrp.bin next to that file:\n{mngrp_path}")
            return
        try:
            self._menu_refine_ref = MenuRefineReference(mngrphd_path, mngrp_path)
        except Exception as exc:
            QMessageBox.warning(self, "Refine reference", f"Failed to read those files:\n{exc}")
            return
        if self._current_index >= 0:
            self._refresh_menu_refine_display(self._entries[self._current_index])

    def _refresh_menu_refine_display(self, entry):
        if self._menu_refine_label is None:
            return
        if self._menu_refine_ref is None or not entry.has_field("menu_index"):
            return
        def _names(lookup_name):
            lk = self.registry.resolve(lookup_name)
            return {e["value"]: e["name"] for e in lk["entries"]} if lk else {}
        lines = self._menu_refine_ref.describe(
            entry.get("menu_index"), entry.get("start_offset"), entry.get("end_offset"),
            _names("item"), _names("magic"), _names("card"))
        self._menu_refine_label.setText("\n".join(lines))

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
            elif kind == "bool":
                entry.set(name, 1 if widget.isChecked() else 0)
            elif kind == "camera":
                if widget._cam_unused.isChecked():
                    entry.set(name, 0xFF)
                else:
                    entry.set(name, (0x80 if widget._cam_force.isChecked() else 0)
                              | (widget._cam_index.value() & 0x7F))
        # Refresh the list label in case the name changed.
        self.list_widget.item(index).setText(self._entry_label(index, entry))

    def commit(self):
        """Flush the currently selected entry back to the underlying data."""
        if self._current_index >= 0:
            self._save_entry(self._current_index)

    def refresh_dynamic_combos(self):
        """Re-populate every combo built from a "dynamic_lookup" field (content computed
        from another section's just-loaded data, e.g. Slot array's per-set summaries) with
        the registry's current entries for that lookup, preserving the selected value."""
        for name, (kind, field, widget) in self._field_widgets.items():
            if kind != "enum" or not field.get("dynamic_lookup"):
                continue
            lookup = self.registry.resolve(field["lookup"])
            if not lookup:
                continue
            current = widget.currentData()
            widget.blockSignals(True)
            widget.clear()
            for entry in lookup["entries"]:
                widget.addItem(entry["name"], entry["value"])
            # Real content can be much longer than the placeholder it was first sized for
            # (e.g. "Set 0" -> "0: Cure x10, Curaga x5, ..."); resize to fit.
            metrics = widget.fontMetrics()
            widest = max((metrics.horizontalAdvance(e["name"]) for e in lookup["entries"]),
                        default=60)
            widget.setFixedWidth(min(widest + 40, 480))
            widget.view().setMinimumWidth(widest + 40)
            pos = widget.findData(current)
            if pos < 0 and current is not None:
                widget.addItem(f"0x{current:X} (raw)", current)
                pos = widget.findData(current)
            if pos >= 0:
                widget.setCurrentIndex(pos)
            widget.blockSignals(False)
