#!/usr/bin/env bash
# scripts/ship.sh — ส่งงานจาก git bundle ที่ Claude เตรียมไว้ ขึ้น GitHub แล้ว deploy บนเซิร์ฟเวอร์
#
# รันบน Mac จากที่ไหนก็ได้ในโฟลเดอร์ repo:
#   scripts/ship.sh pr      [ไฟล์.bundle]   push branch จาก bundle + เปิด PR ด้วย gh
#   scripts/ship.sh merge   [branch]        รอ CI ผ่าน → merge PR → อัปเดต main → ลบ branch + bundle (ลบไม่สำเร็จแค่เตือน)
#   scripts/ship.sh deploy  [auto|backend|frontend|all]
#                                            docker build (linux/arm64) → ชุดวัดผล thai_eval กับ test_pdf_files/ และ
#                                            scan_eval (ถ้ามี backend) → push Docker Hub → เซิร์ฟเวอร์ pull + up -d → log + /api/health
#                                            (auto = เฉพาะส่วนที่เปลี่ยนตั้งแต่ deploy ครั้งก่อน)
#   scripts/ship.sh all     [ไฟล์.bundle]   pr → merge → deploy auto ในคำสั่งเดียว (รันซ้ำได้: ถ้า merge แล้วจะข้ามไป deploy)
#   scripts/ship.sh status                  ดูว่าเซิร์ฟเวอร์รัน commit ไหนอยู่ + สถานะ container
#   scripts/ship.sh rollback <backend|frontend> <commit>
#                                            ย้อนเซิร์ฟเวอร์ไปใช้ image ของ commit ก่อนหน้า (ทุก deploy ติด tag ตาม commit ไว้)
#   scripts/ship.sh cleanup                 ลบ branch ที่ merge เข้า main แล้ว (บน GitHub + ในเครื่อง) และไฟล์ .bundle ที่ใช้แล้ว
#                                            (branch ที่ยังไม่ merge ไม่แตะ — แสดงรายการให้ดูเฉย ๆ)
#   scripts/ship.sh local   [ไฟล์.bundle]   ทดลองบน Docker ในเครื่องก่อน deploy: build จาก bundle (ใน .local-test/ ไม่แตะ main,
#                                            ไม่ push) แล้วเปิด http://localhost:18080 พร้อมผู้ใช้ทดลอง · ไม่ระบุ bundle = โค้ดปัจจุบัน
#   scripts/ship.sh local-down [--wipe]     ปิดระบบทดลอง (--wipe ลบข้อมูลทดลองด้วย)
#
# ตัวเลือก: DRY_RUN=1 scripts/ship.sh ...   แสดงคำสั่งที่จะรัน (git push / gh / docker / ssh) โดยไม่ทำจริง
#          YES=1     ไม่ถามยืนยัน · SKIP_EVAL=1  ข้ามชุดวัดผล thai_eval
#
# ตั้งค่าเซิร์ฟเวอร์ครั้งแรก: สคริปต์จะถามแล้วบันทึกไว้ที่ scripts/deploy.env (ไม่เข้า git) — แก้ทีหลังได้
set -euo pipefail
export GH_PAGER=cat   # gh ไม่เปิด pager ค้างรอกด q

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "ต้องรันในโฟลเดอร์ repo"; exit 1; }
cd "$ROOT"
CONF="$ROOT/scripts/deploy.env"
BASE_BRANCH="main"
IMG_BACKEND="docker.io/jaturon2526/pdf-editor-backend"
IMG_FRONTEND="docker.io/jaturon2526/pdf-editor-frontend"
CORPUS="$ROOT/test_pdf_files"   # ไฟล์ทดสอบจริง (ไม่เข้า git) + expected.json

# ---------- helpers ----------
c_info=$'\033[1;34m'; c_ok=$'\033[1;32m'; c_warn=$'\033[1;33m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
step() { printf '%s==> %s%s\n' "$c_info" "$*" "$c_off"; }
ok()   { printf '%s✓ %s%s\n' "$c_ok" "$*" "$c_off"; }
warn() { printf '%s! %s%s\n' "$c_warn" "$*" "$c_off" >&2; }
die()  { printf '%s✗ %s%s\n' "$c_err" "$*" "$c_off" >&2; exit 1; }
# run: คำสั่งที่มีผลภายนอก (push, gh, docker, ssh) — DRY_RUN=1 แค่พิมพ์
run() {
  if [ "${DRY_RUN:-0}" = "1" ]; then printf '   [dry-run] %s\n' "$*"; return 0; fi
  "$@"
}
need() { command -v "$1" >/dev/null 2>&1 || die "ไม่พบคำสั่ง $1 — $2"; }
confirm() {
  [ "${YES:-0}" = "1" ] && return 0
  local a; read -r -p "$1 [y/N] " a; case "$a" in y|Y|yes) return 0;; *) return 1;; esac
}

# retry: คำสั่งที่ต้องคุยกับ GitHub — เน็ตกระตุก (timeout, can't assign requested address) ลองใหม่สูงสุด 3 ครั้ง
retry() {
  local n=0
  until "$@"; do
    n=$((n+1))
    [ $n -gt 3 ] && return 1
    warn "คำสั่งไม่สำเร็จ (เน็ตหลุด?) — ลองใหม่ครั้งที่ $n/3 ใน $((n * 5)) วินาที"
    sleep $((n * 5))
  done
}

# wait_ci: รอทุก check ของ PR จบ — "ไม่ผ่าน" เฉพาะเมื่อมี check ที่ fail จริง
# (เดิมใช้ gh pr checks --watch ซึ่งคืน error เหมือนกันทั้งตอน CI fail และตอนเน็ตหลุด → สคริปต์บอก CI ไม่ผ่านผิด ๆ)
wait_ci() {
  local br="$1" out last="" errors=0 attempt=1 cancelled i waited=0
  while :; do
    if out="$(gh pr checks "$br" --json bucket -q '[.[].bucket] | join(" ")' 2>/dev/null)"; then
      errors=0
    else
      # gh pr checks คืนค่าไม่ใช่ 0 ตอนมี check pending/fail ด้วย — ถ้าได้ผลลัพธ์ JSON มาถือว่าคุยกับ GitHub ได้
      if [ -z "$out" ]; then
        errors=$((errors + 1))
        if [ $errors -gt 6 ]; then die "ติดต่อ GitHub ไม่ได้ติดต่อกันหลายครั้ง — ดูสถานะเอง: gh pr checks $br --web แล้วรัน scripts/ship.sh merge $br"; fi
        warn "อ่านสถานะ CI ไม่ได้ (เน็ตหลุด?) — ลองใหม่ ($errors/6)"
        sleep 10; continue
      fi
      errors=0
    fi
    if [ -z "$out" ]; then          # check ยังไม่ขึ้นหลัง push
      waited=$((waited + 1)); [ $waited -gt 12 ] && die "ไม่พบ check ของ PR นี้ — ดู: gh pr checks $br --web"
      sleep 5; continue
    fi
    local pass=0 pending=0 fail=0 cancel=0
    for i in $out; do
      case "$i" in pass|skipping) pass=$((pass + 1));; pending) pending=$((pending + 1));; fail) fail=$((fail + 1));; cancel) cancel=$((cancel + 1));; esac
    done
    local summary="ผ่าน $pass · รอ $pending · ไม่ผ่าน $fail · ยกเลิก $cancel"
    [ "$summary" != "$last" ] && printf '   %s\n' "$summary" && last="$summary"
    if [ $fail -gt 0 ]; then die "CI ไม่ผ่าน — ดูรายละเอียด: gh pr checks $br --web"; fi
    if [ $cancel -gt 0 ] && [ $pending -eq 0 ]; then
      # CI ตั้ง cancel-in-progress บน main: merge ต่อกันเร็ว ๆ รอบเก่าถูกยกเลิก (ไม่ใช่เทสต์พัง) → rerun ให้เองหนึ่งรอบ
      [ $attempt -gt 1 ] && die "CI ถูกยกเลิกซ้ำ — ดู: gh pr checks $br --web"
      cancelled="$(gh run list --branch "$br" --limit 20 --json databaseId,conclusion,headSha \
        -q "map(select(.headSha==\"$(git rev-parse "$br")\" and .conclusion==\"cancelled\")) | .[].databaseId" 2>/dev/null || true)"
      warn "มี check ถูกยกเลิก (cancelled) — สั่ง gh run rerun ให้: $(echo $cancelled)"
      for i in $cancelled; do retry gh run rerun "$i" || true; done
      attempt=$((attempt + 1)); last=""; sleep 20; continue
    fi
    [ $pending -eq 0 ] && return 0
    sleep 20
  done
}

require_clean() {
  # ไฟล์ที่ยังไม่ commit (ไม่นับไฟล์ untracked เช่น .bundle) จะทำให้ checkout/pull พัง
  if ! git diff --quiet || ! git diff --cached --quiet; then
    git status --short | grep -v '^??' >&2 || true
    die "มีไฟล์แก้ไขที่ยังไม่ commit — commit หรือ git stash ก่อน"
  fi
}

update_main() {
  require_clean
  step "อัปเดต $BASE_BRANCH"
  [ "$(git branch --show-current)" = "$BASE_BRANCH" ] || git checkout -q "$BASE_BRANCH"
  git pull -q --ff-only origin "$BASE_BRANCH"
  ok "$BASE_BRANCH อยู่ที่ $(git log -1 --format='%h %s')"
}

pick_bundle() {
  if [ -n "${1:-}" ]; then [ -f "$1" ] || die "ไม่พบไฟล์ $1"; echo "$1"; return; fi
  local b; b="$(ls -t ./*.bundle 2>/dev/null | head -1 || true)"
  [ -n "$b" ] || die "ไม่พบไฟล์ .bundle ในโฟลเดอร์ repo — ระบุชื่อไฟล์: scripts/ship.sh pr <ไฟล์.bundle>"
  echo "$b"
}

bundle_branch() {
  # คืนชื่อ branch แรกใน bundle (Claude ส่งมาทีละ branch)
  git bundle list-heads "$1" | awk '$2 ~ /^refs\/heads\// {sub("refs/heads/","",$2); print $2; exit}'
}

# ---------- pr ----------
cmd_pr() {
  need gh "ติดตั้ง: brew install gh แล้ว gh auth login"
  local bundle br url
  bundle="$(pick_bundle "${1:-}")"
  update_main
  step "ตรวจ bundle $bundle"
  git bundle verify -q "$bundle" >/dev/null 2>&1 || die "bundle ใช้ไม่ได้กับ repo นี้ (ต้องการ commit ที่ main ในเครื่องยังไม่มี?) — ลอง git pull แล้วรันใหม่"
  br="$(bundle_branch "$bundle")"
  [ -n "$br" ] || die "ไม่พบ branch ใน bundle"
  [ "$br" != "$BASE_BRANCH" ] || die "bundle นี้เป็น $BASE_BRANCH ไม่ใช่ branch งาน"
  # -f: ถ้า Claude ส่ง bundle แก้ไขรอบใหม่ของ branch เดิมมา ให้ทับของเดิม (branch ไม่ได้ checkout อยู่)
  git fetch -q -f "$bundle" "refs/heads/$br:refs/heads/$br"
  ok "branch $br: $(git log -1 --format='%h %s' "$br")"
  if [ -z "$(git rev-list "$BASE_BRANCH..$br")" ]; then
    # รันซ้ำหลังรอบก่อน merge แล้วแต่หยุดกลางทาง (เช่น ลบ branch บน GitHub ไม่สำเร็จ) — ไม่ต้อง push/เปิด PR อีก
    warn "branch $br ถูก merge เข้า $BASE_BRANCH แล้ว — ข้ามการ push/เปิด PR"
    ALREADY_MERGED=1; LAST_BRANCH="$br"; LAST_BUNDLE="$bundle"
    return 0
  fi
  git log --oneline "$BASE_BRANCH..$br"

  step "push $br"
  run git push -q -f -u origin "$br"

  if url="$(gh pr view "$br" --json url,state -q 'select(.state=="OPEN") | .url' 2>/dev/null)" && [ -n "$url" ]; then
    ok "มี PR อยู่แล้ว (อัปเดตด้วย push นี้): $url"
  else
    step "เปิด PR"
    # --fill: ใช้หัวข้อ/เนื้อหาจาก commit (Claude เขียนรายละเอียดไว้ใน commit message แล้ว)
    run gh pr create --base "$BASE_BRANCH" --head "$br" --fill
    [ "${DRY_RUN:-0}" = "1" ] || ok "เปิด PR แล้ว: $(gh pr view "$br" --json url -q .url)"
  fi
  LAST_BRANCH="$br"; LAST_BUNDLE="$bundle"
}

# ---------- merge ----------
cmd_merge() {
  need gh "ติดตั้ง: brew install gh แล้ว gh auth login"
  local br="${1:-${LAST_BRANCH:-}}"
  if [ -z "$br" ]; then
    br="$(gh pr list --author @me --state open --json headRefName -q '.[0].headRefName')"
    [ -n "$br" ] || die "ไม่พบ PR ที่เปิดอยู่ — ระบุ branch: scripts/ship.sh merge <branch>"
  fi
  if [ "${ALREADY_MERGED:-0}" = "1" ]; then
    ok "merge แล้ว — เก็บกวาด branch/bundle"
    cleanup_branch "$br"
    return 0
  fi
  local num; num="$(retry gh pr view "$br" --json number -q .number)" || die "ติดต่อ GitHub ไม่ได้ — ลองรันใหม่"
  step "รอ CI ของ PR #$num ($br)"
  if [ "${DRY_RUN:-0}" != "1" ]; then
    wait_ci "$br"
  fi
  ok "CI ผ่าน"
  step "merge PR #$num"
  # ไม่ใช้ --delete-branch: ถ้าลบ branch บน GitHub ไม่สำเร็จ (network timeout) gh จะคืนค่า error ทั้งที่ merge แล้ว
  # และสคริปต์หยุดก่อน deploy — ลบเองใน cleanup_branch แบบไม่หยุดสคริปต์แทน
  if ! retry run gh pr merge "$br" --merge; then
    # เน็ตหลุดตอนตอบกลับ: merge อาจสำเร็จไปแล้ว — ดูสถานะจริงก่อนตัดสิน
    [ "$(retry gh pr view "$br" --json state -q .state 2>/dev/null)" = "MERGED" ] || die "merge PR #$num ไม่สำเร็จ"
  fi
  ok "merge PR #$num แล้ว"
  cleanup_branch "$br"
}

cleanup_branch() {
  # ลบ branch งาน (GitHub + ในเครื่อง) และ bundle — ไม่สำเร็จแค่เตือน ไม่หยุดสคริปต์
  local br="$1"
  update_main
  if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
    if run git push -q origin --delete "$br"; then ok "ลบ branch $br บน GitHub แล้ว"
    else warn "ลบ branch $br บน GitHub ไม่สำเร็จ — ลบทีหลังด้วย: git push origin --delete $br"; fi
  fi
  if git show-ref --verify -q "refs/heads/$br"; then run git branch -q -D "$br" || warn "ลบ branch $br ในเครื่องไม่สำเร็จ"; fi
  local b="${LAST_BUNDLE:-}"
  if [ -z "$b" ]; then b="$(ls -t ./*.bundle 2>/dev/null | while read -r f; do [ "$(bundle_branch "$f")" = "$br" ] && echo "$f" && break; done || true)"; fi
  if [ -n "$b" ] && [ -f "$b" ]; then run rm -f "$b"; ok "ลบ $b แล้ว"; fi
}

# ---------- deploy config ----------
load_conf() {
  if [ ! -f "$CONF" ]; then
    warn "ยังไม่มี $CONF — ตั้งค่าเซิร์ฟเวอร์ครั้งแรก (Enter = ใช้ค่าในวงเล็บ)"
    local h k d u s
    read -r -p "SSH ปลายทาง เช่น ubuntu@1.2.3.4 หรือชื่อ Host ใน ~/.ssh/config: " h
    read -r -p "ไฟล์ SSH key (เว้นว่างถ้ากำหนดใน ~/.ssh/config แล้ว): " k
    read -r -p "โฟลเดอร์บนเซิร์ฟเวอร์ที่มี docker-compose.prod.yml และ .env.prod [~/pdf_editor_fullstack]: " d
    read -r -p "URL เว็บ (ไม่มี / ท้าย) เช่น https://pdf.example.com: " u
    read -r -p "คำสั่ง docker บนเซิร์ฟเวอร์ [docker] (ใส่ 'sudo docker' ถ้าต้องใช้ sudo): " s
    [ -n "$h" ] || die "ต้องระบุ SSH ปลายทาง"
    cat > "$CONF" <<CONF
# ตั้งค่า deploy ของ scripts/ship.sh (ไฟล์นี้ไม่เข้า git)
DEPLOY_SSH="$h"
DEPLOY_SSH_KEY="$k"
DEPLOY_DIR="${d:-~/pdf_editor_fullstack}"
DEPLOY_URL="$u"
DEPLOY_DOCKER="${s:-docker}"
# สถาปัตยกรรมของเซิร์ฟเวอร์ (Oracle Ampere A1 = arm64)
DEPLOY_PLATFORM="linux/arm64"
CONF
    ok "บันทึก $CONF แล้ว"
  fi
  # shellcheck disable=SC1090
  . "$CONF"
  DEPLOY_DIR="${DEPLOY_DIR:-~/pdf_editor_fullstack}"
  DEPLOY_DOCKER="${DEPLOY_DOCKER:-docker}"
  DEPLOY_PLATFORM="${DEPLOY_PLATFORM:-linux/arm64}"
  SSH_OPTS=(-o ConnectTimeout=15)
  [ -n "${DEPLOY_SSH_KEY:-}" ] && SSH_OPTS+=(-i "${DEPLOY_SSH_KEY/#\~/$HOME}")
  # ติดตั้งในองค์กรที่ใช้ HTTPS ผ่าน docker-compose.onprem-tls.yml: ตั้ง DEPLOY_COMPOSE_EXTRA="docker-compose.onprem-tls.yml" ใน deploy.env
  COMPOSE_REMOTE="$DEPLOY_DOCKER compose -f docker-compose.prod.yml${DEPLOY_COMPOSE_EXTRA:+ -f $DEPLOY_COMPOSE_EXTRA} --env-file .env.prod"
}

# remote: รันคำสั่งบนเซิร์ฟเวอร์ในโฟลเดอร์ DEPLOY_DIR
remote() { run ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" "cd $DEPLOY_DIR && $*"; }
remote_read() { ssh "${SSH_OPTS[@]}" "$DEPLOY_SSH" "cd $DEPLOY_DIR && $*"; }

img_of() { [ "$1" = backend ] && echo "$IMG_BACKEND" || echo "$IMG_FRONTEND"; }

health_check() {
  [ -n "${DEPLOY_URL:-}" ] || { warn "ไม่ได้ตั้ง DEPLOY_URL — ข้ามการตรวจ health"; return 0; }
  [ "${DRY_RUN:-0}" = "1" ] && { echo "   [dry-run] curl $DEPLOY_URL/api/health"; return 0; }
  step "ตรวจ $DEPLOY_URL/api/health"
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 5 "$DEPLOY_URL/api/health" >/dev/null 2>&1; then ok "เว็บตอบปกติ"; return 0; fi
    sleep 3
  done
  warn "เว็บยังไม่ตอบหลัง 90 วินาที — log ล่าสุดของ backend:"
  remote_read "$DEPLOY_DOCKER logs --tail 30 pdf_backend_prod" || true
  return 1
}

# ---------- deploy ----------
cmd_deploy() {
  local target="${1:-auto}" svcs="" s sha prev
  case "$target" in auto|backend|frontend|all) ;; *) die "ใช้: scripts/ship.sh deploy [auto|backend|frontend|all]";; esac
  need docker "เปิด Docker Desktop ก่อน"
  load_conf
  update_main
  git fetch -q origin "$BASE_BRANCH"
  [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$BASE_BRANCH")" ] || die "main ในเครื่องไม่ตรงกับ origin/main — deploy ได้เฉพาะโค้ดที่ merge แล้ว"
  sha="$(git rev-parse --short=12 HEAD)"

  if [ "$target" = auto ]; then
    step "หาส่วนที่เปลี่ยนตั้งแต่ deploy ครั้งก่อน"
    for s in backend frontend; do
      prev="$(remote_read "cat .deployed-$s 2>/dev/null" 2>/dev/null || true)"
      if [ -z "$prev" ] || ! git cat-file -e "$prev^{commit}" 2>/dev/null; then
        echo "   $s: ไม่มีบันทึก deploy ก่อนหน้า → deploy"; svcs="$svcs $s"
      elif [ -n "$(git diff --name-only "$prev" HEAD -- "$s/")" ]; then
        echo "   $s: เปลี่ยน $(git diff --name-only "$prev" HEAD -- "$s/" | wc -l | tr -d ' ') ไฟล์ตั้งแต่ ${prev:0:12} → deploy"; svcs="$svcs $s"
      else
        echo "   $s: ไม่เปลี่ยนตั้งแต่ ${prev:0:12} → ข้าม"
      fi
    done
  elif [ "$target" = all ]; then svcs="backend frontend"
  else svcs="$target"
  fi
  svcs="${svcs# }"
  [ -n "$svcs" ] || { ok "ไม่มีอะไรต้อง deploy"; return 0; }

  if [[ " $svcs " == *" frontend "* ]] && [ ! -f frontend/.env ]; then
    warn "ไม่พบ frontend/.env — ค่า VITE_* ถูกฝังตอน build image (เช่น Google Client ID) ถ้าไม่มี ฟีเจอร์นั้นจะใช้ไม่ได้"
    confirm "build frontend ต่อโดยไม่มี frontend/.env?" || die "ยกเลิก"
  fi
  echo "จะ deploy: $svcs @ $sha ($(git log -1 --format=%s))  →  $DEPLOY_SSH:$DEPLOY_DIR"
  confirm "ดำเนินการต่อ?" || die "ยกเลิก"

  step "build image ($DEPLOY_PLATFORM)"
  for s in $svcs; do
    run docker build --platform "$DEPLOY_PLATFORM" -t "$(img_of "$s"):latest" "./$s"
  done

  if [[ " $svcs " == *" backend "* ]]; then
    if [ "${SKIP_EVAL:-0}" = "1" ]; then
      warn "SKIP_EVAL=1 — ข้ามชุดวัดผล thai_eval"
    elif [ ! -d "$CORPUS" ]; then
      warn "ไม่พบ $CORPUS — ข้ามชุดวัดผล thai_eval"
    else
      step "ชุดวัดผล thai_eval กับ test_pdf_files/ (ต้อง issues = 0 และเซ็นเซอร์เจอครบทุกคำ)"
      run docker run --rm -v "$CORPUS:/corpus:ro" "$IMG_BACKEND:latest" python -m scripts.thai_eval /corpus --check \
        || die "ชุดวัดผลไม่ผ่าน — ยังไม่ได้ push image (ข้ามได้ด้วย SKIP_EVAL=1 ถ้าแน่ใจ)"
    fi
    if [ "${SKIP_EVAL:-0}" != "1" ]; then
      step "ชุดวัดผล scan_eval (แปลงไฟล์สแกนเป็น Word — เอกสารสังเคราะห์ ไม่ต้องใช้ไฟล์จริง)"
      run docker run --rm "$IMG_BACKEND:latest" python -m scripts.scan_eval --check \
        || die "ชุดวัดผลไฟล์สแกนไม่ผ่าน — ยังไม่ได้ push image (ข้ามได้ด้วย SKIP_EVAL=1 ถ้าแน่ใจ)"
    fi
  fi

  step "push ขึ้น Docker Hub (:latest และ :$sha สำหรับ rollback)"
  for s in $svcs; do
    run docker tag "$(img_of "$s"):latest" "$(img_of "$s"):$sha"
    run docker push -q "$(img_of "$s"):latest"
    run docker push -q "$(img_of "$s"):$sha"
  done

  step "เซิร์ฟเวอร์: pull + up -d"
  # git pull เพื่อให้ docker-compose.prod.yml บนเซิร์ฟเวอร์ตรงกับ main (ถ้าโฟลเดอร์นั้นเป็น git clone)
  remote "if [ -d .git ]; then git pull -q --ff-only || echo '! git pull บนเซิร์ฟเวอร์ไม่สำเร็จ — ใช้ compose file เดิม'; fi"
  remote "$COMPOSE_REMOTE pull -q $svcs && $COMPOSE_REMOTE up -d $svcs && $DEPLOY_DOCKER image prune -f >/dev/null"

  local hc=0; health_check || hc=1
  if [[ " $svcs " == *" backend "* ]] && [ $hc -eq 0 ]; then
    step "log ล่าสุดของ backend"
    remote "sleep 3; $DEPLOY_DOCKER logs --tail 30 pdf_backend_prod 2>&1" || true
  fi
  if [ $hc -eq 0 ]; then
    for s in $svcs; do remote "echo $(git rev-parse HEAD) > .deployed-$s"; done
    ok "deploy เสร็จ: $svcs @ $sha"
  else
    die "deploy แล้วแต่เว็บไม่ตอบ — ตรวจ log ด้านบน (ย้อนกลับ: scripts/ship.sh rollback <backend|frontend> <commit ก่อนหน้า>)"
  fi
}

cmd_status() {
  load_conf
  local s v
  for s in backend frontend; do
    v="$(remote_read "cat .deployed-$s 2>/dev/null" 2>/dev/null || true)"
    if [ -n "$v" ]; then echo "$s: ${v:0:12} $(git log -1 --format=%s "$v" 2>/dev/null || echo '(ไม่พบ commit ในเครื่อง)')"
    else echo "$s: (ยังไม่เคย deploy ด้วยสคริปต์นี้)"; fi
  done
  remote_read "$COMPOSE_REMOTE ps --format 'table {{.Name}}\t{{.Status}}'"
}

cmd_rollback() {
  local s="${1:-}" c="${2:-}" tag
  case "$s" in backend|frontend) ;; *) die "ใช้: scripts/ship.sh rollback <backend|frontend> <commit>";; esac
  [ -n "$c" ] || die "ระบุ commit ที่จะย้อนไป (ดูได้จาก git log --first-parent main)"
  load_conf
  tag="$(git rev-parse --short=12 "$c")" || die "ไม่พบ commit $c"
  confirm "ย้อน $s บนเซิร์ฟเวอร์ไปใช้ image :$tag ?" || die "ยกเลิก"
  remote "$DEPLOY_DOCKER pull -q $(img_of "$s"):$tag && $DEPLOY_DOCKER tag $(img_of "$s"):$tag $(img_of "$s"):latest && $COMPOSE_REMOTE up -d $s"
  health_check && remote "echo $(git rev-parse "$c") > .deployed-$s" && ok "ย้อน $s ไป $tag แล้ว"
}

# ---------- cleanup ----------
cmd_cleanup() {
  update_main
  run git fetch -q --prune origin
  # ไม่ใช้ array: bash 3.2 ของ macOS + set -u error กับ array ว่าง
  local remote_br local_br bundles="" keep="" b head
  remote_br="$(git branch -r --merged "origin/$BASE_BRANCH" | sed 's/^ *//' | grep -v -e "^origin/$BASE_BRANCH\$" -e '^origin/HEAD' | sed 's#^origin/##' || true)"
  local_br="$(git branch --merged "$BASE_BRANCH" | sed 's/^[* ]*//' | grep -v -x "$BASE_BRANCH" || true)"
  for b in ./*.bundle; do
    [ -f "$b" ] || continue
    head="$(git bundle list-heads "$b" 2>/dev/null | awk 'NR==1 {print $1}')"
    if [ -n "$head" ] && git cat-file -e "$head^{commit}" 2>/dev/null && git merge-base --is-ancestor "$head" "$BASE_BRANCH"; then
      bundles="$bundles $b"
    else
      keep="$keep $b"
    fi
  done
  local unmerged; unmerged="$(git branch -r --no-merged "origin/$BASE_BRANCH" | sed 's/^ *//' || true)"

  if [ -z "$remote_br" ] && [ -z "$local_br" ] && [ -z "$bundles" ]; then
    ok "ไม่มีอะไรต้องเก็บกวาด"
  else
    step "สิ่งที่จะลบ (merge เข้า $BASE_BRANCH แล้ว)"
    [ -n "$remote_br" ] && printf '   GitHub: %s\n' $remote_br
    [ -n "$local_br" ] && printf '   ในเครื่อง: %s\n' $local_br
    [ -n "$bundles" ] && printf '   bundle: %s\n' $bundles
    if confirm "ลบทั้งหมดนี้?"; then
      for b in $remote_br; do
        if retry run git push -q origin --delete "$b"; then ok "ลบ origin/$b"; else warn "ลบ origin/$b ไม่สำเร็จ"; fi
      done
      for b in $local_br; do run git branch -q -d "$b" && ok "ลบ $b (ในเครื่อง)" || warn "ลบ $b ไม่สำเร็จ"; done
      for b in $bundles; do run rm -f "$b" && ok "ลบ $b"; done
    else
      warn "ยกเลิก — ไม่ได้ลบอะไร"
    fi
  fi
  if [ -n "$unmerged" ]; then
    warn "branch บน GitHub ที่ยังไม่ merge (ไม่ได้ลบ):"
    printf '   %s\n' $unmerged >&2
  fi
  if [ -n "$keep" ]; then
    warn "bundle ที่ยังไม่ได้ใช้หรือตรวจไม่ได้ (ไม่ได้ลบ):$keep"
  fi
  return 0
}

# ---------- local: ทดลองบน Docker ในเครื่อง ----------
LOCAL_PROJECT="pdf-local"
LOCAL_WEB_PORT="${LOCAL_WEB_PORT:-18080}"
LOCAL_API_PORT="${LOCAL_API_PORT:-18001}"
LOCAL_EMAIL="${LOCAL_EMAIL:-tester@local.test}"
LOCAL_PASSWORD="${LOCAL_PASSWORD:-Local-Test-1234}"

main_root() { (cd "$(git rev-parse --git-common-dir)/.." && pwd); }

local_compose() {
  # แยกจากระบบ dev ปกติ (docker-compose.dev.yml พอร์ต 8080/8001 ชื่อ container pdf_*): ชื่อโปรเจกต์ pdf-local,
  # ไม่ตั้งชื่อ container เอง, พอร์ตคนละชุด, ข้อมูลอยู่ใน volume ของโปรเจกต์นี้เท่านั้น (ต้องใช้ Docker Compose 2.24+)
  local dir="$1"
  cat > "$dir/.local-compose.yml" <<YAML
services:
  db:
    container_name: !reset null
    ports: !reset []
  backend:
    container_name: !reset null
    ports: !override
      - "$LOCAL_API_PORT:8000"
    # ทับค่าใน backend/.env (ซึ่งตั้งไว้สำหรับ dev พอร์ต 8080): ลิงก์ในอีเมล (รีเซ็ตรหัสผ่าน/ยืนยันอีเมล/ลงนาม),
    # CORS และ passkey ต้องชี้มาที่ระบบทดลอง — ไม่ต้องแก้ .env ของ dev
    environment:
      FRONTEND_URL: "http://localhost:$LOCAL_WEB_PORT"
      PDF_ALLOWED_ORIGINS: "http://localhost:$LOCAL_WEB_PORT"
      WEBAUTHN_RP_ID: "localhost"
      WEBAUTHN_ORIGINS: "http://localhost:$LOCAL_WEB_PORT"
  frontend:
    container_name: !reset null
    ports: !override
      - "$LOCAL_WEB_PORT:8080"
YAML
  echo "docker compose -p $LOCAL_PROJECT -f $dir/docker-compose.dev.yml -f $dir/.local-compose.yml --project-directory $dir"
}

cmd_local() {
  need docker "เปิด Docker Desktop ก่อน"
  docker info >/dev/null 2>&1 || die "Docker ยังไม่พร้อม — เปิด Docker Desktop แล้วรอจนขึ้นว่า running"
  local dir compose main br
  main="$(main_root)"
  if [ -n "${1:-}" ]; then
    # จาก bundle: เช็กเอาต์ branch ใน .local-test/ (git worktree) — main และไฟล์ที่กำลังแก้ไม่ถูกแตะ
    local bundle; bundle="$(pick_bundle "$1")"
    step "ตรวจ bundle $bundle"
    git bundle verify -q "$bundle" >/dev/null 2>&1 || die "bundle ใช้ไม่ได้กับ repo นี้ — ลอง git pull origin main แล้วรันใหม่"
    br="$(bundle_branch "$bundle")"; [ -n "$br" ] || die "ไม่พบ branch ใน bundle"
    git fetch -q -f "$bundle" "refs/heads/$br:refs/heads/local-test/$br"
    dir="$main/.local-test"
    if [ -d "$dir" ]; then
      git -C "$dir" checkout -q --detach "local-test/$br" || die "เช็กเอาต์ใน $dir ไม่สำเร็จ — ลบโฟลเดอร์ .local-test แล้วรันใหม่"
    else
      git worktree add -q --detach "$dir" "local-test/$br"
    fi
    ok "ทดลอง $br: $(git -C "$dir" log -1 --format='%h %s')"
  else
    dir="$(git rev-parse --show-toplevel)"
  fi
  # ไฟล์ที่ไม่อยู่ใน git (ค่าตั้งค่า, ใบรับรอง) ใช้ของโฟลเดอร์ repo หลัก
  if [ "$dir" != "$main" ]; then
    for f in backend/.env frontend/.env; do [ -f "$main/$f" ] && cp "$main/$f" "$dir/$f"; done
    if [ -d "$main/backend/secrets" ]; then rm -rf "$dir/backend/secrets"; cp -R "$main/backend/secrets" "$dir/backend/secrets"; fi
  fi
  mkdir -p "$dir/backend/secrets"
  compose="$(local_compose "$dir")"

  step "build + เปิดระบบทดลอง (ครั้งแรกนานหลายนาที — Ghostscript/LibreOffice)"
  $compose up -d --build || die "build/เปิดระบบไม่สำเร็จ — ดู error ด้านบน"

  step "รอระบบพร้อม"
  local i up=0
  for i in $(seq 1 60); do
    if curl -fsS --max-time 3 "http://localhost:$LOCAL_API_PORT/health" >/dev/null 2>&1 \
       && curl -fsS --max-time 3 "http://localhost:$LOCAL_WEB_PORT" >/dev/null 2>&1; then up=1; break; fi
    sleep 3
  done
  [ $up = 1 ] || { $compose logs --tail 40 backend >&2; die "ระบบยังไม่พร้อมภายใน 3 นาที (log backend ด้านบน)"; }
  $compose exec -T backend python -m scripts.create_test_user "$LOCAL_EMAIL" "$LOCAL_PASSWORD" >/dev/null
  ok "Ghostscript ใน image: $($compose exec -T backend gs --version | tr -d '\r')"

  if [ "${SKIP_EVAL:-0}" != "1" ] && [ -d "$main/test_pdf_files" ]; then
    step "ชุดวัดผล thai_eval กับ test_pdf_files/ (แบบเดียวกับตอน deploy)"
    docker run --rm -v "$main/test_pdf_files:/corpus:ro" "$LOCAL_PROJECT-backend" python -m scripts.thai_eval /corpus --check \
      && ok "thai_eval ผ่าน" || warn "thai_eval ไม่ผ่าน — ตอน deploy จริงจะหยุดที่ขั้นนี้"
  fi

  printf '\n%s ระบบทดลองพร้อมแล้ว%s\n' "$c_ok" "$c_off"
  printf '   เปิด:      http://localhost:%s\n' "$LOCAL_WEB_PORT"
  printf '   เข้าสู่ระบบ: %s / %s\n' "$LOCAL_EMAIL" "$LOCAL_PASSWORD"
  printf '   ข้อมูลทดลองแยกจากระบบ dev ปกติ · ปิด: scripts/ship.sh local-down (ลบข้อมูลด้วย: local-down --wipe)\n'
  printf '   หมายเหตุ: ใช้ backend/.env เดิม — ถ้าตั้ง SMTP/LINE ไว้ อีเมล/แจ้งเตือนจากการทดลองจะส่งออกจริง\n'
  command -v open >/dev/null 2>&1 && open "http://localhost:$LOCAL_WEB_PORT" || true
}

cmd_local_down() {
  local main dir compose; main="$(main_root)"
  dir="$main/.local-test"; [ -d "$dir" ] || dir="$main"
  compose="$(local_compose "$dir")"
  if [ "${1:-}" = "--wipe" ]; then
    $compose down -v && ok "ปิดระบบทดลองและลบข้อมูลทดลองแล้ว"
  else
    $compose down && ok "ปิดระบบทดลองแล้ว (ข้อมูลทดลองยังอยู่ — ลบด้วย local-down --wipe)"
  fi
}

usage() { sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; }

LAST_BRANCH=""; LAST_BUNDLE=""; ALREADY_MERGED=0
case "${1:-}" in
  pr) shift; cmd_pr "$@" ;;
  merge) shift; cmd_merge "$@" ;;
  deploy) shift; cmd_deploy "$@" ;;
  all) shift; cmd_pr "$@"; cmd_merge "$LAST_BRANCH"; cmd_deploy auto ;;
  status) cmd_status ;;
  rollback) shift; cmd_rollback "$@" ;;
  cleanup) cmd_cleanup ;;
  local) shift; cmd_local "$@" ;;
  local-down) shift; cmd_local_down "$@" ;;
  ""|-h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac
