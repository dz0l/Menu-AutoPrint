const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
const $ = (id) => document.getElementById(id);

let lastMissing = [];
let lastFixables = [];
let suggestItems = [];
let suggestActive = -1;
let suggestTimer = null;
let previewTimer = null;
let actionTimer = null;

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  setTimeout(() => { box.hidden = true; }, 2600);
}

function lines(value) {
  return (value || "").replace(/\u00a0/g, " ").split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
}

function renderPreview(target, items) {
  target.innerHTML = "";
  for (const item of items || []) {
    const span = document.createElement("span");
    span.className = item.type === "group" ? "group" : "dish";
    span.textContent = `${item.type === "dish" ? "\u2022 " : ""}${item.text}${item.suffix || ""}`;
    target.appendChild(span);
  }
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function preview() {
  const data = await postJson("/api/menu/preview", {
    ru: $("ruText").value,
    show_kcal: $("showKcal").checked,
  });
  renderPreview($("previewRu"), data.ru);
  renderPreview($("previewEn"), data.en);
  $("enText").value = (data.en || []).map((item) => item.text).join("\n");
}

async function refreshActions() {
  const data = await postJson("/api/dishes/check-missing-fixables", {ru_lines: lines($("ruText").value)});
  lastMissing = data.missing || [];
  lastFixables = data.fixables || [];
  $("btnMissing").disabled = lastMissing.length === 0;
  $("btnFix").disabled = lastFixables.length === 0;
  $("btnMissing").title = lastMissing.length ? `Новых блюд: ${lastMissing.length}` : "Новых блюд нет";
  $("btnFix").title = lastFixables.length ? `Неполных блюд: ${lastFixables.length}` : "Неполных блюд нет";
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => preview().catch((err) => toast(err.message)), 180);
}

function scheduleActions() {
  clearTimeout(actionTimer);
  actionTimer = setTimeout(() => refreshActions().catch(() => {}), 220);
}

function currentLineInfo(textarea) {
  const value = textarea.value;
  const pos = textarea.selectionStart || 0;
  const start = value.lastIndexOf("\n", pos - 1) + 1;
  const end = value.indexOf("\n", pos);
  return {value, pos, start, end: end === -1 ? value.length : end, query: value.slice(start, pos).trim()};
}

async function loadSuggestions() {
  const textarea = $("ruText");
  const {query} = currentLineInfo(textarea);
  if (!query || query.length < 2) {
    hideSuggest();
    return;
  }
  const res = await fetch(`/api/dishes/suggest?q=${encodeURIComponent(query)}&lang=ru`);
  if (!res.ok) return;
  const data = await res.json();
  suggestItems = data.items || [];
  suggestActive = suggestItems.length ? 0 : -1;
  renderSuggest();
}

function renderSuggest() {
  const panel = $("suggestRu");
  panel.innerHTML = "";
  if (!suggestItems.length) {
    hideSuggest();
    return;
  }
  suggestItems.forEach((text, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `suggest-item${index === suggestActive ? " active" : ""}`;
    button.textContent = text;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      chooseSuggest(index);
    });
    panel.appendChild(button);
  });
  panel.hidden = false;
}

function hideSuggest() {
  $("suggestRu").hidden = true;
  $("suggestRu").innerHTML = "";
  suggestItems = [];
  suggestActive = -1;
}

function chooseSuggest(index) {
  const text = suggestItems[index];
  if (!text) return;
  const textarea = $("ruText");
  const info = currentLineInfo(textarea);
  textarea.value = info.value.slice(0, info.start) + text + info.value.slice(info.end);
  const nextPos = info.start + text.length;
  textarea.setSelectionRange(nextPos, nextPos);
  hideSuggest();
  schedulePreview();
  scheduleActions();
}

function scheduleSuggest() {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(() => loadSuggestions().catch(() => hideSuggest()), 160);
}

$("btnPreview").addEventListener("click", () => {
  preview().catch((err) => toast(err.message));
  refreshActions().catch(() => {});
});
$("ruText").addEventListener("input", () => {
  schedulePreview();
  scheduleActions();
  scheduleSuggest();
});
$("ruText").addEventListener("keydown", (event) => {
  if ($("suggestRu").hidden) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    suggestActive = (suggestActive + 1) % suggestItems.length;
    renderSuggest();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    suggestActive = (suggestActive - 1 + suggestItems.length) % suggestItems.length;
    renderSuggest();
  } else if (event.key === "Enter" || event.key === "Tab") {
    event.preventDefault();
    chooseSuggest(suggestActive);
  } else if (event.key === "Escape") {
    hideSuggest();
  }
});
$("ruText").addEventListener("blur", () => setTimeout(hideSuggest, 120));
$("showKcal").addEventListener("change", () => preview().catch(() => {}));

$("btnPdf").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/menu/pdf", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
      body: JSON.stringify({
        ru: $("ruText").value,
        en: $("enText").value,
        show_kcal: $("showKcal").checked,
        print_date: $("printDate").value,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  } catch (err) {
    toast(err.message || "Ошибка генерации PDF");
  }
});

$("btnMissing").addEventListener("click", async () => {
  await refreshActions();
  if (!lastMissing.length) return;
  sessionStorage.setItem("menu_missing_ru", JSON.stringify(lastMissing));
  sessionStorage.setItem("menu_last_ru", $("ruText").value);
  sessionStorage.setItem("menu_last_en", $("enText").value);
  location.href = "/editor/";
});

$("btnFix").addEventListener("click", async () => {
  await refreshActions();
  if (!lastFixables.length) return;
  sessionStorage.setItem("menu_fix_ru", JSON.stringify(lastFixables));
  sessionStorage.setItem("menu_last_ru", $("ruText").value);
  sessionStorage.setItem("menu_last_en", $("enText").value);
  location.href = "/editor/";
});

window.addEventListener("load", () => {
  $("ruText").value = sessionStorage.getItem("menu_last_ru") || "";
  $("enText").value = sessionStorage.getItem("menu_last_en") || "";
  sessionStorage.removeItem("menu_last_ru");
  sessionStorage.removeItem("menu_last_en");
  preview().catch(() => {});
  refreshActions().catch(() => {});
});
