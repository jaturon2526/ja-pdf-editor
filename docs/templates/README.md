# แม่แบบวงจรการพัฒนาซอฟต์แวร์ด้วย AI (6-Step AI Development Lifecycle)

โฟลเดอร์นี้เก็บเทมเพลตมาตรฐาน 6 ขั้นตอนของโปรเจกต์ (ใช้เป็นแม่แบบสำหรับฟีเจอร์ใหม่ในโปรเจกต์นี้ และคัดลอกไปใช้เป็นโครงสร้างมาตรฐานในโปรเจกต์อื่นได้ทันที)

## ภาพรวม 6 ขั้นตอน

```text
1. intent.md   → วางแผน (ทำไมต้องทำ · ใครใช้ · ขอบเขตที่ทำและ "ไม่ทำ")
2. spec.md     → ออกแบบ (UI เดสก์ท็อป+มือถือ · API · DB/Redis · Security · ข้อจำกัด)
3. plan.md     → แผนเขียนโค้ด (แตกงานเป็นลำดับขั้น · เช็กลิสต์เอกสาร/เวอร์ชัน · ส่งต่องาน)
4. test        → โค้ด + เทสต์ 3 ชั้น (Backend pytest · Frontend vitest/eslint · E2E Playwright)
5. CLAUDE.md / → ความรู้ของทีม (อัปเดตสถาปัตยกรรม + กฎเหล็ก "ผิดเรื่องเดิม 2 ครั้ง จดลงหมวดกับดักทันที")
   GEMINI.md
6. deploy      → PR รีวิว · ตรวจบั๊ก/ช่องโหว่ (SonarQube + pip-audit + gitleaks) · ตรวจตรงสเป็ก (.github/pull_request_template.md)
```

## วิธีใช้งานเมื่อเริ่มฟีเจอร์ใหม่

1. สร้างโฟลเดอร์สำหรับฟีเจอร์นั้น (หรือคัดลอกเทมเพลตไปวาง):
   ```bash
   mkdir -p docs/features/YYYY-MM-DD-feature-name
   cp docs/templates/{intent,spec,plan}.md docs/features/YYYY-MM-DD-feature-name/
   ```
2. กรอก **`intent.md`** ร่วมกับผู้ใช้ให้ชัดเจนก่อน (โดยเฉพาะสิ่งที่ไม่ทำ เพื่อกัน scope creep)
3. ออกแบบใน **`spec.md`** และแตกงานใน **`plan.md`**
4. ลงมือเขียนโค้ดและเทสต์ครบ 3 ชั้นตาม **`plan.md`**
5. อัปเดตความรู้ของทีมใน **`CLAUDE.md`** / **`GEMINI.md`** (หากเจอปัญหาเดิมซ้ำ 2 ครั้ง ต้องจดลงหมวดกับดักทันที)
6. สแกน SonarQube + เปิด PR ตามเช็กลิสต์ใน **[`.github/pull_request_template.md`](../../.github/pull_request_template.md)** ก่อน deploy
