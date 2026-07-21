"""Dallo storico gol alla forza delle squadre.

Ogni squadra ottiene due numeri relativi alla media del campionato:
  attacco = quanto segna rispetto alla media
  difesa  = quanto subisce rispetto alla media (piu' basso = piu' solido)

Le stagioni recenti pesano molto di piu' (decadimento esponenziale), e chi ha
poche stagioni viene tirato verso un bersaglio: la media del campionato per chi
la Serie A la sta gia' giocando, il prior della neopromossa per chi arriva dalla B.
E' cosi' che il modello capisce che il Como di oggi non e' il Como del 2021.

I parametri sono argomenti con default da `config.py`: servono per la grid search
di `calibra.py`, che deve poter valutare combinazioni diverse senza toccare i moduli.
"""

from collections import defaultdict

from .config import (
    DECADIMENTO_STAGIONI,
    PESO_REGRESSIONE_MEDIA,
    PRIOR_NEOPROMOSSA_ATTACCO,
    PRIOR_NEOPROMOSSA_DIFESA,
)
from .models import Forza, StatStagione


def _mu_per_stagione(storico: list[StatStagione]) -> dict[str, float]:
    """Gol medi segnati da una squadra in una partita, stagione per stagione (~1.35)."""
    totali: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in storico:
        totali[r.stagione][0] += r.gol_fatti
        totali[r.stagione][1] += r.partite
    return {s: gol / partite for s, (gol, partite) in totali.items() if partite}


def _pesi_stagioni(stagioni: list[str], decadimento: float = DECADIMENTO_STAGIONI) -> dict[str, float]:
    """La stagione piu' recente pesa 1.0, ogni anno indietro moltiplica per il decadimento."""
    ordinate = sorted(stagioni)
    ultima = len(ordinate) - 1
    return {s: decadimento ** (ultima - i) for i, s in enumerate(ordinate)}


def media_gol_lega(storico: list[StatStagione], decadimento: float = DECADIMENTO_STAGIONI) -> float:
    """Media gol di riferimento per la stagione da prevedere: media pesata delle passate."""
    mu = _mu_per_stagione(storico)
    pesi = _pesi_stagioni(list(mu), decadimento)
    numeratore = sum(mu[s] * pesi[s] for s in mu)
    return numeratore / sum(pesi.values())


def calcola_forze(
    storico: list[StatStagione],
    squadre_correnti: set[str],
    decadimento: float = DECADIMENTO_STAGIONI,
    peso_regressione: float = PESO_REGRESSIONE_MEDIA,
    prior_attacco: float = PRIOR_NEOPROMOSSA_ATTACCO,
    prior_difesa: float = PRIOR_NEOPROMOSSA_DIFESA,
) -> dict[str, Forza]:
    """Forza di ogni squadra iscritta al campionato corrente.

    Chi non compare nell'ultima stagione dello storico sta salendo dalla B, e la
    sua regressione punta al prior neopromossa invece che alla media della Serie A.
    Senza questa distinzione una squadra retrocessa anni fa risulterebbe FORTE
    proprio perche' ha pochi dati: tirandola verso 1.00 la si dichiara "nella media
    della A", che e' l'opposto di cio' che dice il fatto di essere in B. Con questa
    regola una debuttante assoluta e' semplicemente il caso limite (zero dati, forza
    esattamente uguale al prior), e non serve piu' un ramo a parte.
    """
    mu = _mu_per_stagione(storico)
    pesi = _pesi_stagioni(list(mu), decadimento)
    ultima_stagione = max(mu) if mu else ""

    per_squadra: dict[str, list[StatStagione]] = defaultdict(list)
    for r in storico:
        if r.squadra in squadre_correnti:
            per_squadra[r.squadra].append(r)

    forze: dict[str, Forza] = {}
    for squadra in sorted(squadre_correnti):
        righe = per_squadra.get(squadra, [])
        promossa = not any(r.stagione == ultima_stagione for r in righe)

        bersaglio_attacco = prior_attacco if promossa else 1.0
        bersaglio_difesa = prior_difesa if promossa else 1.0

        peso_totale = 0.0
        somma_attacco = 0.0
        somma_difesa = 0.0
        for r in righe:
            peso = pesi[r.stagione]
            somma_attacco += peso * (r.gol_fatti / r.partite) / mu[r.stagione]
            somma_difesa += peso * (r.gol_subiti / r.partite) / mu[r.stagione]
            peso_totale += peso

        # Regressione verso il bersaglio, tanto piu' forte quanti meno dati ci sono.
        denominatore = peso_totale + peso_regressione
        forze[squadra] = Forza(
            squadra=squadra,
            attacco=(somma_attacco + peso_regressione * bersaglio_attacco) / denominatore,
            difesa=(somma_difesa + peso_regressione * bersaglio_difesa) / denominatore,
            stagioni_usate=len(righe),
            neopromossa=promossa,
        )

    return forze
