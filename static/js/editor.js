const STORAGE_KEYS = {
  editorRows: "menu_editor_rows",
  editorSavedChanges: "menu_editor_saved_changes",
  debugLogging: "menu_debug_logging",
};

const EDITOR_CONFIG = JSON.parse(document.getElementById("editorConfig")?.textContent || "{}");
const TRANSLATION_ENABLED = Boolean(EDITOR_CONFIG.translationEnabled);
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
let fullDatabaseLoaded = false;
let focusedRuSet = null;
let focusedOrder = new Map();
let saveInFlight = false;
let translateAllInFlight = false;
let sortState = {key: "", direction: "asc"};

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
  if (!button) {
    return;
  }
  button.disabled = busy;
  button.textContent = busy ? "Сохранение..." : "Сохранить";
}

function authRequiredMessage() {
  return "Сохранение базы доступно только после входа в систему. Авторизуйтесь и повторите попытку.";
}

function emptyRow(ru = "") {
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

function normalizedKey(value) {
  return (value || "").trim().toLowerCase().replace(/ё/g, "е");
}

function rowInFocusedSet(row) {
  if (!focusedRuSet || !focusedRuSet.size) {
    return false;
  }
  return row._isNew || focusedRuSet.has(normalizedKey(row.ru));
}

function groupRank(value) {
  const index = GROUP_OPTIONS.indexOf(value || "");
  return index === -1 ? GROUP_OPTIONS.length : index;
}

function searchQuery() {
  const input = $("searchRu");
  return input && !$("onlyNew").checked ? normalizedKey(input.value) : "";
}

function visibleRows() {
  let current = rows;
  if (focusedRuSet && focusedRuSet.size) {
    current = current.filter((row) => rowInFocusedSet(row));
  } else if ($("onlyNew").checked) {
    current = current.filter((row) => row._isNew);
  }

  const query = searchQuery();
  if (query) {
    current = current.filter((row) => normalizedKey(row.ru).includes(query));
  }
  return sortRowsForDisplay(current);
}

function editableRows() {
  if (focusedRuSet && focusedRuSet.size) {
    return rows.filter((row) => rowInFocusedSet(row));
  }
  return $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
}

function changedRows() {
  return editableRows().filter((row) => !isBlankNewRow(row) && (row._isNew || row._dirty));
}

function changedDeleteIds() {
  return [...new Set(deletedRowIds)];
}

function statusText(extra = "") {
  const shown = visibleRows().length;
  const total = rows.length;
  status(`${extra}${extra ? " | " : ""}Показано: ${shown}, загружено: ${total}`);
}

function focusedRank(row) {
  const key = normalizedKey(row.ru);
  return focusedOrder.has(key) ? focusedOrder.get(key) : Number.MAX_SAFE_INTEGER;
}

function sortRowsForDisplay(sourceRows) {
  if (!sortState.key) {
    if (focusedRuSet && focusedRuSet.size) {
      return [...sourceRows].sort((left, right) => focusedRank(left) - focusedRank(right));
    }
    return sourceRows;
  }

  const factor = sortState.direction === "desc" ? -1 : 1;
  return [...sourceRows].sort((left, right) => {
    let result = 0;
    if (sortState.key === "catRu") {
      result = groupRank(left.catRu) - groupRank(right.catRu);
      if (result === 0) {
        result = String(left.ru || "").localeCompare(String(right.ru || ""), "ru");
      }
    } else {
      const locale = sortState.key === "en" ? "en" : "ru";
      result = String(left[sortState.key] || "").localeCompare(String(right[sortState.key] || ""), locale);
    }
    return result * factor;
  });
}

function toggleSort(key) {
  if (sortState.key === key) {
    sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
  } else {
    sortState = {key, direction: "asc"};
  }
  updateSortButtons();
  render();
}

function updateSortButtons() {
  document.querySelectorAll(".table-sort").forEach((button) => {
    const active = button.dataset.sort === sortState.key;
    button.classList.toggle("active", active);
    const base = button.dataset.sort === "catRu" ? "Группа RU" : button.dataset.sort.toUpperCase();
    button.textContent = active ? `${base} ${sortState.direction === "asc" ? "↑" : "↓"}` : base;
  });
}

function updateSearchVisibility() {
  const input = $("searchRu");
  if (!input) {
    return;
  }
  input.hidden = $("onlyNew").checked;
  if (input.hidden) {
    input.value = "";
  }
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
    throw new Error(data.error || "Ошибка перевода");
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
  statusText();
}

function mergeRows(fetchedRows) {
  const preservedNewRows = rows.filter((row) => row._isNew);
  const existing = new Set(fetchedRows.map((row) => normalizedKey(row.ru)));

  for (const row of preservedNewRows) {
    const key = normalizedKey(row.ru);
    if (!key || existing.has(key)) {
      continue;
    }
    fetchedRows.push(row);
    existing.add(key);
  }

  rows = fetchedRows;
}

async function loadRows() {
  const res = await fetch("/api/dishes/?limit=5000");
  const data = await res.json();
  const fetchedRows = (data.dishes || []).map((dish) => ({
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
  }));
  mergeRows(fetchedRows);
  fullDatabaseLoaded = true;
  render();
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
    existing.add(key);
    added += 1;
  }

  render();
  return added;
}

function addBlankRow() {
  rows.push(emptyRow(""));
  render();
  statusText("Добавлена пустая строка.");
}

async function ensureFullDatabaseLoaded() {
  if (fullDatabaseLoaded) {
    return;
  }
  status("Загрузка базы...");
  await loadRows();
}

function setFocusedRows(items) {
  focusedRuSet = new Set();
  focusedOrder = new Map();
  items.forEach((item, index) => {
    const key = normalizedKey(item.ru || item);
    if (!key || focusedRuSet.has(key)) {
      return;
    }
    focusedRuSet.add(key);
    focusedOrder.set(key, index);
  });
}

$("onlyNew").addEventListener("change", async () => {
  if (!$("onlyNew").checked) {
    await ensureFullDatabaseLoaded();
  }
  updateSearchVisibility();
  render();
});

$("btnAddRow").addEventListener("click", () => {
  addBlankRow();
});

$("searchRu").addEventListener("input", render);

$("btnResetFilters").addEventListener("click", () => {
  $("searchRu").value = "";
  sortState = {key: "", direction: "asc"};
  updateSortButtons();
  render();
});

document.querySelectorAll(".table-sort").forEach((button) => {
  button.addEventListener("click", () => toggleSort(button.dataset.sort));
});

if ($("btnTranslateAll")) {
  $("btnTranslateAll").addEventListener("click", () => {
    translateRows(translatableVisibleRows(), "bulk").catch((error) => toast(error.message));
  });
}

$("btnSave").addEventListener("click", async () => {
  if (saveInFlight) {
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
    deletedRowIds = [];
    if (errorsCount > 0) {
      toast("Сохранение завершилось с ошибками. Проверьте строки и повторите.");
      return;
    }
    payloadRows.forEach((row) => {
      row._isNew = false;
      row._dirty = false;
      row._autoTranslated = false;
      row._original = rowSnapshot(row);
    });
    if ((data.created || 0) > 0 || (data.updated || 0) > 0) {
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
  const incomingRaw = loadStorageJson(STORAGE_KEYS.editorRows);
  const incoming = Array.isArray(incomingRaw) ? incomingRaw.filter((item) => item && item.ru) : [];
  removeStorage(STORAGE_KEYS.editorRows);

  $("onlyNew").checked = true;
  updateSearchVisibility();
  updateSortButtons();

  if (incoming.length) {
    const missing = incoming.filter((item) => item.mode === "missing").map((item) => item.ru);
    const hasFixRows = incoming.some((item) => item.mode === "fix");
    setFocusedRows(incoming);
    $("onlyNew").checked = !hasFixRows;
    updateSearchVisibility();

    if (hasFixRows) {
      await loadRows();
    }
    const added = addRowsFromLines(missing);
    statusText(`К редактированию: ${incoming.length}, новых строк: ${added}`);
    return;
  }

  focusedRuSet = null;
  focusedOrder = new Map();
  render();
  status("Быстрый режим: нажмите + для нового блюда или снимите галочку, чтобы загрузить всю базу.");
});
