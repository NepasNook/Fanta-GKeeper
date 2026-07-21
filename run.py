"""Classifica delle migliori accoppiate di portieri per il fantacalcio.

    python run.py --scarica     scarica i dati e salva i CSV (da fare una volta)
    python run.py               calcola dai CSV e genera la pagina HTML
    python run.py --scarica --apri

I dati stanno in due CSV normalizzati (data/storico.csv, data/calendario.csv):
si possono correggere a mano senza toccare il codice.
"""

import argparse
import sys
import webbrowser
from pathlib import Path

from fantaportieri.config import (
    MAX_ALTISSIMA,
    MAX_COSTOSI,
    SOGLIA_FACILE,
    SQUADRE_COSTOSE,
    STAGIONE_CORRENTE,
    STAGIONI_STORICHE,
)
from fantaportieri.data_io import (
    ErroreDati,
    leggi_calendario,
    leggi_storico,
    scrivi_calendario,
    scrivi_storico,
)
from fantaportieri.pairing import classifica
from fantaportieri.report import costruisci_dati, scrivi_frammento, scrivi_html
from fantaportieri.scoring import costruisci_impegni
from fantaportieri.strength import calcola_forze, media_gol_lega

RADICE = Path(__file__).parent
CSV_STORICO = RADICE / "data" / "storico.csv"
CSV_CALENDARIO = RADICE / "data" / "calendario.csv"

# Il documento autonomo: si apre con doppio clic, contiene tutto, funziona offline.
HTML = RADICE / "classifica_portieri.html"
# La stessa pagina senza l'involucro <html>/<head>/<body>, per la pubblicazione web.
FRAMMENTO = RADICE / "build" / "artifact.html"


def scarica() -> list[dict]:
    """Scarica dalle fonti e salva i CSV. Restituisce il rapporto sullo storico."""
    from fantaportieri.scrapers.calendario_wikipedia import scarica_calendario
    from fantaportieri.scrapers.storico_openfootball import scarica_storico

    print(f"Calendario {STAGIONE_CORRENTE} da it.wikipedia.org ...")
    partite, problemi = scarica_calendario(STAGIONE_CORRENTE)
    if problemi:
        print("  ATTENZIONE, il calendario non supera la validazione:")
        for p in problemi[:10]:
            print(f"    - {p}")
        print("  I CSV non sono stati scritti. Lancia 'python controlla_fonti.py'.")
        sys.exit(1)
    scrivi_calendario(CSV_CALENDARIO, partite)
    print(f"  {len(partite)} partite -> {CSV_CALENDARIO.relative_to(RADICE)}")

    print(f"Storico {STAGIONI_STORICHE[0]}..{STAGIONI_STORICHE[-1]} da openfootball ...")
    righe, rapporti = scarica_storico(STAGIONI_STORICHE)
    for r in rapporti:
        print(
            f"  {r['stagione']}: {r['partite_con_risultato']}/{r['partite_in_calendario']} "
            f"partite ({r['copertura']:.0%})"
        )
    scrivi_storico(CSV_STORICO, righe)
    print(f"  {len(righe)} righe squadra-stagione -> {CSV_STORICO.relative_to(RADICE)}")
    return rapporti


def calcola(rapporti: list[dict]) -> None:
    storico = leggi_storico(CSV_STORICO)
    calendario = leggi_calendario(CSV_CALENDARIO)

    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}
    mu = media_gol_lega(storico)
    forze = calcola_forze(storico, squadre)
    impegni = costruisci_impegni(calendario, forze, mu)
    giornate = sorted({p.giornata for p in calendario})

    print(f"\nMedia campionato: {mu:.2f} gol per squadra a partita")

    neopromosse = [f.squadra for f in forze.values() if f.neopromossa]
    if neopromosse:
        print(f"Dalla Serie B (prior neopromossa): {', '.join(sorted(neopromosse))}")

    print("\nForza stimata (attacco / difesa, relativi alla media):")
    from fantaportieri.scoring import forza_complessiva

    for f in sorted(forze.values(), key=forza_complessiva, reverse=True):
        segna = "costoso" if f.squadra in SQUADRE_COSTOSE else ""
        print(f"  {f.squadra:<12} att {f.attacco:.2f}   dif {f.difesa:.2f}   {segna}")

    coppie = classifica(impegni, giornate, SOGLIA_FACILE, dimensione=2)
    print(f"\nMigliori 10 coppie SENZA vincolo di spesa (soglia {SOGLIA_FACILE:.0%}, giornate 1-{max(giornate)}):")
    for i, c in enumerate(coppie[:10], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} "
            f"copertura {c.copertura:.0%} ({c.giornate_facili}/{c.giornate_totali})   "
            f"media {c.media_clean_sheet:.1%}   punti {c.punti_totali:+.1f}"
        )

    entro_budget = classifica(
        impegni, giornate, SOGLIA_FACILE, dimensione=2,
        max_altissima=MAX_ALTISSIMA, max_costosi=MAX_COSTOSI,
    )
    print(
        f"\nMigliori 10 coppie ENTRO IL BUDGET "
        f"(max {MAX_ALTISSIMA} di fascia altissima, max {MAX_COSTOSI} cari in tutto):"
    )
    for i, c in enumerate(entro_budget[:10], 1):
        caro = next((s for s in c.squadre if s in SQUADRE_COSTOSE), "-")
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} "
            f"copertura {c.copertura:.0%} ({c.giornate_facili}/{c.giornate_totali})   "
            f"media {c.media_clean_sheet:.1%}   punti {c.punti_totali:+.1f}   [caro: {caro}]"
        )

    per_guadagno = classifica(impegni, giornate, SOGLIA_FACILE, dimensione=2, ordina="guadagno")
    print("\nCoppie piu' COMPLEMENTARI (guadagno dell'alternanza, non valore assoluto):")
    for i, c in enumerate(per_guadagno[:5], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} guadagno {c.guadagno * 100:+.1f} punti   "
            f"(il solo {c.miglior_singolo} vale {c.media_miglior_singolo:.1%}, la coppia {c.media_clean_sheet:.1%})"
        )

    triple = classifica(impegni, giornate, SOGLIA_FACILE, dimensione=3, max_costosi=0)
    print("\nMigliori 5 triple da alternare (nessun portiere caro):")
    for i, c in enumerate(triple[:5], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<34} "
            f"copertura {c.copertura:.0%}   media {c.media_clean_sheet:.1%}   "
            f"punti {c.punti_totali:+.1f}"
        )

    dati = costruisci_dati(forze, impegni, mu, rapporti)
    scrivi_html(dati, HTML)
    print(f"\nPagina interattiva: {HTML}")

    scrivi_frammento(dati, FRAMMENTO)
    print(f"Versione per il web:  {FRAMMENTO}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scarica", action="store_true", help="riscarica i dati dalle fonti e riscrive i CSV")
    p.add_argument("--apri", action="store_true", help="apre la pagina nel browser al termine")
    args = p.parse_args()

    rapporti: list[dict] = []
    if args.scarica:
        rapporti = scarica()
    elif not CSV_STORICO.exists() or not CSV_CALENDARIO.exists():
        print("Dati mancanti. Lancia prima:  python run.py --scarica")
        sys.exit(1)

    try:
        calcola(rapporti)
    except ErroreDati as e:
        print(f"Errore nei dati: {e}")
        sys.exit(1)

    if args.apri:
        webbrowser.open(HTML.as_uri())


if __name__ == "__main__":
    main()
