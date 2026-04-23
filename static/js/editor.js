const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
const $ = (id) => document.getElementById(id);

let rows = [];
let fullDatabaseLoaded = false;

function status(text) {
  $("status").textContent = text;
}

function emptyRow(ru = "") {
  return {ru, en: "", kcal: "", gr: "", catRu: "", catEn: "", _isNew: true};
}

function visibleRows() {
  return $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
}

function render() {
  const tbody = $("rows");
  tbody.innerHTML = "";
  visibleRows().forEach((row) => {
    const index = rows.indexOf(row);
    const tr = document.createElement("tr");
    for (const key of ["ru", "en", "kcal", "gr", "catRu", "catEn"]) {
      const td = document.createElement("td");
      if (key === "kcal" || key === "gr") td.className = "small";
      const input = document.createElement("input");
      input.value = row[key] ?? "";
      input.type = key === "kcal" || key === "gr" ? "number" : "text";
      input.addEventListener("input", () => { row[key] = input.value; });
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
        await fetch(`/api/dishes/${row.id}`, {method: "DELETE", headers: {"X-CSRFToken": csrfToken()}});
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

function statusText(extra = "") {
  const shown = visibleRows().length;
  const total = rows.length;
  status(`${extra}${extra ? " · " : ""}Показано: ${shown}, загружено: ${total}`);
}

async function loadRows() {
  const res = await fetch("/api/dishes?limit=5000");
  const data = await res.json();
  rows = (data.dishes || []).map((d) => ({
    id: d.id,
    ru: d.ru || "",
    en: d.en || "",
    kcal: d.kcal ?? "",
    gr: d.gr ?? "",
    catRu: d.catRu || "",
    catEn: d.catEn || "",
    _isNew: false,
  }));
  fullDatabaseLoaded = true;
  render();
}

function addLines(sourceLines) {
  const existing = new Set(rows.map((r) => (r.ru || "").trim().toLowerCase()));
  let added = 0;
  for (const line of sourceLines) {
    const ru = line.trim();
    if (!ru || existing.has(ru.toLowerCase())) continue;
    rows.push(emptyRow(ru));
    existing.add(ru.toLowerCase());
    added += 1;
  }
  render();
  return added;
}

async function ensureFullDatabaseLoaded() {
  if (!fullDatabaseLoaded) {
    status("Загрузка базы...");
    await loadRows();
  }
}

$("onlyNew").addEventListener("change", async () => {
  if (!$("onlyNew").checked) {
    await ensureFullDatabaseLoaded();
  }
  render();
});

$("btnReload").addEventListener("click", () => loadRows());
$("btnAddLines").addEventListener("click", () => {
  const added = addLines($("newDishes").value.split(/\r?\n/));
  $("newDishes").value = "";
  statusText(`Added: ${added}`);
});
$("btnSave").addEventListener("click", async () => {
  const payloadRows = $("onlyNew").checked ? rows.filter((row) => row._isNew) : rows;
  const res = await fetch("/api/dishes/bulk-upsert", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
    body: JSON.stringify({rows: payloadRows}),
  });
  const data = await res.json();
  if (!res.ok) {
    status(data.error || "Ошибка сохранения");
    return;
  }
  status(`Создано: ${data.created}, обновлено: ${data.updated}, ошибок: ${data.errors.length}`);
  rows.forEach((row) => { row._isNew = false; });
  if (!$("onlyNew").checked || fullDatabaseLoaded) {
    await loadRows();
  } else {
    render();
  }
});
$("btnImport").addEventListener("click", async () => {
  const file = $("csvFile").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/dishes/import.csv", {method: "POST", headers: {"X-CSRFToken": csrfToken()}, body: form});
  const data = await res.json();
  status(`Импорт: создано ${data.created}, обновлено ${data.updated}, ошибок ${data.errors.length}`);
  await loadRows();
});

window.addEventListener("load", () => {
  const missing = JSON.parse(sessionStorage.getItem("menu_missing_ru") || "[]");
  const fix = JSON.parse(sessionStorage.getItem("menu_fix_ru") || "[]");
  sessionStorage.removeItem("menu_missing_ru");
  sessionStorage.removeItem("menu_fix_ru");

  if (missing.length) {
    $("onlyNew").checked = true;
    $("newDishes").value = missing.join("\n");
    addLines(missing);
    statusText(`Новых блюд: ${missing.length}`);
    return;
  }

  if (fix.length) {
    $("onlyNew").checked = false;
    loadRows().then(() => statusText(`Неполных блюд: ${fix.length}`));
    return;
  }

  loadRows();
});
