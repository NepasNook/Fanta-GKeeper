"""Parametri del modello. E' il file da toccare per calibrare."""

STAGIONE_CORRENTE = "2026-27"

# Stagioni storiche usate per stimare la forza delle squadre.
# La piu' recente per prima nel peso, non nell'ordine: l'ordine lo calcola il codice.
STAGIONI_STORICHE = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

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

# Fasce di prezzo, stimate a mano in attesa del listone. Sono TUTTE squadre care:
# la distinzione e' fra "carissimo" e "caro", non fra caro ed economico.
FASCIA_ALTISSIMA = {"Napoli", "Roma", "Inter", "Milan"}
FASCIA_ALTA = {"Juventus", "Como", "Atalanta"}
SQUADRE_COSTOSE = FASCIA_ALTISSIMA | FASCIA_ALTA

# Vincolo di spesa senza prezzi: quanti portieri cari ti puoi permettere.
# Traduce la domanda vera dell'asta -- "se mi sveno su uno, qual e' il miglior
# compagno?" -- senza dover inventare un listino che non esiste ancora.
# Nella pagina HTML sono due menu a tendina, questi sono i valori iniziali.
MAX_ALTISSIMA = 1
MAX_COSTOSI = 1

# Bonus di imbattibilita' del regolamento (classico: -1 per ogni gol, +1 se imbattuto).
# Il malus per gol e' implicito nel modello: i gol attesi sono lambda.
BONUS_IMBATTIBILITA = 1.0

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
