import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./tailwind.css";
import "./styles.css";

// ปุ่ม Google (GoogleOAuthProvider) อยู่ในหน้า Login เท่านั้น และแสดงเมื่อ backend เปิดใช้ (GET /config/public)
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
