"""
ค่าคอนฟิกของแอป — อ่านค่าจาก environment variable ได้ (ใส่ default ไว้สำหรับ dev)
"""
import os
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    """อ่านค่า true/false จาก env — ไม่ตั้ง/ว่าง = default"""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _csv(name: str) -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


# รูปแบบการติดตั้ง: public (เว็บสาธารณะ — ค่าเดิม) | onprem (ติดตั้งในองค์กร)
# onprem เปลี่ยนค่า default: ปิด Google/LINE (ตั้ง AUTH_*_ENABLED=true เพื่อเปิดเองได้) — ค่าอื่นยังตั้งได้ทุกตัว
DEPLOYMENT_PROFILE = (os.getenv("DEPLOYMENT_PROFILE", "public").strip().lower() or "public")
if DEPLOYMENT_PROFILE not in ("public", "onprem"):
    raise RuntimeError(f"DEPLOYMENT_PROFILE ต้องเป็น public หรือ onprem (ได้ {DEPLOYMENT_PROFILE!r})")
_ONPREM = DEPLOYMENT_PROFILE == "onprem"


class Settings:
    # โฟลเดอร์เก็บไฟล์ที่ผู้ใช้ upload มา (ต้นฉบับ ห้ามแก้ทับ)
    UPLOAD_DIR: Path = Path(os.getenv("PDF_UPLOAD_DIR", "./storage/uploads"))

    # โฟลเดอร์เก็บไฟล์ที่กำลังแก้ไข (working copy ต่อ session)
    WORKING_DIR: Path = Path(os.getenv("PDF_WORKING_DIR", "./storage/working"))

    # อายุของ session (นาที) ก่อนจะถูกเคลียร์ทิ้งจากหน่วยความจำ + ลบไฟล์ (upload/working) คู่กันทิ้งด้วย
    # ผู้ใช้แจ้งให้เพิ่ม cleanup ข้อมูลที่ค้างเกิน 24 ชม. — ปรับ default จาก 60 นาทีเป็น 1440 นาที (24 ชม.)
    # (ดู app/core/session.py: cleanup_expired / cleanup_orphan_files กับ app/main.py: _periodic_cleanup)
    # เอกสารที่เปิดค้างโดยไม่มีการใช้งาน (หน้าแก้ไขส่งสัญญาณทุก 5 นาทีขณะเปิดแท็บ) ถูกปิดเพื่อคืนหน่วยความจำ
    # เดิม 1440 (24 ชม.) — เปิดลิงก์เดิมอีกครั้งได้ ระบบเปิดใหม่จากไฟล์ที่บันทึกไว้ (ดูแผน claude/phase-scalability-plan.md)
    SESSION_TTL_MINUTES: int = int(os.getenv("PDF_SESSION_TTL_MINUTES", "120"))

    # ความถี่ (นาที) ที่ background task จะวนมาเรียก cleanup_expired()/cleanup_orphan_files() (ดู main.py)
    CLEANUP_INTERVAL_MINUTES: int = int(os.getenv("PDF_CLEANUP_INTERVAL_MINUTES", "10"))
    # งานหนัก (Ghostscript / LibreOffice / Tesseract) พร้อมกันได้กี่งานต่อ worker — รวมทั้งเครื่อง = workers × ค่านี้
    # งานที่เกินรอคิวได้ HEAVY_QUEUE_TIMEOUT วินาที · คิวต่อ worker ยาวเกิน HEAVY_QUEUE_MAX → ตอบ 503 ทันที (กันเธรดเต็ม)
    HEAVY_JOBS_PER_WORKER: int = max(1, int(os.getenv("HEAVY_JOBS_PER_WORKER", "1") or 1))
    HEAVY_QUEUE_MAX: int = max(0, int(os.getenv("HEAVY_QUEUE_MAX", "8") or 8))
    HEAVY_QUEUE_TIMEOUT: float = float(os.getenv("HEAVY_QUEUE_TIMEOUT", "120") or 120)

    # ขนาดไฟล์สูงสุดที่รับ upload (bytes) — ค่า default 50 MB
    MAX_UPLOAD_SIZE: int = int(os.getenv("PDF_MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
    # รวมไฟล์: ขนาดรวมของไฟล์ต้นทางทั้งหมด (ไฟล์จากเอกสารของฉันไม่ผ่าน nginx จึงจำกัดที่นี่ — ทุกไฟล์อยู่ในหน่วยความจำพร้อมกัน)
    MAX_MERGE_TOTAL: int = int(os.getenv("PDF_MAX_MERGE_TOTAL", str(150 * 1024 * 1024)))
    # พื้นที่เก็บไฟล์เริ่มต้นของแพ็กเกจ free (MB) — ใช้ตอนติดตั้งครั้งแรก (seed plan_configs) และเมื่อไม่พบแพ็กเกจ
    # ติดตั้งแล้วเปลี่ยนได้ที่หน้าผู้ดูแล › แพ็กเกจ (onprem template ตั้ง 200)
    DEFAULT_STORAGE_MB: int = max(1, int(os.getenv("DEFAULT_STORAGE_MB", "100") or 100))

    # origin ที่อนุญาตให้เรียก API (CORS) — คั่นด้วยจุลภาค
    ALLOWED_ORIGINS: list[str] = os.getenv("PDF_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

    # Redis URL สำหรับ multi-instance session (ถ้าไม่ตั้งค่า หรือเชื่อมต่อไม่ได้ — ใช้ InMemorySessionManager เดิม)
    # ตัวอย่าง: redis://localhost:6379/0 หรือ redis://:password@host:6379/0
    REDIS_URL: str = os.getenv("PDF_REDIS_URL", "")
    # Authentication & Verification
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY", None)
    # AI หลายค่าย (ดู services/ai_client.py): gemini | anthropic | openai (OpenAI และ API แบบเดียวกัน)
    # ไม่ตั้ง = gemini ใช้ GEMINI_API_KEY (ค่าเดิม) · AI_MODEL ว่าง = รุ่นเริ่มต้นของค่าย (openai ต้องระบุ)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "")
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "")
    # ผู้ใช้ใส่ API key ของตัวเองได้ (เช่น เครดิตของแผนก) — false = ใช้ AI ของระบบอย่างเดียว
    AI_USER_KEYS_ENABLED: bool = _flag("AI_USER_KEYS_ENABLED", True)
    # โฮสต์ภายในที่ผู้ใช้ตั้งเป็น URL ของ API ได้ (คั่นด้วย ,) — ปกติห้ามชี้เข้าเครือข่ายภายใน
    AI_PRIVATE_HOSTS: str = os.getenv("AI_PRIVATE_HOSTS", "")
    GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID", None)

    DEPLOYMENT_PROFILE: str = DEPLOYMENT_PROFILE
    # เปิด/ปิดการเข้าสู่ระบบด้วย Google / LINE (และการแจ้งเตือนทาง LINE) — public: เปิดเมื่อตั้งค่า client/channel ไว้
    # onprem: ปิดเป็นค่าเริ่มต้นแม้มีค่าค้างอยู่ใน .env
    AUTH_GOOGLE_ENABLED: bool = _flag("AUTH_GOOGLE_ENABLED", not _ONPREM)
    AUTH_LINE_ENABLED: bool = _flag("AUTH_LINE_ENABLED", not _ONPREM)
    # สมัครสมาชิกเองได้ไหม — false: สมัครได้เฉพาะอีเมลใน INITIAL_ADMIN_EMAILS และผู้ที่ได้รับคำเชิญลงนาม
    ALLOW_SELF_REGISTRATION: bool = _flag("ALLOW_SELF_REGISTRATION", True)
    # จำกัดโดเมนอีเมลของบัญชีใหม่ (คั่นด้วย , เช่น company.co.th,company.com) — ว่าง = ทุกโดเมน
    # ผู้ที่ได้รับคำเชิญลงนามสมัครได้แม้อยู่นอกโดเมน (เพื่อให้ลงนามเอกสารที่ส่งถึงได้) · บัญชีเดิมไม่ได้รับผลกระทบ
    ALLOWED_EMAIL_DOMAINS: list[str] = _csv("ALLOWED_EMAIL_DOMAINS")
    
    # SMTP Settings for Email Verification
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME", None)
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD", None)
    # ที่อยู่ผู้ส่งของอีเมลระบบ (ว่าง = ใช้ SMTP_USERNAME) — อีเมลแจ้งเตือนการลงนามส่งจากที่อยู่นี้เสมอ
    # ชื่อผู้ส่งแสดงเป็น "ชื่อผู้ใช้ ผ่าน JA PDF Editor" และ Reply-To เป็นอีเมลของผู้ส่งเอกสาร
    SMTP_FROM: str | None = os.getenv("SMTP_FROM", None)
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() not in ("0", "false", "no")
    # การเข้ารหัสการเชื่อมต่อ: starttls | ssl | none — ว่าง = เดาจากค่าเดิม (พอร์ต 465 → ssl, SMTP_USE_TLS → starttls)
    # mail relay ภายในองค์กรที่ไม่เข้ารหัสใช้ none ได้ (เฉพาะในเครือข่ายภายใน)
    SMTP_SECURITY: str = os.getenv("SMTP_SECURITY", "").strip().lower()
    # ต้อง login ไหม: true | false — ว่าง = login เมื่อตั้ง SMTP_USERNAME (relay ภายในที่อนุญาตตาม IP ไม่ต้องตั้ง)
    SMTP_AUTH: str = os.getenv("SMTP_AUTH", "").strip().lower()
    # ไฟล์ CA ขององค์กร (PEM) สำหรับตรวจใบรับรองของ mail server ภายใน — ว่าง = ใช้ CA มาตรฐานของระบบ
    SMTP_CA_FILE: str | None = os.getenv("SMTP_CA_FILE") or None
    APP_NAME: str = os.getenv("APP_NAME", "JA PDF Editor")
    # ลิงก์ซอร์สโค้ด (AGPL-3.0 ข้อ 13: ผู้ใช้ผ่านเครือข่ายต้องได้ซอร์สของเวอร์ชันที่รันอยู่) — แสดงในหน้า About/หน้า Login
    # ถ้าแก้โค้ดเอง (fork/on-prem ที่ดัดแปลง) ต้องชี้ไปที่ซอร์สฉบับที่แก้แล้ว · ตั้งเป็นค่าว่างไม่ได้ (ใช้ค่าเริ่มต้นแทน)
    SOURCE_CODE_URL: str = os.getenv("SOURCE_CODE_URL") or "https://github.com/jaturon2526/ja-pdf-editor"
    # ส่งเตือนอัตโนมัติก่อนครบกำหนดลงนามกี่ชั่วโมง / ผู้ส่งกดส่งเตือนซ้ำได้ทุกกี่นาที
    SIGNING_DUE_SOON_HOURS: int = int(os.getenv("SIGNING_DUE_SOON_HOURS", "24"))
    # ใบรับรองระบบ (system seal) จาก CA จริง — ไฟล์ .p12/.pfx ที่มี private key + ใบรับรอง + chain
    # ว่าง = ใช้ใบรับรอง self-signed ที่ระบบสร้างเอง (Adobe จะขึ้น "ไม่ทราบผู้ออกใบรับรอง")
    SIGNING_SEAL_P12: str | None = os.getenv("SIGNING_SEAL_P12") or None
    SIGNING_SEAL_P12_PASSWORD: str = os.getenv("SIGNING_SEAL_P12_PASSWORD", "")
    # ดาวน์โหลดใบรับรองของผู้ออก (intermediate/root) ตาม URL "CA Issuers" ในใบรับรอง เมื่อไฟล์ .p12 ไม่ได้รวม chain มา
    # (ทั้งใบรับรองระบบและไฟล์ .p12 ที่ผู้ลงนามอัปโหลด) — เก็บ cache ไว้ใน UPLOAD_DIR/_signing/_aia/
    SIGNING_FETCH_CHAIN: bool = os.getenv("SIGNING_FETCH_CHAIN", "true").lower() not in ("0", "false", "no")
    SIGNING_FETCH_CHAIN_TIMEOUT: int = int(os.getenv("SIGNING_FETCH_CHAIN_TIMEOUT", "5"))
    # ประทับเวลาลายเซ็นโดย TSA ภายนอก (RFC 3161) เช่น http://timestamp.digicert.com — ว่าง = ไม่ใช้
    # ถ้า TSA ล่ม/ติดต่อไม่ได้ ระบบลงนามต่อโดยไม่มี timestamp (บันทึก warning ใน log)
    SIGNING_TSA_URL: str | None = os.getenv("SIGNING_TSA_URL") or None
    SIGNING_TSA_TIMEOUT: int = int(os.getenv("SIGNING_TSA_TIMEOUT", "10"))
    SIGNING_CHECK_INTERVAL_MINUTES: int = int(os.getenv("SIGNING_CHECK_INTERVAL_MINUTES", "10"))
    SIGNING_REMIND_COOLDOWN_MINUTES: int = int(os.getenv("SIGNING_REMIND_COOLDOWN_MINUTES", "60"))
    
    # Frontend URL for Verification Links
    # โควต้าแปลง PDF→Word ด้วย AI ฟรี (ใช้ API key ของระบบ) ต่อผู้ใช้ต่อวัน
    AI_SYSTEM_DAILY_LIMIT: int = int(os.getenv("AI_SYSTEM_DAILY_LIMIT", "2"))
    # เขตเวลาที่ใช้ตัดรอบ "วัน" ของโควต้า (เดิมใช้เวลาเครื่อง ซึ่งใน container คือ UTC → รีเซ็ต 07:00 น.)
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Bangkok")

    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Passkey (WebAuthn) — ปกติไม่ต้องตั้ง: RP ID = โดเมนของ FRONTEND_URL, origin ที่ยอมรับ = FRONTEND_URL + PDF_ALLOWED_ORIGINS
    # passkey ผูกกับ RP ID — ถ้าเปลี่ยนโดเมนภายหลัง passkey เดิมจะใช้ไม่ได้ (ผู้ใช้ยังเข้าด้วยรหัสผ่าน/Google ได้)
    WEBAUTHN_RP_ID: str = os.getenv("WEBAUTHN_RP_ID", "")
    WEBAUTHN_RP_NAME: str = os.getenv("WEBAUTHN_RP_NAME", "JA PDF Editor")
    WEBAUTHN_ORIGINS: str = os.getenv("WEBAUTHN_ORIGINS", "")  # คั่นด้วย , (แทนค่าอัตโนมัติ)

    # LINE Messaging API (แจ้งเตือนการลงนามทาง LINE แทนอีเมล) — ไม่ตั้ง SECRET/TOKEN = ปิดฟีเจอร์
    # ค่าจาก LINE Developers Console: Basic settings → Channel secret, Messaging API → Channel access token (long-lived)
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_OA_BASIC_ID: str = os.getenv("LINE_OA_BASIC_ID", "")  # เช่น @227hmohv — ใช้สร้างลิงก์เพิ่มเพื่อน/ส่งรหัส
    # เพดานข้อความ push ต่อเดือน (แพ็กเกจฟรี 300 — เผื่อไว้) ถึงแล้วส่งอีเมลแทน
    LINE_MONTHLY_LIMIT: int = int(os.getenv("LINE_MONTHLY_LIMIT", "280"))
    LINE_API_BASE: str = os.getenv("LINE_API_BASE", "https://api.line.me")
    # LINE Login ("เข้าสู่ระบบด้วย LINE") — channel แยกจาก Messaging API แต่ต้องอยู่ provider เดียวกัน (userId ตรงกัน)
    # ค่าจาก LINE Developers Console › LINE Login channel › Basic settings — ไม่ตั้ง = ซ่อนปุ่ม
    LINE_LOGIN_CHANNEL_ID: str = os.getenv("LINE_LOGIN_CHANNEL_ID", "")
    LINE_LOGIN_CHANNEL_SECRET: str = os.getenv("LINE_LOGIN_CHANNEL_SECRET", "")
    LINE_LOGIN_AUTHORIZE_URL: str = os.getenv("LINE_LOGIN_AUTHORIZE_URL", "https://access.line.me/oauth2/v2.1/authorize")

    # หน้าโควต้า/เครดิตของแอดมิน (/admin/quotas) และแจ้งเตือนแอดมินเมื่อใกล้เต็ม
    # Brevo API key แบบ Restricted (Transactional email + Account = Read) — ไม่ตั้ง = ใช้ตัวนับภายในแทน
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    BREVO_API_BASE: str = os.getenv("BREVO_API_BASE", "https://api.brevo.com")
    BREVO_DAILY_LIMIT: int = int(os.getenv("BREVO_DAILY_LIMIT", "300"))  # แพ็กเกจฟรี 300 ฉบับ/วัน
    # เพดานคำขอ Gemini ต่อวันของ API key ระบบ (ดูที่ AI Studio) — 0 = ไม่ทราบ แสดงแค่จำนวนที่ใช้
    GEMINI_DAILY_REQUEST_LIMIT: int = int(os.getenv("AI_DAILY_REQUEST_LIMIT") or os.getenv("GEMINI_DAILY_REQUEST_LIMIT", "0"))
    QUOTA_ALERT_PERCENT: int = int(os.getenv("QUOTA_ALERT_PERCENT", "80"))
    QUOTA_CHECK_INTERVAL_MINUTES: int = int(os.getenv("QUOTA_CHECK_INTERVAL_MINUTES", "60"))
    # สำรองข้อมูลล่าสุดเก่ากว่านี้ (ชม.) → หน้าแอดมินขึ้นเตือน + แจ้งแอดมิน (เวลาจาก /data/.last-backup ที่สคริปต์ backup เขียน)
    BACKUP_MAX_AGE_HOURS: int = int(os.getenv("BACKUP_MAX_AGE_HOURS", "36"))
    # ติดตั้งฟอนต์จากลิงก์: โฮสต์ที่เชื่อถือได้ (https เท่านั้น ตรงตัว คั่นด้วย ,) — ดู services/font_url.py
    FONT_URL_ALLOWED_HOSTS: str = os.getenv("FONT_URL_ALLOWED_HOSTS", "fonts.google.com,fonts.googleapis.com")
    # งานเบื้องหลังตามรอบ (ลบไฟล์หมดอายุ, เตือนลงนาม, ตรวจโควต้า) — ปิดใน test ไม่ให้ไปชนกับ test ที่ monkeypatch
    BACKGROUND_JOBS: bool = os.getenv("PDF_BACKGROUND_JOBS", "1") != "0"
    # บัญชีที่จะเป็นผู้ดูแลระบบอัตโนมัติเมื่อสมัคร/เข้าสู่ระบบครั้งแรก (อีเมล คั่นด้วย ,) — ว่าง = ผู้ใช้คนแรกของระบบ
    # (ค่าเดิม: เปิดเว็บใหม่แล้วใครสมัครก่อนคนนั้นได้สิทธิ์ผู้ดูแล)
    INITIAL_ADMIN_EMAILS: str = os.getenv("INITIAL_ADMIN_EMAILS", "")

    @property
    def is_onprem(self) -> bool:
        return self.DEPLOYMENT_PROFILE == "onprem"

    @property
    def google_enabled(self) -> bool:
        return bool(self.AUTH_GOOGLE_ENABLED and self.GOOGLE_CLIENT_ID)

    @property
    def line_enabled(self) -> bool:
        return bool(self.AUTH_LINE_ENABLED and self.LINE_CHANNEL_SECRET and self.LINE_CHANNEL_ACCESS_TOKEN)

    @property
    def line_login_enabled(self) -> bool:
        return bool(self.AUTH_LINE_ENABLED and self.LINE_LOGIN_CHANNEL_ID and self.LINE_LOGIN_CHANNEL_SECRET)

    @property
    def smtp_security(self) -> str:
        if self.SMTP_SECURITY in ("starttls", "ssl", "none"):
            return self.SMTP_SECURITY
        if self.SMTP_PORT == 465:
            return "ssl"
        return "starttls" if self.SMTP_USE_TLS else "none"

    @property
    def smtp_auth(self) -> bool:
        if self.SMTP_AUTH in ("1", "true", "yes", "on"):
            return True
        if self.SMTP_AUTH in ("0", "false", "no", "off"):
            return False
        return bool(self.SMTP_USERNAME)

    @property
    def smtp_configured(self) -> bool:
        """ส่งอีเมลจริงได้ไหม — login: ต้องมี username+password · ไม่ login (relay ภายใน): ต้องมี SMTP_FROM"""
        if self.smtp_auth:
            return bool(self.SMTP_USERNAME and self.SMTP_PASSWORD)
        return bool(self.SMTP_FROM and self.SMTP_SERVER)

    def ensure_dirs(self) -> None:
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.WORKING_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
