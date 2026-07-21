"""C'e' davvero complementarita' fra un portiere di big e uno di provinciale?

La domanda: esistono giornate in cui il portiere del Sassuolo e' schierabile
MEGLIO di quello dell'Inter? Se non ne esistesse nessuna, alternare non avrebbe
senso e la classifica per somma sarebbe l'unica risposta possibile.

    python prova_complementarita.py
"""

from pathlib import Path

from fantaportieri.data_io import leggi_calendario, leggi_storico
from fantaportieri.scoring import costruisci_impegni
from fantaportieri.strength import calcola_forze, media_gol_lega

RADICE = Path(__file__).parent
CSV_STORICO = RADICE / "data" / "storico.csv"
CSV_CALENDARIO = RADICE / "data" / "calendario.csv"

COPPIE_PROVA = [("Inter", "Sassuolo"), ("Napoli", "Lecce"), ("Inter", "Napoli")]


def main() -> None:
    storico = leggi_storico(CSV_STORICO)
    calendario = leggi_calendario(CSV_CALENDARIO)
    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}
    mu = media_gol_lega(storico)
    forze = calcola_forze(storico, squadre)
    impegni = costruisci_impegni(calendario, forze, mu)
    giornate = sorted({p.giornata for p in calendario})

    for a, b in COPPIE_PROVA:
        ma = sum(impegni[a][g].prob_clean_sheet for g in giornate) / len(giornate)
        mb = sum(impegni[b][g].prob_clean_sheet for g in giornate) / len(giornate)
        coppia = sum(max(impegni[a][g].prob_clean_sheet, impegni[b][g].prob_clean_sheet) for g in giornate)
        coppia /= len(giornate)

        volte_b = [g for g in giornate if impegni[b][g].prob_clean_sheet > impegni[a][g].prob_clean_sheet]

        print(f"== {a} + {b} ==")
        print(f"   {a} da solo: {ma:.1%}   {b} da solo: {mb:.1%}   coppia alternando: {coppia:.1%}")
        print(f"   guadagno rispetto a tenere solo il migliore: {coppia - max(ma, mb):+.1%}")
        print(f"   giornate in cui conviene {b}: {len(volte_b)} su {len(giornate)}")
        for g in volte_b[:3]:
            ia, ib = impegni[a][g], impegni[b][g]
            print(
                f"      g{g:<2}  {a} {'vs' if ia.in_casa else '@'} {ia.avversario} ({ia.prob_clean_sheet:.0%})"
                f"   <   {b} {'vs' if ib.in_casa else '@'} {ib.avversario} ({ib.prob_clean_sheet:.0%})"
            )
        print()


if __name__ == "__main__":
    main()
