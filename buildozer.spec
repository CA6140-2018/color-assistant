[app]

# 应用信息
title = AI调色助手
package.name = colorassistant
package.domain = org.colorassistant

# 版本
version = 1.0.0

# 源代码目录
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,otf,ttf,json,txt

# 排除不需要的文件
source.exclude_dirs = __pycache__, .git, build, dist, bin
source.exclude_patterns = requirements.txt, README.md, *.spec.bak

# 依赖（不包含 opencv，Android 用 Kivy 原生 Camera）
requirements = python3,kivy==2.3.1,numpy

# Android 设置
android.permissions = CAMERA
android.api = 33
android.minapi = 24
android.archs = arm64-v8a

# 全屏 + 自动旋转
fullscreen = 1
orientation = all

# 日志级别（debug 构建用 2，release 用 1）
log_level = 2

# 构建类型
android.debug_artifact = bin/colorassistant-debug.apk

# p4a 设置
p4a.branch = stable

# 图标和启动画面（使用默认，可选替换）
#android.icon = icon.png
#android.presplash = presplash.png

# 深度链接（可选）
#android.allow_backup = True

[buildozer]
# 构建目录
build_dir = build

# 日志
log_level = 2
warn_on_root = 0
