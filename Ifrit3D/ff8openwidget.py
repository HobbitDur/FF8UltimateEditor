from typing import List

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

class FF8OpenGLWidget(QOpenGLWidget):
    """
    FF8 Monster Viewer Widget - Reusable PyQt Widget
    """
    def __init__(self, parent=None):
        self.face_color = (0.45, 0.65, 0.95)
        self.raw_vertices = []
        self.set_vertices([(0,0,0)])
        self.skeleton_lines = []  # List of (start, end) or None
        self.bone_parents = []  # List of parent IDs for each bone
        self.selected_bone = -1
        self.model_translation = [0.0, 0.0, 0.0]
        self.reference_position  = [0.0, 0.0, 0.0]
        self.triangles = []
        self.quads =[]
        self.skeleton_lines = []

        # --- NEW: UV / texture state ---
        self.triangles_uv = []   # list of (indices_tuple, uvs_tuple, raw_tex_id)
        self.quads_uv = []       # list of (indices_tuple, uvs_tuple, raw_tex_id)
        self._pending_qpixmaps = []   # QPixmaps waiting to be uploaded
        self._gl_textures = []        # list of GL texture IDs (after upload)
        self._tex_id_to_index = {}    # raw tex_id → _gl_textures index
        self.show_texture = False
        self._textures_dirty = False
        super().__init__(parent)

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

        # Display options
        self.show_triangles = True
        self.show_quads = True
        self.show_wireframe = False
        self.show_axis = False
        self.show_texture = True
        self.show_skeleton = False

        self.back_face_offset = -0.003  # Smaller offset for triangles
        self.triangle_cache = {}  # Cache for back face offsets per fra

    def set_texture_pixmaps(self, qpixmaps: list, tex_ids_used: list):
        """Call this from outside with a list of QPixmaps..."""
        self._free_gl_textures()
        self._pending_qpixmaps = list(qpixmaps)
        self._tex_id_to_index = {}

        unique_ids = sorted(set(tex_ids_used))
        n = len(qpixmaps)

        for rank, raw_id in enumerate(unique_ids):
            idx = min(rank, n - 1)
            self._tex_id_to_index[raw_id] = idx

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

            # Process RGBA data: for each pixel, if RGB is 0, set alpha to 0
            for i in range(0, len(data), 4):
                if data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 0:
                    data[i + 3] = 0  # Set alpha to 0

            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)

            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
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
        """data: list of (indices_tuple, uvs_tuple, raw_tex_id)"""
        self.triangles_uv = data

    def set_quads_with_uv(self, data: list):
        """data: list of (indices_tuple, uvs_tuple, raw_tex_id)"""
        self.quads_uv = data

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
        self.update()

    def set_vertices(self, vertices:list):
        self.vertices = vertices
        self.vertices_array = np.array(self.vertices, dtype=np.float32)

        MIN_BOUNDS = self.vertices_array.min(axis=0)
        MAX_BOUNDS = self.vertices_array.max(axis=0)
        self.MODEL_CENTER = (MIN_BOUNDS + MAX_BOUNDS) / 2
        self.MODEL_SIZE = np.linalg.norm(MAX_BOUNDS - MIN_BOUNDS)

    def set_show_skeleton(self, show: bool):
        self.show_skeleton = show
        self.update()

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
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def set_reference_position(self, x: float, y: float, z: float):
        """Set the reference position (frame 0 position) that camera centers on"""
        self.reference_position = [x, y, z]
        self.update()

    def paintGL(self):
        if self._textures_dirty and self._pending_qpixmaps:
            self._upload_pending_textures()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        # Pull camera back
        glTranslatef(self.pan_x, self.pan_y, -self.zoom)

        # Orbit rotations — no up-vector flip issue
        glRotatef(self.rot_x, 1.0, 0.0, 0.0)
        glRotatef(self.rot_y, 0.0, 1.0, 0.0)

        # Center on model
        glTranslatef(-self.reference_position[0], -self.reference_position[1], -self.reference_position[2])

        # Apply frame position translation
        glTranslatef(self.model_translation[0], self.model_translation[1], self.model_translation[2])

        if self.show_axis:
            self.draw_axis()
        if self.show_texture and self._gl_textures and (self.triangles_uv or self.quads_uv):
            self._draw_textured_triangles()
            self._draw_textured_quads()
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

        self.update()

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
        """Draw triangles - offset back faces based on camera direction"""
        if not self.triangles_uv:
            return

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        # Get camera direction (assuming camera looking along -Z in view space)
        # You may need to adjust this based on your camera setup
        camera_dir = np.array([0, 0, 1])  # Looking along positive Z

        # Count exact duplicates first
        face_count = {}
        for indices, _, _ in self.triangles_uv:
            face_key = frozenset(indices)
            face_count[face_key] = face_count.get(face_key, 0) + 1

        current_raw_id = None
        drawn_faces = {}

        for indices, uvs, raw_id in self.triangles_uv:
            if raw_id != current_raw_id:
                self._bind_texture_for_raw_id(raw_id)
                current_raw_id = raw_id

            face_key = frozenset(indices)
            drawn_faces[face_key] = drawn_faces.get(face_key, 0) + 1
            is_exact_duplicate = (face_count[face_key] > 1)
            is_first_occurrence = (drawn_faces[face_key] == 1)

            verts = [self.vertices_array[idx] for idx in indices]
            normal = self._calculate_triangle_normal_fast(verts)

            # Check if this is likely a back face (normal points away from camera)
            # For animated monsters, this helps detect which face should be offset
            #is_back_face_by_normal = np.dot(normal, camera_dir) < 0
            is_back_face_by_normal = False

            glBegin(GL_TRIANGLES)

            # Decide offset strategy
            if is_exact_duplicate and is_first_occurrence:
                # Exact duplicate - larger offset
                offset = -0.003
                apply_offset = True
            elif is_back_face_by_normal:
                # Detected back face - medium offset
                offset = -0.001
                apply_offset = False #False as I don't want to modify it (for mouth for example) but the code is interesting so I keep it
            else:
                apply_offset = False  # Enable to prevent Z-fighting

            for i in range(3):
                u, v = uvs[i]
                u = u - int(u)
                v = v - int(v)
                glTexCoord2f(u, v)

                if apply_offset:
                    glVertex3f(
                        verts[i][0] + normal[0] * offset,
                        verts[i][1] + normal[1] * offset,
                        verts[i][2] + normal[2] * offset
                    )
                else:
                    glVertex3f(verts[i][0], verts[i][1], verts[i][2])
            glEnd()

        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)

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
        """Draw quads - offset only when there's a matching front face"""
        if not self.quads_uv:
            return

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        # First pass: count occurrences of each face
        face_count = {}
        for indices, _, _ in self.quads_uv:
            face_key = frozenset(indices)
            face_count[face_key] = face_count.get(face_key, 0) + 1

        # Second pass: draw with offset only for duplicates
        current_raw_id = None
        drawn_faces = {}

        for indices, uvs, raw_id in self.quads_uv:
            if raw_id != current_raw_id:
                self._bind_texture_for_raw_id(raw_id)
                current_raw_id = raw_id

            face_key = frozenset(indices)
            drawn_faces[face_key] = drawn_faces.get(face_key, 0) + 1
            is_duplicate = (face_count[face_key] > 1)
            is_first_occurrence = (drawn_faces[face_key] == 1)

            verts = [self.vertices_array[idx] for idx in indices]

            # Get vertices with potential offset
            if is_duplicate and is_first_occurrence:
                # Back face of a duplicate - apply offset
                normal = self._calculate_quad_normal(verts)
                offset = -0.01
                draw_verts = [v + normal * offset for v in verts]
            else:
                # Normal case - no offset
                draw_verts = verts

            # Draw quad as two triangles
            glBegin(GL_TRIANGLES)
            # Triangle 1: A, B, D
            glTexCoord2f(uvs[0][0], uvs[0][1])
            glVertex3f(draw_verts[0][0], draw_verts[0][1], draw_verts[0][2])
            glTexCoord2f(uvs[1][0], uvs[1][1])
            glVertex3f(draw_verts[1][0], draw_verts[1][1], draw_verts[1][2])
            glTexCoord2f(uvs[3][0], uvs[3][1])
            glVertex3f(draw_verts[3][0], draw_verts[3][1], draw_verts[3][2])

            # Triangle 2: A, C, D
            glTexCoord2f(uvs[0][0], uvs[0][1])
            glVertex3f(draw_verts[0][0], draw_verts[0][1], draw_verts[0][2])
            glTexCoord2f(uvs[2][0], uvs[2][1])
            glVertex3f(draw_verts[2][0], draw_verts[2][1], draw_verts[2][2])
            glTexCoord2f(uvs[3][0], uvs[3][1])
            glVertex3f(draw_verts[3][0], draw_verts[3][1], draw_verts[3][2])
            glEnd()

        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)

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

        # Highlight the selected bone's end joint in bright red
        if 0 <= self.selected_bone < len(self.skeleton_lines):
            selected_line = self.skeleton_lines[self.selected_bone]
            if selected_line is not None:
                start, end = selected_line

                # Draw larger red dot at the end point (child joint)
                glPointSize(12.0)
                glColor3f(1.0, 0.2, 0.2)
                glBegin(GL_POINTS)
                glVertex3f(end[0], end[1], end[2])
                glEnd()

                # Add glow effect for selected bone
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                glPointSize(18.0)
                glColor4f(1.0, 0.2, 0.2, 0.5)
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down = True
            self.last_mouse_x = event.position().x()
            self.last_mouse_y = event.position().y()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_down = True
            self.last_mouse_x = event.position().x()
            self.last_mouse_y = event.position().y()

    def mouseMoveEvent(self, event):
        if self.last_mouse_x is None:
            return

        dx = event.position().x() - self.last_mouse_x
        dy = event.position().y() - self.last_mouse_y

        if self.left_button_down:
            self.rot_y += dx * 0.5
            self.rot_x += dy * 0.5

        elif self.right_button_down:
            pan_speed = self.zoom * 0.002 * self.MODEL_SIZE
            self.pan_x -= dx * pan_speed
            self.pan_y += dy * pan_speed

        self.last_mouse_x = event.position().x()
        self.last_mouse_y = event.position().y()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_down = False
        self.last_mouse_x = None
        self.last_mouse_y = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120
        self.zoom -= delta * self.zoom * 0.1
        self.zoom = max(self.MODEL_SIZE * 0.5, min(self.MODEL_SIZE * 3.0, self.zoom))
        self.update()

    def reset_view(self):
        """Reset camera to default position"""
        self.rot_x = 0
        self.rot_y = 180
        self.zoom = self.MODEL_SIZE * 1.5
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
