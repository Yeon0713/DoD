#!/bin/sh
# 사장님 앱(웹, 8090)과 음성 백엔드(8100)를 한 번에 켠다.
# - 8100에 이미 백엔드가 떠 있으면 새로 켜지 않고 그대로 쓴다.
# - 앱을 끄면 여기서 켠 백엔드도 같이 꺼진다.
# .claude/launch.json 의 donna-voice-app 이 이 파일을 실행한다.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PID=""
APP_PID=""

cleanup() {
  trap - EXIT INT TERM
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  wait
}
trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

if nc -z 127.0.0.1 8100 2>/dev/null; then
  echo "[dev-web] 8100에 이미 백엔드가 떠 있어 그대로 씁니다."
else
  echo "[dev-web] 음성 백엔드를 켭니다: http://127.0.0.1:8100"
  (cd "$ROOT/server" && exec .venv/bin/python -m voice.run_voice) &
  BACKEND_PID=$!
fi

cd "$ROOT/donna-voice/app" || exit 1
./node_modules/.bin/expo start --web --port 8090 &
APP_PID=$!
wait "$APP_PID"
