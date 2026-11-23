#!/usr/bin/env bash
# VM 에서 root 로 돈다. Terraform 이 /tmp/donna-release 에 묶음·환경변수·설정을 올린 뒤 부른다.
#   install_release.sh <환경> <릴리스ID> "<운영자 CIDR들>" <주 Caddyfile> "<사이트 Caddyfile들>" <시연 자리 수>
# 헬스 체크가 실패하면 이전 릴리스로 되돌리고 실패로 끝낸다.
set -euo pipefail

ENV_NAME="$1"
RELEASE_ID="$2"
OPERATOR_CIDRS="$3"
CADDY_MAIN="$4"
CADDY_SITES="$5"
SEATS="${6:-0}" # 시연 자리: 자리 i 는 https://<호스트>:844i → 백엔드 810i (donna-<환경>-seat@i)
SEAT_HOST="$ENV_NAME.donna.ai.kr"
STAGE=/tmp/donna-release
SERVICE="donna-$ENV_NAME"
ROOT=/srv/donna
REL="$ROOT/releases/$RELEASE_ID"
ENV_FILE="/etc/donna/$ENV_NAME.env"
NOW="$(date +%Y%m%d%H%M%S)"

log() { echo "[donna] $*"; }

# 1. 패키지와 계정
need=()
command -v caddy >/dev/null || need+=(caddy)
python3 -c 'import venv, ensurepip' 2>/dev/null || need+=(python3-venv)
command -v curl >/dev/null || need+=(curl)
if [ ${#need[@]} -gt 0 ]; then
  log "설치: ${need[*]}"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}"
fi
id donna >/dev/null 2>&1 || useradd --system --home-dir "$ROOT" --shell /usr/sbin/nologin donna
install -d -m 755 "$ROOT" "$ROOT/releases" "$ROOT/landing"
install -d -o donna -g donna -m 750 "$ROOT/shared"

# 2. 릴리스 풀기와 파이썬 패키지
log "릴리스 $RELEASE_ID"
rm -rf "$REL"
mkdir -p "$REL"
tar -xzf "$STAGE/release.tar.gz" -C "$REL"
python3 -m venv "$REL/.venv"
"$REL/.venv/bin/pip" install -q --disable-pip-version-check -r "$REL/server/requirements.txt"
chown -R root:root "$REL"
chmod -R go-w "$REL"

# 실행 중에 쓰는 파일(server/db/app_data, 매장 DB)은 릴리스 밖 shared 에 두고 연결한다.
# 릴리스 폴더는 읽기 전용(ProtectSystem=strict)이고 릴리스마다 새로 만들어지기 때문이다.
# 저장소의 매장 DB 는 data.seed 로 두고, shared/db_data 에 없을 때만 채운다.
PREV="$(readlink -f "$ROOT/current" 2>/dev/null || true)"
SHARED="$ROOT/shared"
install -d -o donna -g donna -m 750 "$SHARED/app_data" "$SHARED/db_data"
rm -rf "$REL/server/db/app_data" "$REL/server/db/data.seed"
mv "$REL/server/db/data" "$REL/server/db/data.seed"
for f in "$REL"/server/db/data.seed/*.db; do
  [ -e "$SHARED/db_data/$(basename "$f")" ] || install -o donna -g donna -m 640 "$f" "$SHARED/db_data/"
done
ln -s "$SHARED/app_data" "$REL/server/db/app_data"
ln -s "$SHARED/db_data" "$REL/server/db/data"

# 3. 환경변수 합치기: app.env 의 키는 새 값으로, 서버에만 있는 키(VOICE_DATABASE_URL 등)는 그대로 둔다
install -d -o root -g donna -m 750 /etc/donna
ENV_BACKUP=""
if [ -f "$ENV_FILE" ]; then ENV_BACKUP="$ENV_FILE.bak-$NOW"; cp -p "$ENV_FILE" "$ENV_BACKUP"; fi
python3 - "$ENV_FILE" "$STAGE/app.env" <<'PY'
import os, sys
old_path, new_path = sys.argv[1], sys.argv[2]

def read(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value
    return out

merged = read(old_path)
merged.update(read(new_path))
tmp = old_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write("# Terraform 이 관리한다 (infra/environments/<환경>/app.env 와 기존 서버 값을 합침)\n")
    for key in sorted(merged):
        f.write(f"{key}={merged[key]}\n")
os.replace(tmp, old_path)
PY
chown root:donna "$ENV_FILE"
chmod 640 "$ENV_FILE"
if ! grep -qE '^VOICE_DATABASE_URL=.+' "$ENV_FILE"; then
  log "VOICE_DATABASE_URL 이 없습니다. app.env 에 넣어 주세요 (없으면 서비스가 시작되지 않음)"
  [ -n "$ENV_BACKUP" ] && cp -p "$ENV_BACKUP" "$ENV_FILE"
  exit 1
fi

# 4. systemd·Caddy 설정
install -m 644 "$STAGE/deploy/$SERVICE.service" "/etc/systemd/system/$SERVICE.service"
# Caddy: 주 Caddyfile 은 /etc/caddy/Caddyfile, 나머지는 /etc/caddy/sites/<이름>.caddy (주 파일이 import 한다)
# 운영자 IP 제한({$DONNA_STAGING_OPERATOR_CIDRS})은 systemd drop-in 이 읽는 /etc/caddy/donna-staging.env 로 넘긴다
[ -f /etc/caddy/Caddyfile ] && cp -p /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak-$NOW"
install -m 644 "$STAGE/deploy/$CADDY_MAIN" /etc/caddy/Caddyfile
install -d -m 755 /etc/caddy/sites
rm -f /etc/caddy/sites/*.caddy
for name in $CADDY_SITES; do
  install -m 644 "$STAGE/deploy/$name" "/etc/caddy/sites/${name%.Caddyfile}.caddy"
done
# 시연 자리: 자리마다 백엔드·데이터(SQLite)·주소(포트)를 따로 둔다. 데이터 폴더는 남겨 두고, 줄인 자리는 끈다
if [ "$SEATS" -gt 0 ]; then
  install -m 644 "$STAGE/deploy/$SERVICE-seat@.service" "/etc/systemd/system/$SERVICE-seat@.service"
fi
for i in $(seq 1 "$SEATS"); do
  install -d -o donna -g donna -m 750 "$ROOT/seats/$i" "$ROOT/seats/$i/app_data" "$ROOT/seats/$i/db_data"
  for f in "$REL"/server/db/data.seed/*.db; do
    [ -e "$ROOT/seats/$i/db_data/$(basename "$f")" ] || install -o donna -g donna -m 640 "$f" "$ROOT/seats/$i/db_data/"
  done
  printf '# 시연 자리 %s (install_release.sh 가 만든다). staging.env 다음에 읽혀 덮어쓴다\nVOICE_DATABASE_URL=\nVOICE_APP_ORIGINS=https://%s:844%s\n' "$i" "$SEAT_HOST" "$i" > "/etc/donna/seat-$i.env"
  chown root:donna "/etc/donna/seat-$i.env"
  chmod 640 "/etc/donna/seat-$i.env"
  printf '%s:844%s {\n\timport donna_app 810%s\n}\n' "$SEAT_HOST" "$i" "$i" > "/etc/caddy/sites/seat-$i.caddy"
done
for i in $(seq $((SEATS + 1)) 9); do
  systemctl disable --now -q "$SERVICE-seat@$i" 2>/dev/null || true
  rm -f "/etc/donna/seat-$i.env"
done
[ "$SEATS" -gt 0 ] || rm -f "/etc/systemd/system/$SERVICE-seat@.service"

printf 'DONNA_STAGING_OPERATOR_CIDRS="%s"\n' "$OPERATOR_CIDRS" > /etc/caddy/donna-staging.env
chmod 600 /etc/caddy/donna-staging.env
install -d -m 755 /etc/systemd/system/caddy.service.d
install -m 644 "$STAGE/deploy/donna-staging-caddy.conf" /etc/systemd/system/caddy.service.d/donna-staging.conf
DONNA_STAGING_OPERATOR_CIDRS="$OPERATOR_CIDRS" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 ||
  { log "Caddy 설정 검사 실패"; DONNA_STAGING_OPERATOR_CIDRS="$OPERATOR_CIDRS" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile || true
    [ -f "/etc/caddy/Caddyfile.bak-$NOW" ] && cp -p "/etc/caddy/Caddyfile.bak-$NOW" /etc/caddy/Caddyfile
    [ -n "$ENV_BACKUP" ] && cp -p "$ENV_BACKUP" "$ENV_FILE"
    exit 1; }

# 5. 전환과 재시작
switch_to() {
  ln -sfn "$1" "$ROOT/current.tmp" && mv -Tf "$ROOT/current.tmp" "$ROOT/current"
  [ -d "$1/landing" ] && ln -sfn "$1/landing" "$ROOT/landing/current.tmp" && mv -Tf "$ROOT/landing/current.tmp" "$ROOT/landing/current"
  systemctl daemon-reload
  systemctl enable -q "$SERVICE"
  systemctl restart "$SERVICE"
  for i in $(seq 1 "$SEATS"); do
    systemctl enable -q "$SERVICE-seat@$i"
    systemctl restart "$SERVICE-seat@$i"
  done
}
healthy_port() {
  for _ in $(seq 1 30); do
    curl -fsS -o /dev/null "http://127.0.0.1:$1/health" && return 0
    sleep 2
  done
  return 1
}
healthy() {
  healthy_port 8100 || { journalctl -u "$SERVICE" -n 40 --no-pager || true; return 1; }
  for i in $(seq 1 "$SEATS"); do
    healthy_port "810$i" || { log "시연 자리 $i 실패"; journalctl -u "$SERVICE-seat@$i" -n 40 --no-pager || true; return 1; }
  done
}

switch_to "$REL"
if ! healthy; then
  log "헬스 체크 실패"
  if [ -n "$ENV_BACKUP" ]; then
    log "환경변수 파일을 되돌림: $ENV_BACKUP"
    cp -p "$ENV_BACKUP" "$ENV_FILE"
  fi
  if [ -n "$PREV" ] && [ "$PREV" != "$REL" ] && [ -d "$PREV" ]; then
    log "이전 릴리스로 되돌림: $PREV"
    switch_to "$PREV"
  fi
  exit 1
fi
systemctl enable -q caddy
systemctl restart caddy # 환경변수(운영자 IP)는 reload 로는 다시 읽지 않는다

# 6. 오래된 릴리스 정리 (최근 3개 유지)
ls -1dt "$ROOT"/releases/*/ | tail -n +4 | xargs -r rm -rf
rm -rf "$STAGE"
log "완료: $SERVICE ($RELEASE_ID), 시연 자리 $SEATS 개"
