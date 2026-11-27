import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, getAdminStats, getAdminUsers, updateAdminUserPlan, updateAdminUserStatus, getAdminPlans, updateAdminPlanConfig } from "../api";
import { getPublicConfig } from "../api/config.js";
import QuotaPanel from "../components/admin/QuotaPanel.jsx";
import DonationsPanel from "../components/admin/DonationsPanel.jsx";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function AdminDashboard() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const [user, setUser] = useState(null);
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 50;
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  
  const [editingUser, setEditingUser] = useState(null);
  const [editPlan, setEditPlan] = useState("free");
  const [plans, setPlans] = useState([]);
  const [showPlanConfig, setShowPlanConfig] = useState(false);
  const [isOnprem, setIsOnprem] = useState(false);

  useEffect(() => {
    getPublicConfig()
      .then((cfg) => setIsOnprem(cfg?.profile === "onprem"))
      .catch(() => {});
  }, []);

  useEffect(() => {
    async function init() {
      try {
        const userData = await getMe();
        setUser(userData);
        if (!userData.is_admin) {
          void navigate("/dashboard");
          return;
        }
        void fetchData();
      } catch (err) {
        void navigate("/");
      }
    }
    void init();
  }, [navigate]); // navigate คงที่ตลอดอายุ component — รันครั้งเดียวตอนเปิดหน้า

  async function fetchData(showLoading = true) {
    if (showLoading) setLoading(true);
    try {
      const statsData = await getAdminStats();
      setStats(statsData);

      const usersData = await getAdminUsers();
      setUsers(usersData.users);
      
      const plansData = await getAdminPlans();
      setPlans(plansData);
    } catch (err) {
      setError(err.message);
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  const handleSavePlanConfig = async (e, planType, maxSessions, maxStorageMb) => {
    e.preventDefault();
    try {
      await updateAdminPlanConfig(planType, Number.parseInt(maxSessions, 10), Number.parseInt(maxStorageMb, 10));
      await fetchData(false);
      setSuccessMessage(t("admin.planSaved", { plan: planType.toUpperCase() }));
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      setError("Error: " + err.message);
      setTimeout(() => setError(""), 3000);
    }
  };

  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  async function handleToggleStatus(u) {
    // Optimistic UI Update (Immediate visual feedback)
    setUsers(users.map(x => x.id === u.id ? { ...x, is_active: !x.is_active } : x));
    try {
      await updateAdminUserStatus(u.id, !u.is_active, u.is_admin);
      void fetchData(false); // Sync in background to prevent UI unmount
    } catch (e) {
      console.error("Failed to toggle status", e);
      // Revert if failed
      setUsers(users.map(x => x.id === u.id ? { ...x, is_active: u.is_active } : x));
    }
  }

  async function handleSavePlan(e) {
    e.preventDefault();
    try {
      await updateAdminUserPlan(editingUser.id, editPlan);
      setEditingUser(null);
      void fetchData(false); // Sync in background
    } catch (err) {
      setError(t("admin.planSaveError", { message: err.message }));
    }
  }

  if (loading) return <div className="p-8 text-center text-gray-500">{t("admin.loadingData")}</div>;
  if (!user || !user.is_admin) return null;

  const filteredUsers = users.filter(u => 
    (u.email || "").toLowerCase().includes(searchQuery.toLowerCase()) || 
    (u.display_name || "").toLowerCase().includes(searchQuery.toLowerCase())
  );
  const totalPages = Math.ceil(filteredUsers.length / itemsPerPage) || 1;
  const paginatedUsers = filteredUsers.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-2xl font-bold text-gray-800">{t("pages.adminTitle")}</h1>
          <div className="flex items-center gap-4">
            <button 
              type="button"
              onClick={() => setShowPlanConfig(true)}
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-md hover:bg-indigo-700 transition-colors shadow-sm"
            >
              {t("admin.planLimitsBtn")}
            </button>
            <button 
              type="button"
              onClick={() => void navigate("/dashboard")}
              className="text-blue-600 hover:text-blue-800 font-medium"
            >
              {t("profile.backToDashboard")}
            </button>
          </div>
        </div>

        {error && <div className="bg-red-50 text-red-600 p-4 rounded mb-6">{error}</div>}

        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <div className="text-gray-500 text-sm mb-1">{t("admin.totalUsers")}</div>
              <div className="text-3xl font-bold text-gray-800">{stats.total_users}</div>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <div className="text-gray-500 text-sm mb-1">{t("admin.totalFiles")}</div>
              <div className="text-3xl font-bold text-gray-800">{stats.total_files}</div>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <div className="text-gray-500 text-sm mb-1">{t("admin.totalStorage")}</div>
              <div className="text-3xl font-bold text-blue-600">{formatBytes(stats.total_storage)}</div>
            </div>
          </div>
        )}

        {user?.is_admin && <QuotaPanel />}
        {user?.is_admin && !isOnprem && <DonationsPanel />}

        <div className="mb-6">
          <div className="relative max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </div>
            <input
              type="text"
              placeholder={t("admin.searchPlaceholder")}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm transition-colors"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
            />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colUser")}</th>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colStatus")}</th>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colPlan")}</th>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colLicense")}</th>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colStorage")}</th>
                <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200">{t("admin.colFiles")}</th>
                <th className="px-6 py-3 bg-gray-50 border-b border-gray-200 relative"><span className="sr-only">{t("admin.colActions")}</span></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {paginatedUsers.map(u => {
                let licenseCell;
                if (u.plan_type === "free") {
                  licenseCell = <span className="text-gray-400">-</span>;
                } else if (u.expire_date === null) {
                  licenseCell = <span className="text-emerald-600 font-medium">{t("admin.licensePermanent")}</span>;
                } else {
                  licenseCell = (
                    <div className="flex flex-col">
                      <span className="text-blue-600 font-medium">Subscribe</span>
                      <span className="text-xs text-gray-400 mt-0.5">
                        {t("admin.licenseExpires", { date: new Date(u.expire_date).toLocaleDateString(locale) })}
                      </span>
                    </div>
                  );
                }
                return (
                <tr key={u.id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold">
                        {(u.display_name || u.email).substring(0, 1).toUpperCase()}
                      </div>
                      <div className="ml-4">
                        <div className="text-sm font-medium text-gray-900">{u.display_name || 'No Name'} {u.is_admin && <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">Admin</span>}</div>
                        <div className="text-sm text-gray-500">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {u.is_active ? t("admin.statusActive") : t("admin.statusSuspended")}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                      u.plan_type === 'premium' ? 'bg-yellow-100 text-yellow-800' :
                      u.plan_type === 'pro' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {u.plan_type.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {licenseCell}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatBytes(u.total_storage)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {u.total_files}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <div className="flex gap-2">
                      <button type="button" onClick={() => { setEditingUser(u); setEditPlan(u.plan_type); }} className="px-3 py-1.5 bg-blue-50 text-blue-700 text-xs font-semibold rounded-md hover:bg-blue-100 transition-colors border border-blue-200">
                        {t("admin.planBtn")}
                      </button>
                      {u.id !== user.id && (
                        <button type="button" onClick={() => void handleToggleStatus(u)} className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors border ${u.is_active ? 'bg-red-50 text-red-700 hover:bg-red-100 border-red-200' : 'bg-green-50 text-green-700 hover:bg-green-100 border-green-200'}`}>
                          {u.is_active ? t("admin.suspendBtn") : t("admin.unsuspendBtn")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="bg-white px-4 py-3 border border-gray-200 border-t-0 rounded-b-lg flex items-center justify-between sm:px-6 mb-6">
            <div className="flex-1 flex justify-between sm:hidden">
              <button
                type="button"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("admin.prevPage")}
              </button>
              <button
                type="button"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("admin.nextPage")}
              </button>
            </div>
            <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-gray-700">
                  {t("admin.showingPrefix")} <span className="font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> {t("admin.showingTo")} <span className="font-medium">{Math.min(currentPage * itemsPerPage, filteredUsers.length)}</span> {t("admin.showingOf")} <span className="font-medium">{filteredUsers.length}</span> {t("admin.showingSuffix")}
                </p>
              </div>
              <div>
                <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                  <button
                    type="button"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">{t("admin.prevPageSr")}</span>
                    <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                  <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
                    {t("admin.pageOf", { current: currentPage, total: totalPages })}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">{t("admin.nextPageSr")}</span>
                    <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                </nav>
              </div>
            </div>
          </div>
        )}
      </div>

      {editingUser && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-sm w-full p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">{t("admin.changePlanTitle")}</h3>
            <p className="text-sm text-gray-600 mb-4">{t("admin.editingAccount", { email: editingUser.email })}</p>
            <form onSubmit={(e) => void handleSavePlan(e)}>
              <select 
                className="w-full border border-gray-300 rounded p-2 mb-4"
                value={editPlan}
                onChange={e => setEditPlan(e.target.value)}
              >
                <option value="free">Free (100MB)</option>
                <option value="pro">Pro (1GB)</option>
                <option value="premium">Premium (5GB)</option>
              </select>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setEditingUser(null)} className="px-4 py-2 text-gray-600 bg-gray-100 rounded hover:bg-gray-200">{t("common.cancel")}</button>
                <button type="submit" className="px-4 py-2 text-white bg-blue-600 rounded hover:bg-blue-700">{t("common.saveShort")}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showPlanConfig && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6">
            <h3 className="text-xl font-bold text-gray-900 mb-2">{t("admin.planLimitsTitle")}</h3>
            <p className="text-sm text-gray-500 mb-4">{t("admin.planLimitsDesc")}</p>
            
            {successMessage && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-2 rounded mb-4 text-sm font-medium">{successMessage}</div>}
            
            <div className="space-y-4">
              {plans.map(p => (
                <form key={p.plan_type} onSubmit={(e) => void handleSavePlanConfig(e, p.plan_type, e.target.max_sessions.value, e.target.max_storage_mb.value)} className="flex items-center justify-between p-3 border rounded-lg bg-gray-50">
                  <div className="w-24">
                    <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                      p.plan_type === 'premium' ? 'bg-yellow-100 text-yellow-800' :
                      p.plan_type === 'pro' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {p.plan_type.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex-1 flex items-center justify-end gap-6">
                    <div className="flex items-center gap-2">
                      <label htmlFor={`plan-${p.plan_type}-max_sessions`} className="text-sm text-gray-600">Sessions:</label>
                      <input id={`plan-${p.plan_type}-max_sessions`} name="max_sessions" type="number" defaultValue={p.max_sessions} min="1" className="w-16 px-2 py-1 border rounded text-center text-sm" />
                    </div>
                    <div className="flex items-center gap-2">
                      <label htmlFor={`plan-${p.plan_type}-max_storage_mb`} className="text-sm text-gray-600">Disk (MB):</label>
                      <input id={`plan-${p.plan_type}-max_storage_mb`} name="max_storage_mb" type="number" defaultValue={p.max_storage_mb} min="1" className="w-24 px-2 py-1 border rounded text-center text-sm" />
                    </div>
                    <button type="submit" className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 ml-2">{t("admin.updateBtn")}</button>
                  </div>
                </form>
              ))}
            </div>

            <div className="mt-6 flex justify-end">
              <button type="button" onClick={() => setShowPlanConfig(false)} className="px-4 py-2 text-gray-600 bg-gray-100 rounded hover:bg-gray-200">{t("admin.closeWindowBtn")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
