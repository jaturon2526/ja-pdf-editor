// imageUtils.js — utility functions ที่ใช้ร่วมกันระหว่าง hooks หลายตัว (แยกออกจาก App.jsx)

// id ท้องถิ่นชั่วคราว ใช้กับย่อหน้า/รูปภาพที่เพิ่งแทรกใหม่ (ยังไม่เคยยิง API)
export function genLocalId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// เปรียบเทียบสองกรอบว่าเท่ากันภายใน epsilon
export function rectsEqual(a, b, eps = 0.5) {
  if (!a || !b) return a === b;
  return (
    Math.abs(a.x0 - b.x0) < eps &&
    Math.abs(a.y0 - b.y0) < eps &&
    Math.abs(a.x1 - b.x1) < eps &&
    Math.abs(a.y1 - b.y1) < eps
  );
}

// โหลดขนาดจริง (naturalWidth/Height) ของไฟล์รูปจาก URL
export function loadImageDimensions(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = reject;
    img.src = url;
  });
}

// เพิกถอน blob URL ที่ค้างอยู่ทั้งหมดใน pendingImageEdits และ draftImageEdit
// ป้องกัน memory leak เมื่อปิดเอกสาร/เปิดใหม่/undo-redo
export function revokeAllPendingImageBlobUrls(pendingImageEditsObj, draftImageEditObj) {
  Object.values(pendingImageEditsObj || {}).forEach((pageMap) => {
    Object.values(pageMap).forEach((e) => {
      if (e.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(e.previewUrl);
    });
  });
  if (draftImageEditObj?.previewUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(draftImageEditObj.previewUrl);
  }
}
