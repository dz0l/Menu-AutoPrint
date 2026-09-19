(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_covers.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const requestJson = C.requestJson;
  const loadStorage = C.loadStorage;
  const saveStorage = C.saveStorage;
  const removeStorage = C.removeStorage;
  const csrfToken = C.csrfToken;
  const {STORAGE_KEYS, COVER_MODE} = App;

  function getCoverSelection() {
    const mode = loadStorage(STORAGE_KEYS.coverMode, COVER_MODE.none);
    const coverIdRaw = loadStorage(STORAGE_KEYS.coverId, "");
    const coverId = Number.parseInt(coverIdRaw, 10);
    return {
      mode: mode === COVER_MODE.custom || mode === COVER_MODE.cover ? mode : COVER_MODE.none,
      coverId: Number.isFinite(coverId) && coverId > 0 ? coverId : null,
    };
  }

  function saveCoverSelection(mode, coverId = null) {
    saveStorage(STORAGE_KEYS.coverMode, mode || COVER_MODE.none);
    if (mode === COVER_MODE.cover && coverId) {
      saveStorage(STORAGE_KEYS.coverId, String(coverId));
    } else {
      removeStorage(STORAGE_KEYS.coverId);
    }
  }

  function restoreBackgroundState() {
    const selection = getCoverSelection();
    const hasBackground =
      (selection.mode === COVER_MODE.cover && Boolean(selection.coverId)) ||
      (selection.mode === COVER_MODE.custom && Boolean(loadStorage(STORAGE_KEYS.pdfBackgroundData, "")));
    const clearButton = $("btnClearBackground");
    if (clearButton) {
      clearButton.hidden = !hasBackground;
      clearButton.disabled = !hasBackground;
    }
    const select = $("coverSelect");
    if (select) {
      select.classList.toggle("active", hasBackground);
    }
  }

  function syncCoverSelectValue() {
    const select = $("coverSelect");
    if (!select) {
      return;
    }
    const selection = getCoverSelection();
    let value = "";
    if (selection.mode === COVER_MODE.custom && loadStorage(STORAGE_KEYS.pdfBackgroundData, "")) {
      value = "__custom__";
    } else if (selection.mode === COVER_MODE.cover && selection.coverId) {
      value = String(selection.coverId);
    }
    S.coverSelectQuiet = true;
    if (value && [...select.options].some((item) => item.value === value)) {
      select.value = value;
    } else if (selection.mode === COVER_MODE.cover && selection.coverId) {
      // Cover was deleted or catalog not ready yet — keep placeholder until options load.
      select.value = "";
    } else {
      select.value = "";
    }
    S.previousCoverSelectValue = select.value || "";
    S.coverSelectQuiet = false;
  }

  function renderCoverSelectOptions() {
    const select = $("coverSelect");
    if (!select) {
      return;
    }
    select.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Подложка:";
    select.appendChild(empty);

    const hideCustom = Boolean(global.MenuMobile?.isMobile?.());
    if (!hideCustom) {
      const custom = document.createElement("option");
      custom.value = "__custom__";
      custom.textContent = "Своя";
      select.appendChild(custom);
    }

    S.coversCatalog
      .slice()
      .sort((left, right) => String(left.location_name || "").localeCompare(String(right.location_name || ""), "ru"))
      .forEach((cover) => {
        const option = document.createElement("option");
        option.value = String(cover.id);
        option.textContent = cover.location_name;
        select.appendChild(option);
      });

    // Always restore saved selection after options are rebuilt.
    syncCoverSelectValue();
    if (hideCustom && getCoverSelection().mode === COVER_MODE.custom) {
      clearBackground();
    }
  }

  async function loadCoversCatalog() {
    try {
      const data = await requestJson("/api/menu/covers");
      S.coversCatalog = data.covers || [];
    } catch (error) {
      S.coversCatalog = [];
      App.debugWarn("covers:list:error", {error: error.message});
    }
    renderCoverSelectOptions();
    restoreBackgroundState();
    App.updatePreviewBackground();
  }

  function storeBackground(file) {
    if (!file) {
      syncCoverSelectValue();
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        toast("Не удалось прочитать файл подложки.");
        syncCoverSelectValue();
        return;
      }
      if (reader.result.length > 4_500_000) {
        toast("Подложка слишком большая. Выберите изображение меньше 3 МБ.");
        syncCoverSelectValue();
        return;
      }
      saveStorage(STORAGE_KEYS.pdfBackgroundName, file.name);
      if (!saveStorage(STORAGE_KEYS.pdfBackgroundData, reader.result)) {
        toast("Не удалось сохранить подложку в браузере. Уменьшите файл или отключите режим приватного просмотра.");
        syncCoverSelectValue();
        return;
      }
      saveCoverSelection(COVER_MODE.custom);
      restoreBackgroundState();
      App.updatePreviewBackground();
      syncCoverSelectValue();
      toast(`Подложка выбрана: ${file.name}`);
    };
    reader.readAsDataURL(file);
  }

  function clearBackground() {
    removeStorage(STORAGE_KEYS.pdfBackgroundName);
    removeStorage(STORAGE_KEYS.pdfBackgroundData);
    saveCoverSelection(COVER_MODE.none);
    const input = $("backgroundFile");
    if (input) {
      input.value = "";
    }
    restoreBackgroundState();
    App.updatePreviewBackground();
    syncCoverSelectValue();
    toast("Подложка очищена");
  }

  function handleCoverSelectChange() {
    if (S.coverSelectQuiet) {
      return;
    }
    const select = $("coverSelect");
    if (!select) {
      return;
    }
    const value = select.value;
    if (value === "__custom__") {
      S.previousCoverSelectValue = value;
      $("backgroundFile")?.click();
      return;
    }
    if (!value) {
      clearBackground();
      return;
    }
    const coverId = Number.parseInt(value, 10);
    if (!Number.isFinite(coverId)) {
      syncCoverSelectValue();
      return;
    }
    removeStorage(STORAGE_KEYS.pdfBackgroundName);
    removeStorage(STORAGE_KEYS.pdfBackgroundData);
    saveCoverSelection(COVER_MODE.cover, coverId);
    S.previousCoverSelectValue = value;
    restoreBackgroundState();
    App.updatePreviewBackground();
    toast("Подложка выбрана");
  }

  function showCoversResult(message) {
    const box = $("coversResult");
    if (!box) {
      return;
    }
    box.textContent = message;
    box.hidden = !message;
  }

  function renderCoversAdminList(covers) {
    const list = $("coversList");
    if (!list) {
      return;
    }
    list.innerHTML = "";
    const sorted = (covers || [])
      .slice()
      .sort((left, right) => String(left.location_name || "").localeCompare(String(right.location_name || ""), "ru"));

    if (!sorted.length) {
      list.innerHTML = '<tr><td colspan="2" class="muted">Пока нет загруженных подложек.</td></tr>';
      return;
    }

    sorted.forEach((cover) => {
      const row = document.createElement("tr");
      row.dataset.coverId = String(cover.id);

      const coverCell = document.createElement("td");
      coverCell.className = "cover-info-cell";
      const coverWrap = document.createElement("div");
      coverWrap.className = "cover-info-wrap";

      const fileLine = document.createElement("span");
      fileLine.className = "cover-file-line";
      fileLine.textContent = cover.original_filename || "—";
      fileLine.title = cover.original_filename || "";

      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "cover-name-input";
      nameInput.value = cover.location_name || "";
      nameInput.maxLength = 128;
      nameInput.dataset.original = cover.location_name || "";
      nameInput.setAttribute("aria-label", "Название локации");
      nameInput.placeholder = "Локация";

      coverWrap.appendChild(fileLine);
      coverWrap.appendChild(nameInput);
      coverCell.appendChild(coverWrap);
      row.appendChild(coverCell);

      const actionCell = document.createElement("td");
      actionCell.className = "covers-actions-cell";
      const actions = document.createElement("div");
      actions.className = "covers-actions";

      const applyBtn = document.createElement("button");
      applyBtn.type = "button";
      applyBtn.className = "button";
      applyBtn.textContent = "Применить";
      applyBtn.hidden = true;
      applyBtn.addEventListener("click", async () => {
        applyBtn.disabled = true;
        try {
          await requestJson(`/api/menu/covers/${cover.id}`, {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken(),
            },
            body: JSON.stringify({location_name: nameInput.value}),
          });
          toast("Название подложки обновлено.");
          await loadCoversAdmin();
          await loadCoversCatalog();
        } catch (error) {
          toast(error.message);
        } finally {
          applyBtn.disabled = false;
        }
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "danger-button";
      deleteBtn.textContent = "Удалить";
      deleteBtn.addEventListener("click", async () => {
        if (!window.confirm(`Удалить подложку «${cover.location_name}»?`)) {
          return;
        }
        deleteBtn.disabled = true;
        try {
          await requestJson(`/api/menu/covers/${cover.id}`, {
            method: "DELETE",
            headers: {"X-CSRFToken": csrfToken()},
          });
          const selection = getCoverSelection();
          if (selection.mode === COVER_MODE.cover && selection.coverId === cover.id) {
            clearBackground();
          }
          toast("Подложка удалена.");
          await loadCoversAdmin();
          await loadCoversCatalog();
        } catch (error) {
          toast(error.message);
        } finally {
          deleteBtn.disabled = false;
        }
      });

      nameInput.addEventListener("input", () => {
        const changed = nameInput.value.trim() !== String(nameInput.dataset.original || "").trim();
        applyBtn.hidden = !changed;
      });

      actions.appendChild(applyBtn);
      actions.appendChild(deleteBtn);
      actionCell.appendChild(actions);
      row.appendChild(actionCell);
      list.appendChild(row);
    });
  }

  async function loadCoversAdmin() {
    const list = $("coversList");
    if (!list || S.coversLoading) {
      return;
    }
    S.coversLoading = true;
    list.innerHTML = '<tr><td colspan="2" class="muted">Загрузка...</td></tr>';
    try {
      const data = await requestJson("/api/menu/covers");
      renderCoversAdminList(data.covers || []);
    } catch (error) {
      list.innerHTML = `<tr><td colspan="2" class="danger">${error.message}</td></tr>`;
    } finally {
      S.coversLoading = false;
    }
  }

  async function uploadCover() {
    const fileInput = $("coverUploadFile");
    const nameInput = $("coverUploadName");
    const file = fileInput?.files?.[0];
    const locationName = nameInput?.value.trim() || "";
    if (!file || !locationName) {
      toast("Нужны файл подложки и название.");
      return;
    }
    if (file.size > 3 * 1024 * 1024) {
      toast("Подложка слишком большая. Выберите изображение меньше 3 МБ.");
      return;
    }

    const btn = $("btnUploadCover");
    btn.disabled = true;
    const body = new FormData();
    body.append("file", file);
    body.append("location_name", locationName);
    try {
      await requestJson("/api/menu/covers", {
        method: "POST",
        headers: {"X-CSRFToken": csrfToken()},
        body,
      });
      if (fileInput) {
        fileInput.value = "";
      }
      if (nameInput) {
        nameInput.value = "";
      }
      showCoversResult(`Подложка «${locationName}» загружена.`);
      toast("Подложка загружена.");
      await loadCoversAdmin();
      await loadCoversCatalog();
    } catch (error) {
      toast(error.message);
    } finally {
      btn.disabled = false;
    }
  }

  Object.assign(App, {
    getCoverSelection,
    saveCoverSelection,
    restoreBackgroundState,
    syncCoverSelectValue,
    renderCoverSelectOptions,
    loadCoversCatalog,
    storeBackground,
    clearBackground,
    handleCoverSelectChange,
    showCoversResult,
    renderCoversAdminList,
    loadCoversAdmin,
    uploadCover,
  });
})(window);
