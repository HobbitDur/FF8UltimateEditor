import os, time
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
app = QApplication([])
from Ifrit.ifritmanager import IfritManager
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from Ifrit.IfritSeq.seqwidget import SeqWidget
from Common.undo import UndoStack
import Ifrit.ifritmonsterwidget as M
mgr = IfritManager("FF8GameData"); gd=mgr.game_data
p="extracted_files/battle/c0m015.dat"
e=mgr.parse_file(p, free_animation=False); mgr.set_active_enemy(e,p,textures=([],True))
pane=M.IfritFilePane(mgr, p, QSettings("t","t"), "Resources")
seq_idx=pane._tabs.indexOf(pane._seq_widget); cam_idx=pane._tabs.indexOf(pane._camera_widget)
pane._tabs.setCurrentIndex(seq_idx); app.processEvents()
out=[]
def cap(): return bytes(mgr.enemy.get_bytes(gd))
def restore(snap, tag):
    sections, focus = tag if isinstance(tag, tuple) else (None, tag)
    ss = MonsterAnalyser.split_sections(snap, gd)
    if not sections:
        return
    for i in sorted(sections):
        mgr.enemy.section_raw_data[i]=bytearray(ss[i]); mgr.enemy.reanalyze_section(i, gd, mgr.decompiler)
    pane.reload_from_model(changed_sections=sections, focus_tab_index=focus)
st=UndoStack(capture=cap, restore=restore)
def seq0(): return bytes(mgr.enemy.seq_animation_data['seq_animation_data'][0]['data'])
orig=seq0()
# edit A: change seq0
mgr.enemy.seq_animation_data['seq_animation_data'][0]['data']=bytearray(SeqWidget.DEFAULT_NEW_SEQUENCE)
A=seq0(); st.commit(tag=(frozenset({5}), seq_idx))
# edit B: append a sequence (still section 5)
mgr.enemy.seq_animation_data['seq_animation_data'].append({'id':99,'data':bytearray(SeqWidget.DEFAULT_NEW_SEQUENCE)})
nB=len(mgr.enemy.seq_animation_data['seq_animation_data']); st.commit(tag=(frozenset({5}), seq_idx))
# undo B -> count back, seq0 == A
pane._tabs.setCurrentIndex(cam_idx)  # pretend user moved to camera tab
st.undo(); app.processEvents()
out.append(f"after undo B: seq count={len(mgr.enemy.seq_animation_data['seq_animation_data'])} (expect {nB-1}), current tab jumped to seq={pane._tabs.currentIndex()==seq_idx}, seq0==A:{seq0()==A}")
# undo A -> seq0 == orig
st.undo(); app.processEvents()
out.append(f"after undo A: seq0==orig:{seq0()==orig}")
# redo A -> seq0==A
st.redo(); app.processEvents()
out.append(f"after redo A: seq0==A:{seq0()==A}")
# redo B -> count back up
st.redo(); app.processEvents()
out.append(f"after redo B: seq count={len(mgr.enemy.seq_animation_data['seq_animation_data'])} (expect {nB})")
# widget matches model
wmatch = sorted((x.getId(),bytes(x.getByteData())) for x in pane._seq_widget.seq_data_widget)==sorted((s['id'],bytes(s['data'])) for s in mgr.enemy.seq_animation_data['seq_animation_data'])
out.append(f"seq widget matches model at end: {wmatch}")
open("scratch_i.txt","w").write("\n".join(out))
