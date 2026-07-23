# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandi

```bash
python run.py --scarica --apri   # scarica dalle fonti, ricalcola, apre le pagine
python run.py                    # ricalcola dai CSV gia' presenti in data/
python controlla_fonti.py        # le fonti esterne rispondono ancora nel formato atteso?
python diagnosi_storico.py       # forma del dataset openfootball, stagione per stagione
python backtest.py               # le probabilita' sono calibrate? (scarica dalla rete)
python backtest_scelta.py        # la coppia di portieri consigliata fa piu' punti? (rete)
python backtest_attacco.py       # e il terzetto di attaccanti? (rete)
python calibra.py                # grid search sui parametri, ~1 min (scarica dalla rete)
python prova_coerenza.py         # Python e il JS della pagina danno la stessa classifica?
python prova_complementarita.py  # esperimento: big + provinciale conviene? (no)
```

**Dopo ogni modifica a `pairing.py` o al JS di `report.py`, lancia `prova_coerenza.py`.**
E' l'unico controllo che intercetta la divergenza fra le due implementazioni, e copre
entrambe le pagine (portieri e attaccanti) su 13 configurazioni ciascuna.

`run.py` produce **due** pagine dallo stesso motore: `classifica_portieri.html` e
`classifica_attaccanti.html`.

Non ci sono test automatici, ne' linter, ne' `requirements.txt`. La validazione e'
`controlla_fonti.py` (fonti vive e ben formate), `backtest.py` (le previsioni sono
oneste?) e `backtest_scelta.py` (il consiglio serve a qualcosa?). Gli script di
analisi sono esperimenti riproducibili, non utilita': ognuno risponde a una domanda
specifica documentata nel suo docstring.

## Vincoli del progetto

- **Solo libreria standard.** Nessun `pip install`, in nessun caso: la rete usa
  `urllib`, i dati `csv`/`json`, il grafico e' HTML+JS scritto a mano. Deve girare
  su un PC qualsiasi con Python e basta. (`unittest` e' stdlib: se un giorno servono
  test veri, non violano il vincolo.)
- **Codice e commenti in italiano**, accenti resi come apostrofo (`perche'`,
  `probabilita'`) nei sorgenti Python. Identificatori italiani (`forze`, `impegni`,
  `giornate`, `scarica_*`, `leggi_*`).
- `data/*.csv` e `classifica_portieri.html` sono **versionati di proposito** (vedi
  `.gitignore`): su un altro PC la pagina si apre e `python run.py` gira senza rete.
  `build/` invece e' derivato e ignorato.
- Serve **Python 3.10+**: il codice usa `X | None` e i generici built-in.

## Architettura

Pipeline lineare, con i due CSV come contratto fra scraping e calcolo:

```
fantaportieri/scrapers/ ──> data/storico.csv ────┐
                            data/calendario.csv ─┤
                            data/prezzi.csv ─────┴─> strength ─> scoring ─> pairing ─> report
                            (scritto a mano)                                   │
                                                        due pagine dallo stesso motore:
                                                        portieri e attaccanti
```

### Un motore, due ruoli

`Impegno` ha campi **neutri** (`gol_attesi`, `probabilita`): per un portiere
`probabilita` e' P(non subire gol), per un attaccante P(la squadra segni. Cambia
solo chi costruisce gli impegni -- `costruisci_impegni` o `costruisci_impegni_offensivi`
-- e `pairing` lavora su entrambi senza saperlo. **Non aggiungere una copia di
`pairing` per un nuovo ruolo**: e' il motivo per cui i campi hanno quei nomi.

`gol_attesi_segnati` non e' un modello nuovo, e' `gol_attesi_subiti` con i ruoli
scambiati: i gol che segno io sono quelli che incassa lui. Anche il fattore campo
si sistema da solo.

Tutto cio' che cambia fra le due pagine sta in `report.RUOLI`: titoli, etichette,
criteri offerti, soglia iniziale, e se i prezzi vanno mostrati. Il template HTML e
il JavaScript sono **gli stessi** per entrambe.

- `scrapers/calendario_wikipedia.py` — parsing del **wikitext** di it.wikipedia
  (non HTML), 38 giornate reali perche' dal 2021 il calendario e' asimmetrico.
  `valida()` impone la forma rigida della Serie A (380 partite, 20 squadre, 19+19
  casa/trasferta): se un controllo salta, `run.py --scarica` **non scrive i CSV** ed
  esce con errore, perche' un parsing sbagliato produrrebbe una classifica plausibile
  ma falsa.
- `scrapers/storico_openfootball.py` — `_risultato()` accetta **due** serializzazioni
  di `score` (`{"ht":…,"ft":…}` e la lista nuda usata solo per gli 0-0). Scartare la
  forma a lista sembra corretto ed e' l'errore: cancellerebbe tutti gli 0-0, cioe' le
  partite piu' preziose per un portiere. Il docstring riporta la prova; `diagnosi_storico.py`
  la rifa'. `scarica_giornate()` aggiunge il numero di giornata (da `round`), che serve
  a `backtest_scelta.py` per sapere quali partite cadono nello stesso turno.
- `data_io.py` — unico punto di lettura/scrittura CSV. Normalizza i nomi squadra in
  ingresso via `normalizza_squadra`, quindi il resto del codice vede solo la forma
  canonica ("Inter", non "FC Internazionale Milano"). `data/prezzi.csv` e' l'unico
  dei tre che **nessuno scraper produce**: i prezzi d'asta non esistono da nessuna
  parte prima del listone e comunque dipendono dalla lega. Se manca si usano i
  `PREZZI_DEFAULT` di `config.py`, cosi' il progetto gira lo stesso.
- `strength.py` — gol storici → `Forza(attacco, difesa)` relative alla media di lega,
  con decadimento esponenziale sulle stagioni e regressione verso un bersaglio per chi
  ha pochi dati. **Il bersaglio non e' sempre la media:** chi non compare nell'ultima
  stagione dello storico arriva dalla B e viene tirato verso `PRIOR_NEOPROMOSSA_*`
  (0.82/1.18), non verso 1.00. Senza questa distinzione una squadra retrocessa anni fa
  risulterebbe *forte* proprio perche' ha pochi dati. Una debuttante assoluta e' il caso
  limite (zero dati → forza esattamente uguale al prior), quindi non serve un ramo a parte.
  I parametri sono argomenti con default da `config.py`, cosi' `calibra.py` puo' variarli.
- `scoring.py` — Poisson: `mu × attacco_avv^1.2 × difesa_mia^0.9 × fattore_campo`,
  poi `P(clean sheet) = e^(−λ)`. Il fattore campo si applica a **chi segna**, cioe'
  all'avversario (gioco in casa → lui e' in trasferta → `FATTORE_TRASFERTA`).
- `pairing.py` — ogni giornata il gruppo vale `max(P_A, P_B, …)`. Sei criteri in
  `CRITERI`: `guadagno` misura la complementarita' rispetto al tenere sempre il
  migliore, `punti` i bonus/malus di chi schieri, `totale` quelli di **tutto** il
  gruppo (per gli attaccanti, che giocano insieme), `efficienza` la resa per credito.
  `efficienza` divide la **probabilita'** e non i punti: `punti_totali` esclude il
  voto base, quindi per i portieri e' negativo con uno zero arbitrario, e dividere
  un numero negativo per il prezzo premierebbe i piu' cari — l'opposto di cio' che
  serve. Il budget e' un tetto sulla SOMMA dei prezzi (`prezzo_gruppo`), con
  tolleranza 1e-9 perche' `0.10 + 0.05` in binario fa `0.15000000000000002`.
  `obbligatoria=` tiene solo i gruppi che contengono una squadra data — e' la domanda
  "quel portiere l'ho gia' preso, adesso chi ci abbino?".
- `report.py` — pagina HTML autonoma. `scrivi_html` produce il documento completo,
  `scrivi_frammento` ne estrae `<style>` + contenuto di `<body>` per la pubblicazione
  come Artifact (l'host avvolge da solo il file).

`models.py` contiene tutte le dataclass frozen condivise; `config.py` contiene **tutti**
i parametri calibrabili piu' la tabella `ALIAS_SQUADRE`.

### Attenzione: la logica di pairing esiste due volte

`report.py` incorpora i dati come JSON e **ricalcola tutto nel browser** (slider soglia,
finestra di giornate, coppie/triple, squadra gia' presa), quindi il template `_PAGINA`
contiene una riscrittura in JS di `pairing._valuta`/`classifica` (`valuta()`,
`combinazioni()`, `classifica()` intorno a report.py:465-545). Ogni modifica alla
semantica del punteggio o dell'ordinamento va applicata **in entrambi i posti**,
altrimenti terminale e pagina divergono in silenzio.

`prova_coerenza.py` confronta **l'ordine della classifica e le scelte giornata per
giornata**, su 11 configurazioni. Le scelte non sono un extra: quando due squadre della
stessa coppia risultano in pari il punteggio della coppia e' identico comunque, quindi
la classifica coincide e il solo confronto sull'ordine passa mentre i due lati
consigliano portieri diversi. E' esattamente cosi' che era sopravvissuto il difetto
descritto qui sotto.

### La precisione del JSON non e' cosmetica

`costruisci_dati` serializza `pcs` e `pnt` a **sei** decimali. A quattro, 69 partite su
760 finivano su un valore duplicato e la pagina schierava un portiere diverso dal
terminale su coppie che il modello distingue benissimo: Inter 0.341552 e Juventus
0.341578 diventavano entrambe 0.3416, e il browser — che a parita' tiene il primo in
ordine alfabetico — mandava in campo l'Inter dove Python mandava la Juventus. Il divario
piu' stretto fra due valori distinti e' 1.2e-06, quindi sei decimali bastano e cinque no.
Non abbassarli per far dimagrire il file: costano 5 KB e comprano la coerenza.

`pairing._valuta` usa `max(candidati, key=lambda c: c[0])`, non `max(candidati)`: senza
`key` il confronto fra tuple scivolerebbe sul nome e a parita' vera vincerebbe l'ultimo
in ordine alfabetico, mentre il JS tiene il primo. `Combo.pari` registra le giornate in
pari merito e la pagina le mostra come "Inter / Juventus — pari merito" invece di
fingere una preferenza.

### Due decisioni che sembrano dettagli e non lo sono

**La tabella delle squadre si ordina per DIFESA, non per `attacco/difesa`.** Prima
`forza_complessiva` era `attacco / difesa` e metteva l'Inter prima di tutti con un
margine enorme — ma quel margine era l'attacco 1.63, che a un portiere non serve a
niente. Per difesa Inter e Juventus sono identiche (0.75) e la Juventus ha piu'
giornate facili: la pagina mostrava quindi una classifica di forza che il modello
della pagina stessa non usava. Ora `scoring.solidita` e' `1 / difesa`, e per gli
attaccanti l'ordinamento passa all'attacco. L'attacco resta in tabella, ma etichettato
per quello che e': la proprieta' che conta quando quella squadra ce l'hai CONTRO.

**Per gli attaccanti la copertura non funziona, e non e' una taratura sbagliata.**
E' il criterio naturale per i portieri e sembra doverlo essere anche qui, ma si rompe
da due lati opposti: sotto il 78% quasi tutti i terzetti coprono 38/38 e la classifica
non ordina; sopra l'85% ordina una cosa sola, cioe' se hai preso l'Inter — che supera
quella soglia in **27 partite su 38** mentre la seconda squadra (Atalanta) ci arriva
5 volte e il Napoli 2. Non esiste una soglia che vada bene: `SOGLIA_ATTACCO = 0.80` e'
il punto meno peggio (17 valori distinti di copertura), non un valore buono.

La conseguenza sta nel criterio, non nella soglia: la pagina attaccanti parte ordinata
per **`totale`**, che somma i gol attesi di tutti e tre. E' anche quello giusto nel
merito, perche' gli attaccanti scendono in campo insieme e non a turno. Se un giorno
aggiungi un ruolo, chiediti prima se `max(...)` descriva davvero come lo schieri.

### La correzione del calo dei gol

I gol in Serie A calano da anni (1.43 → 1.21 per squadra a partita dal 2021-22 al
2025-26) e `media_gol_lega` e' una media all'indietro: il modello grezzo sovrastimava
i gol in **4 stagioni di prova su 4**. `CORREZIONE_MU = 0.93` lo compensa e funziona
(scarto da +0.12 a +0.03 a partita, fasce 25-40% rientrate entro 2 punti), ma il
fattore e' stato **ricavato dalle stesse quattro stagioni su cui e' verificato**:
e' un fit, non una validazione fuori campione. L'ottimo per stagione va da 0.87 a
0.98, quindi corregge il ritardo medio, non quello di ogni annata. Mettere 1.0
disattiva tutto e restituisce il modello grezzo.

### Il riferimento che conta e' "banale", non "a caso"

Entrambi i backtest del prodotto confrontano la scelta del modello con **la regola
banale**: per i portieri "le due difese meno battute l'anno scorso", per gli attaccanti
"i tre attacchi piu' prolifici l'anno scorso". Zero modello, solo memoria.

E' l'unico confronto che dica qualcosa. Battere il caso di +9 punti sembra molto ma non
lo e': quasi tutto quel margine sta nel non comprare a caso, cosa che nessuno fa. Contro
la memoria il modello vale **+2.5 punti a stagione per i portieri e zero per gli
attaccanti** (in due stagioni su quattro sceglie lo stesso identico terzetto).

Il motivo e' strutturale: su 38 giornate ognuno incontra tutti in casa e fuori, quindi
le differenze di calendario si annullano. Il segnale esiste nelle **finestre corte** --
sulle prime 10 giornate il vantaggio sale a +3.5 punti, cinque volte tanto per giornata.
Lo slider della finestra e' quindi il controllo piu' importante della pagina, non un
accessorio. Se aggiungi criteri o metriche, misurale su una finestra corta: sull'intera
stagione qualunque cosa sembra funzionare perche' tutto converge su "prendi i forti".

Quattro stagioni sono poche: sono direzioni, non misure.

### Le due domande del backtest

`backtest.py` chiede se le **previsioni** sono oneste (Brier, calibrazione per fasce,
scarto sui gol). `backtest_scelta.py` chiede se il **consiglio** serve: prende la coppia
in cima alla classifica e conta i fantapunti che ha davvero fatto, contro tre riferimenti
(portiere singolo, media di tutte le 190 coppie, tetto col senno di poi). Sono domande
indipendenti — un modello calibrato puo' consigliare coppie mediocri.

`backtest.py` **importa** `scoring.gol_attesi_subiti` invece di riscriverlo. Ne teneva
una copia: cosi' una modifica al modello lasciava il backtest a validare la versione
vecchia e a dichiararla buona. Non reintrodurre copie del modello negli script di
validazione, per nessun motivo.

### Modifiche tipiche

- Calibrare il modello → solo `config.py`, poi `python run.py` e `python backtest.py`.
  `calibra.py` dice che i valori attuali sono gia' ottimi (15esimi su 1600, con lo 0.02%
  di scarto dal primo): non cambiarli inseguendo la quarta cifra decimale.
- Nuova stagione → cambia **solo** `STAGIONE_CORRENTE`. `STAGIONI_STORICHE` e' derivata
  da li' apposta: tenendo due liste indipendenti bastava aggiornarne una per far
  risultare mezzo campionato promosso dalla B, in silenzio.
- Nuova squadra o nome che non combacia → aggiungere a `ALIAS_SQUADRE`, non toccare i parser.
- Prezzi d'asta cambiati o uscito il listone → `data/prezzi.csv`, non `config.py`.
  Colonne `squadra,portiere,attaccante`: due mercati diversi, e le gerarchie non
  coincidono (la Fiorentina e' terza fascia in attacco e sesta in porta). Sono quote
  del budget (0.10 = 10%), non crediti, cosi' la tabella vale per una lega da 500 e
  per una da 1000. I tetti per reparto stanno in `BUDGET` (15% in porta, 50% in attacco).
- Una fonte cambia formato → `controlla_fonti.py` lo dice; i CSV restano correggibili a mano.
- I colori del semaforo (`PERCENTILE_VERDE`/`ROSSO`) sono **solo resa grafica**, non entrano
  nel modello. Il verde e' spostato verso l'acqua `#1baf7a` per distinguibilita' deuteranope:
  non riportarlo al verde puro.
