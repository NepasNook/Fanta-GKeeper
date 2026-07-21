"""Lettura e scrittura dei CSV normalizzati.

Questi due file sono il contratto fra lo scraping e il motore di calcolo:
lo scraper li produce, tutto il resto legge solo questi. Si possono anche
compilare a mano se un sito e' ostico.

data/storico.csv     stagione,squadra,partite,gol_fatti,gol_subiti
data/calendario.csv  giornata,casa,trasferta
"""

import csv
from pathlib import Path

from .config import normalizza_squadra
from .models import Partita, StatStagione

COLONNE_STORICO = ["stagione", "squadra", "partite", "gol_fatti", "gol_subiti"]
COLONNE_CALENDARIO = ["giornata", "casa", "trasferta"]


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
