// useImageEdit.js — จัดการการแก้ไขรูปภาพใน PDF (insert, replace, reposition)

import { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import { sampleBackgroundColor } from "../utils/bgSample.js";
import { genLocalId, loadImageDimensions, rectsEqual } from "../utils/imageUtils.js";

// ระยะขยายออกนอกกรอบก่อนสุ่มสีพื้นหลัง (ดูหมายเหตุเต็มใน utils/bgSample.js)
const IMAGE_BG_SAMPLE_MARGIN_PT = 6;

/**
 * จัดการ image editing workflow:
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
  const imageInsertInputRef = useRef(null); // hidden input[type=file] สำหรับเลือกรูปใหม่ที่จะแทรก
  const pendingImageInsertPointRef = useRef(null); // {xPt,yPt} จุดที่คลิกไว้ รอไฟล์ถูกเลือก

  const [images, setImages] = useState([]);
  const [draftImageEdit, setDraftImageEdit] = useState(null);
  const [pendingImageEdits, setPendingImageEdits] = useState({});

  // computed
  const imagePendingCount = Object.values(pendingImageEdits).reduce(
    (s, m) => s + Object.keys(m).length,
    0
  );
  const pendingImageEditsForPage = pendingImageEdits[currentPage] || {};
  const queuedDraftRef = useRef(null);

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
      .catch((err) => !cancelled && setStatusMessage(`โหลดรูปภาพไม่สำเร็จ: ${err.message}`));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, currentPage, editMode]);

  function _sampleBgAt(rect, marginPt = 0) {
    const [w, h] = session?.pageSizes?.[currentPage] || [1, 1];
    return sampleBackgroundColor(pageImgElRef.current, w, h, rect, marginPt) || "#ffffff";
  }

  // ---------- Insert Image — คลิกบน canvas ขณะใช้เครื่องมือ insert_image ----------
  // บันทึกจุดที่คลิกไว้ก่อน แล้วเปิด file dialog (รอไฟล์ถูกเลือกใน handleImageInsertFileChosen)
  function handleCanvasInsertClick(xPt, yPt, tool) {
    if (!session || tool !== "insert_image" || draftImageEdit) return;
    pendingImageInsertPointRef.current = { xPt, yPt };
    imageInsertInputRef.current?.click();
  }

  // รับไฟล์รูปใหม่ที่ผู้ใช้เลือกผ่าน hidden input — คำนวณขนาดกล่องเริ่มต้นตามสัดส่วนรูปจริง
  async function handleImageInsertFileChosen(file) {
    const point = pendingImageInsertPointRef.current;
    if (!file || !point) return;
    pendingImageInsertPointRef.current = null;
    const previewUrl = URL.createObjectURL(file);
    let width = 100;
    let height = 100;
    try {
      const dims = await loadImageDimensions(previewUrl);
      const MAX_PT = 200;
      if (dims.width > dims.height) {
        width = MAX_PT;
        height = Math.round((dims.height / dims.width) * MAX_PT);
      } else {
        height = MAX_PT;
        width = Math.round((dims.width / dims.height) * MAX_PT);
      }
    } catch {
      /* ใช้ขนาด fallback 100×100 */
    }
    setDraftImageEdit({
      key: genLocalId("img-new"),
      kind: "insert",
      xref: null,
      serverRect: null,
      rect: { x0: point.xPt, y0: point.yPt, x1: point.xPt + width, y1: point.yPt + height },
      file,
      previewUrl,
    });
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
      .catch((err) => setStatusMessage(`โหลดรูปภาพไม่สำเร็จ: ${err.message}`));
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
    setStatusMessage('ยืนยันรูปภาพนี้แล้ว — กด "บันทึกการแก้ไข" บน toolbar เมื่อแก้ไขครบทุกจุด');
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
    handleCanvasInsertClick,
    handleImageInsertFileChosen,
    startBarcodeInsert,
    handleSelectImage,
    handleResumeImageEdit,
    handleImageReplaceFile,
    handleCommitImageEdit,
    handleCancelImageEdit,
    handleDeleteImageEdit,
    handleRestoreImageEdit,
    // cross-hook
    reset,
    // utilities (used by handleApplyAllEdits in App.jsx)
    rectsEqual,
  };
}
