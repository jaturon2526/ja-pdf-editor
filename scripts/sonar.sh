#!/usr/bin/env bash
# SonarQube บนเครื่องพัฒนา (docker-compose.sonar.yml: SonarQube Community Build + PostgreSQL)
#   scripts/sonar.sh up       เปิด SonarQube (ครั้งแรกสร้าง .env.sonar พร้อมรหัสผ่านฐานข้อมูลสุ่ม) แล้วรอจนพร้อม
#   scripts/sonar.sh scan     สแกนโค้ดตาม sonar-project.properties (ต้องใส่ SONAR_TOKEN ใน .env.sonar ก่อน)
#   scripts/sonar.sh status   สถานะ container + SonarQube
#   scripts/sonar.sh logs     ดู log ของ SonarQube
#   scripts/sonar.sh down     ปิด (ข้อมูลยังอยู่ใน volume) · down --purge = ลบข้อมูลทั้งหมดด้วย
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.sonar
URL="http://localhost:9000"

compose() { docker compose -p sonar --env-file "$ENV_FILE" -f docker-compose.sonar.yml "$@"; }

need_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "✗ Docker ยังไม่ทำงาน — เปิด Docker Desktop ก่อนแล้วลองใหม่" >&2
    exit 1
  fi
}

ensure_env() {
  if [ ! -f "$ENV_FILE" ]; then
    local pw
    pw="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 || true)"
    sed "s/^SONAR_DB_PASSWORD=.*/SONAR_DB_PASSWORD=${pw}/" .env.sonar.template >"$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "✓ สร้าง $ENV_FILE แล้ว (รหัสผ่านฐานข้อมูลสุ่ม — ห้ามเปลี่ยนหลังจากนี้)"
  fi
}

wait_ready() {
  printf "รอ SonarQube พร้อม (ครั้งแรก 1–3 นาที) "
  for _ in $(seq 1 120); do
    if curl -fsS "$URL/api/system/status" 2>/dev/null | grep -q '"status":"UP"'; then
      echo " ✓"
      return 0
    fi
    printf "."
    sleep 5
  done
  echo
  echo "✗ SonarQube ยังไม่พร้อมใน 10 นาที — ดู log: scripts/sonar.sh logs" >&2
  return 1
}

cmd="${1:-up}"
case "$cmd" in
  up)
    need_docker
    ensure_env
    compose up -d sonarqube db
    wait_ready
    echo
    echo "เปิด $URL  (ครั้งแรกเข้า admin / admin แล้วระบบให้ตั้งรหัสใหม่)"
    echo "สร้าง token: รูปบัญชี › My Account › Security › Generate Tokens (Global Analysis)"
    echo "แล้วใส่ใน $ENV_FILE บรรทัด SONAR_TOKEN=... จากนั้นรัน scripts/sonar.sh scan"
    if command -v open >/dev/null 2>&1; then open "$URL" || true; fi
    ;;
  scan)
    need_docker
    ensure_env
    token="$(grep -E '^SONAR_TOKEN=' "$ENV_FILE" | cut -d= -f2- || true)"
    if [ -z "$token" ]; then
      echo "✗ ยังไม่มี SONAR_TOKEN ใน $ENV_FILE — สร้างที่ $URL › My Account › Security แล้วใส่ก่อน" >&2
      exit 1
    fi
    [ -f backend/coverage.xml ] || echo "ℹ ไม่มี backend/coverage.xml — Coverage ฝั่ง Python จะเป็น 0% (สร้างด้วย pytest --cov=app --cov-report=xml)"
    [ -f frontend/coverage/lcov.info ] || echo "ℹ ไม่มี frontend/coverage/lcov.info — Coverage ฝั่ง JS จะเป็น 0% (สร้างด้วย npx vitest run --coverage)"
    compose up -d sonarqube db
    wait_ready
    if ! compose --profile scan run --rm scanner 2>&1 | tee sonar-scan.log; then
      echo "✗ สแกนไม่ผ่าน — ดูรายละเอียดใน sonar-scan.log (ค้นคำว่า ERROR)" >&2
      exit 1
    fi
    echo "✓ สแกนเสร็จ — ดูผลที่ $URL/dashboard?id=pdf_editor_fullstack"
    if command -v open >/dev/null 2>&1; then open "$URL/dashboard?id=pdf_editor_fullstack" || true; fi
    ;;
  status)
    need_docker
    ensure_env
    compose ps
    curl -fsS "$URL/api/system/status" 2>/dev/null && echo || echo "SonarQube ยังไม่ตอบที่ $URL"
    ;;
  logs)
    ensure_env
    compose logs --tail 200 -f sonarqube
    ;;
  down)
    ensure_env
    if [ "${2:-}" = "--purge" ]; then
      compose --profile scan down -v
      echo "✓ ปิดและลบข้อมูล SonarQube ทั้งหมดแล้ว"
    else
      compose --profile scan down
      echo "✓ ปิดแล้ว (ข้อมูลยังอยู่ · เปิดใหม่ด้วย scripts/sonar.sh up)"
    fi
    ;;
  *)
    sed -n '2,8p' "$0"
    exit 2
    ;;
esac
