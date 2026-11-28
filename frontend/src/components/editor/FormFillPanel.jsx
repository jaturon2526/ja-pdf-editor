import React, { useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

const FIELD_TYPES = [
  { id: "text", labelKey: "editor.panels.formFill.fieldTypeText", multiline: false },
  { id: "textarea", labelKey: "editor.panels.formFill.fieldTypeTextarea", multiline: true },
  { id: "checkbox", labelKey: "editor.panels.formFill.fieldTypeCheckbox", multiline: false },
  { id: "radio", labelKey: "editor.panels.formFill.fieldTypeRadio", multiline: false },
  { id: "dropdown", labelKey: "editor.panels.formFill.fieldTypeDropdown", multiline: false },
];

function renderFieldControl(field, val, onChange) {
  if (field.type === "checkbox" || field.type === "radio") {
    return (
      <label className="inline-flex items-center gap-2 cursor-pointer select-none">
        <input
          type={field.type}
          name={field.type === "radio" ? `panel-radio-${field.name}` : undefined}
          disabled={field.read_only}
          checked={!!val}
          onChange={(e) => onChange(field, e.target.checked)}
          className="w-4 h-4 accent-blue-600"
        />
        <span className="text-xs text-slate-700">{field.label}</span>
      </label>
    );
  }
  if (field.type === "dropdown" || field.type === "listbox") {
    return (
      <label className="block">
        <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
        <select
          disabled={field.read_only}
          value={String(val ?? "")}
          onChange={(e) => onChange(field, e.target.value)}
          className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {field.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (field.multiline) {
    return (
      <label className="block">
        <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
        <textarea
          rows={2}
          disabled={field.read_only}
          maxLength={field.max_len || undefined}
          value={String(val ?? "")}
          onChange={(e) => onChange(field, e.target.value)}
          className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </label>
    );
  }
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
      <input
        type="text"
        disabled={field.read_only}
        maxLength={field.max_len || undefined}
        value={String(val ?? "")}
        onChange={(e) => onChange(field, e.target.value)}
        className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </label>
  );
}

/**
 * แผงกรอกและออกแบบแบบฟอร์ม PDF (v1.45.0 + โหมดออกแบบ v1.47.0)
 * เดสก์ท็อป: แผงขวา · มือถือ: bottom sheet ย่อ/ขยายได้
 */
export default function FormFillPanel({
  hook,
  currentPage,
  onSelectPage,
  onSwitchToInsertText,
  onClose,
}) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);
  const [newType, setNewType] = useState("text");
  const [newLabel, setNewLabel] = useState("");
  const [newGroup, setNewGroup] = useState("");
  const [newOptions, setNewOptions] = useState(() => t("editor.panels.formFill.defaultDropdownOptions"));

  const isDesign = hook.mode === "design";

  let saveBtnLabel = t("editor.panels.formFill.saveFormBtn");
  if (hook.saving) {
    saveBtnLabel = t("editor.panels.formFill.savingBtn");
  } else if (hook.dirtyCount > 0) {
    saveBtnLabel = t("editor.panels.formFill.saveFormWithCountBtn", { count: hook.dirtyCount });
  }

  function handlePlaceNewField() {
    const spec = FIELD_TYPES.find((ft) => ft.id === newType) || FIELD_TYPES[0];
    const apiType = spec.id === "textarea" ? "text" : spec.id;
    const opts = apiType === "dropdown"
      ? newOptions.split(",").map((s) => s.trim()).filter(Boolean)
      : [];
    hook.startPlaceField({
      type: apiType,
      label: newLabel.trim() || t(spec.labelKey),
      name: apiType === "radio" ? (newGroup.trim() || "group1") : "",
      multiline: spec.multiline,
      options: opts,
    });
  }

  return (
    <aside
      aria-label={t("editor.panels.formFill.panelAria")}
      className="w-72 bg-white border-l border-slate-200 flex flex-col shrink-0 z-30 shadow-sm phone:fixed phone:inset-x-0 phone:bottom-0 phone:w-full phone:border-l-0 phone:border-t phone:rounded-t-2xl phone:shadow-2xl phone:z-40 phone:max-h-[55dvh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-slate-800 truncate">{t("editor.panels.formFill.title")}</span>
          <span className="text-[11px] text-slate-500 whitespace-nowrap">
            {t("editor.panels.formFill.fieldCount", { count: hook.fields.length })}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="desk:hidden px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
            aria-label={collapsed ? t("editor.panels.formFill.expandPanelAria") : t("editor.panels.formFill.collapsePanelAria")}
          >
            {collapsed ? t("editor.panels.formFill.expandBtn") : t("editor.panels.formFill.collapseBtn")}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("editor.panels.formFill.closeAria")}
            className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Mode Tabs */}
      {!collapsed && (
        <div className="grid grid-cols-2 p-1.5 gap-1 bg-slate-100 border-b border-slate-200 shrink-0 text-xs">
          <button
            type="button"
            onClick={() => {
              hook.setMode("fill");
              hook.cancelDraftField();
            }}
            className={`py-1.5 rounded-md font-medium transition ${
              !isDesign ? "bg-white text-blue-700 shadow-sm" : "text-slate-600 hover:text-slate-800"
            }`}
          >
            {t("editor.panels.formFill.tabFill")}
          </button>
          <button
            type="button"
            onClick={() => hook.setMode("design")}
            className={`py-1.5 rounded-md font-medium transition ${
              isDesign ? "bg-white text-blue-700 shadow-sm" : "text-slate-600 hover:text-slate-800"
            }`}
          >
            {t("editor.panels.formFill.tabDesign")}
          </button>
        </div>
      )}

      {!collapsed && !isDesign && (
        <div className="p-3.5 space-y-3 overflow-y-auto flex-1 text-xs">
          {hook.loading && (
            <div className="text-slate-500 py-4 text-center">{t("editor.panels.formFill.loadingFields")}</div>
          )}

          {!hook.loading && hook.fields.length === 0 && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2 text-slate-600">
              <p className="font-medium text-slate-700">{t("editor.panels.formFill.noFieldsTitle")}</p>
              <p className="leading-relaxed">
                {t("editor.panels.formFill.noFieldsHintBeforeDesign")}
                <strong>{t("editor.panels.formFill.tabDesign")}</strong>
                {t("editor.panels.formFill.noFieldsHintBetween")}
                <strong>{t("editor.panels.formFill.noFieldsHintInsertText")}</strong>
                {t("editor.panels.formFill.noFieldsHintAfter")}
              </p>
              <div className="flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => hook.setMode("design")}
                  className="w-full px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                >
                  {t("editor.panels.formFill.goToDesignBtn")}
                </button>
                <button
                  type="button"
                  onClick={onSwitchToInsertText}
                  className="w-full px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg"
                >
                  {t("editor.panels.formFill.switchToInsertTextBtn")}
                </button>
              </div>
            </div>
          )}

          {!hook.loading && hook.pagesWithFields.length > 1 && (
            <div>
              <div className="text-[11px] text-slate-500 mb-1">{t("editor.panels.formFill.pagesWithFieldsLabel")}</div>
              <div className="flex flex-wrap gap-1">
                {hook.pagesWithFields.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => onSelectPage(p)}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
                      p === currentPage
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                    }`}
                  >
                    {t("editor.panels.formFill.pageNumber", { page: p + 1 })}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!hook.loading && hook.fields.length > 0 && hook.pageFields.length === 0 && (
            <div className="text-slate-500 text-center py-3">
              {t("editor.panels.formFill.noFieldsOnPage", { page: currentPage + 1 })}
            </div>
          )}

          {!hook.loading && hook.pageFields.length > 0 && (
            <div className="space-y-2.5">
              {hook.pageFields.map((field) => {
                const val = hook.draftValues[field.xref] ?? field.value;
                return (
                  <div
                    key={field.xref}
                    className={`p-2 rounded-lg border ${
                      val !== field.value ? "border-blue-300 bg-blue-50/40" : "border-slate-200 bg-white"
                    }`}
                  >
                    {renderFieldControl(field, val, hook.setFieldValue)}
                  </div>
                );
              })}
            </div>
          )}

          {hook.error && (
            <div role="alert" className="text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
              {hook.error}
            </div>
          )}
        </div>
      )}

      {/* Design Mode Body */}
      {!collapsed && isDesign && (
        <div className="p-3.5 space-y-3 overflow-y-auto flex-1 text-xs">
          <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2.5">
            <div className="font-semibold text-slate-800">{t("editor.panels.formFill.addFieldHeading")}</div>
            <div>
              <label htmlFor="form-new-type" className="block text-[11px] text-slate-600 mb-1">
                {t("editor.panels.formFill.fieldTypeLabel")}
              </label>
              <select
                id="form-new-type"
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg bg-white"
              >
                {FIELD_TYPES.map((ft) => (
                  <option key={ft.id} value={ft.id}>
                    {t(ft.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="form-new-label" className="block text-[11px] text-slate-600 mb-1">
                {t("editor.panels.formFill.fieldLabelLabel")}
              </label>
              <input
                id="form-new-label"
                type="text"
                value={newLabel}
                maxLength={120}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder={t("editor.panels.formFill.fieldLabelPlaceholder")}
                className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg"
              />
            </div>
            {newType === "radio" && (
              <div>
                <label htmlFor="form-new-group" className="block text-[11px] text-slate-600 mb-1">
                  {t("editor.panels.formFill.radioGroupLabel")}
                </label>
                <input
                  id="form-new-group"
                  type="text"
                  value={newGroup}
                  maxLength={60}
                  onChange={(e) => setNewGroup(e.target.value)}
                  placeholder={t("editor.panels.formFill.radioGroupPlaceholder")}
                  className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg"
                />
              </div>
            )}
            {newType === "dropdown" && (
              <div>
                <label htmlFor="form-new-options" className="block text-[11px] text-slate-600 mb-1">
                  {t("editor.panels.formFill.dropdownOptionsLabel")}
                </label>
                <input
                  id="form-new-options"
                  type="text"
                  value={newOptions}
                  onChange={(e) => setNewOptions(e.target.value)}
                  placeholder={t("editor.panels.formFill.dropdownOptionsPlaceholder")}
                  className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg"
                />
              </div>
            )}

            {hook.draftField ? (
              <div className="space-y-1.5 pt-1">
                <p className="text-[11px] text-blue-700">{t("editor.panels.formFill.dragBlueBoxHint")}</p>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={hook.cancelDraftField}
                    className="flex-1 px-2 py-1.5 rounded-lg border border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
                  >
                    {t("editor.panels.formFill.cancelBtn")}
                  </button>
                  <button
                    type="button"
                    disabled={hook.saving}
                    onClick={() => void hook.commitDraftField()}
                    className="flex-1 px-2 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-50"
                  >
                    {hook.saving ? t("editor.panels.formFill.placingBtn") : t("editor.panels.formFill.confirmPlaceBtn")}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                disabled={hook.saving}
                onClick={handlePlaceNewField}
                className="w-full px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-50"
              >
                {t("editor.panels.formFill.placeFieldBtn")}
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onSwitchToInsertText}
            className="w-full px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg"
          >
            {t("editor.panels.formFill.insertTextHeadingBtn")}
          </button>

          {hook.pageFields.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[11px] font-medium text-slate-600">
                {t("editor.panels.formFill.fieldsOnPageHeading", { count: hook.pageFields.length })}
              </div>
              {hook.pageFields.map((f) => (
                <div
                  key={f.xref}
                  className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-slate-700 truncate">{f.label}</div>
                    <div className="text-[10px] text-slate-400">{f.type}</div>
                  </div>
                  <button
                    type="button"
                    disabled={hook.saving}
                    onClick={() => void hook.deleteField(f)}
                    aria-label={t("editor.panels.formFill.deleteFieldAria", { label: f.label })}
                    className="px-2 py-1 text-[11px] text-red-600 hover:bg-red-50 border border-red-200 rounded"
                  >
                    {t("editor.panels.formFill.deleteBtn")}
                  </button>
                </div>
              ))}
            </div>
          )}

          {hook.error && (
            <div role="alert" className="text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
              {hook.error}
            </div>
          )}
        </div>
      )}

      {/* Footer Actions (Fill mode only) */}
      {!isDesign && (
        <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-slate-200 bg-slate-50 shrink-0">
          {hook.dirtyCount > 0 ? (
            <button
              type="button"
              onClick={hook.resetDraft}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
            >
              {t("editor.panels.formFill.resetDraftBtn")}
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
            >
              {t("editor.panels.formFill.closeBtn")}
            </button>
          )}
          <button
            type="button"
            disabled={hook.saving || hook.dirtyCount === 0}
            onClick={() => void hook.save()}
            className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
          >
            {saveBtnLabel}
          </button>
        </div>
      )}
    </aside>
  );
}
