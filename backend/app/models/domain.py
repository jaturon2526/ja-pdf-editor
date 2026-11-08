from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Float, ForeignKey, LargeBinary, Text, UniqueConstraint, true
from sqlalchemy.orm import deferred, relationship
from sqlalchemy.sql import func
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)

    @property
    def avatar_url(self):
        """URL รูปโปรไฟล์ที่ตั้งเอง (แนบ token — <img> ส่ง header ไม่ได้) · ?v= เปลี่ยนเมื่อเปลี่ยนรูป · ไม่ได้ตั้ง = None"""
        if not self.avatar_updated_at:
            return None
        from app.core.security import make_resource_token
        v = int(self.avatar_updated_at.timestamp())
        return f"/api/auth/avatar/{self.id}.png?t={make_resource_token('avatar', self.id)}&v={v}"
    display_name = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)
    # รูปโปรไฟล์ที่ตั้งเอง (PNG ~256px) — deferred: โหลดเฉพาะตอนขอรูป ไม่ติดมากับทุก query ของผู้ใช้
    avatar_png = deferred(Column(LargeBinary, nullable=True))
    avatar_emoji = Column(String(60), nullable=True)  # "face|#face|#bg" ถ้าเป็นอีโมจิ (เปิดหน้าเลือกแล้วตั้งค่าเดิมไว้)
    avatar_updated_at = Column(DateTime(timezone=True), nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False) # เพิ่มฟิลด์ยืนยันอีเมล
    is_admin = Column(Boolean, default=False) # ฟิลด์สำหรับผู้ดูแลระบบ
    accepted_tos = Column(Boolean, default=False, server_default="false") # เพิ่มฟิลด์ยอมรับข้อตกลง
    
    # License & Subscription
    plan_type = Column(String, default="free") # free, pro, premium
    expire_date = Column(DateTime(timezone=True), nullable=True) # null = ถาวร
    max_sessions = Column(Integer, default=1)
    
    # User's Personal Settings
    # API key ส่วนตัวสำหรับ AI (ชื่อคอลัมน์เดิม — เก็บ key ของทุกค่าย) + ค่ายที่เลือก (ว่าง = gemini) — ดู services/ai_client.py
    encrypted_gemini_key = Column(String, nullable=True)
    ai_provider = Column(String(20), nullable=True)
    ai_model = Column(String(100), nullable=True)
    ai_base_url = Column(String(300), nullable=True)
    # รับอีเมลแจ้งเตือนการลงนาม (ถึงคิว/ถูกปฏิเสธ/ครบแล้ว/เตือน) — ปิดได้ที่หน้าการลงนาม
    signing_email_notifications = Column(Boolean, nullable=False, default=True, server_default=true())
    # LINE (Messaging API) — ผูกผ่านรหัสที่ส่งในแชท OA (ดู services/line_service.py)
    # ผูกแล้ว + เปิด line_notifications → แจ้งเตือนการลงนามไปทาง LINE แทนอีเมล
    line_user_id = Column(String(64), unique=True, index=True, nullable=True)
    line_display_name = Column(String(255), nullable=True)
    line_linked_at = Column(DateTime(timezone=True), nullable=True)
    line_notifications = Column(Boolean, nullable=False, default=True, server_default=true())
    # LINE Login (เข้าสู่ระบบด้วย LINE) — userId ของ provider เดียวกับ OA แยกจาก line_user_id (แจ้งเตือน)
    # เพราะผู้ใช้บล็อก OA (ยกเลิกแจ้งเตือน) แล้วยังต้องเข้าสู่ระบบด้วย LINE ได้
    line_login_id = Column(String(64), unique=True, index=True, nullable=True)
    
    @property
    def has_api_key(self) -> bool:
        return bool(self.encrypted_gemini_key)

    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    files = relationship("FileRecord", back_populates="owner")
    licenses = relationship("License", back_populates="owner")

class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)           # ชื่อที่แสดงผล (เปลี่ยนได้)
    original_filename = Column(String, nullable=True)  # ชื่อไฟล์จริงบน disk (ไม่เปลี่ยน)
    storage_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="files")

class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String, unique=True, index=True, nullable=False)
    plan_type = Column(String, nullable=False)
    duration_days = Column(Integer, nullable=True) # null = ถาวร
    max_sessions = Column(Integer, default=1)
    
    is_used = Column(Boolean, default=False)
    used_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="licenses")

class PlanConfig(Base):
    __tablename__ = "plan_configs"

    plan_type = Column(String, primary_key=True, index=True) # "free", "pro", "premium"
    max_sessions = Column(Integer, default=1)
    max_storage_mb = Column(Integer, default=100)

class ConversionTask(Base):
    __tablename__ = "conversion_tasks"

    id = Column(String, primary_key=True, index=True) # UUID string
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Optional user
    file_record_id = Column(Integer, ForeignKey("files.id"), nullable=True) # Reference to FileRecord if exists
    status = Column(String, default="pending") # pending, processing, completed, failed
    progress = Column(Integer, default=0) # 0-100
    result_file_path = Column(String, nullable=True) # Path to final DOCX
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AIUsageDaily(Base):
    """จำนวนการใช้ AI ต่อผู้ใช้ต่อวัน (เดิมเก็บใน Redis — ไม่มี Redis ก็ไม่นับ ทำให้โควต้าฟรีไม่ทำงาน)

    kind:
    - system_conversion : แปลง PDF→Word ด้วย API key ของระบบ (โควต้าฟรีรายวัน)
    - personal_request  : คำขอไป Gemini ด้วย API key ส่วนตัวของผู้ใช้ (นับต่อชุดข้อความ)
    - ai_request        : คำขอไป Gemini ทั้งหมด (ใช้ทำสถิติหน้า Admin)
    """
    __tablename__ = "ai_usage_daily"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", "kind", name="uq_ai_usage_user_date_kind"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    usage_date = Column(Date, nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    count = Column(Integer, nullable=False, default=0, server_default="0")


# ---------------------------------------------------------------------------
# ส่งเอกสารให้ลงนามตามลำดับ (ดู app/services/signing_service.py และ claude/plan-sequential-signing.md)
# ---------------------------------------------------------------------------

class SigningRequest(Base):
    """คำขอลงนาม 1 ชุด: เอกสารหนึ่งไฟล์ + ผู้ลงนามเรียงลำดับ 1..N

    status: in_progress → completed | rejected | cancelled
    current_order: เลข "ขั้น" (SigningStep.stage) ที่กำลังรอลงนาม (0 = ไม่มีแล้ว) — ขั้นเดียวกันมีได้หลายคน (ลงนามพร้อมกัน)
    version: เลขเวอร์ชันไฟล์ล่าสุด (UPLOAD_DIR/_signing/{id}/v{version}.pdf)
    """
    __tablename__ = "signing_requests"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_file_id = Column(Integer, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    result_file_id = Column(Integer, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="in_progress", server_default="in_progress", index=True)
    current_order = Column(Integer, nullable=False, default=1, server_default="1")
    version = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # เฟส 2: วันครบกำหนด + การส่งเตือน
    due_at = Column(DateTime(timezone=True), nullable=True)
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)
    due_soon_notified_at = Column(DateTime(timezone=True), nullable=True)
    overdue_notified_at = Column(DateTime(timezone=True), nullable=True)

    steps = relationship("SigningStep", order_by="SigningStep.order", cascade="all, delete-orphan",
                         back_populates="request")
    owner = relationship("User", foreign_keys=[owner_id])


class SigningStep(Base):
    """ผู้ลงนาม 1 คนในคำขอ — ฟิลด์ลายเซ็น (field_name) ถูกสร้างในไฟล์ไว้ตั้งแต่ตอนส่งคำขอ

    order: ลำดับในรายชื่อ 1..N (ไม่ซ้ำ ใช้ตั้งชื่อฟิลด์) · stage: ขั้นที่ต้องลงนาม — คนที่ stage เท่ากันลงนามพร้อมกันได้
    signer_user_id ว่าง = เชิญคนที่ยังไม่มีบัญชี (invite_email) ผูกบัญชีให้อัตโนมัติเมื่อสมัคร/ยืนยันอีเมลแล้ว login

    sign_type: electronic | digital | either (ผู้ส่งกำหนด)
    status: waiting (ยังไม่ถึงคิว) | pending (ถึงคิว) | signed | rejected
    rect: พิกัดกล่องลายเซ็นแบบเดียวกับ Editor (pt, มุมซ้ายบนเป็น 0,0)
    """
    __tablename__ = "signing_steps"
    __table_args__ = (UniqueConstraint("request_id", "order", name="uq_signing_step_order"),)

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    order = Column(Integer, nullable=False)
    stage = Column(Integer, nullable=False, default=1, server_default="1")
    signer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    invite_email = Column(String(255), nullable=True, index=True)
    sign_type = Column(String(20), nullable=False, default="either", server_default="either")
    field_name = Column(String(64), nullable=False)
    page = Column(Integer, nullable=False)
    x0 = Column(Float, nullable=False)
    y0 = Column(Float, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="waiting", server_default="waiting")
    signed_type = Column(String(20), nullable=True)  # electronic | digital — ที่ใช้จริง
    signed_at = Column(DateTime(timezone=True), nullable=True)
    cert_subject = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    # ยืนยันตัวตนด้วย passkey ก่อนลงนาม — require_passkey: ผู้ส่งบังคับ · verified_*: ผลการยืนยันจริง (บันทึกในหนังสือรับรอง)
    require_passkey = Column(Boolean, nullable=False, default=False, server_default="false")
    verified_method = Column(String(20), nullable=True)  # passkey
    verified_detail = Column(String(255), nullable=True)  # ชื่อ passkey ที่ใช้
    verified_at = Column(DateTime(timezone=True), nullable=True)
    # ผู้ลงนามที่ลบบัญชีแล้ว: signer_user_id = NULL และเก็บชื่อ/อีเมลไว้เป็นหลักฐานของเจ้าของเอกสาร
    signer_label = Column(String(255), nullable=True)

    request = relationship("SigningRequest", back_populates="steps")
    signer = relationship("User")


class SigningEvent(Base):
    """บันทึกหลักฐานทุกเหตุการณ์ของคำขอ (ส่ง/เปิดดู/ลงนาม/ปฏิเสธ/ยกเลิก/ครบแล้ว)"""
    __tablename__ = "signing_events"

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_label = Column(String(255), nullable=True)  # ชื่อ/อีเมลของผู้ทำรายการที่ลบบัญชีไปแล้ว
    action = Column(String(32), nullable=False)
    detail = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    sha256_before = Column(String(64), nullable=True)
    sha256_after = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ServiceUsageDaily(Base):
    """จำนวนการใช้บริการภายนอกต่อวัน (ทั้งระบบ) สำหรับกราฟในหน้า Admin — service: email, line"""
    __tablename__ = "service_usage_daily"
    __table_args__ = (UniqueConstraint("usage_date", "service", name="uq_service_usage_date_service"),)

    id = Column(Integer, primary_key=True)
    usage_date = Column(Date, nullable=False, index=True)
    service = Column(String(32), nullable=False)
    count = Column(Integer, nullable=False, default=0, server_default="0")


class Notification(Base):
    """แจ้งเตือนในระบบ (กระดิ่ง) — kind เช่น sign_turn, sign_rejected, sign_completed, sign_cancelled"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    request_id = Column(Integer, ForeignKey("signing_requests.id", ondelete="CASCADE"), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Passkey(Base):
    """Passkey (WebAuthn) สำหรับเข้าสู่ระบบโดยไม่ใช้รหัสผ่าน — ผู้ใช้ 1 คนมีได้หลายอัน (ต่ออุปกรณ์/ผู้จัดการรหัสผ่าน)
    ดู app/services/passkey_service.py

    - credential_id : base64url ของ credential ID ที่ authenticator สร้าง (ใช้หาแถวตอนเข้าสู่ระบบ)
    - public_key    : COSE public key ใช้ตรวจลายเซ็นตอนเข้าสู่ระบบ
    - user_handle   : base64url ของ user.id ฝั่ง WebAuthn (สุ่ม ไม่ใช่ id ในฐานข้อมูล) — เหมือนกันทุกแถวของผู้ใช้คนเดียวกัน
    - backed_up     : ซิงก์ข้ามเครื่องได้ (iCloud Keychain / Google Password Manager)"""
    __tablename__ = "passkeys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(512), nullable=False, unique=True, index=True)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(Integer, nullable=False, default=0, server_default="0")
    user_handle = Column(String(128), nullable=False)
    transports = Column(String(255), nullable=True)
    name = Column(String(100), nullable=False)
    aaguid = Column(String(64), nullable=True)
    backed_up = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
