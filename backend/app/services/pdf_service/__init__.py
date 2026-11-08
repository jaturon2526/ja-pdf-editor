"""
pdf_service — รวม logic ที่คุยกับ PyMuPDF (fitz) โดยตรงสำหรับงาน:
เปิดไฟล์, ตรวจ/ปลดรหัสผ่าน, render หน้าเป็นรูป, ดึงข้อมูลทั่วไปของเอกสาร

หลักการสำคัญ: เราไม่แก้ไฟล์ต้นฉบับ (original_path) เด็ดขาด — ทุกการแก้ไขทำบน
สำเนาทำงาน (working_path) ที่ copy มาตอนสร้าง session เท่านั้น ทำให้ "undo กลับไปต้นฉบับ"
หรือยกเลิกการแก้ไขทั้งหมดทำได้ง่ายด้วยการ copy original ทับ working ใหม่

แยกเป็นโมดูลย่อยตามหน้าที่ (เดิมเป็นไฟล์เดียว ~1,250 บรรทัด) — import จาก app.services.pdf_service ได้เหมือนเดิมทุกชื่อ
- core.py       : เปิด/ปลดล็อก/render, สร้าง session, รหัสผ่าน, ไฟล์ดาวน์โหลด, รวมไฟล์
- pages.py      : bookmark, ลบ/หมุน/เรียง/ส่งออก/แยกหน้า
- optimize.py   : compress, flatten
- redact.py     : redaction
- properties.py : Document Properties + ข้อมูลลายเซ็นดิจิทัล
- ocr.py        : OCR พื้นที่ที่เลือก
- pii.py        : ตรวจหา/ปิดข้อมูลส่วนบุคคล (PDPA)
"""
from app.services.pdf_service.core import (  # noqa: F401
    PDFError,
    _flush_mupdf_warnings,
    create_session_from_upload,
    _try_open,
    unlock,
    is_locked,
    require_unlocked,
    get_page_count,
    get_page_sizes,
    render_page,
    render_page_base64,
    render_page_image,
    save_working_copy,
    get_download_path,
    get_encryption_state,
    add_password,
    check_password_for_mode,
    encrypt_pdf_file,
    pdfa_claim_of,
    ENCRYPTION_MODES,
    remove_password,
    MERGE_MAX_FILES,
    merge_pdf_bytes,
)
from app.services.pdf_service.pages import (  # noqa: F401
    get_bookmarks,
    set_bookmarks,
    export_pages,
    delete_pages,
    rotate_pages,
    reorder_pages,
    parse_page_range,
    extract_pages,
    build_print_pdf,
)
from app.services.pdf_service.optimize import (  # noqa: F401
    compress_pdf,
    flatten_pdf,
)
from app.services.pdf_service.version import (  # noqa: F401
    PDF_VERSIONS,
    export_pdf_version,
)
from app.services.pdf_service.pdfa import (  # noqa: F401
    PDFA_PARTS,
    export_pdfa,
    verify_pdfa,
)
from app.services.pdf_service.scan import (  # noqa: F401
    SCAN_MAX_PAGES,
    build_scan_pdf,
    check_scan_image,
)
from app.services.pdf_service.redact import (  # noqa: F401
    redact_areas_batch,
    redact_area,
    redact_by_search,
    pages_with_images,
)
from app.services.pdf_service.properties import (  # noqa: F401
    get_document_properties,
)
from app.services.pdf_service.ocr import (  # noqa: F401
    extract_text_ocr,
    add_ocr_text_layer,
    image_to_searchable_pdf,
)
from app.services.pdf_service.pii import (  # noqa: F401
    PII_TYPES,
    PIIStaleError,
    scan_pii,
    redact_pii,
)
