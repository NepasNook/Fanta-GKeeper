"""Python e JavaScript dicono la stessa cosa?

La pagina HTML ricalcola tutto nel browser, quindi la logica di classifica esiste
due volte: in `pairing.py` e riscritta in JS dentro `report.py`. Se le due versioni
divergono non se ne accorge nessuno -- il terminale mostra una classifica, la pagina
un'altra, ed entrambe sembrano plausibili.

    python prova_coerenza.py        (dopo aver lanciato run.py almeno una volta)

Questo script traduce la logica JS in Python, la applica ai dati REALMENTE incorporati
nell'HTML e confronta il risultato con `pairing.classifica`. Non esegue il JavaScript:
ne rispecchia il comportamento riga per riga. Se modifichi uno dei due lati e non
l'altro, qui salta fuori.

Usa i valori arrotondati letti dal JSON, non quelli a piena precisione, perche' e'
esattamente cio' che vede il browser. Non e' un dettaglio: con `pcs` a 4 decimali
69 partite su 760 finivano su un valore duplicato e la pagina schierava un portiere
diverso dal terminale su coppie che il modello distingue benissimo. Da qui i sei
decimali in `report.costruisci_dati`.

Confronta due cose, non una: l'ORDINE della classifica e le SCELTE giornata per
giornata. Solo l'ordine non basta, ed e' il motivo per cui quel difetto era
sopravvissuto: quando due squadre della stessa coppia risultano in pari il punteggio
della coppia e' identico comunque, quindi la classifica coincideva e il controllo
passava mentre le due implementazioni consigliavano portieri diversi.
"""

import json
import re
import sys
from itertools import combinations
from pathlib import Path

from fantaportieri.config import BUDGET, SOGLIA_ATTACCO, SOGLIA_FACILE
from fantaportieri.data_io import leggi_calendario, leggi_prezzi, leggi_storico
from fantaportieri.pairing import classifica
from fantaportieri.scoring import costruisci_impegni, costruisci_impegni_offensivi
from fantaportieri.strength import calcola_forze, media_gol_lega

RADICE = Path(__file__).parent
PAGINE = {
    "portieri": (RADICE / "classifica_portieri.html", SOGLIA_FACILE),
    "attaccanti": (RADICE / "classifica_attaccanti.html", SOGLIA_ATTACCO),
}

# I casi da confrontare: dimensione, budget, criterio, squadra gia' presa.
# `None` = nessun tetto; `"suo"` = il budget del ruolo, che e' diverso fra le due
# pagine (15% in porta, 50% in attacco) e va quindi risolto per pagina.
CASI = [
    (2, "suo", "copertura", ""),
    (2, None, "copertura", ""),
    (2, None, "punti", ""),
    (2, None, "media", ""),
    (2, "suo", "guadagno", ""),
    (2, None, "efficienza", ""),
    (2, "suo", "efficienza", ""),
    (3, "suo", "copertura", ""),
    (3, "suo", "punti", ""),
    (3, None, "totale", ""),
    (3, "suo", "totale", ""),
    (2, None, "copertura", "Inter"),
    (2, "suo", "punti", "Bologna"),
    (3, None, "guadagno", "Juventus"),
]


def _dati_incorporati(percorso: Path) -> dict:
    if not percorso.exists():
        print(f"{percorso.name} non esiste. Lancia prima 'python run.py'.")
        sys.exit(1)
    testo = percorso.read_text(encoding="utf-8")
    trovato = re.search(r"const DATI = (\{.*?\});", testo, re.DOTALL)
    if not trovato:
        print("Non trovo il blocco 'const DATI = {...}' nell'HTML: il modello e' cambiato.")
        sys.exit(1)
    return json.loads(trovato.group(1))


def classifica_come_il_browser(dati, dimensione, budget, soglia, ordina, fissa=""):
    """Traduzione fedele di valuta()/ammessa()/classifica() da report.py."""
    indice = {s: {i["g"]: i for i in lista} for s, lista in dati["calendario"].items()}
    nomi = sorted(s["nome"] for s in dati["squadre"])
    prezzi = dati["prezzi"]

    risultati = []
    for gruppo in combinations(nomi, dimensione):
        if fissa and fissa not in gruppo:
            continue
        prezzo = sum(prezzi.get(s, 0.03) for s in gruppo)
        if budget is not None and prezzo > budget + 1e-9:
            continue

        somma = somma_punti = somma_tutti = 0.0
        facili = valide = 0
        singole = {s: 0.0 for s in gruppo}
        scelte = {}
        for g in dati["giornate"]:
            migliore = None
            scelta = None
            for s in gruppo:
                imp = indice[s].get(g)
                if not imp:
                    continue
                singole[s] += imp["pcs"]
                somma_tutti += imp["pnt"]
                # Confronto stretto, come il JS: a parita' resta il primo incontrato,
                # cioe' il primo in ordine alfabetico.
                if migliore is None or imp["pcs"] > migliore["pcs"]:
                    migliore, scelta = imp, s
            if not migliore:
                continue
            somma += migliore["pcs"]
            somma_punti += migliore["pnt"]
            scelte[g] = scelta
            valide += 1
            if migliore["pcs"] >= soglia:
                facili += 1
        if not valide:
            continue

        media = somma / valide
        miglior_singolo = max(singole, key=lambda s: singole[s])
        risultati.append(
            {
                "squadre": gruppo,
                "copertura": facili / valide,
                "media": media,
                "punti": somma_punti,
                "tutti": somma_tutti,
                "prezzo": prezzo,
                "guadagno": media - singole[miglior_singolo] / valide,
                "scelte": scelte,
            }
        )

    chiavi = {
        "copertura": lambda c: (c["copertura"], c["media"]),
        "media": lambda c: (c["media"], c["copertura"]),
        "guadagno": lambda c: (c["guadagno"], c["media"]),
        "punti": lambda c: (c["punti"], c["copertura"]),
        "totale": lambda c: (c["tutti"], c["copertura"]),
        "efficienza": lambda c: (c["media"] / c["prezzo"] if c["prezzo"] else 0.0, c["copertura"]),
    }
    risultati.sort(key=chiavi[ordina], reverse=True)
    return risultati


def _confronta(ruolo: str, impegni, giornate, prezzi, soglia, dati) -> int:
    print(f"--- {ruolo} ---")
    problemi = 0
    for dimensione, budget, ordina, fissa in CASI:
        if budget == "suo":
            budget = BUDGET[ruolo]
        if ordina not in dati["nomiCriteri"]:
            continue   # criterio non offerto da questa pagina
        py = classifica(
            impegni, giornate, soglia, prezzi, dimensione,
            budget=budget, ordina=ordina, obbligatoria=fissa or None,
        )
        js = classifica_come_il_browser(dati, dimensione, budget, soglia, ordina, fissa)
        etichetta = (
            f"dim={dimensione} budget={'-' if budget is None else f'{budget:.0%}'} per={ordina}"
            + (f" fissa={fissa}" if fissa else "")
        )

        if len(py) != len(js):
            print(f"  {etichetta:<48} DIVERSE: {len(py)} in Python, {len(js)} nel browser")
            problemi += 1
            continue

        a = [c.squadre for c in py[:15]]
        b = [c["squadre"] for c in js[:15]]
        if a != b:
            print(f"  {etichetta:<48} ORDINE DIVERSO")
            for i, (x, y) in enumerate(zip(a, b), 1):
                if x != y:
                    print(f"      posizione {i}: Python {' + '.join(x)} / browser {' + '.join(y)}")
                    break
            problemi += 1
            continue

        # Stesso ordine, ma schierano lo stesso giocatore? A parita' esatta il
        # punteggio del gruppo non cambia, quindi qui l'ordine non aiuta.
        divergenti = [
            (i, g, c.scelte[g], d["scelte"][g])
            for i, (c, d) in enumerate(zip(py[:15], js[:15]), 1)
            for g in sorted(c.scelte)
            if c.scelte[g] != d["scelte"].get(g)
        ]
        if divergenti:
            i, g, x, y = divergenti[0]
            print(f"  {etichetta:<48} SCELTE DIVERSE ({len(divergenti)} giornate)")
            print(f"      posizione {i}, giornata {g}: Python sceglie {x} / browser {y}")
            problemi += 1
        else:
            print(f"  {etichetta:<48} ok ({len(py)} combinazioni)")
    print()
    return problemi


def main() -> None:
    storico = leggi_storico(RADICE / "data" / "storico.csv")
    calendario = leggi_calendario(RADICE / "data" / "calendario.csv")
    prezzi = leggi_prezzi(RADICE / "data" / "prezzi.csv")
    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}
    mu = media_gol_lega(storico)
    forze = calcola_forze(storico, squadre)
    giornate = sorted({p.giornata for p in calendario})

    costruttori = {
        "portieri": costruisci_impegni,
        "attaccanti": costruisci_impegni_offensivi,
    }

    print(f"Confronto su {len(CASI)} configurazioni per pagina, prime 15 posizioni di ciascuna.")
    print("Si confrontano l'ordine della classifica E il giocatore scelto a ogni giornata.\n")

    problemi = 0
    for ruolo, (percorso, soglia) in PAGINE.items():
        dati = _dati_incorporati(percorso)
        impegni = costruttori[ruolo](calendario, forze, mu)
        problemi += _confronta(ruolo, impegni, giornate, prezzi[ruolo], soglia, dati)

    if problemi:
        print(f"{problemi} configurazioni divergono: pairing.py e il JS di report.py non sono allineati.")
        sys.exit(1)
    print("Le due implementazioni coincidono, su entrambe le pagine.")


if __name__ == "__main__":
    main()
