import os
import pathlib
import shutil
from typing import List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
                             QScrollArea, QGridLayout, QSizePolicy, QFileDialog, QMessageBox)

from Ifrit3D.ifrit3dmanager import Ifrit3DManager
from IfritTexture.ifrittexturemanager import IfritTextureManager, TextureData, MetaData
from IfritTexture.texturewidget import TextureWidget
import sys
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat
from OpenGL.GL import *
from OpenGL.GLU import *


class FF8OpenGLWidget(QOpenGLWidget):
    """
    FF8 Monster Viewer Widget - Reusable PyQt Widget
    """

    # ─────────────────────────────────────────────────────────────────────────────
    #  FF8 DATA (Embedded - you can replace with your own data source)
    # ─────────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────────
    #  OpenGL Widget (Core Viewer)
    # ─────────────────────────────────────────────────────────────────────────────
    def __init__(self, parent=None):
        self.face_color = (0.45, 0.65, 0.95)
        self.RAW_VERTICES_ORIGINAL = []
        # self.RAW_VERTICES_ORIGINAL = [
        #     (0.0, 0.0078125, 14.4345703125),
        #     (2.54638671875, 0.0078125, 14.4345703125),
        #     (1.80029296875, -1.79248046875, 14.4345703125),
        #     (0.0, -2.53857421875, 14.4345703125),
        #     (-1.80078125, -1.79248046875, 14.4345703125),
        #     (-2.546875, 0.0078125, 14.4345703125),
        #     (-1.80078125, 1.80908203125, 14.4345703125),
        #     (0.0, 2.55517578125, 14.4345703125),
        #     (1.80029296875, 1.80908203125, 14.4345703125),
        #     (2.59423828125, 1.3486328125, 15.90673828125),
        #     (2.89404296875, 0.7333984375, 15.68310546875),
        #     (-2.89697265625, 0.728515625, 15.68310546875),
        #     (-2.5947265625, 1.3486328125, 15.90673828125),
        #     (3.19482421875, 0.0078125, 15.68310546875),
        #     (2.2587890625, -2.2509765625, 15.68310546875),
        #     (0.0, -3.1865234375, 15.68310546875),
        #     (-2.25927734375, -2.2509765625, 15.68310546875),
        #     (-3.1953125, 0.0078125, 15.68310546875),
        #     (-2.220703125, 2.22900390625, 15.90673828125),
        #     (0.0, 3.14892578125, 15.90673828125),
        #     (2.22021484375, 2.22900390625, 15.90673828125),
        # ]

        self.set_vertices([(0,0,0)])

        self.triangles = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]
        self.QUADS = [
            (14, 13, 2, 1), (15, 14, 3, 2), (16, 15, 4, 3),
            (17, 16, 5, 4), (19, 18, 7, 6), (20, 19, 8, 7),
        ]

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
        self.show_wireframe = True
        self.show_axis = True

    def set_vertices(self, vertices:list):
        print("set_vertices")
        print(vertices)
        # self.VERTICES = [transform_vertex(v) for v in self.RAW_VERTICES_ORIGINAL]
        self.vertices = vertices
        self.vertices_array = np.array(self.vertices, dtype=np.float32)
        print(self.vertices_array)

        MIN_BOUNDS = self.vertices_array.min(axis=0)
        MAX_BOUNDS = self.vertices_array.max(axis=0)
        self.MODEL_CENTER = (MIN_BOUNDS + MAX_BOUNDS) / 2
        self.MODEL_SIZE = np.linalg.norm(MAX_BOUNDS - MIN_BOUNDS)

    def set_triangles(self, triangles:List):
        self.triangles = triangles
    def set_quads(self, quads:List):
        self.quads = quads
    def transform_vertex(vertex):
        """Convert from FF8 coordinate system to OpenGL (Y-up, Z-forward)"""
        x, y, z = vertex
        return (x, z, y)  # Swap Y and Z

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

        # Camera position in spherical coordinates
        cam_x = self.zoom * math.cos(rad_y) * math.cos(rad_x)
        cam_y = self.zoom * math.sin(rad_x)
        cam_z = self.zoom * math.sin(rad_y) * math.cos(rad_x)

        # Target is model center + pan offset
        target_x = self.MODEL_CENTER[0] + self.pan_x
        target_y = self.MODEL_CENTER[1] + self.pan_y
        target_z = self.MODEL_CENTER[2]

        gluLookAt(cam_x, cam_y, cam_z,
                  target_x, target_y, target_z,
                  0.0, 1.0, 0.0)

        # Draw axis
        if self.show_axis:
            self.draw_axis()

        # Draw triangles
        glColor3f(*self.face_color)
        for tri in self.triangles:
            glBegin(GL_TRIANGLES)
            for idx in tri:
                v = self.vertices_array[idx]
                glVertex3f(v[0], v[1], v[2])
            glEnd()

        # Draw quads with double-diagonal fix
        self.draw_quads()

        # Draw wireframe
        if self.show_wireframe:
            self.draw_wireframe()

        self.update()

    def draw_quads(self):
        """Draw quads using both diagonals to handle non-planar surfaces"""

        glColor3f(*self.face_color)

        for quad_idx, quad in enumerate(self.QUADS):
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

        for quad in self.QUADS:
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

class Ifrit3DWidget(QWidget):
    """
    Complete FF8 Monster Viewer Widget.
    Ready to drop into any PyQt6 application.
    """

    def __init__(self, parent=None, show_controls=True):
        super().__init__(parent)
        self.ifrit3d_manager = Ifrit3DManager("c0m071.dat")


        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create the OpenGL viewer
        self.gl_widget = FF8OpenGLWidget(self)
        self.gl_widget.set_vertices(self.ifrit3d_manager.monster_data.geometry_data.get_vertices())
        self.gl_widget.set_triangles(self.ifrit3d_manager.monster_data.geometry_data.get_triangles())
        self.gl_widget.set_quads(self.ifrit3d_manager.monster_data.geometry_data.get_quads())

        if show_controls:
            # Create toolbar
            toolbar = QWidget()
            toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(8, 4, 8, 4)

            # Wireframe toggle
            self.cb_wire = QCheckBox("Wireframe")
            self.cb_wire.setChecked(True)
            self.cb_wire.setStyleSheet("color:white;")
            self.cb_wire.toggled.connect(self._on_wire_toggle)
            toolbar_layout.addWidget(self.cb_wire)

            # Axis toggle
            self.cb_axis = QCheckBox("Axis")
            self.cb_axis.setChecked(True)
            self.cb_axis.setStyleSheet("color:white;")
            self.cb_axis.toggled.connect(self._on_axis_toggle)
            toolbar_layout.addWidget(self.cb_axis)

            toolbar_layout.addStretch()

            # Reset button
            reset_btn = QPushButton("Reset View")
            reset_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
            reset_btn.clicked.connect(self.gl_widget.reset_view)
            toolbar_layout.addWidget(reset_btn)

            # Info label
            info = QLabel(f"Tri: {len(self.gl_widget.triangles)} | Quads: {len(self.gl_widget.QUADS)} | LMB: Rotate | RMB: Pan | Scroll: Zoom")
            info.setStyleSheet("background:#1a1a1f; color:#aaa; padding:4px 8px; font-size:10px;")

            layout.addWidget(toolbar)
            layout.addWidget(self.gl_widget, 1)
            layout.addWidget(info)
        else:
            layout.addWidget(self.gl_widget, 1)

    def _on_wire_toggle(self, checked):
        """Toggle wireframe visibility"""
        self.gl_widget.set_show_wireframe(checked)

    def _on_axis_toggle(self, checked):
        """Toggle axis visibility"""
        self.gl_widget.set_show_axis(checked)

    # Public methods for external control
    def reset_view(self):
        """Reset camera position"""
        self.gl_widget.reset_view()

    def set_show_wireframe(self, show):
        self.gl_widget.set_show_wireframe(show)
        if hasattr(self, 'cb_wire'):
            self.cb_wire.setChecked(show)

    def set_show_axis(self, show):
        self.gl_widget.set_show_axis(show)
        if hasattr(self, 'cb_axis'):
            self.cb_axis.setChecked(show)

    def get_gl_widget(self):
        """Return the underlying OpenGL widget for advanced control"""
        return self.gl_widget


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication, QMainWindow


    class DemoWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("FF8 Monster Viewer - Widget Demo")
            self.resize(1000, 700)
            # Create the viewer widget (with controls)
            self.viewer = Ifrit3DWidget(show_controls=True)
            self.setCentralWidget(self.viewer)


    # Set OpenGL format
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())
