"""Il modello ci prende davvero? Validazione walk-forward, alla cieca.

Il punto: tutti i parametri (decadimento, esponenti, fattore campo) li ho scelti
a ragionare, non misurando. Qui si misura. Per ogni stagione di prova si allena
il modello SOLO sulle stagioni precedenti, poi gli si fanno prevedere le partite
che non ha mai visto e si confronta con com'e' andata davvero.

    python backtest.py

Non tocca il modello di produzione (quello per il 26-27 usa tutte le stagioni,
25-26 compresa): questa e' una prova a parte che nasconde una stagione per volta.

Tre domande, tre risposte:
  1. Le probabilita' sono calibrate? Quando dico "40% imbattibilita'", succede il 40%?
  2. Batto una previsione stupida (tirare sempre la media del campionato)?
  3. C'e' un errore sistematico (prevedo troppi o troppo pochi gol)?
"""

import math
from collections import defaultdict

from fantaportieri.config import (
    ESP_ATTACCO_AVVERSARIO,
    ESP_DIFESA_MIA,
    FATTORE_CASA,
    FATTORE_TRASFERTA,
    STAGIONI_STORICHE,
)
from fantaportieri.scrapers.storico_openfootball import scarica_partite, scarica_stagione
from fantaportieri.strength import calcola_forze, media_gol_lega


def _lambda(mia, avversario, in_casa, forze, mu):
    attacco = forze[avversario].attacco ** ESP_ATTACCO_AVVERSARIO
    difesa = forze[mia].difesa ** ESP_DIFESA_MIA
    campo = FATTORE_TRASFERTA if in_casa else FATTORE_CASA
    return mu * attacco * difesa * campo


def _prepara(stagioni):
    """Scarica una volta sola: statistiche aggregate (per allenare) e partite (per testare)."""
    storico, partite = {}, {}
    for s in stagioni:
        righe, _ = scarica_stagione(s)
        storico[s] = righe
        partite[s] = scarica_partite(s)
    return storico, partite


def backtest_stagione(test, storico, partite):
    """Allena su tutto cio' che precede `test`, predice `test`. Ritorna le coppie
    (prob. imbattibilita' prevista, imbattibilita' reale 0/1, gol previsti, gol reali)."""
    train = [s for s in STAGIONI_STORICHE if s < test]
    if not train:
        return None, train

    storico_train = [r for s in train for r in storico[s]]
    squadre_test = {c for c, _, _, _ in partite[test]} | {t for _, t, _, _ in partite[test]}
    mu = media_gol_lega(storico_train)
    forze = calcola_forze(storico_train, squadre_test)

    campioni = []
    for casa, trasferta, gc, gt in partite[test]:
        # Due portieri per partita: quello di casa (subisce gt) e quello in trasferta (subisce gc).
        for mia, avv, in_casa, subiti in ((casa, trasferta, True, gt), (trasferta, casa, False, gc)):
            lam = _lambda(mia, avv, in_casa, forze, mu)
            campioni.append((math.exp(-lam), 1 if subiti == 0 else 0, lam, subiti))
    return campioni, train


def _brier(campioni):
    return sum((p - reale) ** 2 for p, reale, _, _ in campioni) / len(campioni)


def _calibrazione(campioni):
    fasce = [(0.0, 0.25), (0.25, 0.33), (0.33, 0.40), (0.40, 0.50), (0.50, 1.0)]
    righe = []
    for lo, hi in fasce:
        sotto = [c for c in campioni if lo <= c[0] < hi]
        if not sotto:
            continue
        previsto = sum(c[0] for c in sotto) / len(sotto)
        reale = sum(c[1] for c in sotto) / len(sotto)
        righe.append((f"{lo:.0%}-{hi:.0%}", len(sotto), previsto, reale))
    return righe


def report(test, campioni):
    n = len(campioni)
    base = sum(c[1] for c in campioni) / n  # tasso reale di imbattibilita'

    brier_modello = _brier(campioni)
    # Baseline: prevedere per tutti lo stesso tasso medio. Se non lo batto, il modello e' inutile.
    brier_base = sum((base - reale) ** 2 for _, reale, _, _ in campioni) / n
    skill = 1 - brier_modello / brier_base

    gol_previsti = sum(c[2] for c in campioni) / n
    gol_reali = sum(c[3] for c in campioni) / n

    print(f"===== stagione di prova {test}  ({n} partite-portiere) =====")
    print(f"  Imbattibilita' reale nella stagione: {base:.1%}")
    print(f"  Skill vs previsione banale: {skill:+.1%}   ", end="")
    print("(>0 = il modello aggiunge valore)" if skill > 0 else "(<=0 = NON batte la media!)")
    print(f"  Gol subiti: previsti {gol_previsti:.2f}/partita, reali {gol_reali:.2f}  "
          f"(scarto {gol_previsti - gol_reali:+.2f})")
    print("  Calibrazione (quando prevedo X%, succede davvero?):")
    print(f"     {'fascia':<10}{'partite':>8}{'previsto':>10}{'reale':>8}")
    for etichetta, quante, previsto, reale in _calibrazione(campioni):
        segnale = "  ok" if abs(previsto - reale) < 0.05 else "  <-- scarto"
        print(f"     {etichetta:<10}{quante:>8}{previsto:>9.1%}{reale:>8.1%}{segnale}")
    print()


if __name__ == "__main__":
    print("Scarico i dati storici (una volta)...\n")
    storico, partite = _prepara(STAGIONI_STORICHE)

    tutti = []
    for test in STAGIONI_STORICHE:
        campioni, train = backtest_stagione(test, storico, partite)
        if campioni is None:
            continue
        print(f"[allenato su {', '.join(train)}]")
        report(test, campioni)
        tutti.extend(campioni)

    if tutti:
        base = sum(c[1] for c in tutti) / len(tutti)
        brier = _brier(tutti)
        brier_base = sum((base - r) ** 2 for _, r, _, _ in tutti) / len(tutti)
        print("===== complessivo =====")
        print(f"  {len(tutti)} previsioni, skill vs banale: {1 - brier / brier_base:+.1%}")
