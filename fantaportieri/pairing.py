"""La classifica delle accoppiate.

L'idea: se possiedo i portieri di A e di B, ogni giornata schiero quello con la
partita piu' facile. Il valore della coppia a quella giornata e' quindi il
massimo fra i due, e il totale premia automaticamente le coppie COMPLEMENTARI
(quando A ha il big match, B gioca contro l'ultima in classifica).

Senza un vincolo di spesa la classifica e' inutile all'asta: le prime dieci coppie
sono tutte fatte di squadre care, il che equivale a dire "compra i portieri delle
squadre forti". I limiti per fascia rendono la domanda quella vera -- "se mi sveno
su un portiere solo, qual e' il miglior compagno?" -- senza bisogno di un listino.
"""

from itertools import combinations

from .config import FASCIA_ALTISSIMA, SQUADRE_COSTOSE
from .models import Combo, Impegno


def _valuta(
    squadre: tuple[str, ...],
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
) -> Combo | None:
    somma = 0.0
    somma_punti = 0.0
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
        # Chi schierare non cambia fra le due metriche: sia la probabilita' di
        # imbattibilita' sia i punti attesi decrescono al crescere dei gol attesi.
        somma_punti += impegni[squadra][g].punti_attesi
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
        media_punti=somma_punti / valide,
        punti_totali=somma_punti,
    )


CRITERI = {
    # "quante giornate sono coperto?"
    "copertura": lambda c: (c.copertura, c.media_clean_sheet),
    # "quanto vale in media la partita che gioco?"
    "media": lambda c: (c.media_clean_sheet, c.copertura),
    # "quanto mi serve DAVVERO il secondo portiere?" -> premia la complementarita'
    "guadagno": lambda c: (c.guadagno, c.media_clean_sheet),
    # "quanti punti mi fa in stagione?" -> col regolamento classico
    "punti": lambda c: (c.punti_totali, c.copertura),
}


def _ammessa(gruppo: tuple[str, ...], max_altissima: int | None, max_costosi: int | None) -> bool:
    """Il gruppo sta dentro il budget, espresso come numero di portieri cari."""
    if max_altissima is not None:
        if sum(s in FASCIA_ALTISSIMA for s in gruppo) > max_altissima:
            return False
    if max_costosi is not None:
        if sum(s in SQUADRE_COSTOSE for s in gruppo) > max_costosi:
            return False
    return True


def classifica(
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
    dimensione: int = 2,
    max_altissima: int | None = None,
    max_costosi: int | None = None,
    ordina: str = "copertura",
) -> list[Combo]:
    """Tutte le combinazioni di `dimensione` squadre ammesse dal budget, dalla migliore.

    `max_altissima` e `max_costosi` sono tetti sul NUMERO di portieri cari nel gruppo;
    `None` significa nessun limite. Il secondo conta entrambe le fasce, quindi
    max_altissima=1 con max_costosi=1 vuol dire "un solo portiere caro in tutto".
    """
    if ordina not in CRITERI:
        raise ValueError(f"ordina='{ordina}' sconosciuto: usa {sorted(CRITERI)}")

    squadre = sorted(impegni)
    risultati = [
        combo
        for gruppo in combinations(squadre, dimensione)
        if _ammessa(gruppo, max_altissima, max_costosi)
        and (combo := _valuta(gruppo, impegni, giornate, soglia)) is not None
    ]
    risultati.sort(key=CRITERI[ordina], reverse=True)
    return risultati
