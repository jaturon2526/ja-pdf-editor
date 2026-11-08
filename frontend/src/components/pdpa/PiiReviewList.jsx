// รายการข้อมูลส่วนบุคคลที่ตรวจพบ (PDPA) — ใช้ร่วมกันทั้งแผงใน Editor และเครื่องมือด่วนบน Dashboard
// จัดกลุ่มตามประเภท · ประเภทความมั่นใจสูงถูกติ๊กไว้ก่อน ประเภทความมั่นใจกลางให้ผู้ใช้ตรวจแล้วเลือกเอง
import { useEffect, useRef } from "react";
import { saveBlob } from "../../api/client.js";

export const PII_TYPE_ORDER = ["national_id", "credit_card", "bank_account", "phone", "email", "person_name", "address", "person_name_guess"];

export function defaultPiiSelection(findings) {
  return new Set(findings.filter((f) => f.confidence === "high").map((f) => f.id));
}

export function groupFindings(findings) {
  const groups = new Map();
  for (const f of findings) {
    if (!groups.has(f.type)) groups.set(f.type, { type: f.type, label: f.label, confidence: f.confidence, items: [] });
    groups.get(f.type).items.push(f);
  }
  return PII_TYPE_ORDER.filter((t) => groups.has(t)).map((t) => groups.get(t));
}

// รายงานแบบ CSV (UTF-8 BOM เปิดใน Excel ภาษาไทยได้) — ค่าในรายงานถูกปิดบางส่วนจากฝั่ง server แล้ว
export function downloadPiiReport(report, sourceName) {
  const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const rows = [["ลำดับ", "ประเภท", "หน้า", "ค่าที่ปกปิด (บางส่วน)"]];
  report.forEach((r, i) => rows.push([i + 1, r.label, r.page, r.masked]));
  const now = new Date();
  const header = [
    [`รายงานการปกปิดข้อมูลส่วนบุคคล — ${sourceName}`],
    [`วันที่ ${now.toLocaleString("th-TH")}`],
    [`จำนวน ${report.length} รายการ`],
    [],
  ];
  const csv = "﻿" + [...header, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
  saveBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${sourceName.replace(/\.pdf$/i, "")} - รายงาน PDPA.csv`);
}

function GroupCheckbox({ checked, indeterminate, onChange, label }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return <input ref={ref} type="checkbox" className="h-4 w-4 shrink-0" aria-label={label} checked={checked} onChange={onChange} />;
}

export default function PiiReviewList({ scan, selected, onChange, cleanMetadata, onCleanMetadata, activeId = null, onActivate = null, maxHeightClass = "max-h-72" }) {
  const groups = groupFindings(scan.findings);

  function toggle(id) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }

  function toggleGroup(group) {
    const next = new Set(selected);
    const all = group.items.every((f) => next.has(f.id));
    group.items.forEach((f) => (all ? next.delete(f.id) : next.add(f.id)));
    onChange(next);
  }

  const noText = scan.pages_without_text || [];

  return (
    <div className="space-y-3 text-sm">
      {scan.findings.length === 0 ? (
        <p className="p-3 rounded-lg bg-green-50 text-green-800 border border-green-200">ไม่พบข้อมูลส่วนบุคคลในชั้นข้อความของเอกสารนี้</p>
      ) : (
        <div className={`${maxHeightClass} overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-100`} data-testid="pii-list">
          {groups.map((g) => {
            const n = g.items.filter((f) => selected.has(f.id)).length;
            return (
              <div key={g.type}>
                <label className="sticky top-0 z-[1] flex items-center gap-2 px-3 py-2 bg-gray-50 font-semibold text-gray-800 cursor-pointer">
                  <GroupCheckbox
                    label={`เลือก${g.label}ทั้งหมด`}
                    checked={n === g.items.length}
                    indeterminate={n > 0 && n < g.items.length}
                    onChange={() => toggleGroup(g)}
                  />
                  <span className="flex-1 min-w-0 truncate">{g.label}</span>
                  <span className="text-xs font-normal text-gray-500">{n}/{g.items.length}</span>
                  {g.confidence === "high" ? (
                    <span className="text-[11px] font-normal px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">แม่นยำสูง</span>
                  ) : (
                    <span className="text-[11px] font-normal px-1.5 py-0.5 rounded bg-amber-100 text-amber-800" title="อาจตรวจพบผิด — โปรดตรวจก่อนเลือก">ตรวจก่อนเลือก</span>
                  )}
                </label>
                <ul>
                  {g.items.map((f) => (
                    <li
                      key={f.id}
                      className={`flex items-start gap-2 px-3 py-1.5 ${activeId === f.id ? "bg-orange-50" : "hover:bg-gray-50"}`}
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4 mt-0.5 shrink-0"
                        aria-label={`เลือก ${f.text}`}
                        checked={selected.has(f.id)}
                        onChange={() => toggle(f.id)}
                      />
                      <button
                        type="button"
                        className={`flex-1 min-w-0 text-left break-words text-gray-800 ${onActivate ? "hover:underline" : "cursor-default"}`}
                        onClick={() => (onActivate ? onActivate(f) : toggle(f.id))}
                        title={onActivate ? "ไปยังตำแหน่งในเอกสาร" : undefined}
                      >
                        {f.text}
                      </button>
                      <span className="shrink-0 text-xs text-gray-500 mt-0.5">หน้า {f.page + 1}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      {noText.length > 0 && (
        <p className="p-2.5 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-xs">
          {noText.length === scan.page_count ? "ทุกหน้า" : `หน้า ${noText.slice(0, 10).map((p) => p + 1).join(", ")}${noText.length > 10 ? " …" : ""}`}
          {" "}ไม่มีชั้นข้อความ (อาจเป็นภาพสแกน) จึงตรวจอัตโนมัติไม่ได้ — ใช้เครื่องมือ "เซ็นเซอร์" ลากปิดเองได้
        </p>
      )}

      <label className="flex items-center gap-2 text-gray-700 cursor-pointer">
        <input type="checkbox" className="h-4 w-4" checked={cleanMetadata} onChange={(e) => onCleanMetadata(e.target.checked)} />
        ล้างข้อมูลเมตาของไฟล์ด้วย (ชื่อผู้สร้าง, ชื่อเรื่อง ฯลฯ)
      </label>
    </div>
  );
}
