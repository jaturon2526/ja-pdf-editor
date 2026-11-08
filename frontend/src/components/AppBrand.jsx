// โลโก้ + ชื่อแอป (ใช้ร่วมกันใน Dashboard, หน้าเข้าสู่ระบบ และแถบบนของ Editor บนมือถือ)
// คำสุดท้ายของชื่อเป็นสีเน้น เช่น "JA PDF Editor" → "JA PDF" + "Editor" สีฟ้า (ชื่อคำเดียว = ไม่เน้น)
import React from "react";
import { useAppName } from "../hooks/useAppName.js";

export function AppLogo({ className = "w-8 h-8 text-blue-600" }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M9 2a2 2 0 00-2 2v8a2 2 0 002 2h6a2 2 0 002-2V6.414A2 2 0 0016.414 5L14 2.586A2 2 0 0012.586 2H9z" />
      <path d="M3 8a2 2 0 012-2v10h8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
    </svg>
  );
}

/**
 * variant: "light" (พื้นขาว — Dashboard/Login) | "dark" (แถบเมนูสีเข้มของ Editor)
 * size: "md" | "lg" (หน้าเข้าสู่ระบบ) | "sm" (แถบบน Editor มือถือ)
 * hideNameBelow: ซ่อนชื่อเหลือแค่โลโก้เมื่อจอแคบกว่านี้ (class ของ Tailwind เช่น "max-[359px]:hidden")
 */
export default function AppBrand({ variant = "light", size = "md", nameClassName = "", className = "" }) {
  const name = useAppName();
  const words = name.split(/\s+/);
  const last = words.length > 1 ? words.pop() : null;
  const head = words.join(" ");
  const dark = variant === "dark";
  const logo = { sm: "w-5 h-5", md: "w-8 h-8", lg: "w-10 h-10" }[size];
  const text = { sm: "text-sm", md: "text-lg sm:text-xl", lg: "text-2xl" }[size];
  return (
    <span className={`inline-flex items-center gap-2 min-w-0 ${className}`} data-testid="app-brand">
      <AppLogo className={`${logo} shrink-0 ${dark ? "text-sky-400" : "text-blue-600"}`} />
      <span className={`font-bold tracking-tight whitespace-nowrap truncate ${text} ${dark ? "text-white" : "text-gray-900"} ${nameClassName}`}>
        {head}
        {last && <> <span className={dark ? "text-sky-400" : "text-blue-600"}>{last}</span></>}
      </span>
    </span>
  );
}
