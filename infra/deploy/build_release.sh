#!/usr/bin/env bash
# 로컬에서 앱 릴리스 묶음(release.tar.gz)을 만든다. Terraform 이 부른다.
#   build_release.sh <출력 폴더> <EXPO_PUBLIC_API_BASE_URL> <EXPO_PUBLIC_DEV_TOOLS: true|false>
# 묶음 안: server/ (git 이 무시하지 않는 파일), landing/, web/ (Expo 웹 빌드)
set -euo pipefail

OUT="$1"
API_BASE_URL="$2"
DEV_TOOLS="$3" # true 면 /demo·/dev 시연 화면을 켠다
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$OUT/stage"

rm -rf "$OUT"
mkdir -p "$STAGE"

# server/, landing/ — .env, db/app_data, __pycache__ 처럼 git 이 무시하는 파일은 빠진다
(cd "$REPO" && git ls-files -z --cached --others --exclude-standard -- server landing |
  while IFS= read -r -d '' f; do [ -f "$f" ] && printf '%s\0' "$f"; done |
  COPYFILE_DISABLE=1 tar --null -T - -cf -) | tar -xf - -C "$STAGE"

# Expo 웹
cd "$REPO/donna-voice/app"
[ -d node_modules ] || npm ci --no-audit --no-fund
EXPO_PUBLIC_API_BASE_URL="$API_BASE_URL" EXPO_PUBLIC_DEV_TOOLS="$DEV_TOOLS" npx expo export --platform web --output-dir "$STAGE/web" >/dev/null

COPYFILE_DISABLE=1 tar -czf "$OUT/release.tar.gz" -C "$STAGE" .
echo "release: $(du -h "$OUT/release.tar.gz" | cut -f1)"
