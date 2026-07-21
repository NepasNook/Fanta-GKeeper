"""Genera la pagina HTML interattiva, autonoma e senza dipendenze.

I dati vengono incorporati come JSON e tutti i ricalcoli (soglia, finestra di
giornate, coppie/triple) avvengono nel browser: si muove uno slider e la
classifica si rifa' senza rilanciare Python.

Nota sui colori. Il semaforo verde/giallo/rosso e' la convenzione del fantacalcio,
ma verde e rosso puri sono il caso peggiore per il daltonismo: misurati, distano
ΔE 4.1 in visione deuteranope, cioe' un lettore su dodici circa non li
distinguerebbe. Spostando il verde verso l'acqua (#1baf7a) la distanza sale a 9.9
e supera il target, senza perdere la lettura "da semaforo". Il colore non porta
mai il dato da solo: ogni cella ha il tooltip, la classifica ha le colonne
numeriche e la legenda e' etichettata.
"""

import json
from datetime import date
from pathlib import Path

from .config import (
    PERCENTILE_ROSSO,
    PERCENTILE_VERDE,
    SOGLIA_FACILE,
    SQUADRE_COSTOSE,
    STAGIONE_CORRENTE,
)
from .models import Forza, Impegno
from .scoring import forza_complessiva


def _colore_forza(posizione: int, totale: int) -> str:
    quota = 1 - (posizione / max(totale - 1, 1))
    if quota >= PERCENTILE_VERDE:
        return "verde"
    if quota <= PERCENTILE_ROSSO:
        return "rosso"
    return "giallo"


def costruisci_dati(
    forze: dict[str, Forza],
    impegni: dict[str, dict[int, Impegno]],
    mu: float,
    rapporti_storico: list[dict],
) -> dict:
    ordinate = sorted(forze.values(), key=forza_complessiva, reverse=True)
    colori = {f.squadra: _colore_forza(i, len(ordinate)) for i, f in enumerate(ordinate)}

    squadre = [
        {
            "nome": f.squadra,
            "attacco": round(f.attacco, 3),
            "difesa": round(f.difesa, 3),
            "forza": round(forza_complessiva(f), 3),
            "colore": colori[f.squadra],
            "neopromossa": f.neopromossa,
            "stagioni": f.stagioni_usate,
            "costosa": f.squadra in SQUADRE_COSTOSE,
        }
        for f in ordinate
    ]

    calendario = {
        squadra: [
            {
                "g": i.giornata,
                "avv": i.avversario,
                "casa": i.in_casa,
                "gol": round(i.gol_attesi_subiti, 3),
                "pcs": round(i.prob_clean_sheet, 4),
            }
            for i in sorted(per_giornata.values(), key=lambda x: x.giornata)
        ]
        for squadra, per_giornata in impegni.items()
    }

    giornate = sorted({i.giornata for p in impegni.values() for i in p.values()})

    return {
        "stagione": STAGIONE_CORRENTE,
        "generato": date.today().isoformat(),
        "mu": round(mu, 3),
        "sogliaIniziale": SOGLIA_FACILE,
        "giornate": giornate,
        "squadre": squadre,
        "calendario": calendario,
        "costose": sorted(SQUADRE_COSTOSE),
        "storico": rapporti_storico,
    }


def _componi(dati: dict) -> str:
    return _PAGINA.replace("__DATI__", json.dumps(dati, ensure_ascii=False))


def scrivi_html(dati: dict, percorso: Path) -> None:
    """Documento HTML autonomo: si apre con doppio clic, funziona offline."""
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(_componi(dati), encoding="utf-8")


def scrivi_frammento(dati: dict, percorso: Path) -> None:
    """Variante per la pubblicazione web come Artifact su claude.ai.

    L'host avvolge da solo il file in <!doctype><html><head></head><body>:
    passargli un documento completo anniderebbe due documenti. Qui si estraggono
    quindi lo stile e il solo contenuto del body, che e' tutto cio' che serve --
    la pagina e' gia' autonoma (nessuna risorsa esterna, CSS e JS in linea),
    quindi supera la CSP dell'host senza modifiche.
    """
    import re

    pagina = _componi(dati)
    stile = re.search(r"<style>.*?</style>", pagina, re.DOTALL)
    corpo = re.search(r"<body>(.*?)</body>", pagina, re.DOTALL)
    if not stile or not corpo:
        raise ValueError("Il modello HTML non ha piu' la forma attesa (<style> / <body>).")

    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(f"{stile.group(0)}\n{corpo.group(1).strip()}\n", encoding="utf-8")


_PAGINA = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accoppiate portieri — Serie A</title>
<style>
  :root {
    color-scheme: light;
    --plane: #f9f9f7;
    --surface: #fcfcfb;
    --ink: #0b0b0b;
    --ink-2: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --bordo: rgba(11,11,11,0.10);
    --facile: #1baf7a;
    --media: #fab219;
    --difficile: #d03b3b;
    --accento: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --plane: #0d0d0d;
      --surface: #1a1a19;
      --ink: #ffffff;
      --ink-2: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --bordo: rgba(255,255,255,0.10);
      --accento: #3987e5;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --plane: #0d0d0d;
    --surface: #1a1a19;
    --ink: #ffffff;
    --ink-2: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --bordo: rgba(255,255,255,0.10);
    --accento: #3987e5;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 20px 64px;
    background: var(--plane); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  .wrap { max-width: 1180px; margin: 0 auto; }
  h1 { font-size: 21px; margin: 0 0 4px; letter-spacing: -0.01em; }
  h2 { font-size: 15px; margin: 0 0 12px; font-weight: 600; }
  .sub { color: var(--ink-2); margin: 0 0 24px; }
  .sub code { color: var(--ink); }

  .pannello {
    background: var(--surface); border: 1px solid var(--bordo);
    border-radius: 10px; padding: 18px; margin-bottom: 20px;
  }

  .controlli { display: flex; flex-wrap: wrap; gap: 22px; align-items: flex-end; }
  .campo { display: flex; flex-direction: column; gap: 6px; }
  .campo > label { font-size: 12px; color: var(--ink-2); font-weight: 600; }
  .campo output { font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 600; }
  input[type=range] { width: 190px; accent-color: var(--accento); }
  select, button {
    font: inherit; color: var(--ink); background: var(--surface);
    border: 1px solid var(--bordo); border-radius: 7px; padding: 6px 10px;
  }
  button { cursor: pointer; }
  button.attivo { background: var(--accento); border-color: var(--accento); color: #fff; }
  :where(button, select, input, tbody tr):focus-visible {
    outline: 2px solid var(--accento); outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
  }
  .gruppo { display: flex; gap: 0; }
  .gruppo button { border-radius: 0; }
  .gruppo button:first-child { border-radius: 7px 0 0 7px; }
  .gruppo button:last-child { border-radius: 0 7px 7px 0; margin-left: -1px; }

  .legenda { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-top: 14px;
             padding-top: 14px; border-top: 1px solid var(--grid); font-size: 12px; color: var(--ink-2); }
  .voce { display: inline-flex; align-items: center; gap: 6px; }
  .chip { width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--bordo); }
  .chip.facile { background: var(--facile); }
  .chip.media { background: var(--media); }
  .chip.difficile { background: var(--difficile); }
  .chip.verde { background: var(--facile); }
  .chip.giallo { background: var(--media); }
  .chip.rosso { background: var(--difficile); }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }
  .tile { background: var(--surface); border: 1px solid var(--bordo); border-radius: 10px; padding: 14px 16px; }
  .tile .etichetta { font-size: 12px; color: var(--ink-2); }
  .tile .valore { font-size: 25px; font-weight: 650; letter-spacing: -0.02em; margin-top: 2px; }
  .tile .nota { font-size: 12px; color: var(--muted); }

  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); font-weight: 600; }
  td.num, th.num { text-align: right; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: color-mix(in srgb, var(--accento) 8%, transparent); }
  tbody tr.sel { background: color-mix(in srgb, var(--accento) 14%, transparent); }

  .striscia { display: flex; gap: 1px; }
  .cella {
    width: 9px; height: 20px; border-radius: 2px; flex: none;
  }
  .cella.facile { background: var(--facile); }
  .cella.media { background: var(--media); }
  .cella.difficile { background: var(--difficile); }

  .griglia { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 8px; }
  .box { border: 1px solid var(--bordo); border-radius: 8px; padding: 8px; background: var(--surface); }
  .box .g { font-size: 11px; color: var(--muted); }
  .box .sq { font-weight: 650; margin: 2px 0; }
  .box .avv { font-size: 12px; color: var(--ink-2); }
  .box .p { font-size: 12px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .box.facile { border-left: 3px solid var(--facile); }
  .box.media { border-left: 3px solid var(--media); }
  .box.difficile { border-left: 3px solid var(--difficile); }

  .tag { font-size: 10px; padding: 1px 5px; border-radius: 4px; border: 1px solid var(--bordo); color: var(--ink-2); }

  #tooltip {
    position: fixed; z-index: 50; pointer-events: none; opacity: 0;
    background: var(--surface); color: var(--ink);
    border: 1px solid var(--bordo); border-radius: 7px; padding: 7px 10px;
    font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.16); transition: opacity .08s;
    max-width: 240px;
  }
  #tooltip .t { font-weight: 650; }
  #tooltip .r { color: var(--ink-2); }
  .vuoto { color: var(--muted); padding: 20px 0; }
  .piede { color: var(--muted); font-size: 12px; margin-top: 28px; }
  .piede a { color: var(--accento); }
</style>
</head>
<body>
<div class="wrap">

<h1>Accoppiate portieri — Serie A <span id="stagione"></span></h1>
<p class="sub">
  Ogni giornata schieri il portiere con la partita piu' facile: una coppia vale il
  <strong>migliore dei due</strong>, quindi vincono le coppie <strong>complementari</strong>.
  &ldquo;Facile&rdquo; = alta probabilita' di non subire gol, stimata da attacco avversario,
  solidita' difensiva e fattore campo. <span id="meta" class="r"></span>
</p>

<div class="pannello">
  <div class="controlli">
    <div class="campo">
      <label>Quanti portieri</label>
      <div class="gruppo">
        <button id="btn2" class="attivo">Coppia</button>
        <button id="btn3">Tripla</button>
      </div>
    </div>
    <div class="campo">
      <label for="soglia">Soglia &ldquo;partita facile&rdquo; — <output id="outSoglia"></output></label>
      <input type="range" id="soglia" min="0.20" max="0.60" step="0.01">
    </div>
    <div class="campo">
      <label for="da">Dalla giornata — <output id="outDa"></output></label>
      <input type="range" id="da" min="1" max="38" step="1" value="1">
    </div>
    <div class="campo">
      <label for="a">Alla giornata — <output id="outA"></output></label>
      <input type="range" id="a" min="1" max="38" step="1" value="38">
    </div>
    <div class="campo">
      <label for="ordina">Ordina per</label>
      <select id="ordina">
        <option value="copertura">Copertura (giornate coperte)</option>
        <option value="media">Qualita' media della partita</option>
        <option value="guadagno">Guadagno dell'alternanza</option>
      </select>
    </div>
    <div class="campo">
      <label for="escludi">Portieri costosi</label>
      <select id="escludi">
        <option value="no">Ammessi</option>
        <option value="si">Esclusi</option>
      </select>
    </div>
  </div>
  <div class="legenda">
    <span class="voce"><span class="chip facile"></span> Facile — sopra soglia</span>
    <span class="voce"><span class="chip media"></span> Media</span>
    <span class="voce"><span class="chip difficile"></span> Difficile</span>
    <span class="r" id="notaEscludi"></span>
  </div>
</div>

<div class="tiles" id="tiles"></div>

<div class="pannello" style="margin-top:20px">
  <h2>Classifica delle accoppiate <span class="r" id="quante"></span></h2>
  <div class="scroll">
    <table id="tab">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Squadre</th>
          <th class="num">Copertura</th>
          <th class="num">Facili</th>
          <th class="num">Media P(imb.)</th>
          <th class="num" title="Quanto rende alternare, rispetto a tenere sempre il migliore dei due. Vicino a zero = il secondo portiere e' un doppione.">Guadagno</th>
          <th>Calendario</th>
        </tr>
      </thead>
      <tbody id="corpo"></tbody>
    </table>
  </div>
</div>

<div class="pannello">
  <h2 id="titoloDettaglio">Dettaglio</h2>
  <div id="dettaglio" class="griglia"></div>
</div>

<div class="pannello">
  <h2>Forza delle squadre <span class="r">— stimata, non assegnata a mano</span></h2>
  <div class="scroll">
    <table>
      <thead><tr>
        <th class="num">#</th><th>Squadra</th><th></th>
        <th class="num">Attacco</th><th class="num">Difesa</th><th class="num">Forza</th><th>Note</th>
      </tr></thead>
      <tbody id="corpoForze"></tbody>
    </table>
  </div>
  <p class="r" style="font-size:12px;margin:12px 0 0">
    Attacco e difesa sono relativi alla media del campionato: attacco 1.30 = segna il 30% in piu'
    della media; difesa 0.70 = subisce il 30% in meno (piu' basso = piu' solido).
    Le stagioni recenti pesano molto di piu' delle vecchie.
  </p>
</div>

<p class="piede" id="piede"></p>
</div>

<div id="tooltip"></div>

<script>
const DATI = __DATI__;

const $ = (id) => document.getElementById(id);
const pct = (x) => (x * 100).toFixed(0) + "%";
const pct1 = (x) => (x * 100).toFixed(1) + "%";

const stato = {
  dimensione: 2,
  soglia: DATI.sogliaIniziale,
  da: DATI.giornate[0],
  a: DATI.giornate[DATI.giornate.length - 1],
  ordina: "copertura",
  escludi: false,
  selezione: null,
};

const COSTOSE = new Set(DATI.costose);

function classe(pcs, soglia) {
  if (pcs >= soglia) return "facile";
  if (pcs >= soglia - 0.12) return "media";
  return "difficile";
}

function giornateAttive() {
  return DATI.giornate.filter((g) => g >= stato.da && g <= stato.a);
}

function squadreAmmesse() {
  let nomi = DATI.squadre.map((s) => s.nome);
  if (stato.escludi || stato.dimensione === 3) nomi = nomi.filter((n) => !COSTOSE.has(n));
  return nomi.sort();
}

// squadra -> giornata -> impegno.
// Il nome squadra non e' nel JSON (sarebbe ripetuto 380 volte): lo attacco qui.
const INDICE = {};
for (const [squadra, lista] of Object.entries(DATI.calendario)) {
  INDICE[squadra] = {};
  for (const imp of lista) {
    imp.squadra = squadra;
    INDICE[squadra][imp.g] = imp;
  }
}

function valuta(gruppo, giornate) {
  let somma = 0, facili = 0, valide = 0;
  const scelte = [];
  const singole = Object.fromEntries(gruppo.map((s) => [s, 0]));
  for (const g of giornate) {
    let best = null;
    for (const s of gruppo) {
      const imp = INDICE[s]?.[g];
      if (!imp) continue;
      singole[s] += imp.pcs;
      if (best === null || imp.pcs > best.pcs) best = imp;
    }
    if (!best) continue;
    somma += best.pcs;
    valide++;
    if (best.pcs >= stato.soglia) facili++;
    scelte.push(best);
  }
  if (!valide) return null;
  // Il guadagno misura la complementarita': quanto rende alternare rispetto a
  // tenere sempre e solo il migliore del gruppo. Vicino a zero = doppione.
  const migliorSingolo = gruppo.reduce((a, b) => (singole[a] >= singole[b] ? a : b));
  const mediaSingolo = singole[migliorSingolo] / valide;
  const media = somma / valide;
  return {
    squadre: gruppo,
    media,
    copertura: facili / valide,
    facili,
    totali: valide,
    scelte,
    guadagno: media - mediaSingolo,
    migliorSingolo,
    mediaSingolo,
  };
}

function combinazioni(lista, k) {
  const out = [];
  const rec = (inizio, acc) => {
    if (acc.length === k) { out.push(acc.slice()); return; }
    for (let i = inizio; i < lista.length; i++) { acc.push(lista[i]); rec(i + 1, acc); acc.pop(); }
  };
  rec(0, []);
  return out;
}

function classifica() {
  const giornate = giornateAttive();
  const nomi = squadreAmmesse();
  const res = [];
  for (const gruppo of combinazioni(nomi, stato.dimensione)) {
    const v = valuta(gruppo, giornate);
    if (v) res.push(v);
  }
  const criteri = {
    copertura: (x, y) => (y.copertura - x.copertura) || (y.media - x.media),
    media: (x, y) => (y.media - x.media) || (y.copertura - x.copertura),
    guadagno: (x, y) => (y.guadagno - x.guadagno) || (y.media - x.media),
  };
  res.sort(criteri[stato.ordina]);
  return res;
}

// ---- tooltip ----
const tip = $("tooltip");
function mostraTip(e, html) {
  tip.innerHTML = html;
  tip.style.opacity = "1";
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function nascondiTip() { tip.style.opacity = "0"; }

function testoImpegno(imp) {
  return `<div class="t">${imp.avv} ${imp.casa ? "in casa" : "in trasferta"}</div>
          <div class="r">Giornata ${imp.g}</div>
          <div class="r">Imbattibilita': <strong>${pct1(imp.pcs)}</strong></div>
          <div class="r">Gol attesi subiti: ${imp.gol.toFixed(2)}</div>`;
}

// ---- render ----
function render() {
  const res = classifica();
  $("quante").textContent = `— ${res.length.toLocaleString("it-IT")} combinazioni sulle giornate ${stato.da}-${stato.a}`;

  const migliore = res[0];
  $("tiles").innerHTML = migliore ? `
    <div class="tile">
      <div class="etichetta">Migliore accoppiata</div>
      <div class="valore" style="font-size:19px">${migliore.squadre.join(" + ")}</div>
      <div class="nota">giornate ${stato.da}-${stato.a}</div>
    </div>
    <div class="tile">
      <div class="etichetta">Giornate coperte</div>
      <div class="valore">${pct(migliore.copertura)}</div>
      <div class="nota">${migliore.facili} su ${migliore.totali} sopra soglia</div>
    </div>
    <div class="tile">
      <div class="etichetta">Imbattibilita' media</div>
      <div class="valore">${pct1(migliore.media)}</div>
      <div class="nota">schierando ogni volta il migliore</div>
    </div>
    <div class="tile">
      <div class="etichetta">Guadagno dell'alternanza</div>
      <div class="valore">${(migliore.guadagno * 100).toFixed(1)}</div>
      <div class="nota">punti sopra il solo ${migliore.migliorSingolo} (${pct1(migliore.mediaSingolo)})</div>
    </div>` : `<div class="tile"><div class="etichetta">Nessuna combinazione</div></div>`;

  const corpo = $("corpo");
  corpo.innerHTML = "";
  if (!res.length) {
    corpo.innerHTML = `<tr><td colspan="7" class="vuoto">Nessuna combinazione con questi filtri.</td></tr>`;
  }
  const chiave = (c) => c.squadre.join("|");
  if (!stato.selezione || !res.some((c) => chiave(c) === stato.selezione)) {
    stato.selezione = migliore ? chiave(migliore) : null;
  }

  res.slice(0, 60).forEach((c, i) => {
    const tr = document.createElement("tr");
    if (chiave(c) === stato.selezione) tr.className = "sel";
    const celle = c.scelte.map((imp) => {
      const cl = classe(imp.pcs, stato.soglia);
      return `<span class="cella ${cl}" data-g="${imp.g}" data-sq="${imp.squadra || ""}"
               data-tip="${encodeURIComponent(testoImpegno(imp))}"></span>`;
    }).join("");
    tr.innerHTML = `
      <td class="num">${i + 1}</td>
      <td><strong>${c.squadre.join(" + ")}</strong></td>
      <td class="num">${pct(c.copertura)}</td>
      <td class="num">${c.facili}/${c.totali}</td>
      <td class="num">${pct1(c.media)}</td>
      <td class="num" title="Da solo, ${c.migliorSingolo} vale ${pct1(c.mediaSingolo)}">${(c.guadagno * 100).toFixed(1)}</td>
      <td><div class="striscia">${celle}</div></td>`;
    tr.onclick = () => { stato.selezione = chiave(c); render(); };
    corpo.appendChild(tr);
  });

  corpo.querySelectorAll(".cella").forEach((el) => {
    el.onmousemove = (e) => mostraTip(e, decodeURIComponent(el.dataset.tip));
    el.onmouseleave = nascondiTip;
  });

  const sel = res.find((c) => chiave(c) === stato.selezione);
  $("titoloDettaglio").innerHTML = sel
    ? `Dettaglio — <strong>${sel.squadre.join(" + ")}</strong> <span class="r">chi schierare, giornata per giornata</span>`
    : "Dettaglio";
  $("dettaglio").innerHTML = sel ? sel.scelte.map((imp) => {
    const cl = classe(imp.pcs, stato.soglia);
    return `<div class="box ${cl}">
      <div class="g">Giornata ${imp.g}</div>
      <div class="sq">${imp.squadra}</div>
      <div class="avv">${imp.casa ? "vs" : "@"} ${imp.avv}</div>
      <div class="p">${pct(imp.pcs)}</div>
    </div>`;
  }).join("") : `<p class="vuoto">Seleziona una riga della classifica.</p>`;
}

function renderForze() {
  $("corpoForze").innerHTML = DATI.squadre.map((s, i) => {
    const note = [];
    if (s.costosa) note.push(`<span class="tag">portiere costoso</span>`);
    if (s.neopromossa && !s.stagioni) note.push(`<span class="tag">neopromossa — nessuno storico</span>`);
    else if (s.neopromossa) note.push(`<span class="tag">neopromossa — ${s.stagioni} stagioni di A, non l'ultima</span>`);
    else if (s.stagioni < 5) note.push(`<span class="tag">solo ${s.stagioni} stagioni di storico</span>`);
    return `<tr>
      <td class="num">${i + 1}</td>
      <td><strong>${s.nome}</strong></td>
      <td><span class="chip ${s.colore}" title="${s.colore}"></span></td>
      <td class="num">${s.attacco.toFixed(2)}</td>
      <td class="num">${s.difesa.toFixed(2)}</td>
      <td class="num">${s.forza.toFixed(2)}</td>
      <td>${note.join(" ")}</td>
    </tr>`;
  }).join("");
}

// ---- controlli ----
function sincronizza() {
  $("outSoglia").textContent = pct(stato.soglia);
  $("outDa").textContent = stato.da;
  $("outA").textContent = stato.a;
  $("btn2").className = stato.dimensione === 2 ? "attivo" : "";
  $("btn3").className = stato.dimensione === 3 ? "attivo" : "";
  $("escludi").disabled = stato.dimensione === 3;
  $("notaEscludi").textContent = stato.dimensione === 3
    ? "Le triple escludono sempre i portieri costosi (" + DATI.costose.join(", ") + "): con una tripla stai rinunciando al titolare di una big."
    : "";
}

$("soglia").oninput = (e) => { stato.soglia = +e.target.value; sincronizza(); render(); };
$("da").oninput = (e) => {
  stato.da = +e.target.value;
  if (stato.da > stato.a) { stato.a = stato.da; $("a").value = stato.a; }
  sincronizza(); render();
};
$("a").oninput = (e) => {
  stato.a = +e.target.value;
  if (stato.a < stato.da) { stato.da = stato.a; $("da").value = stato.da; }
  sincronizza(); render();
};
$("ordina").onchange = (e) => { stato.ordina = e.target.value; render(); };
$("escludi").onchange = (e) => { stato.escludi = e.target.value === "si"; stato.selezione = null; render(); };
$("btn2").onclick = () => { stato.dimensione = 2; stato.selezione = null; sincronizza(); render(); };
$("btn3").onclick = () => { stato.dimensione = 3; stato.selezione = null; sincronizza(); render(); };

// ---- avvio ----
$("stagione").textContent = DATI.stagione;
$("soglia").value = stato.soglia;
$("da").min = DATI.giornate[0]; $("da").max = DATI.giornate[DATI.giornate.length - 1];
$("a").min = DATI.giornate[0]; $("a").max = DATI.giornate[DATI.giornate.length - 1];
$("meta").textContent = `Media del campionato: ${DATI.mu} gol per squadra a partita.`;
$("piede").innerHTML =
  `Generato il ${DATI.generato}. Calendario da it.wikipedia.org, storico da openfootball/football.json (` +
  DATI.storico.map((r) => `${r.stagione}: ${r.partite_con_risultato}/${r.partite_in_calendario}`).join(", ") +
  `). Il colore non porta mai il dato da solo: passa il mouse su una cella per i numeri esatti.`;

sincronizza();
renderForze();
render();
</script>
</body>
</html>
"""
