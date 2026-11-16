"use strict";
// Vigie — aides communes aux scripts de la page.

// Bulles d'aide : remplacent l'infobulle native des attributs title (lente, sans style),
// pour tout élément, même créé après coup. Le title est mis de côté pendant le survol,
// sinon le navigateur afficherait aussi la sienne.
(() => {
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);
  let cur = null;

  function hide() {
    if (!cur) return;
    if (!cur.hasAttribute("title")) cur.setAttribute("title", cur.dataset.tip);
    delete cur.dataset.tip;
    cur = null;
    tip.hidden = true;
  }
  function show(t) {
    const text = t.getAttribute("title");
    if (!text) return;
    cur = t;
    t.dataset.tip = text;
    t.removeAttribute("title");
    tip.textContent = text;
    tip.hidden = false;
    // Sous l'élément, centrée ; au-dessus s'il n'y a pas la place ; jamais hors de l'écran.
    const r = t.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8)}px`;
    tip.style.top = `${r.bottom + 8 + h > innerHeight - 8 ? Math.max(8, r.top - h - 8) : r.bottom + 8}px`;
  }
  function enter(e) {
    if (cur && cur.contains(e.target)) return;
    hide();
    const t = e.target.closest?.("[title]");
    if (t) show(t);
  }
  function leave(e) {
    if (cur && !cur.contains(e.relatedTarget)) hide();
  }
  document.addEventListener("mouseover", enter);
  document.addEventListener("mouseout", leave);
  document.addEventListener("focusin", enter);
  document.addEventListener("focusout", leave);
  addEventListener("scroll", hide, true);
})();

// Bouton « ? » à côté du titre d'un panneau : montre ou cache son explication.
for (const btn of document.querySelectorAll("main button.help-btn[aria-controls]")) {
  const p = document.getElementById(btn.getAttribute("aria-controls"));
  btn.title = "Comment lire ce panneau";
  btn.setAttribute("aria-label", `Comment lire : ${btn.parentElement.firstChild.textContent.trim()}`);
  btn.setAttribute("aria-expanded", "false");
  btn.addEventListener("click", () => {
    p.hidden = !p.hidden;
    btn.setAttribute("aria-expanded", String(!p.hidden));
    btn.classList.toggle("active", !p.hidden);
  });
}
