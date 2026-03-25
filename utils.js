/* utils.js — общий модуль утилит для проекта
 * Формат: ES Module (import * as U from './utils.js')
 * Содержит:
 *  - Версия/фиче-флаги
 *  - Нормализация/токенизация/сходство
 *  - Дебаунс
 *  - CSV-парсер с кавычками и ;, экспорт в CSV
 *  - Индексы поиска по базе (RU/EN)
 *  - Подсказки: позиционирование по каретке, ARIA listbox
 *  - Тосты/логгер/микрометрики
 *  - Смарт-вставка (анализ уверенности)
 *  - Горячие клавиши и темы
 */

/* ===========================
   Версия и фиче-флаги
   =========================== */
export const APP_VERSION = "v1.2.3";

const FF_KEY = "menu_feature_flags";
const DEFAULT_FLAGS = Object.freeze({
  autoPreview: true,
  useIndexes: true,
  ariaHints: true,
  smartPaste: true,
  toasts: true,
  perfMetrics: true
});

export function getFlags() {
  try {
    const s = localStorage.getItem(FF_KEY);
    if (!s) return { ...DEFAULT_FLAGS };
    return { ...DEFAULT_FLAGS, ...JSON.parse(s) };
  } catch {
    return { ...DEFAULT_FLAGS };
  }
}
export function setFlags(next) {
  try { localStorage.setItem(FF_KEY, JSON.stringify(next)); } catch {}
}
export function flag(name) {
  const f = getFlags();
  return !!f[name];
}

/* ===========================
   Хранилище настроек (с версионированием)
   =========================== */

/* ===========================
   Тосты и логгер
   =========================== */
export function showToast(msg, type = "info", timeout = 2600) {
  if (!flag("toasts")) return;
  let c = document.getElementById("toast-container");
  if (!c) {
    c = document.createElement("div");
    c.id = "toast-container";
    c.style.position = "fixed";
    c.style.bottom = "20px";
    c.style.right = "20px";
    c.style.zIndex = "9999";
    c.style.display = "flex";
    c.style.flexDirection = "column";
    c.style.alignItems = "flex-end";
    document.body.appendChild(c);
  }
  const t = document.createElement("div");
  t.role = "status";
  t.ariaLive = "polite";
  t.textContent = msg;
  t.style.background = type === "error" ? "rgba(190,40,40,.92)"
                    : type === "warn" ? "rgba(200,150,20,.92)"
                    : "rgba(0,0,0,.85)";
  t.style.color = "#fff";
  t.style.padding = "8px 12px";
  t.style.marginTop = "8px";
  t.style.borderRadius = "8px";
  t.style.fontSize = "14px";
  t.style.boxShadow = "0 6px 18px rgba(0,0,0,.25)";
  t.style.maxWidth = "56ch";
  t.style.backdropFilter = "blur(2px)";
  c.appendChild(t);
  setTimeout(()=>t.remove(), timeout);
}

export const Log = Object.freeze({
  info: (...a)=>{ console.log("[INFO]", ...a); },
  warn: (...a)=>{ console.warn("[WARN]", ...a); },
  error:(...a)=>{ console.error("[ERROR]", ...a); },
  perf: (...a)=>{ if(flag("perfMetrics")) console.log("[PERF]", ...a); }
});

/* ===========================
   Микро-метрики (performance marks)
   =========================== */
export function withPerf(label, fn) {
  if (!flag("perfMetrics")) return fn();
  const id = `${label}-${Date.now()}`;
  performance.mark(id + ":start");
  try {
    const res = fn();
    if (res && typeof res.then === "function") {
      return res.finally(() => {
        performance.mark(id + ":end");
        performance.measure(label, id + ":start", id + ":end");
        const [m] = performance.getEntriesByName(label).slice(-1);
        Log.perf(label, Math.round(m.duration) + " ms");
      });
    }
    return res;
  } finally {
    performance.mark(id + ":end");
    performance.measure(label, id + ":start", id + ":end");
    const [m] = performance.getEntriesByName(label).slice(-1);
    Log.perf(label, Math.round(m.duration) + " ms");
  }
}

/* ===========================
   Дебаунс / Троттл / LRU
   =========================== */
export function debounce(fn, ms = 150) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(()=>fn(...args), ms);
  };
}

/* ===========================
   Нормализация / токенизация / сходство
   =========================== */
export function cleanName(s){
  return (s||'')
    .replace(/\u00A0/g,' ')
    .replace(/[•\-—–]/g,' ')
    .replace(/[“”„«»"'’`]/g,'')
    .replace(/\s+/g,' ')
    .trim()
    .toLowerCase();
}
export function escHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
const STOP_WORDS_RU = new Set(['с','со','и','из','на','в','во','от','по','для','над','под','без','при','к','ко']);
export function normalizeRU(s){
  if(!s) return '';
  let x = String(s).toLowerCase().trim();
  x = x.replace(/[«»„”"’'`]/g,'');
  x = x.replace(/[.]+/g,'');
  x = x.replace(/[–—−]+/g,'-');
  x = x.replace(/\s+/g,' ');
  x = x.replace(/\s*-\s*/g,'-');
  return x.trim();
}
export function stemWordRU(w){
  let s = w
    .replace(/(ыми|ими|ого|ему|ому|ее|ая|ое|ые|ий|ый|ой|ых|ым|ою|ой|ому|его)$/,'')
    .replace(/(ами|ями|ев|ов|ом|ем|ам|ям|ах|ях|ей|ью|ия|ие|ий|ию|ии)$/,'')
    .replace(/(у|ю|а|я|е|ы|и|о)$/,'');
  if (s.length > 4) {
    if (/н$/.test(s)) s = s.slice(0, -1);
    s = s.replace(/(ческ|ск)$/, '');
  }
  return s;
}
export function tokensBagRU(s){
  const out = new Set();
  normalizeRU(s).split(/[\s-]+/).filter(Boolean).forEach(t=>{
    if (STOP_WORDS_RU.has(t)) return;
    const base = stemWordRU(t);
    if (!base) return;
    out.add(base);
    if (base.length > 3) {
      if (base.endsWith('н')) out.add(base.slice(0,-1));
      if (base.endsWith('ск')) out.add(base.slice(0,-2));
      if (base.endsWith('ческ')) out.add(base.slice(0,-4));
    }
  });
  return Array.from(out);
}
export function tokensSortedRU(s){
  const t = normalizeRU(s).split(/[\s-]+/).filter(Boolean);
  return t.sort().join(' ');
}
export function jaccardSet(A, B){
  let inter = 0;
  for(const x of A){ if(B.has(x)) inter++; }
  const union = A.size + B.size - inter;
  return union ? inter / union : 0;
}
export function similarityRU(a, b){
  const A = new Set(tokensBagRU(a)), B = new Set(tokensBagRU(b));
  return jaccardSet(A, B);
}
/* ===========================
   CSV парсер и генератор
   =========================== */
export function parseCsvSemicolon(text) {
  const rows = [];
  let i = 0, field = '', row = [], inQ = false;
  const s = (text || '').replace(/^\uFEFF/, '');

  while (i < s.length) {
    const ch = s[i];
    if (inQ) {
      if (ch === '"') {
        if (s[i+1] === '"') { field += '"'; i += 2; continue; }
        inQ = false; i++; continue;
      } else { field += ch; i++; continue; }
    } else {
      if (ch === '"') { inQ = true; i++; continue; }
      if (ch === ';') { row.push(field); field = ''; i++; continue; }
      if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && s[i+1] === '\n') i++;
        row.push(field); rows.push(row);
        field = ''; row = []; i++; continue;
      }
      field += ch; i++; continue;
    }
  }
  row.push(field); rows.push(row);

  const norm = (v) => (v ?? '').toString().trim().toLowerCase();
  const HEADER_SETS = [
    ['ru', 'en', 'kcal', 'catru', 'caten', 'gr'],
    ['блюдо_ru', 'dish_en', 'ккал', 'категория_ru', 'category_en', 'gr']
  ];
  const isHeaderRow = (r) => {
    if (!Array.isArray(r) || r.length < 2) return false;
    const head = r.slice(0, 6).map(norm);
    return HEADER_SETS.some(h => h.every((v, i) => head[i] === v));
  };

  return rows.filter(r => !isHeaderRow(r));
}
export function toCsvSemicolon(rows, header = null) {
  const esc = v => {
    const s = (v ?? '').toString();
    const need = /[;\r\n"]/.test(s);
    const body = s.replace(/"/g,'""');
    return need ? `"${body}"` : body;
  };
  const lines = [];
  if (header) lines.push(header.map(esc).join(';'));
  for (const r of rows) lines.push(r.map(esc).join(';'));
  return lines.join('\n');
}

/* ===========================
   Индексы по базе и группы
   =========================== */
export function buildNameIndexes(rows) {
  const nameToKcalRU = new Map();
  const nameToKcalEN = new Map();
  const nameToGrRU   = new Map();
  const nameToGrEN   = new Map();
  const RU2EN = new Map();
  const EN2RU = new Map();
  const RU_NAMES = [];
  const EN_NAMES = [];

  for (const d of rows) {
    const nru = cleanName(d.ru);
    const nen = cleanName(d.en);
    if (d.ru) {
      nameToKcalRU.set(nru, d.kcal);
      if (d.gr !== undefined) nameToGrRU.set(nru, d.gr);
      RU2EN.set(nru, d.en);
      RU_NAMES.push(d.ru);
    }
    if (d.en) {
      nameToKcalEN.set(nen, d.kcal);
      if (d.gr !== undefined) nameToGrEN.set(nen, d.gr);
      EN2RU.set(nen, d.ru);
      EN_NAMES.push(d.en);
    }
  }
  return {
    nameToKcalRU, nameToKcalEN,
    nameToGrRU,   nameToGrEN,
    RU2EN, EN2RU, RU_NAMES, EN_NAMES
  };
}


/* ===========================
   Подсказки: позиция под кареткой и ARIA listbox
   =========================== */
export function ensureMirror() {
  let mirror = document.getElementById("ta-mirror-measure");
  if (!mirror) {
    mirror = document.createElement("div");
    mirror.id = "ta-mirror-measure";
    mirror.style.position = "absolute";
    mirror.style.visibility = "hidden";
    mirror.style.whiteSpace = "pre-wrap";
    mirror.style.wordWrap = "break-word";
    mirror.style.pointerEvents = "none";
    mirror.style.zIndex = "-1";
    mirror.style.tabIndex = "-1";
    document.body.appendChild(mirror);
  }
  return mirror;
}
export function copyTextareaStyles(src, dst) {
  const cs = getComputedStyle(src);
  [
    "fontFamily","fontSize","lineHeight","paddingTop","paddingRight","paddingBottom","paddingLeft",
    "borderTopWidth","borderRightWidth","borderBottomWidth","borderLeftWidth",
    "boxSizing","letterSpacing","whiteSpace","width"
  ].forEach(k => dst.style[k] = cs[k]);
}
export function caretClientRect(textarea) {
  const mirror = ensureMirror();
  copyTextareaStyles(textarea, mirror);

  const taRect = textarea.getBoundingClientRect();
  // ВЫРАВНИВАЕМ "зеркало" ПО ТЕКСТОВОЙ ОБЛАСТИ (в координатах страницы)
  mirror.style.left = (taRect.left + window.scrollX) + 'px';
  mirror.style.top  = (taRect.top  + window.scrollY) + 'px';
  mirror.style.width = taRect.width + 'px';
  mirror.scrollTop = textarea.scrollTop;
  mirror.scrollLeft = textarea.scrollLeft;

  const val = textarea.value;
  const pos = textarea.selectionStart;
  const before = val.slice(0, pos);
  const after  = val.slice(pos);

  mirror.textContent = before;
  const mark = document.createElement("span");
  mark.textContent = "\u200b";
  mirror.appendChild(mark);
  mirror.appendChild(document.createTextNode(after));

  const markRect = mark.getBoundingClientRect();
  // Возвращаем координаты каретки в координатах документа
  return {
    left: markRect.left + window.scrollX,
    top:  markRect.bottom + window.scrollY
  };
}

export function positionPanelAtCaret(textarea, panel, offsetY = 4) {
  const r = caretClientRect(textarea);
  panel.style.left = `${r.left}px`;
  panel.style.top  = `${r.top + offsetY}px`;
}

export function createListbox(panelEl, onChoose) {
  panelEl.setAttribute("role","listbox");
  panelEl.setAttribute("aria-expanded","false");
  let activeIndex = -1;

  function render(items) {
    panelEl.innerHTML = "";
    if (!items || !items.length) { panelEl.style.display="none"; panelEl.setAttribute("aria-expanded","false"); return; }
    const ul = document.createElement("ul");
    ul.style.listStyle = "none";
    ul.style.margin = "0";
    ul.style.padding = "6px";
    items.forEach((t,i)=>{
      const li = document.createElement("li");
      li.id = `opt-${Date.now()}-${i}`;
      li.setAttribute("role","option");
      li.dataset.i = String(i);
      li.textContent = t;
      li.style.padding = "6px 10px";
      li.style.borderRadius = "6px";
      li.style.cursor = "pointer";
      li.addEventListener("mousedown",(e)=>{ e.preventDefault(); onChoose(i, t); hide(); });
      ul.appendChild(li);
    });
    panelEl.appendChild(ul);
    activeIndex = 0;
    ul.firstChild?.classList.add("active");
    panelEl.style.display = "block";
    panelEl.setAttribute("aria-expanded","true");
  }
  function hide(){
    panelEl.style.display="none";
    panelEl.setAttribute("aria-expanded","false");
    panelEl.innerHTML = "";
    activeIndex = -1;
  }
  function move(delta){
    const items = panelEl.querySelectorAll("li[role='option']");
    if(!items.length) return;
    items.forEach(li=>li.classList.remove("active"));
    activeIndex = (activeIndex + delta + items.length) % items.length;
    items[activeIndex].classList.add("active");
    items[activeIndex].scrollIntoView({block:'nearest'});
    panelEl.setAttribute("aria-activedescendant", items[activeIndex].id);
  }
  function enter(){
    if(activeIndex<0) return;
    const li = panelEl.querySelectorAll("li[role='option']")[activeIndex];
    if(!li) return;
    onChoose(activeIndex, li.textContent);
    hide();
  }
  return { render, hide, move, enter, get activeIndex(){return activeIndex;} };
}

/* ===========================
   Суггест: ранжирование (простое)
   =========================== */
export function tokens(s){ return cleanName(s).split(' ').filter(Boolean); }
export function suggestRank(query, names, limit=12){
  const qNorm = cleanName(query);
  if(!qNorm) return [];
  const qTok = tokens(qNorm);
  const scored = [];
  for(const name of names){
    const nTok = tokens(name);
    const nNorm = cleanName(name);
    let allFound = true;
    let score = 100;
    for(const qt of qTok){
      const starts = nTok.some(nt => nt.startsWith(qt));
      const contains = !starts && nNorm.includes(qt);
      if(starts){ score = Math.min(score, 10); }
      else if(contains){ score = Math.min(score, 30); }
      else { allFound = false; break; }
    }
    if(!allFound) continue;
    if(nNorm.startsWith(qTok[0])) score = Math.min(score, 5);
    scored.push({name, score, len:nNorm.length});
    }
  scored.sort((a,b)=> a.score - b.score || a.len - b.len || a.name.localeCompare(b.name,'ru'));
  return scored.slice(0, limit).map(x=>x.name);
}

/* ===========================
   Смарт-вставка (анализ уверенности)
   =========================== */
export const SMART_THRESH = { HIGH: 0.90, MID: 0.60 };
export function simpleScoreTokens(a, b){
  a = cleanName(a); b = cleanName(b);
  if (a === b) return 1;
  const as = new Set(a.split(" ").filter(Boolean));
  const bs = new Set(b.split(" ").filter(Boolean));
  let inter = 0;
  for (const x of as) if (bs.has(x)) inter++;
  return inter / Math.max(as.size, bs.size || 1);
}
export function bestMatches(line, catalogNames, limit=3) {
  const res = [];
  for (const name of catalogNames) {
    const sc = simpleScoreTokens(line, name);
    if (sc >= SMART_THRESH.MID) res.push({ name, sc });
  }
  res.sort((x,y)=>y.sc - x.sc);
  return res.slice(0, limit);
}
export function analyzePasted(text, catalogNames){
  const lines = (text||'').split(/\r?\n/);
  const decisions = [];
  lines.forEach((raw, i) => {
    const norm = cleanName(raw.replace(/^[•\-\*\d\.\)\s]+/, '').replace(/[ ]{2,}/g, ' ').trim());
    if (!norm) { decisions.push({ i, raw, norm, status:'skip' }); return; }
    const opts = bestMatches(norm, catalogNames, 3);
    if (!opts.length) {
      decisions.push({ i, raw, norm, status:'unknown' });
      return;
    }
    const best = opts[0];
    if (best.sc >= SMART_THRESH.HIGH) {
      decisions.push({ i, raw, norm, status:'auto', best, options:opts });
    } else {
      decisions.push({ i, raw, norm, status:'review', best, options:opts });
    }
  });
  return decisions;
}

/* ===========================
   Провайдеры данных (заготовки)
   =========================== */

/* ===========================
   Разное
   =========================== */
export function mmToPx(mm){ return mm * (96 / 25.4); }
export function isFirefox(win=window){ return /firefox/i.test(win.navigator.userAgent); }
export function isMobile(win=window){ return /android|iphone|ipad|ipod|mobile/i.test(win.navigator.userAgent); }

export function downloadText(filename, text){
  const blob = new Blob([text], {type:'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  a.remove(); URL.revokeObjectURL(url);
}

/* ===========================
   Горячие клавиши
   =========================== */
const HOT = new Map();
export function bindHotkey(combo, handler){
  HOT.set(combo.toLowerCase(), handler);
}
export function initHotkeys(root=document){
  root.addEventListener("keydown", (e)=>{
    const parts = [];
    if(e.ctrlKey) parts.push("ctrl");
    if(e.shiftKey) parts.push("shift");
    if(e.altKey) parts.push("alt");
    parts.push(e.key.toLowerCase());
    const key = parts.join("+");
    if(HOT.has(key)){
      e.preventDefault();
      try { HOT.get(key)(e); } catch(err){ Log.error(err); }
    }
  });
}

/* ===========================
   Дубликаты
   =========================== */
export function findDuplicatesByRU(rows){
  const byNorm = new Map(), byTokens = new Map();
  rows.forEach((r, i)=>{
    const n = normalizeRU(r.ru), t = tokensSortedRU(r.ru);
    if(!byNorm.has(n)) byNorm.set(n, []); byNorm.get(n).push(i);
    if(!byTokens.has(t)) byTokens.set(t, []); byTokens.get(t).push(i);
  });
  const fullDups=[], tokenDups=[];
  byNorm.forEach(arr=>{ if(arr.length>1) fullDups.push(arr); });
  byTokens.forEach(arr=>{ if(arr.length>1) tokenDups.push(arr); });
  return { fullDups, tokenDups };
}

/* ===========================
   Темы оформления
   =========================== */
export const THEME_KEY = 'ui_theme';
export const THEMES = Object.freeze({
  slate: 'slate-ocean',        // тёмная «Slate Ocean»
  frost: 'frosted-glass'       // тёмная «Frosted Glass» (стеклянная)
});
export function getTheme() {
  return localStorage.getItem(THEME_KEY) || THEMES.slate;
}
export function setTheme(name, persist = true) {
  const t = (name === THEMES.frost) ? THEMES.frost : THEMES.slate;
  document.documentElement.setAttribute('data-theme', t);
  if (persist) {
    try { localStorage.setItem(THEME_KEY, t); } catch {}
  }
}
export function toggleTheme() {
  const cur = getTheme();
  const next = (cur === THEMES.slate) ? THEMES.frost : THEMES.slate;
  setTheme(next);
}
export function initThemeControls(selectors = ['#btnTheme']) {
  // начальная тема (без мигания при первой инициализации)
  setTheme(getTheme(), false);
  // обработчики на кнопки (можно списком селекторов)
  const list = Array.isArray(selectors) ? selectors : [selectors];
  list.forEach(sel => {
    const btn = document.querySelector(sel);
    if (!btn) return;
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Сменить тему');
    btn.addEventListener('click', toggleTheme);
  });
  // синхронизация между вкладками
  window.addEventListener('storage', (e) => {
    if (e.key === THEME_KEY) {
      setTheme(e.newValue || THEMES.slate, false);
    }
  });
}
