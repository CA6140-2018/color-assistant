"""给 p4a sdl2 bootstrap 的 PythonActivity.java 注入启动诊断标记。

背景：真机闪退时 boot.txt / crash_log.txt 均为 0 字节，说明崩溃发生在
Python 解释器启动之前（Java/原生层），Python 侧任何日志代码都来不及执行。

本脚本在 Java 启动链路的每个关键阶段写入标记文件（应用外部专属目录，
用户可直接查看）：
  - java_boot.txt : 启动阶段标记，每行带 APK 版本号，可确认实际运行的版本
  - java_crash.txt: Java 未捕获异常堆栈（安装全局钩子 + 解包 try/catch）

标记点：
  j1-onCreate             Activity 创建（最早能落盘的位置）
  j2-unpack-begin         开始解包 private.tar / pybundle
  j3-private-tar-done     private.tar 解包完成
  j4-pybundle-done        Python 标准库解包完成
  j5-postexec             解包任务收尾（准备启动原生线程）
  j6-before-native-resume 即将启动原生线程（此后进入 SDL/Python 原生初始化）
  j7-native-resume-called 原生线程已启动

用法（CI）:  python3 tools/patch_p4a_diagnostics.py
本地测试:    python3 tools/patch_p4a_diagnostics.py <PythonActivity.java 路径>
"""
import os
import sys

DEFAULT_BASES = [
    "/tmp/p4a/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java",
    "/tmp/p4a/pythonforandroid/bootstraps/sdl2/build/src/org/kivy/android/PythonActivity.java",
]

HELPERS = '''
    // ---- boot diagnostics (v1.2.5): java_boot.txt / java_crash.txt ----
    private String jversion() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    private void jmark(String stage) {
        try {
            File d = getExternalFilesDir(null);
            if (d == null) return;
            FileWriter fw = new FileWriter(new File(d, "java_boot.txt"), true);
            fw.write("v" + jversion() + " " + stage + " " + System.currentTimeMillis() + "\\n");
            fw.flush();
            fw.close();
        } catch (Exception e) { }
    }

    private void jcrash(String where, Throwable e) {
        try {
            File d = getExternalFilesDir(null);
            if (d == null) return;
            FileWriter fw = new FileWriter(new File(d, "java_crash.txt"), true);
            java.io.PrintWriter pw = new java.io.PrintWriter(fw);
            pw.write("----- JAVA CRASH v" + jversion() + " at " + where + " -----\\n");
            e.printStackTrace(pw);
            pw.write("\\n");
            pw.flush();
            fw.close();
        } catch (Exception ignored) { }
    }

    private void installJavaCrashHandler() {
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {
            @Override
            public void uncaughtException(Thread t, Throwable e) {
                jcrash("uncaught-" + t.getName(), e);
                if (prev != null) prev.uncaughtException(t, e);
            }
        });
    }
'''

REPLACEMENTS = [
    # 注入辅助方法（挂在字段声明后）
    (
        "    private PowerManager.WakeLock mWakeLock = null;",
        "    private PowerManager.WakeLock mWakeLock = null;\n" + HELPERS,
    ),
    # onCreate 最早期：标记 + 安装 Java 崩溃钩子
    (
        '        Log.v(TAG, "PythonActivity onCreate running");',
        '        Log.v(TAG, "PythonActivity onCreate running");\n'
        '        jmark("j1-onCreate");\n'
        '        installJavaCrashHandler();',
    ),
    # 解包线程：进入时标记 + try 包裹整个解包过程
    (
        "            File app_root_file = new File(params[0]);",
        '            mActivity.jmark("j2-unpack-begin");\n'
        "            try {\n"
        "            File app_root_file = new File(params[0]);",
    ),
    # private.tar 解包完成
    (
        'PythonUtil.unpackAsset(mActivity, "private", app_root_file, true);',
        'PythonUtil.unpackAsset(mActivity, "private", app_root_file, true);\n'
        '            mActivity.jmark("j3-private-tar-done");',
    ),
    # pybundle 解包完成 + catch 住解包异常写盘
    (
        "                    app_root_file,\n"
        "                    false);\n"
        "            return null;",
        "                    app_root_file,\n"
        "                    false);\n"
        '            mActivity.jmark("j4-pybundle-done");\n'
        "            } catch (Throwable e) {\n"
        '                mActivity.jcrash("unpack-failed", e);\n'
        "                throw new RuntimeException(e);\n"
        "            }\n"
        "            return null;",
    ),
    # 解包收尾
    (
        "            mActivity.finishLoad();",
        '            mActivity.jmark("j5-postexec");\n'
        "            mActivity.finishLoad();",
    ),
    # 原生线程启动前后
    (
        "                mActivity.resumeNativeThread();",
        '                mActivity.jmark("j6-before-native-resume");\n'
        "                mActivity.resumeNativeThread();\n"
        '                mActivity.jmark("j7-native-resume-called");',
    ),
]


def apply(path):
    with open(path, encoding="utf-8") as f:
        s = f.read()
    if "jmark(" in s:
        print("already patched: %s" % path)
        return False
    for old, new in REPLACEMENTS:
        n = s.count(old)
        if n != 1:
            raise SystemExit(
                "anchor count=%d (expect 1) in %s: %r" % (n, path, old[:70])
            )
        s = s.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    print("patched OK: %s" % path)
    return True


def main():
    candidates = sys.argv[1:] or DEFAULT_BASES
    target = next((p for p in candidates if os.path.isfile(p)), None)
    if not target:
        raise SystemExit("PythonActivity.java not found: %s" % candidates)
    apply(target)


if __name__ == "__main__":
    main()
