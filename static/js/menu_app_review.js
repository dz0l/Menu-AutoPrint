(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_review.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const postJson = C.postJson;
  const saveStorage = C.saveStorage;
  const {STORAGE_KEYS} = App;

  function replaceMenuLine(source, target) {
    const updated = $("ruText")
      .value
      .split(/\r?\n/)
      .map((line) => (line.trim() === source.trim() ? target : line))
      .join("\n");
    App.setRuTextValue(updated);
    App.flushHeavyUpdate("replace-one");
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
      App.setRuTextValue(updated);
      App.flushHeavyUpdate("replace-many");
    }
    return replaced;
  }

  function renderReview(decisions, options = {}) {
    const body = $("reviewBody");
    const finishReview = () => {
      if (typeof options.onComplete === "function") {
        options.onComplete();
      }
    };
    const autoReplacements = (decisions || [])
      .filter((item) => item.status === "auto" && item.best?.name)
      .map((item) => ({source: item.raw, target: item.best.name}));
    const autoCount = replaceMenuLines(autoReplacements);
    const actionable = (decisions || []).filter((item) => item.status === "review" && item.best?.name);

    if (!actionable.length) {
      App.setReviewOpen(false);
      if (autoCount > 0) {
        toast(`Автоматически заменено: ${autoCount}`);
      } else if (!options.quietNoMatches) {
        toast("Совпадений для замены не найдено.");
      }
      finishReview();
      return;
    }

    body.innerHTML = '<div class="review-list"></div>';
    const list = body.querySelector(".review-list");
    const pending = new Set(actionable.map((_, index) => index));

    actionable.forEach((item, index) => {
      const wrapper = document.createElement("div");
      wrapper.className = "review-item";
      wrapper.dataset.reviewIndex = String(index);

      const compare = document.createElement("div");
      compare.className = "review-compare";

      const source = document.createElement("div");
      source.className = "review-source";
      const sourceStrong = document.createElement("strong");
      sourceStrong.textContent = item.raw || "";
      source.appendChild(sourceStrong);

      const target = document.createElement("div");
      target.className = "review-target";
      target.textContent = item.best.name || "";

      const score = document.createElement("div");
      score.className = "review-score";
      score.textContent = `Сходство: ${Math.round((item.best.score || 0) * 100)}%`;

      compare.appendChild(source);
      compare.appendChild(target);
      compare.appendChild(score);

      const actions = document.createElement("div");
      actions.className = "review-actions review-actions-column";

      wrapper.appendChild(compare);
      wrapper.appendChild(actions);

      const apply = document.createElement("button");
      apply.type = "button";
      apply.textContent = "Заменить";
      apply.addEventListener("click", () => {
        pending.delete(index);
        replaceMenuLine(item.raw, item.best.name);
        wrapper.remove();
        if (!list.children.length) {
          App.setReviewOpen(false);
          toast("Все предложенные замены применены.");
          finishReview();
        }
      });

      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Отменить";
      cancel.addEventListener("click", () => {
        pending.delete(index);
        wrapper.remove();
        if (!list.children.length) {
          App.setReviewOpen(false);
          toast("Список совпадений обработан.");
          finishReview();
        }
      });

      actions.appendChild(apply);
      actions.appendChild(cancel);
      list.appendChild(wrapper);
    });

    $("btnReplaceAll").onclick = () => {
      const replacements = actionable
        .filter((_, index) => pending.has(index))
        .map((item) => ({source: item.raw, target: item.best.name}));
      const replaced = replaceMenuLines(replacements);
      App.setReviewOpen(false);
      toast(`Заменено: ${replaced}${autoCount ? `, автоматически: ${autoCount}` : ""}`);
      finishReview();
    };

    if (autoCount > 0) {
      toast(`Автоматически заменено: ${autoCount}`);
    }
    App.setReviewOpen(true);
  }

  async function runAnalyze(options = {}) {
    if (S.analyzeInFlight) {
      App.debugWarn("analyze:skip", {reason: "already-in-flight"});
      return;
    }

    S.analyzeInFlight = true;
    const button = options.button || $("btnMissing");
    const originalText = button?.textContent || "";
    if (button) {
      button.disabled = true;
      button.textContent = "Проверка...";
    }
    const started = performance.now();
    App.debugLog("analyze:start", {
      payload: App.payloadSummary({text: $("ruText").value}),
    });

    try {
      const decisions = await postJson(
        "/api/menu/analyze",
        {text: $("ruText").value},
        {log: {name: "analyze", reason: "button"}},
      );
      renderReview(decisions.decisions || [], options);
      App.debugLog("analyze:done", {
        durationMs: Math.round(performance.now() - started),
        decisions: (decisions.decisions || []).length,
      });
    } finally {
      S.analyzeInFlight = false;
      if (button) {
        button.disabled = false;
        if (button.id === "btnMissing") {
          button.innerHTML = '<span class="ui-icon" data-ui-icon="database-zap"></span> Проверить меню';
          global.MenuIcons?.render(button);
        } else {
          button.textContent = originalText;
        }
      }
    }
  }

  async function openEditorFromActions() {
    await App.refreshActions("open-editor");
    const editorRows = App.buildEditorRowsFromActions();
    if (!editorRows.length) {
      toast("Новых и неполных блюд нет.");
      return;
    }
    saveStorage(STORAGE_KEYS.editorRows, JSON.stringify(editorRows));
    App.saveMenuDraft();
    location.href = "/editor/";
  }

  async function checkAndOpenEditor() {
    await runAnalyze({
      button: $("btnMissing"),
      onComplete: () => {
        openEditorFromActions().catch((error) => toast(error.message));
      },
    });
  }

  async function refreshAfterEditorSave() {
    await runAnalyze({
      button: $("btnMissing"),
      quietNoMatches: true,
      onComplete: () => {
        App.preview("editor-save-check").catch((error) => toast(error.message));
        App.refreshActions("editor-save-check").catch(() => {});
      },
    });
  }

  Object.assign(App, {
    replaceMenuLine,
    replaceMenuLines,
    renderReview,
    runAnalyze,
    openEditorFromActions,
    checkAndOpenEditor,
    refreshAfterEditorSave,
  });
})(window);
