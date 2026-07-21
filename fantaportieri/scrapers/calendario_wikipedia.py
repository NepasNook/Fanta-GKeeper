"""Calendario di Serie A dal wikitext di it.wikipedia.

Perche' Wikipedia: legaseriea.it e' un'app Next.js che carica il calendario via
Server Action (niente dati nell'HTML), diretta.it incorpora solo le prime 12
giornate e il resto viaggia su un feed Flashscore firmato e non documentato.
Wikipedia invece pubblica tutte e 38 le giornate in wikitext, che e' testo
stabile e servito da un'API pubblica.

La struttura da cui estraiamo:

    | bgcolor=#d3d3d3 |'''1a giornata'''
    | bgcolor="#e0f0ff" | 23 ago. || Atalanta-Sassuolo|| 20:45
    | rowspan="3" bgcolor=#f0ffff |22 ago. || Genoa-Napoli|| 20:45
    |                              Inter-Monza|| 18:30

La squadra di casa e' sempre la prima. Il calendario dal 2021 e' ASIMMETRICO
(il ritorno non e' l'immagine speculare dell'andata), quindi leggiamo davvero
tutte le 38 giornate invece di specchiare le prime 19.
"""

import re
import urllib.parse
from collections import Counter

from ..config import normalizza_squadra
from ..models import Partita
from .rete import scarica_json

API = "https://it.wikipedia.org/w/api.php?action=parse&page={pagina}&prop=wikitext&format=json&formatversion=2"

RE_GIORNATA = re.compile(r"'''\s*(\d{1,2})\s*[ªa°]\s*giornata\s*'''", re.IGNORECASE)

# Una partita: preceduta da '|', due nomi separati da '-', seguita da '||'.
# Volutamente niente \s nelle classi: un nome squadra non attraversa mai una riga.
_NOME = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’. ]{2,24}?"
RE_PARTITA = re.compile(rf"\|[ \t]*({_NOME})[ \t]*-[ \t]*({_NOME})[ \t]*\|\|")

# Inizio di una sezione di livello 2 (== Titolo ==), non di livello 3/4.
RE_SEZIONE_L2 = re.compile(r"\n==(?!=)")


class ErroreCalendario(Exception):
    pass


def _sezione_calendario(wikitext: str) -> str:
    inizio = wikitext.find("Girone di andata")
    if inizio < 0:
        raise ErroreCalendario(
            "Nessuna sezione 'Girone di andata' nella pagina: forse il calendario "
            "non e' ancora stato pubblicato, o la pagina e' stata ristrutturata."
        )
    resto = RE_SEZIONE_L2.search(wikitext, inizio)
    return wikitext[inizio : resto.start() if resto else len(wikitext)]


def _estrai(sezione: str) -> list[Partita]:
    marcatori = list(RE_GIORNATA.finditer(sezione))
    if not marcatori:
        raise ErroreCalendario("Nessun marcatore \"'''Nª giornata'''\" trovato.")

    partite: list[Partita] = []
    for i, marcatore in enumerate(marcatori):
        giornata = int(marcatore.group(1))
        fine = marcatori[i + 1].start() if i + 1 < len(marcatori) else len(sezione)
        blocco = sezione[marcatore.end() : fine]
        for casa, trasferta in RE_PARTITA.findall(blocco):
            partite.append(
                Partita(
                    giornata=giornata,
                    casa=normalizza_squadra(casa.strip()),
                    trasferta=normalizza_squadra(trasferta.strip()),
                )
            )
    return partite


def valida(partite: list[Partita]) -> list[str]:
    """Controlli di sanita'. Restituisce la lista dei problemi (vuota = tutto ok).

    Un calendario di Serie A ha una forma rigidissima: se una di queste
    condizioni salta, il parsing ha sbagliato e i risultati sarebbero silenziosamente
    falsi. Meglio accorgersene qui.
    """
    problemi: list[str] = []

    giornate = Counter(p.giornata for p in partite)
    squadre = {p.casa for p in partite} | {p.trasferta for p in partite}

    if len(partite) != 380:
        problemi.append(f"partite totali = {len(partite)}, attese 380")
    if len(squadre) != 20:
        problemi.append(f"squadre = {len(squadre)}, attese 20: {sorted(squadre)}")
    if sorted(giornate) != list(range(1, 39)):
        problemi.append(f"giornate presenti = {sorted(giornate)}, attese 1..38")

    for giornata, quante in sorted(giornate.items()):
        if quante != 10:
            problemi.append(f"giornata {giornata}: {quante} partite invece di 10")

    in_casa = Counter(p.casa for p in partite)
    in_trasferta = Counter(p.trasferta for p in partite)
    for squadra in sorted(squadre):
        if in_casa[squadra] != 19 or in_trasferta[squadra] != 19:
            problemi.append(
                f"{squadra}: {in_casa[squadra]} in casa / {in_trasferta[squadra]} "
                f"in trasferta (attese 19 e 19)"
            )

    # Ogni squadra gioca una sola volta per giornata.
    for giornata in sorted(giornate):
        del_turno = [p for p in partite if p.giornata == giornata]
        coinvolte = [p.casa for p in del_turno] + [p.trasferta for p in del_turno]
        doppie = [s for s, n in Counter(coinvolte).items() if n > 1]
        if doppie:
            problemi.append(f"giornata {giornata}: {doppie} giocano piu' di una volta")

    return problemi


def scarica_calendario(stagione: str) -> tuple[list[Partita], list[str]]:
    """Calendario della stagione (es. '2026-27') e lista di eventuali problemi."""
    anno = int(stagione.split("-")[0])
    pagina = f"Serie A {anno}-{anno + 1}"
    dati = scarica_json(API.format(pagina=urllib.parse.quote(pagina)))

    if "error" in dati:
        raise ErroreCalendario(f"Wikipedia: {dati['error'].get('info', dati['error'])}")

    wikitext = dati["parse"]["wikitext"]
    partite = _estrai(_sezione_calendario(wikitext))
    return partite, valida(partite)
