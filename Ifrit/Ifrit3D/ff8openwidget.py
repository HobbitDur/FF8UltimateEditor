import math
from typing import List

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QLabel
from OpenGL.GL import *
from OpenGL.GLU import *


def _look_at_matrix(eye, target, up=(0.0, 1.0, 0.0)):
    """A gluLookAt view matrix as a flat column-major 16-tuple for glMultMatrixf (no GLU
    dependency, since libGLU is not reliably present)."""
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    forward = target - eye
    norm = np.linalg.norm(forward)
    forward = forward / norm if norm > 1e-9 else np.array([0.0, 0.0, -1.0])
    side = np.cross(forward, up)
    norm = np.linalg.norm(side)
    side = side / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])
    true_up = np.cross(side, forward)
    return np.array([
        side[0], true_up[0], -forward[0], 0.0,
        side[1], true_up[1], -forward[1], 0.0,
        side[2], true_up[2], -forward[2], 0.0,
        -np.dot(side, eye), -np.dot(true_up, eye), np.dot(forward, eye), 1.0,
    ], dtype=np.float32)


class FF8OpenGLWidget(QOpenGLWidget):
    """
    FF8 Monster Viewer Widget - Reusable PyQt Widget
    """
    # When a character body and its weapon are drawn in the same viewer, the weapon's raw texture
    # ids (0-255) are shifted up by this so they never collide with the body's in the merged
    # atlas. Larger than any real raw id (tex_id_1 & 0xFF).
    _WEAPON_TEX_OFFSET = 1 << 16
    # Direct manipulation of the skeleton in the view
    bone_picked = pyqtSignal(int, bool)        # a joint was clicked: (bone id, additive=Ctrl held)
    bone_length_dragged = pyqtSignal(float)    # Shift+drag: total world-unit delta since drag start
    bone_length_drag_finished = pyqtSignal()
    bone_rotation_dragged = pyqtSignal(int, float)  # ring drag: (axis 0/1/2, total degrees)
    bone_rotation_drag_finished = pyqtSignal()
    drawn_count_changed = pyqtSignal(int)      # primitives actually submitted this frame changed

    PICK_RADIUS_PX = 14   # click-to-joint tolerance, in logical pixels
    CLICK_SLOP_PX = 4     # press/release within this distance = click, beyond = orbit drag

    # Ring radius as a fraction of the model size: the handle is anchored in the 3D scene, so it
    # grows on screen as you zoom in and shrinks as you zoom out (rather than a constant screen
    # size). 0.15 ~ the old 55px look at the default framing distance.
    GIZMO_WORLD_FRACTION = 0.15
    GIZMO_PICK_TOLERANCE_PX = 8
    GIZMO_SEGMENTS = 48
    GIZMO_COLORS = ((1.0, 0.35, 0.35), (0.35, 1.0, 0.35), (0.45, 0.6, 1.0))  # X, Y, Z

    def __init__(self, parent=None):
        self.face_color = (0.45, 0.65, 0.95)
        self.raw_vertices = []
        self.set_vertices([(0,0,0)])
        self.skeleton_lines = []  # List of (start, end) or None
        self.bone_parents = []  # List of parent IDs for each bone
        self.selected_bone = -1
        # Multi-selection (Ctrl+click adds bones to compare). selected_bone stays the "primary"
        # (last-clicked) one, always the last entry of this list; all of them are highlighted.
        self.selected_bones = []
        self.model_translation = [0.0, 0.0, 0.0]
        self.reference_position  = [0.0, 0.0, 0.0]
        self.triangles = []
        self.quads =[]
        self.skeleton_lines = []

        # --- NEW: UV / texture state ---
        self.triangles_uv = []   # list of (indices_tuple, uvs_tuple, raw_tex_id, depth_bias)
        self.quads_uv = []       # list of (indices_tuple, uvs_tuple, raw_tex_id, depth_bias)
        # Backface-cull acceleration: face topology cached on set_*_with_uv, the per-frame cull
        # mask recomputed once per paint (see _build_cull_topology / _recompute_cull_masks).
        self._tri_idx3 = self._tri_mult = self._quad_idx3 = self._quad_mult = None
        self._tri_cull_mask = self._quad_cull_mask = None
        self._tri_hidden = self._quad_hidden = None   # per-entry hidden flags for the budget count
        self._last_drawn_count = -1        # last emitted drawn_primitive_count (change detection)
        # Colored (untextured) primitives — battle stages and magic models
        self.colored_triangles = []  # list of (indices_tuple, rgb_tuple, depth_bias)
        self.colored_quads = []      # list of (indices_tuple, rgb_tuple, depth_bias)
        self._pending_qpixmaps = []   # QPixmaps waiting to be uploaded
        self._gl_textures = []        # list of GL texture IDs (after upload)
        self._tex_id_to_index = {}    # raw tex_id → _gl_textures index
        self.show_texture = False
        self._textures_dirty = False
        super().__init__(parent)

        # Take keyboard focus when clicked, so the 3D-tab shortcuts (←/→ frame, Ctrl+C/V, B...)
        # fire after clicking in the model view - and so clicking the view releases the focus a
        # spin box (anim id, frame...) was holding. ClickFocus: focus on click, not on Tab.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Skeleton edit cheat-sheet, shown in the view corner while the
        # skeleton is displayed (a plain child widget floats over the GL view)
        self._skeleton_help = QLabel(
            "Click joint: select bone\n"
            "Ctrl+click: select several bones\n"
            "Drag ring: rotate bone (X/Y/Z)\n"
            "Shift+Drag: bone length\n"
            "B: add child bone", self)
        self._skeleton_help.setStyleSheet(
            "background: rgba(20, 20, 30, 170); color: #ddd;"
            "padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        self._skeleton_help.adjustSize()
        self._skeleton_help.hide()

        # Camera controls
        self.rot_x = 20.0
        self.rot_y = 30.0
        self.zoom = 0
        self.pan_x = 0.0
        self.pan_y = 0.0

        # Mouse state
        self.last_mouse_x = None
        self.last_mouse_y = None
        self.left_button_down = False
        self.right_button_down = False

        # Picking / direct-edit state. is_edit_allowed is replaced by the
        # owner (Ifrit3DWidget) to block grabbing while an animation plays.
        self.is_edit_allowed = lambda: True
        self._pick_modelview = None
        self._pick_projection = None
        self._pick_viewport = None
        self._press_pos = None
        self._length_drag = False
        self._length_drag_dir = (0.0, -1.0)
        self._length_drag_total = 0.0

        # Rotation gizmo (three rings around the selected joint)
        self.gizmo_center = None       # model-space pivot, or None = hidden
        self.gizmo_axes = None         # 3 unit vectors (model space)
        self._gizmo_active_axis = -1   # axis being dragged, -1 = none
        self._gizmo_use_plane = True   # angle method chosen at grab time
        self._gizmo_last_angle = 0.0
        self._gizmo_total_deg = 0.0

        # Display options
        self.show_triangles = True
        self.show_quads = True
        self.show_wireframe = False
        self.show_axis = False
        self.show_texture = True
        self.show_skeleton = False
        self.show_gizmo = True     # rotation rings ("sphere") around the selected joint

        self.back_face_offset = -0.003  # Smaller offset for triangles
        self.triangle_cache = {}  # Cache for back face offsets per fra
        # Backface culling mode (see _should_cull_backface): 'all' culls every
        # back-facing face exactly like the game — required to see through
        # single-sided fringe/lace fins (e.g. Blobra) instead of their dark
        # backsides. 'duplicates' resolves two-sided pairs only, 'off'
        # disables culling.
        self.backface_cull = 'all'
        # Battle .dat textures go through PNG files that lose alpha, so pure
        # black is keyed to transparent. Tools that provide real alpha
        # (e.g. Seed's TIM decoding) set this to False to keep opaque black.
        self.black_is_transparent = True

    @staticmethod
    def _rank_texture_map(tex_ids_used: list, n: int, base_index: int = 0) -> dict:
        """Map each raw tex-id to a pixmap index by rank: the k-th smallest distinct id -> the
        k-th pixmap (clamped to the last one). `base_index` shifts every result, so a second
        model's ids can point past the first model's pixmaps in a merged atlas."""
        out = {}
        for rank, raw_id in enumerate(sorted(set(tex_ids_used))):
            out[raw_id] = base_index + min(rank, n - 1)
        return out

    def set_texture_pixmaps(self, qpixmaps: list, tex_ids_used: list):
        """Call this from outside with a list of QPixmaps..."""
        self.set_texture_pixmaps_explicit(
            qpixmaps, self._rank_texture_map(tex_ids_used, len(qpixmaps)))

    def set_texture_pixmaps_explicit(self, qpixmaps: list, tex_id_to_index: dict):
        """Like set_texture_pixmaps but with a caller-built raw-id -> pixmap-index map, so a merged
        body+weapon atlas can route each model's faces to its own pixmaps (the rank heuristic can't:
        with more distinct ids than pixmaps it clamps, which would cross the two models' textures)."""
        self._free_gl_textures()
        self._pending_qpixmaps = list(qpixmaps)
        self._tex_id_to_index = dict(tex_id_to_index)
        self._textures_dirty = True
        self.update()

    def _upload_pending_textures(self):
        """Upload QPixmaps to GL textures with black->alpha conversion"""
        self._free_gl_textures()
        for pix in self._pending_qpixmaps:
            img = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()

            # Get raw bytes as bytearray for modification
            ptr = img.bits()
            ptr.setsize(img.sizeInBytes())
            data = bytearray(ptr)

            if self.black_is_transparent:
                # Process RGBA data: for each pixel, if RGB is 0, set alpha to 0
                for i in range(0, len(data), 4):
                    if data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 0:
                        data[i + 3] = 0  # Set alpha to 0

            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)

            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            # Point sampling, no mipmaps - what the PSX/PC engine does (flat FT3/FT4
            # GPU primitives, nearest-texel lookup, no LOD). Keeps the authentic
            # blocky look. Mipmapping/anisotropic were tried to reduce grazing-angle
            # shimmer but made no acceptable difference (atlas bleed and/or blur), so
            # this stays at plain nearest.
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0,
                         GL_RGBA, GL_UNSIGNED_BYTE, bytes(data))
            self._gl_textures.append(tex)
        self._pending_qpixmaps = []
        self._textures_dirty = False

    def _free_gl_textures(self):
        if self._gl_textures:
            glDeleteTextures(len(self._gl_textures), self._gl_textures)
            self._gl_textures = []

    def set_triangles_with_uv(self, data: list):
        """data: list of (indices_tuple, uvs_tuple, raw_tex_id, depth_bias)"""
        self.triangles_uv = data
        self._tri_idx3, self._tri_mult = self._build_cull_topology(data, 3)

    def set_quads_with_uv(self, data: list):
        """data: list of (indices_tuple, uvs_tuple, raw_tex_id, depth_bias)"""
        self.quads_uv = data
        self._quad_idx3, self._quad_mult = self._build_cull_topology(data, 4)

    @staticmethod
    def _build_cull_topology(uv_list, n):
        """Precompute the backface-cull inputs that depend only on FACE TOPOLOGY (constant while
        an animation plays): the first-3 vertex indices of each face (enough for its normal) and
        each face's multiplicity (how many coincident copies share the same vertex set - a
        double-sided pair is 2). Recomputing these + a per-face numpy normal EVERY paint was the
        3D lag: 35-45 ms/frame at ~2600 faces, pure Python, before any GL. Cached here, the paint
        does one vectorized cross-product+dot instead (see _cull_mask_for)."""
        import numpy as _np
        if not uv_list:
            return None, None
        idx3 = _np.array([entry[0][:3] for entry in uv_list], dtype=_np.int64)
        count = {}
        keys = [frozenset(entry[0]) for entry in uv_list]
        for k in keys:
            count[k] = count.get(k, 0) + 1
        mult = _np.array([count[k] for k in keys], dtype=_np.int64)
        return idx3, mult

    def _cull_mask_for(self, idx3, mult, mode):
        """Vectorized backface cull: a bool array, True = drop this face this frame. Replaces the
        per-face _should_cull_backface loop with one numpy pass (same math: normal =
        cross(v1-v0, v2-v0); front-facing when it points away from the eye - see
        _should_cull_backface for the sign convention)."""
        if idx3 is None or len(idx3) == 0:
            return None
        n = len(idx3)
        if mode == 'off':
            return np.zeros(n, dtype=bool)
        va = self.vertices_array
        if va is None or len(va) == 0:
            return np.zeros(n, dtype=bool)
        v0 = va[idx3[:, 0]]
        normal = np.cross(va[idx3[:, 1]] - v0, va[idx3[:, 2]] - v0)
        eye = getattr(self, '_eye_model', None)
        if eye is not None:
            # front-facing when the wound normal points away from the eye -> cull the rest
            back = np.einsum('ij,ij->i', normal, np.asarray(eye, dtype=np.float64) - v0) > 0.0
        else:
            back = normal @ np.asarray(self._view_direction_model(), dtype=np.float64) < 0.0
        if mode == 'duplicates':
            back &= (mult > 1)          # only cull the hidden copy of a double-sided pair
        return back

    def _recompute_cull_masks(self):
        """Per-paint: refresh the cull masks from the current posed vertices + camera."""
        mode = getattr(self, 'backface_cull', 'duplicates')
        self._tri_cull_mask = self._cull_mask_for(getattr(self, '_tri_idx3', None),
                                                  getattr(self, '_tri_mult', None), mode)
        self._quad_cull_mask = self._cull_mask_for(getattr(self, '_quad_idx3', None),
                                                   getattr(self, '_quad_mult', None), mode)

    def set_budget_hidden_masks(self, tri_hidden, quad_hidden):
        """Per-entry hidden flags aligned with the current triangles_uv / quads_uv lists (from
        GeometrySection.get_*_hidden_mask). drawn_primitive_count() subtracts these so the budget
        always excludes engine-hidden faces even while the viewer is displaying them."""
        self._tri_hidden = np.asarray(tri_hidden, dtype=bool) if tri_hidden else None
        self._quad_hidden = np.asarray(quad_hidden, dtype=bool) if quad_hidden else None
        self._last_drawn_count = -1        # force the next paint to re-emit

    def drawn_primitive_count(self):
        """Primitives actually submitted for the CURRENT view: textured triangles + quads that
        survive backface culling AND are not engine-hidden, plus colored faces. Mirrors what the
        PSX engine writes into its per-frame packet buffer - it culls back-faces (GTE NCLIP) before
        adding a polygon to the ordering table and never draws 0xFE00-hidden faces, so raw geometry
        counts overstate the real per-frame cost. Hidden exclusion is unconditional (independent of
        the 'show hidden faces' display toggle)."""
        def visible(cull, hidden, lst):
            if not lst:
                return 0
            n = len(lst)
            drop = np.zeros(n, dtype=bool) if cull is None else cull.copy()
            if hidden is not None and len(hidden) == n:
                drop |= hidden
            return int((~drop).sum())
        return (visible(self._tri_cull_mask, self._tri_hidden, getattr(self, 'triangles_uv', None))
                + visible(self._quad_cull_mask, self._quad_hidden, getattr(self, 'quads_uv', None))
                + len(getattr(self, 'colored_triangles', []) or [])
                + len(getattr(self, 'colored_quads', []) or []))

    def set_colored_triangles(self, data: list):
        """data: list of (indices_tuple, rgb_tuple, depth_bias) — flat-colored faces"""
        self.colored_triangles = data

    def set_colored_quads(self, data: list):
        """data: list of (indices_tuple, rgb_tuple, depth_bias) — flat-colored faces"""
        self.colored_quads = data

    def set_show_texture(self, show: bool):
        self.show_texture = show
        self.update()

    def set_model_translation(self, x: float, y: float, z: float):
        """Set the model translation (frame position)"""
        self.model_translation = [x, y, z]
        self.update()
    def set_skeleton_data(self, lines: list, parents: list):
        """Set both skeleton lines and parent relationships"""
        self.skeleton_lines = lines
        self.bone_parents = parents
        self.update()

    def set_skeleton_lines(self, lines: list):
        self.skeleton_lines = lines
        self.update()

    def set_selected_bone(self, bone_index: int):
        self.selected_bone = bone_index
        self.selected_bones = [bone_index] if bone_index >= 0 else []
        self.update()

    def set_selected_bones(self, bone_indices: list):
        """Set the whole highlighted selection at once (Ctrl+click multi-select). The primary bone
        (drag/gizmo target) is the last one in the list."""
        self.selected_bones = [b for b in bone_indices if b >= 0]
        self.selected_bone = self.selected_bones[-1] if self.selected_bones else -1
        self.update()

    def set_vertices(self, vertices: list):
        self.vertices = vertices
        self.vertices_array = np.array(self.vertices, dtype=np.float32)

        if len(self.vertices) == 0:
            # A model with no geometry (e.g. an empty placeholder file opened with default,
            # empty section data). numpy .min()/.max() raise on a zero-size array, so fall back
            # to a neutral unit-sized view centred on the origin instead of computing bounds.
            self.vertices_array = np.zeros((0, 3), dtype=np.float32)
            self.MODEL_CENTER = np.zeros(3, dtype=np.float32)
            self.model_min = np.zeros(3, dtype=np.float32)
            self.model_max = np.zeros(3, dtype=np.float32)
            self.model_extents = np.zeros(3, dtype=np.float32)
            self.MODEL_SIZE = 1.0
            return

        MIN_BOUNDS = self.vertices_array.min(axis=0)
        MAX_BOUNDS = self.vertices_array.max(axis=0)
        self.MODEL_CENTER = (MIN_BOUNDS + MAX_BOUNDS) / 2

        # Store the actual extents for better zoom calculation
        self.model_min = MIN_BOUNDS
        self.model_max = MAX_BOUNDS
        self.model_extents = MAX_BOUNDS - MIN_BOUNDS
        self.MODEL_SIZE = max(self.model_extents)  # Use max extent, not diagonal


    def set_show_skeleton(self, show: bool):
        self.show_skeleton = show
        self._skeleton_help.setVisible(show)
        self._position_help_label()
        self.update()

    def set_show_gizmo(self, show: bool):
        """Show/hide the rotation rings around the selected joint (skeleton lines stay)."""
        self.show_gizmo = show
        self.update()

    def _position_help_label(self):
        margin = 8
        self._skeleton_help.adjustSize()
        self._skeleton_help.move(self.width() - self._skeleton_help.width() - margin, margin)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_help_label()

    def set_triangles(self, triangles:List):
        self.triangles = triangles
    def set_quads(self, quads:List):
        self.quads = quads

    def initializeGL(self):
        glClearColor(0.12, 0.12, 0.18, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        self._apply_projection(w, h)

    def _apply_projection(self, w, h):
        """(Re)build the projection matrix with clip planes sized to the current
        model/zoom, not a fixed 0.1-100 range: monster models fit comfortably in
        that range, but battle stages (much larger, and zoomable out to 10x their
        size) were getting their far edges clipped by the fixed far=100 plane -
        geometry popping in/out as the camera moved. Recomputed every frame (from
        paintGL) rather than only on resize, since zoom/model size change without
        a resize event."""
        # near scales with the current camera distance (self.zoom), not the model's
        # absolute size: tying it to model size instead gave a far/near ratio in the
        # tens of thousands for large battle stages, which starves the depth buffer's
        # precision at distance and shows up as z-fighting/flicker on coincident faces.
        far_extent = max(getattr(self, 'MODEL_SIZE', 0.0), self.zoom, 1.0)
        near = max(self.zoom * 0.05, 0.05)
        far = far_extent * 3.0 + 100.0
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h if h else 1.0, near, far)
        glMatrixMode(GL_MODELVIEW)

    def set_reference_position(self, x: float, y: float, z: float):
        """Set the reference position (frame 0 position) that camera centers on"""
        self.reference_position = [x, y, z]
        self.update()

    def set_camera(self, eye, target, up=(0.0, 1.0, 0.0)):
        """Place an explicit eye->target camera (used by the camera-animation preview),
        replacing the orbit camera. Coordinates are in viewer space - the same space
        set_vertices() uses. Call clear_explicit_camera() to restore the orbit controls."""
        self._explicit_view = _look_at_matrix(eye, target, up)
        self.update()

    def clear_explicit_camera(self):
        """Restore the normal orbit camera (rot/zoom/pan)."""
        self._explicit_view = None
        self.update()

    def paintGL(self):
        if self._textures_dirty and self._pending_qpixmaps:
            self._upload_pending_textures()

        self._apply_projection(self.width(), self.height())

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        if getattr(self, "_explicit_view", None) is not None:
            # Explicit eye->target camera (the camera-animation preview): apply the view
            # matrix and draw the model at its raw vertex positions (the caller places the
            # eye/target relative to the model's own bounds, so no orbit centering here).
            glMultMatrixf(self._explicit_view)
        else:
            # Pull camera back
            glTranslatef(self.pan_x, self.pan_y, -self.zoom)

            # Orbit rotations — no up-vector flip issue
            glRotatef(self.rot_x, 1.0, 0.0, 0.0)
            glRotatef(self.rot_y, 0.0, 1.0, 0.0)

            # Center on model
            glTranslatef(-self.reference_position[0], -self.reference_position[1], -self.reference_position[2])

            # Apply frame position translation
            glTranslatef(self.model_translation[0], self.model_translation[1], self.model_translation[2])

        # Camera position in model space, for exact per-face backface culling
        # (the PSX culls per face after projection; a single global view axis
        # mis-culls faces near edge-on and shows the wrong side of two-sided
        # dual-textured faces, e.g. Blobra's fins)
        try:
            mv = np.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=np.float64).T
            self._eye_model = (np.linalg.inv(mv) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
        except Exception:
            self._eye_model = None

        # Snapshot the full transform for mouse picking (joints are drawn in
        # this same model space, so gluProject with these gives their screen
        # position)
        try:
            self._pick_modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
            self._pick_projection = glGetDoublev(GL_PROJECTION_MATRIX)
            self._pick_viewport = glGetIntegerv(GL_VIEWPORT)
        except Exception:
            self._pick_modelview = None

        # One vectorized backface-cull pass for the whole model (per posed frame + camera),
        # instead of a per-face numpy normal inside each draw loop - the 3D-lag fix.
        self._recompute_cull_masks()
        # Tell the info bar how many primitives actually survive culling this frame (only when it
        # changes - a static pose emits nothing; rotating/animating updates the budget readout).
        drawn = self.drawn_primitive_count()
        if drawn != self._last_drawn_count:
            self._last_drawn_count = drawn
            self.drawn_count_changed.emit(drawn)

        if self.show_axis:
            self.draw_axis()
        if self.show_texture and self._gl_textures and (self.triangles_uv or self.quads_uv):
            self._draw_textured_triangles()
            self._draw_textured_quads()
            self._draw_colored_faces()
        else:
            # Flat-color fallback (original code)
            glColor3f(*self.face_color)
            for tri in self.triangles:
                glBegin(GL_TRIANGLES)
                for idx in tri:
                    v = self.vertices_array[idx]
                    glVertex3f(v[0], v[1], v[2])
                glEnd()
            self.draw_quads()

        if self.show_wireframe:
            self.draw_wireframe()

        if self.show_skeleton:
            self.draw_skeleton()
            if self.show_gizmo:
                self.draw_rotation_gizmo()

    def _should_cull_backface(self, verts, multiplicity, view_dir):
        """PSX-style per-face backface cull (exact per-face plane test, same
        outcome as the game's screen-space cross product on vertices A,B,C).

        Sign convention: the viewer's model transform (x,y,z)->(-x,z,-y) has
        determinant -1 (mirror), which flips triangle winding relative to the
        game. A face is therefore FRONT-facing here when its wound normal
        points AWAY from the eye (dot(normal, eye - v0) < 0) — verified by
        ray-casting Blobra: the visible nearest surface satisfies this for
        ~97% of rays, and the opposite sign renders models inside-out.

        Mode 'duplicates' (default) only culls the hidden copy of a
        double-sided pair (two coincident opposite-winding faces), leaving
        single-sided faces double-sided — never creates holes. Mode 'all'
        culls every back-facing face exactly like the game (authentic,
        including the game's own gaps at open edges). Mode 'off' disables
        culling."""
        mode = getattr(self, 'backface_cull', 'duplicates')
        if mode == 'off':
            return False
        if mode == 'duplicates' and multiplicity <= 1:
            return False
        if len(verts) == 3:
            normal = self._calculate_triangle_normal_fast(verts)
        else:
            normal = self._calculate_quad_normal(verts)
        eye = getattr(self, '_eye_model', None)
        if eye is not None:
            # Mirrored model space: front-facing = wound normal points away
            # from the eye, so cull when it points toward the eye
            face_to_eye = eye - np.asarray(verts[0], dtype=np.float64)
            return float(np.dot(normal, face_to_eye)) > 0.0
        # Fallback (no eye available): same convention with the approximate
        # global view axis — view_dir points INTO the scene, so a normal
        # aligned with it faces away from the eye = front-facing here
        return float(np.dot(normal, view_dir)) < 0.0

    def _view_direction_model(self):
        """Unit vector pointing from the camera into the scene, expressed in
        model space (inverse of the paintGL orbit rotations)."""
        rx = np.radians(self.rot_x)
        ry = np.radians(self.rot_y)
        # view = Rx(rot_x) * Ry(rot_y); camera looks along -z in view space:
        # dir_model = Ry(-ry) * Rx(-rx) * (0, 0, -1)
        v = np.array([0.0, -np.sin(rx), -np.cos(rx)])
        return np.array([np.cos(ry) * v[0] - np.sin(ry) * v[2],
                         v[1],
                         np.sin(ry) * v[0] + np.cos(ry) * v[2]])

    def _bind_texture_for_raw_id(self, raw_id: int) -> bool:
        """Bind the GL texture that corresponds to a raw tex_id. Returns True on success."""
        idx = self._tex_id_to_index.get(raw_id, 0)
        if idx < len(self._gl_textures):
            glBindTexture(GL_TEXTURE_2D, self._gl_textures[idx])
            return True
        else:
            # Debug: print missing texture IDs once
            if not hasattr(self, '_missing_tex_logged'):
                print(f"Warning: No texture for raw_id {raw_id}, idx={idx}, available textures={len(self._gl_textures)}")
                self._missing_tex_logged = True
            return False

    def _draw_textured_triangles(self):
        """Draw triangles with PSX-style per-face backface culling."""
        if not self.triangles_uv:
            return

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        # Discard fully transparent texels like the PSX does (a texel whose
        # CLUT word is 0x0000 is not rasterized at all). Without this, keyed
        # texels still write the depth buffer and punch "black" holes that
        # occlude the geometry behind the cutout.
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.5)
        glDisable(GL_CULL_FACE)  # we cull in software (winding-independent)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        # Per-face backface cull comes from the one vectorized pass in paintGL
        # (_recompute_cull_masks); True = drop this face this frame.
        cull = self._tri_cull_mask

        # Batch consecutive same-texture triangles into one glBegin/glEnd instead of one
        # per triangle: glBegin(GL_TRIANGLES) with 3N vertices draws the same N triangles,
        # so output is identical but the per-primitive call overhead (the immediate-mode
        # bottleneck) is cut sharply - noticeable when many triangles share a texture.
        # depth_bias joins the batch key alongside the texture: glPolygonOffset, like
        # texture binding, only takes effect outside glBegin/glEnd.
        current_batch_key = None
        batch_open = False
        for i, (indices, uvs, raw_id, depth_bias) in enumerate(self.triangles_uv):
            if cull is not None and cull[i]:
                continue
            verts = [self.vertices_array[idx] for idx in indices]
            batch_key = (raw_id, depth_bias)
            if batch_key != current_batch_key:
                if batch_open:
                    glEnd()
                self._bind_texture_for_raw_id(raw_id)  # only allowed outside glBegin/glEnd
                glPolygonOffset(0.0, self._depth_bias_offset_units(depth_bias))
                current_batch_key = batch_key
                glBegin(GL_TRIANGLES)
                batch_open = True
            for i in range(3):
                u, v = uvs[i]
                # wrap only above 1.0: exactly 1.0 is a texture border, not 0
                if u > 1.0:
                    u = u - int(u)
                if v > 1.0:
                    v = v - int(v)
                glTexCoord2f(u, v)
                glVertex3f(verts[i][0], verts[i][1], verts[i][2])
        if batch_open:
            glEnd()

        glDisable(GL_ALPHA_TEST)
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(0.0, 0.0)

    _DEPTH_BIAS_UNIT = 2.0  # glPolygonOffset units per depth_bias step (-8..7)

    def _depth_bias_offset_units(self, depth_bias):
        """Map a face's parsed depth_bias (top nibble of its first vertex index,
        neutral=8 already subtracted so this is -8..7) to glPolygonOffset units.

        The PSX renderer has no Z-buffer - it sorts whole polygons into priority
        buckets (an ordering table) and this per-face bias nudges a polygon's
        bucket, e.g. to force a decal to draw after (on top of) the surface
        it sits on. This viewer uses a real depth buffer instead, so the same
        intent is reproduced by nudging the written depth: positive bias (assumed
        higher priority => drawn later/on top) moves the fragment closer to the
        camera so it wins the depth test against the coincident base surface."""
        return -float(depth_bias) * self._DEPTH_BIAS_UNIT

    def _calculate_triangle_normal(self, verts):
        """Calculate normal vector for a triangle"""
        # Get two edges of the triangle
        v1 = np.array(verts[1]) - np.array(verts[0])
        v2 = np.array(verts[2]) - np.array(verts[0])

        # Cross product gives perpendicular vector
        normal = np.cross(v1, v2)

        # Normalize to unit length
        norm = np.linalg.norm(normal)
        if norm > 0:
            normal = normal / norm

        return normal

    def _calculate_triangle_normal_fast(self, verts):
        """Fast normal calculation without numpy for triangles"""
        # Get two edges of the triangle
        # Edge 1: from vertex 0 to vertex 1
        ax = verts[1][0] - verts[0][0]
        ay = verts[1][1] - verts[0][1]
        az = verts[1][2] - verts[0][2]

        # Edge 2: from vertex 0 to vertex 2
        bx = verts[2][0] - verts[0][0]
        by = verts[2][1] - verts[0][1]
        bz = verts[2][2] - verts[0][2]

        # Cross product to get normal
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx

        # Normalize to unit length
        length = (nx * nx + ny * ny + nz * nz) ** 0.5
        if length > 0:
            nx /= length
            ny /= length
            nz /= length

        return np.array([nx, ny, nz])

    def _draw_textured_quads(self):
        """Draw quads with PSX-style per-face backface culling."""
        if not self.quads_uv:
            return

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        # Discard fully transparent texels (see _draw_textured_triangles)
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.5)
        glDisable(GL_CULL_FACE)  # we cull in software (winding-independent)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        cull = self._quad_cull_mask

        # Batch consecutive same-texture quads (each as two triangles) into one glBegin/
        # glEnd, same as the triangle path above. depth_bias joins the batch key (see
        # _draw_textured_triangles).
        current_batch_key = None
        batch_open = False
        for i, (indices, uvs, raw_id, depth_bias) in enumerate(self.quads_uv):
            if cull is not None and cull[i]:
                continue
            verts = [self.vertices_array[idx] for idx in indices]
            batch_key = (raw_id, depth_bias)
            if batch_key != current_batch_key:
                if batch_open:
                    glEnd()
                self._bind_texture_for_raw_id(raw_id)
                glPolygonOffset(0.0, self._depth_bias_offset_units(depth_bias))
                current_batch_key = batch_key
                glBegin(GL_TRIANGLES)
                batch_open = True
            # Draw quad as two triangles (perimeter order A, B, D / A, C, D)
            for i in (0, 1, 3, 0, 2, 3):
                glTexCoord2f(uvs[i][0], uvs[i][1])
                glVertex3f(verts[i][0], verts[i][1], verts[i][2])
        if batch_open:
            glEnd()

        glDisable(GL_ALPHA_TEST)
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(0.0, 0.0)

    def _draw_colored_faces(self):
        """Draw the colored (untextured) primitive lists with their flat RGB color."""
        if not self.colored_triangles and not self.colored_quads:
            return

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_POLYGON_OFFSET_FILL)

        view_dir = self._view_direction_model()
        face_count = {}
        for indices, _, _ in self.colored_triangles + self.colored_quads:
            face_key = frozenset(indices)
            face_count[face_key] = face_count.get(face_key, 0) + 1

        for indices, rgb, depth_bias in self.colored_triangles:
            verts = [self.vertices_array[idx] for idx in indices]
            if self._should_cull_backface(verts, face_count[frozenset(indices)], view_dir):
                continue
            glColor3f(*rgb)
            glPolygonOffset(0.0, self._depth_bias_offset_units(depth_bias))
            glBegin(GL_TRIANGLES)
            for v in verts:
                glVertex3f(v[0], v[1], v[2])
            glEnd()

        for indices, rgb, depth_bias in self.colored_quads:
            verts = [self.vertices_array[idx] for idx in indices]
            if self._should_cull_backface(verts, face_count[frozenset(indices)], view_dir):
                continue
            glColor3f(*rgb)
            glPolygonOffset(0.0, self._depth_bias_offset_units(depth_bias))
            # Same perimeter order as textured quads (A, B, D / A, C, D)
            glBegin(GL_TRIANGLES)
            for i in (0, 1, 3, 0, 2, 3):
                glVertex3f(verts[i][0], verts[i][1], verts[i][2])
            glEnd()

        glColor4f(1.0, 1.0, 1.0, 1.0)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(0.0, 0.0)

    def _calculate_quad_normal(self, verts):
        """Calculate normal for a quad"""
        # Use first triangle to determine normal
        v1 = np.array(verts[1]) - np.array(verts[0])
        v2 = np.array(verts[2]) - np.array(verts[0])
        normal = np.cross(v1, v2)
        norm = np.linalg.norm(normal)
        if norm > 0:
            normal = normal / norm
        return normal

    def draw_skeleton(self):
        """Draw bones with selected bone highlighted."""
        glDisable(GL_DEPTH_TEST)

        # First, draw ALL bones in yellow
        glLineWidth(3.0)
        glColor3f(1.0, 0.9, 0.1)
        glBegin(GL_LINES)
        for line in self.skeleton_lines:
            if line is not None:
                start, end = line
                glVertex3f(start[0], start[1], start[2])
                glVertex3f(end[0], end[1], end[2])
        glEnd()

        # Draw all regular joint dots (small, orange)
        glPointSize(6.0)
        glColor3f(1.0, 0.45, 0.1)
        glBegin(GL_POINTS)
        for line in self.skeleton_lines:
            if line is not None:
                start, end = line
                glVertex3f(start[0], start[1], start[2])
                glVertex3f(end[0], end[1], end[2])
        glEnd()

        # Highlight the root bone joint (parent = 0xFFFF) in bright green
        if hasattr(self, 'bone_parents'):
            # Find the root bone(s) - bones with parent_id = 0xFFFF
            root_bones = []
            for bone_idx, parent_id in enumerate(self.bone_parents):
                if parent_id == 0xFFFF:
                    root_bones.append(bone_idx)

            # For each root bone, find its position
            for root_idx in root_bones:
                # Check if this root bone has a line (it shouldn't, but let's be safe)
                if root_idx < len(self.skeleton_lines) and self.skeleton_lines[root_idx] is not None:
                    start, end = self.skeleton_lines[root_idx]
                    # Draw green dot at the start (parent position) of the first child
                    glPointSize(14.0)
                    glColor3f(0.2, 0.8, 0.2)  # Bright green
                    glBegin(GL_POINTS)
                    glVertex3f(start[0], start[1], start[2])
                    glEnd()

                    # Add a glow effect
                    glEnable(GL_BLEND)
                    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                    glPointSize(20.0)
                    glColor4f(0.2, 0.9, 0.2, 0.5)  # Semi-transparent green
                    glBegin(GL_POINTS)
                    glVertex3f(start[0], start[1], start[2])
                    glEnd()
                    glDisable(GL_BLEND)
                else:
                    # Root bone has no line, find its position from its children
                    for bone_idx, line in enumerate(self.skeleton_lines):
                        if line is not None and bone_idx < len(self.bone_parents):
                            if self.bone_parents[bone_idx] == root_idx:
                                start, end = line
                                # Draw green dot at the start (parent position)
                                glPointSize(14.0)
                                glColor3f(0.2, 0.8, 0.2)
                                glBegin(GL_POINTS)
                                glVertex3f(start[0], start[1], start[2])
                                glEnd()

                                # Add glow effect
                                glEnable(GL_BLEND)
                                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                                glPointSize(20.0)
                                glColor4f(0.2, 0.9, 0.2, 0.5)
                                glBegin(GL_POINTS)
                                glVertex3f(start[0], start[1], start[2])
                                glEnd()
                                glDisable(GL_BLEND)
                                break

        # Highlight every selected bone's end joint. The primary (last-clicked, drag/gizmo target)
        # is bright red; the other Ctrl-selected bones are orange, so the comparison target stands
        # out from the bones merely being compared alongside it.
        for sel in (self.selected_bones or ([self.selected_bone] if self.selected_bone >= 0 else [])):
            if not (0 <= sel < len(self.skeleton_lines)):
                continue
            selected_line = self.skeleton_lines[sel]
            if selected_line is None:
                continue
            start, end = selected_line
            is_primary = (sel == self.selected_bone)
            r, g, b = (1.0, 0.2, 0.2) if is_primary else (1.0, 0.6, 0.1)

            # Draw larger dot at the end point (child joint)
            glPointSize(12.0 if is_primary else 10.0)
            glColor3f(r, g, b)
            glBegin(GL_POINTS)
            glVertex3f(end[0], end[1], end[2])
            glEnd()

            # Add glow effect
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glPointSize(18.0 if is_primary else 15.0)
            glColor4f(r, g, b, 0.5)
            glBegin(GL_POINTS)
            glVertex3f(end[0], end[1], end[2])
            glEnd()
            glDisable(GL_BLEND)

        # Also highlight the line(s) where selected bone is the parent
        if hasattr(self, 'bone_parents') and 0 <= self.selected_bone < len(self.bone_parents):
            for bone_idx, line in enumerate(self.skeleton_lines):
                if line is not None:
                    # Check if this bone's parent is the selected bone
                    if bone_idx < len(self.bone_parents) and self.bone_parents[bone_idx] == self.selected_bone:
                        start, end = line
                        # Draw thick red line
                        glLineWidth(8.0)
                        glColor3f(1.0, 0.0, 0.0)
                        glBegin(GL_LINES)
                        glVertex3f(start[0], start[1], start[2])
                        glVertex3f(end[0], end[1], end[2])
                        glEnd()

        glEnable(GL_DEPTH_TEST)

    def draw_quads(self):
        """Draw quads using both diagonals to handle non-planar surfaces"""

        glColor3f(*self.face_color)

        for quad_idx, quad in enumerate(self.quads):
            i0, i1, i2, i3 = quad
            v0 = self.vertices_array[i0]
            v1 = self.vertices_array[i1]
            v2 = self.vertices_array[i2]
            v3 = self.vertices_array[i3]


            # First diagonal
            glBegin(GL_TRIANGLES)
            glVertex3f(v0[0], v0[1], v0[2])
            glVertex3f(v1[0], v1[1], v1[2])
            glVertex3f(v2[0], v2[1], v2[2])
            glVertex3f(v0[0], v0[1], v0[2])
            glVertex3f(v2[0], v2[1], v2[2])
            glVertex3f(v3[0], v3[1], v3[2])
            glEnd()

            # Second diagonal ()
            glColor3f(*self.face_color)
            glBegin(GL_TRIANGLES)
            glVertex3f(v1[0], v1[1], v1[2])
            glVertex3f(v2[0], v2[1], v2[2])
            glVertex3f(v3[0], v3[1], v3[2])
            glVertex3f(v1[0], v1[1], v1[2])
            glVertex3f(v3[0], v3[1], v3[2])
            glVertex3f(v0[0], v0[1], v0[2])
            glEnd()

    def draw_wireframe(self):
        glColor3f(0.9, 0.9, 0.9)
        glLineWidth(1.0)

        for tri in self.triangles:
            glBegin(GL_LINE_LOOP)
            for idx in tri:
                v = self.vertices_array[idx]
                glVertex3f(v[0], v[1], v[2])
            glEnd()

        for quad in self.quads:
            i0, i1, i2, i3 = quad
            v0 = self.vertices_array[i0]
            v1 = self.vertices_array[i1]
            v2 = self.vertices_array[i2]
            v3 = self.vertices_array[i3]
            glBegin(GL_LINE_LOOP)
            glVertex3f(v0[0], v0[1], v0[2])
            glVertex3f(v1[0], v1[1], v1[2])
            glVertex3f(v2[0], v2[1], v2[2])
            glVertex3f(v3[0], v3[1], v3[2])
            glEnd()

    def draw_axis(self):
        c = self.MODEL_CENTER
        length = self.MODEL_SIZE * 1.2

        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 0.2, 0.2)
        glVertex3f(c[0] - length, c[1], c[2])
        glVertex3f(c[0] + length, c[1], c[2])
        glColor3f(0.2, 1.0, 0.2)
        glVertex3f(c[0], c[1] - length, c[2])
        glVertex3f(c[0], c[1] + length, c[2])
        glColor3f(0.2, 0.2, 1.0)
        glVertex3f(c[0], c[1], c[2] - length)
        glVertex3f(c[0], c[1], c[2] + length)
        glEnd()

    # ------------------------------------------------------------------
    # Mouse picking of skeleton joints
    # ------------------------------------------------------------------
    def _pick_transform(self):
        """Snapshot as (modelview, projection, viewport) numpy arrays, or None.

        GL matrices come out column-major: element (row, col) sits at [col][row],
        so a point is transformed as the row vector `v @ matrix`.
        """
        if self._pick_modelview is None or self._pick_projection is None \
                or self._pick_viewport is None:
            return None
        try:
            modelview = np.asarray(self._pick_modelview, dtype=np.float64).reshape(4, 4)
            projection = np.asarray(self._pick_projection, dtype=np.float64).reshape(4, 4)
            viewport = np.asarray(self._pick_viewport, dtype=np.float64).reshape(4)
        except Exception:
            return None
        if viewport[2] == 0 or viewport[3] == 0:
            return None
        return modelview, projection, viewport

    def _project(self, point):
        """gluProject, in plain numpy: model space -> GL window coordinates.

        Done by hand rather than through GLU because libGLU is missing on many
        Linux setups (and on CI), where every glu* call raises and picking would
        silently answer 'nothing here'.
        """
        transform = self._pick_transform()
        if transform is None:
            return None
        modelview, projection, viewport = transform
        clip = np.array([point[0], point[1], point[2], 1.0], dtype=np.float64) @ modelview @ projection
        if abs(clip[3]) < 1e-12:
            return None
        ndc = clip[:3] / clip[3]
        return (viewport[0] + viewport[2] * (ndc[0] + 1.0) / 2.0,
                viewport[1] + viewport[3] * (ndc[1] + 1.0) / 2.0,
                (ndc[2] + 1.0) / 2.0)

    def _unproject(self, win_x, win_y, win_z):
        """gluUnProject, in plain numpy: GL window coordinates -> model space."""
        transform = self._pick_transform()
        if transform is None:
            return None
        modelview, projection, viewport = transform
        ndc = np.array([2.0 * (win_x - viewport[0]) / viewport[2] - 1.0,
                        2.0 * (win_y - viewport[1]) / viewport[3] - 1.0,
                        2.0 * win_z - 1.0,
                        1.0], dtype=np.float64)
        try:
            inverse = np.linalg.inv(modelview @ projection)
        except np.linalg.LinAlgError:
            return None
        obj = ndc @ inverse
        if abs(obj[3]) < 1e-12:
            return None
        return obj[:3] / obj[3]

    def _project_joint(self, point):
        """Project a model-space point to logical widget coordinates.
        Returns (x, y, depth) or None if no transform snapshot exists yet."""
        if self._pick_modelview is None:
            return None
        win = self._project(point)
        if win is None:
            return None
        dpr = self.devicePixelRatioF()
        # GL windows coords are in physical pixels with the origin bottom-left;
        # Qt events are in logical pixels with the origin top-left
        x = win[0] / dpr
        y = (self._pick_viewport[3] - win[1]) / dpr
        return x, y, win[2]

    def _joint_candidates(self):
        """bone_id -> model-space joint position. A bone's joint is the end of
        its line; a root bone (no line) uses the start of any child's line."""
        joints = {}
        for bone_id, line in enumerate(self.skeleton_lines):
            if line is None:
                continue
            joints[bone_id] = line[1]
            if bone_id < len(self.bone_parents):
                parent_id = self.bone_parents[bone_id]
                if (0 <= parent_id < len(self.skeleton_lines)
                        and self.skeleton_lines[parent_id] is None
                        and parent_id not in joints):
                    joints[parent_id] = line[0]
        return joints

    def _pick_joint(self, x, y):
        """Return the bone id whose joint is nearest to the widget position
        (x, y) within PICK_RADIUS_PX, or -1. Overlapping joints resolve to the
        one closest to the camera."""
        candidates = []
        for bone_id, pos in self._joint_candidates().items():
            proj = self._project_joint(pos)
            if proj is None or not (0.0 <= proj[2] <= 1.0):
                continue
            dist = ((proj[0] - x) ** 2 + (proj[1] - y) ** 2) ** 0.5
            if dist <= self.PICK_RADIUS_PX:
                candidates.append((dist, proj[2], bone_id))
        if not candidates:
            return -1
        # Bucket screen distances so joints drawn on top of each other are
        # decided by depth rather than a sub-pixel 2D difference
        return min(candidates, key=lambda c: (round(c[0] / 6), c[1]))[2]

    def _world_units_per_pixel(self):
        """Approximate model-space size of one logical pixel at the model's
        distance (45 deg vertical fov, see resizeGL)."""
        h = max(1, self.height())
        return (2.0 * max(self.zoom, 1e-3) * math.tan(math.radians(22.5))) / h

    # ------------------------------------------------------------------
    # Rotation gizmo
    # ------------------------------------------------------------------
    def set_rotation_gizmo(self, center, axes):
        """Show the rotation rings at `center` with the given 3 axis vectors,
        or hide them (center=None)."""
        self.gizmo_center = center
        self.gizmo_axes = axes
        self.update()

    @staticmethod
    def _axis_basis(axis):
        """Right-handed orthonormal basis (u, v, a) with u x v = a: the ring
        lies in the (u, v) plane and increasing atan2(w.v, w.u) is a positive
        rotation around the axis."""
        a = np.array(axis, dtype=np.float64)
        a /= max(np.linalg.norm(a), 1e-9)
        helper = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        u = np.cross(helper, a)
        u /= max(np.linalg.norm(u), 1e-9)
        v = np.cross(a, u)
        return a, u, v

    def _gizmo_world_radius(self):
        """Ring radius in WORLD units: a fixed fraction of the model size, so the handle is part
        of the 3D scene - it grows on screen as you zoom in and shrinks as you zoom out. Floored
        so a tiny model still gets a usable handle."""
        return max(self.MODEL_SIZE, 1e-3) * self.GIZMO_WORLD_FRACTION

    def _gizmo_ring_points(self, axis):
        radius = self._gizmo_world_radius()
        center = np.array(self.gizmo_center, dtype=np.float64)
        _, u, v = self._axis_basis(axis)
        points = []
        for s in range(self.GIZMO_SEGMENTS):
            t = 2.0 * math.pi * s / self.GIZMO_SEGMENTS
            points.append(center + radius * (math.cos(t) * u + math.sin(t) * v))
        return points

    def draw_rotation_gizmo(self):
        if self.gizmo_center is None or not self.gizmo_axes:
            return
        glDisable(GL_DEPTH_TEST)
        for i, axis in enumerate(self.gizmo_axes):
            if i == self._gizmo_active_axis:
                glLineWidth(5.0)
                glColor3f(1.0, 1.0, 0.4)
            else:
                glLineWidth(2.5)
                glColor3f(*self.GIZMO_COLORS[i])
            glBegin(GL_LINE_LOOP)
            for p in self._gizmo_ring_points(axis):
                glVertex3f(p[0], p[1], p[2])
            glEnd()
        glLineWidth(1.0)
        glEnable(GL_DEPTH_TEST)

    def _pick_gizmo_axis(self, x, y):
        """Ring under the widget position (x, y), or -1."""
        if self.gizmo_center is None or not self.gizmo_axes:
            return -1
        best_axis, best_dist = -1, None
        for i, axis in enumerate(self.gizmo_axes):
            for p in self._gizmo_ring_points(axis):
                proj = self._project_joint(tuple(p))
                if proj is None:
                    return -1
                dist = ((proj[0] - x) ** 2 + (proj[1] - y) ** 2) ** 0.5
                if best_dist is None or dist < best_dist:
                    best_axis, best_dist = i, dist
        if best_dist is not None and best_dist <= self.GIZMO_PICK_TOLERANCE_PX:
            return best_axis
        return -1

    def _mouse_ray(self, x, y):
        """Model-space ray under the widget position: (origin, unit direction)."""
        if self._pick_modelview is None:
            return None
        dpr = self.devicePixelRatioF()
        win_x = x * dpr
        win_y = self._pick_viewport[3] - y * dpr
        p0 = self._unproject(win_x, win_y, 0.0)
        p1 = self._unproject(win_x, win_y, 1.0)
        if p0 is None or p1 is None:
            return None
        direction = p1 - p0
        norm = np.linalg.norm(direction)
        if norm < 1e-9:
            return None
        return p0, direction / norm

    def _gizmo_angle(self, x, y):
        """Angle (degrees) of the mouse around the active gizmo axis. Positive
        = positive rotation around the axis (right-hand rule)."""
        axis = self.gizmo_axes[self._gizmo_active_axis]
        a, u, v = self._axis_basis(axis)
        center = np.array(self.gizmo_center, dtype=np.float64)

        if self._gizmo_use_plane:
            ray = self._mouse_ray(x, y)
            if ray is not None:
                origin, direction = ray
                denom = float(np.dot(direction, a))
                if abs(denom) > 1e-6:
                    t = float(np.dot(center - origin, a)) / denom
                    w = (origin + t * direction) - center
                    return math.degrees(math.atan2(float(np.dot(w, v)), float(np.dot(w, u))))

        # Edge-on ring (or unproject failure): angle around the projected
        # center in screen space. Qt's y axis points down, which mirrors the
        # apparent rotation; the axis facing decides the final sign.
        projected = self._project_joint(tuple(center))
        if projected is None:
            return None
        theta = math.degrees(math.atan2(y - projected[1], x - projected[0]))
        facing = 1.0
        eye = getattr(self, '_eye_model', None)
        if eye is not None:
            facing = 1.0 if float(np.dot(np.asarray(eye) - center, a)) > 0.0 else -1.0
        return -theta * facing

    def _start_rotation_drag(self, axis_index, x, y):
        self._gizmo_active_axis = axis_index
        # Choose the angle method once per drag so it cannot jump mid-drag:
        # ray-plane when the ring faces the camera enough, else screen angle
        a, _, _ = self._axis_basis(self.gizmo_axes[axis_index])
        center = np.array(self.gizmo_center, dtype=np.float64)
        eye = getattr(self, '_eye_model', None)
        if eye is not None:
            view = center - np.asarray(eye)
            norm = np.linalg.norm(view)
            self._gizmo_use_plane = norm > 1e-9 and abs(float(np.dot(view / norm, a))) > 0.3
        else:
            self._gizmo_use_plane = True
        angle = self._gizmo_angle(x, y)
        self._gizmo_last_angle = angle if angle is not None else 0.0
        self._gizmo_total_deg = 0.0
        self.last_mouse_x = x
        self.last_mouse_y = y
        self.update()

    def _selected_bone_axis_screen_dir(self):
        """Screen direction in which the selected bone extends when it gets
        longer: towards its children's joints (a bone's length positions its
        CHILDREN along its own axis — the line ending at the selected joint
        belongs to the parent's axis and does not move with this length)."""
        sel = self.selected_bone
        dirs = []
        for bone_id, line in enumerate(self.skeleton_lines):
            if line is None or bone_id >= len(self.bone_parents):
                continue
            if self.bone_parents[bone_id] != sel:
                continue
            p0 = self._project_joint(line[0])
            p1 = self._project_joint(line[1])
            if p0 is not None and p1 is not None:
                dirs.append((p1[0] - p0[0], p1[1] - p0[1]))
        if not dirs and 0 <= sel < len(self.skeleton_lines) and self.skeleton_lines[sel] is not None:
            # Leaf bone (length has no visible effect): follow the parent's
            # axis so the drag still behaves consistently
            p0 = self._project_joint(self.skeleton_lines[sel][0])
            p1 = self._project_joint(self.skeleton_lines[sel][1])
            if p0 is not None and p1 is not None:
                dirs.append((p1[0] - p0[0], p1[1] - p0[1]))
        if dirs:
            dx = sum(d[0] for d in dirs)
            dy = sum(d[1] for d in dirs)
            norm = (dx * dx + dy * dy) ** 0.5
            if norm > 5.0:
                return dx / norm, dy / norm
        return None

    def _start_length_drag(self, x, y):
        """Begin a Shift+drag that changes the selected bone's length. Movement
        along the bone's screen direction = longer, against it = shorter."""
        direction = self._selected_bone_axis_screen_dir()
        if direction is None:
            # Bone points at the camera: fall back to "drag up = longer"
            direction = (0.0, -1.0)
        self._length_drag = True
        self._length_drag_dir = direction
        self._length_drag_total = 0.0
        self.last_mouse_x = x
        self.last_mouse_y = y

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)   # clicking the view takes keyboard focus
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = (pos.x(), pos.y())
            # Root bones have no line of their own but do have a length (it
            # places their children), so any valid selection can be dragged.
            # Shift+drag changes bone length (Ctrl is reserved for multi-select).
            if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    and self.show_skeleton and self.is_edit_allowed()
                    and 0 <= self.selected_bone < len(self.skeleton_lines)):
                self._start_length_drag(pos.x(), pos.y())
                return
            # Grab a rotation ring of the gizmo (only when it's actually shown - a hidden gizmo
            # must be inert, not an invisible click target that still rotates the bone)
            if self.show_gizmo and self.show_skeleton and self.is_edit_allowed():
                axis_index = self._pick_gizmo_axis(pos.x(), pos.y())
                if axis_index >= 0:
                    self._start_rotation_drag(axis_index, pos.x(), pos.y())
                    return
            self.left_button_down = True
            self.last_mouse_x = pos.x()
            self.last_mouse_y = pos.y()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_down = True
            self.last_mouse_x = pos.x()
            self.last_mouse_y = pos.y()

    def mouseMoveEvent(self, event):
        if self.last_mouse_x is None:
            return

        dx = event.position().x() - self.last_mouse_x
        dy = event.position().y() - self.last_mouse_y

        if self._length_drag:
            step = dx * self._length_drag_dir[0] + dy * self._length_drag_dir[1]
            self._length_drag_total += step * self._world_units_per_pixel()
            self.bone_length_dragged.emit(self._length_drag_total)

        elif self._gizmo_active_axis >= 0:
            angle = self._gizmo_angle(event.position().x(), event.position().y())
            if angle is not None:
                delta = angle - self._gizmo_last_angle
                delta = (delta + 180.0) % 360.0 - 180.0  # shortest way round
                self._gizmo_total_deg += delta
                self._gizmo_last_angle = angle
                self.bone_rotation_dragged.emit(self._gizmo_active_axis, self._gizmo_total_deg)

        elif self.left_button_down:
            self.rot_y += dx * 0.5
            self.rot_x += dy * 0.5

        elif self.right_button_down:
            # One pixel of mouse motion = one pixel of on-screen model motion
            pan_speed = self._world_units_per_pixel()
            self.pan_x += dx * pan_speed
            self.pan_y -= dy * pan_speed

        self.last_mouse_x = event.position().x()
        self.last_mouse_y = event.position().y()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._length_drag:
                self._length_drag = False
                self.bone_length_drag_finished.emit()
            elif self._gizmo_active_axis >= 0:
                self._gizmo_active_axis = -1
                self.bone_rotation_drag_finished.emit()
                self.update()
            elif self._press_pos is not None and self.show_skeleton:
                dx = event.position().x() - self._press_pos[0]
                dy = event.position().y() - self._press_pos[1]
                if dx * dx + dy * dy <= self.CLICK_SLOP_PX ** 2:
                    bone_id = self._pick_joint(event.position().x(), event.position().y())
                    if bone_id >= 0:
                        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                        self.bone_picked.emit(bone_id, additive)
            self._press_pos = None
            self.left_button_down = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_down = False
        self.last_mouse_x = None
        self.last_mouse_y = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120
        self.zoom -= delta * self.zoom * 0.1
        # Allow zooming out much further (up to 10x model size)
        min_zoom = self.MODEL_SIZE * 0.3  # Can zoom in closer
        max_zoom = self.MODEL_SIZE * 10.0  # Can zoom out much further
        self.zoom = max(min_zoom, min(max_zoom, self.zoom))
        self.update()

    def reset_view(self):
        """Reset camera to default position - adaptive zoom based on shape"""
        self.rot_x = 0
        self.rot_y = 180

        # No geometry (empty placeholder model): keep a neutral default zoom rather than
        # reducing an empty vertex array (numpy .min()/.max() raise on zero-size).
        if len(self.vertices) == 0:
            self.zoom = self.MODEL_SIZE * 1.5
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.update()
            return

        # Calculate bounding box dimensions
        bbox_min = self.vertices_array.min(axis=0)
        bbox_max = self.vertices_array.max(axis=0)
        bbox_size = bbox_max - bbox_min

        # Find the largest and smallest dimensions
        max_dim = max(bbox_size)
        min_dim = min(bbox_size)

        # Calculate aspect ratio (how elongated the shape is)
        # If min_dim is very small, aspect_ratio will be large (cone shape)
        aspect_ratio = max_dim / max(min_dim, 0.001)  # Avoid division by zero

        # Adjust zoom factor based on aspect ratio
        # Normal shapes (aspect_ratio ~1-2): use 1.5x zoom
        # Elongated shapes (aspect_ratio >3): use up to 3.5x zoom
        if aspect_ratio > 3:
            zoom_factor = 3.5  # Cone shape - zoom out more
        elif aspect_ratio > 2:
            zoom_factor = 2.5  # Moderately elongated
        else:
            zoom_factor = 1.5  # Normal compact shape

        # Use the maximum dimension for the base distance
        self.zoom = max_dim * zoom_factor

        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def set_show_triangles(self, show):
        self.show_triangles = show
        self.update()

    def set_show_quads(self, show):
        self.show_quads = show
        self.update()

    def set_show_wireframe(self, show):
        self.show_wireframe = show
        self.update()

    def set_show_axis(self, show):
        self.show_axis = show
        self.update()
