"use strict";

const ETATS = {
  demarrage: { libelle: "Démarrage…", icone: "…" },
  ok: { libelle: "Bien droit", icone: "✓" },
  avachi: { libelle: "Avachi", icone: "⚠" },
  absent: { libelle: "Personne", icone: "○" },
  incertain: { libelle: "Mal cadré", icone: "?" },
  pause: { libelle: "En pause", icone: "⏸" },
  non_calibre: { libelle: "À calibrer", icone: "●" },
  sans_camera: { libelle: "Caméra indisponible", icone: "✕" },
  hors_ligne: { libelle: "Service arrêté", icone: "✕" },
};

const $ = (id) => document.getElementById(id);
let signaux = {};
let postures = [];
let referenceActive = null;
let enregistrementEnCours = false;

async function api(chemin, options = {}) {
  const reponse = await fetch(chemin, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}`;
    try { message = (await reponse.json()).detail || message; } catch { /* corps vide */ }
    throw new Error(message);
  }
  return reponse.status === 204 ? null : reponse.json();
}

const deuxChiffres = (n) => String(n).padStart(2, "0");

function dateCourte(d) {
  return `${deuxChiffres(d.getDate())}/${deuxChiffres(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function duree(secondes) {
  const s = Math.round(secondes);
  if (s < 60) return `${s} s`;
  const min = Math.round(s / 60);
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${deuxChiffres(min % 60)}`;
}

function element(balise, classe, texte) {
  const el = document.createElement(balise);
  if (classe) el.className = classe;
  if (texte !== undefined) el.textContent = texte;
  return el;
}

// --- État en direct ---

function afficherEtat(etat) {
  const code = etat.etat;
  const infos = ETATS[code] || { libelle: code, icone: "" };
  const badge = $("etat-badge");
  badge.className = `badge badge--${code}`;
  badge.textContent = `${infos.icone} ${infos.libelle}`;

  let detail = "";
  if (code === "avachi" && etat.fausse_alerte) {
    detail = "Fausse alerte notée : pas d'assombrissement avant ton prochain redressement.";
  } else if (code === "avachi") detail = `Cause principale : ${etat.cause}.`;
  else if (code === "ok") detail = "Posture conforme à tes références.";
  else if (code === "incertain") detail = "Tête ou épaules masquées ou hors du cadre.";
  else if (code === "non_calibre") detail = "Enregistre une première posture de référence pour commencer.";
  else if (code === "absent") detail = "Personne devant la caméra.";
  if (etat.niveau > 0) detail += ` Écran assombri à ${Math.round(etat.niveau * 100)} %.`;
  $("detail").textContent = detail;
  $("fausse-alerte-btn").hidden = code !== "avachi" || etat.fausse_alerte;

  afficherVoile(etat);
  afficherSignaux(etat);
  afficherEnregistrement(etat);
  afficherBandeaux(etat);

  $("pause-btn").textContent = etat.pause ? "Reprendre" : "Mettre en pause";
  $("pause-btn").disabled = code === "hors_ligne";

  if (etat.reference !== referenceActive) {
    referenceActive = etat.reference ?? null;
    afficherPostures();
  }
}

function afficherVoile(etat) {
  const voile = $("apercu-voile");
  let titre = "";
  let sousTitre = "";
  let compte = false;
  if (etat.enregistrement) {
    compte = true;
    titre = etat.enregistrement.phase === "preparation" ? "Prends la pose" : "Ne bouge plus";
    sousTitre = String(Math.ceil(etat.enregistrement.restant));
  } else if (etat.etat === "pause") {
    titre = "En pause : la caméra est libérée.";
  } else if (etat.etat === "sans_camera") {
    titre = "Caméra indisponible";
  } else if (etat.etat === "hors_ligne") {
    titre = "Le service Vigie ne répond pas.";
  }
  voile.hidden = !titre;
  voile.classList.toggle("apercu-voile--compte", compte);
  $("apercu-titre").textContent = titre;
  $("apercu-sous-titre").textContent = sousTitre;
}

function afficherSignaux(etat) {
  const liste = $("signaux");
  liste.replaceChildren();
  if (!etat.ecarts) {
    liste.append(element("li", "signaux-vide",
      etat.etat === "non_calibre" ? "Aucune posture de référence pour l'instant." : "Pas de mesure en ce moment."));
    return;
  }
  for (const [nom, valeur] of Object.entries(etat.ecarts)) {
    const li = element("li", "signal");
    li.append(element("span", "signal-libelle", signaux[nom]?.libelle || nom));
    li.append(element("span", "signal-valeur", valeur.toFixed(2)));
    const jauge = element("div", "jauge");
    const remplie = element("div", "jauge-remplie");
    // Échelle de 0 à 2 : le seuil (1) tombe au milieu.
    remplie.style.width = `${Math.min(100, valeur * 50)}%`;
    if (valeur > 1) remplie.classList.add("jauge-remplie--depasse");
    else if (valeur > 0.7) remplie.classList.add("jauge-remplie--proche");
    jauge.append(remplie);
    jauge.title = valeur > 1 ? `Dépasse : ${signaux[nom]?.cause}` : "Dans la tolérance";
    li.append(jauge);
    liste.append(li);
  }
}

function afficherEnregistrement(etat) {
  const enCours = Boolean(etat.enregistrement);
  $("posture-btn").disabled = enCours || etat.pause;
  if (enCours) {
    $("posture-statut").className = "status";
    $("posture-statut").textContent = `Enregistrement de « ${etat.enregistrement.nom} »…`;
  } else if (enregistrementEnCours && etat.dernier_enregistrement) {
    const r = etat.dernier_enregistrement;
    $("posture-statut").className = `status ${r.ok ? "status--ok" : "status--erreur"}`;
    $("posture-statut").textContent = r.message;
    chargerPostures();
  }
  enregistrementEnCours = enCours;
}

function afficherBandeaux(etat) {
  const bandeaux = [];
  if (etat.extension === false && etat.extensions_desactivees) {
    const p = element("p", "bandeau",
      "GNOME a désactivé les extensions utilisateur (il le fait après un plantage de GNOME Shell) : "
      + "l'écran ne pourra pas s'assombrir. Réactive-les avec ");
    p.append(element("code", "", "dconf write /org/gnome/shell/disable-user-extensions false"),
      " ; si ce bandeau reste, ferme et rouvre ta session.");
    bandeaux.push(p);
  } else if (etat.extension === false) {
    const p = element("p", "bandeau",
      "L'extension GNOME de Vigie ne répond pas : l'écran ne pourra pas s'assombrir. Installe-la avec ");
    p.append(element("code", "", "scripts/installer.sh"), " puis ferme et rouvre ta session.");
    bandeaux.push(p);
  }
  if (etat.camera_erreur) bandeaux.push(element("p", "bandeau", `Caméra : ${etat.camera_erreur}.`));
  $("bandeaux").replaceChildren(...bandeaux);
}

async function rafraichirEtat() {
  try {
    afficherEtat(await api("/api/etat"));
  } catch {
    afficherEtat({ etat: "hors_ligne", pause: false });
  }
}

// --- Postures ---

async function chargerPostures() {
  postures = await api("/api/postures");
  afficherPostures();
}

function afficherPostures() {
  const liste = $("postures");
  liste.replaceChildren();
  for (const p of postures) {
    const li = element("li", p.id === referenceActive ? "posture posture--active" : "posture");
    const texte = element("div", "posture-texte");
    texte.append(element("div", "posture-nom", p.nom));
    const d = new Date(p.cree_le);
    texte.append(element("div", "posture-date",
      `Enregistrée le ${dateCourte(d)} à ${deuxChiffres(d.getHours())}:${deuxChiffres(d.getMinutes())}`));
    li.append(texte);
    if (p.id === referenceActive) li.append(element("span", "posture-proche", "la plus proche"));
    const supprimer = element("button", "btn-secondary btn-petit", "Supprimer");
    supprimer.type = "button";
    supprimer.addEventListener("click", async () => {
      if (!confirm(`Supprimer la posture « ${p.nom} » ?`)) return;
      await api(`/api/postures/${p.id}`, { method: "DELETE" });
      chargerPostures();
    });
    li.append(supprimer);
    liste.append(li);
  }
}

$("posture-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nom = $("posture-nom").value.trim();
  if (!nom) return;
  try {
    await api("/api/postures", { method: "POST", body: { nom } });
    $("posture-nom").value = "";
    enregistrementEnCours = true;
  } catch (err) {
    $("posture-statut").className = "status status--erreur";
    $("posture-statut").textContent = err.message;
  }
});

// --- Pause ---

$("pause-btn").addEventListener("click", async () => {
  $("pause-btn").disabled = true;
  try {
    await api("/api/pause", { method: "POST", body: {} });
  } finally {
    rafraichirEtat();
  }
});

// --- Réglages ---

const REGLAGES = {
  tolerance: (v) => `× ${v.toFixed(1)}`,
  delai: (v) => `${v} s`,
  niveau_max: (v) => `${Math.round(v * 100)} %`,
};

async function chargerReglages() {
  const reglages = await api("/api/reglages");
  for (const [cle, format] of Object.entries(REGLAGES)) {
    $(cle).value = reglages[cle];
    $(`${cle}-val`).textContent = format(Number(reglages[cle]));
  }
}

for (const [cle, format] of Object.entries(REGLAGES)) {
  $(cle).addEventListener("input", () => {
    $(`${cle}-val`).textContent = format(Number($(cle).value));
  });
  $(cle).addEventListener("change", () => {
    api("/api/reglages", { method: "PUT", body: { [cle]: Number($(cle).value) } });
  });
}

$("fausse-alerte-btn").addEventListener("click", async () => {
  $("fausse-alerte-btn").disabled = true;
  try {
    await api("/api/fausse-alerte", { method: "POST", body: {} });
  } catch { /* déjà redressé depuis plus de 10 s : plus rien à signaler */ } finally {
    $("fausse-alerte-btn").disabled = false;
    rafraichirEtat();
    chargerBilan();
  }
});

$("test-btn").addEventListener("click", () => api("/api/test-assombrissement", { method: "POST" }));

const bouton = $("account-menu-btn");
const popup = $("settings-popup");
bouton.addEventListener("click", (e) => {
  e.stopPropagation();
  popup.hidden = !popup.hidden;
  bouton.setAttribute("aria-expanded", String(!popup.hidden));
});
document.addEventListener("click", (e) => {
  if (!popup.hidden && !popup.contains(e.target)) {
    popup.hidden = true;
    bouton.setAttribute("aria-expanded", "false");
  }
});

// --- Bilan du jour ---

async function chargerBilan() {
  const bilan = await api("/api/bilan");
  const devant = (bilan.ok || 0) + (bilan.avachi || 0);
  const part = (s) => (devant ? `${Math.round((100 * (s || 0)) / devant)} % du temps devant l'écran` : "—");
  const n = bilan.fausses_alertes || 0;
  const fausses = n ? ` · ${n} fausse${n > 1 ? "s" : ""} alerte${n > 1 ? "s" : ""}` : "";
  const tuiles = [
    ["Droit", duree(bilan.ok || 0), part(bilan.ok), true],
    ["Avachi", duree(bilan.avachi || 0), part(bilan.avachi) + fausses, false],
    ["Absent", duree(bilan.absent || 0), "caméra allumée, personne devant", false],
    ["En pause", duree(bilan.pause || 0), "caméra libérée", false],
  ];
  $("bilan").replaceChildren(...tuiles.map(([libelle, valeur, note, principal]) => {
    const tuile = element("div", principal ? "kpi kpi--principal" : "kpi");
    tuile.append(element("p", "kpi-libelle", libelle), element("p", "kpi-valeur", valeur),
      element("p", "kpi-note", note));
    return tuile;
  }));
  // Signal qui dépassait le plus pendant le temps avachi : celui dont la tolérance est à revoir
  // si l'on était en fait droit.
  const causes = Object.entries(bilan.causes || {}).sort((a, b) => b[1] - a[1]);
  const totalCauses = causes.reduce((total, [, secondes]) => total + secondes, 0);
  const pourcent = (s) => { const p = Math.round((100 * s) / totalCauses); return p ? `${p} %` : "< 1 %"; };
  $("bilan-causes").hidden = !totalCauses;
  $("bilan-causes").replaceChildren(element("span", "muted", "Temps avachi, par cause :"),
    ...causes.map(([nom, secondes]) => element("span", "cause",
      `${signaux[nom]?.cause || nom} · ${pourcent(secondes)}`)));
  $("bilan-date").textContent = dateCourte(new Date());
}

// --- Démarrage ---

(async () => {
  signaux = await api("/api/signaux");
  await Promise.all([chargerPostures(), chargerReglages(), chargerBilan()]);
  rafraichirEtat();
  setInterval(rafraichirEtat, 400);
  setInterval(chargerBilan, 30000);
})();
