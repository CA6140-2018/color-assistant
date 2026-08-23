"""
崩溃日志捕获：把未捕获异常写入手机可访问文件，便于真机定位闪退。

Android 上普通 App 无法读取其他应用日志（Android 11+），Logcat Read 等工具
拿不到我们应用的崩溃堆栈。此模块在应用内安装全局 hook，闪退前把 traceback
写入外部存储，用户可自行打开读取或发送出来。

写入路径优先级（写到第一个成功的位置，方便用户从文件管理器查看）：
  1. /sdcard/Download/crash_log.txt
  2. /sdcard/crash_log.txt
  3. android App 私有外部目录
  4. 应用私有目录（保底）
"""

import os
import sys
import traceback
import time


def _candidate_paths():
    paths = []

    # Android 常见外部存储根
    for base in ("/sdcard", "/storage/emulated/0"):
        if os.path.isdir(base):
            dl = os.path.join(base, "Download")
            if os.path.isdir(dl):
                paths.append(os.path.join(dl, "crash_log.txt"))
            paths.append(os.path.join(base, "crash_log.txt"))

    # Android 应用专属外部目录（无需额外权限，文件管理器可见度因机型而异）
    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass
            Environment = autoclass("android.os.Environment")
            ext = Environment.getExternalStorageDirectory().getAbsolutePath()
            if os.path.isdir(ext):
                paths.append(os.path.join(ext, "crash_log.txt"))
    except Exception:
        pass

    # 应用私有外部 / 私有数据目录（保底）
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None and app.user_data_dir:
            paths.append(os.path.join(app.user_data_dir, "crash_log.txt"))
    except Exception:
        pass

    return paths


def _write(path, text):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False


def write_crash(text):
    """尝试写入所有候选路径，任一成功即返回 True。"""
    for p in _candidate_paths():
        if _write(p, text):
            return True
    # 兜底：相对当前目录
    try:
        with open("crash_log.txt", "a", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False
    return False


def _crash_file():
    for p in _candidate_paths():
        if os.path.isfile(p):
            return p
    return None


def install() -> str:
    """安装全局崩溃捕获。返回日志文件路径提示（用于界面显示）。"""
    # 记录启动
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    write_crash(
        "\n===== APP START %s =====\n"
        "python=%s kivy=%s android=%s\n"
        % (
            ts,
            sys.version.split()[0],
            getattr(sys, "kivy_version", "n/a"),
            "android" if getattr(sys, "platform", "") == "android" else "desktop",
        )
    )

    def _hook(exc_type, exc_value, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        write_crash("\n----- CRASH %s -----\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), tb))

    sys.excepthook = _hook

    # faulthandler 捕获低层 Python 崩溃（如信号级异常）
    if hasattr(sys, "implementation") and not getattr(sys, "android_exported", False):
        pass
    try:
        import faulthandler
        for p in _candidate_paths():
            try:
                faulthandler.enable(file=open(p + ".fth", "a"))
                break
            except Exception:
                continue
    except Exception:
        pass

    return _crash_file() or "crash_log.txt"


__all__ = ["install", "write_crash"]