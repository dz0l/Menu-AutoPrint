(function (global) {
  "use strict";

  const App = global.MenuApp;
  const S = App.state;
  const C = global.MenuCommon;
  if (!App || !C) {
    throw new Error("MenuApp core must load before menu_app_users.js");
  }

  const $ = C.$;
  const toast = C.toast;
  const requestJson = C.requestJson;
  const csrfToken = C.csrfToken;

  function randomPassword() {
    const upper = "ABCDEFGHJKLMNPQRSTUVWXYZ";
    const lower = "abcdefghijkmnopqrstuvwxyz";
    const digits = "23456789";
    const special = "!@#$%^&*";
    const alphabet = upper + lower + digits + special;
    const pick = (source) => {
      const bytes = new Uint32Array(1);
      window.crypto.getRandomValues(bytes);
      return source[bytes[0] % source.length];
    };
    const chars = [pick(upper), pick(lower), pick(digits), pick(special)];
    const bytes = new Uint32Array(10);
    window.crypto.getRandomValues(bytes);
    for (const value of bytes) {
      chars.push(alphabet[value % alphabet.length]);
    }
    for (let i = chars.length - 1; i > 0; i -= 1) {
      const bytes = new Uint32Array(1);
      window.crypto.getRandomValues(bytes);
      const j = bytes[0] % (i + 1);
      [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return chars.join("");
  }

  function showUserResult(message) {
    const box = $("usersResult");
    if (!box) {
      return;
    }
    box.textContent = message;
    box.hidden = false;
  }

  function renderUsers(users) {
    const list = $("usersList");
    if (!list) {
      return;
    }

    list.innerHTML = "";
    users.forEach((user) => {
      const item = document.createElement("div");
      item.className = "users-item";

      const meta = document.createElement("div");
      meta.className = "users-meta";
      const roleLabel = user.role === "admin" ? "Admin" : "User";
      const nameEl = document.createElement("strong");
      nameEl.textContent = user.username || "";
      const roleEl = document.createElement("span");
      roleEl.className = "muted";
      roleEl.textContent = `Роль: ${roleLabel}`;
      const passEl = document.createElement("span");
      passEl.className = "muted";
      passEl.textContent = user.must_change_password ? "Требуется смена пароля" : "Пароль обновлён";
      meta.appendChild(nameEl);
      meta.appendChild(roleEl);
      meta.appendChild(passEl);
      item.appendChild(meta);

      const actions = document.createElement("div");
      actions.className = "review-actions";

      if (!user.is_admin) {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.textContent = "Сбросить пароль";
        resetBtn.addEventListener("click", async () => {
          resetBtn.disabled = true;
          try {
            const data = await requestJson(`/api/accounts/users/${user.id}/reset-password`, {
              method: "POST",
              headers: {"X-CSRFToken": csrfToken()},
            });
            showUserResult(`Новый пароль для ${user.username}: ${data.generated_password}`);
            toast(`Пароль пользователя ${user.username} сброшен.`);
            await loadUsers();
          } catch (error) {
            toast(error.message);
          } finally {
            resetBtn.disabled = false;
          }
        });

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "danger-button";
        deleteBtn.textContent = "Удалить";
        deleteBtn.addEventListener("click", async () => {
          if (!window.confirm(`Удалить пользователя ${user.username}?`)) {
            return;
          }
          deleteBtn.disabled = true;
          try {
            await requestJson(`/api/accounts/users/${user.id}`, {
              method: "DELETE",
              headers: {"X-CSRFToken": csrfToken()},
            });
            toast(`Пользователь ${user.username} удалён.`);
            await loadUsers();
          } catch (error) {
            toast(error.message);
          } finally {
            deleteBtn.disabled = false;
          }
        });

        actions.appendChild(resetBtn);
        actions.appendChild(deleteBtn);
      } else {
        const label = document.createElement("span");
        label.className = "muted";
        label.textContent = "Администратор защищён от удаления и сброса";
        actions.appendChild(label);
      }

      item.appendChild(actions);
      list.appendChild(item);
    });
  }

  async function loadUsers() {
    const list = $("usersList");
    if (!list || S.usersLoading) {
      return;
    }

    S.usersLoading = true;
    list.innerHTML = '<div class="muted">Загрузка...</div>';
    try {
      const data = await requestJson("/api/accounts/users");
      renderUsers(data.users || []);
    } catch (error) {
      list.innerHTML = `<div class="danger">${error.message}</div>`;
    } finally {
      S.usersLoading = false;
    }
  }

  async function createUser() {
    const username = $("userCreateName")?.value.trim();
    const password = $("userCreatePassword")?.value.trim();
    if (!username) {
      toast("Укажите имя пользователя.");
      return;
    }

    const btn = $("btnCreateUser");
    btn.disabled = true;
    try {
      const data = await requestJson("/api/accounts/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({username, password}),
      });
      $("userCreateName").value = "";
      $("userCreatePassword").value = "";
      showUserResult(`Пользователь ${data.user.username} создан. Пароль: ${data.generated_password}`);
      toast(`Пользователь ${data.user.username} создан.`);
      await loadUsers();
    } catch (error) {
      toast(error.message);
    } finally {
      btn.disabled = false;
    }
  }

  Object.assign(App, {
    randomPassword,
    showUserResult,
    renderUsers,
    loadUsers,
    createUser,
  });
})(window);
