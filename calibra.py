"""Quali parametri il modello preferirebbe davvero? Grid search walk-forward.

I valori in `config.py` sono stati scelti ragionando, non misurando: il docstring
di `backtest.py` lo ammette. Qui si misurano. Stessa validazione walk-forward del
backtest -- per ogni stagione di prova si allena SOLO sulle precedenti, quindi non
si guarda mai il futuro -- ma invece di giudicare un singolo insieme di parametri
se ne provano centinaia e si tiene il migliore.

    python calibra.py

L'obiettivo e' la verosimiglianza di Poisson sui gol effettivamente subiti, non il
Brier sull'imbattibilita'. Col regolamento classico il portiere prende -1 per OGNI
gol subito e +1 se resta imbattuto: una metrica che considera identici "ne subisce
1" e "ne subisce 4" butterebbe via meta' di cio' che ti fa punti. La verosimiglianza
usa tutta la distribuzione, e l'imbattibilita' ne e' solo il caso k=0.

ATTENZIONE ALL'OVERFITTING. Le stagioni di prova sono quattro. Se un parametro
"vince" con un margine minuscolo quel margine e' rumore, non conoscenza: lo script
stampa apposta lo scarto rispetto ai valori attuali, e a parita' sostanziale
conviene tenere il numero tondo che hai gia'. Non copiare la griglia a occhi chiusi.
"""

import math

from fantaportieri.config import (
    DECADIMENTO_STAGIONI,
    ESP_ATTACCO_AVVERSARIO,
    ESP_DIFESA_MIA,
    FATTORE_CASA,
    FATTORE_TRASFERTA,
    PESO_REGRESSIONE_MEDIA,
    PRIOR_NEOPROMOSSA_ATTACCO,
    PRIOR_NEOPROMOSSA_DIFESA,
    STAGIONI_STORICHE,
)
from fantaportieri.scrapers.storico_openfootball import scarica_partite, scarica_stagione
from fantaportieri.strength import calcola_forze, media_gol_lega

# --- Le griglie da esplorare ------------------------------------------------
# Volutamente grossolane e su valori "tondi": una griglia fitta su quattro stagioni
# di prova troverebbe solo il rumore con piu' cifre decimali.
DECADIMENTI = [0.45, 0.55, 0.65, 0.80, 1.00]
PESI_REGRESSIONE = [0.25, 0.50, 1.00, 2.00]
ESP_ATTACCO = [0.90, 1.05, 1.20, 1.35, 1.50]
ESP_DIFESA = [0.70, 0.90, 1.10, 1.30]
# (casa, trasferta). Il primo e' "il campo non conta", utile come riferimento.
CAMPI = [(1.00, 1.00), (1.04, 0.96), (1.08, 0.93), (1.12, 0.89)]
# Fase 2, cercata a parte tenendo fermo il resto: riguarda solo ~3 squadre su 20.
PRIORI = [(1.00, 1.00), (0.90, 1.10), (0.82, 1.18), (0.75, 1.25), (0.70, 1.30)]

ATTUALI = (
    DECADIMENTO_STAGIONI,
    PESO_REGRESSIONE_MEDIA,
    ESP_ATTACCO_AVVERSARIO,
    ESP_DIFESA_MIA,
    (FATTORE_CASA, FATTORE_TRASFERTA),
)


def _prepara() -> tuple[dict, dict]:
    """Scarica una volta sola. La cache in storico_openfootball evita i doppioni."""
    storico, partite = {}, {}
    for s in STAGIONI_STORICHE:
        righe, _ = scarica_stagione(s)
        storico[s] = righe
        partite[s] = scarica_partite(s)
    return storico, partite


def _basi(storico, partite, decadimento, peso_regressione, prior):
    """Per ogni stagione di prova: (log mu, campioni) con le forze gia' calcolate.

    I campioni tengono i LOGARITMI di attacco e difesa perche' il ciclo interno
    valuta migliaia di combinazioni di esponenti: in forma logaritmica ogni
    combinazione costa una sola exp invece di due elevamenti a potenza.
    """
    basi = []
    for test in STAGIONI_STORICHE:
        train = [s for s in STAGIONI_STORICHE if s < test]
        if not train:
            continue
        righe_train = [r for s in train for r in storico[s]]
        squadre = {c for c, _, _, _ in partite[test]} | {t for _, t, _, _ in partite[test]}
        mu = media_gol_lega(righe_train, decadimento)
        forze = calcola_forze(righe_train, squadre, decadimento, peso_regressione, *prior)

        campioni = []
        for casa, trasferta, gc, gt in partite[test]:
            for mia, avv, in_casa, subiti in (
                (casa, trasferta, True, gt),
                (trasferta, casa, False, gc),
            ):
                campioni.append(
                    (math.log(forze[avv].attacco), math.log(forze[mia].difesa), in_casa, subiti)
                )
        basi.append((math.log(mu), campioni))
    return basi


def _nll(basi, esp_attacco, esp_difesa, campo) -> float:
    """Log-verosimiglianza negativa media di Poisson (piu' bassa = predice meglio).

    Il termine log(k!) e' costante rispetto ai parametri: non cambia la classifica,
    ma lo includiamo perche' il numero stampato sia la verosimiglianza vera.
    """
    log_casa, log_trasferta = math.log(campo[0]), math.log(campo[1])
    totale = 0.0
    n = 0
    for log_mu, campioni in basi:
        for log_att, log_dif, in_casa, k in campioni:
            log_lam = log_mu + esp_attacco * log_att + esp_difesa * log_dif
            log_lam += log_trasferta if in_casa else log_casa
            totale += math.exp(log_lam) - k * log_lam + math.lgamma(k + 1)
            n += 1
    return totale / n


def _diagnostica(basi, esp_attacco, esp_difesa, campo) -> dict:
    """Brier e skill (per confronto con backtest.py) + errore sui fantapunti."""
    log_casa, log_trasferta = math.log(campo[0]), math.log(campo[1])
    previsti, reali, punti_previsti, punti_reali, lam_tot, gol_tot = [], [], 0.0, 0.0, 0.0, 0
    for log_mu, campioni in basi:
        for log_att, log_dif, in_casa, k in campioni:
            log_lam = log_mu + esp_attacco * log_att + esp_difesa * log_dif
            log_lam += log_trasferta if in_casa else log_casa
            lam = math.exp(log_lam)
            previsti.append(math.exp(-lam))
            reali.append(1 if k == 0 else 0)
            # Regolamento classico: -1 per ogni gol subito, +1 se imbattuto.
            punti_previsti += -lam + math.exp(-lam)
            punti_reali += -k + (1 if k == 0 else 0)
            lam_tot += lam
            gol_tot += k

    n = len(previsti)
    base = sum(reali) / n
    brier = sum((p - r) ** 2 for p, r in zip(previsti, reali)) / n
    brier_base = sum((base - r) ** 2 for r in reali) / n
    return {
        "brier": brier,
        "skill": 1 - brier / brier_base,
        "bias_gol": (lam_tot - gol_tot) / n,
        "bias_punti": (punti_previsti - punti_reali) / n,
    }


def _etichetta(combo) -> str:
    dec, reg, ea, ed, campo = combo
    return (
        f"dec {dec:.2f}  reg {reg:.2f}  att^{ea:.2f}  dif^{ed:.2f}  "
        f"campo {campo[0]:.2f}/{campo[1]:.2f}"
    )


def cerca(storico, partite, prior) -> list[tuple[float, tuple]]:
    """Griglia completa. Le forze dipendono solo da (decadimento, regressione),
    quindi si calcolano una volta per coppia e si riusano su tutti gli esponenti."""
    risultati = []
    coppie = [(d, r) for d in DECADIMENTI for r in PESI_REGRESSIONE]
    for i, (dec, reg) in enumerate(coppie, 1):
        print(f"   [{i:2d}/{len(coppie)}] decadimento {dec:.2f}, regressione {reg:.2f} ...")
        basi = _basi(storico, partite, dec, reg, prior)
        for ea in ESP_ATTACCO:
            for ed in ESP_DIFESA:
                for campo in CAMPI:
                    risultati.append((_nll(basi, ea, ed, campo), (dec, reg, ea, ed, campo)))
    risultati.sort(key=lambda x: x[0])
    return risultati


if __name__ == "__main__":
    print("Scarico i dati storici (una volta)...\n")
    storico, partite = _prepara()
    prove = [s for s in STAGIONI_STORICHE if s > STAGIONI_STORICHE[0]]
    print(f"Stagioni di prova: {', '.join(prove)}   (allenamento sempre solo sulle precedenti)\n")

    print("== Fase 1: parametri del modello ==")
    prior_attuale = (PRIOR_NEOPROMOSSA_ATTACCO, PRIOR_NEOPROMOSSA_DIFESA)
    risultati = cerca(storico, partite, prior_attuale)

    print(f"\nMigliori 8 combinazioni su {len(risultati)} provate:")
    print(f"   {'NLL':>8}  parametri")
    for nll, combo in risultati[:8]:
        print(f"   {nll:8.4f}  {_etichetta(combo)}")

    nll_attuale = next((n for n, c in risultati if c == ATTUALI), None)
    if nll_attuale is None:
        basi_att = _basi(storico, partite, ATTUALI[0], ATTUALI[1], prior_attuale)
        nll_attuale = _nll(basi_att, ATTUALI[2], ATTUALI[3], ATTUALI[4])
        posizione = sum(1 for n, _ in risultati if n < nll_attuale) + 1
    else:
        posizione = [c for _, c in risultati].index(ATTUALI) + 1

    migliore_nll, migliore = risultati[0]
    print(f"\nConfigurazione attuale: NLL {nll_attuale:.4f}  (posizione {posizione} su {len(risultati)})")
    print(f"   {_etichetta(ATTUALI)}")
    guadagno = nll_attuale - migliore_nll
    print(f"Guadagno del migliore: {guadagno:.4f} nat/partita ({guadagno / nll_attuale:.2%})")
    if guadagno < 0.005:
        print("   -> scarto trascurabile: i valori attuali vanno benissimo, non toccarli.")

    print("\n== Fase 2: prior delle neopromosse (resto dei parametri fermo sul migliore) ==")
    dec, reg, ea, ed, campo = migliore
    classifica_prior = []
    for prior in PRIORI:
        basi = _basi(storico, partite, dec, reg, prior)
        classifica_prior.append((_nll(basi, ea, ed, campo), prior))
    classifica_prior.sort(key=lambda x: x[0])
    for nll, (pa, pd) in classifica_prior:
        segna = "  <- attuale" if (pa, pd) == prior_attuale else ""
        print(f"   NLL {nll:.4f}   attacco {pa:.2f} / difesa {pd:.2f}{segna}")

    prior_migliore = classifica_prior[0][1]

    print("\n== Verifica del vincitore ==")
    basi = _basi(storico, partite, dec, reg, prior_migliore)
    d = _diagnostica(basi, ea, ed, campo)
    print(f"   skill vs previsione banale: {d['skill']:+.1%}   (>0 = il modello aggiunge valore)")
    print(f"   Brier: {d['brier']:.4f}")
    print(f"   bias sui gol:      {d['bias_gol']:+.3f} a partita  (>0 = prevedo troppi gol)")
    print(f"   bias sui fantapunti: {d['bias_punti']:+.3f} a partita  (regolamento classico)")

    print("\n== Da incollare in config.py, SE lo scarto ti convince ==")
    print(f"DECADIMENTO_STAGIONI = {dec}")
    print(f"PESO_REGRESSIONE_MEDIA = {reg}")
    print(f"ESP_ATTACCO_AVVERSARIO = {ea}")
    print(f"ESP_DIFESA_MIA = {ed}")
    print(f"FATTORE_CASA = {campo[0]}")
    print(f"FATTORE_TRASFERTA = {campo[1]}")
    print(f"PRIOR_NEOPROMOSSA_ATTACCO = {prior_migliore[0]}")
    print(f"PRIOR_NEOPROMOSSA_DIFESA = {prior_migliore[1]}")
