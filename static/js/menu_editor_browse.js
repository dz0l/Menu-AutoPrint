(function (global) {
  "use strict";

  const C = global.MenuCommon;
  const E = global.MenuEditor;
  if (!C || !E) {
    throw new Error("MenuCommon and MenuEditor must load before menu_editor_browse");
  }

  const {state} = E;

  async function fetchDishPage({q = "", names = "", targetPage = state.page, size = state.pageSize, applyFilters = true} = {}) {
    const offset = Math.max(0, (targetPage - 1) * size);
    const params = new URLSearchParams({
      limit: String(size),
      offset: String(offset),
    });
    if (q) {
      params.set("q", q);
    }
    if (names) {
      params.set("names", names);
    }
    if (applyFilters) {
      const flags = E.filterFlags();
      if (flags.missingKcal) {
        params.set("missing_kcal", "1");
      }
      if (flags.missingGr) {
        params.set("missing_gr", "1");
      }
      if (flags.missingGroup) {
        params.set("missing_group", "1");
      }
    }
    const res = await fetch(`/api/dishes/?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Ошибка загрузки базы");
    }
    return data;
  }

  async function loadBrowsePage({resetPage = false} = {}) {
    if (state.loadInFlight) {
      state.pendingBrowseReload = true;
      return;
    }
    if (resetPage) {
      state.page = 1;
    }
    state.loadInFlight = true;
    state.browseActive = true;
    E.clearFocusedMode();
    E.updatePagerUi();
    E.status("Загрузка базы...");
    try {
      const data = await fetchDishPage({
        q: E.searchQueryRaw(),
        targetPage: state.page,
        size: state.pageSize,
      });
      state.total = Number(data.total || 0);
      state.pageSize = Number(data.limit || state.pageSize);
      const offset = Number(data.offset || 0);
      state.page = state.total ? Math.floor(offset / state.pageSize) + 1 : 1;
      const preservedNew = E.CAN_EDIT_DATABASE ? state.rows.filter((row) => row._isNew) : [];
      state.rows = (data.dishes || []).map(E.mapDishToRow);
      if (preservedNew.length) {
        state.rows = [...preservedNew, ...state.rows];
      }
      E.render();
    } catch (error) {
      C.toast(error.message || "Ошибка загрузки базы");
      E.status(error.message || "Ошибка загрузки базы");
    } finally {
      state.loadInFlight = false;
      E.updatePagerUi();
      if (state.pendingBrowseReload) {
        state.pendingBrowseReload = false;
        loadBrowsePage({resetPage: true}).catch((error) => C.toast(error.message));
      }
    }
  }

  async function loadFocusedRows(items) {
    const names = [...new Set(items.map((item) => String(item.ru || item || "").trim()).filter(Boolean))];
    if (!names.length) {
      state.rows = [];
      state.total = 0;
      state.browseActive = false;
      E.render();
      return;
    }
    state.loadInFlight = true;
    state.browseActive = false;
    E.status("Загрузка выбранных блюд...");
    try {
      const data = await fetchDishPage({
        names: names.join("|"),
        targetPage: 1,
        size: Math.min(100, Math.max(names.length, 20)),
        applyFilters: false,
      });
      state.total = Number(data.total || 0);
      state.rows = (data.dishes || []).map(E.mapDishToRow);
      state.focusedIds = new Set(state.rows.map((row) => Number(row.id)).filter(Boolean));
      state.rows.forEach((row, index) => {
        state.focusedOrder.set(`id:${row.id}`, index);
        const key = E.normalizedKey(row.ru);
        if (key && state.focusedNewKeys) {
          state.focusedNewKeys.delete(key);
        }
      });
      if (names.length > 100) {
        C.toast(`Загружено первых ${state.rows.length} из ${names.length}. Остальные откройте из базы отдельно.`);
      }
      E.render();
    } catch (error) {
      C.toast(error.message || "Ошибка загрузки");
      E.status(error.message || "Ошибка загрузки");
    } finally {
      state.loadInFlight = false;
      E.updatePagerUi();
    }
  }

  function scheduleBrowseReload() {
    if (state.searchTimer) {
      clearTimeout(state.searchTimer);
    }
    state.searchTimer = setTimeout(() => {
      if (!E.guardUnsaved("обновление списка")) {
        return;
      }
      loadBrowsePage({resetPage: true}).catch((error) => C.toast(error.message));
    }, 280);
  }

  Object.assign(E, {
    fetchDishPage,
    loadBrowsePage,
    loadFocusedRows,
    scheduleBrowseReload,
  });
})(window);
