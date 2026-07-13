"""Alexander: battle stage (a0stgXXX.x) manager - the non-GUI part.

Pure Python/PIL: no Qt import, usable from scripts and tests. The GUI layer
(alexanderwidget) wraps it in a small bridge that adapts textures to QPixmaps
for the Ifrit3D viewer.
"""

import os
import pathlib
from typing import List, Tuple

from FF8GameData.battlestage.battlestageanalyser import build_stage_model, BattleStageModel


class AlexanderManager:
    # Battle stages are static (one bind-pose frame); the viewer still reads
    # these attributes.
    max_animation_frames = 1
    anim_native_fps = 15
    # TIM decoding gives real alpha; do not key opaque black to transparent.
    texture_black_is_transparent = False

    def __init__(self):
        self.enemy = BattleStageModel()
        self.show_sky = False           # sky dome hidden by default (it hides the stage)
        self._full_model = None
        self._all_objects = []
        self._group_of_object = []
        self._visible_texture_images = []   # PIL images, in tex_id order
        self._visible_tex_keys = []         # visible rank -> full-model build rank
        self._folder_files = {}             # display name -> path (folder mode)
        # last directly-loaded stage, kept as a template so an imported/edited
        # mesh can be written back into its camera / TIM / skeleton.
        self._template_raw = None
        self._template_tex_layout = []      # visible rank -> (texpage, clut, w, h)

    # ------------------------------------------------------------------ loading

    def open_files(self, paths: List[str]) -> List[str]:
        """Register battle stage files picked individually (multi-select file
        dialog). Returns display names, normally basenames; if two selected
        files share a basename the parent folder name is prefixed so both
        stay reachable."""
        self._folder_files = {}
        for p in paths:
            name = os.path.basename(p)
            if name in self._folder_files and self._folder_files[name] != p:
                name = os.path.join(os.path.basename(os.path.dirname(p)),
                                    os.path.basename(p))
            self._folder_files[name] = p
        return sorted(self._folder_files)

    def load_stage_by_name(self, name: str):
        self.load_stage_file(self._folder_files[name])

    def load_stage_file(self, path: str):
        data = pathlib.Path(path).read_bytes()
        name = pathlib.Path(path).name
        stage_id = _stage_id_from_name(name)
        model = build_stage_model(data, stage_id=stage_id, name=name)
        self._set_model(model)
        # snapshot this stage as the write-back template (survives a later glb import)
        self._template_raw = model.raw
        self._template_tex_layout = dict(model.tex_layout)   # tex_key -> (page, clut, w, h)

    def load_glb(self, path: str):
        """Load a .glb (previously exported, optionally edited) for viewing."""
        from FF8GameData.battlestage.glbimport import build_model_from_glb
        model = build_model_from_glb(path)
        model.name = os.path.basename(path)
        self._set_model(model)

    def export_glb(self, path: str):
        """Export the whole stage (all 4 groups, group-tagged) to a .glb."""
        from FF8GameData.battlestage.stageexport import export_stage_glb
        m = self._full_model
        # _apply_sky_visibility left object_data as the visible subset; export the
        # full set (all groups incl. the sky) so group membership survives.
        saved_objs, saved_nb = m.geometry_data.object_data, m.geometry_data.nb_object
        saved_groups = m.group_of_object
        try:
            m.geometry_data.object_data = self._all_objects
            m.geometry_data.nb_object = len(self._all_objects)
            m.group_of_object = self._group_of_object
            export_stage_glb(m, path)
        finally:
            m.geometry_data.object_data = saved_objs
            m.geometry_data.nb_object = saved_nb
            m.group_of_object = saved_groups

    def _set_model(self, model: BattleStageModel):
        self._full_model = model
        # keep the full object list so the sky can be toggled without reparsing
        self._all_objects = list(model.geometry_data.object_data)
        self._group_of_object = list(model.group_of_object)
        self.enemy = model
        self._apply_sky_visibility()

    @property
    def is_loaded(self) -> bool:
        return self._full_model is not None

    def has_sky(self) -> bool:
        """True when the stage has a separate sky dome that can be hidden:
        group 3 has geometry AND there is other geometry to show without it."""
        if self._full_model is None:
            return False
        sky = self._full_model.sky_group_index
        groups = self._group_of_object
        return any(g == sky for g in groups) and any(g != sky for g in groups)

    # ------------------------------------------------------------ sky visibility

    def set_show_sky(self, show: bool):
        """The sky group is a huge dome that surrounds (and hides) the stage;
        it is hidden by default so the stage itself is visible."""
        self.show_sky = show
        if self._full_model is not None:
            self._apply_sky_visibility()

    def _apply_sky_visibility(self):
        sky = self._full_model.sky_group_index
        if self.show_sky:
            objs = list(self._all_objects)
        else:
            objs = [o for o, g in zip(self._all_objects, self._group_of_object)
                    if g != sky]
            # A few stages (e.g. 38) put the whole stage in group 3 with no other
            # groups; there is no separate sky to hide, so keep everything.
            if not objs:
                objs = list(self._all_objects)
        self.enemy.geometry_data.object_data = objs
        self.enemy.geometry_data.nb_object = len(objs)
        self._renumber_textures(objs)

    def _renumber_textures(self, visible_objects):
        """Renumber tex ids of the visible faces to a contiguous 0..k-1 range
        and expose the matching images in that order. The Ifrit3D viewer maps
        tex_id -> pixmap by rank, so contiguity keeps it an identity mapping;
        without this, hiding the sky leaves gaps and every texture shifts."""
        used = []
        seen = set()
        for obj in visible_objects:
            for f in list(obj.triangles) + list(obj.quads):
                key = getattr(f, "tex_key", 0)
                if key not in seen:
                    seen.add(key)
                    used.append(key)
        used.sort()
        remap = {key: i for i, key in enumerate(used)}
        for obj in visible_objects:
            for f in list(obj.triangles) + list(obj.quads):
                new_id = remap.get(getattr(f, "tex_key", 0), 0)
                f.tex_id_1 = new_id
                f.tex_id_2 = new_id
        textures = self._full_model.textures
        self._visible_texture_images = [textures[k] for k in used if k < len(textures)]
        self._visible_tex_keys = list(used)

    def visible_textures(self):
        """PIL RGBA images of the visible geometry, ordered by tex_id."""
        return list(self._visible_texture_images)

    # ------------------------------------------------------------------ saving

    @property
    def can_save(self) -> bool:
        return getattr(self.enemy, "raw", None) is not None or self._template_raw is not None

    def save(self, path: str) -> str:
        """Write the current model to an a0stgXXX.x file. A directly-loaded,
        unedited stage is written byte-for-byte; an imported/edited mesh is
        re-encoded into the last-loaded stage (its camera, TIM and skeleton are
        the template). Returns a short note about which path was taken."""
        from FF8GameData.battlestage.battlestagewriter import serialize, encode_object
        model = self.enemy
        if getattr(model, "raw", None) is not None:
            data = serialize(model.raw)
            note = "saved (byte-exact copy of the loaded stage)"
        elif self._template_raw is not None:
            from FF8GameData.battlestage.battlestagewriter import group_bone0_size
            layout = self._template_tex_layout            # tex_key -> (page, clut, w, h)
            # per-group bone-0 vertical offset, subtracted so the reload's bone
            # matrix cancels out (all objects are collapsed onto bone 0).
            y_bias = [group_bone0_size(g.skeleton) if g else 0
                      for g in self._template_raw.groups]
            # distribute the (full) objects back into their groups; the sky stays
            # in group 3 so the engine keeps rotating it.
            group_objects = {0: [], 1: [], 2: [], 3: []}
            for obj, gi in zip(self._all_objects, self._group_of_object):
                gi = gi if 0 <= gi <= 3 else 0
                group_objects[gi].append(encode_object(obj, layout, y_bias=y_bias[gi]))
            data = serialize(self._template_raw, group_objects=group_objects)
            groups_used = sorted(g for g, b in group_objects.items() if b)
            note = ("saved (edited mesh written back into the loaded stage's "
                    f"template; groups {groups_used} filled, sky group 3 kept)")
        else:
            raise ValueError("Load a battle stage first: it provides the camera, "
                             "texture and skeleton the saved file needs.")
        pathlib.Path(path).write_bytes(data)
        return note

    # ---------------------------------------------------- viewer data

    def get_skeleton_lines(self, anim_id: int = 0, frame_id: int = 0) -> tuple:
        matrices = self._matrices(anim_id, frame_id)
        bones = self.enemy.bone_data.bones
        lines = [None] * len(bones)
        parents = [bone.parent_id for bone in bones]
        for k, bone in enumerate(bones):
            if bone.parent_id == 0xFFFF or bone.parent_id >= len(matrices) or k >= len(matrices):
                continue
            pm, cm = matrices[bone.parent_id], matrices[k]
            lines[k] = ((pm.M41, pm.M42, pm.M43), (cm.M41, cm.M42, cm.M43))
        return lines, parents

    def _matrices(self, anim_id, frame_id):
        anims = self.enemy.animation_data.animations
        if not anims:
            return []
        return anims[0].frames[0].bone_matrices

    def get_animated_vertices(self, anim_id: int, frame_id: int, next_frame_id: int = None,
                              step: float = 0.0) -> List[Tuple[float, float, float]]:
        matrices = self._matrices(anim_id, frame_id)
        out = []
        for obj in self.enemy.geometry_data.object_data:
            for vd in obj.vertices_data:
                mat = matrices[vd.bone_id] if vd.bone_id < len(matrices) else None
                for vertex in vd.vertices:
                    out.append(self._transform(vertex.get_list(), mat))
        return out

    @staticmethod
    def _transform(vertex, matrix):
        x, y, z = vertex
        if matrix is None:
            return (x, y, z)
        return (
            matrix.M11 * x + matrix.M12 * y + matrix.M13 * z + matrix.M41,
            matrix.M21 * x + matrix.M22 * y + matrix.M23 * z + matrix.M42,
            matrix.M31 * x + matrix.M32 * y + matrix.M33 * z + matrix.M43,
        )


def _stage_id_from_name(name: str):
    base = os.path.basename(name).lower()
    if base.startswith("a0stg") and len(base) >= 8 and base[5:8].isdigit():
        return int(base[5:8])
    return None
