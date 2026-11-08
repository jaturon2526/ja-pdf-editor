import React, { useState } from 'react';
import { acceptToS } from '../api';
import { useAppName } from '../hooks/useAppName.js';

// Inline SVG icons (no external dependency needed)
const IconShield = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    <polyline points="9 12 11 14 15 10"/>
  </svg>
);
const IconWarning = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
    <line x1="12" y1="9" x2="12" y2="13"/>
    <line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
);

export default function TermsModal({ onAccepted, onDecline }) {
  const appName = useAppName();
  const [loading, setLoading] = useState(false);
  const [scrolledToBottom, setScrolledToBottom] = useState(false);

  const handleScroll = (e) => {
    const bottom = e.target.scrollHeight - e.target.scrollTop <= e.target.clientHeight + 20;
    if (bottom && !scrolledToBottom) {
      setScrolledToBottom(true);
    }
  };

  const handleAccept = async () => {
    try {
      setLoading(true);
      await acceptToS();
      if (onAccepted) onAccepted();
    } catch (err) {
      alert("เกิดข้อผิดพลาดในการบันทึกข้อมูล: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-300">
        
        {/* Header */}
        <div className="bg-sky-600 px-6 py-5 flex items-center gap-4 text-white">
          <div className="p-2 bg-white/20 rounded-xl">
            <IconShield />
          </div>
          <div>
            <h2 className="text-2xl font-bold font-sans">ข้อตกลงและเงื่อนไขการใช้บริการ</h2>
            <p className="text-sky-100 text-sm mt-1">กรุณาอ่านและยอมรับข้อตกลงก่อนเริ่มต้นใช้งาน {appName}</p>
          </div>
        </div>

        {/* Content Body */}
        <div 
          className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 text-slate-700 bg-slate-50"
          onScroll={handleScroll}
        >
          <div className="prose prose-sm md:prose-base max-w-none font-sans leading-relaxed">
            
            <p className="font-semibold text-slate-900 text-lg border-b pb-2">1. บทนำและการยอมรับข้อตกลง</p>
            <p>
              ยินดีต้อนรับสู่ {appName} ("บริการ") โดยการเข้าถึงและใช้งานแอปพลิเคชันนี้ ท่านตกลงที่จะผูกพันตามข้อกำหนดและเงื่อนไข ("ข้อตกลง") เหล่านี้ หากท่านไม่เห็นด้วยกับส่วนใดส่วนหนึ่งของข้อตกลงนี้ โปรดงดเว้นการใช้งานบริการ
            </p>

            <p className="font-semibold text-slate-900 text-lg border-b pb-2 mt-6">2. การอนุญาตให้ใช้สิทธิและสิทธิในทรัพย์สินทางปัญญา</p>
            <p>
              บริการนี้ให้สิทธิ์ท่านในการใช้งานส่วนบุคคลและ/หรือเพื่อธุรกิจของท่าน <strong>เอกสารทั้งหมดที่ท่านอัปโหลดเข้าสู่ระบบยังคงเป็นทรัพย์สินของท่าน 100%</strong> 
              เราไม่เรียกร้องสิทธิ์ความเป็นเจ้าของในเนื้อหาใดๆ ของท่าน อย่างไรก็ตาม ท่านให้สิทธิ์การใช้งานชั่วคราวแก่ระบบของเราในการประมวลผล จัดเก็บ และดัดแปลงไฟล์ตามคำสั่งของท่าน (เช่น การลบเลเยอร์ หรือการประมวลผลข้อความ)
            </p>

            <p className="font-semibold text-slate-900 text-lg border-b pb-2 mt-6">3. การใช้บริการ AI และบุคคลที่สาม (Third-Party AI Services)</p>
            <p>
              คุณสมบัติบางประการของบริการนี้ (เช่น การแปลง PDF เป็น Word, การแก้ไขข้อความที่ผิดเพี้ยน, OCR) ขับเคลื่อนโดยเทคโนโลยีปัญญาประดิษฐ์ของบุคคลที่สาม (เช่น Google Gemini, Anthropic Claude, OpenAI หรือผู้ให้บริการที่ผู้ดูแลระบบหรือท่านเลือก) 
            </p>
            <ul className="list-disc pl-5 space-y-2 mt-2 text-slate-600">
              <li>ท่านตกลงที่จะไม่ใช้ฟีเจอร์ AI ในการประมวลผลเอกสารที่มีเนื้อหาผิดกฎหมาย อนาจาร หรือละเมิดสิทธิส่วนบุคคลของผู้อื่น</li>
              <li>การใช้ฟีเจอร์ AI จะต้องปฏิบัติตามนโยบายการใช้งานที่ยอมรับได้ (Acceptable Use Policy) ของผู้ให้บริการ API นั้น (เช่น Google, Anthropic, OpenAI)</li>
              <li>หากท่านให้ <strong>API Key ส่วนตัว</strong> ของท่านแก่ระบบ ระบบจะทำการเข้ารหัส (Encrypt) และจัดเก็บไว้อย่างปลอดภัย และจะใช้เพื่อส่งคำขอประมวลผลในนามของท่านเท่านั้น</li>
            </ul>

            <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-lg my-6">
              <h4 className="flex items-center gap-2 text-amber-800 font-bold mb-2">
                <IconWarning />
                4. ข้อจำกัดความรับผิดชอบ (Limitation of Liability)
              </h4>
              <p className="text-amber-900 text-sm">
                <strong>ซอฟต์แวร์และบริการนี้ให้บริการตามสภาพ ("AS IS")</strong> โดยไม่มีการรับประกันใดๆ ไม่ว่าโดยชัดแจ้งหรือโดยปริยาย ผู้พัฒนาจะไม่รับผิดชอบต่อ:
              </p>
              <ul className="list-disc pl-5 space-y-1 mt-2 text-amber-900 text-sm">
                <li>การสูญหาย เสียหาย หรือการรั่วไหลของข้อมูลและเอกสารของท่าน</li>
                <li>ความผิดพลาดในการประมวลผลไฟล์ (เช่น ไฟล์ PDF เสียหาย หรือข้อความผิดเพี้ยนจากการทำ OCR)</li>
                <li>ความเสียหายทางอ้อม ความเสียหายเกี่ยวเนื่อง หรือการสูญเสียผลกำไรทางธุรกิจ</li>
              </ul>
              <p className="text-amber-900 text-sm font-semibold mt-2">
                * ขอแนะนำให้ท่านสำรองข้อมูล (Backup) ต้นฉบับของไฟล์สำคัญทุกครั้งก่อนใช้งานเครื่องมือดัดแปลงข้อมูล เช่น ฟีเจอร์เซ็นเซอร์ข้อความ หรือ Flatten PDF
              </p>
            </div>

            <p className="font-semibold text-slate-900 text-lg border-b pb-2 mt-6">5. การใช้งานที่ต้องห้าม</p>
            <p>ท่านตกลงที่จะไม่:</p>
            <ul className="list-disc pl-5 space-y-2 mt-2 text-slate-600">
              <li>อัปโหลด ซ่อน หรือเผยแพร่ซอฟต์แวร์ที่เป็นอันตราย (Malware, Virus) ภายในไฟล์ PDF</li>
              <li>ใช้ระบบในทางที่ก่อให้เกิดภาระหนักหน่วงผิดปกติกับเซิร์ฟเวอร์ (เช่น การยิง Request สแปม)</li>
              <li>พยายามหลบเลี่ยงระบบจำกัดโควต้าพื้นที่เก็บข้อมูล หรือโควต้าการใช้ AI ประจำวัน</li>
              <li>วิศวกรรมย้อนกลับ (Reverse Engineer) คัดลอก หรือนำซอร์สโค้ดของแอปพลิเคชันไปใช้โดยไม่ได้รับอนุญาต</li>
            </ul>

            <p className="font-semibold text-slate-900 text-lg border-b pb-2 mt-6">6. การเปลี่ยนแปลงข้อตกลงและการยกเลิกบัญชี</p>
            <p>
              ผู้พัฒนาขอสงวนสิทธิ์ในการแก้ไขข้อตกลงนี้ได้ตลอดเวลา เราจะแจ้งให้ท่านทราบถึงการเปลี่ยนแปลงที่สำคัญ ผู้พัฒนาขอสงวนสิทธิ์ในการระงับหรือยกเลิกบัญชีผู้ใช้ของท่านทันทีหากพบว่ามีการละเมิดข้อตกลงฉบับนี้
            </p>
            <p className="mt-6 text-sm">
              อ่านฉบับเต็มได้ที่{" "}
              <a href="/terms" target="_blank" rel="noreferrer" className="text-sky-700 underline">ข้อกำหนดการใช้งาน</a> และ{" "}
              <a href="/privacy" target="_blank" rel="noreferrer" className="text-sky-700 underline">นโยบายความเป็นส่วนตัว</a>
            </p>

          </div>
        </div>

        {/* Footer / Actions */}
        <div className="bg-white px-6 py-5 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className={`text-sm transition-colors duration-300 ${scrolledToBottom ? 'text-green-600 font-medium' : 'text-slate-500'}`}>
            {scrolledToBottom 
              ? '✓ คุณได้อ่านข้อตกลงจนครบถ้วนแล้ว' 
              : '↓ โปรดเลื่อนอ่านข้อตกลงให้ครบถ้วนก่อนกดยอมรับ'}
          </p>
          <div className="flex gap-3 w-full sm:w-auto">
            <button
              onClick={onDecline}
              disabled={loading}
              className="flex-1 sm:flex-none px-6 py-2.5 rounded-xl font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors"
            >
              ปฏิเสธและออกจากระบบ
            </button>
            <button
              onClick={handleAccept}
              disabled={!scrolledToBottom || loading}
              className={`flex-1 sm:flex-none px-8 py-2.5 rounded-xl font-bold text-white transition-all duration-300 ${
                !scrolledToBottom || loading
                  ? 'bg-sky-300 cursor-not-allowed'
                  : 'bg-sky-600 hover:bg-sky-700 shadow-md hover:shadow-lg'
              }`}
            >
              {loading ? 'กำลังบันทึก...' : 'ฉันยอมรับข้อตกลง'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
