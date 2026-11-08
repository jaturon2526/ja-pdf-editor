"""QR Code / บาร์โค้ดใน Template ของ Auto-Gen (สร้างเอกสารอัตโนมัติ)

ผู้ออกแบบใส่ได้ 2 แบบใน Word:
1. พิมพ์ในข้อความ  {{ qr(ลิงก์) }} · {{ qr(ลิงก์, 30) }} · {{ barcode("code128", รหัส, 50, 12) }}
   → รูปแทรกในบรรทัดตรงตำแหน่งนั้น ขนาดเป็นมิลลิเมตร (ความกว้าง[, ความสูง])
2. รูปตัวแทน: แทรกรูปอะไรก็ได้ จัดขนาด/ตำแหน่ง/การตัดข้อความเอง แล้วใส่ Alt Text (คำอธิบายรูป) เป็น
   {{ qr(ลิงก์) }} → แทนที่ด้วยรูปบาร์โค้ดของแต่ละแถวในกรอบเดิม (คงสัดส่วนบาร์โค้ด เติมขอบสีพื้นให้เต็มกรอบ)

ลำดับงาน (ดู routes_autogen.auto_generate_documents):
  prepare(template) — เปลี่ยน Alt Text ที่เป็นนิพจน์เป็นตัวบอก (ไม่ให้ docxtpl render รูปลงในแอตทริบิวต์)
  RowBarcodes ต่อแถว — ฟังก์ชัน qr()/barcode() ใน Template คืนตัวบอกข้อความ + จดคำขอ (ตรวจข้อมูลทันที)
  render_all — สร้างรูปทุกแถวในครั้งเดียว (barcode_service.render_png_batch, ค่าซ้ำสร้างครั้งเดียว)
  apply — แทนตัวบอกในไฟล์ Word ของแต่ละแถวด้วยรูปจริง
ข้อมูลว่าง (เช่น บางแถวไม่มีลิงก์) → ไม่ใส่รูป (รูปตัวแทนถูกเอาออก) ไม่ถือเป็นข้อผิดพลาด
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

from app.services import barcode_service
from app.services.barcode_service import BarcodeError, BarcodeSpec

FUNCTIONS = ("qr", "barcode")
KIND_ALIASES = {"qr": "qrcode", "qrcode": "qrcode", "datamatrix": "datamatrix", "pdf417": "pdf417",
                "aztec": "azteccode", "azteccode": "azteccode", "code128": "code128", "code39": "code39",
                "ean13": "ean13", "ean8": "ean8", "upca": "upca", "itf": "itf", "codabar": "codabar"}
_STORY_PART = re.compile(r"^word/(document|header\d*|footer\d*)\.xml$")
_DESCR = re.compile(r'(<wp:docPr\b[^>]*?\sdescr=")([^"]*\{\{[^"]*\}\}[^"]*)(")')
_FRAME_MARK = "JABCFRAME{}X"
_INLINE_MARK = "@@JABC{}@@"
_INLINE_RE = re.compile(r"@@JABC(\d+)@@")
MAX_MM = 300


def uses_barcodes(template_bytes: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(template_bytes)) as z:
            for name in z.namelist():
                if _STORY_PART.match(name):
                    xml = z.read(name)
                    if b"qr(" in xml or b"barcode(" in xml:
                        return True
    except zipfile.BadZipFile:
        return False
    return False


def prepare(template_bytes: bytes) -> tuple[bytes, list[str]]:
    """Alt Text ของรูปที่เป็นนิพจน์ {{ qr(...) }} → ตัวบอก JABCFRAME<n>X · คืน (template ใหม่, นิพจน์ตามลำดับ n)"""
    exprs: list[str] = []

    def repl(m: re.Match) -> str:
        raw = html.unescape(m.group(2)).strip()
        inner = re.fullmatch(r"\{\{-?\s*(.+?)\s*-?\}\}", raw, flags=re.S)
        if not inner or not re.match(r"(qr|barcode)\s*\(", inner.group(1)):
            return m.group(0)  # Alt Text อื่นที่มี {{ }} — ปล่อยให้ docxtpl จัดการเหมือนเดิม
        exprs.append(inner.group(1))
        return f"{m.group(1)}{_FRAME_MARK.format(len(exprs) - 1)}{m.group(3)}"

    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if _STORY_PART.match(item.filename):
                text = data.decode("utf-8")
                new = _DESCR.sub(repl, text)
                if new != text:
                    data = new.encode("utf-8")
            dst.writestr(item, data)
    return out.getvalue(), exprs


def frame_variables(exprs: list[str], env) -> set[str]:
    from jinja2 import meta

    names: set[str] = set()
    for e in exprs:
        names |= meta.find_undeclared_variables(env.parse("{{ " + e + " }}"))
    return names - set(FUNCTIONS)


def _num(value, name: str, default: Optional[float]) -> Optional[float]:
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise BarcodeError(f"{name}ต้องเป็นตัวเลข (มิลลิเมตร)")
    if not 3 <= v <= MAX_MM:
        raise BarcodeError(f"{name}ต้องอยู่ระหว่าง 3–{MAX_MM} มม.")
    return v


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@dataclass
class Request:
    spec: Optional[BarcodeSpec]       # None = ข้อมูลว่าง (ไม่ใส่รูป)
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None


@dataclass
class RowBarcodes:
    """ฟังก์ชันสำหรับแถวหนึ่ง — qr()/barcode() ใน Template ข้อความคืนตัวบอก, รูปตัวแทนคืน Request"""
    inline: list[Request] = field(default_factory=list)
    frames: dict[int, Request] = field(default_factory=dict)

    @staticmethod
    def _make(kind: str, value, width, height, show_text=True, ec="M") -> Request:
        key = KIND_ALIASES.get(str(kind).strip().lower().replace("-", "").replace(" ", "").replace("_", ""))
        if not key:
            raise BarcodeError(f"ไม่รู้จักประเภทบาร์โค้ด \"{kind}\" — ใช้ได้: qr, datamatrix, pdf417, aztec, code128, code39, ean13, ean8, upca, itf, codabar")
        data = _text(value)
        w = _num(width, "ความกว้าง", None)
        h = _num(height, "ความสูง", None)
        if not data.strip():
            return Request(None, w, h)
        spec = barcode_service.validate(BarcodeSpec(type=key, data=data, ec_level=str(ec).upper(), show_text=bool(show_text)))
        return Request(spec, w, h)

    def _inline(self, req: Request) -> str:
        self.inline.append(req)
        return _INLINE_MARK.format(len(self.inline) - 1)

    def qr(self, value, size=25, ec="M"):
        return self._inline(self._make("qrcode", value, size, None, ec=ec))

    def barcode(self, kind, value, width=None, height=None, text=True):
        key = KIND_ALIASES.get(str(kind).strip().lower().replace("-", "").replace(" ", "").replace("_", ""))
        two_d = key in ("qrcode", "datamatrix", "azteccode") if key else False
        default_w = 25 if two_d else (60 if key == "pdf417" else 50)
        return self._inline(self._make(kind, value, width if width is not None else default_w, height, show_text=text))

    def functions(self) -> dict:
        return {"qr": self.qr, "barcode": self.barcode}

    def evaluate_frames(self, exprs: list[str], env, context: dict) -> None:
        """นิพจน์ใน Alt Text ของรูปตัวแทน → Request (ขนาดใช้กรอบรูปที่ออกแบบไว้)"""
        funcs = {
            "qr": lambda value, size=None, ec="M": self._make("qrcode", value, None, None, ec=ec),
            "barcode": lambda kind, value, width=None, height=None, text=True: self._make(kind, value, None, None, show_text=text),
        }
        for i, e in enumerate(exprs):
            req = env.compile_expression(e)(**{**context, **funcs})
            if not isinstance(req, Request):
                raise BarcodeError(f"Alt Text ของรูปตัวแทนต้องเป็น qr(...) หรือ barcode(...) เท่านั้น: {e}")
            self.frames[i] = req

    def specs(self) -> list[BarcodeSpec]:
        return [r.spec for r in (*self.inline, *self.frames.values()) if r.spec is not None]


def _spec_key(spec: BarcodeSpec) -> tuple:
    return (spec.type, spec.data, spec.ec_level, spec.show_text, spec.bar_color, spec.bg_color)


def render_all(rows: list[RowBarcodes]) -> dict[tuple, bytes | BarcodeError]:
    unique: dict[tuple, BarcodeSpec] = {}
    for r in rows:
        for s in r.specs():
            unique.setdefault(_spec_key(s), s)
    keys = list(unique)
    images = barcode_service.render_png_batch([unique[k] for k in keys])
    return dict(zip(keys, images))


def first_error(row: RowBarcodes, images: dict) -> Optional[str]:
    for s in row.specs():
        img = images.get(_spec_key(s))
        if isinstance(img, BarcodeError):
            return f"{barcode_service.TYPES[s.type].label} \"{s.data[:40]}\": {img}"
    return None


# ------------------------------------------------------------------ ใส่รูปลงไฟล์ Word

def _pad_to_ratio(png: bytes, ratio: float, bg: str) -> bytes:
    """เติมขอบสีพื้นให้ภาพมีสัดส่วนเท่ากรอบ (กว้าง/สูง) — บาร์โค้ดไม่ถูกบีบ/ยืดจนสแกนไม่ได้"""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    if ratio <= 0 or abs(w / h - ratio) < 0.01:
        return png
    if w / h > ratio:
        nw, nh = w, round(w / ratio)
    else:
        nw, nh = round(h * ratio), h
    canvas = Image.new("RGB", (nw, nh), bg)
    canvas.paste(img, ((nw - w) // 2, (nh - h) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG", dpi=(300, 300))
    return out.getvalue()


def _story_parts(document):
    from docx.parts.story import StoryPart

    seen = set()
    for rel in [document.part, *[r.target_part for r in document.part.rels.values() if not r.is_external]]:
        if isinstance(rel, StoryPart) and id(rel) not in seen:
            seen.add(id(rel))
            yield rel


def _replace_frames(part, row: RowBarcodes, images: dict) -> None:
    from docx.oxml.ns import qn

    for doc_pr in part.element.iter(qn("wp:docPr")):
        descr = doc_pr.get("descr") or ""
        m = re.fullmatch(r"JABCFRAME(\d+)X", descr)
        if not m:
            continue
        req = row.frames.get(int(m.group(1)))
        holder = doc_pr.getparent()                     # wp:inline / wp:anchor
        drawing = holder.getparent()                    # w:drawing
        if req is None or req.spec is None:
            drawing.getparent().remove(drawing)          # ข้อมูลว่าง → เอารูปตัวแทนออก
            continue
        ext = holder.find(qn("wp:extent"))
        ratio = int(ext.get("cx")) / max(1, int(ext.get("cy"))) if ext is not None else 0
        png = _pad_to_ratio(images[_spec_key(req.spec)], ratio, req.spec.bg_color)
        rid, _ = part.get_or_add_image(io.BytesIO(png))
        for blip in holder.iter(qn("a:blip")):
            blip.set(qn("r:embed"), rid)
            for child in list(blip):                    # ตัด extension (เช่น SVG ทางเลือก) ของรูปเดิม
                blip.remove(child)
        label = barcode_service.TYPES[req.spec.type].label
        doc_pr.set("descr", f"{label}: {req.spec.data[:200]}")


def _picture_run(part, r, png: bytes, req: Request):
    from docx.shared import Mm

    w_mm = req.width_mm or 25
    if req.height_mm:  # กำหนดทั้งกว้างและสูง = กรอบ → เติมขอบให้เต็มกรอบ ไม่บีบภาพ (ตัวเลขใต้บาร์โค้ดไม่เพี้ยน)
        png = _pad_to_ratio(png, w_mm / req.height_mm, req.spec.bg_color)
    img = Image.open(io.BytesIO(png))
    h_mm = req.height_mm or w_mm * img.height / img.width
    inline = part.new_pic_inline(io.BytesIO(png), Mm(w_mm), Mm(h_mm))
    run = deepcopy(r)
    for child in list(run):
        if child.tag != r.tag.replace("}r", "}rPr"):
            run.remove(child)
    run.add_drawing(inline)
    return run


def _text_run(r, text: str):
    from docx.oxml.ns import qn

    run = deepcopy(r)
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    t = run.makeelement(qn("w:t"), {})
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run.append(t)
    return run


def _replace_inline(part, row: RowBarcodes, images: dict) -> None:
    from docx.oxml.ns import qn

    for t in list(part.element.iter(qn("w:t"))):
        if not t.text or "@@JABC" not in t.text:
            continue
        r = t.getparent()
        if r.tag != qn("w:r"):
            continue
        pieces = _INLINE_RE.split(t.text)   # [ข้อความ, n, ข้อความ, n, ...]
        new_runs = []
        for k, piece in enumerate(pieces):
            if k % 2 == 0:
                if piece:
                    new_runs.append(_text_run(r, piece))
                continue
            req = row.inline[int(piece)]
            if req.spec is not None:
                new_runs.append(_picture_run(part, r, images[_spec_key(req.spec)], req))
        anchor = r
        for nr in new_runs:
            anchor.addnext(nr)
            anchor = nr
        r.getparent().remove(r)


def apply(docx_bytes: bytes, row: RowBarcodes, images: dict) -> bytes:
    import docx

    if not row.inline and not row.frames:
        return docx_bytes
    document = docx.Document(io.BytesIO(docx_bytes))
    for part in _story_parts(document):
        _replace_frames(part, row, images)
        _replace_inline(part, row, images)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
