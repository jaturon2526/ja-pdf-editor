import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api.js";
import { applyDraftChange, collectDirtyUpdates, initDraftValues } from "../utils/formFillUtils.js";

export function useFormFill({
  session,
  currentPage,
  pageImage,
  active,
  runDocumentChange,
}) {
  const [fields, setFields] = useState([]);
  const [draftValues, setDraftValues] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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

  // โหลดรายการฟิลด์เมื่อเปิดโหมดกรอกแบบฟอร์ม หรือเมื่อเอกสารเปลี่ยนหลัง Undo/Redo/บันทึก
  useEffect(() => {
    if (!active || !session?.sessionId) {
      if (!active) {
        setFields([]);
        setDraftValues({});
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

  return {
    fields,
    pageFields,
    pagesWithFields,
    draftValues,
    dirtyCount: dirtyUpdates.length,
    loading,
    saving,
    error,
    setFieldValue,
    save,
    resetDraft,
  };
}
