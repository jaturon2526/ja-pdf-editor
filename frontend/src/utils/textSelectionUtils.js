// textSelectionUtils — คำนวณว่าตอนผู้ใช้ "ลากเลือก" พื้นที่ด้วยเมาส์ (เครื่องมือไฮไลท์/โน้ต) ครอบคำไหน
// ในหน้าเอกสารบ้าง แล้ว snap เป็นกรอบรวมทีละบรรทัด (ไม่ใช่กรอบดิบตามพิกัดที่ลากเป๊ะๆ) ให้ผลลัพธ์เหมือน
// การ "เลือกข้อความ" ใน PDF reader ทั่วไป (ดู backend: annotation_service.get_words คืน line_key มาให้)

function isWordSelected(w, d) {
  // กรองเบื้องต้น ถ้าไม่แตะกันเลยข้ามเลย
  if (w.x1 < d.x0 || w.x0 > d.x1 || w.y1 < d.y0 || w.y0 > d.y1) return false;
  
  const overlapX = Math.max(0, Math.min(w.x1, d.x1) - Math.max(w.x0, d.x0));
  const overlapY = Math.max(0, Math.min(w.y1, d.y1) - Math.max(w.y0, d.y0));
  
  const wWidth = w.x1 - w.x0;
  const wHeight = w.y1 - w.y0;
  
  // ป้องกันการลากแล้วไปเกี่ยวขอบของบรรทัดบน/ล่าง หรือคำข้างเคียง
  // 1. แกน Y: ต้องทับซ้อนจุดกึ่งกลาง หรือทับซ้อนอย่างน้อย 30% ของความสูงคำ
  const centerY = (w.y0 + w.y1) / 2;
  const validY = (centerY >= d.y0 && centerY <= d.y1) || (overlapY / wHeight > 0.3);
  
  // 2. แกน X: ต้องทับซ้อนจุดกึ่งกลาง หรือทับซ้อนอย่างน้อย 20% ของความกว้างคำ
  const centerX = (w.x0 + w.x1) / 2;
  const validX = (centerX >= d.x0 && centerX <= d.x1) || (overlapX / wWidth > 0.2);
  
  return validY && validX;
}

// words: [{rect:{x0,y0,x1,y1}, text, line_key}], dragRect: {x0,y0,x1,y1} (หน่วย point ของ PDF)
// คืนกรอบ (rect) หนึ่งอันต่อหนึ่งบรรทัดที่มีคำโดนลากเลือกอย่างน้อยหนึ่งคำ เรียงจากบนลงล่าง
export function computeSelectedLineRects(words, dragRect) {
  const groups = new Map();
  for (const w of words) {
    if (!isWordSelected(w.rect, dragRect)) continue;
    const list = groups.get(w.line_key) || [];
    list.push(w.rect);
    groups.set(w.line_key, list);
  }
  const rects = [];
  for (const list of groups.values()) {
    rects.push({
      x0: Math.min(...list.map((r) => r.x0)),
      y0: Math.min(...list.map((r) => r.y0)),
      x1: Math.max(...list.map((r) => r.x1)),
      y1: Math.max(...list.map((r) => r.y1)),
    });
  }
  rects.sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
  return rects;
}

// กรอบรวมของหลาย rect (ใช้หา "จุดยึด" ของโน้ตจากข้อความที่เลือกได้หลายบรรทัด)
export function unionRects(rects) {
  if (rects.length === 0) return null;
  return {
    x0: Math.min(...rects.map((r) => r.x0)),
    y0: Math.min(...rects.map((r) => r.y0)),
    x1: Math.max(...rects.map((r) => r.x1)),
    y1: Math.max(...rects.map((r) => r.y1)),
  };
}

// สระบน/สระล่าง/วรรณยุกต์/การันต์ของไทย — อักขระ "ไม่มีความกว้าง" ที่วาดซ้อนบนพยัญชนะตัวก่อนหน้า
// (ั ิ ี ึ ื ุ ู ฺ ็ ่ ้ ๊ ๋ ์ ํ ๎) ส่วน ำ (U+0E33) กับสระหน้า (เ แ โ ใ ไ) มีความกว้างของตัวเอง นับเป็นฐาน
const THAI_COMBINING = /^[\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]$/;

// รวมอักขระในบรรทัดเป็นกลุ่ม (cluster) = ฐาน 1 ตัว + เครื่องหมายที่ติดตามมา โดยยึดลำดับที่ backend ส่งมา
// (backend จัดลำดับสระ-วรรณยุกต์ให้ถูกแล้วใน thai_text.normalize_page_dict)
//
// ทำไมต้องรวมก่อนเรียง: เดิมเรียงทีละอักขระด้วย x0 แต่เครื่องหมายบน/ล่างมี x0 อยู่ที่ "ขอบขวา" ของพยัญชนะ
// ซึ่งเท่ากับหรือเลย x0 ของพยัญชนะตัวถัดไปเมื่อกรอบซ้อนกัน (พบบ่อยในชั้นข้อความ OCR ที่ถูกบีบแนวนอน
// ให้พอดีกรอบคำ) → "ผู้อำนวยการสำนัก" กลายเป็น "ผอู้ ำนวยการสำนกั"
function groupClusters(chars) {
  const clusters = [];
  for (const ch of chars) {
    const last = clusters[clusters.length - 1];
    if (last && THAI_COMBINING.test(ch.text)) {
      last.text += ch.text;
      last.x1 = Math.max(last.x1, ch.rect.x1);
      last.y0 = Math.min(last.y0, ch.rect.y0);
      last.y1 = Math.max(last.y1, ch.rect.y1);
      continue;
    }
    clusters.push({
      text: ch.text,
      x0: ch.rect.x0,
      x1: ch.rect.x1,
      y0: ch.rect.y0,
      y1: ch.rect.y1,
      // ความสูงของฐาน (ไม่รวมเครื่องหมายบน/ล่าง) ใช้คำนวณเกณฑ์ช่องว่าง
      h: ch.rect.y1 - ch.rect.y0,
    });
  }
  return clusters;
}

// คืนข้อความทั้งหมดที่ถูกลากคลุม เรียงตามบรรทัดและตำแหน่ง
// words: อักขระทีละตัวจาก /annotation/.../words (ชื่อเดิมยังเป็น "words" แต่ backend ส่งมาทีละอักขระ)
export function extractSelectedText(words, dragRect) {
  const groups = new Map();
  for (const w of words) {
    if (!isWordSelected(w.rect, dragRect)) continue;
    const list = groups.get(w.line_key) || [];
    list.push(w);
    groups.set(w.line_key, list);
  }

  if (groups.size === 0) return null;

  // เรียงบรรทัดจากบนลงล่าง
  const lines = Array.from(groups.values()).sort((a, b) => a[0].rect.y0 - b[0].rect.y0);

  const textLines = lines.map((lineChars) => {
    // รวมเป็นกลุ่มตามลำดับเดิมก่อน แล้วค่อยเรียงซ้ายไปขวาด้วย x0 ของฐาน (sort ของ JS เป็น stable —
    // กลุ่มที่ x0 เท่ากันคงลำดับจาก backend)
    const clusters = groupClusters(lineChars);
    clusters.sort((a, b) => a.x0 - b.x0);

    let lineStr = "";
    for (let i = 0; i < clusters.length; i++) {
      const cur = clusters[i];
      lineStr += cur.text;
      if (i < clusters.length - 1) {
        const next = clusters[i + 1];
        const gap = next.x0 - cur.x1;

        // กฎการเติมเว้นวรรค (backend ไม่ส่งอักขระช่องว่างมา จึงอนุมานจากระยะห่างระหว่างกลุ่ม):
        // 1. ถ้าช่องว่างกว้างกว่า max(2 pt, 20% ของความสูงตัวอักษร) ให้เติม space
        // 2. ถ้าเป็นรอยต่อระหว่าง อังกฤษ <-> ไทย ให้เติม space เสมอ (ถ้ามันไม่เกยกันแบบน่าเกลียด gap > -1)
        const isEngToThai = /[a-zA-Z0-9]$/.test(cur.text) && /^[\u0E00-\u0E7F]/.test(next.text);
        const isThaiToEng = /[\u0E00-\u0E7F]$/.test(cur.text) && /^[a-zA-Z0-9]/.test(next.text);

        if (gap > Math.max(2.0, cur.h * 0.2) || ((isEngToThai || isThaiToEng) && gap > -1)) {
          lineStr += " ";
        }
      }
    }

    // ข้อความไทย (PUA ฟอนต์รุ่นเก่า, สระอำแตก/หาย/วงกลมวาดเป็นเส้น, ลำดับสระ-วรรณยุกต์) ถูกจัดรูปที่ backend แล้ว
    // (backend/app/services/thai_text.py ผ่าน /annotation/.../words) — เดิมมีรายการแก้คำตายตัวตรงนี้
    // ซึ่งทำคำที่ถูกให้ผิด (คานาดา→คำนำดา, ทาสี→ทำสี) จึงเอาออก

    return lineStr.replace(/ +/g, " ").trim();
  });

  return textLines.join("\n");
}
