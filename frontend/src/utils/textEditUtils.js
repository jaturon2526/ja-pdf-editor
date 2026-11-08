// ฟังก์ชันช่วยแปลงค่าสี/font เดิมจาก PDF (int/ชื่อ font ของ PyMuPDF) เป็นค่าที่ UI ใช้ได้ตรงๆ
// แยกมาจาก component เพื่อให้ App.jsx (ตอนสร้าง draft ให้แก้ไข) กับ PropertiesPanel
// (ตอนแสดงผล) ใช้ตรรกะเดียวกัน ไม่ต้อง sync กันเอง

export function colorIntToHex(colorInt) {
  const n = Number(colorInt) || 0;
  return `#${(n & 0xffffff).toString(16).padStart(6, "0")}`;
}

export function hexToRgb01(hex) {
  const n = parseInt(hex.replace("#", ""), 16) || 0;
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

// ทางกลับของ hexToRgb01 — ใช้ตอนอ่านสีปัจจุบันของ annotation ที่มีอยู่แล้วกลับมาจาก backend (RGB 0-1)
// มาเป็น hex ให้ UI (swatch/ตัวเลือกสี) แสดงผลตรงกับสีจริงที่บันทึกไว้ (ดู AnnotationBox.jsx)
export function rgb01ToHex(rgb) {
  if (!rgb || rgb.length < 3) return null;
  const toHex = (c) => Math.max(0, Math.min(255, Math.round(c * 255))).toString(16).padStart(2, "0");
  return `#${toHex(rgb[0])}${toHex(rgb[1])}${toHex(rgb[2])}`;
}

// ตัดอักขระที่ไม่ใช่ตัวอักษร/ตัวเลขออกให้เหลือแต่ตัวที่มีความหมายจริงๆ (ชื่อ font ในไฟล์ PDF มักมีสัญลักษณ์
// ปน เช่น "TH Sarabun New", "Helvetica-Bold", "ABCDEF+Kanit-Regular" ที่ PyMuPDF บางทีก็คง subset prefix
// แบบ "ABCDEF+" ไว้) แปลงเป็นตัวพิมพ์เล็กทั้งหมดก่อนเทียบ — ใช้ทั้งฝั่งชื่อ font เดิมจาก PDF และฝั่ง label/
// key ของ family ที่มีในระบบ ให้เทียบกันตรงๆ ได้ไม่ติดปัญหาช่องว่าง/ตัวพิมพ์ใหญ่เล็ก/เครื่องหมายต่างๆ
function _normalizeFontName(s) {
  return (s || "")
    .toLowerCase()
    .replace(/^[a-z]{6}\+/, "") // ตัด subset prefix แบบ "ABCDEF+" ทิ้ง (ถ้ามี)
    .replace(/[^a-z0-9฀-๿]/g, "");
}

// หา family ที่ "มีอยู่ในระบบ" (bundle มากับแอป/sync จาก Google Fonts/ผู้ใช้ติดตั้งเอง — ทุกตัวที่ได้จาก
// GET /edit/font-families) ที่ชื่อตรง/ใกล้เคียงกับชื่อ font เดิมของข้อความที่กำลังจะแก้ไข (ผู้ใช้แจ้งขอ:
// "ตรวจสอบฟอนต์ของข้อความที่กำลังแก้ไขว่าใช้ฟอนต์อะไร ถ้ามีในระบบให้ default font ที่พบตรงกับระบบ")
// ลำดับการเทียบ: ตรงเป๊ะก่อน (เช่น เคยติดตั้งฟอนต์ "Kanit" เองไว้ ชื่อในไฟล์ก็ "Kanit" พอดี) ถ้าไม่เจอค่อย
// ลองแบบ substring ทั้งสองทาง (เช่นเอกสารใช้ "TH Sarabun New" ซึ่งไม่ตรงเป๊ะกับ family "Sarabun" ที่ bundle
// มา แต่ "sarabun" เป็นส่วนหนึ่งของ "thsarabunnew" จึงถือว่าใกล้เคียงพอที่จะ default ให้)
export function guessMatchingFamily(originalFontName, fontFamilies) {
  const norm = _normalizeFontName(originalFontName);
  if (!norm || !(fontFamilies || []).length) return null;

  const exact = fontFamilies.find((f) => {
    const flabel = _normalizeFontName(f.label);
    const fkey = _normalizeFontName(f.key);
    return (flabel && flabel === norm) || (fkey && fkey === norm);
  });
  if (exact) return exact;

  // อาจมีหลาย family ที่ "ใกล้เคียง" พร้อมกัน (เช่นเอกสารใช้ฟอนต์ชื่อ "TH Sarabun New,Bold" ซึ่งมีคำว่า
  // "sarabun" ตรงกับทั้ง family "Sarabun" ที่ bundle มากับแอป และ family "TH Sarabun New" ที่ผู้ใช้เคย
  // ติดตั้งเอง) — เลือกตัวที่ชื่อ "ตรงกันยาวที่สุด" (เจาะจงที่สุด) เสมอ ไม่ใช่ตัวแรกที่เจอในลิสต์ กันฟอนต์
  // ที่ชื่อสั้น/เป็นแค่ส่วนหนึ่งของคำ ไปทับ family ที่ตรงกับชื่อเดิมของเอกสารมากกว่าจริงๆ โดยไม่ตั้งใจ
  let best = null;
  let bestLen = 0;
  for (const f of fontFamilies) {
    const flabel = _normalizeFontName(f.label);
    const fkey = _normalizeFontName(f.key);
    for (const candidate of [flabel, fkey]) {
      if (candidate && candidate.length >= 3 && (norm.includes(candidate) || candidate.includes(norm))) {
        const matchLen = Math.min(candidate.length, norm.length);
        if (matchLen > bestLen) {
          bestLen = matchLen;
          best = f;
        }
      }
    }
  }
  return best;
}

// เลือก fontKey เริ่มต้นให้ตอนเริ่มแก้ไขย่อหน้าหนึ่ง (ดูหมายเหตุ guessMatchingFamily ด้านบน) — ถ้าหา
// family ที่ตรง/ใกล้เคียงกับ font เดิมของเอกสารเจอ จะเลือกสไตล์ (ปกติ/ตัวหนา/ตัวเอียง/ตัวหนาเอียง) ให้
// ตรงกับที่ชื่อ font เดิมสื่อด้วย (เช่นชื่อเดิมมีคำว่า "Bold" ก็เลือกสไตล์ตัวหนาของ family นั้น ถ้า family
// นั้นไม่มีไฟล์สไตล์ตัวหนาจริงก็ fallback ไปตัวปกติของ family เดียวกัน) หา family ไม่เจอเลย fallback ไป
// พฤติกรรมเดิม (เดา sarabun/sarabun-bold จากคำว่า "bold" ในชื่อ เพราะเป็นฟอนต์ไทยที่ bundle มากับแอปเสมอ)
export function guessDefaultFontKey(originalFontName, fonts, fontFamilies) {
  const name = (originalFontName || "").toLowerCase();
  const wantsBold = name.includes("bold");
  const wantsItalic = name.includes("italic") || name.includes("oblique");

  const family = guessMatchingFamily(originalFontName, fontFamilies);
  if (family?.styles) {
    const styleOrder =
      wantsBold && wantsItalic
        ? ["bold_italic", "bold", "italic", "regular"]
        : wantsBold
        ? ["bold", "regular"]
        : wantsItalic
        ? ["italic", "regular"]
        : ["regular"];
    const matchedKey = styleOrder.map((s) => family.styles[s]).find(Boolean);
    if (matchedKey) return matchedKey;
  }

  const preferred = wantsBold ? "sarabun-bold" : "sarabun";
  if ((fonts || []).some((f) => f.key === preferred)) return preferred;
  return fonts?.[0]?.key || "sarabun";
}

// หาว่า flat fontname key (เช่น "sarabun-bold") มาจาก family ไหน ใช้สไตล์อะไร — ใช้ตอนเปิด properties
// panel แบบใหม่ (ผู้ใช้แจ้งขอเพิ่ม — เลือก family แล้วกดปุ่มสไตล์ Bold/Italic/Bold Italic แทน dropdown
// แบบ flat เดิม) fontFamilies มาจาก GET /edit/font-families (ดู app/services/fonts.py) คืน
// {familyKey, style} — ถ้าหา key ไม่เจอใน family ไหนเลย (เช่นเป็น "helv" fallback ตอน deploy ผิดพลาด)
// fallback ไปที่ family แรกที่มีในรายการ + สไตล์ regular กันปุ่มพัง
export function resolveFamilyAndStyle(fontKey, fontFamilies) {
  for (const fam of fontFamilies || []) {
    for (const style of ["regular", "bold", "italic", "bold_italic"]) {
      if (fam.styles && fam.styles[style] === fontKey) {
        return { familyKey: fam.key, style };
      }
    }
  }
  const fallback = (fontFamilies || [])[0];
  return { familyKey: fallback?.key || null, style: "regular" };
}

// ชื่อ CSS font-family ที่ไม่ชนกับฟอนต์อื่นในระบบ ไว้ผูกกับ @font-face ที่ App.jsx ประกาศจากไฟล์ font
// จริงของแต่ละ fontKey โดยตรง (ผ่าน GET /edit/fonts/{key}/file — ดู api.fontFileUrl) — เดิมพรีวิวตอน
// แก้ไขข้อความอ้างอิง font "Sarabun"/"Kanit" ที่โหลดจาก Google Fonts CDN ตรงๆ (ดู FONT_FAMILY_MAP เดิม)
// ซึ่งเป็นคนละไฟล์กับที่ backend bundle ไว้ใช้เรนเดอร์จริงผ่าน Pillow (ดู fonts.resolve_font_path) ทำให้
// metric ไม่ตรงกันเป๊ะ ผู้ใช้แจ้งบั๊ก: ขนาดฟอนต์ที่เห็นตอนแก้ไข/หลังกด "ตกลง" ใหญ่กว่าที่บันทึกจริงหลังกด
// "บันทึก" (backend เรนเดอร์จริงด้วยไฟล์ font ที่ถูกต้อง เห็นขนาดจริงที่เล็กกว่า) — ทางแก้: 1 fontKey ผูก
// กับ 1 ชื่อ family ที่โหลดจากไฟล์เดียวกันเป๊ะกับที่ backend ใช้จริงเสมอ ไม่ว่าจะเป็นฟอนต์ bundle มากับแอป,
// Google Fonts ที่ sync ไว้แล้ว, หรือฟอนต์ที่ผู้ใช้ติดตั้งเอง — ไม่ต้องพึ่งพา CDN ภายนอกที่อาจเป็นคนละ
// เวอร์ชัน/คนละไฟล์อีกต่อไป
export function cssFontFamilyName(key) {
  return `pdfedit-${(key || "sarabun").toLowerCase().replace(/[^a-z0-9-]/g, "-")}`;
}

// เผื่อ @font-face ของ key นั้นยังโหลดไม่เสร็จ (เพิ่ง mount/สลับย่อหน้า) — fallback ไปที่ตระกูล sans-serif
// ทั่วไปของเครื่อง ระหว่างรอ ไม่ใช่ font เปล่าไปเลย
export function fontFamilyForKey(key) {
  return `'${cssFontFamilyName(key)}', 'Sarabun', sans-serif`;
}

// เดิมเดา font-weight/font-style จากชื่อ key (มีคำว่า "bold"/"italic" ก็ตั้ง 700/italic ให้ CSS
// "สังเคราะห์" ตัวหนา/เอียงเอา) ใช้ตอนพรีวิวทุก style ยังชี้ font-family เดียวกัน (ผ่าน FONT_FAMILY_MAP
// เดิมด้านบน) ตอนนี้แต่ละ fontKey (รวมถึงแต่ละสไตล์ของ 1 family) ผูกกับ @font-face ของตัวเองที่โหลดจาก
// ไฟล์ font จริงที่เป็นตัวหนา/เอียงอยู่แล้วโดยตรง (ดู cssFontFamilyName ด้านบน) ไม่ต้องให้ browser สังเคราะห์
// ตัวหนา/เอียงซ้อนทับไฟล์ที่เป็นสไตล์นั้นอยู่แล้วอีก (จะดูหนา/เอียงเกินจริงกว่าของจริงที่ backend เรนเดอร์)
// — คืนค่าปกติเสมอ ปล่อยให้ไฟล์ font จริงที่โหลดมาเป็นตัวกำหนดหน้าตาเอง
export function fontWeightForKey() {
  return 400;
}

export function fontStyleForKey() {
  return "normal";
}
