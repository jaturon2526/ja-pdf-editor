"""edit_service — แก้ไขข้อความ รูปภาพ และลายน้ำในหน้า PDF

แยกเป็นโมดูลย่อย (เดิมเป็นไฟล์เดียว ~980 บรรทัด):
  - layout.py    ตัวช่วยร่วม: ตัดคำไทย วัด/ตัดบรรทัด สุ่มสีพื้นหลัง ค่าคงที่
  - text.py      get_text_blocks, replace_text  (แก้ข้อความแบบ "redact แล้ววาดใหม่")
  - images.py    get_images, delete/replace/insert/reposition_image, get_image_bytes
  - watermark.py apply_watermark
  - page_numbers.py apply_page_numbers (ใส่เลขหน้า)
เหตุผลการออกแบบและประวัติการแก้บั๊ก ("แก้บั๊กสำคัญ #1–#9") อยู่ใน NOTES.md ในโฟลเดอร์นี้

โค้ดภายนอกเรียกผ่าน `from app.services import edit_service` แล้ว `edit_service.xxx` ได้เหมือนเดิม
"""
from app.services.edit_service.images import (
    delete_image,
    get_image_bytes,
    get_images,
    insert_image,
    replace_image,
    reposition_image,
)
from app.services.edit_service.layout import (  # ใช้โดย annotation_service / signature_service
    _LINE_HEIGHT_RATIO,
    _sample_background_color,
    _wrap_text,
)
from app.services.edit_service.text import get_text_blocks, replace_text
from app.services.edit_service.watermark import apply_watermark
from app.services.edit_service.page_numbers import PageNumberOptions, apply_page_numbers

__all__ = [
    "apply_watermark",
    "apply_page_numbers",
    "PageNumberOptions",
    "delete_image",
    "get_image_bytes",
    "get_images",
    "get_text_blocks",
    "insert_image",
    "replace_image",
    "replace_text",
    "reposition_image",
    "_LINE_HEIGHT_RATIO",
    "_sample_background_color",
    "_wrap_text",
]
