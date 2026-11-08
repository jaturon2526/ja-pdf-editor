import StorageQuotaCard from '../components/dashboard/StorageQuotaCard.jsx';
import DeleteConfirmModal from '../components/dashboard/DeleteConfirmModal.jsx';
import useWordConversion from '../hooks/useWordConversion.jsx';
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPublicConfig } from '../api/config.js';
import { getMyFiles, getMe, uploadPdf, openFile, unlockPdf, closeSession, deleteFile, renameFile, getAiQuota, logout } from '../api';
import AppBrand from "../components/AppBrand.jsx";
import UserAvatar from "../components/UserAvatar.jsx";
import PasswordModal from '../components/PasswordModal.jsx';
import AutoGenModal from '../components/AutoGenModal.jsx';
import MergeModal from '../components/MergeModal.jsx';
import RenameModal from '../components/RenameModal.jsx';
import InstallFontModal from '../components/InstallFontModal.jsx';
import TermsModal from '../components/TermsModal.jsx';
import { useFonts } from '../hooks/useFonts.js';
import NotificationBell from '../components/signing/NotificationBell.jsx';
import ToolCard from '../components/dashboard/ToolCard.jsx';
import CompareStartModal from '../components/compare/CompareStartModal.jsx';
import { isTouchDevice } from '../scan/camera.js';
import ChooseFileModal from '../components/dashboard/ChooseFileModal.jsx';
import QuickFileAction, { formatFileSize } from '../components/dashboard/QuickFileAction.jsx';
import StoredFileProperties from '../components/dashboard/StoredFileProperties.jsx';
import { listSigningRequests } from '../api/signing.js';
import { downloadStoredFile, saveBlob } from '../api.js';

const UPLOAD_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/jpg"];
// ไฟล์ Office แปลงเป็น PDF ที่เซิร์ฟเวอร์ (LibreOffice) แล้วเก็บเป็น PDF — ต้องตรงกับ OFFICE_EXTS ใน backend/app/api/pdf/files.py
const OFFICE_EXTS = [".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".rtf", ".odt", ".ods", ".odp"];
const UPLOAD_ACCEPT = [".pdf", ".png", ".jpg", ".jpeg", ...OFFICE_EXTS].join(",");
const UPLOAD_KINDS = "PDF, รูปภาพ (PNG/JPG) หรือไฟล์ Office (Word/Excel/PowerPoint)";
function isOfficeFile(file) {
  const name = (file.name || "").toLowerCase();
  return OFFICE_EXTS.some((ext) => name.endsWith(ext));
}
// บางเบราว์เซอร์/ระบบไม่ส่ง MIME type มา — ดูนามสกุลไฟล์แทน
function isSupportedUpload(file) {
  return UPLOAD_TYPES.includes(file.type) || /\.(pdf|png|jpe?g)$/i.test(file.name || "") || isOfficeFile(file);
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [quota, setQuota] = useState(null);
  const [aiQuota, setAiQuota] = useState(null);
  // ไฟล์ที่รอยืนยันการลบ (1 ไฟล์จากเมนู หรือหลายไฟล์จากโหมดเลือก)
  const [deleteTargets, setDeleteTargets] = useState(null);
  // โหมดเลือกหลายไฟล์: คลิกการ์ด = เลือก/ยกเลิก แทนการเปิดไฟล์
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [compareStart, setCompareStart] = useState(null); // null | { a, b } ค่าเริ่มต้นของหน้าต่างเปรียบเทียบ
  // สรุปงานลงนามบน Dashboard: รอฉันลงนาม / ที่ฉันส่งและยังไม่ครบ
  const [signingCounts, setSigningCounts] = useState({ toSign: 0, sentPending: 0 });
  const [showSignChooser, setShowSignChooser] = useState(false);
  const [showWordChooser, setShowWordChooser] = useState(false);
  // ทำกับไฟล์โดยไม่ต้องเปิด Editor: { action: 'watermark' | 'page_numbers' | 'redact_search' | 'encrypt' | 'pdpa', file? } | null
  const [quickAction, setQuickAction] = useState(null);
  // สแกนเอกสารด้วยกล้อง — แสดงเฉพาะมือถือ/แท็บเล็ต (จอสัมผัส รวม iPad)
  const [canScan] = useState(() => isTouchDevice());
  const [propsFile, setPropsFile] = useState(null); // ไฟล์ที่เปิดดูคุณสมบัติเอกสาร (เมนู ☰)
  const [deleteError, setDeleteError] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [viewMode, setViewMode] = useState(() => localStorage.getItem('viewMode') || 'grid');
  // ไฟล์ที่มีรหัสผ่านและกำลังรอให้ผู้ใช้กรอกรหัสก่อนเข้า Editor: { sessionId, filename, error, submitting }
  const [passwordState, setPasswordState] = useState(null);

  const filteredFiles = files.filter(f => f?.filename?.toLowerCase().includes(searchQuery.toLowerCase()));
  const selectedFiles = files.filter(f => selectedIds.has(f.id));
  const allVisibleSelected = filteredFiles.length > 0 && filteredFiles.every(f => selectedIds.has(f.id));

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const enterSelectMode = (file) => {
    setSelectMode(true);
    setSelectedIds(file ? new Set([file.id]) : new Set());
  };
  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };
  const toggleSelectAllVisible = () => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allVisibleSelected) filteredFiles.forEach(f => next.delete(f.id));
      else filteredFiles.forEach(f => next.add(f.id));
      return next;
    });
  };
  const handleFileClick = (f) => {
    if (selectMode) toggleSelect(f.id);
    else handleOpenFile(f.session_id);
  };

  // Esc ออกจากโหมดเลือก (ยกเว้นตอนหน้าต่างยืนยันการลบเปิดอยู่)
  useEffect(() => {
    if (!selectMode) return undefined;
    const onKey = (e) => { if (e.key === 'Escape' && !deleteTargets) exitSelectMode(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectMode, deleteTargets]);

  
  // เมนูไฟล์ (คลิกขวา หรือปุ่ม ☰ บนการ์ด) — จัดตำแหน่งไม่ให้ล้นขอบจอ
  // เก็บเป็นพิกัดในหน้าเอกสาร (absolute) ให้เมนูเลื่อนไปพร้อมการ์ด แทนการปิดเมื่อเลื่อนหน้า —
  // เดิมปิดทุกครั้งที่มี scroll ทำให้เมนูหายเองเมื่อเนื้อหาด้านบนโหลดเสร็จแล้วเบราว์เซอร์ปรับตำแหน่งเลื่อน (scroll anchoring)
  const MENU_W = 190;
  const MENU_H = 410;
  const placeMenu = (x, y, file) => {
    const left = Math.max(8, Math.min(x, window.innerWidth - MENU_W - 8));
    const top = y + MENU_H > window.innerHeight - 8 ? Math.max(8, y - MENU_H) : y;
    setContextMenu({ mouseX: left + window.scrollX, mouseY: top + window.scrollY, file });
  };

  const handleContextMenu = (e, file) => {
    e.preventDefault();
    placeMenu(e.clientX - 2, e.clientY - 4, file);
  };

  const handleMenuButton = (e, file) => {
    e.stopPropagation();
    if (contextMenu?.file?.id === file.id) {
      setContextMenu(null);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    placeMenu(rect.right - MENU_W, rect.bottom + 4, file);
  };

  const closeContextMenu = () => {
    setContextMenu(null);
  };

  const handleRenameSubmit = async (newName) => {
    if (!renameTarget) return;
    try {
      // ใช้ชื่อที่เซิร์ฟเวอร์บันทึกจริง (ตัดอักขระที่ใช้ไม่ได้ / เติม .pdf / ชื่อซ้ำเติม (2)) — เดิมแสดงตามที่พิมพ์
      const res = await renameFile(renameTarget.id, newName);
      const saved = res?.filename || newName;
      setMessage({ type: 'success', text: saved === newName ? 'เปลี่ยนชื่อไฟล์สำเร็จ' : `เปลี่ยนชื่อไฟล์เป็น "${saved}" แล้ว` });
      setFiles(files.map(f => f.id === renameTarget.id ? { ...f, filename: saved } : f));
      setRenameTarget(null);
    } catch (err) {
      setMessage({ type: 'error', text: err.message || "เปลี่ยนชื่อไม่สำเร็จ" });
    }
  };

  useEffect(() => {
    localStorage.setItem('viewMode', viewMode);
  }, [viewMode]);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [donationsOn, setDonationsOn] = useState(false);
  useEffect(() => {
    getPublicConfig().then((cfg) => setDonationsOn(!!cfg?.donations)).catch(() => {});
  }, []);
  const [showAutoGenModal, setShowAutoGenModal] = useState(false);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' }); // {type: 'error' | 'success', text: ''}
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null); // {current, total, name} ระหว่างอัปโหลดหลายไฟล์
  const dragDepth = useRef(0);

  const [contextMenu, setContextMenu] = useState(null);
  // ปิดเมนูไฟล์เมื่อกด Esc / คลิกที่อื่น / ย่อขยายหน้าต่าง (เลื่อนหน้าแล้วเมนูเลื่อนตามการ์ด ไม่ปิด)
  useEffect(() => {
    if (!contextMenu) return undefined;
    const close = () => setContextMenu(null);
    const onKey = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
    };
  }, [contextMenu]);
  const [renameTarget, setRenameTarget] = useState(null);


  const fontsHook = useFonts({ setStatusMessage: (msg) => setMessage({ type: 'success', text: msg }) });

  useEffect(() => {
    
  async function loadData() {
      try {
        const userData = await getMe();
        setUser(userData);
        const fileData = await getMyFiles();
        setFiles(fileData.files || []);
        if (fileData.quota) setQuota(fileData.quota);
        
        try {
            const aiData = await getAiQuota();
            setAiQuota(aiData);
        } catch(e) { console.error(e) }
        try {
          const requests = await listSigningRequests("all");
          setSigningCounts({
            toSign: requests.filter(r => r.my_turn).length,
            sentPending: requests.filter(r => r.is_owner && r.status === "in_progress").length,
          });
        } catch (e) { console.error(e) }
      } catch (err) {
        if (err.message && err.message.includes("401")) {
           handleLogout();
        }
      } finally {
        setLoading(false);
      }
    }
    loadData();
    // โหลดครั้งเดียวตอนเปิดหน้า — handleLogout เป็นฟังก์ชันที่สร้างใหม่ทุก render ถ้าใส่ใน deps จะโหลดซ้ำไม่หยุด
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // แปลงเป็น Word (ดู hooks/useWordConversion.jsx — ใช้ร่วมกับเมนู เครื่องมือ ใน Editor)
  const wordConversion = useWordConversion({
    onMessage: (type, text) => setMessage({ type, text }),
    onFinished: async () => {
      try {
        setAiQuota(await getAiQuota());
      } catch (e) { console.error("Failed to refresh AI quota:", e); }
    },
  });

  function handleStartConversion(e, fileRecordId) {
    e.stopPropagation();
    const file = files.find((f) => f.id === fileRecordId);
    wordConversion.request({ fileId: fileRecordId, filename: file?.filename || "" });
  }

  function confirmDelete(e, file) {
    e.stopPropagation();
    setDeleteTargets([file]);
    setDeleteError('');
  }

  function confirmDeleteSelected() {
    if (selectedFiles.length === 0) return;
    setDeleteTargets(selectedFiles);
    setDeleteError('');
  }

  // ลบทีละไฟล์ — ไฟล์ที่ลบไม่สำเร็จยังคงถูกเลือกไว้ ให้ลองใหม่ได้
  async function executeDelete() {
    if (!deleteTargets?.length) return;
    setIsDeleting(true);
    setDeleteError('');
    const failed = [];
    for (const file of deleteTargets) {
      try {
        await deleteFile(file.id);
      } catch (err) {
        console.error(err);
        failed.push({ file, message: err.message || "เกิดข้อผิดพลาดในการเชื่อมต่อ" });
      }
    }
    try {
      const updatedData = await getMyFiles();
      setFiles(updatedData.files || []);
      if (updatedData.quota) setQuota(updatedData.quota);
    } catch (err) {
      console.error(err);
    }
    const deletedIds = new Set(deleteTargets.map(f => f.id));
    failed.forEach(({ file }) => deletedIds.delete(file.id));
    setSelectedIds(prev => new Set([...prev].filter(id => !deletedIds.has(id))));
    setIsDeleting(false);
    if (failed.length === 0) {
      setDeleteTargets(null);
      if (deleteTargets.length > 1) {
        setMessage({ type: 'success', text: `ลบเอกสาร ${deleteTargets.length} ไฟล์เรียบร้อยแล้ว` });
        exitSelectMode();
      }
      return;
    }
    const okCount = deleteTargets.length - failed.length;
    setDeleteTargets(failed.map(({ file }) => file));
    setDeleteError(deleteTargets.length === 1
      ? `ไม่สามารถลบไฟล์ได้: ${failed[0].message}`
      : [`ลบไม่สำเร็จ ${failed.length} ไฟล์${okCount ? ` (ลบสำเร็จ ${okCount} ไฟล์)` : ''}:`,
         ...failed.map(({ file, message }) => `• ${file.filename}: ${message}`)].join('\n'));
  }


  async function handleDownloadFile(file) {
    try {
      const { blob, filename } = await downloadStoredFile(file.id, file.filename);
      saveBlob(blob, filename);
    } catch (err) {
      setMessage({ type: 'error', text: 'ดาวน์โหลดไม่สำเร็จ: ' + (err.message || '') });
    }
  }

  async function handleLogout() {
    await logout();
    localStorage.removeItem("token");
    navigate("/");
  }
  
  async function handleNewProject(e) {
    const input = e.target;
    const file = input.files[0];
    if (!file) return;
    setUploading(true);
    if (isOfficeFile(file)) setMessage({ type: 'success', text: `กำลังแปลง ${file.name} เป็น PDF... (อาจใช้เวลาสักครู่)` });
    try {
      const data = await uploadPdf(file);
      if (data.status === "password_required") {
        // ไฟล์มีรหัสผ่าน — ถามรหัสที่ Dashboard ก่อน แล้วค่อยเข้า Editor ตอนปลดล็อกสำเร็จ
        setPasswordState({ sessionId: data.session_id, filename: data.filename, error: null, submitting: false });
        setUploading(false);
        return;
      }
      navigate(`/editor/${data.session_id}`);
    } catch (err) {
      setMessage({ type: 'error', text: "อัปโหลดไม่สำเร็จ: " + err.message });
      setUploading(false);
    } finally {
      input.value = ""; // อนุญาตให้เลือกไฟล์เดิมซ้ำได้หลังยกเลิก
    }
  }

  async function handleOpenFile(sessionId) {
    try {
      const data = await openFile(sessionId);
      if (data.status === "password_required") {
        setPasswordState({ sessionId: data.session_id, filename: data.filename, error: null, submitting: false });
        return;
      }
      navigate(`/editor/${data.session_id}`);
    } catch (err) {
      setMessage({ type: 'error', text: "ไม่สามารถเปิดไฟล์ได้: " + err.message });
    }
  }

  async function handleUnlockSubmit(password) {
    if (!passwordState) return;
    setPasswordState((s) => ({ ...s, submitting: true, error: null }));
    try {
      const res = await unlockPdf(passwordState.sessionId, password);
      if (res.status === "invalid_password") {
        setPasswordState((s) => ({ ...s, submitting: false, error: "รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่" }));
        return;
      }
      const sessionId = passwordState.sessionId;
      setPasswordState(null);
      navigate(`/editor/${sessionId}`);
    } catch (err) {
      setPasswordState((s) => ({ ...s, submitting: false, error: err.message }));
    }
  }

  function handleUnlockCancel() {
    // ปิดเฉพาะ session ในหน่วยความจำ — ไฟล์ต้นฉบับยังอยู่ในรายการของ Dashboard (ดู session_manager.close)
    if (passwordState) closeSession(passwordState.sessionId).catch(() => {});
    setPasswordState(null);
    // ไฟล์ที่เพิ่งอัปโหลดแล้วยกเลิกรหัสผ่าน ยังต้องปรากฏในรายการไฟล์
    getMyFiles()
      .then((d) => {
        setFiles(d.files || []);
        if (d.quota) setQuota(d.quota);
      })
      .catch(() => {});
  }

  // อัปโหลดหลายไฟล์ (ลากวาง / เลือกหลายไฟล์) — ส่งทีละไฟล์ตามลำดับ ไม่ให้เซิร์ฟเวอร์รับภาระพร้อมกัน
  // อัปโหลดเสร็จแล้วปิด session ทันที (ไฟล์ยังอยู่ในเอกสารของฉัน) — ไฟล์ที่มีรหัสผ่านจะถามรหัสตอนเปิด
  async function handleUploadMany(fileList) {
    const all = Array.from(fileList || []);
    if (all.length === 0 || uploading) return;
    const accepted = all.filter(isSupportedUpload);
    const rejected = all.filter((f) => !isSupportedUpload(f)).map((f) => `${f.name}: ไม่ใช่ไฟล์ ${UPLOAD_KINDS}`);
    if (accepted.length === 0) {
      setMessage({ type: 'error', text: `รองรับเฉพาะไฟล์ ${UPLOAD_KINDS} เท่านั้น`, details: rejected });
      return;
    }
    setUploading(true);
    const failed = [...rejected];
    let done = 0;
    for (const [i, file] of accepted.entries()) {
      setUploadProgress({ current: i + 1, total: accepted.length, name: file.name });
      setMessage({ type: 'success', text: `${isOfficeFile(file) ? "กำลังอัปโหลดและแปลงเป็น PDF" : "กำลังอัปโหลด"} ${i + 1}/${accepted.length}: ${file.name}` });
      try {
        const data = await uploadPdf(file);
        done += 1;
        if (data?.session_id) closeSession(data.session_id).catch(() => {});
      } catch (err) {
        failed.push(`${file.name}: ${err.message || "อัปโหลดไม่สำเร็จ"}`);
      }
    }
    setUploadProgress(null);
    try {
      const updatedData = await getMyFiles();
      setFiles(updatedData.files || []);
      if (updatedData.quota) setQuota(updatedData.quota);
    } catch {
      /* รายการไฟล์จะอัปเดตเมื่อโหลดหน้าใหม่ */
    }
    setUploading(false);
    if (failed.length === 0) {
      setMessage({ type: 'success', text: done === 1 ? `อัปโหลด ${accepted[0].name} สำเร็จแล้ว` : `อัปโหลดสำเร็จ ${done} ไฟล์` });
      setTimeout(() => setMessage({ type: '', text: '' }), 5000);
    } else {
      setMessage({
        type: done > 0 ? 'success' : 'error',
        text: done > 0 ? `อัปโหลดสำเร็จ ${done} ไฟล์ · ไม่สำเร็จ ${failed.length} ไฟล์` : `อัปโหลดไม่สำเร็จ ${failed.length} ไฟล์`,
        details: failed,
      });
    }
  }

  function handleFileInput(e) {
    const input = e.target;
    const picked = Array.from(input.files || []);
    if (picked.length > 1) {
      handleUploadMany(picked).finally(() => { input.value = ""; });
      return;
    }
    handleNewProject(e); // ไฟล์เดียว: อัปโหลดแล้วเปิดใน Editor เหมือนเดิม
  }

  function hasFiles(e) {
    return Array.from(e.dataTransfer?.types || []).includes("Files");
  }

  function handleDragEnter(e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  }

  function handleDragOver(e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
  }

  function handleDragLeave(e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    // dragleave เกิดทุกครั้งที่เมาส์ข้ามขอบ element ลูก — นับชั้นไว้ ไม่งั้นกรอบกะพริบ
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setIsDragging(false);
  }

  function handleDrop(e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setIsDragging(false);
    handleUploadMany(e.dataTransfer.files);
  }

  return (
    <div 
      className="min-h-screen bg-gray-50 relative" onClick={closeContextMenu}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-blue-500 bg-opacity-20 flex items-center justify-center border-4 border-dashed border-blue-500 m-4 rounded-3xl backdrop-blur-sm transition-all pointer-events-none">
          <div className="bg-white px-8 py-6 rounded-2xl shadow-xl flex flex-col items-center gap-4 animate-bounce">
            <div className="bg-blue-100 p-4 rounded-full text-blue-600">
              <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-800 text-center">วางไฟล์ PDF รูปภาพ หรือไฟล์ Office ที่นี่</h2>
            <p className="text-gray-500 font-medium text-center">วางได้หลายไฟล์พร้อมกัน — อัปโหลดเก็บไว้ในเอกสารของฉัน</p>
          </div>
        </div>
      )}
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0 flex items-center min-w-0">
                <AppBrand nameClassName="max-[389px]:hidden" />
              </div>
            </div>
            <div className="flex items-center gap-1 sm:gap-3 relative">
              <NotificationBell />
              <button 
                onClick={() => window.open("/manual.html", "_blank")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                title="คู่มือการใช้งาน"
                aria-label="คู่มือการใช้งาน"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
                <span className="hidden sm:inline">คู่มือ</span>
              </button>
              {user && (
                <div className="relative">
                  <button 
                    aria-label="เมนูบัญชี"
                    onClick={() => setIsProfileOpen(!isProfileOpen)}
                    className="flex items-center gap-2 focus:outline-none"
                  >
                    <UserAvatar user={user} size={40} className="hover:bg-blue-700 transition-colors" />
                  </button>
                  
                  {isProfileOpen && (
                    <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg py-1 z-10 border border-gray-100 overflow-hidden transform opacity-100 scale-100 transition-all origin-top-right">
                      <div className="px-4 py-3 border-b border-gray-50 bg-gray-50/50">
                        <p className="text-sm text-gray-900 font-semibold truncate">{user.display_name || user.email}</p>
                        {user.display_name && <p className="text-xs text-gray-500 truncate mt-0.5">{user.email}</p>}
                        <p className="text-xs text-blue-600 mt-1 font-medium uppercase tracking-wider">Plan: {user.plan_type}{user.plan_type !== "free" && user.expire_date ? ` · ถึง ${new Date(user.expire_date).toLocaleDateString("th-TH", { dateStyle: "medium" })}` : ""}</p>
                      </div>
                      <a href="#" onClick={(e) => { e.preventDefault(); setIsProfileOpen(false); navigate("/profile"); }} className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors">
                        โปรไฟล์ส่วนตัว
                      </a>
                      {donationsOn && !user.is_admin && <a href="#" data-testid="menu-support" onClick={(e) => { e.preventDefault(); setIsProfileOpen(false); navigate("/support"); }} className="block px-4 py-2.5 text-sm text-amber-700 hover:bg-amber-50 transition-colors">
                        ☕ สนับสนุนผู้พัฒนา
                      </a>}
                      <a href="#" onClick={(e) => { e.preventDefault(); setIsProfileOpen(false); navigate("/security"); }} className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors">
                        ความปลอดภัย
                      </a>
                      {/* ไม่มี AI ของระบบและไม่เปิดให้ใช้ key ส่วนตัว = ไม่มีอะไรให้ตั้ง → ซ่อนเมนู */}
                      {(aiQuota?.system_ai || aiQuota?.user_keys_enabled) && (
                        <a href="#" onClick={(e) => { e.preventDefault(); setIsProfileOpen(false); navigate("/ai-config"); }} className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors">
                          ตั้งค่า AI (API Key)
                        </a>
                      )}
                      {user.is_admin && (
                        <a href="#" onClick={(e) => { e.preventDefault(); setIsProfileOpen(false); navigate("/admin"); }} className="block px-4 py-2.5 text-sm text-purple-700 hover:bg-purple-50 hover:text-purple-800 transition-colors font-medium">
                          จัดการระบบ (Admin)
                        </a>
                      )}
                      <div className="border-t border-gray-100"></div>
                      <a href="#" onClick={(e) => { e.preventDefault(); handleLogout(); }} className="block px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 hover:text-red-700 font-medium transition-colors">
                        ออกจากระบบ
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        
        {/* Message Banner */}
        {message.text && (
          <div className={`mb-6 p-4 rounded-lg flex items-start ${message.type === 'error' ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-green-50 text-green-700 border border-green-200'}`}>
            <div className="flex-shrink-0 mr-3 mt-0.5">
              {message.type === 'error' ? (
                <svg className="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              )}
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium">{message.text}</p>
              {message.details?.length > 0 && (
                <ul className="mt-1 list-disc pl-5 text-sm space-y-0.5" data-testid="message-details">
                  {message.details.map((d) => <li key={d} className="break-all">{d}</li>)}
                </ul>
              )}
            </div>
            <button onClick={() => setMessage({type: '', text: ''})} className={`ml-3 -mx-1.5 -my-1.5 p-1.5 rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 inline-flex ${message.type === 'error' ? 'bg-red-50 text-red-500 hover:bg-red-100 focus:ring-offset-red-50 focus:ring-red-600' : 'bg-green-50 text-green-500 hover:bg-green-100 focus:ring-offset-green-50 focus:ring-green-600'}`}>
              <span className="sr-only">Dismiss</span>
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        )}

        {/* Quick Tools Section */}
        <div className="mb-8">
          <h3 className="text-lg leading-6 font-semibold text-gray-900 mb-3 sm:mb-4">เครื่องมือด่วน (Quick Tools)</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            {canScan && (
              <ToolCard
                color="teal"
                testId="tool-card-scan"
                title="สแกนเอกสาร"
                description="ถ่ายเอกสารด้วยกล้อง เป็น PDF ขาวดำ ค้นหาคำได้"
                onClick={() => navigate('/scan')}
                icon={<><path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3" /><path d="M7 12h10" /></>}
              />
            )}
            <ToolCard
              color="sky"
              testId="tool-card-word"
              title="แปลงเป็น Word"
              description="PDF หรือไฟล์สแกน เป็น Word ที่แก้ไขได้"
              onClick={() => setShowWordChooser(true)}
              icon={<><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" /><path d="M8 13l1.5 5L12 14l2.5 4L16 13" /></>}
            />
            <ToolCard
              color="indigo"
              testId="tool-card-compare"
              title="เปรียบเทียบเอกสาร"
              description="หาจุดต่างของ 2 ไฟล์ ข้อความและภาพ"
              onClick={() => setCompareStart({})}
              icon={<><path d="M9 4H5a1 1 0 00-1 1v14a1 1 0 001 1h4M15 4h4a1 1 0 011 1v14a1 1 0 01-1 1h-4" /><path d="M12 2v20" /><path d="M7 9h2M7 13h2M15 9h2M15 13h2" /></>}
            />
            <ToolCard
              color="purple"
              title="สร้างเอกสารอัตโนมัติ"
              description="กรอกข้อมูลแล้วสร้าง PDF ทันที"
              onClick={() => setShowAutoGenModal(true)}
              icon={<path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />}
            />
            <ToolCard
              color="green"
              title="รวมไฟล์ PDF"
              description="รวมหลายไฟล์เป็นไฟล์เดียว"
              onClick={() => setShowMergeModal(true)}
              icon={<path d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />}
            />
            <ToolCard
              color="blue"
              title="ใส่ลายน้ำ"
              description="ประทับข้อความลายน้ำทุกหน้า"
              onClick={() => setQuickAction({ action: 'watermark' })}
              icon={<><path d="M12 3s-6 6.5-6 11a6 6 0 0012 0c0-4.5-6-11-6-11z" /><path d="M9.5 15a2.5 2.5 0 002.5 2.5" /></>}
            />
            <ToolCard
              color="blue"
              testId="tool-card-page-numbers"
              title="ใส่เลขหน้า"
              description="1, 2, 3 หรือ 1/N · เลขไทยได้"
              onClick={() => setQuickAction({ action: 'page_numbers' })}
              icon={<><path d="M7 3h7l5 5v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" /><path d="M9 9h5M9 12h6" /><path d="M11.5 16.5l1-1v3.5" /></>}
            />
            <ToolCard
              color="red"
              title="เซ็นเซอร์ด้วยคำค้นหา"
              description="ลบคำที่ค้นหาออกถาวร"
              onClick={() => setQuickAction({ action: 'redact_search' })}
              icon={<><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5 5" /><path d="M7.5 10.5h6" strokeWidth="3" /></>}
            />
            <ToolCard
              color="indigo"
              testId="tool-card-pdpa"
              title="ปกปิดข้อมูลส่วนบุคคล"
              description="ตรวจหาเลขบัตร เบอร์โทร ฯลฯ ตาม PDPA"
              onClick={() => setQuickAction({ action: 'pdpa' })}
              icon={<><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z" /><path d="M8.5 12h7" strokeWidth="3" /></>}
            />
            {/* ติดตั้งฟอนต์อยู่ท้ายสุดเสมอ — ใช้ไม่บ่อย (ตั้งครั้งเดียวต่อบัญชี) */}
            <ToolCard
              color="orange"
              title="ติดตั้งฟอนต์"
              description="เพิ่มฟอนต์ใหม่เข้าระบบ"
              onClick={fontsHook.handleOpenInstallFont}
              icon={<path d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />}
            />
          </div>
        </div>

        {/* Signing Section */}
        <div className="mb-8">
          <div className="flex items-baseline justify-between mb-3 sm:mb-4">
            <h3 className="text-lg leading-6 font-semibold text-gray-900">การลงนามเอกสาร</h3>
            <button type="button" onClick={() => navigate("/signing")} className="text-sm font-medium text-blue-600 hover:text-blue-800">
              ดูทั้งหมด →
            </button>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
            <ToolCard
              color="sky"
              testId="signing-card-to-sign"
              title="รอฉันลงนาม"
              description={signingCounts.toSign ? `ถึงคิวคุณ ${signingCounts.toSign} เอกสาร` : "ไม่มีเอกสารที่รอคุณ"}
              badge={signingCounts.toSign}
              onClick={() => navigate("/signing?box=to_sign")}
              icon={<path d="M15.232 5.232l3.536 3.536M9 13l6.232-6.232a2.5 2.5 0 113.536 3.536L12.536 16.536 8 18l1.464-4.536zM4 20h16" />}
            />
            <ToolCard
              color="emerald"
              title="ส่งเอกสารให้ลงนาม"
              description="เลือกไฟล์ แล้วกำหนดผู้ลงนาม"
              onClick={() => setShowSignChooser(true)}
              icon={<path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />}
            />
            <ToolCard
              color="indigo"
              title="ที่ฉันส่ง"
              description={signingCounts.sentPending ? `รอผู้อื่นลงนาม ${signingCounts.sentPending} เอกสาร` : "ติดตามสถานะเอกสารที่ส่ง"}
              onClick={() => navigate("/signing?box=sent")}
              icon={<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />}
            />
          </div>
        </div>

        <div className="pb-5 border-b border-gray-200 sm:flex sm:items-center sm:justify-between mb-6">
          <h3 className="text-2xl leading-6 font-bold text-gray-900 whitespace-nowrap shrink-0">
            เอกสารของฉัน
          </h3>
          <div className="mt-3 sm:mt-0 sm:ml-4 flex items-center gap-2 sm:gap-4 flex-wrap sm:justify-end">
            <div className="relative w-full sm:w-64">
              <input 
                type="text" 
                placeholder="ค้นหาเอกสาร..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm transition-colors"
              />
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
            </div>
            {files.length > 0 && (
              <button
                type="button"
                onClick={() => (selectMode ? exitSelectMode() : enterSelectMode())}
                aria-pressed={selectMode}
                className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${selectMode ? 'bg-blue-50 border-blue-300 text-blue-700' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3" /><path strokeLinecap="round" strokeLinejoin="round" d="M8 12l3 3 5-6" /></svg>
                {selectMode ? 'เสร็จสิ้น' : 'เลือกหลายไฟล์'}
              </button>
            )}
            <div className="flex items-center bg-gray-100 p-1 rounded-lg border border-gray-200">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-md ${viewMode === 'grid' ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:text-gray-700'} transition-all`}
                title="มุมมองแบบกริด"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-md ${viewMode === 'list' ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:text-gray-700'} transition-all`}
                title="มุมมองแบบรายการ"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
              </button>
            </div>
            <label className={`ml-auto sm:ml-0 inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${uploading ? 'bg-blue-400 cursor-wait' : 'bg-blue-600 hover:bg-blue-700 cursor-pointer'} focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors`}>
              <svg className="-ml-1 mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              {uploading ? (uploadProgress ? `กำลังอัปโหลด ${uploadProgress.current}/${uploadProgress.total}...` : "กำลังอัปโหลด...") : <><span className="sm:hidden">อัปโหลด</span><span className="hidden sm:inline">อัปโหลด PDF/รูปภาพ/Office</span></>}
              <input type="file" multiple accept={UPLOAD_ACCEPT} className="hidden" onChange={handleFileInput} disabled={uploading} data-testid="upload-input" />
            </label>
          </div>
        </div>

        {!loading && quota && <StorageQuotaCard quota={quota} aiQuota={aiQuota} />}

        {loading ? (
          <div className="flex justify-center items-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : files.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-lg border border-dashed border-gray-300">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">ไม่มีเอกสาร</h3>
            <p className="mt-1 text-sm text-gray-500">เริ่มต้นใช้งานโดยการอัปโหลดไฟล์ PDF ไฟล์แรกของคุณ</p>
          </div>
        ) : (
          <>
            {selectMode && (
              <div className="sticky top-2 z-30 mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-blue-200 bg-blue-50/95 backdrop-blur px-4 py-3 shadow-sm" role="toolbar" aria-label="จัดการไฟล์ที่เลือก">
                <label className="inline-flex items-center gap-2 text-sm text-gray-700 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    disabled={filteredFiles.length === 0}
                  />
                  เลือกทั้งหมด{searchQuery ? 'ที่ค้นพบ' : ''} ({filteredFiles.length})
                </label>
                <span className="text-sm font-medium text-blue-800" data-testid="selected-count">
                  เลือกแล้ว {selectedFiles.length} ไฟล์
                </span>
                <div className="ml-auto flex items-center gap-2">
                  {selectedFiles.length === 2 && (
                    <button
                      type="button"
                      data-testid="compare-selected"
                      onClick={() => {
                        // ไฟล์ที่แก้ไขก่อน = ไฟล์เดิม (A) · ไฟล์ที่แก้ไขล่าสุด = ไฟล์ใหม่ (B)
                        const t = (f) => new Date(f.updated_at || f.created_at || 0).getTime();
                        const [older, newer] = [...selectedFiles].sort((x, y) => t(x) - t(y));
                        const side = (f) => ({ kind: 'file', side: { fileId: f.id, version: 'current' }, fileSide: { fileId: f.id, version: 'current' } });
                        setCompareStart({ a: side(older), b: side(newer) });
                      }}
                      className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-white border border-indigo-300 rounded-lg hover:bg-indigo-50"
                    >
                      เปรียบเทียบ 2 ไฟล์
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={exitSelectMode}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                  >
                    ยกเลิก
                  </button>
                  <button
                    type="button"
                    onClick={confirmDeleteSelected}
                    disabled={selectedFiles.length === 0}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    ลบที่เลือก ({selectedFiles.length})
                  </button>
                </div>
              </div>
            )}
            {viewMode === 'grid' ? (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {filteredFiles.map(f => (
                  <div 
                    key={f.id} 
                    onClick={() => handleFileClick(f)}
                    onContextMenu={(e) => handleContextMenu(e, f)}
                    data-testid="file-card"
                    aria-selected={selectMode ? selectedIds.has(f.id) : undefined}
                    className={`relative bg-white overflow-hidden shadow-sm rounded-xl border transition-all cursor-pointer group flex flex-col ${selectMode && selectedIds.has(f.id) ? 'border-blue-500 ring-2 ring-blue-200' : 'border-gray-200 hover:shadow-lg hover:border-blue-300'}`}
                  >
                    {selectMode && (
                      <input
                        type="checkbox"
                        className="absolute top-3 left-3 z-10 h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        checked={selectedIds.has(f.id)}
                        onChange={() => toggleSelect(f.id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`เลือก ${f.filename}`}
                      />
                    )}
                    <div className="bg-gray-50 flex justify-center items-center p-6 border-b border-gray-100 group-hover:bg-blue-50 transition-colors">
                      <svg className="h-16 w-16 text-gray-400 group-hover:text-blue-500 transition-colors" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="p-4 flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <h4 className="text-sm font-medium text-gray-900 truncate" title={f.filename}>{f.filename}</h4>
                        <p className="text-xs text-gray-500 mt-1">แก้ไขล่าสุด: {new Date(f.updated_at || f.created_at).toLocaleString('th-TH', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
                        {f.file_size > 0 && <p className="text-xs text-gray-500 mt-0.5">ขนาดไฟล์: {formatFileSize(f.file_size)}</p>}
                      </div>
                      <button
                          type="button"
                          onClick={(e) => handleMenuButton(e, f)}
                          className="-mr-1.5 -mt-1 shrink-0 p-1.5 rounded-lg text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
                          aria-label="เมนูไฟล์"
                          aria-haspopup="menu"
                          aria-expanded={contextMenu?.file?.id === f.id}
                          title="เมนู"
                        >
                          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
                        </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
                {/* table-fixed: ชื่อไฟล์ยาวถูกตัดด้วย … แทนการดันคอลัมน์ปุ่มเมนูหลุดจอ (มือถือ) */}
                <table className="w-full table-fixed text-left border-collapse">
                  <thead className="bg-gray-50">
                    <tr>
                      {selectMode && (
                        <th className="w-10 sm:w-12 pl-3 sm:pl-6 py-4 bg-gray-50 border-b border-gray-200">
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            checked={allVisibleSelected}
                            onChange={toggleSelectAllVisible}
                            aria-label="เลือกทั้งหมด"
                          />
                        </th>
                      )}
                      <th className="px-3 sm:px-6 py-4 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">ชื่อไฟล์</th>
                      <th className="hidden sm:table-cell w-56 px-6 py-4 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">เวลาแก้ไขล่าสุด</th>
                      <th className="w-14 sm:w-24 px-2 sm:px-6 py-4 bg-gray-50 text-right text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200"><span className="hidden sm:inline">จัดการ</span><span className="sr-only sm:hidden">เมนู</span></th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredFiles.map(f => (
                      <tr key={f.id} className={`transition-colors cursor-pointer group ${selectMode && selectedIds.has(f.id) ? 'bg-blue-50' : 'hover:bg-gray-50'}`} onClick={() => handleFileClick(f)} onContextMenu={(e) => handleContextMenu(e, f)} aria-selected={selectMode ? selectedIds.has(f.id) : undefined}>
                        {selectMode && (
                          <td className="pl-3 sm:pl-6 py-4">
                            <input
                              type="checkbox"
                              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                              checked={selectedIds.has(f.id)}
                              onChange={() => toggleSelect(f.id)}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`เลือก ${f.filename}`}
                            />
                          </td>
                        )}
                        <td className="px-3 sm:px-6 py-3 sm:py-4">
                          <div className="flex items-center min-w-0">
                            <svg className="flex-shrink-0 h-6 w-6 text-gray-400 group-hover:text-blue-500 transition-colors" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                            </svg>
                            <div className="ml-3 min-w-0">
                              <p className="text-sm font-medium text-gray-900 group-hover:text-blue-600 transition-colors truncate" title={f.filename}>{f.filename}</p>
                              <p className="sm:hidden text-xs text-gray-500 mt-0.5">
                                {new Date(f.updated_at || f.created_at).toLocaleString('th-TH', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                {f.file_size > 0 && ` · ${formatFileSize(f.file_size)}`}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="hidden sm:table-cell px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {new Date(f.updated_at || f.created_at).toLocaleString('th-TH', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          {f.file_size > 0 && <span className="block text-xs text-gray-400">{formatFileSize(f.file_size)}</span>}
                        </td>
                        <td className="px-2 sm:px-6 py-3 sm:py-4 whitespace-nowrap text-right">
                          <button
                          type="button"
                          onClick={(e) => handleMenuButton(e, f)}
                          className="p-1.5 rounded-lg text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
                          aria-label="เมนูไฟล์"
                          aria-haspopup="menu"
                          aria-expanded={contextMenu?.file?.id === f.id}
                          title="เมนู"
                        >
                          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
                        </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {deleteTargets && (
          <DeleteConfirmModal
            files={deleteTargets}
            error={deleteError}
            deleting={isDeleting}
            onCancel={() => setDeleteTargets(null)}
            onConfirm={executeDelete}
          />
        )}

        {quickAction && (
          <QuickFileAction
            action={quickAction.action}
            initialFile={quickAction.file || null}
            files={files}
            onClose={() => setQuickAction(null)}
            onOpenFile={handleOpenFile}
            onDone={async () => {
              try {
                const updated = await getMyFiles();
                setFiles(updated.files || []);
                if (updated.quota) setQuota(updated.quota);
              } catch (e) { console.error(e); }
            }}
          />
        )}

        {propsFile && <StoredFileProperties file={propsFile} onClose={() => setPropsFile(null)} />}

        {showSignChooser && (
          <ChooseFileModal
            title="เลือกเอกสารที่จะส่งให้ลงนาม"
            files={files}
            onCancel={() => setShowSignChooser(false)}
            onChoose={(f) => { setShowSignChooser(false); navigate(`/signing/new?file=${f.id}`); }}
          />
        )}

        {showWordChooser && (
          <ChooseFileModal
            title="เลือกเอกสารที่จะแปลงเป็น Word"
            subtitle="ใช้ได้ทั้ง PDF ทั่วไปและไฟล์สแกน/รูปถ่ายเอกสาร — ระบบตรวจให้อัตโนมัติ"
            emptyText="ยังไม่มีเอกสาร — อัปโหลด PDF หรือสแกนเอกสารก่อน แล้วค่อยแปลงเป็น Word"
            files={files}
            onCancel={() => setShowWordChooser(false)}
            onChoose={(f) => { setShowWordChooser(false); wordConversion.request({ fileId: f.id, filename: f.filename || "" }); }}
          />
        )}

        {wordConversion.dialogs}
      </main>

      {passwordState && (
        <PasswordModal
          fileName={passwordState.filename}
          error={passwordState.error}
          submitting={passwordState.submitting}
          onSubmit={handleUnlockSubmit}
          onCancel={handleUnlockCancel}
        />
      )}

      {showAutoGenModal && <AutoGenModal onClose={() => setShowAutoGenModal(false)} />}
      
      {compareStart && (
        <CompareStartModal
          files={files}
          initialA={compareStart.a || null}
          initialB={compareStart.b || null}
          onClose={() => setCompareStart(null)}
        />
      )}
      {showMergeModal && (
        <MergeModal
          documents={files}
          onClose={() => setShowMergeModal(false)}
          onMerged={async (res) => {
            navigate(`/editor/${res.session_id}`);
          }}
        />
      )}

      {fontsHook.installFontOpen && (
        <InstallFontModal
          fontFamilies={fontsHook.fontFamilies}
          error={fontsHook.installFontError}
          notice={fontsHook.installFontNotice}
          submitting={fontsHook.installFontSubmitting}
          onClose={fontsHook.handleCloseInstallFont}
          onInstallFamily={fontsHook.handleInstallFontFamily}
          onAddStyle={fontsHook.handleAddFontStyle}
          onRemoveFamily={fontsHook.handleRemoveFontFamily}
          onInstallFromUrl={fontsHook.handleInstallFromUrl}
        />
      )}

      {contextMenu && (
        <div 
          role="menu"
          className="absolute bg-white border border-gray-200 rounded-lg shadow-xl z-50 py-1 w-[190px] animate-in fade-in zoom-in-95 duration-100"
          style={{ top: contextMenu.mouseY, left: contextMenu.mouseX }}
          onClick={(e) => e.stopPropagation()}
        >
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-blue-600 flex items-center gap-2"
            onClick={() => {
              setRenameTarget(contextMenu.file);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            เปลี่ยนชื่อไฟล์
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-blue-600 flex items-center gap-2"
            onClick={() => {
              handleDownloadFile(contextMenu.file);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12"></path><path d="M7 10l5 5 5-5"></path><path d="M5 21h14"></path></svg>
            ดาวน์โหลด
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-purple-600 flex items-center gap-2"
            onClick={(e) => {
              handleStartConversion(e, contextMenu.file.id);
              closeContextMenu();
            }}
          >
            <svg className="shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path><path d="M8 13l1.5 5L12 14l2.5 4L16 13"></path></svg>
            <span className="flex flex-col leading-tight">แปลงเป็น Word<span className="text-[11px] text-gray-400">รองรับไฟล์สแกน</span></span>
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-emerald-600 flex items-center gap-2"
            onClick={() => {
              navigate(`/signing/new?file=${contextMenu.file.id}`);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
            ส่งให้ลงนาม
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-blue-600 flex items-center gap-2"
            onClick={() => {
              setQuickAction({ action: 'encrypt', file: contextMenu.file });
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>
            เข้ารหัส PDF
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-indigo-600 flex items-center gap-2"
            onClick={() => {
              setQuickAction({ action: 'pdpa', file: contextMenu.file });
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z"></path><path d="M9 12h6"></path></svg>
            ปกปิดข้อมูลส่วนบุคคล
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-teal-600 flex items-center gap-2"
            onClick={() => {
              setQuickAction({ action: 'compress', file: contextMenu.file });
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 14h6v6"></path><path d="M20 10h-6V4"></path><path d="M14 10l7-7"></path><path d="M3 21l7-7"></path></svg>
            ลดขนาดไฟล์
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-blue-600 flex items-center gap-2"
            onClick={() => {
              setPropsFile(contextMenu.file);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 11v5"></path><path d="M12 8h.01"></path></svg>
            คุณสมบัติเอกสาร
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-blue-600 flex items-center gap-2"
            onClick={() => {
              if (selectMode) toggleSelect(contextMenu.file.id); else enterSelectMode(contextMenu.file);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M8 12l3 3 5-6"></path></svg>
            {selectMode ? (selectedIds.has(contextMenu.file.id) ? 'ยกเลิกการเลือก' : 'เลือกไฟล์นี้') : 'เลือกหลายไฟล์'}
          </button>
          <button 
            role="menuitem"
            className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
            onClick={(e) => {
              confirmDelete(e, contextMenu.file);
              closeContextMenu();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
            ลบเอกสาร
          </button>
        </div>
      )}

      <RenameModal
        isOpen={!!renameTarget}
        onClose={() => setRenameTarget(null)}
        onRename={handleRenameSubmit}
        initialName={renameTarget?.filename || ''}
      />

      {user && user.accepted_tos === false && (
        <TermsModal 
          onAccepted={() => setUser({ ...user, accepted_tos: true })}
          onDecline={handleLogout}
        />
      )}

      {/* Floating Feedback Button */}
      <a
        href="https://docs.google.com/forms/d/e/1FAIpQLScPacKO8qkTy1nKWqVcBph5uZ0sfEKFoI1miugStIk7OyACpA/viewform?usp=header"
        target="_blank"
        rel="noopener noreferrer"
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-600 hover:to-orange-700 text-white font-medium text-sm px-4 py-2.5 rounded-full shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all group"
        title="ส่งข้อเสนอแนะหรือแจ้งปัญหาการใช้งาน"
      >
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
        </span>
        <svg className="w-4 h-4 transition-transform group-hover:scale-110" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        <span>ข้อเสนอแนะ / แจ้งปัญหา</span>
      </a>

    </div>
  );
}
