#!/usr/bin/env bash
# สร้าง backend/requirements.txt และ requirements-dev.txt (เวอร์ชันตายตัว + hash) จากไฟล์ .in
#   ใช้ uv (https://docs.astral.sh/uv/) — ล็อกสำหรับ Python 3.11 ทุกแพลตฟอร์ม (ARM64 Oracle / x86_64 on-prem / Mac)
#   scripts/lock-backend-deps.sh            ล็อกใหม่ คงเวอร์ชันเดิมเท่าที่ทำได้
#   scripts/lock-backend-deps.sh --upgrade  อัปเกรดทุกแพ็กเกจเป็นรุ่นล่าสุดที่เข้ากับ .in
set -euo pipefail
cd "$(dirname "$0")/../backend"
command -v uv >/dev/null || { echo "ต้องติดตั้ง uv ก่อน: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
opts=(--python-version 3.11 --universal --generate-hashes --quiet)
[ "${1:-}" = "--upgrade" ] && opts+=(--upgrade)
uv pip compile "${opts[@]}" requirements.in -o requirements.txt
uv pip compile "${opts[@]}" requirements-dev.in -o requirements-dev.txt
echo "อัปเดต backend/requirements.txt และ requirements-dev.txt แล้ว — รันเทสต์ก่อน commit"
