"""Storico gol da openfootball/football.json.

Perche' non legaseriea.it: il sito ufficiale e' un'app Next.js che carica la
classifica via Server Action lato client. Niente dati nell'HTML, niente API
pubblica raggiungibile: servirebbe un browser headless, fragile a ogni restyle.
openfootball invece pubblica su GitHub i risultati partita per partita in JSON,
senza chiave e senza limiti.

Attenzione: il dataset e' mantenuto dalla comunita' e le ultime stagioni possono
essere incomplete. Per questo il modello usa le MEDIE per partita e non i totali
di stagione: una stagione al 90% resta utilizzabile. `copertura()` dice quanto
manca, cosi' la decisione e' informata invece che nascosta.
"""

import re
from collections import defaultdict

from ..config import normalizza_squadra
from ..models import StatStagione
from .rete import scarica_json

URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{stagione}/it.1.json"

# Una stagione viene scaricata una volta sola per processo: `backtest.py` chiede sia
# gli aggregati sia le singole partite, e senza cache sarebbero due GET dello stesso file.
_CACHE: dict[str, list] = {}


def _partite_grezze(stagione: str) -> list:
    """Le partite della stagione come stanno nel JSON, memorizzate dopo il primo scarico."""
    if stagione not in _CACHE:
        dati = scarica_json(URL.format(stagione=stagione))
        _CACHE[stagione] = dati.get("matches", []) if isinstance(dati, dict) else []
    return _CACHE[stagione]


def _risultato(partita: dict) -> tuple[int, int] | None:
    """(gol casa, gol trasferta) se la partita e' stata giocata, altrimenti None.

    Il dataset usa DUE serializzazioni per `score`, ed entrambe sono valide:
        {"ht": [1,0], "ft": [2,1]}   forma normale
        [0, 0]                       forma degenere, usata solo per gli 0-0

    La forma a lista sembra un segnaposto, e scartarla e' l'errore facile. Non lo
    e': nel 2025-26 compare 36 volte, sempre 0-0, ma su 24 giornate diverse fra la
    1 e la 36 -- se fossero partite non giocate si ammasserebbero in fondo. La
    prova definitiva e' che le 344 partite in forma normale contengono 0-0 nello
    0.0% dei casi, impossibile in un campionato vero: gli 0-0 sono tutti e soli
    quelli in forma a lista. Tenendo entrambe le forme la stagione torna
    verosimile (2.43 gol/partita, 0-0 al 9.5%).

    Scartarli cancellerebbe proprio le partite piu' preziose per un portiere.
    Vedi `diagnosi_storico.py` per rieseguire il controllo.
    """
    punteggio = partita.get("score")
    if isinstance(punteggio, dict):
        finale = punteggio.get("ft")
    elif isinstance(punteggio, list):
        finale = punteggio
    else:
        return None

    if isinstance(finale, list) and len(finale) == 2:
        try:
            return int(finale[0]), int(finale[1])
        except (TypeError, ValueError):
            return None
    return None


def scarica_partite(stagione: str) -> list[tuple[str, str, int, int]]:
    """Le singole partite giocate: (casa, trasferta, gol_casa, gol_trasferta).

    Serve al backtest, che ragiona partita per partita e non sui totali di stagione.
    """
    partite: list[tuple[str, str, int, int]] = []
    for p in _partite_grezze(stagione):
        risultato = _risultato(p)
        if risultato is None:
            continue
        gc, gt = risultato
        partite.append((normalizza_squadra(p["team1"]), normalizza_squadra(p["team2"]), gc, gt))
    return partite


def _giornata(partita: dict) -> int | None:
    """Il numero di giornata da `round` ("Matchday 12"), se c'e'."""
    trovato = re.search(r"(\d{1,2})", str(partita.get("round", "")))
    return int(trovato.group(1)) if trovato else None


def scarica_giornate(stagione: str) -> list[tuple[int, str, str, int, int]]:
    """Le partite giocate con la giornata: (giornata, casa, trasferta, gol_casa, gol_trasferta).

    Serve a `backtest_scelta.py`, che deve sapere quali partite cadono nello stesso
    turno: senza la giornata non si puo' dire quale dei due portieri avresti schierato.
    Le partite senza `round` leggibile vengono scartate, non indovinate.
    """
    partite: list[tuple[int, str, str, int, int]] = []
    for p in _partite_grezze(stagione):
        risultato = _risultato(p)
        giornata = _giornata(p)
        if risultato is None or giornata is None:
            continue
        gc, gt = risultato
        partite.append(
            (giornata, normalizza_squadra(p["team1"]), normalizza_squadra(p["team2"]), gc, gt)
        )
    return partite


def scarica_stagione(stagione: str) -> tuple[list[StatStagione], dict]:
    """Restituisce le statistiche della stagione e un rapporto sulla copertura."""
    partite = _partite_grezze(stagione)

    # squadra -> [partite giocate, gol fatti, gol subiti]
    conto: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    giocate = 0

    for p in partite:
        risultato = _risultato(p)
        if risultato is None:
            continue
        gol_casa, gol_trasferta = risultato
        casa = normalizza_squadra(p["team1"])
        trasferta = normalizza_squadra(p["team2"])

        conto[casa][0] += 1
        conto[casa][1] += gol_casa
        conto[casa][2] += gol_trasferta

        conto[trasferta][0] += 1
        conto[trasferta][1] += gol_trasferta
        conto[trasferta][2] += gol_casa
        giocate += 1

    righe = [
        StatStagione(
            stagione=stagione,
            squadra=squadra,
            partite=valori[0],
            gol_fatti=valori[1],
            gol_subiti=valori[2],
        )
        for squadra, valori in sorted(conto.items())
        if valori[0] > 0
    ]

    rapporto = {
        "stagione": stagione,
        "partite_in_calendario": len(partite),
        "partite_con_risultato": giocate,
        "squadre": len(righe),
        "copertura": giocate / len(partite) if partite else 0.0,
    }
    return righe, rapporto


def scarica_storico(stagioni: list[str]) -> tuple[list[StatStagione], list[dict]]:
    tutte: list[StatStagione] = []
    rapporti: list[dict] = []
    for stagione in stagioni:
        righe, rapporto = scarica_stagione(stagione)
        tutte.extend(righe)
        rapporti.append(rapporto)
    return tutte, rapporti
