import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api.js";
import { applyDraftChange, collectDirtyUpdates, initDraftValues } from "../utils/formFillUtils.js";

function defaultRectForType(type, multiline, pageWidthPt, pageHeightPt) {
  let w = 220;
  let h = 28;
  if (type === "checkbox" || type === "radio") {
    w = 22;
    h = 22;
  } else if (type === "text" && multiline) {
    w = 260;
    h = 72;
  } else if (type === "dropdown") {
    w = 200;
    h = 28;
  }
  const cx = Math.max(20, (pageWidthPt - w) / 2);
  const cy = Math.max(20, (pageHeightPt - h) / 3);
  return { x0: Math.round(cx), y0: Math.round(cy), x1: Math.round(cx + w), y1: Math.round(cy + h) };
}

export function useFormFill({
  session,
  currentPage,
  pageImage,
  active,
  runDocumentChange,
}) {
  const [fields, setFields] = useState([]);
  const [draftValues, setDraftValues] = useState({});
  const [mode, setMode] = useState("fill"); // "fill" | "design"
  const [draftField, setDraftField] = useState(null); // ช่องฟอร์มใหม่ที่กำลังลากวาง/ปรับขนาดบนหน้า
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const pageSize = session?.pageSizes?.[currentPage];
  const pageWidthPt = pageSize?.[0] || 595;
  const pageHeightPt = pageSize?.[1] || 842;

  const reload = useCallback(async () => {
    if (!session?.sessionId) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.getFormFields(session.sessionId);
      const list = res?.fields || [];
      setFields(list);
      setDraftValues(initDraftValues(list));
    } catch (err) {
      setError(err?.message || "โหลดรายการช่องแบบฟอร์มไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [session?.sessionId]);

  useEffect(() => {
    if (!active || !session?.sessionId) {
      if (!active) {
        setFields([]);
        setDraftValues({});
        setDraftField(null);
        setError("");
      }
      return;
    }
    void reload();
  }, [active, session?.sessionId, pageImage, reload]);

  const setFieldValue = useCallback(
    (field, value) => {
      if (field.read_only) return;
      setDraftValues((prev) => applyDraftChange(prev, fields, field, value));
      setError("");
    },
    [fields],
  );

  const pageFields = useMemo(
    () => fields.filter((f) => f.page === currentPage),
    [fields, currentPage],
  );

  const pagesWithFields = useMemo(() => {
    const set = new Set(fields.map((f) => f.page));
    return [...set].sort((a, b) => a - b);
  }, [fields]);

  const dirtyUpdates = useMemo(
    () => collectDirtyUpdates(fields, draftValues),
    [fields, draftValues],
  );

  const save = useCallback(async () => {
    if (!session || saving || dirtyUpdates.length === 0) return;
    setSaving(true);
    setError("");
    try {
      await runDocumentChange(
        (sid) => api.fillFormFields(sid, dirtyUpdates),
        {
          busy: "กำลังบันทึกข้อมูลลงแบบฟอร์ม...",
          success: (res) => `บันทึกแบบฟอร์มเรียบร้อยแล้ว (${res?.updated || dirtyUpdates.length} ช่อง)`,
          failure: "บันทึกแบบฟอร์มไม่สำเร็จ",
          noChange: "ไม่มีข้อมูลที่เปลี่ยนแปลง",
          keepTool: true,
          rethrow: true,
        },
      );
      await reload();
    } catch (err) {
      setError(err?.message || "บันทึกแบบฟอร์มไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  }, [session, saving, dirtyUpdates, runDocumentChange, reload]);

  const resetDraft = useCallback(() => {
    setDraftValues(initDraftValues(fields));
    setError("");
  }, [fields]);

  const startPlaceField = useCallback(
    ({ type, label = "", name = "", multiline = false, options = [] }) => {
      if (type === "dropdown" && (!options || options.length === 0)) {
        setError("กรุณาระบุตัวเลือกอย่างน้อย 1 รายการสำหรับดรอปดาวน์");
        return;
      }
      setError("");
      setDraftField({
        type,
        label: label.trim() || "ช่องกรอกข้อมูล",
        name: name.trim(),
        multiline: !!multiline,
        options,
        rect: defaultRectForType(type, multiline, pageWidthPt, pageHeightPt),
      });
    },
    [pageWidthPt, pageHeightPt],
  );

  const updateDraftRect = useCallback((rect) => {
    setDraftField((prev) => (prev ? { ...prev, rect } : null));
  }, []);

  const cancelDraftField = useCallback(() => {
    setDraftField(null);
    setError("");
  }, []);

  const commitDraftField = useCallback(async () => {
    if (!session || !draftField || saving) return;
    setSaving(true);
    setError("");
    try {
      await runDocumentChange(
        (sid) =>
          api.addFormField(sid, {
            page: currentPage,
            type: draftField.type,
            name: draftField.name,
            label: draftField.label,
            rect: draftField.rect,
            multiline: draftField.multiline,
            options: draftField.options,
          }),
        {
          busy: "กำลังเพิ่มช่องแบบฟอร์ม...",
          success: `เพิ่มช่อง "${draftField.label}" เรียบร้อยแล้ว`,
          failure: "เพิ่มช่องแบบฟอร์มไม่สำเร็จ",
          keepTool: true,
          rethrow: true,
        },
      );
      setDraftField(null);
      await reload();
    } catch (err) {
      setError(err?.message || "เพิ่มช่องแบบฟอร์มไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  }, [session, draftField, saving, currentPage, runDocumentChange, reload]);

  const deleteField = useCallback(
    async (field) => {
      if (!session || saving) return;
      setSaving(true);
      setError("");
      try {
        await runDocumentChange(
          (sid) => api.deleteFormField(sid, field.xref, field.page),
          {
            busy: "กำลังลบช่องแบบฟอร์ม...",
            success: `ลบช่อง "${field.label}" แล้ว`,
            failure: "ลบช่องแบบฟอร์มไม่สำเร็จ",
            keepTool: true,
            rethrow: true,
          },
        );
        await reload();
      } catch (err) {
        setError(err?.message || "ลบช่องแบบฟอร์มไม่สำเร็จ");
      } finally {
        setSaving(false);
      }
    },
    [session, saving, runDocumentChange, reload],
  );

  return {
    fields,
    pageFields,
    pagesWithFields,
    draftValues,
    dirtyCount: dirtyUpdates.length,
    mode,
    setMode,
    draftField,
    startPlaceField,
    updateDraftRect,
    cancelDraftField,
    commitDraftField,
    deleteField,
    loading,
    saving,
    error,
    setFieldValue,
    save,
    resetDraft,
  };
}
