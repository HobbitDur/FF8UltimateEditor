import os

from PyQt6.QtCore import QSize, QSettings, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog,
                             QHBoxLayout, QMessageBox, QLabel, QComboBox, QDialog,
                             QTextBrowser, QSplitter)

from FF8GameData.dat.commandanalyser import CurrentIfType
from FF8GameData.dat.sequencecodec import generate_help_html
from FF8GameData.dat.sequencebake import bake_sequence, background_sequence_id_set
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritSeq.seqwidget import SeqWidget, VIEW_HEX
from Ifrit.IfritSeq.seqcommandwidget import build_op_code_model
from Ifrit.IfritSeq.seqpreviewpanel import SequencePreviewPanel
from Common.deferredcall import defer


class IfritSeqWidget(QWidget):
    # A structural change to the sequences (a whole sequence added) that touches the widgets but not
    # the model until save. The host pane connects this to its edit detection so it dirties the file
    # and records an undo step - a plain "Add sequence" button click otherwise reaches neither.
    data_edited = pyqtSignal()
    ADD_LINE_SELECTOR_ITEMS = ["Condition", "Command"]
    # Same pattern as IfritAI's expert modes, minus Raw-code which has no meaning here:
    # every view shows this sequence's translation next to it except the raw hex one.
    EXPERT_SELECTOR_ITEMS = ["User-friendly", "Hex-editor", "IfritSeq-code"]
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, ifrit_manager: IfritManager, icon_path="Resources",
                 file_registry=None):
        QWidget.__init__(self)
        self.current_if_index = 0
        self.file_loaded = ""
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        self.ifrit_manager = ifrit_manager
        self.current_if_type = CurrentIfType.NONE
        self.file_dialog = QFileDialog()
        self.settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))
        self.__op_code_model = None  # built on first load, shared by every command row
        # Main window

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        self.info_button.setIconSize(QSize(30, 30))
        self.info_button.setFixedSize(40, 40)
        self.info_button.setToolTip("Show toolmaker info")
        self.info_button.clicked.connect(self.__show_info)

        expert_tooltip_text = "The expert mode allow you to change the display: <br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[0] + ":</u></b> One line per command " \
            "(op code names, one box per parameter), with the sequence translation<br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[1] + ":</u></b> For modifying directly the hex<br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[2] + ":</u></b> Sequence editor with the " \
            "IfritSeq language (one command per line, translation beside)"
        self.expert_selector_title = QLabel("Expert mode: ")
        self.expert_selector_title.setToolTip(expert_tooltip_text)
        self.expert_selector = QComboBox()
        self.expert_selector.addItems(self.EXPERT_SELECTOR_ITEMS)
        self.expert_selector.setCurrentIndex(
            self.settings.value("ifrit/Seq/expert_selector", defaultValue=0, type=int))
        self.expert_selector.setToolTip(expert_tooltip_text)
        self.expert_selector.activated.connect(self.__change_expert)

        # A standing reference for the IfritSeq-code language: every command it knows,
        # its syntax and what it does, generated straight from the same json + parser
        # logic the IfritSeq-code view itself uses (so it cannot say something the
        # parser would then refuse). Non-modal: it stays open for reference while typing.
        self.code_help_button = QPushButton("Code help")
        self.code_help_button.setToolTip("Reference for the IfritSeq-code language: "
                                         "every command, its syntax and what it does")
        self.code_help_button.clicked.connect(self.__show_code_help)
        self.__code_help_dialog = None

        self.seq_data_widget = []
        self.add_sequence_button = None  # trailing "append a new sequence" button

        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addWidget(self.expert_selector_title)
        self.layout_top.addWidget(self.expert_selector)
        self.layout_top.addWidget(self.code_help_button)
        self.layout_top.addStretch(1)

        self.main_vertical_layout = QVBoxLayout()
        self.main_vertical_layout.setSpacing(10)  # gap between each sequence frame
        self.window_layout.addLayout(self.layout_top)

        # Editor (left) + shared preview panel (right), split - same pattern as the camera
        # tab. ONE panel (one 3D view, one timeline) for the whole file, loaded with
        # whichever sequence's ▶ Preview was clicked, rather than a viewer per sequence.
        # The panel's 3D viewer is created lazily on the first preview, so a file whose
        # sequences are only ever read pays nothing for it.
        self.preview_panel = SequencePreviewPanel(self.ifrit_manager, self.__bake_sequence,
                                                  file_registry=file_registry)
        self.preview_panel.hide()   # appears on the first ▶ Preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.layout_main = QVBoxLayout()
        self.window_layout.addWidget(self.splitter)
        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.main_vertical_layout)
        self.layout_main.addStretch(1)

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Nihil</b> for beta testing and finding unknown values.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.<br/>"
                            f"For more info on the command, you can check the <a href=\"https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/battle/battle-scripts/\">wiki</a>.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__ifrit_icon)
        message_box.setWindowTitle("IfritAI - Info")
        message_box.exec()

    def __show_code_help(self):
        if self.__code_help_dialog is None:
            self.__code_help_dialog = QDialog(self)
            self.__code_help_dialog.setWindowTitle("IfritSeq-code reference")
            self.__code_help_dialog.resize(900, 700)
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setHtml(generate_help_html(self.ifrit_manager.game_data))
            layout = QVBoxLayout()
            layout.addWidget(browser)
            self.__code_help_dialog.setLayout(layout)
        # Non-modal (show(), not exec()): the dialog stays open and usable side by side
        # with the code you are typing, instead of blocking the rest of the window.
        self.__code_help_dialog.show()
        self.__code_help_dialog.raise_()
        self.__code_help_dialog.activateWindow()

    def load_file(self, path: str):
        self.__load_file(path)

    def save_file(self):
        self.__save_file()

    def __save_file(self):
        self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = []
        for index, seq_widget in enumerate(self.seq_data_widget):
            self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'].append(
                {"id": seq_widget.getId(), "data": seq_widget.getByteData()})

    def __load_file(self, file_to_load: str = ""):
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat")[0]
        if file_to_load:
            self.file_loaded = file_to_load
            # No clear_lines() here: __setup_section_data reuses the sequence widgets whose id+bytes
            # are unchanged and rebuilds only the ones that differ. On the first load there are none
            # to reuse (so it builds everything), but on an undo/redo reload only the one edited
            # sequence is rebuilt - the others (dozens of heavy command rows each) are kept as-is.
            self.__setup_section_data()
        # A (re)load may follow an undo that also changed the MODEL sections (mesh,
        # animations): make the preview reload the mesh on its next use, and re-run the
        # bake if a sequence is being previewed right now.
        self.preview_panel.invalidate_model()
        self.preview_panel.refresh()

    def clear_lines(self):
        self.seq_data_widget = []
        self.add_sequence_button = None
        while self.main_vertical_layout.count():
            item = self.main_vertical_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def __setup_section_data(self):
        if self.__op_code_model is None and self.ifrit_manager.game_data is not None:
            self.__op_code_model = build_op_code_model(self.ifrit_manager.game_data)
        view = self.expert_selector.currentIndex()
        # Show the sequences by id, not by their byte order in the file: the id is what
        # the game (and the user) refers to, so gaps - the sequences a monster does not
        # have - line up in order and their "Add" placeholder sits in the right place.
        seq_list = sorted(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'],
                          key=lambda seq: seq['id'])
        # Reuse the sequence widgets whose id + bytes are unchanged and rebuild only the ones that
        # differ, so an undo/redo (which touches a single sequence) rebuilds just that one row block
        # instead of every sequence - each of which is dozens of heavy command widgets. Keeping the
        # untouched widgets also keeps the scroll position stable. A first load has nothing to reuse,
        # so it builds everything exactly as before.
        vbar = self.scroll_area.verticalScrollBar()
        scroll_pos = vbar.value()
        pool = {}
        for w in self.seq_data_widget:
            pool.setdefault(w.getId(), []).append(w)
        if self.add_sequence_button is not None:
            self.add_sequence_button.setParent(None)
            self.add_sequence_button.deleteLater()
            self.add_sequence_button = None
        old_widgets = self.seq_data_widget
        for w in old_widgets:                       # detach all; kept ones are re-added in order
            self.main_vertical_layout.removeWidget(w)
        self.seq_data_widget = []
        for seq_data in seq_list:
            seq_id = seq_data['id']
            reuse = None
            candidates = pool.get(seq_id)
            if candidates:
                for w in candidates:
                    if bytes(w.getByteData()) == bytes(seq_data['data']):
                        reuse = w
                        candidates.remove(w)
                        break
            if reuse is not None:
                # Keep the widget as-is: it already shows the current view (a reload never changes
                # the expert view - __change_expert updates the widgets directly). Do NOT call
                # set_view here; it would rebuild all of this sequence's command rows, the exact
                # cost the reuse is meant to avoid.
                self.seq_data_widget.append(reuse)
                self.main_vertical_layout.addWidget(reuse)
            else:
                self.__add_seq_widget(seq_data['data'], seq_id, view)
        kept = {id(w) for w in self.seq_data_widget}
        for w in old_widgets:                       # drop the replaced / removed ones
            if id(w) not in kept:
                w.setParent(None)
                w.deleteLater()
        self.__add_trailing_button()
        # Restore the scroll after the layout has settled (the rebuilt sequence may have a different
        # height), so an undo leaves the user looking at the same spot instead of jumping.
        # Tied to this widget: a call arriving after it is gone would touch a deleted C++ scroll
        # bar, which aborts the process rather than reporting (see Common/deferredcall).
        defer(self, lambda: vbar.setValue(min(scroll_pos, vbar.maximum())))

    # ------------------------------------------------------------------ preview
    # Running a sequence needs the whole file, not one sequence: A7 and A2 chain into the
    # others, and how long a command takes comes from the animation section. SeqWidget has
    # neither, so the bake is built here and handed to the preview panel as a callable.
    MAX_TIMELINE_FRAME = 600  # ~20 seconds of battle; an idle stance never ends

    def __bake_sequence(self, seq_id):
        """Run sequence `seq_id` with the bytes currently ON SCREEN (the edit being typed,
        not the last save) and return the BakeResult the preview panel plays."""
        game_data = self.ifrit_manager.game_data
        sequence_by_id = {widget.getId(): bytes(widget.getByteData())
                          for widget in self.seq_data_widget}
        animation_data = getattr(self.ifrit_manager.enemy, 'animation_data', None)
        frame_count = [len(animation.frames)
                       for animation in getattr(animation_data, 'animations', [])]
        background_id_set = background_sequence_id_set(game_data, sequence_by_id)
        return bake_sequence(game_data, sequence_by_id, seq_id, frame_count,
                             # The preview's placement (a scene.out encounter) when one
                             # is picked, else the documented defaults.
                             context=self.preview_panel.battle_context,
                             max_frame=self.MAX_TIMELINE_FRAME,
                             as_background=seq_id in background_id_set)

    def __add_seq_widget(self, data, seq_id, view):
        seq_widget = SeqWidget(data, seq_id, self.ifrit_manager.enemy.entity_type,
                               game_data=self.ifrit_manager.game_data,
                               op_code_model=self.__op_code_model,
                               preview_enabled=True)
        seq_widget.preview_requested.connect(self.preview_panel.preview)
        seq_widget.set_view(view)
        # Write straight to the in-memory monster on every edit (connected AFTER construction so the
        # initial populate doesn't count). The code view already compiles live into the hex source
        # of truth, so getByteData() is always current.
        seq_widget.data_changed.connect(self.__on_seq_data_changed)
        self.seq_data_widget.append(seq_widget)
        self.main_vertical_layout.addWidget(seq_widget)
        return seq_widget

    def __on_seq_data_changed(self):
        """A sequence changed: fold all sequences into enemy.seq_animation_data now (not deferred to
        Save) and tell the host pane so it dirties the file and records an undo step."""
        self.__save_file()
        self.data_edited.emit()
        # The preview follows the bytes on screen: re-run the bake for the sequence being
        # previewed (refresh() is a no-op while the panel is closed).
        self.preview_panel.refresh()

    def __add_trailing_button(self):
        next_id = max((widget.getId() for widget in self.seq_data_widget), default=0) + 1
        self.add_sequence_button = QPushButton(f"+ Add sequence {next_id}")
        self.add_sequence_button.setToolTip("Append a brand-new sequence with the next "
                                            "id, extending the section")
        self.add_sequence_button.clicked.connect(self.__append_sequence)
        self.main_vertical_layout.addWidget(self.add_sequence_button)

    def __append_sequence(self):
        next_id = max((widget.getId() for widget in self.seq_data_widget), default=0) + 1
        view = self.expert_selector.currentIndex()
        # Drop the trailing button, add the new (already-present) sequence, put the button
        # back below it with the next id.
        self.add_sequence_button.setParent(None)
        self.add_sequence_button.deleteLater()
        self.add_sequence_button = None
        self.__add_seq_widget(bytearray(SeqWidget.DEFAULT_NEW_SEQUENCE), next_id, view)
        self.__add_trailing_button()
        self.__on_seq_data_changed()   # sync the new sequence into enemy + dirty + undo-snapshot

    def __change_expert(self):
        expert_chosen = self.expert_selector.currentIndex()
        self.settings.setValue("ifrit/Seq/expert_selector", expert_chosen)
        for seq_widget in self.seq_data_widget:
            seq_widget.set_view(expert_chosen)

