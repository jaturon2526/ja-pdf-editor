// ฟังก์ชันล้วนสำหรับจัดการสถานะการกรอกแบบฟอร์ม PDF (AcroForm, v1.45.0)

export function initDraftValues(fields) {
  const map = {};
  for (const f of fields || []) {
    map[f.xref] = f.value;
  }
  return map;
}

/**
 * อัปเดตค่าฟิลด์ใน draft map — ถ้าเป็น radio และถูกเลือก (true) จะปิด radio ตัวอื่นที่มี name เดียวกันให้อัตโนมัติ
 */
export function applyDraftChange(prevValues, fields, targetField, nextValue) {
  const next = { ...prevValues, [targetField.xref]: nextValue };
  if (targetField.type === "radio" && nextValue === true) {
    for (const f of fields) {
      if (f.type === "radio" && f.name === targetField.name && f.xref !== targetField.xref) {
        next[f.xref] = false;
      }
    }
  }
  return next;
}

/**
 * คืนรายการ updates ([{ xref, page, value }]) เฉพาะฟิลด์ที่ค่าเปลี่ยนจากต้นฉบับและไม่ได้เป็น read_only
 */
export function collectDirtyUpdates(fields, draftValues) {
  const updates = [];
  for (const f of fields || []) {
    if (f.read_only) continue;
    const current = draftValues[f.xref];
    if (current !== undefined && current !== f.value) {
      updates.push({ xref: f.xref, page: f.page, value: current });
    }
  }
  return updates;
}
