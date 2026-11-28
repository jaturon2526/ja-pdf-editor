import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import MenuBar from "../components/MenuBar.jsx";
import Toolbar from "../components/Toolbar.jsx";
import Sidebar from "../components/Sidebar.jsx";
import PDFCanvas from "../components/PDFCanvas.jsx";
import StatusBar from "../components/StatusBar.jsx";
import PasswordModal from "../components/PasswordModal.jsx";
import CopyModal from "../components/CopyModal.jsx";
import AnnotationTextPrompt from "../components/AnnotationTextPrompt.jsx";
import { CompressModal, FlattenModal, PrintOptionsModal, SaveCopyModal } from "../components/EditorDialogs.jsx";
import AboutModal from "../components/AboutModal.jsx";
import DocumentPropertiesModal from "../components/DocumentPropertiesModal.jsx";
import DocumentFontsModal from "../components/editor/DocumentFontsModal.jsx";
import InsertPagesModal from "../components/editor/InsertPagesModal.jsx";
import TableEditPanel from "../components/editor/TableEditPanel.jsx";
import { useTableEdit } from "../hooks/useTableEdit.js";
import BarcodeEditPanel from "../components/editor/BarcodeEditPanel.jsx";
import { useBarcodeEdit } from "../hooks/useBarcodeEdit.js";
import CropPagePanel from "../components/editor/CropPagePanel.jsx";
import { useCropPage } from "../hooks/useCropPage.js";
import FormFillPanel from "../components/editor/FormFillPanel.jsx";
import { useFormFill } from "../hooks/useFormFill.js";
import FontInspectorPanel from "../components/editor/FontInspectorPanel.jsx";
import { useFontInspector } from "../hooks/useFontInspector.js";
import FindBar from "../components/editor/FindBar.jsx";
import { useFindInDocument } from "../hooks/useFindInDocument.js";
import AddPasswordModal from "../components/AddPasswordModal.jsx";
import PropertiesPanel from "../components/PropertiesPanel.jsx";
import ElectronicSignModal from "../components/ElectronicSignModal.jsx";
import DigitalSignModal from "../components/DigitalSignModal.jsx";
import WatermarkModal from "../components/WatermarkModal.jsx";
import PageNumberModal from "../components/PageNumberModal.jsx";
import CompareStartModal from "../components/compare/CompareStartModal.jsx";
import BarcodeModal from "../components/BarcodeModal.jsx";
import StampModal from "../components/editor/StampModal.jsx";
import CreateBlankPdfModal from "../components/CreateBlankPdfModal.jsx";
import SearchRedactModal from "../components/SearchRedactModal.jsx";
import PiiPanel from "../components/pdpa/PiiPanel.jsx";
import { saveBlob } from "../api/client.js";
import ExtractPagesModal from "../components/ExtractPagesModal.jsx";
import * as api from "../api.js";
import { revokeAllPendingImageBlobUrls } from "../utils/imageUtils.js";
import { ZOOM_MAX, ZOOM_MIN, useZoom } from "../hooks/useZoom.js";
import { computeSelectedLineRects, extractSelectedText } from "../utils/textSelectionUtils.js";
import { useFonts } from "../hooks/useFonts.js";
import { printOpensNewTab, useSession } from "../hooks/useSession.js";
import { useDocumentProperties } from "../hooks/useDocumentProperties.js";
import { useTextEdit } from "../hooks/useTextEdit.js";
import { useImageEdit } from "../hooks/useImageEdit.js";
import { useAnnotation } from "../hooks/useAnnotation.js";
import { useSignature } from "../hooks/useSignature.js";
import useRedact from "../hooks/useRedact.js";
import { useEditorShortcuts } from "../hooks/useEditorShortcuts.js";
import { isPhoneLayout, resetUnintendedScroll } from "../utils/viewport.js";
import { useDocumentHistory } from "../hooks/useDocumentHistory.js";
import { useContinuousPages } from "../hooks/useContinuousPages.js";
import { useApplyEdits } from "../hooks/useApplyEdits.js";
import { useEscapeStack } from "../hooks/useEscapeStack.js";
import { buildEditorMenus } from "../components/editor/editorMenus.js";
import useWordConversion from "../hooks/useWordConversion.jsx";
import { useI18n } from "../i18n/I18nContext.jsx";

// ระยะ padding รอบหน้าเอกสารใน .canvas-area (ดู styles.css)
const CANVAS_PADDING_X = 40;
const CANVAS_PADDING_Y = 56;

export default function Editor() {
  const { lang, t } = useI18n();
  // ---------- Refs ----------
  const canvasAreaRef = useRef(null);
  const pageImgElRef = useRef(null);
  const pdfInputRef = useRef(null);
  const officeInputRef = useRef(null);

  // ---------- App-level state ----------
  const [activeTool, setActiveTool] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [isExtractModalOpen, setIsExtractModalOpen] = useState(false);
  const [canUndo, setCanUndoState] = useState(false);
  // มีการแก้ไขที่ยังไม่ได้บันทึกลงเอกสารของฉัน — ทุกงานที่แก้เอกสารเปิดปุ่ม Undo (setCanUndo(true)) จึงใช้เป็นสัญญาณ
  // เดิมไม่มีการเตือนเลย: กลับหน้าเอกสารของฉัน/เปิดไฟล์อื่น/ปิดแท็บ การแก้ไขหายเงียบ ๆ
  const [unsaved, setUnsaved] = useState(false);
  const setCanUndo = useCallback((v) => {
    setCanUndoState(v);
    if (v) setUnsaved(true);
  }, []);
  const [canRedo, setCanRedo] = useState(false);
  const [showWatermarkModal, setShowWatermarkModal] = useState(false);
  const [showPageNumberModal, setShowPageNumberModal] = useState(false);
  const [compareFiles, setCompareFiles] = useState(null); // null = ปิด · [] = รายการไฟล์ของฉัน (หน้าต่างเปรียบเทียบ)
  const [showBarcodeModal, setShowBarcodeModal] = useState(false);
  const [showStampModal, setShowStampModal] = useState(false);
  const [showCreateBlankModal, setShowCreateBlankModal] = useState(false);
  const [showSaveCopyModal, setShowSaveCopyModal] = useState(false);
  const [copyFilename, setCopyFilename] = useState("");
  const [copyPdfVersion, setCopyPdfVersion] = useState("");
  const [currentPdfInfo, setCurrentPdfInfo] = useState(null); // {version, encrypted} ของเอกสารปัจจุบัน (หน้าต่างบันทึกเป็นไฟล์ใหม่)
  const [showRedactSearchModal, setShowRedactSearchModal] = useState(false);
  const [showPiiPanel, setShowPiiPanel] = useState(false);
  const [piiHighlights, setPiiHighlights] = useState([]);
  const [showCompressModal, setShowCompressModal] = useState(false);
  const [copyPopup, setCopyPopup] = useState(null);
  const [showFlattenModal, setShowFlattenModal] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [compressProfile, setCompressProfile] = useState("screen");
  const [showDocumentFonts, setShowDocumentFonts] = useState(false);
  const [insertPagesAt, setInsertPagesAt] = useState(null); // ตำแหน่งเริ่มต้นในหน้าต่างแทรกหน้า (null = ปิด)
  const [continuousMode, setContinuousMode] = useState(() => {
    try {
      return localStorage.getItem("ja_pdf_scroll_mode") !== "single";
    } catch {
      return true;
    }
  });
  const toggleContinuousMode = useCallback(() => {
    setContinuousMode((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("ja_pdf_scroll_mode", next ? "continuous" : "single");
      } catch { /* ignore private mode */ }
      return next;
    });
  }, []);

  // ---------- Derived ----------
  const editMode =
    activeTool === "edit_text" || activeTool === "insert_text"
      ? "text"
      : activeTool === "edit_image" || activeTool === "insert_image"
      ? "image"
      : activeTool === "redact"
      ? "redact"
      : null;

  // ======================== Hooks ========================
  const { zoom, setZoom, zoomIn, zoomOut } = useZoom();

  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const fontsHook = useFonts({ setStatusMessage });

  const sessionHook = useSession({ zoom, setStatusMessage, setCanUndo, setCanRedo, onSaved: () => setUnsaved(false) });
  const wordConversion = useWordConversion({ onMessage: (_type, text) => setStatusMessage(text) });

  // Load session from URL parameter
  // เอกสารที่เปิดค้างไว้หมดอายุ/ถูกปิดแล้ว (รีเฟรชหน้า, ไม่ได้ใช้นานเกิน PDF_SESSION_TTL_MINUTES, ปิดแท็บแล้วเปิดลิงก์เดิม)
  // → เปิดใหม่จากไฟล์ที่บันทึกไว้ใน "เอกสารของฉัน" ให้เอง (id ใน URL = storage_path ของไฟล์)
  useEffect(() => {
    if (!id || sessionHook.session) return;
    sessionHook._activateSession(id, null, null, resetTransientEditState).catch(async (err) => {
      try {
        const res = await api.openFile(id);
        if (res.status === "ok") {
          if (res.session_id === id) await sessionHook._activateSession(id, null, null, resetTransientEditState);
          else void navigate(`/editor/${res.session_id}`, { replace: true });
          setStatusMessage(t("editor.msg.reopenedSaved"));
          return;
        }
        void navigate("/dashboard", { replace: true }); // มีรหัสผ่าน — เปิดจากหน้าเอกสารของฉัน (ถามรหัสที่นั่น)
      } catch {
        setStatusMessage(t("editor.msg.loadFileFailed", { error: err.message }));
      }
    });
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const { session, setSession, currentPage, setCurrentPage } = sessionHook;
  const fontInspector = useFontInspector({
    session, currentPage, pageImage: sessionHook.pageImage, active: activeTool === "inspect_font",
  });

  // คืนหน่วยความจำบนเซิร์ฟเวอร์เมื่อออกจากหน้าแก้ไข (กลับหน้าเอกสารของฉัน / ปิดแท็บ / รีเฟรช) — เดิมเอกสารค้างจนหมดอายุ
  // งานที่ยังไม่บันทึกถูกถามยืนยันก่อนออกอยู่แล้ว (confirmDiscard / beforeunload) · เปิดลิงก์เดิมอีกครั้งได้ (เปิดจากไฟล์ที่บันทึก)
  // ระหว่างเปิดแท็บไว้: ส่งสัญญาณทุก 5 นาที (ไม่ให้หมดอายุตอนอ่านนานโดยไม่ได้กดอะไร)
  const openSessionIdRef = useRef(null);
  useEffect(() => { openSessionIdRef.current = session?.sessionId || null; }, [session?.sessionId]);
  useEffect(() => {
    const closeNow = () => {
      const sid = openSessionIdRef.current;
      if (sid) api.closeSession(sid, { keepalive: true }).catch(() => {});
      openSessionIdRef.current = null;
    };
    const onPageHide = (e) => { if (!e.persisted) closeNow(); };
    window.addEventListener("pagehide", onPageHide);
    const beat = setInterval(() => {
      const sid = openSessionIdRef.current;
      if (sid && document.visibilityState === "visible") api.getInfo(sid).catch(() => {});
    }, 5 * 60 * 1000);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      clearInterval(beat);
      closeNow();
    };
  }, []);

  // Refresh ฟอนต์ทุกครั้งที่เปิดโหมดแก้ไขข้อความหรือแก้ไขตาราง เพื่อให้เห็นฟอนต์ที่ติดตั้งใหม่ทันที
  useEffect(() => {
    if (editMode === "text" || activeTool === "edit_table") {
      if (fontsHook.setFontFamilies) {
        import("../api.js").then(api => {
          api.getFontFamilies().then(fontsHook.setFontFamilies).catch(() => {});
          api.getFonts().then(fontsHook.setFonts).catch(() => {});
        }).catch(() => { /* โหลดโมดูลไม่ได้ (ออฟไลน์) — ใช้รายการฟอนต์เดิม */ });
      }
    }
  }, [editMode, activeTool]); // eslint-disable-line react-hooks/exhaustive-deps

  const docPropsHook = useDocumentProperties({ session, setSession, setStatusMessage });

  const textEditHook = useTextEdit({
    session,
    currentPage,
    editMode,
    pageImgElRef,
    fonts: fontsHook.fonts,
    fontFamilies: fontsHook.fontFamilies,
    setStatusMessage,
  });

  const imageEditHook = useImageEdit({
    session,
    currentPage,
    editMode,
    pageImgElRef,
    setStatusMessage,
  });

  const redactHook = useRedact({
    session,
    currentPage,
    editMode,
    setStatusMessage,
    refreshAfterHistoryChange: async () => {
      resetTransientEditState();
      await refreshAfterHistoryChange();
      setCanUndo(true);
      setCanRedo(false);
    },
    resetTransientEditState: () => resetTransientEditState()
  });

  const annotationHook = useAnnotation({
    session,
    currentPage,
    editMode,
    zoom,
    fonts: fontsHook.fonts,
    setStatusMessage,
  });

  const signatureHook = useSignature({
    session,
    setSession,
    currentPage,
    setActiveTool,
    setStatusMessage,
    setCanUndo,
    setCanRedo,
    currentPageSizePt: sessionHook.currentPageSizePt,
  });

  const findHook = useFindInDocument({
    session,
    currentPage,
    goToPage: sessionHook.goToPage,
  });

  // ======================== Esc: ปิดสิ่งที่อยู่บนสุดทีละชั้น ========================
  useEscapeStack([
    // 1. modal / floating bar
    [findHook.open, findHook.closeFind],
    [showWatermarkModal, () => setShowWatermarkModal(false)],
    [showPageNumberModal, () => setShowPageNumberModal(false)],
    [showBarcodeModal, () => setShowBarcodeModal(false)],
    [showStampModal, () => setShowStampModal(false)],
    [showCreateBlankModal, () => setShowCreateBlankModal(false)],
    [showSaveCopyModal, () => setShowSaveCopyModal(false)],
    [showCompressModal, () => setShowCompressModal(false)],
    [showFlattenModal, () => setShowFlattenModal(false)],
    [isExtractModalOpen, () => setIsExtractModalOpen(false)],
    [showRedactSearchModal, () => setShowRedactSearchModal(false)],
    [showPiiPanel, () => setShowPiiPanel(false)],
    [aboutOpen, () => setAboutOpen(false)],
    [docPropsHook.addPasswordOpen, docPropsHook.handleCloseAddPassword],
    [docPropsHook.docPropsOpen, docPropsHook.handleCloseDocProps],
    [copyPopup, () => setCopyPopup(null)],
    [signatureHook.signModalOpen, signatureHook.handleCancelSignModal],
    // 2. draft ที่กำลังแก้อยู่
    [textEditHook.draftEdit, textEditHook.handleCancelEdit],
    [imageEditHook.draftEdit, imageEditHook.handleCancelEdit],
    [signatureHook.draftSignature, signatureHook.handleCancelSignature],
    [annotationHook.draftAnnotation, annotationHook.handleCancelAnnotationEdit],
    // 3. เครื่องมือที่เลือกอยู่
    [activeTool, () => { setActiveTool(null); setStatusMessage(""); }],
  ]);

  // ======================== Undo / Redo + งานที่เปลี่ยนเอกสาร (ดู hooks/useDocumentHistory.js) ========================
  const {
    resetTransientEditState,
    refreshAfterHistoryChange,
    handleUndo,
    handleRedo,
    runDocumentChange,
    pageOps,
  } = useDocumentHistory({
    session,
    setSession,
    currentPage,
    setCurrentPage,
    zoom,
    editMode,
    sessionHook,
    textEditHook,
    imageEditHook,
    annotationHook,
    signatureHook,
    redactHook,
    activeTool,
    setActiveTool,
    setCanUndo,
    setCanRedo,
    setStatusMessage,
  });

  const tableEdit = useTableEdit({
    session, currentPage, pageImage: sessionHook.pageImage, active: activeTool === "edit_table", runDocumentChange,
  });
  const barcodeEdit = useBarcodeEdit({
    session, currentPage, pageImage: sessionHook.pageImage, active: activeTool === "edit_barcode", runDocumentChange,
  });
  const cropPage = useCropPage({
    session,
    currentPage,
    active: activeTool === "crop_page",
    runDocumentChange,
    onDone: () => setActiveTool(null),
  });
  const formFill = useFormFill({
    session,
    currentPage,
    pageImage: sessionHook.pageImage,
    active: activeTool === "fill_form",
    runDocumentChange,
  });

  const canAutoSwitchPage = !(
    textEditHook.draftEdit
    || imageEditHook.draftImageEdit
    || signatureHook.draftSignature
    || annotationHook.annotationDraft
    || activeTool === "crop_page"
  );
  const continuousPages = useContinuousPages({
    enabled: continuousMode,
    session,
    currentPage,
    pageImage: sessionHook.pageImage,
    pageImagePage: sessionHook.pageImagePage,
    zoom,
    canvasAreaRef,
    canAutoSwitchPage,
    onSelectPageFromScroll: sessionHook.setCurrentPage,
  });

  // รองรับลิงก์ ?tool=fill_form&mode=design เมื่อสร้างเอกสารเปล่าเพื่อออกแบบแบบฟอร์มจากหน้าแรก
  useEffect(() => {
    const toolParam = searchParams.get("tool");
    const modeParam = searchParams.get("mode");
    if (!toolParam || !session) return;
    if (toolParam === "fill_form") {
      setActiveTool("fill_form");
      if (modeParam === "design") formFill.setMode("design");
    }
    setSearchParams({}, { replace: true });
  }, [session?.sessionId, searchParams]); // eslint-disable-line react-hooks/exhaustive-deps
  // ลูกศรขยับตาราง/บาร์โค้ดที่เลือก 1 pt (Shift = 10 pt) — ไม่แย่งปุ่มลูกศรตอนพิมพ์ในช่องตัวเลข
  let arrowTarget = null;
  if (activeTool === "edit_table" && tableEdit.selected) {
    arrowTarget = tableEdit.moveBy;
  } else if (activeTool === "edit_barcode" && barcodeEdit.selected) {
    arrowTarget = barcodeEdit.moveBy;
  }
  useEffect(() => {
    if (!arrowTarget) return undefined;
    const onKey = (e) => {
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const step = e.shiftKey ? 10 : 1;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (!d) return;
      e.preventDefault();
      arrowTarget(d[0], d[1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [arrowTarget]);

  // วางรูปภาพจากคลิปบอร์ด (Ctrl+V / Cmd+V) ทั้งรูปที่คัดลอกจากในโหมดแก้ไขรูปภาพ และรูปจากคลิปบอร์ดระบบ
  useEffect(() => {
    if (!session) return undefined;
    const onPaste = (e) => {
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.target?.isContentEditable) return;
      const items = Array.from(e.clipboardData?.items || []);
      const imgItem = items.find((it) => it.type && it.type.startsWith("image/"));
      const clipFile = imgItem ? imgItem.getAsFile() : null;
      if (clipFile || (editMode === "image" && imageEditHook.copiedImage)) {
        e.preventDefault();
        if (activeTool !== "edit_image") setActiveTool("edit_image");
        void imageEditHook.pasteImage(clipFile);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [session, editMode, activeTool, imageEditHook]);

  // ตั้ง callbacks ให้ annotationHook ใช้ refresh pageImage และ undo/redo state
  // (annotation CRUD ต้องการ re-render หน้า ซึ่ง setPageImage อยู่ใน sessionHook)
  useEffect(() => {
    annotationHook.setCallbacks({
      onPageRendered: (imgBase64, page) => {
        sessionHook.setPageImage(imgBase64);
        // ภาพตัวอย่างในแผงหน้าเอกสารของหน้านั้นโหลดใหม่ (เดิมไม่เห็นไฮไลต์/กล่องข้อความที่เพิ่ง เพิ่ม/แก้/ลบ)
        if (page != null) sessionHook.setThumbnails((prev) => {
          const next = { ...prev };
          delete next[page];
          return next;
        });
      },
      onHistoryChange: (canUndoVal, canRedoVal) => {
        setCanUndo(canUndoVal);
        setCanRedo(canRedoVal);
      },
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // คีย์ลัดทั้งหมดของหน้า Editor (Ctrl+Z/Y, Ctrl+S/P/O, ซูม, PageUp/Down, Delete, Alt+Q) — ดู hooks/useEditorShortcuts.js
  useEditorShortcuts({
    session,
    currentPage,
    zoom,
    editMode,
    goToPage: sessionHook.goToPage,
    annotationHook,
    closeDocument,
    saveToServer: handleAutoSaveToServer,
    print: handleAutoPrint,
    openFileDialog: () => pdfInputRef.current?.click(),
    openFind: findHook.openFind,
    setZoom,
    undo: handleUndo,
    redo: handleRedo,
  });

  // ======================== Session management ========================

  // ยืนยันก่อนทิ้งการแก้ไข — pending = แก้ข้อความ/รูปที่ยังไม่กด "บันทึกการแก้ไข", unsaved = ยังไม่กดบันทึกลงเอกสารของฉัน
  function confirmDiscard(action) {
    const pending = textEditHook.textPendingCount + imageEditHook.imagePendingCount;
    if (!session || (!pending && !unsaved)) return true;
    const what = pending
      ? t("editor.msg.discardPending", { count: pending })
      : t("editor.msg.discardUnsaved");
    return window.confirm(t("editor.msg.discardConfirm", { what, action }));
  }

  useEffect(() => {
    setUnsaved(false); // เปิดเอกสารใหม่ = ยังไม่มีการแก้ไข
  }, [session?.sessionId]);

  // ปิดแท็บ/รีเฟรชระหว่างมีการแก้ไขค้าง → เบราว์เซอร์ถามยืนยัน
  const hasPendingWork = !!session && (unsaved || textEditHook.textPendingCount + imageEditHook.imagePendingCount > 0);
  useEffect(() => {
    if (!hasPendingWork) return undefined;
    const onBeforeUnload = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hasPendingWork]);

  function handleFileSelected(file) {
    if (!confirmDiscard(t("editor.msg.actionOpenOther"))) return;
    if (session) api.closeSession(session.sessionId).catch(() => {}); // เดิมเอกสารเก่าค้างอยู่บนเซิร์ฟเวอร์จนหมดอายุ
    sessionHook.handleFileSelected(file, resetTransientEditState);
  }

  function goToDashboard() {
    if (!confirmDiscard(t("editor.msg.actionGoDashboard"))) return;
    setUnsaved(false);
    void navigate("/dashboard");
  }

  function handleUnlockSubmit(password) {
    void sessionHook.handleUnlockSubmit(password, resetTransientEditState);
  }

  function closeDocument() {
    if (!confirmDiscard(t("editor.msg.actionCloseFile"))) return;
    revokeAllPendingImageBlobUrls(imageEditHook.pendingImageEdits, imageEditHook.draftImageEdit);
    if (session) api.closeSession(session.sessionId).catch(() => {});
    setSession(null);
    sessionHook.setPageImage(null);
    setCurrentPage(0);
    setZoom(1);
    sessionHook.setThumbnails({});
    sessionHook.setBookmarks([]);
    setActiveTool(null);
    textEditHook.reset();
    imageEditHook.reset();
    annotationHook.reset();
    signatureHook.reset();
    if (redactHook) redactHook.reset();
    setCanUndo(false);
    setCanRedo(false);
    setUnsaved(false);
    setStatusMessage(t("editor.msg.fileClosed"));
  }

  // ======================== Page navigation & zoom ========================

  // ปรับซูมพอดีความกว้างอัตโนมัติเมื่อใช้งานบนมือถือ (หน้าจอเล็ก) เพื่อไม่ให้กระดาษล้นตกขอบตอนเปิดไฟล์
  useEffect(() => {
    if (session?.sessionId) {
      setTimeout(() => {
        if (isPhoneLayout()) {
          zoomFitWidth();
        }
      }, 100);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.sessionId]);

  // หมุนมือถือ (แนวตั้ง ↔ แนวนอน): ซูมพอดีความกว้างใหม่ — หน้าตาสลับเป็นแบบมือถือ/คอมด้วย CSS (phone:/desk:) เอง
  useEffect(() => {
    if (!session?.sessionId) return undefined;
    let timer = null;
    const onRotate = () => {
      clearTimeout(timer);
      timer = setTimeout(() => { if (isPhoneLayout()) zoomFitWidth(); }, 250); // รอเบราว์เซอร์จัดขนาดจอใหม่เสร็จ
    };
    window.addEventListener("orientationchange", onRotate);
    const mq = window.matchMedia?.("(orientation: portrait)");
    mq?.addEventListener?.("change", onRotate);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("orientationchange", onRotate);
      mq?.removeEventListener?.("change", onRotate);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.sessionId]);

  // คืน true ถ้าเปลี่ยนหน้าได้ (PDFCanvas ใช้ตัดสินว่าจะเลื่อนหน้าใหม่ไปขอบบน/ล่างไหม) — หน้าแรก/หน้าสุดท้ายแล้ว = false
  function handleNavigatePage(delta) {
    return sessionHook.stepPage(delta);
  }

  function zoomFitWidth() {
    const el = canvasAreaRef.current;
    const pageSize = session?.pageSizes?.[currentPage];
    if (!el || !pageSize) return;
    const [pageWidthPt] = pageSize;
    const available = el.clientWidth - CANVAS_PADDING_X;
    if (available <= 0 || !pageWidthPt) return;
    setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, available / pageWidthPt)));
  }

  function zoomFitHeight() {
    const el = canvasAreaRef.current;
    const pageSize = session?.pageSizes?.[currentPage];
    if (!el || !pageSize) return;
    const [, pageHeightPt] = pageSize;
    const available = el.clientHeight - CANVAS_PADDING_Y;
    if (available <= 0 || !pageHeightPt) return;
    setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, available / pageHeightPt)));
  }

  // ======================== แทรกรูปภาพ ========================
  // เลือกไฟล์จากเมนู/ปุ่ม "แทรกรูปภาพ" หรือลากไฟล์รูปมาวางในโหมดแก้ไขรูปภาพ → เข้าโหมดแก้ไขรูปแล้ววางรูปให้ย้าย/ปรับขนาด
  useEffect(() => {
    if (activeTool === "edit_image" && session) {
      setStatusMessage(t("editor.msg.imageEditModeHint"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool, t]);

  function insertImageFile(file, point = null) {
    if (!session || !file) return;
    setActiveTool("edit_image");
    void imageEditHook.placeNewImage(file, point);
  }

  // ======================== บันทึกการแก้ไข (ดู hooks/useApplyEdits.js) ========================
  const { pendingEditCount, applyAllEdits, applyAllPages, withPendingApplied } = useApplyEdits({
    session,
    currentPage,
    editMode,
    sessionHook,
    textEditHook,
    imageEditHook,
    redactHook,
    setActiveTool,
    setCanUndo,
    setCanRedo,
    setStatusMessage,
  });

  // function declaration (hoisted) — useEditorShortcuts ด้านบนอ้างถึงก่อนบรรทัดนี้
  function handleAutoSaveToServer() {
    return withPendingApplied(sessionHook.handleSaveToServer);
  }

  function handleAutoDownload() {
    return withPendingApplied(sessionHook.handleDownload);
  }

  // เอกสารที่มีหน้าแนวนอน (เช่น หน้าที่หมุนแล้ว) ให้เลือกรูปแบบการพิมพ์ก่อน — ไม่งั้นเครื่องพิมพ์จะหมุนหน้า
  // ให้เองและหน้าที่ "หมุนซ้าย" จะออกมากลับหัว (ดู PrintOptionsModal)
  const [showPrintOptions, setShowPrintOptions] = useState(false);

  async function handleAutoPrint() {
    const hasLandscape = (session?.pageSizes || []).some(([w, h]) => w > h);
    if (hasLandscape) {
      setShowPrintOptions(true);
      return;
    }
    await printDocument("auto");
  }

  async function printDocument(layout) {
    setShowPrintOptions(false);
    // มือถือ/Safari: เปิดแท็บว่าง "ตอนกด" (ยังอยู่ในการกดของผู้ใช้) แล้วค่อยใส่ไฟล์ — เปิดหลังโหลดไฟล์จะถูกบล็อก
    const win = printOpensNewTab() ? window.open("", "_blank") : null;
    if (win) {
      try {
        win.document.title = t("editor.msg.printPreparingTitle");
        const p = win.document.createElement("p");
        p.style.cssText = "font-family:sans-serif;padding:24px;color:#475569";
        p.textContent = t("editor.msg.printPreparingBody");
        win.document.body.replaceChildren(p);
      } catch { /* ignore */ }
    }
    let opened = false;
    try {
      await withPendingApplied(async () => {
        opened = (await sessionHook.handlePrint({ layout, targetWindow: win })) === "tab";
      });
    } finally {
      // ยกเลิก/ล้มเหลวก่อนได้ไฟล์ — ไม่ทิ้งแท็บว่างค้าง
      if (win && !opened && !win.closed) win.close();
    }
  }

  // ======================== Signature after-sign callback ========================

  async function _onAfterSign(res, signedPage) {
    resetTransientEditState();
    setActiveTool(null);
    await refreshAfterHistoryChange();
    sessionHook.setThumbnails((prev) => {
      const next = { ...prev };
      delete next[signedPage];
      return next;
    });
  }

  const hasLocalUndo = !!(
    pendingEditCount > 0 ||
    textEditHook.draftEdit ||
    imageEditHook.draftImageEdit
  );

  // ======================== Menu (ดู components/editor/editorMenus.js) ========================
  const menus = buildEditorMenus({
    lang,
    t,
    session,
    activeTool,
    setActiveTool,
    canUndo: canUndo || hasLocalUndo,
    canRedo,
    isSidebarOpen,
    setIsSidebarOpen,
    goToDashboard,
    openCreateBlank: () => setShowCreateBlankModal(true),
    openOfficeDialog: () => officeInputRef.current?.click(),
    openFileDialog: () => pdfInputRef.current?.click(),
    saveToServer: handleAutoSaveToServer,
    download: handleAutoDownload,
    print: handleAutoPrint,
    closeDocument,
    openExtract: () => setIsExtractModalOpen(true),
    openSaveCopy: () => {
      const baseName = (session?.filename || "document").replace(/\.pdf$/i, "");
      setCopyFilename(t("editor.msg.copyFilename", { name: baseName }));
      setCopyPdfVersion("");
      setCurrentPdfInfo(null);
      setShowSaveCopyModal(true);
      if (session) {
        api.getDocumentProperties(session.sessionId)
          .then((p) => setCurrentPdfInfo({ version: p?.pdf_version || null, encrypted: !!p?.is_encrypted }))
          .catch(() => {});
      }
    },
    undo: handleUndo,
    redo: handleRedo,
    openFind: findHook.openFind,
    zoomIn,
    zoomOut,
    setZoom,
    continuousMode,
    toggleContinuousMode,
    docPropsHook,
    signatureHook,
    openRedactSearch: () => setShowRedactSearchModal(true),
    runOcrLayer: async () => {
      // ข้อความในรูป (ลายเซ็น+ชื่อผู้ลงนาม ภาพสแกน) → ชั้นข้อความล่องหน ให้ค้นหา/เซ็นเซอร์/คัดลอก/PDPA ได้
      setStatusMessage(t("editor.msg.ocrRunning"));
      try {
        const r = await api.addOcrTextLayer(session.sessionId);
        if (!r.words) {
          setStatusMessage(t("editor.msg.ocrEmpty"));
          return;
        }
        sessionHook.refreshCurrentPage().catch((e) => console.warn("refresh page failed", e));
        void refreshAfterHistoryChange();
        setCanUndo(true);
        setCanRedo(false);
        const skippedSuffix = r.skipped_pages ? t("editor.msg.ocrSkippedSuffix", { count: r.skipped_pages }) : "";
        setStatusMessage(
          t("editor.msg.ocrSuccess", { words: r.words, pages: r.pages.join(", ") }) + skippedSuffix,
        );
      } catch (err) {
        setStatusMessage(t("editor.msg.ocrFailed", { error: err.message }));
      }
    },
    openPii: () => {
      setActiveTool(null);
      setShowPiiPanel(true);
    },
    openWatermark: () => setShowWatermarkModal(true),
    openPageNumbers: () => setShowPageNumberModal(true),
    openInsertPages: () => setInsertPagesAt(currentPage + 1),
    openBarcode: () => setShowBarcodeModal(true),
    openStamp: () => setShowStampModal(true),
    insertImage: () => imageEditHook.openImagePicker(),
    openCompress: () => setShowCompressModal(true),
    openFlatten: () => setShowFlattenModal(true),
    // แปลงจากไฟล์ที่บันทึกในเอกสารของฉัน — มีการแก้ไขที่ยังไม่บันทึก ถามก่อนว่าจะบันทึกทับไหม
    // (เดิมบันทึกทับให้เองเงียบ ๆ เหมือนดาวน์โหลด/พิมพ์รุ่นก่อน)
    openConvertWord: () => wordConversion.request({
      sessionId: session.sessionId,
      filename: session.filename || "",
      beforeStart: async () => {
        const pending = textEditHook.textPendingCount + imageEditHook.imagePendingCount > 0;
        if (!unsaved && !pending) return;
        const ok = window.confirm(t("editor.msg.convertWordUnsavedConfirm"));
        if (ok) await handleAutoSaveToServer();
      },
    }),
    // เปรียบเทียบ: เอกสารที่กำลังแก้ (B) กับ เวอร์ชันก่อนหน้า / ที่บันทึกไว้ / ไฟล์อื่น / อัปโหลด (A)
    openCompare: async () => {
      try {
        const res = await api.getMyFiles();
        setCompareFiles(res.files || []);
      } catch (err) {
        setStatusMessage(t("editor.msg.openCompareFailed", { error: err.message }));
      }
    },
    openAbout: () => setAboutOpen(true),
  });

  function formatSize(bytes) {
    return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function handleCompressConfirm() {
    setShowCompressModal(false);
    const trySmallest = compressProfile === "screen" ? "" : t("editor.msg.compressTrySmallest");
    return runDocumentChange((sid) => api.compressPdf(sid, compressProfile), {
      busy: t("editor.msg.compressBusy"),
      success: (res) => (res?.before && res?.after
        ? t("editor.msg.compressSuccessDetail", {
          before: formatSize(res.before),
          after: formatSize(res.after),
          percent: Math.round((1 - res.after / res.before) * 100),
        })
        : t("editor.msg.compressSuccess")),
      failure: t("editor.msg.compressFailed"),
      noChange: t("editor.msg.compressNoChange") + trySmallest,
    });
  }

  // ดาวน์โหลดเสร็จแล้วค่อยปิดหน้าต่าง — ถ้าผิดพลาด (เช่น ไม่มีหน้านั้น) แสดงในหน้าต่างให้แก้ต่อได้ ไม่ต้องพิมพ์ใหม่
  const handleExtractPages = async (pageRange, mode, format = "pdf", dpi = 150) => {
    setStatusMessage(format === "pdf" ? t("editor.msg.extractingPages") : t("editor.msg.creatingImages"));
    const { blob, filename } = await api.extractPages(session.sessionId, pageRange, mode, format, dpi);
    saveBlob(blob, filename);
    setIsExtractModalOpen(false);
    setStatusMessage(t("editor.msg.downloadedFile", { filename }));
  };

  // แผงหน้าเอกสาร › คลิกขวา › ส่งออกหน้าที่เลือกเป็นรูปภาพ (pages = เลขหน้า 0-based เรียงแล้ว)
  const handleExportPagesAsImage = async (pages, format) => {
    if (!session || !pages?.length) return;
    try {
      setStatusMessage(t("editor.msg.creatingImages"));
      const { blob, filename } = await api.extractPages(session.sessionId, pages.map((p) => p + 1).join(","), "single", format, 150);
      saveBlob(blob, filename);
      setStatusMessage(t("editor.msg.downloadedFile", { filename }));
    } catch (err) {
      setStatusMessage(t("editor.msg.exportImagesFailed", { error: err.message }));
    }
  };

  const handleSaveCopy = async () => {
    if (!copyFilename) return;
    try {
      setStatusMessage(t("editor.msg.savingCopy"));
      setShowSaveCopyModal(false);
      const res = await api.saveAsCopy(session.sessionId, copyFilename, copyPdfVersion || null);
      const v = res?.version;
      const notes = v
        ? [...(v.converted || []), ...(v.removed || []).map((r) => t("editor.msg.saveCopyRemovedItem", { item: r }))]
        : [];
      let baseMsg = t("editor.msg.saveCopySuccess");
      if (v) {
        const versionLabel = v.pdf_version.startsWith("PDF/A") ? v.pdf_version : `PDF ${v.pdf_version}`;
        baseMsg = t("editor.msg.saveCopySuccessVersion", { version: versionLabel });
      }
      const notesPart = notes.length ? ` — ${notes.join(", ")}` : "";
      setStatusMessage(`${baseMsg}${notesPart}${t("editor.msg.saveCopyOpenHint")}`);
    } catch (error) {
      console.error(error);
      const errMsg = error?.message
        ? t("editor.msg.saveCopyFailedDetail", { error: error.message })
        : t("editor.msg.saveCopyFailed");
      setStatusMessage(errMsg);
    }
  };

  function handleFlattenConfirm() {
    setShowFlattenModal(false);
    return runDocumentChange((sid) => api.flattenPdf(sid), {
      busy: t("editor.msg.flattenBusy"),
      success: t("editor.msg.flattenSuccess"),
      failure: t("editor.msg.flattenFailed"),
    });
  }

  // ใช้กับ PropertiesPanel/PDFCanvas: patchDraftEdit("fontSize")(12) → แก้ค่าเดียวใน draft ที่กำลังแก้
  const patchDraftEdit = (key) => (value) =>
    textEditHook.setDraftEdit((d) => (d ? { ...d, [key]: value } : d));

  async function handleCanvasDrag(tool, rectPt) {
    if (tool === null) {
      const isTinyDrag = rectPt.x1 - rectPt.x0 < 5 && rectPt.y1 - rectPt.y0 < 5;
      if (isTinyDrag) return;
      try {
        const words = await api.getWords(session.sessionId, currentPage);
        const selectedText = extractSelectedText(words, rectPt);
        setCopyPopup({ rectPt, textNormal: selectedText || "" });
      } catch (err) {
        setStatusMessage(t("editor.msg.genericError", { error: err.message }));
      }
      return;
    }
    

    if (tool === "redact") {
      try {
        const words = await api.getWords(session.sessionId, currentPage);
        const lineRects = computeSelectedLineRects(words, rectPt);
        
        // ถ้าเจอบรรทัดที่มีข้อความ ให้ใช้กรอบของข้อความเลย เพื่อความแม่นยำและลบเนียนๆ
        // แต่ถ้าลากคลุมบริเวณว่างๆ (หรือรูปภาพ) แล้วไม่เจอคำเลย ให้ใช้กรอบที่ลากมาตรงๆ
        if (lineRects && lineRects.length > 0) {
          redactHook.addRedactions(lineRects);
        } else {
          redactHook.addRedactions([rectPt]);
        }
      } catch (err) {
        console.error("Failed to get words for redact snap", err);
        redactHook.addRedactions([rectPt]);
      }
      return;
    }

    if (tool === "insert_text") {
      textEditHook.handleInsertTextDrag(rectPt);
      setActiveTool("edit_text");
    } else {
      void annotationHook.handleAnnotationDrag(tool, rectPt);
    }
  }

  return (
    <div
      className="fixed inset-0 flex flex-col bg-slate-50 overflow-hidden w-full h-full"
      // overflow: clip กันไม่ให้กล่องหลักถูกเลื่อนด้วยโปรแกรม/focus (Safari เคยเลื่อนจนแถบเมนูบนหายไปครึ่งหนึ่ง)
      // onScroll เป็นตัวกันสำรองสำหรับเบราว์เซอร์ที่ยังไม่รองรับ clip
      style={{ overflow: "clip" }}
      onScroll={resetUnintendedScroll}
    >
      {/* hidden file inputs (fixed at top to prevent Safari scrolling when clicked) */}
      <div style={{ position: "fixed", top: 0, left: 0, width: 0, height: 0, overflow: "hidden" }}>
        <input
          ref={pdfInputRef}
          type="file"
          accept="application/pdf"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) handleFileSelected(file);
          }}
        />
        <input
          ref={officeInputRef}
          type="file"
          accept=".docx,.doc,.xlsx,.xls,.pptx,.ppt,.rtf,.odt,.ods,.odp"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) handleFileSelected(file);
          }}
        />
        <input
          ref={imageEditHook.imageInsertInputRef}
          data-testid="image-insert-input"
          type="file"
          accept="image/*"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) insertImageFile(file);
            e.target.value = "";
          }}
        />
      </div>

      <MenuBar menus={menus} fileName={session?.filename} />
      <Toolbar
        hasDocument={!!session}
        onOpenClick={() => pdfInputRef.current?.click()}
        onSaveClick={handleAutoSaveToServer}
        onDownloadClick={handleAutoDownload}
        onPrintClick={handleAutoPrint}
        onCloseClick={closeDocument}
        onDocPropsClick={docPropsHook.handleOpenDocProps}
        zoom={zoom}
          onSetZoom={setZoom}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onZoomFitWidth={zoomFitWidth}
        onZoomFitHeight={zoomFitHeight}
        onZoomSet={(z) => setZoom(Math.min(5, Math.max(0.1, z)))}
        continuousMode={continuousMode}
        onToggleContinuousMode={toggleContinuousMode}
        activeTool={activeTool}
        onSelectTool={setActiveTool}
        onInsertImage={() => imageEditHook.openImagePicker()}
        editMode={editMode}
        pendingEditCount={pendingEditCount}
        onApplyEdits={applyAllEdits}
        applyingEdits={editMode === "redact" ? redactHook.applying : (editMode === "image" ? imageEditHook.applyingEdits : textEditHook.applyingEdits)}
        onCancelEdits={editMode === "redact" ? redactHook.cancelRedactions : null}
        onApplyAllPages={applyAllPages}
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={canUndo || hasLocalUndo}
        canRedo={canRedo}
        findOpen={findHook.open}
        onFindClick={() => (findHook.open ? findHook.closeFind() : findHook.openFind())}
      />
      <FindBar find={findHook} />

      {/* แผง PDPA ลอยอยู่ด้านขวา — เว้นที่ให้หน้าเอกสาร (จอใหญ่) เพื่อไม่ให้กรอบไฮไลต์ถูกบัง */}
      <div className={`flex-1 flex overflow-hidden min-h-0 ${showPiiPanel ? "sm:pr-[396px]" : ""}`}>
        <Sidebar
          pageCount={session?.pageCount || 0}
          currentPage={currentPage}
          thumbnails={sessionHook.thumbnails}
          onSelectPage={sessionHook.goToPage}
          bookmarks={sessionHook.bookmarks}
          onAddBookmark={sessionHook.addBookmark}
          onRemoveBookmark={sessionHook.removeBookmark}
          onRenameBookmark={sessionHook.renameBookmark}
          onExportPages={sessionHook.handleExportPages}
          onExportPagesAsImage={handleExportPagesAsImage}
          onReorderPages={pageOps.reorder}
          onDeletePages={pageOps.remove}
          onRotatePages={pageOps.rotate}
          onMovePages={pageOps.move}
          onInsertPages={(position) => setInsertPagesAt(position)}
          isOpenOnMobile={isSidebarOpen}
          onCloseMobile={() => setIsSidebarOpen(false)}
        />

        <PDFCanvas
          ref={canvasAreaRef}
          onSelectTool={setActiveTool}
          onRotateLeft={() => pageOps.rotate([currentPage], -90)}
          onRotateRight={() => pageOps.rotate([currentPage], 90)}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onZoomOriginal={() => setZoom(1)}
          hasDocument={!!session}
          pageImage={sessionHook.pageImage}
          fontInspector={fontInspector}
          tableEdit={tableEdit}
          barcodeEdit={barcodeEdit}
          cropPage={cropPage}
          formFill={formFill}
          continuousMode={continuousPages.active}
          continuousLayouts={continuousPages.layouts}
          continuousPages={continuousPages.cachedPages}
          thumbnails={sessionHook.thumbnails}
          pageImagePage={sessionHook.pageImagePage}
          currentPage={currentPage}
          onSelectPage={sessionHook.goToPage}
          pageWidthPt={session?.pageSizes?.[currentPage]?.[0] || 1}
          pageHeightPt={session?.pageSizes?.[currentPage]?.[1] || 1}
          zoom={zoom}
          onSetZoom={setZoom}
          loading={sessionHook.pageLoading}
          activeTool={activeTool}
          onAnnotationDrag={handleCanvasDrag}
          onImageDrop={insertImageFile}
          onOpenClick={() => pdfInputRef.current?.click()}
          onFileDrop={handleFileSelected}
          onNavigatePage={handleNavigatePage}
          onImageElementReady={(el) => {
            pageImgElRef.current = el;
          }}
          editMode={editMode}
          textBlocks={textEditHook.textBlocks}
          images={imageEditHook.images}
          onSelectTextBlock={textEditHook.handleSelectTextBlock}
          onResumeTextEdit={textEditHook.handleResumeTextEdit}
          onSelectImage={imageEditHook.handleSelectImage}
          pendingRedactions={redactHook.pendingRedactions}
          piiHighlights={piiHighlights.filter((h) => h.page === currentPage)}
          findMatches={findHook.pageMatches}
          onAddRedactions={redactHook.addRedactions}
          onResumeImageEdit={imageEditHook.handleResumeImageEdit}
          draftEdit={textEditHook.draftEdit}
          onDraftTextChange={patchDraftEdit("text")}
          onDraftRectChange={patchDraftEdit("rect")}
          onCancelEdit={textEditHook.handleCancelEdit}
          onDeleteEdit={textEditHook.handleDeleteEdit}
          onRestoreTextEdit={textEditHook.handleRestoreTextEdit}
          pendingEditsForPage={textEditHook.pendingEditsForPage}
          draftImageEdit={imageEditHook.draftImageEdit}
          onDraftImageRectChange={(rect) =>
            imageEditHook.setDraftImageEdit((d) => (d ? { ...d, rect } : d))
          }
          onImageReplaceFile={imageEditHook.handleImageReplaceFile}
          onCopyImageEdit={imageEditHook.copySelectedImage}
          onPasteImageEdit={() => imageEditHook.pasteImage()}
          canPasteImage={!!imageEditHook.copiedImage}
          onCommitImageEdit={imageEditHook.handleCommitImageEdit}
          onCancelImageEdit={imageEditHook.handleCancelImageEdit}
          onDeleteImageEdit={imageEditHook.handleDeleteImageEdit}
          onRestoreImageEdit={imageEditHook.handleRestoreImageEdit}
          pendingImageEditsForPage={imageEditHook.pendingImageEditsForPage}
          annotations={annotationHook.annotations}
          annotationDraft={annotationHook.annotationDraft}
          fonts={fontsHook.fonts}
          onSelectAnnotation={annotationHook.handleSelectAnnotation}
          onAnnotationDraftRectChange={annotationHook.handleAnnotationDraftRectChange}
          onAnnotationDraftContentChange={annotationHook.handleAnnotationDraftContentChange}
          onAnnotationDraftColorChange={annotationHook.handleAnnotationDraftColorChange}
          onAnnotationDraftFontKeyChange={annotationHook.handleAnnotationDraftFontKeyChange}
          onAnnotationDraftFontSizeChange={annotationHook.handleAnnotationDraftFontSizeChange}
          onCommitAnnotationEdit={annotationHook.handleCommitAnnotationEdit}
          onCancelAnnotationEdit={annotationHook.handleCancelAnnotationEdit}
          onMoveAnnotation={annotationHook.handleMoveAnnotation}
          onDeleteAnnotation={annotationHook.handleDeleteAnnotation}
          draftSignature={signatureHook.draftSignature}
          onDraftSignatureRectChange={signatureHook.handleDraftSignatureRectChange}
          onCommitSignature={() => signatureHook.handleCommitSignature(_onAfterSign)}
          onCancelSignature={signatureHook.handleCancelSignature}
        />

        {activeTool === "edit_table" && session && (
          <TableEditPanel
            hook={tableEdit}
            fontFamilies={fontsHook.fontFamilies}
            onClose={() => setActiveTool(null)}
            canUndo={canUndo || hasLocalUndo}
            canRedo={canRedo}
            onUndo={handleUndo}
            onRedo={handleRedo}
          />
        )}

        {activeTool === "edit_barcode" && session && (
          <BarcodeEditPanel hook={barcodeEdit} onClose={() => setActiveTool(null)}
            onInsertNew={() => setShowBarcodeModal(true)} />
        )}

        {activeTool === "crop_page" && session && (
          <CropPagePanel hook={cropPage} onClose={() => setActiveTool(null)} />
        )}

        {activeTool === "fill_form" && session && (
          <FormFillPanel
            hook={formFill}
            currentPage={currentPage}
            onSelectPage={sessionHook.goToPage}
            onSwitchToInsertText={() => setActiveTool("insert_text")}
            onClose={() => setActiveTool(null)}
          />
        )}

        {activeTool === "inspect_font" && session && (
          <FontInspectorPanel inspector={fontInspector} onClose={() => setActiveTool(null)}
            onShowDocumentFonts={() => setShowDocumentFonts(true)} />
        )}

        {textEditHook.draftEdit && (
          <PropertiesPanel
            fontFamilies={fontsHook.fontFamilies}
            fontKey={textEditHook.draftEdit.fontKey}
            onFontKeyChange={patchDraftEdit("fontKey")}
            fontSize={textEditHook.draftEdit.fontSize}
            onFontSizeChange={patchDraftEdit("fontSize")}
            colorHex={textEditHook.draftEdit.colorHex}
            onColorHexChange={patchDraftEdit("colorHex")}
            align={textEditHook.draftEdit.align || "left"}
            onAlignChange={patchDraftEdit("align")}
            valign={textEditHook.draftEdit.valign || "top"}
            onValignChange={patchDraftEdit("valign")}
            underline={textEditHook.draftEdit.underline || false}
            onUnderlineChange={patchDraftEdit("underline")}
            sourceFonts={textEditHook.draftEdit.sourceFonts}
            saving={false}
            errorMessage={textEditHook.textEditError}
            onSave={textEditHook.handleCommitBlockEdit}
            onCancel={textEditHook.handleCancelEdit}
          />
        )}
      </div>

      <StatusBar
        currentPage={currentPage}
        pageCount={session?.pageCount || 0}
        onGoToPage={sessionHook.goToPage}
        onPrev={() => sessionHook.goToPage(currentPage - 1)}
        onNext={() => sessionHook.goToPage(currentPage + 1)}
        hasDocument={!!session}
      />

      {wordConversion.dialogs}

      {statusMessage && (
        <div key={statusMessage} className="toast" onAnimationEnd={() => setStatusMessage("")}>
          {statusMessage}
        </div>
      )}

      {sessionHook.passwordState && (
        <PasswordModal
          fileName={sessionHook.passwordState.filename}
          error={sessionHook.passwordState.error}
          submitting={sessionHook.passwordState.submitting}
          onSubmit={handleUnlockSubmit}
          onCancel={sessionHook.handleUnlockCancel}
        />
      )}

      {annotationHook.pendingAnnotation && (
        <AnnotationTextPrompt
          type={annotationHook.pendingAnnotation.type}
          onSubmit={annotationHook.submitPendingAnnotation}
          onCancel={() => annotationHook.setPendingAnnotation(null)}
        />
      )}

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}

      {docPropsHook.docPropsOpen && (
        <DocumentPropertiesModal
          fileName={session?.filename}
          properties={docPropsHook.docProps}
          loading={docPropsHook.docPropsLoading}
          errorMessage={docPropsHook.docPropsError}
          onClose={docPropsHook.handleCloseDocProps}
          onShowFontDetails={session ? () => { docPropsHook.handleCloseDocProps(); setShowDocumentFonts(true); } : undefined}
        />
      )}

      {insertPagesAt !== null && session && (
        <InsertPagesModal session={session} currentPage={currentPage} defaultPosition={insertPagesAt}
          onInsert={pageOps.insert} onClose={() => setInsertPagesAt(null)} />
      )}

      {showDocumentFonts && session && (
        <DocumentFontsModal sessionId={session.sessionId} onClose={() => setShowDocumentFonts(false)} />
      )}

      {docPropsHook.addPasswordOpen && (
        <AddPasswordModal
          onSubmit={docPropsHook.handleAddPasswordSubmit}
          onCancel={docPropsHook.handleCloseAddPassword}
          error={docPropsHook.addPasswordError}
          submitting={docPropsHook.addPasswordSubmitting}
          pdfa={docPropsHook.addPasswordPdfa}
        />
      )}

      {signatureHook.signModalOpen === "electronic" && (
        <ElectronicSignModal
          onConfirm={signatureHook.handleElectronicSignatureReady}
          onCancel={signatureHook.handleCancelSignModal}
        />
      )}

      {signatureHook.signModalOpen === "digital" && (
        <DigitalSignModal
          onConfirm={signatureHook.handleDigitalSignatureReady}
          onCancel={signatureHook.handleCancelSignModal}
        />
      )}

      {copyPopup && (
        <CopyModal
          session={session}
          currentPage={currentPage}
          rectPt={copyPopup.rectPt}
          textNormal={copyPopup.textNormal}
          setStatusMessage={setStatusMessage}
          onCancel={() => setCopyPopup(null)}
        />
      )}

      
      {showSaveCopyModal && (
        <SaveCopyModal
          filename={copyFilename}
          onFilenameChange={setCopyFilename}
          pdfVersion={copyPdfVersion}
          onPdfVersionChange={setCopyPdfVersion}
          currentVersion={currentPdfInfo?.version}
          encrypted={!!currentPdfInfo?.encrypted}
          onCancel={() => setShowSaveCopyModal(false)}
          onConfirm={handleSaveCopy}
        />
      )}

      {showCompressModal && (
        <CompressModal
          profile={compressProfile}
          onProfileChange={setCompressProfile}
          onCancel={() => setShowCompressModal(false)}
          onConfirm={handleCompressConfirm}
        />
      )}

      {showPrintOptions && (
        <PrintOptionsModal
          onCancel={() => setShowPrintOptions(false)}
          onChoose={printDocument}
        />
      )}

      {showFlattenModal && (
        <FlattenModal onCancel={() => setShowFlattenModal(false)} onConfirm={handleFlattenConfirm} />
      )}

      {showBarcodeModal && (
        <BarcodeModal
          onClose={() => setShowBarcodeModal(false)}
          onSubmit={(result) => {
            setShowBarcodeModal(false);
            setActiveTool("edit_image"); // โหมดแก้ไขรูป — กล่องบาร์โค้ดลากย้าย/ย่อขยายได้ แล้วกด "บันทึกการแก้ไข"
            imageEditHook.startBarcodeInsert(result);
            setStatusMessage(t("editor.msg.barcodeInsertHint"));
          }}
        />
      )}

      {showStampModal && (
        <StampModal
          onClose={() => setShowStampModal(false)}
          onSubmit={(file, stampLabel) => {
            setShowStampModal(false);
            insertImageFile(file);
            setStatusMessage(t("editor.msg.stampInsertHint", { label: stampLabel }));
          }}
        />
      )}

      {showCreateBlankModal && (
        <CreateBlankPdfModal
          onClose={() => setShowCreateBlankModal(false)}
          onCreated={(res, { openFormBuilder }) => {
            setShowCreateBlankModal(false);
            const suffix = openFormBuilder ? "?tool=fill_form&mode=design" : "";
            void navigate(`/editor/${res.session_id}${suffix}`);
          }}
        />
      )}

      {compareFiles && session && (() => {
        const mine = compareFiles.find((f) => f.session_id === session.sessionId);
        const pending = textEditHook.textPendingCount + imageEditHook.imagePendingCount > 0;
        const previous = {
          label: t("editor.msg.comparePreviousLabel"),
          side: { sessionId: session.sessionId, version: "previous" },
          note: mine?.has_previous_version
            ? t("editor.msg.comparePreviousNoteAvailable")
            : t("editor.msg.comparePreviousNoteUnavailable"),
          disabled: !mine?.has_previous_version,
        };
        const saved = {
          label: t("editor.msg.compareSavedLabel"),
          side: { sessionId: session.sessionId, version: "saved" },
          note: t("editor.msg.compareSavedNote"),
          disabled: !mine,
        };
        return (
          <CompareStartModal
            files={compareFiles.filter((f) => f.session_id !== session.sessionId)}
            presetsA={unsaved && mine ? [saved, previous] : [previous, saved]}
            presetsB={[{
              label: t("editor.msg.compareCurrentLabel"),
              side: { sessionId: session.sessionId },
              note: pending ? t("editor.msg.compareCurrentNotePending") : t("editor.msg.compareCurrentNoteUnsaved"),
            }]}
            onClose={() => setCompareFiles(null)}
          />
        );
      })()}
      {showPageNumberModal && (
        <PageNumberModal
          pageCount={session?.pageCount || null}
          onClose={() => setShowPageNumberModal(false)}
          onSubmit={(payload) => {
            setShowPageNumberModal(false);
            return runDocumentChange((sid) => api.applyPageNumbers(sid, payload), {
              busy: t("editor.msg.pageNumberBusy"),
              success: t("editor.msg.pageNumberSuccess"),
              failure: t("editor.msg.pageNumberFailed"),
            });
          }}
        />
      )}

      {showWatermarkModal && (
        <WatermarkModal
          onClose={() => setShowWatermarkModal(false)}
          onSubmit={(payload) => {
            setShowWatermarkModal(false);
            return runDocumentChange((sid) => api.applyWatermark(sid, payload), {
              busy: t("editor.msg.watermarkBusy"),
              success: t("editor.msg.watermarkSuccess"),
              failure: t("editor.msg.watermarkFailed"),
            });
          }}
        />
      )}


      <ExtractPagesModal
        isOpen={isExtractModalOpen}
        onClose={() => setIsExtractModalOpen(false)}
        onExtract={handleExtractPages}
        totalPages={session?.pageCount || 1}
        currentPage={currentPage + 1}
      />
      {showPiiPanel && session && (
        <PiiPanel
          key={session.sessionId}
          sessionId={session.sessionId}
          fileName={session.filename}
          onGoToPage={sessionHook.goToPage}
          onHighlights={setPiiHighlights}
          onApplied={async () => {
            resetTransientEditState();
            await refreshAfterHistoryChange();
            setCanUndo(true);
            setCanRedo(false);
          }}
          onClose={() => setShowPiiPanel(false)}
        />
      )}
      <SearchRedactModal
        open={showRedactSearchModal}
        onClose={() => setShowRedactSearchModal(false)}
        session={session?.sessionId}
        onComplete={() => {
          sessionHook.refreshCurrentPage().catch((e) => console.warn("refresh page failed", e));
          void refreshAfterHistoryChange();
          setCanUndo(true);
          setCanRedo(false);
        }}
      />
    </div>
  );

}
