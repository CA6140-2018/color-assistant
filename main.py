"""
AI 调色助手 - 主程序

基于 Kivy 的摄像头取色与 AI 调色配方推荐应用。
桌面端使用 OpenCV 摄像头，Android 端使用 Kivy 原生 Camera。
可打包为 Android APK。

用法:
    python main.py
"""

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
from kivy.graphics import (
    Color as GraphicsColor,
    Rectangle,
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
            # 隐藏采集器：画面由 RotatedImage 按 _rotation 旋转渲染
            c.size_hint = (None, None)
            c.size = (0, 0)
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

    def on_touch_down(self, touch):
        if self._frame is None or not self.collide_point(*touch.pos):
            return False

        frame_h, frame_w = self._frame.shape[:2]
        if self.width <= 0 or self.height <= 0:
            return False

        # 显示区域归一化坐标（allow_stretch 满幅，无 letterbox）
        nu = (touch.x - self.x) / self.width
        nv = (touch.y - self.y) / self.height
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

        color = average_color_region(self._frame, (fx, fy), radius=10)

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
            color=(0.9, 0.9, 0.9, 1),
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
    """右侧/下侧信息面板。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.advisor = ColorAdvisor()

        self.container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(8))
        self.container.bind(minimum_height=self.container.setter("height"))
        self.add_widget(self.container)

        self._show_placeholder()

    def _clear(self):
        self.container.clear_widgets()

    def _add_label(self, text, size=None, bold=False, color=(0.9, 0.9, 0.9, 1), font_size=None):
        lbl = Label(
            text=text,
            size_hint_y=None,
            height=size or dp(20),
            valign="top",
            halign="left",
            font_size=font_size or dp(13),
            color=color,
            markup=True,
            bold=bold,
        )
        lbl.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val, None)),
            texture_size=lambda inst, val: setattr(inst, "height", max(val[1], dp(20))),
        )
        lbl.text_size = (lbl.width, None)
        self.container.add_widget(lbl)
        return lbl

    def _add_swatch(self, color: Color, label_text: str):
        swatch = ColorSwatch(color, label_text, size_hint_y=None, height=dp(36))
        self.container.add_widget(swatch)
        return swatch

    def _show_placeholder(self):
        self._clear()
        self._add_label("等待取色...", font_size=dp(15), color=(0.6, 0.6, 0.6, 1))
        self._add_label("", size=dp(8))
        self._add_label(
            "[color=a0a0a0]操作说明：\n"
            "1. 点击摄像头画面任意位置取色\n"
            "2. 或点击「中心取色」按钮\n"
            "3. 系统将分析颜色并给出调色配方[/color]",
            font_size=dp(12),
        )

    def _show_permission_denied(self):
        self._clear()
        self._add_label("[color=F44336]摄像头权限被拒绝[/color]", font_size=dp(15))
        self._add_label("", size=dp(8))
        self._add_label(
            "[color=a0a0a0]请在系统设置中授予摄像头权限，然后重新打开应用。[/color]",
            font_size=dp(12),
        )

    def show_crash_path(self, path):
        self._clear()
        self._add_label("[b][color=FFB300]崩溃日志位置[/color][/b]", font_size=dp(16))
        self._add_label("", size=dp(8))
        self._add_label(
            "[color=a0a0a0]应用若异常闪退，日志会自动写入下面这个文件。\n"
            "请用手机『文件管理』找到它，把内容发给我：[/color]",
            font_size=dp(12),
        )
        self._add_label("", size=dp(8))
        self._add_label(f"[color=4FC3F7][b]{path}[/b][/color]", font_size=dp(11))
        self._add_label("", size=dp(8))
        self._add_label(
            "[color=a0a0a0]文件可能位置：Download / sdcard 根目录 / 应用专属目录[/color]",
            font_size=dp(11),
        )

    def show_analysis(self, color: Color):
        self._clear()

        analysis = self.advisor.analyze(color)

        self._add_label("[b][color=4FC3F7]采集颜色[/color][/b]", font_size=dp(16))
        self._add_swatch(color, f"{analysis.hex_code}  「{analysis.name}」")

        if analysis.paint_matches:
            self._add_label("", size=dp(6))
            self._add_label("[b][color=FFD54F]商用色卡匹配[/color][/b]", font_size=dp(14))
            for m in analysis.paint_matches[:5]:
                self._add_swatch(m.color, f"{m.display}  ΔE={m.delta_e:.1f}")

        self._add_label("", size=dp(6))

        self._add_label("[b]色值数据[/b]", font_size=dp(14), color=(0.8, 0.8, 0.8, 1))
        self._add_label(f"RGB:  {color.rgb[0]}, {color.rgb[1]}, {color.rgb[2]}", font_size=dp(12))
        self._add_label(f"HSL:  H={analysis.hsl[0]:.1f}°  S={analysis.hsl[1]:.1f}%  L={analysis.hsl[2]:.1f}%", font_size=dp(12))
        self._add_label(f"HSV:  H={analysis.hsv[0]:.1f}°  S={analysis.hsv[1]:.1f}%  V={analysis.hsv[2]:.1f}%", font_size=dp(12))
        self._add_label(f"CMYK: C={analysis.cmyk[0]:.1f}  M={analysis.cmyk[1]:.1f}  Y={analysis.cmyk[2]:.1f}  K={analysis.cmyk[3]:.1f}", font_size=dp(12))

        self._add_label("", size=dp(6))

        self._add_label("[b]色彩分析[/b]", font_size=dp(14), color=(0.8, 0.8, 0.8, 1))
        self._add_label(f"色温: {analysis.temperature}", font_size=dp(12))
        self._add_label(f"明度: {analysis.brightness}", font_size=dp(12))
        self._add_label(f"饱和度: {analysis.saturation_level}", font_size=dp(12))
        self._add_label(f"色彩感受: {analysis.mood}", font_size=dp(12))

        self._add_label("", size=dp(6))

        self._add_label("[b][color=81C784]调色配方推荐[/color][/b]", font_size=dp(14))
        recipes = self.advisor.suggest_recipe(color, top_n=3)
        for i, recipe in enumerate(recipes, 1):
            self._add_label(
                f"[b]方案 {i}[/b]  {recipe.accuracy}  ΔE={recipe.delta_e:.2f}",
                font_size=dp(12),
                color=(0.85, 0.85, 0.85, 1),
            )
            self._add_swatch(recipe.result, f"混合 → {recipe.result.hex}")
            for name, _, ratio in recipe.components:
                desc = pigment_description(name)
                line = f"  {name} {ratio:.0f}%"
                if desc:
                    line += f" （{desc}）"
                self._add_label(line, font_size=dp(11), color=(0.7, 0.7, 0.7, 1))
            self._add_label("", size=dp(4))

        self._add_label("[b][color=CE93D8]和谐配色[/color][/b]", font_size=dp(14))
        harmony = self.advisor.suggest_harmony(color)
        for scheme, colors in harmony.items():
            swatch_text = "  ".join(f"{c.hex}" for c in colors)
            self._add_label(f"{scheme}: {swatch_text}", font_size=dp(11), color=(0.7, 0.7, 0.7, 1))

        self.container.height = self.container.minimum_height

    def show_report(self, color: Color):
        self._clear()
        self._add_label("[b][color=4FC3F7]完整调色报告[/color][/b]", font_size=dp(15))
        report = self.advisor.generate_full_report(color)
        self._add_label(report, font_size=dp(11), color=(0.85, 0.85, 0.85, 1))
        self.container.height = self.container.minimum_height


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
    """标题 + 色块 + hex/名称 组合块。"""

    def __init__(self, title, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(2), **kwargs)
        self.lbl_title = Label(
            text=title, size_hint=(1, None), height=dp(15),
            font_size=dp(11), color=(0.62, 0.62, 0.68, 1),
        )
        self.swatch = SwatchWidget()
        self.swatch.size_hint = (1, None)
        self.swatch.height = dp(38)
        self.lbl_hex = Label(
            text="--", size_hint=(1, None), height=dp(15),
            font_size=dp(11), color=(0.9, 0.9, 0.9, 1),
        )
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
    """比例条：深灰底 + 彩色按比例填充。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ratio = 0.0
        self._rgb = (0.35, 0.35, 0.38)
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
            GraphicsColor(0.22, 0.22, 0.25, 1)
            Rectangle(pos=self.pos, size=self.size)
            r, g, b = self._rgb
            GraphicsColor(r, g, b, 1)
            Rectangle(pos=self.pos, size=(self.width * self._ratio, self.height))
            GraphicsColor(0, 0, 0, 0.5)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)


class AiMixScreen(BoxLayout):
    """AI 辅助调色模式。

    竖屏：上下分屏（上半摄像头画面 / 下半信息面板）
    横屏：左右分屏（左摄像头画面 / 右信息面板）

    - 点击画面任意位置：对焦框动画，锁定该处颜色为目标色
    - 画面中心准星：实时采样"当前色浆"
    - 信息面板：目标/当前色块、ΔE 色差、下一步要加的颜料（色块+比例条+预计混合色）
    - 所有颜色先过白卡校色
    """

    def __init__(self, camera_view, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = 0
        self.camera_view = camera_view
        self.advisor = ColorAdvisor()
        self.wb = WhiteBalance()

        self._target = None       # 目标色（校正后 Color）
        self._target_raw = None   # 目标色原始采样
        self._sampling_interval = None
        self._advice_counter = 0
        self.on_close = None

        # 暂存并替换取色回调：AI 模式下点击画面 = 对焦锁定目标色
        self._orig_pick_cb = camera_view.on_color_picked
        camera_view.on_color_picked = self._on_pick_target

        self._build_ui()

    def _build_ui(self):
        # ── 顶栏 ──
        bar = BoxLayout(size_hint=(1, None), height=dp(42), spacing=dp(6), padding=dp(6))
        with bar.canvas.before:
            GraphicsColor(0.13, 0.13, 0.16, 1)
            self._bar_bg = Rectangle(pos=bar.pos, size=bar.size)
        bar.bind(pos=self._resize_bar, size=self._resize_bar)

        self.btn_back = Button(
            text="← 返回", size_hint=(None, 1), width=dp(62),
            font_size=dp(13), background_color=(0.4, 0.25, 0.2, 1),
        )
        self.btn_back.bind(on_release=lambda b: self.request_close())
        bar.add_widget(self.btn_back)

        self.bar_title = Label(
            text="AI 辅助调色", size_hint=(1, 1),
            font_size=dp(15), color=(1, 1, 1, 1), bold=True,
        )
        bar.add_widget(self.bar_title)

        self.btn_cal = Button(
            text="白卡校色", size_hint=(None, 1), width=dp(70),
            font_size=dp(12), background_color=(0.2, 0.5, 0.45, 1),
        )
        self.btn_cal.bind(on_release=lambda b: self._do_calibrate())
        bar.add_widget(self.btn_cal)

        self.bar_status = Label(
            text="", size_hint=(None, 1), width=dp(70),
            font_size=dp(10), color=(0.7, 0.9, 0.7, 1),
        )
        bar.add_widget(self.bar_status)
        self.add_widget(bar)

        # ── 主体：竖屏上下 / 横屏左右 ──
        landscape = Window.width > Window.height
        body = BoxLayout(orientation="horizontal" if landscape else "vertical", spacing=1)
        body.size_hint = (1, 1)
        self.add_widget(body)

        # 摄像头区（CameraView 由主界面 reparent 进来，FocusBox 叠加其上）
        self.cam_area = FloatLayout()
        self.cam_area.size_hint = (0.55, 1) if landscape else (1, 0.55)
        body.add_widget(self.cam_area)
        self.focus_box = FocusBox()

        # 信息面板（可滚动）
        scroll = ScrollView()
        scroll.size_hint = (0.45, 1) if landscape else (1, 0.45)
        body.add_widget(scroll)

        self.info_box = BoxLayout(
            orientation="vertical", size_hint_y=None,
            spacing=dp(4), padding=dp(8),
        )
        self.info_box.bind(minimum_height=self.info_box.setter("height"))
        scroll.add_widget(self.info_box)

        # 目标色 | 当前色浆 并排
        row = BoxLayout(orientation="horizontal", spacing=dp(8),
                        size_hint_y=None, height=dp(76))
        self.target_block = ColorBlock("目标色（点击对焦）")
        self.current_block = ColorBlock("当前色浆（中心准星）")
        row.add_widget(self.target_block)
        row.add_widget(self.current_block)
        self.info_box.add_widget(row)

        # 目标色卡匹配
        self.card_lbl = Label(
            text="目标色卡：--", size_hint_y=None, height=dp(18),
            font_size=dp(11), color=(0.7, 0.85, 1, 1),
        )
        self.info_box.add_widget(self.card_lbl)

        # 色差
        self.delta_lbl = Label(
            text="ΔE 色差：--", size_hint_y=None, height=dp(22),
            font_size=dp(13), color=(1, 0.9, 0.5, 1), bold=True,
        )
        self.info_box.add_widget(self.delta_lbl)

        # 下一步添加（颜料可视化：色块+名称+比例条+比例）
        advice_title = Label(
            text="下一步添加", size_hint_y=None, height=dp(18),
            font_size=dp(12), color=(0.62, 0.62, 0.68, 1),
        )
        self.info_box.add_widget(advice_title)

        pig_row = BoxLayout(orientation="horizontal", spacing=dp(6),
                            size_hint_y=None, height=dp(46))
        self.pig_swatch = SwatchWidget()
        self.pig_swatch.size_hint = (None, 1)
        self.pig_swatch.width = dp(46)
        pig_row.add_widget(self.pig_swatch)

        pig_mid = BoxLayout(orientation="vertical", spacing=dp(2), size_hint=(None, 1))
        pig_mid.width = dp(96)
        self.pig_name_lbl = Label(
            text="先对焦目标色", size_hint=(1, None), height=dp(20),
            font_size=dp(13), color=(1, 1, 1, 1), bold=True,
            halign="left", valign="middle",
        )
        self.pig_name_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pig_mid.add_widget(self.pig_name_lbl)
        self.pig_desc_lbl = Label(
            text="点击画面锁定目标颜色", size_hint=(1, None), height=dp(15),
            font_size=dp(10), color=(0.6, 0.6, 0.65, 1),
            halign="left", valign="middle",
        )
        self.pig_desc_lbl.bind(size=lambda i, v: setattr(i, "text_size", (i.width, None)))
        pig_mid.add_widget(self.pig_desc_lbl)
        pig_row.add_widget(pig_mid)

        self.pig_bar = RatioBar()
        pig_row.add_widget(self.pig_bar)

        self.pig_ratio_lbl = Label(
            text="--", size_hint=(None, 1), width=dp(44),
            font_size=dp(13), color=(1, 0.9, 0.5, 1), bold=True,
        )
        pig_row.add_widget(self.pig_ratio_lbl)
        self.info_box.add_widget(pig_row)

        # 预计混合后
        exp_row = BoxLayout(orientation="horizontal", spacing=dp(8),
                            size_hint_y=None, height=dp(76))
        self.expect_block = ColorBlock("预计混合后")
        self.expect_delta_lbl = Label(
            text="", size_hint=(1, None), height=dp(34),
            font_size=dp(11), color=(0.7, 0.9, 0.7, 1),
        )
        exp_row.add_widget(self.expect_block)
        exp_row.add_widget(self.expect_delta_lbl)
        self.info_box.add_widget(exp_row)

        # 白卡状态 + 操作提示
        self.wb_lbl = Label(
            text=self.wb.describe(), size_hint_y=None, height=dp(16),
            font_size=dp(10), color=(0.55, 0.55, 0.6, 1),
        )
        self.info_box.add_widget(self.wb_lbl)

        tip = Label(
            text="提示：点击画面任意位置对焦锁定目标色；把色浆对准中心准星实时看差距",
            size_hint_y=None, height=dp(28), font_size=dp(10),
            color=(0.5, 0.5, 0.55, 1),
        )
        self.info_box.add_widget(tip)

    def _resize_bar(self, inst, val):
        self._bar_bg.pos = inst.pos
        self._bar_bg.size = inst.size

    def open(self, on_close=None):
        self.on_close = on_close or (lambda: None)
        self._sampling_interval = Clock.schedule_interval(self._poll, 1.0 / 15)

    def close(self):
        """仅清理（计时器 + 恢复回调），不触发 on_close，避免递归。"""
        if self._sampling_interval is not None:
            Clock.unschedule(self._sampling_interval)
            self._sampling_interval = None
        if self.camera_view is not None and getattr(self, "_orig_pick_cb", None) is not None:
            self.camera_view.on_color_picked = self._orig_pick_cb
            self._orig_pick_cb = None

    def request_close(self):
        """请求关闭：清理后通知 on_close（由主界面完成移除与摄像头归还）。"""
        self.close()
        cb = getattr(self, "on_close", None)
        if cb:
            cb()

    def shutdown(self):
        """shutdown = close（清理计时器与回调，不触发 on_close，防止递归）。"""
        self.close()

    # ── 取色 ──

    def _on_pick_target(self, color):
        """点击画面：对焦锁定目标色 + 对焦框动画。"""
        if color is None:
            return
        self._target_raw = color
        self._target = self.wb.apply(color)
        self.target_block.set_color(self._target, nearest_named_color(self._target))
        self._update_card_lbl()
        # 对焦框画在准星位置（CameraView 已把准星移到点击处，坐标与 cam_area 一致）
        try:
            ch = self.camera_view.crosshair
            self.focus_box.show_at(ch.center_x, ch.center_y)
        except Exception:
            pass
        corrected, _ = self._center_color()
        if corrected is not None:
            self._render_advice(corrected)

    def _center_color(self, radius=12):
        """画面中心（准星）采样，返回校正后与原始颜色。"""
        if self.camera_view is None or self.camera_view._frame is None:
            return None, None
        h, w = self.camera_view._frame.shape[:2]
        raw = average_color_region(self.camera_view._frame, (w // 2, h // 2), radius=radius)
        return self.wb.apply(raw), raw

    # ── 校色 ──

    def _do_calibrate(self):
        """把画面中心对标准灰卡采样作为校色基准。"""
        raw = None
        if self.camera_view is not None and self.camera_view._frame is not None:
            h, w = self.camera_view._frame.shape[:2]
            raw = average_color_region(self.camera_view._frame, (w // 2, h // 2), radius=15)
        if raw is None:
            self._set_status("无画面")
            return
        try:
            self.wb.calibrate(raw)
            self._set_status("已校色")
            self.wb_lbl.text = self.wb.describe()
            # 校色改变后重算目标色
            if self._target is not None and self._target_raw is not None:
                self._target = self.wb.apply(self._target_raw)
                self.target_block.set_color(self._target, nearest_named_color(self._target))
                self._update_card_lbl()
        except Exception:
            self._set_status("校色失败")

    def _set_status(self, text):
        self.bar_status.text = text

    def _update_card_lbl(self):
        """刷新目标色的商用色卡匹配显示。"""
        if self._target is None:
            self.card_lbl.text = "目标色卡：--"
            return
        m = best_match(self._target)
        if m is None:
            self.card_lbl.text = "目标色卡：--"
        else:
            self.card_lbl.text = f"目标色卡：{m.display}  ΔE={m.delta_e:.1f}"

    # ── 实时轮询 ──

    def _poll(self, dt):
        if self.camera_view is None:
            return
        corrected, _ = self._center_color()
        if corrected is None:
            return
        self.current_block.set_color(corrected, nearest_named_color(corrected))

        if self._target is not None:
            de = self._target.distance(corrected)
            if de <= 2.0:
                self.delta_lbl.text = f"ΔE 色差：{de:.1f}  ✓ 已非常接近"
            else:
                self.delta_lbl.text = f"ΔE 色差：{de:.1f}"
            # 颜料建议计算量较大，每 5 帧重算一次
            self._advice_counter += 1
            if self._advice_counter % 5 == 0:
                self._render_advice(corrected)
        else:
            self.delta_lbl.text = "ΔE 色差：--"

    # ── 建议渲染 ──

    def _render_advice(self, current):
        if self._target is None:
            return
        suggestion = self.advisor.suggest_next_pigment(current, self._target)

        if suggestion is None:
            self.pig_swatch.set_color(None)
            self.pig_name_lbl.text = "已接近目标"
            self.pig_desc_lbl.text = "无需继续加色，或换更接近的基色微调"
            self.pig_bar.set_ratio(0, None)
            self.pig_ratio_lbl.text = "--"
            self.expect_block.set_color(None)
            self.expect_delta_lbl.text = ""
            return

        p = suggestion["pigment"]
        ratio = suggestion["ratio"]
        self.pig_swatch.set_color(p.color)
        self.pig_name_lbl.text = p.name
        self.pig_desc_lbl.text = p.description or "基色颜料"
        self.pig_bar.set_ratio(ratio, p.color)
        self.pig_ratio_lbl.text = f"{ratio * 100:.0f}%"
        self.expect_block.set_color(suggestion["mixed"])
        self.expect_delta_lbl.text = (
            f"加入后 ΔE：{self._target.distance(current):.1f} → {suggestion['delta_e']:.1f}"
        )


# ──────────────────────────────────────────────
# 主界面
# ──────────────────────────────────────────────

class ColorAssistantApp(App):
    """AI 调色助手主应用。"""

    def build(self):
        self.title = "AI 调色助手"
        Window.clearcolor = (0.12, 0.12, 0.14, 1)

        # 根容器：FloatLayout，用于承载主界面 + AI调色全屏覆盖层
        self.root = FloatLayout()
        self.main_box = BoxLayout(orientation="vertical", spacing=0)
        self.main_box.size_hint = (1, 1)
        self.root.add_widget(self.main_box)

        # 顶部标题栏
        title_bar = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(8), padding=dp(8))
        with title_bar.canvas.before:
            GraphicsColor(0.15, 0.15, 0.17, 1)
            self._title_bg = Rectangle(pos=title_bar.pos, size=title_bar.size)
        title_bar.bind(pos=self._update_title_bg, size=self._update_title_bg)

        title_label = Label(
            text="AI 调色助手",
            size_hint=(1, 1),
            font_size=dp(16),
            color=(1, 1, 1, 1),
            bold=True,
        )
        title_bar.add_widget(title_label)

        btn_report = Button(
            text="完整报告",
            size_hint=(None, 1),
            width=dp(80),
            font_size=dp(12),
            background_color=(0.25, 0.55, 0.85, 1),
        )
        btn_report.bind(on_release=lambda btn: self._on_report())
        title_bar.add_widget(btn_report)

        self.main_box.add_widget(title_bar)

        # 主体区域（竖屏：摄像头 55% / 信息 45%）
        if Window.width > Window.height and Window.width > 600:
            body = BoxLayout(orientation="horizontal", spacing=1)
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(0.55, 1))
            self.info_panel = InfoPanel(size_hint=(0.45, 1))
        else:
            body = BoxLayout(orientation="vertical", spacing=1)
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(1, 0.55))
            self.info_panel = InfoPanel(size_hint=(1, 0.45))

        body.add_widget(self.camera_view)
        body.add_widget(self.info_panel)
        self._body = body
        self.main_box.add_widget(body)

        # 底部工具栏
        toolbar = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(6), padding=dp(8))
        with toolbar.canvas.before:
            GraphicsColor(0.15, 0.15, 0.17, 1)
            self._toolbar_bg = Rectangle(pos=toolbar.pos, size=toolbar.size)
        toolbar.bind(pos=self._update_toolbar_bg, size=self._update_toolbar_bg)

        btn_center = Button(text="中心取色", size_hint=(1, 1), font_size=dp(13), background_color=(0.2, 0.6, 0.4, 1))
        btn_center.bind(on_release=lambda btn: self._on_center_pick())
        toolbar.add_widget(btn_center)

        btn_dominant = Button(text="提取主色", size_hint=(1, 1), font_size=dp(13), background_color=(0.6, 0.4, 0.2, 1))
        btn_dominant.bind(on_release=lambda btn: self._on_dominant_pick())
        toolbar.add_widget(btn_dominant)

        btn_ai = Button(text="AI辅助调色", size_hint=(1, 1), font_size=dp(13), background_color=(0.55, 0.3, 0.65, 1))
        btn_ai.bind(on_release=lambda btn: self._on_open_mix())
        toolbar.add_widget(btn_ai)

        btn_rotate = Button(text="旋转画面", size_hint=(None, 1), width=dp(80), font_size=dp(13), background_color=(0.35, 0.45, 0.6, 1))
        btn_rotate.bind(on_release=lambda btn: self._on_rotate())
        toolbar.add_widget(btn_rotate)

        btn_log = Button(text="日志", size_hint=(None, 1), width=dp(56), font_size=dp(13), background_color=(0.25, 0.25, 0.35, 1))
        btn_log.bind(on_release=lambda btn: self._on_show_crash_path())
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

        # 摄像头在下层，对焦框叠加其上
        self.mix_screen.cam_area.add_widget(self.camera_view)
        self.mix_screen.cam_area.add_widget(self.mix_screen.focus_box)

        self.mix_screen.open(on_close=self._on_close_mix)

    def _on_close_mix(self):
        """关闭 AI 辅助调色界面，摄像头归还主界面。"""
        if self.mix_screen is None:
            return
        self.mix_screen.shutdown()
        # 摄像头移回主界面原位置（body 第一个子项）
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
