#!/usr/bin/env bash
# ส่ง backup ล่าสุด (db_*.dump + files_*.tar.gz จาก ~/bin/pdf-backup.sh) ไปเก็บนอกเซิร์ฟเวอร์ด้วย rclone
# ปลายทางควรเป็น rclone "crypt" remote (เข้ารหัสฝั่งเซิร์ฟเวอร์ก่อนส่ง — ชื่อไฟล์และเนื้อหาอ่านไม่ได้ที่ปลายทาง)
# ตั้งค่า/กู้คืน: ดู DEPLOYMENT_ORACLE_GUIDE.md หัวข้อ 10
#
# ใช้: scripts/server/pdf-backup-offsite.sh            (ส่งชุดล่าสุด + ลบชุดที่เก่ากว่า KEEP_DAYS ที่ปลายทาง)
#      scripts/server/pdf-backup-offsite.sh --check    (ตรวจการเชื่อมต่อ/ดูรายการที่ปลายทาง ไม่ส่งอะไร)
# ตัวแปร (ไม่บังคับ): BACKUP_DIR (~/backups) · REMOTE (ja-pdf-backup:) · KEEP_DAYS (30) · MAX_AGE_HOURS (26)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
REMOTE="${REMOTE:-ja-pdf-backup:}"
KEEP_DAYS="${KEEP_DAYS:-30}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"
STATUS_FILE="$BACKUP_DIR/offsite-status.txt"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }
fail() {
  log "ล้มเหลว: $*"
  printf 'status=failed\ntime=%s\nerror=%s\n' "$(date -u +%FT%TZ)" "$*" > "$STATUS_FILE"
  exit 1
}

command -v rclone >/dev/null || fail "ไม่พบ rclone (ติดตั้ง: sudo apt install -y rclone)"
remotes="$(rclone listremotes)"  # ไม่ใช้ pipe เข้า grep -q (pipefail + SIGPIPE ทำให้ล้มแบบสุ่ม)
grep -qx "${REMOTE%%:*}:" <<<"$remotes" || fail "ยังไม่ได้ตั้งค่า rclone remote '${REMOTE%%:*}'"

if [[ "${1:-}" == "--check" ]]; then
  log "ตรวจปลายทาง $REMOTE"
  rclone lsl "${REMOTE}daily" 2>/dev/null | sort -k2,3 | tail -n 10 || log "(ยังไม่มีไฟล์ในปลายทาง)"
  rclone size "${REMOTE}daily" 2>/dev/null || true
  exit 0
fi

# ชุดล่าสุด: ไฟล์ db_ และ files_ ที่ใหม่ที่สุด และต้องไม่เก่ากว่า MAX_AGE_HOURS (กันส่งของเก่าซ้ำเมื่อ backup เครื่องล้ม)
latest() { find "$BACKUP_DIR" -maxdepth 1 -type f -name "$1" -mmin "-$((MAX_AGE_HOURS * 60))" -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-; }
DB_FILE="$(latest 'db_*.dump')"
FILES_FILE="$(latest 'files_*.tar.gz')"
[[ -n "$DB_FILE" ]] || fail "ไม่พบ db_*.dump ที่ใหม่กว่า ${MAX_AGE_HOURS} ชม. ใน $BACKUP_DIR (backup ในเครื่องรันหรือเปล่า?)"
[[ -n "$FILES_FILE" ]] || fail "ไม่พบ files_*.tar.gz ที่ใหม่กว่า ${MAX_AGE_HOURS} ชม. ใน $BACKUP_DIR"

total=0
for f in "$DB_FILE" "$FILES_FILE"; do
  name="$(basename "$f")"
  size="$(stat -c %s "$f")"
  [[ "$size" -gt 0 ]] || fail "$name มีขนาด 0 ไบต์"
  log "ส่ง $name ($((size / 1024)) KB)"
  rclone copyto "$f" "${REMOTE}daily/$name" --retries 3 --low-level-retries 10 || fail "ส่ง $name ไม่สำเร็จ"
  remote_size="$(rclone lsl "${REMOTE}daily/$name" | awk '{print $1}')"
  [[ "$remote_size" == "$size" ]] || fail "ขนาดที่ปลายทางไม่ตรง: $name ($remote_size != $size)"
  total=$((total + size))
done

log "ลบชุดที่เก่ากว่า ${KEEP_DAYS} วันที่ปลายทาง"
rclone delete "${REMOTE}daily" --min-age "${KEEP_DAYS}d" || log "คำเตือน: ลบชุดเก่าไม่สำเร็จ (ลองใหม่รอบหน้า)"

used="$(rclone size "${REMOTE}daily" --json 2>/dev/null | sed -n 's/.*"bytes":\([0-9]*\).*/\1/p')"
printf 'status=ok\ntime=%s\ndb=%s\nfiles=%s\nbytes_sent=%s\nremote_bytes=%s\n' \
  "$(date -u +%FT%TZ)" "$(basename "$DB_FILE")" "$(basename "$FILES_FILE")" "$total" "${used:-unknown}" > "$STATUS_FILE"
log "สำเร็จ — ส่ง $((total / 1024)) KB · ปลายทางใช้รวม $(( ${used:-0} / 1024 / 1024 )) MB"

# บอก backend เวลาสำรองล่าสุด → หน้าแอดมิน (โควต้าและสถานะเซิร์ฟเวอร์) เตือนเมื่อขาดหายเกิน BACKUP_MAX_AGE_HOURS
# ในเครื่อง = เวลาของไฟล์ db ชุดล่าสุด · นอกเครื่อง = ตอนนี้ (ไม่สำเร็จไม่เป็นไร — แค่หน้าแอดมินไม่อัปเดต)
mark() { docker exec -i pdf_backend_prod sh -c "cat > /data/$1" <<<"$2" 2>/dev/null || log "คำเตือน: เขียน /data/$1 ใน backend ไม่สำเร็จ"; }
mark .last-backup "$(date -u -d "@$(stat -c %Y "$DB_FILE")" +%FT%TZ)"
mark .last-offsite-backup "$(date -u +%FT%TZ)"
