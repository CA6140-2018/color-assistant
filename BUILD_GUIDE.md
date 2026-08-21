# Android APK 打包指南

本项目已配置好 GitHub Actions 自动构建。你只需将代码推送到 GitHub，
云端会自动编译生成 APK，下载安装即可。

---

## 第一步：安装 Git

1. 打开 https://git-scm.com/download/win
2. 下载 "64-bit Git for Windows Setup" 
3. 运行安装程序，一路点「Next」即可（默认选项就行）
4. 安装完成后，关闭并重新打开终端

验证安装成功：
```bash
git --version
```

## 第二步：注册 GitHub 账号（如已有账号可跳过）

1. 打开 https://github.com
2. 点击 "Sign up"，按提示注册
3. 注册完成后验证邮箱

## 第三步：创建 GitHub 仓库

1. 登录 GitHub，点击右上角 **+** → **New repository**
2. 填写信息：
   - Repository name: `color-assistant`
   - Description: `AI 调色助手`
   - 选择 **Private**（私有）或 **Public**（公开）
   - **不要**勾选 "Add a README file"
   - **不要**选择 .gitignore 和 license
3. 点击 **Create repository**

## 第四步：推送代码到 GitHub

打开终端（PowerShell 或 CMD），执行以下命令：

```bash
# 进入项目目录
cd "C:\Users\薄荷威士忌\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a8851a581af227195a2bab6"

# 初始化 Git
git init
git add .
git commit -m "Initial commit: AI 调色助手"

# 设置主分支名
git branch -M main

# 关联远程仓库（把 YOUR_USERNAME 替换为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/color-assistant.git

# 推送
git push -u origin main
```

推送时会弹出 GitHub 登录窗口，输入用户名和密码（或 Token）即可。

## 第五步：等待自动构建

1. 推送完成后，打开你的 GitHub 仓库页面
2. 点击顶部 **Actions** 标签页
3. 你会看到一个名为 "Build Android APK" 的工作流正在运行
4. 首次构建约需 **20-40 分钟**（需要下载 Android SDK 和编译依赖）
5. 构建状态：
   - 黄色圆圈 🟡 = 正在构建
   - 绿色对勾 ✅ = 构建成功
   - 红色叉号 ❌ = 构建失败

## 第六步：下载 APK

1. 构建成功后，点击那条构建记录
2. 在页面底部找到 **Artifacts** 区域
3. 点击 `colorassistant-debug-apk` 下载
4. 下载的是一个 ZIP 文件，解压后得到 `colorassistant-debug.apk`
5. 将 APK 传到手机上安装

## 第七步：安装到手机

1. 将 APK 文件传到手机（微信/QQ/USB/邮件均可）
2. 在手机上点击 APK 文件安装
3. 如果提示"未知来源"，在设置中允许安装
4. 打开应用，授予摄像头权限即可使用

---

## 常见问题

### Q: 构建失败了怎么办？
A: 点击失败的构建记录，查看日志中的红色错误信息。
   常见原因：网络超时（重新触发构建）、依赖冲突。

### Q: 如何重新触发构建？
A: 在 Actions 页面，选择 "Build Android APK" → "Run workflow" → "Run workflow"

### Q: 修改代码后如何重新构建？
A: 重新 commit 和 push 即可，Actions 会自动触发新构建：
```bash
git add .
git commit -m "update"
git push
```

### Q: 中文显示乱码怎么办？
A: 应用会自动检测系统字体。如果仍有问题，
   将一个中文 .ttf/.otf 字体文件放入 `fonts/` 目录，
   命名为 `NotoSansSC-Regular.otf`，然后重新推送。

### Q: 构建太慢？
A: 首次构建最慢（需下载 SDK）。后续构建有缓存，约 5-10 分钟。
```
