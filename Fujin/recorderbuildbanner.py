"""The line across Fujin's top while its effect recorder builds in the background (Fujin.recorderbuild): what is built, how far, how
long, and that Play goes on by itself when it ends; when the build failed, why, with its log and a retry. Hidden the rest of the time."""
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout

from Fujin.recorderbuild import recorder_build

BUILDING_STYLE = "RecorderBuildBanner { background: #33507a; } QLabel { color: white; }"
FAILED_STYLE = "RecorderBuildBanner { background: #8a2f2f; } QLabel { color: white; }"


class RecorderBuildBanner(QFrame):
    def __init__(self):
        super().__init__()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setMaximumWidth(220)
        self.bar.setTextVisible(False)
        self.log_button = QPushButton("Show log")
        self.log_button.clicked.connect(self.show_log)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(lambda: recorder_build().start())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.log_button)
        layout.addWidget(self.retry_button)
        self.started_at = 0.0
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.refresh)
        build = recorder_build()
        build.changed.connect(self._changed)
        build.progress.connect(self.refresh)
        self._changed()

    def _changed(self):
        building = recorder_build().building
        if building and not self.clock.isActive():
            self.started_at = time.monotonic()
            self.clock.start()
        elif not building:
            self.clock.stop()
        self.refresh()

    def refresh(self):
        build = recorder_build()
        self.setVisible(build.building or bool(build.error))
        self.bar.setVisible(build.building)
        self.log_button.setVisible(bool(build.error))
        self.retry_button.setVisible(bool(build.error))
        if build.building:
            self.setStyleSheet(BUILDING_STYLE)
            minutes, seconds = divmod(int(time.monotonic() - self.started_at), 60)
            count = f": {build.done} of {build.total} files" if build.total else ""
            self.text.setText(f"Building {build.stage}{count}, {minutes} min {seconds:02d} s. Play and the part tabs go on by "
                              "themselves when it is ready.")
            self.bar.setRange(0, build.total)                # (0: moving, no count yet)
            self.bar.setValue(min(build.done, build.total))
        elif build.error:
            self.setStyleSheet(FAILED_STYLE)
            self.text.setText(f"Fujin's effect recorder is not ready, {build.error}.")

    def show_log(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Effect recorder build log")
        dialog.resize(900, 500)
        log = QPlainTextEdit(recorder_build().output)
        log.setReadOnly(True)
        QVBoxLayout(dialog).addWidget(log)
        dialog.exec()
