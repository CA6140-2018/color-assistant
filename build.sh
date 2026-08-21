#!/bin/bash
set -exo pipefail

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
echo "=== Free disk space: ==="
df -h /

echo "y" | buildozer android debug 2>&1 | tee /tmp/buildozer.log

echo "=== Build completed at $(date) ==="
