import { useState, useEffect } from "react";
import * as api from "../api";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function useRedact({ session, currentPage, editMode, setStatusMessage, refreshAfterHistoryChange, resetTransientEditState }) {
  const { t } = useI18n();
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
      setStatusMessage(t("editor.hooks.redact.redacting"));
      await api.redactAreaBatch(session.sessionId, currentPage, pendingRedactions);
      setStatusMessage(t("editor.hooks.redact.redactSuccess"));
      setPendingRedactions([]);
      await refreshAfterHistoryChange();
    } catch (err) {
      setStatusMessage(t("editor.hooks.redact.redactFailed", { message: err.message }));
    } finally {
      setApplying(false);
    }
  };

  
  const applyRedactionsAllPages = async () => {
    if (pendingRedactions.length === 0 || !session) return;
    setApplying(true);
    try {
      setStatusMessage(t("editor.hooks.redact.redactingAllPages"));
      
      // Since redactAllPages in API expects a single rect, we will loop pendingRedactions
      // Wait, redactAllPages backend accepts a single `rect`. We can loop over pendingRedactions and call it for each, OR we can modify backend to accept an array of rects.
      // Let's modify frontend to loop over pendingRedactions and call redactAllPages sequentially, OR change API payload.
      // Modifying API to accept array `rects` is better for performance.
      
      await api.redactAllPagesBatch(session.sessionId, pendingRedactions);
      setStatusMessage(t("editor.hooks.redact.redactAllPagesSuccess"));
      setPendingRedactions([]);
      await refreshAfterHistoryChange();
    } catch (err) {
      setStatusMessage(t("editor.hooks.redact.redactFailed", { message: err.message }));
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

  const undoLastPending = () => {
    if (pendingRedactions.length === 0) return false;
    setPendingRedactions((prev) => prev.slice(0, -1));
    return true;
  };

  return {
    pendingRedactions,
    addRedactions,
    applyRedactions,
    applyRedactionsAllPages,
    cancelRedactions,
    undoLastPending,
    applying,
    reset,
  };
}
