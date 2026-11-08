import { useLayoutEffect, useRef } from "react";
import { keepInViewport } from "../utils/viewport.js";

// เมนูคลิกขวาบนพื้นที่เอกสาร (แยกมาจาก PDFCanvas.jsx) — ถูกดันให้อยู่ในหน้าจอเสมอ (ดู utils/viewport.js)
const MENU_CSS = `
  .context-menu-item {
    padding: 8px 16px;
    cursor: pointer;
    font-size: 14px;
    color: #333;
  }
  .context-menu-item:hover {
    background-color: #f1f5f9;
  }

`;

export default function CanvasContextMenu({
  position,
  onSelectTool,
  onRotateLeft,
  onRotateRight,
  onZoomIn,
  onZoomOut,
  onZoomOriginal,
}) {
  const menuRef = useRef(null);
  useLayoutEffect(() => {
    keepInViewport(menuRef.current);
  }, [position]);

  return (
    <>
      <style>{MENU_CSS}</style>
      <div
        ref={menuRef}
        style={{
          position: "fixed",
          top: position.y,
          left: position.x,
          backgroundColor: "white",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          borderRadius: "8px",
          padding: "8px 0",
          zIndex: 9999,
          minWidth: "180px",
        }}
        onContextMenu={(e) => e.preventDefault()}
      >
        <div className="context-menu-item flex items-center" onClick={() => onSelectTool(null)}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: '8px', flexShrink: 0 }}>
            <path d="M3 2l9 4.6-3.6 1-1 3.6L3 2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          </svg>
          <span>เมาส์</span>
        </div>
        <div className="context-menu-item flex items-center" onClick={() => onSelectTool("hand")}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: '8px', flexShrink: 0 }}>
            <path d="M6 8.2V3.4a1 1 0 0 1 2 0V7M8 7V2.6a1 1 0 0 1 2 0V7M10 7.2V3.8a1 1 0 0 1 2 0V9M4.2 9.5V6.9a1 1 0 0 1 2-.1l.2 4.2" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4.2 9.6c0 3 1.9 4.9 4.6 4.9 2.9 0 4.6-1.7 4.7-4.4l.1-2.6" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>มือ</span>
        </div>
        <div style={{ height: "1px", background: "#eee", margin: "4px 0" }} />
        <div className="context-menu-item flex items-center" onClick={onRotateLeft}>
          <span style={{ paddingLeft: '24px' }}>หมุนซ้าย ↺ (-90°)</span>
        </div>
        <div className="context-menu-item flex items-center" onClick={onRotateRight}>
          <span style={{ paddingLeft: '24px' }}>หมุนขวา ↻ (90°)</span>
        </div>
        <div style={{ height: "1px", background: "#eee", margin: "4px 0" }} />
        <div className="context-menu-item flex items-center" onClick={onZoomIn}>
          <span style={{ paddingLeft: '24px' }}>ขยาย (Zoom In)</span>
        </div>
        <div className="context-menu-item flex items-center" onClick={onZoomOut}>
          <span style={{ paddingLeft: '24px' }}>ย่อ (Zoom Out)</span>
        </div>
        <div className="context-menu-item flex items-center" onClick={onZoomOriginal}>
          <span style={{ paddingLeft: '24px' }}>ขนาดจริง (100%)</span>
        </div>
      </div>
    </>
  );
}
