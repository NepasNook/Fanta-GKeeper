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
    BUDGET,
    PERCENTILE_ROSSO,
    PERCENTILE_VERDE,
    PREZZO_SCONOSCIUTO,
    SOGLIA_ATTACCO,
    SOGLIA_FACILE,
    STAGIONE_CORRENTE,
)
from .models import Forza, Impegno
from .scoring import solidita

# Tutto cio' che cambia fra la pagina dei portieri e quella degli attaccanti sta
# qui dentro. Il resto -- modello, classifica, template, JavaScript -- e' lo stesso
# file per entrambi: e' l'unico modo di non ritrovarsi due pagine che divergono.
RUOLI = {
    "portieri": {
        "titolo": "Accoppiate portieri",
        "sommario": (
            "Ogni giornata schieri il portiere con la partita piu' facile: una coppia vale il "
            "<strong>migliore dei due</strong>, quindi vincono le coppie <strong>complementari</strong>. "
            "&ldquo;Facile&rdquo; = alta probabilita' di non subire gol, stimata da attacco avversario, "
            "solidita' difensiva e fattore campo."
        ),
        "probabilita": "P(imbattibilita')",
        "probabilitaBreve": "Media P(imb.)",
        "sogliaEtichetta": "Soglia &ldquo;partita facile&rdquo;",
        "qualita": "Solidita'",
        "qualitaNota": (
            "La colonna <strong>Solidita'</strong> e' l'inverso della difesa, e non contiene "
            "l'attacco: a un portiere l'attacco della propria squadra non serve a niente. "
            "L'<strong>Attacco</strong> e' invece la proprieta' che conta quando quella squadra "
            "ce l'hai CONTRO -- e' lei a rovinare la giornata al portiere altrui. "
            "Difesa 0.70 = subisce il 30% in meno della media (piu' basso = piu' solido)."
        ),
        "tileMigliore": "Migliore accoppiata",
        "tileProbabilita": "Imbattibilita' media",
        "tileNotaProb": "schierando ogni volta il migliore",
        "budgetEtichetta": "Budget portieri",
        "criteri": ["copertura", "media", "guadagno", "punti", "efficienza"],
        "soglia": SOGLIA_FACILE,
        "budget": BUDGET["portieri"],
        "budgetMin": 0.06,
        "budgetMax": 0.40,
    },
    "attaccanti": {
        "titolo": "Accoppiate attaccanti",
        "sommario": (
            "Gli attaccanti li schieri <strong>tutti</strong>, non a turno: qui non si cerca "
            "il ricambio ma la <strong>distribuzione</strong>. Un buon gruppo e' quello in cui "
            "non capita mai che tutti e tre trovino insieme una difesa di ferro, cosi' che "
            "<strong>uno o l'altro</strong> possa segnare ogni giornata. &ldquo;Facile&rdquo; = "
            "alta probabilita' che la squadra segni, stimata da attacco proprio, difesa "
            "avversaria e fattore campo."
        ),
        "probabilita": "P(la squadra segna)",
        "probabilitaBreve": "Media P(segna)",
        "sogliaEtichetta": "Soglia &ldquo;partita da gol&rdquo;",
        "qualita": "Attacco",
        "qualitaNota": (
            "La colonna <strong>Attacco</strong> dice quanto segna la squadra rispetto alla "
            "media: 1.30 = il 30% in piu'. La <strong>Difesa</strong> qui non serve a chi "
            "attacca, e resta solo per completezza. I fantapunti contano <strong>+3 a gol</strong>: "
            "assist e voto restano fuori, perche' non dipendono dal calendario."
        ),
        "tileMigliore": "Miglior terzetto",
        "tileProbabilita": "P(segna) media",
        "tileNotaProb": "del migliore piazzato ogni giornata",
        "budgetEtichetta": "Budget attacco",
        # `totale` per primo, ed e' una scelta obbligata: e' il criterio iniziale.
        # La copertura, che sembrerebbe l'analogo naturale dei portieri, per gli
        # attaccanti non ordina niente -- satura in basso e in alto diventa "hai
        # l'Inter?". Resta disponibile, ma non e' quella che devi guardare.
        "criteri": ["totale", "media", "copertura", "punti", "guadagno", "efficienza"],
        "soglia": SOGLIA_ATTACCO,
        # Il tetto e' molto piu' alto perche' lo e' il mercato: un attaccante di Inter
        # costa tre volte il suo portiere. A 0.50 ci sta 30+15+5 oppure 20+20+10, ma
        # non due giocatori da 30 -- che e' il vincolo vero di un'asta.
        "budget": BUDGET["attaccanti"],
        "budgetMin": 0.20,
        "budgetMax": 0.90,
    },
}

# Etichette dei criteri nel menu a tendina. Stesse chiavi di `pairing.CRITERI`.
NOMI_CRITERI = {
    "copertura": "Copertura (giornate coperte)",
    "media": "Qualita' media della partita",
    "guadagno": "Guadagno dell'alternanza",
    "punti": "Fantapunti del migliore",
    "totale": "Fantapunti di tutto il gruppo",
    "efficienza": "Resa per credito speso",
}


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
    prezzi: dict[str, float],
    ruolo: str = "portieri",
) -> dict:
    if ruolo not in RUOLI:
        raise ValueError(f"ruolo='{ruolo}' sconosciuto: usa {sorted(RUOLI)}")
    testi = RUOLI[ruolo]

    # Che cosa rende "buona" una squadra dipende dal ruolo: per il portiere la
    # difesa, per l'attaccante l'attacco. Ordinare sempre allo stesso modo era
    # proprio l'errore che metteva l'Inter davanti a tutti in una pagina di portieri
    # grazie a un attacco che al portiere non serve.
    qualita = solidita if ruolo == "portieri" else (lambda f: f.attacco)

    ordinate = sorted(forze.values(), key=qualita, reverse=True)
    colori = {f.squadra: _colore_forza(i, len(ordinate)) for i, f in enumerate(ordinate)}

    squadre = [
        {
            "nome": f.squadra,
            "attacco": round(f.attacco, 3),
            "difesa": round(f.difesa, 3),
            "qualita": round(qualita(f), 3),
            "colore": colori[f.squadra],
            "neopromossa": f.neopromossa,
            "stagioni": f.stagioni_usate,
            "prezzo": prezzi.get(f.squadra, PREZZO_SCONOSCIUTO),
        }
        for f in ordinate
    ]

    calendario = {
        squadra: [
            {
                "g": i.giornata,
                "avv": i.avversario,
                "casa": i.in_casa,
                # `gol` serve solo al tooltip, tre decimali bastano. `pcs` e `pnt`
                # invece decidono chi schierare, e a 4 decimali NON bastavano: 69
                # partite su 760 finivano su un valore duplicato, cioe' il browser
                # vedeva in pari coppie che il modello distingue benissimo (Inter
                # 0.341552 e Juventus 0.341578 diventavano entrambe 0.3416, e la
                # pagina schierava l'Inter dove il terminale schierava la Juventus).
                # A sei decimali tutti e 760 i valori restano distinti: il divario
                # piu' stretto e' 1.2e-06.
                "gol": round(i.gol_attesi, 3),
                "pcs": round(i.probabilita, 6),
                "pnt": round(i.punti_attesi, 6),
            }
            for i in sorted(per_giornata.values(), key=lambda x: x.giornata)
        ]
        for squadra, per_giornata in impegni.items()
    }

    giornate = sorted({i.giornata for p in impegni.values() for i in p.values()})

    return {
        "stagione": STAGIONE_CORRENTE,
        "ruolo": ruolo,
        "testi": testi,
        "nomiCriteri": {k: NOMI_CRITERI[k] for k in testi["criteri"]},
        "dimensioni": [2, 3],
        "generato": date.today().isoformat(),
        "mu": round(mu, 3),
        "sogliaIniziale": testi["soglia"],
        "giornate": giornate,
        "squadre": squadre,
        "calendario": calendario,
        "prezzi": {s: prezzi.get(s, PREZZO_SCONOSCIUTO) for s in impegni},
        "budgetIniziale": testi["budget"],
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
  /* Default SCURO: e' la faccia "dashboard premium" della pagina. Il tema chiaro
     resta come override esplicito -- il pulsante in alto lo attiva, e l'host di
     un Artifact lo stampa da solo come data-theme="light". Niente switch
     automatico su prefers-color-scheme: il default voluto e' lo scuro, ovunque. */
  :root {
    color-scheme: dark;
    --plane: #0a0a0c;
    --surface: #141419;
    --surface-2: #1c1c23;
    --ink: #f4f4f6;
    --ink-2: #b6b6c2;
    --muted: #7d7d8c;
    --grid: #26262f;
    --bordo: rgba(255,255,255,0.08);
    --bordo-forte: rgba(255,255,255,0.15);
    --facile: #1baf7a;
    --media: #fab219;
    --difficile: #e0524f;
    --accento: #818cf8;
    --accento-solido: #6366f1;
    --accento-tenue: rgba(129,140,248,0.15);
    --glow: 0 0 0 1px rgba(129,140,248,0.28), 0 10px 34px rgba(99,102,241,0.20);
    --ombra: 0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px rgba(0,0,0,0.45);
    --raggio: 14px;
  }
  :root[data-theme="light"] {
    color-scheme: light;
    --plane: #f4f4f2;
    --surface: #ffffff;
    --surface-2: #fbfbfa;
    --ink: #14141a;
    --ink-2: #4c4c58;
    --muted: #8a8a96;
    --grid: #e6e6e0;
    --bordo: rgba(20,20,26,0.10);
    --bordo-forte: rgba(20,20,26,0.18);
    --difficile: #d03b3b;
    --accento: #4f46e5;
    --accento-solido: #4f46e5;
    --accento-tenue: rgba(79,70,229,0.10);
    --glow: 0 0 0 1px rgba(79,70,229,0.20), 0 10px 26px rgba(79,70,229,0.12);
    --ombra: 0 1px 2px rgba(20,20,26,0.05), 0 10px 26px rgba(20,20,26,0.07);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 30px 20px 76px;
    /* Due bagliori tenui -- indaco e teal -- danno profondita' allo sfondo scuro
       e sono cio' su cui le card "vetro" sembrano galleggiare. Fissi allo scroll. */
    background:
      radial-gradient(1100px 560px at 12% -14%, rgba(99,102,241,0.13), transparent 58%),
      radial-gradient(920px 500px at 108% -6%, rgba(27,175,122,0.07), transparent 55%),
      var(--plane);
    background-attachment: fixed;
    color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 14px; line-height: 1.5;
    -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
  }
  .wrap { max-width: 1180px; margin: 0 auto; }

  .testata { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
  h1 { font-size: 28px; font-weight: 760; margin: 0 0 4px; letter-spacing: -0.03em; line-height: 1.08; }
  h1 .tenue { color: var(--muted); font-weight: 600; letter-spacing: -0.02em; }
  h2 { font-size: 15px; margin: 0 0 14px; font-weight: 650; letter-spacing: -0.01em; }
  .sub { color: var(--ink-2); margin: 4px 0 26px; max-width: 780px; }
  .sub code, .sub strong { color: var(--ink); }
  .sub strong { font-weight: 650; }
  .r { color: var(--ink-2); }

  .tema {
    flex: none; cursor: pointer; width: 40px; height: 40px; border-radius: 11px;
    display: grid; place-items: center; font-size: 18px; line-height: 1;
    background: var(--surface); border: 1px solid var(--bordo); color: var(--ink);
    box-shadow: var(--ombra); transition: border-color .1s, transform .1s;
  }
  .tema:hover { border-color: var(--accento); transform: translateY(-1px); }

  .pannello {
    background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 88%, transparent), var(--surface));
    border: 1px solid var(--bordo);
    border-radius: var(--raggio); padding: 20px; margin-bottom: 20px;
    box-shadow: var(--ombra); backdrop-filter: blur(10px);
  }

  .controlli { display: flex; flex-wrap: wrap; gap: 22px; align-items: flex-end; }
  .campo { display: flex; flex-direction: column; gap: 7px; }
  .campo > label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 650; }
  .campo output { font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 650; }
  input[type=range] { width: 190px; accent-color: var(--accento-solido); height: 5px; }
  select, button {
    font: inherit; color: var(--ink); background: var(--surface-2);
    border: 1px solid var(--bordo); border-radius: 9px; padding: 7px 11px;
    transition: border-color .1s;
  }
  select:hover, button:hover { border-color: var(--bordo-forte); }
  button { cursor: pointer; font-weight: 550; }
  button.attivo {
    background: var(--accento-solido); border-color: var(--accento-solido); color: #fff;
    box-shadow: 0 4px 16px color-mix(in srgb, var(--accento-solido) 45%, transparent);
  }
  :where(button, select, input, tbody tr):focus-visible {
    outline: 2px solid var(--accento); outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
  }
  .gruppo { display: flex; gap: 0; }
  .gruppo button { border-radius: 0; }
  .gruppo button:first-child { border-radius: 9px 0 0 9px; }
  .gruppo button:last-child { border-radius: 0 9px 9px 0; margin-left: -1px; }

  .legenda { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-top: 16px;
             padding-top: 16px; border-top: 1px solid var(--grid); font-size: 12px; color: var(--ink-2); }
  .voce { display: inline-flex; align-items: center; gap: 6px; }
  .chip { width: 12px; height: 12px; border-radius: 4px; border: 1px solid var(--bordo); }
  .chip.facile { background: var(--facile); }
  .chip.media { background: var(--media); }
  .chip.difficile { background: var(--difficile); }
  .chip.verde { background: var(--facile); }
  .chip.giallo { background: var(--media); }
  .chip.rosso { background: var(--difficile); }

  .suggerimento { font-size: 12px; color: var(--ink-2); margin: 16px 0 0; line-height: 1.55; }
  .suggerimento strong { color: var(--ink); font-weight: 650; }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); gap: 14px; }
  .tile {
    position: relative; overflow: hidden;
    background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 86%, transparent), var(--surface));
    border: 1px solid var(--bordo); border-radius: var(--raggio); padding: 16px 18px;
    box-shadow: var(--ombra);
  }
  /* Il primo tile e' la coppia/terzetto migliore: si accende in indaco per essere
     la prima cosa che l'occhio prende. */
  .tile:first-child { border-color: color-mix(in srgb, var(--accento) 45%, var(--bordo)); box-shadow: var(--glow); }
  .tile:first-child::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, var(--accento), transparent 75%);
  }
  .tile .etichetta { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 650; }
  .tile .valore { font-size: 30px; font-weight: 770; letter-spacing: -0.035em; margin-top: 5px; line-height: 1.05; font-variant-numeric: tabular-nums; }
  .tile:first-child .valore { color: var(--accento); }
  .tile .nota { font-size: 12px; color: var(--muted); margin-top: 5px; }

  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 9px 11px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 650; }
  td.num, th.num { text-align: right; }
  tbody tr { cursor: pointer; transition: background .1s; }
  tbody tr:hover { background: color-mix(in srgb, var(--accento) 10%, transparent); }
  tbody tr.sel { background: var(--accento-tenue); box-shadow: inset 3px 0 0 var(--accento); }

  .striscia { display: flex; gap: 2px; }
  .cella {
    width: 9px; height: 22px; border-radius: 3px; flex: none;
  }
  .cella.facile { background: var(--facile); }
  .cella.media { background: var(--media); }
  .cella.difficile { background: var(--difficile); }

  .griglia { display: grid; grid-template-columns: repeat(auto-fill, minmax(116px, 1fr)); gap: 9px; }
  .box { border: 1px solid var(--bordo); border-radius: 10px; padding: 10px; background: var(--surface-2); }
  .box .g { font-size: 11px; color: var(--muted); }
  .box .sq { font-weight: 700; margin: 3px 0; }
  .box .avv { font-size: 12px; color: var(--ink-2); }
  .box .p { font-size: 12px; font-weight: 650; margin-top: 5px; font-variant-numeric: tabular-nums; }
  .box.facile { border-left: 3px solid var(--facile); }
  .box.media { border-left: 3px solid var(--media); }
  .box.difficile { border-left: 3px solid var(--difficile); }

  .tag { font-size: 10px; padding: 2px 6px; border-radius: 5px; border: 1px solid var(--bordo); color: var(--ink-2); background: var(--surface-2); }

  #tooltip {
    position: fixed; z-index: 50; pointer-events: none; opacity: 0;
    background: var(--surface); color: var(--ink);
    border: 1px solid var(--bordo-forte); border-radius: 9px; padding: 8px 11px;
    font-size: 12px; box-shadow: 0 12px 32px rgba(0,0,0,0.5); transition: opacity .08s;
    max-width: 240px; backdrop-filter: blur(10px);
  }
  #tooltip .t { font-weight: 700; }
  #tooltip .r { color: var(--ink-2); }
  .vuoto { color: var(--muted); padding: 20px 0; }
  .piede { color: var(--muted); font-size: 12px; margin-top: 30px; line-height: 1.6; }
  .piede a { color: var(--accento); }
</style>
</head>
<body>
<div class="wrap">

<div class="testata">
  <h1><span id="titolo"></span> <span class="tenue">— Serie A <span id="stagione"></span></span></h1>
  <button class="tema" id="tema" type="button" title="Tema chiaro/scuro" aria-label="Cambia tema chiaro/scuro">◐</button>
</div>
<p class="sub">
  <span id="sommario"></span> <span id="meta" class="r"></span>
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
      <label for="soglia"><span id="etichettaSoglia"></span> — <output id="outSoglia"></output></label>
      <input type="range" id="soglia" min="0.20" max="0.90" step="0.01">
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
      <label for="fissa" title="Se un portiere l'hai gia' preso, la domanda non e' piu' 'qual e' la coppia migliore' ma 'chi ci abbino'.">Squadra gia' presa</label>
      <select id="fissa"><option value="">nessuna</option></select>
    </div>
    <div class="campo">
      <label for="ordina">Ordina per</label>
      <select id="ordina"></select>
    </div>
    <div class="campo col-prezzo" id="campoBudget">
      <label for="budget" title="Quota del monte crediti che sei disposto a spendere per il reparto. Il tetto vale sulla somma dei prezzi del gruppo.">
        <span id="etichettaBudget"></span> — <output id="outBudget"></output></label>
      <input type="range" id="budget" step="0.01">
    </div>
  </div>
  <div class="legenda">
    <span class="voce"><span class="chip facile"></span> Facile — sopra soglia</span>
    <span class="voce"><span class="chip media"></span> Media</span>
    <span class="voce"><span class="chip difficile"></span> Difficile</span>
    <span class="r" id="notaEscludi"></span>
  </div>
  <p class="suggerimento">Il consiglio rende di piu' nelle <strong>finestre corte</strong>: nelle prime giornate il
    calendario pesa, sull'intera stagione si annulla e resta solo &ldquo;prendi i forti&rdquo;. Sposta
    <em>Alla giornata</em> su 8-10 e guarda la classifica riordinarsi.</p>
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
          <th class="num col-prezzo" title="Somma dei prezzi del gruppo, in quota del monte crediti.">Prezzo</th>
          <th class="num">Copertura</th>
          <th class="num">Facili</th>
          <th class="num" id="thProb"></th>
          <th class="num" id="thPunti"></th>
          <th class="num" title="Quanto rende alternare, rispetto a tenere sempre il migliore del gruppo. Vicino a zero = il secondo e' un doppione.">Guadagno</th>
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
        <th class="num">Attacco</th><th class="num">Difesa</th>
        <th class="num" id="thQualita"></th><th class="num col-prezzo">Prezzo</th><th>Note</th>
      </tr></thead>
      <tbody id="corpoForze"></tbody>
    </table>
  </div>
  <p class="r" style="font-size:12px;margin:12px 0 0" id="notaForze"></p>
</div>

<p class="piede" id="piede"></p>
</div>

<div id="tooltip"></div>

<script>
const DATI = __DATI__;

const $ = (id) => document.getElementById(id);
const pct = (x) => (x * 100).toFixed(0) + "%";
const pct1 = (x) => (x * 100).toFixed(1) + "%";

// Tema: il default e' scuro (dashboard premium). Se in una visita precedente hai
// scelto il chiaro, lo ripristiniamo; altrimenti non tocchiamo niente, cosi' l'host
// di un Artifact resta libero di stampare da solo il tema del lettore.
try {
  const salvato = localStorage.getItem("tema");
  if (salvato) document.documentElement.setAttribute("data-theme", salvato);
} catch (e) {}

const stato = {
  // Gli attaccanti si comprano a tre, i portieri a due: e' il default sensato,
  // il pulsante lo cambia comunque.
  dimensione: DATI.ruolo === "attaccanti" ? 3 : 2,
  soglia: DATI.sogliaIniziale,
  da: DATI.giornate[0],
  a: DATI.giornate[DATI.giornate.length - 1],
  ordina: DATI.testi.criteri[0],
  budget: DATI.budgetIniziale,
  fissa: "",
  selezione: null,
};

// Quante righe della classifica si disegnano. Oltre non serve a nessuno, ma il
// numero va detto: senza, "1140 combinazioni" sopra una tabella di 60 righe si
// legge come "le ho viste tutte".
const MOSTRATE = 60;

function classe(pcs, soglia) {
  if (pcs >= soglia) return "facile";
  if (pcs >= soglia - 0.12) return "media";
  return "difficile";
}

function giornateAttive() {
  return DATI.giornate.filter((g) => g >= stato.da && g <= stato.a);
}

const NOMI = DATI.squadre.map((s) => s.nome).sort();

// Rispecchia pairing.prezzo_gruppo: il costo e' la somma dei prezzi dei componenti.
function prezzo(gruppo) {
  let tot = 0;
  for (const s of gruppo) tot += DATI.prezzi[s] ?? 0.03;
  return tot;
}

// Rispecchia pairing.classifica: stessa tolleranza sui float, perche' 0.10 + 0.05
// in binario fa 0.15000000000000002 e senza epsilon la coppia da 15% sparirebbe
// da un budget del 15%.
function ammessa(gruppo) {
  return prezzo(gruppo) <= stato.budget + 1e-9;
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
  let somma = 0, sommaPunti = 0, sommaTutti = 0, facili = 0, valide = 0;
  const scelte = [];
  const singole = Object.fromEntries(gruppo.map((s) => [s, 0]));
  for (const g of giornate) {
    let best = null;
    for (const s of gruppo) {
      const imp = INDICE[s]?.[g];
      if (!imp) continue;
      singole[s] += imp.pcs;
      // Somma su TUTTO il gruppo: gli attaccanti scendono in campo tutti.
      sommaTutti += imp.pnt;
      if (best === null || imp.pcs > best.pcs) best = imp;
    }
    if (!best) continue;
    somma += best.pcs;
    // Chi schierare non cambia fra le due metriche: entrambe decrescono al
    // crescere dei gol attesi. Cambia la somma su tutte le giornate.
    sommaPunti += best.pnt;
    valide++;
    if (best.pcs >= stato.soglia) facili++;
    // A parita' esatta il valore della coppia e' lo stesso comunque, ma il portiere
    // da schierare e' indifferente: si mostrano entrambi invece di fingere una
    // preferenza. `best` resta il primo in ordine alfabetico, come in pairing.py.
    const pari = gruppo.filter((s) => INDICE[s]?.[g]?.pcs === best.pcs);
    scelte.push(pari.length > 1 ? { ...best, pari } : best);
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
    punti: sommaPunti,
    mediaPunti: sommaPunti / valide,
    tutti: sommaTutti,
    prezzo: prezzo(gruppo),
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
  const res = [];
  for (const gruppo of combinazioni(NOMI, stato.dimensione)) {
    if (stato.fissa && !gruppo.includes(stato.fissa)) continue;
    if (!ammessa(gruppo)) continue;
    const v = valuta(gruppo, giornate);
    if (v) res.push(v);
  }
  // Stessi criteri di pairing.CRITERI, stesso ordine di spareggio.
  const eff = (c) => (c.prezzo ? c.media / c.prezzo : 0);
  const criteri = {
    copertura: (x, y) => (y.copertura - x.copertura) || (y.media - x.media),
    media: (x, y) => (y.media - x.media) || (y.copertura - x.copertura),
    guadagno: (x, y) => (y.guadagno - x.guadagno) || (y.media - x.media),
    punti: (x, y) => (y.punti - x.punti) || (y.copertura - x.copertura),
    totale: (x, y) => (y.tutti - x.tutti) || (y.copertura - x.copertura),
    efficienza: (x, y) => (eff(y) - eff(x)) || (y.copertura - x.copertura),
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
  const pari = imp.pari
    ? `<div class="r">Pari merito con ${imp.pari.filter((s) => s !== imp.squadra).join(", ")}: scegli chi vuoi.</div>`
    : "";
  const gol = DATI.ruolo === "attaccanti" ? "Gol attesi segnati" : "Gol attesi subiti";
  return `<div class="t">${imp.avv} ${imp.casa ? "in casa" : "in trasferta"}</div>
          <div class="r">Giornata ${imp.g}</div>
          <div class="r">${DATI.testi.probabilita}: <strong>${pct1(imp.pcs)}</strong></div>
          <div class="r">${gol}: ${imp.gol.toFixed(2)}</div>${pari}`;
}

// ---- render ----
function render() {
  const res = classifica();
  const troncata = res.length > MOSTRATE;
  $("quante").textContent =
    `— ${res.length.toLocaleString("it-IT")} combinazioni sulle giornate ${stato.da}-${stato.a}`
    + (troncata ? `, mostrate le prime ${MOSTRATE}` : "");

  const migliore = res[0];
  const attaccanti = DATI.ruolo === "attaccanti";
  $("tiles").innerHTML = migliore ? `
    <div class="tile">
      <div class="etichetta">${DATI.testi.tileMigliore}</div>
      <div class="valore" style="font-size:19px">${migliore.squadre.join(" + ")}</div>
      <div class="nota">giornate ${stato.da}-${stato.a} · costa ${pct(migliore.prezzo)}</div>
    </div>
    <div class="tile">
      <div class="etichetta">Giornate coperte</div>
      <div class="valore">${pct(migliore.copertura)}</div>
      <div class="nota">${migliore.facili} su ${migliore.totali} sopra soglia</div>
    </div>
    <div class="tile">
      <div class="etichetta">${DATI.testi.tileProbabilita}</div>
      <div class="valore">${pct1(migliore.media)}</div>
      <div class="nota">${DATI.testi.tileNotaProb}</div>
    </div>
    <div class="tile">
      <div class="etichetta">Fantapunti nella finestra</div>
      <div class="valore">${(attaccanti ? migliore.tutti : migliore.punti).toFixed(1)}</div>
      <div class="nota">${attaccanti ? "di tutto il gruppo, solo i gol" : "bonus/malus, voto base escluso"}</div>
    </div>
    <div class="tile">
      <div class="etichetta">Guadagno dell'alternanza</div>
      <div class="valore">${(migliore.guadagno * 100).toFixed(1)}</div>
      <div class="nota">punti sopra il solo ${migliore.migliorSingolo} (${pct1(migliore.mediaSingolo)})</div>
    </div>` : `<div class="tile"><div class="etichetta">Nessuna combinazione</div></div>`;

  const corpo = $("corpo");
  corpo.innerHTML = "";
  if (!res.length) {
    corpo.innerHTML = `<tr><td colspan="9" class="vuoto">Nessuna combinazione con questi filtri: alza il budget o togli la squadra fissa.</td></tr>`;
  }
  const chiave = (c) => c.squadre.join("|");
  if (!stato.selezione || !res.some((c) => chiave(c) === stato.selezione)) {
    stato.selezione = migliore ? chiave(migliore) : null;
  }

  res.slice(0, MOSTRATE).forEach((c, i) => {
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
      <td class="num col-prezzo">${pct(c.prezzo)}</td>
      <td class="num">${pct(c.copertura)}</td>
      <td class="num">${c.facili}/${c.totali}</td>
      <td class="num">${pct1(c.media)}</td>
      <td class="num" title="${c.mediaPunti.toFixed(3)} a giornata schierando il migliore">${(attaccanti ? c.tutti : c.punti).toFixed(1)}</td>
      <td class="num" title="Da solo, ${c.migliorSingolo} vale ${pct1(c.mediaSingolo)}">${(c.guadagno * 100).toFixed(1)}</td>
      <td><div class="striscia">${celle}</div></td>`;
    tr.onclick = () => { stato.selezione = chiave(c); render(); };
    corpo.appendChild(tr);
  });

  if (troncata) {
    const tr = document.createElement("tr");
    tr.style.cursor = "default";
    tr.innerHTML = `<td colspan="9" class="vuoto">
      … altre ${(res.length - MOSTRATE).toLocaleString("it-IT")} combinazioni, peggiori di queste.
      Restringi il budget o fissa la squadra che hai gia' preso.</td>`;
    corpo.appendChild(tr);
  }

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
    // Con un pari merito il valore e' identico: si elencano tutte le squadre e i
    // rispettivi avversari, perche' dire "schiera Inter" sarebbe una precisione finta.
    const insieme = imp.pari || [imp.squadra];
    const avversari = insieme
      .map((s) => { const i2 = INDICE[s][imp.g]; return `${i2.casa ? "vs" : "@"} ${i2.avv}`; })
      .join(" · ");
    return `<div class="box ${cl}">
      <div class="g">Giornata ${imp.g}</div>
      <div class="sq">${insieme.join(" / ")}</div>
      <div class="avv">${avversari}</div>
      <div class="p">${pct(imp.pcs)}${imp.pari ? ` <span class="r">pari merito</span>` : ""}</div>
    </div>`;
  }).join("") : `<p class="vuoto">Seleziona una riga della classifica.</p>`;
}

// Due squadre vicine in classifica la cui QUALITA' (difesa per i portieri, attacco
// per gli attaccanti) differisce meno dell'1% sono, per il modello, indistinguibili:
// Juventus e Inter in porta stanno a 0.4%. Segnalarlo evita di fingere una gerarchia
// che il modello non ha -- e' lo stesso "pari merito" gia' mostrato giornata per
// giornata, portato sulla forza di squadra. La tabella e' gia' ordinata per qualita'.
const TOLLERANZA_PARI = 0.01;

function renderForze() {
  const sq = DATI.squadre;
  $("corpoForze").innerHTML = sq.map((s, i) => {
    const note = [];
    const pari = [];
    if (i > 0 && Math.abs(s.qualita - sq[i - 1].qualita) / sq[i - 1].qualita < TOLLERANZA_PARI)
      pari.push(sq[i - 1].nome);
    if (i < sq.length - 1 && Math.abs(sq[i + 1].qualita - s.qualita) / s.qualita < TOLLERANZA_PARI)
      pari.push(sq[i + 1].nome);
    if (pari.length)
      note.push(`<span class="tag" title="Differenza sotto l'1%: per il modello sono equivalenti, l'ordine e' arbitrario.">≈ pari con ${pari.join(", ")}</span>`);
    if (s.neopromossa && !s.stagioni) note.push(`<span class="tag">neopromossa — nessuno storico</span>`);
    else if (s.neopromossa) note.push(`<span class="tag">neopromossa — ${s.stagioni} stagioni di A, non l'ultima</span>`);
    else if (s.stagioni < 5) note.push(`<span class="tag">solo ${s.stagioni} stagioni di storico</span>`);
    return `<tr>
      <td class="num">${i + 1}</td>
      <td><strong>${s.nome}</strong></td>
      <td><span class="chip ${s.colore}" title="${s.colore}"></span></td>
      <td class="num">${s.attacco.toFixed(2)}</td>
      <td class="num">${s.difesa.toFixed(2)}</td>
      <td class="num">${s.qualita.toFixed(2)}</td>
      <td class="num col-prezzo">${pct(s.prezzo)}</td>
      <td>${note.join(" ")}</td>
    </tr>`;
  }).join("");
}

// ---- controlli ----
function sincronizza() {
  $("outSoglia").textContent = pct(stato.soglia);
  $("outDa").textContent = stato.da;
  $("outA").textContent = stato.a;
  $("outBudget").textContent = pct(stato.budget) + " del monte crediti";
  $("btn2").className = stato.dimensione === 2 ? "attivo" : "";
  $("btn3").className = stato.dimensione === 3 ? "attivo" : "";
  $("budget").value = stato.budget;
  $("fissa").value = stato.fissa;
  // Quali sono i piu' cari che ci stanno ancora dentro: e' l'informazione che
  // serve davvero mentre l'asta corre, molto piu' del numero in se'.
  const dentro = NOMI.filter((n) => (DATI.prezzi[n] ?? 0.03) <= stato.budget + 1e-9)
    .sort((a, b) => (DATI.prezzi[b] ?? 0) - (DATI.prezzi[a] ?? 0));
  const top = dentro.slice(0, 4).map((n) => `${n} (${pct(DATI.prezzi[n])})`).join(", ");
  $("notaEscludi").textContent = dentro.length
    ? `Con ${pct(stato.budget)} il piu' caro che ti puoi permettere: ${top}.`
    : "Budget troppo basso: nessun giocatore rientra.";
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
$("fissa").onchange = (e) => {
  stato.fissa = e.target.value;
  stato.selezione = null; sincronizza(); render();
};
$("budget").oninput = (e) => {
  stato.budget = +e.target.value;
  stato.selezione = null; sincronizza(); render();
};
$("btn2").onclick = () => { stato.dimensione = 2; stato.selezione = null; sincronizza(); render(); };
$("btn3").onclick = () => { stato.dimensione = 3; stato.selezione = null; sincronizza(); render(); };
$("tema").onclick = () => {
  const nuovo = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", nuovo);
  try { localStorage.setItem("tema", nuovo); } catch (e) {}
};

// ---- avvio ----
// Tutte le etichette che dipendono dal ruolo arrivano dal JSON, cosi' portieri e
// attaccanti condividono lo stesso template invece di averne una copia a testa.
document.title = `${DATI.testi.titolo} — Serie A ${DATI.stagione}`;
$("titolo").textContent = DATI.testi.titolo;
$("sommario").innerHTML = DATI.testi.sommario;
$("etichettaSoglia").innerHTML = DATI.testi.sogliaEtichetta;
$("etichettaBudget").textContent = DATI.testi.budgetEtichetta;
$("thProb").textContent = DATI.testi.probabilitaBreve;
$("thPunti").textContent = "Fantapunti";
$("thPunti").title = DATI.ruolo === "attaccanti"
  ? "Gol attesi di tutto il gruppo moltiplicati per il bonus gol (+3). Assist e voto esclusi: non dipendono dal calendario."
  : "Bonus/malus attesi schierando ogni giornata il migliore: -1 per ogni gol subito, +1 se imbattuto. Voto base escluso, quindi il totale e' negativo: conta il confronto, non il segno.";
$("thQualita").textContent = DATI.testi.qualita;
$("notaForze").innerHTML = DATI.testi.qualitaNota;
$("ordina").innerHTML = DATI.testi.criteri
  .map((k) => `<option value="${k}">${DATI.nomiCriteri[k]}</option>`).join("");
$("ordina").value = stato.ordina;
$("btn3").textContent = DATI.ruolo === "attaccanti" ? "Terzetto" : "Tripla";
$("stagione").textContent = DATI.stagione;
$("fissa").insertAdjacentHTML("beforeend",
  NOMI.map((n) => `<option value="${n}">${n}</option>`).join(""));
$("budget").min = DATI.testi.budgetMin;
$("budget").max = DATI.testi.budgetMax;
$("budget").value = stato.budget;
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
