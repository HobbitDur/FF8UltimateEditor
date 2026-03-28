import numpy as np
from PyQt6.QtCore import Qt
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

        self.triangles = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]
        self.quads = [(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)]
        self.skeleton_lines = []
        self.show_skeleton = True
        super().__init__(parent)

        # Camera controls
        self.rot_x = 20.0
        self.rot_y = 30.0
        self.zoom = self.MODEL_SIZE * 1.5
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
        self.show_axis = True
        self.show_mesh = False

    def set_vertices(self, vertices:list):
        # self.VERTICES = [transform_vertex(v) for v in self.RAW_VERTICES_ORIGINAL]
        self.vertices = vertices
        self.vertices_array = np.array(self.vertices, dtype=np.float32)

        MIN_BOUNDS = self.vertices_array.min(axis=0)
        MAX_BOUNDS = self.vertices_array.max(axis=0)
        self.MODEL_CENTER = (MIN_BOUNDS + MAX_BOUNDS) / 2
        self.MODEL_SIZE = np.linalg.norm(MAX_BOUNDS - MIN_BOUNDS)

    def set_skeleton_lines(self, lines: list):
        self.skeleton_lines = lines

    def set_show_skeleton(self, show: bool):
        self.show_skeleton = show
        self.update()

    def set_show_mesh(self, show):
        self.show_mesh = show
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

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        import math
        rad_x = math.radians(self.rot_x)
        rad_y = math.radians(self.rot_y)
        cam_x = self.zoom * math.cos(rad_y) * math.cos(rad_x)
        cam_y = self.zoom * math.sin(rad_x)
        cam_z = self.zoom * math.sin(rad_y) * math.cos(rad_x)
        target_x = self.MODEL_CENTER[0] + self.pan_x
        target_y = self.MODEL_CENTER[1] + self.pan_y
        target_z = self.MODEL_CENTER[2]
        gluLookAt(cam_x, cam_y, cam_z,
                  target_x, target_y, target_z,
                  0.0, 1.0, 0.0)

        if self.show_axis:
            self.draw_axis()
        if self.show_mesh:
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

    def draw_skeleton(self):
        """Draw bones as yellow lines with orange joint dots."""
        glDisable(GL_DEPTH_TEST)  # draw on top of geometry
        glLineWidth(3.0)

        # Bone lines in yellow
        glColor3f(1.0, 0.9, 0.1)
        glBegin(GL_LINES)
        for start, end in self.skeleton_lines:
            glVertex3f(start[0], start[1], start[2])
            glVertex3f(end[0], end[1], end[2])
        glEnd()

        # Joint dots in orange (drawn as small GL_POINTS)
        glPointSize(6.0)
        glColor3f(1.0, 0.45, 0.1)
        glBegin(GL_POINTS)
        for start, end in self.skeleton_lines:
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
            self.rot_x = max(-89.0, min(89.0, self.rot_x))

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
        self.rot_x = 20.0
        self.rot_y = 30.0
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
