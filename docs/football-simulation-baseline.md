# Football simulation baseline

## What is measured

The reproducible harness in
[`scripts/measure_football_balance.py`](../scripts/measure_football_balance.py)
samples every named offensive card in seeded matchups and runs seeded full
games against every AI difficulty. These are measurements of this game's
model, not claims about observed FBS averages.

Run from the repository root:

```sh
python scripts/measure_football_balance.py --samples 5000 --games 300 --seed 20261114
```

Regulation uses two 900-second periods. Offensive card durations are
play-specific (19-32 seconds in the current named catalog); an incomplete
pass uses 5 seconds, while an interception or fumble uses its card's duration.
Punts and kickoffs use 10 seconds, field goals use 5 seconds, and conversions
are untimed. Defensive scheme choices and other actions without an assigned
duration do not consume the game clock.

## Named play and scheme catalog

The initial catalog keeps the six starter actions on each side and adds six
play variants plus six scheme variants. Each variant has a stable action/card
ID and stays a separate owned copy in the deck, hand, match event, and
playbook. Variants share family matchup contributors, counters, and existing
coach/partnership interactions; offensive variants differ only in name,
description, base yards, and clock duration. All play/scheme cards are Common
and cost 2 AP.

| Family | Offensive cards | Defensive schemes |
|---|---|---|
| RB Run | Inside Run; Quarterback Sneak (migrated); Jet Sweep (migrated); Power Toss | Run Fit; Goal-Line Front (migrated); Spill Front |
| Screen Pass | Screen Pass; Bubble Screen | Screen Read; Perimeter Check |
| Play-Action Pass | Play-Action Pass; Bootleg Keeper | Play-Action Read; Read and React |
| Short Pass | Short Pass; Quick Out (migrated); Slot Slant | Under Coverage; Nickel Under |
| Medium Pass | Medium Pass; Deep Dig | Pressure Shell; Fire-Zone Blitz (migrated); Two-High Pressure |
| Deep Pass | Deep Pass; Go Route | Deep Coverage; Cover Two Shell (migrated); Quarters Coverage |

The migrated catalog IDs remain unchanged, so existing in-memory copies keep
their ownership. Assigning variants to a family intentionally changes their
contributors and counter behavior to match that family: Quarterback Sneak and
Jet Sweep use RB Run contributors and interactions; Quick Out uses Short Pass
contributors/counters; Goal-Line Front counters the RB Run family; Cover Two
Shell counters only the Deep Pass family (not Medium Pass or Quick Out); and
Fire-Zone Blitz uses Medium Pass contributors and counters only that family
(not Play-Action Pass). The run-owned card state is not persisted to SQLite,
so no database migration is needed or implemented.

The standardized expected-yardage comparison is deterministic and uses
`calculate_standardized_play_estimate` for every offensive card. All players
on both teams have equal power 10, volatility 0, and stamina 1; there is no
fatigue, coach assignment, partnership, prior play, or fourth-down bonus. It
uses first down and an equivalent defensive scheme from a different family.
The estimator does not apply field-position/goal-line clipping. Expected pass
yards multiply successful-play yards by completion and non-interception
probabilities; expected run yards include the model's fumble loss outcome.
Results are expected actual gain, not raw card yards:

| Family | Card | Expected yards |
|---|---|---:|
| RB Run | Inside Run | 3.705 |
| RB Run | Quarterback Sneak | 2.519 |
| RB Run | Jet Sweep | 3.705 |
| RB Run | Power Toss | 4.199 |
| Screen Pass | Screen Pass | 5.595 |
| Screen Pass | Bubble Screen | 5.944 |
| Play-Action Pass | Play-Action Pass | 6.576 |
| Play-Action Pass | Bootleg Keeper | 7.269 |
| Short Pass | Short Pass | 6.993 |
| Short Pass | Quick Out | 6.294 |
| Short Pass | Slot Slant | 7.343 |
| Medium Pass | Medium Pass | 7.615 |
| Medium Pass | Deep Dig | 7.961 |
| Deep Pass | Deep Pass | 8.520 |
| Deep Pass | Go Route | 8.861 |

Across all variants, the lowest Deep Pass estimate (8.520) exceeds the highest
Medium Pass estimate (7.961), which exceeds the highest Short Pass estimate
(7.343). Screen Pass averages 5.770 expected yards versus 6.877 for Short
Pass; Play-Action Pass averages 6.923 versus 7.788 for Medium Pass. Their
successful-yardage ranges overlap. The highest RB Run estimate is 4.199, below
the lowest Screen Pass estimate. These are neutral reference values, not live
matchup predictions; player ratings, fatigue, counters, coaches, and field
position can change in-game rankings.

On two-point attempts, the human chooses a card from the current offensive
hand and the AI chooses one from its own hand; an empty hand uses the basic
inside-run fallback and played cards cycle normally. The team that scored the
touchdown kicks after a defensive conversion return. Blocked punts and field
goals resolve an automatic recovery and, for defensive recoveries, a return
that can score a touchdown and trigger a conversion. Those recovery and return
rates are provisional gameplay assumptions, not empirically calibrated.
For kicking-team recoveries, the model samples a setback from the original
line of scrimmage, truncated so the recovery spot cannot move forward. Since
these kicks occur on fourth down and the model has no kicking-team advance
outcome, every kicking-team recovery is a turnover on downs; the opponent
starts at the mirrored recovery spot. This avoids granting an automatic first
down and is a deliberate simplification. Defensive recoveries retain the
existing return and touchdown flow.
On two-point plays, drive-based run perks and matched-scheme pass effects use
the normal context-aware estimate; first-down and fourth-down perks do not
trigger on a conversion down. A defensive return on a conversion uses the
existing fixed 1% two-point-return chance. Ball-Hawk's field-position return
yards are not applied there because a conversion has no subsequent field
position; defining a conversion-specific Ball-Hawk effect remains open.

## Initial coach-upgrade catalog

The first catalog has 18 run-unique named upgrades. Coach-upgrade shop slots
unlock after game 3: the first costs 4 AP and the second costs 6 AP. Each
upgrade's purchase cost and rarity are separate from those slot-unlock costs.
Purchased match effects remain active for later games in the run; future-shop
AP bonuses apply only to later shops. These initial values are provisional
gameplay assumptions, not empirically calibrated balance targets.
Future-shop AP upgrades are offered through scheduled game 9, but not in game
10 because no subsequent shop remains.

| Upgrade | Rarity | Cost | Effect |
|---|---|---:|---|
| Two-Minute Drill | Uncommon | 3 AP | +5% relative power for offensive contributors; additive stacking, +20% cap |
| Front Seven Film | Uncommon | 3 AP | +5% relative power for defensive contributors; additive stacking, +20% cap |
| Rhythm Install | Rare | 3 AP | -15% offensive contributor volatility; additive stacking, 30% cap |
| Disguise Package | Rare | 3 AP | -15% defensive contributor volatility; additive stacking, 30% cap |
| Fourth-Quarter Conditioning | Uncommon | 3 AP | +0.10 effective offensive stamina after player training; +0.30 total and 1.00 per-player caps |
| Iron Lungs | Uncommon | 3 AP | +0.10 effective defensive stamina after player training; +0.30 total and 1.00 per-player caps |
| Booster Club Drive | Rare | 4 AP | +1 AP to every later shop this run; does not affect the current shop |
| Facilities Fund | Rare | 5 AP | +1 AP to every later shop this run; future-shop bonuses cap at +2 AP |
| Bye Week | Very Rare | 6 AP | Once per run, end the shop and skip its scheduled game without a match or record change |
| Tempo Install | Rare | 3 AP | -10% relative clock for normal offensive card plays; incomplete passes still use 5 seconds, conversions and special teams retain their rules |
| Huddle Up | Rare | 3 AP | +10% relative clock for normal offensive card plays; incomplete passes still use 5 seconds, conversions and special teams retain their rules |
| Vertical Threat | Rare | 3 AP | +10% Deep Pass-family result-calculation yards; negative gains become 10% less negative |
| Pattern-Match Shell | Rare | 3 AP | -10% opposing Medium Pass-family result-calculation yards when using a Medium Pass-family scheme; negative gains become 10% more negative |
| Ball-Security Clinic | Rare | 3 AP | -20% relative conditional interception chance; fumble risk is unchanged |
| Field-Goal Lab | Rare | 4 AP | +5 percentage points to conditional make probability given an unblocked kick, capped at 100%; 0.5% block risk is unchanged |
| Clean-Pocket Protection | Uncommon | 3 AP | -25% relative punt and field-goal block chance; extra-point block chance is unchanged |
| Punt Return Lane | Uncommon | 2 AP | +2 yards per punt return; non-scoring returns stop one yard short of the goal line |
| Kickoff Return Lane | Uncommon | 2 AP | +2 yards per kickoff return; non-scoring returns stop one yard short of the goal line, and touchback/touchdown chances are unchanged |

Power bonuses apply after existing coach, partnership, fatigue, and scheme
calculations; offense and defense upgrades use separate +20% caps. Volatility
reductions combine additively to 30%, and stamina bonuses combine to +0.30
while each player's effective stamina remains capped at 1.00. Family yardage
changes combine additively after flat yardage bonuses, then apply a 0.50-1.50
multiplier clamp before the existing -5 to 25 yard result clamp. Apply the net
offensive bonus minus matching defensive reduction in the beneficial direction:
nonnegative raw yards use `1 + delta`, while negative raw yards use `1 - delta`;
zero is unchanged. Thus offensive upgrades cannot worsen negative gains and
defensive upgrades cannot improve them. Incomplete passes and interceptions
remain zero, and play risks are unchanged; fumble probabilities are unchanged,
but a fumble's calculated yardage uses the same multiplier when nonzero.
Opposing offense and defense effects combine additively before the direction
is applied. The multiplier affects calculated result yards (and the shared
expected-yardage estimate), not completion, interception, or fumble
probabilities.

Relative offensive-clock changes combine additively and clamp to a 0.75-1.25
multiplier. Durations round half-up to whole seconds with a one-second
minimum. The match hand previews this live normal-play value separately from
the printed base duration; incomplete passes remain 5 seconds, and conversions
and special teams retain their existing clock rules. Interception and kick-block
reductions are relative and capped at 75%. Field-goal accuracy is an additive
five-percentage-point bonus to conditional make probability given an unblocked
kick, capped at 100%; it does not change the 0.5% block chance or the
probability of an overall make after accounting for a block. Return-yard bonuses leave return, touchback, and
touchdown chances unchanged.

A Bye Week preserves the current record and assets, marks one scheduled game
skipped, and opens the next scheduled game's shop for games 1-9. Skipping
scheduled game 10 reaches the existing playoffs marker without fabricating a
match or score; no playable playoff bracket exists yet.

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

The expanded single-play run samples every one of the 15 named offensive
cards 5,000 times in each scripted matchup and distance scenario. In the equal
uncountered sample, offense and defense players each have power 50, volatility
0.1, and stamina 0.75; it is first down, 10 yards to go, the offense starts at
the 30-yard line, and no coach or player partnership is active. Means below
are realized gains including incompletions, interceptions, and fumbles; the
95% confidence intervals are normal approximations.

| Family | Card | Mean actual yards (95% CI) |
|---|---|---:|
| RB Run | Inside Run | 3.68 [3.66, 3.71] |
| RB Run | Quarterback Sneak | 2.50 [2.48, 2.52] |
| RB Run | Jet Sweep | 3.70 [3.67, 3.72] |
| RB Run | Power Toss | 4.21 [4.18, 4.23] |
| Screen Pass | Screen Pass | 5.52 [5.42, 5.63] |
| Screen Pass | Bubble Screen | 5.85 [5.74, 5.96] |
| Play-Action Pass | Play-Action Pass | 6.54 [6.42, 6.67] |
| Play-Action Pass | Bootleg Keeper | 7.18 [7.05, 7.32] |
| Short Pass | Short Pass | 6.94 [6.81, 7.07] |
| Short Pass | Quick Out | 6.27 [6.15, 6.38] |
| Short Pass | Slot Slant | 7.41 [7.28, 7.54] |
| Medium Pass | Medium Pass | 7.64 [7.50, 7.78] |
| Medium Pass | Deep Dig | 7.98 [7.83, 8.13] |
| Deep Pass | Deep Pass | 8.58 [8.41, 8.74] |
| Deep Pass | Go Route | 8.66 [8.49, 8.83] |

This sampled matchup retains the pass-family expected-yardage ordering:
Deep Pass sample minimum 8.58 > Medium Pass maximum 7.98 > Short Pass maximum
7.41. Screen/Short and Play-Action/Medium sample success ranges overlap.
All four RB Run means are below the Screen Pass means in this matchup. Live
field position, defensive counters, coaches, fatigue, and player ratings can
still change the relative results in an actual game.

With the named-card catalog and variant-aware AI, the same command and seed
(`20261114`) completed another 300 games per difficulty. Comparison with the
pre-catalog run:

| Difficulty | Games | Combined points/game before -> after | Offensive snaps/game before -> after | Total drives/game before -> after |
|---|---:|---:|---:|---:|
| Easy | 300 | 35.96 -> 36.26 | 84.6 -> 85.3 | 10.74 -> 10.72 |
| Standard | 300 | 37.53 -> 39.35 | 85.5 -> 86.7 | 10.37 -> 10.53 |
| Hard | 300 | 39.53 -> 40.89 | 85.0 -> 85.2 | 10.72 -> 10.61 |

The catalog/AI update raises scoring by 0.30-1.82 points per game while
snaps and drives remain near the previous baseline and within the approximate
volume targets. Hard scoring is 1.89 points above the earlier approximate
35-39 band and 0.89 above the broader 36-40 target. This is a modest shift,
not a volume regression; human playtesting is still needed to judge whether
the improved Hard AI and higher scoring feel balanced. The seeded measurement
includes the intended variant selection behavior and is not an isolated
yardage-parameter A/B test.

Repeating the 300-game sample with the same seed initially produced small
Hard-only differences because Hard AI broke tied scores by iterating a
`frozenset` of countered plays. The AI now uses the action ID as a stable
tie-break. Two consecutive post-fix runs and the full-catalog run reproduced
the same Easy, Standard, and Hard aggregate metrics.

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

After the blocked-kick recovery adjustment, a fourth fresh-seed run
(`20261117`) completed another 300 games per difficulty: Easy 35.88 combined
points, 84.7 snaps, and 10.73 drives; Standard 37.37 points, 85.5 snaps, and
10.34 drives; Hard 39.69 points, 84.9 snaps, and 10.70 drives. Points include
both teams' final scores, overtime, conversions, and return scores. Snaps count
events with a `play_result`, including overtime but excluding conversions;
drives count defensive-scheme selections, including overtime. These are AI
simulation measurements, not a manual desktop playtest.

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
