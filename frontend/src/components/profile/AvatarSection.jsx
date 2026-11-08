// หน้าโปรไฟล์ › รูปโปรไฟล์: อัปโหลดรูปเอง (ครอป/ซูมก่อนบันทึก) หรือเลือกอีโมจิ 18 แบบ (วาดด้วย Pillow บนเซิร์ฟเวอร์)
// เปลี่ยนสีหน้าอีโมจิ + พื้นหลังได้ · ลบรูป → กลับไปใช้รูปจาก Google/LINE หรือตัวอักษรแรกของชื่อ
import React, { useEffect, useRef, useState } from "react";
import { avatarEmojiPreviewUrl, deleteAvatar, getAvatarEmojis, setAvatarEmoji, uploadAvatar } from "../../api";
import UserAvatar from "../UserAvatar.jsx";

const FACE_COLORS = ["#FFC83D", "#FB923C", "#F87171", "#F472B6", "#A78BFA", "#60A5FA", "#34D399", "#A3A3A3"];
const BG_COLORS = ["#DBEAFE", "#E0F2FE", "#ECFDF5", "#FEF3C7", "#FCE7F3", "#F5F3FF", "#F3F4F6", "#1E293B"];
const CROP_VIEW = 240; // ขนาดกรอบครอปบนจอ (px)

function Swatches({ label, colors, value, onChange, testId }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-700 mb-1">{label}</p>
      <div className="flex flex-wrap items-center gap-1.5" data-testid={testId}>
        {colors.map((c) => (
          <button key={c} type="button" aria-label={`${label} ${c}`} aria-pressed={value === c}
            className={`w-7 h-7 rounded-full border-2 ${value === c ? "border-blue-600 ring-2 ring-blue-200" : "border-white shadow"}`}
            style={{ background: c }} onClick={() => onChange(c)} />
        ))}
        <input type="color" aria-label={`${label} (เลือกเอง)`} value={value} onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="w-8 h-8 p-0 border-0 bg-transparent" />
      </div>
    </div>
  );
}

/** ครอปรูปเป็นสี่เหลี่ยมจัตุรัส: ลากเพื่อเลื่อน · แถบซูม — ได้ PNG 512px ส่งให้เซิร์ฟเวอร์ (ย่อเหลือ 256px + ลบข้อมูลแฝง) */
function Cropper({ file, onCancel, onDone, busy }) {
  const [img, setImg] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => setImg(im);
    im.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const base = img ? CROP_VIEW / Math.min(img.naturalWidth, img.naturalHeight) : 1; // ซูม 1 = ด้านสั้นพอดีกรอบ
  const scale = base * zoom;
  const w = img ? img.naturalWidth * scale : 0;
  const h = img ? img.naturalHeight * scale : 0;
  const clamp = (p) => ({
    x: Math.min(0, Math.max(CROP_VIEW - w, p.x)),
    y: Math.min(0, Math.max(CROP_VIEW - h, p.y)),
  });
  useEffect(() => { if (img) setPos((p) => clamp(p.x === 0 && p.y === 0 ? { x: (CROP_VIEW - w) / 2, y: (CROP_VIEW - h) / 2 } : p)); }, [img, zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  function onPointerDown(e) {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { sx: e.clientX, sy: e.clientY, start: pos };
  }
  function onPointerMove(e) {
    if (!drag.current) return;
    const { sx, sy, start } = drag.current;
    setPos(clamp({ x: start.x + e.clientX - sx, y: start.y + e.clientY - sy }));
  }
  function done() {
    const out = document.createElement("canvas");
    out.width = 512;
    out.height = 512;
    const k = 512 / CROP_VIEW;
    out.getContext("2d").drawImage(img, pos.x * k, pos.y * k, w * k, h * k);
    out.toBlob((blob) => blob && onDone(blob), "image/png");
  }

  return (
    <div className="mt-3 p-3 border border-gray-200 rounded-lg bg-gray-50" data-testid="avatar-cropper">
      <p className="text-sm text-gray-700 mb-2">ลากเพื่อเลื่อนรูป · ปรับซูมให้ใบหน้าอยู่กลางวงกลม</p>
      <div className="relative mx-auto overflow-hidden rounded-lg bg-gray-200 touch-none cursor-grab select-none"
        style={{ width: CROP_VIEW, height: CROP_VIEW }}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null; }}>
        {img && <img src={img.src} alt="" draggable={false} className="absolute max-w-none pointer-events-none"
          style={{ left: pos.x, top: pos.y, width: w, height: h }} />}
        <div className="absolute inset-0 pointer-events-none rounded-full" style={{ boxShadow: "0 0 0 999px rgba(0,0,0,0.45)" }} />
      </div>
      <input type="range" aria-label="ซูมรูป" min="1" max="4" step="0.01" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}
        className="mt-3 w-full" />
      <div className="mt-2 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-sm border border-gray-300 rounded bg-white">ยกเลิก</button>
        <button type="button" onClick={done} disabled={!img || busy} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50">
          {busy ? "กำลังบันทึก..." : "ใช้รูปนี้"}
        </button>
      </div>
    </div>
  );
}

export default function AvatarSection({ user, onChange }) {
  const [mode, setMode] = useState(null); // null | "emoji" | "upload"
  const [faces, setFaces] = useState([]);
  const initial = user?.avatar_emoji?.split("|") || [];
  const [face, setFace] = useState(initial[0] || "smile");
  const [faceColor, setFaceColor] = useState(initial[1] || "#FFC83D");
  const [bgColor, setBgColor] = useState(initial[2] || "#DBEAFE");
  const [thumbs, setThumbs] = useState({});
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { type, text }
  const fileRef = useRef(null);

  useEffect(() => {
    if (mode !== "emoji" || faces.length) return;
    getAvatarEmojis().then((r) => setFaces(r.faces)).catch((e) => setMessage({ type: "error", text: e.message }));
  }, [mode, faces.length]);

  // ภาพตัวอย่างทุกแบบตามสีที่เลือก (หน่วงเล็กน้อยตอนลากเลือกสีเอง)
  useEffect(() => {
    if (mode !== "emoji" || !faces.length) return undefined;
    let alive = true;
    const made = [];
    const timer = setTimeout(async () => {
      const entries = await Promise.all(faces.map(async (f) => {
        try {
          const url = await avatarEmojiPreviewUrl(f.key, faceColor, bgColor, 96);
          made.push(url);
          return [f.key, url];
        } catch { return [f.key, null]; }
      }));
      if (alive) setThumbs((old) => { Object.values(old).forEach((u) => u && URL.revokeObjectURL(u)); return Object.fromEntries(entries); });
      else made.forEach((u) => URL.revokeObjectURL(u));
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [mode, faces, faceColor, bgColor]);

  async function run(fn, okText) {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
      setMessage({ type: "ok", text: okText });
      setMode(null);
      setFile(null);
      await onChange?.();
    } catch (e) {
      setMessage({ type: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  }

  const chip = (active) => `px-3 py-1.5 text-sm rounded-lg border ${active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`;

  return (
    <section className="mb-8 pb-6 border-b" data-testid="avatar-section">
      <h2 className="text-sm font-medium text-gray-700 mb-3">รูปโปรไฟล์</h2>
      <div className="flex items-center gap-4 flex-wrap">
        <UserAvatar user={user} size={72} />
        <div className="flex flex-wrap gap-2">
          <button type="button" className={chip(mode === "upload")} onClick={() => fileRef.current?.click()}>อัปโหลดรูป</button>
          <button type="button" className={chip(mode === "emoji")} onClick={() => setMode(mode === "emoji" ? null : "emoji")}>เลือกอีโมจิ</button>
          {user?.avatar_url && (
            <button type="button" className="px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-700 hover:bg-red-50" disabled={busy}
              onClick={() => run(deleteAvatar, "ลบรูปโปรไฟล์แล้ว")}>ลบรูป</button>
          )}
        </div>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" aria-label="เลือกรูปโปรไฟล์"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (!f) return;
            if (f.size > 8 * 1024 * 1024) { setMessage({ type: "error", text: "ไฟล์รูปใหญ่เกิน 8MB" }); return; }
            setFile(f);
            setMode("upload");
          }} />
      </div>
      {message && (
        <p className={`mt-3 text-sm rounded p-2 ${message.type === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`} role={message.type === "ok" ? "status" : "alert"}>
          {message.text}
        </p>
      )}

      {mode === "upload" && file && (
        <Cropper file={file} busy={busy} onCancel={() => { setFile(null); setMode(null); }}
          onDone={(blob) => run(() => uploadAvatar(blob), "บันทึกรูปโปรไฟล์แล้ว")} />
      )}

      {mode === "emoji" && (
        <div className="mt-3 p-3 border border-gray-200 rounded-lg bg-gray-50 space-y-3" data-testid="emoji-picker">
          <div className="grid grid-cols-6 gap-2">
            {faces.map((f) => (
              <button key={f.key} type="button" title={f.label} aria-label={f.label} aria-pressed={face === f.key}
                className={`rounded-lg p-0.5 border-2 ${face === f.key ? "border-blue-600" : "border-transparent hover:border-gray-300"}`}
                onClick={() => setFace(f.key)}>
                {thumbs[f.key] ? <img src={thumbs[f.key]} alt="" className="w-full aspect-square rounded-md" />
                  : <div className="w-full aspect-square rounded-md bg-gray-200 animate-pulse" />}
              </button>
            ))}
          </div>
          <Swatches label="สีหน้า" colors={FACE_COLORS} value={faceColor} onChange={setFaceColor} testId="face-colors" />
          <Swatches label="สีพื้นหลัง" colors={BG_COLORS} value={bgColor} onChange={setBgColor} testId="bg-colors" />
          <div className="flex items-center justify-between gap-3">
            {thumbs[face] && <img src={thumbs[face]} alt="ตัวอย่างที่เลือก" className="w-14 h-14 rounded-full" />}
            <div className="flex gap-2 ml-auto">
              <button type="button" onClick={() => setMode(null)} className="px-3 py-1.5 text-sm border border-gray-300 rounded bg-white">ยกเลิก</button>
              <button type="button" disabled={busy} onClick={() => run(() => setAvatarEmoji(face, faceColor, bgColor), "บันทึกรูปโปรไฟล์แล้ว")}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50">{busy ? "กำลังบันทึก..." : "ใช้อีโมจินี้"}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
