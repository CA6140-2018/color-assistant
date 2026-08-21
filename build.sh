#!/bin/bash
set -ex

echo "=== Build started at $(date) ==="
echo "=== Working directory: $(pwd) ==="
df -h
free -h
ls -la

mkdir -p /usr/share/man/man1/
apt-get update
apt-get install -y --fix-broken autoconf automake libtool pkg-config cmake libssl-dev libffi-dev libltdl-dev libncurses5-dev openjdk-17-jdk ccache zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget unzip git

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH:$HOME/.local/bin"

pip install --user buildozer 'cython<3.0'

mkdir -p fonts
curl -sL -o fonts/NotoSansSC-Regular.otf 'https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf' || true

echo "=== Starting buildozer at $(date) ==="
df -h /

# Run buildozer and capture output to log file
mkdir -p bin
set +e
echo "y" | buildozer android debug > bin/build_full.log 2>&1
BUILD_EXIT=$?
set -e

echo "=== Buildozer exit code: $BUILD_EXIT ==="
echo "=== Build ended at $(date) ==="
echo "=== Last 100 lines of log: ==="
tail -100 bin/build_full.log
echo "=== Log size: ==="
wc -l bin/build_full.log
ls -la bin/

# Always exit 0 so artifact gets uploaded even on failure
exit 0
