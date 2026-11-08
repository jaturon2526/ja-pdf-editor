"""บาร์โค้ด (เมนูแทรก › บาร์โค้ด): ตรวจข้อมูลตามประเภท + สร้างเป็นเวกเตอร์ (PDF) หรือภาพตัวอย่าง (PNG)

ใช้ BWIPP (Barcode Writer in Pure PostScript, MIT) ผ่าน treepoem (MIT) + Ghostscript ที่มีในระบบอยู่แล้ว
- ประเภท 2 มิติ (QR, Data Matrix, PDF417, Aztec) ใส่ข้อความภาษาไทยได้: เข้ารหัส UTF-8 + ECI 26 (บอกเครื่องอ่านว่าเป็น
  UTF-8) — ข้อความ ASCII ล้วนไม่ใส่ ECI (เครื่องอ่านรุ่นเก่าบางตัวไม่รู้จัก ECI)
- ประเภท 1 มิติ ตรวจรูปแบบ/เลขตรวจสอบก่อนสร้าง (EAN/UPC เติมเลขตรวจสอบให้ถ้าพิมพ์มาไม่ครบหลัก)
- สีเส้น/พื้นต้องตัดกันพอให้สแกนได้ (เส้นเข้มกว่าพื้น · contrast ≥ 3:1)
ข้อมูลส่งเข้า PostScript แบบ hex (treepoem) — ไม่มีทางแทรกคำสั่ง PostScript ได้"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from math import ceil

MAX_DATA_LENGTH = 1000
TIMEOUT_S = 20


@dataclass(frozen=True)
class BarcodeType:
    key: str
    bwipp: str
    label: str
    two_d: bool
    unicode: bool = False
    hint: str = ""


TYPES: dict[str, BarcodeType] = {t.key: t for t in (
    BarcodeType("qrcode", "qrcode", "QR Code", True, True, "ข้อความ ลิงก์ ภาษาไทยได้"),
    BarcodeType("datamatrix", "datamatrix", "Data Matrix", True, True, "ข้อความ ภาษาไทยได้ ขนาดเล็ก"),
    BarcodeType("pdf417", "pdf417", "PDF417", True, True, "ข้อความยาว ภาษาไทยได้ (บัตร/ตั๋ว)"),
    BarcodeType("azteccode", "azteccode", "Aztec", True, True, "ข้อความ ภาษาไทยได้ (ตั๋วเดินทาง)"),
    BarcodeType("code128", "code128", "Code 128", False, False, "ตัวอักษรอังกฤษ ตัวเลข สัญลักษณ์"),
    BarcodeType("code39", "code39", "Code 39", False, False, "A–Z 0–9 และ - . $ / + % ช่องว่าง"),
    BarcodeType("ean13", "ean13", "EAN-13", False, False, "ตัวเลข 12–13 หลัก (สินค้า)"),
    BarcodeType("ean8", "ean8", "EAN-8", False, False, "ตัวเลข 7–8 หลัก"),
    BarcodeType("upca", "upca", "UPC-A", False, False, "ตัวเลข 11–12 หลัก"),
    BarcodeType("itf", "interleaved2of5", "ITF (Interleaved 2 of 5)", False, False, "ตัวเลขจำนวนคู่"),
    BarcodeType("codabar", "rationalizedCodabar", "Codabar", False, False, "ตัวเลข และ - $ : / . +"),
)}

EC_LEVELS = ("L", "M", "Q", "H")
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
_CODE39 = re.compile(r"^[0-9A-Z \-.$/+%]+$")
_CODABAR = re.compile(r"^[0-9\-$:/.+]+$")


class BarcodeError(ValueError):
    """ข้อมูล/ตัวเลือกไม่ถูกต้อง — ข้อความภาษาไทยแสดงผู้ใช้ได้เลย"""


@dataclass
class BarcodeSpec:
    type: str
    data: str
    ec_level: str = "M"            # QR เท่านั้น
    show_text: bool = True         # แสดงข้อความใต้บาร์โค้ด 1 มิติ
    bar_color: str = "#000000"
    bg_color: str = "#FFFFFF"


def _gtin_check(digits: str) -> str:
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return str((10 - total % 10) % 10)


def _gtin(data: str, length: int, name: str) -> str:
    if not data.isdigit():
        raise BarcodeError(f"{name} ใช้ได้เฉพาะตัวเลข")
    if len(data) == length - 1:
        return data + _gtin_check(data)
    if len(data) != length:
        raise BarcodeError(f"{name} ต้องเป็นตัวเลข {length - 1} หลัก (ระบบเติมเลขตรวจสอบให้) หรือ {length} หลัก")
    if data[-1] != _gtin_check(data[:-1]):
        raise BarcodeError(f"เลขตรวจสอบ (หลักสุดท้าย) ไม่ถูกต้อง — ควรเป็น {_gtin_check(data[:-1])}")
    return data


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(_rgb(a)), _luminance(_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def validate(spec: BarcodeSpec) -> BarcodeSpec:
    """คืน spec ที่ปรับแล้ว (เช่น เติมเลขตรวจสอบ, Code 39 เป็นตัวพิมพ์ใหญ่) หรือ BarcodeError"""
    t = TYPES.get(spec.type)
    if not t:
        raise BarcodeError("ไม่รู้จักประเภทบาร์โค้ดนี้")
    data = spec.data if t.two_d else spec.data.strip()
    if not data.strip():
        raise BarcodeError("กรุณากรอกข้อมูล")
    if len(data) > MAX_DATA_LENGTH:
        raise BarcodeError(f"ข้อมูลยาวเกิน {MAX_DATA_LENGTH} ตัวอักษร")
    if not t.unicode and any(ord(c) > 126 or ord(c) < 32 for c in data):
        raise BarcodeError(f"{t.label} ใส่ได้เฉพาะตัวอักษรภาษาอังกฤษ/ตัวเลข — ข้อความภาษาไทยให้ใช้ QR Code หรือ Data Matrix")
    if t.key == "ean13":
        data = _gtin(data, 13, "EAN-13")
    elif t.key == "ean8":
        data = _gtin(data, 8, "EAN-8")
    elif t.key == "upca":
        data = _gtin(data, 12, "UPC-A")
    elif t.key == "itf":
        if not data.isdigit() or len(data) % 2:
            raise BarcodeError("ITF ต้องเป็นตัวเลขจำนวนหลักเป็นคู่ (เช่น 14 หลัก) — เติม 0 ข้างหน้าได้")
    elif t.key == "code39":
        data = data.upper()
        if not _CODE39.match(data):
            raise BarcodeError("Code 39 ใช้ได้เฉพาะ A–Z, 0–9, ช่องว่าง และ - . $ / + %")
    elif t.key == "codabar":
        core = data.upper()
        if core[:1] in "ABCD" and core[-1:] in "ABCD" and len(core) >= 2:
            core = core[1:-1]
        if not core or not _CODABAR.match(core):
            raise BarcodeError("Codabar ใช้ได้เฉพาะตัวเลข และ - $ : / . +")
        data = core
    if spec.ec_level not in EC_LEVELS:
        raise BarcodeError("ระดับการแก้ไขข้อผิดพลาดต้องเป็น L, M, Q หรือ H")
    for name, c in (("สีเส้น", spec.bar_color), ("สีพื้นหลัง", spec.bg_color)):
        if not _HEX.match(c or ""):
            raise BarcodeError(f"{name}ต้องอยู่ในรูปแบบ #RRGGBB")
    bar = "#" + spec.bar_color.lstrip("#").upper()
    bg = "#" + spec.bg_color.lstrip("#").upper()
    if _luminance(_rgb(bar)) >= _luminance(_rgb(bg)):
        raise BarcodeError("สีเส้นต้องเข้มกว่าสีพื้นหลัง — เครื่องสแกนส่วนใหญ่อ่านบาร์โค้ดสีกลับด้านไม่ได้")
    if contrast_ratio(bar, bg) < 3:
        raise BarcodeError("สีเส้นกับพื้นหลังต่างกันน้อยเกินไป สแกนไม่ติด — เลือกสีเส้นเข้มขึ้นหรือพื้นอ่อนลง")
    return BarcodeSpec(t.key, data, spec.ec_level, spec.show_text, bar, bg)


def _bwipp_input(spec: BarcodeSpec) -> tuple[str, bytes, dict]:
    t = TYPES[spec.type]
    opts: dict = {"barcolor": spec.bar_color.lstrip("#"), "backgroundcolor": spec.bg_color.lstrip("#")}
    data = spec.data
    if t.two_d and any(ord(c) > 127 for c in data):
        # UTF-8 + ECI 26 — parsefnc: ^ECI000026 = ตัวบอก ECI, ^^ = เครื่องหมาย ^ จริง
        payload = ("^ECI000026" + data.replace("^", "^^")).encode("utf-8")
        opts["parsefnc"] = True
    else:
        payload = data.encode("ascii")
    if t.key == "qrcode":
        opts["eclevel"] = spec.ec_level
    if t.key == "codabar":
        payload = b"A" + payload + b"A"
    if not t.two_d and spec.show_text:
        opts["includetext"] = True
        opts["textfont"] = "Helvetica"
    return t.bwipp, payload, opts


def _eps(spec: BarcodeSpec) -> tuple[str, float, float]:
    import treepoem

    bwipp_type, payload, opts = _bwipp_input(spec)
    bwipp = treepoem.load_bwipp()
    encoder = treepoem._format_data_options_encoder(payload, opts, bwipp_type)
    bbox_code = treepoem.BBOX_TEMPLATE.format(bwipp=bwipp, data_options_encoder=encoder)
    offset = 3000
    gs = treepoem._ghostscript_binary()
    proc = subprocess.run(
        [gs, "-dSAFER", "-dQUIET", "-dNOPAUSE", "-dBATCH", "-sDEVICE=bbox", "-c",
         f"<</PageOffset [{offset} {offset}]>> setpagedevice", "-f", "-"],
        text=True, capture_output=True, input=bbox_code, timeout=TIMEOUT_S,
    )
    err = proc.stderr.strip()
    if proc.returncode != 0 or "BWIPP ERROR:" in err:
        msg = err.replace("BWIPP ERROR: ", "")
        low = msg.lower()
        if any(k in low for k in ("toolong", "too long", "capacity", "fit", "maximum length", "novalidsymbol")):
            tip = " หรือเลือกระดับแก้ไขข้อผิดพลาดต่ำลง" if spec.type == "qrcode" else ""
            raise BarcodeError(f"ข้อมูลยาวเกินกว่าที่ {TYPES[spec.type].label} รองรับ — ลดข้อความ{tip}")
        raise BarcodeError(f"สร้างบาร์โค้ดไม่สำเร็จ: {msg[:200] or 'ข้อมูลไม่ถูกต้องสำหรับประเภทนี้'}")
    line = next((ln for ln in err.splitlines() if ln.startswith("%%HiResBoundingBox:")), None)
    if not line:
        raise BarcodeError("สร้างบาร์โค้ดไม่สำเร็จ")
    x1, y1, x2, y2 = (float(n) for n in line.split(":", 1)[1].split())
    width, height = x2 - x1, y2 - y1
    eps = treepoem.EPS_TEMPLATE.format(
        ceilwidth=int(ceil(width)), ceilheight=int(ceil(height)), width=width, height=height, bwipp=bwipp,
        translate_x=offset - x1, translate_y=offset - y1, data_options_encoder=encoder,
    )
    return eps, width, height


def render_pdf(spec: BarcodeSpec, quiet_zone_pt: float | None = None) -> tuple[bytes, float, float]:
    """บาร์โค้ดเวกเตอร์เป็น PDF หน้าเดียว (มีขอบว่างรอบตัว = quiet zone ที่เครื่องสแกนต้องการ) → (ไบต์, กว้าง pt, สูง pt)"""
    import fitz
    import treepoem

    spec = validate(spec)
    eps, w, h = _eps(spec)
    proc = subprocess.run(
        [treepoem._ghostscript_binary(), "-dSAFER", "-dQUIET", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
         f"-dDEVICEWIDTHPOINTS={w}", f"-dDEVICEHEIGHTPOINTS={h}", "-dFIXEDMEDIA", "-sOutputFile=-", "-"],
        capture_output=True, input=eps.encode(), timeout=TIMEOUT_S,
    )
    if proc.returncode != 0 or not proc.stdout.startswith(b"%PDF"):
        raise BarcodeError("สร้างบาร์โค้ดไม่สำเร็จ")
    # เติมขอบว่าง (quiet zone) สีพื้นหลังรอบบาร์โค้ด — 2 มิติ ~4 โมดูล, 1 มิติ ~10 เท่าเส้นแคบสุด (ประมาณจากขนาด)
    q = quiet_zone_pt if quiet_zone_pt is not None else (max(4.0, min(w, h) * 0.08) if TYPES[spec.type].two_d else max(8.0, w * 0.08))
    src = fitz.open("pdf", proc.stdout)
    out = fitz.open()
    page = out.new_page(width=w + 2 * q, height=h + 2 * q)
    page.draw_rect(page.rect, color=None, fill=tuple(c / 255 for c in _rgb(spec.bg_color)), width=0)
    page.show_pdf_page(fitz.Rect(q, q, q + w, q + h), src, 0)
    data = out.tobytes(garbage=3, deflate=True)
    return data, page.rect.width, page.rect.height


def render_png(spec: BarcodeSpec, max_px: int = 900) -> bytes:
    """ภาพตัวอย่าง (หน้าต่างตั้งค่า / กล่องลากวางบนหน้า) — เรนเดอร์จาก PDF เวกเตอร์ตัวเดียวกัน"""
    import fitz

    pdf, w, h = render_pdf(spec)
    doc = fitz.open("pdf", pdf)
    zoom = max(1.0, min(8.0, max_px / max(w, h)))
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


_BATCH_ITEM = """
(%stderr) (w) file dup (\nJAITEM {i}\n) writestring flushfile
{{
  0 0 moveto
  {enc}
  /uk.co.terryburton.bwipp findresource exec
}} stopped {{
  (%stderr) (w) file dup (\nBWIPP ERROR: ) writestring
  dup $error /errorname get dup length string cvs writestring flushfile
}} if
showpage
"""


def render_png_batch(specs: list[BarcodeSpec], dpi: int = 300) -> list[bytes | BarcodeError]:
    """หลายบาร์โค้ดใน Ghostscript 2 รอบ (วัดขนาดทั้งชุด → วาดทั้งชุด) แทน 2 รอบต่อรูป — Auto-Gen หลายร้อยแถว
    เสร็จในไม่กี่วินาที (ทีละรูป ~0.6 วินาที) · คืนลำดับเดียวกับ specs: PNG (มีขอบว่างรอบตัว) หรือ BarcodeError"""
    import fitz
    import treepoem

    out: list[bytes | BarcodeError] = [BarcodeError("ไม่ได้สร้าง")] * len(specs)
    items: list[tuple[int, BarcodeSpec, str]] = []
    for i, spec in enumerate(specs):
        try:
            v = validate(spec)
            bwipp_type, payload, opts = _bwipp_input(v)
            items.append((i, v, treepoem._format_data_options_encoder(payload, opts, bwipp_type)))
        except BarcodeError as exc:
            out[i] = exc
    if not items:
        return out
    bwipp = treepoem.load_bwipp()
    gs = treepoem._ghostscript_binary()
    timeout = TIMEOUT_S + 0.2 * len(items)
    offset = 3000
    prog = "%!PS\n" + bwipp + "\n/Helvetica findfont 10 scalefont setfont\n" + "".join(
        _BATCH_ITEM.format(i=k, enc=enc) for k, (_, _, enc) in enumerate(items))
    proc = subprocess.run([gs, "-dSAFER", "-dQUIET", "-dNOPAUSE", "-dBATCH", "-sDEVICE=bbox", "-c",
                           f"<</PageOffset [{offset} {offset}]>> setpagedevice", "-f", "-"],
                          text=True, capture_output=True, input=prog, timeout=timeout)
    boxes: dict[int, tuple[float, float, float, float]] = {}
    failed: dict[int, str] = {}
    current = -1
    for line in proc.stderr.splitlines():
        if line.startswith("JAITEM "):
            current = int(line.split()[1])
        elif line.startswith("BWIPP ERROR:"):
            failed[current] = line.split(":", 1)[1].strip()
        elif line.startswith("%%HiResBoundingBox:") and current >= 0 and current not in failed:
            x1, y1, x2, y2 = (float(n) for n in line.split(":", 1)[1].split())
            if x2 > x1 and y2 > y1:
                boxes[current] = (x1, y1, x2, y2)
    pages = []
    for k, (i, spec, enc) in enumerate(items):
        if k not in boxes:
            msg = failed.get(k, "").lower()
            long_ = any(w in msg for w in ("toolong", "too long", "capacity", "fit", "maximum", "novalidsymbol"))
            out[i] = BarcodeError(f"ข้อมูลยาวเกินกว่าที่ {TYPES[spec.type].label} รองรับ" if long_
                                  else f"สร้าง {TYPES[spec.type].label} จากข้อมูลนี้ไม่ได้")
            continue
        x1, y1, x2, y2 = boxes[k]
        w, h = x2 - x1, y2 - y1
        pages.append((i, spec, w, h))
        # หน้าละรูป ขนาดพอดีบาร์โค้ด (เหมือน EPS ของ treepoem)
        prog_page = (f"<</PageSize [{w:.4f} {h:.4f}]>> setpagedevice\n{offset - x1:.4f} {offset - y1:.4f} moveto\n"
                     f"{enc} /uk.co.terryburton.bwipp findresource exec\nshowpage\n")
        pages[-1] = (*pages[-1], prog_page)
    if not pages:
        return out
    prog = "%!PS\n" + bwipp + "\n/Helvetica findfont 10 scalefont setfont\n" + "".join(p[4] for p in pages)
    proc = subprocess.run([gs, "-dSAFER", "-dQUIET", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", "-sOutputFile=-", "-"],
                          capture_output=True, input=prog.encode(), timeout=timeout)
    if proc.returncode != 0 or not proc.stdout.startswith(b"%PDF"):
        for i, *_ in pages:
            out[i] = BarcodeError("สร้างบาร์โค้ดไม่สำเร็จ")
        return out
    src = fitz.open("pdf", proc.stdout)
    zoom = dpi / 72.0
    for n, (i, spec, w, h, _) in enumerate(pages):
        q = max(4.0, min(w, h) * 0.08) if TYPES[spec.type].two_d else max(8.0, w * 0.08)
        doc = fitz.open()
        page = doc.new_page(width=w + 2 * q, height=h + 2 * q)
        page.draw_rect(page.rect, color=None, fill=tuple(c / 255 for c in _rgb(spec.bg_color)), width=0)
        page.show_pdf_page(fitz.Rect(q, q, q + w, q + h), src, n)
        out[i] = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
    return out


def insert_into_page(page, rect, spec: BarcodeSpec) -> None:
    """วางบาร์โค้ดเวกเตอร์ลงกรอบ rect (พิกัดหน้า) — ยืดให้เต็มกรอบตามที่ผู้ใช้ลาก (เหมือนแทรกรูป)"""
    import fitz

    pdf, _, _ = render_pdf(spec)
    src = fitz.open("pdf", pdf)
    page.show_pdf_page(rect, src, 0, keep_proportion=False)


def to_png_bytes_for_test(pdf: bytes, zoom: float = 4.0) -> bytes:  # ใช้ในเทสต์ (อ่านกลับด้วยตัวสแกน)
    import fitz

    return fitz.open("pdf", pdf)[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")


__all__ = ["TYPES", "EC_LEVELS", "BarcodeSpec", "BarcodeError", "validate", "render_pdf", "render_png", "render_png_batch",
           "insert_into_page", "contrast_ratio"]