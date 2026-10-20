"""OpenGL video widget: uploads Y/U/V planes and converts to RGB in a fragment shader.

This keeps the CPU free of per-pixel work; the GPU does colour conversion and scaling.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QVector2D, QVector3D
from PySide6.QtOpenGL import (QOpenGLBuffer, QOpenGLPixelTransferOptions, QOpenGLShader, QOpenGLShaderProgram,
                              QOpenGLTexture)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QLabel

from .frame import YuvFrame
from .look import PictureLook

GL_COLOR_BUFFER_BIT = 0x4000
GL_TRIANGLE_STRIP = 0x0005
GL_FLOAT = 0x1406

_VERTEX = """
attribute vec2 pos;
varying vec2 uv;
void main() {
    uv = vec2(pos.x * 0.5 + 0.5, 0.5 - pos.y * 0.5);
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

_FRAGMENT = """
varying vec2 uv;
uniform sampler2D ty;
uniform sampler2D tu;
uniform sampler2D tv;
uniform vec3 yuv_offset;
uniform vec3 yuv_scale;
uniform vec3 coef_r;
uniform vec3 coef_g;
uniform vec3 coef_b;
uniform vec2 step_uv;      // one output pixel (one source pixel when enlarging), in texture coordinates
uniform float sharpness;   // 0 = off
uniform vec3 adjust;       // brightness, contrast, saturation
void main() {
    float y = texture2D(ty, uv).r;
    if (sharpness > 0.0) {                                   // unsharp mask on the brightness plane only
        float blur = 0.25 * (texture2D(ty, uv + vec2(step_uv.x, 0.0)).r + texture2D(ty, uv - vec2(step_uv.x, 0.0)).r
                           + texture2D(ty, uv + vec2(0.0, step_uv.y)).r + texture2D(ty, uv - vec2(0.0, step_uv.y)).r);
        y = y + sharpness * 1.5 * (y - blur);
    }
    vec3 yuv = vec3(y, texture2D(tu, uv).r, texture2D(tv, uv).r);
    yuv = (yuv - yuv_offset) * yuv_scale;
    vec3 rgb = vec3(dot(coef_r, yuv), dot(coef_g, yuv), dot(coef_b, yuv));
    float luma = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
    rgb = mix(vec3(luma), rgb, adjust.z);                    // saturation
    rgb = (rgb - 0.5) * adjust.y + 0.5 + adjust.x;           // contrast, brightness
    gl_FragColor = vec4(clamp(rgb, 0.0, 1.0), 1.0);
}
"""

# (Kr-derived) coefficients: r = y + c*v ; g = y - a*u - d*v ; b = y + b*u
_BT709 = (1.5748, 0.187324, 0.468124, 1.8556)
_BT601 = (1.402, 0.344136, 0.714136, 1.772)


class VideoWidget(QOpenGLWidget):
    frameSizeChanged = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(240, 320)
        self.last_paint_latency_ms = 0.0

        self._pending: YuvFrame | None = None
        self._stamp = 0.0
        self._frame: YuvFrame | None = None       # last frame uploaded (for color + size)
        self._size = (0, 0)
        self._look = PictureLook()

        self._program: QOpenGLShaderProgram | None = None
        self._vbo: QOpenGLBuffer | None = None
        self._textures: list[QOpenGLTexture] = []
        self._tex_size = (0, 0)

        self._label = QLabel("No device connected", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setStyleSheet("color: #6b7385; background: transparent; font-size: 14px; padding: 24px;")

    # -- public API ------------------------------------------------------------------------
    def set_look(self, look: PictureLook) -> None:
        """Brightness / contrast / saturation / sharpness / colour conversion; applied on the next paint."""
        self._look = look
        self.update()

    def look(self) -> PictureLook:
        return self._look

    def set_placeholder(self, text: str) -> None:
        self._label.setText(text)

    def set_frame(self, frame: YuvFrame, stamp: float) -> None:
        self._pending = frame
        self._stamp = stamp
        self._label.hide()
        self.update()

    def clear(self) -> None:
        self._pending = None
        self._frame = None
        self._size = (0, 0)
        self.frameSizeChanged.emit(0, 0)
        self._label.show()
        self.update()

    def current_frame(self):
        """The last decoded picture (a YuvFrame) or None. Read-only: used to tell the game from its menus."""
        return self._pending if self._pending is not None else self._frame

    def frame_size(self) -> tuple[int, int]:
        return self._size

    def target_rect(self) -> QRectF:
        """Where the phone picture is drawn inside this widget (letter-boxed), in widget coordinates."""
        return self.target_rect_for(self._size, self.width(), self.height())

    @staticmethod
    def target_rect_for(size: tuple[int, int], width: float, height: float) -> QRectF:
        if size[0] <= 0 or size[1] <= 0:
            return QRectF()
        scale = min(width / size[0], height / size[1])
        w, h = size[0] * scale, size[1] * scale
        return QRectF((width - w) / 2, (height - h) / 2, w, h)

    def map_to_device(self, pos: QPointF, clamp: bool = False) -> tuple[float, float] | None:
        """Widget position -> normalized (0..1) position inside the phone screen.

        Returns None outside the picture, or the nearest edge point when `clamp` is True."""
        target = self.target_rect()
        if target.isEmpty():
            return None
        if not clamp and not target.contains(pos):
            return None
        nx = (pos.x() - target.x()) / target.width()
        ny = (pos.y() - target.y()) / target.height()
        return (min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny)))

    # -- Qt events -------------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._label.setGeometry(self.rect())

    def initializeGL(self) -> None:
        program = QOpenGLShaderProgram(self)
        program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX)
        program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT)
        if not program.link():
            raise RuntimeError("Video shader failed to compile: " + program.log())
        self._program = program

        vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vbo.create()
        vbo.bind()
        quad = (-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
        import array
        data = array.array("f", quad).tobytes()
        vbo.allocate(data, len(data))
        vbo.release()
        self._vbo = vbo

    def _make_textures(self, width: int, height: int) -> None:
        self._textures.clear()
        for w, h in ((width, height), ((width + 1) // 2, (height + 1) // 2), ((width + 1) // 2, (height + 1) // 2)):
            tex = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
            tex.setFormat(QOpenGLTexture.TextureFormat.R8_UNorm)
            tex.setSize(w, h)
            tex.setMipLevels(tex.maximumMipLevels())          # mipmaps: a window smaller than the phone picture is
            tex.allocateStorage(QOpenGLTexture.PixelFormat.Red, QOpenGLTexture.PixelType.UInt8)
            tex.setMinMagFilters(QOpenGLTexture.Filter.LinearMipMapLinear, QOpenGLTexture.Filter.Linear)    # filtered, not aliased
            tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            self._textures.append(tex)
        self._tex_size = (width, height)

    def _upload(self, frame: YuvFrame) -> None:
        if self._tex_size != (frame.width, frame.height) or not self._textures:
            self._make_textures(frame.width, frame.height)
        options = QOpenGLPixelTransferOptions()
        options.setAlignment(1)
        cw, ch = frame.chroma_size
        for tex, data, w, h in ((self._textures[0], frame.y, frame.width, frame.height),
                                (self._textures[1], frame.u, cw, ch),
                                (self._textures[2], frame.v, cw, ch)):
            tex.setData(0, 0, 0, w, h, 1, QOpenGLTexture.PixelFormat.Red, QOpenGLTexture.PixelType.UInt8,
                        data, options)
            tex.generateMipMaps()
        self._frame = frame
        if self._size != (frame.width, frame.height):
            self._size = (frame.width, frame.height)
            self.frameSizeChanged.emit(frame.width, frame.height)

    def paintGL(self) -> None:
        gl = self.context().functions()
        gl.glClearColor(0.043, 0.051, 0.071, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT)

        pending, self._pending = self._pending, None
        if pending is not None:
            self._upload(pending)
        frame = self._frame
        if frame is None or self._program is None:
            return

        ratio = self.devicePixelRatioF()
        target = self.target_rect_for((frame.width, frame.height), self.width(), self.height())
        gl.glViewport(round(target.x() * ratio), round((self.height() - target.bottom()) * ratio),
                      round(target.width() * ratio), round(target.height() * ratio))

        program = self._program
        program.bind()
        for unit, (tex, name) in enumerate(zip(self._textures, ("ty", "tu", "tv"))):
            tex.bind(unit)
            gl.glUniform1i(program.uniformLocation(name), unit)     # must be a GLint, not a float
        mode = self._look.color_mode
        bt601, full_range = (frame.bt601, frame.full_range) if mode == "auto" else (mode.startswith("bt601"), mode.endswith("_full"))
        coef_c, coef_a, coef_d, coef_b = _BT601 if bt601 else _BT709
        if full_range:
            offset, yuv_scale = QVector3D(0, 128 / 255, 128 / 255), QVector3D(1, 1, 1)
        else:
            offset = QVector3D(16 / 255, 128 / 255, 128 / 255)
            yuv_scale = QVector3D(255 / 219, 255 / 224, 255 / 224)
        program.setUniformValue("yuv_offset", offset)
        program.setUniformValue("yuv_scale", yuv_scale)
        program.setUniformValue("coef_r", QVector3D(1, 0, coef_c))
        program.setUniformValue("coef_g", QVector3D(1, -coef_a, -coef_d))
        program.setUniformValue("coef_b", QVector3D(1, coef_b, 0))
        look = self._look
        view_w, view_h = max(1.0, target.width() * ratio), max(1.0, target.height() * ratio)
        program.setUniformValue("step_uv", QVector2D(max(1 / view_w, 1 / frame.width), max(1 / view_h, 1 / frame.height)))
        gl.glUniform1f(program.uniformLocation("sharpness"), float(look.sharpness))      # a real GLfloat (the setUniformValue overloads pick int)
        program.setUniformValue("adjust", QVector3D(look.brightness, look.contrast, look.saturation))

        self._vbo.bind()
        loc = program.attributeLocation("pos")
        program.enableAttributeArray(loc)
        program.setAttributeBuffer(loc, GL_FLOAT, 0, 2, 0)
        gl.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        program.disableAttributeArray(loc)
        self._vbo.release()
        program.release()

        if self._stamp:
            self.last_paint_latency_ms = (time.perf_counter() - self._stamp) * 1000
