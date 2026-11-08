// คุณสมบัติเอกสารของไฟล์ใน "เอกสารของฉัน" (เมนู ☰) — ไม่ต้องเปิดไฟล์ใน Editor
// ไฟล์มีรหัสผ่าน: ถามรหัสก่อน แล้วค่อยแสดง
import { useEffect, useState } from "react";
import { getStoredFileProperties } from "../../api.js";
import DocumentPropertiesModal from "../DocumentPropertiesModal.jsx";
import PasswordModal from "../PasswordModal.jsx";

export default function StoredFileProperties({ file, onClose }) {
  const [properties, setProperties] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [needPassword, setNeedPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  async function load(password = null) {
    setLoading(true);
    setError(null);
    try {
      setProperties(await getStoredFileProperties(file.id, password));
      setNeedPassword(false);
    } catch (e) {
      if (e.status === 423) {
        setPasswordError(password ? e.message : "");
        setNeedPassword(true);
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // โหลดครั้งเดียวต่อไฟล์
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

  if (needPassword) {
    return (
      <PasswordModal
        fileName={file.filename}
        error={passwordError}
        submitting={loading}
        onCancel={onClose}
        onSubmit={(pw) => load(pw)}
      />
    );
  }
  return (
    <DocumentPropertiesModal
      fileName={file.filename}
      properties={properties}
      loading={loading}
      errorMessage={error}
      onClose={onClose}
    />
  );
}
