#!/bin/bash
set -ex

LOGFILE=/tmp/build.log
exec > >(tee "$LOGFILE") 2>&1

trap 'echo "=== BUILD FAILED AT LINE $LINENO ==="; echo "=== LAST 100 LINES OF LOG ==="; tail -100 "$LOGFILE"' ERR

echo "=== Build started at $(date) ==="
echo "=== Hostname: $(hostname) ==="
echo "=== Working directory: $(pwd) ==="
echo "=== Disk space: ==="
df -h
echo "=== Memory: ==="
free -h
echo "=== Files in directory: ==="
ls -la

# Create swap space to help with memory
if [ ! -f /swapfile ]; then
  echo "=== Creating 4GB swap file ==="
  dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "=== Swap enabled ==="
  free -h
fi

mkdir -p /usr/share/man/man1/
apt-get update
apt-get install -y --fix-broken autoconf automake libtool pkg-config cmake libssl-dev libffi-dev libltdl-dev libncurses5-dev openjdk-17-jdk ccache zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget unzip git

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH:$HOME/.local/bin"

pip install --user buildozer 'cython<3.0'

mkdir -p fonts
curl -sL -o fonts/NotoSansSC-Regular.otf 'https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf' || true

echo "=== Starting buildozer at $(date) ==="
echo "y" | buildozer android debug || {
  echo "=== BUILDOZER FAILED ==="
  echo "=== Exit code: $? ==="
  echo "=== Last 200 lines of buildozer output: ==="
  tail -200 "$LOGFILE"
  # Copy log to bin directory for artifact upload
  mkdir -p bin
  cp "$LOGFILE" bin/build.log
  exit 1
}

echo "=== Build succeeded at $(date) ==="
# Copy log to bin directory for artifact upload
mkdir -p bin
cp "$LOGFILE" bin/build.log
ls -la bin/
