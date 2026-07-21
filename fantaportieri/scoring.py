"""Dalla forza delle squadre alla probabilita' di clean sheet, partita per partita.

Modello di Poisson: i gol che il mio portiere si aspetta di subire sono il
prodotto della media del campionato, dell'attacco di chi ho contro, della mia
fragilita' difensiva e del fattore campo. Da li' la probabilita' di non subire
gol e' semplicemente e^(-gol attesi).
"""

import math
from collections import defaultdict

from .config import (
    BONUS_IMBATTIBILITA,
    ESP_ATTACCO_AVVERSARIO,
    ESP_DIFESA_MIA,
    FATTORE_CASA,
    FATTORE_TRASFERTA,
)
from .models import Forza, Impegno, Partita


def gol_attesi_subiti(
    mia: str, avversario: str, gioco_in_casa: bool, forze: dict[str, Forza], mu: float
) -> float:
    """Gol che la mia squadra si aspetta di incassare in questa partita."""
    attacco_loro = forze[avversario].attacco ** ESP_ATTACCO_AVVERSARIO
    difesa_mia = forze[mia].difesa ** ESP_DIFESA_MIA
    # Il fattore campo si applica a CHI SEGNA, cioe' all'avversario:
    # se io sono in casa, lui e' in trasferta e segna un po' meno.
    campo = FATTORE_TRASFERTA if gioco_in_casa else FATTORE_CASA
    return mu * attacco_loro * difesa_mia * campo


def prob_clean_sheet(gol_attesi: float) -> float:
    """P(Poisson(lambda) == 0)."""
    return math.exp(-gol_attesi)


def punti_attesi(gol_attesi: float, bonus: float = BONUS_IMBATTIBILITA) -> float:
    """Bonus/malus attesi del portiere in questa partita, regolamento classico.

        -lambda           il malus: -1 per ogni gol subito, in media lambda gol
        +bonus * e^-lambda  il premio per l'imbattibilita', quando arriva

    Non include il voto base, che il modello non sa prevedere: e' la parte che
    dipende dal calendario, ed e' l'unica che ti serve per scegliere fra due portieri.

    Sulla singola partita ordina come `prob_clean_sheet` (entrambe decrescono al
    crescere di lambda), quindi la scelta di chi schierare non cambia. Cambia la
    SOMMA su 38 giornate: la probabilita' di imbattibilita' considera equivalenti
    "ne subisce 1" e "ne subisce 4", il fantacalcio no.
    """
    return -gol_attesi + bonus * math.exp(-gol_attesi)


def costruisci_impegni(
    calendario: list[Partita], forze: dict[str, Forza], mu: float
) -> dict[str, dict[int, Impegno]]:
    """Per ogni squadra, l'impegno di ogni giornata gia' valutato.

    E' la struttura su cui lavorano sia la classifica sia la pagina HTML.
    """
    impegni: dict[str, dict[int, Impegno]] = defaultdict(dict)

    for p in calendario:
        for squadra, avversario, in_casa in (
            (p.casa, p.trasferta, True),
            (p.trasferta, p.casa, False),
        ):
            if squadra not in forze or avversario not in forze:
                continue
            gol = gol_attesi_subiti(squadra, avversario, in_casa, forze, mu)
            impegni[squadra][p.giornata] = Impegno(
                giornata=p.giornata,
                squadra=squadra,
                avversario=avversario,
                in_casa=in_casa,
                gol_attesi_subiti=gol,
                prob_clean_sheet=prob_clean_sheet(gol),
                punti_attesi=punti_attesi(gol),
            )

    return dict(impegni)


def forza_complessiva(f: Forza) -> float:
    """Un solo numero per ordinare le squadre. Serve solo per assegnare i colori."""
    return f.attacco / f.difesa
