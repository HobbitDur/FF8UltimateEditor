"""The f(x) window of an EXP field: the level formula, its two kernel.bin parameters and the curve,
live with the EXP being edited. Rendered like SolomonRing's formula popup (SolomonRing.formula_latex)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QDialog, QGroupBox, QLabel, QVBoxLayout

from FF8GameData.kernellevels import MAX_LEVEL
from SolomonRing import formula_latex as flx

FORMULA_LATEX = (r"Exp(n) = 10\cdot A\cdot n + \left\lfloor\frac{B\cdot n^2}{256}\right\rfloor"
                 r"\quad\Rightarrow\quad level\ n+1\ at\ Exp(n)")
FORMULA_TEXT = "Level n+1 is reached at Exp(n) = 10 × A × n + B × n² / 256 EXP (integer division), up to level 100"

# Where each kind of curve lives in kernel.bin, and how SolomonRing names its two bytes.
SOURCES = {
    "gf": ("Junctionable GFs section, entry of this GF: byte 24 (A) and byte 25 (B)",
           "SolomonRing: Junctionable GFs, \"GF level modifier 1\" (A) and \"GF level modifier 2\" (B)",
           "GetGFLevelFromExperience"),
    "character": ("Characters section, entry {index} (the character's comId, the \"Model\" field): "
                  "byte 6 (A) and byte 7 (B)",
                  "SolomonRing: Characters, EXP box, \"c1\" (A) and \"c2\" (B)",
                  "Stat_ComputeLevelFromExp"),
}


class LevelFormulaPopup(QDialog):
    """Non-modal tool window, re-targeted by show_for() and refreshed by refresh()."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(500)
        self.setSizeGripEnabled(True)
        self._source = None  # callable -> (kind, owner name, kernel index, LevelCurve or None, exp)

        root = QVBoxLayout(self)
        root.setSpacing(6)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.title.setWordWrap(True)
        root.addWidget(self.title)
        self.formula = self._boxed("Formula", root)
        self.parameters = self._boxed("Parameters, from kernel.bin", root)
        self.substituted = self._boxed("With the current EXP", root)
        self.chart = QLabel()
        self.chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.chart)

    @staticmethod
    def _boxed(title, root):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        root.addWidget(box)
        return label

    def show_for(self, source):
        self._source = source
        self.show()
        self.refresh()
        self.adjustSize()  # the formula and chart pixmaps are only known now
        self.raise_()

    def refresh(self):
        """Redraw from the source, while the window is open (the EXP fields call it on every edit)."""
        if self._source is None or not self.isVisible():
            return
        kind, owner, index, curve, exp = self._source()
        location, solomonring, function = SOURCES[kind]
        color = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.title.setText(f"Level from EXP: {owner}")
        pixmap = flx.render(FORMULA_LATEX, color=color, pt=13)
        if pixmap is not None:
            self.formula.setPixmap(pixmap)
            self.formula.setToolTip(FORMULA_TEXT)
        else:
            self.formula.setText(FORMULA_TEXT)
        where = location.format(index=index)
        if curve is None:
            self.parameters.setText(f"A (linear) and B (quadratic) are two bytes of kernel.bin: {where}.\n"
                                    f"No kernel.bin is open: open one with the toolbar's \"Import complementary\" "
                                    f"button.\n{solomonring}.")
            self.substituted.setText("No level without the two parameters.")
            self.chart.clear()
            self.chart.setVisible(False)
            return
        self.parameters.setText(f"A (linear) = {curve.linear}, B (quadratic) = {curve.quadratic}\n"
                                f"Read from the opened kernel.bin: {where}. The game computes the level the "
                                f"same way ({function}).\nEdit them in {solomonring}.")
        level, past = curve.level_from_exp(exp)
        start = curve.exp_to_leave(level - 1)
        if level < MAX_LEVEL:
            following = curve.exp_to_leave(level)
            self.substituted.setText(
                f"EXP {exp:,}: level {level} starts at Exp({level - 1}) = {start:,}, level {level + 1} at "
                f"Exp({level}) = 10 × {curve.linear} × {level} + {curve.quadratic} × {level}² / 256 = {following:,}\n"
                f"→ Lvl {level} + {past:,} xp ({following - exp:,} to the next level)")
        else:
            self.substituted.setText(f"EXP {exp:,} ≥ Exp(99) = {start:,}\n→ Lvl 100, the maximum")
        points = [(n + 1, curve.exp_to_leave(n)) for n in range(MAX_LEVEL)]
        chart = flx.plot(points, x_label="Level", y_label="Total EXP", marker=(level, start), fg=color)
        self.chart.setVisible(chart is not None)
        if chart is not None:
            self.chart.setPixmap(chart)
