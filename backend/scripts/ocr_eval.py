"""วัดความแม่นของ OCR ภาษาไทย (Tesseract) — ภาพทดสอบสังเคราะห์ + ภาพสแกนจริง (ถ้ามี) แล้ววัด CER

ใช้ (จาก backend/):
    python -m scripts.ocr_eval                       # ภาพสังเคราะห์ (สุ่มแบบกำหนด seed — ผลซ้ำได้)
    python -m scripts.ocr_eval --real ../test_ocr    # + ภาพจริง: x.png/x.jpg/x.pdf คู่กับ x.txt (ข้อความที่ถูกต้อง)
    python -m scripts.ocr_eval --samples 120 --show 5

ภาพสังเคราะห์จำลองเส้นทางจริงของแอป: ข้อความไทย shape ด้วย fpdf2 (HarfBuzz) หลายฟอนต์/ขนาด → แปลงเป็นภาพที่
ความละเอียดต้นทางต่าง ๆ (สแกน 150–300 dpi) → เติมความเสื่อม (เบลอ/noise/JPEG/เอียง/พื้นเทา) → ฝังเป็นรูปใน PDF
→ อ่านด้วยฟังก์ชันเดียวกับแอป (ocr.ocr_region) ที่ render รูปจาก PDF ที่ OCR_DPI

ตัวชี้วัด:
- CER: ระยะแก้ไข (Levenshtein) ระดับอักขระ ÷ ความยาวข้อความที่ถูก โดยไม่นับช่องว่าง (ภาษาไทยไม่เว้นวรรคระหว่างคำ
  ช่องว่างที่ OCR แทรก/ตกหล่นวัดแยกใน CER+sp) — ยิ่งต่ำยิ่งดี
- บรรทัดถูกทั้งบรรทัด (ไม่นับช่องว่าง) และ "คำถูก": สัดส่วนคำ (ตัดคำ newmm จากข้อความที่ถูก) ที่พบในผล OCR
- เส้นจุดไข่ปลา (....) ไม่นับทั้งฝั่งข้อความที่ถูกและผล OCR

ผลวัดเฟส 5b (180 ภาพ, tesseract 5.3 + tessdata tha 4.1 ของ Debian/Ubuntu, OMP_THREAD_LIMIT=1):
                         seed 1 (ใช้ปรับ)                       seed 7 (ไม่เคยใช้ปรับ)
                         CER    คำถูก  บรรทัดถูก  วินาที/ภาพ      CER    คำถูก  บรรทัดถูก
  layer เดิม (psm 6)     5.9%   89.9%  47.1%      0.62           5.8%   90.5%  46.2%
  layer ใหม่ (ocr_thai)  1.3%   96.5%  73.0%      0.77           1.5%   96.0%  69.6%
  text  เดิม (psm 6)     7.5%   90.3%  52.2%      0.50           6.4%   90.8%  51.9%
  text  ใหม่ (ocr_thai)  1.3%   96.6%  76.9%      0.72           1.4%   96.3%  73.6%
ภาพสแกนเต็มหน้า (32 บรรทัด): CER 2.3% → 0.5% เวลา ~3.3 → ~4.8 วินาที/หน้า
2026-10-27 รวม OCR ทุกจุดให้ใช้ชุดเดียวกัน (อ่านซ้ำบรรทัดไทยที่ถูกอ่านเป็นอังกฤษอยู่ใน ocr_thai.recognize แล้ว):
  --mode upload (อัปโหลดรูป/สแกนเอกสาร) seed 1/7: CER 7.1%/6.1% คำถูก 89.5%/89.9% → CER 1.5%/1.4% คำถูก 96.5%/96.1%
  (เดิม OSD ทายภาพข้อความไทยสั้น ๆ เป็น Latin แล้วอ่านด้วยโมเดลอังกฤษทั้งภาพ + ตัวกรองจุดไข่ปลาตัดตัวเลข "๕๐๐", "00001")
  --mode layer เท่าเดิม (CER 1.3%/1.5% → 1.5%/1.4%)
2026-10-27 เลขไทยอ่านด้วยการเทียบรูปร่าง (app/services/thai_digits.py) — Tesseract tha อ่านเลขไทยถูกทั้งชุดแค่ ~16%:
  --mode layer seed 1/7: CER 1.5%/1.4% → 1.0%/0.7% · คำถูก 96.5%/96.1% → 98.0%/98.3% · บรรทัดถูก 73%/70% → 81%/82%
  วันที่เลขไทย (วัน เดือน พ.ศ.) อ่านถูกทั้งชุด ~50% → ~90% (ฟอนต์ที่ไม่มีในแม่แบบ Loma/FreeSerif: 60% → 72%)
 tessdata_best (int) ของ tha ได้ผลเท่ากัน · --psm 3/4 แย่กว่า 6 · ภาษา "tha" อย่างเดียวทั้งบรรทัดแย่กว่า tha+eng
"""
from __future__ import annotations

import argparse
import io
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import thai_text  # noqa: E402
from app.services.pdf_service import ocr  # noqa: E402

FONTS_DIR = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"
# (ชื่อ, ไฟล์, ขนาดที่ใช้บ่อยในเอกสาร pt)
FONTS = [
    ("Sarabun", "Sarabun-Regular.ttf", (11, 14, 16)),
    ("Sarabun-Bold", "Sarabun-Bold.ttf", (14, 16)),
    ("Kanit", "Kanit-Regular.ttf", (11, 14)),
    ("NotoSansThai", "google_cache/noto-sans-thai.ttf", (10, 12, 14)),
]

# ข้อความแบบเอกสารราชการ/ธุรกิจ (สมมติ ไม่มีข้อมูลส่วนบุคคลจริง) — มีสระบน/ล่าง วรรณยุกต์ ตัวเลขไทย/อารบิก อังกฤษปน
LINES = [
    "ผู้อำนวยการสำนักเงินสมทบ",
    "ปฏิบัติราชการแทนเลขาธิการสำนักงานประกันสังคม",
    "หนังสือรับรองการเป็นผู้ประกันตน",
    "ขอรับรองว่า นางสาวตัวอย่าง ทดสอบระบบ",
    "เป็นผู้ประกันตนตามมาตรา ๓๙ แห่งพระราชบัญญัติประกันสังคม",
    "ออกให้ ณ วันที่ ๑๕ ตุลาคม พ.ศ. ๒๕๖๙",
    "ใบส่งสินค้า / ใบแจ้งหนี้ เลขที่ INV-2026/0142",
    "รวมเป็นเงินทั้งสิ้น 12,345.50 บาท (หนึ่งหมื่นสองพันสามร้อยสี่สิบห้าบาทห้าสิบสตางค์)",
    "ภาษีมูลค่าเพิ่ม 7% ชำระภายใน 30 วัน",
    "การไฟฟ้าส่วนภูมิภาค สำนักงานใหญ่ ถนนงามวงศ์วาน",
    "ค่าไฟฟ้าประจำเดือนกันยายน หน่วยที่ใช้ 245 หน่วย",
    "กรุณาชำระเงินภายในวันที่กำหนด มิฉะนั้นจะถูกงดจ่ายไฟฟ้า",
    "หนังสือทวงถามให้ชำระหนี้ ครั้งที่ ๒",
    "ตามที่ท่านได้ทำสัญญากู้ยืมเงินไว้กับบริษัท",
    "บัดนี้ครบกำหนดชำระแล้ว แต่ท่านยังมิได้ชำระหนี้แต่อย่างใด",
    "จึงขอให้ท่านติดต่อชำระภายในเจ็ดวันนับแต่ได้รับหนังสือฉบับนี้",
    "ลงชื่อ ................................ ผู้รับมอบอำนาจ",
    "โทรศัพท์ 0 2123 4567 ต่อ 1234 โทรสาร 0 2123 4568",
    "ที่อยู่ 99/9 หมู่ 4 ตำบลบางพูด อำเภอปากเกร็ด จังหวัดนนทบุรี 11120",
    "เลขประจำตัวผู้เสียภาษี 0105555123456 สาขาที่ 00001",
    "ระบบใบกำกับภาษีอิเล็กทรอนิกส์ (e-Tax Invoice)",
    "มาตรฐานข้อมูลสำหรับการจัดทำเอกสารอิเล็กทรอนิกส์",
    "กิจกรรมนี้จัดขึ้นเพื่อส่งเสริมการเรียนรู้ด้านปัญญาประดิษฐ์",
    "ผู้เข้าร่วมจะได้รับเกียรติบัตรหลังจบกิจกรรม",
    "ทั้งนี้ ตั้งแต่บัดนี้เป็นต้นไป",
    "ประกาศ ณ วันที่ ๒๑ กันยายน พ.ศ. ๒๕๖๙",
    "เรียน ผู้จัดการฝ่ายทรัพยากรบุคคล",
    "สิ่งที่ส่งมาด้วย สำเนาบัตรประจำตัวประชาชน จำนวน ๑ ฉบับ",
    "ด้วยข้าพเจ้ามีความประสงค์จะขอลาพักผ่อนประจำปี",
    "จึงเรียนมาเพื่อโปรดพิจารณาอนุมัติ",
    "ขอแสดงความนับถือ",
    "ฝ่ายบริการลูกค้า โทร. 1129 ตลอด 24 ชั่วโมง",
    "เงื่อนไขการรับประกันสินค้า ๑ ปี นับจากวันที่ซื้อ",
    "น้ำหนักสุทธิ ๕๐๐ กรัม ผลิตในประเทศไทย",
    "คณะกรรมการพิจารณาแล้วเห็นสมควรอนุญาต",
    "ผู้ใหญ่บ้านหมู่ที่ ๗ ตำบลศรีสุนทร",
]


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_WS = re.compile(r"\s+")


def _nospace(s: str) -> str:
    return _WS.sub("", s)


def _onespace(s: str) -> str:
    return "\n".join(_WS.sub(" ", ln).strip() for ln in s.splitlines() if ln.strip())


@dataclass
class Sample:
    name: str
    truth: str
    pdf: bytes            # หน้า PDF หนึ่งหน้าที่มีรูปข้อความหนึ่งรูป
    rect: fitz.Rect       # ตำแหน่งรูปบนหน้า
    tags: dict


def _render_block(lines: list[str], font_file: Path, size: float, dpi: int, bold_faux=False) -> Image.Image:
    from fpdf import FPDF

    line_h = size * 1.7
    width = 40 + max(len(ln) for ln in lines) * size * 0.62
    height = 20 + line_h * len(lines)
    pdf = FPDF(unit="pt", format=(width, height))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0)
    pdf.add_page()
    pdf.add_font("F", "", str(font_file))
    pdf.set_font("F", size=size)
    pdf.set_text_shaping(True, script="thai", language="tha")
    for i, ln in enumerate(lines):
        pdf.set_xy(20, 10 + i * line_h)
        pdf.cell(width - 40, line_h, ln)
    src = fitz.open(stream=bytes(pdf.output()))
    pix = src[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _degrade(img: Image.Image, kind: str, rng: random.Random) -> Image.Image:
    if kind == "clean":
        return img
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.1)))
    if kind == "noise":
        import numpy as np

        a = np.asarray(img, dtype=np.float32)
        a = a * rng.uniform(0.75, 0.9) + rng.uniform(15, 40)          # พื้นเทา คอนทราสต์ต่ำ (ถ่ายเอกสาร)
        a += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(8, 16), a.shape)
        return Image.fromarray(a.clip(0, 255).astype("uint8"))
    if kind == "jpeg":
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.choice((25, 35, 50)))
        return Image.open(io.BytesIO(buf.getvalue())).convert("L")
    if kind == "table":
        # ข้อความในตาราง/กรอบ: เส้นขอบรอบบล็อก + เส้นคั่นระหว่างบรรทัด + เส้นแนวตั้งคั่นคอลัมน์ (แบบฟอร์มราชการ)
        from PIL import ImageDraw

        img = img.copy()
        d = ImageDraw.Draw(img)
        w, h = img.size
        lw = max(1, round(h / 300))
        d.rectangle((4, 4, w - 5, h - 5), outline=0, width=lw)
        d.line((int(w * 0.012), 4, int(w * 0.012), h - 5), fill=0, width=lw)
        return img
    if kind == "skew":
        return img.rotate(rng.choice((-1, 1)) * rng.uniform(0.6, 1.8), resample=Image.BICUBIC,
                          expand=True, fillcolor=255)
    raise ValueError(kind)


DEGRADE = ("clean", "blur", "noise", "jpeg", "skew", "table")
SOURCE_DPI = (150, 200, 300)


def synthetic_samples(n: int, seed: int = 1) -> list[Sample]:
    rng = random.Random(seed)
    out = []
    for k in range(n):
        name, file, sizes = FONTS[k % len(FONTS)]
        size = rng.choice(sizes)
        dpi = SOURCE_DPI[(k // len(FONTS)) % len(SOURCE_DPI)]
        kind = DEGRADE[(k // (len(FONTS) * len(SOURCE_DPI))) % len(DEGRADE)]
        lines = rng.sample(LINES, rng.randint(2, 4))
        img = _degrade(_render_block(lines, FONTS_DIR / file, size, dpi), kind, rng)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        # ฝังรูปขนาดจริงตาม dpi ต้นทาง (เหมือนภาพสแกนในเอกสาร)
        w_pt, h_pt = img.width * 72 / dpi, img.height * 72 / dpi
        doc = fitz.open()
        page = doc.new_page(width=w_pt + 72, height=h_pt + 72)
        rect = fitz.Rect(36, 36, 36 + w_pt, 36 + h_pt)
        page.insert_image(rect, stream=buf.getvalue())
        out.append(Sample(f"{name}-{size}pt-{dpi}dpi-{kind}-{k}", "\n".join(lines), doc.tobytes(), rect,
                          {"font": name, "dpi": dpi, "degrade": kind}))
    return out


def real_samples(folder: Path) -> list[Sample]:
    out = []
    for txt in sorted(folder.glob("*.txt")):
        truth = txt.read_text("utf-8").strip()
        for ext in (".png", ".jpg", ".jpeg", ".pdf"):
            f = txt.with_suffix(ext)
            if not f.exists():
                continue
            if ext == ".pdf":
                doc = fitz.open(f)
                page = doc[0]
                rect = page.rect
                single = fitz.open()
                single.insert_pdf(doc, from_page=0, to_page=0)
                data = single.tobytes()
            else:
                img = Image.open(f)
                dpi = (img.info.get("dpi") or (200, 200))[0] or 200
                w_pt, h_pt = img.width * 72 / dpi, img.height * 72 / dpi
                doc = fitz.open()
                page = doc.new_page(width=w_pt, height=h_pt)
                rect = page.rect
                page.insert_image(rect, filename=str(f))
                data = doc.tobytes()
            out.append(Sample(f.name, truth, data, rect, {"font": "real", "dpi": 0, "degrade": "real"}))
            break
    return out


_DOTS = re.compile(r"\.{4,}")


def score(truth: str, got: str) -> dict:
    # เส้นจุดไข่ปลา ("ลงชื่อ ......") เป็นเส้นประดับ ไม่ใช่ข้อความ — ไม่นับทั้งสองฝั่ง
    truth, got = _DOTS.sub(" ", truth), _DOTS.sub(" ", got)
    t, g = _nospace(truth), _nospace(got)
    t1, g1 = _onespace(truth), _onespace(got)
    words = [w for ln in truth.splitlines() for w in thai_text.tokenize(ln, keep_whitespace=False) if w.strip()]
    gn = _nospace(got)
    found = sum(1 for w in words if _nospace(w) in gn)
    tl = [_nospace(x) for x in truth.splitlines() if x.strip()]
    gl = {_nospace(x) for x in got.splitlines()}
    return {
        "cer": _levenshtein(t, g) / max(1, len(t)),
        "cer_sp": _levenshtein(t1, g1) / max(1, len(t1)),
        "lines_ok": sum(1 for x in tl if x in gl) / max(1, len(tl)),
        "words_ok": found / max(1, len(words)),
    }


def _run_one(args) -> dict:
    s, mode = args
    doc = fitz.open(stream=s.pdf)
    t0 = time.perf_counter()
    got = ocr.ocr_region(doc[0], s.rect, mode=mode)
    return {"got": got, "sec": time.perf_counter() - t0, **score(s.truth, got)}


def evaluate(samples: list[Sample], mode: str, jobs: int = 0) -> list[dict]:
    """jobs: จำนวน process (0 = เท่าจำนวน CPU) — tesseract แต่ละตัวจำกัด 1 thread (OMP_THREAD_LIMIT=1) ให้วัดเวลาเทียบกันได้"""
    import os
    from multiprocessing import Pool

    os.environ["OMP_THREAD_LIMIT"] = "1"
    with Pool(jobs or os.cpu_count()) as pool:
        results = pool.map(_run_one, [(s, mode) for s in samples])
    return [{"sample": s, **r} for s, r in zip(samples, results)]


def _summary_line(label: str, rs: list[dict]) -> str:
    m = lambda k: statistics.mean(r[k] for r in rs)  # noqa: E731
    return (f"  {label:24} n={len(rs):3}  CER {m('cer') * 100:5.1f}%  CER+sp {m('cer_sp') * 100:5.1f}%  "
            f"คำถูก {m('words_ok') * 100:5.1f}%  บรรทัดถูก {m('lines_ok') * 100:5.1f}%  {m('sec'):.2f}s/ภาพ")


def summarize(rows: list[dict], by: tuple[str, ...] = ()) -> None:
    print(_summary_line("ทั้งหมด", rows))
    for key in by:
        groups: dict = {}
        for r in rows:
            groups.setdefault(str(r["sample"].tags[key]), []).append(r)
        for k in sorted(groups, key=lambda x: (len(x), x)):
            print(_summary_line(f"{key}={k}", groups[k]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--samples", type=int, default=180,
                    help="จำนวนภาพสังเคราะห์ (90 = ครบทุกชุดเงื่อนไข ฟอนต์ × dpi × ความเสื่อม; ค่าเริ่มต้น 180 = 2 รอบ)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--real", type=Path, help="โฟลเดอร์ภาพจริง x.png/x.jpg/x.pdf + x.txt")
    ap.add_argument("--mode", choices=("text", "layer", "upload"), default="layer",
                    help="text = ปุ่มคัดลอก/OCR · layer = ชั้นข้อความ OCR (เมนูอ่านข้อความในรูป) · upload = อัปโหลดรูปภาพ/สแกนเอกสาร")
    ap.add_argument("--show", type=int, default=0, help="แสดงผล N ภาพที่แย่ที่สุด")
    args = ap.parse_args(argv)

    samples = synthetic_samples(args.samples, args.seed)
    rows = evaluate(samples, args.mode)
    print(f"ภาพสังเคราะห์ ({args.mode}):")
    summarize(rows, ("degrade", "dpi", "font"))
    if args.real:
        real = evaluate(real_samples(args.real), args.mode)
        if real:
            print(f"ภาพจริง ({args.real}):")
            summarize(real)
            rows += real
    for r in sorted(rows, key=lambda r: -r["cer"])[: args.show]:
        print(f"\n--- {r['sample'].name}  CER {r['cer'] * 100:.1f}%\nถูก:\n{r['sample'].truth}\nOCR:\n{r['got']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
