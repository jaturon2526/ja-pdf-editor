import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changePassword } from "../api";
import { validatePassword } from "../utils/password";
import PasskeySection from "../components/security/PasskeySection.jsx";
import LineSection from "../components/security/LineSection.jsx";
import LineLoginSection from "../components/security/LineLoginSection.jsx";

export default function SecurityPage() {
  const navigate = useNavigate();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword !== confirmPassword) {
      setError("รหัสผ่านใหม่ไม่ตรงกัน");
      return;
    }
    const pwdError = validatePassword(newPassword);
    if (pwdError) {
      setError(pwdError);
      return;
    }

    setSaving(true);
    try {
      await changePassword(oldPassword, newPassword);
      setSuccess("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err.message || "เปลี่ยนรหัสผ่านไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6">
      <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-5 sm:p-8">
        <div className="flex items-center gap-4 mb-8 border-b pb-4">
          <button onClick={() => navigate("/dashboard")} className="text-gray-500 hover:text-gray-800">
            ← กลับหน้าเอกสาร
          </button>
          <h1 className="text-2xl font-bold">ความปลอดภัย</h1>
        </div>

        <PasskeySection />

        <LineLoginSection />

        <LineSection />

        <h2 className="text-lg font-semibold text-gray-900 mt-10 mb-4 pt-6 border-t border-gray-200">เปลี่ยนรหัสผ่าน</h2>
        <form onSubmit={handleSubmit} className="space-y-5">
          {error && <div className="p-3 bg-red-100 text-red-700 rounded text-sm">{error}</div>}
          {success && <div className="p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">รหัสผ่านเดิม</label>
            <input
              type="password"
              required
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">รหัสผ่านใหม่</label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">ยืนยันรหัสผ่านใหม่</label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="mt-2 text-xs text-rose-500">
              * ข้อแนะนำ: รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร และประกอบด้วยตัวพิมพ์ใหญ่ (A-Z) ตัวพิมพ์เล็ก (a-z) และตัวเลข (0-9) อย่างน้อย 1 ตัว
            </p>
          </div>

          <div className="pt-4 border-t flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
            >
              {saving ? "กำลังบันทึก..." : "อัปเดตรหัสผ่าน"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
