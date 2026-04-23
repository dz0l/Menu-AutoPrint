const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
const $ = (id) => document.getElementById(id);
let rows = [];

function status(text) {
  $("status").textContent = text;
}

function emptyRow(ru = "") {
  return {ru, en: "", kcal: "", gr: "", catRu: "", catEn: ""};
}

function render() {
  const tbody = $("rows");
  tbody.innerHTML = "";
  rows.forEach((row, index) => {
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
      status(`Строк: ${rows.length}`);
    });
    action.appendChild(del);
    tr.appendChild(action);
    tbody.appendChild(tr);
  });
  status(`Строк: ${rows.length}`);
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
  }));
  render();
}

function addLines(lines) {
  const existing = new Set(rows.map((r) => (r.ru || "").trim().toLowerCase()));
  for (const line of lines) {
    const ru = line.trim();
    if (!ru || existing.has(ru.toLowerCase())) continue;
    rows.push(emptyRow(ru));
    existing.add(ru.toLowerCase());
  }
  render();
}

$("btnReload").addEventListener("click", () => loadRows());
$("btnAddLines").addEventListener("click", () => {
  addLines($("newDishes").value.split(/\r?\n/));
  $("newDishes").value = "";
});
$("btnSave").addEventListener("click", async () => {
  const res = await fetch("/api/dishes/bulk-upsert", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
    body: JSON.stringify({rows}),
  });
  const data = await res.json();
  if (!res.ok) {
    status(data.error || "Ошибка сохранения");
    return;
  }
  status(`Создано: ${data.created}, обновлено: ${data.updated}, ошибок: ${data.errors.length}`);
  await loadRows();
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
  loadRows().then(() => {
    if (missing.length) addLines(missing);
    if (fix.length) status(`Для исправления: ${fix.length}`);
  });
});
