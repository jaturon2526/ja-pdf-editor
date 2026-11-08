// ลิงก์ซอร์สโค้ด (AGPL-3.0 ข้อ 13) — URL มาจาก backend (SOURCE_CODE_URL → GET /config/public source_url)
// เครื่อง on-prem / fork ที่แก้โค้ดชี้ไปที่ซอร์สของตัวเองได้โดยไม่ต้อง build frontend ใหม่
import React, { useEffect, useState } from "react";
import { getPublicConfig } from "../api/config.js";

export const DEFAULT_SOURCE_URL = "https://github.com/jaturon2526/ja-pdf-editor";

export function useSourceUrl() {
  const [url, setUrl] = useState(DEFAULT_SOURCE_URL);
  useEffect(() => {
    let alive = true;
    getPublicConfig().then((cfg) => {
      const u = (cfg?.source_url || "").trim();
      if (alive && /^https?:\/\//.test(u)) setUrl(u);
    });
    return () => { alive = false; };
  }, []);
  return url;
}

export default function SourceCodeLink({ className = "", children }) {
  const url = useSourceUrl();
  return (
    <a href={url} target="_blank" rel="noreferrer" className={className} data-testid="source-code-link">
      {children || "ซอร์สโค้ด (AGPL-3.0)"}
    </a>
  );
}
