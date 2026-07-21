# Fanta-GKeeper — goalkeeper pairings

Ranks the best pairs (and triples) of Serie A goalkeepers for fantasy football, based
on how easy their fixture list is. Standard library only: no `pip install`.

```bash
python run.py --scarica --apri   # download data, compute, open the page
python run.py                    # recompute from the CSVs already on disk
```

The output is `classifica_portieri.html`: a self-contained page that opens with a
double click and works offline, with sliders for the threshold and matchday window and
dropdowns for the budget caps.

## The question it answers

If you own two goalkeepers, every matchday you field whichever one has the easier
fixture. A pair is therefore worth more than the sum of its parts — but only if the
two teams are **complementary**, with their hard fixtures falling on different weeks.

## How it works

1. **Team strength** — from five seasons of goals (2021-22 → 2025-26) each team gets
   two numbers relative to the league average: *attack* (how much it scores) and
   *defence* (how much it concedes, lower = more solid). Recent seasons weigh far more
   (0.65 decay per year), and teams with little data are pulled toward a target. That
   target is not always the league average: a side that does not appear in the most
   recent season is coming up from Serie B, so it is pulled toward the promoted-team
   prior instead. Without that distinction a team relegated years ago would come out
   *strong* precisely because it has little data.
2. **Fixture difficulty** — Poisson model:
   `expected goals conceded = league_mean × opponent_attack^1.2 × own_defence^0.9 × home_factor`
   and therefore `P(clean sheet) = e^(−expected goals)`. The higher exponent on the
   opponent's attack is deliberate: who you face matters more than how solid you are.
   Note the home factor applies to whoever is *scoring*, i.e. the opponent — if you
   play at home, they are away and score slightly less. The league mean is scaled by
   `CORREZIONE_MU` because scoring keeps falling and a backward-looking average lags.
3. **Pairing** — each matchday you field the better of the two, so a pair is worth
   `max(P_A, P_B)`, summed over every matchday. Which goalkeeper to field is the same
   under either metric: both clean-sheet probability and expected points fall as
   expected goals rise.

The green/yellow/red colours **are not part of the model**: they are only a rendering
of the estimated numbers.

## The four metrics, and why none is enough on its own

| Metric | What it rewards | Winner (unconstrained) |
|---|---|---|
| **Coverage** | matchdays above the "easy" threshold | Juventus + Roma (79%) |
| **Average** | mean quality of the fixture actually played | the big clubs |
| **Points** | expected bonus/malus under classic rules | Inter + Roma (−13.0) |
| **Gain** | how much alternating beats just keeping the better one | Genoa + Udinese (+6.7) |

*Points* is expected fantasy scoring: `−λ + e^(−λ)`, i.e. −1 per goal conceded plus 1
for a clean sheet. The base vote is excluded because the model cannot predict it, so
the total is negative — what matters is the comparison between pairs, not the sign.

Coverage and points genuinely disagree, which is why both exist: coverage counts
matchdays over the line and ignores how far over, while points distinguish conceding
one from conceding four. Under the budget constraint below, coverage picks
Bologna + Juventus while points pick Bologna + Inter.

## The budget constraint

Without a cost constraint the ranking is useless at an auction: **all ten best pairs
are made of expensive teams**, which just says "buy the goalkeepers of the strong
clubs". Real auction budgets do not allow that.

Since a price list is not available yet, cost is modelled as a **cap on the number of
expensive goalkeepers** rather than invented credit values. Teams are split into two
hand-estimated tiers in `config.py` — `FASCIA_ALTISSIMA` (Napoli, Roma, Inter, Milan)
and `FASCIA_ALTA` (Juventus, Como, Atalanta) — and `MAX_ALTISSIMA` / `MAX_COSTOSI` cap
how many of each a combination may contain. Both are dropdowns on the page.

This turns the output into the question an auction actually poses: *if I splash out on
one goalkeeper, who is the best partner?* With the default caps the answer is
Bologna + Juventus (76% coverage) rather than an all-star pair you could never afford.

**Counterintuitive finding:** the idea that a mid-table goalkeeper with a good fixture
list can alternate with a top-six one does not survive contact with the data. Inter +
Sassuolo gains only +0.9 points, and Sassuolo is the better pick on 5 matchdays out of
38. The reason: "easy fixture" is not a property of the fixture but of the team-fixture
pair — Sassuolo concedes anyway, even against Genoa. See `prova_complementarita.py`.

## Data sources

| Data | Source | Why |
|---|---|---|
| 2026-27 fixtures | `it.wikipedia.org` wikitext, via the official MediaWiki API | all 38 matchdays, stable text, public API |
| 2021-2026 results | `openfootball/football.json` (GitHub) | match-by-match results, no key needed |

`legaseriea.it` was rejected: it is a Next.js app that loads statistics through a
client-side Server Action, so there is nothing in the HTML, and the public APIs found
online return 404 (the site was rebuilt). It would need a headless browser, fragile to
every restyle. `diretta.it` only embeds the first 12 matchdays; the rest travels over a
signed, undocumented Flashscore feed.

The fixture list has been **asymmetric** since 2021 (the second half is not a mirror of
the first), so all 38 matchdays are genuinely parsed rather than mirrored.

## Structure

```
run.py                     main command
backtest.py                does the model actually work? walk-forward validation
calibra.py                 which parameters predict best? grid search
prova_coerenza.py          do Python and the in-page JavaScript still agree?
controlla_fonti.py         are the sources still up, and in the expected format?
diagnosi_storico.py        which seasons can be trusted
prova_complementarita.py   does big + mid-table alternate well? (no)
data/storico.csv           season,team,matches,goals_for,goals_against
data/calendario.csv        matchday,home,away
fantaportieri/
  config.py                EVERY tunable parameter lives here
  strength.py              historical goals -> team strength
  scoring.py               strength -> P(clean sheet) per fixture
  pairing.py               ranks pairs/triples
  report.py                HTML page
  scrapers/                fixtures (Wikipedia) + results (openfootball)
```

The two CSVs are the contract between scraping and computation: they can be fixed by
hand and everything else still works. They are committed on purpose, so on another
machine the page opens and `python run.py` runs without network access.

Note that `report.py` embeds the data as JSON and **recomputes everything in the
browser** (threshold slider, matchday window, budget caps, pairs/triples). The ranking
logic therefore exists twice, in Python and in JavaScript: a change to the scoring or
ordering semantics must be applied in both places. `python prova_coerenza.py` mirrors
the JavaScript and diffs it against `pairing.py` across eight configurations, so the
divergence gets caught instead of going unnoticed.

## Tuning

Everything in `fantaportieri/config.py`:

- `DECADIMENTO_STAGIONI` (0.65) — how much the past counts
- `PESO_REGRESSIONE_MEDIA` (0.5) — how hard teams with little data are pulled to the target
- `ESP_ATTACCO_AVVERSARIO` / `ESP_DIFESA_MIA` (1.20 / 0.90) — which side weighs more
- `FATTORE_CASA` / `FATTORE_TRASFERTA` (1.08 / 0.93) — deliberately mild
- `PRIOR_NEOPROMOSSA_*` (0.82 / 1.18) — the target for teams coming up from Serie B
- `CORREZIONE_MU` (0.93) — corrects the falling-scoring bias, see below
- `FASCIA_ALTISSIMA` / `FASCIA_ALTA` — the hand-estimated price tiers
- `MAX_ALTISSIMA` / `MAX_COSTOSI` (1 / 1) — the budget caps, dropdowns on the page
- `BONUS_IMBATTIBILITA` (1.0) — the clean-sheet bonus in your league's rules
- `SOGLIA_FACILE` (0.40) — a slider on the page

`python calibra.py` tries 1600 combinations under the same walk-forward validation as
the backtest. **Result: there is nothing to change.** The hand-picked values rank 15th
out of 1600, and the best beats them by 0.02% — noise. The promoted-team prior is real
signal, though: 0.82/1.18 wins clearly, and pulling toward the league average
(1.00/1.00) is the worst of the five options tried.

## Known limits

- **The falling-scoring correction is fitted, not validated.** Serie A scoring has been
  dropping for years (1.43 goals per team per match in 2021-22, 1.21 in 2025-26), and a
  backward-looking league mean always lags: the raw model overestimated goals in 4 test
  seasons out of 4. `CORREZIONE_MU = 0.93` removes that, and it works — the goal bias
  falls from +0.12 to +0.03 per match, and the 25-40% probability bands, previously off
  by 5-8 points, now land within 2. But 0.93 was derived from those same four seasons,
  so the improvement is a fit rather than an out-of-sample result. The per-season
  optimum ranges from 0.87 to 0.98, so a single factor corrects the average lag, not
  each season's.
- 2024-25 has 370/380 matches in the dataset (the 38th matchday is missing). It removes
  one match from each of the 20 teams, so it does not distort the averages.
- The model ignores injuries, suspensions, rotation and transfers: it is fixtures only.
- It assumes you always field the right goalkeeper, so it measures a pair's potential,
  not what you will actually get.

## Accessibility

The traffic-light scale uses teal `#1baf7a` instead of pure green: full green and red
sit ΔE 4.1 apart under deuteranopia (indistinguishable for roughly one man in twelve),
while teal reaches 9.9 and clears the target while still reading as a traffic light.
Colour never carries the data alone — every cell has a tooltip with the exact numbers,
the ranking has numeric columns, and the legend is labelled.

## Licence

The code is released under the MIT licence — see `LICENSE`.

The data in `data/` is derived from two sources with their own terms:

- `storico.csv` comes from [openfootball/football.json](https://github.com/openfootball/football.json),
  dedicated to the public domain under **CC0-1.0**.
- `calendario.csv` is extracted from Italian Wikipedia, whose text is licensed
  **CC BY-SA 4.0**. What is extracted here is factual fixture data (which teams meet on
  which matchday) rather than prose.
