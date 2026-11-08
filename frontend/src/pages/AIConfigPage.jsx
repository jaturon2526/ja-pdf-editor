// ตั้งค่า AI — AI ของระบบ (ผู้ดูแลตั้งใน .env: AI_PROVIDER) และ API key ส่วนตัวที่เลือกค่ายได้ (Gemini / Claude / OpenAI
// และ API แบบ OpenAI เช่น Azure OpenAI หรือโมเดลขององค์กร) — backend ลองเรียกจริงก่อนบันทึก (POST /auth/api-key)
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAiQuota, getMe, removeApiKey, saveApiKey } from "../api";

const PROVIDER_HELP = {
  gemini: {
    keyPlaceholder: "AIzaSy...",
    modelPlaceholder: "ว่าง = Gemini Flash รุ่นล่าสุด",
    link: "https://aistudio.google.com/apikey",
    linkLabel: "Google AI Studio",
  },
  anthropic: {
    keyPlaceholder: "sk-ant-...",
    modelPlaceholder: "ว่าง = claude-haiku-5-5",
    link: "https://console.anthropic.com/settings/keys",
    linkLabel: "Claude Console",
    note: "ต้องเป็น API key จาก Claude Console (คิดเงินตามการใช้งาน) — แผนสมาชิก Claude Pro/Max/Team ใช้แทนไม่ได้",
  },
  openai: {
    keyPlaceholder: "sk-... (Azure: key ของ resource)",
    modelPlaceholder: "เช่น gpt-4.1-mini หรือชื่อ deployment ของ Azure",
    link: "https://platform.openai.com/api-keys",
    linkLabel: "OpenAI Platform",
    note: "Azure OpenAI: URL = https://<resource>.openai.azure.com/openai/v1 · โมเดลที่องค์กรรันเอง (vLLM/Ollama/LiteLLM) ใส่ URL ของ API นั้น",
    needsModel: true,
    showBaseUrl: true,
  },
};

const input = "w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

export default function AIConfigPage() {
  const [user, setUser] = useState(null);
  const [q, setQ] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ provider: "gemini", apiKey: "", model: "", baseUrl: "" });

  async function fetchData() {
    try {
      const [me, quota] = await Promise.all([getMe(), getAiQuota()]);
      setUser(me);
      setQ(quota);
      if (quota.personal_provider) {
        setForm((f) => ({ ...f, provider: quota.personal_provider, model: quota.personal_model || "", baseUrl: quota.personal_base_url || "" }));
      }
    } catch {
      setError("ไม่สามารถโหลดข้อมูลได้");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
  }, []);

  const help = PROVIDER_HELP[form.provider] || PROVIDER_HELP.gemini;
  const providerLabel = (value) => q?.providers?.find((p) => p.value === value)?.label || value;
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function handleSave(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!form.apiKey.trim() && !(form.provider === "openai" && form.baseUrl.trim())) {
      setError("กรุณากรอก API Key");
      return;
    }
    if (help.needsModel && !form.model.trim()) {
      setError("กรุณาระบุชื่อรุ่น (model)");
      return;
    }
    setSaving(true);
    try {
      const res = await saveApiKey({ ...form, apiKey: form.apiKey.trim(), model: form.model.trim(), baseUrl: form.baseUrl.trim() });
      setSuccess(`ทดสอบผ่านและบันทึกแล้ว — ใช้ ${providerLabel(res.provider)}${res.model ? ` (${res.model})` : ""} เมื่อโควต้า AI ของระบบหมด`);
      setForm((f) => ({ ...f, apiKey: "" }));
      fetchData();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    if (!window.confirm("ลบ API Key ส่วนตัว และกลับไปใช้ AI ของระบบใช่หรือไม่?")) return;
    try {
      await removeApiKey();
      setSuccess("ลบ API Key แล้ว — กลับไปใช้ AI ของระบบ");
      setForm({ provider: "gemini", apiKey: "", model: "", baseUrl: "" });
      fetchData();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) return <div className="p-8 text-center">กำลังโหลด...</div>;

  return (
    <div className="max-w-2xl mx-auto p-4 md:p-8">
      <div className="mb-6">
        <Link to="/dashboard" className="text-blue-600 hover:underline text-sm flex items-center gap-1">
          &larr; กลับหน้า Dashboard
        </Link>
      </div>

      <h1 className="text-2xl font-bold mb-2">ตั้งค่า AI &amp; API Key ส่วนตัว</h1>
      <p className="text-sm text-gray-500 mb-6">AI ใช้แก้คำไทยตอนแปลง PDF เป็น Word และอ่านข้อความจากพื้นที่ที่เลือก (คัดลอกข้อความ)</p>

      {error && <div className="bg-red-50 text-red-700 p-4 rounded mb-4" role="alert">{error}</div>}
      {success && <div className="bg-green-50 text-green-700 p-4 rounded mb-4">{success}</div>}

      <div className="bg-white rounded-lg shadow p-6 mb-6" data-testid="system-ai">
        <h2 className="text-lg font-semibold mb-2">AI ของระบบ</h2>
        {q?.system_ai ? (
          <>
            <p className="text-sm text-gray-700">
              ใช้ <strong>{q.system_provider_label}</strong>{q.system_model ? ` · รุ่น ${q.system_model}` : ""} — แปลงเป็น Word ด้วย AI ได้วันละ{" "}
              <strong>{q.system_daily_limit}</strong> ครั้ง (วันนี้ใช้แล้ว {q.system_requests_today} ครั้ง)
            </p>
            {user?.is_admin && q.system_key_preview && (
              <p className="mt-3 text-xs text-gray-500">
                key ของระบบ (.env): <span className="font-mono bg-gray-50 border border-gray-200 px-2 py-0.5 rounded">{q.system_key_preview}</span>
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-gray-600">ระบบยังไม่ได้ตั้ง AI — แปลงเป็น Word ได้ตามปกติแต่ไม่มีการแก้คำด้วย AI{q?.user_keys_enabled ? " (ใส่ API key ส่วนตัวด้านล่างเพื่อใช้ AI)" : ""}</p>
        )}
        <p className="mt-3 text-xs text-gray-500">คำขอ AI ด้วย key ส่วนตัวของคุณวันนี้: {q?.requests_today ?? 0} ครั้ง</p>
      </div>

      {q?.user_keys_enabled === false ? (
        <div className="bg-white rounded-lg shadow p-6 text-sm text-gray-600">ระบบนี้ไม่เปิดให้ใช้ API key ส่วนตัว — ใช้ AI ของระบบเท่านั้น</div>
      ) : (
        <div className="bg-white rounded-lg shadow p-6" data-testid="personal-ai">
          <h2 className="text-lg font-semibold mb-1">API Key ส่วนตัว</h2>
          <p className="text-sm text-gray-500 mb-4">ใช้เครดิตของคุณเอง (หรือของแผนก) เมื่อโควต้าของระบบหมด หรือใช้ค่ายที่ต่างจากระบบได้ — key ถูกเข้ารหัสก่อนเก็บ</p>

          {user?.has_api_key && (
            <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded text-green-800 text-sm">
              <p>
                ตั้งไว้แล้ว: <strong>{providerLabel(q?.personal_provider || "gemini")}</strong>
                {q?.personal_model ? ` · รุ่น ${q.personal_model}` : ""}
              </p>
              {q?.personal_base_url && <p className="mt-1 break-all">URL: {q.personal_base_url}</p>}
              {q?.personal_key_preview && (
                <p className="font-mono bg-white border border-green-300 px-3 py-1.5 rounded mt-2 select-none">{q.personal_key_preview}</p>
              )}
              <button onClick={handleRemove} className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200 text-sm font-medium">
                ลบ API Key (กลับไปใช้ AI ของระบบ)
              </button>
            </div>
          )}

          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label htmlFor="ai-provider" className="block text-sm font-medium text-gray-700 mb-1">ผู้ให้บริการ AI</label>
              <select id="ai-provider" className={input} value={form.provider}
                onChange={(e) => setForm({ provider: e.target.value, apiKey: "", model: "", baseUrl: "" })}>
                {(q?.providers || [{ value: "gemini", label: "Google Gemini" }]).map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500">
                สร้าง key ได้ที่ <a href={help.link} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">{help.linkLabel}</a>
                {help.note ? <> · {help.note}</> : null}
              </p>
            </div>
            <div>
              <label htmlFor="ai-key" className="block text-sm font-medium text-gray-700 mb-1">
                {user?.has_api_key ? "API Key ใหม่" : "API Key"}
              </label>
              <input id="ai-key" type="password" autoComplete="off" className={input} value={form.apiKey} onChange={set("apiKey")} placeholder={help.keyPlaceholder} />
            </div>
            <div>
              <label htmlFor="ai-model" className="block text-sm font-medium text-gray-700 mb-1">
                รุ่น (model){help.needsModel ? "" : " — ไม่บังคับ"}
              </label>
              <input id="ai-model" className={input} value={form.model} onChange={set("model")} placeholder={help.modelPlaceholder} maxLength={100} />
            </div>
            {help.showBaseUrl && (
              <div>
                <label htmlFor="ai-base" className="block text-sm font-medium text-gray-700 mb-1">URL ของ API — ไม่บังคับ (ว่าง = OpenAI)</label>
                <input id="ai-base" className={input} value={form.baseUrl} onChange={set("baseUrl")} placeholder="https://<resource>.openai.azure.com/openai/v1" maxLength={300} />
              </div>
            )}
            <button type="submit" disabled={saving}
              className="w-full md:w-auto px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
              {saving ? "กำลังทดสอบ key..." : "ทดสอบและบันทึก"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
