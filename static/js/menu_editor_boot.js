(function (global) {
  "use strict";

  const C = global.MenuCommon;
  const E = global.MenuEditor;
  if (!C || !E) {
    throw new Error("MenuCommon and MenuEditor must load before menu_editor_boot");
  }

  const {state} = E;

  C.$("btnAddRow")?.addEventListener("click", () => {
    if (!E.CAN_EDIT_DATABASE) {
      return;
    }
    E.addBlankRow();
  });

  C.$("searchRu")?.addEventListener("input", () => {
    if (E.isFocusedMode()) {
      return;
    }
    E.scheduleBrowseReload();
  });

  ["filterMissingKcal", "filterMissingGr", "filterMissingGroup"].forEach((id) => {
    C.$(id)?.addEventListener("change", () => {
      if (E.isFocusedMode()) {
        return;
      }
      if (!E.guardUnsaved("смену фильтра")) {
        const box = C.$(id);
        if (box) {
          box.checked = !box.checked;
        }
        return;
      }
      E.loadBrowsePage({resetPage: true}).catch((error) => C.toast(error.message));
    });
  });

  C.$("btnResetFilters")?.addEventListener("click", async () => {
    if (!E.guardUnsaved("сброс фильтров")) {
      return;
    }
    if (C.$("searchRu")) {
      C.$("searchRu").value = "";
    }
    ["filterMissingKcal", "filterMissingGr", "filterMissingGroup"].forEach((id) => {
      if (C.$(id)) {
        C.$(id).checked = false;
      }
    });
    state.page = 1;
    await E.loadBrowsePage({resetPage: true});
  });

  C.$("btnPagePrev")?.addEventListener("click", async () => {
    if (state.page <= 1 || !E.guardUnsaved("переход на страницу")) {
      return;
    }
    state.page -= 1;
    await E.loadBrowsePage();
  });

  C.$("btnPageNext")?.addEventListener("click", async () => {
    if (state.page >= E.pageCount() || !E.guardUnsaved("переход на страницу")) {
      return;
    }
    state.page += 1;
    await E.loadBrowsePage();
  });

  document.querySelectorAll(".page-size-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextSize = Number(button.dataset.pageSize);
      if (!E.PAGE_SIZES.includes(nextSize) || nextSize === state.pageSize) {
        return;
      }
      if (!E.guardUnsaved("смену числа строк")) {
        return;
      }
      state.pageSize = nextSize;
      C.saveStorage(E.STORAGE_KEYS.pageSize, String(state.pageSize));
      E.updatePageSizeButtons();
      await E.loadBrowsePage({resetPage: true});
    });
  });

  if (C.$("btnTranslateAll")) {
    C.$("btnTranslateAll").addEventListener("click", () => {
      E.translateRows(E.translatableVisibleRows(), "bulk").catch((error) => C.toast(error.message));
    });
  }

  C.$("btnSave")?.addEventListener("click", () => {
    E.saveChanges().catch((error) => C.toast(error.message));
  });

  window.addEventListener("load", async () => {
    state.pageSize = E.loadPageSize();
    E.updatePageSizeButtons();

    const incomingRaw = C.loadStorageJson(E.STORAGE_KEYS.editorRows, []);
    const incoming = Array.isArray(incomingRaw) ? incomingRaw.filter((item) => item && item.ru) : [];
    C.removeStorage(E.STORAGE_KEYS.editorRows);

    if (incoming.length && E.CAN_EDIT_DATABASE) {
      const missing = incoming.filter((item) => item.mode === "missing").map((item) => item.ru);
      const hasFixRows = incoming.some((item) => item.mode === "fix");
      E.setFocusedRows(incoming);
      state.browseActive = false;
      E.applyLayoutMode();

      if (hasFixRows) {
        await E.loadFocusedRows(incoming.filter((item) => item.mode === "fix"));
      } else {
        state.rows = [];
        state.total = 0;
      }
      const added = E.addRowsFromLines(missing);
      E.statusText(`К редактированию: ${incoming.length}, новых строк: ${added}`);
      return;
    }

    E.clearFocusedMode();
    await E.loadBrowsePage({resetPage: true});
    if (!E.CAN_EDIT_DATABASE) {
      E.status("Просмотр базы. Редактирование доступно только администратору. Можно экспортировать CSV.");
    }
  });
})(window);
