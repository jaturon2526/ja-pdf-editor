"""Load test ของ JA PDF Editor (Locust) — จำลองผู้ใช้จริง: เข้าสู่ระบบ → อัปโหลด/เปิดไฟล์ → เลื่อนดูหน้า → แก้ไข → บันทึก

รันผ่าน scripts/loadtest/run.sh (สร้างบัญชีทดสอบ → ไล่จำนวนผู้ใช้ → เก็บสถิติเซิร์ฟเวอร์ → ลบบัญชีทดสอบ)
สัดส่วนผู้ใช้ (ดูแผน claude/phase-scalability-plan.md): ดูเอกสาร 60% · แก้ไข 35% · งานหนัก (บีบอัดไฟล์) 5%
แต่ละผู้ใช้จำลองใช้บัญชีของตัวเอง lt0001@loadtest.invalid … (จำกัดจำนวนอุปกรณ์ต่อบัญชีไม่ชนกัน)
ตั้งค่าด้วย environment: LT_TOKENS (ไฟล์ token จาก users.py seed) หรือ LT_PASSWORD, LT_PDF (ไฟล์ตัวอย่าง), LT_ZOOM (ซูมตอนแสดงหน้า ค่าเริ่มต้น 3 = 150% × จอ Retina)"""
import itertools
import os
import random
import threading
from pathlib import Path

from locust import HttpUser, between, events, task

PASSWORD = os.environ.get("LT_PASSWORD", "")
PDF_PATH = Path(os.environ.get("LT_PDF") or Path(__file__).with_name("sample.pdf"))
ZOOM = float(os.environ.get("LT_ZOOM", "3"))
# token ที่ users.py seed ออกให้ (run.sh เก็บไว้ในไฟล์) — ไม่ต้อง login พร้อมกันทีละร้อยคนจาก IP เดียว
TOKENS: dict[str, str] = {}
if os.environ.get("LT_TOKENS") and Path(os.environ["LT_TOKENS"]).exists():
    for line in Path(os.environ["LT_TOKENS"]).read_text().splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] == "TOKEN":
            TOKENS[parts[1]] = parts[2]
_ids = itertools.count(1)
_lock = threading.Lock()


def _next_email() -> str:
    with _lock:
        return f"lt{next(_ids):04d}@loadtest.invalid"


class _DocUser(HttpUser):
    abstract = True
    wait_time = between(2, 6)  # เวลาคิด/อ่านระหว่างการกระทำของคนจริง

    def on_start(self):
        email = _next_email()
        token = TOKENS.get(email)
        if not token:
            if not PASSWORD:
                raise RuntimeError("ต้องตั้ง LT_PASSWORD หรือ LT_TOKENS")
            r = self.client.post("/api/auth/login", data={"username": email, "password": PASSWORD}, name="login")
            r.raise_for_status()
            token = r.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"
        with PDF_PATH.open("rb") as f:
            up = self.client.post("/api/pdf/upload", files={"file": (PDF_PATH.name, f, "application/pdf")}, name="upload")
        up.raise_for_status()
        info = up.json()
        self.sid = info["session_id"]
        self.pages = max(1, int(info.get("page_count") or 1))
        self.page = 0
        self.view(first=True)

    def on_stop(self):
        sid = getattr(self, "sid", None)
        if sid:
            self.client.delete(f"/api/pdf/{sid}", name="close")

    def view(self, first=False):
        if not first:
            self.page = (self.page + random.choice((1, 1, 1, -1))) % self.pages
        self.client.get(f"/api/pdf/{self.sid}/page/{self.page}?zoom={ZOOM}", name="render page")
        self.client.get(f"/api/annotation/{self.sid}/page/{self.page}", name="annotations")


class Viewer(_DocUser):
    """อ่าน/เลื่อนดูเอกสาร"""
    weight = 60

    @task(10)
    def scroll(self):
        self.view()

    @task(1)
    def dashboard(self):
        self.client.get("/api/pdf/files", name="file list")


class Editor(_DocUser):
    """แก้ไข: ไฮไลต์/กล่องข้อความ · เลิกทำ · บันทึก"""
    weight = 35

    @task(6)
    def scroll(self):
        self.view()

    @task(3)
    def highlight(self):
        y = random.uniform(80, 700)
        self.client.post(f"/api/annotation/{self.sid}", name="add annotation", json={
            "page_number": self.page, "type": "highlight",
            "rect": {"x0": 60, "y0": y, "x1": 400, "y1": y + 14}, "color": [1, 0.9, 0.2]})

    @task(1)
    def undo(self):
        self.client.post(f"/api/pdf/{self.sid}/undo", name="undo")

    @task(1)
    def save(self):
        self.client.post(f"/api/pdf/{self.sid}/save", name="save")


class Heavy(_DocUser):
    """งานหนัก: บีบอัดไฟล์ (Ghostscript) แล้วเลิกทำ"""
    weight = 5
    wait_time = between(10, 20)

    @task(3)
    def scroll(self):
        self.view()

    @task(1)
    def compress(self):
        r = self.client.post(f"/api/pdf/{self.sid}/compress", json={"profile": "ebook"}, name="compress (heavy)")
        if r.ok and r.json().get("status") != "no_change":
            self.client.post(f"/api/pdf/{self.sid}/undo", name="undo")


@events.init_command_line_parser.add_listener
def _(parser):  # noqa: D401 — ให้ locust --help แสดงว่าตั้งค่าผ่าน env
    parser.add_argument("--lt-note", default="", help="ตั้งค่าด้วย env: LT_PASSWORD, LT_PDF, LT_ZOOM")
