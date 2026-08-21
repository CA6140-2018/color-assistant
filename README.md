# AI 调色助手

基于摄像头采集目标颜色，通过 AI 算法给出调色配方建议的桌面/移动应用。

## 功能

- **摄像头实时取色**：点击画面任意位置采集颜色，或提取画面主色
- **色彩分析**：自动识别色温（暖/冷/中性）、明度、饱和度、色彩感受
- **调色配方推荐**：基于减色混合模型，计算达到目标色所需的基色颜料及配比
- **色差评估**：使用 CIEDE2000 色差公式评估配方精度
- **和谐配色方案**：根据色彩理论推荐互补色、类似色、三角色等
- **完整调色报告**：一键生成包含色值、分析、配方、配色的文字报告

## 技术栈

- **Kivy** — 跨平台 GUI 框架（可打包 Android APK）
- **OpenCV** — 摄像头采集与图像处理
- **NumPy** — 颜色计算与混合算法
- 纯 Python 实现，无外部 AI API 依赖，离线可用

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 使用方法

1. 启动后摄像头自动打开，显示实时画面
2. **点击画面**任意位置 → 采集该处颜色，右侧显示分析结果
3. **中心取色**按钮 → 采集画面正中央颜色
4. **提取主色**按钮 → K-means 提取画面主色调
5. **完整报告**按钮 → 生成文字版调色报告

## 文件结构

```
├── main.py              # Kivy UI + OpenCV 摄像头
├── color_engine.py      # 颜色空间转换、混合模型、配方搜索
├── ai_assistant.py      # 色彩分析、命名、配色建议
├── requirements.txt     # Python 依赖
└── README.md
```

## 核心算法说明

### 减色混合模型

颜料混合遵循减色法（吸光叠加），本系统使用加权几何均值：

```
mixed_channel = ∏(channel_i ^ weight_i)
```

在 sRGB 线性空间计算，物理含义为各颜料按权重吸收对应波长光线后的剩余反射率。

### 配方搜索

在 8 种基础颜料（钛白、炭黑、大红、柠檬黄、群青、翠绿、紫色、橙色）中：
1. 检查单色直接匹配
2. 遍历所有二色组合，网格搜索最佳比例
3. 遍历三色组合，二维网格搜索

以 CIEDE2000 色差最小化为目标，返回前 3 个最优配方。

### 打包 Android

```bash
pip install buildozer
buildozer init
# 编辑 buildozer.spec，设置 requirements = kivy,opencv-python,numpy
buildozer android debug
```

> 注意：buildozer 需要 Linux 环境（WSL 也可），Windows 原生不支持。
