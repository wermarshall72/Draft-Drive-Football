# Football simulation baseline

## What is measured

The reproducible harness in
[`scripts/measure_football_balance.py`](../scripts/measure_football_balance.py)
samples the play resolver and seeded full games. These are measurements of
this game's model, not claims about observed FBS averages.

Run from the repository root:

```sh
python scripts/measure_football_balance.py --samples 5000 --games 300 --seed 20261114
```

The current tuned prototype uses two 650-second regulation periods, an
offensive baseline yardage bonus of 3.5 yards, and a 1.5-yard penalty when
the defensive scheme counters the play. The results below use that command
and seed. Play-yardage intervals are normal-approximation 95% confidence
intervals; binary rates and game win rates use Wilson 95% intervals.

## Play matchup samples

Each row contains 5,000 independently seeded resolutions. `4+` is the share
that gained at least four yards; it is a simple usefulness measure, not a
first-down rate. The equal-rating countered row uses a defense scheme that
counters the play. The offensive-edge row uses offense power 65 vs defense
power 55; the countered version uses the same ratings with a countering scheme.

| Matchup | Play | Mean yards (95% CI) | 4+ yards (95% CI) |
|---|---|---:|---:|
| Equal, uncountered | RB run | 7.38 [7.35, 7.41] | 98.5% [98.1%, 98.8%] |
| Equal, countered | RB run | 3.37 [3.35, 3.39] | 25.0% [23.8%, 26.2%] |
| Offense 65 vs defense 55, uncountered | RB run | 10.59 [10.56, 10.63] | 99.1% [98.8%, 99.3%] |
| Offense 65 vs defense 55, countered | RB run | 6.13 [6.11, 6.16] | 98.3% [97.9%, 98.6%] |
| Offense 40 vs defense 60, uncountered | RB run | 1.08 [1.06, 1.10] | 0.0% [0.0%, 0.1%] |
| Equal, uncountered | Medium pass | 6.84 [6.71, 6.97] | 68.4% [67.1%, 69.7%] |
| Equal, countered | Medium pass | 3.77 [3.69, 3.85] | 63.4% [62.1%, 64.7%] |

Counters materially suppress equal-rated runs, while a large power edge can
still overcome a counter. The high uncountered run success rate is a deliberate
arcade tuning choice, but also a remaining balance risk: in equal matchups,
an uncountered run reaches four yards almost every time. These are game-model
measurements, not calibrated predictions for real players.

## Seeded full-game samples

Each difficulty has 300 games: Standard AI on Team A against the named
opponent on Team B. Points are pooled across both teams (600 team-game
observations per row). Win intervals are over the 300 Team A results. Plays
count offensive snaps by both teams. Drives are counted from defensive-scheme
events and divided by games times two.

| Opponent | Team A wins (95% CI) | Points / team-game (mean; median; 10th-90th pct) | Snaps / game | Drives / team-game |
|---|---:|---:|---:|---:|
| Easy | 76.7% [71.6%, 81.1%] | 18.26; 18; 7-28 | 83.9 | 5.11 |
| Standard | 59.7% [54.0%, 65.1%] | 19.23; 20; 10-28 | 84.1 | 5.00 |
| Hard | 38.0% [32.7%, 43.6%] | 19.66; 21; 10-28 | 83.3 | 5.04 |

An independent 300-game run with seed `20261115` reproduced the result:
83.9/84.0/83.3 snaps, 5.11/5.00/5.03 drives, and 18.25/19.26/19.68
points for Easy/Standard/Hard. This is close to the targets of 80 snaps and
18 points, but the model is consistently about one drive per team short of
six. Scoring drives account for roughly 54-58% of recorded drive endings,
slightly above the desired under-half expectation. The Standard matchup is
also somewhat favorable to Team A in these seeded samples; difficulty and
scoring should be rechecked after any further tuning.

## Historical references and limits

The FootballDB tables are season-long FBS team passing tables for 2022-2024.
CFBStats team pages provide the wider team-season categories used for the
cross-check below:

- [FootballDB 2022 FBS passing](https://www.footballdb.com/college-football/stats/teamstat.html?group=FBS&cat=P&yr=2022)
- [FootballDB 2023 FBS passing](https://www.footballdb.com/college-football/stats/teamstat.html?group=FBS&cat=P&yr=2023)
- [FootballDB 2024 FBS passing](https://www.footballdb.com/college-football/stats/teamstat.html?group=FBS&cat=P&yr=2024)
- [CFBStats 2022 Massachusetts team statistics](https://cfbstats.com/2022/team/400/index.html)
- [CFBStats 2023 Massachusetts team statistics](https://cfbstats.com/2023/team/400/index.html)
- [CFBStats 2024 Massachusetts team statistics](https://cfbstats.com/2024/team/400/index.html)
- [CFBStats 2024 Arkansas team statistics](https://cfbstats.com/2024/team/31/index.html)
- [Sports-Reference year-by-year field-goal percentage leaders](https://www.sports-reference.com/cfb/leaders/fg-pct-player-yearly.html)

The Massachusetts team-season rows show exact source numerators and
denominators across all three years. Rates below are calculated from the
reported counts; the season totals include every game on the schedule, not
only FBS-vs-FBS contests.

| Season | Pass INT / attempts | Rushing yards / attempts | Field goals made / attempts | Punt returns (returns-yards-TD) | Kickoff returns (returns-yards-TD) |
|---|---:|---:|---:|---:|---:|
| 2022 | 14/277 = 5.05% | 1,786/520 = 3.43 | 13/18 = 72.2% | 10-92-0 | 35-638-0 |
| 2023 | 11/348 = 3.16% | 1,706/390 = 4.37 | 11/20 = 55.0% | 12-80-0 | 40-713-0 |
| 2024 | 6/327 = 1.83% | 1,962/483 = 4.06 | 13/21 = 61.9% | 15-130-1 | 22-398-0 |

As a second team-level check, Arkansas in 2024 recorded 9 interceptions on
414 attempts (2.17%) and made 17 of 24 field goals (70.8%). These team
examples expose realistic variation, but are not league averages or a pooled
three-season estimate.

The field-goal curve in the simulator interpolates broad historical
distance-band rates and uses a conservative long-range tail. A verified,
weighted 2022-2024 FBS distance-band aggregate was not available in the
reviewed sources, so the curve must not be presented as a recent-season
league baseline. The same caution applies to the arcade punt, return, and
kickoff probabilities: they are explicit provisional gameplay values.

## Follow-up

A season-wide, weighted 2022-2024 FBS aggregation with consistent participant
and bowl-stat coverage is still needed before tuning the model to league
averages. The Massachusetts and Arkansas rows are illustrative program
samples only. In particular, aggregate field-goal attempts and makes by
distance, passing attempts and interceptions, rushing attempts and fumbles
lost, and punt/kickoff return attempts, yards, and touchdowns; publish each
numerator and denominator with the source and coverage rule.
