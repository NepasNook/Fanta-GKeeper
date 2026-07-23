"""La classifica delle accoppiate.

L'idea: se possiedo i portieri di A e di B, ogni giornata schiero quello con la
partita piu' facile. Il valore della coppia a quella giornata e' quindi il
massimo fra i due, e il totale premia automaticamente le coppie COMPLEMENTARI
(quando A ha il big match, B gioca contro l'ultima in classifica).

Senza un vincolo di spesa la classifica e' inutile all'asta: le prime dieci coppie
sono tutte fatte di squadre care, il che equivale a dire "compra i portieri delle
squadre forti". Il tetto di budget rende la domanda quella vera -- "con i crediti
che ho, qual e' la coppia migliore?".

Non sa niente di ruoli: lavora su `Impegno.probabilita`, che per un portiere e' la
probabilita' di non prendere gol e per un attaccante quella che la sua squadra segni.
Le due pagine usano quindi questo stesso file, e non una copia a testa.
"""

from itertools import combinations

from .config import PREZZO_SCONOSCIUTO
from .models import Combo, Impegno


def prezzo_gruppo(gruppo: tuple[str, ...], prezzi: dict[str, float]) -> float:
    """Costo del gruppo in quota di budget: la somma dei prezzi dei suoi giocatori."""
    return sum(prezzi.get(s, PREZZO_SCONOSCIUTO) for s in gruppo)


def _valuta(
    squadre: tuple[str, ...],
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
    prezzi: dict[str, float],
) -> Combo | None:
    somma = 0.0
    somma_punti = 0.0
    somma_punti_tutti = 0.0
    facili = 0
    scelte: dict[int, str] = {}
    pari: dict[int, tuple[str, ...]] = {}
    valide = 0
    # Somma di ogni squadra da sola, per misurare quanto serve davvero alternare.
    somme_singole: dict[str, float] = dict.fromkeys(squadre, 0.0)

    for g in giornate:
        candidati = [(impegni[s][g].probabilita, s) for s in squadre if g in impegni.get(s, {})]
        if not candidati:
            continue
        for prob, squadra in candidati:
            somme_singole[squadra] += prob
        # Somma su TUTTO il gruppo: per gli attaccanti scendono in campo tutti,
        # quindi il totale conta quanto il migliore.
        somma_punti_tutti += sum(impegni[s][g].punti_attesi for s in squadre if g in impegni.get(s, {}))
        # `key` sulla sola probabilita': senza, a parita' esatta il confronto fra
        # tuple scivolerebbe sul nome e vincerebbe l'ULTIMO in ordine alfabetico,
        # mentre il JS della pagina confronta solo `pcs` e tiene il PRIMO. Un pari
        # merito vero e' improbabile fra due float, ma se capita i due lati devono
        # rispondere lo stesso, non plausibilmente.
        migliore, squadra = max(candidati, key=lambda c: c[0])
        a_pari = tuple(s for prob, s in candidati if prob == migliore)
        if len(a_pari) > 1:
            pari[g] = a_pari
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
        media_probabilita=media,
        copertura=facili / valide,
        giornate_facili=facili,
        giornate_totali=valide,
        scelte=scelte,
        pari=pari,
        guadagno=media - media_singolo,
        miglior_singolo=miglior_singolo,
        media_miglior_singolo=media_singolo,
        media_punti=somma_punti / valide,
        punti_totali=somma_punti,
        punti_tutti=somma_punti_tutti,
        prezzo=prezzo_gruppo(squadre, prezzi),
    )


CRITERI = {
    # "quante giornate sono coperto?"
    "copertura": lambda c: (c.copertura, c.media_probabilita),
    # "quanto vale in media la partita che gioco?"
    "media": lambda c: (c.media_probabilita, c.copertura),
    # "quanto mi serve DAVVERO il secondo?" -> premia la complementarita'
    "guadagno": lambda c: (c.guadagno, c.media_probabilita),
    # "quanti punti mi fa in stagione?" -> schierando ogni volta il migliore
    "punti": lambda c: (c.punti_totali, c.copertura),
    # "quanti punti fanno TUTTI insieme?" -> per gli attaccanti, che giocano tutti
    "totale": lambda c: (c.punti_tutti, c.copertura),
    # "quanto rendono i crediti che ci spendo?"
    # Il rapporto usa la probabilita', non i punti: `punti_totali` esclude il voto
    # base, quindi per i portieri e' negativo e il suo zero e' arbitrario. Dividere
    # un numero negativo per il prezzo premia i piu' cari, cioe' l'opposto. La
    # probabilita' invece uno zero vero ce l'ha, e il rapporto significa qualcosa.
    "efficienza": lambda c: (c.media_probabilita / c.prezzo if c.prezzo else 0.0, c.copertura),
}


def classifica(
    impegni: dict[str, dict[int, Impegno]],
    giornate: list[int],
    soglia: float,
    prezzi: dict[str, float],
    dimensione: int = 2,
    budget: float | None = None,
    ordina: str = "copertura",
    obbligatoria: str | None = None,
) -> list[Combo]:
    """Tutte le combinazioni di `dimensione` squadre entro il budget, dalla migliore.

    `budget` e' il tetto sulla SOMMA dei prezzi del gruppo, in quota del monte crediti
    (0.15 = 15%). `None` significa nessun limite, e serve solo a mostrare quanto la
    classifica senza vincoli sia inservibile: vincono sempre e solo i piu' cari.

    `obbligatoria` tiene solo i gruppi che contengono quella squadra. E' la domanda
    dell'asta a mercato gia' iniziato: "ho preso il portiere del Bologna, adesso chi
    ci abbino?" -- senza, la classifica risponde a una domanda che non ti puoi piu' porre.
    """
    if ordina not in CRITERI:
        raise ValueError(f"ordina='{ordina}' sconosciuto: usa {sorted(CRITERI)}")

    squadre = sorted(impegni)
    if obbligatoria is not None and obbligatoria not in squadre:
        raise ValueError(f"obbligatoria='{obbligatoria}' non e' fra le squadre: {squadre}")

    # Il confronto sui float ha una tolleranza: 0.10 + 0.05 in binario fa
    # 0.15000000000000002, e senza epsilon la coppia da 15% sparirebbe da un
    # budget del 15%.
    tetto = None if budget is None else budget + 1e-9

    risultati = [
        combo
        for gruppo in combinations(squadre, dimensione)
        if (obbligatoria is None or obbligatoria in gruppo)
        and (tetto is None or prezzo_gruppo(gruppo, prezzi) <= tetto)
        and (combo := _valuta(gruppo, impegni, giornate, soglia, prezzi)) is not None
    ]
    risultati.sort(key=CRITERI[ordina], reverse=True)
    return risultati
