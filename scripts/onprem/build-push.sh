#!/usr/bin/env bash
# scripts/onprem/build-push.sh — build image สำหรับ "ติดตั้งในองค์กร" แล้ว push ขึ้น Docker Hub (รันบนเครื่อง build Ubuntu ที่มีซอร์สโค้ด)
# เครื่อง build เป็น Windows + Podman: ใช้ scripts/onprem/build-push.ps1 (ตัวเลือกและแท็กเหมือนกัน)
#
# แยกแท็กจากเว็บสาธารณะเสมอ: <repo>:onprem-v1.26.18-ab12cd3 (เวอร์ชัน-commit) + <repo>:onprem (ล่าสุด)
#   ไม่แตะ :latest / :<commit> ที่ scripts/ship.sh ใช้กับเซิร์ฟเวอร์สาธารณะ (ARM64) — สคริปต์ปฏิเสธแท็กเหล่านั้น
#
#   scripts/onprem/build-push.sh                 build backend + frontend (x86_64) → ชุดวัดผล → push → สร้างชุดไฟล์ deploy
#   scripts/onprem/build-push.sh backend         เฉพาะ backend (หรือ frontend)
#   scripts/onprem/build-push.sh kit             สร้างชุดไฟล์ deploy (dist/onprem-deploy-kit.tar.gz) อย่างเดียว
#   scripts/onprem/build-push.sh tags            แท็ก onprem ที่มีในเครื่องนี้
#
# ตัวเลือก (ตัวแปรนำหน้าคำสั่ง หรือใส่ใน scripts/onprem/build.env):
#   PLATFORM=linux/amd64        สถาปัตยกรรมของเซิร์ฟเวอร์ปลายทาง (linux/arm64 · หลายแบบคั่นด้วย , = multi-arch ต้องมี buildx)
#   BACKEND_IMAGE=docker.io/jaturon2526/pdf-editor-backend   FRONTEND_IMAGE=docker.io/jaturon2526/pdf-editor-frontend
#   TAG_PREFIX=onprem           แท็กจะเป็น <TAG_PREFIX>-v<เวอร์ชัน>-<commit> และ <TAG_PREFIX>
#   TAG=onprem-custom           ระบุแท็กเอง (แทนแท็กอัตโนมัติ)
#   GIT_PULL=1                  git pull --ff-only ก่อน build · ALLOW_DIRTY=1  build ได้แม้มีไฟล์ที่ยังไม่ commit
#   NO_PUSH=1                   build + ทดสอบอย่างเดียว · SKIP_EVAL=1  ข้ามชุดวัดผล · NO_CACHE=1  build ใหม่ทั้งหมด
#   DRY_RUN=1                   แสดงคำสั่งโดยไม่ทำจริง · YES=1  ไม่ถามยืนยัน
#
# เตรียมเครื่อง build ครั้งแรก: ติดตั้ง Docker Engine + git (+ docker-buildx-plugin ถ้า build ต่างสถาปัตยกรรม)
#   แล้ว docker login (บัญชีที่ push repository บน Docker Hub ได้ — แนะนำ Access Token แบบ Read & Write)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "ต้องรันในโฟลเดอร์ repo (git clone)"; exit 1; }
cd "$ROOT"
CONF="$ROOT/scripts/onprem/build.env"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"

PLATFORM="${PLATFORM:-linux/amd64}"
BACKEND_IMAGE="${BACKEND_IMAGE:-docker.io/jaturon2526/pdf-editor-backend}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-docker.io/jaturon2526/pdf-editor-frontend}"
TAG_PREFIX="${TAG_PREFIX:-onprem}"
CORPUS="$ROOT/test_pdf_files"
DIST="$ROOT/dist"

c_info=$'\033[1;34m'; c_ok=$'\033[1;32m'; c_warn=$'\033[1;33m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
step() { printf '%s==> %s%s\n' "$c_info" "$*" "$c_off"; }
ok()   { printf '%s✓ %s%s\n' "$c_ok" "$*" "$c_off"; }
warn() { printf '%s! %s%s\n' "$c_warn" "$*" "$c_off" >&2; }
die()  { printf '%s✗ %s%s\n' "$c_err" "$*" "$c_off" >&2; exit 1; }
run() {
  if [ "${DRY_RUN:-0}" = "1" ]; then printf '   [dry-run] %s\n' "$*"; return 0; fi
  "$@"
}
confirm() {
  [ "${YES:-0}" = "1" ] && return 0
  local a; read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy]$ ]]
}
img_of() { [ "$1" = backend ] && echo "$BACKEND_IMAGE" || echo "$FRONTEND_IMAGE"; }

app_version() {
  # เวอร์ชันที่แสดงในหน้า "เกี่ยวกับ" (frontend/src/components/AboutModal.jsx)
  grep -oE '>v[0-9]+\.[0-9]+\.[0-9]+<' frontend/src/components/AboutModal.jsx | head -1 | tr -d '<>' || true
}

check_tag() {
  local t="$1"
  [[ "$t" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "แท็ก '$t' ใช้ไม่ได้ (A-Z a-z 0-9 _ . - ยาวไม่เกิน 128)"
  [ "$t" != latest ] || die "ห้ามใช้แท็ก latest — เป็นของเว็บสาธารณะ (scripts/ship.sh)"
  [[ ! "$t" =~ ^[0-9a-f]{7,40}$ ]] || die "ห้ามใช้แท็กที่เป็นเลข commit ล้วน — ชนกับแท็ก rollback ของเว็บสาธารณะ"
}

host_platform() {
  case "$(uname -m)" in
    x86_64|amd64) echo linux/amd64 ;;
    aarch64|arm64) echo linux/arm64 ;;
    *) echo "linux/$(uname -m)" ;;
  esac
}

# ---------- build + push ----------
build_push() {
  local target="${1:-all}" svcs s
  case "$target" in
    all) svcs="backend frontend" ;;
    backend|frontend) svcs="$target" ;;
    *) die "ไม่รู้จัก '$target' (all | backend | frontend | kit | tags)" ;;
  esac
  command -v docker >/dev/null || die "ไม่พบ docker — ติดตั้ง Docker Engine ก่อน"
  docker info >/dev/null 2>&1 || die "เรียก docker ไม่ได้ — เพิ่มผู้ใช้เข้ากลุ่ม docker (sudo usermod -aG docker \$USER แล้ว login ใหม่) หรือรันด้วย sudo"

  if [ "${GIT_PULL:-0}" = "1" ]; then
    step "git pull"
    run git pull -q --ff-only || die "git pull ไม่สำเร็จ"
  fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no
    [ "${ALLOW_DIRTY:-0}" = "1" ] || die "มีไฟล์ที่แก้แต่ยังไม่ commit — commit/stash ก่อน หรือ ALLOW_DIRTY=1 (แท็กจะติด -dirty)"
  fi

  local sha version tag dirty=""
  sha="$(git rev-parse --short=7 HEAD)"
  version="$(app_version)"; version="${version:-v0.0.0}"
  [ -n "$(git status --porcelain --untracked-files=no)" ] && dirty="-dirty"
  tag="${TAG:-$TAG_PREFIX-$version-$sha$dirty}"
  check_tag "$tag"; check_tag "$TAG_PREFIX"

  local multi=0 native=1
  [[ "$PLATFORM" == *,* ]] && multi=1
  [ "$PLATFORM" = "$(host_platform)" ] || native=0
  if [ "$native" = 0 ]; then
    docker buildx version >/dev/null 2>&1 || die "build $PLATFORM บนเครื่อง $(host_platform) ต้องใช้ buildx (sudo apt install docker-buildx-plugin) + QEMU (docker run --privileged --rm tonistiigi/binfmt --install all)"
  fi
  [ "$multi" = 1 ] && [ "${NO_PUSH:-0}" = "1" ] && die "multi-arch ($PLATFORM) ต้อง push ตรง — ใช้ NO_PUSH=1 ไม่ได้"

  echo "จะ build: $svcs  ·  commit $sha ($(git log -1 --format=%s))"
  echo "  แพลตฟอร์ม: $PLATFORM  ·  แท็ก: $tag และ $TAG_PREFIX"
  for s in $svcs; do echo "  $(img_of "$s"):$tag"; done
  [ "${NO_PUSH:-0}" = "1" ] && echo "  (NO_PUSH=1 — ไม่ push)"
  confirm "ดำเนินการต่อ?" || die "ยกเลิก"

  local labels=(--label "org.opencontainers.image.revision=$(git rev-parse HEAD)"
                --label "org.opencontainers.image.version=$version"
                --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                --label "ja.pdf-editor.channel=$TAG_PREFIX")
  local cache=(); [ "${NO_CACHE:-0}" = "1" ] && cache=(--no-cache)

  if [ "$multi" = 1 ]; then
    # หลายสถาปัตยกรรม: buildx push ตรงจาก builder (โหลดเข้าเครื่องเพื่อทดสอบไม่ได้)
    warn "multi-arch: ข้ามชุดวัดผลในเครื่อง (ทดสอบด้วย NO_PUSH=1 PLATFORM=<แบบเดียว> ก่อนได้)"
    for s in $svcs; do
      step "buildx $s ($PLATFORM) → push"
      run docker buildx build --platform "$PLATFORM" "${cache[@]}" "${labels[@]}" \
        -t "$(img_of "$s"):$tag" -t "$(img_of "$s"):$TAG_PREFIX" --push "./$s"
    done
  else
    for s in $svcs; do
      step "build $s ($PLATFORM)"
      if [ "$native" = 1 ]; then
        run docker build --platform "$PLATFORM" "${cache[@]}" "${labels[@]}" -t "$(img_of "$s"):$tag" "./$s"
      else
        run docker buildx build --platform "$PLATFORM" "${cache[@]}" "${labels[@]}" -t "$(img_of "$s"):$tag" --load "./$s"
      fi
      run docker tag "$(img_of "$s"):$tag" "$(img_of "$s"):$TAG_PREFIX"
    done
    smoke_test "$svcs" "$tag"
    if [ "${NO_PUSH:-0}" != "1" ]; then
      for s in $svcs; do
        step "push $(img_of "$s"):$tag และ :$TAG_PREFIX"
        run docker push -q "$(img_of "$s"):$tag" || die "push ไม่สำเร็จ — docker login แล้วหรือยัง / บัญชีมีสิทธิ์เขียน repository นี้ไหม"
        run docker push -q "$(img_of "$s"):$TAG_PREFIX"
      done
    fi
  fi

  [ "${DRY_RUN:-0}" = "1" ] || printf '%s\n' "$tag" > "$ROOT/scripts/onprem/.last-tag"
  make_kit "$tag"
  ok "เสร็จ: แท็ก $tag"
  if [ "${NO_PUSH:-0}" != "1" ]; then
    echo
    echo "บนเซิร์ฟเวอร์ในองค์กร:"
    echo "  ./deploy.sh deploy $tag        (หรือ ./deploy.sh deploy $TAG_PREFIX = ล่าสุดเสมอ)"
    [ "$svcs" = "backend frontend" ] || warn "build แค่ $svcs — แท็ก $tag ของอีกส่วนไม่มี: deploy ด้วยแท็ก $TAG_PREFIX แทน"
  fi
}

smoke_test() {
  local svcs="$1" tag="$2"
  if [[ " $svcs " == *" backend "* ]]; then
    step "ทดสอบ backend: import ไลบรารีหลัก + Ghostscript/LibreOffice/Tesseract"
    run docker run --rm "$BACKEND_IMAGE:$tag" sh -c \
      'python -c "import fitz, pikepdf, pyhanko, fpdf, app.main" && gs --version && soffice --version >/dev/null && tesseract --list-langs 2>/dev/null | grep -q tha' \
      || die "image backend ใช้งานไม่ได้ — ยังไม่ได้ push"
    if [ "${SKIP_EVAL:-0}" = "1" ]; then
      warn "SKIP_EVAL=1 — ข้ามชุดวัดผล"
    else
      step "ชุดวัดผล scan_eval (แปลงไฟล์สแกนเป็น Word — เอกสารสังเคราะห์)"
      run docker run --rm "$BACKEND_IMAGE:$tag" python -m scripts.scan_eval --check \
        || die "ชุดวัดผลไม่ผ่าน — ยังไม่ได้ push (ข้ามได้ด้วย SKIP_EVAL=1 ถ้าแน่ใจ)"
      if [ -d "$CORPUS" ]; then
        step "ชุดวัดผล thai_eval กับ test_pdf_files/"
        run docker run --rm -v "$CORPUS:/corpus:ro" "$BACKEND_IMAGE:$tag" python -m scripts.thai_eval /corpus --check \
          || die "ชุดวัดผล thai_eval ไม่ผ่าน — ยังไม่ได้ push"
      fi
    fi
  fi
  if [[ " $svcs " == *" frontend "* ]]; then
    step "ทดสอบ frontend: มีหน้าเว็บและคู่มือ"
    run docker run --rm --entrypoint sh "$FRONTEND_IMAGE:$tag" -c \
      'test -s /usr/share/nginx/html/index.html && test -s /usr/share/nginx/html/manual.html' \
      || die "image frontend ไม่สมบูรณ์ — ยังไม่ได้ push"
  fi
}

# ---------- ชุดไฟล์สำหรับเซิร์ฟเวอร์ (ไม่ต้องมีซอร์สโค้ดบนเซิร์ฟเวอร์) ----------
make_kit() {
  local tag="${1:-}" tmp out
  [ -n "$tag" ] || tag="$(cat "$ROOT/scripts/onprem/.last-tag" 2>/dev/null || echo "$TAG_PREFIX")"
  step "สร้างชุดไฟล์ deploy"
  out="$DIST/onprem-deploy-kit.tar.gz"
  if [ "${DRY_RUN:-0}" = "1" ]; then echo "   [dry-run] $out"; return 0; fi
  mkdir -p "$DIST"
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/pdf-editor/deploy/onprem"
  cp docker-compose.prod.yml docker-compose.onprem-tls.yml "$tmp/pdf-editor/"
  cp deploy/onprem/nginx-tls.conf "$tmp/pdf-editor/deploy/onprem/"
  cp scripts/onprem/deploy.sh "$tmp/pdf-editor/deploy.sh"
  chmod +x "$tmp/pdf-editor/deploy.sh"
  # template พร้อมชื่อ image/แท็กที่เพิ่ง build (แก้ค่าอื่นต่อบนเซิร์ฟเวอร์)
  sed -e "s#^IMAGE_TAG=.*#IMAGE_TAG=$tag#" \
      -e "s#^BACKEND_IMAGE=.*#BACKEND_IMAGE=$BACKEND_IMAGE#" \
      -e "s#^FRONTEND_IMAGE=.*#FRONTEND_IMAGE=$FRONTEND_IMAGE#" \
      .env.onprem.template > "$tmp/pdf-editor/.env.onprem.template"
  cat > "$tmp/pdf-editor/README.txt" <<TXT
JA PDF Editor — ชุดไฟล์ติดตั้งในองค์กร (on-premise)
image: $BACKEND_IMAGE / $FRONTEND_IMAGE  แท็ก: $tag
สร้างจาก commit $(git rev-parse --short=7 HEAD) เมื่อ $(date '+%Y-%m-%d %H:%M')

1. tar xzf onprem-deploy-kit.tar.gz && cd pdf-editor
2. ./deploy.sh setup        ตรวจเครื่อง + สร้าง .env.prod จาก template → แก้ค่า <...> ใน .env.prod
3. วางไฟล์ลับใน ./secrets  (tls/fullchain.pem, tls/privkey.pem, seal.p12 ...) — ดูใน .env.prod
4. ./deploy.sh deploy       ดึง image แท็กใน .env.prod แล้วเปิดระบบ
คำสั่งอื่น: ./deploy.sh help
คู่มือเต็ม: README.md ใน repository หัวข้อ "ติดตั้งในองค์กร (On-premise)"
TXT
  tar czf "$out" -C "$tmp" pdf-editor
  rm -rf "$tmp"
  ok "ชุดไฟล์: $out  (คัดลอกไปเซิร์ฟเวอร์: scp $out user@server:~/)"
}

list_tags() {
  docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.CreatedSince}}\t{{.Size}}' \
    | grep -E "^($BACKEND_IMAGE|$FRONTEND_IMAGE|${BACKEND_IMAGE#docker.io/}|${FRONTEND_IMAGE#docker.io/}):$TAG_PREFIX" || echo "(ยังไม่มีแท็ก $TAG_PREFIX ในเครื่องนี้)"
}

case "${1:-all}" in
  all|backend|frontend) build_push "${1:-all}" ;;
  kit) make_kit "${2:-}" ;;
  tags) list_tags ;;
  -h|--help|help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "ไม่รู้จักคำสั่ง '$1' — ดู scripts/onprem/build-push.sh help" ;;
esac
