// สร้างภาพตราประทับยาง (Rubber Stamp) แบบ PNG พื้นหลังโปร่งใสความละเอียดสูงฝั่งเบราว์เซอร์
// ไม่ต้องพึ่ง dependency ใหม่ — วางลงเอกสารผ่านระบบแทรก/แก้ไขรูปภาพที่มีอยู่ (ลาก ย่อ/ขยาย Undo/Redo ได้ทันที)

const THAI_MONTHS_SHORT = [
  "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
  "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
];

export const STAMP_PRESETS = [
  { id: "certified", label: "สำเนาถูกต้อง", text: "สำเนาถูกต้อง", color: "#1d4ed8", includeDate: true, angleDeg: -12 },
  { id: "approved", label: "อนุมัติแล้ว", text: "อนุมัติแล้ว", color: "#15803d", includeDate: true, angleDeg: -12 },
  { id: "paid", label: "จ่ายแล้ว", text: "จ่ายแล้ว", color: "#047857", includeDate: true, angleDeg: -12 },
  { id: "confidential", label: "ลับ", text: "ลับ", color: "#dc2626", includeDate: false, angleDeg: -20 },
  { id: "urgent", label: "ด่วนที่สุด", text: "ด่วนที่สุด", color: "#b91c1c", includeDate: false, angleDeg: -20 },
  { id: "draft", label: "ร่าง (DRAFT)", text: "ร่าง (DRAFT)", color: "#475569", includeDate: false, angleDeg: -20 },
  { id: "custom", label: "กำหนดเอง", text: "ตรวจแล้ว", color: "#1d4ed8", includeDate: false, angleDeg: -12 },
];

export const STAMP_COLORS = [
  { value: "#1d4ed8", name: "น้ำเงิน" },
  { value: "#dc2626", name: "แดง" },
  { value: "#15803d", name: "เขียว" },
  { value: "#475569", name: "เทา" },
  { value: "#7c3aed", name: "ม่วง" },
];

export const STAMP_ANGLES = [
  { value: 0, label: "ตรง (0°)" },
  { value: -12, label: "เอียงน้อย (−12°)" },
  { value: -20, label: "เอียงมาก (−20°)" },
];

export const STAMP_OPACITIES = [
  { value: 0.7, label: "70%" },
  { value: 0.85, label: "85%" },
  { value: 1, label: "100%" },
];

const STAMP_FONT_FAMILY = '"Sarabun", "Noto Sans Thai", "Sukhumvit Set", "Tahoma", system-ui, sans-serif';

export function formatThaiDate(date = new Date()) {
  const day = date.getDate();
  const month = THAI_MONTHS_SHORT[date.getMonth()] || "";
  const buddhistYear = date.getFullYear() + 543;
  return `${day} ${month} ${buddhistYear}`;
}

function drawRoundedRectPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h - radius);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
  ctx.lineTo(x + radius, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function fitFontSize(ctx, text, maxWidth, startSize, minSize, weight) {
  let size = startSize;
  while (size > minSize) {
    ctx.font = `${weight} ${size}px ${STAMP_FONT_FAMILY}`;
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 2;
  }
  return size;
}

/**
 * วาดตราประทับลงบน 2D canvas context (ขนาด width × height พิกเซล)
 * รองรับพื้นหลังโปร่งใส กรอบสองชั้น ข้อความหลัก บรรทัดรอง/วันที่ มุมเอียง และความทึบ
 */
export function drawStamp(ctx, width, height, options = {}) {
  const text = (options.text || "").trim();
  const subText = (options.subText || "").trim();
  const color = options.color || "#1d4ed8";
  const angleDeg = typeof options.angleDeg === "number" ? options.angleDeg : -12;
  const opacity = typeof options.opacity === "number" ? options.opacity : 0.85;

  ctx.clearRect(0, 0, width, height);
  if (!text) return;

  const scale = width / 720;
  const boxW = Math.round(520 * scale);
  const boxH = Math.round((subText ? 176 : 138) * scale);
  const halfW = boxW / 2;
  const halfH = boxH / 2;

  ctx.save();
  ctx.translate(width / 2, height / 2);
  ctx.rotate((angleDeg * Math.PI) / 180);
  ctx.globalAlpha = Math.max(0.2, Math.min(1, opacity));
  ctx.strokeStyle = color;
  ctx.fillStyle = color;

  // กรอบนอกหนา + กรอบในบางแบบตรายาง
  const outerLine = Math.max(2, Math.round(9 * scale));
  const innerInset = Math.round(13 * scale);
  const innerLine = Math.max(1.5, Math.round(3 * scale));
  const cornerRadius = Math.round(18 * scale);

  ctx.lineWidth = outerLine;
  drawRoundedRectPath(ctx, -halfW, -halfH, boxW, boxH, cornerRadius);
  ctx.stroke();

  ctx.lineWidth = innerLine;
  drawRoundedRectPath(
    ctx,
    -halfW + innerInset,
    -halfH + innerInset,
    boxW - innerInset * 2,
    boxH - innerInset * 2,
    Math.max(4, cornerRadius - innerInset * 0.6),
  );
  ctx.stroke();

  // ข้อความหลัก
  const maxTextW = boxW - Math.round(72 * scale);
  const startMainSize = Math.round((subText ? 66 : 74) * scale);
  const minMainSize = Math.round(24 * scale);
  const mainSize = fitFontSize(ctx, text, maxTextW, startMainSize, minMainSize, "800");

  ctx.font = `800 ${mainSize}px ${STAMP_FONT_FAMILY}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  if (subText) {
    const mainY = -Math.round(24 * scale);
    ctx.fillText(text, 0, mainY);

    // เส้นคั่นบางระหว่างข้อความหลักกับวันที่/บรรทัดรอง
    const lineY = Math.round(20 * scale);
    const lineHalfW = halfW - Math.round(36 * scale);
    ctx.lineWidth = Math.max(1, Math.round(2.5 * scale));
    ctx.beginPath();
    ctx.moveTo(-lineHalfW, lineY);
    ctx.lineTo(lineHalfW, lineY);
    ctx.stroke();

    // บรรทัดรอง / วันที่
    const startSubSize = Math.round(32 * scale);
    const minSubSize = Math.round(16 * scale);
    const subSize = fitFontSize(ctx, subText, maxTextW, startSubSize, minSubSize, "600");
    ctx.font = `600 ${subSize}px ${STAMP_FONT_FAMILY}`;
    ctx.fillText(subText, 0, Math.round(50 * scale));
  } else {
    ctx.fillText(text, 0, Math.round(2 * scale));
  }

  ctx.restore();
}

/**
 * สร้างไฟล์ PNG พื้นหลังโปร่งใสความละเอียดสูง (720×380 px) สำหรับวางลงบนหน้า PDF
 */
export async function renderStampPngFile(options) {
  const width = 720;
  const height = 380;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("เบราว์เซอร์ไม่รองรับการสร้างภาพตราประทับ");

  drawStamp(ctx, width, height, options);

  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("แปลงภาพตราประทับไม่สำเร็จ"))),
      "image/png",
    );
  });
  return new File([blob], "stamp.png", { type: "image/png" });
}
