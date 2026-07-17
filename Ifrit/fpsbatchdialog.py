"""Convert the animations of several .dat files to 30 or 60 fps in one go."""
import os
import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
                             QCheckBox, QFileDialog, QDialogButtonBox, QTextEdit,
                             QProgressDialog, QMessageBox, QLineEdit)


class FpsBatchDialog(QDialog):
    """Pick the .dat files to convert, and the frame rate to convert them to."""

    def __init__(self, parent, folder: str, family_func=None):
        super().__init__(parent)
        self.setWindowTitle("Convert files to 30/60 FPS")
        self.resize(560, 560)
        self._family_func = family_func
        self._folder = folder

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Folder containing the .dat files:"))
        folder_layout = QHBoxLayout()
        self._folder_edit = QLineEdit(folder)
        self._folder_edit.setReadOnly(True)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        folder_layout.addWidget(browse_btn)
        layout.addLayout(folder_layout)

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self._file_list)

        select_layout = QHBoxLayout()
        for text, checked in (("Select all", True), ("Select none", False)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, c=checked: self._set_all_checked(c))
            select_layout.addWidget(btn)
        select_layout.addStretch()
        self._count_label = QLabel("")
        select_layout.addWidget(self._count_label)
        layout.addLayout(select_layout)

        layout.addWidget(QLabel("Convert the animations to:"))
        fps_layout = QHBoxLayout()
        self._fps_group = QButtonGroup(self)
        self._fps_30 = QRadioButton("30 FPS (recommended)")
        self._fps_30.setToolTip("Twice the frames. Every animation of the vanilla game fits, "
                                "except two that are split automatically.")
        self._fps_60 = QRadioButton("60 FPS")
        self._fps_60.setToolTip("Four times the frames. Some animations do not fit the format "
                                "and cannot all be split: the report lists them.")
        self._fps_30.setChecked(True)
        self._fps_group.addButton(self._fps_30)
        self._fps_group.addButton(self._fps_60)
        fps_layout.addWidget(self._fps_30)
        fps_layout.addWidget(self._fps_60)
        fps_layout.addStretch()
        layout.addLayout(fps_layout)

        self._split_check = QCheckBox("Split the animations that are too long for the format")
        self._split_check.setChecked(True)
        self._split_check.setToolTip("An animation too long once converted is cut in parts that "
                                     "the sequences play one after the other, which keeps the\n"
                                     "motion identical. Without this, a file needing it is left "
                                     "untouched.")
        layout.addWidget(self._split_check)

        warning = QLabel("A file is converted whole or not at all: when one of its animations "
                         "cannot make it, the file is left untouched and listed in the report "
                         "(at 60 fps that happens on ~50 monsters, whose idle is too long — "
                         "converting those files to 30 fps works).\n\n"
                         "The selected files are modified in place. Keep a backup of your "
                         "files, and only run this once per file: converting an already "
                         "converted file would interpolate the interpolated frames.")
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#c8a24a;")
        layout.addWidget(warning)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                      QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._fill_file_list(folder)

    # ── File list ─────────────────────────────────────────────────────

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder containing the .dat files",
                                                  self._folder_edit.text())
        if folder:
            self._folder = folder
            self._folder_edit.setText(folder)
            self._fill_file_list(folder)

    def _fill_file_list(self, folder: str):
        self._file_list.clear()
        if not folder or not os.path.isdir(folder):
            self._count_label.setText("no folder")
            return
        for path in sorted(pathlib.Path(folder).glob("*.dat")):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._file_list.addItem(item)
        self._file_list.itemChanged.connect(self._update_count)
        self._update_count()

    def _set_all_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self._file_list.count()):
            self._file_list.item(index).setCheckState(state)
        self._update_count()

    def _update_count(self, *_):
        self._count_label.setText(f"{len(self.get_checked_file_list())} file(s) selected")

    def get_checked_file_list(self) -> list:
        return [self._file_list.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self._file_list.count())
                if self._file_list.item(index).checkState() == Qt.CheckState.Checked]

    # ── Result ────────────────────────────────────────────────────────

    def get_target_fps(self) -> int:
        return 30 if self._fps_30.isChecked() else 60

    def get_split_when_too_long(self) -> bool:
        return self._split_check.isChecked()

    def accept(self):
        file_list = self.get_checked_file_list()
        if not file_list:
            QMessageBox.warning(self, "Convert files to 30/60 FPS", "No file selected.")
            return
        # A character is a body + a weapon animated by the same animation ids: converting
        # one without the other desynchronises them.
        if self._family_func:
            missing = []
            selected = {os.path.normcase(f) for f in file_list}
            for file_path in list(file_list):
                for family_file in self._family_func(file_path):
                    if os.path.normcase(str(family_file)) not in selected:
                        missing.append(str(family_file))
                        selected.add(os.path.normcase(str(family_file)))
            if missing:
                answer = QMessageBox.question(
                    self, "Convert files to 30/60 FPS",
                    "A character is a body file plus its weapon files, and the game plays the "
                    "same animation ids on both. Converting one without the other would leave "
                    "the weapon behind while the body moves.\n\n"
                    f"Add the {len(missing)} matching file(s)?\n" +
                    "\n".join("  " + os.path.basename(f) for f in missing[:12]) +
                    ("\n  ..." if len(missing) > 12 else ""),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel)
                if answer == QMessageBox.StandardButton.Cancel:
                    return
                if answer == QMessageBox.StandardButton.Yes:
                    for index in range(self._file_list.count()):
                        item = self._file_list.item(index)
                        if item.data(Qt.ItemDataRole.UserRole) in missing:
                            item.setCheckState(Qt.CheckState.Checked)
        super().accept()


class FpsBatchReportDialog(QDialog):
    """What each file got, and why an animation was left alone."""

    def __init__(self, parent, report_list: list, target_fps: int):
        super().__init__(parent)
        self.setWindowTitle(f"Converted to {target_fps} FPS")
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        nb_file_done = sum(1 for r in report_list if not r['error'] and r['nb_converted'])
        nb_animation = sum(r['nb_converted'] for r in report_list)
        nb_split = sum(len(r['split_list']) for r in report_list)
        left_alone = [r for r in report_list if r['skipped_list']]
        error_list = [r for r in report_list if r['error']]

        summary = (f"{nb_animation} animation(s) converted to {target_fps} fps in "
                   f"{nb_file_done} file(s).")
        if nb_split:
            summary += f"\n{nb_split} animation(s) were too long and have been split in parts."
        if left_alone:
            summary += (f"\n{len(left_alone)} file(s) were left untouched: one of their "
                        f"animations cannot be converted, and a file where only some "
                        f"animations are converted plays those at the wrong speed.")
            if target_fps == 60:
                summary += ("\nRun the conversion again on those files with 30 FPS: "
                            "they all fit at 30 fps.")
        if error_list:
            summary += f"\n{len(error_list)} file(s) could not be read at all."
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text.setPlainText(self.build_report_text(report_list, target_fps))
        layout.addWidget(text)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        save_btn = QPushButton("Save report...")
        save_btn.clicked.connect(lambda: self._save(report_list, target_fps))
        button_layout.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    @staticmethod
    def build_report_text(report_list: list, target_fps: int) -> str:
        line_list = []
        not_done = [r for r in report_list if r['error'] or r['skipped_list']]
        if not_done:
            line_list.append(f"=== NOT converted, left untouched at 15 fps ===")
            if any(r['skipped_list'] for r in not_done):
                line_list.append("(the whole file is left alone: the engine plays one frame per "
                                 "tick, so an animation still at 15 fps in a converted file "
                                 "would run too fast)")
                if target_fps == 60:
                    line_list.append("(converting these files to 30 FPS instead works: they all "
                                     "fit at 30 fps)")
                line_list.append("")
            for report in not_done:
                title = f"{report['file']}" + (f" ({report['name']})" if report['name'] else "")
                if report['error']:
                    line_list.append(f"{title}: {report['error']}")
                    continue
                line_list.append(f"{title}: {len(report['skipped_list'])} animation(s) cannot be "
                                 f"converted")
                for anim_id, reason in report['skipped_list']:
                    line_list.append(f"    animation {anim_id}: {reason}")
            line_list.append("")

        line_list.append("=== Converted ===")
        for report in report_list:
            if report['error'] or report['skipped_list'] or not report['nb_converted']:
                continue  # untouched files are listed above, not here
            title = f"{report['file']}" + (f" ({report['name']})" if report['name'] else "")
            detail = f"{report['nb_converted']} animation(s)"
            if report['source']:
                detail += f", loops read from {report['source']}"
            line_list.append(f"{title}: {detail}")
            for anim_id, nb_frame, nb_part, new_id_list in report['split_list']:
                line_list.append(f"    animation {anim_id} ({nb_frame} frames) split in "
                                 f"{nb_part} parts: {anim_id}, "
                                 f"{', '.join(str(i) for i in new_id_list)}")
        return "\n".join(line_list)

    def _save(self, report_list, target_fps):
        path, _ = QFileDialog.getSaveFileName(self, "Save report", f"fps_{target_fps}_report.txt",
                                              "Text file (*.txt)")
        if path:
            pathlib.Path(path).write_text(self.build_report_text(report_list, target_fps),
                                          encoding="utf-8")
