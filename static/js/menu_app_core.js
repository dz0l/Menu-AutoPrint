(function (global) {
  "use strict";

  const C = global.MenuCommon;
  const Theme = global.MenuTheme;
  if (!C) {
    throw new Error("MenuCommon must load before MenuApp core");
  }
  if (!Theme) {
    throw new Error("MenuTheme must load before MenuApp core");
  }

  const STORAGE_KEYS = {
    editorRows: "menu_editor_rows",
    lastRu: "menu_last_ru",
    lastEn: "menu_last_en",
    editorSavedChanges: "menu_editor_saved_changes",
    pdfBackgroundName: "menu_pdf_background_name",
    pdfBackgroundData: "menu_pdf_background_data",
    coverMode: "menu_cover_mode",
    coverId: "menu_cover_id",
    alternatePrintMode: "menu_alt_print_mode",
    themeMode: "menu_theme_mode",
    debugLogging: "menu_debug_logging",
    showKcal: "menu_show_kcal",
    autoFormat: "menu_auto_format",
  };

  const APP_CONFIG = JSON.parse(document.getElementById("appConfig")?.textContent || "{}");
  const IS_ADMIN = Boolean(APP_CONFIG.isAdmin);
  const COVER_MODE = {
    none: "none",
    custom: "custom",
    cover: "cover",
  };
  const RU_HISTORY_LIMIT = 120;
  const A4_RATIO = 210 / 297;
  const PREVIEW_BASE_WIDTH = 375;

  const MenuAppState = {
    lastMissing: [],
    lastFixables: [],
    suggestItems: [],
    suggestActive: -1,
    suggestCatalog: [],
    suggestTimer: null,
    previewTimer: null,
    actionTimer: null,
    analyzeInFlight: false,
    usersLoading: false,
    lastPreviewData: null,
    previewSegmentIndex: 0,
    previewLang: "ru",
    pdfInFlight: false,
    coversCatalog: [],
    coversLoading: false,
    coverSelectQuiet: false,
    previousCoverSelectValue: "__custom__",
    previewController: null,
    actionsController: null,
    previewSeq: 0,
    actionsSeq: 0,
    previewActiveSignature: "",
    previewRenderedSignature: "",
    previewQueuedReason: "",
    actionsActiveSignature: "",
    actionsAppliedSignature: "",
    heavyUpdateTimer: null,
    ruHistory: [],
    ruHistoryIndex: -1,
    ruHistoryLastCommit: 0,
    suppressRuHistory: false,
    debugLoggingEnabled: false,
    previewResizeObserver: null,
  };

  const $ = C.$;
  const loadStorage = C.loadStorage;
  const saveStorage = C.saveStorage;
  const removeStorage = C.removeStorage;
  const lines = C.lines;
  const toast = C.toast;
  const csrfToken = C.csrfToken;
  const postJson = C.postJson;
  const requestJson = C.requestJson;

  function debugLog(event, data = {}) {
    if (!MenuAppState.debugLoggingEnabled) {
      return;
    }
    console.info("[MenuLog]", event, {
      at: new Date().toISOString(),
      ...data,
    });
  }

  function debugWarn(event, data = {}) {
    if (!MenuAppState.debugLoggingEnabled) {
      return;
    }
    console.warn("[MenuLog]", event, {
      at: new Date().toISOString(),
      ...data,
    });
  }

  function menuStats(value) {
    const text = String(value || "");
    return {
      chars: text.length,
      lines: lines(text).length,
    };
  }

  function payloadSummary(payload) {
    if (!payload || typeof payload !== "object") {
      return {};
    }
    if (Object.prototype.hasOwnProperty.call(payload, "ru")) {
      return {
        ru: menuStats(payload.ru),
        show_kcal: payload.show_kcal,
      };
    }
    if (Array.isArray(payload.ru_lines)) {
      return {
        ru_lines: payload.ru_lines.length,
      };
    }
    if (Object.prototype.hasOwnProperty.call(payload, "text")) {
      return {
        text: menuStats(payload.text),
      };
    }
    return {};
  }

  function previewSignature(payload) {
    return JSON.stringify({
      ru: payload.ru || "",
      show_kcal: Boolean(payload.show_kcal),
      auto_format: Boolean(payload.auto_format),
    });
  }

  function actionsSignature(payload) {
    return JSON.stringify({
      ru_lines: payload.ru_lines || [],
      show_kcal: Boolean(payload.show_kcal),
    });
  }

  function saveMenuDraft() {
    saveStorage(STORAGE_KEYS.lastRu, $("ruText").value);
    saveStorage(STORAGE_KEYS.lastEn, $("enText").value);
  }

  function resetRuHistory(value) {
    MenuAppState.ruHistory = [String(value || "")];
    MenuAppState.ruHistoryIndex = 0;
    MenuAppState.ruHistoryLastCommit = Date.now();
  }

  function pushRuHistory(value, options = {}) {
    if (MenuAppState.suppressRuHistory) {
      return;
    }

    const next = String(value || "");
    const force = Boolean(options.force);
    if (MenuAppState.ruHistoryIndex < 0) {
      resetRuHistory(next);
      return;
    }

    const current = MenuAppState.ruHistory[MenuAppState.ruHistoryIndex];
    if (next === current) {
      return;
    }

    const now = Date.now();
    const canMerge =
      !force &&
      MenuAppState.ruHistory.length > 1 &&
      MenuAppState.ruHistoryIndex === MenuAppState.ruHistory.length - 1 &&
      now - MenuAppState.ruHistoryLastCommit < 700;

    if (canMerge) {
      MenuAppState.ruHistory[MenuAppState.ruHistoryIndex] = next;
      MenuAppState.ruHistoryLastCommit = now;
      return;
    }

    if (MenuAppState.ruHistoryIndex < MenuAppState.ruHistory.length - 1) {
      MenuAppState.ruHistory = MenuAppState.ruHistory.slice(0, MenuAppState.ruHistoryIndex + 1);
    }

    MenuAppState.ruHistory.push(next);
    if (MenuAppState.ruHistory.length > RU_HISTORY_LIMIT) {
      const overflow = MenuAppState.ruHistory.length - RU_HISTORY_LIMIT;
      MenuAppState.ruHistory.splice(0, overflow);
      MenuAppState.ruHistoryIndex = Math.max(0, MenuAppState.ruHistoryIndex - overflow);
    }

    MenuAppState.ruHistoryIndex = MenuAppState.ruHistory.length - 1;
    MenuAppState.ruHistoryLastCommit = now;
  }

  function applyRuHistoryState(value) {
    const App = global.MenuApp;
    const textarea = $("ruText");
    MenuAppState.suppressRuHistory = true;
    textarea.value = value;
    MenuAppState.suppressRuHistory = false;
    App.hideSuggest();
    saveMenuDraft();
    updateLineCounter();
    App.flushHeavyUpdate("history");
    textarea.focus();
    textarea.setSelectionRange(value.length, value.length);
  }

  function undoRuChange() {
    if (MenuAppState.ruHistoryIndex <= 0) {
      return false;
    }
    MenuAppState.ruHistoryIndex -= 1;
    applyRuHistoryState(MenuAppState.ruHistory[MenuAppState.ruHistoryIndex]);
    return true;
  }

  function redoRuChange() {
    if (MenuAppState.ruHistoryIndex >= MenuAppState.ruHistory.length - 1) {
      return false;
    }
    MenuAppState.ruHistoryIndex += 1;
    applyRuHistoryState(MenuAppState.ruHistory[MenuAppState.ruHistoryIndex]);
    return true;
  }

  function setRuTextValue(value, options = {}) {
    const textarea = $("ruText");
    const next = String(value || "");
    if (textarea.value === next) {
      return;
    }

    textarea.value = next;
    pushRuHistory(next, {force: options.forceHistory !== false});
    saveMenuDraft();
    updateLineCounter();
  }

  function applyDebugLogging(enabled) {
    MenuAppState.debugLoggingEnabled = Boolean(enabled);
    const checkbox = $("debugLogging");
    if (checkbox) {
      checkbox.checked = MenuAppState.debugLoggingEnabled;
    }
    saveStorage(STORAGE_KEYS.debugLogging, MenuAppState.debugLoggingEnabled ? "1" : "0");
    debugLog("logging:enabled");
  }

  function applyAlternatePrintMode(enabled) {
    const checkbox = $("alternatePrintMode");
    if (checkbox) {
      checkbox.checked = Boolean(enabled);
    }
    saveStorage(STORAGE_KEYS.alternatePrintMode, enabled ? "1" : "0");
  }

  function isAlternatePrintMode() {
    return $("alternatePrintMode")?.checked || false;
  }

  function updateKcalToggleUi() {
    const checkbox = $("showKcal");
    const button = $("btnKcalToggle");
    if (!checkbox || !button) {
      return;
    }
    const active = checkbox.checked;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }

  function pluralRu(value, one, few, many) {
    const abs = Math.abs(Number(value) || 0);
    const lastTwo = abs % 100;
    const last = abs % 10;
    if (lastTwo >= 11 && lastTwo <= 14) {
      return many;
    }
    if (last === 1) {
      return one;
    }
    if (last >= 2 && last <= 4) {
      return few;
    }
    return many;
  }

  function updateLineCounter() {
    const counter = $("lineCounter");
    if (!counter) {
      return;
    }
    const count = lines($("ruText").value).length;
    counter.textContent = `${count} ${pluralRu(count, "строка", "строки", "строк")}`;
  }

  function isoDate(date) {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }

  function todayDate() {
    return isoDate(new Date());
  }

  function tomorrowDate() {
    return isoDate(new Date(Date.now() + 24 * 60 * 60 * 1000));
  }

  function updateDateUi() {
    const App = global.MenuApp;
    const mode = $("printDateMode").value;
    if (mode === "today") {
      $("printDateCustom").value = todayDate();
    } else if (mode === "tomorrow") {
      $("printDateCustom").value = tomorrowDate();
    }
    document.querySelectorAll("[data-date-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.dateMode === mode);
    });
    App.updatePreviewMeta();
  }

  function setDateMode(mode) {
    $("printDateMode").value = mode;
    updateDateUi();
  }

  function resolvedPrintDate() {
    const mode = $("printDateMode").value;
    if (mode === "tomorrow") {
      return tomorrowDate();
    }
    if (mode === "custom") {
      return $("printDateCustom").value || todayDate();
    }
    return todayDate();
  }

  function setSettingsOpen(open) {
    $("settingsBar").hidden = !open;
    $("btnSettings").setAttribute("aria-expanded", String(open));
  }

  function setReviewOpen(open) {
    $("reviewModal").hidden = !open;
  }

  function setUsersOpen(open) {
    const modal = $("usersModal");
    if (!modal) {
      return;
    }
    modal.hidden = !open;
  }

  function setCoversOpen(open) {
    const modal = $("coversModal");
    if (!modal) {
      return;
    }
    modal.hidden = !open;
  }

  function clearCustomCoverOnMobile() {
    const App = global.MenuApp;
    if (App.getCoverSelection().mode === COVER_MODE.custom) {
      App.clearBackground();
    }
  }

  const MenuApp = {
    state: MenuAppState,
    STORAGE_KEYS,
    APP_CONFIG,
    IS_ADMIN,
    COVER_MODE,
    RU_HISTORY_LIMIT,
    A4_RATIO,
    PREVIEW_BASE_WIDTH,
    $,
    csrfToken,
    loadStorage,
    saveStorage,
    removeStorage,
    lines,
    toast,
    postJson,
    requestJson,
    debugLog,
    debugWarn,
    menuStats,
    payloadSummary,
    previewSignature,
    actionsSignature,
    saveMenuDraft,
    resetRuHistory,
    pushRuHistory,
    applyRuHistoryState,
    undoRuChange,
    redoRuChange,
    setRuTextValue,
    applyTheme: Theme.applyTheme,
    toggleTheme: Theme.toggleTheme,
    applyDebugLogging,
    applyAlternatePrintMode,
    isAlternatePrintMode,
    updateKcalToggleUi,
    pluralRu,
    updateLineCounter,
    isoDate,
    todayDate,
    tomorrowDate,
    updateDateUi,
    setDateMode,
    resolvedPrintDate,
    setSettingsOpen,
    setReviewOpen,
    setUsersOpen,
    setCoversOpen,
    clearCustomCoverOnMobile,
  };

  global.MenuAppState = MenuAppState;
  global.MenuApp = MenuApp;
})(window);
