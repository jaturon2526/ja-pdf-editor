import { describe, expect, it } from "vitest";
import { validatePassword } from "../utils/password.js";
import { colorIntToHex, hexToRgb01, rgb01ToHex } from "../utils/textEditUtils.js";
import { computeSelectedLineRects, extractSelectedText, unionRects } from "../utils/textSelectionUtils.js";
import OCR_CHARS from "./fixtures/ocr_thai_chars.json";
import { rectsEqual } from "../utils/imageUtils.js";

const word = (text, x0, y0, x1, y1, line_key) => ({ text, rect: { x0, y0, x1, y1 }, line_key });
const WORDS = [
  word("Hello", 10, 10, 50, 20, "a"),
  word("World", 55, 10, 100, 20, "a"),
  word("Second", 10, 30, 60, 40, "b"),
];

describe("validatePassword", () => {
  it("requires length, upper, lower and digit", () => {
    expect(validatePassword("Ab1")).toMatch(/8/);
    expect(validatePassword("abcdefg1")).toMatch(/ใหญ่/);
    expect(validatePassword("ABCDEFG1")).toMatch(/เล็ก/);
    expect(validatePassword("Abcdefgh")).toMatch(/ตัวเลข/);
    expect(validatePassword("Abcdefg1")).toBeNull();
  });
});

describe("color helpers", () => {
  it("round-trips hex <-> rgb01", () => {
    expect(colorIntToHex(0xff8000)).toBe("#ff8000");
    expect(hexToRgb01("#ff0000")).toEqual([1, 0, 0]);
    expect(rgb01ToHex(hexToRgb01("#12ab9f"))).toBe("#12ab9f");
    expect(rgb01ToHex(null)).toBeNull();
  });
});

describe("text selection", () => {
  it("snaps selection to one rect per line", () => {
    const rects = computeSelectedLineRects(WORDS, { x0: 0, y0: 0, x1: 200, y1: 50 });
    expect(rects).toEqual([
      { x0: 10, y0: 10, x1: 100, y1: 20 },
      { x0: 10, y0: 30, x1: 60, y1: 40 },
    ]);
  });

  it("ignores words that are barely touched", () => {
    expect(computeSelectedLineRects(WORDS, { x0: 0, y0: 19.5, x1: 200, y1: 29 })).toEqual([]);
  });

  it("extracts selected text line by line", () => {
    const text = extractSelectedText(WORDS, { x0: 0, y0: 0, x1: 200, y1: 50 });
    expect(text).toContain("Hello");
    expect(text).toContain("Second");
    expect(extractSelectedText(WORDS, { x0: 500, y0: 500, x1: 600, y1: 600 })).toBeNull();
  });

  it("unions rects", () => {
    expect(unionRects([])).toBeNull();
    expect(unionRects([{ x0: 1, y0: 2, x1: 3, y1: 4 }, { x0: 0, y0: 5, x1: 2, y1: 9 }])).toEqual({ x0: 0, y0: 2, x1: 3, y1: 9 });
  });
});

describe("rectsEqual", () => {
  it("compares within epsilon", () => {
    expect(rectsEqual({ x0: 0, y0: 0, x1: 1, y1: 1 }, { x0: 0.2, y0: 0, x1: 1, y1: 1 })).toBe(true);
    expect(rectsEqual({ x0: 0, y0: 0, x1: 1, y1: 1 }, { x0: 2, y0: 0, x1: 1, y1: 1 })).toBe(false);
  });
});

import { clampToViewport } from "../utils/viewport.js";

describe("clampToViewport", () => {
  it("keeps menus inside the screen", () => {
    expect(clampToViewport({ left: 100, top: 100, width: 200, height: 300 }, 1400, 800)).toEqual({ left: 100, top: 100 });
    expect(clampToViewport({ left: 1300, top: 700, width: 200, height: 300 }, 1400, 800)).toEqual({ left: 1192, top: 492 });
    expect(clampToViewport({ left: 10, top: 10, width: 2000, height: 2000 }, 1400, 800)).toEqual({ left: 8, top: 8 });
  });
});

import { formatBytes } from "../utils/format.js";

describe("formatBytes", () => {
  it("formats sizes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(11.2 * 1024 * 1024)).toBe("11.2 MB");
  });
});

describe("extractSelectedText ภาษาไทย", () => {
  const w = (text, x0, line = "0-0") => ({ text, line_key: line, rect: { x0, y0: 0, x1: x0 + 5, y1: 10 } });
  it("ไม่แก้คำที่ถูกอยู่แล้ว (เดิมมีรายการแก้คำตายตัว: ทาสี→ทำสี, คานาดา→คำนำดา)", () => {
    const words = [..."ทาสีคานาดา"].map((c, i) => w(c, i * 5));
    expect(extractSelectedText(words, { x0: -1, y0: -1, x1: 100, y1: 20 })).toBe("ทาสีคานาดา");
  });
});

describe("extractSelectedText — สระบน/ล่าง/วรรณยุกต์ที่กรอบซ้อนกับตัวถัดไป", () => {
  // จำลองชั้นข้อความ OCR ที่ถูกบีบแนวนอน: เครื่องหมายบน/ล่าง (กว้าง 0) มี x0 = ขอบขวาของพยัญชนะ
  // ซึ่งเลย x0 ของพยัญชนะตัวถัดไปเพราะกรอบซ้อนกัน — เดิมได้ "ผอู้" แทน "ผู้"
  const c = (text, x0, x1) => ({ text, line_key: "0-0", rect: { x0, y0: 0, x1, y1: 12 } });
  const ALL = { x0: -1, y0: -1, x1: 500, y1: 200 };

  it("ผู้อำนวยการ — ู ้ ติดกับ ผ ไม่ไปต่อท้าย อ", () => {
    const chars = [
      c("ผ", 0, 6), c("ู", 5.5, 5.5), c("้", 5.5, 5.5),
      c("อ", 5, 11), c("ำ", 10.8, 16), c("น", 16, 22), c("ว", 22, 27),
      c("ย", 27, 33), c("ก", 33, 39), c("า", 39, 44), c("ร", 44, 49),
    ];
    expect(extractSelectedText(chars, ALL)).toBe("ผู้อำนวยการ");
  });

  it("สำนัก + คำถัดไป — ไม่สลับ ั กับ ก และไม่เติมช่องว่างผิดที่", () => {
    const chars = [
      c("ส", 0, 6), c("ำ", 5.8, 11), c("น", 11, 17), c("ั", 17.2, 17.2), c("ก", 17, 23),
      c("เ", 23.5, 27), c("ง", 27, 33), c("ิ", 33.1, 33.1), c("น", 33, 39),
    ];
    expect(extractSelectedText(chars, ALL)).toBe("สำนักเงิน");
  });

  it("ช่องว่างจริงระหว่างคำยังคงอยู่ (วัดจากขอบขวาของกลุ่ม)", () => {
    const chars = [c("ด", 0, 6), c("ี", 6, 6), c("ม", 12, 18), c("า", 18, 22)];
    expect(extractSelectedText(chars, ALL)).toBe("ดี มา");
  });

  it("ข้อมูลจริงจากชั้นข้อความ OCR (tesseract + Sarabun ล่องหน)", () => {
    const text = extractSelectedText(OCR_CHARS, ALL);
    expect(text.split("\n")[0]).toBe("ผู้อำนวยการสำนักเงินสมทบ");
    // เดิมได้ "ปฏบิ ัตหิ นา้" — ส่วน "ที" ที่ขาดไม้เอกเป็นผลอ่านของ OCR เอง (เฟส 5b) ไม่ใช่การเรียงลำดับ
    expect(text.split("\n")[1]).toContain("ปฏิบัติหน้า");
  });
});

