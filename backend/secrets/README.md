# backend/secrets

โฟลเดอร์นี้ถูก mount เข้า container backend ที่ `/run/secrets/pdf-editor` แบบอ่านอย่างเดียว
(ดู `docker-compose.dev.yml`) — ไฟล์อื่นนอกจาก README นี้ไม่ถูก commit และไม่ถูกใส่ใน image

## ใบรับรองระบบสำหรับลายเซ็นอิเล็กทรอนิกส์

1. วางไฟล์ใบรับรองแบบ document signing (.p12/.pfx ที่มี private key + ใบรับรอง + intermediate/root) ไว้ที่ `backend/secrets/seal.p12`
2. ใน `backend/.env` ตั้ง
   ```
   SIGNING_SEAL_P12=/run/secrets/pdf-editor/seal.p12
   SIGNING_SEAL_P12_PASSWORD=รหัสผ่านไฟล์
   ```
3. `docker compose -f docker-compose.dev.yml up -d --force-recreate backend`
4. ตรวจ: `docker compose -f docker-compose.dev.yml exec backend python -m scripts.seal_info`

ไม่ตั้งค่า = ระบบใช้ใบรับรอง self-signed ที่สร้างเอง (Adobe จะขึ้นว่าไม่ทราบผู้ออกใบรับรอง)
