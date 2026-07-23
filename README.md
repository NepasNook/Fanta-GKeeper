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

The team table is ranked by **defensive solidity** (`1 / defence`), not by overall
strength. `attack / defence` used to put Inter far ahead of everyone — but that gap was
its 1.63 attack, which is worth nothing to a goalkeeper. By defence Inter and Juventus
are identical (0.75), and Juventus in fact has more easy matchdays. Attack is still
shown, labelled as what it actually is here: what makes that team dangerous when you
*face* it. On the attackers page the ordering flips to attack, for the same reason.

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

Prices live in `data/prezzi.csv` (`team,goalkeeper,attacker`) as a **share of the total
budget** (0.10 = 10%), not credits, so the same table works for a 500-credit league and
a 1000-credit one. A combination is allowed when the sum of its prices fits under the
department cap in `BUDGET` — 15% for goalkeepers, 50% for attackers — a slider on each
page.

Prices do **not** follow team strength, and that is the point: Lecce is 15th for
defensive solidity but its goalkeeper costs as much as Fiorentina's, which is 10th,
because the price is set by the team *and* by who keeps goal. That is why the table
cannot be derived from the model and is maintained by hand. It is the only one of the
three CSVs no scraper produces; if it is missing, the defaults in `config.py` are used.

This turns the output into the question an auction actually poses: *with the credits I
have, which pair is best?* At 15% the answer is Bologna + Juventus (76% coverage, 14%
spent) rather than an all-star pair you could never afford.

## Attackers

`run.py` also produces `classifica_attaccanti.html` from the **same engine**. Expected
goals scored is the same model seen from the other side — the goals I score are the
goals you concede — so `gol_attesi_segnati` is `gol_attesi_subiti` with the roles
swapped, and `Impegno` carries deliberately neutral field names so `pairing.py` works
for both without a second copy.

Prices are a **separate column** in `data/prezzi.csv`, because these are two different
markets: an Inter attacker costs three times its goalkeeper, and the pecking orders do
not even match — Fiorentina is third tier in attack and sixth in goal. The budget cap
is 50% of the total, which allows 30+15+5 or 20+20+10 but not two 30% players.

**Coverage does not work for attackers, and that is a finding, not a bad setting.** It
is the natural metric for goalkeepers and looks like it should transfer, but it breaks
from both ends: below 78% nearly every trio covers all 38 matchdays and nothing is
ranked, while above 85% the only thing being ranked is whether you own Inter — which
clears that bar in **27 matches out of 38**, against 5 for the next-best attack
(Atalanta) and 2 for Napoli. No threshold works. The page therefore opens sorted by
**`totale`**, the sum of expected goals across all three, which is also the honest
metric: attackers take the field together, not in rotation.

This is the attacking twin of the goalkeeper result above — the appealing idea that you
can weave complementary calendars together does not survive contact with the data in
either department.

### Does the attackers page work? Measured, and mostly no

`backtest_attacco.py` runs the same walk-forward test. The result is blunt:

| Criterion | Avg. finish (of 1140) | Percentile | vs. random | **vs. naive** |
|---|---|---|---|---|
| Coverage | 11.8 | 99% | +192 | **+10** |
| Total | 25.2 | 98% | +174 | **−8** |
| Average | 25.2 | 98% | +174 | **−8** |
| Points | 25.2 | 98% | +174 | **−8** |
| Gain | 850.8 | 25% | −61 | **−243** |

Against random the model looks superb — 98th percentile. Against *naive* ("buy the three
teams that scored most last season") it is **worth nothing**: in two test seasons out of
four it picked the identical trio, and the four-season average is a rounding error either
way. Over a full season the calendar cancels out, and what is left is "the best attacks
score the most", which you did not need a model to know.

So: use the page with the **matchday window narrowed** — that is where the goalkeeper
test showed the fixture signal actually lives — and treat the full-season ranking as
confirmation of the obvious. *Gain* is again the worst possible criterion.

### How much of a team's goals reaches the striker you buy?

The page estimates goals for a *team*, but you buy a *player*, and a team fields three or
four attackers, wingers included. Part 2 of `backtest_attacco.py` measures the gap, using
Wikipedia's scorer lists across five seasons (58 team-seasons):

**The top scorer takes 25% of his team's goals on average, ranging from 16% to 42%** —
standard deviation 6 points. The per-season averages are stable (22-27%), so the link is
real, but on a team scoring 60 goals its best striker takes anywhere between 10 and 25 of
them. Team quality moves the needle; who you actually buy moves it just as much.

Note this is measured with hindsight: in August nobody knew who the top scorer would be,
and the 2026-27 players are not the 2025-26 ones. It is an upper bound on how much of the
team signal can transfer to an individual, not a prediction.

One limit that no setting can fix: **it ranks teams, not scorers.** Knowing Napoli
expects 1.8 goals says nothing about whether Lukaku or McTominay gets them. openfootball
carries no player data at all, and Wikipedia lists only ~19 scorers a season (everyone
above 10 goals, covering 12-13 of the 20 clubs) — enough for the elite strikers, useless
for the cheap one you actually need advice on. A true player-level model needs a source
this project does not have.

**Counterintuitive finding:** the idea that a mid-table goalkeeper with a good fixture
list can alternate with a top-six one does not survive contact with the data. Inter +
Sassuolo gains only +0.9 points, and Sassuolo is the better pick on 5 matchdays out of
38. The reason: "easy fixture" is not a property of the fixture but of the team-fixture
pair — Sassuolo concedes anyway, even against Genoa. See `prova_complementarita.py`.

## Does the advice actually work?

`backtest.py` asks whether the *probabilities* are honest. `backtest_scelta.py` asks
whether the *recommendation* is worth anything, which is a different question — a
perfectly calibrated model can still recommend mediocre pairs. For each test season it
trains only on earlier seasons, takes the pair at the top of the ranking, and counts the
fantasy points that pair really scored, fielding whichever goalkeeper the model would
have chosen at the time.

Averaged over four test seasons (2022-23 → 2025-26), unconstrained pairs:

| Criterion | Avg. finish (of 190) | Percentile | vs. random | vs. best single | **vs. naive** |
|---|---|---|---|---|---|
| Points | 46.5 | 76% | +9.2 | +5.2 | **+2.5** |
| Average | 46.5 | 76% | +9.2 | +5.2 | **+2.5** |
| Coverage | 50.5 | 74% | +7.4 | +3.5 | **+0.8** |
| Gain | 68.0 | 65% | +5.4 | +1.5 | **−1.2** |

The last column is the one that matters, and it is the one most tools never show.
*Naive* means "buy the two teams that conceded fewest last season" — no model at all,
just memory. Beating random by +9 sounds impressive; beating memory by **+2.5 points a
season** is the honest measure of what the Poisson model, the decay, the home factor
and the promoted-team prior are actually worth. It is positive, it is small, and it is
**not every year**: in 2022-23 the best single goalkeeper (Napoli, −10.0) crushed the
recommended pair (−22.0) by 12 points.

*Gain* finishing last — and actually losing to memory — confirms from a second direction
what `prova_complementarita.py` already found: chasing complementarity is a trap.

**Where the edge actually lives: short windows.** Over 38 matchdays everyone plays
everyone home and away, so calendar differences cancel out almost entirely. Restricting
the same test to the opening stretch:

| Window | Model | Naive | Edge |
|---|---|---|---|
| Matchdays 1-5 | −0.5 | −1.2 | +0.8 |
| **Matchdays 1-10** | **−2.8** | **−6.2** | **+3.5** |
| Matchdays 1-19 | −8.5 | −10.2 | +1.8 |
| Matchdays 1-38 | −16.8 | −19.2 | +2.5 |

The edge over ten matchdays is larger in absolute terms than over the whole season, and
about five times larger per matchday. That makes the **matchday-window slider the most
valuable control on the page**, not a decoration. Four seasons is a small sample, so read
this as a direction rather than a measurement.

No budget cap is applied in these tests: the price tiers are for 2026-27 and applying
them to 2022 would be an anachronism.

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
backtest.py                are the probabilities honest? walk-forward calibration
backtest_scelta.py         does the recommended pair actually score more?
calibra.py                 which parameters predict best? grid search
prova_coerenza.py          do Python and the in-page JavaScript still agree?
controlla_fonti.py         are the sources still up, and in the expected format?
diagnosi_storico.py        which seasons can be trusted
prova_complementarita.py   does big + mid-table alternate well? (no)
data/storico.csv           season,team,matches,goals_for,goals_against
data/calendario.csv        matchday,home,away
data/prezzi.csv            team,goalkeeper,attacker  <- hand-written, no scraper
fantaportieri/
  config.py                EVERY tunable parameter lives here
  strength.py              historical goals -> team strength
  scoring.py               strength -> P(clean sheet) / P(scores) per fixture
  pairing.py               ranks pairs/triples, for either role
  report.py                HTML page, one template for both roles
  scrapers/                fixtures (Wikipedia) + results (openfootball)
```

The two CSVs are the contract between scraping and computation: they can be fixed by
hand and everything else still works. They are committed on purpose, so on another
machine the page opens and `python run.py` runs without network access.

Note that `report.py` embeds the data as JSON and **recomputes everything in the
browser** (threshold slider, matchday window, budget caps, pairs/triples, pinned team).
The ranking logic therefore exists twice, in Python and in JavaScript: a change to the
scoring or ordering semantics must be applied in both places. `python prova_coerenza.py`
mirrors the JavaScript and diffs it against `pairing.py` across eleven configurations,
comparing both the ranking order **and the goalkeeper picked on each matchday**.

The second half of that check is not decoration. When two teams in the same pair come
out equal, the pair scores the same either way, so the ranking matches while the two
sides field different goalkeepers — which is exactly how a real bug survived: `pcs` was
serialised to 4 decimals, 69 fixtures out of 760 collapsed onto a duplicate value, and
the page fielded Inter (0.341552) where the terminal fielded Juventus (0.341578). The
JSON now carries 6 decimals; the tightest genuine gap is 1.2e-06, so 6 are needed and 5
are not enough.

## Tuning

Everything in `fantaportieri/config.py`:

- `DECADIMENTO_STAGIONI` (0.65) — how much the past counts
- `PESO_REGRESSIONE_MEDIA` (0.5) — how hard teams with little data are pulled to the target
- `ESP_ATTACCO_AVVERSARIO` / `ESP_DIFESA_MIA` (1.20 / 0.90) — which side weighs more
- `FATTORE_CASA` / `FATTORE_TRASFERTA` (1.08 / 0.93) — deliberately mild
- `PRIOR_NEOPROMOSSA_*` (0.82 / 1.18) — the target for teams coming up from Serie B
- `CORREZIONE_MU` (0.93) — corrects the falling-scoring bias, see below
- `FASCIA_ALTISSIMA` / `FASCIA_ALTA` — the hand-estimated price tiers
- `BUDGET` (0.15 / 0.50) — share of the total budget per department; a slider on each page
- `PREZZI_DEFAULT` / `PREZZO_SCONOSCIUTO` — fallback prices when `data/prezzi.csv` is absent
- `SOGLIA_ATTACCO` (0.80) — the "scoring fixture" threshold. Higher than the goalkeeper
  one because it measures the opposite event. It is the least-bad value rather than a
  good one, for the reason given in the attackers section
- `BONUS_GOL` (3.0) — points per goal, used by the attackers page
- `BONUS_IMBATTIBILITA` / `MALUS_GOL` (1.0 / 1.0) — your league's clean-sheet bonus and
  per-goal malus; some leagues use −0.5 a goal, or no clean-sheet bonus at all
- `SOGLIA_FACILE` (0.40) — a slider on the page
- `STAGIONE_CORRENTE` / `N_STAGIONI_STORICHE` — rolling to a new season means changing
  the first one **only**: `STAGIONI_STORICHE` is derived from it. Two independent lists
  meant updating one and not the other silently marked half the league as promoted from
  Serie B, since promotion is detected as "absent from the most recent stored season"
- `COPERTURA_MINIMA_STORICO` (0.90) — a season below this share of played matches is
  refused rather than written, on the same principle as the fixture validation

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
- **The edge is real but thin, and swings by season.** See the backtest above: +5.2
  points a season over a single goalkeeper on average, yet −12 in 2022-23. Treat the
  ranking as a shortlist, not a verdict — the top ten pairs are separated by far less
  than that spread.
- It ranks *teams*, not goalkeepers: there is no notion of who the starter actually is,
  of a keeper losing his place, or of a summer transfer.

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
