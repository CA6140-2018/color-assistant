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

# GitHub mirror for China
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "https://github.com/"
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "git@github.com:"
git config --global http.postBuffer 1048576000
git config --global https.postBuffer 1048576000

# Install buildozer
pip install --user buildozer 'cython<3.0'

# Download Chinese font
mkdir -p "$WORKDIR/fonts"
curl -sL -o "$WORKDIR/fonts/NotoSansSC-Regular.otf" 'https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf' || true

echo "=== Starting buildozer at $(date) ==="
cd "$WORKDIR"

# Run buildozer - use PIPESTATUS[1] for buildozer exit code
set +e
echo "y" | buildozer android debug 2>&1 | tee "$WORKDIR/bin/build_full.log"
BUILD_EXIT=${PIPESTATUS[1]}
set -e

echo "=== Buildozer exit code: $BUILD_EXIT ==="
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

# Always exit with buildozer's code
exit $BUILD_EXIT
