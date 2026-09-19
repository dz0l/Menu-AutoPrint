(function (global) {
  "use strict";

  const C = global.MenuCommon;
  const E = global.MenuEditor;
  if (!C || !E) {
    throw new Error("MenuCommon and MenuEditor must load before menu_editor_translate");
  }

  const {state} = E;

  function canTranslateRow(row) {
    return (
      E.TRANSLATION_ENABLED &&
      !state.translateAllInFlight &&
      !row._translating &&
      String(row.ru || "").trim() &&
      !String(row.en || "").trim()
    );
  }

  function translatableVisibleRows() {
    return E.visibleRows().filter((row) => canTranslateRow(row));
  }

  function updateTranslateAllButton() {
    const button = C.$("btnTranslateAll");
    if (!button) {
      return;
    }
    const count = translatableVisibleRows().length;
    button.disabled = state.translateAllInFlight || count === 0;
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

  async function requestTranslation(texts) {
    const res = await fetch("/api/dishes/translate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": C.csrfToken(),
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
    if (!E.TRANSLATION_ENABLED) {
      return;
    }
    const candidates = targetRows.filter((row) => canTranslateRow(row));
    if (!candidates.length) {
      C.toast("Нет строк для перевода.");
      return;
    }
    if (reason === "bulk") {
      state.translateAllInFlight = true;
    }
    candidates.forEach((row) => {
      row._translating = true;
      row._translateRu = String(row.ru || "").trim();
    });
    E.render();
    E.status(`Перевод: ${candidates.length} строк...`);
    E.debugLog("translate:start", {reason, count: candidates.length});

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
          row._dirty = E.isRowDirty(row);
          translated += 1;
        });
      }
      E.statusText(`Переведено: ${translated}`);
      C.toast(`Переведено: ${translated}`);
      E.debugLog("translate:done", {reason, count: translated});
    } catch (error) {
      E.status(`Ошибка перевода: ${error.message}`);
      C.toast(`Ошибка перевода: ${error.message}`);
      E.debugLog("translate:error", {reason, error: error.message, translated});
    } finally {
      candidates.forEach((row) => {
        row._translating = false;
      });
      state.translateAllInFlight = false;
      E.render();
    }
  }

  Object.assign(E, {
    canTranslateRow,
    translatableVisibleRows,
    updateTranslateAllButton,
    updateTranslateButton,
    requestTranslation,
    translateRows,
  });
})(window);
