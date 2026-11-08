#!/bin/bash
# ดับเบิลคลิกเพื่อ load test เซิร์ฟเวอร์ (ค่าเริ่มต้น 10 → 25 → 50 → 100 ผู้ใช้ ขั้นละ 3 นาที ~15 นาที) — ดู scripts/loadtest/run.sh
cd "$(dirname "$0")/../.." || exit 1
scripts/loadtest/run.sh 2>&1 | tee loadtest-log.txt
echo "== exit: ${PIPESTATUS[0]}" | tee -a loadtest-log.txt
read -r -p "กด Enter เพื่อปิดหน้าต่าง"
