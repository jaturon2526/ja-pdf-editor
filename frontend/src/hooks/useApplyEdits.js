// "บันทึกการแก้ไข" — ส่งการแก้ข้อความ/รูปภาพที่ค้างอยู่ทุกหน้าไป server ทีละจุด (แยกมาจาก Editor.jsx)
// ถ้าผิดพลาดกลางทาง จุดที่ยังไม่ได้บันทึกจะยังค้างอยู่ให้กดบันทึกใหม่ได้
import * as api from "../api.js";
import { hexToRgb01 } from "../utils/textEditUtils.js";

// รวม draft ที่กำลังแก้อยู่เข้า pending ของหน้าปัจจุบัน
function mergeDraft(pending, page, key, value) {
  return { ...pending, [page]: { ...(pending[page] || {}), [key]: value } };
}

function flatten(edits, keyName) {
  const tasks = [];
  for (const [pageStr, map] of Object.entries(edits)) {
    for (const [key, edit] of Object.entries(map)) {
      tasks.push({ pageNumber: Number(pageStr), [keyName]: key, edit });
    }
  }
  return tasks;
}

const countEdits = (edits) => Object.values(edits).reduce((s, m) => s + Object.keys(m).length, 0);

function removeDone(remaining, page, key) {
  delete remaining[page][key];
  if (Object.keys(remaining[page]).length === 0) delete remaining[page];
}

export function useApplyEdits({
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
}) {
  const pendingEditCount =
    textEditHook.textPendingCount +
    imageEditHook.imagePendingCount +
    (redactHook.pendingRedactions ? redactHook.pendingRedactions.length : 0);

  function markChanged() {
    setCanUndo(true);
    setCanRedo(false);
  }

  async function applyAllPages() {
    if (!session) return;
    if (editMode === "redact") {
      await redactHook.applyRedactionsAllPages();
      markChanged();
    }
  }

  async function sendImageEdit(pageNumber, edit) {
    if (edit.kind === "insert") {
      if (edit.barcode) {
        // บาร์โค้ด: ส่งสเปกไปให้ backend วาดเป็นเวกเตอร์ (ภาพในกล่องเป็นแค่ตัวอย่าง)
        await api.insertBarcode(session.sessionId, pageNumber, edit.rect, edit.barcode);
      } else {
        await api.insertImage(session.sessionId, pageNumber, edit.rect, edit.file);
      }
      return;
    }
    if (edit.file) {
      await api.replaceImage(session.sessionId, pageNumber, edit.xref, edit.file);
    }
    if (!imageEditHook.rectsEqual(edit.serverRect, edit.rect)) {
      await api.repositionImage(session.sessionId, pageNumber, edit.xref, edit.serverRect, edit.rect);
    }
  }

  async function refreshAfterApply(touchedPages, remainingCount) {
    if (remainingCount === 0) {
      // บันทึกครบทุกจุด — ออกจากโหมดแก้ไขกลับเป็นอ่านอย่างเดียว
      setActiveTool(null);
    }
    if (touchedPages.has(currentPage)) {
      try {
        await sessionHook.refreshCurrentPage();
        if (remainingCount > 0) {
          // ยังมีจุดที่เหลือ (บันทึกไม่ครบ) — อยู่โหมดแก้ไขต่อ
          if (editMode === "text") {
            textEditHook.setTextBlocks(await api.getTextBlocks(session.sessionId, currentPage));
          }
          if (editMode === "image") {
            imageEditHook.setImages(await api.getImages(session.sessionId, currentPage));
          }
        }
      } catch (err) {
        setStatusMessage(`รีเฟรชหน้าปัจจุบันไม่สำเร็จ: ${err.message}`);
      }
    }
    if (touchedPages.size > 0) {
      // ล้าง thumbnail ของหน้าที่แก้ไขไป ให้โหลดใหม่
      sessionHook.setThumbnails((prev) => {
        const next = { ...prev };
        touchedPages.forEach((p) => delete next[p]);
        return next;
      });
    }
  }

  async function applyAllEdits() {
    if (!session) return;

    if (editMode === "redact") {
      await redactHook.applyRedactions();
      markChanged();
      return;
    }

    // auto-commit draft ที่กำลังแก้อยู่ก่อน (ป้องกันการแก้ไขล่าสุดหาย)
    let textEdits = textEditHook.pendingEdits;
    if (textEditHook.draftEdit) {
      const { blockId, ...rest } = textEditHook.draftEdit;
      textEdits = mergeDraft(textEdits, currentPage, blockId, rest);
      textEditHook.setPendingEdits(textEdits);
      textEditHook.setDraftEdit(null);
    }
    let imageEdits = imageEditHook.pendingImageEdits;
    if (imageEditHook.draftImageEdit) {
      const { key, ...rest } = imageEditHook.draftImageEdit;
      imageEdits = mergeDraft(imageEdits, currentPage, key, rest);
      imageEditHook.setPendingImageEdits(imageEdits);
      imageEditHook.setDraftImageEdit(null);
    }

    const textTasks = flatten(textEdits, "blockId");
    const imageTasks = flatten(imageEdits, "key");
    if (textTasks.length === 0 && imageTasks.length === 0) return;

    textEditHook.setApplyingEdits(true);
    textEditHook.setTextEditError(null);

    // คัดลอก remaining แยกต่างหาก — ถ้า error กลางทาง รายการที่เหลือจะไม่หายไป
    const remainingText = JSON.parse(JSON.stringify(textEdits));
    const remainingImages = Object.fromEntries(
      Object.entries(imageEdits).map(([page, map]) => [page, { ...map }])
    );
    const touchedPages = new Set();
    const blobUrlsToRevoke = [];
    let succeededCount = 0;

    try {
      for (const { pageNumber, blockId, edit } of textTasks) {
        await api.editText(session.sessionId, {
          page_number: pageNumber,
          rect: edit.rect,
          new_text: edit.text,
          fontname: edit.fontKey,
          fontsize: edit.fontSize,
          color: hexToRgb01(edit.colorHex),
          align: edit.align || "left",
          valign: edit.valign || "top",
          underline: edit.underline || false,
          block_id: blockId,
          previous_rect: edit.serverRect,
        });
        succeededCount += 1;
        touchedPages.add(pageNumber);
        removeDone(remainingText, pageNumber, blockId);
      }

      for (const { pageNumber, key, edit } of imageTasks) {
        if (edit.deleted) {
          // รูปเดิมที่ถูกลบ → เรียก API ลบ; รูปที่แทรกใหม่แล้วลบทิ้ง → ไม่ต้องส่งอะไร
          if (edit.kind !== "insert") {
            await api.deleteImage(session.sessionId, pageNumber, edit.xref, edit.serverRect);
            touchedPages.add(pageNumber);
          }
          succeededCount += 1;
          continue; // เหมือนเดิม: ไม่ลบออกจาก remaining (ถูกล้างทั้งหมดเมื่อบันทึกครบ)
        }
        await sendImageEdit(pageNumber, edit);
        succeededCount += 1;
        touchedPages.add(pageNumber);
        if (edit.previewUrl?.startsWith("blob:")) blobUrlsToRevoke.push(edit.previewUrl);
        removeDone(remainingImages, pageNumber, key);
      }

      textEditHook.setPendingEdits({});
      imageEditHook.setPendingImageEdits({});
      setStatusMessage(`บันทึกการแก้ไขทั้งหมดสำเร็จ (${succeededCount} จุด)`);
    } catch (err) {
      textEditHook.setPendingEdits(remainingText);
      imageEditHook.setPendingImageEdits(remainingImages);
      setStatusMessage(
        `บันทึกสำเร็จ ${succeededCount} จุด แต่มีจุดที่ผิดพลาด: ${err.message} (จุดที่เหลือยังไม่หายไป กดบันทึกใหม่ได้)`
      );
    } finally {
      textEditHook.setApplyingEdits(false);
      blobUrlsToRevoke.forEach((u) => URL.revokeObjectURL(u));
      if (succeededCount > 0) markChanged();
      await refreshAfterApply(touchedPages, countEdits(remainingText) + countEdits(remainingImages));
    }
  }

  // บันทึก/ดาวน์โหลด/พิมพ์ — ถ้ามีการแก้ไขค้างอยู่ให้บันทึกก่อนเสมอ
  async function withPendingApplied(fn) {
    if (pendingEditCount > 0) await applyAllEdits();
    return fn();
  }

  return { pendingEditCount, applyAllEdits, applyAllPages, withPendingApplied };
}
