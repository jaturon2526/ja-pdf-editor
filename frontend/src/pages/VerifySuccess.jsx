import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppName } from '../hooks/useAppName.js';
import { useI18n } from '../i18n/I18nContext.jsx';

export default function VerifySuccess() {
  const { t } = useI18n();
  const appName = useAppName();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow-xl sm:rounded-xl sm:px-10 border border-gray-100 text-center">
          <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-6">
            <svg className="h-10 w-10 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            {t("authExtra.verifySuccess.title")}
          </h2>
          <p className="text-gray-600 mb-8">
            {t("authExtra.verifySuccess.desc", { appName })}
          </p>
          <button
            onClick={() => void navigate("/login")}
            className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors duration-200"
          >
            {t("authExtra.verifySuccess.goToLogin")}
          </button>
        </div>
      </div>
    </div>
  );
}
