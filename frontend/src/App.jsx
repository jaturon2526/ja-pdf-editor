import React, { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { getMe } from "./api";
import Login from "./pages/Login";
import VerifySuccess from "./pages/VerifySuccess";
import Dashboard from "./pages/Dashboard";
import Editor from "./pages/Editor";
import SigningInbox from "./pages/SigningInbox.jsx";
import SigningCreate from "./pages/SigningCreate.jsx";
import SigningRequest from "./pages/SigningRequest.jsx";

// หน้าสแกน (โหลด OpenCV.js ขนาดใหญ่) แยก chunk — โหลดเมื่อเปิดหน้านั้นเท่านั้น
const ScanPage = lazy(() => import("./pages/ScanPage.jsx"));
const ComparePage = lazy(() => import("./pages/ComparePage.jsx"));
import ProfilePage from "./pages/ProfilePage";
import SecurityPage from "./pages/SecurityPage";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import UpgradePage from "./pages/UpgradePage";
import AdminDashboard from "./pages/AdminDashboard";
import AIConfigPage from "./pages/AIConfigPage";
import LineLoginCallback from "./pages/LineLoginCallback.jsx";

// ตรวจว่า token ยังใช้ได้ (เช่น ถูก login จากอุปกรณ์อื่นเกินจำนวนที่ plan อนุญาต) — ทุกๆ 60 วินาที
// เฉพาะตอนแท็บแสดงอยู่ และตรวจทันทีเมื่อผู้ใช้กลับมาที่แท็บ (เดิมยิงทุก 10 วินาทีแม้แท็บถูกซ่อน)
// request อื่นๆ ทุกตัวผ่าน fetchWithAuth ซึ่ง redirect ไปหน้า login เองทันทีที่เจอ 401 อยู่แล้ว
const SESSION_CHECK_INTERVAL_MS = 60_000;
const PUBLIC_PATHS = ["/", "/login", "/forgot-password", "/reset-password", "/verify-success", "/auth/line/callback"];

function SessionWatcher() {
  const location = useLocation();
  useEffect(() => {
    if (PUBLIC_PATHS.includes(location.pathname)) return undefined;

    const check = () => {
      if (document.visibilityState !== "visible") return;
      // fetchWithAuth จัดการ redirect ไปหน้า login แล้วถ้าได้ 401
      getMe().catch(() => {});
    };
    const interval = setInterval(check, SESSION_CHECK_INTERVAL_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", check);
    };
  }, [location.pathname]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionWatcher />
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route path="/verify-success" element={<VerifySuccess />} />
        <Route path="/auth/line/callback" element={<LineLoginCallback />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/ai-config" element={<AIConfigPage />} />
        <Route path="/upgrade" element={<UpgradePage />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        {/* :id รับพารามิเตอร์รหัสไฟล์ เพื่อให้ Editor รู้ว่าต้องโหลดไฟล์ไหน */}
        <Route path="/editor/:id" element={<Editor />} />
        <Route path="/signing" element={<SigningInbox />} />
        <Route path="/signing/new" element={<SigningCreate />} />
        <Route path="/signing/:id" element={<SigningRequest />} />
        <Route path="/scan" element={<Suspense fallback={null}><ScanPage /></Suspense>} />
        <Route path="/compare/:taskId" element={<Suspense fallback={null}><ComparePage /></Suspense>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
