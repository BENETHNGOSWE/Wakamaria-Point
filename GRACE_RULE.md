# GraceRule

The name for every selection rule agreed on 2026-11-08. When the user says
**"push updated for GraceRule"**, apply the deploy section at the bottom.

---

## The rules, exactly

| # | Rule |
|---|---|
| 1 | **Certainty floor 80%.** Any market the model rates 80% or better is a candidate. Among those candidates the **best price wins**. If two are equal on price, the higher probability wins. |
| 2 | **No price floor.** A cheap pick that is the most certain option still wins. A 1.04 beats a 1.19 when it is the more certain of the two. |
| 3 | **No market is excluded.** All 19 markets compete, including `12` "either team wins". |
| 4 | **Nothing at 80%?** Then the highest probability wins and price plays no part. |
| 5 | **Odds never decide the pick** on their own — only as the tie-break *inside* the 80% band. Nothing below 80% can ever be chosen for its price. |
| 6 | **Every listed prediction shows its odds.** Odds are cosmetic and labelled `EST` on the site. |
| 7 | **Never hide a fixture.** Every match gets a prediction, even with no team data. |
| 8 | **Home advantage is measured per fixture**, from the two teams' own home and away records. There is no fixed 55/45. A stronger away side can be the favourite. |
| 9 | **Goal markets come from both teams**, attack and defence of each side — never a league average. |
| 10 | **One prediction per fixture.** Single team per row. |

## What GraceRule fixed

| Bug | Fix |
|---|---|
| Model claimed 93% confidence, delivered 55% | `wakamaria/calibration.py` — per-market curves mapping stated probability to observed |
| Calibration clamped at the top, so an 88% near-certainty could only be stated as 64% | Curves now extend to (0,0) and (1,1) instead of holding flat |
| Model could never rate an away win above ~60% | Ratings widened to 0.30–3.20; `Sabah v Barcelona` now prices Barcelona at 0.85 |
| Fixed 55/45 home advantage | `model.league_split` measures the split per fixture |
| "12 — either team wins" on every row | Rule 1 makes it lose to any better-priced candidate |
| `Under 4.5` missing from the goal lines | Added. 19 markets now |

## Ben Rule vs Grace Rule, side by side

Both rules run on **every fixture**. The row stores both picks, so they settle
from the same score and can be compared on identical matches.

| | Ben Rule | Grace Rule |
|---|---|---|
| Rule | highest probability, price ignored | 80% floor, best price among candidates |
| Published on the site | **yes** (the list you trust) | shadow |
| Hit rate, 17,538 matches | **86.4%** | 84.7% |
| Hit rate, held out | 86.7% | 84.8% |
| Average price | 1.092 | 1.112 |
| Mix | Under 4.5 81%, 1X 11%, Over 1.5 6% | Under 4.5 65%, Over 1.5 17%, 1X 9%, 12 4%, X2 4% |

**The measured trade: Grace Rule wins 1.7 points less often and pays 0.02 more
per bet.** Ben Rule is the more accurate of the two; Grace Rule is the better
priced. Both are far above the 70% target.

On the site: tabs `Ben Rule` / `Grace Rule` in the toolbar, and a strip above
them showing each rule's live win rate.

## Verified numbers

| Test | Result |
|---|---|
| Whole history through `predictor.choose` (17,538 matches) | **84.7%** |
| Held out (last 40%) | **84.3%** |
| 2026/27 season alone | **83.1%** |
| Average stated confidence | 0.85 — matches the 84.7% |

Market mix: Under 4.5 65%, Over 1.5 17%, 1X 9%, 12 4%, X2 4%, rest <1%.

**Known trade-off:** `Under 4.5` dominates the list because it is the most
certain option most days. Accuracy is high, variety is low. Rule 1 causes this
and the user accepted it.

## Where the code lives

| File | Holds |
|---|---|
| `wakamaria/predictor.py` | `CERTAINTY_FLOOR = 0.80`, the two-rule selection |
| `wakamaria/calibration.py` | the fitted curves and the extrapolation |
| `wakamaria/model.py` | `league_split`, `team_venue_rates`, `RATING_FLOOR/CEIL` |
| `wakamaria/agent.py` | `HISTORY_FETCH_BUDGET = 30`, `enable_accuracy_band` |
| `wakamaria/tips.py` | the 19 markets |
| `backtest.py` | the chronological harness |
| `BACKTEST.md` | the measurements |

## Git state

| Commit | What |
|---|---|
| `2f3c086` | **Pushed.** Calibration. The version whose win rate is trusted today. |
| `50f6888` | Pushed. Standings shrinkage. |
| `625084e` | Pushed. `fmtOdds` restore. |
| `f2df849` | **NOT PUSHED.** GraceRule: certainty floor, best price, no exclusions, Under 4.5, ceiling fix. |

Tests: 173, all passing.

## Deploy — what "push updated for GraceRule" means

```bash
cd /home/user/wakamaria
GIT_TERMINAL_PROMPT=0 git push "https://x-access-token:<TOKEN>@github.com/BENETHNGOSWE/Wakamaria-Point.git" HEAD:main
```

On the server:

```bash
cd ~/frappe-v16/apps/wakamaria && git pull
cd ~/frappe-v16 && bench clear-cache && bench restart
bench --site mkamaria.localhost execute wakamaria.agent.enable_accuracy_band
bench --site mkamaria.localhost enable-scheduler
bench --site mkamaria.localhost clear-cache
```

Then rebuild the published rows:

```bash
bench --site mkamaria.localhost mariadb -e "SET SQL_SAFE_UPDATES=0; DELETE FROM \`tabWakamaria Match\` WHERE result_confirmed=0 AND kickoff > NOW()"
bench --site mkamaria.localhost execute wakamaria.agent.run_agent
```

### Reminders that still apply

- The GitHub token must be **revoked** once testing is done; it was pasted in
  chat on 2026-11-08 and must never be written to `.git/config`, a file or a log.
- Results only settle if `Wakamaria Settings.enabled` is ticked **and** the site
  scheduler is enabled **and** `bench start` is running. `sync_all` skips
  fixtures that have not kicked off yet.
- Agent runs need the site python, not system python.

## Before trusting the next measurement

GraceRule is a backtest of 84.7%. Live, expect less. After ~100 settled picks
under GraceRule, compare the stated confidence against the actual win rate. If
they land within five points, the calibration is holding.
