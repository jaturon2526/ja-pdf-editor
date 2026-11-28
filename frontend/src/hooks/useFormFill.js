import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
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
  const { t } = useI18n();
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
      setError(err?.message || t("editor.hooks.formFill.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [session?.sessionId, t]);

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
          busy: t("editor.hooks.formFill.saving"),
          success: (res) => t("editor.hooks.formFill.saveSuccess", { count: res?.updated || dirtyUpdates.length }),
          failure: t("editor.hooks.formFill.saveFailed"),
          noChange: t("editor.hooks.formFill.noChange"),
          keepTool: true,
          rethrow: true,
        },
      );
      await reload();
    } catch (err) {
      setError(err?.message || t("editor.hooks.formFill.saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [session, saving, dirtyUpdates, runDocumentChange, reload, t]);

  const resetDraft = useCallback(() => {
    setDraftValues(initDraftValues(fields));
    setError("");
  }, [fields]);

  const startPlaceField = useCallback(
    ({ type, label = "", name = "", multiline = false, options = [] }) => {
      if (type === "dropdown" && (!options || options.length === 0)) {
        setError(t("editor.hooks.formFill.dropdownOptionsRequired"));
        return;
      }
      setError("");
      setDraftField({
        type,
        label: label.trim() || t("editor.hooks.formFill.defaultFieldLabel"),
        name: name.trim(),
        multiline: !!multiline,
        options,
        rect: defaultRectForType(type, multiline, pageWidthPt, pageHeightPt),
      });
    },
    [pageWidthPt, pageHeightPt, t],
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
          busy: t("editor.hooks.formFill.addingField"),
          success: t("editor.hooks.formFill.addFieldSuccess", { label: draftField.label }),
          failure: t("editor.hooks.formFill.addFieldFailed"),
          keepTool: true,
          rethrow: true,
        },
      );
      setDraftField(null);
      await reload();
    } catch (err) {
      setError(err?.message || t("editor.hooks.formFill.addFieldFailed"));
    } finally {
      setSaving(false);
    }
  }, [session, draftField, saving, currentPage, runDocumentChange, reload, t]);

  const deleteField = useCallback(
    async (field) => {
      if (!session || saving) return;
      setSaving(true);
      setError("");
      try {
        await runDocumentChange(
          (sid) => api.deleteFormField(sid, field.xref, field.page),
          {
            busy: t("editor.hooks.formFill.deletingField"),
            success: t("editor.hooks.formFill.deleteFieldSuccess", { label: field.label }),
            failure: t("editor.hooks.formFill.deleteFieldFailed"),
            keepTool: true,
            rethrow: true,
          },
        );
        await reload();
      } catch (err) {
        setError(err?.message || t("editor.hooks.formFill.deleteFieldFailed"));
      } finally {
        setSaving(false);
      }
    },
    [session, saving, runDocumentChange, reload, t],
  );

  const moveField = useCallback(
    async (field, rect) => {
      if (!session || saving) return;
      // อัปเดตตำแหน่งใน state ทันทีไม่ให้กระพริบกลับตำแหน่งเดิมระหว่างรอเซิร์ฟเวอร์
      setFields((prev) => prev.map((f) => (f.xref === field.xref && f.page === field.page ? { ...f, rect } : f)));
      setSaving(true);
      setError("");
      try {
        await runDocumentChange(
          (sid) => api.updateFormField(sid, field.xref, { page: field.page, rect }),
          {
            busy: t("editor.hooks.formFill.movingField"),
            success: t("editor.hooks.formFill.moveFieldSuccess", { label: field.label }),
            failure: t("editor.hooks.formFill.moveFieldFailed"),
            keepTool: true,
            rethrow: true,
          },
        );
        await reload();
      } catch (err) {
        setError(err?.message || t("editor.hooks.formFill.moveFieldFailed"));
        await reload();
      } finally {
        setSaving(false);
      }
    },
    [session, saving, runDocumentChange, reload, t],
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
    moveField,
    deleteField,
    loading,
    saving,
    error,
    setFieldValue,
    save,
    resetDraft,
  };
}
