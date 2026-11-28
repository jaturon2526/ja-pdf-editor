import React, { useEffect, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

// ต้อง import extractSelectedText ให้ถูกด้วย หรือโยน textNormal มาจากข้างนอก
export default function CopyModal({ session, currentPage, rectPt, textNormal, onCancel, setStatusMessage }) {
  const { t } = useI18n();
  const [text, setText] = useState(textNormal || "");
  const [loadingOcr, setLoadingOcr] = useState(false);
  // อ่านด้วย AI เฉพาะผู้ที่มี key ส่วนตัว (backend: ai_ocr) ไม่งั้นเป็น OCR บนเซิร์ฟเวอร์ (Tesseract) — ชื่อปุ่มตามจริง
  const [aiOcr, setAiOcr] = useState(false);
  useEffect(() => {
    let alive = true;
    api.getAiQuota().then((q) => alive && setAiOcr(!!q.ai_ocr)).catch(() => {
      /* ignore quota fetch error */
    });
    return () => { alive = false; };
  }, []);
  const ocrLabel = aiOcr ? t("editor.modals.copy.ocrAiBtn") : t("editor.modals.copy.ocrServerBtn");

  async function handleCopy() {
    if (!text.trim()) {
      setStatusMessage(t("editor.modals.copy.emptyText"));
      return;
    }

    // ตรวจสอบว่ามี clipboard API ให้ใช้งานหรือไม่ (มักจะพังเมื่อไม่ได้รันบน HTTPS)
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        setStatusMessage(t("editor.modals.copy.copySuccess"));
        onCancel();
      } catch (err) {
        setStatusMessage(t("editor.modals.copy.copyFailed", { error: err.message }));
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

        const successful = document.execCommand("copy");
        document.body.removeChild(textArea);

        if (successful) {
          setStatusMessage(t("editor.modals.copy.copyFallbackSuccess"));
          onCancel();
        } else {
          setStatusMessage(t("editor.modals.copy.copyNotAllowed"));
        }
      } catch (err) {
        setStatusMessage(t("editor.modals.copy.copyFallbackFailed", { error: err.message }));
      }
    }
  }

  async function handleRunOCR() {
    setLoadingOcr(true);
    setStatusMessage(aiOcr ? t("editor.modals.copy.ocrAiLoading") : t("editor.modals.copy.ocrServerLoading"));
    try {
      let ocrText = await api.extractTextOCR(session.sessionId, currentPage, rectPt);
      if (!ocrText) {
        setStatusMessage(t("editor.modals.copy.ocrEmpty"));
      } else {
        // ผล OCR ถูกจัดรูปภาษาไทยที่ backend แล้ว (thai_text.normalize) — เหลือแก้คำที่ Tesseract อ่านผิดบ่อย ("ตำราง" -> "ตาราง")
        ocrText = ocrText.replace(/\u0e15\u0e33\u0e23\u0e32\u0e07/g, "\u0e15\u0e32\u0e23\u0e32\u0e07");
        setText(ocrText);
        setStatusMessage(t("editor.modals.copy.ocrSuccess"));
      }
    } catch (err) {
      setStatusMessage(t("editor.modals.copy.ocrFailed", { error: err.message }));
    } finally {
      setLoadingOcr(false);
    }
  }

  return (
    <div role="presentation" className="modal-overlay" onClick={onCancel}>
      <div role="presentation" className="modal-card" onClick={(e) => e.stopPropagation()} style={{ width: "500px", maxWidth: "90vw" }}>
        <h2 className="modal-title">{t("editor.modals.copy.title")}</h2>
        <p className="modal-subtitle">
          {t("editor.modals.copy.subtitleBefore")}
          <b>{ocrLabel}</b>
          {t("editor.modals.copy.subtitleAfter")}
        </p>

        <textarea
          className="modal-input"
          style={{ height: "150px", resize: "vertical" }}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={loadingOcr ? t("editor.modals.copy.placeholderWorking") : t("editor.modals.copy.placeholderEmpty")}
          disabled={loadingOcr}
        />

        <div className="modal-actions" style={{ marginTop: "16px", justifyContent: "space-between" }}>
          <button
            type="button"
            className="secondary-btn"
            onClick={() => void handleRunOCR()}
            disabled={loadingOcr}
            style={{ display: "flex", alignItems: "center", gap: "4px" }}
          >
            {aiOcr ? "🤖" : "🔍"} {ocrLabel}
          </button>

          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" className="secondary-btn" onClick={onCancel} disabled={loadingOcr}>
              {t("editor.modals.copy.cancel")}
            </button>
            <button type="button" className="primary-btn" onClick={() => void handleCopy()} disabled={loadingOcr || !text.trim()}>
              {t("editor.modals.copy.copyBtn")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
