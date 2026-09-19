(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp modules must load before menu_app_boot.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const loadStorage = C.loadStorage;
  const saveStorage = C.saveStorage;
  const removeStorage = C.removeStorage;
  const {STORAGE_KEYS, COVER_MODE, IS_ADMIN} = App;

  function wireEvents() {
    $("ruText").addEventListener("input", () => {
      App.pushRuHistory($("ruText").value);
      App.saveMenuDraft();
      App.updateLineCounter();
      App.scheduleSuggest();
      App.scheduleHeavyUpdate(650, "ru-input");
    });

    $("ruText").addEventListener("click", App.scheduleSuggest);
    $("ruText").addEventListener("keyup", App.positionSuggest);
    $("ruText").addEventListener("scroll", App.positionSuggest);

    $("ruText").addEventListener("keydown", (event) => {
      const key = String(event.key || "").toLowerCase();
      const withModifier = event.ctrlKey || event.metaKey;
      if (withModifier && !event.altKey && !event.shiftKey && key === "z") {
        event.preventDefault();
        App.undoRuChange();
        return;
      }
      if (withModifier && !event.altKey && ((event.shiftKey && key === "z") || (!event.shiftKey && key === "y"))) {
        event.preventDefault();
        App.redoRuChange();
        return;
      }
      if (event.key === "Enter" && ($("suggestRu").hidden || S.suggestItems.length === 0)) {
        setTimeout(() => App.flushHeavyUpdate("enter"), 0);
      }
    });

    $("ruText").addEventListener("paste", () => {
      setTimeout(() => App.flushHeavyUpdate("paste"), 0);
    });

    $("ruText").addEventListener("keydown", (event) => {
      if ($("suggestRu").hidden || S.suggestItems.length === 0) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        S.suggestActive = (S.suggestActive + 1) % S.suggestItems.length;
        App.renderSuggest();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        S.suggestActive = (S.suggestActive - 1 + S.suggestItems.length) % S.suggestItems.length;
        App.renderSuggest();
      } else if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        App.chooseSuggest(S.suggestActive);
      } else if (event.key === "Escape") {
        App.hideSuggest();
      }
    });

    $("ruText").addEventListener("blur", () => {
      setTimeout(App.hideSuggest, 120);
      App.flushHeavyUpdate("blur");
    });

    $("showKcal").addEventListener("change", () => {
      saveStorage(STORAGE_KEYS.showKcal, $("showKcal").checked ? "1" : "0");
      App.updateKcalToggleUi();
      App.updatePreviewMeta();
      App.preview("show-kcal-change").catch(() => {});
      App.refreshActions("show-kcal-change").catch(() => {});
    });

    $("btnKcalToggle")?.addEventListener("click", () => {
      const checkbox = $("showKcal");
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event("change", {bubbles: true}));
    });

    $("debugLogging")?.addEventListener("change", () => {
      App.applyDebugLogging($("debugLogging").checked);
    });

    $("alternatePrintMode").addEventListener("change", () => {
      App.applyAlternatePrintMode($("alternatePrintMode").checked);
    });

    $("autoFormat")?.addEventListener("change", () => {
      saveStorage(STORAGE_KEYS.autoFormat, $("autoFormat").checked ? "1" : "0");
      App.scheduleHeavyUpdate(120, "auto-format");
    });

    if (global.MenuTheme) {
      global.MenuTheme.bindThemeButton("btnTheme");
    } else {
      $("btnTheme").addEventListener("click", () => {
        App.toggleTheme();
      });
    }

    $("printDateMode").addEventListener("change", App.updateDateUi);

    document.querySelectorAll("[data-date-mode]").forEach((button) => {
      button.addEventListener("click", () => App.setDateMode(button.dataset.dateMode));
    });

    $("printDateCustom").addEventListener("change", () => {
      $("printDateMode").value = "custom";
      App.updateDateUi();
    });

    $("btnUndo")?.addEventListener("click", () => {
      if (App.undoRuChange()) {
        App.updateLineCounter();
      }
    });

    $("btnRedo")?.addEventListener("click", () => {
      if (App.redoRuChange()) {
        App.updateLineCounter();
      }
    });

    document.querySelectorAll("[data-preview-lang]").forEach((button) => {
      button.addEventListener("click", () => App.setPreviewLang(button.dataset.previewLang));
    });

    $("btnPreviewPrev")?.addEventListener("click", () => {
      if (S.previewSegmentIndex <= 0) {
        return;
      }
      S.previewSegmentIndex -= 1;
      App.applyPreviewSegment();
    });

    $("btnPreviewNext")?.addEventListener("click", () => {
      const count = App.previewSegments(S.lastPreviewData).length;
      if (S.previewSegmentIndex >= count - 1) {
        return;
      }
      S.previewSegmentIndex += 1;
      App.applyPreviewSegment();
    });

    $("coverSelect")?.addEventListener("change", App.handleCoverSelectChange);

    $("backgroundFile").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (!file) {
        App.syncCoverSelectValue();
        return;
      }
      App.storeBackground(file);
    });

    $("btnClearBackground")?.addEventListener("click", App.clearBackground);

    $("btnCloseReview").addEventListener("click", () => {
      App.setReviewOpen(false);
    });

    $("reviewModal").addEventListener("click", (event) => {
      if (event.target.dataset.closeModal === "1") {
        App.setReviewOpen(false);
      }
    });

    $("btnSettings").addEventListener("click", (event) => {
      event.stopPropagation();
      App.setSettingsOpen($("settingsBar").hidden);
    });

    if ($("btnUsers")) {
      $("btnUsers").addEventListener("click", async () => {
        App.showUserResult("");
        $("usersResult").hidden = true;
        App.setUsersOpen(true);
        await App.loadUsers();
      });

      $("btnCloseUsers").addEventListener("click", () => {
        App.setUsersOpen(false);
      });

      $("usersModal").addEventListener("click", (event) => {
        if (event.target.dataset.closeUsers === "1") {
          App.setUsersOpen(false);
        }
      });

      $("btnRefreshUsers").addEventListener("click", () => {
        App.loadUsers().catch(() => {});
      });

      $("btnGenerateUserPassword").addEventListener("click", () => {
        $("userCreatePassword").value = App.randomPassword();
        App.showUserResult("Пароль сгенерирован. Он будет показан повторно только после создания или сброса.");
      });

      $("btnCreateUser").addEventListener("click", () => {
        App.createUser().catch((error) => toast(error.message));
      });
    }

    if ($("btnCovers")) {
      $("btnCovers").addEventListener("click", async () => {
        App.showCoversResult("");
        App.setCoversOpen(true);
        await App.loadCoversAdmin();
      });

      $("btnCloseCovers")?.addEventListener("click", () => {
        App.setCoversOpen(false);
      });

      $("coversModal")?.addEventListener("click", (event) => {
        if (event.target.dataset.closeCovers === "1") {
          App.setCoversOpen(false);
        }
      });

      $("btnRefreshCovers")?.addEventListener("click", () => {
        App.loadCoversAdmin().catch(() => {});
      });

      $("btnUploadCover")?.addEventListener("click", () => {
        App.uploadCover().catch((error) => toast(error.message));
      });
    }

    document.addEventListener("click", (event) => {
      const panel = $("settingsBar");
      const button = $("btnSettings");
      if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) {
        App.setSettingsOpen(false);
      }
    });

    window.addEventListener("resize", App.positionSuggest);

    $("btnPdf").addEventListener("click", async () => {
      if (S.pdfInFlight) {
        return;
      }

      const useAlternativePrint = App.isAlternatePrintMode();
      const printWindow = useAlternativePrint ? window.open("", "_blank") : null;
      if (printWindow) {
        printWindow.document.write("<!doctype html><title>Печать</title><body>Подготовка печати...</body>");
        printWindow.document.close();
      }

      App.setPdfBusy(true);
      try {
        const issues = await App.collectPdfValidation();
        if (issues.length) {
          if (printWindow && !printWindow.closed) {
            printWindow.close();
          }
          toast(issues[0]);
          App.setPdfBusy(false);
          return;
        }
        if (useAlternativePrint) {
          await App.openAlternativePrintFlow(printWindow);
        } else {
          await App.downloadPdfFlow();
        }
        setTimeout(() => App.setPdfBusy(false), 1800);
      } catch (err) {
        if (printWindow && !printWindow.closed) {
          printWindow.close();
        }
        App.setPdfBusy(false);
        toast(err.message || "Ошибка формирования документа");
      }
    });

    $("btnMissing")?.addEventListener("click", async () => {
      await App.checkAndOpenEditor();
    });
  }

  function boot() {
    const runEditorSaveCheck = IS_ADMIN && loadStorage(STORAGE_KEYS.editorSavedChanges, "") === "1";
    removeStorage(STORAGE_KEYS.editorSavedChanges);
    $("ruText").value = loadStorage(STORAGE_KEYS.lastRu, "");
    $("enText").value = loadStorage(STORAGE_KEYS.lastEn, "");
    removeStorage(STORAGE_KEYS.lastRu);
    removeStorage(STORAGE_KEYS.lastEn);

    $("printDateMode").value = "today";
    $("printDateCustom").value = App.todayDate();
    $("showKcal").checked = loadStorage(STORAGE_KEYS.showKcal, $("showKcal").checked ? "1" : "0") === "1";
    const autoFormat = $("autoFormat");
    if (autoFormat) {
      autoFormat.checked = loadStorage(STORAGE_KEYS.autoFormat, "0") === "1";
    }
    App.updateDateUi();
    App.updateLineCounter();
    App.updateKcalToggleUi();
    if (!loadStorage(STORAGE_KEYS.coverMode, "") && loadStorage(STORAGE_KEYS.pdfBackgroundData, "")) {
      App.saveCoverSelection(COVER_MODE.custom);
    }
    App.restoreBackgroundState();
    App.updatePreviewBackground();
    App.initPreviewPageFit();
    App.applyTheme(loadStorage(STORAGE_KEYS.themeMode, "light"));
    App.applyDebugLogging(IS_ADMIN && loadStorage(STORAGE_KEYS.debugLogging, "0") === "1");
    App.applyAlternatePrintMode(loadStorage(STORAGE_KEYS.alternatePrintMode, "0") === "1");
    App.setSettingsOpen(false);
    App.setReviewOpen(false);
    App.setUsersOpen(false);
    App.setCoversOpen(false);
    App.setPreviewLang("ru");
    App.resetRuHistory($("ruText").value);

    App.preview("page-load").catch(() => {});
    App.refreshActions("page-load").catch(() => {});
    App.preloadSuggestCatalog().catch(() => {});
    App.loadCoversCatalog().catch(() => {});
    if (runEditorSaveCheck) {
      setTimeout(() => App.refreshAfterEditorSave().catch((error) => toast(error.message)), 0);
    }
  }

  App.wireEvents = wireEvents;
  App.boot = boot;

  wireEvents();
  window.addEventListener("load", () => App.boot());
})(window);
