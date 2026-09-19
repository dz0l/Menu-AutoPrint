(function (global) {
  "use strict";

  const C = global.MenuCommon;
  if (!C) {
    throw new Error("MenuCommon must load before MenuTheme");
  }

  function themeIconName(theme) {
    return theme === "dark" ? "sun" : "moon-star";
  }

  function currentTheme() {
    return document.body.classList.contains("theme-dark") ? "dark" : "light";
  }

  function applyTheme(theme) {
    const mode = theme === "dark" ? "dark" : "light";
    document.body.classList.toggle("theme-dark", mode === "dark");
    document.documentElement.classList.toggle("theme-dark-root", mode === "dark");
    const button = C.$("btnTheme");
    if (button) {
      const icon = button.querySelector("[data-ui-icon]");
      if (icon) {
        icon.setAttribute("data-ui-icon", themeIconName(mode));
        global.MenuIcons?.render(button);
      }
      button.title = mode === "dark" ? "Светлая тема" : "Тёмная тема";
      button.setAttribute("aria-label", button.title);
    }
    C.saveStorage(C.THEME_KEY, mode);
  }

  function toggleTheme() {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  }

  function bindThemeButton(buttonId) {
    const button = C.$(buttonId || "btnTheme");
    if (!button || button.dataset.themeBound === "1") {
      return;
    }
    button.dataset.themeBound = "1";
    button.addEventListener("click", () => toggleTheme());
  }

  function initFromStorage() {
    applyTheme(C.loadStorage(C.THEME_KEY, "light"));
  }

  global.MenuTheme = {
    themeIconName,
    currentTheme,
    applyTheme,
    toggleTheme,
    bindThemeButton,
    initFromStorage,
  };
})(window);
