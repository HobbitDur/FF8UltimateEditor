"""Small live popup showing a field's formula with the current value + assumptions
substituted. Opened by the "f(x)" button next to a formula-tagged field."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QSpinBox, QPushButton,
    QHBoxLayout, QWidget,
)

from . import formula_specs as fs
from . import formula_latex as flx


class FormulaPopup(QDialog):
    """Non-modal tool window: formula + editable assumptions + live result. One per tab
    (opening a new one for another field re-targets this same window)."""

    def __init__(self, parent, tab):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(500)
        self.setSizeGripEnabled(True)     # draggable resize handle
        self._tab = tab
        self._field = None
        self._formula_key = None
        self._param_spins = {}
        self._field_conn = None

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self._title.setWordWrap(True)
        root.addWidget(self._title)

        self._symbolic = self._boxed("Formula", root)
        self._substituted = self._boxed("With the current value", root)

        cap = QLabel("Result")
        cap.setStyleSheet("color: gray; font-size: 8pt; font-weight: bold;")
        root.addWidget(cap)
        self._result = QLabel()
        self._result.setStyleSheet("font-weight: bold; font-size: 12pt; color: palette(highlight);")
        self._result.setWordWrap(True)
        self._result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._result)

        self._note = QLabel()
        self._note.setStyleSheet("color: gray; font-size: 8pt;")
        self._note.setWordWrap(True)
        root.addWidget(self._note)

        self._params_group = QGroupBox("Assumptions — edit these; they are NOT saved to kernel")
        self._params_form = QFormLayout(self._params_group)
        self._params_form.setContentsMargins(8, 8, 8, 8)
        self._params_form.setSpacing(6)
        root.addWidget(self._params_group)

        btn_row = QHBoxLayout()
        reset = QPushButton("Reset assumptions")
        reset.setToolTip("Restore every assumed parameter to its default value.")
        reset.clicked.connect(self._reset)
        btn_row.addWidget(reset)
        btn_row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btn_row.addWidget(close)
        root.addLayout(btn_row)

    def _boxed(self, caption, root):
        """A small gray caption above a bordered, word-wrapping monospace line."""
        cap = QLabel(caption)
        cap.setStyleSheet("color: gray; font-size: 8pt; font-weight: bold;")
        root.addWidget(cap)
        lbl = QLabel()
        lbl.setStyleSheet(
            "font-family: monospace; font-size: 9pt; padding: 5px;"
            "background: palette(base); border: 1px solid palette(mid); border-radius: 3px;")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(lbl)
        return lbl

    # -------------------------------------------------- targeting a field
    def show_for(self, field):
        """(Re)point this popup at ``field`` of the current tab and show it."""
        self._disconnect_field()
        self._field = field
        self._formula_key = field.get("formula")
        self.setWindowTitle("f(x)  " + field.get("label", field["name"]))
        # Rebuild param editors for exactly the params this formula uses.
        out = fs.compute(self._formula_key, self._current_value(), self._current_entry())
        self._build_param_editors(out["params"] if out else ())
        # Recompute live when the field's own value changes, or the selected entry changes.
        spin = self._field_spin()
        if spin is not None and hasattr(spin, "valueChanged"):
            spin.valueChanged.connect(self._recompute)
            self._field_conn = spin
        self._recompute()
        self.show()
        # Grow to fit the (variable) content height so the assumptions box is never clipped.
        self.adjustSize()
        self.resize(max(self.width(), 500), self.sizeHint().height())
        self.raise_()
        self.activateWindow()

    def _build_param_editors(self, param_keys):
        while self._params_form.rowCount():
            self._params_form.removeRow(0)
        self._param_spins = {}
        if not param_keys:
            self._params_group.setVisible(False)
            return
        self._params_group.setVisible(True)
        for pk in param_keys:
            label, default, lo, hi, help_text = fs.PARAM_DEFS[pk]
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(fs.PARAM_VALUES[pk])
            spin.setToolTip(help_text)
            spin.setMinimumWidth(90)
            spin.valueChanged.connect(lambda v, k=pk: self._on_param(k, v))
            lab = QLabel(label)
            lab.setToolTip(help_text)
            self._params_form.addRow(lab, spin)
            self._param_spins[pk] = spin

    # -------------------------------------------------- live update
    def _on_param(self, key, value):
        fs.PARAM_VALUES[key] = value
        self._recompute()

    def _reset(self):
        fs.reset_params()
        for pk, spin in self._param_spins.items():
            spin.blockSignals(True)
            spin.setValue(fs.PARAM_VALUES[pk])
            spin.blockSignals(False)
        self._recompute()

    def _current_entry(self):
        idx = getattr(self._tab, "_current_index", -1)
        entries = getattr(self._tab, "_entries", [])
        if 0 <= idx < len(entries):
            return entries[idx]
        return None

    def _field_spin(self):
        rec = self._tab._field_widgets.get(self._field["name"]) if self._field else None
        return rec[2] if rec else None

    def _current_value(self):
        spin = self._field_spin()
        if spin is not None and hasattr(spin, "value"):
            return spin.value()
        entry = self._current_entry()
        if entry is not None:
            try:
                return entry.get(self._field["name"])
            except Exception:
                pass
        return 0

    def _recompute(self, *_):
        out = fs.compute(self._formula_key, self._current_value(), self._current_entry())
        if not out:
            return
        self._title.setText(out["title"])
        self._set_math(self._symbolic, out.get("latex"), out["symbolic"])
        self._set_math(self._substituted, out.get("latex_sub"), out["substituted"])
        self._result.setText(out["result"])
        note = out.get("note")
        self._note.setText(note or "")
        self._note.setVisible(bool(note))

    def _set_math(self, label, latex, text_fallback):
        """Show ``latex`` as a typeset image if matplotlib is available and it parses; otherwise
        fall back to the plain-text formula. Keeps the plain text as the tooltip either way."""
        pix = None
        if latex:
            color = self.palette().color(QPalette.ColorRole.WindowText).name()
            pix = flx.render(latex, color=color, pt=13)
        if pix is not None:
            label.setPixmap(pix)
            label.setToolTip(text_fallback)
        else:
            label.setPixmap(QPixmap())          # clear any stale image
            label.setText(text_fallback)
            label.setToolTip("")

    # -------------------------------------------------- cleanup
    def _disconnect_field(self):
        if self._field_conn is not None:
            try:
                self._field_conn.valueChanged.disconnect(self._recompute)
            except (TypeError, RuntimeError):
                pass
            self._field_conn = None

    def closeEvent(self, event):
        self._disconnect_field()
        super().closeEvent(event)
