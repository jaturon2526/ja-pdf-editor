"""เปรียบเทียบเอกสาร PDF (ข้อความ + ภาพ + OCR) — ดู engine.py และ claude/phase-compare-pdf-plan.md"""
from app.services.compare_service.engine import CompareError, Options, compare_documents

__all__ = ["CompareError", "Options", "compare_documents"]
