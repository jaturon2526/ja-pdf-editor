// bgSample — สุ่มสีพื้นหลังของหน้าเอกสาร (จากรูป PNG ที่ render มาแสดงอยู่แล้ว) ตรงตำแหน่งกล่องที่
// กำลังจะแก้ไข ใช้ทำพื้นหลังทึบให้กล่องแก้ไข/พรีวิวข้อความ กันปัญหา "เห็นข้อความเดิมทับซ้อนกับข้อความ
// ที่กำลังพิมพ์ใหม่" (เดิมกล่องใช้พื้นหลังโปร่งแสง rgba(255,255,255,0.55) ทำให้ข้อความเดิมในรูปหน้า
// เอกสาร ซึ่งยังไม่ถูก redact จริงจนกว่าจะกดบันทึก โผล่ทะลุมาผสมกับข้อความใหม่ที่พิมพ์อยู่)
//
// ใช้หลักการเดียวกับ backend (_sample_background_color ใน edit_service.py): สุ่มสีที่ 4 มุมของกล่อง
// แล้วเลือกสีที่เจอซ้ำมากที่สุด (สันนิษฐานว่าเป็นพื้นหลัง) วาดรูปหน้าเอกสารลง canvas ที่ซ่อนไว้ชั่วคราว
// แล้วอ่านค่าพิกเซลด้วย getImageData — รูปเป็น data: URI (base64) มาจาก origin เดียวกันเสมอ ไม่มีปัญหา
// canvas ถูก "taint" จาก cross-origin

export function sampleBackgroundColor(imgEl, pageWidthPt, pageHeightPt, rect, marginPt = 0) {
  try {
    if (!imgEl || !imgEl.naturalWidth || !pageWidthPt || !pageHeightPt) return null;
    const canvas = document.createElement("canvas");
    canvas.width = imgEl.naturalWidth;
    canvas.height = imgEl.naturalHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(imgEl, 0, 0);

    const toPx = (xPt, yPt) => [
      Math.min(canvas.width - 1, Math.max(0, Math.round((xPt / pageWidthPt) * canvas.width))),
      Math.min(canvas.height - 1, Math.max(0, Math.round((yPt / pageHeightPt) * canvas.height))),
    ];
    // marginPt > 0: ขยายมุมที่สุ่มออกไปนอกกรอบเล็กน้อยก่อน — ใช้กับรูปภาพที่มักเต็มกรอบขอบชนขอบพอดี
    // (ต่างจากข้อความที่มักมีขอบเผื่อรอบตัวอักษรอยู่บ้าง) สุ่มตรงมุมกรอบเป๊ะๆ จะได้สีของ "ตัวรูปเอง" ไม่ใช่
    // พื้นหลังจริงเบื้องหลัง (เจอปัญหานี้จริงฝั่ง backend มาก่อนแล้ว — ดู _BG_SAMPLE_MARGIN_PT ใน
    // edit_service.py ใช้ margin ค่าเดียวกัน 6pt เพื่อความสอดคล้องกัน)
    const corners = [
      toPx(rect.x0 - marginPt, rect.y0 - marginPt),
      toPx(rect.x1 + marginPt, rect.y0 - marginPt),
      toPx(rect.x0 - marginPt, rect.y1 + marginPt),
      toPx(rect.x1 + marginPt, rect.y1 + marginPt),
    ];

    const counts = new Map();
    for (const [x, y] of corners) {
      const [r, g, b] = ctx.getImageData(x, y, 1, 1).data;
      const key = `${r},${g},${b}`;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    let bestKey = null;
    let bestCount = -1;
    for (const [key, count] of counts) {
      if (count > bestCount) {
        bestKey = key;
        bestCount = count;
      }
    }
    if (!bestKey) return null;
    const [r, g, b] = bestKey.split(",").map(Number);
    return `rgb(${r}, ${g}, ${b})`;
  } catch {
    // canvas/รูปยังไม่พร้อม หรือ error อื่นๆ — ปล่อยให้ผู้เรียกใช้ fallback เป็นสีขาวทึบแทน
    return null;
  }
}
