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
esattamente cio' che vede il browser: `pcs` e `pnt` sono salvati a 4 decimali, e un
arrotondamento potrebbe in teoria ribaltare un confronto fra due partite quasi identiche.
"""

import json
import re
import sys
from itertools import combinations
from pathlib import Path

from fantaportieri.config import MAX_ALTISSIMA, MAX_COSTOSI, SOGLIA_FACILE
from fantaportieri.data_io import leggi_calendario, leggi_storico
from fantaportieri.pairing import classifica
from fantaportieri.scoring import costruisci_impegni
from fantaportieri.strength import calcola_forze, media_gol_lega

RADICE = Path(__file__).parent
HTML = RADICE / "classifica_portieri.html"

# I casi da confrontare: dimensione, tetto fascia altissima, tetto cari, criterio.
# 9 = nessun limite, come nel menu della pagina.
CASI = [
    (2, MAX_ALTISSIMA, MAX_COSTOSI, "copertura"),
    (2, 9, 9, "copertura"),
    (2, 9, 9, "punti"),
    (2, 9, 9, "media"),
    (2, 0, 0, "guadagno"),
    (2, 1, 2, "punti"),
    (3, 0, 0, "copertura"),
    (3, 1, 1, "punti"),
]


def _dati_incorporati() -> dict:
    if not HTML.exists():
        print(f"{HTML.name} non esiste. Lancia prima 'python run.py'.")
        sys.exit(1)
    testo = HTML.read_text(encoding="utf-8")
    trovato = re.search(r"const DATI = (\{.*?\});", testo, re.DOTALL)
    if not trovato:
        print("Non trovo il blocco 'const DATI = {...}' nell'HTML: il modello e' cambiato.")
        sys.exit(1)
    return json.loads(trovato.group(1))


def classifica_come_il_browser(dati, dimensione, max_alt, max_cost, soglia, ordina):
    """Traduzione fedele di valuta()/ammessa()/classifica() da report.py."""
    indice = {s: {i["g"]: i for i in lista} for s, lista in dati["calendario"].items()}
    costose, altissime = set(dati["costose"]), set(dati["altissime"])
    nomi = sorted(s["nome"] for s in dati["squadre"])

    risultati = []
    for gruppo in combinations(nomi, dimensione):
        if sum(s in altissime for s in gruppo) > max_alt:
            continue
        if sum(s in costose for s in gruppo) > max_cost:
            continue

        somma = somma_punti = 0.0
        facili = valide = 0
        singole = {s: 0.0 for s in gruppo}
        for g in dati["giornate"]:
            migliore = None
            for s in gruppo:
                imp = indice[s].get(g)
                if not imp:
                    continue
                singole[s] += imp["pcs"]
                if migliore is None or imp["pcs"] > migliore["pcs"]:
                    migliore = imp
            if not migliore:
                continue
            somma += migliore["pcs"]
            somma_punti += migliore["pnt"]
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
                "guadagno": media - singole[miglior_singolo] / valide,
            }
        )

    chiavi = {
        "copertura": lambda c: (c["copertura"], c["media"]),
        "media": lambda c: (c["media"], c["copertura"]),
        "guadagno": lambda c: (c["guadagno"], c["media"]),
        "punti": lambda c: (c["punti"], c["copertura"]),
    }
    risultati.sort(key=chiavi[ordina], reverse=True)
    return risultati


def main() -> None:
    dati = _dati_incorporati()

    storico = leggi_storico(RADICE / "data" / "storico.csv")
    calendario = leggi_calendario(RADICE / "data" / "calendario.csv")
    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}
    mu = media_gol_lega(storico)
    forze = calcola_forze(storico, squadre)
    impegni = costruisci_impegni(calendario, forze, mu)
    giornate = sorted({p.giornata for p in calendario})

    print(f"Confronto su {len(CASI)} configurazioni, prime 15 posizioni di ciascuna.\n")
    problemi = 0
    for dimensione, max_alt, max_cost, ordina in CASI:
        py = classifica(
            impegni, giornate, SOGLIA_FACILE, dimensione,
            max_altissima=max_alt, max_costosi=max_cost, ordina=ordina,
        )
        js = classifica_come_il_browser(
            dati, dimensione, max_alt, max_cost, SOGLIA_FACILE, ordina
        )
        etichetta = f"dim={dimensione} altissima<={max_alt} cari<={max_cost} per={ordina}"

        if len(py) != len(js):
            print(f"  {etichetta:<44} DIVERSE: {len(py)} combinazioni in Python, {len(js)} nel browser")
            problemi += 1
            continue

        a = [c.squadre for c in py[:15]]
        b = [c["squadre"] for c in js[:15]]
        if a != b:
            print(f"  {etichetta:<44} ORDINE DIVERSO")
            for i, (x, y) in enumerate(zip(a, b), 1):
                if x != y:
                    print(f"      posizione {i}: Python {' + '.join(x)} / browser {' + '.join(y)}")
                    break
            problemi += 1
        else:
            print(f"  {etichetta:<44} ok ({len(py)} combinazioni)")

    print()
    if problemi:
        print(f"{problemi} configurazioni divergono: pairing.py e il JS di report.py non sono allineati.")
        sys.exit(1)
    print("Le due implementazioni coincidono.")


if __name__ == "__main__":
    main()
