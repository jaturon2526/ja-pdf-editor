// useDocumentProperties.js — จัดการ modal คุณสมบัติเอกสาร และ modal ตั้ง/ลบรหัสผ่าน

import { useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

export function useDocumentProperties({ session, setSession, setStatusMessage }) {
  const { t } = useI18n();
  // ---------- Document Properties ----------
  const [docPropsOpen, setDocPropsOpen] = useState(false);
  const [docProps, setDocProps] = useState(null);
  const [docPropsLoading, setDocPropsLoading] = useState(false);
  const [docPropsError, setDocPropsError] = useState(null);

  // ---------- Password ----------
  const [addPasswordOpen, setAddPasswordOpen] = useState(false);
  const [addPasswordError, setAddPasswordError] = useState(null);
  const [addPasswordSubmitting, setAddPasswordSubmitting] = useState(false);
  const [addPasswordPdfa, setAddPasswordPdfa] = useState(null); // "PDF/A-2b" = ไฟล์เป็น PDF/A (ห้ามเข้ารหัส) → เตือน

  // เปิดกล่องคุณสมบัติเอกสาร — ดึงข้อมูลจาก backend ใหม่ทุกครั้ง (เผื่อมีการแก้ไขระหว่างเปิด)
  async function handleOpenDocProps() {
    if (!session) return;
    setDocPropsOpen(true);
    setDocPropsLoading(true);
    setDocPropsError(null);
    try {
      const data = await api.getDocumentProperties(session.sessionId);
      setDocProps(data);
    } catch (err) {
      setDocPropsError(err.message);
    } finally {
      setDocPropsLoading(false);
    }
  }

  function handleCloseDocProps() {
    setDocPropsOpen(false);
    setDocProps(null);
    setDocPropsError(null);
  }

  // เปิดกล่องตั้งรหัสผ่านใหม่ (เมนู File > เข้ารหัส PDF... — โชว์เฉพาะตอนยังไม่มีรหัสผ่าน)
  function handleOpenAddPassword() {
    if (!session) return;
    setAddPasswordError(null);
    setAddPasswordPdfa(null);
    setAddPasswordOpen(true);
    api.getDocumentProperties(session.sessionId)
      .then((p) => setAddPasswordPdfa(p?.pdfa || null))
      .catch(() => {});
  }

  function handleCloseAddPassword() {
    setAddPasswordOpen(false);
    setAddPasswordError(null);
  }

  async function handleAddPasswordSubmit(password, encryption = "aes256") {
    if (!session) return;
    setAddPasswordSubmitting(true);
    setAddPasswordError(null);
    try {
      const res = await api.addPassword(session.sessionId, password, encryption);
      setSession((s) => (s ? { ...s, isPasswordProtected: res.is_password_protected } : s));
      setAddPasswordOpen(false);
      const algorithm = encryption === "aes128" ? "AES-128" : "AES-256";
      setStatusMessage(t("editor.hooks.docProps.addPasswordSuccess", { algorithm }));
    } catch (err) {
      setAddPasswordError(err.message);
    } finally {
      setAddPasswordSubmitting(false);
    }
  }

  // ลบรหัสผ่าน (เมนู File > ลบรหัสผ่าน — โชว์เฉพาะตอนมีรหัสผ่านป้องกันอยู่)
  async function handleRemovePassword() {
    if (!session) return;
    const ok = window.confirm(t("editor.hooks.docProps.removePasswordConfirm"));
    if (!ok) return;
    try {
      const res = await api.removePassword(session.sessionId);
      setSession((s) => (s ? { ...s, isPasswordProtected: res.is_password_protected } : s));
      setStatusMessage(t("editor.hooks.docProps.removePasswordSuccess"));
    } catch (err) {
      setStatusMessage(t("editor.hooks.docProps.removePasswordFailed", { error: err.message }));
    }
  }

  return {
    docPropsOpen,
    docProps,
    docPropsLoading,
    docPropsError,
    addPasswordOpen,
    addPasswordError,
    addPasswordSubmitting,
    addPasswordPdfa,
    handleOpenDocProps,
    handleCloseDocProps,
    handleOpenAddPassword,
    handleCloseAddPassword,
    handleAddPasswordSubmit,
    handleRemovePassword,
  };
}
