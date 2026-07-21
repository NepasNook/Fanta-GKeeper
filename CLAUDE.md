# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandi

```bash
python run.py --scarica --apri   # scarica dalle fonti, ricalcola, apre la pagina
python run.py                    # ricalcola dai CSV gia' presenti in data/
python controlla_fonti.py        # le fonti esterne rispondono ancora nel formato atteso?
python diagnosi_storico.py       # forma del dataset openfootball, stagione per stagione
python backtest.py               # validazione walk-forward del modello (scarica dalla rete)
python calibra.py                # grid search sui parametri, ~1 min (scarica dalla rete)
python prova_coerenza.py         # Python e il JS della pagina danno la stessa classifica?
python prova_complementarita.py  # esperimento: big + provinciale conviene? (no)
```

**Dopo ogni modifica a `pairing.py` o al JS di `report.py`, lancia `prova_coerenza.py`.**
E' l'unico controllo che intercetta la divergenza fra le due implementazioni.

Non ci sono test automatici, ne' linter, ne' `requirements.txt`. La validazione e'
`controlla_fonti.py` (fonti vive e ben formate) e `backtest.py` (il modello batte la
previsione banale?). I quattro script di analisi sono esperimenti riproducibili, non
utilita': ognuno risponde a una domanda specifica documentata nel suo docstring.

## Vincoli del progetto

- **Solo libreria standard.** Nessun `pip install`, in nessun caso: la rete usa
  `urllib`, i dati `csv`/`json`, il grafico e' HTML+JS scritto a mano. Deve girare
  su un PC qualsiasi con Python e basta.
- **Codice e commenti in italiano**, accenti resi come apostrofo (`perche'`,
  `probabilita'`) nei sorgenti Python. Identificatori italiani (`forze`, `impegni`,
  `giornate`, `scarica_*`, `leggi_*`).
- `data/*.csv` e `classifica_portieri.html` sono **versionati di proposito** (vedi
  `.gitignore`): su un altro PC la pagina si apre e `python run.py` gira senza rete.
  `build/` invece e' derivato e ignorato.

## Architettura

Pipeline lineare, con i due CSV come contratto fra scraping e calcolo:

```
scrapers/ ──> data/storico.csv ────┐
              data/calendario.csv ─┴─> strength ─> scoring ─> pairing ─> report
```

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
  la rifa'.
- `data_io.py` — unico punto di lettura/scrittura CSV. Normalizza i nomi squadra in
  ingresso via `normalizza_squadra`, quindi il resto del codice vede solo la forma
  canonica ("Inter", non "FC Internazionale Milano").
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
- `pairing.py` — ogni giornata la coppia vale `max(P_A, P_B)`. Quattro criteri in
  `CRITERI` (copertura / media / guadagno / punti); `guadagno` misura la complementarita'
  rispetto al tenere sempre il migliore del gruppo, `punti` i bonus/malus attesi col
  regolamento classico. `_ammessa` applica il budget come tetto sul NUMERO di portieri
  cari per fascia: senza quel vincolo le prime dieci coppie sono tutte di squadre care,
  che all'asta non serve a niente.
- `report.py` — pagina HTML autonoma. `scrivi_html` produce il documento completo,
  `scrivi_frammento` ne estrae `<style>` + contenuto di `<body>` per la pubblicazione
  come Artifact (l'host avvolge da solo il file).

`models.py` contiene tutte le dataclass frozen condivise; `config.py` contiene **tutti**
i parametri calibrabili piu' la tabella `ALIAS_SQUADRE`.

### Attenzione: la logica di pairing esiste due volte

`report.py` incorpora i dati come JSON e **ricalcola tutto nel browser** (slider soglia,
finestra di giornate, coppie/triple), quindi il template `_PAGINA` contiene una
riscrittura in JS di `pairing._valuta`/`classifica` (`valuta()`, `combinazioni()`,
`classifica()` intorno a report.py:421-480). Ogni modifica alla semantica del punteggio
o dell'ordinamento va applicata **in entrambi i posti**, altrimenti terminale e pagina
divergono in silenzio.

### La correzione del calo dei gol

I gol in Serie A calano da anni (1.43 → 1.21 per squadra a partita dal 2021-22 al
2025-26) e `media_gol_lega` e' una media all'indietro: il modello grezzo sovrastimava
i gol in **4 stagioni di prova su 4**. `CORREZIONE_MU = 0.93` lo compensa e funziona
(scarto da +0.12 a +0.03 a partita, fasce 25-40% rientrate entro 2 punti), ma il
fattore e' stato **ricavato dalle stesse quattro stagioni su cui e' verificato**:
e' un fit, non una validazione fuori campione. L'ottimo per stagione va da 0.87 a
0.98, quindi corregge il ritardo medio, non quello di ogni annata. Mettere 1.0
disattiva tutto e restituisce il modello grezzo.

### Modifiche tipiche

- Calibrare il modello → solo `config.py`, poi `python run.py` e `python backtest.py`.
  `calibra.py` dice che i valori attuali sono gia' ottimi (15esimi su 1600, con lo 0.02%
  di scarto dal primo): non cambiarli inseguendo la quarta cifra decimale.
- Nuova squadra o nome che non combacia → aggiungere a `ALIAS_SQUADRE`, non toccare i parser.
- Una fonte cambia formato → `controlla_fonti.py` lo dice; i CSV restano correggibili a mano.
- I colori del semaforo (`PERCENTILE_VERDE`/`ROSSO`) sono **solo resa grafica**, non entrano
  nel modello. Il verde e' spostato verso l'acqua `#1baf7a` per distinguibilita' deuteranope:
  non riportarlo al verde puro.
