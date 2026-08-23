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

# 依赖（不包含 opencv 与 numpy，Android 用 Kivy 原生 Camera + 纯 Python 取色，缩短交叉编译）
requirements = python3,kivy==2.3.1

# Android 设置
android.permissions = CAMERA
android.api = 33
android.minapi = 24
android.archs = arm64-v8a

# 固定 NDK 版本（国内镜像脚本按此版本预下载），避免每次联网去 Google 找版本
android.ndk_version = 25c
# 自动接受 SDK 许可，避免交互卡住
android.accept_sdk_license = True

# 全屏 + 自动旋转
fullscreen = 1
orientation = all

# 日志级别（debug 构建用 2，release 用 1）
log_level = 2

# 构建类型
# 注：此处不再设置 android.debug_artifact —— 该键在当前 buildozer+p4a 下会把产物路径误当作
# p4a 子命令传入导致 "invalid choice"；产物命名沿用默认，上传步骤用 bin/*.apk 通配。

# p4a 设置（使用 develop 分支以支持 AAB）
p4a.branch = develop
# 使用 CI 预置的 p4a 源码（已改 kivy recipe 清空 python_depends，见 workflow），buildozer 不再自行拉取
p4a.source_dir = /tmp/p4a

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
