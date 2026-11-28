// สร้างรูปลายเซ็น 4 วิธี (ใช้ร่วมกันทั้งลายเซ็นอิเล็กทรอนิกส์และลายเซ็นดิจิทัล):
// ลายเซ็นที่บันทึกไว้ (ปลดล็อกด้วย Passkey) · พิมพ์ข้อความ · ใส่รูปภาพ (ลบพื้นขาวให้อัตโนมัติ) · เซ็นสดด้วยนิ้ว/ปากกา/เมาส์
// optional=true: เพิ่มแท็บ "ไม่ใส่รูป" (ลายเซ็นดิจิทัลแสดงเป็นข้อความได้)
// ref.getDataUrl() → PNG data URL หรือ null · onReadyChange(boolean) บอกว่ากด "ตกลง" ได้หรือยัง
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";
import { getSavedSignatureBlob, listSavedSignatures } from "../../api/signature.js";
import {
  sigPasskeyErrorMessage,
  supportsWebAuthn,
  unlockSignatureWithPasskey,
} from "../../utils/sigPasskey.js";
import SignaturePad from "./SignaturePad.jsx";

export const SIGN_COLOR_PRESETS = [
  { key: "black", labelKey: "editor.modals.sigCreator.colorBlack", value: "#12172b" },
  { key: "blue", labelKey: "editor.modals.sigCreator.colorBlue", value: "#1a56db" },
  { key: "red", labelKey: "editor.modals.sigCreator.colorRed", value: "#d32f2f" },
];

const TEXT_FONTS = [
  { key: "script", labelKey: "editor.modals.sigCreator.fontScript", css: 'italic {size}px "Segoe Script", "Brush Script MT", "Snell Roundhand", cursive, sans-serif' },
  { key: "thai", labelKey: "editor.modals.sigCreator.fontThai", css: '{size}px "Sarabun", "Thonburi", "Leelawadee UI", sans-serif' },
  { key: "serif", labelKey: "editor.modals.sigCreator.fontSerif", css: 'italic {size}px Georgia, "Times New Roman", serif' },
];

const isTouch = () => typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

// รูปถ่ายลายเซ็นบนกระดาษ: ทำพื้นสีขาว/เทาอ่อนให้โปร่งใส แล้วครอปให้พอดี
export async function cleanSignatureImage(dataUrl, removeBackground) {
  const img = await new Promise((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = reject;
    el.src = dataUrl;
  });
  const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, w, h);
  if (!removeBackground) return canvas.toDataURL("image/png");
  const data = ctx.getImageData(0, 0, w, h);
  const px = data.data;
  let minX = w; let minY = h; let maxX = -1; let maxY = -1;
  for (let i = 0; i < px.length; i += 4) {
    const lum = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
    if (lum > 200) {
      px[i + 3] = 0;
    } else if (lum > 150) {
      px[i + 3] = Math.round(px[i + 3] * ((200 - lum) / 50)); // ขอบนุ่ม
    }
    if (px[i + 3] > 40) {
      const p = i / 4;
      const x = p % w;
      const y = (p - x) / w;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  ctx.putImageData(data, 0, 0);
  if (maxX < 0) return canvas.toDataURL("image/png");
  const pad = Math.round(Math.max(maxX - minX, maxY - minY) * 0.04) + 4;
  const cx = Math.max(0, minX - pad);
  const cy = Math.max(0, minY - pad);
  const cw = Math.min(w, maxX + pad) - cx;
  const ch = Math.min(h, maxY + pad) - cy;
  const out = document.createElement("canvas");
  out.width = cw;
  out.height = ch;
  out.getContext("2d").drawImage(canvas, cx, cy, cw, ch, 0, 0, cw, ch);
  return out.toDataURL("image/png");
}

function ColorPicker({ value, onChange }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="text-sm font-medium text-slate-700">{t("editor.modals.sigCreator.penColor")}</span>
      <div className="flex items-center gap-2" role="radiogroup" aria-label={t("editor.modals.sigCreator.penColor")}>
        {SIGN_COLOR_PRESETS.map((c) => {
          const label = t(c.labelKey);
          return (
            <button
              key={c.key}
              type="button"
              role="radio"
              aria-checked={value === c.value}
              aria-label={label}
              title={label}
              onClick={() => onChange(c.value)}
              className={`w-9 h-9 short:w-8 short:h-8 rounded-full border-2 transition ${value === c.value ? "border-sky-500 ring-2 ring-sky-200 scale-105" : "border-white shadow"}`}
              style={{ backgroundColor: c.value }}
            />
          );
        })}
        {(() => {
          const custom = !SIGN_COLOR_PRESETS.some((c) => c.value === value);
          return (
            <label
              className={`relative w-9 h-9 rounded-full overflow-hidden border-2 cursor-pointer flex items-center justify-center ${custom ? "border-sky-500 ring-2 ring-sky-200" : "border-white shadow"}`}
              style={{ background: custom ? value : "conic-gradient(#ef4444,#f59e0b,#22c55e,#06b6d4,#6366f1,#ec4899,#ef4444)" }}
              title={t("editor.modals.sigCreator.customColor")}
            >
              <span className="sr-only">{t("editor.modals.sigCreator.customColor")}</span>
              {!custom && <span className="w-5 h-5 rounded-full bg-white/90 text-slate-700 text-sm leading-5 text-center font-bold">+</span>}
              <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            </label>
          );
        })()}
      </div>
    </div>
  );
}

function initialTab(optional) {
  if (optional) return "none";
  return isTouch() ? "draw" : "text";
}

const SignatureCreator = forwardRef(function SignatureCreator({ optional = false, onReadyChange }, ref) {
  const { t } = useI18n();
  // ลายเซ็นที่บันทึกไว้ (เข้ารหัสด้วย Passkey)
  const [savedList, setSavedList] = useState([]);
  const [selectedSavedId, setSelectedSavedId] = useState(null);
  const [savedBlob, setSavedBlob] = useState(null);
  const [blobLoading, setBlobLoading] = useState(false);
  const [unlockedUrl, setUnlockedUrl] = useState(null);
  const [unlocking, setUnlocking] = useState(false);
  const [unlockError, setUnlockError] = useState("");

  const tabs = [
    ...(optional ? [{ key: "none", label: t("editor.modals.sigCreator.tabNone") }] : []),
    ...(savedList.length > 0 ? [{ key: "saved", label: t("editor.modals.sigCreator.tabSaved") }] : []),
    { key: "draw", label: t("editor.modals.sigCreator.tabDraw") },
    { key: "text", label: t("editor.modals.sigCreator.tabText") },
    { key: "image", label: t("editor.modals.sigCreator.tabImage") },
  ];
  const [tab, setTab] = useState(() => initialTab(optional));
  const [color, setColor] = useState(SIGN_COLOR_PRESETS[0].value);

  // พิมพ์ข้อความ
  const [text, setText] = useState("");
  const [font, setFont] = useState(TEXT_FONTS[0].key);
  const textCanvasRef = useRef(null);
  const textInputRef = useRef(null);

  // รูปภาพ
  const [rawImage, setRawImage] = useState(null);
  const [removeBg, setRemoveBg] = useState(true);
  const [imageUrl, setImageUrl] = useState(null);
  const fileRef = useRef(null);

  // เซ็นสด
  const padRef = useRef(null);
  const [hasInk, setHasInk] = useState(false);

  // โหลดรายการลายเซ็นที่บันทึกไว้ (ถ้าไม่ได้ล็อกอินจะข้ามเงียบๆ)
  useEffect(() => {
    let cancelled = false;
    listSavedSignatures()
      .then((res) => {
        if (cancelled) return;
        const items = Array.isArray(res) ? res : [];
        setSavedList(items);
        if (items.length > 0) setSelectedSavedId(items[0].id);
      })
      .catch(() => { /* ข้ามเงียบๆ หากไม่ได้ล็อกอิน */ });
    return () => { cancelled = true; };
  }, []);

  // โฟกัสช่องพิมพ์ข้อความอัตโนมัติบนเดสก์ท็อปเมื่อเปิดแท็บพิมพ์
  useEffect(() => {
    if (tab === "text" && !isTouch()) {
      textInputRef.current?.focus();
    }
  }, [tab]);

  // โหลด ciphertext blob ล่วงหน้าเมื่อเปลี่ยนลายเซ็นที่เลือก เพื่อให้การกด "ปลดล็อกด้วย Passkey"
  // เรียก navigator.credentials.get() ได้ทันทีภายใน user gesture (รองรับ Safari)
  useEffect(() => {
    if (!selectedSavedId) {
      setSavedBlob(null);
      return;
    }
    let cancelled = false;
    setUnlockedUrl(null);
    setUnlockError("");
    setBlobLoading(true);
    getSavedSignatureBlob(selectedSavedId)
      .then((blob) => {
        if (!cancelled) setSavedBlob(blob);
      })
      .catch(() => {
        if (!cancelled) {
          setSavedBlob(null);
          setUnlockError(t("editor.modals.sigCreator.loadSavedFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) setBlobLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedSavedId, t]);

  const handleUnlockSaved = async () => {
    if (!savedBlob || unlocking) return;
    setUnlockError("");
    setUnlocking(true);
    try {
      const dataUrl = await unlockSignatureWithPasskey(savedBlob);
      setUnlockedUrl(dataUrl);
    } catch (e) {
      setUnlockError(sigPasskeyErrorMessage(e));
    } finally {
      setUnlocking(false);
    }
  };

  const ready =
    tab === "none" ||
    (tab === "saved" && !!unlockedUrl) ||
    (tab === "text" && text.trim().length > 0) ||
    (tab === "image" && !!imageUrl) ||
    (tab === "draw" && hasInk);
  useEffect(() => {
    onReadyChange?.(ready);
  }, [ready, onReadyChange]);

  useEffect(() => {
    padRef.current?.setColor(color);
  }, [color]);

  useEffect(() => {
    if (!rawImage) {
      setImageUrl(null);
      return;
    }
    let cancelled = false;
    cleanSignatureImage(rawImage, removeBg).then((url) => !cancelled && setImageUrl(url)).catch(() => !cancelled && setImageUrl(rawImage));
    return () => { cancelled = true; };
  }, [rawImage, removeBg]);

  // วาดข้อความลง canvas (ความละเอียด 2 เท่า) — ปรับขนาดตัวอักษรให้พอดีกรอบ
  useEffect(() => {
    if (tab !== "text") return;
    const canvas = textCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!text.trim()) return;
    const spec = TEXT_FONTS.find((f) => f.key === font).css;
    let size = 112;
    ctx.font = spec.replace("{size}", size);
    let width = ctx.measureText(text).width;
    while (width > canvas.width - 48 && size > 28) {
      size -= 4;
      ctx.font = spec.replace("{size}", size);
      width = ctx.measureText(text).width;
    }
    ctx.fillStyle = color;
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    ctx.fillText(text, (canvas.width - width) / 2, canvas.height / 2);
  }, [tab, text, font, color]);

  useImperativeHandle(ref, () => ({
    getDataUrl() {
      if (tab === "none") return null;
      if (tab === "saved") return unlockedUrl;
      if (tab === "text") return text.trim() ? textCanvasRef.current.toDataURL("image/png") : null;
      if (tab === "image") return imageUrl;
      return padRef.current?.toDataURL() || null;
    },
  }));

  const tabBtn = (item) => (
    <button
      key={item.key}
      type="button"
      role="tab"
      aria-selected={tab === item.key}
      onClick={() => setTab(item.key)}
      className={`flex-1 min-w-0 px-2 py-2.5 short:py-1.5 text-sm font-medium rounded-lg transition ${tab === item.key ? "bg-white text-sky-700 shadow" : "text-slate-600 hover:text-slate-900"}`}
    >
      {item.label}
    </button>
  );

  return (
    <div className="space-y-3 short:space-y-2">
      <div className="flex gap-1 p-1 rounded-xl bg-slate-100" role="tablist" aria-label={t("editor.modals.sigCreator.methodAria")}>{tabs.map(tabBtn)}</div>


      {tab === "none" && (
        <p className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-sm text-slate-600">
          {t("editor.modals.sigCreator.noImageHint")}
        </p>
      )}

      {tab === "saved" && (
        <div className="space-y-3">
          <div className="space-y-1.5" role="radiogroup" aria-label={t("editor.modals.sigCreator.savedListAria")}>
            {savedList.map((s) => {
              const selected = s.id === selectedSavedId;
              return (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setSelectedSavedId(s.id)}
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg border text-left transition ${
                    selected
                      ? "border-sky-500 bg-sky-50 text-sky-900"
                      : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{s.label}</div>
                    <div className="text-xs text-slate-500 truncate">
                      {t("editor.modals.sigCreator.unlockWithPasskeyName", { name: s.passkey_name || "Passkey" })}
                    </div>
                  </div>
                  <span className="text-xs shrink-0 px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-600">
                    {selected && unlockedUrl ? t("editor.modals.sigCreator.unlockedBadge") : t("editor.modals.sigCreator.lockedBadge")}
                  </span>
                </button>
              );
            })}
          </div>

          {!unlockedUrl && (
            <button
              type="button"
              disabled={!supportsWebAuthn() || blobLoading || !savedBlob || unlocking}
              onClick={() => void handleUnlockSaved()}
              className="w-full py-2.5 px-4 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium disabled:opacity-50 transition"
            >
              {unlocking ? t("editor.modals.sigCreator.verifyingPasskey") : t("editor.modals.sigCreator.unlockPasskey")}
            </button>
          )}

          {unlockError && (
            <p className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700" role="alert">
              {unlockError}
            </p>
          )}

          <div className="flex items-center justify-center min-h-[140px] rounded-xl border-2 border-dashed border-slate-300 bg-[repeating-conic-gradient(#f1f5f9_0%_25%,#fff_0%_50%)] bg-[length:16px_16px]">
            {unlockedUrl ? (
              <img src={unlockedUrl} alt={t("editor.modals.sigCreator.unlockedPreviewAlt")} className="max-h-56 max-w-full object-contain p-2" />
            ) : (
              <span className="text-sm text-slate-400 px-4 text-center">
                {t("editor.modals.sigCreator.lockedPreviewHint")}
              </span>
            )}
          </div>
        </div>
      )}

      {tab === "draw" && (
        <div className="space-y-3 short:space-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ColorPicker value={color} onChange={setColor} />
            <div className="flex items-center gap-2 ml-auto">
              <button type="button" onClick={() => padRef.current?.undo()} disabled={!hasInk}
                className="px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-700 disabled:opacity-40">
                {t("editor.modals.sigCreator.undo")}
              </button>
              <button type="button" onClick={() => padRef.current?.clear()} disabled={!hasInk}
                className="px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-700 disabled:opacity-40">
                {t("editor.modals.sigCreator.clear")}
              </button>
            </div>
          </div>
          <SignaturePad ref={padRef} color={color} onChange={setHasInk}
            className="h-[clamp(180px,42dvh,360px)] sm:h-[clamp(200px,34dvh,280px)] short:h-[max(140px,calc(100dvh-210px))]" />
          <p className="text-xs text-slate-500 short:hidden">
            {t("editor.modals.sigCreator.drawHint")}
            {isTouch() && <span className="portrait:inline landscape:hidden">{t("editor.modals.sigCreator.rotateHint")}</span>}
          </p>
        </div>
      )}

      {tab === "text" && (
        <div className="space-y-3">
          <input
            ref={textInputRef}
            type="text"
            maxLength={60}
            className="w-full px-4 py-3 text-base border border-slate-300 rounded-lg bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
            placeholder={t("editor.modals.sigCreator.textPlaceholder")}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-700">{t("editor.modals.sigCreator.fontLabel")}</span>
            {TEXT_FONTS.map((f) => (
              <button key={f.key} type="button" onClick={() => setFont(f.key)}
                className={`px-3 py-1.5 text-sm rounded-full border ${font === f.key ? "border-sky-500 bg-sky-50 text-sky-700" : "border-slate-300 bg-white text-slate-600"}`}>
                {t(f.labelKey)}
              </button>
            ))}
          </div>
          <ColorPicker value={color} onChange={setColor} />
          <canvas ref={textCanvasRef} width={960} height={300} className="w-full h-auto rounded-xl border-2 border-dashed border-slate-300 bg-white" />
        </div>
      )}

      {tab === "image" && (
        <div className="space-y-3">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            data-testid="signature-image-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              const reader = new FileReader();
              reader.onload = () => setRawImage(reader.result);
              reader.readAsDataURL(f);
            }}
          />
          <button type="button" onClick={() => fileRef.current?.click()}
            className="w-full py-3 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50">
            {rawImage ? t("editor.modals.sigCreator.changeImage") : t("editor.modals.sigCreator.chooseImage")}
          </button>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" className="h-4 w-4" checked={removeBg} onChange={(e) => setRemoveBg(e.target.checked)} />
            {t("editor.modals.sigCreator.removeBgLabel")}
          </label>
          <div className="flex items-center justify-center min-h-[140px] rounded-xl border-2 border-dashed border-slate-300 bg-[repeating-conic-gradient(#f1f5f9_0%_25%,#fff_0%_50%)] bg-[length:16px_16px]">
            {imageUrl ? (
              <img src={imageUrl} alt={t("editor.modals.sigCreator.uploadedPreviewAlt")} className="max-h-56 max-w-full object-contain p-2" />
            ) : (
              <span className="text-sm text-slate-400">{t("editor.modals.sigCreator.noImageSelected")}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default SignatureCreator;
