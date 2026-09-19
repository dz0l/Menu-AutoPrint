(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_print.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const postJson = C.postJson;
  const lines = C.lines;
  const csrfToken = C.csrfToken;
  const loadStorage = C.loadStorage;
  const {STORAGE_KEYS, COVER_MODE} = App;

  async function collectPdfValidation() {
    const payload = {
      ru: $("ruText").value,
      show_kcal: $("showKcal").checked,
      auto_format: $("autoFormat")?.checked ?? false,
    };
    const data = await postJson(
      "/api/menu/preview",
      payload,
      {log: {name: "pdf-validation-preview", reason: "pdf-button"}},
    );
    S.lastPreviewData = data;
    S.previewSegmentIndex = 0;
    $("enText").value = App.enTextFromPreview(data);
    App.applyPreviewSegment();

    const segments = App.previewSegments(data);
    const ruPreview = segments.flatMap((segment) => segment.ru || []);
    const enPreview = segments.flatMap((segment) => segment.en || []);
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
    const payload = {
      ru: $("ruText").value,
      show_kcal: $("showKcal").checked,
      auto_format: $("autoFormat")?.checked ?? false,
      print_date: App.resolvedPrintDate(),
    };
    const selection = App.getCoverSelection();
    if (selection.mode === COVER_MODE.cover && selection.coverId) {
      payload.cover_id = selection.coverId;
    } else if (selection.mode === COVER_MODE.custom) {
      payload.background_name = loadStorage(STORAGE_KEYS.pdfBackgroundName, "");
      payload.background_data = loadStorage(STORAGE_KEYS.pdfBackgroundData, "");
    }
    return payload;
  }

  async function downloadPdfFlow() {
    const payload = buildDocumentPayload();
    const res = await fetch("/api/menu/pdf", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.text();
      let message = "Ошибка формирования PDF";
      try {
        const parsed = JSON.parse(body);
        message = parsed.error || message;
      } catch (error) {
        if (body) {
          message = body.slice(0, 200);
        }
      }
      throw new Error(message);
    }

    const blob = await res.blob();
    let filename = "menu.pdf";
    const disposition = res.headers.get("Content-Disposition") || "";
    const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    const plainMatch = /filename="([^"]+)"/i.exec(disposition);
    if (utfMatch) {
      try {
        filename = decodeURIComponent(utfMatch[1]);
      } catch (error) {
        filename = utfMatch[1];
      }
    } else if (plainMatch) {
      filename = plainMatch[1];
    }

    const pdfBlob = blob.type === "application/pdf" ? blob : new Blob([blob], {type: "application/pdf"});
    const file = new File([pdfBlob], filename, {type: "application/pdf"});
    const canShareFile =
      typeof navigator.canShare === "function" &&
      (() => {
        try {
          return navigator.canShare({files: [file]});
        } catch {
          return false;
        }
      })();

    if (canShareFile && typeof navigator.share === "function") {
      try {
        await navigator.share({
          files: [file],
          title: filename,
        });
        return;
      } catch (error) {
        if (error && error.name === "AbortError") {
          toast("Отправка отменена.");
          return;
        }
        App.debugWarn("pdf:share-failed", {error: error?.message || String(error)});
      }
    }

    const objectUrl = URL.createObjectURL(pdfBlob);
    const isMobileUa = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || "");
    if (isMobileUa) {
      const opened = window.open(objectUrl, "_blank");
      if (!opened) {
        const link = document.createElement("a");
        link.href = objectUrl;
        link.target = "_blank";
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      return;
    }

    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  async function openAlternativePrintFlow(printWindow = null) {
    const data = await postJson("/api/menu/render", buildDocumentPayload());
    if (printWindow && !printWindow.closed) {
      printWindow.location.href = data.print_url;
      return;
    }
    const opened = window.open(data.print_url, "_blank");
    if (!opened) {
      location.href = data.print_url;
    }
  }

  function setPdfBusy(busy) {
    S.pdfInFlight = busy;
    const button = $("btnPdf");
    if (!button) {
      return;
    }
    button.disabled = busy;
    button.innerHTML = busy
      ? '<span class="ui-icon" data-ui-icon="printer"></span> Печать...'
      : '<span class="ui-icon" data-ui-icon="printer"></span> Печать';
    global.MenuIcons?.render(button);
  }

  Object.assign(App, {
    collectPdfValidation,
    buildDocumentPayload,
    downloadPdfFlow,
    openAlternativePrintFlow,
    setPdfBusy,
  });
})(window);
