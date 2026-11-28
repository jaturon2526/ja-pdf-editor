// สแกนเอกสารด้วยกล้องมือถือ/แท็บเล็ต: กล้องหลัง + ตรวจขอบอัตโนมัติ → ปรับ 4 มุม → ขาวดำแบบเครื่องถ่ายเอกสาร
// → ถ่ายต่อเนื่องหลายหน้า → บันทึกเป็น PDF (OCR ค้นหา/เซ็นเซอร์ได้) ในเอกสารของฉัน
// ดูแผน: Project doc claude/phase-document-scanner-plan.md
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createScan, getScanStatus, openFile } from "../api.js";
import { getAiQuota } from "../api/auth.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import CornerEditor from "../components/scan/CornerEditor.jsx";
import useWordConversion from "../hooks/useWordConversion.jsx";
import { cameraSupported, capturePhoto, isInAppBrowser, openRearCamera, setTorch, stopStream, toImageData } from "../scan/camera.js";
import { INSET_FRAME, FULL_FRAME, scanFilename, smoothCorners } from "../scan/geometry.js";
import { bitmapToJpeg, blobToImageData, encodePage } from "../scan/imageUtils.js";
import { createScanEngine } from "../scan/scanEngine.js";
import { clearPages, deletePage, loadPages, savePage } from "../scan/scanStore.js";

const MAX_PAGES = 50;
const MODES = [
  { value: "bw", labelKey: "scan.modeBw" },
  { value: "gray", labelKey: "scan.modeGray" },
  { value: "color", labelKey: "scan.modeColor" },
];
const STRENGTHS = [
  { value: "light", labelKey: "scan.strengthLight" },
  { value: "normal", labelKey: "scan.strengthNormal" },
  { value: "dark", labelKey: "scan.strengthDark" },
];

function drawLiveQuad(canvas, video, corners) {
  if (!canvas || !video) return;
  const w = video.clientWidth;
  const h = video.clientHeight;
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  if (!corners) return;
  const vw = video.videoWidth || 1;
  const vh = video.videoHeight || 1;
  const s = Math.min(w / vw, h / vh); // วิดีโอแสดงแบบ object-contain — เห็นเท่ากับที่ถ่ายได้จริง
  const ox = (w - vw * s) / 2;
  const oy = (h - vh * s) / 2;
  ctx.beginPath();
  corners.forEach((c, i) => {
    const x = ox + c.x * vw * s;
    const y = oy + c.y * vh * s;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(34,197,94,0.2)";
  ctx.strokeStyle = "#22c55e";
  ctx.lineWidth = 3;
  ctx.fill();
  ctx.stroke();
}

function Btn({ children, className = "", ...props }) {
  return (
    <button type="button" className={`min-h-[48px] px-4 rounded-xl font-medium active:scale-95 transition disabled:opacity-40 ${className}`} {...props}>
      {children}
    </button>
  );
}

export default function ScanPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const engineRef = useRef(null);
  const camRef = useRef(null);
  const cornersRef = useRef(null);
  const busyRef = useRef(false);
  const loopRef = useRef(0);
  const fileRef = useRef(null);
  const startedAtRef = useRef(null);

  const [screen, setScreen] = useState("loading"); // loading | camera | adjust | review | saving | done
  const [engineReady, setEngineReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [torch, setTorchState] = useState({ available: false, on: false });
  const [found, setFound] = useState(false);
  const [pages, setPages] = useState([]); // {id, order, source, sourceUrl, corners, rotation, thumbUrl, out, outKey}
  const [draft, setDraft] = useState(null); // {id?, source, sourceUrl, corners, rotation}
  const [qualityWarn, setQualityWarn] = useState(null); // หน้าที่แปลงแล้วแต่ภาพเบลอ/มีแสงสะท้อน — รอผู้ใช้ตัดสินใจ
  const [mode, setMode] = useState("bw");
  const [strength, setStrength] = useState("normal");
  const [outputMode, setOutputMode] = useState("image"); // image | rebuild
  const [useAi, setUseAi] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(null);
  const [busy, setBusy] = useState("");
  const [filename, setFilename] = useState("");
  const [progress, setProgress] = useState(null); // {label, value}
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const wordConversion = useWordConversion({
    onMessage: (type, text) => (type === "error" ? setError(text) : setNotice(text)),
  });

  // ---------- เริ่มต้น: ตัวประมวลผลภาพ + กู้หน้าที่สแกนค้างไว้ ----------
  useEffect(() => {
    const engine = createScanEngine();
    engineRef.current = engine;
    engine.ready
      .then(() => setEngineReady(true))
      .catch((e) => {
        const msg = e?.message;
        setError(
          !msg || msg === "SCAN_ENGINE_LOAD_FAILED"
            ? t("scanPage.engineLoadFailedSimple")
            : t("scanPage.engineLoadFailed", { message: msg }),
        );
      });
    loadPages().then((saved) => {
      if (saved.length) {
        const restored = saved.map((p) => ({ ...p, sourceUrl: URL.createObjectURL(p.source), thumbUrl: null, out: null, outKey: null }));
        setPages(restored);
        startedAtRef.current = new Date(saved[0].createdAt);
        setFilename(scanFilename(startedAtRef.current));
        setScreen("review");
      } else {
        setScreen("camera");
      }
    }).catch(() => setScreen("camera"));
    return () => {
      engine.terminate();
      stopStream(camRef.current?.stream);
      cancelAnimationFrame(loopRef.current);
    };
  }, [t]);

  // ---------- กล้อง ----------
  const stopCamera = useCallback(() => {
    cancelAnimationFrame(loopRef.current);
    stopStream(camRef.current?.stream);
    camRef.current = null;
    cornersRef.current = null;
  }, []);

  const liveLoop = useCallback(() => {
    const video = videoRef.current;
    if (!camRef.current || !video) return;
    if (engineReady && !busyRef.current && video.readyState >= 2) {
      busyRef.current = true;
      engineRef.current.detect(toImageData(video, 360))
        .then(({ corners }) => {
          cornersRef.current = corners ? smoothCorners(cornersRef.current, corners, 0.5) : null;
          setFound(!!corners);
          drawLiveQuad(overlayRef.current, video, cornersRef.current);
        })
        .catch(() => {})
        .finally(() => { busyRef.current = false; });
    }
    loopRef.current = requestAnimationFrame(liveLoop);
  }, [engineReady]);

  useEffect(() => {
    if (screen !== "camera") return undefined;
    let cancelled = false;
    void (async () => {
      if (!cameraSupported()) {
        setCameraError(isInAppBrowser()
          ? t("scanPage.cameraInAppError")
          : t("scanPage.cameraUnsupportedError"));
        return;
      }
      try {
        const cam = await openRearCamera();
        if (cancelled) { stopStream(cam.stream); return; }
        camRef.current = cam;
        const video = videoRef.current;
        video.srcObject = cam.stream;
        await video.play();
        setTorchState({ available: !!cam.caps.torch, on: false });
        setCameraError("");
        loopRef.current = requestAnimationFrame(liveLoop);
      } catch (e) {
        setCameraError(e?.name === "NotAllowedError"
          ? t("scanPage.cameraDeniedError")
          : t("scanPage.cameraOpenFailed", { message: e?.message || e }));
      }
    })();
    return () => { cancelled = true; stopCamera(); };
  }, [screen, liveLoop, stopCamera, t]);

  // กลับมาที่แอปหลังสลับไปแอปอื่น — iOS หยุดกล้องให้ เปิดใหม่
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible" && screen === "camera" && camRef.current?.track.readyState === "ended") {
        setScreen("loading");
        setTimeout(() => setScreen("camera"), 0);
      }
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [screen]);

  async function detectOn(blobOrBitmap) {
    if (!engineReady) return null;
    const small = blobOrBitmap instanceof Blob ? await blobToImageData(blobOrBitmap, 640) : toImageData(blobOrBitmap, 640);
    const { corners } = await engineRef.current.detect(small);
    return corners;
  }

  async function onShutter() {
    if (!camRef.current || busy) return;
    if (pages.length >= MAX_PAGES) { setError(t("scanPage.maxPagesError", { max: MAX_PAGES })); return; }
    setBusy(t("scanPage.capturing"));
    try {
      const bitmap = await capturePhoto(camRef.current.track, videoRef.current);
      const corners = await detectOn(bitmap);
      const source = await bitmapToJpeg(bitmap);
      bitmap.close?.();
      setDraft({ source, sourceUrl: URL.createObjectURL(source), corners: corners || INSET_FRAME, rotation: 0 });
      setScreen("adjust");
    } catch (e) {
      setError(t("scanPage.captureFailed", { message: e.message }));
    } finally {
      setBusy("");
    }
  }

  async function onSystemCamera(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(t("scanPage.openingImage"));
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      const corners = await detectOn(bitmap);
      const source = await bitmapToJpeg(bitmap);
      bitmap.close?.();
      setDraft({ source, sourceUrl: URL.createObjectURL(source), corners: corners || INSET_FRAME, rotation: 0 });
      setScreen("adjust");
    } catch (err) {
      setError(t("scanPage.openImageFailed", { message: err.message }));
    } finally {
      setBusy("");
    }
  }

  async function toggleTorch() {
    try {
      await setTorch(camRef.current.track, !torch.on);
      setTorchState((t) => ({ ...t, on: !t.on }));
    } catch { setTorchState({ available: false, on: false }); }
  }

  // ---------- ประมวลผลหน้า ----------
  async function renderPage(page, m = mode, s = strength) {
    const key = `${m}|${s}|${page.rotation}|${page.corners.map((c) => `${c.x.toFixed(4)},${c.y.toFixed(4)}`).join(";")}`;
    if (page.out && page.outKey === key) return page;
    const full = await blobToImageData(page.source, 4000);
    const { image, quality } = await engineRef.current.process(full, page.corners, m, s);
    const out = await encodePage(image, m, page.rotation);
    if (page.thumbUrl) URL.revokeObjectURL(page.thumbUrl);
    return { ...page, out: out.blob, outKey: key, thumbUrl: URL.createObjectURL(out.thumbBlob), quality };
  }

  async function confirmDraft() {
    if (!draft || !engineReady) return;
    setBusy(t("scanPage.processingImage"));
    try {
      const isNew = !draft.id;
      const base = isNew
        ? { id: crypto.randomUUID?.() || String(Date.now()), order: Date.now(), createdAt: Date.now(), thumbUrl: null, out: null }
        : pages.find((p) => p.id === draft.id);
      const page = await renderPage({ ...base, source: draft.source, sourceUrl: draft.sourceUrl, corners: draft.corners, rotation: draft.rotation });
      // ภาพเบลอ/มีแสงสะท้อน → ถามก่อนว่าจะถ่ายใหม่ไหม (OCR อ่านภาพเบลอไม่ได้ แก้ทีหลังไม่ได้)
      if (isNew && (page.quality?.blurry || page.quality?.glary)) {
        setQualityWarn(page);
        return;
      }
      commitPage(page, isNew);
    } catch (e) {
      setError(t("scanPage.processImageFailed", { message: e.message }));
    } finally {
      setBusy("");
    }
  }

  function commitPage(page, isNew) {
    void savePage({ id: page.id, order: page.order, createdAt: page.createdAt, source: page.source, corners: page.corners, rotation: page.rotation });
    if (isNew) {
      if (!startedAtRef.current) {
        startedAtRef.current = new Date();
        setFilename(scanFilename(startedAtRef.current));
      }
      setPages((ps) => [...ps, page]);
      setDraft(null);
      setScreen("camera"); // ถ่ายหน้าถัดไปต่อได้ทันที
    } else {
      setPages((ps) => ps.map((p) => (p.id === page.id ? page : p)));
      setDraft(null);
      setScreen("review");
    }
  }

  function retakeAfterWarning() {
    if (qualityWarn?.thumbUrl) URL.revokeObjectURL(qualityWarn.thumbUrl);
    setQualityWarn(null);
    discardDraft();
  }

  function keepAfterWarning() {
    const page = qualityWarn;
    setQualityWarn(null);
    if (page) commitPage(page, true);
  }

  function discardDraft() {
    const wasEditing = !!draft?.id;
    if (draft && !draft.id) URL.revokeObjectURL(draft.sourceUrl);
    setDraft(null);
    setScreen(wasEditing ? "review" : "camera");
  }

  // หน้าที่กู้มา/เปลี่ยนโหมด → สร้างภาพย่อใหม่ทีละหน้า
  useEffect(() => {
    if (screen !== "review" || !engineReady) return undefined;
    let cancelled = false;
    void (async () => {
      for (const p of pages) {
        if (cancelled) return;
        const key = `${mode}|${strength}|${p.rotation}`;
        if (p.out && p.outKey?.startsWith(key)) continue;
        setBusy(t("scanPage.adjustingMode"));
        try {
          const updated = await renderPage(p);
          if (!cancelled) setPages((ps) => ps.map((x) => (x.id === updated.id ? updated : x)));
        } catch { /* แสดงหน้าเดิมต่อ */ }
      }
      if (!cancelled) setBusy("");
    })();
    return () => { cancelled = true; };
    // renderPage อ่านค่า mode/strength ล่าสุดอยู่แล้ว
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, engineReady, mode, strength, pages.length, t]);

  // ตรวจสิทธิ์ AI เมื่อเข้าหน้าตรวจสอบเอกสาร (ครั้งเดียว)
  useEffect(() => {
    if (screen !== "review" || aiAvailable !== null) return undefined;
    let cancelled = false;
    getAiQuota()
      .then((q) => { if (!cancelled) setAiAvailable(q.ai_available !== false); })
      .catch(() => { if (!cancelled) setAiAvailable(false); });
    return () => { cancelled = true; };
  }, [screen, aiAvailable]);

  function movePage(index, delta) {
    setPages((ps) => {
      const next = [...ps];
      const j = index + delta;
      if (j < 0 || j >= next.length) return ps;
      [next[index], next[j]] = [next[j], next[index]];
      next.forEach((p, k) => { p.order = k; void savePage({ id: p.id, order: k, createdAt: p.createdAt, source: p.source, corners: p.corners, rotation: p.rotation }); });
      return next;
    });
  }

  function removePage(id) {
    setPages((ps) => {
      const p = ps.find((x) => x.id === id);
      if (p) { URL.revokeObjectURL(p.sourceUrl); if (p.thumbUrl) URL.revokeObjectURL(p.thumbUrl); }
      return ps.filter((x) => x.id !== id);
    });
    void deletePage(id);
  }

  function editPage(p) {
    setDraft({ id: p.id, source: p.source, sourceUrl: p.sourceUrl, corners: p.corners, rotation: p.rotation });
    setScreen("adjust");
  }

  async function startOver() {
    if (pages.length && !window.confirm(t("scanPage.confirmStartOver", { count: pages.length }))) return;
    pages.forEach((p) => { URL.revokeObjectURL(p.sourceUrl); if (p.thumbUrl) URL.revokeObjectURL(p.thumbUrl); });
    setPages([]);
    startedAtRef.current = null;
    await clearPages();
    setScreen("camera");
  }

  // ---------- บันทึก ----------
  // โหมดขาวดำ: ส่งภาพเทาที่ลบเงาแล้ว (ก่อนตัดเป็นขาวดำ) ไปให้เซิร์ฟเวอร์อ่านข้อความด้วย — เส้นบาง/วรรณยุกต์ครบกว่า
  // เซิร์ฟเวอร์อ่านทั้งสองภาพแล้วเลือกผลที่ดีกว่า ภาพเทาใช้อ่านอย่างเดียว ไม่เก็บลงไฟล์
  async function ocrImage(page) {
    try {
      const full = await blobToImageData(page.source, 4000);
      const { image } = await engineRef.current.process(full, page.corners, "gray", strength);
      return (await encodePage(image, "gray", page.rotation)).blob;
    } catch {
      return null; // ไม่มีภาพเทา → เซิร์ฟเวอร์อ่านจากภาพขาวดำตามเดิม
    }
  }

  async function save() {
    if (!pages.length) return;
    setError("");
    setScreen("saving");
    try {
      const blobs = [];
      const ocrBlobs = [];
      for (let i = 0; i < pages.length; i++) {
        setProgress({ label: t("scanPage.preparingPage", { current: i + 1, total: pages.length }), value: (i / pages.length) * 0.2 });
        const p = await renderPage(pages[i]);
        blobs.push(p.out);
        ocrBlobs.push(mode === "bw" ? await ocrImage(p) : null);
      }
      const name = filename.trim() || scanFilename(startedAtRef.current || new Date());
      const aiEnabled = outputMode === "rebuild" && useAi && aiAvailable !== false;
      let savingLabel = t("scanPage.creatingPdfOcr");
      if (outputMode === "rebuild") {
        savingLabel = aiEnabled
          ? t("scanPage.rebuildingPdfAi")
          : t("scanPage.rebuildingPdf");
      }
      const { task_id: taskId } = await createScan(
        name,
        blobs,
        (f) => setProgress({ label: t("scanPage.uploading"), value: 0.2 + f * 0.3 }),
        ocrBlobs,
        { outputMode, useAi: aiEnabled },
      );
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await getScanStatus(taskId);
        if (st.status === "failed") throw new Error(st.error_message || t("scanPage.createPdfFailed"));
        if (st.status === "completed") {
          setResult({ ...st.file, outputMode: st.output_mode || outputMode, aiStatus: st.ai_status || null });
          break;
        }
        setProgress({ label: savingLabel, value: 0.5 + (st.progress / 100) * 0.5 });
      }
      await clearPages();
      setScreen("done");
    } catch (e) {
      setError(e.message);
      setScreen("review");
    } finally {
      setProgress(null);
    }
  }

  async function openResult() {
    try {
      const res = await openFile(result.session_id);
      void navigate(`/editor/${res.session_id}`);
    } catch (e) {
      setError(e.message);
    }
  }

  function exitScan() {
    if (pages.length && screen !== "done" && !window.confirm(t("scanPage.confirmExit"))) return;
    void navigate("/dashboard");
  }

  // ---------- หน้าจอ ----------
  const safe = { paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" };
  const lastThumb = pages[pages.length - 1]?.thumbUrl;

  let scanHintText = "";
  if (!cameraError) {
    if (!engineReady) {
      scanHintText = t("scanPage.loadingDetector");
    } else if (found) {
      scanHintText = t("scanPage.docFoundHint");
    } else {
      scanHintText = t("scanPage.placeDocHint");
    }
  }

  return (
    <div className="fixed inset-0 bg-black text-white flex flex-col overflow-hidden overscroll-none" style={safe}>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => void onSystemCamera(e)} />

      {/* แถบบน */}
      <div className="flex items-center gap-2 px-3 py-2 bg-black/70 z-10">
        <button type="button" className="min-h-[44px] min-w-[44px] text-2xl" aria-label={t("common.close")} onClick={exitScan}>×</button>
        <h1 className="font-semibold">{t("scan.title")}</h1>
        {pages.length > 0 && screen !== "done" && <span className="ml-auto text-sm text-slate-300">{t("scan.pagesCount", { count: pages.length })}</span>}
      </div>

      {notice && (
        <div className="mx-3 my-2 p-3 rounded-lg bg-emerald-900/80 text-emerald-50 text-sm z-10 flex gap-2" role="status">
          <span className="flex-1">{notice}</span>
          <button type="button" aria-label={t("scanPage.dismissMessage")} onClick={() => setNotice("")}>×</button>
        </div>
      )}
      {error && (
        <div className="mx-3 my-2 p-3 rounded-lg bg-red-900/80 text-red-50 text-sm z-10 flex gap-2" role="alert">
          <span className="flex-1">{error}</span>
          <button type="button" aria-label={t("scanPage.dismissMessage")} onClick={() => setError("")}>×</button>
        </div>
      )}

      {screen === "loading" && <div className="flex-1 flex items-center justify-center text-slate-300">{t("scanPage.preparing")}</div>}

      {screen === "camera" && (
        <>
          <div className="relative flex-1">
            <video ref={videoRef} playsInline muted autoPlay className="absolute inset-0 w-full h-full object-contain" />
            <canvas ref={overlayRef} className="absolute inset-0 w-full h-full pointer-events-none" />
            <div className="absolute top-3 inset-x-0 flex justify-center pointer-events-none">
              <span className="px-3 py-1 rounded-full bg-black/60 text-sm" data-testid="scan-hint">
                {scanHintText}
              </span>
            </div>
            {cameraError && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center">
                <p className="text-slate-200">{cameraError}</p>
                <Btn className="bg-blue-600" onClick={() => fileRef.current?.click()}>{t("scanPage.deviceCamera")}</Btn>
              </div>
            )}
          </div>
          <div className="grid grid-cols-3 items-center px-4 py-4 bg-black">
            <div className="flex items-center gap-2">
              {pages.length > 0 ? (
                <button type="button" className="relative w-14 h-14 rounded-lg overflow-hidden border-2 border-white/70 bg-slate-800" aria-label={t("scanPage.viewScannedPages", { count: pages.length })} onClick={() => setScreen("review")}>
                  {lastThumb && <img src={lastThumb} alt="" className="w-full h-full object-cover" />}
                  <span className="absolute -top-1 -right-1 min-w-[22px] h-[22px] px-1 rounded-full bg-blue-600 text-xs flex items-center justify-center">{pages.length}</span>
                </button>
              ) : (
                <button type="button" className="min-h-[48px] px-2 text-sm text-slate-300" onClick={() => fileRef.current?.click()}>{t("scanPage.deviceCamera")}</button>
              )}
            </div>
            <div className="flex justify-center">
              <button type="button" aria-label={t("scanPage.capturePhoto")} disabled={!!busy || !!cameraError} onClick={() => void onShutter()}
                className="w-[76px] h-[76px] rounded-full border-4 border-white flex items-center justify-center disabled:opacity-40 active:scale-95 transition">
                <span className={`block w-[60px] h-[60px] rounded-full ${found ? "bg-emerald-400" : "bg-white"}`} />
              </button>
            </div>
            <div className="flex justify-end gap-2">
              {torch.available && <Btn className={torch.on ? "bg-amber-400 text-black" : "bg-white/15"} aria-label={t("scanPage.torch")} onClick={() => void toggleTorch()}>⚡</Btn>}
              {pages.length > 0 && <Btn className="bg-blue-600" onClick={() => setScreen("review")}>{t("scanPage.done")}</Btn>}
            </div>
          </div>
        </>
      )}

      {screen === "adjust" && draft && (
        <>
          <div className="flex-1 relative bg-slate-950">
            <CornerEditor src={draft.sourceUrl} corners={draft.corners} onChange={(c) => setDraft((d) => ({ ...d, corners: c }))} />
          </div>
          <p className="text-center text-xs text-slate-400 py-1 px-3">{t("scanPage.cornerHint")}</p>
          <div className="flex flex-wrap justify-between gap-2 px-3 py-3 bg-black">
            <Btn className="bg-white/15" onClick={discardDraft}>{draft.id ? t("scanPage.cancel") : t("scanPage.retake")}</Btn>
            <Btn className="bg-white/15" onClick={() => setDraft((d) => ({ ...d, corners: FULL_FRAME }))}>{t("scanPage.fullImage")}</Btn>
            <Btn className="bg-white/15" aria-label={t("scanPage.rotate90Aria")} onClick={() => setDraft((d) => ({ ...d, rotation: (d.rotation + 90) % 360 }))}>↻ {draft.rotation ? `${draft.rotation}°` : t("scanPage.rotate")}</Btn>
            <Btn className="bg-emerald-500 text-black" disabled={!engineReady || !!busy} onClick={() => void confirmDraft()}>{draft.id ? t("scanPage.saveChanges") : t("scanPage.usePhoto")}</Btn>
          </div>
          {qualityWarn && (
            <div className="absolute inset-0 z-20 flex items-end sm:items-center justify-center bg-black/60 p-4" role="alertdialog" aria-labelledby="scan-quality-title" data-testid="scan-quality-warning">
              <div className="w-full max-w-sm rounded-2xl bg-slate-900 border border-white/10 p-4 space-y-3">
                <div className="flex gap-3 items-start">
                  {qualityWarn.thumbUrl && <img src={qualityWarn.thumbUrl} alt="" className="w-16 rounded bg-white" />}
                  <div>
                    <p id="scan-quality-title" className="font-semibold text-amber-300">
                      {qualityWarn.quality?.blurry ? t("scanPage.blurryTitle") : t("scanPage.glaryTitle")}
                    </p>
                    <p className="text-sm text-slate-300 mt-1">
                      {qualityWarn.quality?.blurry
                        ? t("scanPage.blurryDesc")
                        : t("scanPage.glaryDesc")}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2 justify-end">
                  <Btn className="bg-white/15" onClick={keepAfterWarning}>{t("scanPage.keepPhoto")}</Btn>
                  <Btn className="bg-emerald-500 text-black" onClick={retakeAfterWarning}>{t("scanPage.retake")}</Btn>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {screen === "review" && (
        <>
          <div className="flex-1 overflow-y-auto bg-slate-900 p-3">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="scan-pages">
              {pages.map((p, i) => (
                <div key={p.id} className="bg-slate-800 rounded-xl overflow-hidden flex flex-col">
                  <button type="button" className="relative aspect-[3/4] bg-white flex items-center justify-center" onClick={() => editPage(p)} aria-label={t("scanPage.adjustPageAria", { page: i + 1 })}>
                    {p.thumbUrl ? <img src={p.thumbUrl} alt={t("scanPage.pageAlt", { page: i + 1 })} className="max-w-full max-h-full object-contain" /> : <span className="text-slate-400 text-sm">{t("scanPage.converting")}</span>}
                    <span className="absolute top-1 left-1 px-2 py-0.5 rounded bg-black/70 text-xs">{i + 1}</span>
                    {(p.quality?.blurry || p.quality?.glary) && (
                      <span className="absolute top-1 right-1 px-1.5 py-0.5 rounded bg-amber-400 text-black text-[11px] font-semibold" title={p.quality.blurry ? t("scanPage.blurryBadgeTitle") : t("scanPage.glaryBadgeTitle")}>⚠ {p.quality.blurry ? t("scanPage.blurryBadge") : t("scanPage.glaryBadge")}</span>
                    )}
                  </button>
                  <div className="flex justify-between">
                    <button type="button" className="flex-1 min-h-[44px] disabled:opacity-30" disabled={i === 0} aria-label={t("scanPage.movePageUpAria", { page: i + 1 })} onClick={() => movePage(i, -1)}>←</button>
                    <button type="button" className="flex-1 min-h-[44px]" aria-label={t("scanPage.editPageAria", { page: i + 1 })} onClick={() => editPage(p)}>✎</button>
                    <button type="button" className="flex-1 min-h-[44px] text-red-300" aria-label={t("scanPage.deletePageAria", { page: i + 1 })} onClick={() => removePage(p.id)}>🗑</button>
                    <button type="button" className="flex-1 min-h-[44px] disabled:opacity-30" disabled={i === pages.length - 1} aria-label={t("scanPage.movePageDownAria", { page: i + 1 })} onClick={() => movePage(i, 1)}>→</button>
                  </div>
                </div>
              ))}
              {pages.length < MAX_PAGES && (
                <button type="button" className="aspect-[3/4] rounded-xl border-2 border-dashed border-slate-600 text-slate-300 flex flex-col items-center justify-center gap-1" onClick={() => setScreen("camera")}>
                  <span className="text-3xl">+</span>{t("scanPage.captureNextPage")}
                </button>
              )}
            </div>
          </div>
          <div className="bg-black px-3 py-3 space-y-3">
            <div className="flex flex-wrap gap-2 items-center">
              {MODES.map((m) => (
                <button key={m.value} type="button" className={`min-h-[40px] px-3 rounded-lg text-sm ${mode === m.value ? "bg-blue-600" : "bg-white/10"}`} onClick={() => setMode(m.value)}>{t(m.labelKey)}</button>
              ))}
              {mode === "bw" && <span className="w-px h-6 bg-white/20 mx-1" />}
              {mode === "bw" && STRENGTHS.map((s) => (
                <button key={s.value} type="button" className={`min-h-[40px] px-3 rounded-lg text-sm ${strength === s.value ? "bg-blue-600" : "bg-white/10"}`} onClick={() => setStrength(s.value)}>{t(s.labelKey)}</button>
              ))}
              {busy && <span className="text-xs text-slate-400">{busy}</span>}
            </div>
            <div className="space-y-2">
              <span className="block text-xs text-slate-400">{t("scan.outputFormat")}</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  data-testid="scan-output-image"
                  className={`min-h-[48px] px-3 py-2 rounded-xl text-left border transition ${outputMode === "image" ? "bg-blue-600/25 border-blue-400 text-white" : "bg-white/5 border-white/10 text-slate-300"}`}
                  onClick={() => setOutputMode("image")}
                >
                  <div className="text-sm font-medium">{t("scan.outputImage")}</div>
                  <div className="text-[11px] text-slate-300/80">{t("scan.outputImageHint")}</div>
                </button>
                <button
                  type="button"
                  data-testid="scan-output-rebuild"
                  className={`min-h-[48px] px-3 py-2 rounded-xl text-left border transition ${outputMode === "rebuild" ? "bg-emerald-600/25 border-emerald-400 text-white" : "bg-white/5 border-white/10 text-slate-300"}`}
                  onClick={() => setOutputMode("rebuild")}
                >
                  <div className="text-sm font-medium">{t("scan.outputRebuild")}</div>
                  <div className="text-[11px] text-slate-300/80">{t("scan.outputRebuildHint")}</div>
                </button>
              </div>
              {outputMode === "rebuild" && (
                <div className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 space-y-2 text-xs">
                  <p className="text-emerald-300">{t("scan.rebuildAutoThai")}</p>
                  {aiAvailable !== false && (
                    <div className="flex items-start gap-2.5 pt-1 border-t border-white/10">
                      <input
                        id="scan-use-ai"
                        type="checkbox"
                        data-testid="scan-use-ai"
                        checked={useAi}
                        onChange={(e) => setUseAi(e.target.checked)}
                        className="mt-0.5 h-4 w-4 rounded accent-emerald-500"
                      />
                      <label htmlFor="scan-use-ai" className="cursor-pointer select-none">
                        <span className="block text-slate-100 font-medium">{t("scan.useAiTitle")}</span>
                        <span className="block text-[11px] text-slate-400">{t("scan.useAiHint")}</span>
                      </label>
                    </div>
                  )}
                </div>
              )}
            </div>
            <label className="block text-xs text-slate-400">
              {t("scan.filename")}
              <input value={filename} onChange={(e) => setFilename(e.target.value)} className="mt-1 w-full rounded-lg bg-white/10 px-3 py-2 text-base text-white" />
            </label>
            <div className="flex gap-2">
              <Btn className="bg-white/10 text-sm" onClick={() => void startOver()}>{t("scan.startOver")}</Btn>
              <Btn className="flex-1 bg-emerald-500 text-black" disabled={!pages.length || !!busy} onClick={() => void save()}>{t("scan.savePdf", { count: pages.length })}</Btn>
            </div>
          </div>
        </>
      )}

      {screen === "saving" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6" data-testid="scan-saving">
          <p className="text-slate-200">{progress?.label || t("common.saving")}</p>
          <div className="w-full max-w-sm h-2 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full bg-emerald-400 transition-all" style={{ width: `${Math.round((progress?.value || 0) * 100)}%` }} />
          </div>
          <p className="text-xs text-slate-400">{t("scan.doNotClose")}</p>
        </div>
      )}

      {screen === "done" && result && (
        <div className="flex-1 flex flex-col items-center justify-center gap-5 p-6 text-center" data-testid="scan-done">
          <div className="text-5xl">✓</div>
          <div>
            <p className="text-lg font-semibold">{t("scan.savedTitle")}</p>
            <p className="text-slate-300 break-all mt-1">{result.filename}</p>
            {result.outputMode === "rebuild" ? (
              <div className="mt-2 space-y-1">
                <p className="text-xs text-slate-300">{t("scan.savedRebuildDesc")}</p>
                {result.aiStatus === "ai" && (
                  <p className="text-xs text-emerald-300">{t("scan.savedAiOk")}</p>
                )}
                {result.aiStatus === "fallback" && (
                  <p className="text-xs text-amber-300">{t("scan.savedAiFallback")}</p>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400 mt-1">{t("scan.savedImageDesc")}</p>
            )}
          </div>
          <div className="flex flex-col w-full max-w-xs gap-2">
            <Btn className="bg-blue-600" onClick={() => void openResult()}>{t("scan.openFile")}</Btn>
            <Btn className="bg-white/10" data-testid="scan-to-word"
              onClick={() => wordConversion.request({ fileId: result.id, filename: result.filename })}>
              {t("scan.convertToWord")}
            </Btn>
            <Btn className="bg-white/10" onClick={() => void navigate("/dashboard")}>{t("scan.backToDocs")}</Btn>
            <Btn className="bg-white/10" onClick={() => { setPages([]); setResult(null); startedAtRef.current = null; setScreen("camera"); }}>{t("scan.scanNew")}</Btn>
          </div>
        </div>
      )}

      {wordConversion.dialogs}

      {busy && screen !== "review" && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20 pointer-events-none">
          <span className="px-4 py-2 rounded-full bg-black/80 text-sm">{busy}</span>
        </div>
      )}
    </div>
  );
}
