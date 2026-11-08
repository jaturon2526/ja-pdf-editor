"""ตำแหน่งไฟล์ PDF ของ FileRecord (ไฟล์ในหน้า Dashboard) บนดิสก์ — ใช้ที่เดียวทุกจุด

ประวัติรูปแบบชื่อไฟล์ (ไฟล์เก่ายังอยู่บนดิสก์ จึงต้องอ่านได้ทุกแบบ):
- เดิม: `{storage_path}_{ชื่อไฟล์}` — ชื่อไทยยาวทำให้เกิด "[Errno 36] File name too long" และพอผู้ใช้
  เปลี่ยนชื่อไฟล์ใน Dashboard ชื่อบนดิสก์ก็ไม่ตรงกับ FileRecord.filename อีกต่อไป
- upload (ตั้งแต่ commit 840b968): `{storage_path}.pdf`
- บันทึกการแก้ไข (Save): `{storage_path}_saved.pdf` — ชื่อคงที่ ไม่ขึ้นกับชื่อไฟล์

เดิมแต่ละจุดเดาชื่อไฟล์เอง: แปลง PDF→Word หาแค่แบบ `{id}_{ชื่อ}` จึงไม่เจอไฟล์ที่ upload ใหม่ ("ไม่พบ
ไฟล์ต้นฉบับบนเซิร์ฟเวอร์") และการเปิดไฟล์ซ้ำหยิบ `{id}.pdf` ก่อน ทำให้การแก้ไขที่กด Save ไว้หายไป
ตอนนี้ทุกจุดใช้ resolve_stored_pdf() ซึ่งเลือก "ไฟล์ที่แก้ไขล่าสุด" จากทุกรูปแบบ
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import settings


def saved_path(storage_path: str) -> Path:
    """ที่เก็บไฟล์หลังกด Save (บันทึกการแก้ไขลงไฟล์ในบัญชี)"""
    return settings.UPLOAD_DIR / f"{storage_path}_saved.pdf"


def upload_path(storage_path: str) -> Path:
    """ที่เก็บไฟล์ใหม่ (upload / save as copy)"""
    return settings.UPLOAD_DIR / f"{storage_path}.pdf"


def previous_path(storage_path: str) -> Path:
    """สำเนาก่อนบันทึกครั้งล่าสุด (เวอร์ชันก่อนหน้า 1 ชุด — ใช้ "เทียบกับเวอร์ชันก่อนหน้า") · ไม่อยู่ใน candidate_paths
    จึงไม่ถูกเลือกเป็นไฟล์ปัจจุบัน · ไม่นับในพื้นที่ของผู้ใช้ (มีได้ชุดเดียวต่อไฟล์ และถูกแทนที่ทุกครั้งที่บันทึก)"""
    return settings.UPLOAD_DIR / f"{storage_path}_prev.pdf"


def keep_previous_version(record) -> None:
    """ก่อนบันทึกทับ: เก็บไฟล์ปัจจุบันไว้เป็นเวอร์ชันก่อนหน้า (ล้มเหลวไม่เป็นไร — การบันทึกสำคัญกว่า)"""
    import shutil

    current = resolve_stored_pdf(record)
    if current is None:
        return
    try:
        shutil.copy2(current, previous_path(record.storage_path))
    except OSError:
        pass


def move_previous_version(old_storage: str, new_storage: str) -> None:
    """เปิดไฟล์ซ้ำแล้ว storage_path เปลี่ยน — ย้ายเวอร์ชันก่อนหน้าตามไปด้วย"""
    old = previous_path(old_storage)
    if _exists(old):
        try:
            old.replace(previous_path(new_storage))
        except OSError:
            pass


def resolve_previous_pdf(record) -> Optional[Path]:
    p = previous_path(record.storage_path)
    return p if _exists(p) else None


def candidate_paths(storage_path: str, *names: Optional[str]) -> list[Path]:
    """ทุกตำแหน่งที่ไฟล์ของ storage_path นี้อาจอยู่ (ไม่สนว่ามีอยู่จริงหรือไม่)"""
    paths = [saved_path(storage_path), upload_path(storage_path), settings.WORKING_DIR / f"{storage_path}.pdf"]
    for name in names:
        if not name:
            continue
        safe = Path(name).name
        for directory in (settings.UPLOAD_DIR, settings.WORKING_DIR):
            try:
                paths.append(directory / f"{storage_path}_{safe}")
            except ValueError:
                continue
    seen, unique = set(), []
    for p in paths:
        if str(p) not in seen:
            seen.add(str(p))
            unique.append(p)
    return unique


def _exists(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:  # เช่น ชื่อไฟล์ยาวเกินที่ระบบไฟล์รับได้
        return False


def resolve_stored_pdf(record) -> Optional[Path]:
    """ไฟล์ PDF ปัจจุบันของ FileRecord — เลือกไฟล์ใน UPLOAD_DIR ที่แก้ไขล่าสุด (mtime ใหม่สุด)

    WORKING_DIR ใช้เป็นทางสุดท้ายเท่านั้น: ไฟล์ในนั้นคือ working copy ของ session ที่อาจมีการแก้ไขที่ผู้ใช้
    ยังไม่ได้กด Save (ไม่ควรถูกเลือกแทนไฟล์ที่บันทึกไว้)"""
    existing = [p for p in candidate_paths(record.storage_path, record.filename, record.original_filename) if _exists(p)]
    if not existing:
        return None
    uploads = [p for p in existing if p.parent == settings.UPLOAD_DIR]
    return max(uploads or existing, key=lambda p: p.stat().st_mtime)


def all_existing_paths(record) -> list[Path]:
    """ไฟล์ทุกเวอร์ชันของ FileRecord ที่มีอยู่บนดิสก์ (ใช้ตอนลบไฟล์) — รวมเวอร์ชันก่อนหน้า"""
    paths = candidate_paths(record.storage_path, record.filename, record.original_filename) + [previous_path(record.storage_path)]
    return [p for p in paths if _exists(p)]


def remove_stored_copies(storage_path: str, *names: Optional[str]) -> int:
    """ลบไฟล์ของ storage_path เดิมใน UPLOAD_DIR (ใช้หลังเปิดไฟล์ซ้ำแล้ว FileRecord ย้ายไป storage_path ใหม่)"""
    removed = 0
    for p in candidate_paths(storage_path, *names):
        if p.parent == settings.UPLOAD_DIR and _exists(p):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


import re as _re  # noqa: E402

_STORED_NAME = _re.compile(r"^([0-9a-f]{32})(?:_.+)?\.pdf$")


def cleanup_unreferenced_files(db, max_age_hours: float = 24.0, active_ids: set[str] | None = None) -> int:
    """ลบไฟล์ PDF ใน UPLOAD_DIR (เฉพาะชั้นบนสุด ชื่อแบบ `<id 32 หลัก>.pdf` / `<id>_saved.pdf` / `<id>_<ชื่อ>`)
    ที่ไม่มี FileRecord ไหนอ้างอิงแล้ว และเก่ากว่า max_age_hours

    เดิมทุกครั้งที่เปิดไฟล์จากเอกสารของฉัน (หลัง session หมดอายุ) ระบบคัดลอกไฟล์เป็นชุดใหม่แล้วทิ้งชุดเดิมไว้บนดิสก์
    ตลอดไป — ดิสก์โตเรื่อย ๆ และไฟล์ที่ผู้ใช้ลบ (หรือลบบัญชี) ยังมีสำเนาเก่าค้างอยู่ · โฟลเดอร์ย่อย (_signing, users,
    _conversions) ไม่ถูกแตะ ยกเว้นไฟล์ Word ใน _conversions ที่เก่ากว่า max_age_hours"""
    import time

    from app.models.domain import FileRecord

    referenced = {sp for (sp,) in db.query(FileRecord.storage_path).all()} | set(active_ids or ())
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    # ไฟล์ Word ที่แปลงแล้ว (ดาวน์โหลดได้ภายใน 24 ชม.) — เดิมเก็บทุกไฟล์ตลอดไป
    conv = settings.UPLOAD_DIR / "_conversions"
    try:
        for f in conv.iterdir() if conv.is_dir() else []:
            try:
                if f.is_file() and f.suffix == ".docx" and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    try:
        entries = list(settings.UPLOAD_DIR.iterdir())
    except OSError:
        return 0
    for f in entries:
        m = _STORED_NAME.match(f.name)
        if not m or m.group(1) in referenced:
            continue
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed
