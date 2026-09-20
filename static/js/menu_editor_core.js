(function (global) {
  "use strict";

  const C = global.MenuCommon;
  if (!C) {
    throw new Error("MenuCommon must load before MenuEditor");
  }

  const STORAGE_KEYS = {
    editorRows: "menu_editor_rows",
    editorSavedChanges: "menu_editor_saved_changes",
    debugLogging: "menu_debug_logging",
    pageSize: "menu_editor_page_size",
  };

  const EDITOR_CONFIG = JSON.parse(document.getElementById("editorConfig")?.textContent || "{}");
  const TRANSLATION_ENABLED = Boolean(EDITOR_CONFIG.translationEnabled);
  const CAN_EDIT_DATABASE = Boolean(EDITOR_CONFIG.canEditDatabase);
  const PAGE_SIZES = [20, 60, 100];
  const GROUP_OPTIONS = [
    "",
    "Салаты",
    "Закуска",
    "Горячая Закуска",
    "Холодная Закуска",
    "Супы",
    "Горячее",
    "Гарнир",
    "Завтрак",
    "Шашлык",
  ];

  const state = {
    rows: [],
    deletedRowIds: [],
    focusedIds: null,
    focusedNewKeys: null,
    focusedOrder: new Map(),
    focusedActive: false,
    saveInFlight: false,
    saveSeq: 0,
    browseSeq: 0,
    translateAllInFlight: false,
    loadInFlight: false,
    pendingBrowseReload: false,
    searchTimer: null,
    pageSize: 20,
    page: 1,
    total: 0,
    browseActive: false,
  };

  function debugLog(event, data = {}) {
    C.debugLog("[EditorLog]", event, data);
  }

  function status(text) {
    C.$("status").textContent = text;
  }

  function setSaveBusy(busy) {
    state.saveInFlight = busy;
    const button = C.$("btnSave");
    if (button) {
      button.disabled = busy;
      button.textContent = busy ? "Сохранение..." : "Сохранить";
    }
    document.querySelector(".editor-workspace")?.classList.toggle("editor-save-busy", busy);
    const selectors = [
      "#rows input",
      "#rows textarea",
      "#rows select",
      "#rows button",
      "#btnAddRow",
      "#btnTranslateAll",
      "#btnPrevPage",
      "#btnNextPage",
      "#searchInput",
      "#pageSize",
      ".editor-filters input",
      ".editor-filters button",
      ".editor-sidebar input",
      ".editor-sidebar button",
      ".editor-sidebar select",
    ].join(", ");
    document.querySelectorAll(selectors).forEach((el) => {
      el.disabled = busy;
    });
  }

  function authRequiredMessage() {
    return "Сохранение базы доступно только после входа в систему. Авторизуйтесь и повторите попытку.";
  }

  function emptyRow(ru = "") {
    const key = normalizedKey(ru) || `blank-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return {
      ru,
      en: "",
      kcal: "",
      gr: "",
      catRu: "",
      catEn: "",
      _autoTranslated: false,
      _translating: false,
      _isNew: true,
      _dirty: true,
      _focusKey: key,
      _original: null,
    };
  }

  function rowSnapshot(row) {
    return {
      ru: row.ru || "",
      en: row.en || "",
      kcal: row.kcal ?? "",
      gr: row.gr ?? "",
      catRu: row.catRu || "",
      catEn: row.catEn || "",
    };
  }

  function isBlankNewRow(row) {
    const snapshot = rowSnapshot(row);
    return row._isNew && Object.values(snapshot).every((value) => String(value || "").trim() === "");
  }

  function isRowDirty(row) {
    if (row._isNew) {
      return true;
    }
    const original = row._original || {};
    const current = rowSnapshot(row);
    return Object.keys(current).some((key) => current[key] !== (original[key] ?? ""));
  }

  function syncRowDirty(row) {
    row._dirty = isRowDirty(row);
  }

  function loadPageSize() {
    try {
      const raw = Number(C.loadStorage(STORAGE_KEYS.pageSize, "20"));
      return PAGE_SIZES.includes(raw) ? raw : 20;
    } catch {
      return 20;
    }
  }

  function normalizedKey(value) {
    return (value || "").trim().toLowerCase().replace(/ё/g, "е");
  }

  function rowInFocusedSet(row) {
    if (!state.focusedActive) {
      return true;
    }
    if (row.id != null && state.focusedIds && state.focusedIds.has(Number(row.id))) {
      return true;
    }
    if (row._focusKey && state.focusedNewKeys && state.focusedNewKeys.has(row._focusKey)) {
      return true;
    }
    const key = normalizedKey(row.ru);
    return Boolean(key && state.focusedNewKeys && state.focusedNewKeys.has(key));
  }

  function isFocusedMode() {
    return state.focusedActive;
  }

  function searchQueryRaw() {
    const input = C.$("searchRu");
    if (!input) {
      return "";
    }
    return String(input.value || "").trim();
  }

  function filterFlags() {
    return {
      missingKcal: Boolean(C.$("filterMissingKcal")?.checked),
      missingGr: Boolean(C.$("filterMissingGr")?.checked),
      missingGroup: Boolean(C.$("filterMissingGroup")?.checked),
    };
  }

  function hasUnsavedChanges() {
    return changedRows().length > 0 || changedDeleteIds().length > 0;
  }

  function guardUnsaved(actionLabel = "действие") {
    if (!hasUnsavedChanges()) {
      return true;
    }
    C.toast(`Сначала сохраните изменения перед: ${actionLabel}.`);
    return false;
  }

  function pageCount() {
    if (!state.total) {
      return 1;
    }
    return Math.max(1, Math.ceil(state.total / state.pageSize));
  }

  function editableRows() {
    if (isFocusedMode()) {
      return state.rows.filter((row) => rowInFocusedSet(row));
    }
    return state.rows;
  }

  function visibleRows() {
    if (isFocusedMode()) {
      return [...state.rows]
        .filter((row) => rowInFocusedSet(row))
        .sort((left, right) => focusedRank(left) - focusedRank(right));
    }
    return state.rows;
  }

  function changedRows() {
    return editableRows().filter((row) => !isBlankNewRow(row) && (row._isNew || row._dirty));
  }

  function changedDeleteIds() {
    return [...new Set(state.deletedRowIds)];
  }

  function focusedRank(row) {
    if (row.id != null && state.focusedOrder.has(`id:${row.id}`)) {
      return state.focusedOrder.get(`id:${row.id}`);
    }
    if (row._focusKey && state.focusedOrder.has(`new:${row._focusKey}`)) {
      return state.focusedOrder.get(`new:${row._focusKey}`);
    }
    const key = normalizedKey(row.ru);
    return state.focusedOrder.has(key) ? state.focusedOrder.get(key) : Number.MAX_SAFE_INTEGER;
  }

  function statusText(extra = "") {
    if (isFocusedMode()) {
      status(`${extra}${extra ? " | " : ""}К правке: ${visibleRows().length}`);
      return;
    }
    const from = state.total ? (state.page - 1) * state.pageSize + 1 : 0;
    const to = Math.min(state.page * state.pageSize, state.total);
    status(`${extra}${extra ? " | " : ""}Показано: ${from}–${to} из ${state.total}`);
  }

  function applyLayoutMode() {
    const workspace = document.querySelector(".editor-workspace");
    const sidebar = C.$("editorSidebar");
    const focused = isFocusedMode();
    workspace?.classList.toggle("editor-focus-mode", focused);
    if (sidebar) {
      sidebar.hidden = focused;
    }
  }

  function updatePageSizeButtons() {
    document.querySelectorAll(".page-size-btn").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.pageSize) === state.pageSize);
    });
  }

  function updatePagerUi() {
    const pager = C.$("editorPager");
    const sizeControls = C.$("pageSizeControls");
    const showBrowseChrome = state.browseActive && !isFocusedMode();
    if (pager) {
      pager.hidden = !showBrowseChrome;
    }
    if (sizeControls) {
      sizeControls.hidden = !showBrowseChrome;
    }
    applyLayoutMode();
    if (!showBrowseChrome) {
      return;
    }
    const pages = pageCount();
    const label = C.$("pagerLabel");
    if (label) {
      label.textContent = `${state.page} / ${pages}`;
    }
    const prev = C.$("btnPagePrev");
    const next = C.$("btnPageNext");
    if (prev) {
      prev.disabled = state.page <= 1 || state.loadInFlight;
    }
    if (next) {
      next.disabled = state.page >= pages || state.loadInFlight;
    }
    updatePageSizeButtons();
  }

  function buildReadOnlyCell(text) {
    const span = document.createElement("span");
    span.className = "readonly-cell";
    span.textContent = text ?? "";
    return span;
  }

  function buildGroupSelect(row, onManualEdit = null) {
    const select = document.createElement("select");
    select.className = "compact-input";
    GROUP_OPTIONS.forEach((option) => {
      const element = document.createElement("option");
      element.value = option;
      element.textContent = option || "Без группы";
      if (option === (row.catRu || "")) {
        element.selected = true;
      }
      select.appendChild(element);
    });
    select.addEventListener("change", () => {
      row.catRu = select.value;
      row.catEn = "";
      if (typeof onManualEdit === "function") {
        onManualEdit();
      } else {
        syncRowDirty(row);
      }
    });
    return select;
  }

  function markManualEdit(row, tr) {
    row._autoTranslated = false;
    syncRowDirty(row);
    tr.classList.toggle("dirty-row", !row._isNew && Boolean(row._dirty));
    tr.classList.toggle("error-row", !String(row.ru || "").trim());
    tr.classList.toggle("auto-translated-row", false);
    E.updateTranslateAllButton();
  }

  function buildTextInput(row, key, tr, updateRowButtons) {
    const input = document.createElement("input");
    input.className = "compact-input";
    input.value = row[key] ?? "";
    input.type = "text";
    input.addEventListener("input", () => {
      row[key] = input.value;
      markManualEdit(row, tr);
      if (typeof updateRowButtons === "function") {
        updateRowButtons();
      }
    });
    return input;
  }

  function mapDishToRow(dish) {
    return {
      id: dish.id,
      ru: dish.ru || "",
      en: dish.en || "",
      kcal: dish.kcal ?? "",
      gr: dish.gr ?? "",
      catRu: dish.catRu || "",
      catEn: dish.catEn || "",
      _autoTranslated: false,
      _translating: false,
      _isNew: false,
      _dirty: false,
      _original: {
        ru: dish.ru || "",
        en: dish.en || "",
        kcal: dish.kcal ?? "",
        gr: dish.gr ?? "",
        catRu: dish.catRu || "",
        catEn: dish.catEn || "",
      },
    };
  }

  function render() {
    const tbody = C.$("rows");
    tbody.innerHTML = "";

    visibleRows().forEach((row) => {
      const index = state.rows.indexOf(row);
      const tr = document.createElement("tr");
      tr.classList.toggle("new-row", Boolean(row._isNew));
      tr.classList.toggle("dirty-row", !row._isNew && Boolean(row._dirty));
      tr.classList.toggle("error-row", !String(row.ru || "").trim());
      tr.classList.toggle("auto-translated-row", Boolean(row._autoTranslated));

      if (!CAN_EDIT_DATABASE) {
        const ruTd = document.createElement("td");
        ruTd.appendChild(buildReadOnlyCell(row.ru));
        tr.appendChild(ruTd);

        const enTd = document.createElement("td");
        enTd.appendChild(buildReadOnlyCell(row.en));
        tr.appendChild(enTd);

        const numberTd = document.createElement("td");
        numberTd.className = "number-cell";
        const numberGrid = document.createElement("div");
        numberGrid.className = "number-grid";
        ["kcal", "gr"].forEach((key) => {
          numberGrid.appendChild(buildReadOnlyCell(row[key] ?? ""));
        });
        numberTd.appendChild(numberGrid);
        tr.appendChild(numberTd);

        const groupTd = document.createElement("td");
        groupTd.appendChild(buildReadOnlyCell(row.catRu || "Без группы"));
        tr.appendChild(groupTd);

        tbody.appendChild(tr);
        return;
      }

      let translateButton = null;
      const updateRowButtons = () => E.updateTranslateButton(translateButton, row);

      const ruTd = document.createElement("td");
      ruTd.appendChild(buildTextInput(row, "ru", tr, updateRowButtons));
      tr.appendChild(ruTd);

      if (TRANSLATION_ENABLED) {
        const translateTd = document.createElement("td");
        translateTd.className = "translate-cell";
        translateButton = document.createElement("button");
        translateButton.type = "button";
        translateButton.className = "icon-button";
        translateButton.innerHTML = '<span class="ui-icon" data-ui-icon="spell-check"></span>';
        translateButton.addEventListener("click", () => E.translateRows([row]).catch((error) => C.toast(error.message)));
        translateTd.appendChild(translateButton);
        tr.appendChild(translateTd);
        updateRowButtons();
      }

      const enTd = document.createElement("td");
      enTd.appendChild(buildTextInput(row, "en", tr, updateRowButtons));
      tr.appendChild(enTd);

      const numberTd = document.createElement("td");
      numberTd.className = "number-cell";
      const numberGrid = document.createElement("div");
      numberGrid.className = "number-grid";
      ["kcal", "gr"].forEach((key) => {
        const input = document.createElement("input");
        input.className = "compact-input number-field";
        input.value = row[key] ?? "";
        input.type = "number";
        input.addEventListener("input", () => {
          row[key] = input.value;
          markManualEdit(row, tr);
        });
        numberGrid.appendChild(input);
      });
      numberTd.appendChild(numberGrid);
      tr.appendChild(numberTd);

      const groupTd = document.createElement("td");
      groupTd.appendChild(buildGroupSelect(row, () => markManualEdit(row, tr)));
      tr.appendChild(groupTd);

      const action = document.createElement("td");
      action.className = "action-col";
      const del = document.createElement("button");
      del.type = "button";
      del.className = "icon-button danger";
      del.textContent = "×";
      del.title = "Удалить";
      del.setAttribute("aria-label", "Удалить");
      del.addEventListener("click", () => {
        if (state.saveInFlight || state.loadInFlight) {
          return;
        }
        if (row.id) {
          state.deletedRowIds.push(row.id);
        }
        state.rows.splice(index, 1);
        render();
        statusText("Удаление будет применено после сохранения.");
      });
      action.appendChild(del);
      tr.appendChild(action);

      tbody.appendChild(tr);
    });

    global.MenuIcons?.render(tbody);
    E.updateTranslateAllButton();
    updatePagerUi();
    statusText();
  }

  function addRowsFromLines(sourceLines) {
    const existing = new Set(state.rows.map((row) => normalizedKey(row.ru)).filter(Boolean));
    let added = 0;

    for (const line of sourceLines) {
      const ru = (line || "").trim();
      const key = normalizedKey(ru);
      if (!ru || existing.has(key)) {
        continue;
      }
      state.rows.push(emptyRow(ru));
      if (state.focusedActive && state.focusedNewKeys) {
        state.focusedNewKeys.add(key);
      }
      existing.add(key);
      added += 1;
    }

    render();
    return added;
  }

  function addBlankRow() {
    state.rows.unshift(emptyRow(""));
    render();
    statusText("Добавлена пустая строка.");
  }

  function setFocusedRows(items) {
    state.focusedActive = true;
    state.focusedIds = new Set();
    state.focusedNewKeys = new Set();
    state.focusedOrder = new Map();
    items.forEach((item, index) => {
      const ru = String(item.ru || item || "").trim();
      const key = normalizedKey(ru);
      if (!key) {
        return;
      }
      state.focusedNewKeys.add(key);
      state.focusedOrder.set(key, index);
      state.focusedOrder.set(`new:${key}`, index);
    });
  }

  function clearFocusedMode() {
    state.focusedActive = false;
    state.focusedIds = null;
    state.focusedNewKeys = null;
    state.focusedOrder = new Map();
  }

  const E = {
    state,
    STORAGE_KEYS,
    EDITOR_CONFIG,
    TRANSLATION_ENABLED,
    CAN_EDIT_DATABASE,
    PAGE_SIZES,
    GROUP_OPTIONS,
    debugLog,
    status,
    setSaveBusy,
    authRequiredMessage,
    emptyRow,
    rowSnapshot,
    isBlankNewRow,
    isRowDirty,
    syncRowDirty,
    loadPageSize,
    normalizedKey,
    rowInFocusedSet,
    isFocusedMode,
    searchQueryRaw,
    filterFlags,
    hasUnsavedChanges,
    guardUnsaved,
    pageCount,
    editableRows,
    visibleRows,
    changedRows,
    changedDeleteIds,
    focusedRank,
    statusText,
    applyLayoutMode,
    updatePageSizeButtons,
    updatePagerUi,
    buildReadOnlyCell,
    buildGroupSelect,
    markManualEdit,
    buildTextInput,
    mapDishToRow,
    render,
    addRowsFromLines,
    addBlankRow,
    setFocusedRows,
    clearFocusedMode,
  };

  global.MenuEditor = E;

  if (global.MenuTheme) {
    global.MenuTheme.bindThemeButton("btnTheme");
    global.MenuTheme.initFromStorage();
  }
})(window);
