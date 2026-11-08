// เก็บหน้าที่สแกนไว้ใน IndexedDB ของเบราว์เซอร์ — แท็บถูกรีโหลด/ปิดไปกลางทาง (มือถือหน่วยความจำเต็ม) กลับมายังกู้ได้
// เก็บเฉพาะในเครื่องผู้ใช้ ลบเมื่อบันทึกสำเร็จหรือกดเริ่มใหม่ — ถ้า IndexedDB ใช้ไม่ได้ (โหมดส่วนตัว) ทำงานต่อได้แต่กู้ไม่ได้

const DB = "ja-scan";
const STORE = "pages";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  return await new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const result = fn(t.objectStore(STORE));
    t.oncomplete = () => { db.close(); resolve(result?.result ?? result); };
    t.onerror = () => { db.close(); reject(t.error); };
  });
}

/** หน้า: {id, order, source: Blob, corners, rotation, createdAt} */
export async function savePage(page) {
  try { await tx("readwrite", (s) => s.put(page)); } catch { /* กู้ไม่ได้ก็ใช้งานต่อได้ */ }
}

export async function deletePage(id) {
  try { await tx("readwrite", (s) => s.delete(id)); } catch { /* ignore */ }
}

export async function loadPages() {
  try {
    const all = await tx("readonly", (s) => s.getAll());
    return (all || []).sort((a, b) => a.order - b.order);
  } catch {
    return [];
  }
}

export async function clearPages() {
  try { await tx("readwrite", (s) => s.clear()); } catch { /* ignore */ }
}
