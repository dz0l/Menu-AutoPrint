(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_preview.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const postJson = C.postJson;
  const {A4_RATIO, PREVIEW_BASE_WIDTH, COVER_MODE, STORAGE_KEYS} = App;
  const loadStorage = C.loadStorage;

  function appendTextWithUnknown(parent, text) {
    if (!text.includes("??")) {
      parent.appendChild(document.createTextNode(text));
      return;
    }
    const [before, ...rest] = text.split("??");
    parent.appendChild(document.createTextNode(before));
    rest.forEach((part) => {
      const unknown = document.createElement("span");
      unknown.className = "unknown";
      unknown.textContent = "??";
      parent.appendChild(unknown);
      parent.appendChild(document.createTextNode(part));
    });
  }

  function applyPreviewLayout(target, layout) {
    if (!target) {
      return;
    }
    const values = layout || {};
    // Keep CSS --preview-pt-scale aligned with PREVIEW_BASE_WIDTH / A4 pt width.
    const page = target.closest(".preview-page") || target;
    page.style.setProperty("--preview-pt-scale", String(PREVIEW_BASE_WIDTH / 595.28));
    target.style.setProperty("--menu-font-pt", values.menu_font_size || 20);
    target.style.setProperty("--menu-leading-pt", values.menu_leading || 28);
    target.style.setProperty("--continuation-leading-pt", values.continuation_leading || 24);
    target.style.setProperty("--group-space-pt", values.group_space_before || 20);
    target.style.setProperty("--after-group-space-pt", values.after_group_space_before || 6);
    target.style.setProperty("--dish-space-pt", values.dish_space_before || 2);
  }

  function getPreviewInner(target) {
    const stage = target.querySelector(".preview-doc-stage");
    if (stage) {
      const stagedInner = stage.querySelector(".preview-doc-inner");
      if (stagedInner) {
        stage.replaceWith(stagedInner);
      } else {
        stage.remove();
      }
    }
    let inner = target.querySelector(":scope > .preview-doc-inner");
    if (!inner) {
      inner = document.createElement("div");
      inner.className = "preview-doc-inner";
      target.appendChild(inner);
    }
    return inner;
  }

  function renderPreview(target, items, layout) {
    applyPreviewLayout(target, layout);
    const inner = getPreviewInner(target);
    inner.innerHTML = "";
    for (const item of items || []) {
      const itemLines = item.lines;
      if (!itemLines || itemLines.length <= 1) {
        const span = document.createElement("span");
        span.className = item.type === "group" ? "group" : "dish";
        const text = itemLines?.[0] ?? `${item.type === "dish" ? "\u2022 " : ""}${item.text}${item.suffix || ""}`;
        appendTextWithUnknown(span, text);
        inner.appendChild(span);
        continue;
      }

      if (item.type === "group") {
        const block = document.createElement("span");
        block.className = "group-block";
        itemLines.forEach((line, index) => {
          const span = document.createElement("span");
          span.className = index === 0 ? "group" : "group-line continuation";
          appendTextWithUnknown(span, line);
          block.appendChild(span);
        });
        inner.appendChild(block);
        continue;
      }

      const block = document.createElement("span");
      block.className = "dish-block";
      itemLines.forEach((line, index) => {
        const span = document.createElement("span");
        span.className = index === 0 ? "dish" : "dish-line continuation";
        appendTextWithUnknown(span, line);
        block.appendChild(span);
      });
      inner.appendChild(block);
    }
  }

  function previewSegments(data) {
    if (!data) {
      return [];
    }
    if (Array.isArray(data.segments) && data.segments.length) {
      return data.segments;
    }
    return [
      {
        ru: data.ru || [],
        en: data.en || [],
        layout: data.layout || {},
      },
    ];
  }

  function enTextFromPreview(data) {
    const segments = previewSegments(data);
    return segments
      .map((segment) => (segment.en || []).map((item) => item.text).join("\n"))
      .join("\n---\n");
  }

  function applyPreviewSegment() {
    const segments = previewSegments(S.lastPreviewData);
    if (!segments.length) {
      renderPreview($("previewRu"), [], {});
      renderPreview($("previewEn"), [], {});
      updatePreviewPager();
      updatePreviewMeta();
      return;
    }
    if (S.previewSegmentIndex >= segments.length) {
      S.previewSegmentIndex = segments.length - 1;
    }
    if (S.previewSegmentIndex < 0) {
      S.previewSegmentIndex = 0;
    }
    const segment = segments[S.previewSegmentIndex];
    const layout = segment.layout || {};
    renderPreview($("previewRu"), segment.ru, layout.ru);
    renderPreview($("previewEn"), segment.en, layout.en);
    updatePreviewPager();
    updatePreviewMeta();
    fitPreviewPage();
  }

  function updatePreviewPager() {
    const pager = $("previewPager");
    const label = $("previewPagerLabel");
    const prev = $("btnPreviewPrev");
    const next = $("btnPreviewNext");
    if (!pager || !label) {
      return;
    }
    const count = previewSegments(S.lastPreviewData).length;
    const show = count > 1;
    pager.hidden = !show;
    pager.classList.toggle("visible", show);
    label.textContent = `${S.previewSegmentIndex + 1} / ${count || 1}`;
    if (prev) {
      prev.disabled = S.previewSegmentIndex <= 0;
    }
    if (next) {
      next.disabled = S.previewSegmentIndex >= count - 1;
    }
  }

  function setPreviewLang(lang) {
    S.previewLang = lang === "en" ? "en" : "ru";
    const isEn = S.previewLang === "en";
    $("previewRu").hidden = isEn;
    $("previewEn").hidden = !isEn;
    $("previewRu").classList.toggle("active", !isEn);
    $("previewEn").classList.toggle("active", isEn);
    $("previewTabRu")?.classList.toggle("active", !isEn);
    $("previewTabEn")?.classList.toggle("active", isEn);
    updatePreviewMeta();
  }

  function updatePreviewMeta() {
    const date = $("previewFooterDate");
    if (date) {
      const value = App.resolvedPrintDate();
      if (value) {
        const [year, month, day] = value.split("-");
        date.textContent = year && month && day ? `${day}.${month}.${year}` : value;
      } else {
        date.textContent = "";
      }
    }
    const note = $("previewFooterNote");
    if (note) {
      note.hidden = !$("showKcal").checked;
      if (!note.hidden) {
        const isEn = !$("previewEn").hidden;
        note.textContent = isEn ? "Calories indicated per serving" : "Калорийность и вес указаны на порцию";
      }
    }
  }

  function updatePreviewBackground() {
    const image = $("previewBackground");
    const overlay = $("previewOverlay");
    if (!image || !overlay) {
      return;
    }

    const selection = App.getCoverSelection();
    if (selection.mode === COVER_MODE.cover && selection.coverId) {
      image.src = `/api/menu/covers/${selection.coverId}/image`;
      image.hidden = false;
      overlay.hidden = false;
      return;
    }

    const data = loadStorage(STORAGE_KEYS.pdfBackgroundData, "");
    if (selection.mode === COVER_MODE.custom && data) {
      image.src = data;
      image.hidden = false;
      overlay.hidden = false;
      return;
    }

    image.removeAttribute("src");
    image.hidden = true;
    overlay.hidden = true;
  }

  function fitPreviewPage() {
    const area = $("previewPageArea");
    const page = $("previewPage");
    if (!area || !page) {
      return;
    }

    const style = window.getComputedStyle(area);
    const availableWidth = area.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const availableHeight = area.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    if (availableWidth <= 0 || availableHeight <= 0) {
      return;
    }

    let width = availableWidth;
    let height = width / A4_RATIO;
    if (height > availableHeight) {
      height = availableHeight;
      width = height * A4_RATIO;
    }

    const scale = Math.max(0.72, width / PREVIEW_BASE_WIDTH);
    page.style.setProperty("--preview-page-width", `${Math.floor(width)}px`);
    page.style.setProperty("--preview-page-height", `${Math.floor(height)}px`);
    page.style.setProperty("--preview-scale", String(scale));
  }

  function initPreviewPageFit() {
    const area = $("previewPageArea");
    const shell = area?.closest(".preview-shell");
    if (!area) {
      return;
    }

    fitPreviewPage();
    if ("ResizeObserver" in window) {
      S.previewResizeObserver = new ResizeObserver(() => fitPreviewPage());
      S.previewResizeObserver.observe(area);
      if (shell) {
        S.previewResizeObserver.observe(shell);
      }
    } else {
      window.addEventListener("resize", fitPreviewPage);
    }
  }

  function finishPreviewRequest(signature, controller) {
    if (S.previewActiveSignature === signature) {
      S.previewActiveSignature = "";
    }
    if (S.previewController === controller) {
      S.previewController = null;
    }
    if (S.previewQueuedReason) {
      const reason = S.previewQueuedReason;
      S.previewQueuedReason = "";
      setTimeout(() => preview(`queued:${reason}`).catch((err) => toast(err.message)), 0);
    }
  }

  async function preview(reason = "manual") {
    const payload = {
      ru: $("ruText").value,
      show_kcal: $("showKcal").checked,
      auto_format: $("autoFormat")?.checked ?? false,
    };
    const signature = App.previewSignature(payload);
    if (signature === S.previewActiveSignature) {
      App.debugLog("preview:skip", {reason, cause: "same-payload-in-flight"});
      return;
    }
    if (signature === S.previewRenderedSignature) {
      App.debugLog("preview:skip", {reason, cause: "same-payload-rendered"});
      return;
    }
    if (S.previewActiveSignature) {
      S.previewQueuedReason = reason;
      App.debugLog("preview:queued", {
        reason,
        cause: "different-payload-in-flight",
        payload: App.payloadSummary(payload),
      });
      return;
    }

    const seq = ++S.previewSeq;
    const controller = new AbortController();
    S.previewController = controller;
    S.previewActiveSignature = signature;
    const started = performance.now();
    App.debugLog("preview:start", {
      seq,
      reason,
      payload: App.payloadSummary(payload),
    });

    let data;
    try {
      data = await postJson(
        "/api/menu/preview",
        payload,
        {signal: controller.signal, log: {name: "preview", reason, seq}},
      );
    } catch (error) {
      finishPreviewRequest(signature, controller);
      if (error.name === "AbortError") {
        App.debugLog("preview:aborted", {seq, reason});
        return;
      }
      App.debugWarn("preview:error", {seq, reason, error: error.message});
      throw error;
    }

    const currentSignature = App.previewSignature({
      ru: $("ruText").value,
      show_kcal: $("showKcal").checked,
      auto_format: $("autoFormat")?.checked ?? false,
    });
    if (currentSignature !== signature) {
      S.previewQueuedReason = S.previewQueuedReason || reason;
      App.debugLog("preview:stale-ui", {seq, reason});
      finishPreviewRequest(signature, controller);
      return;
    }

    if (seq !== S.previewSeq) {
      App.debugWarn("preview:stale", {seq, currentSeq: S.previewSeq, reason});
      finishPreviewRequest(signature, controller);
      return;
    }
    S.lastPreviewData = data;
    S.previewSegmentIndex = 0;
    $("enText").value = enTextFromPreview(data);
    applyPreviewSegment();
    S.previewRenderedSignature = signature;
    App.debugLog("preview:rendered", {
      seq,
      reason,
      durationMs: Math.round(performance.now() - started),
      ruItems: (data.ru || []).length,
      enItems: (data.en || []).length,
    });
    finishPreviewRequest(signature, controller);
  }

  Object.assign(App, {
    appendTextWithUnknown,
    applyPreviewLayout,
    getPreviewInner,
    renderPreview,
    previewSegments,
    enTextFromPreview,
    applyPreviewSegment,
    updatePreviewPager,
    setPreviewLang,
    updatePreviewMeta,
    updatePreviewBackground,
    fitPreviewPage,
    initPreviewPageFit,
    finishPreviewRequest,
    preview,
  });
})(window);
