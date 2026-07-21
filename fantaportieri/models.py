"""Strutture dati condivise da tutto il progetto."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StatStagione:
    """Il rendimento di una squadra in una stagione: la materia prima del modello."""

    stagione: str
    squadra: str
    partite: int
    gol_fatti: int
    gol_subiti: int


@dataclass(frozen=True)
class Partita:
    giornata: int
    casa: str
    trasferta: str


@dataclass(frozen=True)
class Forza:
    """Forza di una squadra, relativa alla media del campionato.

    attacco 1.30 = segna il 30% in piu' della media.
    difesa  0.70 = subisce il 30% in meno della media (piu' basso = piu' solido).
    """

    squadra: str
    attacco: float
    difesa: float
    stagioni_usate: int
    # Non ha giocato l'ultima stagione di A, quindi arriva dalla B. Puo' comunque
    # avere `stagioni_usate > 0` se in A c'era gia' stata negli anni precedenti.
    neopromossa: bool


@dataclass(frozen=True)
class Impegno:
    """Una giornata vista dal portiere di `squadra`."""

    giornata: int
    squadra: str
    avversario: str
    in_casa: bool
    gol_attesi_subiti: float
    prob_clean_sheet: float


@dataclass(frozen=True)
class Combo:
    """Una coppia (o tripla) di squadre valutata sul calendario."""

    squadre: tuple[str, ...]
    media_clean_sheet: float
    copertura: float
    giornate_facili: int
    giornate_totali: int
    scelte: dict[int, str]
    # Quanto rende alternare rispetto a tenere sempre il migliore del gruppo.
    # E' la misura della complementarita': se e' vicino a zero, il secondo
    # portiere e' un doppione e i suoi crediti sono buttati.
    guadagno: float
    miglior_singolo: str
    media_miglior_singolo: float
