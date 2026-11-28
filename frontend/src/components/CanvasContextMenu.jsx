import { useLayoutEffect, useRef } from "react";
import { keepInViewport } from "../utils/viewport.js";
import { useI18n } from "../i18n/I18nContext.jsx";

// เมนูคลิกขวาบนพื้นที่เอกสาร (แยกมาจาก PDFCanvas.jsx) — ถูกดันให้อยู่ในหน้าจอเสมอ (ดู utils/viewport.js)
const MENU_CSS = `
  .context-menu-item {
    width: 100%;
    border: 0;
    background: none;
    text-align: left;
    padding: 8px 16px;
    cursor: pointer;
    font-size: 14px;
    color: #333;
  }
  .context-menu-item:hover,
  .context-menu-item:focus-visible {
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
  const { t } = useI18n();
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
        role="menu"
        tabIndex={-1}
        onContextMenu={(e) => e.preventDefault()}
      >
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={() => onSelectTool(null)}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: '8px', flexShrink: 0 }}>
            <path d="M3 2l9 4.6-3.6 1-1 3.6L3 2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          </svg>
          <span>{t("editor.panels.contextMenu.cursor")}</span>
        </button>
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={() => onSelectTool("hand")}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: '8px', flexShrink: 0 }}>
            <path d="M6 8.2V3.4a1 1 0 0 1 2 0V7M8 7V2.6a1 1 0 0 1 2 0V7M10 7.2V3.8a1 1 0 0 1 2 0V9M4.2 9.5V6.9a1 1 0 0 1 2-.1l.2 4.2" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4.2 9.6c0 3 1.9 4.9 4.6 4.9 2.9 0 4.6-1.7 4.7-4.4l.1-2.6" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{t("editor.panels.contextMenu.hand")}</span>
        </button>
        <div role="separator" style={{ height: "1px", background: "#eee", margin: "4px 0" }} />
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={onRotateLeft}>
          <span style={{ paddingLeft: '24px' }}>{t("editor.panels.contextMenu.rotateLeft")}</span>
        </button>
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={onRotateRight}>
          <span style={{ paddingLeft: '24px' }}>{t("editor.panels.contextMenu.rotateRight")}</span>
        </button>
        <div role="separator" style={{ height: "1px", background: "#eee", margin: "4px 0" }} />
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={onZoomIn}>
          <span style={{ paddingLeft: '24px' }}>{t("editor.panels.contextMenu.zoomIn")}</span>
        </button>
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={onZoomOut}>
          <span style={{ paddingLeft: '24px' }}>{t("editor.panels.contextMenu.zoomOut")}</span>
        </button>
        <button type="button" role="menuitem" className="context-menu-item flex items-center" onClick={onZoomOriginal}>
          <span style={{ paddingLeft: '24px' }}>{t("editor.panels.contextMenu.zoomOriginal")}</span>
        </button>
      </div>
    </>
  );
}
