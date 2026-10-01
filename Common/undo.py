"""Snapshot (memento) based undo/redo, shared by every tool.

A tool does not build reversible command objects for each edit. Instead it hands this stack two
tiny callables:

  * ``capture()``  -> an opaque, self-contained snapshot of the document's saved state (for the
                      FF8 tools this is just the bytes the tool would write to disk).
  * ``restore(s)`` -> put snapshot ``s`` back into the model and refresh the UI.

The stack keeps a ``baseline`` (the current committed state) plus an undo and a redo list of
snapshots. Every real, committed edit calls ``commit()``: the old baseline is pushed onto the undo
list and a fresh snapshot becomes the baseline. ``undo()``/``redo()`` move the baseline between the
lists and call ``restore``. This reuses each tool's existing save-serialize and load-from-model
paths, so almost no per-edit code is needed - the trade-off is memory (bounded by ``depth``) for a
snapshot per step rather than a minimal reverse-delta.

Object identity is preserved across push/pop (snapshots are never copied inside the stack), so a
``saved`` marker can point at the exact baseline that matches what is on disk, letting the tool show
its unsaved-changes ``*`` correctly even after undoing back to the saved state.
"""


class UndoStack:
    def __init__(self, capture, restore, depth=40):
        self._capture = capture       # () -> snapshot
        self._restore = restore       # (snapshot, tag) -> None (applies + refreshes UI)
        self._depth = max(1, depth)
        self._baseline = capture()    # the current committed state
        self._saved = self._baseline  # the state last written to / read from disk
        self._undo = []
        self._redo = []
        # A `tag` travels with each step: an opaque marker (the Ifrit tools use the edited tab's
        # index) identifying WHERE the change happened, so undo/redo can bring that spot back into
        # view and refresh only it. _undo_tags[i] tags the edit that restoring _undo[i] reverts.
        self._undo_tags = []
        self._redo_tags = []

    # ── edit recording ────────────────────────────────────────────────
    def commit(self, tag=None):
        """Record that the document changed since the last commit: the previous baseline becomes
        undoable and the current state becomes the new baseline. `tag` marks where this edit
        happened (see above). A no-op edit (state unchanged) is ignored so a stray trigger does not
        add an empty undo step."""
        new_state = self._capture()
        if new_state == self._baseline:
            return
        self._undo.append(self._baseline)
        self._undo_tags.append(tag)
        if len(self._undo) > self._depth:
            self._undo.pop(0)
            self._undo_tags.pop(0)
        self._redo.clear()
        self._redo_tags.clear()
        self._baseline = new_state

    def mark_saved(self):
        """Call after the document is written to disk: the current baseline is now the on-disk
        state, so is_dirty() reports clean until it changes again."""
        self._saved = self._baseline

    # ── queries ───────────────────────────────────────────────────────
    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def is_dirty(self):
        """Whether the current state differs from the last saved/loaded one (identity, cheap)."""
        return self._baseline is not self._saved

    # ── navigation ────────────────────────────────────────────────────
    def undo(self):
        if not self._undo:
            return False
        tag = self._undo_tags.pop()      # tag of the edit being reverted
        self._redo.append(self._baseline)
        self._redo_tags.append(tag)      # redoing re-applies that same edit
        self._baseline = self._undo.pop()
        self._restore(self._baseline, tag)
        return True

    def redo(self):
        if not self._redo:
            return False
        tag = self._redo_tags.pop()
        self._undo.append(self._baseline)
        self._undo_tags.append(tag)
        self._baseline = self._redo.pop()
        self._restore(self._baseline, tag)
        return True
