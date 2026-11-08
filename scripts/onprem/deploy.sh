#!/usr/bin/env bash
# deploy.sh — ติดตั้ง/อัปเดต JA PDF Editor บนเซิร์ฟเวอร์ Ubuntu ขององค์กร จาก image บน Docker Hub (ไม่ต้องมีซอร์สโค้ด)
# อยู่ในชุดไฟล์ onprem-deploy-kit.tar.gz (สร้างด้วย scripts/onprem/build-push.sh) — รันในโฟลเดอร์ที่มี docker-compose.prod.yml
#
#   ./deploy.sh setup              ตรวจเครื่อง (Docker หรือ Podman + compose) + สร้าง .env.prod จาก template + ตรวจค่าที่ยังไม่ได้แก้
#   ./deploy.sh deploy [แท็ก]       ดึง image แล้วเปิด/อัปเดตระบบ (ไม่ระบุ = แท็กใน .env.prod) → รอ backend พร้อม → ตรวจ /api/health
#   ./deploy.sh rollback [แท็ก]     กลับไปแท็กก่อนหน้า (ไม่ระบุ = แท็กที่ใช้ก่อน deploy ครั้งล่าสุด)
#   ./deploy.sh status             แท็ก/เวอร์ชันที่รันอยู่ + สถานะ container + รูปแบบการติดตั้ง
#   ./deploy.sh logs [backend|frontend|db|redis|tls] [จำนวนบรรทัด]
#   ./deploy.sh backup [โฟลเดอร์]    สำรองฐานข้อมูล + ไฟล์ผู้ใช้ + .env.prod + secrets (ค่าเริ่มต้น ./backups/<วันเวลา>)
#   ./deploy.sh backup-schedule [HH:MM|off]  ตั้งสำรองอัตโนมัติทุกวัน (cron ของผู้ใช้นี้ ค่าเริ่มต้น 02:30) · off = ยกเลิก
#   ./deploy.sh make-admin <email> ตั้งผู้ดูแลระบบ (บัญชีต้องสมัครแล้ว) · --revoke ถอนสิทธิ์
#   ./deploy.sh stop | start       ปิด/เปิดระบบ (ข้อมูลอยู่ครบ)
#
# Docker หรือ Podman: ใช้ docker ถ้ามี ไม่งั้น podman (บังคับ: CONTAINER_ENGINE=podman ./deploy.sh ...)
#   Podman ต้องมี compose: podman compose (ติดตั้ง docker-compose v2 หรือ podman-compose — แนะนำ docker-compose)
# HTTPS: ใช้ docker-compose.onprem-tls.yml อัตโนมัติเมื่อมี ./secrets/tls/fullchain.pem
#   บังคับเอง: ONPREM_TLS=true|false ใน .env.prod (false = องค์กรมี reverse proxy ทำ HTTPS ให้)
# ตัวเลือก: YES=1 ไม่ถามยืนยัน · BACKUP_KEEP=7 เก็บ backup ล่าสุดกี่ชุด (0 = ไม่ลบ) · HEALTH_TIMEOUT=300 (วินาที)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
ENV_FILE=".env.prod"
HISTORY=".deploy-history"

c_info=$'\033[1;34m'; c_ok=$'\033[1;32m'; c_warn=$'\033[1;33m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
step() { printf '%s==> %s%s\n' "$c_info" "$*" "$c_off"; }
ok()   { printf '%s✓ %s%s\n' "$c_ok" "$*" "$c_off"; }
warn() { printf '%s! %s%s\n' "$c_warn" "$*" "$c_off" >&2; }
die()  { printf '%s✗ %s%s\n' "$c_err" "$*" "$c_off" >&2; exit 1; }
confirm() {
  [ "${YES:-0}" = "1" ] && return 0
  local a; read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy]$ ]]
}

# อ่านค่าจาก .env.prod โดยไม่ source (ค่าอาจมีช่องว่าง/อักขระพิเศษ)
env_get() {
  [ -f "$ENV_FILE" ] || return 0
  { grep -E "^$1=" "$ENV_FILE" || true; } | tail -1 | cut -d= -f2- | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}
env_set() {
  local key="$1" val="$2"
  if grep -qE "^$key=" "$ENV_FILE"; then
    sed -i "s#^$key=.*#$key=$val#" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

DOCKER="docker"   # คำสั่งของ engine (docker | podman | sudo docker ...)
ENGINE=""         # docker | podman
COMPOSE_PROVIDER="" # podman: docker-compose | podman-compose
need_docker() {
  [ -n "$ENGINE" ] && return 0
  local want="${CONTAINER_ENGINE:-}"
  if [ -z "$want" ]; then
    # docker ที่เรียกได้จริงก่อน (มีแค่ตัวคำสั่งแต่ไม่มี daemon / เป็น podman-docker → ใช้ podman)
    if command -v docker >/dev/null && ! docker --version 2>/dev/null | grep -qi podman \
       && { docker info >/dev/null 2>&1 || sudo -n docker info >/dev/null 2>&1 || ! command -v podman >/dev/null; }; then
      want=docker
    elif command -v podman >/dev/null; then want=podman
    else die "ไม่พบ docker หรือ podman — ติดตั้ง Docker Engine (https://docs.docker.com/engine/install/ubuntu/) หรือ sudo apt install podman"; fi
  fi
  command -v "$want" >/dev/null || die "ไม่พบ $want"
  ENGINE="$want"
  DOCKER="$want"
  if ! $DOCKER info >/dev/null 2>&1; then
    if sudo -n "$want" info >/dev/null 2>&1; then DOCKER="sudo $want"
    elif [ "$want" = docker ]; then die "เรียก docker ไม่ได้ — sudo usermod -aG docker \$USER แล้ว logout/login ใหม่ (หรือรันด้วย sudo)"
    else die "เรียก podman ไม่ได้ — ลอง podman info"; fi
  fi
  if [ "$ENGINE" = podman ]; then
    local out
    out="$($DOCKER compose version 2>&1)" || die "Podman ยังไม่มี compose — แนะนำ: sudo apt install docker-compose-v2 (หรือ podman-compose) แล้ว systemctl --user enable --now podman.socket"
    if echo "$out" | grep -qi "podman-compose"; then COMPOSE_PROVIDER=podman-compose; else COMPOSE_PROVIDER=docker-compose; fi
  fi
}

use_tls() {
  local v; v="$(env_get ONPREM_TLS | tr 'A-Z' 'a-z')"
  case "$v" in
    true|1|yes) return 0 ;;
    false|0|no) return 1 ;;
  esac
  [ -f docker-compose.onprem-tls.yml ] && [ -f secrets/tls/fullchain.pem ]
}

compose() {
  local files=(-f docker-compose.prod.yml)
  if use_tls; then
    files+=(-f docker-compose.onprem-tls.yml)
    # หน้าเว็บย้ายออกจากพอร์ต 80 ให้ nginx tls (ค่าจากเชลล์ทับค่าใน .env.prod)
    export FRONTEND_BIND="${ONPREM_FRONTEND_BIND:-127.0.0.1:8081}"
  fi
  # shellcheck disable=SC2086
  $DOCKER compose --env-file "$ENV_FILE" "${files[@]}" "$@"
}

# ดึง image ของแท็กนี้ด้วย engine ตรงๆ (ไม่ผ่าน compose — podman-compose ไม่รองรับตัวเลือก pull ทุกแบบ)
pull_images() {
  local tag="$1" b f
  b="$(env_get BACKEND_IMAGE)"; b="${b:-docker.io/jaturon2526/pdf-editor-backend}"
  f="$(env_get FRONTEND_IMAGE)"; f="${f:-docker.io/jaturon2526/pdf-editor-frontend}"
  $DOCKER pull -q "$b:$tag" >/dev/null && $DOCKER pull -q "$f:$tag" >/dev/null
}

# backend พร้อมไหม — Podman: healthcheck ทำงานผ่าน systemd timer (บางเครื่องไม่มี) จึงสั่งตรวจเองด้วย
backend_health() {
  local st
  st="$($DOCKER inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' pdf_backend_prod 2>/dev/null || echo missing)"
  if [ "$ENGINE" = podman ] && [ "$st" != healthy ] && [ "$st" != missing ] && [ "$st" != exited ]; then
    if $DOCKER healthcheck run pdf_backend_prod >/dev/null 2>&1; then st=healthy; fi
  fi
  echo "$st"
}

require_env() { [ -f "$ENV_FILE" ] || die "ยังไม่มี $ENV_FILE — รัน ./deploy.sh setup ก่อน"; }

current_tag() { local t; t="$(env_get IMAGE_TAG)"; echo "${t:-latest}"; }

check_tag() {
  [[ "$1" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "แท็ก '$1' ใช้ไม่ได้"
  if [ "$1" = latest ] && [ "$(env_get DEPLOYMENT_PROFILE)" = onprem ]; then
    warn "แท็ก latest คือ image ของเว็บสาธารณะ (ARM64) — ติดตั้งในองค์กรควรใช้แท็ก onprem / onprem-v..."
    confirm "ใช้ latest ต่อ?" || die "ยกเลิก"
  fi
}

# ค่าใน .env ไม่รวมคอมเมนต์ท้ายบรรทัด (KEY=value   # ...)
env_val() { env_get "$1" | sed -E 's/[[:space:]]+#.*$//; s/[[:space:]]+$//'; }

# LINE (AUTH_LINE_ENABLED=true): เข้าสู่ระบบ = LINE Login channel · แจ้งเตือน = Messaging API channel (OA)
# สอง channel ต้องอยู่ provider เดียวกัน (userId ตรงกัน → เข้าด้วย LINE แล้วผูกรับแจ้งเตือนให้อัตโนมัติ) — ดู README
check_line() {
  local url="$1" enabled id sec chs tok
  enabled="$(env_val AUTH_LINE_ENABLED | tr '[:upper:]' '[:lower:]')"
  case "$enabled" in 1|true|yes|on) ;; *) return 0 ;; esac
  id="$(env_val LINE_LOGIN_CHANNEL_ID)"; sec="$(env_val LINE_LOGIN_CHANNEL_SECRET)"
  chs="$(env_val LINE_CHANNEL_SECRET)"; tok="$(env_val LINE_CHANNEL_ACCESS_TOKEN)"
  if [ -n "$id" ] && [ -n "$sec" ]; then
    [[ "$id" =~ ^[0-9]{10}$ ]] || warn "LINE_LOGIN_CHANNEL_ID ควรเป็นตัวเลข 10 หลัก (ได้ ${#id} ตัวอักษร) — คัดลอกจากแท็บ Basic settings ของ channel LINE Login"
    [ "${#sec}" -eq 32 ] || warn "LINE_LOGIN_CHANNEL_SECRET ควรยาว 32 ตัวอักษร (ได้ ${#sec})"
    ok "เข้าสู่ระบบด้วย LINE: เปิด · Callback URL ที่ต้องลงทะเบียน: ${url%/}/auth/line/callback"
  else
    warn "AUTH_LINE_ENABLED=true แต่ไม่ได้ตั้ง LINE_LOGIN_CHANNEL_ID / LINE_LOGIN_CHANNEL_SECRET — ไม่มีปุ่มเข้าสู่ระบบด้วย LINE"
  fi
  if [ -n "$chs" ] && [ -n "$tok" ]; then
    [ "${#chs}" -eq 32 ] || warn "LINE_CHANNEL_SECRET ควรยาว 32 ตัวอักษร (ได้ ${#chs}) — แท็บ Basic settings ของ channel Messaging API"
    [ "${#tok}" -ge 100 ] || warn "LINE_CHANNEL_ACCESS_TOKEN สั้นผิดปกติ (${#tok} ตัวอักษร) — ใช้ Channel access token (long-lived) จากแท็บ Messaging API"
    ok "แจ้งเตือนทาง LINE: เปิด · Webhook URL ที่ต้องลงทะเบียน: ${url%/}/api/line/webhook (LINE ต้องเข้าถึงได้จากอินเทอร์เน็ต)"
  else
    warn "ไม่ได้ตั้ง LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN — เข้าสู่ระบบด้วย LINE ได้ แต่ไม่มีแจ้งเตือนทาง LINE"
  fi
  [[ "$url" == https://* ]] || warn "LINE ต้องใช้ FRONTEND_URL แบบ https://<โดเมน> — Callback/Webhook URL ที่ลงทะเบียนกับ LINE ต้องเป็น https"
}

# ---------- setup ----------
cmd_setup() {
  step "ตรวจเครื่อง"
  local bad=0 line
  need_docker
  local v major minor
  v="$($DOCKER compose version --short 2>/dev/null | tail -1 || true)"
  [ -n "$v" ] || v="$($DOCKER compose version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | tail -1 || true)"
  [ -n "$v" ] || die "ไม่พบ compose — Docker: sudo apt install docker-compose-plugin · Podman: sudo apt install docker-compose-v2 (หรือ podman-compose)"
  v="${v#v}"; major="${v%%.*}"; minor="${v#*.}"; minor="${minor%%.*}"
  if [ "$ENGINE" = podman ]; then
    ok "Podman $($DOCKER --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) · compose: $COMPOSE_PROVIDER $v"
    if [ "$COMPOSE_PROVIDER" = podman-compose ]; then
      warn "podman-compose รองรับ depends_on/healthcheck ไม่ครบ — แนะนำ docker-compose v2: sudo apt install docker-compose-v2 && systemctl --user enable --now podman.socket"
    fi
    if [ "$DOCKER" = podman ] && [ "$(id -u)" != 0 ]; then
      local low port
      low="$(sysctl -n net.ipv4.ip_unprivileged_port_start 2>/dev/null || echo 1024)"
      if use_tls; then port=80; else port="$(env_get FRONTEND_BIND)"; port="${port##*:}"; port="${port:-80}"; fi
      if [ "$port" -lt "$low" ]; then
        warn "Podman แบบไม่ใช้ root เปิดพอร์ต $port ไม่ได้ (เปิดได้ตั้งแต่ $low) — เลือกอย่างใดอย่างหนึ่ง:"
        warn "  อนุญาตพอร์ต 80 ขึ้นไป: echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/90-unprivileged-ports.conf && sudo sysctl --system"
        warn "  หรือใช้พอร์ตอื่น (ไม่มี HTTPS ในตัว): FRONTEND_BIND=8080 และ FRONTEND_URL=http://<IP>:8080 ใน $ENV_FILE"
        bad=1
      fi
      if command -v loginctl >/dev/null && ! loginctl show-user "$USER" 2>/dev/null | grep -q '^Linger=yes'; then
        warn "ให้ระบบทำงานต่อหลัง logout/รีบูต: sudo loginctl enable-linger $USER && systemctl --user enable podman-restart.service"
      fi
    fi
  elif [ "$major" -lt 2 ]; then
    warn "Docker Compose $v — ต้องใช้ v2 ขึ้นไป (docker compose)"
  else ok "Docker Compose $v"; fi
  [ "$(uname -m)" = x86_64 ] || [ "$(uname -m)" = aarch64 ] || warn "สถาปัตยกรรม $(uname -m) — ตรวจว่า image build ตรงกัน"
  ok "สถาปัตยกรรม $(uname -m) (image ต้อง build เป็น $( [ "$(uname -m)" = x86_64 ] && echo linux/amd64 || echo linux/arm64 ))"
  [ -f docker-compose.prod.yml ] || die "ไม่พบ docker-compose.prod.yml — แตกไฟล์ onprem-deploy-kit.tar.gz แล้วรันในโฟลเดอร์นั้น"

  if [ ! -f "$ENV_FILE" ]; then
    [ -f .env.onprem.template ] || die "ไม่พบ .env.onprem.template"
    cp .env.onprem.template "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok "สร้าง $ENV_FILE จาก template แล้ว"
    if grep -q '^JWT_SECRET=<' "$ENV_FILE"; then
      env_set JWT_SECRET "$(head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | head -c 64)"
      ok "สุ่ม JWT_SECRET ให้แล้ว (ห้ามเปลี่ยนหลังเปิดใช้)"
    fi
    if grep -q '^DB_PASSWORD=<' "$ENV_FILE"; then
      env_set DB_PASSWORD "$(head -c 32 /dev/urandom | base64 | tr -d '/+=\n' | head -c 32)"
      ok "สุ่ม DB_PASSWORD ให้แล้ว"
    fi
  fi
  mkdir -p secrets && chmod 700 secrets

  step "ตรวจ $ENV_FILE"
  while IFS= read -r line; do
    warn "ยังไม่ได้แก้: $line"; bad=1
  done < <(grep -nE '^[A-Z_]+=.*<[^>]*>' "$ENV_FILE" || true)
  local url; url="$(env_get FRONTEND_URL)"
  # http: แค่เตือน (ทดสอบด้วย IP ได้ — ใช้ passkey ไม่ได้) · ไม่นับเป็นข้อที่ต้องแก้
  [[ "$url" == https://* ]] || warn "FRONTEND_URL เป็น http — ใช้ทดสอบได้ แต่ passkey ใช้ไม่ได้ (ใช้งานจริงควรเป็น https://)"
  # $ ในค่าที่ไม่ได้ครอบ '...' ถูก compose แปลงเป็นตัวแปร (รหัสผ่านโดนตัด เช่น SMTP login ไม่ผ่าน 535)
  while IFS= read -r line; do
    warn "ค่ามี \$ แต่ไม่ได้ครอบด้วย '...': ${line%%=*} — แก้เป็น ${line%%=*}='ค่าเดิม' (ไม่งั้นส่วนหลัง \$ หาย)"; bad=1
  done < <(grep -E '^[A-Z_]+=[^'"'"']*\$' "$ENV_FILE" || true)
  [ -n "$(env_get INITIAL_ADMIN_EMAILS)" ] || warn "ไม่ได้ตั้ง INITIAL_ADMIN_EMAILS — ผู้ที่สมัครคนแรกจะได้สิทธิ์ผู้ดูแล"
  [ -n "$(env_get SMTP_FROM)" ] || warn "ไม่ได้ตั้ง SMTP_FROM — อีเมลยืนยัน/ลืมรหัสผ่านจะส่งไม่ออก"
  check_line "$url"
  local seal; seal="$(env_get SIGNING_SEAL_P12)"
  if [ -n "$seal" ]; then
    local host="secrets/${seal#/run/secrets/pdf-editor/}"
    [ -f "$host" ] && ok "ใบรับรองลงนาม: $host" || { warn "SIGNING_SEAL_P12=$seal แต่ไม่พบ $host"; bad=1; }
  fi
  local ca; ca="$(env_get SMTP_CA_FILE)"
  if [ -n "$ca" ]; then
    [ -f "secrets/${ca#/run/secrets/pdf-editor/}" ] || { warn "SMTP_CA_FILE=$ca แต่ไม่พบไฟล์ใน ./secrets"; bad=1; }
  fi
  if use_tls; then
    [ -f secrets/tls/fullchain.pem ] && [ -f secrets/tls/privkey.pem ] || { warn "เปิด HTTPS แต่ไม่พบ secrets/tls/fullchain.pem + privkey.pem"; bad=1; }
    if command -v openssl >/dev/null && [ -f secrets/tls/fullchain.pem ]; then
      local end host
      end="$(openssl x509 -in secrets/tls/fullchain.pem -noout -enddate 2>/dev/null | cut -d= -f2 || true)"
      host="$(echo "$url" | sed -E 's#^https?://([^/:]+).*#\1#')"
      [ -n "$end" ] && ok "ใบรับรอง TLS หมดอายุ $end"
      if [ -n "$host" ] && ! openssl x509 -in secrets/tls/fullchain.pem -noout -checkhost "$host" 2>/dev/null | grep -q "does match"; then
        warn "ใบรับรอง TLS ไม่ได้ออกให้ $host"; bad=1
      fi
    fi
    ok "HTTPS: ใช้ docker-compose.onprem-tls.yml (พอร์ต 80 → 443)"
  else
    local fb; fb="$(env_get FRONTEND_BIND)"; fb="${fb##*:}"
    ok "HTTPS: ไม่ใช้ในตัว — หน้าเว็บอยู่ที่ http://<เครื่องนี้>:${fb:-80} (reverse proxy ขององค์กรส่งต่อมาที่นี่ได้)"
  fi
  compose config >/dev/null || die "ไฟล์ compose / $ENV_FILE ผิดรูปแบบ"
  if [ "$bad" = 1 ]; then
    warn "แก้ $ENV_FILE / ./secrets ตามรายการด้านบน แล้วรัน ./deploy.sh setup อีกครั้ง"
    return 1
  fi
  ok "พร้อม deploy: ./deploy.sh deploy"
}

# ---------- deploy / rollback ----------
wait_healthy() {
  local timeout="${HEALTH_TIMEOUT:-300}" waited=0 st
  step "รอ backend พร้อม (สร้าง/อัปเกรดฐานข้อมูลตอน start · สูงสุด ${timeout}s)"
  while [ "$waited" -lt "$timeout" ]; do
    st="$(backend_health)"
    case "$st" in
      healthy) ok "backend พร้อม"; return 0 ;;
      unhealthy|exited|dead|missing) break ;;
    esac
    sleep 5; waited=$((waited + 5))
  done
  warn "backend ไม่พร้อม (สถานะ: $st) — log ล่าสุด:"
  $DOCKER logs --tail 40 pdf_backend_prod 2>&1 || true
  return 1
}

check_url() {
  local url; url="$(env_get FRONTEND_URL)"
  [ -n "$url" ] || return 0
  command -v curl >/dev/null || return 0
  if curl -fsS --max-time 10 "$url/api/health" >/dev/null 2>&1; then
    ok "$url/api/health ตอบปกติ"
  else
    warn "เรียก $url/api/health จากเครื่องนี้ไม่ได้ — ตรวจ DNS/ใบรับรอง/firewall (ระบบอาจทำงานปกติถ้าเครื่องนี้มองไม่เห็นโดเมนตัวเอง)"
  fi
}

show_profile() {
  $DOCKER logs pdf_backend_prod 2>&1 | grep -E "รูปแบบการติดตั้ง|ใบรับรองระบบ" | tail -2 || true
}

do_deploy() {
  local tag="$1" prev
  prev="$(current_tag)"
  check_tag "$tag"
  echo "deploy แท็ก: $tag  (เดิม: $prev)"
  echo "  $(env_get BACKEND_IMAGE):$tag"
  echo "  $(env_get FRONTEND_IMAGE):$tag"
  confirm "ดำเนินการต่อ?" || die "ยกเลิก"
  env_set IMAGE_TAG "$tag"
  step "ดึง image"
  if ! pull_images "$tag"; then
    env_set IMAGE_TAG "$prev"
    die "ดึง image ไม่สำเร็จ (คืนแท็กเป็น $prev) — แท็กมีอยู่จริงไหม / repository private ต้อง docker login ก่อน"
  fi
  step "เปิด/อัปเดตระบบ"
  if [ "$COMPOSE_PROVIDER" = podman-compose ]; then compose up -d; else compose up -d --remove-orphans; fi
  printf '%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$prev" "$tag" >> "$HISTORY"
  if wait_healthy; then
    check_url
    show_profile
    $DOCKER image prune -f >/dev/null 2>&1 || true
    ok "deploy เสร็จ: $tag"
  else
    warn "ย้อนกลับ: ./deploy.sh rollback   (กลับไป $prev)"
    exit 1
  fi
}

cmd_deploy() {
  need_docker; require_env
  local tag="${1:-$(current_tag)}"
  do_deploy "$tag"
}

cmd_rollback() {
  need_docker; require_env
  local tag="${1:-}"
  if [ -z "$tag" ]; then
    [ -f "$HISTORY" ] || die "ยังไม่มีประวัติ deploy — ระบุแท็ก: ./deploy.sh rollback <แท็ก>"
    tag="$(tail -1 "$HISTORY" | cut -f2)"
    [ -n "$tag" ] || die "อ่านแท็กก่อนหน้าไม่ได้ — ระบุแท็กเอง"
  fi
  warn "ฐานข้อมูลไม่ถูกย้อน — ถ้าเวอร์ชันใหม่อัปเกรด schema ไปแล้ว เวอร์ชันเก่าอาจใช้ไม่ได้ (กู้จาก backup ก่อน deploy)"
  do_deploy "$tag"
}

cmd_status() {
  need_docker; require_env
  echo "แท็กใน $ENV_FILE: $(current_tag)  ·  HTTPS ในตัว: $(use_tls && echo ใช้ || echo ไม่ใช้)"
  local s img
  for s in pdf_backend_prod pdf_frontend_prod; do
    img="$($DOCKER inspect -f '{{.Config.Image}}' "$s" 2>/dev/null || true)"
    [ -n "$img" ] || continue
    printf '  %-18s %s  (version %s, commit %s)\n' "$s" "$img" \
      "$($DOCKER inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$s" 2>/dev/null)" \
      "$($DOCKER inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$s" 2>/dev/null | cut -c1-7)"
  done
  compose ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || compose ps
  show_profile
  [ -f "$HISTORY" ] && { echo "deploy ล่าสุด:"; tail -5 "$HISTORY" | awk -F'\t' '{printf "  %s  %s → %s\n", $1, $2, $3}'; }
}

cmd_logs() {
  need_docker; require_env
  local svc="${1:-backend}" n="${2:-100}"
  compose logs --tail "$n" -f "$svc"
}

cmd_backup() {
  need_docker; require_env
  local dest="${1:-backups/$(date +%Y%m%d-%H%M%S)}" user db keep
  user="$(env_get DB_USER)"; user="${user:-pdf_user}"
  db="$(env_get DB_NAME)"; db="${db:-pdf_editor}"
  mkdir -p "$dest"; chmod 700 "$dest"
  step "สำรองฐานข้อมูล → $dest/db.dump"
  $DOCKER exec pdf_db_prod pg_dump -U "$user" -Fc "$db" > "$dest/db.dump" || die "pg_dump ไม่สำเร็จ"
  step "สำรองไฟล์ผู้ใช้ → $dest/files.tgz"
  $DOCKER run --rm --volumes-from pdf_backend_prod -v "$(cd "$dest" && pwd):/backup" docker.io/library/alpine:3.20 \
    tar czf /backup/files.tgz -C /data . || die "สำรองไฟล์ไม่สำเร็จ"
  step "สำรอง .env.prod + secrets"
  tar czf "$dest/config.tgz" "$ENV_FILE" secrets "$HISTORY" 2>/dev/null || tar czf "$dest/config.tgz" "$ENV_FILE" secrets
  chmod 600 "$dest"/*
  # เวลาสำรองล่าสุด → หน้าแอดมินเตือนเมื่อขาดหายเกิน BACKUP_MAX_AGE_HOURS (ไม่สำเร็จไม่เป็นไร)
  date -u +%FT%TZ | $DOCKER exec -i pdf_backend_prod sh -c 'cat > /data/.last-backup' 2>/dev/null || true
  ok "สำรองเสร็จ: $dest ($(du -sh "$dest" | cut -f1)) — คัดลอกออกนอกเครื่องด้วย (มี JWT_SECRET และใบรับรอง)"
  keep="${BACKUP_KEEP:-7}"
  if [ "$keep" -gt 0 ] && [ -z "${1:-}" ]; then
    # ลบชุดเก่าใน ./backups เกิน $keep ชุด (เฉพาะโฟลเดอร์ชื่อวันเวลาที่สคริปต์สร้าง)
    ls -1d backups/[0-9]*-[0-9]* 2>/dev/null | sort | head -n -"$keep" | while read -r old; do
      rm -rf -- "$old" && echo "  ลบ backup เก่า $old"
    done
  fi
}

cmd_backup_schedule() {
  command -v crontab >/dev/null || die "ไม่พบ crontab (Ubuntu: sudo apt install -y cron)"
  local when="${1:-02:30}" here tag="# ja-pdf-editor-backup" current
  here="$(pwd)"
  current="$(crontab -l 2>/dev/null | grep -v "$tag" || true)"
  if [ "$when" = "off" ]; then
    printf '%s\n' "$current" | sed '/^$/d' | crontab -
    ok "ยกเลิกสำรองอัตโนมัติแล้ว"; return
  fi
  [[ "$when" =~ ^([01]?[0-9]|2[0-3]):([0-5][0-9])$ ]] || die "รูปแบบเวลา HH:MM เช่น 02:30"
  local hh="${BASH_REMATCH[1]}" mm="${BASH_REMATCH[2]}"
  # เวลาตามนาฬิกาของเครื่อง (ดู timedatectl) · log อยู่ที่ backups/backup.log · เก็บ BACKUP_KEEP ชุดล่าสุด (ค่าเริ่มต้น 7)
  { printf '%s\n' "$current" | sed '/^$/d'
    echo "$((10#$mm)) $((10#$hh)) * * * cd '$here' && mkdir -p backups && YES=1 ./deploy.sh backup >> backups/backup.log 2>&1 $tag"
  } | crontab -
  ok "ตั้งสำรองอัตโนมัติทุกวัน $hh:$mm น. (เวลาเครื่อง $(date +%Z)) — ดู: crontab -l · log: $here/backups/backup.log"
  warn "สำรองไว้ในเครื่องเดียวกันยังไม่พอ — คัดลอก ./backups ไปเก็บนอกเครื่องเป็นประจำ (ไดรฟ์ร่วม/NAS/อีกเซิร์ฟเวอร์)"
}

cmd_make_admin() {
  need_docker; require_env
  [ -n "${1:-}" ] || die "ระบุอีเมล: ./deploy.sh make-admin <email> [--revoke]"
  $DOCKER exec pdf_backend_prod python -m scripts.make_admin "$@"
}

case "${1:-help}" in
  setup) cmd_setup ;;
  deploy) shift; cmd_deploy "$@" ;;
  rollback) shift; cmd_rollback "$@" ;;
  status) cmd_status ;;
  logs) shift; cmd_logs "$@" ;;
  backup) shift; cmd_backup "$@" ;;
  backup-schedule) shift; cmd_backup_schedule "$@" ;;
  make-admin) shift; cmd_make_admin "$@" ;;
  stop) need_docker; require_env; compose stop ;;
  start) need_docker; require_env; compose up -d && wait_healthy ;;
  -h|--help|help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "ไม่รู้จักคำสั่ง '$1' — ./deploy.sh help" ;;
esac
