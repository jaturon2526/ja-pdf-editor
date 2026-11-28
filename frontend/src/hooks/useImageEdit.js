// useImageEdit.js — จัดการการแก้ไขรูปภาพใน PDF (insert, replace, reposition)

import { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import { sampleBackgroundColor } from "../utils/bgSample.js";
import { genLocalId, loadImageDimensions, rectsEqual } from "../utils/imageUtils.js";

// ระยะขยายออกนอกกรอบก่อนสุ่มสีพื้นหลัง (ดูหมายเหตุเต็มใน utils/bgSample.js)
const IMAGE_BG_SAMPLE_MARGIN_PT = 6;

/**
 * จัดการ image editing workflow:
 * 0. แทรกรูปใหม่: เลือกไฟล์ (openImagePicker) หรือลากไฟล์มาวางในโหมดแก้ไขรูป → placeNewImage → draft
 * 1. โหลดรูปภาพของหน้าปัจจุบัน (เมื่ออยู่ editMode="image")
 * 2. เลือกรูป → สร้าง draft → ลาก/ย้าย/แทนที่
 * 3. กด "ตกลง" → ย้าย draft ไป pendingImageEdits (ยังไม่ยิง API)
 * 4. App.jsx เรียก handleApplyAllEdits → ยิง API จริงทีเดียว
 */
export function useImageEdit({
  session,
  currentPage,
  editMode,
  pageImgElRef,
  setStatusMessage,
}) {
  const { t } = useI18n();
  const imageInsertInputRef = useRef(null); // hidden input[type=file] สำหรับเลือกรูปใหม่ที่จะแทรก

  const [images, setImages] = useState([]);
  const [draftImageEdit, setDraftImageEdit] = useState(null);
  const [pendingImageEdits, setPendingImageEdits] = useState({});
  const [copiedImage, setCopiedImage] = useState(null); // { file, width, height, x0, y0 }

  // computed
  const imagePendingCount = Object.values(pendingImageEdits).reduce(
    (s, m) => s + Object.keys(m).length,
    0
  );
  const pendingImageEditsForPage = pendingImageEdits[currentPage] || {};
  const queuedDraftRef = useRef(null);
  // ค่าล่าสุดสำหรับ placeNewImage ที่รอโหลดขนาดรูป (async) — โหมดอาจเปลี่ยนระหว่างรอ
  const editModeRef = useRef(editMode);
  editModeRef.current = editMode;
  const draftRef = useRef(null);
  draftRef.current = draftImageEdit;

  // โหลดรูปภาพของหน้าปัจจุบันใหม่ทุกครั้งที่เปลี่ยนโหมด/หน้า/เอกสาร
  // ล้าง draft ตอนเปลี่ยนหน้าด้วย (ป้องกัน previewUrl ของหน้าเก่าค้าง)
  useEffect(() => {
    setDraftImageEdit((d) => {
      if (d?.previewUrl?.startsWith("blob:")) {
        // ตรวจว่า blob URL นี้เป็นของ pending entry ที่ยืนยันไปแล้วหรือไม่ก่อนเพิกถอน
        const committed = pendingImageEdits[currentPage]?.[d.key];
        if (!committed || committed.previewUrl !== d.previewUrl) {
          URL.revokeObjectURL(d.previewUrl);
        }
      }
      return null;
    });
    if (!session || editMode !== "image") {
      setImages([]);
      return;
    }
    // บาร์โค้ดที่สั่งแทรกตอนยังไม่อยู่โหมดแก้ไขรูป — วางหลังเปลี่ยนโหมดเสร็จ (ไม่งั้นถูกล้างด้วยบรรทัดบน)
    if (queuedDraftRef.current) {
      setDraftImageEdit(queuedDraftRef.current);
      queuedDraftRef.current = null;
    }
    let cancelled = false;
    api
      .getImages(session.sessionId, currentPage)
      .then((imgs) => {
        if (!cancelled) {
          const list = (imgs || []).map((im, idx) => ({
            ...im,
            id: im.id || `img-${im.xref}-${idx}`,
          }));
          setImages(list);
        }
      })
      .catch((err) => !cancelled && setStatusMessage(t("editor.hooks.imageEdit.loadFailed", { message: err.message })));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, currentPage, editMode]);

  function _sampleBgAt(rect, marginPt = 0) {
    const [w, h] = session?.pageSizes?.[currentPage] || [1, 1];
    return sampleBackgroundColor(pageImgElRef.current, w, h, rect, marginPt) || "#ffffff";
  }

  // ---------- แทรกรูปใหม่ ----------
  // เมนูแทรก › แทรกรูปภาพ / ปุ่ม "แทรกรูปภาพ": เปิดหน้าต่างเลือกไฟล์ทันที แล้ววางรูปกลางหน้า (ลากย้าย/ย่อขยายได้)
  // โหมดแก้ไขรูปภาพ: ลากไฟล์รูปมาวางบนหน้า → วางตรงจุดที่ปล่อย (placeNewImage ด้วย point)
  function openImagePicker() {
    if (!session) return;
    imageInsertInputRef.current?.click();
  }

  // วางรูปใหม่เป็น draft — point {xPt,yPt} = จุดกึ่งกลางรูป (ไม่ระบุ = กลางหน้า) · มี draft ค้างอยู่ → ยืนยันอันเดิมก่อน
  // ขนาดเริ่มต้น: ด้านยาว 200pt (ไม่เกิน 60% ของหน้า) ตามสัดส่วนรูปจริง · ไม่ให้ล้นขอบหน้า
  async function placeNewImage(file, point = null, customBox = null) {
    if (!file || !session) return;
    if (!/^image\//.test(file.type || "")) {
      setStatusMessage(t("editor.hooks.imageEdit.invalidImageFile"));
      return;
    }
    const [pw, ph] = session.pageSizes?.[currentPage] || [595, 842];
    const previewUrl = URL.createObjectURL(file);
    let width;
    let height;
    let x0;
    let y0;
    if (customBox && customBox.width > 0 && customBox.height > 0) {
      width = Math.min(customBox.width, pw);
      height = Math.min(customBox.height, ph);
      x0 = Math.min(Math.max(0, customBox.x0 ?? (pw - width) / 2), Math.max(0, pw - width));
      y0 = Math.min(Math.max(0, customBox.y0 ?? (ph - height) / 2), Math.max(0, ph - height));
    } else {
      const maxSide = Math.min(200, pw * 0.6, ph * 0.6);
      width = maxSide;
      height = maxSide;
      try {
        const dims = await loadImageDimensions(previewUrl);
        if (dims.width >= dims.height) height = Math.max(8, Math.round((dims.height / dims.width) * maxSide));
        else width = Math.max(8, Math.round((dims.width / dims.height) * maxSide));
      } catch {
        /* อ่านขนาดไม่ได้ — ใช้กล่องจัตุรัส */
      }
      const cx = point ? point.xPt : pw / 2;
      const cy = point ? point.yPt : ph / 2;
      x0 = Math.min(Math.max(0, cx - width / 2), Math.max(0, pw - width));
      y0 = Math.min(Math.max(0, cy - height / 2), Math.max(0, ph - height));
    }
    const draft = {
      key: genLocalId("img-new"),
      kind: "insert",
      xref: null,
      serverRect: null,
      rect: { x0, y0, x1: x0 + width, y1: y0 + height },
      file,
      previewUrl,
    };
    const previous = draftRef.current;
    if (previous && editModeRef.current === "image") {
      const { key, ...rest } = previous; // ยืนยันรูปที่กำลังแก้ค้างอยู่ก่อน ไม่ให้หาย
      setPendingImageEdits((prev) => ({ ...prev, [currentPage]: { ...(prev[currentPage] || {}), [key]: rest } }));
    }
    if (editModeRef.current === "image") setDraftImageEdit(draft);
    else queuedDraftRef.current = draft; // effect ด้านบนวางให้หลังเปลี่ยนเป็นโหมดแก้ไขรูป
    setStatusMessage(t("editor.hooks.imageEdit.dragToPlaceHint"));
  }

  // คัดลอกรูปภาพที่กำลังเลือกอยู่ไปยังคลิปบอร์ด (ทั้งในแอปและ System Clipboard ถ้ารองรับ)
  async function copySelectedImage() {
    const cur = draftRef.current;
    if (!cur || !session) return false;
    try {
      let blob = cur.file;
      if (!blob && cur.previewUrl) {
        const res = await fetch(cur.previewUrl);
        blob = await res.blob();
      }
      if (!blob) return false;
      const ext = (blob.type && blob.type.split("/")[1]) || "png";
      const file = new File([blob], `copied-image.${ext}`, { type: blob.type || "image/png" });
      const width = Math.max(12, cur.rect.x1 - cur.rect.x0);
      const height = Math.max(12, cur.rect.y1 - cur.rect.y0);
      setCopiedImage({ file, width, height, x0: cur.rect.x0, y0: cur.rect.y0 });

      if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined" && file.type === "image/png") {
        navigator.clipboard.write([new ClipboardItem({ "image/png": file })]).catch(() => {});
      }
      setStatusMessage(t("editor.hooks.imageEdit.copySuccess"));
      return true;
    } catch (err) {
      setStatusMessage(t("editor.hooks.imageEdit.copyFailed", { message: err.message }));
      return false;
    }
  }

  // วางรูปภาพจากคลิปบอร์ดระบบ (externalFile) หรือรูปที่เพิ่งกดคัดลอกไว้ในแอป (copiedImage)
  async function pasteImage(externalFile = null) {
    if (!session) return false;
    if (copiedImage && (!externalFile || externalFile.size === copiedImage.file.size)) {
      const nextX0 = copiedImage.x0 + 18;
      const nextY0 = copiedImage.y0 + 18;
      setCopiedImage((prev) => (prev ? { ...prev, x0: nextX0, y0: nextY0 } : prev));
      await placeNewImage(copiedImage.file, null, {
        width: copiedImage.width,
        height: copiedImage.height,
        x0: nextX0,
        y0: nextY0,
      });
      setStatusMessage(t("editor.hooks.imageEdit.pasteSuccess"));
      return true;
    }
    if (externalFile) {
      await placeNewImage(externalFile);
      return true;
    }
    return false;
  }

  // แทรกบาร์โค้ด (เมนูแทรก › บาร์โค้ด): วางกล่องกลางหน้าให้ลากย้าย/ย่อขยายได้เหมือนรูป — บันทึกจริงเป็นเวกเตอร์
  // (useApplyEdits ส่ง edit.barcode ไป /barcode) · widthPt/heightPt ตามสัดส่วนภาพตัวอย่าง
  function startBarcodeInsert({ spec, blob, widthPt, heightPt }) {
    if (!session) return;
    const [pw, ph] = session.pageSizes?.[currentPage] || [595, 842];
    const w = Math.min(widthPt, pw * 0.8);
    const h = (heightPt / widthPt) * w;
    const x0 = Math.max(0, (pw - w) / 2);
    const y0 = Math.max(0, (ph - h) / 2);
    const draft = {
      key: genLocalId("barcode"),
      kind: "insert",
      xref: null,
      serverRect: null,
      rect: { x0, y0, x1: x0 + w, y1: y0 + h },
      file: null,
      barcode: spec,
      previewUrl: URL.createObjectURL(blob),
    };
    if (editMode === "image") setDraftImageEdit(draft);
    else queuedDraftRef.current = draft; // effect ด้านบนวางให้หลังเปลี่ยนเป็นโหมดแก้ไขรูป
  }

  // เลือกรูปที่ \"ยังไม่เคย\" มีการแก้ไขค้างอยู่ — เปิด draft ใหม่ พรีวิวด้วยรูปจริงจาก backend
  // bgColor: สุ่มสีพื้นหลังจริงรอบๆ ตำแหน่งเดิมของรูป ใช้ทาทึบตำแหน่งเดิมระหว่าง draft
  function handleSelectImage(img) {
    if (!session) return;
    const key = img.id || `img-${img.xref}`;
    setDraftImageEdit({
      key,
      kind: "existing",
      xref: img.xref,
      serverRect: { ...img.rect },
      rect: { ...img.rect },
      file: null,
      bgColor: _sampleBgAt(img.rect, IMAGE_BG_SAMPLE_MARGIN_PT),
      previewUrl: null, // โหลดผ่าน fetchWithAuth ด้านล่าง (endpoint ต้องแนบ token จึงใช้ URL ตรงๆ ไม่ได้)
    });
    api
      .fetchImageRawObjectUrl(session.sessionId, currentPage, img.xref)
      .then((url) => {
        setDraftImageEdit((d) => {
          if (d && d.key === key && d.kind === "existing" && !d.previewUrl) {
            return { ...d, previewUrl: url };
          }
          // draft ถูกปิด/เปลี่ยนไปแล้วก่อนรูปโหลดเสร็จ — คืนหน่วยความจำ (revoke ซ้ำได้ ไม่มีผลเสีย)
          URL.revokeObjectURL(url);
          return d;
        });
      })
      .catch((err) => setStatusMessage(t("editor.hooks.imageEdit.loadFailed", { message: err.message })));
  }

  // คลิกกล่อง pending ที่ "ตกลง" ไปแล้วแต่ยังไม่กด "บันทึกการแก้ไข" — กลับมาแก้ไขต่อ
  function handleResumeImageEdit(key) {
    const existing = pendingImageEditsForPage[key];
    if (!existing) return;
    setDraftImageEdit({ key, ...existing });
  }

  // กด "แทนที่รูปภาพ" ใน ImageEditBox — เปลี่ยนแค่เนื้อรูปใน draft (ยังไม่ยิง API)
  function handleImageReplaceFile(file) {
    if (!file) return;
    setDraftImageEdit((d) => {
      if (!d) return d;
      if (d.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(d.previewUrl);
      return { ...d, file, barcode: null, previewUrl: URL.createObjectURL(file) }; // แทนที่ด้วยรูป = ไม่ใช่บาร์โค้ดแล้ว
    });
  }

  // กด "ตกลง" ใน ImageEditBox — ย้าย draft ไป pendingImageEdits (ยังไม่ยิง API)
  function handleCommitImageEdit() {
    if (!draftImageEdit) return;
    const { key, ...rest } = draftImageEdit;
    setPendingImageEdits((prev) => ({
      ...prev,
      [currentPage]: { ...(prev[currentPage] || {}), [key]: rest },
    }));
    setDraftImageEdit(null);
    setStatusMessage(t("editor.hooks.imageEdit.commitSuccess"));
  }

  // ยกเลิก draft ปัจจุบัน — เพิกถอน blob URL ถ้าเป็น URL ที่สร้างเองและไม่ได้ถูก commit ไปแล้ว
  function handleCancelImageEdit() {
    if (draftImageEdit?.previewUrl?.startsWith("blob:")) {
      const committed = pendingImageEditsForPage[draftImageEdit.key];
      if (!committed || committed.previewUrl !== draftImageEdit.previewUrl) {
        URL.revokeObjectURL(draftImageEdit.previewUrl);
      }
    }
    setDraftImageEdit(null);
  }

  function handleDeleteImageEdit() {
    if (!draftImageEdit) return;
    if (draftImageEdit.kind === "new") {
      handleCancelImageEdit();
      return;
    }
    const { key, ...rest } = draftImageEdit;
    setPendingImageEdits((prev) => ({
      ...prev,
      [currentPage]: {
        ...(prev[currentPage] || {}),
        [key]: {
          ...rest,
          deleted: true,
        },
      },
    }));
    setDraftImageEdit(null);
  }

  // ยกเลิกการแก้ไขที่อยู่ในสถานะ pending (เช่นกดยกเลิกการลบ)
  function handleRestoreImageEdit(key) {
    setPendingImageEdits((prev) => {
      const pageEdits = { ...(prev[currentPage] || {}) };
      const edit = pageEdits[key];
      if (edit && edit.previewUrl && edit.previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(edit.previewUrl);
      }
      delete pageEdits[key];
      return { ...prev, [currentPage]: pageEdits };
    });
  }

  // รีเซ็ต draft + pending (ใช้ตอน undo/redo/เปลี่ยนเอกสาร)
  // หมายเหตุ: ไม่เพิกถอน blob URL ของ pending — ให้ App.jsx เรียก revokeAllPendingImageBlobUrls ก่อน reset
  function reset() {
    setDraftImageEdit(null);
    setPendingImageEdits({});
  }

  // ย้อนรายการแก้ไขรูปภาพล่าสุดที่ยังไม่กด "ยืนยัน" (ไม่ล้างรูปอื่นที่วางไว้แล้ว)
  function undoLastPending() {
    if (draftImageEdit) {
      handleCancelImageEdit();
      return true;
    }
    const curKeys = Object.keys(pendingImageEdits[currentPage] || {});
    if (curKeys.length > 0) {
      handleRestoreImageEdit(curKeys.at(-1));
      return true;
    }
    const pagesWithEdits = Object.keys(pendingImageEdits).filter((p) => Object.keys(pendingImageEdits[p] || {}).length > 0);
    if (pagesWithEdits.length === 0) return false;
    const targetP = pagesWithEdits.at(-1);
    const lastKey = Object.keys(pendingImageEdits[targetP]).at(-1);
    setPendingImageEdits((prev) => {
      const pageMap = { ...(prev[targetP] || {}) };
      const edit = pageMap[lastKey];
      if (edit?.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(edit.previewUrl);
      delete pageMap[lastKey];
      return { ...prev, [targetP]: pageMap };
    });
    return true;
  }

  return {
    // state
    images,
    setImages,
    draftImageEdit,
    setDraftImageEdit,
    pendingImageEdits,
    setPendingImageEdits,
    // refs
    imageInsertInputRef,
    // computed
    imagePendingCount,
    pendingImageEditsForPage,
    // handlers
    openImagePicker,
    placeNewImage,
    copySelectedImage,
    pasteImage,
    copiedImage,
    startBarcodeInsert,
    handleSelectImage,
    handleResumeImageEdit,
    handleImageReplaceFile,
    handleCommitImageEdit,
    handleCancelImageEdit,
    handleDeleteImageEdit,
    handleRestoreImageEdit,
    undoLastPending,
    // cross-hook
    reset,
    // utilities (used by handleApplyAllEdits in App.jsx)
    rectsEqual,
  };
}
