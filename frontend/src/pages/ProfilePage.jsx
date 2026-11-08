import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, updateProfile } from "../api";
import DeleteAccountSection from "../components/profile/DeleteAccountSection.jsx";
import AvatarSection from "../components/profile/AvatarSection.jsx";

export default function ProfilePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    getMe()
      .then((data) => {
        setUser(data);
        setDisplayName(data.display_name || "");
      })
      .catch((err) => setError("โหลดข้อมูลโปรไฟล์ไม่สำเร็จ: " + err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await updateProfile({ display_name: displayName });
      setSuccess("บันทึกข้อมูลเรียบร้อยแล้ว");
    } catch (err) {
      setError("บันทึกข้อมูลไม่สำเร็จ: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="p-8 text-center">กำลังโหลด...</div>;
  if (!user && !error) return <div className="p-8 text-center text-red-500">ไม่พบข้อมูลผู้ใช้</div>;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <div className="flex items-center gap-4 mb-8 border-b pb-4">
          <button onClick={() => navigate("/dashboard")} className="text-gray-500 hover:text-gray-800">
            ← กลับหน้าเอกสาร
          </button>
          <h1 className="text-2xl font-bold">โปรไฟล์ส่วนตัว</h1>
        </div>

        {user && <AvatarSection user={user} onChange={() => getMe().then(setUser)} />}

        <form onSubmit={handleSave} className="space-y-6">
          {error && <div className="p-3 bg-red-100 text-red-700 rounded text-sm">{error}</div>}
          {success && <div className="p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">อีเมล</label>
            <input
              type="text"
              value={user?.email || ""}
              disabled
              className="w-full border border-gray-300 rounded px-3 py-2 bg-gray-100 text-gray-500"
            />
            <p className="text-xs text-gray-500 mt-1">อีเมลใช้สำหรับเข้าสู่ระบบ ไม่สามารถเปลี่ยนได้</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">ชื่อที่แสดง</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="กรอกชื่อของคุณ"
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">แพ็กเกจปัจจุบัน</label>
            <div className="inline-block bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-semibold capitalize">
              {user?.plan_type || "free"} Plan
            </div>
          </div>

          <div className="pt-4 border-t flex justify-end gap-3">
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
            >
              {saving ? "กำลังบันทึก..." : "บันทึกข้อมูล"}
            </button>
          </div>
        </form>

        {user?.email && <DeleteAccountSection email={user.email} />}
      </div>
    </div>
  );
}
