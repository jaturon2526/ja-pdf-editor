// วัดความกว้างจริงของกล่อง (เปลี่ยนตามขนาดจอ/หมุนจอ) — ใช้ย่อหน้าเอกสารให้พอดีจอมือถือ
import { useCallback, useEffect, useState } from "react";

export function useElementWidth(fallback = 640) {
  const [node, setNode] = useState(null);
  const [width, setWidth] = useState(fallback);
  const ref = useCallback((el) => setNode(el), []);

  useEffect(() => {
    if (!node) return undefined;
    const measure = () => setWidth(node.clientWidth || fallback);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(node);
    return () => ro.disconnect();
  }, [node, fallback]);

  return [ref, width];
}

// สเกลของหน้า: กว้างไม่เกิน maxWidth (เดสก์ท็อป) และไม่เกินกล่องที่วาง (มือถือ)
export function previewScale(pageWidthPt, containerWidth, maxWidth = 640) {
  return Math.min(1.2, Math.min(maxWidth, Math.max(200, containerWidth)) / pageWidthPt);
}

// ความละเอียดภาพหน้า — คมบนจอ retina แต่ไม่เกิน 2 เท่า
export function previewZoom(scale) {
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  return Math.min(2, Math.max(scale * 1.5, scale * dpr));
}
