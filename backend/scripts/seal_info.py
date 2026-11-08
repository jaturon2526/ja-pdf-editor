"""แสดงข้อมูลใบรับรองระบบที่ใช้ลงนามอิเล็กทรอนิกส์ (ไม่แสดง private key/รหัสผ่าน)

ใช้หลังตั้งค่า SIGNING_SEAL_P12 / SIGNING_SEAL_P12_PASSWORD:
    docker compose -f docker-compose.dev.yml exec backend python -m scripts.seal_info
"""
import sys

from app.services import signing_pdf


def main() -> int:
    try:
        info = signing_pdf.seal_info()
    except Exception as exc:  # ไฟล์ไม่พบ/รหัสผ่านผิด
        print(f"ใช้งานใบรับรองระบบไม่ได้: {exc}")
        return 1
    print(f"แหล่งที่มา      : {'ไฟล์ .p12 ที่ตั้งค่า (SIGNING_SEAL_P12)' if info['source'] == 'p12' else 'self-signed ที่ระบบสร้างเอง'}")
    print(f"ชื่อ (CN)       : {info['subject']}")
    print(f"องค์กร          : {info['organization'] or '-'}")
    print(f"ผู้ออกใบรับรอง  : {info['issuer']}")
    print(f"ใบรับรองใน chain: {', '.join(info['chain']) or '-'}")
    print(f"หมดอายุ         : {info['not_after'][:10]} (อีก {info['days_left']} วัน)")
    print(f"SHA-256         : {info['sha256']}")
    for w in info["warnings"]:
        print(f"คำเตือน         : {w}")
    if not info["warnings"]:
        print("สถานะ           : พร้อมใช้งาน")
    return 0


if __name__ == "__main__":
    sys.exit(main())
