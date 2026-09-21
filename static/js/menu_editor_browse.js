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
    if (state.saveInFlight) {
      return;
    }
    if (state.loadInFlight) {
      state.pendingBrowseReload = true;
      return;
    }
    if (resetPage) {
      state.page = 1;
    }
    state.loadInFlight = true;
    const browseToken = ++state.browseSeq;
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
      if (browseToken !== state.browseSeq) {
        return;
      }
      state.total = Number(data.total || 0);
      state.pageSize = Number(data.limit || state.pageSize);
      const offset = Number(data.offset || 0);
      state.page = state.total ? Math.floor(offset / state.pageSize) + 1 : 1;
      const preserved = E.CAN_EDIT_DATABASE
        ? state.rows.filter((row) => row._isNew || E.isRowDirty(row))
        : [];
      state.rows = (data.dishes || []).map(E.mapDishToRow);
      if (preserved.length) {
        const loadedIds = new Set(state.rows.map((row) => Number(row.id)).filter(Boolean));
        // Keep dirty/new rows that are not on this page (do not drop off-page edits).
        const extras = preserved.filter((row) => row._isNew || !loadedIds.has(Number(row.id)));
        state.rows = state.rows.map((row) => {
          const dirty = preserved.find((item) => item.id && Number(item.id) === Number(row.id) && E.isRowDirty(item));
          return dirty || row;
        });
        state.rows = [...extras, ...state.rows];
      }
      E.render();
    } catch (error) {
      if (browseToken !== state.browseSeq) {
        return;
      }
      C.toast(error.message || "Ошибка загрузки базы");
      E.status(error.message || "Ошибка загрузки базы");
    } finally {
      if (browseToken === state.browseSeq) {
        state.loadInFlight = false;
        E.updatePagerUi();
        if (state.pendingBrowseReload) {
          state.pendingBrowseReload = false;
          loadBrowsePage({resetPage: true}).catch((error) => C.toast(error.message));
        }
      }
    }
  }

  async function loadFocusedRows(items) {
    // Only existing (fix) dishes are fetched by name; missing rows are added locally.
    const fixItems = (items || []).filter((item) => {
      if (!item) {
        return false;
      }
      if (typeof item === "string") {
        return true;
      }
      return item.mode !== "missing";
    });
    const names = [...new Set(fixItems.map((item) => String(item.ru || item || "").trim()).filter(Boolean))];
    if (!names.length) {
      state.rows = [];
      state.total = 0;
      state.browseActive = false;
      E.render();
      return;
    }
    // Server accepts at most 200 names and pages of 100; load in batches.
    const NAMES_CAP = 200;
    const PAGE_SIZE = 100;
    const capped = names.slice(0, NAMES_CAP);
    state.loadInFlight = true;
    state.browseActive = false;
    E.status("Загрузка выбранных блюд...");
    try {
      const loaded = [];
      for (let start = 0; start < capped.length; start += PAGE_SIZE) {
        const chunk = capped.slice(start, start + PAGE_SIZE);
        let offsetPage = 1;
        let chunkTotal = Infinity;
        while ((offsetPage - 1) * PAGE_SIZE < chunkTotal) {
          const data = await fetchDishPage({
            names: chunk.join("|"),
            targetPage: offsetPage,
            size: PAGE_SIZE,
            applyFilters: false,
          });
          chunkTotal = Number(data.total || 0);
          loaded.push(...(data.dishes || []).map(E.mapDishToRow));
          if (!data.dishes?.length) {
            break;
          }
          offsetPage += 1;
        }
      }
      // Deduplicate by id while preserving first-seen order.
      const seen = new Set();
      state.rows = loaded.filter((row) => {
        const id = Number(row.id);
        if (!id || seen.has(id)) {
          return false;
        }
        seen.add(id);
        return true;
      });
      state.total = state.rows.length;
      state.focusedIds = new Set(state.rows.map((row) => Number(row.id)).filter(Boolean));
      state.rows.forEach((row, index) => {
        state.focusedOrder.set(`id:${row.id}`, index);
        const key = E.normalizedKey(row.ru);
        if (key && state.focusedNewKeys) {
          state.focusedNewKeys.delete(key);
        }
      });
      if (names.length > capped.length) {
        C.toast(`Открыто ${state.rows.length} из ${names.length}. Остальные — из базы отдельно.`);
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
