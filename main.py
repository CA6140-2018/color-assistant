"""
AI 调色助手 - 主程序（设备安全渲染版）
"""

import math
import os
import traceback

# 崩溃日志必须最先安装（在任何 Kivy/jnius 导入之前），
# 这样即使 Kivy 原生库加载失败，APP START 记录也已写入，可区分崩溃阶段。
import crash_log
_crash_path = crash_log.install()


def _boot_paths():
    """boot.txt 候选路径：应用外部专属目录（用户可见）+ 脚本所在目录。"""
    paths = []
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        d = activity.getExternalFilesDir(None)
        if d is not None:
            paths.append(os.path.join(d.getAbsolutePath(), "boot.txt"))
    except Exception:
        pass
    paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "boot.txt"))
    return paths


def _boot_marker(stage):
    """启动阶段标记：即使闪退也能知道执行到了哪一步。"""
    import time as _t
    line = "stage=%s %s\n" % (stage, _t.strftime("%Y-%m-%d %H:%M:%S"))
    for p in _boot_paths():
        try:
            with open(p, "a", encoding="utf-8") as _f:
                _f.write(line)
            return
        except Exception:
            continue


_boot_marker("1-python-started")

# ── 中文字体注册（Android 默认字体不支持中文）──
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

def _find_cjk_font():
    candidates = [
        # MIUI 系统字体（视觉接近苹方）- 优先使用
        "/system/fonts/MiSans-Regular.ttf",
        "/system/fonts/MiSans.ttf",
        "/system/fonts/MiSans-Regular.otf",
        # 本地打包字体（下载到项目fonts目录）
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.otf"),
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.ttf"),
        # Android 通用中文字体
        "/system/fonts/NotoSansSC-Regular.otf",
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/NotoSansSC-Regular.ttf",
        # Windows
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def _is_android():
    try:
        from kivy.utils import platform
        return platform == "android"
    except Exception:
        return False

IS_ANDROID = _is_android()

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color as GColor, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

# Kivy 事件循环内的异常（时钟回调/触摸事件）默认不触发 sys.excepthook，
# 这里挂一个 ExceptionHandler 把它们也写进崩溃日志。
try:
    from kivy.base import ExceptionManager, ExceptionHandler

    class _KivyCrashWriter(ExceptionHandler):
        def handle_exception(self, inst):
            tb = "".join(traceback.format_exception(type(inst), inst, inst.__traceback__))
            crash_log.write_crash("\n----- KIVY CRASH -----\n%s\n" % tb)
            return ExceptionManager.RAISE

    ExceptionManager.add_handler(_KivyCrashWriter())
except Exception:
    pass

_cjk_font = _find_cjk_font()
if _cjk_font:
    from kivy.core.text import LabelBase
    LabelBase.register("Roboto", _cjk_font, _cjk_font, _cjk_font, _cjk_font)

from color_engine import (
    Color,
    ColorMixer,
    Frame,
    WhiteBalance,
    average_color_region,
    extract_dominant_color,
    pigment_description,
)
from ai_assistant import ColorAdvisor

# ── 主题色（按参考图2：iOS 浅色模式）──
THEME = {
    "bg": (0.949, 0.949, 0.961, 1),       # 系统灰 #F2F2F7
    "card": (1, 1, 1, 1),                 # 纯白
    "placeholder": (0.898, 0.898, 0.918, 1),  # 空状态灰 #E5E5EA
    "label": (0, 0, 0, 1),                # 主文字黑
    "label_2": (0.556, 0.557, 0.576, 1),  # 次要文字 #8E8E93
    "primary": (0.0, 0.478, 1, 1),        # 系统蓝 #007AFF
    "success": (0.203, 0.78, 0.349, 1),   # 绿 #34C759
    "warning": (1, 0.584, 0, 1),          # 橙 #FF9500
    "danger": (1, 0.231, 0.188, 1),       # 红 #FF3B30
    "separator": (0.78, 0.78, 0.80, 1),   # 分割线
    # 语义色 — Lab 轴
    "tag_l": (0.227, 0.227, 0.235, 1),    # L 深灰标签
    "tag_a": (0.298, 0.686, 0.314, 1),    # a 绿标签
    "tag_b": (1, 0.757, 0.027, 1),        # b 黄标签
    "tag_red": (1, 0.231, 0.188, 1),      # 红标签
    "tag_blue": (0.0, 0.478, 1, 1),       # 蓝标签
    "chroma": (1, 0.176, 0.573, 1),       # 饱和度粉色 #FF2D92
    "hue_color": (0.0, 0.478, 1, 1),      # 色相角蓝色
}
# 按参考图1：深色模式（专业调色面板）
DARK = {
    "bg": (0.039, 0.086, 0.157, 1),      # 深海军蓝 #0a1628
    "card": (0.102, 0.176, 0.290, 1),    # 卡片 #1a2d4a
    "card_2": (0.165, 0.227, 0.333, 1),  # 次级 #2a3a55
    "bar": (0.059, 0.122, 0.227, 1),     # 顶栏 #0f1f3a
    "text": (1, 1, 1, 1),
    "sub": (0.627, 0.690, 0.753, 1),     # #a0aec0
    "gold": (0.961, 0.784, 0.259, 1),    # 金色 #f5c842
    "accent": (0.290, 0.565, 0.886, 1),  # 蓝 #4a90e2
    "orange": (0.941, 0.541, 0.365, 1),  # 橙 #f08a5d
    "orange_dark": (0.908, 0.365, 0.243, 1),  # 深橙 #e85d3e
    "yellow": (0.961, 0.784, 0.259, 1),  # 黄 #f5c842
    "track_bg": (0.227, 0.290, 0.373, 1), # 进度条底 #3a4a5f
    "selected": (0.961, 0.784, 0.259, 1), # 选中态黄
    "unselected": (0.165, 0.227, 0.333, 1), # 未选中 #2a3a55
}


def _bg(widget, rgba, radius=0, shadow=False):
    """给 widget 画一个跟随 pos/size 的矩形背景（只用安全图元）。"""
    with widget.canvas.before:
        if shadow:
            GColor(0, 0, 0, 0.05)
            RoundedRectangle(pos=(widget.x, widget.y - dp(2)), size=widget.size, radius=[radius or dp(10)])
        GColor(*rgba)
        if radius:
            rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
        else:
            rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda i, v, r=rect: setattr(r, "pos", i.pos),
        size=lambda i, v, r=rect: setattr(r, "size", i.size),
    )
    return rect


def _card_bg(widget, radius=dp(12)):
    """iOS 卡片背景：白色圆角。"""
    with widget.canvas.before:
        GColor(*THEME["card"])
        RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    widget.bind(
        pos=lambda i, v: _update_card_bg(i, v, radius),
        size=lambda i, v: _update_card_bg(i, v, radius),
    )


def _update_card_bg(widget, val, radius):
    widget.canvas.before.clear()
    with widget.canvas.before:
        GColor(*THEME["card"])
        RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])


def _dark_card_bg(widget, radius=dp(12)):
    """深色卡片背景（参考图1）。"""
    with widget.canvas.before:
        GColor(*DARK["card"])
        RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    widget.bind(
        pos=lambda i, v: _update_dark_card_bg(i, v, radius),
        size=lambda i, v: _update_dark_card_bg(i, v, radius),
    )


def _update_dark_card_bg(widget, val, radius):
    widget.canvas.before.clear()
    with widget.canvas.before:
        GColor(*DARK["card"])
        RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])


def _lbl(text, size=None, font_size=None, color=None, bold=False, halign="left", width=None):
    l = Label(
        text=text,
        size_hint_y=None if size else 1,
        height=size or dp(20),
        size_hint_x=None if width else 1,
        width=width or 0,
        font_size=font_size or dp(12),
        color=color or THEME["label"],
        bold=bold,
        halign=halign,
        valign="middle",
        markup=True,
    )
    l.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
    return l


def _update_sep(widget, val):
    widget.canvas.after.clear()
    with widget.canvas.after:
        GColor(0.78, 0.78, 0.80, 1)
        Rectangle(pos=(widget.x, widget.y), size=(widget.width, 0.5))


def _update_toolbar_sep(widget, val):
    widget.canvas.after.clear()
    with widget.canvas.after:
        GColor(0.78, 0.78, 0.80, 1)
        Rectangle(pos=(widget.x, widget.y + widget.height), size=(widget.width, 0.5))


def _update_mix_sep(widget, val):
    widget.canvas.after.clear()
    with widget.canvas.after:
        GColor(0.22, 0.22, 0.25, 1)
        Rectangle(pos=(widget.x, widget.y), size=(widget.width, 0.5))


# ──────────────────────────────────────────────
# 摄像头画面（tex_coords 旋转，无矩阵变换）
# ──────────────────────────────────────────────

_UV_MAP = {
    0: [0, 0, 1, 0, 1, 1, 0, 1],
    90: [1, 0, 1, 1, 0, 1, 0, 0],
    180: [1, 1, 0, 1, 0, 0, 1, 0],
    270: [0, 1, 0, 0, 1, 0, 1, 1],
}


class TexView(Widget):
    """用默认 shader 的 Rectangle + tex_coords 显示纹理并实现 0/90/180/270 旋转。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tex = None
        self._rot = 0
        self.bind(pos=self._redraw, size=self._redraw)

    def set_texture(self, tex):
        self._tex = tex
        self._redraw()

    def set_rotation(self, rot):
        self._rot = int(rot) % 360
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        if self._tex is None or self.width <= 1 or self.height <= 1:
            return
        with self.canvas:
            Rectangle(
                texture=self._tex,
                pos=self.pos,
                size=self.size,
                tex_coords=_UV_MAP.get(self._rot, _UV_MAP[0]),
            )


class CameraView(FloatLayout):
    """摄像头实时画面 + 点击取色。桌面 OpenCV / Android Kivy Camera。"""

    def __init__(self, on_color_picked=None, **kwargs):
        super().__init__(**kwargs)
        self.on_color_picked = on_color_picked
        self._frame = None
        self._camera_started = False
        self._rotation = 90 if IS_ANDROID else 0

        # 暗色背景占满（让摄像头区域不是白色）
        with self.canvas:
            GColor(0.039, 0.086, 0.157, 1)  # DARK["bg"]
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.tex_view = TexView(size_hint=(1, 1))
        self.tex_view.set_rotation(self._rotation)
        self.add_widget(self.tex_view)

        self._placeholder = BoxLayout(orientation="vertical", size_hint=(None, None), size=(dp(120), dp(120)),
                                       pos_hint={"center_x": 0.5, "center_y": 0.5})
        self._placeholder.add_widget(Label(
            text="📷", font_size=dp(40), size_hint=(1, None), height=dp(50),
        ))
        self._placeholder.add_widget(Label(
            text="请点击画面取色", font_size=dp(13), color=(0.7, 0.7, 0.7, 1),
            size_hint=(1, None), height=dp(24),
        ))
        self.add_widget(self._placeholder)

        self.crosshair = Label(
            text="＋", font_size=dp(28), color=(1, 1, 1, 0.95),
            size_hint=(None, None), size=(dp(36), dp(36)),
            bold=True,
        )
        # 准星周围加一圈深色轮廓（用两个Label叠加效果）
        self.crosshair_outline = Label(
            text="＋", font_size=dp(32), color=(0, 0, 0, 0.5),
            size_hint=(None, None), size=(dp(40), dp(40)),
            bold=True,
        )
        self.add_widget(self.crosshair_outline)
        self.add_widget(self.crosshair)
        self.bind(size=self._center_crosshair)

        if HAS_CV2 and not IS_ANDROID:
            self.capture = None
            self._texture = None
            self._camera_active = False
        else:
            self.kivy_camera = None

    def _center_crosshair(self, *args):
        self.crosshair.center = self.center
        self.crosshair_outline.center = self.center

    def _update_bg(self, *args):
        self.canvas.clear()
        with self.canvas:
            GColor(0.039, 0.086, 0.157, 1)
            Rectangle(pos=self.pos, size=self.size)

    def rotate_cw(self):
        if HAS_CV2 and not IS_ANDROID:
            return
        self._rotation = (self._rotation + 90) % 360
        self.tex_view.set_rotation(self._rotation)

    # ── 启动 ──
    def start_camera(self, camera_index=0):
        if self._camera_started:
            return
        if HAS_CV2 and not IS_ANDROID:
            self.capture = cv2.VideoCapture(camera_index)
            if not self.capture.isOpened():
                for i in range(4):
                    self.capture = cv2.VideoCapture(i)
                    if self.capture.isOpened():
                        break
            if self.capture.isOpened():
                self._camera_active = True
                self._camera_started = True
                Clock.schedule_interval(self._update_cv2_frame, 1.0 / 30)
        else:
            if self.kivy_camera is None and not getattr(self, "_cam_sched", False):
                self._cam_sched = True
                Clock.schedule_once(self._init_android_camera, 0)
            self._camera_started = True
            # 首帧超时兜底：10 秒后如果还没收到纹理，尝试重新初始化
            Clock.schedule_once(self._frame_timeout, 10.0)

    def _frame_timeout(self, dt):
        if self._placeholder.parent is None:
            return  # 已收到首帧，正常
        crash_log.write_crash("[camera] frame timeout: no texture after 10s, restarting\n")
        if self.kivy_camera is not None:
            self.kivy_camera.play = False
            self.remove_widget(self.kivy_camera)
            self.kivy_camera = None
        self._camera_started = False
        self._cam_sched = False
        Clock.schedule_once(self._init_android_camera, 0)
        self._camera_started = True

    def _init_android_camera(self, dt):
        """主线程创建隐藏采集器（三重隐藏，防漏画面）。"""
        self._cam_sched = False
        if self.kivy_camera is not None:
            return
        try:
            from kivy.uix.camera import Camera as KivyCamera
            c = KivyCamera(play=True, index=0, resolution=(640, 480))
            c.size_hint = (None, None)
            c.size = (0, 0)
            c.opacity = 0
            c.pos = (-2000, -2000)
            self.add_widget(c)
            self.kivy_camera = c
            crash_log.write_crash("[camera] KivyCamera created ok (hidden capture)\n")
        except Exception as e:
            import traceback as _tb
            crash_log.write_crash("[camera] KivyCamera create FAILED: %s\n%s\n" % (e, _tb.format_exc()))
            self.kivy_camera = None
            self._placeholder.text = "摄像头启动失败，见日志"
            return
        Clock.schedule_interval(self._update_kivy_frame, 1.0 / 30)

    def stop_camera(self):
        if HAS_CV2 and not IS_ANDROID:
            if self._camera_active:
                self._camera_active = False
                Clock.unschedule(self._update_cv2_frame)
            if self.capture:
                self.capture.release()
                self.capture = None
        else:
            Clock.unschedule(self._update_kivy_frame)
            if self.kivy_camera is not None:
                self.kivy_camera.play = False
        self._camera_started = False

    # ── 帧更新 ──
    def _update_cv2_frame(self, dt):
        if not self._camera_active or self.capture is None:
            return
        ret, frame = self.capture.read()
        if not ret:
            return
        import numpy as np
        self._frame = Frame(frame.tobytes(), frame.shape[1], frame.shape[0], src="bgr")
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = np.rot90(frame_rgb)
        frame_rgb = np.flipud(frame_rgb)
        buf = frame_rgb.tobytes()
        if (
            self._texture is None
            or self._texture.size[0] != frame_rgb.shape[1]
            or self._texture.size[1] != frame_rgb.shape[0]
        ):
            self._texture = Texture.create(size=(frame_rgb.shape[1], frame_rgb.shape[0]), colorfmt="rgb")
            self._texture.flip_horizontal = True
        self._texture.blit_buffer(buf, colorfmt="rgb")
        self.tex_view.set_texture(self._texture)
        self._on_first_frame()

    def _update_kivy_frame(self, dt):
        if getattr(self, "kivy_camera", None) is None:
            return
        tex = self.kivy_camera.texture
        if tex is None:
            return
        self.tex_view.set_texture(tex)
        self._on_first_frame()
        w, h = tex.size
        try:
            pixels = tex.pixels
            if pixels:
                self._frame = Frame(pixels, w, h, src="rgba_flip")
        except Exception:
            pass

    def _on_first_frame(self):
        if self._placeholder.parent is not None and self._placeholder.opacity > 0.99:
            # 淡出占位
            self._placeholder.opacity = 0
            Clock.schedule_once(lambda dt: self.remove_widget(self._placeholder) if self._placeholder.parent is not None else None, 0.1)
        if not getattr(self, "_geom_logged", False):
            self._geom_logged = True
            crash_log.write_crash(
                "[layout] cam=%d,%d,%d,%d tex=%d,%d,%d,%d\n" % (
                    self.x, self.y, self.width, self.height,
                    self.tex_view.x, self.tex_view.y, self.tex_view.width, self.tex_view.height,
                )
            )

    # ── 取色 ──
    def frame_coords_for(self, lx, ly, radius=10):
        if self._frame is None:
            return None
        frame_h, frame_w = self._frame.shape[:2]
        if self.width <= 0 or self.height <= 0:
            return None
        if lx is None:
            nu, nv = 0.5, 0.5
        else:
            nu = max(0.0, min(1.0, (lx - self.x) / self.width))
            nv = max(0.0, min(1.0, (ly - self.y) / self.height))
        rot = self._rotation
        if rot == 90:
            fx, fy = (1 - nv) * frame_w, nu * frame_h
        elif rot == 180:
            fx, fy = (1 - nu) * frame_w, (1 - nv) * frame_h
        elif rot == 270:
            fx, fy = nv * frame_w, (1 - nu) * frame_h
        else:
            fx, fy = nu * frame_w, nv * frame_h
        fx = int(max(0, min(frame_w - 1, fx)))
        fy = int(max(0, min(frame_h - 1, fy)))
        return average_color_region(self._frame, (fx, fy), radius=radius)

    def sample_at(self, lx, ly, radius=10):
        return self.frame_coords_for(lx, ly, radius=radius)

    def on_touch_down(self, touch):
        if self._frame is None or not self.collide_point(*touch.pos):
            return False
        color = self.sample_at(touch.x, touch.y, radius=10)
        if color is None:
            return False
        self.crosshair.center = (touch.x, touch.y)
        if self.on_color_picked:
            self.on_color_picked(color)
        return True

    def pick_center(self):
        if self._frame is None:
            return None
        h, w = self._frame.shape[:2]
        color = average_color_region(self._frame, (w // 2, h // 2), radius=15)
        if color and self.on_color_picked:
            self.on_color_picked(color)
        return color

    def get_frame(self):
        return self._frame


# ──────────────────────────────────────────────
# 安全图元组件
# ──────────────────────────────────────────────

class SwatchWidget(Widget):
    """纯色块（圆角矩形）。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._color = (0.8, 0.8, 0.8, 1)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def set_color(self, color):
        if color is None:
            self._color = (0.8, 0.8, 0.8, 1)
        else:
            r, g, b = color.rgb_normalized
            self._color = (r, g, b, 1)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            GColor(*self._color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])


class RatioBar(Widget):
    """比例条：灰底 + 彩色填充（两个矩形）。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ratio = 0.0
        self._fill = THEME["primary"]
        self.bind(pos=self._redraw, size=self._redraw)

    def set_ratio(self, ratio, color=None):
        self._ratio = max(0.0, min(1.0, ratio))
        if color is not None:
            r, g, b = color.rgb_normalized
            self._fill = (r, g, b, 1)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            GColor(0.88, 0.88, 0.9, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
            fw = self.width * self._ratio
            if fw > dp(4):
                GColor(*self._fill)
                RoundedRectangle(pos=self.pos, size=(fw, self.height), radius=[dp(4)])


# ──────────────────────────────────────────────
# 信息面板（色彩分析 / 报告）
# ──────────────────────────────────────────────

class InfoPanel(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.advisor = ColorAdvisor()
        self.do_scroll_x = False
        self.bar_width = dp(2)
        self.bar_color = (0.78, 0.78, 0.80, 1)
        # 白色背景
        with self.canvas.before:
            GColor(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        self.container = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(12), padding=(dp(16), dp(12), dp(16), dp(12)),
        )
        self.container.bind(minimum_height=self.container.setter("height"))
        self.add_widget(self.container)
        self._show_placeholder()

    def _clear(self):
        self.container.clear_widgets()

    def _card(self, title=None, padding=dp(14)):
        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=padding)
        body.bind(minimum_height=body.setter("height"))
        _card_bg(body)
        if title:
            body.add_widget(_lbl(title, size=dp(26), font_size=dp(15), bold=True, color=THEME["label"]))
        self.container.add_widget(body)
        return body

    def _scroll_top(self):
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 1), 0.15)

    def _show_placeholder(self):
        self._clear()
        c = self._card(padding=dp(20))
        c.add_widget(Label(
            text="👆", font_size=dp(40), size_hint_y=None, height=dp(50), halign="center", valign="middle",
        ))
        c.add_widget(_lbl("等待取色...", size=dp(24), font_size=dp(15), color=THEME["label_2"], halign="center"))
        c.add_widget(_lbl("点击摄像头画面取色", size=dp(40), font_size=dp(12), color=THEME["label_2"], halign="center"))

    def _update_bg(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            GColor(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)

    def _clear(self):
        self.container.clear_widgets()

    def _show_permission_denied(self):
        self._clear()
        c = self._card()
        c.add_widget(_lbl("[color=FF3B30]摄像头权限被拒绝[/color]", size=dp(24), font_size=dp(15)))
        c.add_widget(_lbl("请在系统设置中授予摄像头权限，然后重新打开应用。", size=dp(36), font_size=dp(12), color=THEME["label_2"]))

    def show_crash_path(self, path):
        self._clear()
        c = self._card()
        c.add_widget(_lbl("崩溃日志位置", size=dp(24), font_size=dp(15), bold=True))
        c.add_widget(_lbl("应用若异常闪退，日志会自动写入：", size=dp(20), font_size=dp(12), color=THEME["label_2"]))
        c.add_widget(_lbl(f"[color=007AFF]{path}[/color]", size=dp(30), font_size=dp(11)))
        self._scroll_top()

    def _make_tag(self, text, color):
        """制作彩色圆角标签（参考图2的L=, a=, b=标签）。"""
        label = Label(
            text=text, font_size=dp(12), color=(1, 1, 1, 1), bold=True,
            size_hint=(None, None), size=(dp(56), dp(22)), halign="center", valign="middle",
        )
        _bg(label, color, radius=dp(6))
        label.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        return label

    def _make_slider_row(self, left_label, left_color, right_label, right_color, value, callback):
        """制作参考图2风格的滑块行（带左右彩色标签）。"""
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(6))
        left = Label(
            text=left_label, font_size=dp(10), color=(1, 1, 1, 1), bold=True,
            size_hint=(None, 1), width=dp(28), halign="center", valign="middle",
        )
        _bg(left, left_color, radius=dp(4))
        row.add_widget(left)
        right = Label(
            text=right_label, font_size=dp(10), color=right_color, bold=True,
            size_hint=(None, 1), width=dp(28), halign="center", valign="middle",
        )
        _bg(right, right_color, radius=dp(4)) if right_color != (1, 1, 1, 1) else None
        slider = Slider(min=0, max=100, value=value, size_hint=(1, 1))
        slider.bind(value=callback)
        row.add_widget(slider)
        row.add_widget(right)
        return row

    def show_analysis(self, color):
        self._clear()
        analysis = self.advisor.analyze(color)
        L, a, b = color.lab
        C = math.hypot(a, b)
        h = math.degrees(math.atan2(b, a)) % 360.0

        # ── 颜色预览卡片（参考图2：左侧图片区 + 右侧预览区） ──
        preview = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(80), spacing=dp(12))
        preview.bind(minimum_height=preview.setter("height"))
        _card_bg(preview)
        # 左侧大色块
        sw = SwatchWidget(size_hint=(None, 1), width=dp(68))
        sw.set_color(color)
        preview.add_widget(sw)
        # 右侧信息
        info = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(2), padding=(dp(4), dp(8), dp(4), dp(8)))
        info.add_widget(_lbl(f"[b]{analysis.hex_code}[/b]  「{analysis.name}」", size=dp(22), font_size=dp(15)))
        info.add_widget(_lbl(
            f"{analysis.temperature} | {analysis.brightness} | {analysis.saturation_level}",
            size=dp(16), font_size=dp(11), color=THEME["label_2"],
        ))
        preview.add_widget(info)
        self.container.add_widget(preview)

        # ── Lab LCh 数据区（参考图2：彩色标签） ──
        lab_section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        lab_section.bind(minimum_height=lab_section.setter("height"))
        _card_bg(lab_section)

        # 标签行
        tag_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(6))
        tag_row.add_widget(_lbl("[b]Lab LCh[/b]", size=dp(26), font_size=dp(14), width=dp(60)))
        tag_row.add_widget(self._make_tag(f"L= {L:.1f}", THEME["tag_l"]))
        tag_row.add_widget(self._make_tag(f"a= {a:+.1f}", THEME["tag_a"]))
        tag_row.add_widget(self._make_tag(f"b= {b:+.1f}", THEME["tag_b"]))
        # 注：a为正绿、b为正黄，参考图2以实际值着色
        if a > 0:
            a_tag_color = THEME["tag_red"]
        else:
            a_tag_color = THEME["tag_a"]
        if b > 0:
            b_tag_color = THEME["tag_b"]
        else:
            b_tag_color = THEME["tag_blue"]
        lab_section.add_widget(tag_row)

        # 三个滑块（参考图2：黑→白、红→绿、黄→蓝）
        def _noop(*args):
            pass
        lab_section.add_widget(self._make_slider_row("黑", (0, 0, 0, 1), "白", (1, 1, 1, 1), L / 100 * 100, _noop))
        lab_section.add_widget(self._make_slider_row("红", THEME["danger"], "绿", THEME["tag_a"], (a + 128) / 256 * 100, _noop))
        lab_section.add_widget(self._make_slider_row("黄", THEME["tag_b"], "蓝", THEME["tag_blue"], (b + 128) / 256 * 100, _noop))

        # 极坐标数据卡（参考图2：C*和h°大数字）
        polar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(60), spacing=dp(8), padding=dp(8))
        polar.bind(minimum_height=polar.setter("height"))
        _bg(polar, (0.890, 0.933, 0.992, 1), radius=dp(10))
        # 饱和度
        sat_col = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(2))
        sat_col.add_widget(Label(text="饱和度(C*)", font_size=dp(10), color=THEME["label_2"],
                                 size_hint_y=None, height=dp(16), halign="left", valign="bottom"))
        sat_col.add_widget(Label(text=f"{C:.2f}", font_size=dp(22), color=THEME["chroma"], bold=True,
                                 size_hint_y=None, height=dp(30), halign="left", valign="middle"))
        polar.add_widget(sat_col)
        # 色相角
        hue_col = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(2))
        hue_col.add_widget(Label(text="色相角(h°)", font_size=dp(10), color=THEME["label_2"],
                                 size_hint_y=None, height=dp(16), halign="left", valign="bottom"))
        hue_col.add_widget(Label(text=f"{h:.2f}°", font_size=dp(22), color=THEME["hue_color"], bold=True,
                                 size_hint_y=None, height=dp(30), halign="left", valign="middle"))
        polar.add_widget(hue_col)
        lab_section.add_widget(polar)
        self.container.add_widget(lab_section)

        # ── 商用色卡匹配 ──
        if analysis.paint_matches:
            pc = self._card("商用色卡匹配")
            for m in analysis.paint_matches[:4]:
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8))
                s = SwatchWidget(size_hint=(None, 1), width=dp(24))
                s.set_color(m.color if hasattr(m, "color") else None)
                row.add_widget(s)
                row.add_widget(_lbl(f"{m.display}", font_size=dp(12), bold=True, width=dp(80)))
                row.add_widget(_lbl(f"ΔE={m.delta_e:.1f}", font_size=dp(12), color=THEME["danger"] if m.delta_e > 5 else THEME["success"]))
                pc.add_widget(row)

        # ── 参考颜色配方（参考图2：比例条列表） ──
        rc = self._card("参考颜色配方")
        recipes = self.advisor.suggest_recipe(color, top_n=1)
        pname_color = {}
        for p in getattr(self.advisor.recipe_finder, "pigments", []) or []:
            pname_color[p.name] = p.color
        if recipes:
            rec = recipes[0]
            rc.add_widget(_lbl(f"模拟配方 ΔE={rec.delta_e:.1f}", size=dp(18), font_size=dp(11), color=THEME["label_2"]))
            for name, _hex, ratio in rec.components:
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(8))
                s = SwatchWidget(size_hint=(None, 1), width=dp(24))
                s.set_color(pname_color.get(name))
                row.add_widget(s)
                row.add_widget(_lbl(name, size=dp(30), width=dp(50), font_size=dp(12), bold=True))
                bar = RatioBar(size_hint=(1, 1))
                bar.set_ratio(ratio, pname_color.get(name))
                row.add_widget(bar)
                pct = Label(text=f"{ratio:.0f}%", size_hint=(None, 1), width=dp(36),
                            font_size=dp(12), bold=True, color=THEME["primary"], valign="middle")
                row.add_widget(pct)
                rc.add_widget(row)
        else:
            rc.add_widget(_lbl("暂无配方", size=dp(20), font_size=dp(12), color=THEME["label_2"]))

        # ── 和谐配色（色块式展示） ──
        hc = self._card("和谐配色")
        for scheme, colors in self.advisor.suggest_harmony(color).items():
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6))
            row.add_widget(_lbl(f"{scheme}:", size=dp(28), width=dp(50), font_size=dp(11), bold=True, color=THEME["label"]))
            for c in colors:
                cs = SwatchWidget(size_hint=(None, 1), width=dp(20))
                cs.set_color(c)
                row.add_widget(cs)
                row.add_widget(_lbl(c.hex, size=dp(28), width=dp(44), font_size=dp(9), color=THEME["label_2"]))
            hc.add_widget(row)

        self._scroll_top()

    def show_report(self, color):
        self._clear()
        c = self._card("完整调色报告")
        report = self.advisor.generate_full_report(color)
        c.add_widget(_lbl(report, font_size=dp(11)))
        self._scroll_top()


# ──────────────────────────────────────────────
# AI 辅助调色（点击取色）
# ──────────────────────────────────────────────

class AiMixScreen(BoxLayout):
    """AI 辅助调色：按参考图1设计（深色专业面板，取消划块，改用点击取色）。"""

    def __init__(self, camera_view, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = 0
        self.camera_view = camera_view
        self.advisor = ColorAdvisor()
        self.wb = WhiteBalance()
        self._target = None
        self._current = None
        self._wet = False
        self._radius = 12
        self._sampling_interval = None
        self._advice_tick = 0
        self._mode = "current"  # correction / current
        self.on_close = None
        self._build_ui()

    def _build_ui(self):
        _bg(self, DARK["bg"])
        # ── 顶栏（参考图1：深色渐变） ──
        bar = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6), padding=(dp(12), 0, dp(12), 0))
        _bg(bar, DARK["bar"])
        self.btn_back = Button(
            text="‹ 返回", size_hint=(None, 1), width=dp(52),
            font_size=dp(14), color=DARK["text"], background_color=(0, 0, 0, 0), background_normal="",
        )
        self.btn_back.bind(on_release=lambda b: self.request_close())
        bar.add_widget(self.btn_back)
        bar.add_widget(Label(text="AI辅助调色", size_hint=(1, 1), font_size=dp(16), color=DARK["text"], bold=True))
        self.add_widget(bar)

        # ── 摄像头区（点击取中心色） ──
        self.cam_area = FloatLayout()
        self.cam_area.size_hint = (1, 0.60)
        _bg(self.cam_area, DARK["bg"])
        # 点击取色提示
        tip = Label(
            text="点击画面取色", font_size=dp(14), color=DARK["sub"],
            size_hint=(None, None), size=(dp(120), dp(30)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        self.cam_area.add_widget(tip)
        # 准星
        self._crosshair = Label(
            text="＋", font_size=dp(24), color=(1, 1, 1, 0.8),
            size_hint=(None, None), size=(dp(32), dp(32)),
        )
        self.cam_area.add_widget(self._crosshair)
        self.cam_area.bind(size=self._center_xhair)
        self.add_widget(self.cam_area)

        # ── 底部面板（参考图1：深色大圆角卡片） ──
        bottom = BoxLayout(orientation="vertical", size_hint=(1, 0.50), spacing=dp(6), padding=(dp(12), dp(8), dp(12), dp(12)))
        _bg(bottom, DARK["bg"], radius=dp(24))
        panel = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(6), padding=(dp(0), dp(0), dp(0), dp(0)))
        _bg(panel, DARK["bar"])
        bottom.add_widget(panel)
        self.add_widget(bottom)

        # ΔE 行（参考图1：金色大字）
        delta_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8), padding=(dp(12), 0, dp(12), 0))
        delta_row.add_widget(Label(text="色差", font_size=dp(14), color=DARK["text"], size_hint=(1, 1), halign="left", valign="middle"))
        self.delta_lbl = Label(
            text="--", size_hint=(None, 1), width=dp(80),
            font_size=dp(24), color=DARK["gold"], bold=True, halign="right", valign="middle",
        )
        self.delta_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        delta_row.add_widget(self.delta_lbl)
        panel.add_widget(delta_row)

        # 实时预览颜色块（参考图1：大色块卡片）
        preview_card = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(72), spacing=dp(4), padding=(dp(12), dp(8), dp(12), dp(8)))
        _dark_card_bg(preview_card, radius=dp(14))
        preview_card.add_widget(Label(text="实时预览效果", size_hint_y=None, height=dp(16), font_size=dp(12), color=DARK["text"], halign="left", valign="middle"))
        self.preview_block = SwatchWidget(size_hint=(1, 1))
        self.preview_block.set_color(None)
        preview_card.add_widget(self.preview_block)
        panel.add_widget(preview_card)

        # 双按钮组（矫正色/当前色）
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6), padding=(dp(12), 0, dp(12), 0))
        self._btn_correction = Button(
            text="矫正色", size_hint=(1, 1), font_size=dp(12), background_normal="",
            background_color=DARK["unselected"], color=DARK["text"],
        )
        self._btn_correction.bind(on_release=lambda b: self._set_mode("correction"))
        self._btn_current = Button(
            text="当前色", size_hint=(1, 1), font_size=dp(12), background_normal="",
            background_color=DARK["selected"], color=(0.1, 0.1, 0.1, 1), bold=True,
        )
        self._btn_current.bind(on_release=lambda b: self._set_mode("current"))
        btn_row.add_widget(self._btn_correction)
        btn_row.add_widget(self._btn_current)
        panel.add_widget(btn_row)

        # 干/潮检测 + 大小滑块（参考图1）
        mid_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(6), padding=(dp(12), 0, dp(12), 0))
        self._btn_dry = Button(
            text="干物检测", size_hint=(None, 1), width=dp(76), font_size=dp(11), background_normal="",
            background_color=DARK["orange"], color=(1, 1, 1, 1),
        )
        self._btn_dry.bind(on_release=lambda b: self._set_wet(False))
        self._btn_wet = Button(
            text="潮物检测", size_hint=(None, 1), width=dp(76), font_size=dp(11), background_normal="",
            background_color=DARK["unselected"], color=DARK["text"],
        )
        self._btn_wet.bind(on_release=lambda b: self._set_wet(True))
        mid_row.add_widget(self._btn_dry)
        mid_row.add_widget(self._btn_wet)
        mid_row.add_widget(Label(text="调节大小", size_hint=(None, 1), width=dp(60), font_size=dp(11), color=DARK["sub"]))
        size_slider = Slider(min=4, max=30, value=self._radius, size_hint=(1, 1))
        size_slider.bind(value=self._on_size_change)
        mid_row.add_widget(size_slider)
        self._pct_lbl = Label(text="40%", size_hint=(None, 1), width=dp(32), font_size=dp(11), color=DARK["accent"], bold=True)
        mid_row.add_widget(self._pct_lbl)
        panel.add_widget(mid_row)

        # 色彩成分分析（参考图1：黄/红/黑进度条）
        comp_row = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2), padding=(dp(12), 0, dp(12), dp(4)))
        comp_row.bind(minimum_height=comp_row.setter("height"))
        panel.add_widget(comp_row)

        self._comp_bars = []
        for label, color_tuple in [("黄色", DARK["yellow"]), ("红色", DARK["orange"]), ("黑色", (0.6, 0.6, 0.6, 1))]:
            item = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(6))
            dot = Label(text="●", size_hint=(None, 1), width=dp(16), font_size=dp(8), color=color_tuple, valign="middle")
            item.add_widget(dot)
            item.add_widget(Label(text=label, size_hint=(None, 1), width=dp(36), font_size=dp(11), color=DARK["text"], halign="left", valign="middle"))
            bar_w = RatioBar(size_hint=(1, 1))
            bar_w._fill = color_tuple
            bar_w.set_ratio(0.5)
            item.add_widget(bar_w)
            pct = Label(text="+0.0%", size_hint=(None, 1), width=dp(44), font_size=dp(10), color=DARK["sub"], valign="middle")
            item.add_widget(pct)
            self._comp_bars.append((bar_w, pct))
            comp_row.add_widget(item)

        # 加料建议容器
        self.advice_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2), padding=(dp(0), 0, dp(0), 0))
        self.advice_box.bind(minimum_height=self.advice_box.setter("height"))
        panel.add_widget(self.advice_box)

    def _center_xhair(self, *args):
        self._crosshair.center = self.cam_area.center

    # ── 模式切换 ──
    def _set_mode(self, mode):
        self._mode = mode
        self._btn_correction.background_color = DARK["selected"] if mode == "correction" else DARK["unselected"]
        self._btn_correction.color = (0.1, 0.1, 0.1, 1) if mode == "correction" else DARK["text"]
        self._btn_current.background_color = DARK["selected"] if mode == "current" else DARK["unselected"]
        self._btn_current.color = (0.1, 0.1, 0.1, 1) if mode == "current" else DARK["text"]

    # ── 干/潮切换 ──
    def _set_wet(self, wet):
        self._wet = wet
        self._btn_dry.background_color = DARK["orange"] if not wet else DARK["unselected"]
        self._btn_wet.background_color = DARK["orange_dark"] if wet else DARK["unselected"]
        self._poll(None)

    def _on_size_change(self, inst, val):
        self._radius = int(val)
        self._pct_lbl.text = f"{int(val / 30 * 100)}%"

    def _surface_adjust(self, color):
        if not self._wet or color is None:
            return color
        r, g, b = color.rgb_normalized
        lift = 0.06
        r = r + (1.0 - r) * lift
        g = g + (1.0 - g) * lift
        b = b + (1.0 - b) * lift
        return Color(int(max(0, min(255, r * 255))), int(max(0, min(255, g * 255))), int(max(0, min(255, b * 255))))

    # ── 生命周期 ──
    def open(self, on_close=None):
        self.on_close = on_close or (lambda: None)
        self._sampling_interval = Clock.schedule_interval(self._poll, 1.0 / 10)

    def request_close(self):
        self.close()
        self.on_close()

    def close(self):
        if self._sampling_interval is not None:
            Clock.unschedule(self._sampling_interval)
            self._sampling_interval = None

    def shutdown(self):
        self.close()

    # ── 轮询（取中心色） ──
    def _poll(self, dt):
        raw = self.camera_view.sample_at(None, None, radius=self._radius)
        if raw is None:
            return
        corrected = self.wb.apply(raw)
        current = self._surface_adjust(corrected)
        self._current = current
        self.preview_block.set_color(current)
        self.delta_lbl.text = "ΔE = --"

        # 更新成分分析条
        if self._comp_bars and len(self._comp_bars) >= 3:
            c_r, c_g, c_b = current.rgb_normalized
            yellow = (c_r + c_g) / 2 * 0.5
            red = c_r * 0.4
            black = (1 - c_r + 1 - c_g + 1 - c_b) / 3 * 0.3
            total = yellow + red + black
            if total > 0:
                y_pct = yellow / total
                r_pct = red / total
                bl_pct = black / total
                self._comp_bars[0][0].set_ratio(y_pct, None)
                self._comp_bars[0][1].text = f"+{y_pct*100:.1f}%"
                self._comp_bars[1][0].set_ratio(r_pct, None)
                self._comp_bars[1][1].text = f"+{r_pct*100:.1f}%"
                self._comp_bars[2][0].set_ratio(bl_pct, None)
                self._comp_bars[2][1].text = f"+{bl_pct*100:.1f}%"

        self._advice_tick += 1
        if self._advice_tick % 5 == 0:
            self._rebuild_advice(current)

    def _rebuild_advice(self, current):
        self.advice_box.clear_widgets()
        # 简单显示当前颜色信息
        info = Label(
            text=f"当前色: {current.hex}  |  Lab({current.lab[0]:.0f}, {current.lab[1]:+.0f}, {current.lab[2]:+.0f})",
            size_hint_y=None, height=dp(18), font_size=dp(10), color=DARK["sub"], halign="left",
        )
        info.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.advice_box.add_widget(info)


# ──────────────────────────────────────────────
# 权限
# ──────────────────────────────────────────────

def request_android_camera_permission(callback=None):
    if not IS_ANDROID:
        if callback:
            callback(True)
        return
    try:
        from android.permissions import (
            check_permission, request_permissions, Permission,
        )
        from android.runnable import run_on_ui_thread

        # MIUI 上已授予权限后再调用 request_permissions 可能不触发回调。
        # 先检查，已授权则直接跳过。
        if check_permission(Permission.CAMERA):
            crash_log.write_crash("[perm] camera already granted, skip request\n")
            if callback:
                callback(True)
            return

        def _cb(results):
            granted = any(results) if isinstance(results, (list, tuple)) else bool(results)
            crash_log.write_crash("[perm] camera permission results=%s\n" % (results,))
            if callback:
                callback(granted)

        run_on_ui_thread(lambda: request_permissions([Permission.CAMERA], _cb))()
    except Exception as e:
        import traceback as _tb
        crash_log.write_crash("[perm] request failed: %s\n%s\n" % (e, _tb.format_exc()))
        if callback:
            callback(True)


# ──────────────────────────────────────────────
# 应用
# ──────────────────────────────────────────────

class ColorAssistantApp(App):
    def build(self):
        _boot_marker("2-build-entered")
        try:
            root = self._build_impl()
            # 启动成功后，若上次运行曾崩溃，弹出上次的堆栈供截图回传
            Clock.schedule_once(lambda dt: self._show_last_crash(), 0.6)
            return root
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            crash_log.write_crash("\n----- BUILD CRASH -----\n%s\n" % tb)
            _boot_marker("build-failed")
            self._build_failed = True
            return self._error_screen(tb)

    def _error_screen(self, tb):
        """构建失败时显示错误堆栈（用户可直接截图回传，不依赖文件传输）。"""
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        _bg(box, THEME["bg"])
        box.add_widget(_lbl("启动出错 - 请截图发回开发者", size=dp(30),
                             font_size=dp(15), bold=True, color=THEME["danger"]))
        sv = ScrollView()
        content = Label(
            text=tb or "未知错误", font_size=dp(11), size_hint_y=None,
            color=(0.15, 0.15, 0.15, 1), halign="left", valign="top",
        )
        content.bind(texture_size=lambda i, v: setattr(content, "height", v[1]))
        content.bind(width=lambda i, v: setattr(content, "text_size", (v[0], None)))
        sv.add_widget(content)
        box.add_widget(sv)
        btn = Button(text="关闭应用", size_hint=(1, None), height=dp(46),
                     background_color=THEME["danger"], color=(1, 1, 1, 1))
        btn.bind(on_release=lambda *a: App.get_running_app().stop())
        box.add_widget(btn)
        return box

    def _show_last_crash(self):
        """弹窗显示上次运行的崩溃堆栈（弹一次，截图即可）。"""
        try:
            seg = crash_log.pop_unshown_crash()
            if not seg:
                return
            from kivy.uix.popup import Popup
            box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
            box.add_widget(_lbl("上次运行崩溃记录 - 请截图发回", size=dp(30),
                                 font_size=dp(14), bold=True, color=THEME["danger"]))
            sv = ScrollView()
            content = Label(
                text=seg, font_size=dp(10), size_hint_y=None,
                color=(0.15, 0.15, 0.15, 1), halign="left", valign="top",
            )
            content.bind(texture_size=lambda i, v: setattr(content, "height", v[1]))
            content.bind(width=lambda i, v: setattr(content, "text_size", (v[0], None)))
            sv.add_widget(content)
            box.add_widget(sv)
            btn = Button(text="关闭", size_hint=(1, None), height=dp(44),
                         background_color=THEME["label_2"], color=(1, 1, 1, 1))
            box.add_widget(btn)
            popup = Popup(title="崩溃诊断", content=box,
                          size_hint=(0.95, 0.85), auto_dismiss=True)
            btn.bind(on_release=popup.dismiss)
            popup.open()
        except Exception:
            pass

    def _build_impl(self):
        self.title = "AI 调色助手 v1.2.2"
        Window.clearcolor = THEME["bg"]

        self.root = FloatLayout()
        self.main_box = BoxLayout(orientation="vertical", spacing=0)
        self.root.add_widget(self.main_box)

        # ── 启动画面 ──
        from kivy.uix.image import Image as KivyImage
        splash = FloatLayout()
        _bg(splash, DARK["bg"])
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
        if os.path.exists(logo_path):
            try:
                logo_img = KivyImage(
                    source=logo_path, size_hint=(None, None),
                    size=(dp(260), dp(180)), pos_hint={"center_x": 0.5, "center_y": 0.55},
                    keep_ratio=True, allow_stretch=True,
                )
                splash.add_widget(logo_img)
            except Exception as e:
                crash_log.write_crash("[boot] logo load failed: %s\n" % (e,))
                splash.add_widget(_lbl("CHENGDU\n无痕修复工作室", size=dp(80), font_size=dp(20), bold=True,
                                       color=(1, 1, 1, 1), halign="center"))
        else:
            splash.add_widget(_lbl("CHENGDU\n无痕修复工作室", size=dp(80), font_size=dp(20), bold=True,
                                   color=(1, 1, 1, 1), halign="center"))
        splash.add_widget(_lbl("v1.2.2", size=dp(30), font_size=dp(12), color=(0.6, 0.6, 0.7, 1), halign="center",
                               width=dp(60)))
        splash.children[-1].pos_hint = {"center_x": 0.5, "y": 0.08}
        self.root.add_widget(splash)
        _boot_marker("3-splash-added")
        Clock.schedule_once(lambda dt: self._fade_out(splash), 2.0)

        # ── 顶栏 ──
        title_bar = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(6), padding=(dp(16), 0, dp(16), 0))
        _bg(title_bar, THEME["card"])
        with title_bar.canvas.after:
            GColor(0.78, 0.78, 0.80, 0.5)
            Rectangle(pos=(title_bar.x, title_bar.y), size=(title_bar.width, 0.5))
        title_bar.bind(pos=lambda i, v: _update_sep(i, v), size=lambda i, v: _update_sep(i, v))

        title_bar.add_widget(Label(text="颜色配比分析", size_hint=(1, 1), font_size=dp(17), color=THEME["label"], bold=True))
        self.main_box.add_widget(title_bar)

        # ── 主体（参考图：图片区 + 数据区）──
        landscape = Window.width > Window.height and Window.width > 600
        body = BoxLayout(orientation="horizontal" if landscape else "vertical", spacing=0, padding=0)
        self.camera_view = CameraView(
            on_color_picked=self._on_color_picked,
            size_hint=(0.60, 1) if landscape else (1, 0.60),
        )
        self.info_panel = InfoPanel(size_hint=(0.40, 1) if landscape else (1, 0.40))
        body.add_widget(self.camera_view)
        body.add_widget(self.info_panel)
        _boot_marker("4-body-created")
        self._body = body
        self.main_box.add_widget(body)
        Clock.schedule_once(lambda dt: self.camera_view._center_crosshair(), 0.5)

        # ── 工具栏 ──
        toolbar = BoxLayout(size_hint=(1, None), height=dp(56), spacing=dp(8), padding=(dp(16), dp(8), dp(16), dp(10)))
        _bg(toolbar, THEME["card"])
        with toolbar.canvas.after:
            GColor(0.78, 0.78, 0.80, 0.5)
            Rectangle(pos=(toolbar.x, toolbar.y + toolbar.height), size=(toolbar.width, 0.5))
        toolbar.bind(pos=lambda i, v: _update_toolbar_sep(i, v), size=lambda i, v: _update_toolbar_sep(i, v))

        def _btn(text, color, cb, width=None):
            b = Button(
                text=text, size_hint=(1, 1) if width is None else (None, 1),
                width=width or 0, font_size=dp(12),
                background_color=color, background_normal="", color=(1, 1, 1, 1),
            )
            b.bind(on_release=cb)
            return b

        toolbar.add_widget(_btn("AI辅助调色", (0.42, 0.42, 0.9, 1), lambda b: self._on_open_mix()))
        self.main_box.add_widget(toolbar)

        self._current_color = None
        self.mix_screen = None
        Clock.schedule_once(self._init_camera, 1.0)
        _boot_marker("5-build-returning")
        return self.root

    def _fade_out(self, splash):
        def _do(dt):
            try:
                self.root.remove_widget(splash)
            except Exception:
                pass
        Clock.schedule_once(_do, 0.5)

    def _init_camera(self, dt):
        if getattr(self, "_build_failed", False):
            return
        crash_log.write_crash("[init] _init_camera called\n")
        request_android_camera_permission(self._on_permission_result)
        # 安全兜底：如果 5 秒后摄像头还没启动，尝试强制启动
        Clock.schedule_once(self._camera_safety_timeout, 5.0)

    def _camera_safety_timeout(self, dt):
        cv = self.camera_view
        if cv._camera_started:
            return
        crash_log.write_crash("[init] safety timeout: camera not started, force-starting\n")
        crash_log.write_crash("[init]  kivy_camera=%s _cam_sched=%s\n" % (cv.kivy_camera, getattr(cv, "_cam_sched", False)))
        cv.start_camera()

    def _on_permission_result(self, granted):
        crash_log.write_crash("[init] _on_permission_result granted=%s\n" % (granted,))
        if granted:
            self.camera_view.start_camera()
        else:
            self.info_panel._show_permission_denied()

    def _on_color_picked(self, color):
        self._current_color = color
        self.info_panel.show_analysis(color)

    def _on_center_pick(self):
        color = self.camera_view.pick_center()
        if color:
            self._on_color_picked(color)

    def _on_dominant_pick(self):
        frame = self.camera_view.get_frame()
        if frame is not None:
            self._on_color_picked(extract_dominant_color(frame, k=3))

    def _on_report(self):
        if self._current_color:
            self.info_panel.show_report(self._current_color)

    def _on_open_mix(self):
        if self.mix_screen is not None:
            return
        if self.camera_view.parent is not None:
            self.camera_view.parent.remove_widget(self.camera_view)
        self.camera_view.size_hint = (1, 1)
        self.mix_screen = AiMixScreen(camera_view=self.camera_view)
        self.mix_screen.size_hint = (1, 1)
        self.root.add_widget(self.mix_screen)
        self.mix_screen.cam_area.add_widget(self.camera_view)
        self.mix_screen.open(on_close=self._on_close_mix)

    def _on_close_mix(self):
        if self.mix_screen is None:
            return
        self.mix_screen.shutdown()
        landscape = Window.width > Window.height and Window.width > 600
        self.camera_view.size_hint = (0.60, 1) if landscape else (1, 0.60)
        self.mix_screen.cam_area.remove_widget(self.camera_view)
        self._body.add_widget(self.camera_view, index=0)
        self.root.remove_widget(self.mix_screen)
        self.mix_screen = None


if __name__ == "__main__":
    ColorAssistantApp().run()
