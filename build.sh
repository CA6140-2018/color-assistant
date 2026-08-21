#!/bin/bash
set -ex

echo "=== Build started at $(date) ==="
echo "=== Working directory: $(pwd) ==="
df -h
free -h
ls -la

# Create man dir (needed for JDK)
mkdir -p /usr/share/man/man1/

# Install dependencies
apt-get update
apt-get install -y --fix-broken autoconf automake libtool pkg-config cmake libssl-dev libffi-dev libltdl-dev libncurses5-dev openjdk-17-jdk ccache zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget unzip git curl ca-certificates

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH:$HOME/.local/bin"

# Add swap space to prevent OOM (4GB)
echo "=== Adding swap space ==="
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile || true
fi
free -h

# Configure git to use GitHub mirrors for faster access in China
# Primary mirror: ghproxy.com
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "https://github.com/"
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "git@github.com:"

# Git optimizations
git config --global http.postBuffer 1048576000
git config --global https.postBuffer 1048576000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999
git config --global core.compression 0

# Install buildozer and cython (pin versions for compatibility)
pip install --user 'buildozer==1.6.0' 'cython<3.0'

# Download Chinese font
mkdir -p fonts
curl -sL -o fonts/NotoSansSC-Regular.otf 'https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf' || true

echo "=== Starting buildozer at $(date) ==="
df -h /

# Create bin directory for output
mkdir -p bin

# Run buildozer with retry (up to 3 attempts)
BUILD_EXIT=1
for i in 1 2 3; do
  echo "=== Build attempt $i at $(date) ==="
  set +e
  # PIPESTATUS[1] = buildozer exit code (PIPESTATUS[0] is echo "y")
  echo "y" | buildozer android debug 2>&1 | tee bin/build_full.log | tail -100
  BUILD_EXIT=${PIPESTATUS[1]}
  set -e
  echo "=== Build attempt $i exit code: $BUILD_EXIT ==="
  if [ $BUILD_EXIT -eq 0 ]; then
    echo "=== Build SUCCESS on attempt $i ==="
    break
  fi
  echo "=== Build failed on attempt $i ==="
  echo "=== Last 30 lines of error log: ==="
  tail -30 bin/build_full.log || true
  if [ $i -lt 3 ]; then
    echo "=== Retrying in 15 seconds... ==="
    sleep 15
  fi
done

echo "=== Build ended at $(date) ==="
echo "=== Final exit code: $BUILD_EXIT ==="
echo "=== Last 50 lines of log: ==="
tail -50 bin/build_full.log || true
echo "=== Log size: ==="
wc -l bin/build_full.log || true
echo "=== Files in bin/: ==="
ls -la bin/ || true
echo "=== APK file check: ==="
find bin -name "*.apk" -ls || true

# Exit with buildozer's exit code
exit $BUILD_EXIT
