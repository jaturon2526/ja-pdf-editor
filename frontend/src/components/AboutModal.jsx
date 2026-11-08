import React from "react";
import SourceCodeLink from "./SourceCodeLink.jsx";

export const APP_VERSION = "v1.33.2";

const OSS_CREDITS = [
  // ---- Backend (Python) ----
  { name: "FastAPI", role: "Backend API framework", license: "MIT License" },
  { name: "Uvicorn", role: "ASGI server", license: "BSD-3-Clause" },
  { name: "Pydantic", role: "ตรวจสอบ/validate ข้อมูล API", license: "MIT License" },
  { name: "python-multipart", role: "รับไฟล์อัปโหลดแบบ multipart", license: "Apache License 2.0" },
  { name: "PyMuPDF (fitz)", role: "อ่าน/เขียน/เรนเดอร์ PDF หลัก", license: "GNU AGPL v3" },
  { name: "fpdf2", role: "วาดข้อความไทยแบบ Vector และหนังสือรับรองการลงนาม", license: "LGPL-3.0" },
  { name: "uharfbuzz (HarfBuzz)", role: "จัดสระและวรรณยุกต์ภาษาไทย (Text Shaping)", license: "Apache License 2.0" },
  { name: "pyHanko + pyhanko-certvalidator", role: "ลายเซ็นดิจิทัล PAdES, ลงนามตามลำดับ, ประทับเวลา TSA, ตรวจลายเซ็น", license: "MIT License" },
  { name: "asn1crypto", role: "อ่านใบรับรอง X.509 และเติม chain ของผู้ออกใบรับรอง", license: "MIT License" },
  { name: "cryptography", role: "เข้ารหัส และจัดการใบรับรองดิจิทัล (X.509 / PKCS#12)", license: "Apache-2.0 / BSD-3-Clause" },
  { name: "certifi", role: "ฐานข้อมูลใบรับรองที่เชื่อถือได้ (Mozilla CA Bundle)", license: "MPL-2.0" },
  { name: "aiohttp", role: "ติดต่อ TSA เพื่อขอประทับเวลาลายเซ็น", license: "Apache-2.0 / MIT" },
  { name: "pikepdf (qpdf)", role: "ถอดรหัสรหัสผ่าน PDF", license: "MPL-2.0" },
  { name: "segno", role: "สร้าง QR code สำหรับเชื่อมต่อ LINE และ QR พร้อมเพย์", license: "BSD-3-Clause" },
  { name: "zxing-cpp", role: "อ่าน QR ในสลิปโอนเงิน (กันสลิปซ้ำ)", license: "Apache License 2.0" },
  { name: "PyThaiNLP", role: "ตัดคำภาษาไทย", license: "Apache License 2.0" },
  { name: "Pillow", role: "ประมวลผลรูปภาพ และตราลายเซ็น", license: "MIT-CMU License" },
  { name: "Tesseract OCR + pytesseract", role: "OCR แปลงรูปภาพเป็น Searchable PDF", license: "Apache License 2.0" },
  { name: "treepoem + BWIPP", role: "สร้างบาร์โค้ด/QR (เมนูแทรก และ Auto-Gen)", license: "MIT License" },
  { name: "py_webauthn + @simplewebauthn/browser", role: "เข้าสู่ระบบด้วย Passkey", license: "BSD-3-Clause / MIT" },
  { name: "fontTools + Brotli", role: "ตรวจ/แปลงไฟล์ฟอนต์ที่ผู้ใช้ติดตั้ง", license: "MIT License" },
  { name: "pdf2docx", role: "แปลงไฟล์ PDF เป็น Word (แบบแก้ไขข้อความได้อิสระ)", license: "GNU GPL v3" },
  { name: "python-docx", role: "สร้างและแก้ไขโครงสร้างไฟล์ Word", license: "MIT License" },
  { name: "docxtpl", role: "สร้างเอกสาร Word จาก Template", license: "LGPL-2.1" },
  { name: "docxcompose", role: "รวมไฟล์ Word เข้าด้วยกัน", license: "MIT License" },
  { name: "openpyxl", role: "อ่านไฟล์ Excel (.xlsx)", license: "MIT License" },
  { name: "Jinja2", role: "Template Engine (Auto-Gen)", license: "BSD-3-Clause" },
  { name: "Google Gen AI SDK (google-genai)", role: "เชื่อมต่อ Gemini: AI แก้คำไทยใน PDF เป็น Word และ OCR (Claude / OpenAI เรียกผ่าน HTTP โดยตรง)", license: "Apache License 2.0" },
  { name: "SQLAlchemy", role: "Database ORM", license: "MIT License" },
  { name: "Alembic", role: "อัปเกรดโครงสร้างฐานข้อมูล (Migrations)", license: "MIT License" },
  { name: "psycopg 3", role: "เชื่อมต่อฐานข้อมูล PostgreSQL", license: "LGPL-3.0" },
  { name: "redis-py", role: "เชื่อมต่อ Redis (เซสชันแบบหลายเครื่อง)", license: "MIT License" },
  { name: "passlib", role: "จัดการการเข้ารหัสรหัสผ่าน", license: "BSD License" },
  { name: "bcrypt", role: "อัลกอริทึมเข้ารหัสรหัสผ่านผู้ใช้", license: "Apache License 2.0" },
  { name: "python-jose", role: "สร้างและตรวจสอบ JWT Token", license: "MIT License" },
  { name: "email-validator", role: "ตรวจสอบความถูกต้องของอีเมล", license: "Unlicense" },
  { name: "google-auth", role: "ตรวจสอบการเข้าสู่ระบบด้วย Google", license: "Apache License 2.0" },
  { name: "tzdata", role: "ฐานข้อมูลเขตเวลา (เวลาในอีเมลและหนังสือรับรอง)", license: "Apache License 2.0" },
  // ---- Frontend ----
  { name: "React + React DOM", role: "Frontend UI framework", license: "MIT License" },
  { name: "React Router", role: "จัดการเส้นทาง URL ของหน้าเว็บ", license: "MIT License" },
  { name: "@react-oauth/google", role: "ปุ่มเข้าสู่ระบบด้วย Google Account", license: "MIT License" },
  { name: "OpenCV.js (@techstark/opencv-js)", role: "หาขอบเอกสารในเครื่องสแกน", license: "Apache License 2.0" },
  { name: "Tailwind CSS", role: "CSS framework สำหรับจัดรูปแบบหน้าจอและคู่มือ", license: "MIT License" },
  { name: "Vite", role: "Frontend build tool", license: "MIT License" },
  { name: "Vitest + Playwright", role: "ทดสอบระบบอัตโนมัติ (Unit / E2E)", license: "MIT / Apache License 2.0" },
  // ---- โปรแกรมและบริการ ----
  { name: "Ghostscript", role: "บีบอัดขนาดไฟล์ แปลงเป็น PDF/A และเวอร์ชัน PDF", license: "GNU AGPL v3" },
  { name: "LibreOffice", role: "แปลงไฟล์เอกสาร Office เป็น PDF", license: "MPL-2.0" },
  { name: "PostgreSQL", role: "ฐานข้อมูลหลักของระบบ", license: "PostgreSQL License" },
  { name: "Redis", role: "จัดการแคชและจำกัดเซสชัน", license: "RSALv2 / SSPLv1 (7.4+)" },
  { name: "Nginx", role: "Web server / Reverse proxy", license: "BSD-2-Clause" },
  { name: "Docker", role: "Container platform สำหรับ deploy ระบบ", license: "Apache License 2.0" },
  {
    name: "ฟอนต์ไทยเปิดเผย",
    role: "Sarabun, Kanit, Noto Sans Thai, Prompt, Mitr",
    license: "SIL Open Font License 1.1",
  },
];

export default function AboutModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 sm:p-6" onClick={onClose}>
      <div 
        className="bg-white w-full max-w-3xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-fade-in-up" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Section */}
        <div className="bg-gradient-to-br from-[#08092e] via-[#131850] to-[#1e1b6e] p-8 text-center relative shrink-0">
          <div className="absolute top-4 right-4">
            <button 
              onClick={onClose}
              className="text-white/70 hover:text-white transition-colors bg-white/10 hover:bg-white/20 rounded-full p-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          {/* JA PDF Editor Icon */}
          <div className="flex justify-center mb-5">
            <div className="w-24 h-24 drop-shadow-[0_0_18px_rgba(34,211,238,0.5)]">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" className="w-full h-full">
                <defs>
                  <radialGradient id="ab-outerBg" cx="50%" cy="35%" r="70%">
                    <stop offset="0%" stopColor="#1e1b6e"/>
                    <stop offset="100%" stopColor="#08092e"/>
                  </radialGradient>
                  <radialGradient id="ab-innerBg" cx="50%" cy="42%" r="65%">
                    <stop offset="0%" stopColor="#131850"/>
                    <stop offset="100%" stopColor="#060921"/>
                  </radialGradient>
                  <filter id="ab-hexGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur in="SourceGraphic" stdDeviation="8" result="blur"/>
                    <feMerge><feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                  </filter>
                  <filter id="ab-jGlow" x="-35%" y="-25%" width="170%" height="150%">
                    <feGaussianBlur in="SourceAlpha" stdDeviation="14" result="blur"/>
                    <feFlood floodColor="#93c5fd" floodOpacity="0.85" result="color"/>
                    <feComposite in="color" in2="blur" operator="in" result="glow"/>
                    <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
                  </filter>
                  <filter id="ab-aGlow" x="-35%" y="-25%" width="170%" height="150%">
                    <feGaussianBlur in="SourceAlpha" stdDeviation="14" result="blur"/>
                    <feFlood floodColor="#fb923c" floodOpacity="0.95" result="color"/>
                    <feComposite in="color" in2="blur" operator="in" result="glow"/>
                    <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
                  </filter>
                  <filter id="ab-orbGlow" x="-150%" y="-150%" width="400%" height="400%">
                    <feGaussianBlur in="SourceGraphic" stdDeviation="16" result="blur"/>
                    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                  </filter>
                </defs>
                <circle cx="256" cy="256" r="256" fill="url(#ab-outerBg)"/>
                <circle cx="256" cy="265" r="220" fill="url(#ab-innerBg)"/>
                <polygon points="256,58 424,155 424,353 256,450 88,353 88,155" fill="none" stroke="#22d3ee" strokeWidth="14" filter="url(#ab-hexGlow)" opacity="0.8"/>
                <polygon points="256,58 424,155 424,353 256,450 88,353 88,155" fill="none" stroke="#22d3ee" strokeWidth="2.5" opacity="0.95"/>
                <text x="174" y="318" fontFamily="'Arial Black','Impact','Helvetica Neue',Arial,sans-serif" fontSize="192" fontWeight="900" fill="white" textAnchor="middle" filter="url(#ab-jGlow)">J</text>
                <text x="340" y="318" fontFamily="'Arial Black','Impact','Helvetica Neue',Arial,sans-serif" fontSize="192" fontWeight="900" fill="#fbbf24" textAnchor="middle" filter="url(#ab-aGlow)">A</text>
                <circle cx="256" cy="266" r="20" fill="#22d3ee" filter="url(#ab-orbGlow)" opacity="0.6"/>
                <circle cx="256" cy="266" r="12" fill="#06b6d4"/>
                <circle cx="256" cy="266" r="6" fill="#e0f9fe"/>
                <circle cx="254" cy="264" r="3" fill="white"/>
                <circle cx="206" cy="403" r="5.5" fill="#22d3ee" opacity="0.7"/>
                <circle cx="256" cy="416" r="6" fill="#22d3ee" opacity="0.9"/>
                <circle cx="306" cy="403" r="5.5" fill="#22d3ee" opacity="0.7"/>
                <text x="256" y="480" fontFamily="Arial,'Helvetica Neue',sans-serif" fontSize="46" fontWeight="bold" fill="white" textAnchor="middle" letterSpacing="10" opacity="0.92">PDF</text>
              </svg>
            </div>
          </div>
          
          <div className="flex items-center justify-center gap-2 mb-1">
            <h2 className="text-3xl font-bold text-white">JA PDF Editor</h2>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-400/30">{APP_VERSION}</span>
          </div>
          <p className="text-cyan-300 text-xs font-medium tracking-widest uppercase mb-3">ทำงานร่วมกับ AI · Human × Antigravity × Claude</p>
          <p className="text-blue-200 text-sm max-w-xl mx-auto leading-relaxed opacity-85">
            ระบบจัดการเอกสาร PDF ครบวงจร — สร้าง, แก้ไขข้อความ/รูปภาพ, พิมพ์เอกสาร, แยกและรวมไฟล์, แปลงเป็น Word, สร้างเอกสารอัตโนมัติ (Mail Merge), ใส่ลายน้ำ, เข้ารหัส, ลายเซ็นดิจิทัล และส่งเอกสารให้ลงนามตามลำดับพร้อมหนังสือรับรองการลงนาม
          </p>
        </div>


        {/* Content Section (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8 bg-gray-50">
          
          <div className="grid sm:grid-cols-2 gap-4 mb-8">
            <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-100">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">ผู้พัฒนา</h4>
              <p className="text-base font-medium text-gray-900">จตุรนต์ พันธะสุมา</p>
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-100">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">พัฒนาด้วยความช่วยเหลือของ</h4>
              <p className="text-base font-medium text-gray-900 flex flex-wrap items-center gap-x-4">
                <span className="whitespace-nowrap">Antigravity <span className="text-xs font-normal text-gray-500">(Google DeepMind)</span></span>
                <span className="whitespace-nowrap">Claude <span className="text-xs font-normal text-gray-500">(Anthropic)</span></span>
              </p>
            </div>
          </div>

          <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-100 mb-8" data-testid="about-license">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">สัญญาอนุญาต</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              JA PDF Editor เป็นซอฟต์แวร์เสรีภายใต้ <b>GNU AGPL-3.0</b> — ใช้ ศึกษา แก้ไข และแจกจ่ายต่อได้ โดยฉบับที่แก้ไขแล้วนำไปให้บริการต้องเปิดซอร์สด้วยเช่นกัน
            </p>
            <p className="text-sm mt-2">
              <SourceCodeLink className="text-sky-700 underline font-medium">ดาวน์โหลดซอร์สโค้ด {APP_VERSION}</SourceCodeLink>
              <span className="text-gray-400"> · </span>
              <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer" className="text-sky-700 underline">อ่านสัญญาอนุญาต</a>
            </p>
          </div>

          <div>
            <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
              <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              Open Source Credits
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              โปรเจกต์นี้ขับเคลื่อนด้วยไลบรารีและเครื่องมือ Open Source ดังต่อไปนี้ (ลิขสิทธิ์ตามข้อมูลของแต่ละแพ็กเกจ ณ เวอร์ชันที่ใช้งาน):
            </p>
            
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 font-semibold text-gray-600">แพ็กเกจ (Package)</th>
                    <th className="px-4 py-3 font-semibold text-gray-600">หน้าที่การทำงาน</th>
                    <th className="px-4 py-3 font-semibold text-gray-600 whitespace-nowrap">ลิขสิทธิ์ (License)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {OSS_CREDITS.map((item, idx) => (
                    <tr key={idx} className="hover:bg-blue-50/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-gray-900">{item.name}</td>
                      <td className="px-4 py-3 text-gray-500">{item.role}</td>
                      <td className="px-4 py-3 text-gray-500">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 whitespace-nowrap">
                          {item.license}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
