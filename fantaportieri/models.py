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
    """Una giornata vista da un giocatore di `squadra`.

    I nomi dei campi sono volutamente neutri: cambia il significato col ruolo, non
    la forma. E' per questo che `pairing` funziona per entrambi senza riscritture --
    e una terza copia della logica di combinazione e' esattamente cio' che questo
    progetto non si puo' permettere.

        ruolo         gol_attesi              probabilita
        portiere      quelli che incassa      P(non subire gol)
        attaccante    quelli che la squadra   P(la squadra segna almeno un gol)
                      segna
    """

    giornata: int
    squadra: str
    avversario: str
    in_casa: bool
    gol_attesi: float
    probabilita: float
    # Bonus/malus attesi col regolamento della lega, voto base escluso.
    punti_attesi: float


@dataclass(frozen=True)
class Combo:
    """Una coppia (o tripla) di squadre valutata sul calendario."""

    squadre: tuple[str, ...]
    # Media di `Impegno.probabilita` schierando ogni giornata il migliore del gruppo.
    media_probabilita: float
    copertura: float
    giornate_facili: int
    giornate_totali: int
    scelte: dict[int, str]
    # Le giornate in cui piu' squadre del gruppo valgono ESATTAMENTE uguale, con
    # tutte le pari merito. `scelte` ne fissa comunque una (serve un solo portiere
    # in campo); questo serve solo a dirlo, invece di fingere una preferenza.
    pari: dict[int, tuple[str, ...]]
    # Quanto rende alternare rispetto a tenere sempre il migliore del gruppo.
    # E' la misura della complementarita': se e' vicino a zero, il secondo
    # portiere e' un doppione e i suoi crediti sono buttati.
    guadagno: float
    miglior_singolo: str
    media_miglior_singolo: float
    # Bonus/malus attesi col regolamento classico (voto base escluso): per giornata
    # e sull'intera finestra. E' la stessa informazione della media di imbattibilita',
    # ma in punti invece che in percentuale -- e distingue "subisce 1" da "subisce 4".
    media_punti: float
    punti_totali: float
    # Punti sommando TUTTE le squadre del gruppo, non solo quella schierata.
    # Per i portieri non vuol dire niente, in porta ne va uno; per gli attaccanti
    # e' la misura giusta, perche' in campo ci vanno tutti e tre.
    punti_tutti: float
    # Costo del gruppo in quota del budget (0.15 = 15%), somma dei prezzi.
    prezzo: float
