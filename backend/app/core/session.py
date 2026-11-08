"""
SessionManager — ตัวกลางเก็บสถานะไฟล์ PDF ที่กำลังถูกเปิด/แก้ไขอยู่

แนวคิด:
- ผู้ใช้ upload ไฟล์ -> ได้ session_id กลับมา
- ทุก endpoint ถัดไป (render/annotate/edit) อ้างอิงด้วย session_id เท่านั้น
- fitz.Document ที่เปิดค้างไว้อยู่ใน memory ของ process นี้ (เหมาะกับ single-instance dev server
  ถ้า deploy จริงแบบ multi-worker ต้องย้ายไปเก็บ state ที่ shared store เช่น redis + เปิดไฟล์ใหม่ทุกครั้งแทน)

เรื่อง Undo/Redo: ผู้ใช้แจ้งว่าเมนู Edit > Undo/Redo ต้องใช้ได้จริงทั้งกับการแก้ไข Annotations และ
Edit PDF (ข้อความ/รูปภาพ) — เนื่องจากการแก้ข้อความ/รูปภาพเป็นแบบ "redact แล้ววาดใหม่" (ทำลายข้อมูลเดิม
ทิ้งถาวร ไม่มี inverse operation ง่ายๆ แบบ undo ทีละคำสั่ง) จึงเลือกใช้วิธี "จำสถานะทั้งเอกสารเป็น snapshot"
แทนการเก็บ inverse operation ทีละชนิด: ทุกครั้งที่มีการแก้ไขสำเร็จ (annotation add/update/delete, text
edit, image insert/replace/reposition) จะเรียก push_history() เก็บสำเนาไบต์ทั้งไฟล์ ณ ตอนนั้น (รวมถึง
ทะเบียน text_edits ที่ผูกกับสถานะเอกสารตอนนั้นด้วย — ไม่งั้น undo/redo แล้ว get_text_blocks() จะเห็น
ย่อหน้าที่แก้ไปแล้ว "ไม่ตรง" กับสถานะจริงของเอกสารที่ถูกย้อนกลับไป) ไว้ใน session.history เป็น stack
พร้อม history_pos ชี้ตำแหน่งปัจจุบัน — undo() ถอยตำแหน่งแล้วโหลดเอกสารจาก snapshot นั้นใหม่ redo()
เดินหน้าตำแหน่งแล้วโหลดใหม่เช่นกัน จำกัดจำนวน snapshot ไว้ (กันหน่วยความจำบวมถ้าผู้ใช้แก้ไขเยอะมากใน
เซสชันเดียว) — เก่ากว่านั้นจะ undo กลับไปไม่ได้อีก (จำกัดแค่ช่วงล่าสุด)

ข้อสำคัญ (แก้ไขรอบนี้ — เดิม push_history()/_restore_from_history() ใช้ doc.tobytes() /
fitz.open(stream=...) ล้วนๆ): session.doc ต้องเปิดจาก "ไฟล์จริงบนดิสก์" (session.working_path) เสมอ
ทุกจุดในโค้ด ไม่ใช่จาก in-memory stream เลย เพราะ (1) fitz.Document.saveIncr() (ใช้ตอน
save_working_copy()/ดาวน์โหลด) ต้องการให้เอกสารเปิดจากไฟล์จริงเท่านั้น ("incremental needs original
file") เปิดจาก stream แล้วจะดาวน์โหลดไม่ได้อีกเลย และ (2) เอกสารที่มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่
ต้องแก้ไขต่อแบบ incremental (saveIncr()) เท่านั้นถึงจะรักษาลายเซ็นเดิมให้ยัง valid อยู่ — ถ้าใช้
doc.tobytes() (full rewrite) แม้แต่ครั้งเดียวจะทำให้ลายเซ็นเดิมเสียทันที ดังนั้น push_history() จึงเซฟ
ด้วย doc.saveIncr() แล้วอ่านไบต์จากไฟล์จริงกลับมาเก็บใน snapshot (ไม่ใช้ tobytes()) และ
_restore_from_history() จึงเขียนไบต์ snapshot ทับ working_path แล้วเปิดใหม่ด้วย fitz.open(path) เสมอ
(ไม่ใช้ stream) — ผลพลอยได้: undo/redo แล้วดาวน์โหลดทันทีจะไม่ crash อีกต่อไป (บั๊กเดิมที่พบระหว่าง
การแก้ไขรอบนี้)
"""
from __future__ import annotations

import copy
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF

from app.core.config import settings

logger = logging.getLogger("session")

# จำนวน snapshot สูงสุดที่เก็บไว้ต่อ session (undo ย้อนได้ไกลสุดเท่านี้ก้าว) — แต่ละ snapshot คือไบต์
# ทั้งไฟล์ PDF ทั้งฉบับ ณ ตอนนั้น ถ้าเก็บไม่จำกัดจะกินหน่วยความจำมากถ้าผู้ใช้แก้ไขเยอะในเซสชันเดียว
_HISTORY_LIMIT = 25


@dataclass
class _HistoryEntry:
    """หนึ่งจุดใน undo/redo stack — เก็บทั้งไบต์เอกสาร ณ ตอนนั้น และสำเนาทะเบียน text_edits ที่ตรงกัน
    (ดูหมายเหตุ Undo/Redo ด้านบนของไฟล์ — ทั้งสองต้องย้อนกลับไปพร้อมกันเสมอ ไม่งั้นจะไม่ตรงกัน)"""

    doc_bytes: bytes
    text_edits: dict
    # ---------- สถานะการเซ็นเอกสาร (เมนู Digital Signature — ผู้ใช้แจ้งขอ) ----------
    # ต้องย้อนกลับไปพร้อมกับเนื้อหาเอกสารเสมอเวลา undo/redo เหมือน text_edits ด้านบน ไม่งั้น undo
    # การเซ็นแล้วเอกสารจะยังถูกล็อกอยู่ (หรือ redo กลับไปเป็นเอกสารที่เซ็นแล้วแต่ระบบคิดว่ายังไม่ได้เซ็น)
    is_signed: bool = False
    signature_type: Optional[str] = None  # "electronic" | "digital" | None
    # เฉพาะ digital sign เท่านั้นที่มีค่า — ใช้เป็น flag บอกว่า "ตอน snapshot นี้ เอกสารมีลายเซ็นดิจิทัล
    # (PAdES) ฝังอยู่แล้ว" (ดูการใช้งานใน pdf_service.add_password()/reorder_pages() ที่กันไม่ให้ทำ
    # ปฏิบัติการที่ไม่ใช่ incremental ต่อ) ไม่ได้ใช้เป็นทางลัด bypass การดาวน์โหลดอีกต่อไป (แก้ไขรอบนี้ —
    # เดิม get_download_path คืนค่านี้ตรงๆ แทน doc_bytes เพราะ doc_bytes ตอนนั้นมาจาก doc.tobytes() ซึ่ง
    # ไม่ตรงกับไบต์ที่ลายเซ็นครอบคลุม แต่ตอนนี้ doc_bytes มาจาก doc.saveIncr() แล้วอ่านจากไฟล์จริงเสมอ จึง
    # เป็นไบต์เดียวกับที่ signed_pdf_bytes เคยเก็บไว้อยู่แล้วโดยธรรมชาติ ไม่ต้องแยกใช้อีก)
    signed_pdf_bytes: Optional[bytes] = None
    # ลำดับเลขเพิ่มขึ้นเรื่อยๆ ต่อ session — ใช้เป็นชื่อ key ใน Redis (session:{sid}:hist:{seq}) แทนตำแหน่งใน
    # stack ซึ่งเลื่อนทุกครั้งที่ตัดประวัติเก่าทิ้ง (ดู RedisSessionManager._sync_to_redis)
    seq: int = 0


class SessionBusyError(RuntimeError):
    """รอ lock ของ session นานเกินกำหนด (มี request อื่น/pod อื่นกำลังแก้ไขเอกสารเดียวกันอยู่)"""


class SessionLock:
    """ตัวล็อกของ PDFSession ใช้แทน threading.Lock แบบเดิมได้ทันที (`with session.lock:`)

    - โหมดปกติ (InMemorySessionManager): ทำงานเหมือน threading.Lock ทุกอย่าง — กัน request พร้อมกัน
      ใน process เดียวเข้าถึง fitz.Document ตัวเดียวกัน (PyMuPDF ไม่ thread-safe)
    - โหมด Redis (RedisSessionManager ผูกไว้ผ่าน bind()): ถือ Redis lock ด้วย จึงกันได้ข้าม process/
      replica และตอนเข้าล็อกจะโหลดสถานะล่าสุดจาก Redis + shared storage ถ้า pod อื่นเพิ่งแก้ไขไป
      ตอนออกจากล็อกถ้าสถานะเปลี่ยน จะ flush ลงดิสก์ + sync ขึ้น Redis + เพิ่มเลข version ให้ pod อื่นรู้
    """

    def __init__(self) -> None:
        self._local = threading.Lock()
        self._manager = None
        self._session: Optional["PDFSession"] = None
        self._redis_lock = None
        self._fingerprint = None

    def bind(self, manager, session: "PDFSession") -> None:
        self._manager = manager
        self._session = session

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if not self._local.acquire(blocking, timeout):
            return False
        if self._manager is None:
            return True
        try:
            self._redis_lock = self._manager._acquire_distributed_lock(self._session)
            self._manager._refresh_if_stale(self._session)
            self._fingerprint = self._session._state_fingerprint()
        except BaseException:
            self._release_redis_lock()
            self._local.release()
            raise
        return True

    def release(self) -> None:
        try:
            if self._manager is not None and self._session is not None:
                try:
                    if self._session._state_fingerprint() != self._fingerprint or self._session._doc_dirty:
                        self._manager._publish_changes(self._session)
                except Exception:
                    logger.warning("sync session %s ไป Redis ไม่สำเร็จ", self._session.session_id, exc_info=True)
        finally:
            self._release_redis_lock()
            self._local.release()

    def _release_redis_lock(self) -> None:
        lock, self._redis_lock = self._redis_lock, None
        if lock is not None:
            try:
                lock.release()
            except Exception:
                # lock หมดอายุไปเองแล้ว (งานนานเกิน timeout) — ไม่ต้องทำอะไร
                logger.warning("ปล่อย Redis lock ไม่สำเร็จ (อาจหมดอายุแล้ว) session=%s",
                               self._session.session_id if self._session else "?", exc_info=True)

    def locked(self) -> bool:
        return self._local.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


@dataclass
class PDFSession:
    session_id: str
    original_path: Path
    working_path: Path
    doc: Optional[fitz.Document] = None
    is_unlocked: bool = False
    original_filename: str = ""
    user_id: Optional[int] = field(default=None, compare=False, repr=False)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)
    # ล็อกเฉพาะของ session นี้ — กัน request พร้อมกัน (เช่น render หน้า/ขนาดจริง กับ render thumbnail
    # ที่ frontend ยิงเกือบพร้อมกันหลัง unlock) เข้าถึง fitz.Document ตัวเดียวกันจากคนละ thread
    # พร้อมกัน ซึ่ง PyMuPDF/MuPDF ไม่ thread-safe (ตัว lib เองแนะนำให้ใช้ multiprocessing หรือ lock
    # เอง) — ถ้าไม่ล็อก จะเกิด corruption แบบ "zlib error: incorrect header check" /
    # "read error; treating as end of file" ตอน decode หน้าแบบสุ่ม ๆ แม้ authenticate ผ่านแล้วก็ตาม
    lock: SessionLock = field(default_factory=SessionLock, compare=False, repr=False)
    # ทะเบียนย่อหน้าที่เคยถูกแก้ไขไปแล้วในเซสชันนี้ คีย์ชั้นนอกคือเลขหน้า คีย์ชั้นในคือ edit_id
    # (รูปแบบ "edit-<hex>") ค่าคือ dict ของ rect/text/fontname/fontsize/color_int ล่าสุด
    # ใช้แก้บั๊ก "แก้ไขย่อหน้าเดิมซ้ำไม่ได้" — เพราะย่อหน้าที่แก้ไปแล้วจะกลายเป็นรูปภาพ (ไม่ใช่ text
    # block ของ PyMuPDF อีกต่อไป) get_text_blocks() ปกติจะมองไม่เห็น จึงต้องพึ่งทะเบียนนี้แทนเพื่อให้
    # ยังคลิกเลือกกลับมาแก้ไขต่อได้เรื่อยๆ (ดูรายละเอียดที่ app/services/edit_service.py หมายเหตุ
    # "แก้บั๊กสำคัญ #6")
    text_edits: dict[int, dict[str, dict]] = field(default_factory=dict, compare=False, repr=False)
    # undo/redo stack (ดูหมายเหตุ Undo/Redo ด้านบนของไฟล์)
    history: list[_HistoryEntry] = field(default_factory=list, compare=False, repr=False)
    history_pos: int = field(default=-1, compare=False, repr=False)
    # ---------- จัดการรหัสผ่าน (Remove/Add Password จากเมนู File — ผู้ใช้แจ้งขอ) ----------
    # ค่าเริ่มต้น (encryption_touched=False) แปลว่ายังไม่เคยกด Remove/Add Password ในเซสชันนี้เลย —
    # สถานะ "มีรหัสผ่านป้องกันอยู่ไหม" ตอนนี้จึงต้องดูจากไฟล์ต้นฉบับ (original_path) แทน (ดู
    # pdf_service.get_encryption_state) พอผู้ใช้กด Remove/Add Password ครั้งแรก จะ set เป็น True
    # แล้วยึดตาม output_password ที่ตั้งไว้ล่าสุดเสมอ ไม่ต้องเช็คไฟล์ต้นฉบับอีกต่อไป — output_password
    # ไม่ใช่รหัสผ่านสำหรับ "ปลดล็อกเพื่อแก้ไข" (นั่นคือ /unlock ไปแล้ว เอกสารในหน่วยความจำไม่เข้ารหัส
    # เสมอ) แต่เป็นรหัสผ่านที่จะ "ใส่ตอนสร้างไฟล์สำหรับดาวน์โหลด" เท่านั้น (ดู
    # pdf_service.get_download_path) — None แปลว่าดาวน์โหลดแบบไม่เข้ารหัส
    output_password: Optional[str] = field(default=None, compare=False, repr=False)
    encryption_touched: bool = field(default=False, compare=False, repr=False)
    # วิธีเข้ารหัสตอนดาวน์โหลด: "aes256" (ค่าเริ่มต้น) | "aes128" (เข้ากันได้กับโปรแกรมรุ่นเก่า) — ดู pdf_service.encrypt_pdf_file
    output_encryption: str = field(default="aes256", compare=False, repr=False)
    # ---------- เมนู Digital Signature (Electronic Sign / Digital Sign — ผู้ใช้แจ้งขอ) ----------
    # is_signed/signature_type/signed_pdf_bytes เป็นข้อมูล "สถานะ" ของเอกสารเท่านั้น (ใช้โชว์ผลใน UI
    # เช่น badge "เซ็นแล้ว") — ผู้ใช้แจ้งว่าไม่ต้องการให้เซ็นแล้ว "ล็อก" เอกสารอีกต่อไป ทั้ง Electronic
    # Sign (ต้องยังคลิกกลับมาย้าย/แก้ไขตำแหน่งลายเซ็นได้ปกติ — ใช้กลไกเดียวกับแก้ไขรูปภาพทั่วไป) และ
    # Digital Sign (เอกสารอาจต้องส่งต่อให้อีกคนเซ็นซ้อนเป็นลำดับถัดไป จึงห้ามล็อกไฟล์) service ที่แก้ไข
    # เนื้อหาเอกสารทุกตัวจึงใช้ require_unlocked() เหมือนเดิมปกติ ไม่มี is_signed มาบล็อกอีกต่อไป
    # (ข้อยกเว้นทางเทคนิคจริงที่ยังกันอยู่ 2 จุด — ไม่ใช่การล็อกตามใจ — ดู pdf_service.add_password()/
    # reorder_pages(): ห้ามเข้ารหัส PDF หรือสลับลำดับหน้าถ้ามีลายเซ็นดิจิทัลฝังอยู่ เพราะทั้งสองปฏิบัติการ
    # ต้อง rebuild เอกสารใหม่ทั้งหมด ไม่ใช่ incremental จะทำให้ลายเซ็นเดิมเสียหาย) signed_pdf_bytes ไม่ใช่
    # None แปลว่า "เอกสารนี้มีลายเซ็นดิจิทัลฝังอยู่ในสาขา undo ปัจจุบัน" — ย้อนกลับไปพร้อมกับเนื้อหา
    # เอกสารเสมอเวลา undo/redo (ดู _restore_from_history)
    is_signed: bool = field(default=False, compare=False, repr=False)
    signature_type: Optional[str] = field(default=None, compare=False, repr=False)
    signed_pdf_bytes: Optional[bytes] = field(default=None, compare=False, repr=False)
    # ---------- ติดตามว่า self.doc มีการแก้ไขค้างที่ยังไม่ได้ saveIncr() ลงดิสก์หรือไม่ ----------
    # (พบระหว่างแก้ไขรอบนี้ — บั๊กสำคัญของ MuPDF/PyMuPDF: เรียก doc.saveIncr() ติดกัน 2 ครั้งโดยไม่มีการ
    # แก้ไขเอกสารจริงคั่นกลางเลย จะทำให้ไฟล์เสียหายทันที เปิดกลับมาได้ 0 หน้า "cannot find object in
    # xref" — ทดสอบยืนยันแล้วว่าเกิดจริง ไม่ใช่แค่ทฤษฎี) เดิมไม่เป็นปัญหาเพราะ saveIncr() ถูกเรียกแค่จุด
    # เดียวคือตอนดาวน์โหลด (save_working_copy) แต่ตอนนี้ push_history()/apply_digital_signature() ก็
    # เรียก flush ลงดิสก์ด้วยเช่นกัน (ดูหมายเหตุ Undo/Redo ด้านล่าง) จึงต้องเช็ค "มีอะไรค้างจริงไหม" ก่อน
    # ทุกครั้งผ่าน flush_to_disk()/mark_dirty() ด้านล่างเสมอ ห้ามเรียก doc.saveIncr() ตรงๆ จากที่อื่นอีก
    _doc_dirty: bool = field(default=False, compare=False, repr=False)
    # callback ที่ RedisSessionManager inject ไว้เพื่อ sync state ไปยัง Redis หลัง push_history()
    # (InMemorySessionManager ไม่ set ค่านี้ — จะเป็น None ตลอด ไม่มีผลใดๆ)
    _on_history_push: Optional[Callable] = field(default=None, compare=False, repr=False)
    # เลข seq ถัดไปของ history entry และ version ล่าสุดที่ process นี้เห็นใน Redis (ใช้เฉพาะโหมด Redis)
    _next_seq: int = field(default=1, compare=False, repr=False)
    _seen_version: int = field(default=0, compare=False, repr=False)
    # นับทุกครั้งที่เนื้อหาเอกสารเปลี่ยนใน process นี้ (mark_dirty / undo-redo) — ใช้เป็น key ของ cache ภาพหน้า
    # ในโหมดไม่มี Redis (โหมด Redis ใช้ _seen_version ที่ทุก worker เห็นตรงกัน) ดู services/render_cache.py
    _render_rev: int = field(default=0, compare=False, repr=False)

    def _state_fingerprint(self) -> tuple:
        """สรุปสถานะที่ต้อง sync ข้าม process — ถ้าค่านี้เปลี่ยนระหว่างถือ lock ถือว่ามีการแก้ไข"""
        current = self.history[self.history_pos].seq if 0 <= self.history_pos < len(self.history) else None
        return (
            current,
            tuple(e.seq for e in self.history),
            self.output_password,
            self.output_encryption,
            self.encryption_touched,
            self.is_signed,
            self.signature_type,
            self.user_id,
            self.is_unlocked,
        )

    def touch(self) -> None:
        self.last_accessed_at = datetime.utcnow()

    # ---------- กันบั๊ก "saveIncr() ซ้อนกันโดยไม่มีการแก้ไขคั่น" (ดูหมายเหตุ _doc_dirty ด้านบน) ----------

    def mark_dirty(self) -> None:
        """เรียกจากทุก service ที่แก้ไขเนื้อหา self.doc จริงๆ (annotation/text edit/image/bookmark/
        reorder หน้า) ทันทีหลังแก้ไขสำเร็จ ก่อน push_history() เสมอ — บอกว่ามีการเปลี่ยนแปลงค้างที่ยังไม่
        ได้ saveIncr() ลงดิสก์ ให้ flush_to_disk() รู้ว่าต้องเรียก doc.saveIncr() จริง (ไม่ใช่ no-op)"""
        self._doc_dirty = True
        self._render_rev += 1

    def flush_to_disk(self) -> None:
        """เขียนการเปลี่ยนแปลงของ self.doc ทับ working_path ด้วย doc.saveIncr() — "เฉพาะตอนที่มีการ
        เปลี่ยนแปลงค้างจริง" (self._doc_dirty) เท่านั้น ถ้าไม่มีอะไรค้าง (เช่น เรียกซ้ำติดกัน หรือเพิ่งเปิด/
        กู้คืนเอกสารมาสดๆ ยังไม่มีใครแก้ไขอะไรเลย) จะข้ามไปเฉยๆ ไม่เรียก saveIncr() ซ้ำ (ดูหมายเหตุ
        _doc_dirty ด้านบนว่าทำไมจำเป็นต้องเช็คแม่นยำแบบนี้ ไม่ใช่แค่เรียกเผื่อไว้)

        หลัง saveIncr() สำเร็จ จะปิดแล้วเปิด self.doc ใหม่จาก working_path ทันที (ไม่ใช้ doc object เดิม
        ต่อ) — ทดสอบพบบั๊กจริงของ MuPDF/PyMuPDF (เวอร์ชันที่ pin ไว้) ระหว่างแก้ไขฟีเจอร์นี้: ถ้าเปิด doc
        object เดิมค้างไว้แล้วแก้ไข+saveIncr() ต่อเนื่องกันหลายรอบโดยไม่ปิด/เปิดใหม่เลย โดยเฉพาะ pattern
        "ลบ annotation เดิมแล้วสร้างใหม่" ที่ update_annotation()/apply_electronic_signature() (ผ่าน
        insert_image ถ้าทำซ้ำ) ใช้ประจำ จะทำให้ xref ของไฟล์เพี้ยน (เปิดกลับมาต้อง "repair" แล้วหลังจากนั้น
        saveIncr() บนไฟล์เดิมจะ error ถาวร "Can't do incremental writes on a repaired file") ทดสอบยืนยัน
        แล้วว่าถ้าปิดแล้วเปิด doc ใหม่จากไฟล์จริงหลัง saveIncr() ทุกครั้ง ปัญหานี้จะไม่เกิดเลยแม้แก้ไขต่อ
        กันกี่รอบก็ตาม จึงทำเป็นมาตรฐานตรงนี้จุดเดียว (ค่าใช้จ่ายเพิ่มน้อยมากเทียบกับความเสี่ยงไฟล์เสีย)
        """
        if self.doc is None or not self._doc_dirty:
            return
            
        # พยายามเก็บรักษาและอัปเดต Metadata ก่อนเซฟ
        try:
            meta = self.doc.metadata or {}
            # อัปเดตเฉพาะวันที่แก้ไข (Modification Date) เป็นเวลาปัจจุบัน
            meta["modDate"] = fitz.get_pdf_now()
            # ใส่ชื่อ Producer ของแอปเราต่อท้ายถ้ายังไม่มี
            old_producer = meta.get("producer") or ""
            if "PDF Editor" not in old_producer:
                meta["producer"] = f"{old_producer} (Modified by JA PDF Editor)".strip()
                
            self.doc.set_metadata(meta)
        except Exception as e:
            pass
            
        self.doc.saveIncr()
        self._doc_dirty = False
        self.doc.close()
        self.doc = fitz.open(self.working_path)

    # ---------- Undo / Redo ----------

    def push_history(self) -> None:
        """เรียกทันทีหลังการแก้ไขสำเร็จทุกครั้ง (annotation add/update/delete, text edit, image
        insert/replace/reposition) — เก็บ snapshot สถานะปัจจุบันไว้ ตัดกิ่ง redo เดิมทิ้ง (ถ้าเพิ่ง
        undo แล้วมาแก้ไขใหม่ กิ่ง redo เดิมจะไม่ valid อีกต่อไป — พฤติกรรมมาตรฐานของ undo/redo ทั่วไป)

        ใช้ flush_to_disk() (ซึ่งข้างในเรียก doc.saveIncr() "เฉพาะตอนมีการแก้ไขค้างจริง" — ดูหมายเหตุ
        _doc_dirty ด้านบน กันบั๊ก saveIncr() ซ้อนกันไม่มีอะไรเปลี่ยนแล้วไฟล์พัง) แล้วอ่านไบต์จากไฟล์จริง
        (working_path) กลับมาเก็บใน snapshot — "ไม่ใช้" doc.tobytes() (full rewrite) เพราะจะทำให้ลายเซ็น
        ดิจิทัล (PAdES) ที่อาจฝังอยู่แล้วเสียหายทันที (ดูหมายเหตุยาวหัวไฟล์) doc.saveIncr() ต้องการให้
        self.doc เปิดจากไฟล์จริงเสมอ (ไม่ใช่ stream) ซึ่งเป็นจริงเสมอในทุกจุดของโค้ดแล้ว (ดู
        pdf_service.py / _restore_from_history ด้านล่าง)
        """
        if self.doc is None:
            return
        try:
            self.flush_to_disk()
            data = self.working_path.read_bytes()
        except Exception:
            logger.warning("push_history: บันทึกสถานะเอกสารไม่สำเร็จ session=%s", self.session_id, exc_info=True)
            return
        entry = _HistoryEntry(
            doc_bytes=data,
            text_edits=copy.deepcopy(self.text_edits),
            is_signed=self.is_signed,
            signature_type=self.signature_type,
            signed_pdf_bytes=self.signed_pdf_bytes,
            seq=self._next_seq,
        )
        self._next_seq += 1
        self.history = self.history[: self.history_pos + 1]
        self.history.append(entry)
        if len(self.history) > _HISTORY_LIMIT:
            overflow = len(self.history) - _HISTORY_LIMIT
            self.history = self.history[overflow:]
        self.history_pos = len(self.history) - 1
        # แจ้ง RedisSessionManager ให้ sync state ไปยัง Redis (ถ้ามี callback)
        if self._on_history_push is not None:
            try:
                self._on_history_push(self)
            except Exception:
                logger.warning(
                    "push_history: sync Redis ล้มเหลว session=%s", self.session_id, exc_info=True
                )

    def can_undo(self) -> bool:
        return self.history_pos > 0

    def can_redo(self) -> bool:
        return self.history_pos < len(self.history) - 1

    def undo(self) -> bool:
        if not self.can_undo():
            return False
        self.history_pos -= 1
        self._restore_from_history()
        return True

    def redo(self) -> bool:
        if not self.can_redo():
            return False
        self.history_pos += 1
        self._restore_from_history()
        return True

    def _restore_from_history(self) -> None:
        """โหลดสถานะเอกสารกลับจาก snapshot — เขียนไบต์ทับ working_path บนดิสก์แล้วเปิดจาก "ไฟล์จริง"
        เสมอ (fitz.open(path), ไม่ใช่ fitz.open(stream=...)) เพื่อให้ doc.saveIncr() (ใช้ทั้งตอน
        push_history() ครั้งถัดไป และตอนดาวน์โหลด — ดู pdf_service.save_working_copy) ยังใช้งานได้ต่อ
        ไปเรื่อยๆ ไม่ crash (เดิมเปิดจาก stream ทำให้ saveIncr() หลังจากนี้ throw
        "incremental needs original file" ทันทีที่มีการดาวน์โหลดหลัง undo/redo — บั๊กที่พบระหว่างแก้ไข
        รอบนี้)"""
        entry = self.history[self.history_pos]
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.working_path.write_bytes(entry.doc_bytes)
        self.doc = fitz.open(self.working_path)
        self._doc_dirty = False  # เพิ่งเขียน/เปิดใหม่จากไฟล์เดียวกันเป๊ะๆ ไม่มีอะไรค้างให้ flush อีก
        self._render_rev += 1
        self.text_edits = copy.deepcopy(entry.text_edits)
        self.is_signed = entry.is_signed
        self.signature_type = entry.signature_type
        self.signed_pdf_bytes = entry.signed_pdf_bytes


class InMemorySessionManager:
    """SessionManager แบบดั้งเดิม — เก็บทุกอย่างใน process memory (single-instance เท่านั้น)"""

    def __init__(self) -> None:
        self._sessions: dict[str, PDFSession] = {}
        self._lock = threading.Lock()

    def create_session(self, original_path: Path, working_path: Path, original_filename: str, user_id: Optional[int] = None, session_id: Optional[str] = None) -> PDFSession:
        session_id = session_id or uuid.uuid4().hex
        session = PDFSession(
            session_id=session_id,
            original_path=original_path,
            working_path=working_path,
            original_filename=original_filename,
            user_id=user_id,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def save(self, session: PDFSession) -> None:
        """โหมด in-memory ไม่ต้อง sync ไปไหน (มีไว้ให้ interface ตรงกับ RedisSessionManager)"""

    def get(self, session_id: str) -> Optional[PDFSession]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def close(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return
        if session.doc is not None:
            try:
                session.doc.close()
            except Exception:
                pass
        # ลบไฟล์ต้นฉบับ + working copy บนดิสก์คู่กับ session ที่ปิด/หมดอายุไปด้วย (ข้อ "Backend ->
        # Cleanup ข้อมูลที่มากกว่า 24 ชั่วโมง" ที่ผู้ใช้แจ้งไว้) — ไม่งั้นไฟล์จะค้างอยู่ใน
        # storage/uploads กับ storage/working ตลอดไปแม้ session ในหน่วยความจำจะถูกเคลียร์แล้วก็ตาม
        for p in (session.working_path,): # Keep original_path for Dashboard
            try:
                if p and Path(p).exists():
                    Path(p).unlink()
            except Exception:
                logger.warning("ลบไฟล์ค้างไม่สำเร็จ: %s", p)

    def cleanup_expired(self) -> int:
        """เคลียร์ session ที่ไม่ได้ใช้งานเกิน TTL (ดีฟอลต์ 24 ชม. — settings.SESSION_TTL_MINUTES)
        พร้อมไฟล์บนดิสก์คู่กัน (ดู close()) — เรียกเป็นระยะจาก background task ใน main.py"""
        cutoff = datetime.utcnow() - timedelta(minutes=settings.SESSION_TTL_MINUTES)
        expired_ids = []
        with self._lock:
            for sid, s in self._sessions.items():
                if s.last_accessed_at < cutoff:
                    expired_ids.append(sid)
        for sid in expired_ids:
            self.close(sid)
        return len(expired_ids)

    def cleanup_orphan_files(self, max_age_hours: float = 24.0) -> int:
        """เก็บกวาดไฟล์ค้างในโฟลเดอร์ upload/working บนดิสก์ที่ "ไม่มี session อยู่ในหน่วยความจำแล้ว"
        (เช่น เซิร์ฟเวอร์ถูกรีสตาร์ท ทำให้ session ในหน่วยความจำหายไปหมดแต่ไฟล์บนดิสก์ยังค้างอยู่ —
        cleanup_expired() ด้านบนเคลียร์ไม่ถึงเพราะเช็คจาก session ในหน่วยความจำเท่านั้น) และเก่ากว่า
        max_age_hours ชั่วโมง — ข้ามไฟล์ที่ session ที่ยังทำงานอยู่ตอนนี้อ้างอิงอยู่เสมอ กันลบไฟล์ที่
        กำลังใช้งานจริงโดยไม่ตั้งใจ"""
        cutoff_ts = (datetime.utcnow() - timedelta(hours=max_age_hours)).timestamp()
        with self._lock:
            active_paths = set()
            for s in self._sessions.values():
                active_paths.add(str(s.original_path))
                active_paths.add(str(s.working_path))

        removed = 0
        for directory in (settings.WORKING_DIR,): # Keep UPLOAD_DIR for Dashboard
            try:
                if not Path(directory).is_dir():
                    continue
                for f in Path(directory).iterdir():
                    if not f.is_file() or str(f) in active_paths:
                        continue
                    try:
                        if f.stat().st_mtime < cutoff_ts:
                            f.unlink()
                            removed += 1
                    except Exception:
                        continue
            except Exception:
                logger.warning("เก็บกวาดไฟล์ค้างในโฟลเดอร์ %s ไม่สำเร็จ", directory)
        return removed


class RedisSessionManager:
    """
    SessionManager ที่ใช้ Redis เป็น shared store — รองรับ multi-instance deployment (หลาย pod/worker)

    fitz.Document ยังอยู่ใน process memory ของแต่ละ pod (เปิดจากไฟล์บน shared storage) ส่วน metadata,
    text_edits และ undo history เก็บใน Redis ให้ pod อื่นเข้าถึงได้

    ความสอดคล้องข้าม pod (ดู SessionLock):
    - `with session.lock:` ถือ Redis lock (session:{sid}:lock) → แก้ไขเอกสารเดียวกันได้ทีละ request ทั้งคลัสเตอร์
    - ทุกครั้งที่สถานะเปลี่ยนภายใต้ lock จะเพิ่ม session:{sid}:ver — pod ที่เห็น version ไม่ตรงกับที่ตัวเอง
      cache ไว้จะโหลดสถานะใหม่จาก Redis + ไฟล์บน shared storage ก่อนทำงานต่อ

    ข้อกำหนด infrastructure:
    1. ทุก pod ต้องเขียน/อ่าน shared storage เดียวกันได้ (NFS / PVC ชนิด ReadWriteMany)
    2. Redis ต้องเข้าถึงได้จากทุก pod และควรตั้ง maxmemory-policy เป็น volatile-lru หรือ noeviction
       (ห้าม allkeys-lru — key ของ auth session ไม่มี TTL จะถูกลบทิ้งแบบสุ่มได้)
    """

    # Redis lock หมดอายุเองถ้า pod ตายระหว่างถือ lock (วินาที) — ต้องนานกว่างานที่ช้าที่สุด (compress/OCR)
    LOCK_TIMEOUT = 300
    # รอ lock นานสุดเท่านี้ก่อนตอบว่าเอกสารไม่ว่าง (วินาที)
    LOCK_WAIT = 120

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        # per-process cache ของ PDFSession — doc objects serialize ไม่ได้ จึงเก็บแค่ใน process นี้
        self._local_cache: dict[str, PDFSession] = {}
        self._cache_lock = threading.Lock()

    # ---- Redis key helpers ----
    def _meta_key(self, sid: str) -> str:
        return f"session:{sid}:meta"

    def _text_edits_key(self, sid: str) -> str:
        return f"session:{sid}:text_edits"

    def _version_key(self, sid: str) -> str:
        return f"session:{sid}:ver"

    def _lock_key(self, sid: str) -> str:
        return f"session:{sid}:lock"

    def _hist_key(self, sid: str, seq: int) -> str:
        return f"session:{sid}:hist:{seq}"

    def _hist_meta_key(self, sid: str, seq: int) -> str:
        return f"session:{sid}:histmeta:{seq}"

    # key รูปแบบเดิม (อ้างอิงตามตำแหน่งใน stack) — อ่านได้เพื่อรองรับ session ที่สร้างก่อนอัปเดต
    def _legacy_history_bytes_key(self, sid: str, pos: int) -> str:
        return f"session:{sid}:history:{pos}"

    def _legacy_history_meta_key(self, sid: str, pos: int) -> str:
        return f"session:{sid}:history_meta:{pos}"

    def _ttl(self) -> int:
        return settings.SESSION_TTL_MINUTES * 60

    def _session_keys(self, sid: str) -> list[str]:
        return [self._meta_key(sid), self._text_edits_key(sid), self._version_key(sid)]

    def _refresh_ttl(self, session_id: str) -> None:
        """ต่ออายุ TTL ของทุก key ของ session — เรียกทุกครั้งที่ get() สำเร็จ"""
        import json  # noqa: PLC0415

        ttl = self._ttl()
        raw_seqs = self._redis.hget(self._meta_key(session_id), b"history_seqs")
        seqs = json.loads(raw_seqs) if raw_seqs else []
        pipe = self._redis.pipeline()
        for key in self._session_keys(session_id):
            pipe.expire(key, ttl)
        for seq in seqs:
            pipe.expire(self._hist_key(session_id, seq), ttl)
            pipe.expire(self._hist_meta_key(session_id, seq), ttl)
        pipe.execute()

    # ---- ความสอดคล้องข้าม process (เรียกจาก SessionLock) ----
    def _acquire_distributed_lock(self, session: PDFSession):
        lock = self._redis.lock(
            self._lock_key(session.session_id),
            timeout=self.LOCK_TIMEOUT,
            blocking_timeout=self.LOCK_WAIT,
            thread_local=False,
        )
        if not lock.acquire():
            raise SessionBusyError(f"เอกสาร {session.session_id} กำลังถูกแก้ไขโดยคำขออื่น กรุณาลองใหม่")
        return lock

    def _current_version(self, session_id: str) -> int:
        raw = self._redis.get(self._version_key(session_id))
        return int(raw) if raw else 0

    def _refresh_if_stale(self, session: PDFSession) -> None:
        """ถ้า pod อื่นแก้ไข session นี้หลังจากที่ process นี้ cache ไว้ → โหลดสถานะใหม่ทั้งหมด"""
        version = self._current_version(session.session_id)
        if version == session._seen_version:
            return
        fresh = self._reconstruct_session(session.session_id, bind=False)
        if fresh is None:
            raise SessionBusyError(f"โหลดสถานะล่าสุดของเอกสาร {session.session_id} ไม่สำเร็จ")
        if session.doc is not None:
            try:
                session.doc.close()
            except Exception:
                pass
        for name in (
            "original_path", "working_path", "original_filename", "user_id", "doc", "is_unlocked",
            "text_edits", "history", "history_pos", "output_password", "output_encryption", "encryption_touched",
            "is_signed", "signature_type", "signed_pdf_bytes", "_next_seq",
        ):
            setattr(session, name, getattr(fresh, name))
        session._doc_dirty = False
        session._seen_version = version
        logger.info("session %s: โหลดสถานะใหม่จาก Redis (version %d)", session.session_id, version)

    def _publish_changes(self, session: PDFSession) -> None:
        """เรียกตอนปล่อย lock ถ้าสถานะเปลี่ยน — flush ลงดิสก์ แล้ว sync ขึ้น Redis และเพิ่ม version"""
        session.flush_to_disk()
        self._sync_to_redis(session)
        pipe = self._redis.pipeline()
        pipe.incr(self._version_key(session.session_id))
        pipe.expire(self._version_key(session.session_id), self._ttl())
        session._seen_version = int(pipe.execute()[0])

    def _sync_to_redis(self, session: PDFSession) -> None:
        """sync metadata + text_edits + history entries ที่ยังไม่เคยเขียนไป Redis (อ้างอิงด้วย seq)
        และลบ entry ที่ถูกตัดทิ้งออกจาก stack แล้ว"""
        import json  # noqa: PLC0415

        ttl = self._ttl()
        sid = session.session_id
        seqs = [e.seq for e in session.history]
        prev_raw = self._redis.hget(self._meta_key(sid), b"history_seqs")
        prev_seqs = set(json.loads(prev_raw)) if prev_raw else set()

        pipe = self._redis.pipeline()
        pipe.hset(
            self._meta_key(sid),
            mapping={
                b"session_id": sid.encode(),
                b"original_path": str(session.original_path).encode(),
                b"working_path": str(session.working_path).encode(),
                b"original_filename": session.original_filename.encode(),
                b"user_id": str(session.user_id).encode() if session.user_id is not None else b"",
                b"created_at": session.created_at.isoformat().encode(),
                b"last_accessed_at": session.last_accessed_at.isoformat().encode(),
                b"output_password": (session.output_password or "").encode(),
                b"encryption_touched": b"1" if session.encryption_touched else b"0",
                b"output_encryption": (session.output_encryption or "aes256").encode(),
                b"is_signed": b"1" if session.is_signed else b"0",
                b"signature_type": (session.signature_type or "").encode(),
                b"has_signed_bytes": b"1" if session.signed_pdf_bytes is not None else b"0",
                b"history_pos": str(session.history_pos).encode(),
                b"history_seqs": json.dumps(seqs).encode(),
                b"next_seq": str(session._next_seq).encode(),
            },
        )
        pipe.expire(self._meta_key(sid), ttl)
        te_json = json.dumps({str(k): v for k, v in session.text_edits.items()})
        pipe.set(self._text_edits_key(sid), te_json.encode(), ex=ttl)

        for entry in session.history:
            if entry.seq in prev_seqs:
                continue  # เขียนไปแล้ว — snapshot ไม่เปลี่ยนหลังสร้าง
            pipe.set(self._hist_key(sid, entry.seq), entry.doc_bytes, ex=ttl)
            pipe.hset(
                self._hist_meta_key(sid, entry.seq),
                mapping={
                    b"is_signed": b"1" if entry.is_signed else b"0",
                    b"signature_type": (entry.signature_type or "").encode(),
                    b"has_signed_bytes": b"1" if entry.signed_pdf_bytes is not None else b"0",
                    b"text_edits": json.dumps({str(k): v for k, v in entry.text_edits.items()}).encode(),
                },
            )
            pipe.expire(self._hist_meta_key(sid, entry.seq), ttl)
        stale = prev_seqs - set(seqs)
        for seq in stale:
            pipe.delete(self._hist_key(sid, seq), self._hist_meta_key(sid, seq))
        pipe.execute()

    def _load_history(self, session_id: str, raw: dict, current_text_edits: dict) -> tuple[list, int, int]:
        """อ่าน undo history จาก Redis — คืน (entries, history_pos, next_seq)"""
        import json  # noqa: PLC0415

        def _te(blob):
            try:
                return {int(k): v for k, v in json.loads(blob).items()} if blob else {}
            except Exception:
                return {}

        history_pos = int(raw.get(b"history_pos", b"-1").decode())
        if raw.get(b"history_seqs"):
            seqs = json.loads(raw[b"history_seqs"])
            entries = []
            for seq in seqs:
                data = self._redis.get(self._hist_key(session_id, seq))
                if data is None:
                    continue
                hmeta = self._redis.hgetall(self._hist_meta_key(session_id, seq))
                entries.append(_HistoryEntry(
                    doc_bytes=data,
                    text_edits=_te(hmeta.get(b"text_edits")),
                    is_signed=hmeta.get(b"is_signed", b"0") == b"1",
                    signature_type=hmeta.get(b"signature_type", b"").decode() or None,
                    signed_pdf_bytes=data if hmeta.get(b"has_signed_bytes") == b"1" else None,
                    seq=seq,
                ))
            if len(entries) != len(seqs):  # บาง entry หาย (เช่นโดน evict) — เก็บแค่ entry ปัจจุบันพอ
                current_seq = seqs[history_pos] if 0 <= history_pos < len(seqs) else None
                entries = [e for e in entries if e.seq == current_seq]
                history_pos = 0 if entries else -1
            next_seq = int(raw.get(b"next_seq", b"0").decode() or 0) or (max(seqs, default=0) + 1)
            return entries, min(history_pos, len(entries) - 1), next_seq

        # รูปแบบเดิม: มีแค่ entry ปัจจุบันที่ใช้ได้แน่นอน
        if history_pos >= 0:
            hbytes = self._redis.get(self._legacy_history_bytes_key(session_id, history_pos))
            if hbytes:
                hmeta = self._redis.hgetall(self._legacy_history_meta_key(session_id, history_pos))
                entry = _HistoryEntry(
                    doc_bytes=hbytes,
                    text_edits=copy.deepcopy(current_text_edits),
                    is_signed=hmeta.get(b"is_signed", b"0") == b"1",
                    signature_type=hmeta.get(b"signature_type", b"").decode() or None,
                    seq=1,
                )
                return [entry], 0, 2
        return [], -1, 1

    def _reconstruct_session(self, session_id: str, bind: bool = True) -> Optional[PDFSession]:
        """สร้าง PDFSession ใหม่จาก Redis metadata + ไฟล์บน shared storage
        เรียกเมื่อ session มีอยู่ใน Redis แต่ยังไม่อยู่ใน local cache ของ pod นี้ (หรือ cache เก่าแล้ว)"""
        import json  # noqa: PLC0415

        raw = self._redis.hgetall(self._meta_key(session_id))
        if not raw:
            return None
        try:
            working_path = Path(raw[b"working_path"].decode())
            if not working_path.exists():
                logger.warning("reconstruct: ไม่พบ working_path %s — session %s ใช้งานไม่ได้", working_path, session_id)
                return None
            doc = fitz.open(working_path)
            session = PDFSession(
                session_id=session_id,
                original_path=Path(raw[b"original_path"].decode()),
                working_path=working_path,
                original_filename=raw.get(b"original_filename", b"").decode(),
                user_id=int(raw[b"user_id"].decode()) if raw.get(b"user_id") else None,
                doc=doc,
                is_unlocked=not bool(doc.needs_pass),
            )
            session.output_password = raw.get(b"output_password", b"").decode() or None
            session.encryption_touched = raw.get(b"encryption_touched", b"0") == b"1"
            session.output_encryption = raw.get(b"output_encryption", b"aes256").decode() or "aes256"
            session.is_signed = raw.get(b"is_signed", b"0") == b"1"
            session.signature_type = raw.get(b"signature_type", b"").decode() or None
            te_raw = self._redis.get(self._text_edits_key(session_id))
            if te_raw:
                try:
                    session.text_edits = {int(k): v for k, v in json.loads(te_raw).items()}
                except Exception:
                    session.text_edits = {}
            session.history, session.history_pos, session._next_seq = self._load_history(
                session_id, raw, session.text_edits
            )
            if raw.get(b"has_signed_bytes") == b"1" and 0 <= session.history_pos < len(session.history):
                session.signed_pdf_bytes = session.history[session.history_pos].doc_bytes
            session._seen_version = self._current_version(session_id)
            if bind:
                self._bind(session)
            return session
        except Exception as exc:
            logger.warning("reconstruct: สร้าง session %s ไม่สำเร็จ: %s", session_id, exc)
            return None

    def _bind(self, session: PDFSession) -> None:
        session._on_history_push = self._sync_to_redis
        session.lock.bind(self, session)

    def create_session(
        self, original_path: Path, working_path: Path, original_filename: str, user_id: Optional[int] = None, session_id: Optional[str] = None
    ) -> PDFSession:
        session_id = session_id or uuid.uuid4().hex
        session = PDFSession(
            session_id=session_id,
            original_path=original_path,
            working_path=working_path,
            original_filename=original_filename,
            user_id=user_id,
        )
        self._bind(session)
        with self._cache_lock:
            self._local_cache[session_id] = session
        # บันทึก meta เริ่มต้นไปยัง Redis ทันที (ให้ pod อื่นเห็น session ใหม่นี้ได้)
        self._sync_to_redis(session)
        return session

    def save(self, session: PDFSession) -> None:
        """sync สถานะที่เปลี่ยนนอก lock (เช่น ย้ายไฟล์/ผูกเจ้าของ) ขึ้น Redis และแจ้ง pod อื่น"""
        self._sync_to_redis(session)
        pipe = self._redis.pipeline()
        pipe.incr(self._version_key(session.session_id))
        pipe.expire(self._version_key(session.session_id), self._ttl())
        session._seen_version = int(pipe.execute()[0])

    def get(self, session_id: str) -> Optional[PDFSession]:
        # 1. local cache ก่อน (fast path) — ความสดของข้อมูลตรวจตอนเข้า session.lock (ดู SessionLock)
        with self._cache_lock:
            session = self._local_cache.get(session_id)
        if session:
            if not self._redis.exists(self._meta_key(session_id)):
                self._drop_local(session_id)  # หมดอายุ/ถูกปิดจาก pod อื่นแล้ว
                return None
            session.touch()
            self._refresh_ttl(session_id)
            return session
        # 2. ตรวจ Redis — ถ้า key ยังอยู่แสดงว่ายังไม่หมดอายุ
        if not self._redis.exists(self._meta_key(session_id)):
            return None
        # 3. reconstruct จาก Redis + disk (pod อื่นสร้างไว้ หรือ pod นี้รีสตาร์ทมาใหม่)
        session = self._reconstruct_session(session_id)
        if session is None:
            return None
        session.touch()
        with self._cache_lock:
            self._local_cache[session_id] = session
        self._refresh_ttl(session_id)
        return session

    def _drop_local(self, session_id: str) -> Optional[PDFSession]:
        with self._cache_lock:
            session = self._local_cache.pop(session_id, None)
        if session and session.doc:
            try:
                session.doc.close()
            except Exception:
                pass
        return session

    def close(self, session_id: str) -> None:
        import json  # noqa: PLC0415

        session = self._drop_local(session_id)
        try:
            raw = self._redis.hgetall(self._meta_key(session_id))
            keys = self._session_keys(session_id) + [self._lock_key(session_id)]
            for seq in json.loads(raw.get(b"history_seqs", b"[]")):
                keys += [self._hist_key(session_id, seq), self._hist_meta_key(session_id, seq)]
            for i in range(_HISTORY_LIMIT + 2):  # key รูปแบบเดิม
                keys += [self._legacy_history_bytes_key(session_id, i), self._legacy_history_meta_key(session_id, i)]
            working = raw.get(b"working_path")
            self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("close: ลบ Redis keys ของ session %s ไม่สำเร็จ: %s", session_id, exc)
            working = None
        # ลบ working copy บน disk (เก็บ original_path ไว้ให้ Dashboard)
        path = session.working_path if session else (Path(working.decode()) if working else None)
        try:
            if path and Path(path).exists():
                Path(path).unlink()
        except Exception:
            logger.warning("ลบไฟล์ค้างไม่สำเร็จ: %s", path)

    def cleanup_expired(self) -> int:
        """เคลียร์ session จาก local cache ที่ Redis key หมดอายุแล้ว
        (Redis จัดการ TTL ของ key ตัวเองอยู่แล้ว — เราแค่ sync local cache ตาม)"""
        with self._cache_lock:
            all_ids = list(self._local_cache.keys())
        expired_ids = [sid for sid in all_ids if not self._redis.exists(self._meta_key(sid))]
        for sid in expired_ids:
            self.close(sid)
        return len(expired_ids)

    def cleanup_orphan_files(self, max_age_hours: float = 24.0) -> int:
        """เก็บกวาดไฟล์ค้างใน WORKING_DIR ที่ไม่มี session ใน Redis อ้างอิงอยู่แล้ว และเก่ากว่า max_age_hours
        (ตรวจกับ Redis ด้วย ไม่ใช่แค่ local cache — กันลบไฟล์ที่ pod อื่นกำลังใช้อยู่บน shared storage)"""
        cutoff_ts = (datetime.utcnow() - timedelta(hours=max_age_hours)).timestamp()
        active_paths = set()
        try:
            for key in self._redis.scan_iter(match="session:*:meta", count=500):
                wp = self._redis.hget(key, b"working_path")
                if wp:
                    active_paths.add(wp.decode())
        except Exception:
            logger.warning("cleanup: อ่านรายการ session จาก Redis ไม่สำเร็จ — ข้ามรอบนี้")
            return 0
        removed = 0
        directory = Path(settings.WORKING_DIR)
        if not directory.is_dir():
            return 0
        for f in directory.iterdir():
            if not f.is_file() or str(f) in active_paths:
                continue
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    removed += 1
            except Exception:
                continue
        return removed


def _create_session_manager() -> "InMemorySessionManager | RedisSessionManager":
    """เลือก SessionManager ที่เหมาะสม ณ เวลา import:
    - ถ้า PDF_REDIS_URL ตั้งค่าไว้และเชื่อมต่อ Redis ได้ → RedisSessionManager (multi-instance)
    - ถ้าไม่มี/เชื่อมต่อไม่ได้ → InMemorySessionManager (single-instance เดิม)
    """
    from app.core.redis_client import get_redis  # noqa: PLC0415

    r = get_redis()
    if r is not None:
        logger.info("ใช้ RedisSessionManager (multi-instance mode)")
        return RedisSessionManager(r)
    logger.info("ใช้ InMemorySessionManager (single-instance mode)")
    return InMemorySessionManager()


# instance เดียวใช้ร่วมกันทั้งแอป — เลือกอัตโนมัติตาม PDF_REDIS_URL
session_manager = _create_session_manager()
