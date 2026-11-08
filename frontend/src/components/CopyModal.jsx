import React, { useEffect, useState } from "react";
import * as api from "../api.js";

// ต้อง import extractSelectedText ให้ถูกด้วย หรือโยน textNormal มาจากข้างนอก
export default function CopyModal({ session, currentPage, rectPt, textNormal, onCancel, setStatusMessage }) {
  const [text, setText] = useState(textNormal || "");
  const [loadingOcr, setLoadingOcr] = useState(false);
  // อ่านด้วย AI เฉพาะผู้ที่มี key ส่วนตัว (backend: ai_ocr) ไม่งั้นเป็น OCR บนเซิร์ฟเวอร์ (Tesseract) — ชื่อปุ่มตามจริง
  const [aiOcr, setAiOcr] = useState(false);
  useEffect(() => {
    let alive = true;
    api.getAiQuota().then((q) => alive && setAiOcr(!!q.ai_ocr)).catch(() => {});
    return () => { alive = false; };
  }, []);
  const ocrLabel = aiOcr ? "ดึงข้อความด้วย AI (OCR)" : "อ่านข้อความจากภาพ (OCR)";

  async function handleCopy() {
    if (!text.trim()) {
      setStatusMessage("ไม่มีข้อความให้คัดลอก");
      return;
    }
    
    // ตรวจสอบว่ามี clipboard API ให้ใช้งานหรือไม่ (มักจะพังเมื่อไม่ได้รันบน HTTPS)
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        setStatusMessage("คัดลอกข้อความสำเร็จแล้ว");
        onCancel();
      } catch (err) {
        setStatusMessage(`คัดลอกไม่สำเร็จ: ${err.message}`);
      }
    } else {
      // Fallback สำหรับ HTTP หรือ Browser รุ่นเก่า
      try {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        // ทำให้ textarea ไม่แสดงผลบนหน้าจอ
        textArea.style.position = "fixed";
        textArea.style.left = "-999999px";
        textArea.style.top = "-999999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
          setStatusMessage("คัดลอกข้อความสำเร็จแล้ว (Fallback)");
          onCancel();
        } else {
          setStatusMessage("คัดลอกไม่สำเร็จ: เบราว์เซอร์ไม่อนุญาต");
        }
      } catch (err) {
        setStatusMessage(`คัดลอกไม่สำเร็จ (Fallback): ${err.message}`);
      }
    }
  }

  async function handleRunOCR() {
    setLoadingOcr(true);
    setStatusMessage(aiOcr ? "กำลังดึงข้อความด้วย AI (OCR)..." : "กำลังอ่านข้อความจากภาพ (OCR)...");
    try {
      let ocrText = await api.extractTextOCR(session.sessionId, currentPage, rectPt);
      if (!ocrText) {
         setStatusMessage("OCR ไม่พบข้อความ");
      } else {
         // ผล OCR ถูกจัดรูปภาษาไทยที่ backend แล้ว (thai_text.normalize) — เหลือแก้คำที่ Tesseract อ่านผิดบ่อย
         ocrText = ocrText.replace(/ตำราง/g, "ตาราง");
         setText(ocrText);
         setStatusMessage("ดึงข้อความด้วย OCR สำเร็จ (คุณสามารถแก้ไขก่อนคัดลอกได้)");
      }
    } catch (err) {
      setStatusMessage(`OCR ไม่สำเร็จ: ${err.message}`);
    } finally {
      setLoadingOcr(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()} style={{ width: "500px", maxWidth: "90vw" }}>
        <h2 className="modal-title">คัดลอกข้อความ</h2>
        <p className="modal-subtitle">
          ตรวจสอบและแก้ไขข้อความก่อนคัดลอก 
          (หากข้อความเพี้ยนหรือไม่ครบ ลองกดปุ่ม <b>{ocrLabel}</b>)
        </p>

        <textarea
          className="modal-input"
          style={{ height: "150px", resize: "vertical" }}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={loadingOcr ? "กำลังทำงาน..." : "ไม่มีข้อความในบริเวณที่เลือก..."}
          disabled={loadingOcr}
        />

        <div className="modal-actions" style={{ marginTop: "16px", justifyContent: "space-between" }}>
          <button 
            type="button" 
            className="secondary-btn" 
            onClick={handleRunOCR}
            disabled={loadingOcr}
            style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            {aiOcr ? "🤖" : "🔍"} {ocrLabel}
          </button>
          
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" className="secondary-btn" onClick={onCancel} disabled={loadingOcr}>
              ยกเลิก
            </button>
            <button type="button" className="primary-btn" onClick={handleCopy} disabled={loadingOcr || !text.trim()}>
              📋 คัดลอก
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
