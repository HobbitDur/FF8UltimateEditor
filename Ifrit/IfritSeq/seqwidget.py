from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit,
                             QPushButton, QGroupBox, QSizePolicy, QToolButton)

from FF8GameData.monsterdata import EntityType
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from FF8GameData.dat.sequencecodec import sequence_to_code, code_to_sequence, SeqCodeError
from FF8GameData.dat.sequencecommand import SequenceCommand, read_sequence, write_sequence
from FF8GameData.dat.sequencevm import as_sequence_vm
from Ifrit.IfritSeq.seqcommandwidget import SeqCommandRow


class AutoHeightTextEdit(QTextEdit):
    """A text edit that grows to show every line instead of scrolling.

    The code and translation panes of a sequence must display in full - a modder reads
    the whole translation at a glance and edits the whole code, so a scrollbar that hides
    part of it defeats the point. The widget wraps long lines and keeps its height equal
    to the document height (no scrollbar ever appears).

    QTextEdit (not QPlainTextEdit) on purpose: its document().size() is in pixels, so the
    height can be computed exactly; QPlainTextEdit reports it in lines.

    content_height_changed fires whenever the natural height was (re)computed - on text
    edits and on resize (wrapping changes with width) - so a caller can keep two of these
    the same height (e.g. the hex box and the translation beside it) without polling.
    """

    content_height_changed = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self._fit_to_content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_to_content()  # width changed -> lines re-wrap -> height changes

    def natural_height(self) -> int:
        """The height this widget needs to show its whole (wrapped) content, without
        applying it - lets a caller equalize several of these to the same height."""
        viewport_width = self.viewport().width()
        if viewport_width <= 0:
            return self.fontMetrics().height() + 2 * self.frameWidth() + 8
        document = self.document()
        document.setTextWidth(viewport_width)
        content = document.size().height()
        return int(max(content, self.fontMetrics().height())) + 2 * self.frameWidth() + 8

    def _fit_to_content(self):
        height = self.natural_height()
        if self.height() != height:
            self.setFixedHeight(height)
        self.content_height_changed.emit()


# The three views, same order as the selector in IfritSeqWidget
VIEW_USER_FRIENDLY = 0
VIEW_HEX = 1
VIEW_CODE = 2


class OpIdChangedEmitter(QObject):
    op_id_signal = pyqtSignal()


class SeqWidget(QWidget):
    """One animation sequence, shown as one of three views of the same bytes.

    - User-friendly: one row per command (op code dropdown, one box per parameter,
      live description), plus this sequence's translation text beside it.
    - Hex-editor: the raw bytes, exactly the old IfritSeq behaviour.
    - IfritSeq-code: the sequence as text (sequencecodec language), translation beside
      it; the code is parsed as it is typed and errors point at the line.

    Whatever the view, the hex box stays the internal source of truth (getByteData()
    reads it, as it always did) and every view is rebuilt from it through the one
    sequence walker, so the views cannot drift from each other or from the file.
    """
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MIN_OP_ID = 0
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0
    SEQ_DESCRIPTION_CHARA = [
        "None",
        "Basic Standing Animation loop",
        "Exhausted - low hp animation loop",
        "Death loop",
        "Damage Taken into a low hp phase",
        "Damage Taken Normal",
        "Damage Taken Crit",
        "Nothing happens",
        "Appearance (like at the start of the battle)",
        "Staying in 'rdy to attack standing'",
        "Draw command fail animation",
        "Magic animation",
        "Basic Standing Animation",
        "Attack - normal",
        "Guardian Force Summoning (Disappear)",
        "Item Use",
        "Runaway 1",
        "Runaway 2 - Escaped disappear",
        "Victory Animation",
        "Changing into 'rdy to attack standing'",
        "Guardian Force Summoning (Re-appear)",
        "Limit break 1 (Normal)",
        "Draw/Defend Phase again?",
        "Changing into Defend/Draw Phase",
        "Kamikaze Command - Running to the enemy",
        "Attack - Darkside",
        "Runaway 2? (same as 1) - maybe used at Edea Disc 1 fight? (Rinoa / Irvine appearance)",
        "Defend/Draw stock",
        "Limit break 2 (Special, e.g. Squall/Zell Blue aura)",
        "Defend command standing again",
        "Draw Stock Magic"
    ]

    # Character sequences live in the weapon file, or in a weapon-less character body.
    # Their whole list is action-specific (SEQ_DESCRIPTION_CHARA), because the engine
    # drives a precise sequence per action/status (FF8_EN.exe analyse_animation_status
    # @0x509C10, only reached for com_id < 0x10).
    _CHARACTER_ENTITY_TYPE = (EntityType.WEAPON, EntityType.WEAPON_NO_ANIM,
                              EntityType.CHARACTER_NO_WEAPON)

    # Monsters (com_id >= 0x10) only have two sequences the engine references by fixed
    # index; everything else is driven by their AI script. {id: (label, why)}.
    #  - seq 8 is queued as every entity's entrance at battle start
    #    (initAnimationSequenceAtStartBattle @0x5027D0);
    #  - seq 1 is the idle base sequence the engine falls back to when nothing is queued
    #    (same function sets basedAnimSeq = 1; analyse_animation_status returns it for
    #    monsters). Unlike characters, monsters do NOT get the status-driven map.
    SEQ_DESCRIPTION_MONSTER = {
        1: ("Idle", "Idle stance. The engine uses sequence 1 as the base sequence a "
                    "monster falls back to when its AI queues nothing else "
                    "(FF8_EN.exe initAnimationSequenceAtStartBattle @0x5027D0)."),
        8: ("Entrance", "Played once when the monster appears at battle start: the "
                        "engine queues sequence 8 for every entity "
                        "(FF8_EN.exe initAnimationSequenceAtStartBattle @0x5027D0)."),
    }

    # The two sequences the engine references by fixed index for EVERY entity, so a file
    # must keep them: seq 1 (idle base sequence) and seq 8 (entrance queued at battle
    # start) - FF8_EN.exe initAnimationSequenceAtStartBattle @0x5027D0. These cannot be
    # removed; the rest can (a removed sequence becomes an empty offset-0 slot).
    MANDATORY_SEQ_ID = (1, 8)

    # What an "Add sequence" creates: a single end-of-sequence opcode. It is the minimal
    # valid, harmless sequence (A2 resets rotation and hands over to the next queued
    # sequence); the user then fills it in.
    DEFAULT_NEW_SEQUENCE = bytearray([0xA2])

    @classmethod
    def is_mandatory(cls, seq_id):
        return seq_id in cls.MANDATORY_SEQ_ID

    @classmethod
    def sequence_meaning(cls, entity_type, seq_id):
        """(label, tooltip) the engine gives this sequence id, or ('', '') if none.

        Characters name every sequence (action-specific); monsters only name the two the
        engine mandates (idle + entrance), the rest being free for their AI script."""
        if entity_type in cls._CHARACTER_ENTITY_TYPE:
            if 0 <= seq_id < len(cls.SEQ_DESCRIPTION_CHARA):
                label = cls.SEQ_DESCRIPTION_CHARA[seq_id]
                return (label if label != "None" else "", "")
            return "", ""
        if entity_type == EntityType.MONSTER:
            label, why = cls.SEQ_DESCRIPTION_MONSTER.get(seq_id, ("", ""))
            return (f"{label} (mandatory)", why) if label else ("", "")
        return "", ""

    data_changed = pyqtSignal()

    def __init__(self, seq: bytearray, id: int, entity_type: EntityType = EntityType.MONSTER,
                 game_data=None, op_code_model=None, *, vm=None, title: str = None,
                 removable: bool = None, can_be_absent: bool = True,
                 collapsible: bool = True):
        QWidget.__init__(self)
        # Parameters
        self._sequence = seq
        self._id = id
        self.entity_type = entity_type
        # The VM decides op code families/animation range; either passed explicitly (the
        # camera editor passes the camera VM) or derived from game_data (the entity VM).
        if vm is not None:
            self.vm = vm
        elif game_data is not None:
            self.vm = as_sequence_vm(game_data)
        else:
            self.vm = None
        self.op_code_model = op_code_model
        # A camera section holds a single always-present, non-removable sequence; the entity
        # editor holds a list where any non-mandatory sequence can be removed or be absent.
        self._title_override = title
        self._can_be_absent = can_be_absent
        self._removable_override = removable
        self._collapsible = collapsible
        self._syncing = False
        self._view = VIEW_HEX
        self._equalizing_height = False

        # signal
        self.op_id_changed_signal_emitter = OpIdChangedEmitter()

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 4)
        self.setLayout(self.main_layout)

        # Everything about this sequence lives in its own frame: a file has dozens of
        # sequences one under the other, and the id is what the rest of the game refers
        # to (a monster's AI plays "sequence 13"), so it belongs in the frame title. The
        # engine-defined meaning, when there is one, is appended so a mandatory sequence
        # (idle, entrance) is obvious at a glance.
        if self._title_override is not None:
            title_text, title_tooltip = self._title_override, ""
        else:
            meaning, title_tooltip = self.sequence_meaning(entity_type, id)
            title_text = f"Seq ID {id} - {meaning}" if meaning else f"Seq ID {id}"

        # A multi-sequence list (the entity editor) gets a small collapse arrow beside a
        # title label, so a file's many sequences can be folded away to focus on one - a
        # checkbox reads as enable/disable, not collapse, so it is not reused here even
        # though it would be just as compact. A single always-present section (the camera
        # one, collapsible=False) has nothing to collapse and keeps the plain native title.
        self.collapse_button = None
        self.title_label = None
        self.__title_row_layout = None
        if self._collapsible:
            self.group_box = QGroupBox()
            self.collapse_button = QToolButton()
            self.collapse_button.setArrowType(Qt.ArrowType.DownArrow)
            self.collapse_button.setAutoRaise(True)
            self.collapse_button.setFixedSize(16, 16)
            self.collapse_button.setToolTip("Collapse this sequence (hide its content, "
                                            "keep the title)")
            self.collapse_button.clicked.connect(self.__toggle_collapsed)
            self.title_label = QLabel(title_text)
            self.title_label.setStyleSheet("font-weight: bold;")
            if title_tooltip:
                self.title_label.setToolTip(title_tooltip)
            self.__title_row_layout = QHBoxLayout()
            self.__title_row_layout.setContentsMargins(2, 2, 2, 0)
            self.__title_row_layout.setSpacing(4)
            self.__title_row_layout.addWidget(self.collapse_button)
            self.__title_row_layout.addWidget(self.title_label)
            self.__title_row_layout.addStretch(1)
        else:
            self.group_box = QGroupBox(title_text)
            if title_tooltip:
                self.group_box.setToolTip(title_tooltip)
        self.group_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Internal source of truth + the Hex-editor view. Auto-height like the other two
        # panes (no scrollbar), and kept the same height as the translation beside it -
        # see __equalize_hex_translation_height.
        self.sequence_text_widget = AutoHeightTextEdit()
        self.sequence_text_widget.setPlainText(self._sequence.hex(" "))
        self.sequence_text_widget.textChanged.connect(self.__hex_edited)

        # This sequence's translation, shown in full beside every view (no scrollbar)
        self.translation_widget = AutoHeightTextEdit()
        self.translation_widget.setReadOnly(True)
        self.translation_widget.setToolTip("What this sequence does, command by command")

        # The editor (hex or code) and the translation are shown side by side; keep them
        # the same height (whichever needs more) instead of one looking arbitrarily short.
        self.sequence_text_widget.content_height_changed.connect(
            self.__equalize_editor_translation_height)
        self.translation_widget.content_height_changed.connect(
            self.__equalize_editor_translation_height)

        # User-friendly view: command rows
        self.command_row_list = []
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        rows_holder_layout = QVBoxLayout()
        rows_holder_layout.setContentsMargins(0, 0, 0, 0)
        rows_holder_layout.addLayout(self.rows_layout)
        self.add_first_button = QPushButton("+ Add a first command")
        self.add_first_button.clicked.connect(self.__add_first_command)
        self.add_first_button.hide()
        rows_holder_layout.addWidget(self.add_first_button)
        self.rows_container.setLayout(rows_holder_layout)
        self.rows_container.hide()

        # IfritSeq-code view, shown in full (no scrollbar)
        self.code_widget = AutoHeightTextEdit()
        self.code_widget.setToolTip(
            "This sequence in IfritSeq-code: one command per line, func_name(arg, ...).\n"
            "# starts a comment. The text is parsed as you type; errors show below.")
        self.code_widget.textChanged.connect(self.__code_edited)
        self.code_widget.content_height_changed.connect(
            self.__equalize_editor_translation_height)
        self.code_widget.hide()
        self.code_error_label = QLabel()
        self.code_error_label.setStyleSheet("color: red")
        self.code_error_label.hide()

        # Left of the frame: whichever editor the current view uses. Right: what this
        # sequence does. Each pane says what it is, so the two texts of the code view
        # cannot be mistaken for one another.
        self.editor_title = QLabel()
        self.editor_title.setStyleSheet("color: gray")
        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(self.editor_title)
        editor_layout.addWidget(self.rows_container)
        editor_layout.addWidget(self.code_widget)
        editor_layout.addWidget(self.code_error_label)
        editor_layout.addWidget(self.sequence_text_widget)
        # A trailing stretch pins the content to the top: the two columns rarely have the
        # same height (a short editor next to a long translation), and without it the
        # shorter one is spread down the frame instead of starting at the top.
        editor_layout.addStretch(1)

        self.translation_title = QLabel("Translation")
        self.translation_title.setStyleSheet("color: gray")
        self.translation_layout = QVBoxLayout()
        self.translation_layout.setContentsMargins(0, 0, 0, 0)
        self.translation_layout.addWidget(self.translation_title)
        self.translation_layout.addWidget(self.translation_widget)
        self.translation_layout.addStretch(1)
        self.translation_title.hide()
        self.translation_widget.hide()

        content_layout = QHBoxLayout()
        content_layout.addLayout(editor_layout, stretch=3)
        content_layout.addLayout(self.translation_layout, stretch=2)

        # Remove: turn an existing sequence back into a "not present" slot. Its id is kept
        # (only the data is dropped) so every other sequence keeps its number. Absent for
        # the mandatory idle/entrance the engine needs by fixed index. Lives right above
        # the editor/translation split, so it disappears together with the content
        # instead of needing its own always-present header row.
        self._mandatory = self.is_mandatory(id)
        # A sequence is removable unless it is mandatory, or unless the caller forces it
        # (the camera section's single sequence is never removable).
        self._removable = (not self._mandatory if self._removable_override is None
                           else self._removable_override)
        self.remove_button = QPushButton("Remove sequence")
        self.remove_button.setToolTip("Delete this sequence. Its slot (id) stays so the "
                                      "other sequences keep their number; it just becomes "
                                      "empty (the game skips it).")
        self.remove_button.clicked.connect(self.__remove_sequence)
        self.remove_row_layout = remove_row_layout = QHBoxLayout()
        remove_row_layout.setContentsMargins(0, 0, 0, 0)
        remove_row_layout.addWidget(self.remove_button)
        remove_row_layout.addStretch(1)

        content_outer_layout = QVBoxLayout()
        content_outer_layout.setContentsMargins(0, 0, 0, 0)
        content_outer_layout.addLayout(remove_row_layout)
        content_outer_layout.addLayout(content_layout)
        # The editor + translation of an existing sequence, hidden when the sequence is
        # not present (offset 0) so an empty slot does not look like an empty editor.
        self.content_widget = QWidget()
        self.content_widget.setContentsMargins(0, 0, 0, 0)
        self.content_widget.setLayout(content_outer_layout)

        self._collapsed = False

        # Not-present state: an empty sequence (offset 0) the game skips. Instead of an
        # empty editor, say so and offer to create a minimal valid sequence in this slot.
        self.absent_label = QLabel("This sequence is not present (the game skips it).")
        self.absent_label.setStyleSheet("color: gray")
        self.add_button = QPushButton("Add sequence")
        self.add_button.setToolTip("Create this sequence (a single end-of-sequence "
                                   "command to start from)")
        self.add_button.clicked.connect(self.__add_sequence)
        absent_layout = QHBoxLayout()
        absent_layout.setContentsMargins(0, 0, 0, 0)
        absent_layout.addWidget(self.absent_label)
        absent_layout.addWidget(self.add_button)
        absent_layout.addStretch(1)
        self.absent_widget = QWidget()
        self.absent_widget.setLayout(absent_layout)

        group_layout = QVBoxLayout()
        if self.__title_row_layout is not None:
            group_layout.addLayout(self.__title_row_layout)
        group_layout.addWidget(self.content_widget)
        group_layout.addWidget(self.absent_widget)
        self.group_box.setLayout(group_layout)

        self.main_layout.addWidget(self.group_box)
        self.__refresh_translation()
        self.set_view(self._view)  # coherent titles/visibility before anyone switches
        self.__apply_presence()    # existing/empty -> editor or add-placeholder

    def __str__(self):
        return str(self._sequence)

    def __repr__(self):
        return self.__str__()

    def getByteData(self):
        return bytearray.fromhex(self.sequence_text_widget.toPlainText())

    def getId(self):
        return self._id

    def get_displayed_title(self) -> str:
        """The title text as shown to the user, whichever of the two title renderings
        (custom collapsible row, or the group box's own plain title) is in use."""
        return self.title_label.text() if self.title_label is not None else self.group_box.title()

    # -------------------------------------------------------------- presence
    def is_present(self) -> bool:
        """A sequence exists when it has data; an empty one is an offset-0 slot the game
        skips. getByteData() stays the single source of truth, empty included."""
        return bool(self.getByteData())

    def __apply_presence(self):
        # Collapsed: only the titled frame (with its collapse arrow) stays; everything
        # else is hidden so the sequence can be folded away.
        if self._collapsed:
            self.content_widget.setVisible(False)
            self.absent_widget.setVisible(False)
            self.remove_button.setVisible(False)
            return
        # A section whose sequence cannot be absent (the camera one) always shows the editor,
        # never the "not present / Add" placeholder.
        present = self.is_present() or not self._can_be_absent
        self.content_widget.setVisible(present)
        self.absent_widget.setVisible(not present)
        # Mandatory idle/entrance are never removable; a not-present sequence has the Add
        # button in its place instead.
        self.remove_button.setVisible(present and self._removable)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        if self.collapse_button is not None:
            self.collapse_button.setArrowType(Qt.ArrowType.RightArrow if collapsed
                                              else Qt.ArrowType.DownArrow)
            self.collapse_button.setToolTip("Expand this sequence" if collapsed
                                            else "Collapse this sequence (hide its "
                                                 "content, keep the title)")
        self.__apply_presence()

    def __toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def __add_sequence(self):
        self._syncing = True
        self.sequence_text_widget.setPlainText(self.DEFAULT_NEW_SEQUENCE.hex(" "))
        self._syncing = False
        self.__apply_presence()
        self.set_view(self._view)  # rebuild the active view from the new bytes
        self.__refresh_translation()
        self.data_changed.emit()

    def __remove_sequence(self):
        self._syncing = True
        self.sequence_text_widget.setPlainText("")  # empty data -> offset 0 on save
        self._syncing = False
        self.__apply_presence()
        self.__refresh_translation()
        self.data_changed.emit()

    # ----------------------------------------------------------------- views
    def set_view(self, view: int):
        """Show one of VIEW_USER_FRIENDLY / VIEW_HEX / VIEW_CODE."""
        if self.vm is None and view != VIEW_HEX:
            view = VIEW_HEX  # nothing but hex can be built without the game data
        self._view = view
        if view == VIEW_USER_FRIENDLY:
            self.__rebuild_rows()
        elif view == VIEW_CODE:
            self.__rebuild_code()
        self.rows_container.setVisible(view == VIEW_USER_FRIENDLY)
        self.code_widget.setVisible(view == VIEW_CODE)
        self.code_error_label.setVisible(view == VIEW_CODE and
                                         bool(self.code_error_label.text()))
        self.sequence_text_widget.setVisible(view == VIEW_HEX)
        # Every view keeps the translation beside it: raw hex least of all is readable
        # on its own, and the command rows/code still gain from the full decoded text.
        self.translation_widget.setVisible(True)
        self.translation_title.setVisible(True)
        self.editor_title.setText({VIEW_USER_FRIENDLY: "Commands",
                                   VIEW_HEX: "Hex",
                                   VIEW_CODE: "IfritSeq-code"}[view])
        if view in (VIEW_HEX, VIEW_CODE):
            self.__equalize_editor_translation_height()

    def get_view(self) -> int:
        return self._view

    def __equalize_editor_translation_height(self):
        """Hex and Code views: match the editor's height to the translation beside it (or
        vice versa), so neither looks arbitrarily short next to the other. Left alone in
        the User-friendly view: the command rows are not a simple auto-height text box, so
        matching heights there would just pad the shorter one with blank space."""
        if self._equalizing_height or self._view not in (VIEW_HEX, VIEW_CODE):
            return
        editor = self.sequence_text_widget if self._view == VIEW_HEX else self.code_widget
        self._equalizing_height = True
        try:
            target = max(editor.natural_height(), self.translation_widget.natural_height())
            if editor.height() != target:
                editor.setFixedHeight(target)
            if self.translation_widget.height() != target:
                self.translation_widget.setFixedHeight(target)
        finally:
            self._equalizing_height = False

    def __refresh_translation(self):
        if self.vm is None:
            return
        try:
            data = self.getByteData()
        except ValueError:
            self.translation_widget.setPlainText("(invalid hex)")
            return
        text = SequenceAnalyser(game_data=self.vm, model_anim_data=None,
                                sequence=data).get_text()
        self.translation_widget.setPlainText(text)

    def __bytes_changed_from(self, source_view: int, data: bytearray):
        """One view produced new bytes: push them to the truth and the other views."""
        self._syncing = True
        self.sequence_text_widget.setPlainText(data.hex(" "))
        self._syncing = False
        if source_view != VIEW_CODE and self._view == VIEW_CODE:
            self.__rebuild_code()
        self.__refresh_translation()
        self.data_changed.emit()

    # ------------------------------------------------------------------ rows
    def __rebuild_rows(self):
        for row in self.command_row_list:
            row.setParent(None)
            row.deleteLater()
        self.command_row_list = []
        try:
            data = self.getByteData()
        except ValueError:
            return  # invalid hex: keep the previous rows away rather than lie
        for command in read_sequence(self.vm, bytes(data)):
            self.__append_row(command)
        self.add_first_button.setVisible(not self.command_row_list)

    def __append_row(self, command):
        row = SeqCommandRow(self.vm, command, op_code_model=self.op_code_model)
        row.data_changed.connect(self.__rows_edited)
        row.insert_requested.connect(self.__insert_after)
        row.remove_requested.connect(self.__remove_row)
        self.rows_layout.addWidget(row)
        self.command_row_list.append(row)
        return row

    def __rows_edited(self):
        """A row changed: rewrite the bytes from the rows, through the one walker."""
        data = write_sequence([row.command for row in self.command_row_list])
        for row in self.command_row_list:
            row.refresh_address()
        self.__bytes_changed_from(VIEW_USER_FRIENDLY, data)

    def __insert_after(self, row):
        index = self.command_row_list.index(row)
        command = SequenceCommand(self.vm, 0xA1)  # Yield: the most harmless default
        new_row = SeqCommandRow(self.vm, command, op_code_model=self.op_code_model)
        new_row.data_changed.connect(self.__rows_edited)
        new_row.insert_requested.connect(self.__insert_after)
        new_row.remove_requested.connect(self.__remove_row)
        self.rows_layout.insertWidget(index + 1, new_row)
        self.command_row_list.insert(index + 1, new_row)
        self.__rows_edited()

    def __remove_row(self, row):
        self.command_row_list.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.__rows_edited()
        self.add_first_button.setVisible(not self.command_row_list)

    def __add_first_command(self):
        self.__append_row(SequenceCommand(self.vm, 0xA1))
        self.add_first_button.hide()
        self.__rows_edited()

    # ------------------------------------------------------------------ code
    def __rebuild_code(self):
        try:
            data = self.getByteData()
        except ValueError:
            return
        self._syncing = True
        self.code_widget.setPlainText(sequence_to_code(self.vm, bytes(data)))
        self._syncing = False
        self.code_error_label.hide()
        self.code_error_label.setText("")

    def __code_edited(self):
        if self._syncing:
            return
        try:
            data = code_to_sequence(self.vm, self.code_widget.toPlainText())
        except SeqCodeError as error:
            self.code_error_label.setText(str(error))
            self.code_error_label.show()
            return
        self.code_error_label.hide()
        self.code_error_label.setText("")
        self.__bytes_changed_from(VIEW_CODE, data)

    # ------------------------------------------------------------------- hex
    def __hex_edited(self):
        if self._syncing:
            return
        if self._view == VIEW_USER_FRIENDLY:
            self.__rebuild_rows()
        elif self._view == VIEW_CODE:
            self.__rebuild_code()
        self.__refresh_translation()
        self.data_changed.emit()
