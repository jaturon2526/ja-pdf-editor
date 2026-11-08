// โหลดรูปจาก endpoint ที่ต้องมี Authorization header แล้วคืน object URL (ห้ามใส่ URL ตรงๆ ใน <img src>)
import { useEffect, useState } from "react";
import { fetchWithAuth } from "../../api/client.js";

export function useAuthedImage(url) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!url) return undefined;
    let objectUrl = null;
    let cancelled = false;
    fetchWithAuth(url)
      .then((res) => (res.ok ? res.blob() : null))
      .then((blob) => {
        if (!blob || cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  return src;
}
