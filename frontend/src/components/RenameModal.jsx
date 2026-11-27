import React, { useState, useEffect } from 'react';
import { useI18n } from '../i18n/I18nContext.jsx';

function RenameModal({ isOpen, onClose, onRename, initialName }) {
  const { t } = useI18n();
  const [name, setName] = useState('');

  useEffect(() => {
    if (isOpen) {
      // Remove .pdf extension for editing if present
      setName(initialName.replace(/\.pdf$/i, ''));
    }
  }, [isOpen, initialName]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (name.trim()) {
      onRename(name.trim() + (name.toLowerCase().endsWith('.pdf') ? '' : '.pdf'));
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-sm w-full overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-slate-50">
          <h2 className="text-lg font-bold text-slate-800">{t("renameModal.title")}</h2>
          <button type="button" onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"></path></svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6">
          <input
            type="text"
            className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            placeholder={t("renameModal.placeholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50">{t("common.cancel")}</button>
            <button type="submit" disabled={!name.trim()} className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">{t("common.saveShort")}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RenameModal;
