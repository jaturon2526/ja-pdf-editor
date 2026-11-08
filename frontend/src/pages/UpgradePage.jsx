import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api";

export default function UpgradePage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const userData = await getMe();
        setUser(userData);
      } catch (err) {
        navigate("/");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const plans = [
    {
      id: "free",
      name: "Free",
      price: "฿0",
      period: "/ ตลอดชีพ",
      storage: "100 MB",
      features: [
        "แก้ไขข้อความและรูปภาพพื้นฐาน",
        "เซ็นเอกสารอิเล็กทรอนิกส์",
        "พื้นที่จัดเก็บ 100 MB",
        "เปิดใช้งานได้ 1 อุปกรณ์"
      ]
    },
    {
      id: "pro",
      name: "Pro",
      price: "฿199",
      period: "/ เดือน",
      storage: "1 GB",
      features: [
        "เครื่องมือทั้งหมดในแพ็กเกจ Free",
        "รวมไฟล์, แยกไฟล์, บีบอัดไฟล์ PDF",
        "จัดการหน้าเอกสาร (หมุน, ลบ, จัดเรียง)",
        "พื้นที่จัดเก็บ 1 GB",
        "เปิดใช้งานได้สูงสุด 3 อุปกรณ์พร้อมกัน"
      ],
      popular: true
    },
    {
      id: "premium",
      name: "Premium",
      price: "฿499",
      period: "/ เดือน",
      storage: "5 GB",
      features: [
        "เครื่องมือทั้งหมดในแพ็กเกจ Pro",
        "ดึงข้อความจากภาพ (OCR)",
        "ระบบเซนเซอร์ข้อมูลสำคัญ (Redaction)",
        "พื้นที่จัดเก็บ 5 GB",
        "เปิดใช้งานได้ไม่จำกัดอุปกรณ์",
        "การสนับสนุนระดับ Priority"
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="flex justify-between items-center mb-10">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">อัปเกรดแพ็กเกจ</h1>
            <p className="mt-2 text-gray-600">เลือกแพ็กเกจที่เหมาะสมกับการทำงานของคุณ</p>
          </div>
          <button
            onClick={() => navigate("/dashboard")}
            className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            กลับหน้าหลัก
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {plans.map((plan) => {
            const isCurrentPlan = user?.plan_type === plan.id;
            return (
              <div 
                key={plan.id} 
                className={`relative bg-white rounded-2xl shadow-sm border ${
                  plan.popular ? 'border-blue-500 shadow-md' : 'border-gray-200'
                } p-8 flex flex-col`}
              >
                {plan.popular && (
                  <div className="absolute top-0 right-6 transform -translate-y-1/2">
                    <span className="bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
                      ยอดนิยม
                    </span>
                  </div>
                )}
                
                {isCurrentPlan && (
                  <div className="absolute top-0 left-6 transform -translate-y-1/2">
                    <span className="bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                      แพ็กเกจปัจจุบัน
                    </span>
                  </div>
                )}

                <div className="mb-6">
                  <h3 className="text-xl font-bold text-gray-900">{plan.name}</h3>
                  <div className="mt-4 flex items-baseline text-gray-900">
                    <span className="text-4xl font-extrabold tracking-tight">{plan.price}</span>
                    <span className="ml-1 text-xl font-medium text-gray-500">{plan.period}</span>
                  </div>
                </div>

                <ul className="mb-8 space-y-4 flex-1">
                  {plan.features.map((feature, idx) => (
                    <li key={idx} className="flex items-start">
                      <svg className="flex-shrink-0 h-5 w-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      <span className="ml-3 text-gray-600 text-sm leading-relaxed">{feature}</span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => !isCurrentPlan && setShowModal(true)}
                  disabled={isCurrentPlan}
                  className={`w-full py-3 px-4 rounded-xl font-bold transition-colors ${
                    isCurrentPlan
                      ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                      : plan.popular
                        ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
                        : 'bg-white border-2 border-blue-600 text-blue-600 hover:bg-blue-50'
                  }`}
                >
                  {isCurrentPlan ? "แพ็กเกจของคุณ" : "เลือกแพ็กเกจนี้"}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl p-8 max-w-sm w-full mx-auto text-center transform transition-all">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">อัปเกรดระบบชำระเงิน</h3>
            <p className="text-gray-600 text-sm mb-6">
              ระบบชำระเงินอัตโนมัติกำลังอยู่ในระหว่างการพัฒนา ในระหว่างนี้กรุณาติดต่อผู้ดูแลระบบเพื่อทำการอัปเกรดแพ็กเกจครับ
            </p>
            <button
              onClick={() => setShowModal(false)}
              className="w-full bg-blue-600 text-white rounded-xl py-2.5 font-medium hover:bg-blue-700 transition-colors"
            >
              เข้าใจแล้ว
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
