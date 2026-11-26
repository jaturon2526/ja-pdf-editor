// เมนูบนสุดของหน้า Editor (ไฟล์ / แก้ไข / มุมมอง / ...) — แยกมาจาก Editor.jsx
// ฟังก์ชันล้วน: รับ state + handler แล้วคืนโครงสร้างเมนูให้ <MenuBar>

const FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLScPacKO8qkTy1nKWqVcBph5uZ0sfEKFoI1miugStIk7OyACpA/viewform?usp=header";

export function buildEditorMenus({
  session,
  activeTool,
  setActiveTool,
  canUndo,
  canRedo,
  isSidebarOpen,
  setIsSidebarOpen,
  goToDashboard,
  openCreateBlank,
  openOfficeDialog,
  openFileDialog,
  saveToServer,
  download,
  print,
  closeDocument,
  openExtract,
  openSaveCopy,
  undo,
  redo,
  openFind,
  zoomIn,
  zoomOut,
  setZoom,
  continuousMode,
  toggleContinuousMode,
  docPropsHook,
  signatureHook,
  openRedactSearch,
  runOcrLayer,
  openPii,
  openWatermark,
  openPageNumbers,
  openInsertPages,
  openBarcode,
  openStamp,
  insertImage,
  openCompress,
  openFlatten,
  openConvertWord,
  openCompare,
  openAbout,
}) {
  const noDoc = !session;
  const toggleTool = (tool) => () => setActiveTool(activeTool === tool ? null : tool);

  return [
    {
      label: "ไฟล์",
      items: [
        { label: "← กลับหน้าเอกสารของฉัน", onClick: goToDashboard },
        { divider: true },
        { label: "สร้างเอกสารเปล่า...", hint: "หน้าเปล่า / ออกแบบแบบฟอร์ม", onClick: openCreateBlank },
        { label: "สร้างจาก Office...", onClick: openOfficeDialog },
        { label: "เปิดไฟล์...", shortcut: "Ctrl+O", onClick: openFileDialog },
        { divider: true },
        { label: "บันทึก (ทับไฟล์เดิม)", shortcut: "Ctrl+S", onClick: saveToServer, disabled: noDoc },
        { label: "แยกหน้า / ส่งออกเป็นรูปภาพ...", onClick: openExtract, disabled: noDoc },
        { label: "บันทึกเป็นไฟล์ใหม่...", onClick: openSaveCopy, disabled: noDoc },
        { label: "ดาวน์โหลด", onClick: download, disabled: noDoc },
        { label: "พิมพ์เอกสาร...", shortcut: "Ctrl+P", onClick: print, disabled: noDoc },
        { divider: true },
        session?.isPasswordProtected
          ? { label: "ลบรหัสผ่าน...", onClick: docPropsHook.handleRemovePassword, disabled: noDoc }
          : { label: "เข้ารหัส PDF...", onClick: docPropsHook.handleOpenAddPassword, disabled: noDoc },
        { divider: true },
        { label: "คุณสมบัติเอกสาร...", onClick: docPropsHook.handleOpenDocProps, disabled: noDoc },
        { divider: true },
        { label: "ปิดเอกสาร", shortcut: "Alt+Q (Mac: ⌥Q)", onClick: closeDocument, disabled: noDoc },
      ],
    },
    {
      label: "แก้ไข",
      items: [
        { label: "เลิกทำ", shortcut: "Ctrl+Z", onClick: undo, disabled: noDoc || !canUndo },
        { label: "ทำซ้ำ", shortcut: "Ctrl+Y", onClick: redo, disabled: noDoc || !canRedo },
        { divider: true },
        { label: "ค้นหาในเอกสาร...", shortcut: "Ctrl+F", onClick: openFind, disabled: noDoc },
      ],
    },
    {
      label: "มุมมอง",
      items: [
        {
          label: isSidebarOpen ? "ซ่อนแผงด้านข้าง (Sidebar)" : "แสดงแผงด้านข้าง (Sidebar)",
          onClick: () => setIsSidebarOpen(!isSidebarOpen),
        },
        {
          label: continuousMode ? "✓ เลื่อนหน้าต่อเนื่อง" : "เลื่อนหน้าต่อเนื่อง",
          hint: continuousMode ? "คลิกเพื่อสลับเป็นแสดงทีละหน้า" : "เลื่อนดูทุกหน้าต่อเนื่องแนวตั้ง",
          onClick: toggleContinuousMode,
          disabled: noDoc,
        },
        { divider: true },
        { label: "ขยาย", shortcut: "Ctrl++", onClick: zoomIn, disabled: noDoc },
        { label: "ย่อ", shortcut: "Ctrl+-", onClick: zoomOut, disabled: noDoc },
        { label: "ขนาดจริง (100%)", shortcut: "Ctrl+0", onClick: () => setZoom(1), disabled: noDoc },
      ],
    },
    {
      label: "แทรก",
      items: [
        { label: "แทรกข้อความ", hint: "เพิ่มกล่องข้อความใหม่บนหน้า", onClick: toggleTool("insert_text"), disabled: noDoc },
        { label: "แทรกรูปภาพ", hint: "เลือกไฟล์รูปมาวางบนหน้า", onClick: insertImage, disabled: noDoc },
        { label: "แทรกตาราง...", hint: "กำหนดแถวและคอลัมน์เริ่มต้น", onClick: toggleTool("edit_table"), disabled: noDoc },
        { label: "ตราประทับ...", hint: "สำเนาถูกต้อง · อนุมัติแล้ว · ลับ", onClick: openStamp, disabled: noDoc },
        { label: "บาร์โค้ด / QR Code...", hint: "สร้างบาร์โค้ด/QR ใหม่ลงหน้า", onClick: openBarcode, disabled: noDoc },
        { label: "ย้าย / ลบบาร์โค้ดในหน้า", hint: "จัดตำแหน่งหรือลบบาร์โค้ดเดิม", onClick: toggleTool("edit_barcode"), disabled: noDoc },
        { label: "เลขหน้า...", hint: "1/N · เลขไทย · สลับหน้าคู่", onClick: openPageNumbers, disabled: noDoc },
        { label: "แทรกหน้า...", hint: "จากไฟล์ / เอกสารของฉัน / หน้าว่าง", onClick: openInsertPages, disabled: noDoc },
      ],
    },
    {
      label: "คำอธิบายประกอบ",
      items: [
        { label: "เน้นข้อความ", onClick: () => setActiveTool("highlight"), disabled: noDoc },
        { label: "กล่องข้อความ", onClick: () => setActiveTool("freetext"), disabled: noDoc },
        { label: "รูปสี่เหลี่ยม", onClick: () => setActiveTool("rect"), disabled: noDoc },
        { label: "บันทึกย่อ", onClick: () => setActiveTool("text_note"), disabled: noDoc },
        { divider: true },
        { label: "ยกเลิกเครื่องมือ", onClick: () => setActiveTool(null), disabled: !activeTool },
      ],
    },
    {
      label: "เครื่องมือ",
      items: [
        { label: "แก้ไขข้อความ", hint: "แก้ข้อความ ฟอนต์ สี ขนาด", onClick: toggleTool("edit_text"), disabled: noDoc },
        { label: "แก้ไขรูปภาพ", hint: "ย้าย ย่อขยาย คัดลอก วาง ลบ", onClick: toggleTool("edit_image"), disabled: noDoc },
        { label: "แก้ไขตาราง", hint: "ย้าย ขนาด คอลัมน์ แถว พิมพ์ในเซลล์", onClick: toggleTool("edit_table"), disabled: noDoc },
        { label: "ย้าย / ลบบาร์โค้ด", hint: "บาร์โค้ดและ QR ในหน้า", onClick: toggleTool("edit_barcode"), disabled: noDoc },
        { label: "ตัดขอบหน้ากระดาษ...", hint: "ครอปขอบขาว · หน้านี้ / ทุกหน้า", onClick: toggleTool("crop_page"), disabled: noDoc },
        { label: "กรอกแบบฟอร์ม...", hint: "กรอก · ออกแบบช่องฟอร์ม", onClick: toggleTool("fill_form"), disabled: noDoc },
        { label: "เซ็นเซอร์", hint: "ลากคลุมปิดข้อมูลถาวร", onClick: toggleTool("redact"), disabled: noDoc },
        { label: "ตรวจฟอนต์", hint: "ชื่อฟอนต์ ขนาด การฝัง", onClick: toggleTool("inspect_font"), disabled: noDoc },
        { label: "เซ็นเซอร์ด้วยคำค้นหา...", hint: "ค้นหาคำแล้วปิดทับทั้งเอกสาร", onClick: openRedactSearch, disabled: noDoc },
        { label: "อ่านข้อความในรูปภาพ (OCR)", hint: "ทำให้ค้นหาและคัดลอกข้อความได้", onClick: runOcrLayer, disabled: noDoc },
        { label: "ตรวจหาข้อมูลส่วนบุคคล (PDPA)...", hint: "สแกนเลขบัตร เบอร์โทร อีเมล", onClick: openPii, disabled: noDoc },
        { divider: true },
        { label: "ใส่ลายน้ำ...", hint: "ข้อความทับทุกหน้า", onClick: openWatermark, disabled: noDoc },
        { label: "ลดขนาดไฟล์...", hint: "บีบอัดให้ไฟล์เล็กลง", onClick: openCompress, disabled: noDoc },
        { label: "รวมเลเยอร์...", hint: "ฝังฟอร์มและลายเซ็นลงหน้า", onClick: openFlatten, disabled: noDoc },
        { divider: true },
        { label: "เปรียบเทียบกับ...", hint: "ไฟล์อื่น / เวอร์ชันก่อนหน้า", onClick: openCompare, disabled: noDoc },
        { label: "แปลงเป็น Word...", hint: "รองรับไฟล์สแกน", onClick: openConvertWord, disabled: noDoc },
      ],
    },
    {
      label: "ลายเซ็นดิจิทัล",
      items: [
        {
          label: "ลายเซ็นอิเล็กทรอนิกส์...",
          hint: "วาด อัปโหลด หรือใช้ลายเซ็นที่บันทึกไว้",
          onClick: signatureHook.handleOpenElectronicSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
        {
          label: "เซ็นดิจิทัลรับรอง...",
          hint: "ลงนามรับรองด้วยใบรับรอง .p12 / .pfx",
          onClick: signatureHook.handleOpenDigitalSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
      ],
    },
    {
      label: "วิธีใช้",
      items: [
        { label: "คู่มือการใช้งาน...", onClick: () => window.open("/manual.html", "_blank") },
        { label: "ข้อเสนอแนะ / แจ้งปัญหา...", onClick: () => window.open(FEEDBACK_FORM_URL, "_blank", "noopener,noreferrer") },
        { divider: true },
        { label: "เกี่ยวกับ JA PDF Editor", onClick: openAbout },
      ],
    },
  ];
}
