"""
崩溃日志捕获：把未捕获异常写入手机可访问文件，便于真机定位闪退。

Android 上普通 App 无法读取其他应用日志（Android 11+），Logcat Read 等工具
拿不到我们应用的崩溃堆栈。此模块在应用内安装全局 hook，闪退前把 traceback
写入外部存储，用户可自行打开读取或发送出来。

写入路径优先级（写到第一个成功的位置，方便用户从文件管理器查看）：
  1. 应用专属外部目录 getExternalFilesDir()  —— 无需权限必然可写。
     Android 11+ 分区存储下必须用它（/sdcard 根目录应用无权写入）。
     用户可在文件管理器『内部存储/Android/data/<包名>/files/』看到。
  2. Android 常见外部存储根（Download/根目录，作为附加尝试）
  3. 应用私有目录（保底）
"""

import os
import sys
import traceback
import time


def _get_android_dir():
    """返回应用专属外部目录的绝对路径（无需任何权限，必然可写）。"""
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        files_dir = activity.getExternalFilesDir(None)
        if files_dir is not None:
            return os.path.join(files_dir.getAbsolutePath(), "crash_log.txt")
    except Exception:
        pass
    return None


def _candidate_paths():
    paths = []

    # 1) 应用专属外部目录（首选）
    d = _get_android_dir()
    if d:
        paths.append(d)

    # 2) Android 常见外部存储根（仅作为附加尝试，分区存储下可能失败）
    for base in ("/sdcard", "/storage/emulated/0"):
        if os.path.isdir(base):
            dl = os.path.join(base, "Download")
            if os.path.isdir(dl):
                paths.append(os.path.join(dl, "crash_log.txt"))
            paths.append(os.path.join(base, "crash_log.txt"))

    # 3) 应用私有目录（保底）
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None and app.user_data_dir:
            paths.append(os.path.join(app.user_data_dir, "crash_log.txt"))
    except Exception:
        pass

    # 4) 应用源码目录（绝对保底，Android 上也可写）
    try:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(src_dir, "crash_log.txt"))
    except Exception:
        pass

    return paths


def pop_unshown_crash():
    """读出尚未展示过的最近一次崩溃堆栈；没有则返回 None。

    读到后在日志尾部追加 SHOWN 标记，避免下次启动重复弹出。
    """
    for p in _candidate_paths():
        try:
            if not os.path.isfile(p):
                continue
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            idx = text.rfind("----- SHOWN")
            recent = text[idx:] if idx >= 0 else text
            c = recent.rfind("----- CRASH")
            if c < 0:
                continue
            seg = recent[c:].strip()
            if len(seg) < 20:
                continue
            with open(p, "a", encoding="utf-8") as f:
                f.write("\n----- SHOWN %s -----\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            return seg[:4000]
        except Exception:
            continue
    return None


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