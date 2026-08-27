(function () {
  const icons = {
    "image-plus": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/><path d="m5 17 4.5-4.5 3 3 2-2L19 18"/><path d="M8.5 9.5h.01"/><path d="M16 6v6"/><path d="M13 9h6"/>',
    "image-off": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h9.5"/><path d="M20 14.5v4a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-13"/><path d="m5 17 4.5-4.5 2 2"/><path d="m14 14 1-1 4 5"/><path d="M3 3l18 18"/>',
    database: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    "database-zap": '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.2 1.5 2.2 3.8 2.7"/><path d="M5 11v6c0 1.7 3.1 3 7 3 .7 0 1.4 0 2-.1"/><path d="m16 12-3 5h4l-2 5 5-7h-4z"/>',
    "moon-star": '<path d="M20 15.5A8 8 0 0 1 8.5 4a7 7 0 1 0 11.5 11.5"/><path d="M17 3v4"/><path d="M15 5h4"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/>',
    settings: '<path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.2a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 0 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4.6 15a1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.2a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 0 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9 4.6a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.2a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1A1.6 1.6 0 0 0 19.4 9c.2.6.8 1 1.5 1h.1a2 2 0 0 1 0 4h-.2c-.6 0-1.2.4-1.4 1"/>',
    "spell-check": '<path d="m6 16 6-12 6 12"/><path d="M8 12h8"/><path d="m5 20 2 2 4-4"/>',
    scale: '<path d="m16 16 3-8 3 8"/><path d="M2 16h6"/><path d="M16 16h6"/><path d="M5 16 8 8l3 8"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 8h18"/>',
    printer: '<path d="M6 9V4h12v5"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v6H6z"/><path d="M18 12h.01"/>',
    "undo-2": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-2"/>',
    "redo-2": '<path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h2"/>',
    login: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    archive: '<path d="M4 6h16v3H4z"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9"/><path d="M10 13h4"/>',
    calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><path d="M3 10h18"/><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  };

  function render(root) {
    (root || document).querySelectorAll("[data-ui-icon]").forEach((target) => {
      const name = target.getAttribute("data-ui-icon");
      if (!icons[name]) {
        return;
      }
      target.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[name]}</svg>`;
    });
  }

  window.MenuIcons = {render};

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => render(document));
  } else {
    render(document);
  }
})();
