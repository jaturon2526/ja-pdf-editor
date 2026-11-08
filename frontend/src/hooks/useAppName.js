// ชื่อแอปจาก backend (APP_NAME ใน .env → GET /config/public app_name) — เว็บสาธารณะ "JA PDF Editor",
// เครื่องติดตั้งในองค์กรตั้งชื่อเองได้ · ตั้งชื่อแท็บเบราว์เซอร์ (document.title) ตามด้วย
import { useEffect, useState } from "react";
import { getPublicConfig } from "../api/config.js";

export const DEFAULT_APP_NAME = "JA PDF Editor";
let known = null;

export function useAppName() {
  const [name, setName] = useState(known || DEFAULT_APP_NAME);
  useEffect(() => {
    let alive = true;
    getPublicConfig().then((cfg) => {
      const n = (cfg?.app_name || "").trim() || DEFAULT_APP_NAME;
      known = n;
      if (alive) setName(n);
      if (typeof document !== "undefined") document.title = n;
    });
    return () => { alive = false; };
  }, []);
  return name;
}
