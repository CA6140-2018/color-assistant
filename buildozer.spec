[app]

# 应用信息
title = AI调色助手
package.name = colorassistant
package.domain = org.colorassistant

# 版本
version = 1.3.1

# 源代码目录
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,otf,ttf,json,txt

# 排除不需要的文件
source.exclude_dirs = __pycache__, .git, build, dist, bin
source.exclude_patterns = requirements.txt, README.md, *.spec.bak

# 依赖（不包含 opencv 与 numpy，Android 用 Kivy 原生 Camera + 纯 Python 取色，缩短交叉编译）
# filetype 是纯 Python 包，Kivy 的 kivy.core.image 启动时依赖它；
# 我们把 p4a 的 kivy recipe 里 python_depends 清空了（避免 charset-normalizer 编译扩展问题），
# 所以必须在此显式补上 filetype，否则运行时 No module named 'filetype' 直接闪退。
requirements = python3,kivy==2.3.1,filetype==1.2.0

# Android 设置
android.permissions = CAMERA, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
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
# release 产物格式：显式设为 apk（默认是 aab；我们需要可直接安装的 APK，并由 gradle apksigner 做 v2 签名）
android.release_artifact = apk
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
