// ลายเซ็นอิเล็กทรอนิกส์: สร้างรูปลายเซ็น (เซ็นสด / พิมพ์ / รูปภาพ) แล้วส่ง PNG กลับไป
// onConfirm(base64ไม่มีหัว data:, dataUrl) — Editor ใช้ base64 เพื่อวางตำแหน่งต่อ · หน้าลงนามใช้ dataUrl
// ทุกอย่างประมวลผลในเบราว์เซอร์ (ข้อความไทยใช้ฟอนต์ของเบราว์เซอร์ วาดลง canvas)
import { useRef, useState } from "react";
import SignModalShell from "./signature/SignModalShell.jsx";
import SignatureCreator from "./signature/SignatureCreator.jsx";

function dataUrlToBase64(dataUrl) {
  const idx = dataUrl.indexOf(",");
  return idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
}

export default function ElectronicSignModal({ onConfirm, onCancel }) {
  const creatorRef = useRef(null);
  const [ready, setReady] = useState(false);

  function handleConfirm() {
    const dataUrl = creatorRef.current?.getDataUrl();
    if (!dataUrl) return;
    onConfirm(dataUrlToBase64(dataUrl), dataUrl);
  }

  return (
    <SignModalShell
      title="ลายเซ็นอิเล็กทรอนิกส์"
      subtitle="เซ็นสดด้วยนิ้ว/ปากกา พิมพ์ชื่อ หรือใช้รูปลายเซ็น"
      onCancel={onCancel}
      footer={
        <>
          <button type="button" onClick={onCancel} className="px-5 py-2.5 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100">ยกเลิก</button>
          <button type="button" onClick={handleConfirm} disabled={!ready}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-600 hover:bg-sky-700 disabled:opacity-50 shadow-sm">
            ตกลง
          </button>
        </>
      }
    >
      <SignatureCreator ref={creatorRef} onReadyChange={setReady} />
    </SignModalShell>
  );
}
