"""
AI 调色助手 - 主程序（设备安全渲染版）

针对部分 Android GPU 驱动不支持 Kivy 矩阵变换/Line/Ellipse 指令的问题，
本版本只使用 Rectangle / RoundedRectangle / Label 等默认 shader 必通的图元：
- 摄像头旋转改用纹理坐标映射（tex_coords），不做 GPU 矩阵变换
- 比例条/色块/卡片全部用矩形绘制
- 准星/取样点用文字符号表示

功能（模板两屏）：
1. 色彩分析：点击取色 → 色块+名称+HEX、商用色卡匹配、调色配方比例条、和谐配色、完整报告
2. AI 调色辅助：双点取样（样板区/调整区）实时 ΔE、差量加料建议、干/潮物检测、取样大小调节、白卡校色
"""

import math
import os

# ── 中文字体注册（Android 默认字体不支持中文）──
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

def _find_cjk_font():
    candidates = [
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.otf"),
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.ttf"),
        "/system/fonts/NotoSansSC-Regular.otf",
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
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

import crash_log
_crash_path = crash_log.install()

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

# ── 主题色 ──
THEME = {
    "bg": (0.94, 0.94, 0.96, 1),
    "card": (1, 1, 1, 1),
    "label": (0.12, 0.12, 0.15, 1),
    "label_2": (0.45, 0.45, 0.5, 1),
    "primary": (0.0, 0.48, 1, 1),
    "success": (0.2, 0.78, 0.35, 1),
    "warning": (1, 0.58, 0, 1),
    "danger": (1, 0.23, 0.19, 1),
}
DARK = {
    "bg": (0.09, 0.10, 0.13, 1),
    "card": (0.13, 0.15, 0.19, 1),
    "bar": (0.10, 0.11, 0.15, 1),
    "text": (0.92, 0.94, 0.97, 1),
    "sub": (0.55, 0.60, 0.68, 1),
    "gold": (1, 0.84, 0.25, 1),
    "accent": (0.35, 0.78, 1, 1),
}


def _bg(widget, rgba, radius=0):
    """给 widget 画一个跟随 pos/size 的矩形背景（只用安全图元）。"""
    with widget.canvas.before:
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

        self.tex_view = TexView(size_hint=(1, 1))
        self.tex_view.set_rotation(self._rotation)
        self.add_widget(self.tex_view)

        self._placeholder = Label(
            text="摄像头启动中…", font_size=dp(14), color=(0.45, 0.45, 0.5, 1),
        )
        self.add_widget(self._placeholder)

        self.crosshair = Label(
            text="＋", font_size=dp(26), color=(1, 1, 1, 0.95),
            size_hint=(None, None), size=(dp(34), dp(34)),
            outline_width=2, outline_color=(0, 0, 0, 0.8),
        )
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
        if self._placeholder.parent is not None:
            self.remove_widget(self._placeholder)
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
        self.container = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(10), padding=dp(6),
        )
        self.container.bind(minimum_height=self.container.setter("height"))
        self.add_widget(self.container)
        self._show_placeholder()

    def _clear(self):
        self.container.clear_widgets()

    def _card(self, title=None):
        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(12))
        body.bind(minimum_height=body.setter("height"))
        _bg(body, THEME["card"], radius=dp(10))
        if title:
            body.add_widget(_lbl(title, size=dp(22), font_size=dp(13), bold=True))
        self.container.add_widget(body)
        return body

    def _scroll_top(self):
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 1), 0.15)

    def _show_placeholder(self):
        self._clear()
        c = self._card("调色助手")
        c.add_widget(_lbl("等待取色...", size=dp(24), font_size=dp(15), color=THEME["label_2"]))
        c.add_widget(_lbl(
            "1. 点击摄像头画面任意位置取色\n2. 或点击「中心取色」/「提取主色」\n3. 系统将分析颜色并给出调色配方",
            size=dp(54), font_size=dp(12), color=THEME["label_2"],
        ))

    def _show_permission_denied(self):
        self._clear()
        c = self._card("提示")
        c.add_widget(_lbl("[color=FF3B30]摄像头权限被拒绝[/color]", size=dp(24), font_size=dp(15)))
        c.add_widget(_lbl("请在系统设置中授予摄像头权限，然后重新打开应用。", size=dp(36), font_size=dp(12), color=THEME["label_2"]))

    def show_crash_path(self, path):
        self._clear()
        c = self._card("崩溃日志位置")
        c.add_widget(_lbl("应用若异常闪退，日志会自动写入：", size=dp(20), font_size=dp(12), color=THEME["label_2"]))
        c.add_widget(_lbl(f"[color=007AFF]{path}[/color]", size=dp(30), font_size=dp(11)))
        self._scroll_top()

    def show_analysis(self, color):
        self._clear()
        analysis = self.advisor.analyze(color)

        # 采集颜色
        c = self._card()
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(10))
        sw = SwatchWidget(size_hint=(None, 1), width=dp(44))
        sw.set_color(color)
        row.add_widget(sw)
        row.add_widget(_lbl(f"[b]{analysis.hex_code}[/b]  「{analysis.name}」", font_size=dp(15)))
        c.add_widget(row)
        c.add_widget(_lbl(
            f"{analysis.temperature} | {analysis.brightness} | {analysis.saturation_level}",
            size=dp(18), font_size=dp(11), color=THEME["label_2"],
        ))
        c.add_widget(_lbl(f"感受：{analysis.mood}", size=dp(18), font_size=dp(11), color=THEME["label_2"]))
        L, a, b = color.lab
        C = math.hypot(a, b)
        h = math.degrees(math.atan2(b, a)) % 360.0
        c.add_widget(_lbl(
            f"Lab ({L:.1f}, {a:+.1f}, {b:+.1f})   LCh C*={C:.1f} h°={h:.1f}",
            size=dp(18), font_size=dp(11), color=THEME["label_2"],
        ))

        # 商用色卡匹配
        if analysis.paint_matches:
            pc = self._card("商用色卡匹配")
            for m in analysis.paint_matches[:4]:
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(8))
                s = SwatchWidget(size_hint=(None, 1), width=dp(22))
                s.set_color(m.color if hasattr(m, "color") else None)
                row.add_widget(s)
                row.add_widget(_lbl(f"{m.display}   ΔE={m.delta_e:.1f}", font_size=dp(12)))
                pc.add_widget(row)

        # 调色配方（比例条可视化）
        rc = self._card("参考颜色配方")
        recipes = self.advisor.suggest_recipe(color, top_n=1)
        pname_color = {}
        for p in getattr(self.advisor.recipe_finder, "pigments", []) or []:
            pname_color[p.name] = p.color
        if recipes:
            rec = recipes[0]
            rc.add_widget(_lbl(f"方案 ΔE={rec.delta_e:.1f}", size=dp(18), font_size=dp(11), color=THEME["label_2"]))
            for name, _hex, ratio in rec.components:
                row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(6))
                s = SwatchWidget(size_hint=(None, 1), width=dp(22))
                s.set_color(pname_color.get(name))
                row.add_widget(s)
                row.add_widget(_lbl(name, size=dp(26), width=dp(56), font_size=dp(12), bold=True))
                bar = RatioBar(size_hint=(1, 1))
                bar.set_ratio(ratio, pname_color.get(name))
                row.add_widget(bar)
                row.add_widget(_lbl(f"{ratio:.0%}", size=dp(26), width=dp(40), font_size=dp(12), bold=True, halign="center"))
                rc.add_widget(row)
        else:
            rc.add_widget(_lbl("暂无配方", size=dp(20), font_size=dp(12), color=THEME["label_2"]))

        # 和谐配色
        hc = self._card("和谐配色")
        for scheme, colors in self.advisor.suggest_harmony(color).items():
            txts = "  ".join(x.hex for x in colors)
            hc.add_widget(_lbl(f"{scheme}: {txts}", size=dp(18), font_size=dp(11), color=THEME["label_2"]))

        self._scroll_top()

    def show_report(self, color):
        self._clear()
        c = self._card("完整调色报告")
        report = self.advisor.generate_full_report(color)
        c.add_widget(_lbl(report, font_size=dp(11)))
        self._scroll_top()


# ──────────────────────────────────────────────
# AI 辅助调色（双点取样）
# ──────────────────────────────────────────────

class DragMarker(Widget):
    """可拖动取样点：彩色方块 + 文字标签（不用 Line/Ellipse）。"""

    def __init__(self, title, rgba, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.rgba = rgba
        self.size_hint = (None, None)
        self.size = (dp(64), dp(64))
        self.on_drag = None
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            GColor(*self.rgba)
            RoundedRectangle(pos=(self.x + dp(14), self.y + dp(4), ), size=(dp(36), dp(36)), radius=[dp(6)])
            GColor(1, 1, 1, 0.9)
            RoundedRectangle(pos=(self.x + dp(29), self.y + dp(19)), size=(dp(6), dp(6)), radius=[dp(2)])
        # 标签用 canvas 外不行，这里直接画文字到 canvas 也不安全，改用子 Label
        if not getattr(self, "_lab", None):
            self._lab = Label(
                text=self.title, font_size=dp(11), color=(1, 1, 1, 0.95),
                size_hint=(None, None), size=(dp(64), dp(20)),
                outline_width=2, outline_color=(0, 0, 0, 0.8),
            )
            self.add_widget(self._lab)
        self._lab.center_x = self.center_x
        self._lab.y = self.y + dp(40)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return
        p = self.parent
        if p is None:
            return
        self.center_x = max(0, min(p.width, touch.x))
        self.center_y = max(0, min(p.height, touch.y))
        if self.on_drag:
            self.on_drag(self)

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return
        touch.ungrab(self)


class AiMixScreen(BoxLayout):
    """AI 辅助调色：双点取样 · 实时 ΔE · 差量加料建议 · 干/潮检测。"""

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
        self.on_close = None
        self._build_ui()

    def _build_ui(self):
        _bg(self, DARK["bg"])
        # 顶栏
        bar = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(6), padding=(dp(6), 0, dp(6), 0))
        _bg(bar, DARK["bar"])
        self.btn_back = Button(
            text="‹ 返回", size_hint=(None, 1), width=dp(62),
            font_size=dp(14), color=DARK["text"], background_color=(0, 0, 0, 0), background_normal="",
        )
        self.btn_back.bind(on_release=lambda b: self.request_close())
        bar.add_widget(self.btn_back)
        bar.add_widget(Label(text="AI 辅助调色", size_hint=(1, 1), font_size=dp(16), color=DARK["text"], bold=True))
        self.btn_cal = Button(
            text="白卡校色", size_hint=(None, 1), width=dp(82),
            font_size=dp(12), color=(0.04, 0.07, 0.12, 1), background_color=DARK["accent"], background_normal="",
        )
        self.btn_cal.bind(on_release=lambda b: self._do_calibrate())
        bar.add_widget(self.btn_cal)
        self.bar_status = Label(text="", size_hint=(None, 1), width=dp(54), font_size=dp(11), color=DARK["accent"])
        bar.add_widget(self.bar_status)
        self.add_widget(bar)

        # 主体：竖屏上下 / 横屏左右
        landscape = Window.width > Window.height
        body = BoxLayout(orientation="horizontal" if landscape else "vertical", spacing=dp(6), padding=dp(6))
        self.add_widget(body)

        self.cam_area = FloatLayout()
        self.cam_area.size_hint = (0.62, 1) if landscape else (1, 0.5)
        _bg(self.cam_area, (0.16, 0.17, 0.21, 1))
        body.add_widget(self.cam_area)

        scroll = ScrollView(size_hint=(0.38, 1) if landscape else (1, 0.5))
        scroll.bar_width = dp(2)
        body.add_widget(scroll)
        self.info_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=dp(4))
        self.info_box.bind(minimum_height=self.info_box.setter("height"))
        scroll.add_widget(self.info_box)

        # 色差卡片
        pc = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(10))
        pc.bind(minimum_height=pc.setter("height"))
        _bg(pc, DARK["card"], radius=dp(10))
        self.delta_lbl = Label(
            text="ΔE = --", size_hint_y=None, height=dp(40),
            font_size=dp(24), color=DARK["gold"], bold=True, halign="center", valign="middle",
        )
        self.delta_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(self.delta_lbl)
        pv_t = Label(text="实时预览（调整区校正后）", size_hint_y=None, height=dp(16), font_size=dp(11), color=DARK["sub"], halign="left")
        pv_t.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(pv_t)
        self.preview_block = SwatchWidget(size_hint=(1, None), height=dp(56))
        pc.add_widget(self.preview_block)
        self.preview_hex = Label(text="--", size_hint_y=None, height=dp(16), font_size=dp(11), color=DARK["text"], halign="left")
        self.preview_hex.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(self.preview_hex)
        self.info_box.add_widget(pc)

        # 干/潮检测
        det = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        self.btn_dry = Button(text="干物检测", size_hint=(1, 1), font_size=dp(12), background_normal="")
        self.btn_dry.bind(on_release=lambda b: self._set_wet(False))
        self.btn_wet = Button(text="潮物检测", size_hint=(1, 1), font_size=dp(12), background_normal="")
        self.btn_wet.bind(on_release=lambda b: self._set_wet(True))
        det.add_widget(self.btn_dry)
        det.add_widget(self.btn_wet)
        self.info_box.add_widget(det)
        self._paint_detect_buttons()

        # 取样大小
        sz = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
        sz.add_widget(Label(text="调节大小", size_hint=(None, 1), width=dp(62), font_size=dp(12), color=DARK["text"]))
        slider = Slider(min=4, max=30, value=self._radius, size_hint=(1, 1))
        slider.bind(value=self._on_size_change)
        sz.add_widget(slider)
        self._pct_lbl = Label(text="40%", size_hint=(None, 1), width=dp(40), font_size=dp(12), color=DARK["accent"], bold=True)
        sz.add_widget(self._pct_lbl)
        self.info_box.add_widget(sz)

        # 加料建议容器
        self.advice_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(2))
        self.advice_box.bind(minimum_height=self.advice_box.setter("height"))
        self.info_box.add_widget(self.advice_box)

        tip = Label(
            text="拖动两个方块取样：样板区=想要的颜色，调整区=当前颜料色。开启潮物检测会把湿料校正为干态后再算配比。",
            size_hint_y=None, height=dp(40), font_size=dp(10), color=DARK["sub"], halign="left", valign="top",
        )
        tip.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.info_box.add_widget(tip)

    # ── 开关/状态 ──
    def _set_wet(self, wet):
        self._wet = wet
        self._paint_detect_buttons()
        self.bar_status.text = "潮物" if wet else ""
        self._poll(None)

    def _paint_detect_buttons(self):
        self.btn_dry.background_color = (0.25, 0.55, 0.35, 1) if not self._wet else (0.25, 0.27, 0.32, 1)
        self.btn_wet.background_color = (0.2, 0.5, 0.8, 1) if self._wet else (0.25, 0.27, 0.32, 1)
        self.btn_dry.color = (1, 1, 1, 1)
        self.btn_wet.color = (1, 1, 1, 1)

    def _on_size_change(self, inst, val):
        self._radius = int(val)
        self._pct_lbl.text = f"{int(val / 30 * 100)}%"

    def _do_calibrate(self):
        color = self.camera_view.sample_at(None, None, radius=15)
        if color:
            self.wb.calibrate(color)
            self.bar_status.text = "已校色"

    def _surface_adjust(self, color):
        if not self._wet or color is None:
            return color
        r, g, b = color.rgb_normalized
        lift = 0.06
        r = r + (1.0 - r) * lift
        g = g + (1.0 - g) * lift
        b = b + (1.0 - b) * lift
        return Color(int(max(0, min(255, r * 255))), int(max(0, min(255, g * 255))), int(max(0, min(255, b * 255))))

    def _sample_marker(self, marker, is_current=False):
        raw = self.camera_view.sample_at(marker.center_x, marker.center_y, radius=self._radius)
        if raw is None:
            return None
        corrected = self.wb.apply(raw)
        return self._surface_adjust(corrected) if is_current else corrected

    # ── 生命周期 ──
    def open(self, on_close=None):
        self.on_close = on_close or (lambda: None)
        self.marker_sample = DragMarker("样板区", (1, 0.23, 0.19, 1))
        self.marker_current = DragMarker("调整区", (1, 1, 1, 1))
        for m in (self.marker_sample, self.marker_current):
            self.cam_area.add_widget(m)
        Clock.schedule_once(self._place_markers, 0)
        self._sampling_interval = Clock.schedule_interval(self._poll, 1.0 / 10)

    def _place_markers(self, dt=None):
        if self.cam_area.width <= 1:
            Clock.schedule_once(self._place_markers, 0.2)
            return
        self.marker_sample.center = (self.cam_area.width * 0.3, self.cam_area.height * 0.5)
        self.marker_current.center = (self.cam_area.width * 0.7, self.cam_area.height * 0.5)

    def request_close(self):
        self.close()
        self.on_close()

    def close(self):
        if self._sampling_interval is not None:
            Clock.unschedule(self._sampling_interval)
            self._sampling_interval = None

    def shutdown(self):
        self.close()

    # ── 轮询 ──
    def _poll(self, dt):
        target = self._sample_marker(self.marker_sample)
        current = self._sample_marker(self.marker_current, is_current=True)
        if target is None or current is None:
            return
        self._target, self._current = target, current
        de = current.distance(target)
        self.delta_lbl.text = f"ΔE = {de:.1f}"
        self.preview_block.set_color(current)
        self.preview_hex.text = f"{current.hex}  →  目标 {target.hex}"

        self._advice_tick += 1
        if self._advice_tick % 5 == 0:
            self._rebuild_advice(current, target)

    def _rebuild_advice(self, current, target):
        self.advice_box.clear_widgets()
        t = Label(text="差量加料建议", size_hint_y=None, height=dp(20), font_size=dp(13), color=DARK["text"], bold=True, halign="left")
        t.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.advice_box.add_widget(t)

        pname_color = {}
        for p in getattr(self.advisor.recipe_finder, "pigments", []) or []:
            pname_color[p.name] = p.color

        cur = current
        steps = []
        for _ in range(3):
            s = self.advisor.suggest_next_pigment(cur, target)
            if not s:
                break
            steps.append(s)
            w = s["ratio"]
            cur = ColorMixer.mix_subtractive([cur, s["pigment"].color], [1 - w, w])
        if not steps:
            ok = Label(text="已非常接近目标色，无需加料。", size_hint_y=None, height=dp(20), font_size=dp(12), color=DARK["gold"], halign="left")
            ok.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            self.advice_box.add_widget(ok)
        for i, s in enumerate(steps, 1):
            pig = s["pigment"]
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(6))
            sw = SwatchWidget(size_hint=(None, 1), width=dp(24))
            sw.set_color(pig.color)
            row.add_widget(sw)
            row.add_widget(Label(
                text=f"{i}. {pig.name} +{s['ratio']:.0%}",
                size_hint=(1, 1), font_size=dp(12), color=DARK["text"], halign="left", valign="middle",
            ))
            row.add_widget(Label(
                text=f"ΔE→{s['delta_e']:.1f}",
                size_hint=(None, 1), width=dp(64), font_size=dp(11), color=DARK["gold"], valign="middle",
            ))
            self.advice_box.add_widget(row)
            desc = pigment_description(pig.name)
            if desc:
                d = Label(text=desc, size_hint_y=None, height=dp(14), font_size=dp(10), color=DARK["sub"], halign="left")
                d.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
                self.advice_box.add_widget(d)


# ──────────────────────────────────────────────
# 权限
# ──────────────────────────────────────────────

def request_android_camera_permission(callback=None):
    if not IS_ANDROID:
        if callback:
            callback(True)
        return
    try:
        from android.permissions import request_permissions, Permission
        from android.runnable import run_on_ui_thread

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
        self.title = "AI 调色助手"
        Window.clearcolor = THEME["bg"]

        self.root = FloatLayout()
        self.main_box = BoxLayout(orientation="vertical", spacing=0)
        self.root.add_widget(self.main_box)

        # 顶栏
        title_bar = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(8), padding=(dp(6), 0, dp(6), 0))
        _bg(title_bar, THEME["card"])
        title_bar.add_widget(Label(text="AI 调色助手", size_hint=(1, 1), font_size=dp(17), color=THEME["label"], bold=True))
        btn_report = Button(
            text="完整报告", size_hint=(None, 1), width=dp(84),
            font_size=dp(13), background_color=THEME["primary"], background_normal="", color=(1, 1, 1, 1),
        )
        btn_report.bind(on_release=lambda b: self._on_report())
        title_bar.add_widget(btn_report)
        self.main_box.add_widget(title_bar)

        # 主体
        landscape = Window.width > Window.height and Window.width > 600
        body = BoxLayout(orientation="horizontal" if landscape else "vertical", spacing=dp(6), padding=dp(6))
        self.camera_view = CameraView(
            on_color_picked=self._on_color_picked,
            size_hint=(0.55, 1) if landscape else (1, 0.55),
        )
        self.info_panel = InfoPanel(size_hint=(0.45, 1) if landscape else (1, 0.45))
        body.add_widget(self.camera_view)
        body.add_widget(self.info_panel)
        self._body = body
        self.main_box.add_widget(body)
        Clock.schedule_once(lambda dt: self.camera_view._center_crosshair(), 0.5)

        # 工具栏
        toolbar = BoxLayout(size_hint=(1, None), height=dp(56), spacing=dp(8), padding=(dp(10), dp(8), dp(10), dp(8)))
        _bg(toolbar, THEME["card"])

        def _btn(text, color, cb, width=None):
            b = Button(
                text=text, size_hint=(1, 1) if width is None else (None, 1),
                width=width or 0, font_size=dp(13),
                background_color=color, background_normal="", color=(1, 1, 1, 1),
            )
            b.bind(on_release=cb)
            return b

        toolbar.add_widget(_btn("中心取色", THEME["primary"], lambda b: self._on_center_pick()))
        toolbar.add_widget(_btn("提取主色", THEME["warning"], lambda b: self._on_dominant_pick()))
        toolbar.add_widget(_btn("AI辅助调色", (0.42, 0.42, 0.9, 1), lambda b: self._on_open_mix()))
        toolbar.add_widget(_btn("旋转画面", (0.55, 0.55, 0.6, 1), lambda b: self.camera_view.rotate_cw(), width=dp(80)))
        toolbar.add_widget(_btn("日志", (0.45, 0.45, 0.5, 1), lambda b: self.info_panel.show_crash_path(_crash_path), width=dp(52)))
        self.main_box.add_widget(toolbar)

        self._current_color = None
        self.mix_screen = None
        Clock.schedule_once(self._init_camera, 1.0)
        return self.root

    def _init_camera(self, dt):
        request_android_camera_permission(self._on_permission_result)

    def _on_permission_result(self, granted):
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
        self.camera_view.size_hint = (0.55, 1) if landscape else (1, 0.55)
        self.mix_screen.cam_area.remove_widget(self.camera_view)
        self._body.add_widget(self.camera_view, index=0)
        self.root.remove_widget(self.mix_screen)
        self.mix_screen = None


if __name__ == "__main__":
    ColorAssistantApp().run()
