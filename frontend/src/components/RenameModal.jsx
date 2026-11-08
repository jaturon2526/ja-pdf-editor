import React, { useState, useEffect } from 'react';

function RenameModal({ isOpen, onClose, onRename, initialName }) {
  const [name, setName] = useState('');

  useEffect(() => {
    if (isOpen) {
      // Remove .pdf extension for editing if present
      setName(initialName.replace(/\\.pdf$/i, ''));
    }
  }, [isOpen, initialName]);

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
          <h2 className="text-lg font-bold text-slate-800">เปลี่ยนชื่อไฟล์</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"></path></svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6">
          <input
            type="text"
            className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            placeholder="ชื่อไฟล์ใหม่"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50">ยกเลิก</button>
            <button type="submit" disabled={!name.trim()} className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">บันทึก</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RenameModal;
