"""Widths that show a list's or a combo box's names in full, instead of cutting them."""
from PyQt6.QtWidgets import QComboBox, QListWidget


def fit_list_width(list_widget: QListWidget, minimum=240, maximum=480):
    """Give a list the fixed width that shows its longest item in full (plus the frame and the
    vertical scroll bar), between minimum and maximum. Call it again after the items change."""
    content = list_widget.sizeHintForColumn(0) if list_widget.count() else 0
    chrome = 2 * list_widget.frameWidth() + list_widget.verticalScrollBar().sizeHint().width() + 8
    list_widget.setFixedWidth(max(minimum, min(maximum, content + chrome)))


def fit_combo(combo: QComboBox, min_chars=16):
    """Make a combo box at least min_chars characters wide closed (it may still be stretched by
    its layout), and its drop-down list wide enough for every name. Call fit_combo_popup again
    after the items change."""
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(min_chars)
    fit_combo_popup(combo)


def fit_combo_popup(combo: QComboBox):
    """Widen the drop-down list (not the closed box) to its longest name."""
    view = combo.view()
    if combo.count() == 0:
        view.setMinimumWidth(0)
        return
    chrome = 2 * view.frameWidth() + view.verticalScrollBar().sizeHint().width() + 8
    view.setMinimumWidth(view.sizeHintForColumn(0) + chrome)
