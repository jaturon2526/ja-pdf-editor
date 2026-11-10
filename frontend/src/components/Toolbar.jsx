import React, { useEffect, useState } from "react";

const ICONS = {
  redact: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <rect x="2" y="4" width="12" height="8" rx="1" />
      <path d="M4 6L12 10M12 6L4 10" stroke="white" strokeWidth="1.5" />
    </svg>
  ),

  open: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3H6l1.2 1.5H12.5A1.5 1.5 0 0 1 14 6v5.5A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5v-7Z" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  save: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 2h8l3 3v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 2v3.5h5V2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 9.5h6V14H5z" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  download: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M8 2v9m0 0l-3-3m3 3l3-3M3 13h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  print: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M4 5.5V2h8v3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 11H2.5A1.5 1.5 0 0 1 1 9.5v-3A1.5 1.5 0 0 1 2.5 5h11A1.5 1.5 0 0 1 15 6.5v3a1.5 1.5 0 0 1-1.5 1.5H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="4" y="9" width="8" height="5" rx="0.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="12.5" cy="7.5" r="0.6" fill="currentColor" />
    </svg>
  ),
  zoomOut: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M13 13l-2.7-2.7M5 7h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  zoomIn: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M13 13l-2.7-2.7M7 5v4M5 7h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  select: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 2l9 4.6-3.6 1-1 3.6L3 2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  ),
  hand: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M6 8.2V3.4a1 1 0 0 1 2 0V7M8 7V2.6a1 1 0 0 1 2 0V7M10 7.2V3.8a1 1 0 0 1 2 0V9M4.2 9.5V6.9a1 1 0 0 1 2-.1l.2 4.2"
        stroke="currentColor"
        strokeWidth="1.15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4.2 9.6c0 3 1.9 4.9 4.6 4.9 2.9 0 4.6-1.7 4.7-4.4l.1-2.6"
        stroke="currentColor"
        strokeWidth="1.15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  highlight: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M9.5 2.5l4 4-6 6-4.2.8.8-4.2 5.4-6.6Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M2 14h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  freetext: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 3.5h10M8 3.5V13M6 13h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  rect: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="3.5" width="11" height="9" rx="1" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  note: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 3h10v7.5H7.5L4.5 13v-2.5H3V3Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  ),
  fitWidth: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="5" y="3" width="6" height="10" rx="0.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M3.5 8h-2M1.5 8l1.6-1.6M1.5 8l1.6 1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12.5 8h2M14.5 8l-1.6-1.6M14.5 8l-1.6 1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  fitHeight: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="3" y="5" width="10" height="6" rx="0.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 3.5v-2M8 1.5l-1.6 1.6M8 1.5l1.6 1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 12.5v2M8 14.5l-1.6-1.6M8 14.5l1.6-1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  close: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 2h6.5L12 4.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M9 2v2.5h2.5" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M5.3 8.3l3.4 3.4M8.7 8.3l-3.4 3.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  insertText: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 3.5h7M2 6.5h7M2 9.5h4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M12.5 8v5M10 10.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  insertImage: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="1.5" y="2.5" width="8" height="7" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="4" cy="5" r="0.9" fill="currentColor" />
      <path d="M2.3 8.2l2.3-2.3 1.6 1.6 1.4-1.4 1.4 1.4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12.5 8v5M10 10.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  undo: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 6h6.5a3.5 3.5 0 0 1 0 7H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5.8 3.2 2.8 6l3 2.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  redo: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M13 6H6.5a3.5 3.5 0 0 0 0 7H10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.2 3.2 13.2 6l-3 2.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  properties: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 7.3v4M8 5.2v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
};

function ToolbarButton({ icon, label, onClick, active, disabled }) {
  return (
    <button type="button"
      className={`p-1.5 rounded-lg transition-colors focus:outline-none flex items-center justify-center ${active ? "bg-sky-100 text-sky-700" : "text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"}`}
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
    >
      {ICONS[icon]}
    </button>
  );
}

const ZOOM_MIN_PCT = 10;
const ZOOM_MAX_PCT = 500;

// ช่องกรอกซูมเป็น % ได้ตรงๆ (พิมพ์เลขเอง แทนที่จะกดปุ่ม +/- อย่างเดียว)
// เก็บ text ที่พิมพ์อยู่แยกจาก zoom จริง เพื่อให้พิมพ์เลขระหว่างทาง (เช่นลบเลขเดิมออกก่อน) ได้อิสระ
// แล้วค่อย commit (พอ blur หรือกด Enter) — ถ้าเลขไม่ถูกต้องจะ revert กลับไปค่าซูมปัจจุบัน
function ZoomPercentInput({ zoom, onCommit, disabled }) {
  const [text, setText] = useState(String(Math.round(zoom * 100)));

  useEffect(() => {
    setText(String(Math.round(zoom * 100)));
  }, [zoom]);

  function commit() {
    const n = parseInt(text, 10);
    if (!Number.isNaN(n)) {
      const clamped = Math.min(ZOOM_MAX_PCT, Math.max(ZOOM_MIN_PCT, n));
      onCommit(clamped / 100);
      setText(String(clamped));
    } else {
      setText(String(Math.round(zoom * 100)));
    }
  }

  return (
    <span className="flex items-center mx-1 bg-slate-50 border border-slate-200 rounded-md overflow-hidden h-8 focus-within:ring-1 focus-within:ring-sky-500">
      <input
        className="w-10 text-center text-xs text-slate-700 bg-transparent border-none focus:outline-none focus:ring-0 p-0 m-0"
        type="text"
        inputMode="numeric"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value.replace(/[^0-9]/g, ""))}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        title="พิมพ์เปอร์เซ็นต์ซูม"
      />
      <span className="text-xs text-slate-500 pr-1 select-none">%</span>
    </span>
  );
}

// ปุ่ม "บันทึกการแก้ไข" — ยิง API จริงทีเดียวรวมทุกย่อหน้าที่กด "ตกลง" สะสมไว้ในโหมดแก้ไขข้อความ
// (ดูหมายเหตุ pendingEdits ใน App.jsx) ผู้ใช้แจ้งว่าอยากบันทึกครั้งเดียวหลังแก้ไขครบทุกจุดแล้ว
// ไม่ใช่ยิงทีละจุดเหมือนเดิม ปุ่มนี้จึงแยกจากปุ่ม "ดาวน์โหลด" เดิม (ซึ่งแค่ export ไฟล์ปัจจุบันออกไป)
function ApplyEditsButton({ pendingEditCount, onApplyEdits, applyingEdits, onCancelEdits, showApplyAllButton, onApplyAllPages }) {
  const disabled = applyingEdits || pendingEditCount === 0;
  return (
    <div className="flex gap-2">
      <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-md hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" onClick={onApplyEdits} disabled={disabled} title="บันทึกการแก้ไขทั้งหมดลงไฟล์จริง">
        {ICONS.save}
        <span>{applyingEdits ? "กำลังบันทึก…" : "ยืนยัน"}</span>
        {!applyingEdits && pendingEditCount > 0 && (
          <span className="bg-white text-green-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-1">{pendingEditCount}</span>
        )}
      </button>
      
      {showApplyAllButton && pendingEditCount > 0 && (
        <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" onClick={onApplyAllPages} disabled={disabled} title="บันทึกและนำไปใช้กับทุกหน้า">
          {ICONS.save}
          <span>นำไปใช้ทุกหน้า</span>
        </button>
      )}
      {onCancelEdits && (
        <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-xs font-medium rounded-md hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" onClick={onCancelEdits} disabled={applyingEdits} title="ยกเลิกการแก้ไขทั้งหมด">
          <span>ยกเลิก</span>
        </button>
      )}
    </div>
  );
}

export default function Toolbar({
  hasDocument,
  onOpenClick,
  onSaveClick,
  onDownloadClick,
  onPrintClick,
  onCloseClick,
  onDocPropsClick,
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomFitWidth,
  onZoomFitHeight,
  onZoomSet,
  activeTool,
  onSelectTool,
  onInsertImage,
  editMode,
  pendingEditCount = 0,
  onApplyEdits,
  applyingEdits = false,
  onCancelEdits,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  onApplyAllPages,
}) {
  return (
    <div className="flex flex-nowrap overflow-x-auto items-center gap-1.5 px-3 py-2 bg-white border-b border-slate-200 shadow-sm z-40 relative scrollbar-hide" style={{ scrollbarWidth: "none" }}>
      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton icon="open" label="เปิดไฟล์ (Ctrl+O)" onClick={onOpenClick} />
        <ToolbarButton icon="save" label="บันทึกลงเซิร์ฟเวอร์ (Ctrl+S)" onClick={onSaveClick} disabled={!hasDocument} />
        <ToolbarButton icon="download" label="ดาวน์โหลดลงเครื่อง" onClick={onDownloadClick} disabled={!hasDocument} />
        <ToolbarButton icon="print" label="พิมพ์เอกสาร (Ctrl+P)" onClick={onPrintClick} disabled={!hasDocument} />
        <ToolbarButton icon="close" label="ปิดไฟล์" onClick={onCloseClick} disabled={!hasDocument} />
        <ToolbarButton
          icon="properties"
          label="คุณสมบัติเอกสาร"
          onClick={onDocPropsClick}
          disabled={!hasDocument}
        />
      </div>

      <div className="w-px h-6 shrink-0 bg-slate-300 mx-1" />

      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton icon="zoomOut" label="ย่อ" onClick={onZoomOut} disabled={!hasDocument} />
        <ZoomPercentInput zoom={zoom} onCommit={onZoomSet} disabled={!hasDocument} />
        <ToolbarButton icon="zoomIn" label="ขยาย" onClick={onZoomIn} disabled={!hasDocument} />
        <ToolbarButton icon="fitWidth" label="พอดีความกว้าง" onClick={onZoomFitWidth} disabled={!hasDocument} />
        <ToolbarButton icon="fitHeight" label="พอดีหน้า" onClick={onZoomFitHeight} disabled={!hasDocument} />
      </div>

      <div className="w-px h-6 shrink-0 bg-slate-300 mx-1" />

      {/* เลิกทำ/ทำซ้ำ (Undo/Redo) — ผู้ใช้แจ้งให้เพิ่มปุ่มบน toolbar แทรกถัดจากกลุ่มซูม (เดิมมีแค่ใน
          เมนู Edit เท่านั้น — ดู MenuBar.jsx/App.jsx handleUndo/handleRedo ซึ่ง toolbar เรียกใช้ตัวเดียวกัน) */}
      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton icon="undo" label="เลิกทำ (Ctrl+Z)" onClick={onUndo} disabled={!hasDocument || !canUndo} />
        <ToolbarButton icon="redo" label="ทำซ้ำ (Ctrl+Y)" onClick={onRedo} disabled={!hasDocument || !canRedo} />
      </div>

      <div className="w-px h-6 shrink-0 bg-slate-300 mx-1" />

      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton
          icon="select"
          label="เลือก"
          active={activeTool === null}
          onClick={() => onSelectTool(null)}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="hand"
          label="เลื่อนหน้า"
          active={activeTool === "hand"}
          onClick={() => onSelectTool(activeTool === "hand" ? null : "hand")}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="highlight"
          label="เน้นข้อความ"
          active={activeTool === "highlight"}
          onClick={() => onSelectTool("highlight")}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="freetext"
          label="กล่องข้อความ"
          active={activeTool === "freetext"}
          onClick={() => onSelectTool("freetext")}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="rect"
          label="รูปสี่เหลี่ยม"
          active={activeTool === "rect"}
          onClick={() => onSelectTool("rect")}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="note"
          label="บันทึกย่อ"
          active={activeTool === "text_note"}
          onClick={() => onSelectTool("text_note")}
          disabled={!hasDocument}
        />
      </div>

      <div className="w-px h-6 shrink-0 bg-slate-300 mx-1" />

      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton
          icon="insertText"
          label="แทรกข้อความ"
          active={activeTool === "insert_text" || activeTool === "edit_text"}
          onClick={() => onSelectTool(activeTool === "insert_text" || activeTool === "edit_text" ? null : "insert_text")}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="insertImage"
          label="แทรกรูปภาพ"
          active={activeTool === "edit_image"}
          onClick={onInsertImage}
          disabled={!hasDocument}
        />
        <ToolbarButton
          icon="redact"
          label="เซ็นเซอร์"
          active={activeTool === "redact"}
          onClick={() => onSelectTool("redact")}
          disabled={!hasDocument}
        />
      </div>

      {(editMode === "text" || editMode === "image" || editMode === "redact") && (
        <>
          <div className="w-px h-6 shrink-0 bg-slate-300 mx-1" />
          <div className="flex items-center gap-1 shrink-0">
            <ApplyEditsButton
              pendingEditCount={pendingEditCount}
              onApplyEdits={onApplyEdits}
              applyingEdits={applyingEdits}
              onCancelEdits={onCancelEdits}
              showApplyAllButton={editMode === "redact"}
              onApplyAllPages={onApplyAllPages}
            />
          </div>
        </>
      )}
    </div>
  );
}
