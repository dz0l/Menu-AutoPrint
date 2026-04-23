const STORAGE_KEYS = {
  missing: "menu_missing_ru",
  fix: "menu_fix_ru",
  lastRu: "menu_last_ru",
  lastEn: "menu_last_en",
  pdfBackgroundName: "menu_pdf_background_name",
  pdfBackgroundData: "menu_pdf_background_data",
  themeMode: "menu_theme_mode",
};

const $ = (id) => document.getElementById(id);
const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";

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
  setTimeout(() => {
    box.hidden = true;
  }, 2600);
}

function loadStorage(key, fallback = "") {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function saveStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}

function lines(value) {
  return (value || "")
    .replace(/\u00a0/g, " ")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function saveMenuDraft() {
  saveStorage(STORAGE_KEYS.lastRu, $("ruText").value);
  saveStorage(STORAGE_KEYS.lastEn, $("enText").value);
}

function applyTheme(theme) {
  document.body.classList.toggle("theme-dark", theme === "dark");
  if ($("themeMode")) {
    $("themeMode").value = theme;
  }
  saveStorage(STORAGE_KEYS.themeMode, theme);
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
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
  const data = await postJson("/api/dishes/check-missing-fixables", {
    ru_lines: lines($("ruText").value),
  });
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
  const query = value.slice(start, pos).trim();
  return {
    value,
    pos,
    start,
    end: end === -1 ? value.length : end,
    query,
  };
}

function getCaretCoordinates(textarea, position) {
  const div = document.createElement("div");
  const span = document.createElement("span");
  const style = window.getComputedStyle(textarea);
  const properties = [
    "boxSizing",
    "width",
    "height",
    "overflowX",
    "overflowY",
    "borderTopWidth",
    "borderRightWidth",
    "borderBottomWidth",
    "borderLeftWidth",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "fontStyle",
    "fontVariant",
    "fontWeight",
    "fontStretch",
    "fontSize",
    "fontSizeAdjust",
    "lineHeight",
    "fontFamily",
    "textAlign",
    "textTransform",
    "textIndent",
    "textDecoration",
    "letterSpacing",
    "wordSpacing",
  ];

  div.style.position = "absolute";
  div.style.visibility = "hidden";
  div.style.whiteSpace = "pre-wrap";
  div.style.wordWrap = "break-word";

  for (const property of properties) {
    div.style[property] = style[property];
  }

  div.textContent = textarea.value.slice(0, position);
  span.textContent = textarea.value.slice(position) || ".";
  div.appendChild(span);
  document.body.appendChild(div);

  const coordinates = {
    left: span.offsetLeft - textarea.scrollLeft,
    top: span.offsetTop - textarea.scrollTop,
    lineHeight: Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.4 || 20,
  };

  document.body.removeChild(div);
  return coordinates;
}

function positionSuggest() {
  if (!suggestItems.length) {
    return;
  }

  const textarea = $("ruText");
  const panel = $("suggestRu");
  const rect = textarea.getBoundingClientRect();
  const caret = getCaretCoordinates(textarea, textarea.selectionStart || 0);
  const left = Math.min(rect.left + caret.left, window.innerWidth - 320);
  const top = rect.top + caret.top + caret.lineHeight + 4;

  panel.style.left = `${Math.max(16, left)}px`;
  panel.style.top = `${Math.max(16, top)}px`;
  panel.style.minWidth = "260px";
}

async function loadSuggestions() {
  const textarea = $("ruText");
  const {query} = currentLineInfo(textarea);
  if (!query || query.endsWith(":")) {
    hideSuggest();
    return;
  }

  const res = await fetch(`/api/dishes/suggest?q=${encodeURIComponent(query)}&lang=ru`);
  if (!res.ok) {
    hideSuggest();
    return;
  }

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

  positionSuggest();
  panel.hidden = false;
}

function hideSuggest() {
  const panel = $("suggestRu");
  panel.hidden = true;
  panel.innerHTML = "";
  suggestItems = [];
  suggestActive = -1;
}

function chooseSuggest(index) {
  const text = suggestItems[index];
  if (!text) {
    return;
  }

  const textarea = $("ruText");
  const info = currentLineInfo(textarea);
  textarea.value = info.value.slice(0, info.start) + text + info.value.slice(info.end);
  const nextPos = info.start + text.length;
  textarea.setSelectionRange(nextPos, nextPos);
  saveMenuDraft();
  hideSuggest();
  schedulePreview();
  scheduleActions();
}

function scheduleSuggest() {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(() => loadSuggestions().catch(() => hideSuggest()), 120);
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
  const mode = $("printDateMode").value;
  $("printDateCustom").hidden = mode !== "custom";
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

function restoreBackgroundState() {
  const name = loadStorage(STORAGE_KEYS.pdfBackgroundName, "");
  $("backgroundName").textContent = name ? `Подложка: ${name}` : "Подложка: не выбрана";
}

function storeBackground(file) {
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    saveStorage(STORAGE_KEYS.pdfBackgroundName, file.name);
    if (typeof reader.result === "string") {
      saveStorage(STORAGE_KEYS.pdfBackgroundData, reader.result);
    }
    restoreBackgroundState();
    toast(`Подложка выбрана: ${file.name}`);
  };
  reader.readAsDataURL(file);
}

function replaceMenuLine(source, target) {
  const updated = $("ruText")
    .value
    .split(/\r?\n/)
    .map((line) => (line.trim() === source.trim() ? target : line))
    .join("\n");
  $("ruText").value = updated;
  saveMenuDraft();
  schedulePreview();
  scheduleActions();
}

function renderReview(decisions) {
  const body = $("reviewBody");
  const actionable = (decisions || []).filter((item) => (item.status === "review" || item.status === "auto") && item.best?.name);

  if (!actionable.length) {
    setReviewOpen(false);
    toast("Совпадений для замены не найдено.");
    return;
  }

  body.innerHTML = '<div class="review-list"></div>';
  const list = body.querySelector(".review-list");

  actionable.forEach((item) => {
    const wrapper = document.createElement("div");
    wrapper.className = "review-item";
    wrapper.innerHTML = `
      <div><strong>${item.raw}</strong> → ${item.best.name}</div>
      <div class="review-score">Сходство: ${Math.round((item.best.score || 0) * 100)}%</div>
      <div class="review-actions"></div>
    `;
    const actions = wrapper.querySelector(".review-actions");

    const apply = document.createElement("button");
    apply.type = "button";
    apply.textContent = "Заменить";
    apply.addEventListener("click", () => {
      replaceMenuLine(item.raw, item.best.name);
      wrapper.remove();
      if (!list.children.length) {
        setReviewOpen(false);
        toast("Все предложенные замены применены.");
      }
    });

    actions.appendChild(apply);
    list.appendChild(wrapper);
  });

  setReviewOpen(true);
}

async function runAnalyze() {
  const decisions = await postJson("/api/menu/analyze", {text: $("ruText").value});
  renderReview(decisions.decisions || []);
}

$("ruText").addEventListener("input", () => {
  saveMenuDraft();
  schedulePreview();
  scheduleActions();
  scheduleSuggest();
});

$("ruText").addEventListener("click", scheduleSuggest);
$("ruText").addEventListener("keyup", positionSuggest);
$("ruText").addEventListener("scroll", positionSuggest);

$("ruText").addEventListener("keydown", (event) => {
  if ($("suggestRu").hidden || suggestItems.length === 0) {
    return;
  }

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

$("ruText").addEventListener("blur", () => {
  setTimeout(hideSuggest, 120);
});

$("showKcal").addEventListener("change", () => {
  preview().catch(() => {});
});

$("themeMode").addEventListener("change", (event) => {
  applyTheme(event.target.value);
});

$("printDateMode").addEventListener("change", updateDateUi);

$("btnBackground").addEventListener("click", () => {
  $("backgroundFile").click();
});

$("backgroundFile").addEventListener("change", (event) => {
  storeBackground(event.target.files?.[0]);
});

$("btnAnalyze").addEventListener("click", () => {
  runAnalyze().catch((err) => toast(err.message));
});

$("btnCloseReview").addEventListener("click", () => {
  setReviewOpen(false);
});

$("reviewModal").addEventListener("click", (event) => {
  if (event.target.dataset.closeModal === "1") {
    setReviewOpen(false);
  }
});

$("btnSettings").addEventListener("click", (event) => {
  event.stopPropagation();
  setSettingsOpen($("settingsBar").hidden);
});

document.addEventListener("click", (event) => {
  const panel = $("settingsBar");
  const button = $("btnSettings");
  if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
    setSettingsOpen(false);
  }
});

window.addEventListener("resize", positionSuggest);

$("btnPdf").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/menu/pdf", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        ru: $("ruText").value,
        en: $("enText").value,
        show_kcal: $("showKcal").checked,
        print_date: resolvedPrintDate(),
        background_name: loadStorage(STORAGE_KEYS.pdfBackgroundName, ""),
        background_data: loadStorage(STORAGE_KEYS.pdfBackgroundData, ""),
      }),
    });

    if (!res.ok) {
      throw new Error(await res.text());
    }

    const blob = await res.blob();
    window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
  } catch (err) {
    toast(err.message || "Ошибка генерации PDF");
  }
});

$("btnMissing").addEventListener("click", async () => {
  await refreshActions();
  if (!lastMissing.length) {
    return;
  }
  saveStorage(STORAGE_KEYS.missing, JSON.stringify(lastMissing));
  removeStorage(STORAGE_KEYS.fix);
  saveMenuDraft();
  location.href = "/editor/";
});

$("btnFix").addEventListener("click", async () => {
  await refreshActions();
  if (!lastFixables.length) {
    return;
  }
  saveStorage(STORAGE_KEYS.fix, JSON.stringify(lastFixables));
  removeStorage(STORAGE_KEYS.missing);
  saveMenuDraft();
  location.href = "/editor/";
});

window.addEventListener("load", () => {
  $("ruText").value = loadStorage(STORAGE_KEYS.lastRu, "");
  $("enText").value = loadStorage(STORAGE_KEYS.lastEn, "");
  removeStorage(STORAGE_KEYS.lastRu);
  removeStorage(STORAGE_KEYS.lastEn);

  $("printDateMode").value = "today";
  $("printDateCustom").value = todayDate();
  updateDateUi();
  restoreBackgroundState();
  applyTheme(loadStorage(STORAGE_KEYS.themeMode, "light"));
  setSettingsOpen(false);
  setReviewOpen(false);

  preview().catch(() => {});
  refreshActions().catch(() => {});
});
