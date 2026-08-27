(function () {
  const MOBILE_MQ = window.matchMedia("(max-width: 768px)");

  const $ = (id) => document.getElementById(id);

  function isMobile() {
    return MOBILE_MQ.matches;
  }

  function closeSheets() {
    document.querySelectorAll("[data-mobile-sheet]").forEach((sheet) => {
      sheet.hidden = true;
    });
    const backdrop = $("mobileSheetBackdrop");
    if (backdrop) {
      backdrop.hidden = true;
    }
    document.querySelectorAll(".mobile-tab").forEach((tab) => {
      tab.classList.remove("active");
      if (tab.dataset.mobileTab !== "print") {
        tab.setAttribute("aria-pressed", "false");
      }
    });
    document.body.classList.remove("mobile-sheet-open");
  }

  function openSheet(name) {
    if (!isMobile() || name === "print") {
      return;
    }
    document.querySelectorAll("[data-mobile-sheet]").forEach((sheet) => {
      sheet.hidden = sheet.dataset.mobileSheet !== name;
    });
    const backdrop = $("mobileSheetBackdrop");
    if (backdrop) {
      backdrop.hidden = false;
    }
    document.querySelectorAll(".mobile-tab").forEach((tab) => {
      const active = tab.dataset.mobileTab === name;
      tab.classList.toggle("active", active);
      if (tab.dataset.mobileTab !== "print") {
        tab.setAttribute("aria-pressed", active ? "true" : "false");
      }
    });
    document.body.classList.add("mobile-sheet-open");
    window.MenuIcons?.render(document.getElementById(`mobileSheet${name[0].toUpperCase()}${name.slice(1)}`) || document);
  }

  function placeControls() {
    const mainToolbar = $("mainToolbar");
    const mainSlot = $("mobileMainSlot");
    const mainHome = document.querySelector(".topbar");
    const mainHint = $("mobileMainHint");
    const extras = $("settingsMobileExtras");
    const settingsSlot = $("mobileSettingsSlot");
    const settingsBar = $("settingsBar");

    if (isMobile()) {
      document.body.classList.add("mobile-ui");
      if (mainToolbar && mainSlot && mainToolbar.parentElement !== mainSlot) {
        mainSlot.appendChild(mainToolbar);
      }
      if (mainHint) {
        mainHint.hidden = Boolean(mainToolbar);
      }
      if (extras && settingsSlot && extras.parentElement !== settingsSlot) {
        settingsSlot.appendChild(extras);
      }
      applyMobileCoverRules();
    } else {
      document.body.classList.remove("mobile-ui");
      closeSheets();
      if (mainToolbar && mainHome && mainToolbar.parentElement !== mainHome) {
        const actionsHost = mainHome.querySelector(".brand")?.nextElementSibling;
        // Restore after brand: original block was topbar_actions between brand and nav
        const nav = mainHome.querySelector(".nav");
        if (nav) {
          mainHome.insertBefore(mainToolbar, nav);
        } else {
          mainHome.appendChild(mainToolbar);
        }
      }
      if (extras && settingsBar && extras.parentElement !== settingsBar) {
        const debug = settingsBar.querySelector("#debugLogging")?.closest("label");
        if (debug) {
          settingsBar.insertBefore(extras, debug);
        } else {
          settingsBar.appendChild(extras);
        }
      }
      restoreCustomCoverOption();
    }
    updateViewportPadding();
  }

  function applyMobileCoverRules() {
    const select = $("coverSelect");
    if (!select) {
      return;
    }
    const custom = select.querySelector('option[value="__custom__"]');
    if (custom) {
      custom.hidden = true;
      custom.disabled = true;
    }
    if (select.value === "__custom__") {
      select.value = "";
      select.dispatchEvent(new Event("change", {bubbles: true}));
    }
    if (typeof window.MenuApp?.clearCustomCoverOnMobile === "function") {
      window.MenuApp.clearCustomCoverOnMobile();
    }
  }

  function restoreCustomCoverOption() {
    const select = $("coverSelect");
    if (!select) {
      return;
    }
    const custom = select.querySelector('option[value="__custom__"]');
    if (custom) {
      custom.hidden = false;
      custom.disabled = false;
    }
  }

  function updateViewportPadding() {
    const root = document.documentElement;
    if (!isMobile()) {
      root.style.setProperty("--mobile-keyboard-inset", "0px");
      return;
    }
    const vv = window.visualViewport;
    if (!vv) {
      root.style.setProperty("--mobile-keyboard-inset", "0px");
      return;
    }
    const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    root.style.setProperty("--mobile-keyboard-inset", `${Math.round(inset)}px`);
  }

  function triggerPrint() {
    closeSheets();
    const btn = $("btnPdf");
    if (btn) {
      btn.click();
      return;
    }
    window.location.href = "/";
  }

  function onTabClick(event) {
    const tab = event.currentTarget;
    const name = tab.dataset.mobileTab;
    if (name === "print") {
      triggerPrint();
      return;
    }
    const sheet = document.querySelector(`[data-mobile-sheet="${name}"]`);
    if (sheet && !sheet.hidden && document.body.classList.contains("mobile-sheet-open")) {
      closeSheets();
      return;
    }
    openSheet(name);
  }

  function init() {
    if (!$("mobileTabBar")) {
      return;
    }

    document.querySelectorAll(".mobile-tab").forEach((tab) => {
      tab.addEventListener("click", onTabClick);
    });
    document.querySelectorAll("[data-close-sheet]").forEach((btn) => {
      btn.addEventListener("click", closeSheets);
    });
    $("mobileSheetBackdrop")?.addEventListener("click", closeSheets);

    $("btnMobileTheme")?.addEventListener("click", () => {
      const themeBtn = $("btnTheme");
      if (themeBtn) {
        themeBtn.click();
        return;
      }
      const dark = document.body.classList.toggle("theme-dark");
      document.documentElement.classList.toggle("theme-dark-root", dark);
      try {
        localStorage.setItem("menu_theme_mode", dark ? "dark" : "light");
      } catch (_) {}
    });

    placeControls();
    if (typeof MOBILE_MQ.addEventListener === "function") {
      MOBILE_MQ.addEventListener("change", placeControls);
    } else if (typeof MOBILE_MQ.addListener === "function") {
      MOBILE_MQ.addListener(placeControls);
    }

    window.visualViewport?.addEventListener("resize", updateViewportPadding);
    window.visualViewport?.addEventListener("scroll", updateViewportPadding);
    window.addEventListener("resize", updateViewportPadding);

    window.MenuMobile = {
      isMobile,
      closeSheets,
      openSheet,
      placeControls,
      applyMobileCoverRules,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
