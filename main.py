"""
AI 调色助手 - 主程序

基于 Kivy 的摄像头取色与 AI 调色配方推荐应用。
桌面端使用 OpenCV 摄像头，Android 端使用 Kivy 原生 Camera。
可打包为 Android APK。

用法:
    python main.py
"""

import math
import os
import sys

# ── 中文字体注册（Android 默认字体不支持中文）──
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

def _find_cjk_font():
    """在所有平台上寻找支持中文的字体文件。"""
    candidates = [
        # 项目内置字体
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.otf"),
        os.path.join(_FONT_DIR, "NotoSansSC-Regular.ttf"),
        # Android 系统字体
        "/system/fonts/NotoSansSC-Regular.otf",
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        # Windows 系统字体
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        # Linux 系统字体
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

# ── 平台检测 ──
def _is_android():
    try:
        from kivy.utils import platform
        return platform == "android"
    except Exception:
        return False

IS_ANDROID = _is_android()

# 尽早安装崩溃捕获，确保启动/初始化期的异常也能落盘
import crash_log
_crash_path = crash_log.install()

# ── OpenCV 可选导入 ──
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 注意：不在此处顶层导入 numpy。
# 桌面端 numpy 随 OpenCV 提供；Android 端不安装 numpy，仅用 Frame（纯 Python）。

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.slider import Slider
from kivy.graphics import (
    Color as GraphicsColor,
    Rectangle,
    RoundedRectangle,
    Line,
    Ellipse,
    PushMatrix,
    PopMatrix,
    Translate,
    Rotate,
    Scale,
)
from kivy.core.window import Window
from kivy.metrics import dp

# 注册中文字体（必须在 Label 首次渲染前执行）
_cjk_font = _find_cjk_font()
if _cjk_font:
    from kivy.core.text import LabelBase
    LabelBase.register("Roboto", _cjk_font, _cjk_font, _cjk_font, _cjk_font)

from color_engine import (
    Color,
    Frame,
    RecipeFinder,
    ColorMixer,
    average_color_region,
    extract_dominant_color,
    pigment_description,
    WhiteBalance,
)
from ai_assistant import ColorAdvisor, nearest_named_color
from paint_library import best_match


# ──────────────────────────────────────────────
# iOS 浅色主题配色
# ──────────────────────────────────────────────
THEME = {
    "bg":        (0.949, 0.949, 0.953, 1),   # 系统灰（F2F2F7）
    "card":      (1.000, 1.000, 1.000, 1),   # 卡片白
    "card_alt":  (0.969, 0.969, 0.973, 1),   # 次级卡片
    "primary":   (0.000, 0.478, 1.000, 1),   # iOS 蓝 007AFF
    "primary_d": (0.038, 0.337, 0.780, 1),   # 深蓝（点按）
    "label":     (0.110, 0.110, 0.118, 1),   # 主文字 1C1C1E
    "label_2":   (0.557, 0.557, 0.576, 1),   # 次要文字 8E8E93
    "separator": (0.780, 0.780, 0.800, 1),   # 分隔线
    "success":   (0.204, 0.780, 0.349, 1),   # 绿 34C759
    "warning":   (1.000, 0.580, 0.000, 1),   # 橙 FF9400
    "danger":    (1.000, 0.271, 0.227, 1),   # 红 FF453A
    "text_on_bg": (0.110, 0.110, 0.118, 1),  # 卡片上文字
}

RC = 12  # 卡片圆角


def _rounded_card(widget, color=THEME["card"], radius=(RC, RC, RC, RC), alpha=1.0):
    """给 widget 画一张圆角卡片背景，返回可随 pos/size 更新的背景 Rectangle。"""
    from kivy.graphics import RoundedRectangle
    with widget.canvas.before:
        GraphicsColor(color[0], color[1], color[2], alpha)
        r = RoundedRectangle(pos=widget.pos, size=widget.size, radius=radius)
    widget.bind(pos=lambda i, v: setattr(r, "pos", i.pos),
                size=lambda i, v: setattr(r, "size", i.size))
    return r


# ──────────────────────────────────────────────
# AI 调色界面深色主题（参考图 2 工业深蓝风）
# ──────────────────────────────────────────────
DARK = {
    "bg":        (0.039, 0.086, 0.157, 1),   # #0a1628
    "title_bg":  (0.102, 0.227, 0.361, 1),   # #1a3a5c 渐变起点
    "card":      (0.118, 0.227, 0.373, 1),   # #1e3a5f
    "card_2":    (0.086, 0.176, 0.314, 1),   # #163050
    "text":      (1.000, 1.000, 1.000, 1),
    "sub":       (0.541, 0.608, 0.702, 1),   # #8a9bb3
    "accent":    (0.961, 0.902, 0.000, 1),   # #f5e600 亮黄
    "orange":    (1.000, 0.420, 0.208, 1),   # #ff6b35
    "orange_2":  (1.000, 0.549, 0.259, 1),   # #ff8c42
    "gold":      (0.941, 0.753, 0.251, 1),   # #f0c040
    "track":     (0.082, 0.204, 0.353, 1),   # 深色轨道
    "red":       (1.000, 0.271, 0.271, 1),   # 样板区红圈
    "sel_bg":    (0.176, 0.294, 0.431, 1),   # 选中按钮背景
}


def _dark_card(widget, color=DARK["card"], radius=[dp(10)]):
    """给 widget 画一张深色圆角卡片背景（参考图 2）。"""
    with widget.canvas.before:
        GraphicsColor(color[0], color[1], color[2], 1)
        r = RoundedRectangle(pos=widget.pos, size=widget.size, radius=radius)
    widget.bind(pos=lambda i, v: setattr(r, "pos", i.pos),
                size=lambda i, v: setattr(r, "size", i.size))
    return r


# ──────────────────────────────────────────────
# 色彩分析可视化组件（参考图 1）
# ──────────────────────────────────────────────

class MeterBar(Widget):
    """双向仪表条：深灰低 + 高亮区 + 彩色指示线（只读，展示分量位置）。"""

    def __init__(self, lo, hi, **kwargs):
        super().__init__(**kwargs)
        self.lo = lo
        self.hi = hi
        self.value = 0.0
        self._tint = (0.0, 0.478, 1.0, 1)
        self.bind(pos=self._redraw, size=self._redraw)

    def set(self, value, tint=None):
        self.value = value
        if tint:
            self._tint = tint
        self._redraw()

    def _norm(self):
        if self.hi - self.lo <= 0:
            return 0.0
        return max(0.0, min(1.0, (self.value - self.lo) / (self.hi - self.lo)))

    def _redraw(self, *args):
        self.canvas.clear()
        W, H = self.width, self.height
        if W <= 1 or H <= 1:
            return
        mid = W * 0.5
        n = self._norm()
        xp = W * n
        with self.canvas:
            GraphicsColor(0.87, 0.87, 0.9, 1)
            Line(points=[0, H / 2, W, H / 2], width=max(2.0, H * 0.4))
            # 高亮区：偏向一侧填充到指示线
            t = self._tint
            GraphicsColor(t[0], t[1], t[2], 0.9)
            lo_x, hi_x = (mid, xp) if xp >= mid else (xp, mid)
            Line(points=[lo_x, H / 2, hi_x, H / 2], width=max(2.0, H * 0.4))
            # 指示线
            GraphicsColor(*t)
            Line(points=[xp, 0, xp, H], width=2.0)
            # 中心刻度
            GraphicsColor(0.6, 0.6, 0.66, 1)
            Line(points=[mid, 0, mid, H], width=1.2)


class PolarHueChart(Widget):
    """极坐标色相图：C* 饱和度 + h° 色相角定位。

    同心圆表示饱和度等级；黄(+b)/红(+a)/蓝(-b)/绿(-a) 四轴；
    蓝色射线指向色相角 h°，其末端的彩色圆点表示当前颜色位置。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__color = None
        self._C = 0.0
        self._h_deg = 0.0
        self._labels = []
        for i, (text, pos) in enumerate([
            ("红(+a)", 0), ("黄(+b)", 1), ("蓝(-b)", 2), ("绿(-a)", 3),
        ]):
            from kivy.uix.label import Label as KLabel
            lb = KLabel(
                text=text, font_size=dp(9), color=(0.45, 0.45, 0.5, 1),
                size_hint=(None, None), size=(dp(40), dp(14)),
                halign="center", valign="middle",
            )
            self._labels.append(lb)
        self.bind(pos=self._redraw, size=self._redraw)

    def set_color(self, color):
        self.__color = color
        if color is not None:
            a, b = color.lab[1], color.lab[2]
            self._C = math.hypot(a, b)
            self._h_deg = math.degrees(math.atan2(b, a)) % 360.0
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        W, H = self.width, self.height
        if W <= 1 or H <= 1:
            return
        cx, cy = W / 2.0, H / 2.0
        R = min(W, H) / 2.0 - 2.0
        h_rad = math.radians(self._h_deg)
        # 取色点半径：饱和度 C 满幅按 60 计（Lab 典型最大 ~128），留余量
        scale = min(1.0, self._C / 70.0)
        xp = cx + math.cos(h_rad) * R * scale
        yp = cy + math.sin(h_rad) * R * scale

        with self.canvas:
            # 同心圆（饱和度环）
            for i in range(1, 4):
                rr = R * i / 4.0
                GraphicsColor(0.84, 0.84, 0.87, 1)
                Line(circle=(cx, cy, rr), width=0.7)
            GraphicsColor(0.74, 0.74, 0.78, 1)
            Line(circle=(cx, cy, R), width=1.1)
            # 十字轴
            GraphicsColor(0.88, 0.88, 0.9, 1)
            Line(points=[cx - R, cy, cx + R, cy], width=0.6)
            Line(points=[cx, cy - R, cx, cy + R], width=0.6)
            # 射线
            if scale > 0.01:
                GraphicsColor(0.0, 0.478, 1.0, 0.55)
                Line(points=[cx, cy, cx + math.cos(h_rad) * R * scale,
                             cy + math.sin(h_rad) * R * scale], width=2.5)
            # 外圈四个象限轴加粗
            GraphicsColor(0.24, 0.85, 0.44, 1)   # 绿 -a 左
            Line(points=[cx - R, cy - 3, cx - R, cy + 3], width=1.4)
            GraphicsColor(1.0, 0.16, 0.18, 1)    # 红 +a 右
            Line(points=[cx + R, cy - 3, cx + R, cy + 3], width=1.4)
            GraphicsColor(1.0, 0.78, 0.05, 1)    # 黄 +b 上
            Line(points=[cx - 3, cy + R, cx + 3, cy + R], width=1.4)
            GraphicsColor(0.28, 0.45, 0.95, 1)   # 蓝 -b 下
            Line(points=[cx - 3, cy - R, cx + 3, cy - R], width=1.4)
            # 当前色点
            if self.__color is not None:
                r, g, b = self.__color.rgb_normalized
                GraphicsColor(r, g, b, 1)
                Ellipse(pos=(xp - 4, yp - 4), size=(8, 8))
                GraphicsColor(0.5, 0.5, 0.5, 1)
                Ellipse(pos=(xp - 5, yp - 5), size=(10, 10))
            else:
                GraphicsColor(0.5, 0.5, 0.55, 1)
                Ellipse(pos=(cx - 3, cy - 3), size=(6, 6))
        # 轴上文字：红右 / 黄上 / 蓝下 / 绿左
        lw2 = dp(20)
        for lb, (tx, ty) in zip(self._labels, [
            (cx + R / 2 + 2, cy - lw2 / 2),      # 红 +a 右
            (cx - lw2 / 2, cy + R / 2 + 2),      # 黄 +b 上
            (cx - lw2 / 2, cy - R / 2 - 2),      # 蓝 -b 下
            (cx - R / 2 - 2, cy - lw2 / 2),      # 绿 -a 左
        ]):
            lb.center = (tx, ty)
            if lb.parent is None:
                self.add_widget(lb)


# ──────────────────────────────────────────────
# Android 权限请求
# ──────────────────────────────────────────────

def request_android_camera_permission(callback=None):
    """在 Android 上请求摄像头权限，桌面端直接回调。"""
    if not IS_ANDROID:
        if callback:
            callback(True)
        return

    from android.permissions import request_permissions, Permission

    def _on_result(permissions, grant_results):
        granted = all(grant_results)
        if callback:
            callback(granted)

    request_permissions([Permission.CAMERA], _on_result)


# ──────────────────────────────────────────────
# 摄像头画面组件
# ──────────────────────────────────────────────

class RotatedImage(Widget):
    """按 0/90/180/270 度旋转绘制 texture，满幅拉伸填满自身。

    Android 摄像头传感器默认横置（landscape），竖屏手机上画面会旋转 90°，
    用 canvas 矩阵变换在 GPU 侧旋转，避免逐帧像素级旋转的开销。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tex = None
        self._rot = 0
        self.bind(pos=self._redraw, size=self._redraw)

    def set_texture(self, tex, rot):
        self._tex = tex
        self._rot = int(rot) % 360
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        tex = self._tex
        if tex is None or self.width <= 1 or self.height <= 1:
            return
        tw, th = tex.size
        rot = self._rot
        # 旋转 90/270 时交换宽高方向的缩放比例，保证旋转后恰好填满
        if rot in (90, 270):
            angle = -90 if rot == 90 else 90
            s1, s2 = self.height / float(tw), self.width / float(th)
        else:
            angle = rot  # 0 或 180
            s1, s2 = self.width / float(tw), self.height / float(th)
        with self.canvas:
            PushMatrix()
            Translate(self.center_x, self.center_y)
            if angle:
                Rotate(angle)
            Scale(s1, s2)
            Rectangle(texture=tex, pos=(-tw / 2.0, -th / 2.0), size=(tw, th))
            PopMatrix()


class CameraView(FloatLayout):
    """摄像头实时画面，支持点击取色。

    桌面端：OpenCV VideoCapture
    Android 端：Kivy 原生 Camera（texture 像素提取）
    """

    def __init__(self, on_color_picked=None, **kwargs):
        super().__init__(**kwargs)
        self.on_color_picked = on_color_picked

        self._frame = None        # BGR/RGBA 数据的 Frame（统一格式）
        self._camera_started = False
        # Android 传感器横置，竖屏手机上画面需顺时针旋转 90°；可用旋转按钮调整
        self._rotation = 90 if IS_ANDROID else 0

        if HAS_CV2 and not IS_ANDROID:
            # ── OpenCV 模式（桌面）──
            self.image_widget = Image(allow_stretch=True, keep_ratio=False)
            self.add_widget(self.image_widget)
            self.capture = None
            self._texture = None
            self._camera_active = False
        else:
            # ── Kivy Camera 模式（Android / 无 OpenCV）──
            # 注意：Kivy 的 Camera 在构造时（_on_index）就会尝试打开摄像头硬件，
            # play=False 并不能阻止这次连接。若此时相机权限还没授予，
            # Camera.open 会抛 "Fail to connect to camera service" 直接闪退。
            # 因此这里绝不在此创建 Camera，改为 RotatedImage 占位显示，
            # 等 start_camera()（权限获批后）再创建。
            self.kivy_camera = None
            self.rotated_img = RotatedImage()
            self.rotated_img.size_hint = (1, 1)
            self.add_widget(self.rotated_img)
            self._placeholder = Label(
                text="摄像头启动中…",
                font_size=dp(14),
                color=(0.45, 0.45, 0.5, 1),
            )
            self.add_widget(self._placeholder)

        # 十字准星
        self.crosshair = CrosshairWidget()
        self.add_widget(self.crosshair)
        self.bind(size=self._center_crosshair)

    def _center_crosshair(self, *args):
        """尺寸变化时把准星放回中心。"""
        self.crosshair.center = self.center

    def rotate_cw(self):
        """画面顺时针旋转 90°（修正传感器方向，仅 Android 生效）。"""
        if HAS_CV2 and not IS_ANDROID:
            return  # 桌面摄像头方向正常，无需旋转
        self._rotation = (self._rotation + 90) % 360
        self.rotated_img.set_texture(
            self.kivy_camera.texture if self.kivy_camera else None,
            self._rotation,
        )

    def start_camera(self, camera_index=0):
        """启动摄像头。"""
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
            # 权限已授予后才创建摄像头并播放。KivyCamera() 构造时会创建 graphics 指令，
            # 只能在 Kivy 主线程执行；而 start_camera 可能被权限回调等非主线程调用，
            # 因此整个 Android 分支统一调度到主线程执行。
            if self.kivy_camera is None and not getattr(self, "_cam_sched", False):
                self._cam_sched = True
                Clock.schedule_once(self._init_android_camera, 0)
            self._camera_started = True

    def _init_android_camera(self, dt):
        """在主线程创建 Android KivyCamera（隐藏，仅作采集器，不直接显示）。"""
        self._cam_sched = False
        if self.kivy_camera is not None:
            return
        try:
            from kivy.uix.camera import Camera as KivyCamera
            c = KivyCamera(
                play=True,
                index=0,
                resolution=(640, 480),
            )
            # 隐藏采集器：画面由 RotatedImage 按 _rotation 旋转渲染。
            # 三重保险（尺寸0 + 透明 + 移出屏幕），防止采集器自身画面漏到界面上。
            c.size_hint = (None, None)
            c.size = (0, 0)
            c.opacity = 0
            c.pos = (-2000, -2000)
            self.add_widget(c)
            self.kivy_camera = c
            crash_log.write_crash("[camera] KivyCamera created ok (hidden capture), play=True\n")
        except Exception as e:
            import traceback as _tb
            crash_log.write_crash("[camera] KivyCamera create FAILED: %s\n%s\n" % (e, _tb.format_exc()))
            self.kivy_camera = None
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

    # ── OpenCV 帧更新 ──

    def _update_cv2_frame(self, dt):
        if not self._camera_active or self.capture is None:
            return

        ret, frame = self.capture.read()
        if not ret:
            return

        # 桌面端才有 OpenCV，numpy 一定可用，这里局部导入
        import numpy as np
        self._frame = Frame(frame.tobytes(), frame.shape[1], frame.shape[0], src="bgr")  # BGR

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb = np.rot90(frame_rgb)
        frame_rgb = np.flipud(frame_rgb)

        buf = frame_rgb.tobytes()
        if (
            self._texture is None
            or self._texture.size[0] != frame_rgb.shape[1]
            or self._texture.size[1] != frame_rgb.shape[0]
        ):
            self._texture = Texture.create(
                size=(frame_rgb.shape[1], frame_rgb.shape[0]),
                colorfmt="rgb",
            )
            self._texture.flip_horizontal = True

        self._texture.blit_buffer(buf, colorfmt="rgb")
        self.image_widget.texture = self._texture
        self.image_widget.canvas.ask_update()

    # ── Kivy Camera 帧更新 ──

    def _update_kivy_frame(self, dt):
        if not hasattr(self, "kivy_camera") or self.kivy_camera is None:
            return

        tex = self.kivy_camera.texture
        if tex is None:
            # 只记录一次，避免刷屏；用于诊断"创建成功但没出画面"
            if not getattr(self, "_tex_none_logged", False):
                self._tex_none_logged = True
                crash_log.write_crash(
                    "[camera] texture is None, camera.index=%s play=%s\n" % (
                        getattr(self.kivy_camera, "index", "?"),
                        getattr(self.kivy_camera, "play", "?"),
                    )
                )
            return

        # 画面渲染（GPU 侧旋转）
        self.rotated_img.set_texture(tex, self._rotation)

        if getattr(self, "_placeholder", None) is not None:
            self.remove_widget(self._placeholder)
            self._placeholder = None
        if not getattr(self, "_geom_logged", False):
            self._geom_logged = True
            ri = self.rotated_img
            kc = self.kivy_camera
            crash_log.write_crash(
                "[layout] cam=%d,%d,%d,%d rot=%d,%d,%d,%d kcam=%d,%d,%d,%d op=%.1f\n" % (
                    self.x, self.y, self.width, self.height,
                    ri.x, ri.y, ri.width, ri.height,
                    kc.x, kc.y, kc.width, kc.height, kc.opacity,
                )
            )

        w, h = tex.size
        try:
            pixels = tex.pixels
            if not pixels:
                return
            # 存为 Frame（原始传感器方向，未旋转），仅在取色时按需解码
            self._frame = Frame(pixels, w, h, src="rgba_flip")
        except Exception:
            pass

    # ── 点击取色 ──

    def frame_coords_for(self, lx, ly, radius=10):
        """把显示区局部坐标 (lx,ly) 逆映射为原始帧坐标，返回 Color。
        取色点传 None 表示显示区中心。"""
        if self._frame is None:
            return None
        frame_h, frame_w = self._frame.shape[:2]
        if self.width <= 0 or self.height <= 0:
            return None

        # 显示区域归一化坐标（allow_stretch 满幅，无 letterbox）
        if lx is None:
            nu, nv = 0.5, 0.5
        else:
            nu = (lx - self.x) / self.width
            nv = (ly - self.y) / self.height
            nu = max(0.0, min(1.0, nu))
            nv = max(0.0, min(1.0, nv))

        # Frame 保持传感器原始方向；显示时旋转了 _rotation，
        # 这里把显示坐标逆映射回原始帧坐标。
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
        """采样显示区局部坐标 (lx,ly) 的颜色，返回 Color 或 None。"""
        return self.frame_coords_for(lx, ly, radius=radius)

    def on_touch_down(self, touch):
        if self._frame is None or not self.collide_point(*touch.pos):
            return False

        color = self.sample_at(touch.x, touch.y, radius=10)
        if color is None:
            return False

        self.crosshair.pos = (touch.x - self.x - 15, touch.y - self.y - 15)

        if self.on_color_picked:
            self.on_color_picked(color)

        return True

    def pick_center(self):
        if self._frame is None:
            return None
        h, w = self._frame.shape[:2]
        color = average_color_region(self._frame, (w // 2, h // 2), radius=15)
        if self.on_color_picked:
            self.on_color_picked(color)
        return color

    def get_frame(self):
        """返回当前帧（BGR numpy 数组），供主色提取等使用。"""
        return self._frame


class CrosshairWidget(Widget):
    """中心十字准星。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (30, 30)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.canvas.clear()
        with self.canvas:
            GraphicsColor(1, 1, 1, 0.8)
            Line(circle=(self.center_x, self.center_y, 12), width=1.5)
            GraphicsColor(0, 0, 0, 0.8)
            Line(circle=(self.center_x, self.center_y, 12.5), width=0.5)
            GraphicsColor(1, 1, 1, 0.8)
            Line(points=[self.center_x - 8, self.center_y, self.center_x + 8, self.center_y], width=1)
            Line(points=[self.center_x, self.center_y - 8, self.center_x, self.center_y + 8], width=1)


class ColorSwatch(BoxLayout):
    """颜色色块 + 标签。"""

    def __init__(self, color: Color, label_text: str = "", **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(36)
        self.spacing = dp(8)

        sw = Widget(size_hint=(None, None), size=(dp(36), dp(36)))
        with sw.canvas:
            r, g, b = color.rgb_normalized
            GraphicsColor(r, g, b, 1)
            Rectangle(pos=sw.pos, size=sw.size)
            GraphicsColor(0.3, 0.3, 0.3, 0.6)
            Line(rectangle=(sw.pos[0], sw.pos[1], sw.size[0], sw.size[1]), width=0.8)
        sw.bind(pos=self._update_swatch, size=self._update_swatch)
        self._swatch = sw
        self.add_widget(sw)

        self.label = Label(
            text=label_text,
            size_hint=(1, None),
            height=dp(36),
            valign="middle",
            halign="left",
            font_size=dp(13),
            color=THEME["label"],
            markup=True,
        )
        self.label.bind(size=self._update_label)
        self.add_widget(self.label)

    def _update_swatch(self, instance, value):
        instance.canvas.clear()
        with instance.canvas:
            r, g, b = self.color.rgb_normalized
            GraphicsColor(r, g, b, 1)
            Rectangle(pos=instance.pos, size=instance.size)
            GraphicsColor(0.3, 0.3, 0.3, 0.6)
            Line(rectangle=(instance.pos[0], instance.pos[1], instance.size[0], instance.size[1]), width=0.8)

    def _update_label(self, instance, value):
        instance.text_size = (instance.width, None)


class InfoPanel(ScrollView):
    """右侧/下侧信息面板（iOS 浅色卡片风格）。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.advisor = ColorAdvisor()
        self.do_scroll_x = False

        self.container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=(dp(4), dp(4), dp(4), dp(4)))
        self.container.bind(minimum_height=self.container.setter("height"))
        self.add_widget(self.container)

        self._show_placeholder()

    def _clear(self):
        self.container.clear_widgets()

    # ── iOS 卡片 ——
    def _card(self, title=None):
        """创建一张圆角白卡片，返回外层容器（可滚动高度自适配）。"""
        outer = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        card = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(12))
        if title:
            t = Label(
                text=title, size_hint_y=None, height=dp(22),
                font_size=dp(13), bold=True, color=THEME["label"],
                halign="left", valign="middle",
            )
            t.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            body.add_widget(t)
        card.add_widget(body)
        outer.add_widget(card)
        _rounded_card(card)
        # 高度跟随内容：body.minimum→body.height→card.height→outer.height
        body.bind(minimum_height=body.setter("height"))
        body.bind(minimum_height=lambda i, v: setattr(card, "height", v))
        card.bind(minimum_height=card.setter("height"))
        card.bind(minimum_height=lambda i, v: setattr(outer, "height", v))
        outer.bind(minimum_height=outer.setter("height"))
        return outer

    def _lbl(self, text, size=None, bold=False, color=None, font_size=None):
        lbl = Label(
            text=text,
            size_hint_y=None,
            height=size or dp(20),
            valign="top",
            halign="left",
            font_size=font_size or dp(12),
            color=color or THEME["label"],
            markup=True,
            bold=bold,
        )
        lbl.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val, None)),
            texture_size=lambda inst, val: setattr(inst, "height", max(val[1], dp(20))),
        )
        lbl.text_size = (lbl.width, None)
        return lbl

    def _add_swatch(self, color: Color, label_text: str):
        swatch = ColorSwatch(color, label_text, size_hint_y=None, height=dp(36))
        self.container.add_widget(swatch)
        return swatch

    def _show_placeholder(self):
        self._clear()
        c = self._card("调色助手")
        body = c.children[0]
        body.add_widget(self._lbl("等待取色...", font_size=dp(15), color=THEME["label_2"]))
        body.add_widget(self._lbl(""))
        body.add_widget(self._lbl(
            "1. 点击摄像头画面任意位置取色\n"
            "2. 或点击「中心取色」/「提取主色」\n"
            "3. 系统将分析颜色并给出调色配方",
            color=THEME["label_2"], font_size=dp(12),
        ))
        self.container.add_widget(c)

    def _show_permission_denied(self):
        self._clear()
        c = self._card("提示")
        body = c.children[0]
        body.add_widget(self._lbl("[color=FF3B30]摄像头权限被拒绝[/color]", font_size=dp(15)))
        body.add_widget(self._lbl(""))
        body.add_widget(self._lbl(
            "请在系统设置中授予摄像头权限，然后重新打开应用。",
            color=THEME["label_2"], font_size=dp(12),
        ))
        self.container.add_widget(c)

    def show_crash_path(self, path):
        self._clear()
        c = self._card("崩溃日志位置")
        body = c.children[0]
        body.add_widget(self._lbl("应用若异常闪退，日志会自动写入下面这个文件。", color=THEME["label_2"], font_size=dp(12)))
        body.add_widget(self._lbl(f"[b][color=007AFF]{path}[/color][/b]", font_size=dp(11)))
        self.container.add_widget(c)

    def show_analysis(self, color: Color):
        self._clear()

        analysis = self.advisor.analyze(color)

        # —— 采集颜色卡片 ——
        head = self._card()
        body = head.children[0]
        body.add_widget(self._lbl(f"[b]{analysis.hex_code}[/b]  「{analysis.name}」", font_size=dp(14)))
        self.container.add_widget(head)
        self._add_swatch(color, f"{analysis.hex_code}  「{analysis.name}」")

        # —— Lab LCh 卡片（参考图 1）——
        lch = self._card("Lab LCh")
        lbody = lch.children[0]
        L, a, b = color.lab
        C = math.hypot(a, b)
        h = math.degrees(math.atan2(b, a)) % 360.0

        # 三个彩色徽标
        badge_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(34))
        for txt, col in ((f"L {L:.1f}", THEME["label"]),
                         (f"a {a:+.1f}", THEME["success"]),
                         (f"b {b:+.1f}", THEME["warning"])):
            bx = BoxLayout(size_hint_x=None, width=dp(104), size_hint_y=None, height=dp(30))
            dark = (0.30, 0.30, 0.32, 1) if col is THEME["label"] else col
            with bx.canvas.before:
                GraphicsColor(dark[0], dark[1], dark[2], 1)
                _r = RoundedRectangle(pos=bx.pos, size=bx.size, radius=[dp(6)])
            bx.bind(pos=lambda i, v, rect=_r: setattr(rect, "pos", i.pos),
                    size=lambda i, v, rect=_r: setattr(rect, "size", i.size))
            bl = Label(
                text=txt, font_size=dp(15), bold=True, color=(1, 1, 1, 1),
                halign="center", valign="middle",
            )
            bl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            bx.add_widget(bl)
            badge_row.add_widget(bx)
        badge_row.add_widget(Widget())
        lbody.add_widget(badge_row)

        # C* 与 h° 大字
        metric = BoxLayout(orientation="horizontal", spacing=dp(16), size_hint_y=None, height=dp(52))
        for (val, _sub) in ((f"C* {C:.1f}", "饱和度"), (f"h° {h:.1f}", "色相角")):
            bx = BoxLayout(orientation="vertical")
            bl = Label(text=val, font_size=dp(20), color=THEME["primary"], bold=True, halign="left")
            bl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            bx.add_widget(bl)
            bx.add_widget(self._lbl(_sub, font_size=dp(10), color=THEME["label_2"]))
            metric.add_widget(bx)
        metric.add_widget(Widget())
        lbody.add_widget(metric)

        # 三条双向仪表条：L 黑白 / a 红绿 / b 黄蓝
        def _lab_meter(title, lo, hi, value, tint):
            row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(22))
            lab = Label(
                text=title, size_hint=(None, 1), width=dp(86),
                font_size=dp(11), color=THEME["label_2"], halign="right", valign="middle",
            )
            lab.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            bar = MeterBar(lo, hi, size_hint=(1, 1))
            bar.set(value, tint)
            row.add_widget(lab)
            row.add_widget(bar)
            lbody.add_widget(row)

        _lab_meter("明度 L", 0, 100, L, THEME["label"])
        _lab_meter("红绿 a", -128, 128, a, THEME["success"])
        _lab_meter("黄蓝 b", -128, 128, b, THEME["warning"])

        # 极坐标色相图
        chart_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(170))
        self._polar = PolarHueChart(size_hint=(1, 1))
        self._polar.set_color(color)
        chart_row.add_widget(self._polar)
        side = BoxLayout(orientation="vertical", size_hint=(None, 1), width=dp(66), spacing=dp(6))
        for txt, col in ((f"C* {C:.1f}", (0.8, 0.1, 0.3, 1)), (f"h° {h:.1f}", THEME["primary"])):
            sl = Label(
                text=txt, size_hint_y=None, height=dp(22),
                font_size=dp(15), bold=True, color=col, halign="center", valign="middle",
            )
            sl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            side.add_widget(sl)
        side.add_widget(Widget())
        chart_row.add_widget(side)
        lbody.add_widget(chart_row)

        rgb_line = self._lbl(
            f"RGB {color.rgb[0]} {color.rgb[1]} {color.rgb[2]}   HEX {color.hex}",
            font_size=dp(11), color=THEME["label_2"],
        )
        lbody.add_widget(rgb_line)
        self.container.add_widget(lch)

        # —— 商用色卡匹配 ——
        if analysis.paint_matches:
            pc = self._card("商用色卡匹配")
            pbody = pc.children[0]
            for m in analysis.paint_matches[:4]:
                pbody.add_widget(self._lbl(f"● {m.display}   ΔE={m.delta_e:.1f}", font_size=dp(12)))
            self.container.add_widget(pc)

        # —— 色彩分析 ——
        ma = self._card("色彩分析")
        mbody = ma.children[0]
        mbody.add_widget(self._lbl(f"识别：{analysis.name}  |  {analysis.temperature}  |  {analysis.brightness}  |  {analysis.saturation_level}", font_size=dp(12)))
        mbody.add_widget(self._lbl(f"感受：{analysis.mood}", font_size=dp(12), color=THEME["label_2"]))
        self.container.add_widget(ma)

        # —— 参考颜色配方（参考图 1：色点 + 比例条 + 数值）——
        rc = self._card("参考颜色配方")
        rbody = rc.children[0]
        recipes = self.advisor.suggest_recipe(color, top_n=1)
        if recipes:
            rec = recipes[0]
            rec_note = self._lbl(f"方案 ΔE={rec.delta_e:.1f}", size=dp(16), font_size=dp(11), color=THEME["label_2"])
            rbody.add_widget(rec_note)
            pname_color = {}
            for p in getattr(self.advisor.recipe_finder, "pigments", []) or []:
                pname_color[p.name] = p.color
            for name, _, ratio in rec.components:
                row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(30))
                sw = SwatchWidget()
                sw.size_hint = (None, 1)
                sw.width = dp(22)
                col = pname_color.get(name)
                sw.set_color(col if col else None)
                row.add_widget(sw)
                nm = Label(
                    text=name, size_hint=(None, 1), width=dp(56),
                    font_size=dp(12), color=THEME["label"], bold=True,
                    halign="left", valign="middle",
                )
                nm.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
                row.add_widget(nm)
                bar = RatioBar(size_hint=(1, 1))
                bar.set_ratio(ratio, col if col else None)
                row.add_widget(bar)
                vl = Label(
                    text=f"{ratio:.1f}", size_hint=(None, 1), width=dp(40),
                    font_size=dp(12), color=THEME["label"], bold=True,
                    halign="center", valign="middle",
                )
                row.add_widget(vl)
                rbody.add_widget(row)
            for i, recipe in enumerate(recipes[1:], 2):
                rbody.add_widget(self._lbl(f"备选方案 {i}  ΔE={recipe.delta_e:.1f}", size=dp(18), font_size=dp(11), color=THEME["label_2"]))
                parts = "  ".join(f"{n} {r:.0f}%" for n, _, r in recipe.components[:4])
                rbody.add_widget(self._lbl(parts, size=dp(18), font_size=dp(11), color=THEME["label"]))
        else:
            rbody.add_widget(self._lbl("暂无配方", size=dp(20), font_size=dp(12), color=THEME["label_2"]))
        self.container.add_widget(rc)

        # —— 和谐配色 ——
        hc = self._card("和谐配色")
        hbody = hc.children[0]
        harmony = self.advisor.suggest_harmony(color)
        for scheme, colors in harmony.items():
            txts = "  ".join(c.hex for c in colors)
            hbody.add_widget(self._lbl(f"{scheme}: {txts}", font_size=dp(11), color=THEME["label_2"]))
        self.container.add_widget(hc)

        self.container.height = self.container.minimum_height
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 1), 0.15)

    def show_report(self, color: Color):
        self._clear()
        rc = self._card("完整调色报告")
        rbody = rc.children[0]
        report = self.advisor.generate_full_report(color)
        rbody.add_widget(self._lbl(report, font_size=dp(11), color=THEME["label"]))
        self.container.add_widget(rc)
        self.container.height = self.container.minimum_height
        # 内容高度异步更新后滚回顶部，避免首行被裁
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 1), 0.15)


# ──────────────────────────────────────────────
# AI 辅助调色横屏界面
# ──────────────────────────────────────────────

class FocusBox(Widget):
    """相机对焦框：点击处显示黄色角框 + 中心点，缩放动画后淡出。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (0, 0)
        self.opacity = 0
        self.bind(opacity=self._redraw, pos=self._redraw, size=self._redraw)

    def show_at(self, x, y):
        self.center = (x, y)
        self.size = (120, 120)
        final = 72
        target_pos = (x - final / 2.0, y - final / 2.0)
        self.opacity = 1
        Animation.cancel_all(self)
        anim = Animation(size=(final, final), pos=target_pos, d=0.18, t="out_quad")
        anim += Animation(opacity=0, d=1.2)
        anim.start(self)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        o = self.opacity
        if o <= 0.02:
            return
        L, w = dp(16), dp(2)
        x, y, W, H = self.x, self.y, self.width, self.height
        with self.canvas:
            GraphicsColor(1, 0.85, 0.2, o)
            Line(points=[x, y + H, x, y + H - L], width=w)
            Line(points=[x, y + H, x + L, y + H], width=w)
            Line(points=[x + W, y + H, x + W - L, y + H], width=w)
            Line(points=[x + W, y + H, x + W, y + H - L], width=w)
            Line(points=[x, y, x + L, y], width=w)
            Line(points=[x, y, x, y + L], width=w)
            Line(points=[x + W, y, x + W - L, y], width=w)
            Line(points=[x + W, y, x + W, y + L], width=w)
            Line(circle=(self.center_x, self.center_y, dp(3)), width=w)


class SwatchWidget(Widget):
    """纯色色块（pos/size 变化自动重绘）。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._col = None
        self.bind(pos=self._redraw, size=self._redraw)

    def set_color(self, color):
        self._col = color
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        col = self._col
        if col is None:
            return
        r, g, b = col.rgb_normalized
        with self.canvas:
            GraphicsColor(r, g, b, 1)
            Rectangle(pos=self.pos, size=self.size)
            GraphicsColor(0, 0, 0, 0.4)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)


class ColorBlock(BoxLayout):
    """标题 + 色块 + hex/名称 组合块（iOS 浅色）。"""

    def __init__(self, title, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(2), **kwargs)
        self.lbl_title = Label(
            text=title, size_hint=(1, None), height=dp(15),
            font_size=dp(11), color=THEME["label_2"],
            halign="left", valign="middle",
        )
        self.lbl_title.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.swatch = SwatchWidget()
        self.swatch.size_hint = (1, None)
        self.swatch.height = dp(38)
        self.lbl_hex = Label(
            text="--", size_hint=(1, None), height=dp(15),
            font_size=dp(11), color=THEME["label"],
            halign="left", valign="middle",
        )
        self.lbl_hex.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.add_widget(self.lbl_title)
        self.add_widget(self.swatch)
        self.add_widget(self.lbl_hex)

    def set_color(self, color, name=""):
        if color is None:
            self.swatch.set_color(None)
            self.lbl_hex.text = "--"
            return
        self.swatch.set_color(color)
        self.lbl_hex.text = color.hex + (f"  {name}" if name else "")


class RatioBar(Widget):
    """比例条：浅灰底 + 彩色按比例填充。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ratio = 0.0
        self._rgb = (0.6, 0.6, 0.66)
        self.bind(pos=self._redraw, size=self._redraw)

    def set_ratio(self, ratio, color):
        self._ratio = max(0.0, min(1.0, ratio))
        if color is not None:
            self._rgb = color.rgb_normalized
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        if self.width <= 1 or self.height <= 1:
            return
        with self.canvas:
            GraphicsColor(0.88, 0.88, 0.9, 1)
            Rectangle(pos=self.pos, size=self.size)
            r, g, b = self._rgb
            GraphicsColor(r, g, b, 1)
            Rectangle(pos=self.pos, size=(self.width * self._ratio, self.height))
            GraphicsColor(0, 0, 0, 0.5)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)


class DragRing(Widget):
    """可拖动的取样圈：圆环 + 中心点 + 底部小标签。

    - 在 cam_area（与 CameraView 同坐标）内拖动
    - 拖动时调用 on_drag，把显示坐标交给上层采样
    """

    def __init__(self, label, ring_color, **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self._ring = ring_color
        self._radius = dp(26)
        self._dragging = False
        self.on_drag = None
        self.size = (dp(160), dp(160))
        self.bind(pos=self._redraw, size=self._redraw)

        from kivy.uix.label import Label as KLabel
        self._label = KLabel(
            text=label, font_size=dp(10), bold=True,
            color=(1, 1, 1, 1), size_hint=(None, None), size=(dp(56), dp(16)),
        )
        with self._label.canvas.before:
            GraphicsColor(0, 0, 0, 0.55)
            self._label_bg = Rectangle(pos=self._label.pos, size=self._label.size)
        self._label.bind(pos=lambda i, v: setattr(self._label_bg, "pos", i.pos),
                         size=lambda i, v: setattr(self._label_bg, "size", i.size))
        self._label_parent = None

    def set_radius(self, r):
        self._radius = max(dp(14), r)
        self._redraw()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._dragging = True
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if self._dragging and touch.grab_current is self:
            self.center = touch.pos
            self._redraw()
            if self.on_drag:
                self.on_drag()
            return True
        return False

    def on_touch_up(self, touch):
        if self._dragging and touch.grab_current is self:
            self._dragging = False
            touch.ungrab(self)
            return True
        return False

    def _redraw(self, *args):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        r = self._radius
        with self.canvas:
            # 半透明填充 + 圆环
            GraphicsColor(self._ring[0], self._ring[1], self._ring[2], 0.16)
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
            GraphicsColor(self._ring[0], self._ring[1], self._ring[2], 0.95)
            Line(circle=(cx, cy, r), width=dp(3))
            GraphicsColor(1, 1, 1, 0.9)
            Line(circle=(cx, cy, r + 3), width=dp(1))
            # 中心点
            GraphicsColor(self._ring[0], self._ring[1], self._ring[2], 1)
            Ellipse(pos=(cx - 4, cy - 4), size=(8, 8))
        # 标签放在圆下方
        if self._label is not None and self._label.parent is self:
            self._label.center_x = cx
            self._label.y = cy - r - dp(20)


class AiMixScreen(BoxLayout):
    """AI 辅助调色模式 —— 双点取样·实时对比（iOS 浅色）。

    竖屏上下分屏 / 横屏左右分屏。
    - 两个可拖动的取样圈：样板区 / 调整区
    - 实时对比两点的颜色差 ΔE
    - 差量配方：实时显示要把当前色调成样板色，还需添加哪些颜料
    - 取样大小可调；所有颜色先过白卡校色
    """

    def __init__(self, camera_view, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = 0
        self.camera_view = camera_view
        self.advisor = ColorAdvisor()
        self.wb = WhiteBalance()

        self._sample_kind = None   # 当前拖动的是哪个圈: "sample"/"current"
        self._target = None        # 样板色（校正后 Color）
        self._current = None       # 当前色（校正后 Color）
        self._corrected = None     # 矫正色（AI 理想配方色）
        self._mode = "sample"      # 预览模式: "correct"/"sample"/"current"
        self._wet = False          # 潮物检测
        self._composition = []     # [(pigment, ratio), ...] 渐增差量配方
        self._sampling_interval = None
        self._advice_counter = 0
        self._radius = 12          # 取样半径
        self._size_pct = 50
        self.on_close = None

        self._build_ui()

    def _build_ui(self):
        D = DARK
        # ── 顶栏（深色，参考图 2）──
        bar = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(6), padding=(dp(6), dp(0), dp(6), dp(0)))
        with bar.canvas.before:
            GraphicsColor(D["title_bg"][0], D["title_bg"][1], D["title_bg"][2], 1)
            self._bar_bg = Rectangle(pos=bar.pos, size=bar.size)
        bar.bind(pos=self._resize_bar, size=self._resize_bar)

        self.btn_back = Button(
            text="‹ 返回", size_hint=(None, 1), width=dp(62),
            font_size=dp(14), color=D["text"], background_color=(0, 0, 0, 0),
            background_normal="",
        )
        self.btn_back.bind(on_release=lambda b: self.request_close())
        bar.add_widget(self.btn_back)

        self.bar_title = Label(
            text="AI 辅助调色", size_hint=(1, 1),
            font_size=dp(16), color=D["text"], bold=True,
        )
        bar.add_widget(self.bar_title)

        self.btn_cal = Button(
            text="白卡校色", size_hint=(None, 1), width=dp(82),
            font_size=dp(12), color=(0.04, 0.07, 0.12, 1), background_color=D["accent"],
            background_normal="",
        )
        self.btn_cal.bind(on_release=lambda b: self._do_calibrate())
        bar.add_widget(self.btn_cal)

        self.bar_status = Label(
            text="", size_hint=(None, 1), width=dp(54),
            font_size=dp(11), color=D["accent"],
        )
        bar.add_widget(self.bar_status)
        self.add_widget(bar)

        # ── 主体：竖屏上下 / 横屏左右 ──
        landscape = Window.width > Window.height
        body = BoxLayout(orientation="horizontal" if landscape else "vertical", spacing=dp(6), padding=dp(6))
        body.size_hint = (1, 1)
        self.add_widget(body)

        # 摄像头区（CameraView 由主界面 reparent 进来，取样圈叠加其上）
        self.cam_area = FloatLayout()
        self.cam_area.size_hint = (0.62, 1) if landscape else (1, 0.5)
        body.add_widget(self.cam_area)

        # 信息面板（可滚动，深色卡片）
        scroll = ScrollView()
        scroll.size_hint = (0.38, 1) if landscape else (1, 0.5)
        scroll.bar_width = dp(2)
        body.add_widget(scroll)

        self.info_box = BoxLayout(
            orientation="vertical", size_hint_y=None,
            spacing=dp(6), padding=(dp(2), dp(2), dp(2), dp(2)),
        )
        self.info_box.bind(minimum_height=self.info_box.setter("height"))
        scroll.add_widget(self.info_box)

        # —— 色差 + 实时预览 卡片（参考图 2）——
        pc = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        pc.bind(minimum_height=pc.setter("height"))
        _dark_card(pc)
        self._pc = pc
        self.info_box.add_widget(pc)

        # 色差行
        de_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(40))
        lbl_de = Label(
            text="色差", size_hint=(None, 1), width=dp(52),
            font_size=dp(13), color=D["sub"], halign="left", valign="middle",
        )
        lbl_de.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        de_row.add_widget(lbl_de)
        self.delta_lbl = Label(
            text="ΔE = --", size_hint=(1, 1),
            font_size=dp(24), color=D["gold"], bold=True,
            halign="center", valign="middle",
        )
        self.delta_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        de_row.add_widget(self.delta_lbl)
        pc.add_widget(de_row)
        self._de_hint = Label(
            text="", size_hint_y=None, height=dp(14),
            font_size=dp(10), color=D["sub"], halign="left", valign="middle",
        )
        self._de_hint.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(self._de_hint)

        # 实时预览效果
        pv_title = Label(
            text="实时预览效果", size_hint_y=None, height=dp(16),
            font_size=dp(12), color=D["sub"], halign="left", valign="middle",
        )
        pv_title.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(pv_title)
        self.preview_block = SwatchWidget()
        self.preview_block.size_hint = (1, None)
        self.preview_block.height = dp(70)
        pc.add_widget(self.preview_block)
        self.preview_hex = Label(
            text="--", size_hint_y=None, height=dp(15),
            font_size=dp(11), color=D["text"], halign="left", valign="middle",
        )
        self.preview_hex.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pc.add_widget(self.preview_hex)

        # 三模式切换（矫正色/样板色/当前色）
        mode_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(32))
        self._mode_btns = {}
        for key, label in (("correct", "矫正色"), ("sample", "样板色"), ("current", "当前色")):
            b = Button(
                text=label, size_hint=(1, 1), font_size=dp(11),
                background_normal="", color=D["text"],
            )
            b.bind(on_release=lambda b, k=key: self._set_mode(k))
            self._mode_btns[key] = b
            mode_row.add_widget(b)
        pc.add_widget(mode_row)
        self._paint_mode_buttons()

        # —— 干/潮检测 ——
        det_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(32))
        self.btn_dry = Button(
            text="干物检测", size_hint=(1, 1), font_size=dp(12), background_normal="",
        )
        self.btn_dry.bind(on_release=lambda b: self._set_wet(False))
        self.btn_wet = Button(
            text="潮物检测", size_hint=(1, 1), font_size=dp(12), background_normal="",
        )
        self.btn_wet.bind(on_release=lambda b: self._set_wet(True))
        det_row.add_widget(self.btn_dry)
        det_row.add_widget(self.btn_wet)
        self.info_box.add_widget(det_row)
        self._paint_detect_buttons()

        # —— 调节大小 ——
        size_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
        self.size_lbl = Label(
            text="调节大小", size_hint=(None, 1), width=dp(66),
            font_size=dp(12), color=D["text"], halign="left", valign="middle",
        )
        self.size_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        slider = Slider(min=4, max=30, value=self._radius, size_hint=(1, 1))
        slider.value_track = True
        slider.bind(value=self._on_size_change)
        self.size_slider = slider
        self._size_pct_lbl = Label(
            text=f"{self._size_pct}%", size_hint=(None, 1), width=dp(44),
            font_size=dp(13), color=D["accent"], bold=True, halign="center", valign="middle",
        )
        size_row.add_widget(self.size_lbl)
        size_row.add_widget(slider)
        size_row.add_widget(self._size_pct_lbl)
        self.info_box.add_widget(size_row)

        # —— 色彩成分分析 ——
        comp_title = Label(
            text="色彩成分分析", size_hint_y=None, height=dp(18),
            font_size=dp(13), color=D["text"], bold=True,
            halign="left", valign="middle",
        )
        comp_title.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.info_box.add_widget(comp_title)

        self.comp_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.comp_box.bind(minimum_height=self.comp_box.setter("height"))
        self.info_box.add_widget(self.comp_box)

        # —— 提示 ——
        tip = Label(
            text="拖动两个圆圈取样：样板区=想要的颜色，调整区=当前颜料色。开启潮物检测会将湿料自动校正为干态后再算配比建议",
            size_hint_y=None, height=dp(34), font_size=dp(10),
            color=D["sub"], halign="left", valign="middle",
        )
        tip.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        self.info_box.add_widget(tip)
        self.info_box.height = self.info_box.minimum_height

    def _resize_bar(self, inst, val):
        self._bar_bg.pos = inst.pos
        self._bar_bg.size = inst.size

    def open(self, on_close=None):
        self.on_close = on_close or (lambda: None)
        # 两个取样圈初始放在画面左右
        self.sample_ring = DragRing("样板区", DARK["red"])
        self.current_ring = DragRing("调整区", (1.0, 1.0, 1.0, 1))
        for ring in (self.sample_ring, self.current_ring):
            ring.on_drag = self._ring_moved
        self.cam_area.add_widget(self.sample_ring)
        self.cam_area.add_widget(self.current_ring)
        Clock.schedule_once(self._place_rings, 0)
        self._sampling_interval = Clock.schedule_interval(self._poll, 1.0 / 15)

    def _place_rings(self):
        if self.cam_area.width <= 1 or self.cam_area.height <= 1:
            return
        self.sample_ring.center = (self.cam_area.width * 0.3, self.cam_area.height * 0.5)
        self.current_ring.center = (self.cam_area.width * 0.7, self.cam_area.height * 0.5)

    def close(self):
        if self._sampling_interval is not None:
            Clock.unschedule(self._sampling_interval)
            self._sampling_interval = None
        for name in ("sample_ring", "current_ring"):
            ring = getattr(self, name, None)
            if ring is not None and ring.parent is not None:
                ring.parent.remove_widget(ring)

    def request_close(self):
        self.close()
        cb = getattr(self, "on_close", None)
        if cb:
            cb()

    def shutdown(self):
        self.close()

    # ── 取样 ──

    def _ring_moved(self):
        self._poll(None)

    def _surface_adjust(self, color):
        """湿态→干态近似校正：只对调整区（正在混合的湿料）生效。

        湿漆比干漆更深、更饱和；开启潮物检测时，把湿读色轻微提亮、
        去饱和，得到接近干态的等效色，再与干态样板比较。
        """
        if not self._wet or color is None:
            return color
        r, g, b = color.rgb_normalized
        # 轻微提高明度（向白靠拢）并压缩饱和度，模拟干燥后的变化
        lift = 0.06
        r = r + (1.0 - r) * lift
        g = g + (1.0 - g) * lift
        b = b + (1.0 - b) * lift
        return Color(int(max(0, min(255, r * 255))),
                     int(max(0, min(255, g * 255))),
                     int(max(0, min(255, b * 255))))

    def _sample_color(self, ring, is_current=False):
        """采样某个取样圈中心点的原始颜色，返回校正后 Color。"""
        cv = self.camera_view
        if cv is None or ring is None:
            return None
        raw = cv.sample_at(ring.center_x, ring.center_y, radius=self._radius)
        if raw is None:
            return None
        corrected = self.wb.apply(raw)
        if is_current:
            corrected = self._surface_adjust(corrected)
        return corrected

    # ── 校色 ──

    def _do_calibrate(self):
        if self.camera_view is None:
            return
        raw = self.camera_view.sample_at(self.camera_view.center_x, self.camera_view.center_y, radius=15)
        if raw is None:
            self._set_status("无画面")
            return
        try:
            self.wb.calibrate(raw)
            self._set_status("已校色")
            self._poll(None)
        except Exception:
            self._set_status("校色失败")

    def _set_status(self, text):
        self.bar_status.text = text

    def _on_size_change(self, inst, value):
        self._radius = int(value)
        self._size_pct = int((self._radius - 4) * 100 // 26)
        if hasattr(self, "_size_pct_lbl"):
            self._size_pct_lbl.text = f"{max(0, min(100, self._size_pct))}%"
        for ring in (getattr(self, "sample_ring", None), getattr(self, "current_ring", None)):
            if ring is not None:
                ring.set_radius(dp(26) * self._radius / 12)

    # ── 实时轮询（每帧刷新两点颜色、ΔE 与配方）──

    def _poll(self, dt):
        if self.camera_view is None or self.camera_view._frame is None:
            return
        if not hasattr(self, "sample_ring") or not hasattr(self, "current_ring"):
            return
        sample = self._sample_color(self.sample_ring, is_current=False)
        current = self._sample_color(self.current_ring, is_current=True)
        if sample is None or current is None:
            return
        self._target = sample
        self._current = current
        de = sample.distance(current)
        self.delta_lbl.text = f"ΔE = {de:.1f}"
        if de <= 2:
            hint = "完美匹配 ✓"
        elif de <= 6:
            hint = "已接近，可微调"
        else:
            hint = "差异较大，按下方配方添加色料"
        self._de_hint.text = "提示：" + hint
        # 差量配方每 5 帧重算一次；拖动时立即重算
        self._advice_counter += 1
        if dt is None or self._advice_counter % 5 == 0:
            self._greedy_recipe(current, sample)
            self._render_composition()
            self._update_preview()

    # ── 预览模式（矫正色/样板色/当前色）──

    def _set_mode(self, key):
        self._mode = key
        self._paint_mode_buttons()
        self._update_preview()

    def _paint_mode_buttons(self):
        for key, b in self._mode_btns.items():
            if key == self._mode:
                b.background_color = DARK["accent"]
                b.color = (0.04, 0.07, 0.12, 1)
            else:
                b.background_color = DARK["sel_bg"]
                b.color = DARK["text"]

    def _preview_color(self):
        if self._mode == "current":
            return self._current
        if self._mode == "correct":
            return self._corrected or self._target
        return self._target

    def _update_preview(self):
        c = self._preview_color()
        if c is None:
            self.preview_block.set_color(None)
            self.preview_hex.text = "--"
            return
        self.preview_block.set_color(c)
        self.preview_hex.text = c.hex + "  " + nearest_named_color(c)

    # ── 干/潮物检测 ──

    def _set_wet(self, wet):
        self._wet = wet
        self._paint_detect_buttons()
        self.bar_status.text = "潮物模式" if wet else ""
        # 切换后立即重算 ΔE 与配比建议
        self._poll(None)

    def _paint_detect_buttons(self):
        if self._wet:
            self.btn_dry.background_color = DARK["sel_bg"]
            self.btn_dry.color = DARK["text"]
            self.btn_wet.background_color = DARK["orange"]
            self.btn_wet.color = (1, 1, 1, 1)
        else:
            self.btn_dry.background_color = DARK["orange"]
            self.btn_dry.color = (1, 1, 1, 1)
            self.btn_wet.background_color = DARK["sel_bg"]
            self.btn_wet.color = DARK["text"]

    # ── 渐增差量配方（资源贪心，最多 3 步）──

    def _greedy_recipe(self, current, target, max_steps=3):
        steps = []
        cur = current
        for _ in range(max_steps):
            if cur.distance(target) <= 3.0:
                break
            sug = self.advisor.suggest_next_pigment(cur, target)
            if sug is None:
                break
            p = sug["pigment"]
            ratio = sug["ratio"]
            cur = ColorMixer.mix_subtractive([cur, p.color], [1 - ratio, ratio])
            steps.append((p, ratio, sug["delta_e"]))
        self._corrected = cur
        self._composition = steps
        return steps

    # ── 色彩成分分析渲染（参考图 2：色点 + 进度条 + 增减% ）──

    def _render_composition(self):
        D = DARK
        self.comp_box.clear_widgets()
        if self._composition:
            for p, ratio, de in self._composition:
                row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(26))
                sw = SwatchWidget()
                sw.size_hint = (None, 1)
                sw.width = dp(18)
                sw.set_color(p.color)
                row.add_widget(sw)
                nm = Label(
                    text=p.name, size_hint=(None, 1), width=dp(46),
                    font_size=dp(11), color=D["text"], bold=True,
                    halign="left", valign="middle",
                )
                nm.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
                row.add_widget(nm)
                bar = RatioBar(size_hint=(1, 1))
                bar.set_ratio(ratio, p.color)
                row.add_widget(bar)
                val = Label(
                    text=f"+{ratio * 100:.1f}%", size_hint=(None, 1), width=dp(52),
                    font_size=dp(12), color=D["gold"], bold=True,
                    halign="center", valign="middle",
                )
                row.add_widget(val)
                self.comp_box.add_widget(row)
        else:
            l = Label(
                text="无需添加，已接近样板色", size_hint_y=None, height=dp(22),
                font_size=dp(11), color=D["accent"], halign="left", valign="middle",
            )
            l.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
            self.comp_box.add_widget(l)
        self.comp_box.height = self.comp_box.minimum_height
        self.info_box.height = self.info_box.minimum_height


# ──────────────────────────────────────────────
# 主界面
# ──────────────────────────────────────────────

class ColorAssistantApp(App):
    """AI 调色助手主应用。"""

    def build(self):
        self.title = "AI 调色助手"
        Window.clearcolor = THEME["bg"]

        # 根容器：FloatLayout，用于承载主界面 + AI调色全屏覆盖层
        self.root = FloatLayout()
        self.main_box = BoxLayout(orientation="vertical", spacing=0)
        self.main_box.size_hint = (1, 1)
        self.root.add_widget(self.main_box)

        # 顶部标题栏（iOS 导航栏样式）
        title_bar = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(8), padding=(dp(6), dp(0), dp(6), dp(0)))
        with title_bar.canvas.before:
            GraphicsColor(*THEME["card"])
            self._title_bg = Rectangle(pos=title_bar.pos, size=title_bar.size)
        title_bar.bind(pos=self._update_title_bg, size=self._update_title_bg)

        title_label = Label(
            text="AI 调色助手",
            size_hint=(1, 1),
            font_size=dp(17),
            color=THEME["label"],
            bold=True,
        )
        title_bar.add_widget(title_label)

        btn_report = Button(
            text="完整报告",
            size_hint=(None, 1),
            width=dp(84),
            font_size=dp(13),
            background_color=THEME["primary"],
            background_normal="",
            color=(1, 1, 1, 1),
        )
        btn_report.bind(on_release=lambda btn: self._on_report())
        title_bar.add_widget(btn_report)

        self.main_box.add_widget(title_bar)

        # 主体区域（竖屏：摄像头 55% / 信息 45%）
        if Window.width > Window.height and Window.width > 600:
            body = BoxLayout(orientation="horizontal", spacing=dp(8), padding=dp(8))
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(0.55, 1))
            self.info_panel = InfoPanel(size_hint=(0.45, 1))
        else:
            body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(1, 0.55))
            self.info_panel = InfoPanel(size_hint=(1, 0.45))

        body.add_widget(self.camera_view)
        body.add_widget(self.info_panel)
        self._body = body
        self.main_box.add_widget(body)
        # 布局完成后再把准星放到画面中心（构造时尺寸还是默认值）
        Clock.schedule_once(lambda dt: self.camera_view._center_crosshair(), 0.5)

        # 底部工具栏（iOS 浅色卡片风格）
        toolbar = BoxLayout(size_hint=(1, None), height=dp(56), spacing=dp(8), padding=(dp(10), dp(8), dp(10), dp(8)))
        with toolbar.canvas.before:
            GraphicsColor(*THEME["card"])
            self._toolbar_bg = Rectangle(pos=toolbar.pos, size=toolbar.size)
        toolbar.bind(pos=self._update_toolbar_bg, size=self._update_toolbar_bg)

        def _btn(text, color, callback):
            b = Button(
                text=text, size_hint=(1, 1), font_size=dp(13),
                background_color=color, background_normal="", color=(1, 1, 1, 1),
            )
            b.bind(on_release=callback)
            return b

        toolbar.add_widget(_btn("中心取色", THEME["primary"], lambda b: self._on_center_pick()))
        toolbar.add_widget(_btn("提取主色", THEME["warning"], lambda b: self._on_dominant_pick()))
        toolbar.add_widget(_btn("AI辅助调色", (0.42, 0.42, 0.9, 1), lambda b: self._on_open_mix()))

        btn_rotate = Button(
            text="旋转画面", size_hint=(None, 1), width=dp(80), font_size=dp(12),
            background_color=(0.55, 0.55, 0.6, 1), background_normal="", color=(1, 1, 1, 1),
        )
        btn_rotate.bind(on_release=lambda b: self._on_rotate())
        toolbar.add_widget(btn_rotate)

        btn_log = Button(
            text="日志", size_hint=(None, 1), width=dp(52), font_size=dp(12),
            background_color=THEME["label_2"], background_normal="", color=(1, 1, 1, 1),
        )
        btn_log.bind(on_release=lambda b: self._on_show_crash_path())
        toolbar.add_widget(btn_log)

        self.main_box.add_widget(toolbar)

        self._current_color = None
        self.mix_screen = None

        # 启动摄像头（Android 需先请求权限）
        Clock.schedule_once(self._init_camera, 1.0)

        return self.root

    def _init_camera(self, dt):
        """延迟启动摄像头，Android 上先请求权限。"""
        request_android_camera_permission(self._on_permission_result)

    def _on_permission_result(self, granted):
        if granted:
            self.camera_view.start_camera()
        else:
            self.info_panel._show_permission_denied()

    # ── 事件处理 ──

    def _on_color_picked(self, color: Color):
        self._current_color = color
        self.info_panel.show_analysis(color)

    def _on_center_pick(self):
        color = self.camera_view.pick_center()
        if color:
            self._on_color_picked(color)

    def _on_dominant_pick(self):
        frame = self.camera_view.get_frame()
        if frame is not None:
            color = extract_dominant_color(frame, k=3)
            self._on_color_picked(color)

    def _on_report(self):
        if self._current_color:
            self.info_panel.show_report(self._current_color)

    def _on_show_crash_path(self):
        """向用户展示崩溃日志写入位置。"""
        self.info_panel.show_crash_path(_crash_path)

    def _on_rotate(self):
        """画面顺时针旋转 90°（修正 Android 传感器方向）。"""
        self.camera_view.rotate_cw()

    # ── AI 辅助调色 ──

    def _on_open_mix(self):
        """打开 AI 辅助调色界面（竖屏上下分屏 / 横屏左右分屏）。"""
        if self.mix_screen is not None:
            return
        # 摄像头从主界面摘下，reparent 到 AI 界面画面区（复用同一摄像头）
        if self.camera_view.parent is not None:
            self.camera_view.parent.remove_widget(self.camera_view)
        self.camera_view.size_hint = (1, 1)

        self.mix_screen = AiMixScreen(camera_view=self.camera_view)
        # 全屏覆盖（FloatLayout 顶层）
        self.mix_screen.size_hint = (1, 1)
        self.mix_screen.pos_hint = {"x": 0, "y": 0}
        self.root.add_widget(self.mix_screen)

        # 摄像头在下层，取样圈在 AiMixScreen.open() 里叠加到 cam_area
        self.mix_screen.cam_area.add_widget(self.camera_view)

        self.mix_screen.open(on_close=self._on_close_mix)

    def _on_close_mix(self):
        """关闭 AI 辅助调色界面，摄像头归还主界面。"""
        if self.mix_screen is None:
            return
        self.mix_screen.shutdown()
        # 摄像头移回主界面原位置（body 第一个子项），恢复主界面布局比例
        landscape = Window.width > Window.height and Window.width > 600
        self.camera_view.size_hint = (0.55, 1) if landscape else (1, 0.55)
        self.mix_screen.cam_area.remove_widget(self.camera_view)
        self._body.add_widget(self.camera_view, index=0)
        self.root.remove_widget(self.mix_screen)
        self.mix_screen = None

    # ── 背景 ──

    def _update_title_bg(self, instance, value):
        self._title_bg.pos = instance.pos
        self._title_bg.size = instance.size

    def _update_toolbar_bg(self, instance, value):
        self._toolbar_bg.pos = instance.pos
        self._toolbar_bg.size = instance.size

    # ── 生命周期 ──

    def on_pause(self):
        self.camera_view.stop_camera()
        if self.mix_screen is not None:
            self._on_close_mix()
        return True

    def on_resume(self):
        self.camera_view.start_camera()

    def on_stop(self):
        self.camera_view.stop_camera()
        if self.mix_screen is not None:
            self._on_close_mix()


if __name__ == "__main__":
    ColorAssistantApp().run()
