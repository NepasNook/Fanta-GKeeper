"""Lettura e scrittura dei CSV normalizzati.

Questi due file sono il contratto fra lo scraping e il motore di calcolo:
lo scraper li produce, tutto il resto legge solo questi. Si possono anche
compilare a mano se un sito e' ostico.

data/storico.csv     stagione,squadra,partite,gol_fatti,gol_subiti
data/calendario.csv  giornata,casa,trasferta
data/prezzi.csv      squadra,portiere,attaccante  <- NON scaricato: si scrive a mano
"""

import csv
from pathlib import Path

from .config import PREZZI_DEFAULT, normalizza_squadra
from .models import Partita, StatStagione

COLONNE_STORICO = ["stagione", "squadra", "partite", "gol_fatti", "gol_subiti"]
COLONNE_CALENDARIO = ["giornata", "casa", "trasferta"]
COLONNE_PREZZI = ["squadra", "portiere", "attaccante"]
# Le colonne del CSV sono al singolare (il giocatore), le chiavi in memoria al
# plurale (il ruolo/la pagina). Questa tabella tiene insieme le due convenzioni.
RUOLO_DA_COLONNA = {"portiere": "portieri", "attaccante": "attaccanti"}


class ErroreDati(Exception):
    """Un CSV di input e' assente o malformato."""


def _controlla_colonne(lettore: csv.DictReader, attese: list[str], percorso: Path) -> None:
    mancanti = [c for c in attese if c not in (lettore.fieldnames or [])]
    if mancanti:
        raise ErroreDati(
            f"{percorso}: mancano le colonne {', '.join(mancanti)}. "
            f"Attese: {', '.join(attese)}"
        )


def leggi_storico(percorso: Path) -> list[StatStagione]:
    if not percorso.exists():
        raise ErroreDati(f"{percorso} non esiste. Lancia 'python run.py --scarica'.")

    righe: list[StatStagione] = []
    with percorso.open(encoding="utf-8-sig", newline="") as f:
        lettore = csv.DictReader(f)
        _controlla_colonne(lettore, COLONNE_STORICO, percorso)
        for n, riga in enumerate(lettore, start=2):
            try:
                partite = int(riga["partite"])
                if partite <= 0:
                    raise ValueError("partite deve essere > 0")
                righe.append(
                    StatStagione(
                        stagione=riga["stagione"].strip(),
                        squadra=normalizza_squadra(riga["squadra"]),
                        partite=partite,
                        gol_fatti=int(riga["gol_fatti"]),
                        gol_subiti=int(riga["gol_subiti"]),
                    )
                )
            except (ValueError, KeyError) as e:
                raise ErroreDati(f"{percorso} riga {n}: {e}") from e

    if not righe:
        raise ErroreDati(f"{percorso} e' vuoto.")
    return righe


def leggi_calendario(percorso: Path) -> list[Partita]:
    if not percorso.exists():
        raise ErroreDati(f"{percorso} non esiste. Lancia 'python run.py --scarica'.")

    partite: list[Partita] = []
    with percorso.open(encoding="utf-8-sig", newline="") as f:
        lettore = csv.DictReader(f)
        _controlla_colonne(lettore, COLONNE_CALENDARIO, percorso)
        for n, riga in enumerate(lettore, start=2):
            try:
                casa = normalizza_squadra(riga["casa"])
                trasferta = normalizza_squadra(riga["trasferta"])
                if casa == trasferta:
                    raise ValueError(f"{casa} non puo' giocare contro se stessa")
                partite.append(
                    Partita(giornata=int(riga["giornata"]), casa=casa, trasferta=trasferta)
                )
            except (ValueError, KeyError) as e:
                raise ErroreDati(f"{percorso} riga {n}: {e}") from e

    if not partite:
        raise ErroreDati(f"{percorso} e' vuoto.")
    return partite


def leggi_prezzi(percorso: Path) -> dict[str, dict[str, float]]:
    """Prezzi attesi per ruolo, in quota del budget: {"portieri": {...}, "attaccanti": {...}}.

    A differenza degli altri due, questo CSV non lo produce nessuno scraper: i prezzi
    d'asta non stanno da nessuna parte prima che esca il listone, e comunque
    dipendono dalla tua lega. Se il file non c'e' si usano i valori di `config.py`,
    cosi' il progetto gira comunque: e' una stima, non un dato, e va trattata come tale.
    """
    if not percorso.exists():
        return {ruolo: dict(tabella) for ruolo, tabella in PREZZI_DEFAULT.items()}

    prezzi: dict[str, dict[str, float]] = {r: {} for r in RUOLO_DA_COLONNA.values()}
    with percorso.open(encoding="utf-8-sig", newline="") as f:
        lettore = csv.DictReader(f)
        _controlla_colonne(lettore, COLONNE_PREZZI, percorso)
        for n, riga in enumerate(lettore, start=2):
            try:
                squadra = normalizza_squadra(riga["squadra"])
                for colonna, ruolo in RUOLO_DA_COLONNA.items():
                    valore = float(riga[colonna])
                    if not 0.0 <= valore <= 1.0:
                        raise ValueError(
                            f"{colonna}={valore} fuori da 0..1 (e' una quota del budget, non crediti)"
                        )
                    prezzi[ruolo][squadra] = valore
            except (ValueError, KeyError) as e:
                raise ErroreDati(f"{percorso} riga {n}: {e}") from e

    if not any(prezzi.values()):
        raise ErroreDati(f"{percorso} e' vuoto.")
    return prezzi


def scrivi_prezzi(percorso: Path, prezzi: dict[str, dict[str, float]]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    squadre = sorted({s for tabella in prezzi.values() for s in tabella})
    # Ordinate per prezzo dell'attaccante: e' la colonna con piu' spread, quindi
    # il file si legge come un listino invece che come un elenco alfabetico.
    squadre.sort(key=lambda s: (-prezzi["attaccanti"].get(s, 0.0), s))
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(COLONNE_PREZZI)
        for squadra in squadre:
            scrittore.writerow([
                squadra,
                f"{prezzi['portieri'].get(squadra, 0.0):.2f}",
                f"{prezzi['attaccanti'].get(squadra, 0.0):.2f}",
            ])


def scrivi_storico(percorso: Path, righe: list[StatStagione]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(COLONNE_STORICO)
        for r in righe:
            scrittore.writerow([r.stagione, r.squadra, r.partite, r.gol_fatti, r.gol_subiti])


def scrivi_calendario(percorso: Path, partite: list[Partita]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(COLONNE_CALENDARIO)
        for p in partite:
            scrittore.writerow([p.giornata, p.casa, p.trasferta])
