"""Where Cure's ring goes around its target, drawn from what the port measured in the recording
(FFNx FX_NOTE, the recorder's M lines: the target's radius and height, the ring's radius, rise per
step and start height, the motes' circle and drops) and the tab's values: a side view (the target,
the ring's helix from its start to where it ends, its top) and a top view (the target, the ring's
circle and the one it would take without its cap, the motes' circle, the first tick's steps), and
the numbers under them. Choreography's Ring and Motes tabs show it under the preview (Geometry)."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

TARGET, RING, MOTES, CAP = QColor(150, 150, 160), QColor(190, 90, 255), QColor(60, 190, 150), QColor(235, 170, 60)


def geometry(recording, values):
    """{name: value} of the measured sizes (None when the recording has none) and what follows from
    them: where the ring ends, the radius it would take without its cap."""
    if recording is None:
        return None
    first = lambda name: (recording.notes(name) or [(None, None)])[0][1]
    radius, height = first("target radius"), first("target height")
    if radius is None or height is None:
        return None
    ring_ticks = [index for index, tick in enumerate(recording.ticks) if 1 in tick.parts]
    found = {"target radius": radius, "target height": height, "ring radius": first("ring radius"),
             "rise": first("ring rise per step") or 0, "start": first("ring start above feet") or 0,
             "ring ticks": len(ring_ticks), "per tick": values.get("ring.steps.per_tick", 4),
             "angle": values.get("ring.steps.angle", 0x80)}
    if "ring.radius.num" in values and values.get("ring.radius.den"):
        found["asked"] = radius * values["ring.radius.num"] // values["ring.radius.den"]
        found["at most"] = values.get("ring.radius.max")
    motes = [value for _tick, value in recording.notes("mote circle radius")]
    drops = [value for _tick, value in recording.notes("mote drop")]
    found["mote radius"] = max(motes) if motes else None
    found["drops"] = (min(drops), max(drops)) if drops else None
    found["end"] = found["start"] + found["rise"] * found["per tick"] * found["ring ticks"]
    return found


class GeometryView(QWidget):
    """The side and top views and their numbers (see the module)."""

    def __init__(self):
        super().__init__()
        self.found = None
        self.setMinimumHeight(170)
        self.text = QLabel()
        self.text.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(self.text)

    def set_geometry(self, found):
        self.found = found
        if found is None:
            self.text.setText("Record the effect (its part tabs do) with FFNx's effect sources noting sizes "
                              "(FX_NOTE) to see where the ring goes around its target.")
        else:
            f = found
            capped = (f" (asked {f['asked']}: the target's x Times / Divided by, capped by At most {f['at most']})"
                      if f.get("asked") is not None and f["ring radius"] is not None and f["asked"] > f["ring radius"]
                      else "")
            lines = [f"Target: radius {f['target radius']}, height {f['target height']} (game units).",
                     f"Ring: radius {f['ring radius']}{capped}; it starts {f['start']} over the feet and rises "
                     f"{f['rise']} a step, {f['rise'] * f['per tick']} a tick: after its {f['ring ticks']} ticks it is "
                     f"{f['end']} over the feet ({f['end'] - f['target height']:+} from the target's top)."]
            if f["mote radius"] is not None:
                drops = f" born {f['drops'][0]}-{f['drops'][1]} below the ring" if f["drops"] else ""
                lines.append(f"Motes: on a circle of radius {f['mote radius']}{drops}.")
            self.text.setText(" ".join(lines))
        self.update()

    def paintEvent(self, event):
        f = self.found
        if f is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(4, 4, self.width() - 8, max(40, self.height() - self.text.height() - 12))
        side = QRectF(area.left(), area.top(), area.width() * 0.6 - 6, area.height())
        top = QRectF(side.right() + 12, area.top(), area.width() - side.width() - 12, area.height())
        reach = max(f["target radius"], f["ring radius"] or 0, f.get("asked") or 0, f["mote radius"] or 0, 1)
        tall = max(f["target height"], f["end"], 1)
        # side view: x = across, y = up; feet at the bottom
        scale = min(side.width() / (2.4 * reach), side.height() / (1.1 * tall))
        middle, ground = side.center().x(), side.bottom() - 4
        at = lambda x, y: QPointF(middle + x * scale, ground - y * scale)
        painter.setPen(QPen(QColor(110, 110, 115), 1))
        painter.drawLine(QPointF(side.left(), ground), QPointF(side.right(), ground))
        painter.fillRect(QRectF(at(-f["target radius"], f["target height"]), at(f["target radius"], 0)), QColor(80, 80, 90))
        painter.setPen(QPen(TARGET, 1, Qt.PenStyle.DashLine))
        painter.drawLine(at(-reach * 1.15, f["target height"]), at(reach * 1.15, f["target height"]))
        steps = max(1, f["per tick"] * f["ring ticks"])
        helix = [at((f["ring radius"] or 0) * math.sin(2 * math.pi * n * f["angle"] / 4096), f["start"] + n * f["rise"])
                 for n in range(steps + 1)]
        painter.setPen(QPen(RING, 1.5))
        painter.drawPolyline(QPolygonF(helix))
        painter.setPen(QPen(RING, 1, Qt.PenStyle.DotLine))
        painter.drawLine(at(-reach * 1.15, f["end"]), at(reach * 1.15, f["end"]))
        painter.setPen(QColor(200, 200, 205))
        painter.drawText(at(-reach * 1.15, f["target height"]) + QPointF(2, -3), "target top")
        painter.drawText(at(-reach * 1.15, f["end"]) + QPointF(2, -3), "ring ends")
        # top view: the circles around the target's middle
        scale = min(top.width(), top.height()) / (2.3 * reach)
        centre = top.center()
        circle = lambda radius: QRectF(centre.x() - radius * scale, centre.y() - radius * scale,
                                       2 * radius * scale, 2 * radius * scale)
        painter.setBrush(QColor(80, 80, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle(f["target radius"]))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if f.get("asked") and f["ring radius"] and f["asked"] > f["ring radius"]:
            painter.setPen(QPen(CAP, 1, Qt.PenStyle.DotLine))
            painter.drawEllipse(circle(f["asked"]))
        if f["mote radius"]:
            painter.setPen(QPen(MOTES, 1, Qt.PenStyle.DashLine))
            painter.drawEllipse(circle(f["mote radius"]))
        if f["ring radius"]:
            painter.setPen(QPen(RING, 1.5))
            painter.drawEllipse(circle(f["ring radius"]))
            painter.setBrush(RING)
            for n in range(f["per tick"]):          # the first tick's steps, the ring drawn at the last
                angle = 2 * math.pi * n * f["angle"] / 4096
                point = QPointF(centre.x() + math.sin(angle) * f["ring radius"] * scale,
                                centre.y() - math.cos(angle) * f["ring radius"] * scale)
                painter.drawEllipse(point, 4 if n == f["per tick"] - 1 else 2.5, 4 if n == f["per tick"] - 1 else 2.5)
        painter.end()
