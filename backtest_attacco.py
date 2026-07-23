"""Il terzetto di attaccanti consigliato ad agosto produce davvero piu' gol?

E' il gemello di `backtest_scelta.py` per la pagina attaccanti, e serve a rispondere
a una domanda che finora era rimasta senza risposta: quella pagina va usata o ignorata?

    python backtest_attacco.py

Due misure distinte, perche' due sono i salti da verificare.

PARTE 1 - il salto sul CALENDARIO. Per ogni stagione di prova il modello si allena
solo sulle precedenti, sceglie il terzetto migliore e si contano i gol che quelle tre
squadre hanno REALMENTE segnato. Il riferimento importante non e' il caso: e' la
scelta banale, cioe' "prendo le tre squadre che hanno segnato di piu' l'anno scorso",
che non richiede nessun modello. Se il modello non batte quella, tutta la macchina di
Poisson, decadimento e fattore campo non sta guadagnando niente.

PARTE 2 - il salto sul GIOCATORE. La pagina stima i gol di una SQUADRA, ma all'asta
compri un GIOCATORE, e di attaccanti una squadra ne ha tre o quattro (esterni
compresi). Quanta parte dei gol della squadra finisce al suo migliore? Se la quota
fosse costante, il segnale di squadra si tradurrebbe in modo prevedibile sul singolo;
se ballasse, il consiglio si ferma alla squadra e sul giocatore non dice niente.

Il secondo salto e' quello che nessuna quantita' di dati di squadra puo' colmare, e
va guardato prima di fidarsi della pagina.

Nota sul senno di poi: i marcatori veri di una stagione passata li conosciamo, ma ad
agosto non li conosceva nessuno -- e i giocatori del 2026-27 non saranno quelli del
2025-26. La Parte 2 non e' quindi una previsione, e' una misura di quanto il legame
squadra-giocatore sia regolare.
"""

import statistics
from collections import defaultdict
from itertools import combinations

from fantaportieri.config import BONUS_GOL, SOGLIA_ATTACCO, STAGIONI_STORICHE
from fantaportieri.models import Partita
from fantaportieri.pairing import CRITERI, classifica
from fantaportieri.scoring import costruisci_impegni_offensivi
from fantaportieri.scrapers.marcatori_wikipedia import miglior_marcatore
from fantaportieri.scrapers.storico_openfootball import scarica_giornate, scarica_stagione
from fantaportieri.strength import calcola_forze, media_gol_lega

# I criteri che la pagina attaccanti offre davvero. `efficienza` resta fuori: divide
# per il prezzo, e i prezzi valgono per il 2026-27, non per il 2022.
CRITERI_ATTACCO = ["totale", "media", "copertura", "punti", "guadagno"]

DIMENSIONE = 3


def _prepara(stagioni):
    storico, giornate = {}, {}
    for s in stagioni:
        righe, _ = scarica_stagione(s)
        storico[s] = righe
        giornate[s] = scarica_giornate(s)
    return storico, giornate


def _giornate_complete(partite):
    """Solo le giornate con tutte e 10 le partite: altrimenti i terzetti non sono
    confrontabili fra loro per un buco nei dati invece che per una previsione."""
    per_giornata = defaultdict(list)
    for g, casa, trasferta, gc, gt in partite:
        per_giornata[g].append((casa, trasferta, gc, gt))
    return {g: v for g, v in per_giornata.items() if len(v) == 10}


def _gol_segnati(complete) -> dict[str, int]:
    """Gol realmente segnati da ogni squadra nelle giornate considerate."""
    segnati: dict[str, int] = defaultdict(int)
    for partite in complete.values():
        for casa, trasferta, gc, gt in partite:
            segnati[casa] += gc
            segnati[trasferta] += gt
    return dict(segnati)


def valuta_stagione(test, storico, giornate_per_stagione):
    train = [s for s in STAGIONI_STORICHE if s < test]
    if not train:
        return None

    complete = _giornate_complete(giornate_per_stagione[test])
    if not complete:
        return None

    calendario = [
        Partita(giornata=g, casa=casa, trasferta=trasferta)
        for g, partite in complete.items()
        for casa, trasferta, _, _ in partite
    ]
    squadre = sorted({p.casa for p in calendario} | {p.trasferta for p in calendario})

    storico_train = [r for s in train for r in storico[s]]
    mu = media_gol_lega(storico_train)
    forze = calcola_forze(storico_train, set(squadre))
    impegni = costruisci_impegni_offensivi(calendario, forze, mu)
    elenco_giornate = sorted(complete)

    segnati = _gol_segnati(complete)
    reali = {
        gruppo: BONUS_GOL * sum(segnati.get(s, 0) for s in gruppo)
        for gruppo in combinations(squadre, DIMENSIONE)
    }
    ordinate = sorted(reali, key=lambda k: reali[k], reverse=True)
    posizione = {g: i for i, g in enumerate(ordinate, 1)}

    tutti = classifica(impegni, elenco_giornate, SOGLIA_ATTACCO, {}, dimensione=DIMENSIONE)
    scelte = {}
    for nome in CRITERI_ATTACCO:
        vincente = max(tutti, key=CRITERI[nome]).squadre
        scelte[nome] = (vincente, reali[vincente], posizione[vincente])

    # Il riferimento che conta: le tre squadre piu' prolifiche della stagione
    # PRECEDENTE. Zero modello, solo memoria. Se il modello non batte questo, la
    # differenza fra "guardo l'anno scorso" e "costruisco un Poisson" e' zero.
    ultima = train[-1]
    gol_ultima = {r.squadra: r.gol_fatti / r.partite for r in storico[ultima] if r.partite}
    banale = tuple(sorted(sorted(gol_ultima, key=lambda s: gol_ultima[s], reverse=True)[:DIMENSIONE]))
    # Una promossa puo' non essere nel calendario dell'anno dopo (retrocessa): in quel
    # caso il terzetto banale non e' comparabile e si salta.
    banale_reale = reali.get(banale)

    return {
        "train": train,
        "giornate": len(elenco_giornate),
        "terzetti": len(reali),
        "scelte": scelte,
        "media": sum(reali.values()) / len(reali),
        "senno": reali[ordinate[0]],
        "banale": (banale, banale_reale, posizione.get(banale)),
    }


def stampa(test, e):
    print(f"[allenato su {', '.join(e['train'])}]")
    print(f"===== stagione di prova {test}  ({e['giornate']} giornate complete) =====")
    print(f"     {'criterio':<12}{'terzetto scelto':<36}{'gol-punti':>11}{'posizione':>13}")
    for nome in CRITERI_ATTACCO:
        gruppo, punti, posto = e["scelte"][nome]
        print(
            f"     {nome:<12}{' + '.join(gruppo):<36}{punti:>11.0f}"
            f"{f'{posto} / ' + str(e['terzetti']):>13}"
        )
    print("     --- riferimenti ---")
    gruppo, punti, posto = e["banale"]
    if punti is None:
        print(f"     {'banale':<12}{' + '.join(gruppo):<36}{'n/d':>11}{'(retrocessa)':>13}")
    else:
        print(
            f"     {'banale':<12}{' + '.join(gruppo):<36}{punti:>11.0f}"
            f"{f'{posto} / ' + str(e['terzetti']):>13}"
        )
    print(f"     {'medio':<12}{'tutti i ' + str(e['terzetti']) + ' terzetti':<36}{e['media']:>11.0f}")
    print(f"     {'tetto':<12}{'il migliore col senno di poi':<36}{e['senno']:>11.0f}")
    print()


def riepilogo(esiti):
    print("===== complessivo: il salto sul calendario =====")
    print(f"  {len(esiti)} stagioni di prova.\n")
    print(f"  {'criterio':<12}{'posizione media':>17}{'percentile':>13}{'vs medio':>11}{'vs banale':>12}")
    righe = list(CRITERI_ATTACCO)
    confrontabili = [e for e in esiti if e["banale"][1] is not None]
    for nome in righe:
        posti = [e["scelte"][nome][2] for e in esiti]
        perc = [100 * (e["terzetti"] - e["scelte"][nome][2]) / (e["terzetti"] - 1) for e in esiti]
        vs_medio = [e["scelte"][nome][1] - e["media"] for e in esiti]
        vs_banale = [e["scelte"][nome][1] - e["banale"][1] for e in confrontabili]
        media_banale = sum(vs_banale) / len(vs_banale) if vs_banale else float("nan")
        print(
            f"  {nome:<12}{sum(posti) / len(posti):>17.1f}{sum(perc) / len(perc):>12.0f}%"
            f"{sum(vs_medio) / len(vs_medio):>+11.0f}{media_banale:>+12.0f}"
        )
    print()
    print("  vs medio    gol-punti sopra il 'compra a caso'.")
    print("  vs banale   gol-punti sopra il 'prendo chi ha segnato di piu' l'anno scorso'.")
    print("              Se e' <= 0, il modello non aggiunge niente alla memoria.")
    print()


def parte_giocatore(stagioni):
    """Quanta parte dei gol di squadra finisce al suo miglior attaccante?"""
    print("===== il salto sul giocatore =====")
    print("  Il modello stima i gol della SQUADRA. All'asta compri un GIOCATORE, e di")
    print("  attaccanti una squadra ne ha tre o quattro. Quanto ne prende il migliore?\n")

    quote: list[float] = []
    per_stagione: dict[str, list[float]] = {}
    for stagione in stagioni:
        migliori = miglior_marcatore(stagione)
        if not migliori:
            continue
        righe, _ = scarica_stagione(stagione)
        gol_squadra = {r.squadra: r.gol_fatti for r in righe}
        quote_stagione = []
        for squadra, (_, reti) in migliori.items():
            totale = gol_squadra.get(squadra, 0)
            if totale:
                quote_stagione.append(reti / totale)
        if quote_stagione:
            per_stagione[stagione] = quote_stagione
            quote.extend(quote_stagione)

    if not quote:
        print("  Nessun dato sui marcatori: la fonte non ha risposto o le voci sono cambiate.\n")
        return

    print(f"     {'stagione':<12}{'squadre':>9}{'quota media':>14}{'min':>8}{'max':>8}")
    for stagione, valori in sorted(per_stagione.items()):
        print(
            f"     {stagione:<12}{len(valori):>9}{sum(valori) / len(valori):>13.0%}"
            f"{min(valori):>8.0%}{max(valori):>8.0%}"
        )

    media = sum(quote) / len(quote)
    scarto = statistics.pstdev(quote)
    print(
        f"\n  Su {len(quote)} coppie squadra-stagione: il miglior marcatore prende in media "
        f"il {media:.0%}\n  dei gol della sua squadra, con scarto tipico {scarto:.0%} "
        f"(dal {min(quote):.0%} al {max(quote):.0%})."
    )
    print(
        "\n  Come si legge: quanto piu' quello scarto e' largo, tanto meno il gol di squadra\n"
        "  predice il gol del singolo, e tanto piu' la pagina attaccanti va presa per quello\n"
        "  che e' -- una classifica di SQUADRE con il calendario giusto, non di giocatori.\n"
        "  Nota che qui il bomber e' noto col senno di poi: ad agosto non lo sapeva nessuno,\n"
        "  e i giocatori del 2026-27 non saranno quelli del 2025-26. E' un limite superiore\n"
        "  a quanto si possa trasferire dal reparto al singolo, non una previsione.\n"
    )


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

    parte_giocatore(STAGIONI_STORICHE)
