"""The interpolation-curve chooser, shared by every feature that inserts in-between frames.

Both the fps conversion and the manual "interpolate between two frames" ask for it, and both used
to blend linearly with no way to say otherwise. They offer the same curves (see
FF8GameData/dat/interpolation.py) but not the same default: raising the frame rate of a continuous
motion wants a curve that flows through the original poses, while morphing between two poses the
user picked themselves usually wants to ease in and out of them.

The chosen curve also carries its own settings - how many waves a sine makes, how round it is, how
much the spline lets the neighbours pull it - which appear under the combo and change with it.
They come back inside the mode itself (an interpolation.InterpolationMode), so the callers hand it
over exactly as they did when it was a bare string. Leaving them alone gives the curve as it was
before they existed.

Two shapes of the same thing:
  * InterpolationSelector, a labelled combo to drop into a dialog that asks other things too;
  * ask_interpolation_mode(), a standalone popup for a flow that has nothing else to ask.
"""
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                             QFormLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox,
                             QVBoxLayout, QWidget)

from FF8GameData.dat import interpolation

# The preview draws the segment as going from 0 to 1, with the motion carrying on at the same
# speed on either side, so the curves that read their neighbours (the spline) show what they
# actually do inside a moving animation rather than the flattened end-of-animation case.
_PREVIEW_BEFORE = -1.0
_PREVIEW_AFTER = 2.0


def _first_sentence(text: str) -> str:
    """The opening sentence of a parameter description, for the line shown under its spin box."""
    end = text.find(". ")
    return text if end < 0 else text[:end + 1]


class CurvePreview(QWidget):
    """The shape of the chosen curve, drawn from the curve itself.

    Sampled through interpolation.interpolate_value rather than redrawn by hand, so it can never
    disagree with what the frames will get - which is the whole point of showing it: a sine with
    four half-waves or a spline pulled to 1.20 is far easier to judge here than in a number.
    """

    NB_SAMPLE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = interpolation.LINEAR
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("The curve the values follow, from the first pose (bottom line) to the "
                        "second one (top line), across the segment.")

    def set_mode(self, mode):
        self._mode = mode
        self.update()

    def sample_list(self) -> list:
        """The curve as (step, value) pairs, value 0 being the first pose and 1 the second."""
        samples = []
        for index in range(self.NB_SAMPLE + 1):
            step = index / self.NB_SAMPLE
            samples.append((step, interpolation.interpolate_value(
                _PREVIEW_BEFORE, 0.0, 1.0, _PREVIEW_AFTER, step, self._mode)))
        return samples

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        text_color = self.palette().text().color()
        frame_color = QColor(text_color)
        frame_color.setAlpha(70)
        guide_color = QColor(text_color)
        guide_color.setAlpha(110)

        rect = self.rect().adjusted(1, 1, -2, -2)
        painter.setPen(QPen(frame_color, 1))
        painter.drawRoundedRect(rect, 3, 3)

        samples = self.sample_list()
        values = [value for _, value in samples]
        # A curve is allowed to leave the 0..1 band (a spline overshoots, a sine with amplitude
        # over 1 goes past the pose): the view follows it instead of cutting it off.
        low = min(0.0, min(values))
        high = max(1.0, max(values))
        margin = max((high - low) * 0.12, 0.05)
        low -= margin
        high += margin

        left = rect.left() + 8
        right = rect.right() - 8
        top = rect.top() + 6
        bottom = rect.bottom() - 6

        def to_x(step):
            return left + (right - left) * step

        def to_y(value):
            return bottom - (bottom - top) * (value - low) / (high - low)

        # The two poses: everything between the dashed lines stays inside the segment.
        dashed = QPen(guide_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(dashed)
        painter.drawLine(int(left), int(to_y(0.0)), int(right), int(to_y(0.0)))
        painter.drawLine(int(left), int(to_y(1.0)), int(right), int(to_y(1.0)))
        painter.setPen(QPen(guide_color, 1))
        font = painter.font()
        font.setPointSize(max(6, font.pointSize() - 2))
        painter.setFont(font)
        painter.drawText(int(left) - 6, int(to_y(0.0)) + 4, "A")
        painter.drawText(int(left) - 6, int(to_y(1.0)) + 4, "B")

        path = QPainterPath()
        for index, (step, value) in enumerate(samples):
            point = QPointF(to_x(step), to_y(value))
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setPen(QPen(QColor("#4c9be8"), 2))
        painter.drawPath(path)


class InterpolationSelector(QWidget):
    """A combo of every interpolation curve, with the description of the selected one, its own
    settings, and a preview of the shape they produce."""

    mode_changed = pyqtSignal()

    def __init__(self, parent=None, default_mode: str = interpolation.LINEAR,
                 label: str = "Interpolation between the frames:", show_preview: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(label))
        self._combo = QComboBox()
        for mode in interpolation.ALL_MODES:
            self._combo.addItem(interpolation.MODE_LABEL[mode], mode)
            self._combo.setItemData(self._combo.count() - 1,
                                    interpolation.MODE_DESCRIPTION[mode], role=3)  # tooltip
        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._combo)

        # The descriptions are what makes the choice meaningful, so one is always on screen
        # rather than hidden in a tooltip the user has to go looking for.
        self._description = QLabel()
        self._description.setWordWrap(True)
        self._description.setStyleSheet("color:#999; font-size:10px;")
        layout.addWidget(self._description)

        # Each curve keeps the settings it was given while another one is selected, so trying a
        # few of them out does not throw away the values already dialled in.
        self._value_dict = {mode: {} for mode in interpolation.ALL_MODES}
        self._widget_dict = {}
        self._loading = False

        self._parameter_form = QFormLayout()
        self._parameter_form.setContentsMargins(0, 0, 0, 0)
        self._parameter_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._parameter_widget = QWidget()
        self._parameter_widget.setLayout(self._parameter_form)
        layout.addWidget(self._parameter_widget)

        self._reset_button = QPushButton("Reset the settings of this curve")
        self._reset_button.setToolTip("Back to the plain curve: the values it had before any of "
                                      "these settings existed.")
        self._reset_button.clicked.connect(self.reset_parameters)
        reset_layout = QHBoxLayout()
        reset_layout.setContentsMargins(0, 0, 0, 0)
        reset_layout.addStretch(1)
        reset_layout.addWidget(self._reset_button)
        layout.addLayout(reset_layout)

        self._preview = CurvePreview()
        self._preview.setVisible(show_preview)
        layout.addWidget(self._preview)

        # Settings can send the curve somewhere else than the second pose (a sine coming back, an
        # amplitude sailing past it). Nothing wrong with that - it is how one range does a whole
        # up-and-down - but the two keyframes never move, so it is worth saying out loud.
        self._landing_warning = QLabel()
        self._landing_warning.setWordWrap(True)
        self._landing_warning.setStyleSheet("color:#c8a24a; font-size:10px;")
        self._landing_warning.setVisible(False)
        layout.addWidget(self._landing_warning)

        self.set_mode(default_mode)

    # ── Result ────────────────────────────────────────────────────────

    def get_mode(self) -> interpolation.InterpolationMode:
        """The chosen curve, carrying its settings. Compares equal to the plain mode string, so a
        caller that only forwards it needs to know nothing about them."""
        name = self._combo.currentData()
        return interpolation.InterpolationMode(name, self._value_dict.get(name, {}))

    def get_mode_name(self) -> str:
        """Just the curve, without its settings."""
        return str(self._combo.currentData())

    def set_mode(self, mode):
        """Select `mode`, taking its settings along when it carries any."""
        index = self._combo.findData(str(mode))
        self._value_dict.setdefault(str(mode), {}).update(
            {key: value for key, value in (getattr(mode, "parameters", None) or {}).items()})
        self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._on_mode_changed()

    def reset_parameters(self):
        """Give the selected curve its default settings back."""
        self._value_dict[self.get_mode_name()] = {}
        self._on_mode_changed()

    # ── Internals ─────────────────────────────────────────────────────

    def _on_mode_changed(self, _=None):
        self._description.setText(interpolation.MODE_DESCRIPTION.get(self.get_mode_name(), ""))
        self._build_parameter_widgets()
        self._refresh_preview()
        self.mode_changed.emit()

    def _build_parameter_widgets(self):
        """Rebuild the settings rows for the selected curve: its own (none at all for the linear
        one) followed by the ones offered whatever the curve is, the 3D arc for the rotations."""
        self._loading = True
        while self._parameter_form.count():
            item = self._parameter_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._widget_dict = {}

        name = self.get_mode_name()
        spec_list = interpolation.parameters_for(name)
        self._parameter_widget.setVisible(bool(spec_list))
        self._reset_button.setEnabled(bool(spec_list))
        if not spec_list:
            self._loading = False
            return

        value_dict = interpolation.parameters_of(self.get_mode())
        for spec in spec_list:
            widget = self._make_parameter_widget(spec, value_dict[spec.key])
            widget.setToolTip(spec.description)
            label = QLabel(spec.label)
            label.setToolTip(spec.description)
            self._parameter_form.addRow(label, widget)
            # Same rule as the curve descriptions: what the setting does is on screen, not buried
            # in a tooltip. Only the first sentence though - five settings' worth of full text
            # would push the popup past the bottom of the screen - the rest stays in the tooltip.
            hint = QLabel(_first_sentence(spec.description))
            hint.setWordWrap(True)
            hint.setToolTip(spec.description)
            hint.setStyleSheet("color:#999; font-size:10px;")
            self._parameter_form.addRow(hint)
            self._widget_dict[spec.key] = widget
        self._loading = False

    def _make_parameter_widget(self, spec, value):
        if spec.kind == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.toggled.connect(self._on_parameter_changed)
            return widget
        if spec.kind == "int":
            widget = QSpinBox()
            widget.setRange(int(spec.minimum), int(spec.maximum))
            widget.setSingleStep(max(1, int(spec.step)))
            widget.setValue(int(value))
        else:
            widget = QDoubleSpinBox()
            widget.setDecimals(spec.decimals)
            widget.setRange(float(spec.minimum), float(spec.maximum))
            widget.setSingleStep(float(spec.step))
            widget.setValue(float(value))
        widget.valueChanged.connect(self._on_parameter_changed)
        return widget

    def _on_parameter_changed(self, _=None):
        if self._loading:
            return
        name = self.get_mode_name()
        values = {}
        for spec in interpolation.parameters_for(name):
            widget = self._widget_dict.get(spec.key)
            if widget is None:
                continue
            values[spec.key] = (widget.isChecked() if spec.kind == "bool" else widget.value())
        self._value_dict[name] = values
        self._refresh_preview()
        self.mode_changed.emit()

    def _refresh_preview(self):
        mode = self.get_mode()
        self._preview.set_mode(mode)
        self._refresh_landing_warning(mode)

    def _refresh_landing_warning(self, mode):
        """Say it when the settings send the end of the segment somewhere else than the second
        pose. Hold is left out: not blending at all is what it is for."""
        if str(mode) == interpolation.HOLD:
            self._landing_warning.setText("")
            self._landing_warning.setVisible(False)
            return
        landing = interpolation.landing_ratio(mode)
        if abs(landing - 1.0) < 0.001:
            self._landing_warning.setText("")
            self._landing_warning.setVisible(False)
            return
        if abs(landing) < 0.001:
            where = "comes back to the first pose"
        elif landing > 1.0:
            where = "goes past the second pose"
        else:
            where = "stops short of the second pose"
        self._landing_warning.setText(
            f"With these settings the curve {where} at the end of the range. The two frames you "
            f"pick keep their own values, so the motion jumps there unless that is what you are "
            f"after (a wave coming back down is).")
        self._landing_warning.setVisible(True)


def ask_interpolation_mode(parent, title: str, default_mode: str = interpolation.LINEAR,
                           intro: str = ""):
    """Popup asking only for the curve. Returns the chosen mode, or None if the user cancels."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    if intro:
        intro_label = QLabel(intro)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

    selector = InterpolationSelector(dialog, default_mode)
    layout.addWidget(selector)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return selector.get_mode()
