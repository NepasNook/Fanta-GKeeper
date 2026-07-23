"""Parametri del modello. E' il file da toccare per calibrare."""

STAGIONE_CORRENTE = "2026-27"

# Quante stagioni concluse alimentano la stima delle forze.
N_STAGIONI_STORICHE = 5


def _stagioni_precedenti(corrente: str, quante: int) -> list[str]:
    """Le `quante` stagioni concluse prima di `corrente`, dalla piu' vecchia."""
    anno = int(corrente.split("-")[0])
    return [f"{a}-{str(a + 1)[-2:]}" for a in range(anno - quante, anno)]


# Derivate, non scritte a mano: l'ultima stagione dello storico DEVE essere quella
# subito precedente alla corrente, perche' `strength.calcola_forze` marca come
# neopromossa chi non vi compare. Tenendo due liste indipendenti bastava aggiornarne
# una sola per far risultare mezzo campionato promosso dalla B, in silenzio.
STAGIONI_STORICHE = _stagioni_precedenti(STAGIONE_CORRENTE, N_STAGIONI_STORICHE)

# Copertura minima (partite con risultato / partite in calendario) perche' una
# stagione sia accettata. openfootball e' mantenuto dalla comunita': una stagione
# a meta' produrrebbe forze plausibili ma sbagliate, quindi vale la stessa regola
# del calendario -- meglio non scrivere i CSV che scriverli falsi.
COPERTURA_MINIMA_STORICO = 0.90

# Decadimento esponenziale del peso di una stagione per ogni anno di eta'.
# 0.65 -> l'ultima stagione pesa 1.00, quella prima 0.65, ... il 2021-22 pesa 0.18.
DECADIMENTO_STAGIONI = 0.65

# Quanto "tira verso la media del campionato" una squadra con pochi dati.
# E' espresso nella stessa unita' dei pesi stagionali: 0.5 = mezza stagione di
# evidenza fittizia a favore della media. Serve per Como & co. (poche stagioni).
PESO_REGRESSIONE_MEDIA = 0.5

# Esponenti del modello di Poisson.
# ESP_ATTACCO_AVVERSARIO > ESP_DIFESA_MIA significa: conta di piu' chi ho contro
# che quanto e' solida la mia difesa. E' la richiesta "evitare il portiere contro l'Inter".
ESP_ATTACCO_AVVERSARIO = 1.20
ESP_DIFESA_MIA = 0.90

# Fattore campo, volutamente mite (richiesta: "si' ma non pesa tanto").
# Moltiplica i gol attesi di chi gioca in quel campo.
FATTORE_CASA = 1.08
FATTORE_TRASFERTA = 0.93

# Prior per chi non ha nessuna stagione di Serie A alle spalle (neopromosse).
# 1.00 = esattamente la media del campionato.
PRIOR_NEOPROMOSSA_ATTACCO = 0.82   # segna meno della media
PRIOR_NEOPROMOSSA_DIFESA = 1.18    # subisce piu' della media

# Soglia di default per considerare "facile" una partita (prob. di clean sheet).
# Nella pagina HTML e' uno slider, questo e' solo il valore iniziale.
SOGLIA_FACILE = 0.40

# La soglia degli attaccanti misura l'evento OPPOSTO a quella dei portieri: una
# squadra segna in circa due partite su tre (mediana 68%, estremi 41% e 94%), mentre
# resta imbattuta in una su tre. Va quindi molto piu' in alto.
#
# 0.80 e' un compromesso fra due modi di rompersi, e nessuna scelta e' buona --
# vedi la nota in CLAUDE.md. Sotto, la copertura satura (al 75% quasi tutti i
# terzetti coprono 38/38); sopra, degenera in "hai l'Inter?", perche' l'Inter supera
# l'85% in 27 partite su 38 e la seconda squadra (Atalanta) in 5. A 0.80 restano 17
# valori distinti di copertura, che e' il massimo ottenibile.
#
# La conseguenza vera non e' la soglia ma il criterio: la pagina attaccanti parte
# ordinata per `totale`, non per copertura.
SOGLIA_ATTACCO = 0.80

# Prezzo atteso di ogni giocatore, in QUOTA DEL BUDGET (0.10 = 10%). Percentuali e
# non crediti perche' ogni lega ha un monte diverso: cosi' la stessa tabella vale per
# una lega da 500 e per una da 1000.
#
# Due tabelle separate perche' sono due mercati diversi. Un attaccante di Inter costa
# tre volte il suo portiere, e le gerarchie non coincidono nemmeno: la Fiorentina e'
# terza fascia in attacco e sesta in porta.
#
# NON seguono la forza stimata, e non e' un errore da correggere. Il Lecce e'
# quindicesimo per solidita' ma il suo portiere costa come quello della Fiorentina,
# decima, perche' il prezzo lo fa anche il nome di chi para; il Genoa e' dato sotto
# media in attacco ma il suo attaccante si paga da squadra propositiva. Il prezzo
# segue l'aspettativa, il modello lo storico: e' esattamente per questo che la
# tabella non si puo' derivare dal modello e va scritta a mano.
#
# Sono solo i valori di partenza: `data/prezzi.csv` ha la precedenza, ed e' li' che
# vanno corretti quando esce il listone.
PREZZI_DEFAULT = {
    "portieri": {
        "Inter": 0.10, "Roma": 0.10, "Napoli": 0.10, "Milan": 0.10,
        "Juventus": 0.08, "Como": 0.08, "Atalanta": 0.08,
        "Lazio": 0.06, "Bologna": 0.06, "Fiorentina": 0.06,
        "Lecce": 0.04, "Torino": 0.04, "Udinese": 0.04, "Genoa": 0.04, "Parma": 0.04,
        "Cagliari": 0.03, "Venezia": 0.03, "Sassuolo": 0.03, "Monza": 0.03,
        "Frosinone": 0.03,
    },
    "attaccanti": {
        "Inter": 0.30, "Roma": 0.30,
        "Napoli": 0.25, "Milan": 0.25, "Juventus": 0.25,
        "Atalanta": 0.20, "Como": 0.20, "Fiorentina": 0.20,
        "Lazio": 0.15, "Bologna": 0.15, "Sassuolo": 0.15, "Genoa": 0.15,
        "Udinese": 0.10, "Torino": 0.10, "Cagliari": 0.10, "Parma": 0.10,
        # Le neopromosse stanno in fondo d'ufficio: il loro attacco stimato viene dal
        # prior della Serie B, non da qualcosa che il modello abbia visto, e un
        # attaccante di neopromossa raramente costa piu' di uno di meta' classifica.
        "Lecce": 0.05, "Frosinone": 0.05, "Monza": 0.05, "Venezia": 0.05,
    },
}

# Prezzo attribuito a una squadra che non compare in tabella (nome nuovo, neopromossa
# mai vista). Volutamente basso: e' il caso "giocatore sconosciuto".
PREZZO_SCONOSCIUTO = 0.03

# Quota del budget destinata a ciascun reparto: e' il tetto sulla SOMMA dei prezzi
# del gruppo. Nelle pagine sono slider, questi sono i valori iniziali.
# A 0.15 in porta ci sta un big piu' un portiere da 5%, ma non due big.
# A 0.50 in attacco ci sta 30+15+5 oppure 20+20+10, ma non due giocatori da 30.
BUDGET = {"portieri": 0.15, "attaccanti": 0.50}
BUDGET_PORTIERI = BUDGET["portieri"]

# Bonus/malus del regolamento (classico: -1 per ogni gol subito, +1 se imbattuto).
# Sono entrambi configurabili perche' le leghe li cambiano: qualcuna usa -0.5 a gol,
# qualcuna non premia affatto l'imbattibilita'.
BONUS_IMBATTIBILITA = 1.0
MALUS_GOL = 1.0

# Bonus per gol segnato, usato dalla pagina degli attaccanti. Col regolamento
# classico un gol vale +3. Assist e voto restano fuori: il modello non li sa
# prevedere, e comunque non dipendono dal calendario.
BONUS_GOL = 3.0

# Correzione del calo dei gol in Serie A (1.43 a squadra nel 2021-22, 1.21 nel 2025-26).
# La media storica guarda all'indietro e quindi insegue il passato: nel backtest
# sovrastima i gol in 4 stagioni di prova su 4. Il fattore che azzera lo scarto
# complessivo e' 0.93 (per stagione: 0.87 / 0.97 / 0.98 / 0.91 -- sempre sotto 1, mai
# sopra). Lo spread e' ampio, quindi questo corregge il pregiudizio MEDIO, non
# l'errore di ogni singola stagione. Metti 1.0 per disattivarlo.
CORREZIONE_MU = 0.93

# Soglie dei colori, usate solo per colorare la griglia (NON entrano nel modello).
# Sono percentili sulla distribuzione delle forze, non valori assoluti.
PERCENTILE_VERDE = 0.70   # top 30% per forza complessiva
PERCENTILE_ROSSO = 0.30   # bottom 30%

# Normalizzazione dei nomi squadra: openfootball usa la ragione sociale
# ("FC Internazionale Milano"), Wikipedia il nome comune ("Inter"). Tutto il
# progetto lavora sulla forma canonica a destra.
ALIAS_SQUADRE = {
    # --- forme usate da openfootball/football.json (storico) ---
    "ac milan": "Milan",
    "ac monza": "Monza",
    "ac pisa 1909": "Pisa",
    "acf fiorentina": "Fiorentina",
    "as roma": "Roma",
    "atalanta bc": "Atalanta",
    "bologna fc 1909": "Bologna",
    "cagliari calcio": "Cagliari",
    "como 1907": "Como",
    "empoli fc": "Empoli",
    "fc internazionale milano": "Inter",
    "frosinone calcio": "Frosinone",
    "genoa cfc": "Genoa",
    "hellas verona fc": "Verona",
    "juventus fc": "Juventus",
    "parma calcio 1913": "Parma",
    "spezia calcio": "Spezia",
    "ss lazio": "Lazio",
    "ssc napoli": "Napoli",
    "torino fc": "Torino",
    "uc sampdoria": "Sampdoria",
    "udinese calcio": "Udinese",
    "us cremonese": "Cremonese",
    "us lecce": "Lecce",
    "us salernitana 1919": "Salernitana",
    "us sassuolo calcio": "Sassuolo",
    "venezia fc": "Venezia",
    # --- varianti comuni (Wikipedia, uso manuale) ---
    "internazionale": "Inter",
    "inter milan": "Inter",
    "juve": "Juventus",
    "hellas verona": "Verona",
    "verona hellas": "Verona",
    "us sassuolo": "Sassuolo",
    "sassuolo calcio": "Sassuolo",
    "salernitana 1919": "Salernitana",
    "pisa sc": "Pisa",
    "monza calcio": "Monza",
}


def normalizza_squadra(nome: str) -> str:
    """Riporta un nome squadra alla forma canonica usata ovunque nel progetto."""
    pulito = " ".join(nome.strip().split())
    return ALIAS_SQUADRE.get(pulito.casefold(), pulito)
