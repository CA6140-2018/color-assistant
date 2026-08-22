#!/bin/bash
set -ex

# Ensure valid working directory
cd /root/workspace/ca6140/color-assistant 2>/dev/null || cd /workspace 2>/dev/null || cd /home 2>/dev/null || cd /tmp
WORKDIR=$(pwd)
echo "=== Build started at $(date) ==="
echo "=== Working directory: $WORKDIR ==="

# Create bin dir for log (so artifact always has something)
mkdir -p "$WORKDIR/bin"

echo "=== System info ==="
df -h || true
free -h || true
ls -la || true

# Create man dir (needed for JDK)
mkdir -p /usr/share/man/man1/

# Install dependencies
apt-get update
apt-get install -y --fix-broken autoconf automake libtool pkg-config cmake libssl-dev libffi-dev libltdl-dev libncurses5-dev openjdk-17-jdk ccache zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget unzip git curl ca-certificates

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH:$HOME/.local/bin"

# Add swap space
echo "=== Adding swap space ==="
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096 || true
  chmod 600 /swapfile 2>/dev/null || true
  mkswap /swapfile 2>/dev/null || true
  swapon /swapfile 2>/dev/null || true
fi
free -h || true

# GitHub mirror for git (只有 git 走这里；p4a 源码下载是 Python urlretrieve，需要下面的预下载)
git config --global url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"
git config --global url."https://ghfast.top/https://github.com/".insteadOf "git@github.com:"
git config --global http.postBuffer 1048576000
git config --global https.postBuffer 1048576000

# PyPI 国内镜像，保证 kivy 等 pip 包下载稳定
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || true

# Install buildozer
pip install --user buildozer 'cython<3.0'

# Download Chinese font
mkdir -p "$WORKDIR/fonts"
curl -sL -o "$WORKDIR/fonts/NotoSansSC-Regular.otf" 'https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf' || true

# ─────────────────────────────────────────────────────────────
# 预下载 p4a 依赖源包进缓存目录，让 p4a 跳过不稳定的 GitHub 下载。
# p4a 判定缓存：packages 目录下存在同名文件 + 对应 .mark- 标记文件。
# 以下 URL/版本与 p4a (develop 分支, 2026-08) 构建所用的完全一致。
# ─────────────────────────────────────────────────────────────
PACKAGES="$HOME/.buildozer/android/packages"
mkdir -p "$PACKAGES"

GH_MIRRORS=(
  "https://ghfast.top/"
  "https://mirror.ghproxy.com/"
  "https://gh-proxy.com/"
  "https://ghproxy.net/"
  ""
)

seed_source() {
  local name="$1" base="$2" origin="$3"
  if [ -f "$PACKAGES/$base" ] && [ -f "$PACKAGES/.mark-$base" ]; then
    echo "SEED cached: $name ($base)"
    return 0
  fi
  rm -f "$PACKAGES/.mark-$base" "$PACKAGES/$base"
  for m in "${GH_MIRRORS[@]}"; do
    echo "SEED downloading $name from $m$origin"
    if curl -fL --retry 3 --connect-timeout 20 --max-time 300 -o "$PACKAGES/$base" "$m$origin"; then
      touch "$PACKAGES/.mark-$base"
      echo "SEED success: $name ($base)"
      return 0
    fi
    rm -f "$PACKAGES/$base"
  done
  echo "SEED failed: $name (将由 p4a 自身重试下载)"
  return 1
}

seed_source hostpython3 "v3.14.2.tar.gz" "https://github.com/python/cpython/archive/refs/tags/v3.14.2.tar.gz" || true
seed_source jpeg    "2.0.1.tar.gz"            "https://github.com/libjpeg-turbo/libjpeg-turbo/archive/2.0.1.tar.gz" || true
seed_source libffi  "v3.4.2.tar.gz"           "https://github.com/libffi/libffi/archive/v3.4.2.tar.gz" || true
seed_source png     "v1.6.37.zip"             "https://github.com/glennrp/libpng/archive/v1.6.37.zip" || true
seed_source sdl2_image "SDL2_image-2.8.2.tar.gz"  "https://github.com/libsdl-org/SDL_image/releases/download/release-2.8.2/SDL2_image-2.8.2.tar.gz" || true
seed_source sdl2_mixer "SDL2_mixer-2.6.3.tar.gz"  "https://github.com/libsdl-org/SDL_mixer/releases/download/release-2.6.3/SDL2_mixer-2.6.3.tar.gz" || true
seed_source sdl2    "SDL2-2.30.11.tar.gz"     "https://github.com/libsdl-org/SDL/releases/download/release-2.30.11/SDL2-2.30.11.tar.gz" || true
seed_source sdl2_ttf "SDL2_ttf-2.22.0.tar.gz" "https://github.com/libsdl-org/SDL_ttf/releases/download/release-2.22.0/SDL2_ttf-2.22.0.tar.gz" || true
seed_source libthorvg "v1.0.5.tar.gz"         "https://github.com/thorvg/thorvg/archive/refs/tags/v1.0.5.tar.gz" || true

echo "=== Packages cache contents: ==="
ls -la "$PACKAGES" || true

# ─────────────────────────────────────────────────────────────
# 构建（最多重试 2 次：已下载/已编译内容在 VM 内持久，重跑可冲过间歇性断连）
# ─────────────────────────────────────────────────────────────
echo "=== Starting buildozer at $(date) ==="
cd "$WORKDIR"

attempt=1
max_attempts=2
BUILD_EXIT=1
while [ "$attempt" -le "$max_attempts" ]; do
  echo "=== buildozer attempt $attempt/$max_attempts at $(date) ==="
  set +e
  echo "y" | timeout 1650 buildozer android debug 2>&1 | tee -a "$WORKDIR/bin/build_full.log"
  BUILD_EXIT=${PIPESTATUS[1]}
  set -e
  echo "=== buildozer attempt $attempt exit code: $BUILD_EXIT ==="
  if [ "$BUILD_EXIT" -eq 0 ] && ls "$WORKDIR/bin/"*.apk >/dev/null 2>&1; then
    echo "=== SUCCESS on attempt $attempt ==="
    break
  fi
  echo "=== attempt $attempt failed (exit=$BUILD_EXIT), will retry if allowed ==="
  attempt=$((attempt + 1))
done

echo "=== Build ended at $(date) ==="

# List bin contents
cd "$WORKDIR"
echo "=== bin/ contents: ==="
ls -la bin/ || true
echo "=== APK files: ==="
find bin -name "*.apk" -type f -ls || true
echo "=== Log lines: ==="
wc -l bin/build_full.log || true
echo "=== Last 30 lines: ==="
tail -30 bin/build_full.log || true

# Always exit with buildozer's code (APK 存在则视为成功)
if ls "$WORKDIR/bin/"*.apk >/dev/null 2>&1; then
  echo "APK generated, forcing success"
  exit 0
fi
exit "$BUILD_EXIT"