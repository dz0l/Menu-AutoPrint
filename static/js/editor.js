const STORAGE_KEYS = {
  missing: "menu_missing_ru",
  fix: "menu_fix_ru",
};

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
let fullDatabaseLoaded = false;
let focusedRuSet = null;
let saveInFlight = false;

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

function emptyRow(ru = "") {
  return {
    ru,
    en: "",
    kcal: "",
    gr: "",
    catRu: "",
    catEn: "",
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

function normalizedKey(value) {
  return (value || "").trim().toLowerCase();
}

function allTypedLines(includeDraft = false) {
  const raw = $("newDishes").value.replace(/\r/g, "");
  const source = raw.split("\n").map((line) => line.trim());
  const hasTrailingBreak = raw.endsWith("\n");

  return source.filter((line, index) => {
    if (!line) {
      return false;
    }
    if (includeDraft || hasTrailingBreak) {
      return true;
    }
    return index < source.length - 1;
  });
}

function visibleRows() {
  let current = $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
  if (focusedRuSet && focusedRuSet.size) {
    current = current.filter((row) => focusedRuSet.has(normalizedKey(row.ru)));
  }
  return current;
}

function editableRows() {
  if (focusedRuSet && focusedRuSet.size) {
    return rows.filter((row) => focusedRuSet.has(normalizedKey(row.ru)));
  }
  return $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
}

function changedRows() {
  return editableRows().filter((row) => row._isNew || row._dirty);
}

function statusText(extra = "") {
  const shown = visibleRows().length;
  const total = rows.length;
  status(`${extra}${extra ? " | " : ""}Показано: ${shown}, загружено: ${total}`);
}

function buildGroupSelect(row) {
  const select = document.createElement("select");
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
    syncRowDirty(row);
  });
  return select;
}

function render() {
  const tbody = $("rows");
  tbody.innerHTML = "";

  visibleRows().forEach((row) => {
    const index = rows.indexOf(row);
    const tr = document.createElement("tr");

    ["ru", "en", "kcal", "gr"].forEach((key) => {
      const td = document.createElement("td");
      if (key === "kcal" || key === "gr") {
        td.className = "small";
      }
      const input = document.createElement("input");
      input.value = row[key] ?? "";
      input.type = key === "kcal" || key === "gr" ? "number" : "text";
      input.addEventListener("input", () => {
        row[key] = input.value;
        syncRowDirty(row);
      });
      td.appendChild(input);
      tr.appendChild(td);
    });

    const groupTd = document.createElement("td");
    groupTd.appendChild(buildGroupSelect(row));
    tr.appendChild(groupTd);

    const action = document.createElement("td");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Удалить";
    del.addEventListener("click", async () => {
      if (row.id) {
        await fetch(`/api/dishes/${row.id}`, {
          method: "DELETE",
          headers: {"X-CSRFToken": csrfToken()},
        });
      }
      rows.splice(index, 1);
      render();
      statusText();
    });
    action.appendChild(del);
    tr.appendChild(action);

    tbody.appendChild(tr);
  });

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

function addLines(sourceLines) {
  const existing = new Set(rows.map((row) => normalizedKey(row.ru)));
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

function syncRowsFromTextarea(includeDraft = false) {
  const added = addLines(allTypedLines(includeDraft));
  if (added > 0) {
    statusText(`Добавлено новых строк: ${added}`);
  }
}

async function ensureFullDatabaseLoaded() {
  if (fullDatabaseLoaded) {
    return;
  }
  status("Загрузка базы...");
  await loadRows();
}

$("onlyNew").addEventListener("change", async () => {
  if (!$("onlyNew").checked) {
    await ensureFullDatabaseLoaded();
  }
  render();
});

$("newDishes").addEventListener("input", () => {
  syncRowsFromTextarea(false);
});

$("newDishes").addEventListener("blur", () => {
  syncRowsFromTextarea(true);
});

$("btnSave").addEventListener("click", async () => {
  if (saveInFlight) {
    return;
  }

  const payloadRows = changedRows();
  if (!payloadRows.length) {
    status("Нет изменений для сохранения.");
    toast("Нет изменений для сохранения.");
    return;
  }

  setSaveBusy(true);
  status(`Пожалуйста, подождите... идёт сохранение (${payloadRows.length}).`);
  toast("Пожалуйста, подождите... идёт сохранение.");
  try {
    const res = await fetch("/api/dishes/bulk-upsert", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({rows: payloadRows}),
    });
    const data = await res.json();
    if (!res.ok) {
      status(data.error || "Ошибка сохранения");
      toast(data.error || "Ошибка сохранения");
      return;
    }

    status(`Создано: ${data.created}, обновлено: ${data.updated}, ошибок: ${data.errors.length}`);
    payloadRows.forEach((row) => {
      row._isNew = false;
      row._dirty = false;
      row._original = rowSnapshot(row);
    });

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
  const missingRaw = loadStorageJson(STORAGE_KEYS.missing);
  const fixRaw = loadStorageJson(STORAGE_KEYS.fix);
  const missing = Array.isArray(missingRaw) ? missingRaw : [];
  const fix = Array.isArray(fixRaw) ? fixRaw : [];

  removeStorage(STORAGE_KEYS.missing);
  removeStorage(STORAGE_KEYS.fix);

  $("onlyNew").checked = true;

  if (missing.length) {
    focusedRuSet = null;
    $("newDishes").value = missing.join("\n");
    syncRowsFromTextarea(true);
    statusText(`Новых блюд: ${missing.length}`);
    return;
  }

  if (fix.length) {
    focusedRuSet = new Set(fix.map((item) => normalizedKey(item)));
    $("onlyNew").checked = false;
    $("newDishes").value = fix.join("\n");
    await loadRows();
    statusText(`Неполных блюд: ${fix.length}`);
    return;
  }

  focusedRuSet = null;
  render();
  status("Быстрый режим: полная база скрыта. Снимите галочку, чтобы загрузить все блюда.");
});
