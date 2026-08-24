"""
AI 调色助手：色彩分析、颜色命名、配色建议、调色配方生成与文字解说。

所有逻辑纯 Python，不依赖外部 AI API，离线可用（适合移动端场景）。
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

from color_engine import Color, Recipe, RecipeFinder, BASE_PIGMENTS, ColorMixer, pigment_description
from paint_library import find_closest as find_paint_closest


# ──────────────────────────────────────────────
# 命名色库
# ──────────────────────────────────────────────

NAMED_COLORS: Dict[str, Color] = {
    "纯白": Color(255, 255, 255),
    "象牙白": Color(255, 250, 240),
    "米白": Color(245, 245, 220),
    "浅灰": Color(192, 192, 192),
    "中灰": Color(128, 128, 128),
    "深灰": Color(64, 64, 64),
    "纯黑": Color(0, 0, 0),
    "大红": Color(220, 40, 40),
    "朱红": Color(230, 70, 30),
    "绯红": Color(180, 30, 30),
    "粉红": Color(255, 180, 180),
    "橙红": Color(230, 100, 30),
    "橙色": Color(255, 140, 30),
    "橘黄": Color(255, 170, 50),
    "柠檬黄": Color(255, 220, 30),
    "金黄": Color(255, 200, 0),
    "土黄": Color(180, 140, 40),
    "浅黄": Color(255, 240, 150),
    "草绿": Color(80, 180, 50),
    "翠绿": Color(30, 160, 60),
    "墨绿": Color(20, 80, 40),
    "橄榄绿": Color(80, 100, 30),
    "青色": Color(0, 180, 180),
    "天蓝": Color(80, 160, 230),
    "群青": Color(40, 60, 200),
    "深蓝": Color(20, 30, 120),
    "藏青": Color(30, 40, 80),
    "紫色": Color(130, 40, 160),
    "紫红": Color(180, 40, 120),
    "藕色": Color(230, 200, 210),
    "卡其": Color(160, 140, 100),
    "咖啡": Color(120, 70, 30),
    "棕色": Color(150, 90, 50),
    "深棕": Color(80, 50, 20),
    "肉色": Color(230, 190, 160),
    "玫红": Color(220, 60, 100),
}


# ──────────────────────────────────────────────
# 色彩分析
# ──────────────────────────────────────────────

@dataclass
class ColorAnalysis:
    """对单个颜色的完整分析结果。"""
    color: Color
    name: str
    hex_code: str
    rgb: Tuple[int, int, int]
    hsl: Tuple[float, float, float]
    hsv: Tuple[float, float, float]
    cmyk: Tuple[float, float, float, float]
    lab: Tuple[float, float, float]
    temperature: str       # 暖色 / 冷色 / 中性
    brightness: str        # 亮 / 中等 / 暗
    saturation_level: str  # 高 / 中等 / 低
    mood: str              # 色彩心理
    description: str       # 完整文字描述
    paint_matches: List = field(default_factory=list)  # 商用色卡匹配(PaintMatch 列表)


def nearest_named_color(color: Color) -> str:
    """找到最接近的命名色。"""
    best_name = ""
    best_dist = float("inf")
    for name, nc in NAMED_COLORS.items():
        d = color.distance_lab(nc)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


def color_temperature(color: Color) -> str:
    """判断暖色/冷色/中性。"""
    h, s, l = color.hsl
    # 低饱和度视为中性
    if s < 10:
        return "中性"

    # 色相区间：0-60 和 300-360 为暖色，180-240 为冷色
    if (h <= 60 or h >= 300) and s > 15:
        return "暖色"
    elif 180 <= h <= 260 and s > 15:
        return "冷色"
    else:
        # 60-180 和 260-300 为过渡区，根据饱和度和明度判断倾向
        if s > 30 and l > 40:
            return "偏暖"
        elif s > 30:
            return "偏冷"
        return "中性"


def brightness_level(color: Color) -> str:
    """明暗程度。"""
    _, _, l = color.hsl
    if l >= 70:
        return "明亮"
    elif l >= 40:
        return "中等"
    elif l >= 15:
        return "偏暗"
    else:
        return "暗"


def saturation_level(color: Color) -> str:
    """饱和度等级。"""
    _, s, _ = color.hsl
    if s >= 70:
        return "高饱和"
    elif s >= 30:
        return "中等饱和"
    elif s >= 10:
        return "低饱和"
    else:
        return "无彩色"


def color_mood(color: Color) -> str:
    """色彩心理/情感联想。"""
    h, s, l = color.hsl

    if s < 10:
        if l > 80:
            return "纯净、简洁"
        elif l > 40:
            return "沉稳、平和"
        elif l > 15:
            return "低调、内敛"
        else:
            return "神秘、深沉"

    temp = color_temperature(color)
    if "暖" in temp:
        if h <= 30 or h >= 330:
            if s > 60:
                return "热情、活力"
            else:
                return "温暖、舒适"
        elif h <= 60:
            return "欢快、阳光"
        else:
            return "活力、积极"
    elif "冷" in temp:
        if 180 <= h <= 220:
            return "冷静、深邃"
        elif 220 <= h <= 260:
            return "理智、沉稳"
        else:
            return "清新、宁静"
    else:
        return "平衡、自然"


class ColorAdvisor:
    """AI 调色助手核心。"""

    def __init__(self):
        self.recipe_finder = RecipeFinder()

    def analyze(self, color: Color) -> ColorAnalysis:
        """完整分析一个颜色。"""
        h, s, l = color.hsl
        name = nearest_named_color(color)
        temp = color_temperature(color)
        bright = brightness_level(color)
        sat = saturation_level(color)
        mood = color_mood(color)
        paint_matches = sorted(
            find_paint_closest(color, "RAL", top_n=3)
            + find_paint_closest(color, "传统色", top_n=2),
            key=lambda m: m.delta_e,
        )

        desc_parts = [
            f"该颜色为{self._hue_name(h)}系",
            f"{temp}，{bright}，{sat}",
            f"最接近的色彩名称为「{name}」",
        ]
        if paint_matches:
            best = paint_matches[0]
            desc_parts.append(f"最接近的商用色卡为「{best.display}」(ΔE {best.delta_e:.1f})")
        desc_parts.append(f"色彩感受：{mood}")

        return ColorAnalysis(
            color=color,
            name=name,
            hex_code=color.hex,
            rgb=color.rgb,
            hsl=color.hsl,
            hsv=color.hsv,
            cmyk=color.cmyk,
            lab=color.lab,
            temperature=temp,
            brightness=bright,
            saturation_level=sat,
            mood=mood,
            description="，".join(desc_parts) + "。",
            paint_matches=paint_matches,
        )

    def suggest_recipe(self, target: Color, top_n: int = 3) -> List[Recipe]:
        """为目标色生成调色配方。"""
        return self.recipe_finder.find_recipes(target, top_n=top_n)

    def suggest_adjustment(self, current: Color, target: Color) -> str:
        """给出从当前色到目标色的调整建议。"""
        ch, cs, cl = current.hsl
        th, ts, tl = target.hsl

        suggestions = []

        # 明度调整
        dl = tl - cl
        if abs(dl) > 3:
            if dl > 0:
                suggestions.append(f"提亮 {abs(dl):.0f}%：加入钛白")
            else:
                suggestions.append(f"压暗 {abs(dl):.0f}%：加入炭黑或深色颜料")

        # 饱和度调整
        ds = ts - cs
        if abs(ds) > 5:
            hue_name = self._hue_name(th)
            if ds > 0:
                suggestions.append(f"提高饱和度 {abs(ds):.0f}%：加入纯度更高的{hue_name}系颜料")
            else:
                suggestions.append(f"降低饱和度 {abs(ds):.0f}%：加入互补色或灰色")

        # 色相调整
        dh = self._hue_diff(ch, th)
        if abs(dh) > 5:
            if dh > 0:
                suggestions.append(f"色相偏移 {abs(dh):.0f}°（向暖方向）：微调加入{self._hue_name(th)}系颜料")
            else:
                suggestions.append(f"色相偏移 {abs(dh):.0f}°（向冷方向）：微调加入{self._hue_name(th)}系颜料")

        if not suggestions:
            return "当前颜色已非常接近目标，无需大幅调整。"

        return "调整建议：\n" + "\n".join(f"  • {s}" for s in suggestions)

    def suggest_next_pigment(self, current: Color, target: Color) -> Optional[dict]:
        """搜索"下一步加入哪种基色颜料、加多少"的最优单颜料方案。

        在基色库中穷举（颜料 × 比例），按减色混合模型找出 ΔE 最小的方案。
        返回 {"pigment": Pigment, "ratio": 0-1, "mixed": 预计混合色, "delta_e": 预计ΔE}，
        若任何添加都无法改善（ΔE 不下降）返回 None。
        """
        from color_engine import ColorMixer

        pigments = self.recipe_finder.pigments
        cur_d = current.distance(target)
        best = None
        ratios = (0.04, 0.08, 0.12, 0.16, 0.22, 0.30, 0.40, 0.50)
        for p in pigments:
            for w in ratios:
                mixed = ColorMixer.mix_subtractive([current, p.color], [1 - w, w])
                d = mixed.distance(target)
                if best is None or d < best["delta_e"]:
                    best = {"pigment": p, "ratio": w, "mixed": mixed, "delta_e": d}
        if best is None or best["delta_e"] >= cur_d - 0.3:
            return None
        return best

    def suggest_harmony(self, color: Color) -> Dict[str, List[Color]]:
        """根据色彩理论给出和谐配色方案。"""
        h, s, l = color.hsl

        def make(hue_offset, sat_mult=1.0, light_mult=1.0):
            new_h = (h + hue_offset) % 360
            new_s = max(0, min(100, s * sat_mult))
            new_l = max(5, min(95, l * light_mult))
            return Color.from_hsl(new_h, new_s, new_l)

        return {
            "互补色": [make(180)],
            "类似色": [make(-30), make(30)],
            "三角色": [make(120), make(240)],
            "分裂互补": [make(150), make(210)],
            "四角色": [make(90), make(180), make(270)],
            "明暗层次": [Color.from_hsl(h, s, max(15, l - 30)), Color.from_hsl(h, s, min(90, l + 30))],
        }

    def generate_full_report(self, target: Color) -> str:
        """生成完整的调色报告（文字）。"""
        analysis = self.analyze(target)
        recipes = self.suggest_recipe(target, top_n=3)
        harmony = self.suggest_harmony(target)

        lines = []
        lines.append("═══════════════════════════════════════")
        lines.append("          AI 调色分析报告")
        lines.append("═══════════════════════════════════════")
        lines.append("")

        # 色彩信息
        lines.append("【采集颜色信息】")
        lines.append(f"  HEX:  {analysis.hex_code}")
        lines.append(f"  RGB:  {analysis.rgb}")
        lines.append(f"  HSL:  H={analysis.hsl[0]:.1f}°  S={analysis.hsl[1]:.1f}%  L={analysis.hsl[2]:.1f}%")
        lines.append(f"  HSV:  H={analysis.hsv[0]:.1f}°  S={analysis.hsv[1]:.1f}%  V={analysis.hsv[2]:.1f}%")
        lines.append(f"  CMYK: C={analysis.cmyk[0]:.1f}% M={analysis.cmyk[1]:.1f}% Y={analysis.cmyk[2]:.1f}% K={analysis.cmyk[3]:.1f}%")
        lines.append("")

        # 分析
        lines.append("【色彩分析】")
        lines.append(f"  最近命名色: {analysis.name}")
        lines.append(f"  色温: {analysis.temperature}")
        lines.append(f"  明度: {analysis.brightness}")
        lines.append(f"  饱和度: {analysis.saturation_level}")
        lines.append(f"  色彩感受: {analysis.mood}")
        lines.append(f"  {analysis.description}")
        lines.append("")

        # 色卡匹配
        if analysis.paint_matches:
            lines.append("【商用色卡匹配】")
            for m in analysis.paint_matches:
                extra = f"  {m.description}" if m.description else ""
                lines.append(f"  {m.display}  {m.color.hex}  ΔE={m.delta_e:.1f}{extra}")
            lines.append("")

        # 调色配方
        lines.append("【调色配方推荐】")
        for i, recipe in enumerate(recipes, 1):
            lines.append(f"  方案 {i}（{recipe.accuracy}，ΔE={recipe.delta_e:.2f}）:")
            for name, c, ratio in recipe.components:
                desc = pigment_description(name)
                suffix = f"（{desc}）" if desc else ""
                lines.append(f"    {name} {c.hex} → {ratio:.1f}% {suffix}")
            lines.append(f"    混合结果: {recipe.result.hex}")
            lines.append("")

        # 配色建议
        lines.append("【和谐配色方案】")
        for scheme_name, colors in harmony.items():
            color_strs = [f"{c.hex}({nearest_named_color(c)})" for c in colors]
            lines.append(f"  {scheme_name}: {' + '.join(color_strs)}")
        lines.append("")

        lines.append("═══════════════════════════════════════")
        return "\n".join(lines)

    # ── 私有工具 ──

    @staticmethod
    def _hue_name(h: float) -> str:
        if h < 15 or h >= 345:
            return "红"
        elif h < 45:
            return "橙红"
        elif h < 75:
            return "橙黄"
        elif h < 105:
            return "黄绿"
        elif h < 165:
            return "绿"
        elif h < 195:
            return "青绿"
        elif h < 255:
            return "蓝"
        elif h < 285:
            return "蓝紫"
        elif h < 345:
            return "紫红"
        return "红"

    @staticmethod
    def _hue_diff(h1: float, h2: float) -> float:
        """计算色相差值，考虑环形（结果在 -180~180）。"""
        d = h2 - h1
        if d > 180:
            d -= 360
        elif d < -180:
            d += 360
        return d
