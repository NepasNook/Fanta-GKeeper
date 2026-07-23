"""Classifica marcatori dal wikitext di it.wikipedia.

Serve a una domanda sola, ma decisiva per la pagina attaccanti: **quanta parte dei
gol di una squadra finisce al suo miglior attaccante?** Il modello stima i gol della
SQUADRA, ma all'asta tu compri un GIOCATORE, e una squadra di attaccanti ne ha tre o
quattro (gli esterni compresi). Se la quota del bomber fosse stabile, il segnale di
squadra si tradurrebbe in modo prevedibile sul giocatore; se ballasse, no.

Copertura parziale e va detto: la voce elenca solo chi ha segnato almeno una decina
di gol, cioe' 18-19 giocatori a stagione su 12-13 squadre delle 20. Basta per misurare
la quota dei bomber veri, non per dire niente sull'attaccante da pochi crediti.

Struttura da cui si estrae:

    {{Classifica marcatori|reti=25|rigori=4|nazione=ITA|nome=[[Mateo Retegui]]|squadra=Atalanta|testa=on}}
"""

import re
import urllib.parse

from ..config import normalizza_squadra
from .rete import scarica_json

API = "https://it.wikipedia.org/w/api.php?action=parse&page={pagina}&prop=wikitext&format=json&formatversion=2"

# Una riga della classifica: si cattura il corpo del template e poi si leggono le
# coppie chiave=valore, invece di fissarne l'ordine. Wikipedia lo cambia.
RE_RIGA = re.compile(r"\{\{\s*Classifica marcatori\s*\|([^}]*)\}\}")
# "[[Mateo Retegui]]" oppure "[[Nikola Krstovic|Krstovic]]": si tiene la prima parte.
RE_LINK = re.compile(r"\[\[([^\]|]+)")

_CACHE: dict[str, list] = {}


def _campi(corpo: str) -> dict[str, str]:
    campi = {}
    for pezzo in corpo.split("|"):
        if "=" in pezzo:
            chiave, _, valore = pezzo.partition("=")
            campi[chiave.strip().casefold()] = valore.strip()
    return campi


def scarica_marcatori(stagione: str) -> list[tuple[int, str, str]]:
    """(reti, giocatore, squadra) per la stagione, dal piu' prolifico.

    `stagione` nella forma "2024-25". Lista vuota se la voce non ha la sezione,
    che e' il caso normale di una stagione non ancora giocata.
    """
    if stagione in _CACHE:
        return _CACHE[stagione]

    anno = int(stagione.split("-")[0])
    pagina = f"Serie A {anno}-{anno + 1}"
    dati = scarica_json(API.format(pagina=urllib.parse.quote(pagina)))
    if "error" in dati:
        _CACHE[stagione] = []
        return []

    wikitext = dati["parse"]["wikitext"]
    marcatori: list[tuple[int, str, str]] = []
    for trovato in RE_RIGA.finditer(wikitext):
        campi = _campi(trovato.group(1))
        reti, nome, squadra = campi.get("reti"), campi.get("nome"), campi.get("squadra")
        if not (reti and nome and squadra):
            continue
        link = RE_LINK.search(nome)
        try:
            marcatori.append(
                (int(reti), (link.group(1) if link else nome).strip(), normalizza_squadra(squadra))
            )
        except ValueError:
            continue

    marcatori.sort(reverse=True)
    _CACHE[stagione] = marcatori
    return marcatori


def miglior_marcatore(stagione: str) -> dict[str, tuple[str, int]]:
    """Per ogni squadra presente in classifica: (giocatore, reti) del suo migliore."""
    migliori: dict[str, tuple[str, int]] = {}
    for reti, nome, squadra in scarica_marcatori(stagione):
        if squadra not in migliori or reti > migliori[squadra][1]:
            migliori[squadra] = (nome, reti)
    return migliori
