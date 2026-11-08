"""วัดผลการตรวจข้อมูลส่วนบุคคล (PDPA, pdf_service.pii) — ชุดข้อความทดสอบสมมติ (ชื่อ/เลขทั้งหมดแต่งขึ้น)

ใช้ (จาก backend/):
    python -m scripts.pii_eval                  # recall ต่อประเภท + รายการที่ตรวจผิด (false positive)
    python -m scripts.pii_eval --pdf ../test_pdf_files   # + จำนวนที่พบในไฟล์จริงต่อประเภท (ไว้ตรวจด้วยตา)

CASES: (ข้อความ, [(ประเภท, ส่วนของข้อความที่ต้องพบ)]) — รายการว่าง = ห้ามพบอะไรเลย ("\\n" = ขึ้นบรรทัดใน PDF)
พบ = มีรายการประเภทเดียวกันที่ครอบส่วนนั้นทั้งหมด · false positive = รายการที่ไม่ทับส่วนที่คาดไว้เลย
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pdf_service import pii  # noqa: E402

_TH = str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙")


def _id(first12: str) -> str:
    total = sum(int(first12[i]) * (13 - i) for i in range(12))
    return first12 + str((11 - total % 11) % 10)


ID = _id("310050123456")
ID_FMT = f"{ID[0]}-{ID[1:5]}-{ID[5:10]}-{ID[10:12]}-{ID[12]}"
ID_TH = ID_FMT.translate(_TH)

CASES: list[tuple[str, list[tuple[str, str]]]] = [
    # --- ตัวเลขอารบิก (ของเดิม — ต้องยังพบ)
    (f"เลขประจำตัวประชาชน {ID_FMT}", [("national_id", ID_FMT)]),
    ("โทร 081-234-5678", [("phone", "081-234-5678")]),
    ("บัญชีออมทรัพย์เลขที่ 123-4-56789-0", [("bank_account", "123-4-56789-0")]),
    ("ข้าพเจ้า นายสมชาย ใจดี อายุ 45 ปี", [("person_name", "นายสมชาย ใจดี")]),
    ("(นางสาวกมลวรรณ ศรีสุข)", [("person_name", "นางสาวกมลวรรณ ศรีสุข")]),
    # --- ตัวเลขไทย
    (f"เลขประจำตัวประชาชน {ID_TH}", [("national_id", ID_TH)]),
    (f"บัตรประชาชนเลขที่ {ID.translate(_TH)}", [("national_id", ID.translate(_TH))]),
    ("โทรศัพท์ ๐๘๑-๒๓๔-๕๖๗๘", [("phone", "๐๘๑-๒๓๔-๕๖๗๘")]),
    ("โทร. ๐ ๒๑๒๓ ๔๕๖๗", [("phone", "๐ ๒๑๒๓ ๔๕๖๗")]),
    ("บัญชีกระแสรายวัน เลขที่ ๑๒๓-๔-๕๖๗๘๙-๐", [("bank_account", "๑๒๓-๔-๕๖๗๘๙-๐")]),
    ("บ้านเลขที่ ๙๙/๙ หมู่ ๔ ตำบลบางพูด อำเภอปากเกร็ด จังหวัดนนทบุรี ๑๑๑๒๐",
     [("address", "บ้านเลขที่ ๙๙/๙ หมู่ ๔ ตำบลบางพูด อำเภอปากเกร็ด จังหวัดนนทบุรี ๑๑๑๒๐")]),
    # --- ชื่อข้ามบรรทัด
    ("ข้าพเจ้า นายสมชาย\nใจดี อายุ ๔๕ ปี", [("person_name", "นายสมชาย\nใจดี")]),
    ("ระหว่าง นางสาวกมลวรรณ\nศรีสุข ซึ่งต่อไปเรียกว่า ผู้เช่า", [("person_name", "นางสาวกมลวรรณ\nศรีสุข")]),
    ("ลงชื่อ ผู้ให้เช่า (นาย\nประเสริฐ วงศ์ทอง)", [("person_name", "นาย\nประเสริฐ วงศ์ทอง")]),
    # --- ยศ ตำแหน่งวิชาการ ราชสกุล
    ("พล.ต.อ. สมศักดิ์ รักษ์ไทย ผู้บังคับบัญชา", [("person_name", "พล.ต.อ. สมศักดิ์ รักษ์ไทย")]),
    ("โดย พ.ต.ท.สุรชัย มั่นคงดี สารวัตร", [("person_name", "พ.ต.ท.สุรชัย มั่นคงดี")]),
    ("จ.ส.อ.ประยงค์ ทองแท้ ผู้รับมอบ", [("person_name", "จ.ส.อ.ประยงค์ ทองแท้")]),
    ("ว่าที่ ร.ต. อนันต์ สุขใจดี", [("person_name", "ว่าที่ ร.ต. อนันต์ สุขใจดี")]),
    ("ว่าที่ร้อยตรีอนันต์ สุขใจดี", [("person_name", "ว่าที่ร้อยตรีอนันต์ สุขใจดี")]),
    ("พันเอกวีระพงษ์ แสงทอง ผู้อำนวยการ", [("person_name", "พันเอกวีระพงษ์ แสงทอง")]),
    ("ร้อยตำรวจเอกหญิงสุดารัตน์ ใจงาม", [("person_name", "ร้อยตำรวจเอกหญิงสุดารัตน์ ใจงาม")]),
    ("ม.ร.ว.ศรีสุดา วงศ์ใหญ่ ประธาน", [("person_name", "ม.ร.ว.ศรีสุดา วงศ์ใหญ่")]),
    ("หม่อมหลวงสุภาพร ทองสุขดี", [("person_name", "หม่อมหลวงสุภาพร ทองสุขดี")]),
    ("ศ.ดร.วิชัย ใจดีมาก คณบดี", [("person_name", "ศ.ดร.วิชัย ใจดีมาก")]),
    ("รศ.ดร. กาญจนา มีสุขดี", [("person_name", "รศ.ดร. กาญจนา มีสุขดี")]),
    ("ผศ.สมพร แก้วใสดี อาจารย์ที่ปรึกษา", [("person_name", "ผศ.สมพร แก้วใสดี")]),
    ("เรียน คุณสมหญิง รักเรียนดี", [("person_name", "คุณสมหญิง รักเรียนดี")]),
    ("ลูกค้า: คุณ สมชาย ใจดี", [("person_name", "คุณ สมชาย ใจดี")]),
    ("พระครูสมุห์วิชัย ปัญญาดี เจ้าอาวาส", [("person_name", "พระครูสมุห์วิชัย ปัญญาดี")]),
    # --- ชื่อหลังหัวข้อในแบบฟอร์ม (ไม่มีคำนำหน้า)
    ("ชื่อ-นามสกุล: สมชาย ใจดี", [("person_name", "สมชาย ใจดี")]),
    ("ชื่อ - สกุล  กมลวรรณ ศรีสุข  วันเกิด ๑ มกราคม ๒๕๓๐", [("person_name", "กมลวรรณ ศรีสุข")]),
    # --- หัวข้ออื่นที่ตามด้วยชื่อ / ลายมือชื่อ (2026-10)
    ("ชื่อลูกค้า :  กิตติพัฒน์  ทองประเสริฐ", [("person_name", "กิตติพัฒน์  ทองประเสริฐ")]),
    ("ชื่อผู้รับ: สมหญิง ใจงาม โทร ๐๘๑-๒๓๔-๕๖๗๘", [("person_name", "สมหญิง ใจงาม"), ("phone", "๐๘๑-๒๓๔-๕๖๗๘")]),
    ("ผู้ติดต่อ : วิชัย ศรีสุข", [("person_name", "วิชัย ศรีสุข")]),
    ("ลงชื่อ ................................ ผู้รับเงิน\n(ประเสริฐ วงศ์ทอง)", [("person_name", "ประเสริฐ วงศ์ทอง")]),
    ("Customer Name: John Smith", [("person_name", "John Smith")]),
    # --- ชื่อไม่มีคำนำหน้า/หัวข้อ → พบจากรายชื่อคนไทย (ให้ผู้ใช้ตรวจเอง)
    ("ประชุมร่วมกับ วิชัย ศรีสุข และทีมงาน", [("person_name_guess", "วิชัย ศรีสุข")]),
    ("ผู้อนุมัติ วชิรา เทพศิริ", [("person_name_guess", "วชิรา เทพศิริ")]),
    # --- ห้ามพบ (false positive ที่พบบ่อย)
    ("ธนาคาร กรุงเทพ สาขาสีลม", []),
    ("วันที่สั่งซื้อ : 12/01/2568 ที่อยู่จัดส่ง : ตามใบเสร็จ", []),
    ("ผู้รับผิดชอบโครงการ ฝ่ายเทคโนโลยีสารสนเทศ", []),
    ("ชื่อ : ระบบบริการลูกค้า", []),
    ("คุณภาพ สินค้าดีเยี่ยม", []),
    ("คุณสมบัติ ของผู้สมัคร", []),
    ("คุณค่า ทางอาหารสูง", []),
    ("นายจ้าง ต้องจ่ายค่าจ้าง", []),
    ("นาย\nทะเบียน ประจำสำนักงาน", []),
    ("ประกาศ ณ วันที่ ๒๑ กันยายน พ.ศ. ๒๕๖๙", []),
    ("อ. เมือง จ. นนทบุรี", []),
    ("พล.อ.อ. คือ ยศ", []),
    ("ชื่อ-นามสกุล", []),
    ("ชื่อสินค้า โน้ตบุ๊ก ราคา ๒๕,๐๐๐ บาท", []),
    ("รายการที่ ๑ จำนวน ๑๒๓๔๕๖๗๘๙๐ ชิ้น", []),
    ("มาตรา ๑๒๓ แห่งประมวลกฎหมายที่ดิน", []),
    ("ร้อยละ ๒๐ ของยอดขาย", []),
    ("พันธมิตร ทางธุรกิจ", []),
]


def evaluate(cases=CASES) -> dict:
    per_type: dict[str, list[int]] = {}
    misses, false_pos = [], []
    for text, expected in cases:
        found = pii.find_in_text(text)
        spans = []
        for typ, part in expected:
            s = text.index(part)
            e = s + len(part)
            spans.append((s, e))
            hit = any(t == typ and fs <= s and fe >= e for t, fs, fe in found)
            per_type.setdefault(typ, [0, 0])
            per_type[typ][0] += hit
            per_type[typ][1] += 1
            if not hit:
                misses.append((typ, text, [(t, text[a:b]) for t, a, b in found]))
        for t, fs, fe in found:
            if not any(fs < e and fe > s for s, e in spans):
                false_pos.append((t, text, text[fs:fe]))
    return {"per_type": per_type, "misses": misses, "false_pos": false_pos,
            "negatives": sum(1 for _, exp in cases if not exp)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path, help="โฟลเดอร์ PDF จริง — นับจำนวนที่พบต่อประเภท")
    args = ap.parse_args(argv)
    r = evaluate()
    found = sum(v[0] for v in r["per_type"].values())
    total = sum(v[1] for v in r["per_type"].values())
    print(f"พบ {found}/{total} รายการที่ควรพบ · false positive {len(r['false_pos'])} (ข้อความห้ามพบ {r['negatives']} ข้อ)")
    for t, (h, n) in sorted(r["per_type"].items()):
        print(f"  {t:14} {h}/{n}")
    for t, text, got in r["misses"]:
        print(f"  ✗ ไม่พบ {t}: {text!r} → ได้ {got}")
    for t, text, part in r["false_pos"]:
        print(f"  ✗ ผิด {t}: {part!r} ใน {text!r}")
    if args.pdf:
        import fitz

        for f in sorted(args.pdf.glob("*.pdf")):
            counts: dict[str, int] = {}
            for page in fitz.open(f):
                for typ, s, e in pii.find_in_text(pii._page_text(page).text):
                    counts[typ] = counts.get(typ, 0) + 1
            print(f"{f.name[:40]:40} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
