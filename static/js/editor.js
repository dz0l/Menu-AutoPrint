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

const $ = (id) => document.getElementById(id);
const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";

let rows = [];
let deletedRowIds = [];
let focusedIds = null;
let focusedNewKeys = null;
let focusedOrder = new Map();
let focusedActive = false;
let saveInFlight = false;
let translateAllInFlight = false;
let loadInFlight = false;
let pendingBrowseReload = false;
let searchTimer = null;
let pageSize = 20;
let page = 1;
let total = 0;
let browseActive = false;

function debugLog(event, data = {}) {
  try {
    if (localStorage.getItem(STORAGE_KEYS.debugLogging) !== "1") {
      return;
    }
  } catch {
    return;
  }
  console.info("[EditorLog]", event, {
    at: new Date().toISOString(),
    ...data,
  });
}

function status(text) {
  $("status").textContent = text;
}

function toast(message) {
  const box = $("toast");
  if (!box) {
    return;
  }
  box.textContent = message;
  box.hidden = false;
  setTimeout(() => {
    box.hidden = true;
  }, 2600);
}

function setSaveBusy(busy) {
  saveInFlight = busy;
  const button = $("btnSave");
  if (button) {
    button.disabled = busy;
    button.textContent = busy ? "Сохранение..." : "Сохранить";
  }
  document.querySelector(".editor-workspace")?.classList.toggle("editor-save-busy", busy);
  document.querySelectorAll("#rows input, #rows textarea, #rows select, #btnAddRow").forEach((el) => {
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

function loadStorageJson(key, fallback = []) {
  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
  } catch {
    return fallback;
  }
}

function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}

function saveStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function loadPageSize() {
  try {
    const raw = Number(localStorage.getItem(STORAGE_KEYS.pageSize) || "20");
    return PAGE_SIZES.includes(raw) ? raw : 20;
  } catch {
    return 20;
  }
}

function normalizedKey(value) {
  return (value || "").trim().toLowerCase().replace(/ё/g, "е");
}

function rowInFocusedSet(row) {
  if (!focusedActive) {
    return true;
  }
  if (row.id != null && focusedIds && focusedIds.has(Number(row.id))) {
    return true;
  }
  if (row._focusKey && focusedNewKeys && focusedNewKeys.has(row._focusKey)) {
    return true;
  }
  const key = normalizedKey(row.ru);
  return Boolean(key && focusedNewKeys && focusedNewKeys.has(key));
}

function isFocusedMode() {
  return focusedActive;
}

function searchQueryRaw() {
  const input = $("searchRu");
  if (!input) {
    return "";
  }
  return String(input.value || "").trim();
}

function filterFlags() {
  return {
    missingKcal: Boolean($("filterMissingKcal")?.checked),
    missingGr: Boolean($("filterMissingGr")?.checked),
    missingGroup: Boolean($("filterMissingGroup")?.checked),
  };
}

function hasUnsavedChanges() {
  return changedRows().length > 0 || changedDeleteIds().length > 0;
}

function guardUnsaved(actionLabel = "действие") {
  if (!hasUnsavedChanges()) {
    return true;
  }
  toast(`Сначала сохраните изменения перед: ${actionLabel}.`);
  return false;
}

function pageCount() {
  if (!total) {
    return 1;
  }
  return Math.max(1, Math.ceil(total / pageSize));
}

function editableRows() {
  if (isFocusedMode()) {
    return rows.filter((row) => rowInFocusedSet(row));
  }
  return rows;
}

function visibleRows() {
  if (isFocusedMode()) {
    return [...rows]
      .filter((row) => rowInFocusedSet(row))
      .sort((left, right) => focusedRank(left) - focusedRank(right));
  }
  return rows;
}

function changedRows() {
  return editableRows().filter((row) => !isBlankNewRow(row) && (row._isNew || row._dirty));
}

function changedDeleteIds() {
  return [...new Set(deletedRowIds)];
}

function focusedRank(row) {
  if (row.id != null && focusedOrder.has(`id:${row.id}`)) {
    return focusedOrder.get(`id:${row.id}`);
  }
  if (row._focusKey && focusedOrder.has(`new:${row._focusKey}`)) {
    return focusedOrder.get(`new:${row._focusKey}`);
  }
  const key = normalizedKey(row.ru);
  return focusedOrder.has(key) ? focusedOrder.get(key) : Number.MAX_SAFE_INTEGER;
}

function statusText(extra = "") {
  if (isFocusedMode()) {
    status(`${extra}${extra ? " | " : ""}К правке: ${visibleRows().length}`);
    return;
  }
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, total);
  status(`${extra}${extra ? " | " : ""}Показано: ${from}–${to} из ${total}`);
}

function applyLayoutMode() {
  const workspace = document.querySelector(".editor-workspace");
  const sidebar = $("editorSidebar");
  const focused = isFocusedMode();
  workspace?.classList.toggle("editor-focus-mode", focused);
  if (sidebar) {
    sidebar.hidden = focused;
  }
}

function updatePageSizeButtons() {
  document.querySelectorAll(".page-size-btn").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.pageSize) === pageSize);
  });
}

function updatePagerUi() {
  const pager = $("editorPager");
  const sizeControls = $("pageSizeControls");
  const showBrowseChrome = browseActive && !isFocusedMode();
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
  const label = $("pagerLabel");
  if (label) {
    label.textContent = `${page} / ${pages}`;
  }
  const prev = $("btnPagePrev");
  const next = $("btnPageNext");
  if (prev) {
    prev.disabled = page <= 1 || loadInFlight;
  }
  if (next) {
    next.disabled = page >= pages || loadInFlight;
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
  updateTranslateAllButton();
}

function canTranslateRow(row) {
  return (
    TRANSLATION_ENABLED &&
    !translateAllInFlight &&
    !row._translating &&
    String(row.ru || "").trim() &&
    !String(row.en || "").trim()
  );
}

function translatableVisibleRows() {
  return visibleRows().filter((row) => canTranslateRow(row));
}

function updateTranslateAllButton() {
  const button = $("btnTranslateAll");
  if (!button) {
    return;
  }
  const count = translatableVisibleRows().length;
  button.disabled = translateAllInFlight || count === 0;
  button.title = count ? `Перевести пустые EN: ${count}` : "Нет строк для перевода";
  button.setAttribute("aria-label", button.title);
}

function updateTranslateButton(button, row) {
  if (!button) {
    return;
  }
  button.disabled = !canTranslateRow(row);
  button.title = row._translating ? "Перевод..." : "Перевести RU в EN";
  button.setAttribute("aria-label", button.title);
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

async function requestTranslation(texts) {
  const res = await fetch("/api/dishes/translate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify({texts}),
  });
  const data = await res.json();
  if (!res.ok) {
    const providerStatus = data.provider_status ? ` (${data.provider_status})` : "";
    throw new Error(`${data.error || "Ошибка перевода"}${providerStatus}`);
  }
  return data.translations || [];
}

async function translateRows(targetRows, reason = "row") {
  if (!TRANSLATION_ENABLED) {
    return;
  }
  const candidates = targetRows.filter((row) => canTranslateRow(row));
  if (!candidates.length) {
    toast("Нет строк для перевода.");
    return;
  }
  if (reason === "bulk") {
    translateAllInFlight = true;
  }
  candidates.forEach((row) => {
    row._translating = true;
    row._translateRu = String(row.ru || "").trim();
  });
  render();
  status(`Перевод: ${candidates.length} строк...`);
  debugLog("translate:start", {reason, count: candidates.length});

  let translated = 0;
  try {
    for (let start = 0; start < candidates.length; start += 50) {
      const chunk = candidates.slice(start, start + 50);
      const translations = await requestTranslation(chunk.map((row) => row.ru));
      translations.forEach((value, index) => {
        const row = chunk[index];
        if (!row || !value) {
          return;
        }
        const currentRu = String(row.ru || "").trim();
        const requestedRu = String(chunk[index]._translateRu || currentRu).trim();
        if (currentRu !== requestedRu) {
          return;
        }
        if (row.en && row.en !== (row._original?.en || "") && !row._autoTranslated) {
          return;
        }
        row.en = value;
        row._autoTranslated = true;
        row._dirty = isRowDirty(row);
        translated += 1;
      });
    }
    statusText(`Переведено: ${translated}`);
    toast(`Переведено: ${translated}`);
    debugLog("translate:done", {reason, count: translated});
  } catch (error) {
    status(`Ошибка перевода: ${error.message}`);
    toast(`Ошибка перевода: ${error.message}`);
    debugLog("translate:error", {reason, error: error.message, translated});
  } finally {
    candidates.forEach((row) => {
      row._translating = false;
    });
    translateAllInFlight = false;
    render();
  }
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
  const tbody = $("rows");
  tbody.innerHTML = "";

  visibleRows().forEach((row) => {
    const index = rows.indexOf(row);
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
    const updateRowButtons = () => updateTranslateButton(translateButton, row);

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
      translateButton.addEventListener("click", () => translateRows([row]).catch((error) => toast(error.message)));
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
      if (row.id) {
        deletedRowIds.push(row.id);
      }
      rows.splice(index, 1);
      render();
      statusText("Удаление будет применено после сохранения.");
    });
    action.appendChild(del);
    tr.appendChild(action);

    tbody.appendChild(tr);
  });

  window.MenuIcons?.render(tbody);
  updateTranslateAllButton();
  updatePagerUi();
  statusText();
}

async function fetchDishPage({q = "", names = "", targetPage = page, size = pageSize, applyFilters = true} = {}) {
  const offset = Math.max(0, (targetPage - 1) * size);
  const params = new URLSearchParams({
    limit: String(size),
    offset: String(offset),
  });
  if (q) {
    params.set("q", q);
  }
  if (names) {
    params.set("names", names);
  }
  if (applyFilters) {
    const flags = filterFlags();
    if (flags.missingKcal) {
      params.set("missing_kcal", "1");
    }
    if (flags.missingGr) {
      params.set("missing_gr", "1");
    }
    if (flags.missingGroup) {
      params.set("missing_group", "1");
    }
  }
  const res = await fetch(`/api/dishes/?${params.toString()}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Ошибка загрузки базы");
  }
  return data;
}

async function loadBrowsePage({resetPage = false} = {}) {
  if (loadInFlight) {
    pendingBrowseReload = true;
    return;
  }
  if (resetPage) {
    page = 1;
  }
  loadInFlight = true;
  browseActive = true;
  clearFocusedMode();
  updatePagerUi();
  status("Загрузка базы...");
  try {
    const data = await fetchDishPage({
      q: searchQueryRaw(),
      targetPage: page,
      size: pageSize,
    });
    total = Number(data.total || 0);
    pageSize = Number(data.limit || pageSize);
    const offset = Number(data.offset || 0);
    page = total ? Math.floor(offset / pageSize) + 1 : 1;
    const preservedNew = CAN_EDIT_DATABASE ? rows.filter((row) => row._isNew) : [];
    rows = (data.dishes || []).map(mapDishToRow);
    if (preservedNew.length) {
      rows = [...preservedNew, ...rows];
    }
    render();
  } catch (error) {
    toast(error.message || "Ошибка загрузки базы");
    status(error.message || "Ошибка загрузки базы");
  } finally {
    loadInFlight = false;
    updatePagerUi();
    if (pendingBrowseReload) {
      pendingBrowseReload = false;
      loadBrowsePage({resetPage: true}).catch((error) => toast(error.message));
    }
  }
}

async function loadFocusedRows(items) {
  const names = [...new Set(items.map((item) => String(item.ru || item || "").trim()).filter(Boolean))];
  if (!names.length) {
    rows = [];
    total = 0;
    browseActive = false;
    render();
    return;
  }
  loadInFlight = true;
  browseActive = false;
  status("Загрузка выбранных блюд...");
  try {
    const data = await fetchDishPage({
      names: names.join("|"),
      targetPage: 1,
      size: Math.min(100, Math.max(names.length, 20)),
      applyFilters: false,
    });
    total = Number(data.total || 0);
    rows = (data.dishes || []).map(mapDishToRow);
    focusedIds = new Set(rows.map((row) => Number(row.id)).filter(Boolean));
    rows.forEach((row, index) => {
      focusedOrder.set(`id:${row.id}`, index);
      const key = normalizedKey(row.ru);
      if (key && focusedNewKeys) {
        focusedNewKeys.delete(key);
      }
    });
    if (names.length > 100) {
      toast(`Загружено первых ${rows.length} из ${names.length}. Остальные откройте из базы отдельно.`);
    }
    render();
  } catch (error) {
    toast(error.message || "Ошибка загрузки");
    status(error.message || "Ошибка загрузки");
  } finally {
    loadInFlight = false;
    updatePagerUi();
  }
}

function addRowsFromLines(sourceLines) {
  const existing = new Set(rows.map((row) => normalizedKey(row.ru)).filter(Boolean));
  let added = 0;

  for (const line of sourceLines) {
    const ru = (line || "").trim();
    const key = normalizedKey(ru);
    if (!ru || existing.has(key)) {
      continue;
    }
    rows.push(emptyRow(ru));
    if (focusedActive && focusedNewKeys) {
      focusedNewKeys.add(key);
    }
    existing.add(key);
    added += 1;
  }

  render();
  return added;
}

function addBlankRow() {
  rows.unshift(emptyRow(""));
  render();
  statusText("Добавлена пустая строка.");
}

function setFocusedRows(items) {
  focusedActive = true;
  focusedIds = new Set();
  focusedNewKeys = new Set();
  focusedOrder = new Map();
  items.forEach((item, index) => {
    const ru = String(item.ru || item || "").trim();
    const key = normalizedKey(ru);
    if (!key) {
      return;
    }
    focusedNewKeys.add(key);
    focusedOrder.set(key, index);
    focusedOrder.set(`new:${key}`, index);
  });
}

function clearFocusedMode() {
  focusedActive = false;
  focusedIds = null;
  focusedNewKeys = null;
  focusedOrder = new Map();
}

function scheduleBrowseReload() {
  if (searchTimer) {
    clearTimeout(searchTimer);
  }
  searchTimer = setTimeout(() => {
    if (!guardUnsaved("обновление списка")) {
      return;
    }
    loadBrowsePage({resetPage: true}).catch((error) => toast(error.message));
  }, 280);
}

$("btnAddRow")?.addEventListener("click", () => {
  if (!CAN_EDIT_DATABASE) {
    return;
  }
  addBlankRow();
});

$("searchRu")?.addEventListener("input", () => {
  if (isFocusedMode()) {
    return;
  }
  scheduleBrowseReload();
});

["filterMissingKcal", "filterMissingGr", "filterMissingGroup"].forEach((id) => {
  $(id)?.addEventListener("change", () => {
    if (isFocusedMode()) {
      return;
    }
    if (!guardUnsaved("смену фильтра")) {
      const box = $(id);
      if (box) {
        box.checked = !box.checked;
      }
      return;
    }
    loadBrowsePage({resetPage: true}).catch((error) => toast(error.message));
  });
});

$("btnResetFilters")?.addEventListener("click", async () => {
  if (!guardUnsaved("сброс фильтров")) {
    return;
  }
  if ($("searchRu")) {
    $("searchRu").value = "";
  }
  ["filterMissingKcal", "filterMissingGr", "filterMissingGroup"].forEach((id) => {
    if ($(id)) {
      $(id).checked = false;
    }
  });
  page = 1;
  await loadBrowsePage({resetPage: true});
});

$("btnPagePrev")?.addEventListener("click", async () => {
  if (page <= 1 || !guardUnsaved("переход на страницу")) {
    return;
  }
  page -= 1;
  await loadBrowsePage();
});

$("btnPageNext")?.addEventListener("click", async () => {
  if (page >= pageCount() || !guardUnsaved("переход на страницу")) {
    return;
  }
  page += 1;
  await loadBrowsePage();
});

document.querySelectorAll(".page-size-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const nextSize = Number(button.dataset.pageSize);
    if (!PAGE_SIZES.includes(nextSize) || nextSize === pageSize) {
      return;
    }
    if (!guardUnsaved("смену числа строк")) {
      return;
    }
    pageSize = nextSize;
    saveStorage(STORAGE_KEYS.pageSize, String(pageSize));
    updatePageSizeButtons();
    await loadBrowsePage({resetPage: true});
  });
});

if ($("btnTranslateAll")) {
  $("btnTranslateAll").addEventListener("click", () => {
    translateRows(translatableVisibleRows(), "bulk").catch((error) => toast(error.message));
  });
}

$("btnSave")?.addEventListener("click", async () => {
  if (!CAN_EDIT_DATABASE || saveInFlight) {
    return;
  }

  const payloadRows = changedRows();
  const deleteIds = changedDeleteIds();
  if (!payloadRows.length && !deleteIds.length) {
    status("Нет изменений для сохранения.");
    toast("Нет изменений для сохранения.");
    return;
  }

  setSaveBusy(true);
  status(`Пожалуйста, подождите... идёт сохранение (${payloadRows.length}), удаление (${deleteIds.length}).`);
  toast("Пожалуйста, подождите... идёт сохранение.");
  try {
    const res = await fetch("/api/dishes/bulk-upsert", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({rows: payloadRows, delete_ids: deleteIds}),
    });
    const data = await res.json();
    if (!res.ok) {
      const message =
        res.status === 403
          ? authRequiredMessage()
          : data.error || "Ошибка сохранения";
      status(message);
      toast(message);
      return;
    }

    const errorsCount = data.errors?.length || 0;
    status(`Создано: ${data.created}, обновлено: ${data.updated}, удалено: ${data.deleted || 0}, ошибок: ${errorsCount}`);
    (data.row_results || []).forEach((item) => {
      const row = payloadRows[item.index];
      if (!row) {
        return;
      }
      row.id = item.id;
      row._isNew = false;
      row._dirty = false;
      row._autoTranslated = false;
      row._original = rowSnapshot(row);
      if (focusedActive) {
        focusedIds = focusedIds || new Set();
        focusedIds.add(Number(item.id));
        if (row._focusKey && focusedNewKeys) {
          focusedNewKeys.delete(row._focusKey);
        }
      }
    });
    const deletedOk = new Set(data.deleted_ids || []);
    deletedRowIds = deletedRowIds.filter((id) => !deletedOk.has(id));
    if (errorsCount > 0) {
      toast("Сохранение завершилось с ошибками. Проверьте строки и повторите.");
      render();
      return;
    }
    if ((data.created || 0) > 0 || (data.updated || 0) > 0 || (data.deleted || 0) > 0) {
      saveStorage(STORAGE_KEYS.editorSavedChanges, "1");
    }
    location.href = "/";
  } catch (error) {
    const message = error?.message || "Ошибка сохранения";
    status(message);
    toast(message);
  } finally {
    setSaveBusy(false);
  }
});

window.addEventListener("load", async () => {
  pageSize = loadPageSize();
  updatePageSizeButtons();

  const incomingRaw = loadStorageJson(STORAGE_KEYS.editorRows);
  const incoming = Array.isArray(incomingRaw) ? incomingRaw.filter((item) => item && item.ru) : [];
  removeStorage(STORAGE_KEYS.editorRows);

  if (incoming.length && CAN_EDIT_DATABASE) {
    const missing = incoming.filter((item) => item.mode === "missing").map((item) => item.ru);
    const hasFixRows = incoming.some((item) => item.mode === "fix");
    setFocusedRows(incoming);
    browseActive = false;
    applyLayoutMode();

    if (hasFixRows) {
      await loadFocusedRows(incoming);
    } else {
      rows = [];
      total = 0;
    }
    const added = addRowsFromLines(missing);
    statusText(`К редактированию: ${incoming.length}, новых строк: ${added}`);
    return;
  }

  clearFocusedMode();
  await loadBrowsePage({resetPage: true});
  if (!CAN_EDIT_DATABASE) {
    status("Просмотр базы. Редактирование доступно только администратору. Можно экспортировать CSV.");
  }
});
