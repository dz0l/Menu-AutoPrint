const csrfToken = () => document.cookie.split("; ").find((v) => v.startsWith("csrftoken="))?.split("=")[1] || "";
const $ = (id) => document.getElementById(id);

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  setTimeout(() => { box.hidden = true; }, 2600);
}

function lines(value) {
  return (value || "").replace(/\u00a0/g, " ").split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
}

function renderPreview(target, items) {
  target.innerHTML = "";
  for (const item of items || []) {
    const span = document.createElement("span");
    span.className = item.type === "group" ? "group" : "dish";
    span.textContent = `${item.type === "dish" ? "• " : ""}${item.text}${item.suffix || ""}`;
    target.appendChild(span);
  }
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function preview() {
  const data = await postJson("/api/menu/preview", {
    ru: $("ruText").value,
    en: $("enText").value,
    show_kcal: $("showKcal").checked,
  });
  renderPreview($("previewRu"), data.ru);
  renderPreview($("previewEn"), data.en);
  if (!lines($("enText").value).length) {
    $("enText").value = (data.en || []).map((item) => item.text).join("\n");
  }
  $("btnMissing").disabled = !(data.missing || []).length;
}

async function checkMissing() {
  return postJson("/api/dishes/check-missing-fixables", {ru_lines: lines($("ruText").value)});
}

$("btnPreview").addEventListener("click", () => preview().catch((err) => toast(err.message)));
$("ruText").addEventListener("input", () => preview().catch(() => {}));
$("enText").addEventListener("input", () => preview().catch(() => {}));
$("showKcal").addEventListener("change", () => preview().catch(() => {}));

$("btnPdf").addEventListener("click", async () => {
  const res = await fetch("/api/menu/pdf", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
    body: JSON.stringify({
      ru: $("ruText").value,
      en: $("enText").value,
      show_kcal: $("showKcal").checked,
      print_date: $("printDate").value,
    }),
  });
  const blob = await res.blob();
  window.open(URL.createObjectURL(blob), "_blank");
});

$("btnMissing").addEventListener("click", async () => {
  const data = await checkMissing();
  sessionStorage.setItem("menu_missing_ru", JSON.stringify(data.missing || []));
  sessionStorage.setItem("menu_last_ru", $("ruText").value);
  sessionStorage.setItem("menu_last_en", $("enText").value);
  location.href = "/editor/";
});

$("btnFix").addEventListener("click", async () => {
  const data = await checkMissing();
  sessionStorage.setItem("menu_fix_ru", JSON.stringify(data.fixables || []));
  sessionStorage.setItem("menu_last_ru", $("ruText").value);
  sessionStorage.setItem("menu_last_en", $("enText").value);
  location.href = "/editor/";
});

window.addEventListener("load", () => {
  $("ruText").value = sessionStorage.getItem("menu_last_ru") || "";
  $("enText").value = sessionStorage.getItem("menu_last_en") || "";
  sessionStorage.removeItem("menu_last_ru");
  sessionStorage.removeItem("menu_last_en");
  preview().catch(() => {});
});
