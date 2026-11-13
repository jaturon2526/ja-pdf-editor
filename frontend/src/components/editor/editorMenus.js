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
  zoomIn,
  zoomOut,
  setZoom,
  docPropsHook,
  signatureHook,
  openRedactSearch,
  runOcrLayer,
  openPii,
  openWatermark,
  openPageNumbers,
  openBarcode,
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
      ],
    },
    {
      label: "มุมมอง",
      items: [
        {
          label: isSidebarOpen ? "ซ่อนแผงด้านข้าง (Sidebar)" : "แสดงแผงด้านข้าง (Sidebar)",
          onClick: () => setIsSidebarOpen(!isSidebarOpen),
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
        { label: "แทรกข้อความ", onClick: toggleTool("insert_text"), disabled: noDoc },
        { label: "แทรกรูปภาพ", onClick: insertImage, disabled: noDoc },
        { label: "บาร์โค้ด / QR Code...", onClick: openBarcode, disabled: noDoc },
        { label: "เลขหน้า...", onClick: openPageNumbers, disabled: noDoc },
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
        { label: "แก้ไขข้อความ", onClick: toggleTool("edit_text"), disabled: noDoc },
        { label: "แก้ไขรูปภาพ", onClick: toggleTool("edit_image"), disabled: noDoc },
        { label: "เซ็นเซอร์", onClick: toggleTool("redact"), disabled: noDoc },
        { label: "เซ็นเซอร์ด้วยคำค้นหา...", onClick: openRedactSearch, disabled: noDoc },
        { label: "อ่านข้อความในรูปภาพ (OCR)", onClick: runOcrLayer, disabled: noDoc },
        { label: "ตรวจหาข้อมูลส่วนบุคคล (PDPA)...", onClick: openPii, disabled: noDoc },
        { divider: true },
        { label: "ใส่ลายน้ำ...", onClick: openWatermark, disabled: noDoc },
        { label: "ลดขนาดไฟล์...", onClick: openCompress, disabled: noDoc },
        { label: "รวมเลเยอร์...", onClick: openFlatten, disabled: noDoc },
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
          onClick: signatureHook.handleOpenElectronicSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
        {
          label: "เซ็นดิจิทัลรับรอง...",
          onClick: signatureHook.handleOpenDigitalSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
      ],
    },
    {
      label: "วิธีใช้",
      items: [
        { label: "คู่มือการใช้งาน...", onClick: () => window.open("/manual.html", "_blank") },
        { label: "ข้อเสนอแนะ / แจ้งปัญหา...", onClick: () => window.open(FEEDBACK_FORM_URL, "_blank") },
        { divider: true },
        { label: "เกี่ยวกับ JA PDF Editor", onClick: openAbout },
      ],
    },
  ];
}
