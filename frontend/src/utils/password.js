export function validatePassword(password, t) {
  const tr = (key, fallback) => (t ? t(key) : fallback);
  if (password.length < 8) return tr("validation.password.minLength", "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร");
  if (!/[A-Z]/.test(password)) return tr("validation.password.uppercase", "รหัสผ่านต้องมีตัวพิมพ์ใหญ่อย่างน้อย 1 ตัว");
  if (!/[a-z]/.test(password)) return tr("validation.password.lowercase", "รหัสผ่านต้องมีตัวพิมพ์เล็กอย่างน้อย 1 ตัว");
  if (!/[0-9]/.test(password)) return tr("validation.password.digit", "รหัสผ่านต้องมีตัวเลขอย่างน้อย 1 ตัว");
  return null; // Valid
}
