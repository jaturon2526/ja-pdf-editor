// คีย์ลัดของหน้า Editor — แยกมาจาก Editor.jsx (พฤติกรรมเดิมทุกอย่าง)
// ข้ามเมื่อ focus อยู่ในช่องพิมพ์ และปิดเมนูคลิกขวาของเบราว์เซอร์ทั้งหน้า (ยกเว้นช่องพิมพ์)
import { useEffect } from "react";
import { ZOOM_MAX } from "./useZoom.js";

export function useEditorShortcuts({
  session,
  currentPage,
  zoom,
  editMode,
  goToPage,
  annotationHook,
  closeDocument,
  saveToServer,
  print,
  openFileDialog,
  setZoom,
  undo,
  redo,
}) {
  useEffect(() => {
    function onKeyDown(e) {
      const active = document.activeElement;
      const isEditableFocus =
        active?.isContentEditable || active?.tagName === "TEXTAREA" || active?.tagName === "INPUT";
      if (isEditableFocus) return;

      const key = e.key.toLowerCase();
      const mod = e.ctrlKey || e.metaKey;

      // === No modifier required ===
      if (key === "pageup") {
        e.preventDefault();
        if (session) goToPage(currentPage - 1);
        return;
      }
      if (key === "pagedown") {
        e.preventDefault();
        if (session) goToPage(currentPage + 1);
        return;
      }
      if (key === "delete" || key === "backspace") {
        if (annotationHook.annotationDraft) {
          e.preventDefault();
          annotationHook.handleDeleteAnnotation();
        }
        return;
      }

      // === Modifier required (Ctrl/Cmd/Alt) ===
      if (!e.ctrlKey && !e.metaKey && !e.altKey) return;

      if (key === "q" || e.code === "KeyQ") {
        if (e.altKey && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          if (session) closeDocument();
          return;
        }
      }

      if (!mod) return;

      // Block default browser shortcuts
      if (["s", "p", "o", "+", "=", "-", "0"].includes(key)) {
        e.preventDefault();
        if (key === "s" && session) {
          saveToServer();
        }
        if (key === "p" && session) {
          print();
        }
        if (key === "o") {
          openFileDialog();
        }
        if ((key === "+" || key === "=") && session) {
          setZoom((z) => Math.min(ZOOM_MAX, z + 0.25)); // ขอบเขตเดียวกับปุ่มซูม (เดิมค้างที่ 300%)
        }
        if (key === "-" && session) {
          setZoom((z) => Math.max(0.25, z - 0.25));
        }
        if (key === "0" && session) {
          setZoom(1);
        }
      }
      
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        redo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    
    // Prevent default context menu globally
    const onContextMenuGlobal = (e) => {
      // อนุญาตให้คลิกขวาใน input/textarea ได้เผื่อผู้ใช้ต้องการ copy/paste
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) {
        return;
      }
      e.preventDefault();
    };
    window.addEventListener("contextmenu", onContextMenuGlobal);
  
  return () => {
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("contextmenu", onContextMenuGlobal);
  };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, currentPage, zoom, editMode]);
}
