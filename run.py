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
    BUDGET,
    COPERTURA_MINIMA_STORICO,
    SOGLIA_ATTACCO,
    SOGLIA_FACILE,
    STAGIONE_CORRENTE,
    STAGIONI_STORICHE,
)
from fantaportieri.data_io import (
    ErroreDati,
    leggi_calendario,
    leggi_prezzi,
    leggi_storico,
    scrivi_calendario,
    scrivi_storico,
)
from fantaportieri.pairing import classifica
from fantaportieri.report import costruisci_dati, scrivi_frammento, scrivi_html
from fantaportieri.scoring import costruisci_impegni, costruisci_impegni_offensivi, solidita
from fantaportieri.scrapers.rete import ErroreRete
from fantaportieri.strength import calcola_forze, media_gol_lega

RADICE = Path(__file__).parent
CSV_STORICO = RADICE / "data" / "storico.csv"
CSV_CALENDARIO = RADICE / "data" / "calendario.csv"
CSV_PREZZI = RADICE / "data" / "prezzi.csv"

# I documenti autonomi: si aprono con doppio clic, contengono tutto, funzionano offline.
HTML = {
    "portieri": RADICE / "classifica_portieri.html",
    "attaccanti": RADICE / "classifica_attaccanti.html",
}
# Le stesse pagine senza l'involucro <html>/<head>/<body>, per la pubblicazione web.
FRAMMENTO = {
    "portieri": RADICE / "build" / "artifact.html",
    "attaccanti": RADICE / "build" / "artifact_attaccanti.html",
}


def scarica() -> list[dict]:
    """Scarica dalle fonti e salva i CSV. Restituisce il rapporto sullo storico.

    Prima scarica e valida TUTTO, poi scrive. Scrivendo man mano, una fonte caduta
    a meta' lascerebbe su disco un calendario nuovo accanto a uno storico vecchio:
    due CSV coerenti singolarmente e incoerenti fra loro, che e' il modo peggiore
    di fallire perche' il calcolo dopo funziona lo stesso.
    """
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
    print(f"  {len(partite)} partite, validate")

    print(f"Storico {STAGIONI_STORICHE[0]}..{STAGIONI_STORICHE[-1]} da openfootball ...")
    righe, rapporti = scarica_storico(STAGIONI_STORICHE)
    scarse = []
    for r in rapporti:
        segnale = "" if r["copertura"] >= COPERTURA_MINIMA_STORICO else "  <-- troppo incompleta"
        print(
            f"  {r['stagione']}: {r['partite_con_risultato']}/{r['partite_in_calendario']} "
            f"partite ({r['copertura']:.0%}){segnale}"
        )
        if r["copertura"] < COPERTURA_MINIMA_STORICO:
            scarse.append(r)

    if scarse:
        print(
            f"\n  ATTENZIONE: {len(scarse)} stagioni sotto la copertura minima "
            f"({COPERTURA_MINIMA_STORICO:.0%}). Le forze sarebbero stimate su mezzo\n"
            "  campionato e sembrerebbero comunque ragionevoli, quindi i CSV non sono\n"
            "  stati scritti. Se la fonte e' semplicemente indietro, abbassa\n"
            "  COPERTURA_MINIMA_STORICO in config.py, oppure togli quella stagione."
        )
        sys.exit(1)

    scrivi_calendario(CSV_CALENDARIO, partite)
    print(f"\n  {len(partite)} partite -> {CSV_CALENDARIO.relative_to(RADICE)}")
    scrivi_storico(CSV_STORICO, righe)
    print(f"  {len(righe)} righe squadra-stagione -> {CSV_STORICO.relative_to(RADICE)}")
    return rapporti


def _classifica_portieri(impegni, giornate, prezzi) -> None:
    budget = BUDGET["portieri"]
    senza = classifica(impegni, giornate, SOGLIA_FACILE, prezzi, dimensione=2)
    print(f"\nMigliori 10 coppie SENZA vincolo di spesa (soglia {SOGLIA_FACILE:.0%}, giornate 1-{max(giornate)}):")
    for i, c in enumerate(senza[:10], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} costa {c.prezzo:>5.0%}   "
            f"copertura {c.copertura:.0%} ({c.giornate_facili}/{c.giornate_totali})   "
            f"media {c.media_probabilita:.1%}   punti {c.punti_totali:+.1f}"
        )

    entro = classifica(impegni, giornate, SOGLIA_FACILE, prezzi, dimensione=2, budget=budget)
    print(f"\nMigliori 10 coppie ENTRO IL BUDGET ({budget:.0%} del monte crediti):")
    for i, c in enumerate(entro[:10], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} costa {c.prezzo:>5.0%}   "
            f"copertura {c.copertura:.0%} ({c.giornate_facili}/{c.giornate_totali})   "
            f"media {c.media_probabilita:.1%}   punti {c.punti_totali:+.1f}"
        )

    resa = classifica(
        impegni, giornate, SOGLIA_FACILE, prezzi, dimensione=2,
        budget=budget, ordina="efficienza",
    )
    print("\nMiglior RESA PER CREDITO (imbattibilita' media divisa per il prezzo):")
    for i, c in enumerate(resa[:5], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<26} costa {c.prezzo:>5.0%}   "
            f"media {c.media_probabilita:.1%}   resa {c.media_probabilita / c.prezzo:.2f}"
        )


def _classifica_attaccanti(impegni, giornate, prezzi) -> None:
    budget = BUDGET["attaccanti"]
    # Ordinati per `totale` e non per copertura: in campo vanno tutti e tre, quindi
    # conta la somma. La copertura, che per i portieri e' il criterio naturale, qui
    # non ordina -- l'Inter supera la soglia in 27 partite su 38 e la seconda squadra
    # in 5, quindi "copertura alta" finisce per voler dire solo "hai preso l'Inter".
    terzetti = classifica(
        impegni, giornate, SOGLIA_ATTACCO, prezzi, dimensione=3,
        budget=budget, ordina="totale",
    )
    print(
        f"\nMigliori 10 TERZETTI di attaccanti entro il {budget:.0%} del monte crediti, "
        f"per fantapunti di tutti e tre:"
    )
    for i, c in enumerate(terzetti[:10], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<34} costa {c.prezzo:>5.0%}   "
            f"gol-punti {c.punti_tutti:.0f}   copertura {c.copertura:.0%}"
        )

    resa = classifica(
        impegni, giornate, SOGLIA_ATTACCO, prezzi, dimensione=3,
        budget=budget, ordina="efficienza",
    )
    print("\nMiglior RESA PER CREDITO in attacco:")
    for i, c in enumerate(resa[:5], 1):
        print(
            f"  {i:2d}. {' + '.join(c.squadre):<34} costa {c.prezzo:>5.0%}   "
            f"media {c.media_probabilita:.1%}   resa {c.media_probabilita / c.prezzo:.2f}"
        )


def calcola(rapporti: list[dict]) -> None:
    storico = leggi_storico(CSV_STORICO)
    calendario = leggi_calendario(CSV_CALENDARIO)
    prezzi = leggi_prezzi(CSV_PREZZI)
    if not CSV_PREZZI.exists():
        print(f"({CSV_PREZZI.name} assente: uso i prezzi di config.py)")

    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}
    mu = media_gol_lega(storico)
    forze = calcola_forze(storico, squadre)
    giornate = sorted({p.giornata for p in calendario})

    print(f"\nMedia campionato: {mu:.2f} gol per squadra a partita")

    neopromosse = [f.squadra for f in forze.values() if f.neopromossa]
    if neopromosse:
        print(f"Dalla Serie B (prior neopromossa): {', '.join(sorted(neopromosse))}")

    print("\nForza stimata, ordinata per SOLIDITA' DIFENSIVA (cio' che conta per un portiere):")
    for f in sorted(forze.values(), key=solidita, reverse=True):
        print(
            f"  {f.squadra:<12} dif {f.difesa:.2f} (solidita' {solidita(f):.2f})   "
            f"att {f.attacco:.2f}   "
            f"prezzi P {prezzi['portieri'].get(f.squadra, 0.03):>4.0%} / "
            f"A {prezzi['attaccanti'].get(f.squadra, 0.03):>4.0%}"
        )

    impegni = costruisci_impegni(calendario, forze, mu)
    _classifica_portieri(impegni, giornate, prezzi["portieri"])

    offensivi = costruisci_impegni_offensivi(calendario, forze, mu)
    _classifica_attaccanti(offensivi, giornate, prezzi["attaccanti"])

    for ruolo, dati_impegni in (("portieri", impegni), ("attaccanti", offensivi)):
        dati = costruisci_dati(forze, dati_impegni, mu, rapporti, prezzi[ruolo], ruolo=ruolo)
        scrivi_html(dati, HTML[ruolo])
        scrivi_frammento(dati, FRAMMENTO[ruolo])
        print(f"\nPagina {ruolo}: {HTML[ruolo]}")
        print(f"  per il web:  {FRAMMENTO[ruolo]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scarica", action="store_true", help="riscarica i dati dalle fonti e riscrive i CSV")
    p.add_argument("--apri", action="store_true", help="apre la pagina nel browser al termine")
    args = p.parse_args()

    rapporti: list[dict] = []
    if args.scarica:
        try:
            rapporti = scarica()
        except ErroreRete as e:
            print(f"Fonte irraggiungibile: {e}")
            print("I CSV gia' presenti sono intatti: 'python run.py' senza --scarica funziona.")
            sys.exit(1)
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
