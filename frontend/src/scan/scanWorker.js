// Web Worker ของการสแกน (module worker — โหลด OpenCV.js เอง) ไม่ให้ภาพกล้องกระตุก
// ข้อความเข้า: {type:"init", cvUrl} | {type:"detect", id, image: ImageData} | {type:"process", id, image, corners, mode, strength}
// ตอบกลับ:   {type:"ready", ms} | {id, corners|null, ms} | {id, image: ImageData, quality, ms} | {id, error}
//            quality = {sharp, glare, blurry, glary} — เตือนผู้ใช้ให้ถ่ายใหม่เมื่อภาพเบลอ/มีแสงสะท้อน
import { orderCorners, quadArea, warpSize } from "./geometry.js";

let cv = null;

async function loadOpenCV(url) {
  // module worker ใช้ importScripts ไม่ได้ — โหลดสคริปต์ UMD ของ OpenCV แล้วรันใน global scope ของ worker
  const started = performance.now();
  const code = await (await fetch(url)).text();
  (0, eval)(code);
  const g = self.cv;
  if (!g.Mat) {
    // Module ของ emscripten เป็น thenable ที่ resolve ด้วยตัวเอง — await ตรงๆ จะค้างตลอดไป จึงห่อด้วย object
    const { mod } = await new Promise((resolve) => {
      if (typeof g.then === "function") g.then((m) => resolve({ mod: m }));
      else g.onRuntimeInitialized = () => resolve({ mod: g });
    });
    cv = mod;
  } else {
    cv = g;
  }
  return performance.now() - started;
}

function matToPoints(mat) {
  const pts = [];
  for (let i = 0; i < mat.rows; i++) pts.push({ x: mat.data32S[i * 2], y: mat.data32S[i * 2 + 1] });
  return pts;
}

/** หา 4 เหลี่ยมใหญ่สุดจากภาพขอบ (edges: CV_8U) */
function bestQuad(edges, w, h) {
  const contours = new cv.MatVector();
  const hierarchy = new cv.Mat();
  cv.findContours(edges, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
  let best = null;
  let bestArea = 0.15 * w * h;
  let largest = null;
  let largestArea = 0.25 * w * h;
  for (let i = 0; i < contours.size(); i++) {
    const c = contours.get(i);
    const area = cv.contourArea(c);
    if (area > largestArea) {
      largestArea = area;
      if (largest) largest.delete();
      largest = c.clone();
    }
    if (area > bestArea) {
      const approx = new cv.Mat();
      cv.approxPolyDP(c, approx, 0.02 * cv.arcLength(c, true), true);
      if (approx.rows === 4 && cv.isContourConvex(approx)) {
        bestArea = area;
        best = matToPoints(approx);
      }
      approx.delete();
    }
    c.delete();
  }
  if (!best && largest) {
    // ไม่เจอ 4 เหลี่ยมพอดี (มุมกระดาษพับ/โดนบัง) → ใช้สี่เหลี่ยมที่ครอบเส้นขอบใหญ่สุด
    const rect = cv.minAreaRect(largest);
    best = cv.RotatedRect.points(rect).map((p) => ({ x: p.x, y: p.y }));
  }
  if (largest) largest.delete();
  contours.delete();
  hierarchy.delete();
  return best;
}

function detect(image) {
  const src = cv.matFromImageData(image);
  const gray = new cv.Mat();
  const edges = new cv.Mat();
  const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(3, 3));
  let quad;
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, gray, new cv.Size(5, 5), 0);
    // รอบ 1: เส้นขอบ (Canny) — ใช้ได้กับพื้นหลังหลายแบบ
    cv.Canny(gray, edges, 30, 90);
    cv.dilate(edges, edges, kernel);
    quad = bestQuad(edges, image.width, image.height);
    if (!quad) {
      // รอบ 2: กระดาษขาวบนพื้นเข้ม — แยกด้วย Otsu
      cv.threshold(gray, edges, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
      cv.morphologyEx(edges, edges, cv.MORPH_CLOSE, kernel);
      quad = bestQuad(edges, image.width, image.height);
    }
  } finally {
    src.delete();
    gray.delete();
    edges.delete();
    kernel.delete();
  }
  if (!quad) return null;
  const norm = orderCorners(quad.map((p) => ({ x: p.x / image.width, y: p.y / image.height })));
  return quadArea(norm) >= 0.15 ? norm : null;
}

// เกณฑ์ภาพไม่ดี (วัดกับเอกสารสังเคราะห์ที่ทำเป็นภาพถ่าย: ความคม < 10 ≈ เบลอระดับที่ OCR อ่านคำถูกลดจาก ~96% เหลือ ~85%)
const SHARP_MIN = 10;
const GLARE_MAX = 0.02;      // สัดส่วนพื้นที่ที่สว่างจ้า (แสงสะท้อน) บนกระดาษที่ไม่ได้สว่างทั้งแผ่น

/** ความคมของภาพเอกสาร (ไม่ขึ้นกับปริมาณตัวหนังสือ): ค่าเฉลี่ย |Laplacian| ÷ ความชันของขอบ ตรงขอบที่ชัดที่สุด ×100
 *  norm: ภาพเทาที่ลบเงาแล้ว (CV_8U) · glare จากภาพเทาก่อนลบเงา */
function quality(gray, norm) {
  const small = new cv.Mat();
  const gx = new cv.Mat();
  const gy = new cv.Mat();
  const lap = new cv.Mat();
  try {
    const w = 1000;
    const h = Math.max(1, Math.round((norm.rows * w) / norm.cols));
    cv.resize(norm, small, new cv.Size(w, h), 0, 0, cv.INTER_AREA);
    small.convertTo(small, cv.CV_32F);
    cv.Sobel(small, gx, cv.CV_32F, 1, 0);
    cv.Sobel(small, gy, cv.CV_32F, 0, 1);
    cv.Laplacian(small, lap, cv.CV_32F);
    const n = w * h;
    const mag = new Float32Array(n);
    const X = gx.data32F, Y = gy.data32F, L = lap.data32F;
    for (let i = 0; i < n; i++) mag[i] = Math.hypot(X[i], Y[i]);
    const sample = [];
    for (let i = 0; i < n; i += 7) sample.push(mag[i]);
    sample.sort((a, b) => a - b);
    const thr = 0.3 * (sample[Math.floor(sample.length * 0.995)] || 0);
    let sl = 0, sm = 0;
    for (let i = 0; i < n; i++) if (mag[i] > thr && thr > 0) { sl += Math.abs(L[i]); sm += mag[i]; }
    const sharp = sm ? (100 * sl) / sm : 0;
    // แสงสะท้อน: จุดสว่างจ้า (≥ 250) บนกระดาษที่โดยรวมไม่ได้สว่างจ้า (ค่ากลาง < 235)
    const hist = new Uint32Array(256);
    const G = gray.data;
    for (let i = 0; i < G.length; i++) hist[G[i]]++;
    let acc = 0, median = 0;
    for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= G.length / 2) { median = v; break; } }
    let bright = 0;
    for (let v = 250; v < 256; v++) bright += hist[v];
    const glare = median < 235 ? bright / G.length : 0;
    return { sharp: Math.round(sharp * 10) / 10, glare: Math.round(glare * 1000) / 1000, blurry: sharp < SHARP_MIN, glary: glare > GLARE_MAX };
  } finally {
    [small, gx, gy, lap].forEach((m) => m.delete());
  }
}

const STRENGTH = { dark: 210, normal: 185, light: 160 }; // เกณฑ์ขาวดำหลังลบเงา (สูง = เส้นจางก็ติดเป็นสีดำ / ต่ำ = พื้นสะอาดกว่า)

function process({ image, corners, mode = "bw", strength = "normal" }) {
  const src = cv.matFromImageData(image);
  const px = corners.map((c) => ({ x: c.x * image.width, y: c.y * image.height }));
  const { width, height } = warpSize(px);
  const from = cv.matFromArray(4, 1, cv.CV_32FC2, px.flatMap((p) => [p.x, p.y]));
  const to = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, width, 0, width, height, 0, height]);
  const M = cv.getPerspectiveTransform(from, to);
  const warped = new cv.Mat();
  const gray = new cv.Mat();
  const bg = new cv.Mat();
  const out = new cv.Mat();
  const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(9, 9));
  let q;
  try {
    cv.warpPerspective(src, warped, M, new cv.Size(width, height), cv.INTER_LINEAR, cv.BORDER_REPLICATE);
    cv.cvtColor(warped, gray, cv.COLOR_RGBA2GRAY);
    // พื้นหลัง (แสง/เงา): ขยายส่วนสว่างกลบตัวอักษร แล้วเบลอใหญ่ → หารภาพด้วยพื้นหลัง = พื้นขาวเรียบเท่ากันทั้งหน้า
    cv.dilate(gray, bg, kernel);
    cv.medianBlur(bg, bg, 31);
    const flat = new cv.Mat();
    cv.divide(gray, bg, flat, 255);
    try { q = quality(gray, flat); } catch { q = null; } finally { flat.delete(); }
    if (mode === "color") {
      const channels = new cv.MatVector();
      cv.split(warped, channels);
      for (let i = 0; i < 3; i++) {
        const ch = channels.get(i);
        cv.divide(ch, bg, ch, 255);
        channels.set(i, ch);
        ch.delete();
      }
      cv.merge(channels, out);
      channels.delete();
    } else {
      const norm = new cv.Mat();
      cv.divide(gray, bg, norm, 255);
      if (mode === "gray") {
        cv.normalize(norm, norm, 0, 255, cv.NORM_MINMAX);
        cv.cvtColor(norm, out, cv.COLOR_GRAY2RGBA);
      } else {
        const bw = new cv.Mat();
        cv.threshold(norm, bw, STRENGTH[strength] || STRENGTH.normal, 255, cv.THRESH_BINARY);
        cv.medianBlur(bw, bw, 3); // ลบจุดรบกวนเล็กๆ
        // ขอบภาพหลังดัดมักติดขอบกระดาษ/โต๊ะเป็นเส้นประดำ — ทาขาวขอบบางๆ รอบหน้า
        const m = Math.max(3, Math.round(0.006 * Math.min(width, height)));
        cv.rectangle(bw, new cv.Point(0, 0), new cv.Point(width - 1, height - 1), new cv.Scalar(255), m * 2);
        cv.cvtColor(bw, out, cv.COLOR_GRAY2RGBA);
        bw.delete();
      }
      norm.delete();
    }
    if (out.channels() === 3) cv.cvtColor(out, out, cv.COLOR_RGB2RGBA);
    return { image: new ImageData(new Uint8ClampedArray(out.data), out.cols, out.rows), quality: q };
  } finally {
    [src, from, to, M, warped, gray, bg, out, kernel].forEach((m) => m.delete());
  }
}

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "init") {
      const ms = await loadOpenCV(msg.cvUrl);
      self.postMessage({ type: "ready", ms });
      return;
    }
    const t0 = performance.now();
    if (msg.type === "detect") {
      self.postMessage({ id: msg.id, corners: detect(msg.image), ms: performance.now() - t0 });
    } else if (msg.type === "process") {
      const { image, quality: q } = process(msg);
      self.postMessage({ id: msg.id, image, quality: q, ms: performance.now() - t0 }, [image.data.buffer]);
    }
  } catch (err) {
    self.postMessage({ id: msg.id, type: msg.type === "init" ? "error" : undefined, error: String(err?.message || err) });
  }
};
