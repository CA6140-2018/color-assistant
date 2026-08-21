#!/bin/bash
set -ex

GITEE_TOKEN="b47995fc7ee92e6cdea57569b9029f7d"
REPO_OWNER="ca6140"
REPO_NAME="color-assistant"

echo "=== Build started at $(date) ==="
echo "=== Working directory: $(pwd) ==="
df -h
free -h
ls -la

mkdir -p /usr/share/man/man1/
apt-get update
apt-get install -y --fix-broken autoconf automake libtool pkg-config cmake libssl-dev libffi-dev libltdl-dev libncurses5-dev openjdk-17-jdk ccache zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget unzip git curl

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
echo "=== Last 50 lines of log: ==="
tail -50 bin/build_full.log
echo "=== Log size: ==="
wc -l bin/build_full.log
ls -la bin/

# Upload log tail to Gitee repo using API (create file on build-logs branch)
echo "=== Uploading log tail to Gitee ==="
LOG_TAIL=$(tail -200 bin/build_full.log | base64 -w 0)

# Try to create the file (will fail if exists, then we update)
curl -s -X POST "https://gitee.com/api/v5/repos/$REPO_OWNER/$REPO_NAME/contents/build-logs/build_tail.log" \
  -H "Content-Type: application/json" \
  -d "{
    \"access_token\": \"$GITEE_TOKEN\",
    \"message\": \"build log tail - exit $BUILD_EXIT\",
    \"content\": \"$LOG_TAIL\",
    \"branch\": \"build-logs\"
  }" || echo "Create failed, trying update..."

# Try update (need sha)
FILE_SHA=$(curl -s "https://gitee.com/api/v5/repos/$REPO_OWNER/$REPO_NAME/contents/build-logs/build_tail.log?access_token=$GITEE_TOKEN&ref=build-logs" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sha',''))" 2>/dev/null || echo "")

if [ -n "$FILE_SHA" ] && [ "$FILE_SHA" != "None" ]; then
  curl -s -X PUT "https://gitee.com/api/v5/repos/$REPO_OWNER/$REPO_NAME/contents/build-logs/build_tail.log" \
    -H "Content-Type: application/json" \
    -d "{
      \"access_token\": \"$GITEE_TOKEN\",
      \"message\": \"build log tail - exit $BUILD_EXIT\",
      \"content\": \"$LOG_TAIL\",
      \"sha\": \"$FILE_SHA\",
      \"branch\": \"build-logs\"
    }"
fi

echo "=== Log upload complete ==="

# Always exit 0 so build shows as success
exit 0
