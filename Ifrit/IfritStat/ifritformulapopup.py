"""Popup: view & experiment with a monster stat's per-level formula.

Opened by the small "ƒ(x)" button next to each stat row in IfritStatWidget's
Stats tab. Lets the user pick an arbitrary level and see the formula evaluated
live as the underlying stat bytes are edited — mirrors SolomonRing's f(x)
popup (SolomonRing/formula_popup.py), but standalone: Ifrit's stat tab isn't
built on a generic field registry, so it can't reuse FormulaPopup directly.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QSpinBox, QPushButton,
)

from SolomonRing import formula_latex as flx

_DEFAULT_LEVEL = 20

# LaTeX form of each stat's per-level curve, keyed the same way as StatCurvePlot._stat_value.
# Every multiplication is spelled out with \times so substituted numbers never read as one
# concatenated digit string (e.g. "1000" next to "4" looking like "10004").
_LATEX = {
    'hp': r"HP=\lfloor b_0 \times (\frac{L^2}{20}+L)\rfloor+10 \times b_1+100 \times b_2 \times L+1000 \times b_3",
    'str': r"S=\lfloor\frac{L \times b_0}{40}\rfloor+\lfloor\frac{L}{4 \times b_1}\rfloor+\lfloor\frac{b_2}{4}\rfloor+\lfloor\frac{L^2}{8 \times b_3}\rfloor",
    'mag': r"S=\lfloor\frac{L \times b_0}{40}\rfloor+\lfloor\frac{L}{4 \times b_1}\rfloor+\lfloor\frac{b_2}{4}\rfloor+\lfloor\frac{L^2}{8 \times b_3}\rfloor",
    'vit': r"S=L \times b_0+\lfloor\frac{L}{b_1}\rfloor+b_2-\lfloor\frac{L}{b_3}\rfloor",
    'spr': r"S=L \times b_0+\lfloor\frac{L}{b_1}\rfloor+b_2-\lfloor\frac{L}{b_3}\rfloor",
    'spd': r"S=L \times b_0+\lfloor\frac{L}{b_1}\rfloor+b_2-\lfloor\frac{L}{b_3}\rfloor",
    'eva': r"S=L \times b_0+\lfloor\frac{L}{b_1}\rfloor+b_2-\lfloor\frac{L}{b_3}\rfloor",
}


def _plain_formula(stat_name):
    if stat_name == 'hp':
        return "HP = floor(b0 × (L × L / 20 + L)) + 10 × b1 + b2 × 100 × L + 1000 × b3"
    if stat_name in ('str', 'mag'):
        return "S = floor(L × b0 / 40) + floor(L / (4 × b1)) + floor(b2 / 4) + floor(L × L / (8 × b3))"
    return "S = L × b0 + floor(L / b1) + b2 - floor(L / b3)"


def _substitute(text, b, level):
    """Replace the b0..b3 and L tokens in a formula string with concrete numbers."""
    for i in (0, 1, 2, 3):
        text = text.replace(f"b_{i}", str(b[i])).replace(f"b{i}", str(b[i]))
    return text.replace("L", str(level))


class IfritFormulaPopup(QDialog):
    """Non-modal tool window for one stat at a time; opening another stat re-targets it."""

    def __init__(self, parent, stat_widget):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(460)
        self.setSizeGripEnabled(True)
        self._stat_widget = stat_widget
        self._stat_name = None
        self._conns = []

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        root.addWidget(self._title)

        self._symbolic = self._boxed("Formula", root)
        self._substituted = self._boxed("With the current bytes", root)

        cap = QLabel("Result")
        cap.setStyleSheet("color: gray; font-size: 8pt; font-weight: bold;")
        root.addWidget(cap)
        self._result = QLabel()
        self._result.setStyleSheet("font-weight: bold; font-size: 12pt; color: palette(highlight);")
        self._result.setWordWrap(True)
        self._result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._result)

        params_group = QGroupBox("Assumption — pick a level to evaluate at")
        params_form = QFormLayout(params_group)
        self._level_spin = QSpinBox()
        self._level_spin.setRange(1, 100)
        self._level_spin.setValue(_DEFAULT_LEVEL)
        self._level_spin.setToolTip("Monster level (1-100) at which to evaluate the stat curve.")
        self._level_spin.valueChanged.connect(self._recompute)
        params_form.addRow("Monster level (1-100)", self._level_spin)
        root.addWidget(params_group)

        btn_row = QHBoxLayout()
        reset = QPushButton("Reset level")
        reset.setToolTip(f"Restore the level to its default ({_DEFAULT_LEVEL}).")
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

    # -------------------------------------------------- targeting a stat
    def show_for(self, stat_name):
        self._disconnect_stat()
        self._stat_name = stat_name
        self.setWindowTitle(f"f(x)  {stat_name.upper()} curve")
        self._title.setText(f"{stat_name.upper()} — value at a chosen level")
        # Recompute live as the 4 byte spins for this stat are edited.
        self._connect_stat()
        self._recompute()
        self.show()
        self.adjustSize()
        self.resize(max(self.width(), 460), self.sizeHint().height())
        self.raise_()
        self.activateWindow()

    def _reset(self):
        self._level_spin.setValue(_DEFAULT_LEVEL)

    def _current_bytes(self):
        spins = self._stat_widget._stat_spins.get(self._stat_name, [])
        values = [sp.value() for sp in spins]
        return values + [0] * max(0, 4 - len(values))

    # -------------------------------------------------- live update
    def _recompute(self, *_):
        if self._stat_name is None:
            return
        from .ifritstatwidget import StatCurvePlot
        b = self._current_bytes()
        level = self._level_spin.value()
        result = StatCurvePlot._stat_value(self._stat_name, b, level)

        latex = _LATEX.get(self._stat_name)
        plain = _plain_formula(self._stat_name)
        self._set_math(self._symbolic, latex, plain)

        latex_sub = _substitute(latex, b, level) if latex else None
        plain_sub = _substitute(plain, b, level)
        self._set_math(self._substituted, latex_sub, plain_sub)

        self._result.setText(f"{self._stat_name.upper()}(L={level}) = {result}")

    def _set_math(self, label, latex, text_fallback):
        """Show ``latex`` as a typeset image if matplotlib is available and it parses;
        otherwise fall back to the plain-text formula. Plain text stays the tooltip either way."""
        pix = None
        if latex:
            color = self.palette().color(QPalette.ColorRole.WindowText).name()
            pix = flx.render(latex, color=color, pt=15, dpr=3.0)
        if pix is not None:
            label.setPixmap(pix)
            label.setToolTip(text_fallback)
        else:
            label.setPixmap(QPixmap())          # clear any stale image
            label.setText(text_fallback)
            label.setToolTip("")

    # -------------------------------------------------- cleanup
    def _connect_stat(self):
        self._disconnect_stat()
        if self._stat_name is None:
            return
        for spin in self._stat_widget._stat_spins.get(self._stat_name, []):
            spin.valueChanged.connect(self._recompute)
            self._conns.append(spin.valueChanged)

    def _disconnect_stat(self):
        for sig in self._conns:
            try:
                sig.disconnect(self._recompute)
            except (TypeError, RuntimeError):
                pass
        self._conns = []

    def closeEvent(self, event):
        self._disconnect_stat()
        super().closeEvent(event)
