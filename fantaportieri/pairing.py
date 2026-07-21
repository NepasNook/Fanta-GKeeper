"""La classifica delle accoppiate.

L'idea: se possiedo i portieri di A e di B, ogni giornata schiero quello con la
partita piu' facile. Il valore della coppia a quella giornata e' quindi il
massimo fra i due, e il totale premia automaticamente le coppie COMPLEMENTARI
(quando A ha il big match, B gioca contro l'ultima in classifica).
"""

from itertools import combinations

from .config import SQUADRE_COSTOSE
from .models import Combo, Impegno


def _valuta(
    squadre: tuple[str, ...],
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
) -> Combo | None:
    somma = 0.0
    facili = 0
    scelte: dict[int, str] = {}
    valide = 0
    # Somma di ogni squadra da sola, per misurare quanto serve davvero alternare.
    somme_singole: dict[str, float] = dict.fromkeys(squadre, 0.0)

    for g in giornate:
        candidati = [(impegni[s][g].prob_clean_sheet, s) for s in squadre if g in impegni.get(s, {})]
        if not candidati:
            continue
        for prob, squadra in candidati:
            somme_singole[squadra] += prob
        migliore, squadra = max(candidati)
        somma += migliore
        scelte[g] = squadra
        if migliore >= soglia:
            facili += 1
        valide += 1

    if not valide:
        return None

    media = somma / valide
    miglior_singolo = max(somme_singole, key=lambda s: somme_singole[s])
    media_singolo = somme_singole[miglior_singolo] / valide

    return Combo(
        squadre=squadre,
        media_clean_sheet=media,
        copertura=facili / valide,
        giornate_facili=facili,
        giornate_totali=valide,
        scelte=scelte,
        guadagno=media - media_singolo,
        miglior_singolo=miglior_singolo,
        media_miglior_singolo=media_singolo,
    )


CRITERI = {
    # "quante giornate sono coperto?"
    "copertura": lambda c: (c.copertura, c.media_clean_sheet),
    # "quanto vale in media la partita che gioco?"
    "media": lambda c: (c.media_clean_sheet, c.copertura),
    # "quanto mi serve DAVVERO il secondo portiere?" -> premia la complementarita'
    "guadagno": lambda c: (c.guadagno, c.media_clean_sheet),
}


def classifica(
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
    dimensione: int = 2,
    escludi_costose: bool = False,
    ordina: str = "copertura",
) -> list[Combo]:
    """Tutte le combinazioni di `dimensione` squadre, ordinate dalla migliore.

    `escludi_costose` serve alle triple: hanno senso solo se rinunci al portiere
    titolare di una big, altrimenti tanto vale spendere e giocare di coppia.
    """
    if ordina not in CRITERI:
        raise ValueError(f"ordina='{ordina}' sconosciuto: usa {sorted(CRITERI)}")

    squadre = sorted(impegni)
    if escludi_costose:
        squadre = [s for s in squadre if s not in SQUADRE_COSTOSE]

    risultati = [
        combo
        for gruppo in combinations(squadre, dimensione)
        if (combo := _valuta(gruppo, impegni, giornate, soglia)) is not None
    ]
    risultati.sort(key=CRITERI[ordina], reverse=True)
    return risultati
