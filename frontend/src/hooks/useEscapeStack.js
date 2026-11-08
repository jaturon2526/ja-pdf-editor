// ปุ่ม Esc ปิดสิ่งที่อยู่ "บนสุด" ทีละชั้น — layers เรียงจากบนสุดลงล่าง: [[เปิดอยู่ไหม, ฟังก์ชันปิด], ...]
// (แยกมาจาก Editor.jsx: modal → draft ที่กำลังแก้ → เครื่องมือที่เลือกอยู่)
import { useEffect, useRef } from "react";

export function useEscapeStack(layers) {
  const latest = useRef(layers);
  latest.current = layers;

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key !== "Escape") return;
      const top = latest.current.find(([open]) => open);
      if (top) top[1]();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
