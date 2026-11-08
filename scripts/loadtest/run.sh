#!/usr/bin/env bash
# scripts/loadtest/run.sh — load test เซิร์ฟเวอร์จริงจากเครื่อง Mac (ใช้ค่าเซิร์ฟเวอร์จาก scripts/deploy.env ของ ship.sh)
#
#   scripts/loadtest/run.sh                  ไล่ 10 → 25 → 50 → 100 ผู้ใช้ ขั้นละ 3 นาที
#   STAGES="10 25" STAGE_SECONDS=120 scripts/loadtest/run.sh
#
# ขั้นตอน: สร้างบัญชีทดสอบ lt0001@loadtest.invalid … บนเซิร์ฟเวอร์ (ไม่ส่งอีเมล) → เก็บสถิติ CPU/RAM ของ container ทุก 5 วินาที
#          → Locust ไล่จำนวนผู้ใช้ทีละขั้น (หยุดเองถ้าขั้นไหนช้า/พังเกินเกณฑ์) → ลบบัญชีทดสอบพร้อมไฟล์ (ทำเสมอแม้กด Ctrl+C)
# ⚠ nginx จำกัด API 50 คำขอ/วินาทีต่อ IP (frontend/nginx.conf) — เครื่องเดียวยิงได้ราว 120 ผู้ใช้จำลอง เกินนั้นจะเห็น 429
#   (ตัวเลขที่ได้คือเพดาน rate limit ไม่ใช่เพดานเซิร์ฟเวอร์) — ทดสอบมากกว่านั้นให้ยิงจากหลายเครื่อง
# ผลลัพธ์: loadtest-results/<เวลา>/ (summary.md, server-stats.csv, stage-*.html/csv) — ไม่เข้า git
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/scripts/loadtest"
CONF="$ROOT/scripts/deploy.env"
STAGES="${STAGES:-10 25 50 100}"
STAGE_SECONDS="${STAGE_SECONDS:-180}"
MAX_P95_MS="${MAX_P95_MS:-8000}"     # render page p95 เกินนี้ = ไม่ไล่ขั้นต่อ
MAX_FAIL_PCT="${MAX_FAIL_PCT:-10}"
LOCUST_VERSION="2.32.4"

c_ok=$'\033[1;32m'; c_info=$'\033[1;34m'; c_warn=$'\033[1;33m'; c_off=$'\033[0m'
step() { printf '%s==> %s%s\n' "$c_info" "$*" "$c_off"; }
ok() { printf '%s✓ %s%s\n' "$c_ok" "$*" "$c_off"; }
warn() { printf '%s! %s%s\n' "$c_warn" "$*" "$c_off" >&2; }
die() { warn "$*"; exit 1; }

[ -f "$CONF" ] || die "ไม่พบ $CONF — รัน scripts/ship.sh deploy สักครั้งเพื่อตั้งค่าเซิร์ฟเวอร์ก่อน"
# shellcheck disable=SC1090
. "$CONF"
DEPLOY_DIR="${DEPLOY_DIR:-~/pdf_editor_fullstack}"
DEPLOY_DOCKER="${DEPLOY_DOCKER:-docker}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=30)
[ -n "${DEPLOY_SSH_KEY:-}" ] && SSH_OPTS+=(-i "${DEPLOY_SSH_KEY/#\~/$HOME}")
HOST_URL="${LT_HOST:-${DEPLOY_URL:-http://${DEPLOY_SSH#*@}}}"
remote() { ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" "cd $DEPLOY_DIR && $*"; }

MAX_USERS=0
for n in $STAGES; do [ "$n" -gt "$MAX_USERS" ] && MAX_USERS=$n; done
OUT="$ROOT/loadtest-results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
echo "เป้าหมาย: $HOST_URL · ขั้น: $STAGES ผู้ใช้ · ขั้นละ ${STAGE_SECONDS}s · ผลลัพธ์: $OUT"
curl -fsS --max-time 10 "$HOST_URL/api/health" >/dev/null || die "เข้า $HOST_URL/api/health ไม่ได้"

# ---------- Locust (venv แยกในโฟลเดอร์โปรเจกต์ ไม่แตะ Python ของเครื่อง) ----------
VENV="$ROOT/.loadtest-venv"
if [ ! -x "$VENV/bin/locust" ]; then
  step "ติดตั้ง Locust $LOCUST_VERSION (ครั้งแรกครั้งเดียว)"
  python3 -m venv "$VENV" || die "สร้าง venv ไม่สำเร็จ (ต้องมี python3)"
  "$VENV/bin/pip" install -q "locust==$LOCUST_VERSION" || die "ติดตั้ง Locust ไม่สำเร็จ"
fi

# ---------- บัญชีทดสอบ + ลบเสมอเมื่อจบ ----------
LT_PASSWORD="Lt-$(openssl rand -hex 12)-9a"; export LT_PASSWORD
STATS_PID=""
cleanup() {
  [ -n "$STATS_PID" ] && kill "$STATS_PID" 2>/dev/null
  [ -n "${LT_TOKENS:-}" ] && rm -f "$LT_TOKENS"
  step "ลบบัญชีทดสอบและไฟล์บนเซิร์ฟเวอร์"
  remote "$DEPLOY_DOCKER exec -i pdf_backend_prod python - cleanup" < "$HERE/users.py" || warn "ลบบัญชีทดสอบไม่สำเร็จ — รันซ้ำ: CLEANUP_ONLY=1 scripts/loadtest/run.sh"
}
if [ "${CLEANUP_ONLY:-0}" = "1" ]; then cleanup; exit 0; fi
trap cleanup EXIT
trap 'exit 130' INT TERM

step "สร้างบัญชีทดสอบ $MAX_USERS บัญชี"
# token ของทุกบัญชี → ไฟล์ชั่วคราว (ไม่อยู่ในโฟลเดอร์ผลลัพธ์ · ลบเมื่อจบ) — ไม่ login ทีละร้อยคนจาก IP เดียว (หน้าเข้าสู่ระบบจำกัด 20 ครั้ง/นาทีต่อ IP)
LT_TOKENS="$(mktemp)"; export LT_TOKENS; chmod 600 "$LT_TOKENS"
remote "$DEPLOY_DOCKER exec -i pdf_backend_prod python - seed $MAX_USERS '$LT_PASSWORD'" < "$HERE/users.py" > "$LT_TOKENS" || die "สร้างบัญชีทดสอบไม่สำเร็จ"
echo "   ได้ token $(grep -c '^TOKEN' "$LT_TOKENS") บัญชี"

LT_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
remote "$DEPLOY_DOCKER exec pdf_backend_prod printenv BACKEND_WORKERS" > "$OUT/backend-workers.txt" 2>/dev/null || true
step "เก็บสถิติเซิร์ฟเวอร์ทุก 5 วินาที → server-stats.csv"
echo "time,container,cpu,mem" > "$OUT/server-stats.csv"
remote "while true; do t=\$(date -u +%H:%M:%S); $DEPLOY_DOCKER stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | sed \"s/^/\$t,/\"; f=\$(free -m | awk '/Mem:/ {print \$3\"MiB / \"\$2\"MiB\"}'); echo \"\$t,HOST,-,\$f\"; sleep 5; done" \
  >> "$OUT/server-stats.csv" 2>/dev/null &
STATS_PID=$!

# ---------- ไล่จำนวนผู้ใช้ ----------
for n in $STAGES; do
  rate=$(( n / 10 )); [ "$rate" -lt 1 ] && rate=1
  step "ขั้น $n ผู้ใช้ (เพิ่มทีละ $rate คน/วินาที) ${STAGE_SECONDS}s"
  echo "stage,$n,$(date -u +%H:%M:%S)" >> "$OUT/stages.csv"  # UTC ให้ตรงกับเวลาในสถิติเซิร์ฟเวอร์
  (cd "$HERE" && "$VENV/bin/locust" -f locustfile.py --headless -H "$HOST_URL" -u "$n" -r "$rate" -t "${STAGE_SECONDS}s" \
      --csv "$OUT/stage-$n" --html "$OUT/stage-$n.html" --only-summary --stop-timeout 20) 2>&1 | tail -25 | tee "$OUT/stage-$n.log"
  read -r p95 fail <<<"$("$VENV/bin/python" - "$OUT/stage-${n}_stats.csv" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
render = next((r for r in rows if r["Name"] == "render page"), None)
total = next((r for r in rows if r["Name"] == "Aggregated"), None)
p95 = int(float(render["95%"])) if render and render["95%"] not in ("", "N/A") else 0
reqs = int(total["Request Count"]) if total else 0
fails = int(total["Failure Count"]) if total else 0
print(p95, round(100 * fails / reqs, 1) if reqs else 0)
PY
)"
  echo "   render p95 = ${p95} ms · ล้มเหลว ${fail}%"
  if [ "${p95:-0}" -gt "$MAX_P95_MS" ] || awk "BEGIN{exit !(${fail:-0} > $MAX_FAIL_PCT)}"; then
    warn "ขั้น $n ผู้ใช้เกินเกณฑ์ (p95 > ${MAX_P95_MS}ms หรือล้มเหลว > ${MAX_FAIL_PCT}%) — หยุดไล่ขั้นต่อ"
    break
  fi
  sleep 20  # ให้เซิร์ฟเวอร์ปิด session ของขั้นก่อน
done

kill "$STATS_PID" 2>/dev/null; STATS_PID=""
step "ดึง error ของ backend ช่วงทดสอบ → backend-errors.log"
remote "$DEPLOY_DOCKER logs --since $LT_START pdf_backend_prod 2>&1 | grep -E -A12 'Traceback|ERROR|Exception' | tail -300" > "$OUT/backend-errors.log" 2>/dev/null || true
"$VENV/bin/python" "$HERE/summarize.py" "$OUT" | tee "$OUT/summary.md"
ok "เสร็จ — ผลลัพธ์อยู่ที่ $OUT (ส่ง summary.md ให้ Claude ดูต่อได้)"
