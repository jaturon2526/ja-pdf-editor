// แปลงภาพสำหรับหน้าสแกน (main thread)

function makeCanvas(w, h) {
  return Object.assign(document.createElement("canvas"), { width: w, height: h });
}

/** ภาพที่ถ่าย → JPEG ด้านยาวไม่เกิน maxSide (เก็บเป็นต้นฉบับไว้ปรับมุม/โหมดใหม่ และกันหน่วยความจำเต็ม) */
export async function bitmapToJpeg(bitmap, maxSide = 3000, quality = 0.92) {
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const c = makeCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale));
  c.getContext("2d").drawImage(bitmap, 0, 0, c.width, c.height);
  return await new Promise((resolve) => c.toBlob(resolve, "image/jpeg", quality));
}

/** Blob ภาพ → ImageData (ด้านยาวไม่เกิน maxSide) */
export async function blobToImageData(blob, maxSide = 4000) {
  const bmp = await createImageBitmap(blob);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const c = makeCanvas(Math.round(bmp.width * scale), Math.round(bmp.height * scale));
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return ctx.getImageData(0, 0, c.width, c.height);
}

/** ผลลัพธ์จาก worker → ไฟล์หน้า (หมุนตาม rotation เป็นองศา 0/90/180/270)
 *  ขาวดำ = PNG (backend เก็บเป็น 1 บิต), สีเทา/สี = JPEG */
export async function encodePage(imageData, mode, rotation = 0) {
  const src = makeCanvas(imageData.width, imageData.height);
  src.getContext("2d").putImageData(imageData, 0, 0);
  const r = ((rotation % 360) + 360) % 360;
  let out = src;
  if (r) {
    const swap = r === 90 || r === 270;
    out = makeCanvas(swap ? src.height : src.width, swap ? src.width : src.height);
    const ctx = out.getContext("2d");
    // หมุนแบบพิกเซลต่อพิกเซล (ไม่มีการเกลี่ยสี) — ภาพขาวดำต้องคงเป็นสองสีให้ backend เก็บเป็น 1 บิตได้
    ctx.imageSmoothingEnabled = false;
    if (r === 90) ctx.setTransform(0, 1, -1, 0, out.width, 0);
    else if (r === 180) ctx.setTransform(-1, 0, 0, -1, out.width, out.height);
    else ctx.setTransform(0, -1, 1, 0, 0, out.height);
    ctx.drawImage(src, 0, 0);
  }
  const type = mode === "bw" ? "image/png" : "image/jpeg";
  const blob = await new Promise((resolve) => out.toBlob(resolve, type, 0.85));
  const tw = 240;
  const thumb = makeCanvas(tw, Math.round((out.height / out.width) * tw));
  thumb.getContext("2d").drawImage(out, 0, 0, thumb.width, thumb.height);
  const thumbBlob = await new Promise((resolve) => thumb.toBlob(resolve, "image/jpeg", 0.7));
  return { blob, thumbBlob, width: out.width, height: out.height };
}
