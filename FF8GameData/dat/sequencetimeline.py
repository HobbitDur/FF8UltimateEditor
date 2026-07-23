"""A baked sequence, as something to read: what happens, and on which frame.

sequencebake produces one record per battle frame, which is what a 3D preview needs and
exactly what a human does not: a 90 frame sequence is 90 records of which 6 matter. This
module folds that into the rows a reader wants - "these commands ran on frame 45", "frames
1 to 44 played animation 3 and nothing else happened" - and renders them.

The fold is the whole idea: the interpreter already knows the difference between a frame
that ran op codes and a frame that only waited, so the rows fall out of it rather than
being guessed from the bytes. A row is therefore either
  - an EVENT row: one frame, and the commands that ran on it, or
  - a WAIT row: the frames in between, and what they were waiting for.

Background sequences (9A) are dropped by default. They run every single frame, so keeping
them would give every frame commands, turn every row into an event row and bury the
sequence being read under its own wallpaper; the header says one line about them instead.

The HTML renderer lives here rather than in the widget, next to the fold it renders and
away from Qt, so it can be tested - the same reason sequencecodec.generate_help_html does.
"""
from .sequencebake import (STOP_END, STOP_LOOP, STOP_HANG, STOP_ERROR, STOP_MAX_FRAMES,
                           EVENT_ANIMATION, EVENT_SOUND, EVENT_EFFECT, EVENT_TEXT,
                           EVENT_TARGET, EVENT_MODEL, EVENT_FLOW, EVENT_MOVE, EVENT_STATE)

# One colour per kind of thing a command does, so a timeline can be skimmed for "where is
# the sound" without reading it. Mid-tones on purpose: they have to stay legible on the
# light and the dark palette alike, since the app does not fix one.
_COLOUR_BY_KIND = {
    EVENT_ANIMATION: "#7fa650",
    EVENT_SOUND: "#4f8fc0",
    EVENT_EFFECT: "#c07f4f",
    EVENT_TEXT: "#9a7fb0",
    EVENT_TARGET: "#b06a8f",
    EVENT_MODEL: "#4f9f9f",
    EVENT_MOVE: "#8f8f4f",
    EVENT_FLOW: "#808080",
    EVENT_STATE: "#909090",
}

_LABEL_BY_STOP_REASON = {
    STOP_END: "ends here",
    STOP_LOOP: "loops forever",
    STOP_HANG: "the engine HANGS here",
    STOP_ERROR: "stops here",
    STOP_MAX_FRAMES: "still running at the preview limit",
}


class TimelineRow:
    """One line of the timeline: a frame that ran commands, or a stretch that waited."""

    __slots__ = ("first_frame", "last_frame", "command_list", "anim_id", "anim_total",
                 "anim_frame_first", "anim_frame_last", "is_waiting_animation")

    def __init__(self, frame, command_list):
        self.first_frame = frame.index
        self.last_frame = frame.index
        self.command_list = command_list
        self.anim_id = frame.anim_id
        self.anim_total = frame.anim_total
        self.anim_frame_first = frame.anim_frame
        self.anim_frame_last = frame.anim_frame
        self.is_waiting_animation = frame.is_waiting_animation

    def extend(self, frame):
        self.last_frame = frame.index
        self.anim_frame_last = frame.anim_frame

    @property
    def nb_frame(self):
        return self.last_frame - self.first_frame + 1

    @property
    def is_wait(self):
        return not self.command_list

    @property
    def is_repeat(self):
        """The same commands ran on every frame of this row (a per-frame poll)."""
        return bool(self.command_list) and self.nb_frame > 1

    def frame_text(self) -> str:
        if self.first_frame == self.last_frame:
            return str(self.first_frame)
        return f"{self.first_frame}-{self.last_frame}"

    def animation_text(self) -> str:
        """What the model is doing over this row, animation-wise."""
        if self.anim_id is None:
            return ""
        text = f"anim {self.anim_id}"
        if not self.anim_total:
            return text
        if self.anim_frame_first == self.anim_frame_last:
            return text + f" [{self.anim_frame_first}/{self.anim_total}]"
        if self.anim_frame_last < self.anim_frame_first:
            # The animation wrapped inside this row: A0 re-queues it from frame 0 when it
            # ends, so a frame range would read backwards.
            return text + f" [looping, {self.anim_total} frames]"
        return text + f" [{self.anim_frame_first}-{self.anim_frame_last}/{self.anim_total}]"

    def repeat_text(self) -> str:
        """Said once instead of printing the block on every frame. Empty when it ran once."""
        if not self.is_repeat:
            return ""
        return (f"the same {len(self.command_list)} commands ran on each of these "
                f"{self.nb_frame} frames")

    def wait_text(self) -> str:
        """Why nothing ran. Empty on an event row."""
        if not self.is_wait:
            return ""
        if self.is_waiting_animation:
            return f"waiting for the animation ({self.nb_frame} frames)"
        return f"waiting ({self.nb_frame} frames)"

    def __repr__(self):
        return (f"TimelineRow({self.frame_text()}, "
                f"{len(self.command_list)} command, {self.animation_text()})")


def _command_signature(command_list):
    """What identifies "the same commands ran": which commands, from where. None for a
    frame that ran nothing, so a wait row and an event row can never merge."""
    if not command_list:
        return None
    return tuple((command.seq_id, command.address, command.op_code)
                 for command in command_list)


def build_timeline(result, include_background=False) -> list:
    """Fold a BakeResult into TimelineRows.

    Consecutive frames merge into one row when they are the same thing happening: frames
    that ran nothing and are waiting for the same animation, and - just as important -
    frames that ran the SAME commands. A sequence polling a battle flag once a frame until
    it clears (c0m001 sequence 13 does it for 10 frames) is one thing happening, and
    printing its nine op codes ten times over would bury the two frames that differ.
    """
    row_list = []
    open_row = None
    open_signature = None
    for frame in result.frame_list:
        command_list = [command for command in frame.command_list
                        if include_background or not command.is_background]
        signature = _command_signature(command_list)
        if open_row is not None and signature == open_signature and (
                signature is not None  # same commands
                or (open_row.anim_id == frame.anim_id  # or the same wait
                    and open_row.is_waiting_animation == frame.is_waiting_animation)):
            open_row.extend(frame)
            continue
        open_row = TimelineRow(frame, command_list)
        open_signature = signature
        row_list.append(open_row)
    return row_list


def assumption_list(result) -> list:
    """[(what was read, value)] of the battle values the bake had to assume, deduplicated.

    What makes a timeline trustworthy is knowing which of its branches rest on a guess, so
    this is meant to be shown with it, not buried.
    """
    seen = []
    for _frame, _parameter, what, value in result.assumption_list:
        if what == "random value":
            value = "seeded, changes on re-roll"
        if (what, value) not in seen:
            seen.append((what, value))
    return seen


def _escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def format_timeline_html(result, include_background=False) -> str:
    """The timeline as HTML, for a read-only text pane."""
    if not result.frame_list:
        ending = _LABEL_BY_STOP_REASON.get(result.stop_reason, result.stop_reason)
        return (f"<p style='color:#bf616a'>Nothing to show &mdash; {_escape(ending)} "
                f"before the first frame: {_escape(result.stop_detail)}</p>")

    line_list = [f"<p style='margin:0 0 4px 0'><b>{_escape(result.summary())}</b></p>"]
    if result.background_seq_id_list and not include_background:
        named = ", ".join(str(seq_id) for seq_id in result.background_seq_id_list)
        line_list.append(f"<p style='margin:0 0 4px 0;color:gray'>Sequence {named} runs "
                         f"underneath every frame (9A); its commands are not listed.</p>")

    line_list.append("<table cellspacing='0' cellpadding='2' width='100%'>")
    for row in build_timeline(result, include_background):
        is_loop_start = (result.loop_from is not None
                         and row.first_frame <= result.loop_from <= row.last_frame)
        frame_cell = _escape(row.frame_text())
        if is_loop_start:
            frame_cell = f"&#8635; {frame_cell}"  # the frame the sequence comes back to
        line_list.append("<tr>")
        line_list.append(f"<td valign='top' align='right' width='12%' "
                         f"style='color:gray'>{frame_cell}</td>")
        line_list.append(f"<td valign='top' width='22%' style='color:gray'>"
                         f"{_escape(row.animation_text())}</td>")
        if row.is_wait:
            line_list.append(f"<td valign='top' style='color:#909090'>"
                             f"<i>{_escape(row.wait_text())}</i></td>")
        else:
            command_html = []
            if row.is_repeat:
                command_html.append(f"<div style='color:#909090'><i>"
                                    f"{_escape(row.repeat_text())}</i></div>")
            for command in row.command_list:
                colour = _COLOUR_BY_KIND.get(command.kind, "#909090")
                description = _escape(command.description) or "&mdash;"
                command_html.append(
                    f"<div><span style='color:{colour}'>&#9679;</span> "
                    f"<span style='color:gray'>{command.op_code:02X}</span> "
                    f"{description}</div>")
            line_list.append(f"<td valign='top'>{''.join(command_html)}</td>")
        line_list.append("</tr>")
    line_list.append("</table>")

    ending = _LABEL_BY_STOP_REASON.get(result.stop_reason, result.stop_reason)
    colour = "#bf616a" if result.stop_reason in (STOP_HANG, STOP_ERROR) else "gray"
    detail = f" &mdash; {_escape(result.stop_detail)}" if result.stop_detail else ""
    line_list.append(f"<p style='margin:4px 0 0 0;color:{colour}'>After frame "
                     f"{result.frame_list[-1].index}: {_escape(ending)}{detail}</p>")

    assumed = assumption_list(result)
    if assumed:
        text = ", ".join(f"{_escape(what)} = {_escape(value)}" for what, value in assumed)
        line_list.append(f"<p style='margin:4px 0 0 0;color:gray'><i>Assumed from the "
                         f"battle, not from the file: {text}</i></p>")
    return "".join(line_list)
