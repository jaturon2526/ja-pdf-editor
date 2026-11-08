// แปลง PDF เป็น Word แบบ async (เลือกรูปแบบ → เริ่มงาน → ดูความคืบหน้า → ดาวน์โหลด .docx)
// ใช้ร่วมกันระหว่างหน้าเอกสารของฉัน (เมนู ☰ ของไฟล์) และหน้า Editor (เมนู เครื่องมือ > แปลงเป็น Word...)
import { useEffect, useState } from "react";

import { getAiQuota } from "../api/auth.js";
import { checkConversionStatus, downloadConversionResult, inspectConversion, startConversionAsync } from "../api/files.js";
import ConversionModal, { ConversionModeChooser } from "../components/dashboard/ConversionModal.jsx";

/**
 * onMessage(type, text): แจ้งผล ("success" | "error")
 * onFinished(): เรียกหลังดาวน์โหลดสำเร็จ (เช่น โหลดโควต้า AI ใหม่)
 *
 * request({ fileId | sessionId, filename, beforeStart }) — เปิดหน้าต่างเลือกรูปแบบ
 *   beforeStart: async () => void เรียกหลังผู้ใช้เลือกรูปแบบแล้ว ก่อนเริ่มแปลง (Editor ใช้บันทึกการแก้ไขล่าสุดก่อน)
 */
export default function useWordConversion({ onMessage, onFinished } = {}) {
  const [choice, setChoice] = useState(null);
  const [task, setTask] = useState(null);
  const [mode, setMode] = useState("editable");
  const [showProgress, setShowProgress] = useState(false);
  // มี AI ให้ใช้ไหม (AI ของระบบ หรือ key ส่วนตัว) — false = ซ่อนตัวเลือก/ข้อความที่พูดถึง AI · null = ยังไม่รู้ (แสดงแบบเดิม)
  const [aiAvailable, setAiAvailable] = useState(null);

  useEffect(() => {
    if (!showProgress || !task || (task.status !== "pending" && task.status !== "processing")) return undefined;
    const intervalId = setInterval(async () => {
      try {
        const statusData = await checkConversionStatus(task.task_id);
        setTask(statusData);
        if (statusData.status !== "completed" && statusData.status !== "failed") return;
        clearInterval(intervalId);
        if (statusData.status !== "completed") return;
        if (statusData.error_message === "basic") {
          onMessage?.("success", "แปลงไฟล์เป็น Word สำเร็จแล้ว!");
        } else if (statusData.error_message === "fallback") {
          onMessage?.("error", "⚠️ การเชื่อมต่อ AI ขัดข้อง ระบบจึงเปลี่ยนไปใช้วิธีจัดเรียงคำแบบพื้นฐานแทน (อาจมีคำผิดพลาดบางส่วน)");
        } else if (statusData.error_message === "scan" || statusData.error_message === "scan-ai") {
          onMessage?.("success", statusData.error_message === "scan-ai"
            ? "แปลงไฟล์สแกนเป็น Word และให้ AI แก้คำไทยแล้ว — ตรวจทานข้อความก่อนนำไปใช้"
            : "แปลงไฟล์สแกนเป็น Word สำเร็จแล้ว — ตรวจทานข้อความก่อนนำไปใช้ (OCR อาจอ่านผิดบางคำ)");
        } else {
          onMessage?.("success", mode === "layout"
            ? "แปลงไฟล์แบบรักษาหน้าตาต้นฉบับสำเร็จแล้ว!"
            : "แปลงไฟล์และแก้คำไทยด้วย AI สำเร็จแล้ว!");
        }
        const blob = await downloadConversionResult(statusData.task_id);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = statusData.filename ? statusData.filename.replace(/\.pdf$/i, ".docx") : "converted.docx";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        onFinished?.();
      } catch (err) {
        console.error(err);
      }
    }, 2000);
    return () => clearInterval(intervalId);
    // onMessage/onFinished เป็นฟังก์ชันที่สร้างใหม่ทุก render — ไม่ใส่ใน deps (ไม่งั้น interval เริ่มใหม่ตลอด)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showProgress, task, mode]);

  function request(target) {
    // ตรวจก่อนว่าเป็นไฟล์สแกนไหม (ไฟล์สแกนมีตัวเลือกต่างจาก PDF ทั่วไป) — ตรวจไม่ได้ก็แสดงตัวเลือกปกติ
    // Editor ที่ยังไม่บันทึก: ตรวจจากไฟล์ที่บันทึกล่าสุด (การแก้ไขที่ยังไม่บันทึกไม่ทำให้ไฟล์สแกนกลายเป็นไฟล์ปกติ)
    setChoice({ ...target, inspecting: true });
    getAiQuota()
      .then((q) => setAiAvailable(q.ai_available !== false))
      .catch(() => setAiAvailable(null));
    inspectConversion(target.sessionId ? { sessionId: target.sessionId } : { fileId: target.fileId })
      .then((info) => setChoice((c) => (c && c.inspecting ? { ...c, inspecting: false, scan: info.scanned ? info : null } : c)))
      .catch(() => setChoice((c) => (c && c.inspecting ? { ...c, inspecting: false, scan: null } : c)));
  }

  async function start(target, chosenMode, options = {}) {
    setChoice(null);
    try {
      if (target.beforeStart) await target.beforeStart();
      const res = await startConversionAsync(
        target.sessionId ? { sessionId: target.sessionId } : { fileId: target.fileId },
        chosenMode,
        options,
      );
      setMode(chosenMode);
      setTask({ task_id: res.task_id, status: "pending", progress: 0 });
      setShowProgress(true);
    } catch (err) {
      onMessage?.("error", "เริ่มการแปลงไฟล์ล้มเหลว: " + err.message);
    }
  }

  const dialogs = (
    <>
      {choice && (
        <ConversionModeChooser
          filename={choice.filename}
          inspecting={choice.inspecting}
          scan={choice.scan}
          aiAvailable={aiAvailable !== false}
          onCancel={() => setChoice(null)}
          onChoose={(m, options) => start(choice, m, options)}
        />
      )}
      {showProgress && task && (
        <ConversionModal task={task} mode={mode} aiAvailable={aiAvailable !== false} onClose={() => setShowProgress(false)} />
      )}
    </>
  );

  return { request, dialogs };
}
