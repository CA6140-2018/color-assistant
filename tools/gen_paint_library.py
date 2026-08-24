# -*- coding: utf-8 -*-
"""从下载的原始数据生成 paint_library.py。

数据来源:
  1. RAL Classic RGB 数据(216色): https://github.com/iw365/RAL-pallete-data (GPL-3.0)
     原始文件: ral_classic.json (ral-classic-uncategorised-rounded.json)
  2. RAL 官方中文色名: 劳尔中国官网 http://ralcolours.com.cn/about/allcolor/allcolorth/
  3. 中国传统色(158色): https://github.com/longtian/ancient-chinese-color (MIT)
     原始文件: ancient_colors.json (data.json)

用法:
    python tools/gen_paint_library.py <ral_classic.json> <ancient_colors.json> > paint_library.py
"""

import json
import sys

# RAL 官方中文色名 (劳尔中国官网)
RAL_CN_NAMES = {
    "1000": "绿米色", "1001": "米黄色", "1002": "沙黄色", "1003": "信号黄",
    "1004": "金黄色", "1005": "蜜黄色", "1006": "玉米黄", "1007": "水仙黄",
    "1011": "棕米色", "1012": "柠檬黄", "1013": "牡蛎白", "1014": "象牙色",
    "1015": "浅象牙色", "1016": "硫磺色", "1017": "橘黄色", "1018": "锌黄色",
    "1019": "灰米色", "1020": "橄榄黄", "1021": "油菜黄", "1023": "交通黄",
    "1024": "赭黄色", "1026": "荧光黄", "1027": "咖喱色", "1028": "瓜黄色",
    "1032": "金雀花黄", "1033": "大丽花黄", "1034": "粉彩黄", "1035": "珍珠米",
    "1036": "珍珠金", "1037": "太阳黄",
    "2000": "黄橙色", "2001": "红橙色", "2002": "朱红色", "2003": "粉彩橙",
    "2004": "纯橙色", "2005": "荧光橙", "2007": "荧光亮橙", "2008": "亮红橙",
    "2009": "交通橙", "2010": "信号橙", "2011": "深橙色", "2012": "鲑鱼橙",
    "2013": "珍珠橙", "2017": "RAL橙",
    "3000": "火焰红", "3001": "信号红", "3002": "胭脂红", "3003": "宝石红",
    "3004": "紫红色", "3005": "酒红色", "3007": "黑红色", "3009": "氧化红",
    "3011": "棕红色", "3012": "米红色", "3013": "番茄红", "3014": "古旧粉",
    "3015": "淡粉色", "3016": "珊瑚红", "3017": "玫瑰色", "3018": "草莓红",
    "3020": "交通红", "3022": "鲑鱼粉", "3024": "荧光红", "3026": "荧光亮红",
    "3027": "树莓红", "3028": "纯红色", "3031": "东方红", "3032": "珍珠宝石红",
    "3033": "珍珠粉",
    "4001": "红丁香紫", "4002": "红紫色", "4003": "石南紫", "4004": "酒红紫",
    "4005": "蓝丁香紫", "4006": "交通紫", "4007": "罗兰紫", "4008": "信号紫",
    "4009": "粉彩紫", "4010": "电信紫", "4011": "珍珠紫", "4012": "珍珠黑莓紫",
    "5000": "紫蓝色", "5001": "绿蓝色", "5002": "群青蓝", "5003": "宝石蓝",
    "5004": "黑蓝色", "5005": "信号蓝", "5007": "亮蓝色", "5008": "灰蓝色",
    "5009": "天青蓝", "5010": "龙胆蓝", "5011": "钢蓝色", "5012": "淡蓝色",
    "5013": "钴蓝色", "5014": "鸽蓝色", "5015": "天空蓝", "5017": "交通蓝",
    "5018": "绿松石蓝", "5019": "卡普里蓝", "5020": "海洋蓝", "5021": "水蓝色",
    "5022": "夜蓝色", "5023": "深邃蓝", "5024": "粉彩蓝", "5025": "珍珠龙胆蓝",
    "5026": "珍珠夜蓝",
    "6000": "铜绿色", "6001": "翠绿色", "6002": "叶绿色", "6003": "橄榄绿",
    "6004": "蓝绿色", "6005": "苔藓绿", "6006": "灰橄榄绿", "6007": "瓶绿色",
    "6008": "褐绿色", "6009": "冷杉绿", "6010": "草绿色", "6011": "灰绿色",
    "6012": "墨绿色", "6013": "芦苇绿", "6014": "黄橄榄绿", "6015": "黑橄榄绿",
    "6016": "松石绿", "6017": "五月绿", "6018": "黄绿色", "6019": "粉彩绿",
    "6020": "铬绿色", "6021": "苍白绿", "6022": "橄榄土褐色", "6024": "交通绿",
    "6025": "蕨绿色", "6026": "蛋白石绿", "6027": "淡绿色", "6028": "松绿色",
    "6029": "薄荷绿", "6032": "信号绿", "6033": "薄荷蓝绿", "6034": "粉彩蓝绿",
    "6035": "珍珠绿", "6036": "珍珠蛋白石绿", "6037": "纯绿色", "6038": "荧光绿",
    "6039": "纤维绿",
    "7000": "松鼠灰", "7001": "银灰色", "7002": "橄榄灰", "7003": "苔藓灰",
    "7004": "信号灰", "7005": "鼠灰色", "7006": "米灰色", "7008": "卡其灰",
    "7009": "绿灰色", "7010": "油布灰", "7011": "铁灰色", "7012": "玄武岩灰",
    "7013": "棕灰色", "7015": "板岩灰", "7016": "煤灰色", "7021": "黑灰色",
    "7022": "暗灰色", "7023": "混凝土灰", "7024": "石墨灰", "7026": "花岗岩灰",
    "7030": "石灰色", "7031": "蓝灰色", "7032": "卵石灰", "7033": "水泥灰",
    "7034": "黄灰色", "7035": "淡灰色", "7036": "铂金灰", "7037": "土灰色",
    "7038": "玛瑙灰", "7039": "石英灰", "7040": "窗灰色", "7042": "交通灰A",
    "7043": "交通灰B", "7044": "丝灰色", "7045": "电信灰1", "7046": "电信灰2",
    "7047": "电视灰4", "7048": "珍珠鼠灰",
    "8000": "绿棕色", "8001": "赭石棕", "8002": "信号棕", "8003": "泥土棕",
    "8004": "铜棕色", "8007": "鹿棕色", "8008": "橄榄棕", "8011": "深棕色",
    "8012": "红棕色", "8014": "乌贼棕", "8015": "粟棕色", "8016": "红木棕",
    "8017": "巧克力棕", "8019": "灰棕色", "8022": "黑棕色", "8023": "橙棕色",
    "8024": "米黄棕", "8025": "苍白棕", "8028": "大地棕", "8029": "珍珠铜棕",
    "9001": "奶油色", "9002": "灰白色", "9003": "信号白", "9004": "信号黑",
    "9005": "墨黑色", "9006": "白铝色", "9007": "灰铝色", "9010": "纯白色",
    "9011": "石墨黑", "9012": "净室白", "9016": "交通白", "9017": "交通黑",
    "9018": "草纸白", "9022": "珍珠浅灰", "9023": "珍珠深灰",
}

HEADER = '''# -*- coding: utf-8 -*-
"""
商用色卡库: RAL 经典色卡 + 中国传统色。

用于把摄像头采集的颜色匹配到真实商用涂料色号(如 RAL 3020 交通红)，
比内置的 36 个常用色名覆盖面广得多(共 @RAL_COUNT@+@TRAD_COUNT@ 色)。

数据来源:
  - RAL Classic 216 色 RGB: github.com/iw365/RAL-pallete-data (GPL-3.0)
  - RAL 中文色名: 劳尔中国官网 ralcolours.com.cn
  - 中国传统色 @TRAD_COUNT@ 色: github.com/longtian/ancient-chinese-color (MIT)

本文件由 tools/gen_paint_library.py 生成，请勿手改。
"""

from typing import List, Optional

from color_engine import Color


class PaintMatch:
    """一个色卡匹配结果。"""

    __slots__ = ("library", "name", "code", "en_name", "color", "delta_e", "description")

    def __init__(self, library, name, code, en_name, color, delta_e, description=""):
        self.library = library      # "RAL" / "传统色"
        self.name = name            # 中文色名
        self.code = code            # 色号(RAL) / 名称(传统色)
        self.en_name = en_name      # 英文名(可空)
        self.color = color          # Color
        self.delta_e = delta_e      # 与目标色的色差
        self.description = description  # 释义(传统色)

    @property
    def display(self):
        """如 "RAL 3020 交通红"。"""
        if self.library == "RAL":
            return f"RAL {self.code} {self.name}"
        return f"传统色·{self.name}"


# (色号, 中文名, 英文名, r, g, b)
RAL_CLASSIC = [
'''

TRAD_HEADER = '''
# (名称, 释义, r, g, b)
TRADITIONAL_CN = [
'''

FOOTER = '''

def _build():
    ral = [dict(library="RAL", name=cn, code=code, en_name=en,
                color=Color(r, g, b)) for code, cn, en, r, g, b in RAL_CLASSIC]
    trad = [dict(library="传统色", name=name, code=name, en_name="",
                 color=Color(r, g, b), description=desc)
            for name, desc, r, g, b in TRADITIONAL_CN]
    return ral, trad


_RAL_COLORS, _TRAD_COLORS = _build()


def find_closest(color: Color, library: str = "all", top_n: int = 3) -> List[PaintMatch]:
    """在色卡库中找最接近的颜色。

    library: "RAL" / "传统色" / "all"（all 时两库各自取前 top_n 合并按 ΔE 排序）
    """
    pools = []
    if library in ("RAL", "all"):
        pools.append(_RAL_COLORS)
    if library in ("传统色", "all"):
        pools.append(_TRAD_COLORS)

    matches = []
    for pool in pools:
        scored = []
        for item in pool:
            d = color.distance_lab(item["color"])
            scored.append((d, item))
        scored.sort(key=lambda x: x[0])
        for d, item in scored[:top_n]:
            matches.append(PaintMatch(
                library=item["library"], name=item["name"], code=item["code"],
                en_name=item.get("en_name", ""), color=item["color"], delta_e=d,
                description=item.get("description", ""),
            ))
    if library == "all":
        matches.sort(key=lambda m: m.delta_e)
        # 去掉两库中重复度极高的项（同名或 ΔE 几乎相同）
        seen = set()
        uniq = []
        for m in matches:
            key = (m.library, m.code)
            if key not in seen:
                seen.add(key)
                uniq.append(m)
        matches = uniq
    return matches


def best_match(color: Color) -> Optional[PaintMatch]:
    """全库最优匹配。"""
    ms = find_closest(color, "all", top_n=1)
    return ms[0] if ms else None
'''


def main():
    ral_path, trad_path = sys.argv[1], sys.argv[2]

    with open(ral_path, "r", encoding="utf-8") as f:
        ral_data = json.load(f)

    ral_rows = []
    missing_cn = []
    for code in sorted(ral_data.keys()):
        item = ral_data[code]
        en = item["name"]
        rgb = item["rgb"]
        cn = RAL_CN_NAMES.get(code)
        if cn is None:
            missing_cn.append(code)
            cn = en
        ral_rows.append((code, cn, en, rgb["r"], rgb["g"], rgb["b"]))

    with open(trad_path, "r", encoding="utf-8") as f:
        trad_data = json.load(f)

    trad_rows = []
    for item in trad_data:
        rgb_str = item["RGB"].replace("​", "").replace("\u200b", "")
        r, g, b = [int(x) for x in rgb_str.split(",")]
        desc = item.get("description", "")
        desc = " ".join(desc.split())
        # 释义去掉前缀"名称："
        if desc.startswith(item["name"] + "："):
            desc = desc[len(item["name"]) + 1:]
        trad_rows.append((item["name"], desc, r, g, b))

    out = [HEADER.replace("@RAL_COUNT@", str(len(ral_rows))).replace("@TRAD_COUNT@", str(len(trad_rows)))]
    for code, cn, en, r, g, b in ral_rows:
        out.append(f'    ("{code}", "{cn}", "{en}", {r}, {g}, {b}),\n')
    out.append("]\n")
    out.append(TRAD_HEADER)
    for name, desc, r, g, b in trad_rows:
        desc_escaped = desc.replace("\\", "\\\\").replace('"', '\\"')
        out.append(f'    ("{name}", "{desc_escaped}", {r}, {g}, {b}),\n')
    out.append("]\n")
    out.append(FOOTER)

    sys.stdout.write("".join(out))
    if missing_cn:
        sys.stderr.write(f"警告: {len(missing_cn)} 个 RAL 色无中文名: {missing_cn}\n")


if __name__ == "__main__":
    main()
