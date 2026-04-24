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
let suggestCatalog = [];
let suggestTimer = null;
let previewTimer = null;
let actionTimer = null;
let analyzeInFlight = false;
let usersLoading = false;
let lastPreviewData = null;
let pdfInFlight = false;
let previewController = null;
let actionsController = null;
let previewSeq = 0;
let actionsSeq = 0;
let heavyUpdateTimer = null;
let ruHistory = [];
let ruHistoryIndex = -1;
let ruHistoryLastCommit = 0;
let suppressRuHistory = false;
const RU_HISTORY_LIMIT = 120;

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

function resetRuHistory(value) {
  ruHistory = [String(value || "")];
  ruHistoryIndex = 0;
  ruHistoryLastCommit = Date.now();
}

function pushRuHistory(value, options = {}) {
  if (suppressRuHistory) {
    return;
  }

  const next = String(value || "");
  const force = Boolean(options.force);
  if (ruHistoryIndex < 0) {
    resetRuHistory(next);
    return;
  }

  const current = ruHistory[ruHistoryIndex];
  if (next === current) {
    return;
  }

  const now = Date.now();
  const canMerge =
    !force &&
    ruHistory.length > 1 &&
    ruHistoryIndex === ruHistory.length - 1 &&
    now - ruHistoryLastCommit < 700;

  if (canMerge) {
    ruHistory[ruHistoryIndex] = next;
    ruHistoryLastCommit = now;
    return;
  }

  if (ruHistoryIndex < ruHistory.length - 1) {
    ruHistory = ruHistory.slice(0, ruHistoryIndex + 1);
  }

  ruHistory.push(next);
  if (ruHistory.length > RU_HISTORY_LIMIT) {
    const overflow = ruHistory.length - RU_HISTORY_LIMIT;
    ruHistory.splice(0, overflow);
    ruHistoryIndex = Math.max(0, ruHistoryIndex - overflow);
  }

  ruHistoryIndex = ruHistory.length - 1;
  ruHistoryLastCommit = now;
}

function applyRuHistoryState(value) {
  const textarea = $("ruText");
  suppressRuHistory = true;
  textarea.value = value;
  suppressRuHistory = false;
  hideSuggest();
  saveMenuDraft();
  flushHeavyUpdate();
  textarea.focus();
  textarea.setSelectionRange(value.length, value.length);
}

function undoRuChange() {
  if (ruHistoryIndex <= 0) {
    return false;
  }
  ruHistoryIndex -= 1;
  applyRuHistoryState(ruHistory[ruHistoryIndex]);
  return true;
}

function redoRuChange() {
  if (ruHistoryIndex >= ruHistory.length - 1) {
    return false;
  }
  ruHistoryIndex += 1;
  applyRuHistoryState(ruHistory[ruHistoryIndex]);
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
}

function themeButtonText(theme) {
  return theme === "dark" ? "☀️" : "🌙";
}

function applyTheme(theme) {
  document.body.classList.toggle("theme-dark", theme === "dark");
  const button = $("btnTheme");
  if (button) {
    button.textContent = themeButtonText(theme);
    button.title = theme === "dark" ? "Светлая тема" : "Тёмная тема";
    button.setAttribute("aria-label", button.title);
  }
  saveStorage(STORAGE_KEYS.themeMode, theme);
}

function toggleTheme() {
  const next = document.body.classList.contains("theme-dark") ? "light" : "dark";
  applyTheme(next);
}

async function postJson(url, payload, options = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    if (typeof data === "object" && data) {
      throw new Error(data.error || (data.errors || []).join("\n") || "Request failed");
    }
    throw new Error(String(data || "Request failed"));
  }
  return data;
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
  const seq = ++previewSeq;
  previewController?.abort();
  previewController = new AbortController();

  let data;
  try {
    data = await postJson(
      "/api/menu/preview",
      {
        ru: $("ruText").value,
        show_kcal: $("showKcal").checked,
      },
      {signal: previewController.signal},
    );
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    throw error;
  }

  if (seq !== previewSeq) {
    return;
  }
  lastPreviewData = data;
  renderPreview($("previewRu"), data.ru);
  renderPreview($("previewEn"), data.en);
  $("enText").value = (data.en || []).map((item) => item.text).join("\n");
}

async function refreshActions() {
  const seq = ++actionsSeq;
  actionsController?.abort();
  actionsController = new AbortController();

  let data;
  try {
    data = await postJson(
      "/api/dishes/check-missing-fixables",
      {
        ru_lines: lines($("ruText").value),
      },
      {signal: actionsController.signal},
    );
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    throw error;
  }

  if (seq !== actionsSeq) {
    return;
  }
  lastMissing = data.missing || [];
  lastFixables = data.fixables || [];
  $("btnMissing").disabled = lastMissing.length === 0;
  $("btnFix").disabled = lastFixables.length === 0;
  $("btnMissing").title = lastMissing.length ? `Новых блюд: ${lastMissing.length}` : "Новых блюд нет";
  $("btnFix").title = lastFixables.length ? `Неполных блюд: ${lastFixables.length}` : "Неполных блюд нет";
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => preview().catch((err) => toast(err.message)), 260);
}

function scheduleActions() {
  clearTimeout(actionTimer);
  actionTimer = setTimeout(() => refreshActions().catch(() => {}), 320);
}

function scheduleHeavyUpdate(delay = 650) {
  clearTimeout(heavyUpdateTimer);
  heavyUpdateTimer = setTimeout(() => {
    preview().catch((err) => toast(err.message));
    refreshActions().catch(() => {});
  }, delay);
}

function flushHeavyUpdate() {
  clearTimeout(heavyUpdateTimer);
  clearTimeout(previewTimer);
  clearTimeout(actionTimer);
  preview().catch((err) => toast(err.message));
  refreshActions().catch(() => {});
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

  if (suggestCatalog.length) {
    suggestItems = localSuggest(query, suggestCatalog);
    suggestActive = suggestItems.length ? 0 : -1;
    renderSuggest();
    return;
  }

  const res = await fetch(`/api/dishes/suggest?q=${encodeURIComponent(query)}&lang=ru`);
  if (!res.ok) {
    hideSuggest();
    return;
  }

  const data = await res.json();
  suggestItems = (data.items || []).slice(0, 4);
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
  setRuTextValue(info.value.slice(0, info.start) + text + info.value.slice(info.end));
  const nextPos = info.start + text.length;
  textarea.setSelectionRange(nextPos, nextPos);
  hideSuggest();
  flushHeavyUpdate();
}

function scheduleSuggest() {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(() => loadSuggestions().catch(() => hideSuggest()), 40);
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

function setUsersOpen(open) {
  const modal = $("usersModal");
  if (!modal) {
    return;
  }
  modal.hidden = !open;
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
  setRuTextValue(updated);
  flushHeavyUpdate();
}

function replaceMenuLines(replacements) {
  if (!replacements.length) {
    return 0;
  }

  const pending = new Map();
  replacements.forEach(({source, target}) => {
    if (!pending.has(source.trim())) {
      pending.set(source.trim(), target);
    }
  });

  let replaced = 0;
  const updated = $("ruText")
    .value
    .split(/\r?\n/)
    .map((line) => {
      const next = pending.get(line.trim());
      if (next && next !== line) {
        replaced += 1;
        return next;
      }
      return line;
    })
    .join("\n");

  if (replaced > 0) {
    setRuTextValue(updated);
    flushHeavyUpdate();
  }
  return replaced;
}

function renderReview(decisions) {
  const body = $("reviewBody");
  const autoReplacements = (decisions || [])
    .filter((item) => item.status === "auto" && item.best?.name)
    .map((item) => ({source: item.raw, target: item.best.name}));
  const autoCount = replaceMenuLines(autoReplacements);
  const actionable = (decisions || []).filter((item) => item.status === "review" && item.best?.name);

  if (!actionable.length) {
    setReviewOpen(false);
    if (autoCount > 0) {
      toast(`Автоматически заменено: ${autoCount}`);
    } else {
      toast("Совпадений для замены не найдено.");
    }
    return;
  }

  body.innerHTML = '<div class="review-list"></div>';
  const list = body.querySelector(".review-list");

  actionable.forEach((item) => {
    const wrapper = document.createElement("div");
    wrapper.className = "review-item";
    wrapper.innerHTML = `
      <div class="review-compare">
        <div class="review-source"><strong>${item.raw}</strong></div>
        <div class="review-target">${item.best.name}</div>
        <div class="review-score">Сходство: ${Math.round((item.best.score || 0) * 100)}%</div>
      </div>
      <div class="review-actions review-actions-column"></div>
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

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Отменить";
    cancel.addEventListener("click", () => {
      wrapper.remove();
      if (!list.children.length) {
        setReviewOpen(false);
        toast("Список совпадений обработан.");
      }
    });

    actions.appendChild(apply);
    actions.appendChild(cancel);
    list.appendChild(wrapper);
  });

  $("btnReplaceAll").onclick = () => {
    const replacements = actionable.map((item) => ({source: item.raw, target: item.best.name}));
    const replaced = replaceMenuLines(replacements);
    setReviewOpen(false);
    toast(`Заменено: ${replaced}${autoCount ? `, автоматически: ${autoCount}` : ""}`);
  };

  if (autoCount > 0) {
    toast(`Автоматически заменено: ${autoCount}`);
  }
  setReviewOpen(true);
}

async function runAnalyze() {
  if (analyzeInFlight) {
    return;
  }

  analyzeInFlight = true;
  $("btnAnalyze").disabled = true;
  const originalText = $("btnAnalyze").textContent;
  $("btnAnalyze").textContent = "Поиск...";

  try {
    const decisions = await postJson("/api/menu/analyze", {text: $("ruText").value});
    renderReview(decisions.decisions || []);
  } finally {
    analyzeInFlight = false;
    $("btnAnalyze").disabled = false;
    $("btnAnalyze").textContent = originalText;
  }
}

function randomPassword() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*";
  const bytes = new Uint32Array(14);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
}

async function collectPdfValidation() {
  const data = await postJson("/api/menu/preview", {
    ru: $("ruText").value,
    show_kcal: $("showKcal").checked,
  });
  lastPreviewData = data;
  renderPreview($("previewRu"), data.ru);
  renderPreview($("previewEn"), data.en);
  $("enText").value = (data.en || []).map((item) => item.text).join("\n");

  const ruPreview = data.ru || [];
  const enPreview = data.en || [];
  const enLines = lines($("enText").value);
  const issues = [];

  if ($("showKcal").checked) {
    const hasUnknownSuffix = [...ruPreview, ...enPreview].some((item) => (item.suffix || "").includes("??"));
    const hasUnknownTranslation = enLines.some((line) => line.includes("???"));
    if (hasUnknownSuffix || hasUnknownTranslation) {
      issues.push("Есть неизвестные блюда, переводы, граммовки или калории.");
    }
  } else {
    const hasUnknownTranslation = enLines.some((line) => line.includes("???"));
    if (hasUnknownTranslation) {
      issues.push("Есть блюда без перевода.");
    }
  }

  return issues;
}

function buildDocumentPayload() {
  return {
    ru: $("ruText").value,
    show_kcal: $("showKcal").checked,
    print_date: resolvedPrintDate(),
    background_name: loadStorage(STORAGE_KEYS.pdfBackgroundName, ""),
    background_data: loadStorage(STORAGE_KEYS.pdfBackgroundData, ""),
  };
}

async function openDocumentFlow() {
  const data = await postJson("/api/menu/render", buildDocumentPayload());
  location.href = data.preview_url;
}

function normalizeSuggestValue(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[•"'`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function localSuggest(query, catalog) {
  const norm = normalizeSuggestValue(query);
  if (!norm) {
    return [];
  }

  const tokens = norm.split(" ").filter(Boolean);
  const scored = [];
  for (const name of catalog) {
    const normalizedName = normalizeSuggestValue(name);
    if (!normalizedName) {
      continue;
    }

    let score = 100;
    for (const token of tokens) {
      const parts = normalizedName.split(" ");
      const starts = parts.some((part) => part.startsWith(token));
      const contains = normalizedName.includes(token);
      if (starts) {
        score = Math.min(score, 10);
      } else if (contains) {
        score = Math.min(score, 30);
      } else {
        score = null;
        break;
      }
    }

    if (score === null) {
      continue;
    }
    if (normalizedName.startsWith(tokens[0])) {
      score = Math.min(score, 5);
    }
    scored.push({name, score, length: normalizedName.length});
  }

  scored.sort((left, right) => left.score - right.score || left.length - right.length || left.name.localeCompare(right.name));
  return scored.slice(0, 4).map((item) => item.name);
}

async function preloadSuggestCatalog() {
  try {
    const data = await requestJson("/api/dishes/names?lang=ru");
    suggestCatalog = data.items || [];
  } catch {
    suggestCatalog = [];
  }
}

function setPdfBusy(busy) {
  pdfInFlight = busy;
  const button = $("btnPdf");
  if (!button) {
    return;
  }
  button.disabled = busy;
  button.textContent = busy ? "PDF..." : "PDF";
}

function showUserResult(message) {
  const box = $("usersResult");
  if (!box) {
    return;
  }
  box.textContent = message;
  box.hidden = false;
}

function renderUsers(users) {
  const list = $("usersList");
  if (!list) {
    return;
  }

  list.innerHTML = "";
  users.forEach((user) => {
    const item = document.createElement("div");
    item.className = "users-item";

    const meta = document.createElement("div");
    meta.className = "users-meta";
    meta.innerHTML = `
      <strong>${user.username}</strong>
      <span class="muted">${user.must_change_password ? "Требуется смена пароля" : "Пароль обновлён"}</span>
    `;
    item.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "review-actions";

    if (!user.is_madmin) {
      const resetBtn = document.createElement("button");
      resetBtn.type = "button";
      resetBtn.textContent = "Сбросить пароль";
      resetBtn.addEventListener("click", async () => {
        resetBtn.disabled = true;
        try {
          const data = await requestJson(`/api/accounts/users/${user.id}/reset-password`, {
            method: "POST",
            headers: {"X-CSRFToken": csrfToken()},
          });
          showUserResult(`Новый пароль для ${user.username}: ${data.generated_password}`);
          toast(`Пароль пользователя ${user.username} сброшен.`);
          await loadUsers();
        } catch (error) {
          toast(error.message);
        } finally {
          resetBtn.disabled = false;
        }
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "danger-button";
      deleteBtn.textContent = "Удалить";
      deleteBtn.addEventListener("click", async () => {
        if (!window.confirm(`Удалить пользователя ${user.username}?`)) {
          return;
        }
        deleteBtn.disabled = true;
        try {
          await requestJson(`/api/accounts/users/${user.id}`, {
            method: "DELETE",
            headers: {"X-CSRFToken": csrfToken()},
          });
          toast(`Пользователь ${user.username} удалён.`);
          await loadUsers();
        } catch (error) {
          toast(error.message);
        } finally {
          deleteBtn.disabled = false;
        }
      });

      actions.appendChild(resetBtn);
      actions.appendChild(deleteBtn);
    } else {
      const label = document.createElement("span");
      label.className = "muted";
      label.textContent = "mAdmin защищён от удаления и сброса";
      actions.appendChild(label);
    }

    item.appendChild(actions);
    list.appendChild(item);
  });
}

async function loadUsers() {
  const list = $("usersList");
  if (!list || usersLoading) {
    return;
  }

  usersLoading = true;
  list.innerHTML = '<div class="muted">Загрузка...</div>';
  try {
    const data = await requestJson("/api/accounts/users");
    renderUsers(data.users || []);
  } catch (error) {
    list.innerHTML = `<div class="danger">${error.message}</div>`;
  } finally {
    usersLoading = false;
  }
}

async function createUser() {
  const username = $("userCreateName")?.value.trim();
  const password = $("userCreatePassword")?.value.trim();
  if (!username) {
    toast("Укажите имя пользователя.");
    return;
  }

  const btn = $("btnCreateUser");
  btn.disabled = true;
  try {
    const data = await requestJson("/api/accounts/users", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({username, password}),
    });
    $("userCreateName").value = "";
    $("userCreatePassword").value = "";
    showUserResult(`Пользователь ${data.user.username} создан. Пароль: ${data.generated_password}`);
    toast(`Пользователь ${data.user.username} создан.`);
    await loadUsers();
  } catch (error) {
    toast(error.message);
  } finally {
    btn.disabled = false;
  }
}

$("ruText").addEventListener("input", () => {
  pushRuHistory($("ruText").value);
  saveMenuDraft();
  scheduleSuggest();
  scheduleHeavyUpdate(650);
});

$("ruText").addEventListener("click", scheduleSuggest);
$("ruText").addEventListener("keyup", positionSuggest);
$("ruText").addEventListener("scroll", positionSuggest);

$("ruText").addEventListener("keydown", (event) => {
  const key = String(event.key || "").toLowerCase();
  const withModifier = event.ctrlKey || event.metaKey;
  if (withModifier && !event.altKey && !event.shiftKey && key === "z") {
    event.preventDefault();
    undoRuChange();
    return;
  }
  if (withModifier && !event.altKey && ((event.shiftKey && key === "z") || (!event.shiftKey && key === "y"))) {
    event.preventDefault();
    redoRuChange();
    return;
  }
  if (event.key === "Enter" && ($("suggestRu").hidden || suggestItems.length === 0)) {
    setTimeout(() => flushHeavyUpdate(), 0);
  }
});

$("ruText").addEventListener("paste", () => {
  setTimeout(() => flushHeavyUpdate(), 0);
});

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
  flushHeavyUpdate();
});

$("showKcal").addEventListener("change", () => {
  preview().catch(() => {});
});

$("btnTheme").addEventListener("click", () => {
  toggleTheme();
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

if ($("btnUsers")) {
  $("btnUsers").addEventListener("click", async () => {
    showUserResult("");
    $("usersResult").hidden = true;
    setUsersOpen(true);
    await loadUsers();
  });

  $("btnCloseUsers").addEventListener("click", () => {
    setUsersOpen(false);
  });

  $("usersModal").addEventListener("click", (event) => {
    if (event.target.dataset.closeUsers === "1") {
      setUsersOpen(false);
    }
  });

  $("btnRefreshUsers").addEventListener("click", () => {
    loadUsers().catch(() => {});
  });

  $("btnGenerateUserPassword").addEventListener("click", () => {
    $("userCreatePassword").value = randomPassword();
    showUserResult("Пароль сгенерирован. Он будет показан повторно только после создания или сброса.");
  });

  $("btnCreateUser").addEventListener("click", () => {
    createUser().catch((error) => toast(error.message));
  });
}

document.addEventListener("click", (event) => {
  const panel = $("settingsBar");
  const button = $("btnSettings");
  if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
    setSettingsOpen(false);
  }
});

window.addEventListener("resize", positionSuggest);

$("btnPdf").addEventListener("click", async () => {
  if (pdfInFlight) {
    return;
  }

  setPdfBusy(true);
  try {
    const issues = await collectPdfValidation();
    if (issues.length) {
      toast(issues[0]);
      setPdfBusy(false);
      return;
    }
    await openDocumentFlow();
    setTimeout(() => setPdfBusy(false), 1800);
  } catch (err) {
    setPdfBusy(false);
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
  setUsersOpen(false);
  resetRuHistory($("ruText").value);

  preview().catch(() => {});
  refreshActions().catch(() => {});
  preloadSuggestCatalog().catch(() => {});
});
