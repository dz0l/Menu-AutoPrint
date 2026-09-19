(function (global) {
  "use strict";

  const THEME_KEY = "menu_theme_mode";
  const DEBUG_KEY = "menu_debug_logging";

  function $(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    return document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
  }

  function loadStorage(key, fallback = "") {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  }

  function saveStorage(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  }

  function removeStorage(key) {
    try {
      localStorage.removeItem(key);
    } catch {}
  }

  function loadStorageJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) {
        return fallback;
      }
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function toast(message) {
    const box = $("toast");
    if (!box) {
      return;
    }
    box.textContent = message;
    box.hidden = false;
    setTimeout(() => {
      box.hidden = true;
    }, 5200);
  }

  function lines(value) {
    return (value || "")
      .replace(/\u00a0/g, " ")
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function isDebugLoggingEnabled() {
    return loadStorage(DEBUG_KEY, "0") === "1";
  }

  function debugLog(prefix, event, data = {}) {
    if (!isDebugLoggingEnabled()) {
      return;
    }
    console.info(prefix, event, {
      at: new Date().toISOString(),
      ...data,
    });
  }

  function debugWarn(prefix, event, data = {}) {
    if (!isDebugLoggingEnabled()) {
      return;
    }
    console.warn(prefix, event, {
      at: new Date().toISOString(),
      ...data,
    });
  }

  async function postJson(url, payload, options = {}) {
    const started = performance.now();
    const log = options.log || null;
    const logPrefix = options.logPrefix || "[MenuLog]";

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify(payload),
        signal: options.signal,
      });
      const durationMs = Math.round(performance.now() - started);
      if (!res.ok) {
        const body = await res.text();
        if (log) {
          debugWarn(logPrefix, "request:error", {
            name: log.name,
            reason: log.reason,
            seq: log.seq,
            url,
            status: res.status,
            durationMs,
            body: body.slice(0, 500),
          });
        }
        let message = body || "Request failed";
        try {
          const parsed = JSON.parse(body);
          if (parsed && typeof parsed === "object") {
            message = parsed.error || (parsed.errors || []).join("\n") || message;
          }
        } catch {
          // keep raw body text
        }
        throw new Error(message);
      }
      const data = await res.json();
      return data;
    } catch (error) {
      if (log) {
        const event = error.name === "AbortError" ? "request:abort" : "request:fail";
        const logger = error.name === "AbortError" ? debugLog : debugWarn;
        logger(logPrefix, event, {
          name: log.name,
          reason: log.reason,
          seq: log.seq,
          url,
          durationMs: Math.round(performance.now() - started),
          error: error.message,
        });
      }
      throw error;
    }
  }

  async function requestJson(url, options = {}) {
    const res = await fetch(url, options);
    const isJson = (res.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await res.json() : await res.text();
    if (!res.ok) {
      if (typeof data === "object" && data) {
        throw new Error(data.error || (data.errors || []).join("\n") || "Request failed");
      }
      throw new Error(String(data || "Request failed"));
    }
    return data;
  }

  global.MenuCommon = {
    THEME_KEY,
    DEBUG_KEY,
    $,
    csrfToken,
    loadStorage,
    saveStorage,
    removeStorage,
    loadStorageJson,
    toast,
    lines,
    isDebugLoggingEnabled,
    debugLog,
    debugWarn,
    postJson,
    requestJson,
  };
})(window);
