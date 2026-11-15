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

Regulation uses two 900-second periods. Offensive card durations are
play-specific (24-28 seconds); an incomplete pass uses 5 seconds, while an
interception or fumble uses its card's duration. Punts and kickoffs use 10
seconds, field goals use 5 seconds, and conversions are untimed. Defensive
scheme choices and other actions without an assigned duration do not consume
the game clock.

On two-point attempts, the human chooses a card from the current offensive
hand and the AI chooses one from its own hand; an empty hand uses the basic
inside-run fallback and played cards cycle normally. The team that scored the
touchdown kicks after a defensive conversion return. Blocked punts and field
goals resolve an automatic recovery and, for defensive recoveries, a return
that can score a touchdown and trigger a conversion. Those recovery and return
rates are provisional gameplay assumptions, not empirically calibrated.
On two-point plays, drive-based run perks and matched-scheme pass effects use
the normal context-aware estimate; first-down and fourth-down perks do not
trigger on a conversion down. A defensive return on a conversion uses the
existing fixed 1% two-point-return chance. Ball-Hawk's field-position return
yards are not applied there because a conversion has no subsequent field
position; defining a conversion-specific Ball-Hawk effect remains open.

The measured balance uses a 3.5-yard global offensive yardage bonus, a
-3.75-yard run adjustment, a +1-yard pass adjustment, and a 0.5-yard matched
scheme penalty. The results below use the command and seed above.
Play-yardage intervals are normal-approximation 95% confidence intervals;
binary rates use Wilson 95% intervals.

## Play matchup samples

Each row contains 5,000 independently seeded resolutions. `4+` is the share
that gained at least four yards; it is a simple usefulness threshold, not a
first-down rate. The equal-rating countered row uses a defense scheme that
counters the play. The offensive-edge row uses offense power 65 vs defense
power 55; the countered version uses the same ratings with a countering scheme.

| Matchup | Play | Mean yards (95% CI) | 4+ yards (95% CI) |
|---|---|---:|---:|
| Equal, uncountered | RB run | 3.68 [3.66, 3.71] | 38.6% [37.2%, 39.9%] |
| Equal, countered | RB run | 0.67 [0.66, 0.69] | 0.0% [0.0%, 0.1%] |
| Offense 65 vs defense 55, uncountered | RB run | 6.88 [6.85, 6.90] | 99.1% [98.8%, 99.3%] |
| Offense 65 vs defense 55, countered | RB run | 3.43 [3.41, 3.45] | 28.2% [27.0%, 29.5%] |
| Offense 40 vs defense 60, uncountered | RB run | -2.65 [-2.67, -2.63] | 0.0% [0.0%, 0.1%] |
| Equal, uncountered | Medium pass | 7.53 [7.38, 7.67] | 68.4% [67.1%, 69.7%] |
| Equal, countered | Medium pass | 5.04 [4.93, 5.15] | 63.4% [62.1%, 64.7%] |

The prior equal-rated uncountered run result was 7.38 yards on average and
gained at least four yards 98.5% of the time. That strongly favored offense
and did not meet the approved design goal. The measured adjustment reduces
that rate to 38.6% (95% CI 37.2%-39.9%) and the mean to 3.68 yards, so equal
uncountered runs now generally fall short of four yards. A +30% offensive
power edge retains a strong uncountered result, while the run counter reduces
that edge to a 3.43-yard mean and a 28.2% 4+ rate. This is a deliberate
defense-favoring adjustment; the especially low 0.67-yard mean against a run
counter remains a balance risk for human playtesting.

## Seeded full-game samples

Each difficulty has 300 games: Standard AI on Team A against the named
opponent on Team B. All metrics are per full game; results include overtime
where played.

| Opponent | Games | Combined points/game (mean; median; 10th-90th pct) | Offensive snaps/game | Total drives/game | 2-point attempts/game | Overtime games |
|---|---:|---:|---:|---:|---:|---:|
| Easy | 300 | 35.96; 36; 27-45 | 84.6 | 10.74 | 0.31 | 10 |
| Standard | 300 | 37.53; 38; 28-49 | 85.5 | 10.37 | 0.38 | 17 |
| Hard | 300 | 39.53; 41; 28-50 | 85.0 | 10.72 | 0.41 | 9 |

Combined points are both teams' final scores, including overtime and all
scoring types, including two-point conversions and defensive or kickoff
returns. Offensive snaps count events with a `play_result`; they include
overtime scrimmage plays but exclude conversion attempts, which do not have a
`play_result`. Two-point attempts are counted separately from conversion
events. Total drives count defensive-scheme events (one per drive start by
either team); they include overtime and do not count a conversion as a drive.
The overtime column counts games with any event in period 3 or later.

The results are close to the targets of about 84 snaps, 10 drives, and 36-40
combined points. Easy is just below 36 points/game; Hard remains within the
target band. These are seeded AI-vs-AI model measurements, not a completed
human playtest or evidence of real-world scoring rates.

A separate 300-game-per-difficulty run with seed `20261115` reproduced the
pattern: Easy 35.90 points, 84.7 snaps, and 10.73 drives; Standard 37.50,
85.5, and 10.37; Hard 39.57, 84.9, and 10.71. The two seeds give 600 games
per difficulty for this validation, but remain simulations of the same AI
model rather than independent real-world or human-playtest evidence.

A third 300-game-per-difficulty run with seed `20261116` also reproduced the
pattern: Easy 35.94 points, 84.7 snaps, and 10.75 drives; Standard 37.48,
85.5, and 10.36; Hard 39.62, 84.9, and 10.71. Across these three seeds, the
equal, uncountered RB run remained 3.68 yards on average and gained at least
four yards 38.6% of the time (95% Wilson CI: 37.3%-40.0%) in the 5,000-play
sample. These additional samples improve repeatability checks but do not
replace human playtesting or independently validate the model assumptions.

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
