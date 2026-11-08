# scripts/

สคริปต์ยูทิลิตี้ที่ยังใช้งานได้ (รันจากโฟลเดอร์รากของ repo)

| สคริปต์ | ใช้ทำอะไร |
|---|---|
| `ship.sh` | (บน Mac) รับ git bundle จาก Claude → push + เปิด PR ด้วย gh → รอ CI → merge → build image arm64 → push Docker Hub → เซิร์ฟเวอร์ pull + up -d → ตรวจ `/api/health` · `scripts/ship.sh all` ทำครบในคำสั่งเดียว, `deploy` เลือกเฉพาะส่วนที่เปลี่ยน, `rollback`, `status` · ค่าเซิร์ฟเวอร์อยู่ใน `scripts/deploy.env` (ไม่เข้า git) |
| `create_admin.py <email>` | ตั้งผู้ใช้เป็น admin |
| `seed_70_users.py` | สร้างผู้ใช้ทดสอบ 70 คนใน Postgres (dev เท่านั้น) |
| `create_samples.py` | สร้างไฟล์ตัวอย่างสำหรับ Auto-Gen |
| `server/pdf-backup-offsite.sh` | (บนเซิร์ฟเวอร์) ส่ง backup ล่าสุดแบบเข้ารหัสไป Oracle Object Storage ด้วย rclone — ดู DEPLOYMENT_ORACLE_GUIDE.md หัวข้อ 10 |

สคริปต์ฝั่ง backend อยู่ที่ `backend/scripts/` (รันจาก `backend/`)

สคริปต์ `patch_*.py` / `fix_*.py` ที่เคยใช้แก้โค้ดครั้งเดียว และสคริปต์ทดลองต่างๆ ถูกย้ายไป `archive/`
(ยังอยู่ใน git history ครบ) — ไม่ควรสร้างสคริปต์ patch ใหม่ไว้ที่ root อีก ให้แก้โค้ดโดยตรงแล้ว commit แทน
