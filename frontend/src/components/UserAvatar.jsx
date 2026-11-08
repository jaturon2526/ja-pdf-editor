// รูปโปรไฟล์วงกลม: รูปที่ตั้งเอง (avatar_url) → รูปจาก Google/LINE (profile_picture) → ตัวอักษรแรกของชื่อ
import React, { useState } from "react";

export default function UserAvatar({ user, size = 40, className = "" }) {
  const [broken, setBroken] = useState(false);
  const src = !broken && (user?.avatar_url || user?.profile_picture);
  const initial = (user?.display_name || user?.email || "U").charAt(0).toUpperCase();
  return (
    <div
      className={`rounded-full bg-blue-600 flex items-center justify-center text-white font-bold shadow-md overflow-hidden shrink-0 ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      data-testid="user-avatar"
    >
      {src ? (
        <img src={src} alt="รูปโปรไฟล์" className="w-full h-full object-cover" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
      ) : initial}
    </div>
  );
}
