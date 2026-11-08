"""วัดคุณภาพการอ่านข้อความภาษาไทยจาก PDF — เทียบข้อความดิบจาก PyMuPDF กับหลังจัดรูป (services/thai_text.py)

ใช้ (จาก backend/):
    python -m scripts.thai_eval ../test_pdf_files            # ตารางสรุป
    python -m scripts.thai_eval ../test_pdf_files --json out.json
    python -m scripts.thai_eval ../test_pdf_files --check    # exit 1 ถ้า issues หลังจัดรูป > 0 หรือเซ็นเซอร์หาคำไม่เจอ
                                                              # (scripts/ship.sh ใช้เป็นด่านก่อน push image)

ตัวชี้วัดต่อไฟล์:
- coverage: สัดส่วนอักษรไทยที่อยู่ในคำที่มีในพจนานุกรม (ยิ่งสูง = อ่านออก) ก่อน → หลัง
- issues: จำนวนรูปแบบที่ผิดแน่ๆ (PUA, ช่องว่าง+สระอา, นิคหิต+สระอา, ำ+วรรณยุกต์, วรรณยุกต์ก่อนสระ, เเ, zero-width)
- fonts: ฟอนต์ที่ตรวจพบว่า map สระอาเป็น ำ · vector_am: สระอาที่มีวงกลมนิคหิตวาดเป็นเส้น (แก้เป็น ำ)
- keywords: ถ้ามีไฟล์ expected.json ในโฟลเดอร์ ({"ชื่อไฟล์.pdf": ["คำที่ต้องเจอ", ...]})
  นับว่าเจอในข้อความดิบ / หลังจัดรูป / page.search_for (วิธีค้นแบบเดิม) / การค้นหาเพื่อเซ็นเซอร์ (text_index)

ไฟล์ตัวอย่างจริงอาจมีข้อมูลส่วนบุคคล — ไม่ commit เข้า git (test_pdf_files/ อยู่ใน .gitignore)
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import thai_text  # noqa: E402
from app.services.pdf_service import text_index  # noqa: E402

ISSUE_PATTERNS = {
    "pua": r"[\uf700-\uf71d]",
    "space+aa": r"[ก-ฮ][่-๋]?[ \u00a0][าำ]",
    "nikhahit+aa": r"ํ[่-๋]?า",
    "am+tone": r"ำ[่-๋]",
    "tone+vowel": r"[่-๋][ัิ-ฺ็]",
    "sara-e-x2": r"เเ",
    "zero-width": r"[\u200b-\u200d\u2060\ufeff]",
    "replacement-char": r"\ufffd",
    "control-char": r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
}


def _page_texts(page: fitz.Page) -> tuple[str, str]:
    raw = page.get_text("dict")
    before = "\n".join("".join(s["text"] for s in ln["spans"])
                       for b in raw["blocks"] if b.get("type") == 0 for ln in b["lines"])
    thai_text.normalize_page_dict(raw, page)
    after = "\n".join("".join(s["text"] for s in ln["spans"])
                      for b in raw["blocks"] if b.get("type") == 0 for ln in b["lines"])
    return before, after


def _issues(text: str) -> int:
    return sum(len(re.findall(p, text)) for p in ISSUE_PATTERNS.values())


def evaluate(path: Path, keywords: list[str]) -> dict:
    doc = fitz.open(path)
    before_parts, after_parts, flagged, vector_am = [], [], set(), 0
    found_search = {k: False for k in keywords}
    found_redact = {k: False for k in keywords}
    patterns = {k: text_index.keyword_pattern(k) for k in keywords}
    for page in doc:
        b, a = _page_texts(page)
        before_parts.append(b)
        after_parts.append(a)
        flagged |= thai_text._page_flags(page.get_text("dict"))
        vector_am += len(thai_text.vector_am_flags(page, page.get_text("rawdict")))
        pt = text_index.page_text(page) if keywords else None
        for k in keywords:
            if not found_search[k] and page.search_for(k):
                found_search[k] = True
            if not found_redact[k] and text_index.find(pt, patterns[k]):
                found_redact[k] = True
    before, after = "\n".join(before_parts), "\n".join(after_parts)
    flat_b, flat_a = re.sub(r"\s+", " ", before), re.sub(r"\s+", " ", after)
    return {
        "file": path.name,
        "pages": doc.page_count,
        "thai_chars": sum(1 for c in after if thai_text.is_thai(c)),
        "coverage_before": round(thai_text.dictionary_coverage(before), 4),
        "coverage_after": round(thai_text.dictionary_coverage(after), 4),
        "issues_before": _issues(before),
        "issues_after": _issues(after),
        "issue_detail_before": {k: len(re.findall(p, before)) for k, p in ISSUE_PATTERNS.items()
                                if re.search(p, before)},
        "misencoded_am_fonts": sorted(flagged),
        "vector_am": vector_am,
        "unknown_words": Counter(thai_text.unknown_words(after)).most_common(30),
        "keywords": {k: {"raw": k in flat_b, "normalized": k in flat_a,
                         "search_for": found_search[k], "redact": found_redact[k]} for k in keywords},
    }


def check_failures(results: list[dict]) -> list[str]:
    """เกณฑ์ผ่านของชุดวัดผล: ทุกไฟล์ต้องไม่มี issues หลังจัดรูป และการค้นหาเพื่อเซ็นเซอร์ต้องเจอทุกคำใน expected.json"""
    failures = []
    for r in results:
        if r["issues_after"]:
            failures.append(f"{r['file']}: issues หลังจัดรูป {r['issues_after']}")
        missing = [k for k, v in r["keywords"].items() if not v["redact"]]
        if missing:
            failures.append(f"{r['file']}: เซ็นเซอร์หาไม่เจอ {missing}")
    return failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--json", type=Path, help="บันทึกผลเป็น JSON")
    ap.add_argument("--oov", action="store_true",
                    help="แสดงคำไทยที่ไม่อยู่ในพจนานุกรม (หาคำเพิ่มใน app/assets/thai_custom_words.txt)")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 ถ้า issues หลังจัดรูป > 0 หรือการค้นหาเพื่อเซ็นเซอร์หาคำใน expected.json ไม่เจอ")
    args = ap.parse_args(argv)

    expected_file = args.folder / "expected.json"
    expected = json.loads(expected_file.read_text("utf-8")) if expected_file.exists() else {}
    results = [evaluate(p, expected.get(p.name, [])) for p in sorted(args.folder.glob("*.pdf"))]

    print(f"{'file':42} {'pages':>5} {'thai':>7} {'coverage':>15} {'issues':>11} {'keywords raw/norm/old/redact':>30}")
    for r in results:
        kw = r["keywords"]
        k = (f"{sum(v['raw'] for v in kw.values())}/{sum(v['normalized'] for v in kw.values())}/"
             f"{sum(v['search_for'] for v in kw.values())}/{sum(v['redact'] for v in kw.values())} of {len(kw)}"
             ) if kw else "-"
        print(f"{r['file'][:42]:42} {r['pages']:>5} {r['thai_chars']:>7} "
              f"{r['coverage_before']:.3f}→{r['coverage_after']:.3f}  {r['issues_before']:>4}→{r['issues_after']:<4} {k:>30}")
        if r["misencoded_am_fonts"]:
            print(f"{'':44}ฟอนต์ map สระอาเป็น ำ: {', '.join(r['misencoded_am_fonts'])}")
        if args.oov and r["unknown_words"]:
            print(f"{'':44}คำที่ไม่รู้จัก: " + ", ".join(f"{w}×{n}" for w, n in r["unknown_words"][:15]))
        if r["vector_am"]:
            print(f"{'':44}สระอำที่วงกลมวาดเป็นเส้น (แก้แล้ว): {r['vector_am']} จุด")
        missing = [w for w, v in kw.items() if not v["normalized"]]
        if missing:
            print(f"{'':44}ยังหาไม่เจอหลังจัดรูป: {missing}")
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    if args.check:
        if not results:
            print("CHECK FAIL: ไม่พบไฟล์ PDF ในโฟลเดอร์")
            return 1
        failures = check_failures(results)
        n_kw = sum(len(r["keywords"]) for r in results)
        if failures:
            print("CHECK FAIL:\n  " + "\n  ".join(failures))
            return 1
        print(f"CHECK OK: {len(results)} ไฟล์ issues = 0, เซ็นเซอร์เจอ {n_kw}/{n_kw} คำ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
