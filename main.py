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

# ── OpenCV 可选导入 ──
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 注意：不在此处顶层导入 numpy。
# 桌面端 numpy 随 OpenCV 提供；Android 端不安装 numpy，仅用 Frame（纯 Python）。

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color as GraphicsColor, Rectangle, Line, Ellipse
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
)
from ai_assistant import ColorAdvisor, nearest_named_color


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

class CameraView(FloatLayout):
    """摄像头实时画面，支持点击取色。

    桌面端：OpenCV VideoCapture
    Android 端：Kivy 原生 Camera（texture 像素提取）
    """

    def __init__(self, on_color_picked=None, **kwargs):
        super().__init__(**kwargs)
        self.on_color_picked = on_color_picked

        self._frame = None        # BGR numpy 数组（统一格式）
        self._pick_marks = []
        self._camera_started = False

        if HAS_CV2 and not IS_ANDROID:
            # ── OpenCV 模式（桌面）──
            self.image_widget = Image(allow_stretch=True, keep_ratio=False)
            self.add_widget(self.image_widget)
            self.capture = None
            self._texture = None
            self._camera_active = False
        else:
            # ── Kivy Camera 模式（Android / 无 OpenCV）──
            from kivy.uix.camera import Camera as KivyCamera

            self.kivy_camera = KivyCamera(
                play=True,
                index=0,
                allow_stretch=True,
                keep_ratio=False,
                resolution=(640, 480),
            )
            self.add_widget(self.kivy_camera)

        # 十字准星
        self.crosshair = CrosshairWidget()
        self.add_widget(self.crosshair)

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
            # Kivy Camera 在 __init__ 中已 play=True，只需启动帧更新
            self._camera_started = True
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
            if hasattr(self, "kivy_camera"):
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
        if not hasattr(self, "kivy_camera"):
            return

        tex = self.kivy_camera.texture
        if tex is None:
            return

        w, h = tex.size
        try:
            pixels = tex.pixels
            if not pixels:
                return
            # 存为 Frame，仅在取色时按需解码（无需 numpy，避免逐帧转换开销）
            self._frame = Frame(pixels, w, h, src="rgba_flip")
        except Exception:
            pass

    # ── 点击取色 ──

    def on_touch_down(self, touch):
        if self._frame is None or not self.collide_point(*touch.pos):
            return False

        # 获取画面显示尺寸
        if HAS_CV2 and not IS_ANDROID:
            img_w, img_h = self.image_widget.norm_image_size
        else:
            img_w, img_h = self.kivy_camera.texture_size if self.kivy_camera.texture else (0, 0)
            # 纹理尺寸与显示尺寸可能不同，需要用 norm_image_size
            try:
                img_w, img_h = self.kivy_camera.norm_image_size
            except Exception:
                pass

        if img_w == 0 or img_h == 0:
            return False

        iw, ih = self.size
        ox = (iw - img_w) / 2
        oy = (ih - img_h) / 2

        local_x = touch.x - self.x - ox
        local_y = touch.y - self.y - oy

        if local_x < 0 or local_x > img_w or local_y < 0 or local_y > img_h:
            return False

        frame_h, frame_w = self._frame.shape[:2]
        fx = int((local_x / img_w) * frame_w)
        fy = int((1 - local_y / img_h) * frame_h)
        fx = max(0, min(frame_w - 1, fx))
        fy = max(0, min(frame_h - 1, fy))

        color = average_color_region(self._frame, (fx, fy), radius=10)

        self._add_pick_mark(touch.x - self.x, touch.y - self.y, color)
        self.crosshair.pos = (touch.x - self.x - 15, touch.y - self.y - 15)

        if self.on_color_picked:
            self.on_color_picked(color)

        return True

    def _add_pick_mark(self, x, y, color: Color):
        mark = PickMark(color=color)
        mark.size = (30, 30)
        mark.pos = (x - 15, y - 15)
        self._pick_marks.append(mark)
        self.add_widget(mark)
        while len(self._pick_marks) > 5:
            old = self._pick_marks.pop(0)
            self.remove_widget(old)

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


class PickMark(Widget):
    """取色点标记（显示取色颜色）。"""

    def __init__(self, color: Color, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *args):
        self.canvas.clear()
        with self.canvas:
            r, g, b = self.color.rgb_normalized
            GraphicsColor(r, g, b, 1)
            Ellipse(pos=self.pos, size=self.size)
            GraphicsColor(1, 1, 1, 0.9)
            Line(circle=(self.center_x, self.center_y, 14), width=1.5)


# ──────────────────────────────────────────────
# 信息面板
# ──────────────────────────────────────────────

class ColorSwatch(BoxLayout):
    """颜色色块 + 标签。"""

    def __init__(self, color: Color, label_text: str = "", **kwargs):
        super().__init__(**kwargs)
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

    def show_analysis(self, color: Color):
        self._clear()

        analysis = self.advisor.analyze(color)

        self._add_label("[b][color=4FC3F7]采集颜色[/color][/b]", font_size=dp(16))
        self._add_swatch(color, f"{analysis.hex_code}  「{analysis.name}」")

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
# 主界面
# ──────────────────────────────────────────────

class ColorAssistantApp(App):
    """AI 调色助手主应用。"""

    def build(self):
        self.title = "AI 调色助手"
        Window.clearcolor = (0.12, 0.12, 0.14, 1)

        self.root = BoxLayout(orientation="vertical", spacing=0)

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

        self.root.add_widget(title_bar)

        # 主体区域
        if Window.width > Window.height and Window.width > 600:
            body = BoxLayout(orientation="horizontal", spacing=1)
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(0.55, 1))
            self.info_panel = InfoPanel(size_hint=(0.45, 1))
        else:
            body = BoxLayout(orientation="vertical", spacing=1)
            self.camera_view = CameraView(on_color_picked=self._on_color_picked, size_hint=(1, 0.5))
            self.info_panel = InfoPanel(size_hint=(1, 0.5))

        body.add_widget(self.camera_view)
        body.add_widget(self.info_panel)
        self.root.add_widget(body)

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

        btn_clear = Button(text="清除标记", size_hint=(None, 1), width=dp(80), font_size=dp(13), background_color=(0.4, 0.2, 0.2, 1))
        btn_clear.bind(on_release=lambda btn: self._on_clear_marks())
        toolbar.add_widget(btn_clear)

        self.root.add_widget(toolbar)

        self._current_color = None

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

    def _on_clear_marks(self):
        for mark in self.camera_view._pick_marks:
            self.camera_view.remove_widget(mark)
        self.camera_view._pick_marks.clear()

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
        return True

    def on_resume(self):
        self.camera_view.start_camera()

    def on_stop(self):
        self.camera_view.stop_camera()


if __name__ == "__main__":
    ColorAssistantApp().run()
