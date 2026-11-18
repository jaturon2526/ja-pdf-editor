import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./tailwind.css";
import "./styles.css";

import { migrateLegacyToken } from "./api/client.js";

// ปุ่ม Google (GoogleOAuthProvider) อยู่ในหน้า Login เท่านั้น และแสดงเมื่อ backend เปิดใช้ (GET /config/public)
// ย้าย token จาก localStorage (หน้าเว็บรุ่นเก่า) เป็น cookie ก่อน render — หน้าแรกจะได้เรียก API ด้วย cookie ได้เลย
void migrateLegacyToken().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
