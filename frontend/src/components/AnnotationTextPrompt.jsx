import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function AnnotationTextPrompt({ type, onSubmit, onCancel }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const textRef = useRef(null);

  let title = t("editor.modals.annotPrompt.titleNote");
  if (type === "freetext") {
    title = t("editor.modals.annotPrompt.titleFreetext");
  } else if (type === "rect") {
    title = t("editor.modals.annotPrompt.titleRect");
  }

  // กรอบสี่เหลี่ยม (rect) ไม่บังคับว่าต้องมีข้อความ — วาดกรอบเปล่าๆ ก็ได้
  const textOptional = type === "rect";

  useEffect(() => {
    if (textRef.current) {
      // ใช้ setTimeout เพื่อให้แน่ใจว่า render เสร็จแล้ว และ preventScroll เพื่อไม่ให้เด้งลงล่างสุด
      setTimeout(() => {
        textRef.current?.focus({ preventScroll: true });
      }, 10);
    }
  }, []);

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">{title}</h2>
        <textarea
          ref={textRef}
          className="modal-textarea"
          rows={3}
          placeholder={
            textOptional
              ? t("editor.modals.annotPrompt.placeholderRect")
              : t("editor.modals.annotPrompt.placeholderDefault")
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={onCancel}>
            {t("editor.modals.annotPrompt.cancel")}
          </button>
          <button
            type="button"
            className="primary-btn"
            onClick={() => onSubmit(text)}
            disabled={!textOptional && !text.trim()}
          >
            {t("editor.modals.annotPrompt.add")}
          </button>
        </div>
      </div>
    </div>
  );
}
