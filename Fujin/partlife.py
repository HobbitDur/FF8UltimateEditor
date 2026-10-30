"""A part's life, computed from its values the way the port's code runs them: when its pieces are
born (a spawn window with a count per tick, or every N ticks: Cure's motes and glints,
Hypnotize's layouts and sprites) and how one glint grows and shrinks (the shared effect
library's glint, FFNx fx_glint.cpp: tick 0 at size 0, `ticks` ticks growing, `ticks` shrinking,
hidden on the last). Choreography's part tabs show it under the preview (Life)."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

SHOWN_TICKS = 40                    # a window open "forever" (Cure's motes: to 32766) shows this many
WIDTH_COLOUR, HEIGHT_COLOUR = QColor(42, 120, 214), QColor(235, 104, 52)


def births(values):
    """{spawner prefix: [(tick, how many)]} for every spawn window in `values` ({key: value}): a
    "<p>window.first/last" pair with a "<p>count.from[k]/count[k]" schedule (the last step reached
    counts) or a "<p>every" (one every N ticks from the first). Ticks are the spawner's."""
    found = {}
    for key in values:
        if not key.endswith("window.first"):
            continue
        base = key[:-len("window.first")]
        first, last = values[key], values.get(base + "window.last", values[key])
        ticks = range(first, min(last, first + SHOWN_TICKS - 1) + 1)
        if base + "count.from[0]" in values:
            steps = [(values[f"{base}count.from[{k}]"], values[f"{base}count.count[{k}]"]) for k in range(4)
                     if f"{base}count.from[{k}]" in values]
            count = lambda tick: ([n for start, n in steps if tick >= start] or [0])[-1]
            found[base] = [(tick, count(tick)) for tick in ticks]
        elif base + "every" in values and values[base + "every"] > 0:
            every = values[base + "every"]
            found[base] = [(tick, 1 if (tick - first) % every == 0 else 0) for tick in ticks]
    return found


def glint_life(values, prefix="glint.style."):
    """[(tick, width, height, centre rgb, tip rgb)] of one glint's drawn ticks (FFNx fx_glint.cpp
    Effect_Glint_Tick: sizes wrap as 16-bit, colours as bytes), or [] without a glint style."""
    if prefix + "ticks" not in values:
        return []
    get = lambda name: values.get(prefix + name, 0)
    steps = max(1, get("ticks"))
    wrap16 = lambda v: (v + 0x8000) % 0x10000 - 0x8000
    w = h = 0
    centre, tip = [0, 0, 0], [0, 0, 0]
    life = [(0, 0, 0, tuple(centre), tuple(tip))]
    for tick in range(1, 2 * steps):
        sign = 1 if tick <= steps else -1
        w = wrap16(w + sign * (get("grow.w") if sign > 0 else get("shrink.w")))
        h = wrap16(h + sign * (get("grow.h") if sign > 0 else get("shrink.h")))
        centre = [(c + sign * get(f"centre_step[{k}]")) & 0xFF for k, c in enumerate(centre)]
        tip = [(c + sign * get(f"tip_step[{k}]")) & 0xFF for k, c in enumerate(tip)]
        life.append((tick, w, h, tuple(centre), tuple(tip)))
    return life


class _Chart(QWidget):
    MARGIN = 26

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def _plot(self):
        return QRectF(self.MARGIN, 8, max(1, self.width() - self.MARGIN - 8), max(1, self.height() - self.MARGIN - 8))

    def _axes(self, painter, plot, labels):
        painter.setPen(QPen(QColor(120, 120, 120), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        font = QFont(painter.font())
        font.setPointSize(7)
        painter.setFont(font)
        every = max(1, len(labels) // 12)
        for index, label in enumerate(labels):
            if index % every == 0:
                x = plot.left() + (index + 0.5) * plot.width() / max(1, len(labels))
                painter.drawText(QRectF(x - 15, plot.bottom() + 2, 30, 12), Qt.AlignmentFlag.AlignCenter, str(label))


class BirthChart(_Chart):
    """How many pieces a spawner makes per tick: a bar per tick of its window."""

    def __init__(self):
        super().__init__()
        self.rows, self.title = [], ""

    def set_rows(self, rows, title):
        self.rows, self.title = rows, title
        self.setToolTip(title)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        plot = self._plot()
        if not self.rows:
            return
        top = max(1, max(n for _tick, n in self.rows))
        slot = plot.width() / len(self.rows)
        for index, (_tick, n) in enumerate(self.rows):
            height = plot.height() * n / top
            painter.fillRect(QRectF(plot.left() + index * slot + slot * 0.15, plot.bottom() - height, slot * 0.7, height),
                             WIDTH_COLOUR)
            if n and slot > 12:
                painter.drawText(QRectF(plot.left() + index * slot, plot.bottom() - height - 13, slot, 12),
                                 Qt.AlignmentFlag.AlignCenter, str(n))
        self._axes(painter, plot, [tick for tick, _n in self.rows])


class GlintLifeChart(_Chart):
    """One glint's life: its width and height (each as a share of its largest), and its centre and
    tip colours tick by tick in two strips under them."""
    STRIP = 9

    def __init__(self):
        super().__init__()
        self.life = []

    def set_life(self, life):
        self.life = life
        self.update()

    def mouseMoveEvent(self, event):
        plot = self._plot()
        if self.life:
            index = int((event.position().x() - plot.left()) * len(self.life) / plot.width())
            if 0 <= index < len(self.life):
                tick, w, h, centre, tip = self.life[index]
                self.setToolTip(f"its tick {tick}: width {w}, height {h}, centre colour {centre}, tip colour {tip}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        if not self.life:
            return
        lines = plot.adjusted(0, 0, 0, -2 * self.STRIP - 6)
        slot = plot.width() / len(self.life)
        x = lambda index: plot.left() + (index + 0.5) * slot
        for column, colour, dash in ((1, WIDTH_COLOUR, Qt.PenStyle.SolidLine), (2, HEIGHT_COLOUR, Qt.PenStyle.DashLine)):
            top = max(1, max(abs(row[column]) for row in self.life))
            pen = QPen(colour, 2)
            pen.setStyle(dash)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([QPointF(x(i), lines.bottom() - lines.height() * max(0, row[column]) / top)
                                            for i, row in enumerate(self.life)]))
        for strip, column in ((0, 3), (1, 4)):
            y = lines.bottom() + 4 + strip * (self.STRIP + 2)
            for i, row in enumerate(self.life):
                painter.fillRect(QRectF(plot.left() + i * slot, y, slot - 1, self.STRIP), QColor(*row[column]))
        self._axes(painter, plot, [row[0] for row in self.life])


class PartLife(QWidget):
    """Under a part's preview (Life): when its pieces are born, and a glint's life - both from the
    tab's values, redrawn as they change. has_content(): whether the part has any of them."""

    def __init__(self, values, part_names=None):
        super().__init__()
        self.births = BirthChart()
        self.births_title = QLabel()
        self.glint = GlintLifeChart()
        self.glint_title = QLabel("One glint's life, tick by tick: width (solid) and height (dashed), each as a share "
                                  "of its largest; under them its centre and tip colours")
        self.glint_title.setWordWrap(True)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(self.glint_title)
        left.addWidget(self.glint, 1)
        right.addWidget(self.births_title)
        right.addWidget(self.births, 1)
        self.glint_column, self.births_column = QWidget(), QWidget()
        self.glint_column.setLayout(left)
        self.births_column.setLayout(right)
        layout = QHBoxLayout(self)
        layout.addWidget(self.glint_column, 3)
        layout.addWidget(self.births_column, 2)
        self.set_values(values)

    def has_content(self):
        return not self.glint_column.isHidden() or not self.births_column.isHidden()

    def set_values(self, values):
        life = glint_life(values)
        self.glint.set_life(life)
        self.glint_column.setHidden(not life)
        spawns = births(values)
        rows = next(iter(spawns.values()), [])
        total = sum(n for _tick, n in rows)
        title = f"Born per spawner tick: {total} in all" + (f" (first {SHOWN_TICKS} ticks)" if len(rows) == SHOWN_TICKS else "")
        self.births.set_rows(rows, title)
        self.births_title.setText(title)
        self.births_column.setHidden(not rows)
