// useSignature.js — จัดการ Electronic Sign และ Digital Sign

import { useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

/**
 * workflow ลายเซ็น:
 * 1. เปิด modal (Electronic / Digital)
 * 2. กด "ตกลง" ใน modal → สร้าง draftSignature (ยังไม่ยิง API)
 * 3. ลาก/ย้าย/ย่อ/ขยายกล่องบนหน้าเอกสาร
 * 4. กด "ตกลง" ในกล่อง → handleCommitSignature → ยิง API จริง
 */
export function useSignature({
  session,
  setSession,
  currentPage,
  setActiveTool,
  setStatusMessage,
  setCanUndo,
  setCanRedo,
  currentPageSizePt,
}) {
  const { t } = useI18n();
  const [signModalOpen, setSignModalOpen] = useState(null); // null | "electronic" | "digital"
  const [draftSignature, setDraftSignature] = useState(null);
  const [signSubmitting, setSignSubmitting] = useState(false);

  // กรอบเริ่มต้นตอนเปิดโหมดลากวาง — วางมุมล่างขวาของหน้า ขนาดสัดส่วนตามความกว้างหน้า
  // แก้บั๊ก: ถ้า pageSizes ยังไม่โหลด fallback เป็น A4 (595×842pt) กัน rect เล็กจนมองไม่เห็น
  function defaultSignatureRectPt() {
    let [w, h] = currentPageSizePt();
    if (!w || !h || w < 10 || h < 10) {
      [w, h] = [595, 842];
    }
    const boxW = Math.min(220, Math.max(120, w * 0.35));
    const boxH = boxW * 0.42;
    const x0 = Math.max(20, w - boxW - 40);
    const y0 = Math.max(20, h - boxH - 60);
    return { x0, y0, x1: x0 + boxW, y1: y0 + boxH };
  }

  function handleOpenElectronicSign() {
    if (!session) return;
    setSignModalOpen("electronic");
  }

  function handleOpenDigitalSign() {
    if (!session) return;
    setSignModalOpen("digital");
  }

  function handleCancelSignModal() {
    setSignModalOpen(null);
  }

  // กด "ตกลง" ใน ElectronicSignModal — ปิด modal แล้วเปิดกล่องลากวางตำแหน่ง
  function handleElectronicSignatureReady(imageBase64, previewDataUrl) {
    setSignModalOpen(null);
    setActiveTool(null);
    setDraftSignature({
      kind: "electronic",
      rect: defaultSignatureRectPt(),
      previewUrl: previewDataUrl,
      imageBase64,
    });
    setStatusMessage(t("editor.hooks.signature.electronicDragHint"));
  }

  // กด "ตกลง" ใน DigitalSignModal — ปิด modal แล้วเปิดกล่องลากวาง (ยังไม่เซ็นจริง)
  function handleDigitalSignatureReady(pfxFile, password, reason, location, contact, name, imageFile, certInfo) {
    setSignModalOpen(null);
    setActiveTool(null);
    setDraftSignature({
      kind: "digital",
      rect: defaultSignatureRectPt(),
      previewUrl: undefined,
      pfxFile,
      password,
      reason,
      location,
      contact,
      name,
      imageFile,
    });
    const who = certInfo?.common_name
      ? t("editor.hooks.signature.digitalCertPrefix", {
          commonName: certInfo.common_name,
          validTo: certInfo.valid_to,
        })
      : "";
    const warn = certInfo?.warnings?.length
      ? t("editor.hooks.signature.digitalWarnSuffix", { warnings: certInfo.warnings.join(" · ") })
      : "";
    setStatusMessage(t("editor.hooks.signature.digitalDragHint", { who, warn }));
  }

  function handleDraftSignatureRectChange(rect) {
    setDraftSignature((d) => (d ? { ...d, rect } : d));
  }

  function handleCancelSignature() {
    setDraftSignature(null);
  }

  // กด "ตกลง" ในกล่องลากวาง — ยิง API เซ็นจริง (ทั้ง Electronic และ Digital)
  // เซ็นเสร็จแล้วยังแก้ไข/เซ็นซ้อนต่อได้ (ไม่ล็อก) — push_history() ฝั่ง backend ตามปกติ
  async function handleCommitSignature(onAfterSign) {
    if (!draftSignature || !session) return;
    setSignSubmitting(true);
    try {
      let res;
      if (draftSignature.kind === "electronic") {
        res = await api.electronicSign(
          session.sessionId,
          currentPage,
          draftSignature.rect,
          draftSignature.imageBase64
        );
      } else {
        res = await api.digitalSign(
          session.sessionId,
          currentPage,
          draftSignature.rect,
          draftSignature.pfxFile,
          draftSignature.password,
          draftSignature.reason,
          draftSignature.location,
          draftSignature.contact,
          draftSignature.name,
          draftSignature.imageFile
        );
      }
      setSession((s) =>
        s ? { ...s, isSigned: res.is_signed, signatureType: res.signature_type } : s
      );
      setDraftSignature(null);
      setActiveTool(null);
      setCanUndo(true);
      setCanRedo(false);
      // ให้ App.jsx รีเฟรช thumbnail/หน้า/state หลังเซ็น
      if (onAfterSign) await onAfterSign(res, currentPage);
      setStatusMessage(
        res.signature_type === "digital"
          ? t("editor.hooks.signature.digitalSignSuccess", {
              signerName: res.signer_name || t("editor.hooks.signature.unknownSigner"),
            })
          : t("editor.hooks.signature.electronicSignSuccess")
      );
    } catch (err) {
      // เก็บกรอบไว้ ให้ลองใหม่หรือกดยกเลิกเอง (เดิมกรอบหาย ต้องสร้างลายเซ็น/เลือกใบรับรองใหม่ทั้งหมด)
      setStatusMessage(t("editor.hooks.signature.signFailed", { message: err.message }));
    } finally {
      setSignSubmitting(false);
    }
  }

  // รีเซ็ต draft (ใช้ตอน undo/redo/เปลี่ยนเอกสาร)
  function reset() {
    setDraftSignature(null);
    setSignModalOpen(null);
  }

  return {
    signModalOpen,
    setSignModalOpen,
    draftSignature,
    setDraftSignature,
    signSubmitting,
    handleOpenElectronicSign,
    handleOpenDigitalSign,
    handleCancelSignModal,
    handleElectronicSignatureReady,
    handleDigitalSignatureReady,
    handleDraftSignatureRectChange,
    handleCancelSignature,
    handleCommitSignature,
    defaultSignatureRectPt,
    reset,
  };
}
