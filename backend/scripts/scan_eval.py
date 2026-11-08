"""วัดผลการแปลงไฟล์สแกน → Word (app/services/scan_docx)

ใช้ (จาก backend/):
    python -m scripts.scan_eval                          # เอกสารสังเคราะห์ (สร้างเอง รู้ข้อความถูกต้อง)
    python -m scripts.scan_eval --corpus ../test_pdf_files --pages 2   # + หน้า PDF จริงที่ทำให้เป็นภาพสแกน
    python -m scripts.scan_eval --check                  # คืนค่า 1 ถ้าผลต่ำกว่าเกณฑ์ (ใช้ก่อน deploy)
    python -m scripts.scan_eval --keep /tmp/scan_eval    # เก็บไฟล์ภาพสแกน/Word ไว้เปิดดู

ขั้นตอนต่อหน้า: หน้า PDF ต้นฉบับ (มีข้อความจริง) → เรนเดอร์เป็นภาพ + ความเสื่อมแบบสแกน/ถ่ายรูป
(ขาวดำแบบเครื่องสแกน, เอียง+เบลอ, พื้นเทา+noise+JPEG) → PDF ภาพล้วนหนึ่งหน้า → convert_scan_to_docx → เทียบ

ตัวชี้วัด:
- CER: ระยะแก้ไขระดับอักขระ (ไม่นับช่องว่าง/จุดไข่ปลา) ÷ ความยาวข้อความที่ถูก — ประมาณด้วย difflib
- คำถูก: สัดส่วนคำ (ตัดคำจากข้อความที่ถูก) ที่พบในผลลัพธ์
- ตาราง: จำนวนตารางใน Word เทียบกับตารางในต้นฉบับ (fitz find_tables) · รูป: จำนวนรูปใน Word ≥ รูปในต้นฉบับ
- ไฟล์สแกนจริง (ไม่รู้ข้อความถูกต้อง — โฟลเดอร์ --real): รายงานสัดส่วนอักษรไทยที่เป็นคำในพจนานุกรม, ตาราง, รูป

ไฟล์ตัวอย่างจริงอาจมีข้อมูลส่วนบุคคล — ไม่ commit (test_pdf_files/ อยู่ใน .gitignore)
"""
from __future__ import annotations

import argparse
import difflib
import io
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import scan_docx, thai_text  # noqa: E402

FONTS = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"
DEGRADE = ("bw", "skew", "photo")

# เกณฑ์ --check (เอกสารสังเคราะห์ทั้งหมด) — ตั้งจากผลวัดจริง เผื่อความแกว่งเล็กน้อย
CHECK_MAX_CER = 0.06
CHECK_MIN_WORDS = 0.88
CHECK_MIN_TABLES = 0.8


# ---------------------------------------------------------------- เอกสารสังเคราะห์

PARAS = [
    "ตามที่ท่านได้ยื่นคำขอรับบริการสินเชื่อเพื่อที่อยู่อาศัยกับธนาคาร เมื่อวันที่ 15 กันยายน 2568 นั้น "
    "ธนาคารได้พิจารณาเอกสารประกอบคำขอของท่านเรียบร้อยแล้ว และขอแจ้งผลการพิจารณาให้ทราบดังต่อไปนี้",
    "ผู้กู้ต้องชำระค่างวดเป็นรายเดือน เดือนละ 12,500 บาท ภายในวันที่ 5 ของทุกเดือน โดยหักบัญชีเงินฝาก "
    "ออมทรัพย์อัตโนมัติ หากชำระล่าช้าจะมีค่าปรับตามอัตราที่ธนาคารประกาศกำหนด",
    "หากท่านมีข้อสงสัยประการใด กรุณาติดต่อเจ้าหน้าที่สินเชื่อ สาขาสำนักงานใหญ่ โทรศัพท์ 0 2123 4567 "
    "ในวันและเวลาทำการ หรือทางอีเมล loan@example.co.th",
]
TABLE = [
    ["ลำดับ", "รายการ", "จำนวน", "ราคา (บาท)"],
    ["1", "ค่าธรรมเนียมการจดจำนอง", "1", "2,000.00"],
    ["2", "ค่าประเมินราคาหลักประกัน", "1", "3,500.00"],
    ["3", "ค่าอากรแสตมป์", "1", "750.00"],
]
FORM = ["ชื่อ-นามสกุล", "ที่อยู่", "เบอร์โทรศัพท์"]


def _logo(path: Path) -> None:
    im = Image.new("L", (240, 240), 255)
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 230, 230), outline=0, width=14)
    d.polygon([(120, 40), (200, 190), (40, 190)], fill=0)
    d.ellipse((95, 120, 145, 170), fill=255)
    im.save(path)


def _barcode(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    w = 360
    im = Image.new("L", (w, 70), 255)
    d = ImageDraw.Draw(im)
    x = 10
    while x < w - 14:
        bw = rng.choice((2, 2, 4, 6))
        d.rectangle((x, 0, x + bw - 1, 69), fill=0)
        x += bw + rng.choice((2, 4, 4, 6))
    im.save(path)


def synthetic_doc(font: str, size: float, seed: int, workdir: Path) -> tuple[bytes, str, int]:
    """เอกสารหนึ่งหน้า: หัวจดหมาย+โลโก้, เลขที่/วันที่ชิดขวา, ย่อหน้า, ตาราง, แบบฟอร์มจุดไข่ปลา, ลงชื่อ, บาร์โค้ด
    คืน (pdf, ข้อความที่ถูกต้อง, จำนวนตาราง)"""
    from fpdf import FPDF

    logo, bar = workdir / "logo.png", workdir / f"bar{seed}.png"
    if not logo.exists():
        _logo(logo)
    _barcode(bar, seed)
    pdf = FPDF(unit="pt", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.add_font("F", "", str(FONTS / f"{font}-Regular.ttf"))
    pdf.add_font("F", "B", str(FONTS / f"{font}-Bold.ttf"))
    pdf.set_text_shaping(True, script="thai", language="tha")
    truth: list[str] = []
    lh = size * 1.55
    left, width = 64, 595 - 128

    def line(text, style="", align="L", x=left, w=width, h=lh):
        pdf.set_font("F", style, size)
        pdf.set_x(x)
        pdf.cell(w, h, text, align=align, new_x="LMARGIN", new_y="NEXT")
        truth.append(text)

    pdf.image(str(logo), x=left, y=40, w=54)
    pdf.set_xy(left + 64, 46)
    pdf.set_font("F", "B", size + 2)
    pdf.cell(width - 64, lh, "ธนาคารตัวอย่างเพื่อการทดสอบ จำกัด (มหาชน)", new_x="LMARGIN", new_y="NEXT")
    truth.append("ธนาคารตัวอย่างเพื่อการทดสอบ จำกัด (มหาชน)")
    pdf.set_x(left + 64)
    pdf.set_font("F", "", size - 2)
    pdf.cell(width - 64, lh, "สำนักงานใหญ่ 99 ถนนพหลโยธิน แขวงสามเสนใน เขตพญาไท กรุงเทพฯ 10400", new_x="LMARGIN", new_y="NEXT")
    truth.append("สำนักงานใหญ่ 99 ถนนพหลโยธิน แขวงสามเสนใน เขตพญาไท กรุงเทพฯ 10400")
    pdf.set_y(130)
    line(f"ที่ ธท {1000 + seed}/2568", align="L")
    line("วันที่ 20 ตุลาคม 2568", align="R")
    line("เรื่อง แจ้งผลการพิจารณาสินเชื่อ", "B")
    line("เรียน คุณสมชาย ใจดี")
    pdf.ln(4)
    pdf.set_font("F", "", size)
    for p in PARAS:
        pdf.set_x(left)
        pdf.multi_cell(width, lh, "        " + p, align="J", new_x="LMARGIN", new_y="NEXT")
        truth.append(p)
        pdf.ln(3)
    pdf.ln(4)
    widths = (50, 230, 70, 117)
    for r, row in enumerate(TABLE):
        pdf.set_x(left)
        for c, (cell, w) in enumerate(zip(row, widths)):
            pdf.set_font("F", "B" if r == 0 else "", size - 1)
            pdf.cell(w, lh + 4, cell, border=1, align="C" if c != 1 or r == 0 else "L")
        pdf.ln(lh + 4)
        truth.append(" ".join(row))
    pdf.ln(10)
    pdf.set_font("F", "", size)
    for label in FORM:
        pdf.set_x(left)
        pdf.cell(width, lh + 2, label + " " + "." * int((width - pdf.get_string_width(label + " ")) / pdf.get_string_width(".")),
                 new_x="LMARGIN", new_y="NEXT")
        truth.append(label)
    pdf.ln(18)
    line("ขอแสดงความนับถือ", align="C", x=300, w=230)
    pdf.ln(lh)
    line("(นางสาวสมหญิง รักงาน)", align="C", x=300, w=230)
    line("ผู้จัดการฝ่ายสินเชื่อ", align="C", x=300, w=230)
    pdf.image(str(bar), x=left, y=770, w=150)
    return bytes(pdf.output()), "\n".join(truth), 1


# ---------------------------------------------------------------- ทำให้เป็นภาพสแกน

def degrade(img: Image.Image, kind: str, rng: random.Random) -> Image.Image:
    if kind == "bw":         # เครื่องสแกน/แอปสแกนโหมดขาวดำ
        return img.point(lambda v: 255 if v > 165 else 0)
    if kind == "skew":       # วางเอียงเล็กน้อย + เบลอจากโฟกัส
        img = img.rotate(rng.choice((-1, 1)) * rng.uniform(0.5, 1.4), resample=Image.BICUBIC, fillcolor=255)
        return img.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 0.9)))
    if kind == "photo":      # ถ่ายรูป: พื้นเทาไม่สม่ำเสมอ + noise + JPEG
        import numpy as np

        a = np.asarray(img, dtype=np.float32)
        h, w = a.shape
        grad = np.linspace(rng.uniform(15, 35), rng.uniform(35, 60), w)[None, :]
        a = a * 0.82 + grad
        a += np.random.default_rng(rng.randrange(1 << 30)).normal(0, 7, a.shape)
        im = Image.fromarray(a.clip(0, 255).astype("uint8"))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=55)
        return Image.open(io.BytesIO(buf.getvalue())).convert("L")
    raise ValueError(kind)


def to_scan_pdf(page: fitz.Page, kind: str, rng: random.Random, dpi: int = 200) -> bytes:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    img = degrade(Image.frombytes("L", (pix.width, pix.height), pix.samples), kind, rng)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = fitz.open()
    p = out.new_page(width=page.rect.width, height=page.rect.height)
    p.insert_image(p.rect, stream=buf.getvalue())
    return out.tobytes()


# ---------------------------------------------------------------- วัด

_WS = re.compile(r"\s+")
_DOTS = re.compile(r"[.…]{3,}|_{3,}")


def _clean(s: str) -> str:
    return _WS.sub("", _DOTS.sub(" ", thai_text.normalize(s)))


def cer(truth: str, got: str) -> float:
    t, g = _clean(truth), _clean(got)
    sm = difflib.SequenceMatcher(None, t, g, autojunk=False)
    dist = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return dist / max(1, len(t))


def words_ok(truth: str, got: str) -> float:
    g = _clean(got)
    words = [w for ln in truth.splitlines() for w in thai_text.tokenize(_DOTS.sub(" ", ln), keep_whitespace=False)
             if w.strip() and not _DOTS.fullmatch(w)]
    return sum(1 for w in words if _clean(w) in g) / max(1, len(words))


def docx_stats(data: bytes) -> dict:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(data))
    texts = []
    body = doc.element.body
    for el in body.iter():
        if el.tag == qn("w:p"):
            texts.append("".join(t.text or "" for t in el.iter(qn("w:t"))))
    return {
        "text": "\n".join(texts),
        "tables": len(body.findall(qn("w:tbl"))),
        "pictures": len(list(body.iter(qn("pic:pic")))),
    }


@dataclass
class Sample:
    name: str
    pdf: bytes
    truth: str | None
    tables: int | None
    pictures: int | None


def evaluate(samples: list[Sample], keep: Path | None) -> list[dict]:
    rows = []
    for s in samples:
        t0 = time.time()
        try:
            data = scan_docx.convert_scan_to_docx(s.pdf)
        except Exception as e:  # pragma: no cover - รายงานแล้วไปต่อ
            rows.append({"name": s.name, "error": str(e)})
            continue
        st = docx_stats(data)
        r = {"name": s.name, "sec": time.time() - t0, "tables": st["tables"], "pictures": st["pictures"],
             "tables_truth": s.tables, "pictures_truth": s.pictures}
        if s.truth is not None:
            r["cer"] = cer(s.truth, st["text"])
            r["words"] = words_ok(s.truth, st["text"])
        else:
            r["coverage"] = thai_text.dictionary_coverage(st["text"])
        rows.append(r)
        if keep:
            keep.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.-]+", "_", s.name)
            (keep / f"{safe}.pdf").write_bytes(s.pdf)
            (keep / f"{safe}.docx").write_bytes(data)
    return rows


def synthetic_samples(seed: int, workdir: Path) -> list[Sample]:
    rng = random.Random(seed)
    out = []
    for k, (font, size) in enumerate((("Sarabun", 12), ("Sarabun", 16))):
        pdf, truth, tables = synthetic_doc(font, size, seed * 10 + k, workdir)
        page = fitz.open(stream=pdf)[0]
        for kind in DEGRADE:
            out.append(Sample(f"synthetic-{font}{size}-{kind}", to_scan_pdf(page, kind, rng), truth, tables, 2))
    return out


def corpus_samples(folder: Path, pages: int, seed: int) -> list[Sample]:
    from scripts.thai_eval import _page_texts

    rng = random.Random(seed)
    out = []
    for path in sorted(folder.glob("*.pdf")):
        try:
            doc = fitz.open(path)
        except Exception:
            continue
        if doc.needs_pass:
            continue
        if scan_docx.is_scanned_pdf(path.read_bytes()):
            continue
        for i in range(min(pages, doc.page_count)):
            page = doc[i]
            truth = _page_texts(page)[1]
            if len(_clean(truth)) < 80:
                continue
            try:
                tables = len(page.find_tables().tables)
            except Exception:
                tables = None
            kind = DEGRADE[(i + len(out)) % len(DEGRADE)]
            out.append(Sample(f"{path.stem[:28]}-p{i + 1}-{kind}", to_scan_pdf(page, kind, rng), truth, tables, None))
    return out


def real_samples(folder: Path) -> list[Sample]:
    out = []
    for path in sorted(folder.glob("*.pdf")):
        data = path.read_bytes()
        if scan_docx.is_scanned_pdf(data):
            out.append(Sample(f"REAL {path.stem[:30]}", data, None, None, None))
    return out


def summarize(rows: list[dict]) -> dict:
    print(f"{'sample':48} {'CER':>6} {'words':>6} {'tbl':>7} {'pic':>5} {'sec':>6}")
    for r in rows:
        if "error" in r:
            print(f"{r['name'][:48]:48} ERROR {r['error']}")
            continue
        tbl = f"{r['tables']}/{r['tables_truth']}" if r["tables_truth"] is not None else str(r["tables"])
        if "cer" in r:
            print(f"{r['name'][:48]:48} {r['cer']:6.1%} {r['words']:6.1%} {tbl:>7} {r['pictures']:>5} {r['sec']:6.1f}")
        else:
            print(f"{r['name'][:48]:48} {'cov':>6} {r['coverage']:6.1%} {tbl:>7} {r['pictures']:>5} {r['sec']:6.1f}")
    scored = [r for r in rows if "cer" in r]
    synth = [r for r in scored if r["name"].startswith("synthetic")]
    res = {}
    for label, group in (("synthetic", synth), ("all", scored)):
        if not group:
            continue
        tb = [r for r in group if r["tables_truth"]]
        res[label] = {
            "cer": statistics.mean(r["cer"] for r in group),
            "words": statistics.mean(r["words"] for r in group),
            "tables": (sum(1 for r in tb if r["tables"] >= r["tables_truth"]) / len(tb)) if tb else 1.0,
        }
        print(f"== {label}: CER {res[label]['cer']:.1%} · คำถูก {res[label]['words']:.1%} · "
              f"ตารางครบ {res[label]['tables']:.0%} ({len(group)} หน้า, {sum(r['sec'] for r in group):.0f} วินาที)")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, help="โฟลเดอร์ PDF ที่มีข้อความ (ทำเป็นภาพสแกนแล้ววัด)")
    ap.add_argument("--real", type=Path, help="โฟลเดอร์ไฟล์สแกนจริง (รายงานอย่างเดียว)")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--keep", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    import logging
    import tempfile

    logging.disable(logging.INFO)
    with tempfile.TemporaryDirectory() as d:
        samples = synthetic_samples(args.seed, Path(d))
    if args.corpus:
        samples += corpus_samples(args.corpus, args.pages, args.seed)
    if args.real:
        samples += real_samples(args.real)
    res = summarize(evaluate(samples, args.keep))
    if args.check:
        s = res.get("synthetic", {})
        fails = []
        if s.get("cer", 1) > CHECK_MAX_CER:
            fails.append(f"CER {s.get('cer', 1):.1%} > {CHECK_MAX_CER:.0%}")
        if s.get("words", 0) < CHECK_MIN_WORDS:
            fails.append(f"คำถูก {s.get('words', 0):.1%} < {CHECK_MIN_WORDS:.0%}")
        if s.get("tables", 0) < CHECK_MIN_TABLES:
            fails.append(f"ตารางครบ {s.get('tables', 0):.0%} < {CHECK_MIN_TABLES:.0%}")
        if fails:
            print("CHECK FAIL: " + " · ".join(fails))
            return 1
        print("CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
