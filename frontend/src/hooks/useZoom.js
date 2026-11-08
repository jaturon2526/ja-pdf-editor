// useZoom.js — จัดการ zoom state และ step navigation

import { useState } from "react";

export const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];
export const ZOOM_MIN = 0.1;
export const ZOOM_MAX = 5;

/**
 * จัดการ zoom state (ย่อ/ขยาย/กำหนดเอง)
 * หมายเหตุ: zoomFitWidth / zoomFitHeight ต้องการ session + canvasAreaRef ซึ่งมาจากหลาย context
 * จึงถูกนิยามใน App.jsx และรับ setZoom จาก hook นี้แทน
 */
export function useZoom() {
  const [zoom, setZoom] = useState(1);

  function zoomIn() {
    setZoom((z) => ZOOM_STEPS.find((s) => s > z + 0.001) ?? z);
  }

  function zoomOut() {
    setZoom((z) => [...ZOOM_STEPS].reverse().find((s) => s < z - 0.001) ?? z);
  }

  return { zoom, setZoom, zoomIn, zoomOut };
}
