const STORAGE_KEYS = {
  missing: "menu_missing_ru",
  fix: "menu_fix_ru",
};

const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
const $ = (id) => document.getElementById(id);

let rows = [];
let fullDatabaseLoaded = false;

function status(text) {
  $("status").textContent = text;
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
  };
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

function visibleRows() {
  return $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
}

function statusText(extra = "") {
  const shown = visibleRows().length;
  const total = rows.length;
  status(`${extra}${extra ? " | " : ""}Показано: ${shown}, загружено: ${total}`);
}

function updateAddButtonState() {
  $("btnAddLines").disabled = normalizedNewDishLines().length === 0;
}

function normalizedNewDishLines() {
  return $("newDishes")
    .value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function render() {
  const tbody = $("rows");
  tbody.innerHTML = "";

  visibleRows().forEach((row) => {
    const index = rows.indexOf(row);
    const tr = document.createElement("tr");
    for (const key of ["ru", "en", "kcal", "gr", "catRu", "catEn"]) {
      const td = document.createElement("td");
      if (key === "kcal" || key === "gr") {
        td.className = "small";
      }

      const input = document.createElement("input");
      input.value = row[key] ?? "";
      input.type = key === "kcal" || key === "gr" ? "number" : "text";
      input.addEventListener("input", () => {
        row[key] = input.value;
      });
      td.appendChild(input);
      tr.appendChild(td);
    }

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
  const existing = new Set(fetchedRows.map((row) => (row.ru || "").trim().toLowerCase()));

  for (const row of preservedNewRows) {
    const key = (row.ru || "").trim().toLowerCase();
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
  }));
  mergeRows(fetchedRows);
  fullDatabaseLoaded = true;
  render();
}

function addLines(sourceLines) {
  const existing = new Set(rows.map((row) => (row.ru || "").trim().toLowerCase()));
  let added = 0;

  for (const line of sourceLines) {
    const ru = (line || "").trim();
    const key = ru.toLowerCase();
    if (!ru || existing.has(key)) {
      continue;
    }
    rows.push(emptyRow(ru));
    existing.add(key);
    added += 1;
  }

  render();
  updateAddButtonState();
  return added;
}

function syncRowsFromTextarea() {
  const added = addLines(normalizedNewDishLines());
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

$("btnReload").addEventListener("click", async () => {
  await ensureFullDatabaseLoaded();
  statusText("База обновлена");
});

$("newDishes").addEventListener("input", () => {
  syncRowsFromTextarea();
  updateAddButtonState();
});

$("btnAddLines").addEventListener("click", () => {
  const added = addLines(normalizedNewDishLines());
  statusText(`Добавлено новых строк: ${added}`);
});

$("btnSave").addEventListener("click", async () => {
  const payloadRows = $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
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
    return;
  }

  status(`Создано: ${data.created}, обновлено: ${data.updated}, ошибок: ${data.errors.length}`);
  rows.forEach((row) => {
    row._isNew = false;
  });

  if (fullDatabaseLoaded) {
    await loadRows();
  } else {
    render();
  }
});

$("btnImport").addEventListener("click", async () => {
  const file = $("csvFile").files[0];
  if (!file) {
    return;
  }

  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/dishes/import.csv", {
    method: "POST",
    headers: {"X-CSRFToken": csrfToken()},
    body: form,
  });
  const data = await res.json();
  status(`Импорт: создано ${data.created}, обновлено ${data.updated}, ошибок ${data.errors.length}`);
  await loadRows();
});

window.addEventListener("load", async () => {
  const missingRaw = loadStorageJson(STORAGE_KEYS.missing);
  const fixRaw = loadStorageJson(STORAGE_KEYS.fix);
  const missing = Array.isArray(missingRaw) ? missingRaw : [];
  const fix = Array.isArray(fixRaw) ? fixRaw : [];
  removeStorage(STORAGE_KEYS.missing);
  removeStorage(STORAGE_KEYS.fix);

  $("onlyNew").checked = true;
  updateAddButtonState();

  if (missing.length) {
    $("newDishes").value = missing.join("\n");
    syncRowsFromTextarea();
    statusText(`Новых блюд: ${missing.length}`);
    return;
  }

  if (fix.length) {
    $("onlyNew").checked = false;
    await loadRows();
    statusText(`Неполных блюд: ${fix.length}`);
    return;
  }

  render();
  status("Быстрый режим: полная база скрыта. Снимите галочку, чтобы загрузить все блюда.");
});
