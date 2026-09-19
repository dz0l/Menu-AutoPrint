(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_suggest.js");
  }

  const $ = C.$;
  const requestJson = C.requestJson;

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
    if (!S.suggestItems.length) {
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

    if (S.suggestCatalog.length) {
      S.suggestItems = localSuggest(query, S.suggestCatalog);
      S.suggestActive = S.suggestItems.length ? 0 : -1;
      renderSuggest();
      return;
    }

    const started = performance.now();
    App.debugLog("suggest:fallback:start", {
      queryChars: query.length,
      url: "/api/dishes/suggest",
    });
    const res = await fetch(`/api/dishes/suggest?q=${encodeURIComponent(query)}&lang=ru`);
    if (!res.ok) {
      App.debugWarn("suggest:fallback:error", {
        status: res.status,
        durationMs: Math.round(performance.now() - started),
      });
      hideSuggest();
      return;
    }

    const data = await res.json();
    S.suggestItems = (data.items || []).slice(0, 4);
    S.suggestActive = S.suggestItems.length ? 0 : -1;
    renderSuggest();
    App.debugLog("suggest:fallback:done", {
      durationMs: Math.round(performance.now() - started),
      items: S.suggestItems.length,
    });
  }

  function renderSuggest() {
    const panel = $("suggestRu");
    panel.innerHTML = "";
    if (!S.suggestItems.length) {
      hideSuggest();
      return;
    }

    S.suggestItems.forEach((text, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `suggest-item${index === S.suggestActive ? " active" : ""}`;
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
    S.suggestItems = [];
    S.suggestActive = -1;
  }

  function chooseSuggest(index) {
    const text = S.suggestItems[index];
    if (!text) {
      return;
    }

    const textarea = $("ruText");
    const info = currentLineInfo(textarea);
    App.setRuTextValue(info.value.slice(0, info.start) + text + info.value.slice(info.end));
    const nextPos = info.start + text.length;
    textarea.setSelectionRange(nextPos, nextPos);
    hideSuggest();
    App.flushHeavyUpdate("suggest-choice");
  }

  function scheduleSuggest() {
    clearTimeout(S.suggestTimer);
    S.suggestTimer = setTimeout(() => loadSuggestions().catch(() => hideSuggest()), 40);
  }

  function normalizeSuggestValue(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/ё/g, "е")
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
    const started = performance.now();
    App.debugLog("dish-catalog:start", {url: "/api/dishes/names?lang=ru"});
    try {
      const data = await requestJson("/api/dishes/names?lang=ru");
      S.suggestCatalog = data.items || [];
      App.debugLog("dish-catalog:done", {
        durationMs: Math.round(performance.now() - started),
        items: S.suggestCatalog.length,
      });
    } catch {
      S.suggestCatalog = [];
      App.debugWarn("dish-catalog:error", {
        durationMs: Math.round(performance.now() - started),
      });
    }
  }

  Object.assign(App, {
    currentLineInfo,
    getCaretCoordinates,
    positionSuggest,
    loadSuggestions,
    renderSuggest,
    hideSuggest,
    chooseSuggest,
    scheduleSuggest,
    normalizeSuggestValue,
    localSuggest,
    preloadSuggestCatalog,
  });
})(window);
