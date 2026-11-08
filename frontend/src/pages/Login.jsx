import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google';
import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import SourceCodeLink from '../components/SourceCodeLink.jsx';
import { emailDomainAllowed, getLineLoginConfig, getPublicConfig, startLineLogin } from '../api';
import AppBrand from "../components/AppBrand.jsx";
import LineIcon from '../components/LineIcon.jsx';
import { authLogin, authRegister, authGoogleLogin, resendVerification, browserSupportsWebAuthn, browserSupportsWebAuthnAutofill, loginWithPasskey, passkeyErrorMessage, preparePasskeyLogin } from '../api';
import { WebAuthnAbortService } from '@simplewebauthn/browser';
import { validatePassword } from "../utils/password";

// ความกว้างปุ่ม Google และ LINE (px) — Google รับได้ไม่เกิน 400
const GOOGLE_BUTTON_WIDTH = 320;
// ค่าสำรองเมื่อโหลด /config/public ไม่ได้ (backend รุ่นเก่า) — ปกติใช้ค่าจาก backend
const FALLBACK_GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || null;

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchParams] = useSearchParams();
  const [showResend, setShowResend] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [passkeySupported] = useState(() => browserSupportsWebAuthn());
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [lineLogin, setLineLogin] = useState(false);
  const [lineBusy, setLineBusy] = useState(false);
  // ค่าจาก backend: Google client ID (null = ปิด), สมัครเองได้ไหม, โดเมนอีเมลที่สมัครได้ (onprem)
  const [googleClientId, setGoogleClientId] = useState(null);
  const [selfRegistration, setSelfRegistration] = useState(true);
  const [allowedDomains, setAllowedDomains] = useState([]);
  const [invited, setInvited] = useState(false);
  const preparedLogin = React.useRef(null); // options สำหรับปุ่ม Passkey (ขอไว้ก่อน — Safari ห้ามมี fetch คั่นระหว่างกดกับ WebAuthn)

  const preparePasskeyButton = React.useCallback(() => {
    preparedLogin.current = null;
    preparePasskeyLogin().then((p) => { preparedLogin.current = p; }).catch(() => {});
  }, []);

  function finishPasskeyLogin(data) {
    localStorage.setItem("token", data.access_token);
    window.location.href = "/dashboard";
  }

  useEffect(() => {
    getPublicConfig().then((cfg) => {
      if (cfg) {
        setGoogleClientId(cfg.google_client_id || null);
        setLineLogin(!!cfg.line_login);
        setSelfRegistration(cfg.self_registration !== false);
        setAllowedDomains(Array.isArray(cfg.allowed_email_domains) ? cfg.allowed_email_domains : []);
      } else {
        setGoogleClientId(FALLBACK_GOOGLE_CLIENT_ID);
        getLineLoginConfig().then((c) => setLineLogin(!!c.enabled)).catch(() => setLineLogin(false));
      }
    });
    const reset = () => setLineBusy(false); // กดย้อนกลับจากหน้า LINE (bfcache) → ปุ่มกดได้อีก
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);

  async function handleLineLogin() {
    setErrorMsg("");
    setLineBusy(true);
    try {
      await startLineLogin(); // ไปหน้าอนุญาตของ LINE
    } catch (err) {
      setErrorMsg("เข้าสู่ระบบด้วย LINE ไม่สำเร็จ: " + err.message);
      setLineBusy(false);
    }
  }

  useEffect(() => {
    if (!isRegister && passkeySupported) preparePasskeyButton();
  }, [isRegister, passkeySupported, preparePasskeyButton]);

  // ช่องอีเมลแนะนำ passkey อัตโนมัติ (autofill) — เริ่มเมื่อผู้ใช้แตะช่องอีเมลเท่านั้น
  // Safari: ถ้ามีคำขอ autofill ค้างอยู่ แล้วยกเลิกพร้อมเปิดคำขอจากปุ่มในจังหวะเดียวกัน หน้าต่างสแกนนิ้วจะไม่ขึ้น
  // (Chrome ไม่เป็น) จึงไม่เปิด autofill ตั้งแต่โหลดหน้า และยกเลิกตั้งแต่ตอนกดลง (pointerdown) ก่อนถึง click
  const autofillActive = React.useRef(false);
  const autofillCancelled = React.useRef(false);
  const buttonActive = React.useRef(false);   // คำขอจากปุ่ม Passkey กำลังรอผู้ใช้ยืนยัน
  const buttonTimedOut = React.useRef(false);

  const startPasskeyAutofill = React.useCallback(async () => {
    if (isRegister || !passkeySupported || autofillActive.current) return;
    try {
      if (!(await browserSupportsWebAuthnAutofill())) return;
      autofillActive.current = true;
      autofillCancelled.current = false;
      // ขอ options ก่อน แล้วค่อยเริ่มคำขอ autofill — ถ้าระหว่างรอ (ไม่กี่ร้อยมิลลิวินาที) ผู้ใช้กดปุ่ม Passkey ไปแล้ว
      // ห้ามเริ่ม: การเริ่มคำขอใหม่จะยกเลิกคำขอของปุ่มที่กำลังเปิดอยู่ และใน Safari คำขอของปุ่มจะค้างตลอดไป
      // (ปุ่มขึ้น "รอยืนยันที่อุปกรณ์..." โดยไม่มีหน้าต่างสแกนนิ้ว) — เดิมยกเลิกได้เฉพาะตอนคำขอเริ่มแล้ว
      const prepared = await preparePasskeyLogin();
      if (autofillCancelled.current || buttonActive.current) return;
      const data = await loginWithPasskey({ autofill: true, prepared });
      finishPasskeyLogin(data);
    } catch (err) {
      // ถูกยกเลิกเพราะกดปุ่ม Passkey / เปลี่ยนหน้า → ไม่ต้องแสดง
      const msg = passkeyErrorMessage(err);
      if (!autofillCancelled.current && msg && err?.name !== "NotAllowedError") setErrorMsg(msg);
    } finally {
      autofillActive.current = false;
    }
  }, [isRegister, passkeySupported]);

  useEffect(() => () => {
    if (autofillActive.current) WebAuthnAbortService.cancelCeremony();
  }, [isRegister]);

  function cancelPasskeyAutofill() {
    if (!autofillActive.current) return;
    autofillCancelled.current = true;
    WebAuthnAbortService.cancelCeremony();
  }

  async function handlePasskeyLogin() {
    cancelPasskeyAutofill(); // กรณีกดด้วยคีย์บอร์ด (ไม่มี pointerdown)
    setErrorMsg("");
    setSuccessMsg("");
    setPasskeyBusy(true);
    buttonActive.current = true;
    buttonTimedOut.current = false;
    // กันปุ่มค้าง: เบราว์เซอร์บางตัว (Safari) ไม่แสดงหน้าต่างและไม่ตอบกลับเลยในบางจังหวะ — เกินเวลาที่ server กำหนด
    // (options.timeout) แล้วยกเลิกเอง ให้กดใหม่ได้ · ผู้ใช้กด "ยกเลิก" เองได้ตลอด (ดู cancelPasskeyButton)
    const prepared = preparedLogin.current;
    preparedLogin.current = null;
    const limit = (prepared?.options?.timeout || 60000) + 5000;
    const watchdog = setTimeout(() => {
      buttonTimedOut.current = true;
      WebAuthnAbortService.cancelCeremony();
    }, limit);
    try {
      finishPasskeyLogin(await loginWithPasskey({ prepared }));
    } catch (err) {
      const msg = buttonTimedOut.current
        ? "ไม่ได้รับการยืนยันจากอุปกรณ์ — กด \"เข้าสู่ระบบด้วย Passkey\" อีกครั้ง"
        : passkeyErrorMessage(err);
      if (msg) setErrorMsg(msg);
      preparePasskeyButton();
    } finally {
      clearTimeout(watchdog);
      buttonActive.current = false;
      setPasskeyBusy(false);
    }
  }

  function cancelPasskeyButton() {
    if (buttonActive.current) WebAuthnAbortService.cancelCeremony();
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("expired")) {
      setErrorMsg("เซสชันของคุณหมดอายุ หรือมีการเข้าสู่ระบบซ้อนจากอุปกรณ์อื่น กรุณาเข้าสู่ระบบใหม่");
      // clear param
      window.history.replaceState({}, document.title, "/login");
    }

    if (searchParams.get("verified") === "true") {
      setSuccessMsg("ยืนยันอีเมลสำเร็จ กรุณาเข้าสู่ระบบ");
    }
    if (searchParams.get("deleted") === "1") {
      setSuccessMsg("ลบบัญชีพร้อมไฟล์และข้อมูลทั้งหมดเรียบร้อยแล้ว ขอบคุณที่ใช้งาน");
    }

    // ลิงก์จากอีเมลเชิญลงนาม: /login?register=1&email=... → เปิดหน้าสมัครพร้อมอีเมลที่ถูกเชิญ
    const invitedEmail = searchParams.get("email");
    if (invitedEmail) setEmail(invitedEmail);
    if (searchParams.get("register") === "1") {
      setIsRegister(true);
      setInvited(true);
      setSuccessMsg("คุณได้รับเชิญให้ลงนามเอกสาร — สมัครด้วยอีเมลนี้แล้วยืนยันอีเมล เอกสารจะอยู่ในเมนู \"การลงนาม\"");
    }
  }, [searchParams]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("expired")) {
      setErrorMsg("เซสชันของคุณหมดอายุ หรือมีการเข้าสู่ระบบซ้อนจากอุปกรณ์อื่น กรุณาเข้าสู่ระบบใหม่");
      // clear param
      window.history.replaceState({}, document.title, "/login");
    }

    let timer;
    if (resendCooldown > 0) {
      timer = setInterval(() => setResendCooldown(c => c - 1), 1000);
    }
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    try {
      setResendCooldown(60);
      await resendVerification(email);
      setSuccessMsg("ส่งลิงก์ยืนยันตัวตนไปที่อีเมลของคุณแล้ว (กรุณาเช็กในกล่องจดหมายขยะด้วยครับ)");
      setErrorMsg("");
    } catch (err) {
      setErrorMsg(err.message || "ไม่สามารถส่งอีเมลได้");
      setResendCooldown(0);
    }
  };

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    setSuccessMsg("");
    setLoading(true);
    try {
      if (isRegister) {
        if (password !== confirmPassword) {
          setErrorMsg("รหัสผ่านไม่ตรงกัน");
          setLoading(false);
          return;
        }
        const pwdError = validatePassword(password);
        if (pwdError) {
          setErrorMsg(pwdError);
          setLoading(false);
          return;
        }
        // ผู้ได้รับเชิญลงนามสมัครได้แม้อยู่นอกโดเมน — backend ตรวจซ้ำเสมอ
        if (!invited && !emailDomainAllowed(email, allowedDomains)) {
          setErrorMsg(`สมัครได้เฉพาะอีเมลขององค์กร (${allowedDomains.map((d) => "@" + d).join(", ")})`);
          setLoading(false);
          return;
        }
        await authRegister(email, password);
        setSuccessMsg(
          `สมัครสมาชิกสำเร็จ! เราส่งลิงก์ยืนยันไปที่ ${email} แล้ว — กรุณากดลิงก์ในอีเมลก่อนเข้าสู่ระบบ (ถ้าไม่เห็น ลองดูในโฟลเดอร์ Junk/สแปม)`,
        );
        setIsRegister(false);
      } else {
        const data = await authLogin(email, password);
        localStorage.setItem("token", data.access_token);
        navigate("/dashboard");
      }
    } catch (err) {
      setErrorMsg(err.message || "เกิดข้อผิดพลาด");
      if (err.message && err.message.includes("กรุณายืนยันอีเมล")) {
        setShowResend(true);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center"><AppBrand size="lg" /></div>
        <p className="mt-2 text-center text-xs text-gray-500">แก้ไข แปลง และส่งเอกสาร PDF ให้ผู้อื่นลงนามออนไลน์</p>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
          {isRegister ? "สร้างบัญชีใหม่" : "เข้าสู่ระบบ"}
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          และเริ่มจัดการเอกสาร PDF ของคุณแบบมืออาชีพ
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow-xl sm:rounded-xl sm:px-10 border border-gray-100">
          <form className="space-y-6" onSubmit={handleSubmit}>
            {errorMsg && (
              <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
                <div className="flex flex-col">
                  <div className="ml-3">
                    <p className="text-sm text-red-700">{errorMsg}</p>
                  </div>
                  {showResend && !isRegister && (
                    <div className="ml-3 mt-3">
                      <button 
                        type="button" 
                        onClick={handleResend}
                        disabled={resendCooldown > 0}
                        className={`text-sm font-medium underline ${resendCooldown > 0 ? 'text-gray-500 cursor-not-allowed' : 'text-blue-600 hover:text-blue-800'}`}
                      >
                        {resendCooldown > 0 ? `กรุณารอ ${resendCooldown} วินาทีเพื่อส่งซ้ำ` : 'ส่งอีเมลยืนยันตัวตนอีกครั้ง'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
            {successMsg && (
              <div className="bg-green-50 border-l-4 border-green-400 p-4 mb-4">
                <div className="flex">
                  <div className="ml-3">
                    <p className="text-sm text-green-700">{successMsg}</p>
                  </div>
                </div>
              </div>
            )}
            
            <div>
              <label className="block text-sm font-medium text-gray-700">อีเมล</label>
              <div className="mt-1">
                <input 
                  type="email" 
                  autoComplete={isRegister ? "email" : "username webauthn"}
                  // เริ่มเมื่อผู้ใช้แตะ/พิมพ์ในช่องเอง — ไม่ใช้ onFocus: Safari บน Mac โฟกัสช่องอีเมลให้เองตอนเปิดหน้า
                  // คำขอ autofill จึงค้างอยู่ก่อนผู้ใช้กดปุ่ม Passkey แล้วปุ่มค้าง "รอยืนยันที่อุปกรณ์..."
                  onPointerDown={startPasskeyAutofill}
                  onKeyDown={startPasskeyAutofill}
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required 
                  className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder={isRegister && allowedDomains.length ? `you@${allowedDomains[0]}` : "you@example.com"}
                />
              </div>
              {isRegister && allowedDomains.length > 0 && !invited && (
                <p className="mt-1 text-xs text-gray-500" data-testid="register-domain-hint">
                  ใช้อีเมลขององค์กร: {allowedDomains.map((d) => "@" + d).join(", ")}
                </p>
              )}
            </div>

            <div>
              <div className="flex justify-between items-center">
                <label className="block text-sm font-medium text-gray-700">รหัสผ่าน</label>
                {!isRegister && (
                  <a href="#" onClick={(e) => { e.preventDefault(); navigate("/forgot-password"); }} className="text-sm font-medium text-blue-600 hover:text-blue-500 transition-colors">
                    ลืมรหัสผ่าน?
                  </a>
                )}
              </div>
              <div className="mt-1">
                <input 
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required 
                  className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {isRegister && (
              <div>
                <label className="block text-sm font-medium text-gray-700">ยืนยันรหัสผ่าน</label>
                <div className="mt-1">
                  <input 
                    type="password"
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    required 
                    className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                    placeholder="••••••••"
                  />
                  <p className="mt-2 text-xs text-rose-500 leading-relaxed">
                    * รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร มีตัวพิมพ์ใหญ่ (A-Z) ตัวพิมพ์เล็ก (a-z) และตัวเลข (0-9) อย่างน้อย 1 ตัว
                  </p>
                </div>
              </div>
            )}

            <div>
              <button 
                type="submit" 
                disabled={loading}
                className={`w-full flex justify-center py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors duration-200'}`}
              >
                {loading ? "กำลังประมวลผล..." : (isRegister ? "สมัครใช้งาน" : "เข้าสู่ระบบ")}
              </button>
            </div>
          </form>

          {!isRegister && passkeySupported && (
            <div className="mt-4">
              <button
                type="button"
                onPointerDown={cancelPasskeyAutofill}
                onClick={handlePasskeyLogin}
                disabled={passkeyBusy}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="8" cy="15" r="4" />
                  <path d="M10.85 12.15L19 4M17 6l2 2M15 8l2 2" />
                </svg>
                {passkeyBusy ? "รอยืนยันที่อุปกรณ์..." : "เข้าสู่ระบบด้วย Passkey"}
              </button>
              {passkeyBusy && (
                <p className="mt-2 text-center text-xs text-gray-500">
                  ไม่มีหน้าต่างสแกนนิ้ว/ใบหน้าขึ้นมา?{" "}
                  <button type="button" className="text-blue-600 hover:underline" onClick={cancelPasskeyButton} data-testid="passkey-cancel">
                    ยกเลิกแล้วกดใหม่
                  </button>
                </p>
              )}
            </div>
          )}


          {(googleClientId || lineLogin) && (
          <div className="mt-6" data-testid="social-login">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-gray-500">
                  {googleClientId && lineLogin ? "หรือใช้บัญชี Google / LINE" : googleClientId ? "หรือใช้บัญชี Google" : "หรือใช้บัญชี LINE"}
                </span>
              </div>
            </div>

            {googleClientId && (
            <GoogleOAuthProvider clientId={googleClientId}>
            <div className="mt-6 flex justify-center">
              <GoogleLogin
                // กว้าง/สูงเท่าปุ่ม LINE ด้านล่าง (ปุ่ม Google เป็น iframe — ปรับได้ผ่าน prop เท่านั้น)
                width={GOOGLE_BUTTON_WIDTH}
                size="large"
                shape="rectangular"
                onSuccess={async (credentialResponse) => {
                  try {
                    const data = await authGoogleLogin(credentialResponse.credential);
                    localStorage.setItem("token", data.access_token);
                    window.location.href = "/dashboard";
                  } catch (err) {
                    setErrorMsg("เข้าสู่ระบบด้วย Google ไม่สำเร็จ: " + err.message);
                  }
                }}
                onError={() => {
                  setErrorMsg("เข้าสู่ระบบด้วย Google ไม่สำเร็จ");
                }}
              />
            </div>
            </GoogleOAuthProvider>
            )}
            {lineLogin && (
              <div className={`${googleClientId ? "mt-3" : "mt-6"} flex flex-col items-center`}>
                <button
                  type="button"
                  onClick={handleLineLogin}
                  disabled={lineBusy}
                  data-testid="line-login-button"
                  style={{ width: GOOGLE_BUTTON_WIDTH }}
                  className="inline-flex items-center justify-center gap-2 max-w-full h-10 px-4 rounded bg-[#06C755] hover:bg-[#05b34c] text-white text-sm font-semibold disabled:opacity-60"
                >
                  <LineIcon /> {lineBusy ? "กำลังไปที่ LINE..." : "เข้าสู่ระบบด้วย LINE"}
                </button>
                <p className="mt-2 max-w-[320px] text-center text-xs text-gray-500">
                  เราขออีเมลจาก LINE เพื่อสร้างบัญชี เชื่อมกับบัญชีเดิม และส่งการแจ้งเตือน — ดู{" "}
                  <a href="/privacy" className="underline hover:text-gray-700">นโยบายความเป็นส่วนตัว</a>
                </p>
              </div>
            )}
          </div>
          )}

          {(selfRegistration || isRegister) && (
          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-gray-500">
                  {isRegister ? "มีบัญชีอยู่แล้ว?" : "ยังไม่มีบัญชี?"}
                </span>
              </div>
            </div>

            <div className="mt-6">
              <button
                onClick={() => { setIsRegister(!isRegister); setErrorMsg(""); setSuccessMsg(""); setConfirmPassword(""); setShowResend(false); }}
                className="w-full inline-flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors duration-200"
              >
                {isRegister ? "กลับไปหน้าเข้าสู่ระบบ" : "สมัครสมาชิกใหม่"}
              </button>
            </div>
          </div>
          )}
          {!selfRegistration && !isRegister && (
            <p className="mt-6 text-center text-sm text-gray-500" data-testid="register-closed">
              ยังไม่มีบัญชี? ติดต่อผู้ดูแลระบบขององค์กร
            </p>
          )}
        </div>
        <nav className="mt-6 flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm text-gray-500" aria-label="ข้อมูลบริการ" data-testid="legal-links">
          <a href="/privacy" className="hover:text-gray-700 hover:underline">นโยบายความเป็นส่วนตัว</a>
          <a href="/terms" className="hover:text-gray-700 hover:underline">ข้อกำหนดการใช้งาน</a>
          <a href="/manual.html" className="hover:text-gray-700 hover:underline">คู่มือการใช้งาน</a>
          <SourceCodeLink className="hover:text-gray-700 hover:underline" />
        </nav>
      </div>
    </div>
  );
}
