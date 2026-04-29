from PyQt6.QtWidgets import QSpinBox
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression


class QSpinHex(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Set a range of acceptable values in decimal form.
        # Internal representation will handle the integers directly.
        self.setRange(0, 0xFF)  # Adjust as needed for your use case.

        # Set a validator for hexadecimal input (must start with 0x)
        hex_regex = QRegularExpression(r"^0x[0-9A-Fa-f]{2,}$")
        self.hex_validator = QRegularExpressionValidator(hex_regex, self)

        # Assign the validator to the internal QLineEdit
        self.lineEdit().setValidator(self.hex_validator)
        self.setKeyboardTracking(False)

    def textFromValue(self, value: int) -> str:
        """Convert the internal integer value to a hexadecimal string."""
        return f"0x{value:02X}"  # Uppercase hexadecimal format with at least 2 digits

    def valueFromText(self, text: str) -> int:
        """Convert the hexadecimal text to an integer value."""
        try:
            if text.startswith("0x"):
                return int(text, 16)
            else:
                return 0  # Default to 0 if input is invalid
        except ValueError:
            return 0

    def validate(self, input_text: str, pos: int):
        """Validate the input text with the custom regex validator."""
        state, _, _ = self.hex_validator.validate(input_text, pos)
        return state, input_text, pos


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

    app = QApplication([])

    window = QWidget()
    layout = QVBoxLayout()

    # Create an instance of QSpinHex
    spin_hex = QSpinHex()
    layout.addWidget(spin_hex)

    window.setLayout(layout)
    window.show()

    app.exec()
