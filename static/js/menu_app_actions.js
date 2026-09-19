(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_actions.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const postJson = C.postJson;
  const lines = C.lines;
  const {IS_ADMIN} = App;

  async function refreshActions(reason = "manual") {
    if (!IS_ADMIN || !$("btnMissing")) {
      return;
    }

    const payload = {
      ru_lines: lines($("ruText").value),
      show_kcal: $("showKcal").checked,
    };
    const signature = App.actionsSignature(payload);
    const force = reason === "open-editor";
    if (!force && signature === S.actionsActiveSignature) {
      App.debugLog("actions:skip", {reason, cause: "same-payload-in-flight"});
      return;
    }
    if (!force && signature === S.actionsAppliedSignature) {
      App.debugLog("actions:skip", {reason, cause: "same-payload-applied"});
      return;
    }

    const seq = ++S.actionsSeq;
    if (S.actionsController) {
      App.debugLog("actions:abort-previous", {seq, reason, previousSeq: seq - 1});
      S.actionsController.abort();
    }
    const controller = new AbortController();
    S.actionsController = controller;
    S.actionsActiveSignature = signature;
    const started = performance.now();
    App.debugLog("actions:start", {
      seq,
      reason,
      payload: App.payloadSummary(payload),
    });

    let data;
    try {
      data = await postJson(
        "/api/dishes/check-missing-fixables",
        payload,
        {signal: controller.signal, log: {name: "check-missing-fixables", reason, seq}},
      );
    } catch (error) {
      if (S.actionsActiveSignature === signature) {
        S.actionsActiveSignature = "";
      }
      if (S.actionsController === controller) {
        S.actionsController = null;
      }
      if (error.name === "AbortError") {
        App.debugLog("actions:aborted", {seq, reason});
        return;
      }
      App.debugWarn("actions:error", {seq, reason, error: error.message});
      throw error;
    }

    if (seq !== S.actionsSeq) {
      if (S.actionsActiveSignature === signature) {
        S.actionsActiveSignature = "";
      }
      if (S.actionsController === controller) {
        S.actionsController = null;
      }
      App.debugWarn("actions:stale", {seq, currentSeq: S.actionsSeq, reason});
      return;
    }
    S.lastMissing = data.missing || [];
    S.lastFixables = data.fixables || [];
    S.actionsAppliedSignature = signature;
    const total = S.lastMissing.length + S.lastFixables.length;
    const btnMissing = $("btnMissing");
    if (btnMissing) {
      btnMissing.classList.toggle("warn", total > 0);
      btnMissing.title = total
        ? `Новых блюд: ${S.lastMissing.length}, неполных блюд: ${S.lastFixables.length}`
        : "Проверить меню и открыть редактор при необходимости";
    }
    App.debugLog("actions:updated", {
      seq,
      reason,
      durationMs: Math.round(performance.now() - started),
      missing: S.lastMissing.length,
      fixables: S.lastFixables.length,
    });
    if (S.actionsActiveSignature === signature) {
      S.actionsActiveSignature = "";
    }
    if (S.actionsController === controller) {
      S.actionsController = null;
    }
  }

  function scheduleHeavyUpdate(delay = 650, reason = "idle") {
    clearTimeout(S.heavyUpdateTimer);
    App.debugLog("heavy-update:scheduled", {reason, delayMs: delay});
    S.heavyUpdateTimer = setTimeout(() => {
      App.debugLog("heavy-update:run", {reason});
      App.preview(`heavy:${reason}`).catch((err) => toast(err.message));
      refreshActions(`heavy:${reason}`).catch(() => {});
    }, delay);
  }

  function flushHeavyUpdate(reason = "flush") {
    clearTimeout(S.heavyUpdateTimer);
    clearTimeout(S.previewTimer);
    clearTimeout(S.actionTimer);
    App.debugLog("heavy-update:flush", {reason});
    App.preview(`flush:${reason}`).catch((err) => toast(err.message));
    refreshActions(`flush:${reason}`).catch(() => {});
  }

  function buildEditorRowsFromActions() {
    const missingByKey = new Map(S.lastMissing.map((item) => [App.normalizeSuggestValue(item), item]));
    const fixableByKey = new Map(S.lastFixables.map((item) => [App.normalizeSuggestValue(item), item]));
    const seen = new Set();
    const result = [];

    function addItem(ru, mode) {
      const key = App.normalizeSuggestValue(ru);
      if (!key || key === "---" || seen.has(key)) {
        return;
      }
      seen.add(key);
      result.push({ru, mode});
    }

    lines($("ruText").value).forEach((line) => {
      if (line.trim() === "---") {
        return;
      }
      const key = App.normalizeSuggestValue(line);
      if (missingByKey.has(key)) {
        addItem(line, "missing");
      } else if (fixableByKey.has(key)) {
        addItem(line, "fix");
      }
    });

    S.lastMissing.forEach((item) => addItem(item, "missing"));
    S.lastFixables.forEach((item) => addItem(item, "fix"));
    return result;
  }

  Object.assign(App, {
    refreshActions,
    scheduleHeavyUpdate,
    flushHeavyUpdate,
    buildEditorRowsFromActions,
  });
})(window);
