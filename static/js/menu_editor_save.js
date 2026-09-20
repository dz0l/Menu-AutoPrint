(function (global) {
  "use strict";

  const C = global.MenuCommon;
  const E = global.MenuEditor;
  if (!C || !E) {
    throw new Error("MenuCommon and MenuEditor must load before menu_editor_save");
  }

  const {state} = E;

  async function saveChanges() {
    if (!E.CAN_EDIT_DATABASE || state.saveInFlight) {
      return;
    }

    const payloadRows = E.changedRows();
    const deleteIds = E.changedDeleteIds();
    if (!payloadRows.length && !deleteIds.length) {
      E.status("Нет изменений для сохранения.");
      C.toast("Нет изменений для сохранения.");
      return;
    }

    E.setSaveBusy(true);
    const saveToken = ++state.saveSeq;
    const deletedAtStart = state.deletedRowIds.length;
    E.status(`Пожалуйста, подождите... идёт сохранение (${payloadRows.length}), удаление (${deleteIds.length}).`);
    C.toast("Пожалуйста, подождите... идёт сохранение.");
    try {
      const res = await fetch("/api/dishes/bulk-upsert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": C.csrfToken(),
        },
        body: JSON.stringify({rows: payloadRows, delete_ids: deleteIds}),
      });
      const data = await res.json();
      if (saveToken !== state.saveSeq) {
        return;
      }
      if (!res.ok) {
        const message =
          res.status === 403
            ? E.authRequiredMessage()
            : data.error || "Ошибка сохранения";
        E.status(message);
        C.toast(message);
        return;
      }

      const errorsCount = data.errors?.length || 0;
      E.status(`Создано: ${data.created}, обновлено: ${data.updated}, удалено: ${data.deleted || 0}, ошибок: ${errorsCount}`);
      (data.row_results || []).forEach((item) => {
        const row = payloadRows[item.index];
        if (!row) {
          return;
        }
        row.id = item.id;
        row._isNew = false;
        row._dirty = false;
        row._autoTranslated = false;
        row._original = E.rowSnapshot(row);
        if (state.focusedActive) {
          state.focusedIds = state.focusedIds || new Set();
          state.focusedIds.add(Number(item.id));
          if (row._focusKey && state.focusedNewKeys) {
            state.focusedNewKeys.delete(row._focusKey);
          }
        }
      });
      const deletedOk = new Set(data.deleted_ids || []);
      state.deletedRowIds = state.deletedRowIds.filter((id) => !deletedOk.has(id));
      if (errorsCount > 0) {
        C.toast("Сохранение завершилось с ошибками. Проверьте строки и повторите.");
        E.render();
        return;
      }
      // If user queued more deletes/edits while request was in flight, stay on editor.
      if (state.deletedRowIds.length > Math.max(0, deletedAtStart - deletedOk.size) || E.changedRows().length) {
        C.toast("Сохранение применено. Есть новые локальные изменения — сохраните ещё раз.");
        E.render();
        return;
      }
      if ((data.created || 0) > 0 || (data.updated || 0) > 0 || (data.deleted || 0) > 0) {
        C.saveStorage(E.STORAGE_KEYS.editorSavedChanges, "1");
      }
      location.href = "/";
    } catch (error) {
      if (saveToken !== state.saveSeq) {
        return;
      }
      const message = error?.message || "Ошибка сохранения";
      E.status(message);
      C.toast(message);
    } finally {
      if (saveToken === state.saveSeq) {
        E.setSaveBusy(false);
      }
    }
  }

  Object.assign(E, {
    saveChanges,
  });
})(window);
