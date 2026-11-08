"""วัดผลการแปลง PDF → Word (โหมดแก้ไขได้): รูปแบบตัวอักษรคงอยู่ไหม และข้อความไทยถูกต้องแค่ไหน

ใช้ (จาก backend/):
    python -m scripts.docx_eval ../test_pdf_files            # ตารางสรุปต่อไฟล์
    python -m scripts.docx_eval ../test_pdf_files --show 5   # ตัวอย่างย่อหน้าที่รูปแบบหาย

ขั้นตอนต่อไฟล์: pdf2docx แปลง (ผลดิบ) → ขั้นแก้คำไทยของแอป (_fix_thai_in_docx แบบไม่ใช้ AI) → เทียบกัน
- รูปแบบคงอยู่ (fmt): สัดส่วนอักขระในผลลัพธ์ที่มีรูปแบบ (w:rPr ทั้งชุด: หนา/เอียง/ขีดเส้นใต้/สี/ไฮไลต์/ขนาด/ฟอนต์)
  ตรงกับอักขระเดียวกันในผลดิบ — จับคู่อักขระด้วย difflib ต่อย่อหน้า
- ย่อหน้าหลายรูปแบบ (mixed): ย่อหน้าในผลดิบที่มี run รูปแบบต่างกันมากกว่า 1 แบบ → หลังแก้ยังต่างกันอยู่กี่ย่อหน้า
- issues: รูปแบบไทยที่ผิดแน่ ๆ (scripts.thai_eval) ในข้อความ Word หลังแก้ · coverage: สัดส่วนอักษรไทยที่อยู่ในคำในพจนานุกรม
- zwsp นอกไทย: zero-width space ที่ไม่ได้อยู่ระหว่างอักษร/ตัวเลขไทยสองตัว (ไม่ควรมี)

ไฟล์ตัวอย่างจริงอาจมีข้อมูลส่วนบุคคล — ไม่ commit (test_pdf_files/ อยู่ใน .gitignore)
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from lxml import etree  # noqa: E402

from app.services import thai_text  # noqa: E402
from scripts.thai_eval import _issues  # noqa: E402


def _rpr_key(run_el) -> str:
    rpr = run_el.find(qn("w:rPr"))
    if rpr is None:
        return ""
    # ค่าที่ขั้นปรับฟอนต์ของแอปเติมทีหลัง (cs/lang) ไม่นับ — วัดเฉพาะรูปแบบที่ผู้ใช้เห็น
    keep = [c for c in rpr if etree.QName(c).localname not in ("lang", "szCs", "bCs", "iCs", "rFonts")]
    fonts = rpr.find(qn("w:rFonts"))
    name = "" if fonts is None else (fonts.get(qn("w:ascii")) or fonts.get(qn("w:cs")) or "")
    return name + "|" + "".join(etree.tostring(c, encoding="unicode") for c in sorted(keep, key=lambda e: e.tag))


def paragraph_segments(document) -> list[list[tuple[str, str]]]:
    """ทุกย่อหน้า (รวมในตาราง ตามลำดับเอกสาร) → [(ข้อความของ run, รูปแบบ)]"""
    out = []
    for p in document.element.body.iter(qn("w:p")):
        segs = []
        for r in p.iter(qn("w:r")):
            t = "".join(x.text or "" for x in r.iter(qn("w:t")))
            if t:
                segs.append((t, _rpr_key(r)))
        out.append(segs)
    return out


def _chars_with_fmt(segs) -> tuple[str, list[str]]:
    text, fmts = [], []
    for t, f in segs:
        text.append(t)
        fmts.extend([f] * len(t))
    return "".join(text), fmts


_ZW = "\u200b"


def compare(raw: list, fixed: list) -> dict:
    kept = total = 0
    mixed_raw = mixed_kept = 0
    examples = []
    for a, b in zip(raw, fixed):
        ta, fa = _chars_with_fmt(a)
        tb, fb = _chars_with_fmt(b)
        if len({f for _, f in a}) > 1:
            mixed_raw += 1
            if len({f for t, f in b if t.strip(_ZW + " ")}) > 1:
                mixed_kept += 1
            elif len(examples) < 50:
                examples.append((a, b))
        tb_plain = tb.replace(_ZW, "")
        fb_plain = [f for c, f in zip(tb, fb) if c != _ZW]
        sm = difflib.SequenceMatcher(None, ta, tb_plain, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                total += i2 - i1
                kept += sum(1 for k in range(i2 - i1) if fa[i1 + k] == fb_plain[j1 + k])
    return {"fmt": kept / max(1, total), "mixed_raw": mixed_raw, "mixed_kept": mixed_kept, "examples": examples}


def convert_raw(pdf_path: Path, out_docx: Path) -> None:
    from pdf2docx import Converter

    from app.services.pdf2docx_fixes import patched_pdf2docx, upright_rotated_pages

    data = upright_rotated_pages(pdf_path.read_bytes())
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp = f.name
    with patched_pdf2docx():
        cv = Converter(tmp)
        cv.convert(str(out_docx), start=0, end=None)
        cv.close()
    Path(tmp).unlink(missing_ok=True)


def evaluate(pdf_path: Path, workdir: Path) -> dict:
    from app.services.convert_service import _fix_thai_in_docx

    raw_path = workdir / (pdf_path.stem + ".raw.docx")
    fixed_path = workdir / (pdf_path.stem + ".fixed.docx")
    convert_raw(pdf_path, raw_path)
    shutil.copyfile(raw_path, fixed_path)
    _fix_thai_in_docx(str(fixed_path), user=None)   # ไม่มี key → ตัวจัดรูปในเครื่อง (ทางเดียวกับผู้ใช้ทั่วไป)
    raw = paragraph_segments(Document(str(raw_path)))
    fixed = paragraph_segments(Document(str(fixed_path)))
    text = "\n".join("".join(t for t, _ in segs) for segs in fixed)
    plain = text.replace(_ZW, "")
    zw_bad = len(re.findall(r"(?<![\u0E01-\u0E5B])\u200b|\u200b(?![\u0E01-\u0E5B])", text))
    res = compare(raw, fixed)
    res.update({
        "file": pdf_path.name,
        "paragraphs": len(fixed),
        "issues": _issues(plain),
        "coverage": thai_text.dictionary_coverage(plain),
        "zwsp_bad": zw_bad,
        "aligned": len(raw) == len(fixed),
    })
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--show", type=int, default=0, help="แสดงตัวอย่างย่อหน้าที่รูปแบบหาย N ย่อหน้า")
    args = ap.parse_args(argv)
    rows = []
    with tempfile.TemporaryDirectory() as d:
        for pdf in sorted(args.folder.glob("*.pdf")):
            try:
                rows.append(evaluate(pdf, Path(d)))
            except Exception as e:  # pragma: no cover
                print(f"{pdf.name}: แปลงไม่สำเร็จ {e}")
    print(f"{'file':40} {'paras':>6} {'fmt':>7} {'mixed raw→kept':>15} {'issues':>7} {'coverage':>9} {'zwsp นอกไทย':>12}")
    for r in rows:
        print(f"{r['file'][:40]:40} {r['paragraphs']:>6} {r['fmt'] * 100:6.1f}% {r['mixed_raw']:>7}→{r['mixed_kept']:<7} "
              f"{r['issues']:>7} {r['coverage']:>9.3f} {r['zwsp_bad']:>12}")
    if rows:
        tot_mixed = sum(r["mixed_raw"] for r in rows)
        print(f"{'รวม':40} {sum(r['paragraphs'] for r in rows):>6} "
              f"{sum(r['fmt'] for r in rows) / len(rows) * 100:6.1f}% {tot_mixed:>7}→{sum(r['mixed_kept'] for r in rows):<7} "
              f"{sum(r['issues'] for r in rows):>7}")
    shown = 0
    for r in rows:
        for a, b in r["examples"]:
            if shown >= args.show:
                break
            shown += 1
            print(f"\n--- {r['file']}\nดิบ : " + " | ".join(f"{t!r}" for t, _ in a) + "\nหลัง: " + " | ".join(f"{t!r}" for t, _ in b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
