"""Present several loaded character models as one model, so Ifrit's camera preview can
film the whole victory party at once.

r0win's victory camera is framed for the party standing in the battle scene, not a single
model at the origin - so a lone character falls out of frame. This composite places each
imported character at a party-slot offset and merges their geometry and per-frame
(win-pose) vertices into one model, which the unchanged `CameraPreviewPanel` renders.

It duck-types just enough of `IfritManager` for `Ifrit3DWidget.load_file` and
`CameraPreviewPanel`: geometry, textures and the animated vertices are the merged versions;
anything else (skeleton, bone helpers, model translation) is delegated to the first
character's real manager. Each character keeps its own textures - they are flattened into
one atlas and every face's texture id is rebased into it (see `_build_texture_atlas`).
"""


def _build_texture_atlas(entries):
    """Flatten every character's textures into one list and map each model's raw UV tex-id
    to a global index in it. The 3D widget maps a face's raw tex-id to a pixmap by the rank
    of that id among the sorted distinct ids used (clamped to the pixmap count); combining
    models would collide those ids, so we assign contiguous global ids (0,1,2,...) - one per
    (model, raw-id) - and stack the matching pixmap descriptors in the same order, which
    makes the rank equal the index. Returns (global_texture_data, {(model_idx, raw): index})."""
    global_textures = []
    remap = {}
    for model_index, (manager, _win_pose, _offset) in enumerate(entries):
        images = [td for td in getattr(manager, "texture_data", [])
                  if getattr(td, "texture_image", None) is not None]
        geometry = manager.enemy.geometry_data
        raw_ids = sorted({tex for _i, _uv, tex, _bias in geometry.get_triangles_with_uv()} |
                         {tex for _i, _uv, tex, _bias in geometry.get_quads_with_uv()})
        for rank, raw in enumerate(raw_ids):
            remap[(model_index, raw)] = len(global_textures)
            global_textures.append(images[min(rank, len(images) - 1)] if images else None)
    return global_textures, remap


class _CompositeGeometry:
    """Merged geometry of several models: vertices concatenated, face indices rebased, and
    UV faces' texture ids rebased into the shared texture atlas.

    It stands in for a real GeometryData in front of Ifrit3DWidget, so it has to answer the same
    calls with the same signatures - `include_hidden` included. That flag asks for the faces whose
    TPage word sets the 0xFE00 "hide" bits, which the engine never draws and the viewer only shows
    on request; it is passed straight down to each model rather than interpreted here.
    """

    def __init__(self, entries, tex_remap):
        self._entries = entries  # list of (manager, win_pose_id, offset)
        self._tex_remap = tex_remap

    def get_vertices(self):
        vertices = []
        for manager, _win_pose, offset in self._entries:
            for x, y, z in manager.enemy.geometry_data.get_vertices():
                vertices.append((x + offset[0], y + offset[1], z + offset[2]))
        return vertices

    def _rebased_faces(self, method, include_hidden):
        faces = []
        base = 0
        for manager, _win_pose, _offset in self._entries:
            geometry = manager.enemy.geometry_data
            for indices in getattr(geometry, method)(include_hidden=include_hidden):
                faces.append(tuple(index + base for index in indices))
            base += len(geometry.get_vertices())
        return faces

    def _rebased_uv_faces(self, method, include_hidden):
        faces = []
        base = 0
        for model_index, (manager, _win_pose, _offset) in enumerate(self._entries):
            geometry = manager.enemy.geometry_data
            for indices, uvs, raw_tex, depth_bias in getattr(geometry, method)(
                    include_hidden=include_hidden):
                faces.append((tuple(index + base for index in indices), uvs,
                              self._tex_remap.get((model_index, raw_tex), 0), depth_bias))
            base += len(geometry.get_vertices())
        return faces

    def _joined_mask(self, method, include_hidden):
        mask = []
        for manager, _win_pose, _offset in self._entries:
            mask.extend(getattr(manager.enemy.geometry_data, method)(include_hidden=include_hidden))
        return mask

    def get_triangles(self, include_hidden=False):
        return self._rebased_faces("get_triangles", include_hidden)

    def get_quads(self, include_hidden=False):
        return self._rebased_faces("get_quads", include_hidden)

    def get_triangles_with_uv(self, include_hidden=False):
        return self._rebased_uv_faces("get_triangles_with_uv", include_hidden)

    def get_quads_with_uv(self, include_hidden=False):
        return self._rebased_uv_faces("get_quads_with_uv", include_hidden)

    # Aligned 1:1 with get_*_with_uv above, model after model, so the viewer can count the faces
    # the engine actually draws whether or not it is currently showing the hidden ones.
    def get_triangles_hidden_mask(self, include_hidden=False):
        return self._joined_mask("get_triangles_hidden_mask", include_hidden)

    def get_quads_hidden_mask(self, include_hidden=False):
        return self._joined_mask("get_quads_hidden_mask", include_hidden)

    def get_colored_triangles_with_color(self, include_hidden=False):
        return []

    def get_colored_quads_with_color(self, include_hidden=False):
        return []


class _CompositeAnimationData:
    """One synthetic animation. Its frames ARE the real AnimationFrame objects of the
    longest win pose (not placeholders): Ifrit3DWidget.load_file reads the current frame's
    .position (model translation) and bone matrices (skeleton), so they must be real. The
    merged VERTICES come from get_animated_vertices, not from these frames, so borrowing one
    character's frame list only affects the (small) whole-model translation and the
    skeleton overlay, both harmless in the preview."""

    class _Anim:
        """Stands in for a real Animation in front of Ifrit3DWidget, so it answers the same
        calls - get_nb_frame() included, which the viewer asks for on every frame."""

        def __init__(self, frames):
            self.frames = frames

        def get_nb_frame(self):
            return len(self.frames)

    def __init__(self, frames):
        self.nb_animations = 1
        self.animations = [self._Anim(frames)]


class _CompositeEnemy:
    """Delegates to the first character's enemy for everything except the merged geometry
    and the synthetic single animation."""

    def __init__(self, base_enemy, geometry, animation_data):
        self._base = base_enemy
        self.geometry_data = geometry
        self.animation_data = animation_data

    def __getattr__(self, name):  # bone_data, entity_type, ... from the real base enemy
        return getattr(self._base, name)


class CompositeVictoryModel:
    """An IfritManager-like facade over up to three character models for the preview."""

    def __init__(self, entries):
        # entries: list of dicts {manager, win_pose_id, offset, frame_count, real_frame_count}
        self._entries = [(e["manager"], e["win_pose_id"], e["offset"]) for e in entries]
        self._win_frame_count = [e["frame_count"] for e in entries]
        base_manager = entries[0]["manager"]
        # Precompute each unique frame's merged, offset vertices ONCE. Playback then just
        # indexes this list, instead of re-running every character's bone transform every
        # frame (which made the render lag). The win pose winds up then holds, so only the
        # pre-padding frames differ; the rest reuse the last one.
        self._baked_frames = self._bake_frames(entries)
        self._base_manager = base_manager
        self.game_data = base_manager.game_data
        # Representative real frames = the longest win pose (covers full playback and gives
        # Ifrit3DWidget real .position / bone matrices to read).
        rep = max(entries, key=lambda e: e["frame_count"])
        rep_frames = rep["manager"].enemy.animation_data.animations[rep["win_pose_id"]].frames
        self.texture_data, tex_remap = _build_texture_atlas(self._entries)
        self.enemy = _CompositeEnemy(
            base_manager.enemy, _CompositeGeometry(self._entries, tex_remap),
            _CompositeAnimationData(rep_frames))
        self.texture_black_is_transparent = getattr(
            base_manager, "texture_black_is_transparent", True)
        self.backface_cull_mode = getattr(base_manager, "backface_cull_mode", "all")

    @staticmethod
    def _bake_frames(entries):
        """[merged offset vertices] for each unique frame (0 .. longest real pose)."""
        per_model = []  # each: list over real frames of that character's offset vertices
        for entry in entries:
            manager, win_pose_id = entry["manager"], entry["win_pose_id"]
            ox, oy, oz = entry["offset"]
            frames = []
            for frame in range(max(1, entry["real_frame_count"])):
                frames.append([(x + ox, y + oy, z + oz)
                               for x, y, z in manager.get_animated_vertices(win_pose_id, frame)])
            per_model.append(frames)
        total = max(len(frames) for frames in per_model)
        baked = []
        for frame in range(total):
            merged = []
            for frames in per_model:
                merged.extend(frames[frame] if frame < len(frames) else frames[-1])
            baked.append(merged)
        return baked

    def get_animated_vertices(self, anim_id, frame_id, next_frame_id=None, step=0.0):
        if not self._baked_frames:
            return []
        index = frame_id if frame_id < len(self._baked_frames) else len(self._baked_frames) - 1
        return self._baked_frames[index]

    def __getattr__(self, name):
        # Anything the 3D viewer needs that we do not override (skeleton lines, bone
        # helpers, ...) is served by the first character's real manager. This keeps the
        # preview working against the full IfritManager interface without listing every
        # method; those helpers act on the first character (a harmless overlay).
        if name == "_base_manager":
            raise AttributeError(name)
        return getattr(self._base_manager, name)


def party_slot_offsets(count, spacing):
    """Lateral (world-X) offsets that stand `count` characters in a centred row."""
    if count <= 0:
        return []
    start = -spacing * (count - 1) / 2.0
    return [(start + spacing * i, 0.0, 0.0) for i in range(count)]
