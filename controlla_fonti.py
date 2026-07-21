"""Verifica che le fonti esterne rispondano ancora e nel formato atteso.

Le fonti cambiano senza preavviso. Questo script le interroga e controlla la
forma dei dati, cosi' un problema si vede subito invece di diventare una
classifica sbagliata ma dall'aria plausibile.

    python controlla_fonti.py
"""

import sys

from fantaportieri.config import STAGIONE_CORRENTE, STAGIONI_STORICHE
from fantaportieri.scrapers.calendario_wikipedia import ErroreCalendario, scarica_calendario
from fantaportieri.scrapers.rete import ErroreRete
from fantaportieri.scrapers.storico_openfootball import scarica_storico


def controlla_calendario() -> bool:
    print(f"== Calendario {STAGIONE_CORRENTE} (it.wikipedia.org) ==")
    try:
        partite, problemi = scarica_calendario(STAGIONE_CORRENTE)
    except (ErroreRete, ErroreCalendario, KeyError) as e:
        print(f"   FALLITO: {e}\n")
        return False

    squadre = sorted({p.casa for p in partite} | {p.trasferta for p in partite})
    print(f"   partite: {len(partite)}   giornate: {len({p.giornata for p in partite})}")
    print(f"   squadre ({len(squadre)}): {', '.join(squadre)}")

    if problemi:
        print("   PROBLEMI:")
        for p in problemi[:12]:
            print(f"      - {p}")
        print()
        return False

    print("   validazione: ok")
    prima = sorted((p for p in partite if p.giornata == 1), key=lambda p: p.casa)
    print(f"   giornata 1: {', '.join(f'{p.casa}-{p.trasferta}' for p in prima)}")
    print()
    return True


def controlla_storico() -> bool:
    print("== Storico (openfootball/football.json) ==")
    try:
        righe, rapporti = scarica_storico(STAGIONI_STORICHE)
    except (ErroreRete, KeyError) as e:
        print(f"   FALLITO: {e}\n")
        return False

    ok = True
    for r in rapporti:
        stato = "ok" if r["copertura"] > 0.98 else "PARZIALE"
        if r["copertura"] <= 0.98:
            ok = False
        print(
            f"   {r['stagione']}  {r['partite_con_risultato']:3d}/{r['partite_in_calendario']:3d} "
            f"partite ({r['copertura']:.0%})  squadre={r['squadre']:2d}  [{stato}]"
        )

    print(f"   righe squadra-stagione totali: {len(righe)}")
    print()
    if not ok:
        print("   Nota: le stagioni parziali restano usabili perche' il modello lavora")
        print("   sulle medie per partita, non sui totali. Ma se manca troppo, il dato")
        print("   di quella stagione e' piu' rumoroso.\n")
    return True


if __name__ == "__main__":
    esiti = [controlla_calendario(), controlla_storico()]
    if all(esiti):
        print("Tutte le fonti rispondono correttamente.")
        sys.exit(0)
    print("Almeno una fonte ha problemi (vedi sopra).")
    sys.exit(1)
