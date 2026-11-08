import { useState, useEffect } from "react";
import * as api from "../api";

export default function useRedact({ session, currentPage, editMode, setStatusMessage, refreshAfterHistoryChange, resetTransientEditState }) {
  const [pendingRedactions, setPendingRedactions] = useState([]);
  const [applying, setApplying] = useState(false);

  // Clear when page changes or edit mode changes
  useEffect(() => {
    setPendingRedactions([]);
  }, [currentPage, editMode]);

  const addRedactions = (rects) => {
    setPendingRedactions((prev) => [...prev, ...rects]);
  };

  const applyRedactions = async () => {
    if (pendingRedactions.length === 0 || !session) return;
    setApplying(true);
    try {
      setStatusMessage("กำลังเซ็นเซอร์ข้อมูล... (Redacting)");
      await api.redactAreaBatch(session.sessionId, currentPage, pendingRedactions);
      setStatusMessage("เซ็นเซอร์และลบข้อมูลถาวรสำเร็จ");
      setPendingRedactions([]);
      await refreshAfterHistoryChange();
    } catch (err) {
      setStatusMessage(`เซ็นเซอร์ล้มเหลว: ${err.message}`);
    } finally {
      setApplying(false);
    }
  };

  
  const applyRedactionsAllPages = async () => {
    if (pendingRedactions.length === 0 || !session) return;
    setApplying(true);
    try {
      setStatusMessage("กำลังเซ็นเซอร์ข้อมูลทุกหน้า... (Redacting All Pages)");
      
      // Since redactAllPages in API expects a single rect, we will loop pendingRedactions
      // Wait, redactAllPages backend accepts a single `rect`. We can loop over pendingRedactions and call it for each, OR we can modify backend to accept an array of rects.
      // Let's modify frontend to loop over pendingRedactions and call redactAllPages sequentially, OR change API payload.
      // Modifying API to accept array `rects` is better for performance.
      
      await api.redactAllPagesBatch(session.sessionId, pendingRedactions);
      setStatusMessage("เซ็นเซอร์และลบข้อมูลทุกหน้าสำเร็จ");
      setPendingRedactions([]);
      await refreshAfterHistoryChange();
    } catch (err) {
      setStatusMessage(`เซ็นเซอร์ล้มเหลว: ${err.message}`);
    } finally {
      setApplying(false);
    }
  };

  const cancelRedactions = () => {
    setPendingRedactions([]);
    resetTransientEditState();
  };

  const reset = () => {
    setPendingRedactions([]);
  };

  return {
    pendingRedactions,
    addRedactions,
    applyRedactions,
    applyRedactionsAllPages,
    cancelRedactions,
    applying,
    reset,
  };
}
