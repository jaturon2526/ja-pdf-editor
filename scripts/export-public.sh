#!/usr/bin/env bash
# scripts/export-public.sh — คัดลอกซอร์สฉบับปัจจุบันไปยัง repo สาธารณะ (AGPL-3.0) โดยไม่พาประวัติ git ของ repo นี้ไปด้วย
#
# ทำไมต้องแยก repo: ประวัติของ repo นี้ (private) เคยมีไฟล์ทดสอบที่เป็นเอกสารจริงของคนจริง — ลบใน commit ใหม่แล้ว
# แต่ยังดึงจากประวัติได้ · repo สาธารณะจึงเริ่มจาก snapshot ที่สะอาด แล้วต่อ commit ทีละ release (ไม่มีประวัติเก่า)
#
#   scripts/export-public.sh [--push] [ref]
#     ref     commit/branch/tag ที่จะส่งออก (ค่าเริ่มต้น main)
#     --push  push ขึ้น remote ของ repo สาธารณะด้วย (ต้องตั้ง PUBLIC_REMOTE ครั้งแรก)
#
# ตัวแปร:
#   PUBLIC_DIR     โฟลเดอร์ repo สาธารณะในเครื่อง (ค่าเริ่มต้น ../ja-pdf-editor-public)
#   PUBLIC_REMOTE  เช่น https://github.com/jaturon2526/ja-pdf-editor.git (ใช้ตอนสร้างครั้งแรก)
#   BLOCKLIST      ไฟล์คำต้องห้ามส่วนตัว (บรรทัดละคำ: เบอร์โทร เลขบัตร IP เซิร์ฟเวอร์ ชื่อไฟล์คีย์ ...)
#                  ค่าเริ่มต้น .public-blocklist ในโฟลเดอร์ repo (อยู่ใน .gitignore — ไม่เข้า git และ git archive ไม่ส่งออก)
#                  ถ้าไม่มี ใช้ ~/.ja-pdf-public-blocklist
#
# ขั้นตอน: git archive <ref> (เฉพาะไฟล์ที่ track) → ตัด path ใน EXCLUDES → ตรวจคำต้องห้าม + gitleaks (ถ้ามี)
#         → แทนที่ไฟล์ใน PUBLIC_DIR (เก็บ .git ไว้) → commit "Release vX.Y.Z (source <sha>)" · ตรวจไม่ผ่าน = หยุด ไม่ commit
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "ต้องรันในโฟลเดอร์ repo"; exit 1; }
cd "$ROOT"

PUSH=0
REF=main
for a in "$@"; do
  case "$a" in
    --push) PUSH=1 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) REF="$a" ;;
  esac
done

PUBLIC_DIR="${PUBLIC_DIR:-$ROOT/../ja-pdf-editor-public}"
if [ -z "${BLOCKLIST:-}" ]; then
  BLOCKLIST="$ROOT/.public-blocklist"
  [ -f "$BLOCKLIST" ] || BLOCKLIST="$HOME/.ja-pdf-public-blocklist"
fi
if [ -f "$BLOCKLIST" ] && git ls-files --error-unmatch "$BLOCKLIST" >/dev/null 2>&1; then
  echo "✗ $BLOCKLIST ถูก commit เข้า git — เอาออก (git rm --cached) ก่อน"; exit 1
fi
# ไม่ส่งออก: สคริปต์ทดลองเก่า (มี path เครื่องผู้พัฒนา), บันทึกการทำงานกับ Claude, คู่มือ deploy เฉพาะเซิร์ฟเวอร์ของเรา
EXCLUDES=(archive CLAUDE.md DEPLOYMENT_ORACLE_GUIDE.md .local-test ship-now.command)

SHA="$(git rev-parse --short "$REF^{commit}")"
VERSION="$(grep -o 'APP_VERSION = "v[0-9.]*"' frontend/src/components/AboutModal.jsx | grep -o 'v[0-9.]*' || echo dev)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "▶ ส่งออก $REF ($SHA) $VERSION → $PUBLIC_DIR"
git archive --format=tar "$REF" | tar -x -C "$WORK"
for p in "${EXCLUDES[@]}"; do rm -rf "${WORK:?}/$p"; done

# ---- ตรวจก่อนเผยแพร่ ----
fail=0
for f in .env .env.prod scripts/deploy.env backend/.env frontend/.env; do
  if [ -e "$WORK/$f" ]; then echo "✗ พบไฟล์ค่าตั้งจริง: $f"; fail=1; fi
done
if find "$WORK" -type f \( -name '*.pem' -o -name '*.key' -o -name 'id_rsa*' -o -name '*.pfx' \) | grep -q .; then
  echo "✗ พบไฟล์คีย์/ใบรับรอง:"; find "$WORK" -type f \( -name '*.pem' -o -name '*.key' -o -name 'id_rsa*' -o -name '*.pfx' \); fail=1
fi
if [ -s "$BLOCKLIST" ]; then
  # -F ตรงตัวอักษร, -i ไม่สนตัวพิมพ์, -I ข้ามไฟล์ไบนารี (PDF ที่บีบอัดตรวจไม่ได้ — ตรวจเฉพาะ fixture ที่สร้างจากสคริปต์)
  if hits="$(grep -rIilF -f <(grep -v '^\s*\(#\|$\)' "$BLOCKLIST") "$WORK")"; then
    echo "✗ พบคำต้องห้ามจาก $BLOCKLIST ในไฟล์:"; echo "${hits//$WORK\//  }"; fail=1
  fi
else
  echo "⚠ ไม่มี $BLOCKLIST — ข้ามการตรวจคำต้องห้าม (แนะนำให้สร้าง .public-blocklist: เบอร์โทร IP เซิร์ฟเวอร์ บรรทัดละคำ)"
fi
if command -v gitleaks >/dev/null 2>&1; then
  if ! gitleaks dir --no-banner --redact -c "$WORK/.gitleaks.toml" "$WORK"; then echo "✗ gitleaks พบความลับ"; fail=1; fi
else
  echo "⚠ ไม่มี gitleaks (brew install gitleaks) — ข้ามการสแกนความลับ"
fi
[ "$fail" = 0 ] || { echo "หยุด — แก้ใน repo หลักแล้วรันใหม่ (ยังไม่มีอะไรถูกเขียนลง $PUBLIC_DIR)"; exit 1; }

# ---- เขียนลง repo สาธารณะ ----
if [ ! -d "$PUBLIC_DIR/.git" ]; then
  mkdir -p "$PUBLIC_DIR"
  git -C "$PUBLIC_DIR" init -q -b main
  if [ -n "${PUBLIC_REMOTE:-}" ]; then git -C "$PUBLIC_DIR" remote add origin "$PUBLIC_REMOTE"; fi
  echo "▶ สร้าง repo ใหม่ที่ $PUBLIC_DIR"
fi
find "$PUBLIC_DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$WORK/." "$PUBLIC_DIR/"

cd "$PUBLIC_DIR"
git add -A
if git diff --cached --quiet; then
  echo "✓ ไม่มีอะไรเปลี่ยนจากครั้งก่อน"
else
  # ผู้เขียนใช้ชื่อ/อีเมลที่ตั้งใน repo สาธารณะ (แนะนำ noreply ของ GitHub: git -C "$PUBLIC_DIR" config user.email ...)
  git commit -q -m "Release $VERSION (source $SHA)"
  git tag -f "$VERSION" >/dev/null
  echo "✓ commit $(git rev-parse --short HEAD) — Release $VERSION"
fi
if [ "$PUSH" = 1 ]; then
  git push -u origin main && git push -f origin "$VERSION"
else
  echo "ตรวจดูแล้ว push เอง:  cd \"$PUBLIC_DIR\" && git push -u origin main --tags"
fi
