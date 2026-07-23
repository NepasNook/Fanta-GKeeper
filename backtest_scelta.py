"""La coppia che il modello consiglia ad agosto fa davvero piu' punti degli altri?

`backtest.py` chiede se le probabilita' sono oneste: quando dico 40%, succede il 40%?
E' una domanda sul modello. Questa e' la domanda sullo STRUMENTO, ed e' diversa: un
modello puo' essere perfettamente calibrato e consigliare comunque coppie mediocri,
perche' la calibrazione misura le previsioni una per una mentre all'asta conta solo
se la coppia in cima alla lista fosse quella giusta.

    python backtest_scelta.py

Per ogni stagione di prova il modello viene allenato SOLO sulle stagioni precedenti,
poi produce la sua classifica sul calendario vero di quella stagione. Si prende la
coppia in prima posizione -- una per ciascuno dei quattro criteri -- e si contano i
fantapunti che quella coppia ha REALMENTE fatto, alternando ogni giornata il portiere
che il modello avrebbe schierato (scelta ex ante, senza sapere come e' finita).

Quattro riferimenti per dare una scala ai numeri, che da soli non dicono niente:

    miglior singolo   tenere sempre un portiere solo, quello che il modello stima
                      migliore. E' il confronto che conta davvero: se la coppia non
                      lo batte, alternare e' fatica sprecata e il secondo portiere
                      sono crediti buttati.
    coppia banale     le due squadre che hanno subito meno gol l'anno scorso. Zero
                      modello, solo memoria. E' il riferimento piu' severo: batterlo
                      e' l'unica prova che Poisson, decadimento, fattore campo e
                      prior neopromosse stiano aggiungendo qualcosa a "guarda com'e'
                      andata l'ultima volta".
    coppia media      la media esatta di tutte e 190 le coppie possibili. E' il
                      "compra a caso": batterlo e' il minimo sindacale.
    senno di poi      la coppia migliore a risultati noti, schierando ogni giornata
                      quello che ha davvero fatto piu' punti. Non e' raggiungibile,
                      e' il tetto: dice quanto margine esiste in assoluto.
    posizione         dove si e' piazzata la coppia scelta nella classifica finale
                      vera. 3 su 190 e' un successo, 95 su 190 e' un lancio di dado.

Nessun vincolo di spesa: le fasce di prezzo in `config.py` valgono per il 2026-27 e
applicarle al 2022 sarebbe un anacronismo. Qui si misura il potere predittivo del
calendario, non la strategia d'asta.
"""

from collections import defaultdict
from itertools import combinations

from fantaportieri.config import (
    BONUS_IMBATTIBILITA,
    MALUS_GOL,
    SOGLIA_FACILE,
    STAGIONI_STORICHE,
)
from fantaportieri.models import Partita
from fantaportieri.pairing import CRITERI, classifica

# Solo i criteri che hanno senso per un portiere. `totale` somma i punti di TUTTI
# i portieri del gruppo, ma in porta ne va uno: e' la misura degli attaccanti.
# `efficienza` divide per il prezzo, e qui i prezzi non si applicano (le fasce
# valgono per il 2026-27, non per il 2022).
CRITERI_PORTIERI = ["copertura", "media", "guadagno", "punti"]
from fantaportieri.scoring import costruisci_impegni
from fantaportieri.scrapers.storico_openfootball import scarica_giornate, scarica_stagione
from fantaportieri.strength import calcola_forze, media_gol_lega


def _punti_reali(gol_subiti: int) -> float:
    """I bonus/malus che il portiere ha davvero preso. Voto base escluso, come nel modello."""
    return -MALUS_GOL * gol_subiti + (BONUS_IMBATTIBILITA if gol_subiti == 0 else 0.0)


def _prepara(stagioni):
    """Aggregati (per allenare) e partite con giornata (per misurare). Una GET per stagione."""
    storico, giornate = {}, {}
    for s in stagioni:
        righe, _ = scarica_stagione(s)
        storico[s] = righe
        giornate[s] = scarica_giornate(s)
    return storico, giornate


def _giornate_complete(partite):
    """Solo le giornate con tutte e 10 le partite.

    Una giornata a meta' falserebbe il confronto: le coppie che comprendono una
    squadra la cui partita manca perderebbero punti rispetto alle altre per un
    buco nei dati, non per una previsione sbagliata. Nel 2024-25 manca la 38a.
    """
    per_giornata = defaultdict(list)
    for g, casa, trasferta, gc, gt in partite:
        per_giornata[g].append((casa, trasferta, gc, gt))
    return {g: v for g, v in per_giornata.items() if len(v) == 10}


def valuta_stagione(test, storico, giornate_per_stagione):
    """Allena su cio' che precede `test`, consiglia, poi conta i punti veri."""
    train = [s for s in STAGIONI_STORICHE if s < test]
    if not train:
        return None

    complete = _giornate_complete(giornate_per_stagione[test])
    if not complete:
        return None

    # Il calendario vero della stagione di prova: il modello lo conosce ad agosto,
    # e' l'unica cosa di quella stagione che gli e' lecito sapere.
    calendario = [
        Partita(giornata=g, casa=casa, trasferta=trasferta)
        for g, partite in complete.items()
        for casa, trasferta, _, _ in partite
    ]
    squadre = {p.casa for p in calendario} | {p.trasferta for p in calendario}

    storico_train = [r for s in train for r in storico[s]]
    mu = media_gol_lega(storico_train)
    forze = calcola_forze(storico_train, squadre)
    impegni = costruisci_impegni(calendario, forze, mu)
    elenco_giornate = sorted(complete)

    # (giornata, squadra) -> gol subiti davvero.
    subiti = {}
    for g, partite in complete.items():
        for casa, trasferta, gc, gt in partite:
            subiti[(g, casa)] = gt
            subiti[(g, trasferta)] = gc

    # Una sola valutazione: la classifica contiene gia' tutte le coppie con le loro
    # scelte giornata per giornata, e i quattro criteri sono solo ordinamenti diversi
    # dello stesso insieme.
    # Prezzi vuoti e nessun budget: le fasce di `config.py` valgono per il 2026-27,
    # applicarle al 2022 sarebbe un anacronismo. Qui si misura il potere predittivo
    # del calendario, non la strategia d'asta.
    tutte = classifica(impegni, elenco_giornate, SOGLIA_FACILE, {}, dimensione=2)

    def reali(combo):
        """Punti veri della coppia, schierando chi il modello avrebbe schierato."""
        return sum(_punti_reali(subiti[(g, s)]) for g, s in combo.scelte.items())

    punteggi = {c.squadre: reali(c) for c in tutte}
    ordinate = sorted(punteggi, key=lambda k: punteggi[k], reverse=True)
    posizione = {sq: i for i, sq in enumerate(ordinate, 1)}

    scelte_criteri = {}
    for nome in CRITERI_PORTIERI:
        vincente = max(tutte, key=CRITERI[nome])
        scelte_criteri[nome] = (
            vincente.squadre,
            punteggi[vincente.squadre],
            posizione[vincente.squadre],
        )

    # Miglior portiere singolo secondo il modello: quello con la somma piu' alta di
    # probabilita' di imbattibilita' sull'intera stagione.
    singolo = max(
        squadre,
        key=lambda s: sum(impegni[s][g].probabilita for g in elenco_giornate if g in impegni[s]),
    )
    punti_singolo = sum(_punti_reali(subiti[(g, singolo)]) for g in elenco_giornate)

    media_coppie = sum(punteggi.values()) / len(punteggi)

    # La coppia banale: le due difese meno battute della stagione precedente.
    # Nessun modello, solo memoria. I suoi punti si contano con la stessa regola --
    # ogni giornata si schiera quella con la partita piu' facile secondo il modello --
    # perche' altrimenti si confronterebbero due strategie e non due scelte d'acquisto.
    ultima = train[-1]
    subiti_ultima = {r.squadra: r.gol_subiti / r.partite for r in storico[ultima] if r.partite}
    coppia_banale = tuple(sorted(sorted(subiti_ultima, key=lambda s: subiti_ultima[s])[:2]))
    combo_banale = next((c for c in tutte if c.squadre == coppia_banale), None)
    banale = (
        (coppia_banale, punteggi[coppia_banale], posizione[coppia_banale])
        if combo_banale is not None
        else (coppia_banale, None, None)
    )

    # Il tetto: coppia migliore a risultati noti, schierando col senno di poi.
    senno = max(
        sum(max(_punti_reali(subiti[(g, a)]), _punti_reali(subiti[(g, b)])) for g in elenco_giornate)
        for a, b in combinations(sorted(squadre), 2)
    )

    return {
        "train": train,
        "giornate": len(elenco_giornate),
        "coppie": len(punteggi),
        "criteri": scelte_criteri,
        "singolo": (singolo, punti_singolo),
        "banale": banale,
        "media": media_coppie,
        "senno": senno,
    }


def stampa(test, esito):
    print(f"[allenato su {', '.join(esito['train'])}]")
    print(f"===== stagione di prova {test}  ({esito['giornate']} giornate complete) =====")
    print(f"     {'criterio':<12}{'coppia scelta':<28}{'fantapunti':>12}{'posizione':>13}")
    for nome in CRITERI_PORTIERI:
        squadre, punti, posto = esito["criteri"][nome]
        print(
            f"     {nome:<12}{' + '.join(squadre):<28}{punti:>12.1f}"
            f"{f'{posto} / ' + str(esito['coppie']):>13}"
        )
    singolo, punti_singolo = esito["singolo"]
    print("     --- riferimenti ---")
    print(f"     {'singolo':<12}{'il solo ' + singolo:<28}{punti_singolo:>12.1f}")
    gruppo, punti, posto = esito["banale"]
    if punti is None:
        print(f"     {'banale':<12}{' + '.join(gruppo):<28}{'n/d':>12}{'(retrocessa)':>13}")
    else:
        print(
            f"     {'banale':<12}{' + '.join(gruppo):<28}{punti:>12.1f}"
            f"{f'{posto} / ' + str(esito['coppie']):>13}"
        )
    print(f"     {'media':<12}{'tutte le ' + str(esito['coppie']) + ' coppie':<28}{esito['media']:>12.1f}")
    print(f"     {'tetto':<12}{'la migliore col senno di poi':<28}{esito['senno']:>12.1f}")
    print()


def riepilogo(esiti):
    print("===== complessivo =====")
    print(f"  {len(esiti)} stagioni di prova.\n")
    confrontabili = [e for e in esiti if e["banale"][1] is not None]
    print(f"  {'criterio':<12}{'posizione media':>17}{'percentile':>13}{'vs media':>11}{'vs singolo':>13}{'vs banale':>12}")
    for nome in CRITERI_PORTIERI:
        posti = [e["criteri"][nome][2] for e in esiti]
        # Percentile: 100 = ha scelto la coppia migliore in assoluto, 50 = come il caso.
        percentili = [
            100 * (e["coppie"] - e["criteri"][nome][2]) / (e["coppie"] - 1) for e in esiti
        ]
        vs_media = [e["criteri"][nome][1] - e["media"] for e in esiti]
        vs_singolo = [e["criteri"][nome][1] - e["singolo"][1] for e in esiti]
        vs_banale = [e["criteri"][nome][1] - e["banale"][1] for e in confrontabili]
        media_banale = sum(vs_banale) / len(vs_banale) if vs_banale else float("nan")
        print(
            f"  {nome:<12}{sum(posti) / len(posti):>17.1f}"
            f"{sum(percentili) / len(percentili):>12.0f}%"
            f"{sum(vs_media) / len(vs_media):>+11.1f}{sum(vs_singolo) / len(vs_singolo):>+13.1f}"
            f"{media_banale:>+12.1f}"
        )
    print()
    print("  posizione media   dove si e' piazzata la coppia consigliata nella classifica vera")
    print("  percentile        100 = la coppia migliore in assoluto, 50 = come sceglierla a caso")
    print("  vs media          fantapunti sopra il 'compra a caso'. Se e' <= 0 il modello non serve.")
    print("  vs singolo        fantapunti sopra il tenere un solo portiere, quello stimato migliore.")
    print("                    Se e' <= 0 il secondo portiere non ripaga i crediti che costa.")
    print("  vs banale         fantapunti sopra il 'prendo le due difese meno battute dell'anno")
    print("                    scorso'. E' il confronto piu' severo: se e' <= 0, tutto il modello")
    print("                    non sta aggiungendo niente alla semplice memoria.")


if __name__ == "__main__":
    print("Scarico i dati storici (una volta)...\n")
    storico, giornate = _prepara(STAGIONI_STORICHE)

    esiti = []
    for test in STAGIONI_STORICHE:
        esito = valuta_stagione(test, storico, giornate)
        if esito is None:
            continue
        stampa(test, esito)
        esiti.append(esito)

    if esiti:
        riepilogo(esiti)
