"""
颜色引擎：颜色空间转换、颜色差异计算、减色混合模型、配方搜索。

所有函数和类不依赖任何 GUI 框架，可在桌面和 Android 上复用。
"""

import math
import colorsys
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# ──────────────────────────────────────────────
# 颜色类
# ──────────────────────────────────────────────

@dataclass
class Color:
    """以 RGB(0-255) 为基准存储，提供各色彩空间转换。"""
    r: int
    g: int
    b: int

    # ── 转换属性 ──

    @property
    def rgb(self) -> Tuple[int, int, int]:
        return (self.r, self.g, self.b)

    @property
    def rgb_normalized(self) -> Tuple[float, float, float]:
        return (self.r / 255.0, self.g / 255.0, self.b / 255.0)

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @property
    def hsl(self) -> Tuple[float, float, float]:
        h, l, s = colorsys.rgb_to_hls(*self.rgb_normalized)
        return (h * 360, s * 100, l * 100)

    @property
    def hsv(self) -> Tuple[float, float, float]:
        h, s, v = colorsys.rgb_to_hsv(*self.rgb_normalized)
        return (h * 360, s * 100, v * 100)

    @property
    def cmyk(self) -> Tuple[float, float, float, float]:
        r, g, b = self.rgb_normalized
        k = 1.0 - max(r, g, b)
        if k >= 1.0:
            return (0.0, 0.0, 0.0, 100.0)
        c = (1.0 - r - k) / (1.0 - k)
        m = (1.0 - g - k) / (1.0 - k)
        y = (1.0 - b - k) / (1.0 - k)
        return (c * 100, m * 100, y * 100, k * 100)

    @property
    def lab(self) -> Tuple[float, float, float]:
        """RGB → XYZ → CIELAB（D65 白点）。"""
        r, g, b = self.rgb_normalized

        # sRGB → 线性 RGB
        def lin(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b = lin(r), lin(g), lin(b)

        # 线性 RGB → XYZ (D65)
        x = r * 0.4124 + g * 0.3576 + b * 0.1805
        y = r * 0.2126 + g * 0.7152 + b * 0.0722
        z = r * 0.0193 + g * 0.1192 + b * 0.9505

        # XYZ → LAB (D65 参考白)
        xn, yn, zn = 0.95047, 1.0, 1.08883
        x, y, z = x / xn, y / yn, z / zn

        def f(t):
            return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

        fx, fy, fz = f(x), f(y), f(z)
        L = 116 * fy - 16
        a_val = 500 * (fx - fy)
        b_val = 200 * (fy - fz)
        return (L, a_val, b_val)

    # ── 工厂方法 ──

    @classmethod
    def from_hex(cls, hex_str: str) -> "Color":
        hex_str = hex_str.lstrip("#")
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return cls(r, g, b)

    @classmethod
    def from_hsl(cls, h: float, s: float, l: float) -> "Color":
        r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
        return cls(int(r * 255), int(g * 255), int(b * 255))

    @classmethod
    def from_lab(cls, L: float, a: float, b: float) -> "Color":
        """LAB → XYZ → RGB"""
        fy = (L + 16) / 116
        fx = a / 500 + fy
        fz = fy - b / 200

        def inv_f(t):
            return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787

        xn, yn, zn = 0.95047, 1.0, 1.08883
        x = xn * inv_f(fx)
        y = yn * inv_f(fy)
        z = zn * inv_f(fz)

        # XYZ → 线性 RGB (D65)
        r = x * 3.2406 + y * -1.5372 + z * -0.4986
        g = x * -0.9689 + y * 1.8758 + z * 0.0415
        b_val = x * 0.0557 + y * -0.2040 + z * 1.0570

        # 线性 → sRGB
        def srgb(c):
            return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

        r, g, b_val = srgb(r), srgb(g), srgb(b_val)
        return cls(
            max(0, min(255, int(round(r * 255)))),
            max(0, min(255, int(round(g * 255)))),
            max(0, min(255, int(round(b_val * 255)))),
        )

    # ── 工具 ──

    def distance_lab(self, other: "Color") -> float:
        """CIE76 颜色差异（Lab 欧氏距离）。"""
        l1, a1, b1 = self.lab
        l2, a2, b2 = other.lab
        return math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)

    def distance_de2000(self, other: "Color") -> float:
        """CIEDE2000 颜色差异，感知上更准确。"""
        l1, a1, b1 = self.lab
        l2, a2, b2 = other.lab

        kL = kC = kH = 1.0
        C1 = math.sqrt(a1 ** 2 + b1 ** 2)
        C2 = math.sqrt(a2 ** 2 + b2 ** 2)
        C_bar = (C1 + C2) / 2

        G = 0.5 * (1 - math.sqrt(C_bar ** 7 / (C_bar ** 7 + 25 ** 7)))
        a1p = (1 + G) * a1
        a2p = (1 + G) * a2
        C1p = math.sqrt(a1p ** 2 + b1 ** 2)
        C2p = math.sqrt(a2p ** 2 + b2 ** 2)
        h1p = math.degrees(math.atan2(b1, a1p)) % 360
        h2p = math.degrees(math.atan2(b2, a2p)) % 360

        dLp = l2 - l1
        dCp = C2p - C1p

        if C1p * C2p == 0:
            dhp = 0
        else:
            diff = h2p - h1p
            if abs(diff) <= 180:
                dhp = diff
            elif diff > 180:
                dhp = diff - 360
            else:
                dhp = diff + 360
        dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

        Lp_bar = (l1 + l2) / 2
        Cp_bar = (C1p + C2p) / 2

        if C1p * C2p == 0:
            Hp_bar = h1p + h2p
        else:
            if abs(h1p - h2p) > 180:
                Hp_bar = (h1p + h2p + 360) / 2 if (h1p + h2p) < 360 else (h1p + h2p - 360) / 2
            else:
                Hp_bar = (h1p + h2p) / 2

        T = (1
             - 0.17 * math.cos(math.radians(Hp_bar - 30))
             + 0.24 * math.cos(math.radians(2 * Hp_bar))
             + 0.32 * math.cos(math.radians(3 * Hp_bar + 6))
             - 0.20 * math.cos(math.radians(4 * Hp_bar - 63)))

        dTheta = 30 * math.exp(-((Hp_bar - 275) / 25) ** 2)
        SL = 1 + 0.015 * (Lp_bar - 50) ** 2 / math.sqrt(20 + (Lp_bar - 50) ** 2)
        SC = 1 + 0.045 * Cp_bar
        SH = 1 + 0.015 * Cp_bar * T
        RT = -2 * math.sqrt(Cp_bar ** 7 / (Cp_bar ** 7 + 25 ** 7)) * math.sin(math.radians(2 * dTheta))

        dE = math.sqrt(
            (dLp / (kL * SL)) ** 2 +
            (dCp / (kC * SC)) ** 2 +
            (dHp / (kH * SH)) ** 2 +
            RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
        )
        return dE

    def distance(self, other: "Color", method: str = "de2000") -> float:
        if method == "lab":
            return self.distance_lab(other)
        return self.distance_de2000(other)

    def __repr__(self):
        return f"Color(r={self.r}, g={self.g}, b={self.b}, hex={self.hex})"


# ──────────────────────────────────────────────
# 基础颜料库
# ──────────────────────────────────────────────

@dataclass
class Pigment:
    name: str
    color: Color
    # 中文别名
    aliases: List[str] = field(default_factory=list)


BASE_PIGMENTS: List[Pigment] = [
    Pigment("钛白", Color(255, 255, 255), ["白色", "白"]),
    Pigment("炭黑", Color(0, 0, 0), ["黑色", "黑"]),
    Pigment("大红", Color(220, 40, 40), ["红色", "红", "朱红"]),
    Pigment("柠檬黄", Color(255, 220, 30), ["黄色", "黄"]),
    Pigment("群青", Color(40, 60, 200), ["蓝色", "蓝"]),
    Pigment("翠绿", Color(30, 160, 60), ["绿色", "绿"]),
    Pigment("紫色", Color(130, 40, 160), ["紫"]),
    Pigment("橙色", Color(255, 140, 30), ["橙"]),
]


# ──────────────────────────────────────────────
# 减色混合引擎
# ──────────────────────────────────────────────

class ColorMixer:
    """基于减色法（颜料吸光）的颜色混合模型。"""

    @staticmethod
    def mix_subtractive(colors: List[Color], weights: List[float]) -> Color:
        """
        减色混合：各颜料按权重吸收光线，混合结果为各通道的加权几何均值。

        公式：mixed_channel = prod(channel_i ^ weight_i)
        这模拟了颜料叠加时各波长被逐层吸收的物理过程。
        """
        if len(colors) != len(weights):
            raise ValueError("颜色数量与权重数量不匹配")
        total = sum(weights)
        if total <= 0:
            raise ValueError("权重之和必须大于 0")
        weights = [w / total for w in weights]

        # 在线性 sRGB 空间做减色混合
        def to_lin(c):
            return (c / 255.0) ** 2.2 if c / 255.0 > 0.04045 else (c / 255.0) / 12.92

        def from_lin(c):
            c = max(0.0, min(1.0, c))
            return int(round((1.055 * (c ** (1 / 2.2)) - 0.055) * 255)) if c > 0.0031308 else int(round(c * 12.92 * 255))

        r_lin = 1.0
        g_lin = 1.0
        b_lin = 1.0
        for color, w in zip(colors, weights):
            r, g, b = color.rgb_normalized
            r_lin *= (to_lin(color.r)) ** w
            g_lin *= (to_lin(color.g)) ** w
            b_lin *= (to_lin(color.b)) ** w

        return Color(from_lin(r_lin), from_lin(g_lin), from_lin(b_lin))

    @staticmethod
    def mix_additive(colors: List[Color], weights: List[float]) -> Color:
        """加色混合（光混合），简单加权平均，用于参考对比。"""
        total = sum(weights)
        weights = [w / total for w in weights]
        r = sum(c.r * w for c, w in zip(colors, weights))
        g = sum(c.g * w for c, w in zip(colors, weights))
        b = sum(c.b * w for c, w in zip(colors, weights))
        return Color(int(round(r)), int(round(g)), int(round(b)))


# ──────────────────────────────────────────────
# 配方搜索
# ──────────────────────────────────────────────

@dataclass
class Recipe:
    """一份调色配方。"""
    components: List[Tuple[str, Color, float]]  # (颜料名, 颜色, 比例百分比)
    result: Color  # 混合后的颜色
    target: Color  # 目标颜色
    delta_e: float  # 与目标色的色差

    @property
    def accuracy(self) -> str:
        """色差对应的匹配精度等级。"""
        if self.delta_e < 1.0:
            return "极精确"
        elif self.delta_e < 2.0:
            return "非常接近"
        elif self.delta_e < 5.0:
            return "接近"
        elif self.delta_e < 10.0:
            return "可接受"
        else:
            return "偏差较大"

    def format(self) -> str:
        lines = [f"目标色: {self.target.hex}  混合色: {self.result.hex}"]
        lines.append(f"色差 ΔE: {self.delta_e:.2f}  ({self.accuracy})")
        lines.append("配方:")
        for name, color, ratio in self.components:
            lines.append(f"  {name} ({color.hex}): {ratio:.1f}%")
        return "\n".join(lines)


class RecipeFinder:
    """在基础颜料库中搜索最佳调色配方。"""

    def __init__(self, pigments: List[Pigment] = None):
        self.pigments = pigments or BASE_PIGMENTS

    def find_best_recipe(
        self,
        target: Color,
        max_components: int = 3,
        search_steps: int = 20,
    ) -> Recipe:
        """
        搜索最接近目标色的配方。

        策略：
        1. 先检查单色匹配
        2. 二色组合：对每对颜料做比例搜索
        3. 三色组合：网格搜索两个比例，第三个为剩余
        """
        best_recipe = None
        best_delta = float("inf")

        n = len(self.pigments)

        # 1. 单色
        for i, p in enumerate(self.pigments):
            d = target.distance(p.color)
            if d < best_delta:
                best_delta = d
                best_recipe = Recipe(
                    components=[(p.name, p.color, 100.0)],
                    result=p.color,
                    target=target,
                    delta_e=d,
                )

        # 2. 二色组合
        for i in range(n):
            for j in range(i + 1, n):
                ci, cj = self.pigments[i].color, self.pigments[j].color
                ni, nj = self.pigments[i].name, self.pigments[j].name
                for step in range(1, search_steps):
                    w = step / search_steps
                    mixed = ColorMixer.mix_subtractive([ci, cj], [w, 1 - w])
                    d = target.distance(mixed)
                    if d < best_delta:
                        best_delta = d
                        best_recipe = Recipe(
                            components=[(ni, ci, w * 100), (nj, cj, (1 - w) * 100)],
                            result=mixed,
                            target=target,
                            delta_e=d,
                        )

        # 3. 三色组合
        if max_components >= 3:
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        ci, cj, ck = (
                            self.pigments[i].color,
                            self.pigments[j].color,
                            self.pigments[k].color,
                        )
                        ni, nj, nk = (
                            self.pigments[i].name,
                            self.pigments[j].name,
                            self.pigments[k].name,
                        )
                        steps = max(6, search_steps // 2)
                        for si in range(1, steps):
                            for sj in range(1, steps - si):
                                wi = si / steps
                                wj = sj / steps
                                wk = 1.0 - wi - wj
                                if wk <= 0:
                                    continue
                                mixed = ColorMixer.mix_subtractive(
                                    [ci, cj, ck], [wi, wj, wk]
                                )
                                d = target.distance(mixed)
                                if d < best_delta:
                                    best_delta = d
                                    best_recipe = Recipe(
                                        components=[
                                            (ni, ci, wi * 100),
                                            (nj, cj, wj * 100),
                                            (nk, ck, wk * 100),
                                        ],
                                        result=mixed,
                                        target=target,
                                        delta_e=d,
                                    )

        return best_recipe

    def find_recipes(
        self,
        target: Color,
        top_n: int = 3,
        max_components: int = 3,
    ) -> List[Recipe]:
        """返回前 N 个最佳配方。"""
        results: List[Recipe] = []

        n = len(self.pigments)
        search_steps = 20

        # 收集所有候选
        # 单色
        for p in self.pigments:
            d = target.distance(p.color)
            results.append(Recipe(
                components=[(p.name, p.color, 100.0)],
                result=p.color,
                target=target,
                delta_e=d,
            ))

        # 二色
        for i in range(n):
            for j in range(i + 1, n):
                ci, cj = self.pigments[i].color, self.pigments[j].color
                ni, nj = self.pigments[i].name, self.pigments[j].name
                for step in range(1, search_steps):
                    w = step / search_steps
                    mixed = ColorMixer.mix_subtractive([ci, cj], [w, 1 - w])
                    d = target.distance(mixed)
                    results.append(Recipe(
                        components=[(ni, ci, w * 100), (nj, cj, (1 - w) * 100)],
                        result=mixed,
                        target=target,
                        delta_e=d,
                    ))

        # 三色
        if max_components >= 3:
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        ci, cj, ck = (
                            self.pigments[i].color,
                            self.pigments[j].color,
                            self.pigments[k].color,
                        )
                        ni, nj, nk = (
                            self.pigments[i].name,
                            self.pigments[j].name,
                            self.pigments[k].name,
                        )
                        steps = 8
                        for si in range(1, steps):
                            for sj in range(1, steps - si):
                                wi = si / steps
                                wj = sj / steps
                                wk = 1.0 - wi - wj
                                if wk <= 0:
                                    continue
                                mixed = ColorMixer.mix_subtractive(
                                    [ci, cj, ck], [wi, wj, wk]
                                )
                                d = target.distance(mixed)
                                results.append(Recipe(
                                    components=[
                                        (ni, ci, wi * 100),
                                        (nj, cj, wj * 100),
                                        (nk, ck, wk * 100),
                                    ],
                                    result=mixed,
                                    target=target,
                                    delta_e=d,
                                ))

        results.sort(key=lambda r: r.delta_e)
        # 去重：避免返回过多相似的配方
        unique: List[Recipe] = []
        for r in results:
            if all(abs(r.delta_e - u.delta_e) > 0.5 for u in unique):
                unique.append(r)
            if len(unique) >= top_n:
                break
        return unique


# ──────────────────────────────────────────────
# 图像取色
# ──────────────────────────────────────────────

class Frame:
    """轻量像素帧，避免在 Android 上依赖 numpy。

    ``data`` 为行主序像素字节，``bgr_at`` 负责按需解码为 BGR：
      - src="bgr"：data 直接是 BGR 交错字节（桌面 OpenCV 帧）
      - src="rgba_flip"：Kivy 纹理像素（RGBA，行自下而上），
        解码时垂直翻转并将 RGB 转成 BGR，与桌面帧格式保持一致
    """

    def __init__(self, data: bytes, width: int, height: int, src: str = "bgr"):
        self.data = data
        self.width = width
        self.height = height
        self.src = src

    @property
    def shape(self) -> Tuple[int, int, int]:
        return (self.height, self.width, 3)

    def bgr_at(self, x: int, y: int) -> Tuple[int, int, int]:
        d = self.data
        if self.src == "bgr":
            i = (y * self.width + x) * 3
            return (d[i], d[i + 1], d[i + 2])
        # rgba_flip：Kivy 纹理行自下而上，且为 RGBA 顺序
        sy = self.height - 1 - y
        i = (sy * self.width + x) * 4
        r, g, b = d[i], d[i + 1], d[i + 2]
        return (b, g, r)


def _dist2(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2


def extract_dominant_color(image: Frame, k: int = 3) -> Color:
    """
    从 BGR 帧中提取主色（简化 K-means，纯 Python 实现）。
    像素按网格下采样以加速；手动取色可接受亚秒级耗时。
    """
    if image is None:
        return Color(128, 128, 128)
    h, w = image.shape[:2]

    # 网格下采样，最多约 MAX_SAMPLES 个像素点
    max_samples = 4000
    stride = max(1, int((h * w / max(1, max_samples)) ** 0.5))
    samples = []
    y = 0
    while y < h:
        x = 0
        while x < w:
            samples.append(image.bgr_at(x, y))
            x += stride
        y += stride

    n = len(samples)
    if n == 0:
        return Color(128, 128, 128)

    k = max(1, min(k, n))

    # 简易 K-means
    import random
    random.seed(42)
    centers = random.sample(samples, k)

    clusters = [[] for _ in range(k)]
    for _ in range(10):
        clusters = [[] for _ in range(k)]
        for p in samples:
            best = 0
            bd = _dist2(p, centers[0])
            for ci in range(1, k):
                dd = _dist2(p, centers[ci])
                if dd < bd:
                    bd = dd
                    best = ci
            clusters[best].append(p)
        for ci in range(k):
            if clusters[ci]:
                sb = sg = sr = 0
                m = len(clusters[ci])
                for b, g, r in clusters[ci]:
                    sb += b
                    sg += g
                    sr += r
                centers[ci] = (sb / m, sg / m, sr / m)

    # 选择像素最多的簇的中心
    dom = 0
    for ci in range(1, k):
        if len(clusters[ci]) > len(clusters[dom]):
            dom = ci
    b, g, r = centers[dom]
    return Color(
        max(0, min(255, int(round(r)))),
        max(0, min(255, int(round(g)))),
        max(0, min(255, int(round(b)))),
    )


def average_color_region(image: Frame, center: Tuple[int, int], radius: int = 10) -> Color:
    """
    取帧中以 center 为中心、radius 为半径的圆形区域的平均色。
    Frame.bgr_at 返回 BGR。
    """
    if image is None:
        return Color(128, 128, 128)
    h, w = image.shape[:2]
    cx, cy = center
    y0 = max(0, cy - radius)
    y1 = min(h, cy + radius)
    x0 = max(0, cx - radius)
    x1 = min(w, cx + radius)

    if y1 <= y0 or x1 <= x0:
        return Color(128, 128, 128)

    # 圆形掩码（以区域中心为圆心）
    crx = x0 + (x1 - x0) / 2.0
    cry = y0 + (y1 - y0) / 2.0
    sb = sg = sr = 0
    count = 0
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            dx = xx - crx
            dy = yy - cry
            if dx * dx + dy * dy <= radius * radius:
                b, g, r = image.bgr_at(xx, yy)
                sb += b
                sg += g
                sr += r
                count += 1

    if count == 0:
        # 圆形为空时退化为整块区域平均
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                b, g, r = image.bgr_at(xx, yy)
                sb += b
                sg += g
                sr += r
                count += 1

    if count == 0:
        return Color(128, 128, 128)

    m = count
    return Color(
        max(0, min(255, int(round(sr / m)))),
        max(0, min(255, int(round(sg / m)))),
        max(0, min(255, int(round(sb / m)))),
    )
