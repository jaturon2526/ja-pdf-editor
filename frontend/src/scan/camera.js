// กล้องหลังของมือถือ/แท็บเล็ต — ต้องเป็น HTTPS (หรือ localhost) และเบราว์เซอร์อนุญาต getUserMedia

export function cameraSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

/** อุปกรณ์จอสัมผัส (มือถือ/แท็บเล็ต รวม iPad ที่รายงานตัวเป็น Mac) */
export function isTouchDevice() {
  const coarse = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
  return coarse || (navigator.maxTouchPoints || 0) > 1;
}

/** เบราว์เซอร์ในแอป (LINE/Facebook/Instagram) — มักเปิดกล้องสดไม่ได้ */
export function isInAppBrowser() {
  return /Line\/|FBAN|FBAV|Instagram/i.test(navigator.userAgent || "");
}

export async function openRearCamera() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 3840 },
      height: { ideal: 2160 },
    },
  });
  const track = stream.getVideoTracks()[0];
  const caps = typeof track.getCapabilities === "function" ? track.getCapabilities() : {};
  // บางเครื่องให้ความละเอียดต่ำในตอนแรก — ขอสูงสุดที่กล้องทำได้อีกรอบ
  if (caps.width?.max && caps.height?.max) {
    try {
      await track.applyConstraints({ width: { ideal: caps.width.max }, height: { ideal: caps.height.max } });
    } catch { /* ใช้ค่าเดิม */ }
  }
  return { stream, track, caps };
}

export function stopStream(stream) {
  stream?.getTracks().forEach((t) => t.stop());
}

export async function setTorch(track, on) {
  await track.applyConstraints({ advanced: [{ torch: on }] });
}

/** ถ่ายภาพเต็มความละเอียด: ImageCapture.takePhoto (Android Chrome) ไม่งั้นใช้เฟรมจากวิดีโอ → ImageBitmap */
export async function capturePhoto(track, video) {
  if (typeof window.ImageCapture === "function") {
    try {
      const blob = await new window.ImageCapture(track).takePhoto();
      return await createImageBitmap(blob, { imageOrientation: "from-image" });
    } catch { /* ใช้เฟรมวิดีโอแทน */ }
  }
  return await createImageBitmap(video);
}

/** ImageBitmap/วิดีโอ → ImageData ที่ด้านยาวไม่เกิน maxSide */
export function toImageData(source, maxSide) {
  const sw = source.videoWidth || source.width;
  const sh = source.videoHeight || source.height;
  const scale = Math.min(1, maxSide / Math.max(sw, sh));
  const w = Math.max(1, Math.round(sw * scale));
  const h = Math.max(1, Math.round(sh * scale));
  const canvas = typeof OffscreenCanvas === "function" ? new OffscreenCanvas(w, h) : Object.assign(document.createElement("canvas"), { width: w, height: h });
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(source, 0, 0, w, h);
  return ctx.getImageData(0, 0, w, h);
}
