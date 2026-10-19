"""Story explanations checked against the original English field scripts.

Offsets are absolute byte offsets in each .jsm, at POPM_B 266, preceded by
PSHN_L <phase>. Keep references testable without redistributing game scripts.
"""
from dataclasses import dataclass
from html import escape

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox


@dataclass(frozen=True)
class PhaseSource:
    field: str
    entity: str
    script: str
    offset: int
    note: str = ''


@dataclass(frozen=True)
class StoryPhase:
    phase: int
    title: str
    when: str
    disc_context: str
    sources: tuple[PhaseSource, ...] = ()


STORY_PHASES = (
    StoryPhase(0, 'Initial world',
               'The initial world variant, before the Missile Base finale. No normal field '
               'script in the audit explicitly assigns phase 0.', 'Disc 1 and early Disc 2'),
    StoryPhase(1, 'Missile Base escape',
               'Assigned during the Missile Base finale, as Selphie\'s team escapes. '
               'Both ending branches set variable 266 to 1.', 'Disc 2', (
                   PhaseSource('gmpark2', 'lastevent2_1', 'touchOn', 0x1CD4),
                   PhaseSource('gmpark2', 'lastevent2_2', 'touchOn', 0x2410))),
    StoryPhase(2, 'Balamb Garden emergency steering',
               'Assigned after the steering movie in which the newly airborne Garden turns '
               'away from Balamb town. The script also sets story progress to 570.',
               'Disc 2, continuing into early Disc 3', (
                   PhaseSource('bgsido_8', 'dic', 'defalut', 0x2284,
                               'The misspelt script name defalut is the original symbol.'),)),
    StoryPhase(3, 'Esthar revealed',
               'Assigned after the city-reveal sequence on the approach bridge to Esthar, '
               'after the Great Salt Lake. The script also sets story progress to 1750.',
               'Disc 3', (
                   PhaseSource('ewbrdg1', 'Director', 'default', 0x1AD0),)),
    StoryPhase(4, 'Rinoa rescued in space',
               'Assigned during the successful rescue of Rinoa in space, after the Lunar Cry '
               'and before the next scene jump. It is set to 4 again in the later Esthar '
               'air-station scene, alongside story progress 3150. This is already active '
               'during Disc 3, rather than beginning at Disc 4.', 'Late Disc 3 and Disc 4', (
                   PhaseSource('ssspace2', 'director0', 'default', 0xDBC,
                               'The space-rescue assignment, followed by a map jump.'),
                   PhaseSource('eaplane1', 'Director', 'default', 0x648,
                               'Later reassertion of phase 4 at Esthar air station.'))),
)


def phase_story_html():
    rows = ''.join(f'<tr><td><b>{p.phase}</b></td><td><b>{escape(p.title)}</b><br>'
                   f'{escape(p.when)}</td><td>{escape(p.disc_context)}</td></tr>'
                   for p in STORY_PHASES)
    sources = []
    for phase in STORY_PHASES:
        for source in phase.sources:
            sources.append(f'<li><b>Phase {phase.phase}</b>: <code>{source.field}.jsm</code>, '
                           f'<code>{escape(source.entity)}::{escape(source.script)}</code>, '
                           f'file offset <code>0x{source.offset:X}</code>: '
                           f'<code>PSHN_L {phase.phase}; POPM_B 266</code>. '
                           f'{escape(source.note)}</li>')
    return (
        '<h2>When do world phases change?</h2>'
        '<p>World phases are story variants, not disc numbers. Field scripts write '
        '<b>variable 266 (0x10A), WorldmapVariantIndex</b>. World-map initialization '
        'copies it into the runtime phase; the draw routine uses its low five bits '
        'to choose the group searches.</p>'
        '<table border="1" cellpadding="7" cellspacing="0"><tr><th>Phase</th>'
        '<th>When it becomes active</th><th>Disc context</th></tr>' + rows + '</table>'
        '<h3>Verified script references</h3><ul>' + ''.join(sources) + '</ul>'
        '<p>These references describe the original English PC scripts. Offsets point '
        'to the assignment instruction inside each JSM file; they are not Hext addresses. '
        'Test maps and the unused bgmast_6 debug menu are excluded from the story sequence. '
        'Modified field scripts can change these transitions.</p>'
        '<p>The <b>Groups and phases</b> tab changes which draw groups are searched at '
        'each existing phase. It does not modify these scripts or advance story progress.</p>')


class PhaseStoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('CID - World phase story transitions')
        self.resize(920, 720)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setHtml(phase_story_html())
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
