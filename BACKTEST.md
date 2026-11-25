# Backtest report

Measured on **17,538 matches**, 12 competitions, July 2022 → November 2026.
Every match predicted using only matches that finished before it.

Run it yourself: `python3 backtest.py` (about 5 minutes).

> **Correction.** The first version of this file reported that all four
> modelling upgrades were worth only +1.1 points. That was wrong: the "what
> the site does today" baseline in the harness was double-dividing the ratings,
> so its expected goals were far too low. The table below is the corrected
> run. The harness bug was found before anything was shipped.

## What each fix is worth

| Variant | Picks | Correct | Hit rate | Claimed | Log loss |
|---|---|---|---|---|---|
| v0 what the site does today | 17,537 | 12,326 | **70.3%** | 94.8% | 0.9454 |
| v1 + per-league goal baselines | 17,526 | 12,278 | 70.1% | 94.3% | 0.9159 |
| v2 + opponent-adjusted ratings | 17,526 | 12,668 | **72.3%** | 92.4% | 0.8669 |
| v3 + time decay (90-day half-life) | 17,526 | 12,579 | 71.8% | 92.2% | 0.8546 |
| v4 + Dixon-Coles correction | 17,526 | 12,608 | 71.9% | 92.3% | 0.8519 |

Opponent adjustment is the only model change worth shipping on its own
(+2.0 points). Time decay and Dixon-Coles lower the hit rate slightly while
improving log loss, which means the probabilities get better even when the top
pick does not change.

**None of this is what fixed the site.**

## The actual problem: the stated probabilities were fiction

Comparing every stated probability against what happened:

| Market | Model said | Reality |
|---|---|---|
| Over 1.5 goals | 22% | **71%** |
| Under 3.5 goals | 95% | **68%** |
| 1X | 85% | 89% |
| X2 | 80% | 78% |

The model badly underestimates goals. Because it believed Over 1.5 was
unlikely, it never picked Over 1.5 — and instead picked Under 3.5 on
**nine rows out of ten**.

Correcting the stated probability, and then selecting the market with the
highest corrected probability, is the whole fix:

| | Hit rate |
|---|---|
| Select on raw probability | 70.3% |
| **Select on calibrated probability** | **80.0%** |

## Verified on three separate chronological splits

The calibration table was fitted only on earlier matches and tested on later
ones, three different ways:

| Split | Raw | Calibrated |
|---|---|---|
| First 60% / last 40% | 70.3% | **79.9%** |
| Up to 2025-07 / after | 69.9% | **80.1%** |
| Up to 2024-07 / after | 70.6% | **80.0%** |

Eight of ten, consistently. That is above the seven-in-ten target.

## What the site will publish

Checked through the real `predictor.choose` path on the held-out 40%
(7,015 fixtures, none skipped):

| Market | Share | 
|---|---|
| Over 1.5 | 48% |
| 1X | 29% |
| Under 3.5 | 14% |
| X2 | 9% |
| 12 | 1% |

Hit rate **80.0%**. Published confidence ranges 0.75–0.95, mean 0.81 — and
because the number is calibrated, it now means what it says.

Variety survived. Earlier concern that accuracy would force "Under 3.5 on
every row" was wrong: once the goal bias is corrected, Over 1.5 is correctly
recognised as the most likely market and takes its proper place.

## What was shipped

1. `wakamaria/calibration.py` — the fitted curves, 18 markets, 231 knots.
2. `predictor.choose` ranks and publishes the **calibrated** probability.
3. Confidence ceiling raised 0.90 → 0.97 (`agentconfig.DEFAULTS`), plus
   `agent.enable_accuracy_band` to apply it to an existing site.
4. Model prices recomputed from the calibrated probability, so a 75% chance
   is never posted at the price of a 40% one.

## What the numbers cannot promise

80.0% is a backtest. The calibration table is fitted on 12 European leagues
with deep history. The live site covers competitions with thinner data, and
the agent sees only the last 20 results per team. Expect the live figure
below the backtest, and measure it: after ~100 settled picks compare
`confidence` against the actual win rate. If the two land within five points
of each other, the calibration is holding.

## Reproducing

```
python3 backtest.py                 # the five-variant comparison
python3 -m unittest discover -s tests
```
