import { useEffect, useRef, useState } from "react";

export default function AnnotationTextPrompt({ type, onSubmit, onCancel }) {
  const [text, setText] = useState("");
  const textRef = useRef(null);
  const title =
    type === "freetext" ? "เพิ่มกล่องข้อความ" : type === "rect" ? "เพิ่มกรอบสี่เหลี่ยม" : "เพิ่มโน้ต";
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
          placeholder={textOptional ? "พิมพ์ข้อความในกรอบ (ไม่บังคับ)..." : "พิมพ์ข้อความ..."}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={onCancel}>
            ยกเลิก
          </button>
          <button type="button"
            className="primary-btn"
            onClick={() => onSubmit(text)}
            disabled={!textOptional && !text.trim()}
          >
            เพิ่ม
          </button>
        </div>
      </div>
    </div>
  );
}
