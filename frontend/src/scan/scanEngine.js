// ตัวเรียก worker ของการสแกน — โหลด OpenCV.js (ไฟล์ใหญ่ ~3 MB เมื่อบีบอัด) เฉพาะตอนเปิดหน้าสแกน
import cvUrl from "@techstark/opencv-js/dist/opencv.js?url";

export function createScanEngine() {
  const worker = new Worker(new URL("./scanWorker.js", import.meta.url), { type: "module" });
  let seq = 0;
  const pending = new Map();
  let readyResolve;
  let readyReject;
  const ready = new Promise((res, rej) => { readyResolve = res; readyReject = rej; });

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === "ready") return readyResolve(msg.ms);
    if (msg.type === "error") return readyReject(new Error(msg.error));
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    if (msg.error) p.reject(new Error(msg.error));
    else p.resolve(msg);
  };
  worker.onerror = (e) => readyReject(new Error(e.message || "โหลดตัวประมวลผลภาพไม่สำเร็จ"));
  worker.postMessage({ type: "init", cvUrl: new URL(cvUrl, window.location.href).href });

  function call(type, payload, transfer = []) {
    const id = ++seq;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({ type, id, ...payload }, transfer);
    });
  }

  return {
    ready,
    /** มุมเอกสาร (สัดส่วน 0..1) หรือ null — image: ImageData ขนาดย่อ */
    detect: (image) => call("detect", { image }).then((r) => ({ corners: r.corners, ms: r.ms })),
    /** ดัดภาพ + ฟิลเตอร์ → {image: ImageData, quality: {sharp, glare, blurry, glary} | null} — mode: bw | gray | color */
    process: (image, corners, mode = "bw", strength = "normal") =>
      call("process", { image, corners, mode, strength }).then((r) => ({ image: r.image, quality: r.quality || null, ms: r.ms })),
    terminate: () => worker.terminate(),
  };
}
