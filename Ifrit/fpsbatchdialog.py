"""Convert the animations of several .dat files to 30 or 60 fps in one go."""
import os
import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QRadioButton, QButtonGroup, QCheckBox, QFileDialog,
                             QDialogButtonBox, QTextEdit, QMessageBox)

from FF8GameData.dat import interpolation
from SmallWidget.interpolationselector import InterpolationSelector


class FpsBatchDialog(QDialog):
    """The frame rate to convert the chosen files to, and how."""

    def __init__(self, parent, file_list: list):
        super().__init__(parent)
        self.setWindowTitle("Convert files to 30/60 FPS")
        # Tall on purpose: the interpolation block below carries the settings of the chosen curve
        # and its preview, which grow and shrink as the curve changes.
        self.resize(600, 720)
        self._file_list = list(file_list)

        layout = QVBoxLayout(self)

        file_label = QLabel(f"{len(self._file_list)} file(s) selected: " +
                            ", ".join(os.path.basename(f) for f in self._file_list[:6]) +
                            (", ..." if len(self._file_list) > 6 else ""))
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

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

        self._interpolation = InterpolationSelector(
            self, interpolation.DEFAULT_FOR_FPS_CONVERSION,
            label="Interpolation of the frames added between the original ones:")
        layout.addWidget(self._interpolation)

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

    # ── Result ────────────────────────────────────────────────────────

    def get_file_list(self) -> list:
        return list(self._file_list)

    def get_target_fps(self) -> int:
        return 30 if self._fps_30.isChecked() else 60

    def get_split_when_too_long(self) -> bool:
        return self._split_check.isChecked()

    def get_interpolation_mode(self) -> str:
        return self._interpolation.get_mode()


def select_battle_model_file_list(parent, folder: str, file_filter: str, is_model_func,
                                  family_func=None) -> list:
    """Ask for the .dat files to convert, in the file explorer.

    Files that are not a monster/character/weapon model are refused (battle.fs holds .dat
    files that are not models at all), and the missing files of a character family are
    offered, since a body and its weapons must be converted together.
    Returns [] when the user cancels or nothing usable is left.
    """
    path_list, _ = QFileDialog.getOpenFileNames(
        parent, "Select the .dat files to convert (Ctrl+A to select them all)", folder,
        f"{file_filter};;All files (*)")
    if not path_list:
        return []

    refused = [p for p in path_list if not is_model_func(p)]
    file_list = [p for p in path_list if is_model_func(p)]
    if refused:
        QMessageBox.warning(
            parent, "Convert files to 30/60 FPS",
            f"{len(refused)} file(s) are not a monster (c0mXXX.dat), a character "
            f"(dXcYYY.dat) or a weapon (dXwYYY.dat), and hold no model animation. They are "
            f"ignored:\n" +
            "\n".join("  " + os.path.basename(p) for p in refused[:12]) +
            ("\n  ..." if len(refused) > 12 else ""))
    if not file_list:
        return []

    # A character is a body + weapons animated by the same animation ids: converting one
    # without the other desynchronises them.
    if family_func:
        selected = {os.path.normcase(f) for f in file_list}
        missing = []
        for file_path in list(file_list):
            for family_file in family_func(file_path):
                if os.path.normcase(str(family_file)) not in selected:
                    missing.append(str(family_file))
                    selected.add(os.path.normcase(str(family_file)))
        if missing:
            answer = QMessageBox.question(
                parent, "Convert files to 30/60 FPS",
                "A character is a body file plus its weapon files, and the game plays the "
                "same animation ids on both. Converting one without the other would leave "
                "the weapon behind while the body moves.\n\n"
                f"Add the {len(missing)} matching file(s)?\n" +
                "\n".join("  " + os.path.basename(f) for f in missing[:12]) +
                ("\n  ..." if len(missing) > 12 else ""),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return []
            if answer == QMessageBox.StandardButton.Yes:
                file_list.extend(missing)
    return sorted(file_list)


class FpsBatchReportDialog(QDialog):
    """What each file got, and why an animation was left alone."""

    def __init__(self, parent, report_list: list, target_fps: int, mode: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"Converted to {target_fps} FPS")
        self.resize(720, 560)
        self._mode = mode
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
        text.setPlainText(self.build_report_text(report_list, target_fps, mode))
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
    def build_report_text(report_list: list, target_fps: int, mode: str = "") -> str:
        line_list = []
        if mode:
            # Saved reports outlive the popup, and a folder converted with a sine at four
            # half-waves is not the same file set as one converted with the plain spline.
            settings = interpolation.describe_parameters(mode)
            line_list.append("Interpolation: "
                             + interpolation.MODE_LABEL.get(str(mode), str(mode))
                             + (f" ({settings})" if settings else ""))
            line_list.append("")
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
            pathlib.Path(path).write_text(
                self.build_report_text(report_list, target_fps, self._mode), encoding="utf-8")
