"""The PlayStation GPU packets of a recording drawn with OpenGL: the same pictures as the software
Gpu (FF8GameData.psxgpu.gpu), a hundred times faster, so an effect plays at the battle's 15
frames per second.

The packets are decoded by the software Gpu's own code (a PrimitiveCollector keeps the triangles it
would rasterise, in draw order); OpenGL then draws them into an offscreen framebuffer, the way GPU
emulators do: VRAM is a 1024 x 512 16-bit integer texture, the fragment shader reads the texel
through the tpage (4/8-bit CLUT or 15-bit direct), drops texel 0x0000, modulates by the vertex
colour (128 = unchanged) unless "raw", and the four semi-transparency modes are blend equations
(0 = B/2 + F/2, 1 = B + F, 2 = B - F, 3 = B + F/4). A textured pixel only blends where its texel's
STP bit is set: each run of primitives sharing a blend mode is drawn twice, its opaque pixels then
its blended ones (the console does it pixel by pixel in one go; overlaps inside one run can differ).

Needs an OpenGL 3.3 context: PsxGlRenderer.create() returns None without one (the offscreen Qt
platform of the tests) and callers keep the software Gpu.
"""
import numpy as np

from FF8GameData.psxgpu.gpu import VRAM_H, VRAM_W, Gpu

_VERTEX = """
#version 330 core
layout(location = 0) in vec2 position;
layout(location = 1) in vec3 colour;
layout(location = 2) in vec2 uv;
layout(location = 3) in vec4 state;     // clut, tpage, flags (1 textured, 2 semi, 4 raw), unused
uniform vec2 size;
noperspective out vec3 v_colour;
noperspective out vec2 v_uv;
flat out ivec3 v_state;
void main() {
    gl_Position = vec4(position.x / size.x * 2.0 - 1.0, 1.0 - position.y / size.y * 2.0, 0.0, 1.0);
    v_colour = colour;
    v_uv = uv;
    v_state = ivec3(state.xyz);
}
"""
_FRAGMENT = """
#version 330 core
uniform usampler2D vram;
uniform int pass_kind;                  // 0 everything, 1 the opaque pixels, 2 the blended pixels
noperspective in vec3 v_colour;
noperspective in vec2 v_uv;
flat in ivec3 v_state;
out vec4 colour;
uint word_at(int x, int y) { return texelFetch(vram, ivec2(x & 1023, y & 511), 0).r; }
void main() {
    bool textured = (v_state.z & 1) != 0, semi = (v_state.z & 2) != 0, raw = (v_state.z & 4) != 0;
    vec3 rgb = v_colour / 255.0;
    bool blend = semi;
    if (textured) {
        int tpage = v_state.y, clut = v_state.x;
        int u = int(floor(v_uv.x)) & 255, v = int(floor(v_uv.y)) & 255;
        int base_x = (tpage & 15) * 64, base_y = ((tpage >> 4) & 1) * 256, depth = (tpage >> 7) & 3;
        uint texel;
        if (depth == 2) {
            texel = word_at(base_x + u, base_y + v);
        } else {
            int clut_x = (clut & 63) * 16, clut_y = (clut >> 6) & 511;
            uint index = depth == 0 ? (word_at(base_x + u / 4, base_y + v) >> uint((u % 4) * 4)) & 15u
                                    : (word_at(base_x + u / 2, base_y + v) >> uint((u % 2) * 8)) & 255u;
            texel = word_at(clut_x + int(index), clut_y);
        }
        if (texel == 0u) discard;
        vec3 t = vec3(float(texel & 31u), float((texel >> 5) & 31u), float((texel >> 10) & 31u)) / 31.0;
        rgb = raw ? t : clamp(t * v_colour / 128.0, 0.0, 1.0);
        blend = semi && (texel & 0x8000u) != 0u;
    }
    if ((pass_kind == 1 && blend) || (pass_kind == 2 && !blend)) discard;
    colour = vec4(rgb, 1.0);
}
"""


class PrimitiveCollector(Gpu):
    """The software Gpu's packet decoding, keeping each triangle (and line pixel) in draw order
    instead of rasterising it: [(vertices (3, 10) float32, semi, mode)]."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.primitives = []

    def _command(self, words, index, code):
        if code == 0x02 and index + 2 < len(words):        # fill rectangle: an untextured quad
            x = (words[index + 1] & 0x3F0) - self.origin[0]
            y = ((words[index + 1] >> 16) & 0x1FF) - self.origin[1]
            w, h = words[index + 2] & 0x3FF, (words[index + 2] >> 16) & 0x1FF
            colour = (words[index] & 0xFF, (words[index] >> 8) & 0xFF, (words[index] >> 16) & 0xFF)
            corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
            for triangle in ((0, 1, 2), (1, 3, 2)):
                self._triangle([corners[i] for i in triangle], [colour] * 3, None, 0, self.tpage, False, False)
            return 3
        return super()._command(words, index, code)

    def _triangle(self, xys, colours, uvs, clut, tpage, semi, raw):
        flags = (1 if uvs is not None else 0) | (2 if semi else 0) | (4 if raw else 0)
        vertices = np.zeros((3, 10), np.float32)
        vertices[:, 0:2] = xys
        vertices[:, 2:5] = colours
        if uvs is not None:
            vertices[:, 5:7] = uvs
        vertices[:, 7:10] = (clut, tpage, flags)
        self.primitives.append((vertices, bool(semi), (tpage >> 5) & 3))

    def _blend(self, ys, xs, colour, semi, mode):
        # only lines reach here (triangles are kept above): each pixel as a 1-pixel square
        colour = np.asarray(colour, np.float32)
        for y, x, rgb, blended in zip(ys, xs, colour, semi):
            corners = [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
            for triangle in ((0, 1, 2), (1, 3, 2)):
                self._triangle([corners[i] for i in triangle], [rgb] * 3, None, 0, mode << 5, bool(blended), False)


class PsxGlRenderer:
    """Draws recordings' ticks offscreen; one per thread that owns a Qt OpenGL context."""

    def __init__(self, context, surface):
        from OpenGL import GL
        self.GL, self.context, self.surface = GL, context, surface
        self._program = self._build_program()
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        self._vram_texture = GL.glGenTextures(1)
        self._vram_key = None
        self._fbo = self._colour = None
        self._fbo_size = None

    @classmethod
    def create(cls):
        """A renderer on its own offscreen OpenGL 3.3 context, or None when there is none."""
        try:
            from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
            surface_format = QSurfaceFormat()
            surface_format.setVersion(3, 3)
            surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
            surface = QOffscreenSurface()
            surface.setFormat(surface_format)
            surface.create()
            context = QOpenGLContext()
            context.setFormat(surface_format)
            if not surface.isValid() or not context.create() or not context.makeCurrent(surface):
                return None
            if context.format().version() < (3, 3):
                return None
            return cls(context, surface)
        except Exception:
            return None

    # ------------------------------------------------------------------ setup
    def _build_program(self):
        GL = self.GL

        def compile_shader(source, kind):
            shader = GL.glCreateShader(kind)
            GL.glShaderSource(shader, source)
            GL.glCompileShader(shader)
            if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
                raise RuntimeError(GL.glGetShaderInfoLog(shader).decode(errors="replace"))
            return shader

        program = GL.glCreateProgram()
        for source, kind in ((_VERTEX, GL.GL_VERTEX_SHADER), (_FRAGMENT, GL.GL_FRAGMENT_SHADER)):
            GL.glAttachShader(program, compile_shader(source, kind))
        GL.glLinkProgram(program)
        if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(program).decode(errors="replace"))
        return program

    def _target(self, width, height):
        GL = self.GL
        if self._fbo_size == (width, height):
            return
        if self._fbo is not None:
            GL.glDeleteFramebuffers(1, [self._fbo])
            GL.glDeleteRenderbuffers(1, [self._colour])
        self._fbo = GL.glGenFramebuffers(1)
        self._colour = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self._colour)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_RGBA8, width, height)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_RENDERBUFFER, self._colour)
        self._fbo_size = (width, height)

    def _upload_vram(self, vram, key):
        GL = self.GL
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._vram_texture)
        if key is not None and key == self._vram_key:
            return
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 2)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R16UI, VRAM_W, VRAM_H, 0, GL.GL_RED_INTEGER,
                        GL.GL_UNSIGNED_SHORT, np.ascontiguousarray(vram.words))
        self._vram_key = key

    # ------------------------------------------------------------------ drawing
    def draw(self, collector, vram_key=None, background=(16, 16, 24)):
        """The (H, W, 3) uint8 image of a PrimitiveCollector that decoded a tick's packets."""
        GL = self.GL
        self.context.makeCurrent(self.surface)
        width, height = collector.width, collector.height
        self._target(width, height)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glViewport(0, 0, width, height)
        GL.glClearColor(*(c / 255.0 for c in background), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        primitives = collector.primitives
        if primitives:
            self._upload_vram(collector.vram, vram_key)
            GL.glUseProgram(self._program)
            GL.glUniform2f(GL.glGetUniformLocation(self._program, "size"), width, height)
            GL.glUniform1i(GL.glGetUniformLocation(self._program, "vram"), 0)
            pass_location = GL.glGetUniformLocation(self._program, "pass_kind")
            data = np.ascontiguousarray(np.concatenate([vertices for vertices, _semi, _mode in primitives]))
            GL.glBindVertexArray(self._vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STREAM_DRAW)
            stride = 10 * 4
            for location, (count, offset) in enumerate(((2, 0), (3, 2), (2, 5), (3, 7))):
                GL.glEnableVertexAttribArray(location)
                GL.glVertexAttribPointer(location, count, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                         GL.ctypes.c_void_p(offset * 4))
            # runs of primitives sharing (semi, mode), in draw order
            start = 0
            for index in range(1, len(primitives) + 1):
                if index < len(primitives) and primitives[index][1:] == primitives[start][1:]:
                    continue
                _vertices, semi, mode = primitives[start]
                first, count = start * 3, (index - start) * 3
                if not semi:
                    GL.glDisable(GL.GL_BLEND)
                    GL.glUniform1i(pass_location, 0)
                    GL.glDrawArrays(GL.GL_TRIANGLES, first, count)
                else:
                    GL.glDisable(GL.GL_BLEND)
                    GL.glUniform1i(pass_location, 1)
                    GL.glDrawArrays(GL.GL_TRIANGLES, first, count)
                    self._blend_mode(mode)
                    GL.glUniform1i(pass_location, 2)
                    GL.glDrawArrays(GL.GL_TRIANGLES, first, count)
                start = index
            GL.glDisable(GL.GL_BLEND)
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        pixels = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        image = np.frombuffer(pixels, np.uint8).reshape(height, width, 3)
        return np.ascontiguousarray(image[::-1])

    def _blend_mode(self, mode):
        GL = self.GL
        GL.glEnable(GL.GL_BLEND)
        if mode == 0:       # B/2 + F/2
            GL.glBlendColor(0.5, 0.5, 0.5, 0.5)
            GL.glBlendEquation(GL.GL_FUNC_ADD)
            GL.glBlendFunc(GL.GL_CONSTANT_COLOR, GL.GL_CONSTANT_COLOR)
        elif mode == 1:     # B + F
            GL.glBlendEquation(GL.GL_FUNC_ADD)
            GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
        elif mode == 2:     # B - F
            GL.glBlendEquation(GL.GL_FUNC_REVERSE_SUBTRACT)
            GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
        else:               # B + F/4
            GL.glBlendColor(0.25, 0.25, 0.25, 0.25)
            GL.glBlendEquation(GL.GL_FUNC_ADD)
            GL.glBlendFunc(GL.GL_CONSTANT_COLOR, GL.GL_ONE)
