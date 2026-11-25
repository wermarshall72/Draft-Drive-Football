# Specialist Player Perks: Proposal

Status: **approved and implemented.** The 48 type IDs and partner pairings in
`_SPECIALISTS` (`src/engine/football_player_catalog.py`) are unchanged; each
specialist now carries a typed perk with these values. Two display names changed
(W2 Field Stretcher, W3 Chain Mover). Basic players keep no perk. The decisions
in §0 override the rest of this document where they differ; the affected rules
below have been updated to match.

## 0. Approved decisions

1. **Green Dog (L6)** stays as designed: once per game, after a rival 3rd- or
   4th-down conversion (not a touchdown), the defense may swap its active scheme
   for one in hand; the swapped-in card is discarded and replaced. It is offered
   on each conversion until used. The human gets a prompt (keep, or swap with a
   hand scheme); the AI swaps when its best hand scheme outscores the active one
   in the estimate.
2. **Read Keys (L4)** reveals the rival's whole offensive hand while the owner
   chooses a defensive scheme (a "READ KEYS" panel for the human, closed when the
   scheme is chosen). Standard and Hard AI favor schemes that counter the
   revealed cards; Easy ignores them.
3. **No hand ceiling** for perk draws (the 6 offense / 4 defense ceiling is removed).
4. **Hands reset at the end of each drive.** The offense's offensive hand returns
   to 3 and the defense's defensive hand to 2: extras are discarded at random with
   that deck's own RNG, short hands draw with the existing helpers (nothing if
   nothing is drawable). Both teams; after any two-point try. This replaces "extra
   cards stay until the next redeal"; Draw bonus cards help for the rest of the
   drive only, and the trim can discard cards kept by R4 or D1. Halftime and
   overtime still redeal.
5. **Spot clash:** the defense gets the last word (§2 step 6).
6. **Challenge:** perk uses spent on a challenged play are not refunded, and card
   moves stay (a Green Dog swap included).
7. **Silent Count (Q6)** cancels only the base counter modifiers; coach perks keyed
   to matching still apply.
8. **Renames approved:** Vertical Threat → Field Stretcher, Screen Outlet → Chain
   Mover (type IDs unchanged).
9. **AI drafting** at every difficulty is a seeded weighted choice that prefers
   partners of already-drafted players and perks fitting its deck's families.
10. **Keep Read (R2)** works on two-point tries; the AI goes for two when it holds
    an unused Keep Read and a Play-Action card.
11. **Dice perks are fine** (R3, W2, D5, S6), using the match RNG.
12. **Halftime ends the drive** and period 2 starts with a kickoff by the team
    that received the opening kickoff (`opening_possession`, saved). A pending
    touchdown conversion still resolves first. Overtime is unchanged.
13. **Bait & Jump (C6) and Keep Read (R2) are once per half** (after the first
    balance measurement, §8). C6 keeps its charge (one charge, consumed by any
    rival Deep snap, renewed by an allowed Deep catch, kept through halftime),
    but its +8 pp payoff applies at most once per half; R2 changes from once per
    drive to once per half, and a two-point try counts in its touchdown's half.
    Overtime is one half for both. The AI goes for two with Keep Read only while
    that half's use is unused.

## 1. Summary

**Goals.** Each specialist should be a different reason to draft. Every perk
has a checkable trigger, exact numbers, and a clear limit. Most perks push a
deck or play-calling choice ("I drafted Screen Setter, so I want more
Screens"). Perks with only invisible number changes were cut.

**Four effect types.**

| Type | What it touches | Count |
|---|---|---|
| Stats | Temporary power, matchup (counter) status | 10 |
| Cards | Draw, keep, pull, swap, or force rival discards/churn; reveal hand | 13 |
| Yards / clock / field | Bonus yards, caps, floors, spots, clock seconds, drive start, FG range | 16 |
| Turnovers / big plays | Incompletion/INT odds, rerolls, conversions, big gains, blocked kicks | 9 |

**Frequent vs rare.** Tiers use measured fires per team per game (method in
§5): **Frequent** ≥ 2.0, **Moderate** 1.0–2.0, **Rare** < 1.0. Each position
has 3–4 frequent or moderate perks that fire most games several times, and 2–3
rare "moment" perks (about once a game or less).

**Partners.** 19 of 48 perks require the partner position on the play or
scheme (offense: the pair's play family; defense: the pair's scheme family).
The other 29 work with or without the partner, so drafting a specialist without
its partner never wastes the pick. The existing +10% partnership bonus stays
unchanged and separate.

**AI.** Perks follow the same rules for both teams. AI rosters already draft
from this catalog, so AI teams will carry perks. Card perks use the normal deck
helpers for whichever team triggers them and never use bonus cards. Perks that
change a play's inputs feed into the play estimate, so the AI and the human's
previews both see them. Only the two perks that need a new system (L4, L6)
need new AI decision logic.

## 2. Shared rules

### Scope and limit vocabulary

| Term | Meaning |
|---|---|
| That snap | The triggering offensive play only. |
| Next snap | The same team's next offensive play in the same drive. Lost if the drive ends first. |
| Drive | From scheme selection until possession changes (score, turnover, punt, FG, downs, safety). A two-point attempt belongs to its scoring drive. |
| Rival drive | A drive in which your team is on defense. |
| Half | Period 1, period 2, or overtime (all OT periods together). |
| Once per drive / half / game | The perk fires at most once in that scope for that team. Uses refresh at the next drive / at the start of period 2 and of the first OT period / never. |
| Charge | A stored effect waiting for a later play (Q4, R1, C6). One charge at a time; a new trigger doesn't stack a second. C6's payoff is also limited to once per half. |

### Halftime, overtime, turnovers, conversions

- **Halftime.** Halftime ends the drive: drive-scoped effects and charges end,
  per-half uses refresh, and hands are redealt (a kept card is reshuffled like any
  other). Period 2 opens with a kickoff by the team that received the opening
  kickoff.
- **Overtime.** OT is one "half" for limits. OT drives start at the 25 with no
  kickoff, so O6 never fires in OT. "Final 3:00" (Q3) and "period 2" (O3, C1)
  triggers are regulation only. Perks that stop a score (L3, S1) can extend
  sudden death, and one that grants a score (W5) can end it.
- **Turnovers.** A turnover ends the drive: drive-scoped effects and charges
  end. "Next drive" effects (L5) and takeaway effects (S5) apply as written.
- **Conversions.** Perks ignore two-point attempts unless they say otherwise
  (only R2). Extra points count as kicks for D5.

### Stacking and caps

- One player per position, so a team never holds two copies of a perk. Both
  teams may hold the same perk independently.
- **Power.** Flat perk power (+N own, −N rival) is added to the player's base
  power (floor 0) **before** fatigue. The coach + partnership modifier (capped
  at 130%), the scheme counter multipliers, and coach-upgrade power (capped at
  +20%) then apply as today. The 130% cap limits the modifier, not the flat
  amount. Rule of thumb: +8 power to one contributor ≈ +1.3 yards and
  ≈ −0.6 pp incompletion.
- **Additive yards** (R1, R5, S2) join coach yard perks before the family
  yardage multiplier and the −5 to 25 yard cap.
- **Odds.** Incompletion changes (Q4, S2) are added before the 12–52% clamp.
  Interception changes (C6) are added before the 0.5–10% clamp, then the
  offense's risk reduction applies. R2 replaces pass risk with the run fumble
  chance (0.3–8%). D5 adds to the base block chance before the kicking team's
  block-risk reduction (max 75%).
- **Stamina** is not changed by any perk; stamina is still capped at 1.0.
- **Clock.** Card duration × coach clock multiplier (0.75–1.25, round half up)
  → Q3 sets the result to at most 8 s → O3 / C1 add seconds → minimum 1 s.
  Incompletions stay 5 s. Clock can't go below 0.

### Order of application on one play

1. **Inputs (in the estimate):** perk power → fatigue → coach and partnership
   modifier → counter status (Q6 cancels a counter, including one created by
   C2) → scheme multipliers → coach-upgrade power → yards (base, power edge,
   coach perks, perk yards) → family multiplier → −5 to 25 cap → risk odds.
2. **Roll** with the match RNG.
3. **Completion reroll:** W2.
4. **Result swaps:** offense first (O1), then defense (S4 before D6). A result
   is swapped at most once.
5. **Yards:** R3 big gain → R6 floor → defensive caps (D3, C5). Defensive
   caps win.
6. **Spot:** offense (W3, then W5) then defense (L3, then S1). Each side changes
   the spot at most once, and the defense has the last word: a defensive spot
   perk checks the offense's result and may override it (Hold the Line can stop a
   Move the Sticks catch short; Last Line can stop a Pylon Reach touchdown).
7. **Clock**, then **cards:** the played card cycles (R4 replaces the cycle),
   then offensive card perks, then defensive ones.

### Perk draws and the end-of-drive reset

Perk draws have no hand ceiling. Every drive's end resets the offense's
offensive hand to 3 and the defense's defensive hand to 2 (decision 4), so extra
cards last for the rest of that drive.

### Randomness and save data

- Only the match RNG (`FootballMatchSimulator.rng`) is used. It is drawn only
  when a perk's condition holds: R3 (one roll), W2 (one roll), W6/D4/C4 (pick a
  random card). D5 and S6 change the odds of existing rolls. Deck RNGs are
  untouched except through the existing draw/reshuffle helpers.
- All perk state can be rebuilt from the saved event history. The only
  addition: each event records the typed perk activations that fired on it.
  That needs a schema bump and a migration (see §6).

## 3. Perks by position

Column key: **Req.** = partner required. **Tier** = fires per team per game
(baseline AI decks; deck-tuned estimate in brackets where a focused deck
changes it a lot). **New?** = needs a new system.

### QB

QB contributes to Play-Action (with RB), Medium (with O-line), and Deep
(with WR). Tiers: 2 frequent, 2 moderate, 2 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Q1 `qb_rb_mesh_reader` Mesh Reader | RB | Mesh Read | Completed PA: pull an RB Run card into hand (1/drive) | Your Play-Action Pass is completed. | After the card cycles, the first RB Run-family card in your draw pile (else discard) joins your hand as an extra card. Nothing if none. | Once per drive. | Yes (PA) | Cards | Moderate 2.0 [~3] | No | Play-action sets up the run. Wants PA cards plus a few runs; pairs with Ground and Pound. |
| Q2 `qb_rb_option_ledger` Option Ledger | RB | Option Ledger | 4th different play family in a drive: draw 2 (1/game) | You snap your 4th different play family in one drive. | Draw 2 offensive cards. | Once per game. | No | Cards | Rare 1.0 | No | Rewards a varied playbook: the opposite pull from family-focus perks. |
| Q3 `qb_wr_boundary_captain` Boundary Captain | WR | Hurry-Up Captain | Final 3:00 of a half: QB completions use 8 seconds | A pass the QB contributes to (PA, Medium, Deep) is completed with ≤180 s left in period 1 or 2. | The play uses 8 s instead of its card duration (never more than the card would). | Every such play; regulation only. | No | Clock | Frequent 2.7 | No | Adds 1–3 late-half snaps. Different from Tempo Install (−10% on every play). |
| Q4 `qb_wr_vertical_architect` Vertical Architect | WR | Shot Setup | Deep incompletion: next Deep this half -12% incomplete | Your Deep Pass is incomplete. | Your next Deep Pass this half gets −12 pp incompletion (12% floor). | One charge; clears at halftime, OT start, or when used. | Yes (Deep) | Turnovers / big plays | Moderate 1.8 | No | Makes a second Deep card worth holding after a miss. Wants 2+ Deep cards. |
| Q5 `qb_oline_pocket_anchor` Pocket Anchor | O-line | Pocket Presence | From snap 5 of a drive: QB +5 power | The 5th and later snaps of a drive (not two-point attempts). | QB +5 power on those snaps. | Rest of the drive. | No | Stats (QB's one generic bump) | Frequent 4.1 drives (~10 QB snaps) | No | Rewards long drives and ball control. |
| Q6 `qb_oline_silent_count` Silent-Count Caller | O-line | Silent Count | 3rd/4th down vs a counter: ignore it (1/half) | A 3rd- or 4th-down snap where the active scheme counters your play's family. | Treat the snap as not countered: no ×1.12 / ×0.96, no −0.5 yd, no +4 pp incompletion or +0.5 pp turnover. | Once per half. | No | Stats (matchup) | Rare 0.8 | No | Lets you call your best card into a counter on the money down. |

### RB

RB contributes to RB Run (with O-line), Play-Action (with QB), and Short
(with WR). Tiers: 3 frequent, 3 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 `rb_qb_checkdown_back` Checkdown Back | QB | Checkdown | After a QB incompletion: next RB play +2 yards | A pass the QB contributes to is incomplete. | If your next snap this drive is an RB play (Run, PA, Short) and not a turnover, it gains +2 yards. | Next snap only; no per-drive limit. | Yes (trigger needs QB) | Yards | Frequent 2.3 | No | A missed shot becomes a planned checkdown. Hold a Short or Run card behind Deep calls. |
| R2 `rb_qb_option_keeper` Option Keeper | QB | Keep Read | PA on 3rd/4th or 2-pt: no inc or INT roll (1/half) | Your PA Pass on 3rd or 4th down, or as a two-point attempt. | No incompletion or interception roll; use the RB Run fumble chance (1.2% base, 0.3–8%) instead. Yards unchanged. | Once per half (overtime is one half; a 2-pt try counts in its touchdown's half). Was once per drive (§0.13). | Yes (PA) | Turnovers / big plays | Rare 0.6 [~1.5] | No | PA becomes the safe money-down call and a near-sure two-point play. |
| R3 `rb_wr_orbit_runner` Orbit Runner | WR | Orbit Breakaway | Completed Short pass: 25% chance of +8 yards (1/half) | Your Short Pass is completed. | Roll: 25% chance of +8 yards (25 cap; defensive caps apply after). | Once per half; spent only when it hits. | Yes (Short) | Turnovers / big plays | Rare 1.0 | No | The one random big-play perk; Short cards become a home-run threat. |
| R4 `rb_wr_slot_outlet` Slot Outlet | WR | Outlet Repeat | Short pass first down: keep the card (1/drive) | Your Short Pass earns a first down (or TD). | The card returns to your hand instead of the discard pile; no replacement draw. | Once per drive. | Yes (Short) | Cards | Frequent 2.6 | No | Repeat your best Short card; strong with few Short copies. |
| R5 `rb_oline_gap_runner` Gap Runner | O-line | Downhill | RB Run after an RB play: +1 yard (+2 after a run) | Your RB Run on the snap right after an RB play (Run, PA, Short) in the same drive. | +1 yard, or +2 if that previous snap was an RB Run. Not on turnovers. | Every such snap. | Yes (RB Run) | Yards | Frequent 2.7 [~5 run-heavy] | No | Rewards run-heavy sequencing; can stack with Ground and Pound. |
| R6 `rb_oline_pull_guard_back` Pull-Guard Back | O-line | Fall Forward | RB Run under 1 yard gains 1 instead (1/drive) | Your non-turnover RB Run would gain under 1 yard (including losses). | It gains exactly 1 yard (this also prevents a safety). | Once per drive. | Yes (RB Run) | Yards | Rare 0.7 | No | Short-yardage and backed-up insurance; pairs with Pull Lead. |

### WR

WR contributes to Screen (with O-line), Short (with RB), and Deep (with QB).
Tiers: 2 frequent, 1 moderate, 3 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W1 `wr_qb_route_technician` Route Technician | QB | Hot Route | Drive start: swap your weakest countered card | Your first offensive decision of each drive, if the active scheme counters a card in your hand. | Before you choose, the countered card with the lowest expected yards (ties: leftmost) is discarded and replaced from your draw pile. | Once per drive. | No | Cards | Frequent 2.4 | No | Automatic hand fix against counters. Less need for Challenge or Draw bonuses. |
| W2 `wr_qb_vertical_threat` **Field Stretcher** (was Vertical Threat) | QB | Contested Catch | Failed Deep pass: reroll the catch (1/game) | Your Deep Pass rolls incomplete or intercepted. | Reroll the completion roll once with the same odds; yards are kept. The second result stands. | Once per game (the first failure). | Yes (Deep) | Turnovers / big plays | Rare 0.9 | No | One free retry on a deep shot. The rename avoids clashing with the Vertical Threat coach upgrade. |
| W3 `wr_rb_screen_outlet` **Chain Mover** (was Screen Outlet) | RB | Move the Sticks | Short catch 2 yds or less shy: move the chains (1/half) | Your completed Short Pass ends ≤2 yards short of the line to gain (any down, not goal-to-go). | It gains exactly enough to reach the line: first down. | Once per half. | Yes (Short) | Yards / field | Rare 0.9 | No | The pair plays Short, not Screen, hence the rename. Opposes Hold the Line. |
| W4 `wr_rb_motion_receiver` Motion Receiver | RB | Motion Jump | First WR play of each drive: WR +8 power | The first snap of each drive the WR contributes to (Screen, Short, Deep). | WR +8 power that snap. | Once per drive. | No | Stats (WR's one generic bump) | Frequent 5.2 | No | A reliable opener; lead drives with a WR card. |
| W5 `wr_oline_boundary_route` Boundary Route | O-line | Pylon Reach | WR catch ending inside the 5 scores (1/game) | Your completed pass the WR contributes to would end at the rival 1–4 (field position 95–99.9) without scoring. | It is a touchdown. | Once per game. | No | Yards / field | Rare 0.6 | No | A guaranteed red-zone finish once a game. |
| W6 `wr_oline_release_specialist` Release Specialist | O-line | Release Read | Screen of 8+ yds: rival swaps a random scheme (1/drive) | Your completed Screen Pass gains 8+ yards. | The rival discards a random scheme from its defensive hand and draws a replacement. The active scheme is unaffected. | Once per drive. | Yes (Screen) | Cards | Moderate 1.7 | No | Burns the scheme the rival was saving. Works on the human's hand when the AI has it. |

### O-line

O-line contributes to RB Run (with RB), Screen (with WR), and Medium (with
QB). Tiers: 3 frequent, 1 moderate, 2 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| O1 `oline_qb_pass_set_guard` Pass-Set Guard | QB | Pass Pro | First QB interception each game is incomplete instead | A pass the QB contributes to would be intercepted. | It is incomplete instead (5 s, the down advances). | Once per game. | Yes (QB contributes) | Turnovers / big plays | Rare 0.4 | No | Erases one pick outright. Different from Ball Security Clinic (−20% risk on every pass). |
| O2 `oline_qb_pocket_tempo` Pocket Tempo | QB | Tempo Read | Medium pass first down: draw 1 (1/drive) | Your Medium Pass earns a first down. | Draw 1 offensive card. | Once per drive. | Yes (Medium) | Cards | Frequent 2.8 | No | Medium passes become card engines; wants several Medium cards. |
| O3 `oline_rb_drive_blocker` Drive Blocker | RB | Four-Minute Drill | Leading in 2nd half: RB Runs use +10 seconds | Your non-turnover RB Run in period 2 while you lead. | +10 s clock. | Every such run. | Yes (RB Run) | Clock | Moderate 1.3 [~3 run-heavy] | No | A closer. Like Huddle Up (+10% on all plays) but only when it helps. |
| O4 `oline_rb_pull_guard` Pull Guard | RB | Pull Lead | 3rd/4th & 3 or less, O-line play: O-line +10 power | 3rd or 4th down with ≤3 to go, on a play the O-line contributes to (Run, Screen, Medium). | O-line +10 power that snap. | Every such snap. | No | Stats (O-line's one generic bump) | Frequent 2.8 | No | Short-yardage specialist. Different from Option / Spread (+1 yard on 4th down). |
| O5 `oline_wr_screen_setter` Screen Setter | WR | Screen Wall | Completed Screen: rival D-line -8 power this drive | Your Screen Pass is completed. | Rival D-line −8 power on every later snap this drive where it contributes (rival Run, Screen, or Medium scheme). | Once per drive; ends on possession change. | Yes (Screen) | Stats (rival) | Frequent 3.3 (~8 affected snaps) | No | Screens slow the rush; follow with Runs and Medium passes. |
| O6 `oline_wr_space_creator` Space Creator | WR | Breathing Room | Drive starts at your 20 or worse: +5 yards | Your drive starts at or inside your own 20 (returns, punts, turnovers, missed-FG spots). | The ball moves 5 yards upfield before the first snap; still 1st & 10. | At drive start; never in OT (touchbacks start at the 25). | No | Yards / field | Rare 0.8 | No | Backed-up insurance; applies after return-lane upgrades. |

### D-line

D-line contributes to Run (with LB), Screen (with CB), and Medium (with S)
schemes. Tiers: 2 frequent, 2 moderate, 2 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D1 `dline_lb_a_gap_plug` A-Gap Plug | LB | Hold the Front | Run-scheme drive ends without a TD: keep the scheme | A rival drive against your Run-family scheme ends without a touchdown. | That scheme card returns from discard to your hand as an extra card (the end-of-drive trim may still discard it). | Once per rival drive. | Yes (Run scheme) | Cards | Rare 0.5 [~1.5] | No | Rewards stocking Run-family schemes (Bear Front, Goal-Line Front). |
| D2 `dline_lb_edge_setter` Edge Setter | LB | Edge Set | Rival's first snap of each drive: D-line +8 power | The rival's first snap of each drive, when your D-line contributes (Run, Screen, Medium scheme). | D-line +8 power that snap. | Once per rival drive. | No | Stats (D-line's one generic bump) | Frequent 2.8 | No | Wins the opening snap of every rival drive. |
| D3 `dline_cb_contain_end` Contain End | CB | Contain | Screens vs your D-line schemes gain at most 6 yards | A rival Screen Pass is completed when your D-line contributes. | The gain is capped at 6 yards. | Every such snap. | No | Yards (cap) | Moderate 1.8 | No | Screen insurance without needing a Screen scheme in hand. |
| D4 `dline_cb_rush_contain` Rush Contain | CB | Collapse | 3rd-down stop: rival swaps a random play (1/drive) | A rival 3rd-down snap ends with no first down, turnover, or score. | The rival discards a random offensive card and draws a replacement. | Once per rival drive. | No | Cards | Frequent 2.3 | No | Strips the card the rival saved for 4th down; works on the human too. |
| D5 `dline_s_interior_rusher` Interior Rusher | S | Kick Rush | Rival punts, FGs, and PATs: +8% block chance | The rival attempts a punt, field goal, or extra point. | +8 pp block chance (base 0.7% / 0.5% / 0.3%), then the kicker's block-risk reduction. Uses the existing blocked-kick recovery and return rules. | Every attempt. | No | Turnovers / big plays | Rare 0.3 blocks | No | A true special-teams moment; counters Clean Pocket Protection. |
| D6 `dline_s_stunt_tackle` Stunt Tackle | S | Stunt Sack | QB incompletion vs D-line scheme: sack, -5 (1/drive) | A rival pass the QB contributes to would be incomplete when your D-line contributes. | It becomes a sack: −5 yards, the card's full clock, the down advances. A sack into the end zone is a safety. | Once per rival drive. | No | Yards | Moderate 1.8 | No | Turns an empty down into lost field position and FG range. |

### Linebackers

Linebackers contribute to Run (with DL), Play-Action (with S), and Short
(with CB) schemes. Tiers: 3 frequent, 1 moderate, 2 rare. All six are solo;
LB is the flexible position.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L1 `lb_dline_front_fit_back` Front-Fit Back | D-line | Fit & Shed | Rival gains 2 or less: draw a scheme (1/drive) | A rival non-turnover snap gains ≤2 yards (incompletions count) when your linebackers contribute. | Draw 1 defensive scheme. | Once per rival drive. | No | Cards | Frequent 2.1 | No | Gets more scheme choices into the hand; pairs with Read Keys. |
| L2 `lb_dline_run_fit_captain` Run-Fit Captain | D-line | Captain's Adjustment | Rival run first down: LB +8 power rest of drive | The rival earns a first down with an RB Run. | Linebackers +8 power for the rest of that rival drive, when they contribute. | Once per rival drive. | No | Stats (LB's one generic bump) | Frequent 2.5 | No | The defense adjusts after being gashed. |
| L3 `lb_cb_nickel_rover` Nickel Rover | Cornerbacks | Hold the Line | 3rd/4th-down first down by <2 yds: stop short (1/half) | A rival 3rd- or 4th-down snap would earn a first down by under 2 yards (not a TD). | The ball is spotted 0.5 yards short of the line: no first down. | Once per half. | No | Yards / field | Rare 0.7 | No | A goal-line-stand moment. Opposes Move the Sticks, Pull Lead, and Option / Spread. |
| L4 `lb_cb_hook_curl_reader` Hook-Curl Reader | Cornerbacks | Read Keys | See the rival's play hand when you pick a scheme | You choose a defensive scheme (start of each rival drive). | The rival's offensive hand is shown to you while you choose. AI (Standard/Hard) favors schemes that counter the revealed cards; Easy ignores it. | Every rival drive. | No | Cards (information) | Frequent 5.3 | **Yes**: rival-hand reveal UI and hand-aware AI scheme choice | Turns the once-per-drive scheme pick into a real read. |
| L5 `lb_s_robber_backer` Robber Backer | Safeties | Short Field | Rival punts or fails on 4th: your drive +5 yards | A rival drive ends in a punt or a turnover on downs. | Your next drive starts 5 yards further upfield, after any return (max field position 99). | Your next drive only. | No | Yards / field | Moderate 1.1 | No | Like Punt Return Lane, but also covers fair catches, touchbacks, and downs. |
| L6 `lb_s_green_dog_blitzer` Green-Dog Blitzer | Safeties | Green Dog | Rival converts 3rd/4th: swap your scheme (1/game) | The rival converts a 3rd or 4th down. | You may swap the active scheme for one in your hand; the old one is discarded and you draw a replacement. AI swaps when its best hand scheme outscores the active one. | Once per game; offered on each conversion until used. | No | Cards | Rare 1.0 | **Yes**: mid-drive scheme change (the engine forbids it today) and a prompt | The only mid-drive adjustment in the game. |

### Cornerbacks

Cornerbacks contribute to Screen (with DL), Short (with LB), and Deep (with S)
schemes. Tiers: 3 frequent, 1 moderate, 2 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 `cb_dline_edge_corner` Edge Corner | D-line | Keep It Inbounds | Leading in 2nd half: rival completions +6 seconds | You lead in period 2 and a rival pass is completed. | The play uses +6 s of clock. | Every such play. | No | Clock | Frequent 7.0 | No | Defensive closer; can't overlap with Four-Minute Drill on the same snap. |
| C2 `cb_dline_force_corner` Force Corner | D-line | Force & Fold | Your Screen schemes also counter RB Runs | A rival RB Run against your Screen-family scheme. | The run counts as countered: ×1.12 defense, ×0.96 offense, −0.5 yards, +0.5 pp fumble. Run Stop's −2 doesn't apply. | Every such snap. | Yes (Screen scheme) | Stats (matchup) | Moderate 1.1 | No | Screen schemes stop being run-soft; wants Screen schemes. |
| C3 `cb_lb_nickel_matcher` Nickel Matcher | Linebackers | Nickel Lock | 3rd down vs your CB scheme: CB +8 power | A rival 3rd-down snap when your cornerbacks contribute (Screen, Short, Deep scheme). | Cornerbacks +8 power that snap. | Every such snap. | No | Stats (CB's one generic bump) | Frequent 2.9 | No | A money-down stopper. |
| C4 `cb_lb_underneath_bracket` Underneath Bracket | Linebackers | Bracket | Short incompletion: rival discards a play (1/game) | A rival Short Pass is incomplete when your cornerbacks contribute. | The rival discards a random offensive card with no replacement; its hand stays one card smaller until its drive ends. | Once per game. | No | Cards | Rare 0.7 | No | The strongest hand attack among perks, so it is once per game. |
| C5 `cb_s_deep_half_corner` Deep-Half Corner | Safeties | Deep Lock | Your Deep schemes: rival catches gain at most 10 | A rival completion while your Deep-family scheme is active. | The gain is capped at 10 yards (after any offensive bonus). | Every such snap. | Yes (Deep scheme) | Yards (cap) | Frequent 2.1 [more in Deep-scheme decks] | No | "I drafted Deep-Half Corner, so I want more Deep Coverage schemes." |
| C6 `cb_s_trail_corner` Trail Corner | Safeties | Bait & Jump | Allow a Deep catch: next rival Deep +8% INT (1/half) | The rival completes a Deep Pass against you. | The rival's next Deep Pass this game gets +8 pp interception chance. | One charge; renewed by each allowed Deep catch; survives halftime. The payoff applies at most once per half (overtime is one half). Was every charged Deep pass (§0.13). | No | Turnovers / big plays | Rare payoff: arms ~4.4×, ~0.35 extra INTs | No | Corners bait the throw. Works alongside Pressure / Blitz on matched passes. |

### Safeties

Safeties contribute to Play-Action (with LB), Medium (with DL), and Deep (with
CB) schemes. Tiers: 2 frequent, 1 moderate, 3 rare.

| Player | Partner | Perk | Card line | Trigger | Effect | Duration / limit | Req. | Type | Tier | New? | Design note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 `s_dline_post_safety` Post Safety | D-line | Last Line | Rival TD from 5+ yds out: stopped at the 1 (1/game) | A rival snap from outside your 5 (field position ≤95) would score a touchdown. | The runner is stopped at your 1: first down if the line to gain was crossed, otherwise the next down. | Once per game. | No | Yards / field | Rare 0.7 | No | A goal-line stand; decisive in sudden death. |
| S2 `s_dline_blitz_safety` Blitz Safety | D-line | Safety Blitz | 2nd/3rd-down pass vs Medium scheme: +10% inc, +2 on catch | A rival pass on 2nd or 3rd down against your Medium-family scheme. | +10 pp incompletion, but completed passes gain +2 yards. | Every such snap. | Yes (Medium scheme) | Turnovers / big plays | Frequent 3.0 | No | A boom-or-bust blitz; wants Medium-family pressure schemes. |
| S3 `s_lb_box_safety` Box Safety | Linebackers | Downhill Fill | Rival RB Run vs your S scheme: safety +10 power | A rival RB Run when your safeties contribute (PA, Medium, Deep scheme). | Safeties +10 power that snap. | Every such snap. | No | Stats (S's one generic bump) | Frequent 3.7 | No | Pass-coverage schemes stop being run-soft. |
| S4 `s_lb_robber_safety` Robber Safety | Linebackers | Tip Drill | 3rd/4th-down incompletion becomes an INT (1/game) | A rival pass on 3rd or 4th down is incomplete when your safeties contribute. | It becomes an interception at the line of scrimmage; Ball-Hawk's +10 return applies. | Once per game. | No | Turnovers / big plays | Rare 0.5 | No | A guaranteed takeaway moment. |
| S5 `s_cb_boundary_safety` Boundary Safety | Cornerbacks | Sudden Change | Your takeaway: draw 1 play card for your drive | Your defense makes a takeaway (interception, fumble, or turnover on downs, including perk-made ones). | Draw 1 offensive card. | Every takeaway. | No | Cards | Moderate 1.2 | No | Defense feeds offense; pairs with Tip Drill and Bait & Jump. |
| S6 `s_cb_range_safety` Range Safety | Cornerbacks | Range Denial | Rival field goals kick as if 7 yards longer | The rival attempts a field goal. | Success is computed as if the kick were 7 yards longer (37 yd: 74% → 62%). AI field-goal choices use the same number. | Every attempt. | No | Yards / field (FG range) | Rare 0.4 attempts | No | Pushes rivals to go for it; a counter to Field-Goal Lab. |

## 4. Uniqueness check

Trigger pattern + effect pattern for all 48. **No two rows share both.**
Effect patterns that appear twice (marked ²) always have different triggers.

| ID | Trigger pattern | Effect pattern |
|---|---|---|
| Q1 | Own PA completed | Pull a family card from deck ² (pull) |
| Q2 | 4th distinct family in a drive | Draw 2 offensive |
| Q3 | QB completion in the final 3:00 | Clock set to 8 s |
| Q4 | Own Deep incomplete | Charge: −pp incompletion on a family |
| Q5 | Drive snap 5+ | Own power, rest of drive (QB generic) |
| Q6 | 3rd/4th down vs counter | Cancel counter |
| R1 | QB incomplete → next RB snap | +2 yards next snap |
| R2 | PA on 3rd/4th or 2-pt | Swap pass risk for fumble risk |
| R3 | Own Short completed | Chance of +8 yards |
| R4 | Own Short first down | Keep played card |
| R5 | RB Run after RB play | +1/+2 yards that snap |
| R6 | Own run under 1 yard | Yard floor |
| W1 | Drive start with countered card | Swap own card |
| W2 | Own Deep fails | Reroll completion |
| W3 | Own Short short by ≤2 | Move to the line to gain |
| W4 | First WR snap of a drive | Own power, that snap (WR generic) |
| W5 | Own WR catch ends at the 1–4 | Spot into the end zone |
| W6 | Own Screen 8+ yards | Rival defensive churn ² |
| O1 | Own QB pass intercepted | INT → incomplete |
| O2 | Own Medium first down | Draw 1 offensive ² |
| O3 | Own run while leading, period 2 | +10 s clock ² |
| O4 | Own O-line snap on 3rd/4th & ≤3 | Own power, that snap (O-line generic) |
| O5 | Own Screen completed | Rival power −, rest of drive |
| O6 | Own drive starts ≤ own 20 | Drive start +5 ² |
| D1 | Rival drive vs Run scheme ends without TD | Keep played scheme ² (keep) |
| D2 | Rival's first snap of a drive | Own power, that snap (DL generic) |
| D3 | Rival Screen completed | Yard cap 6 ² |
| D4 | Rival 3rd-down stop | Rival offensive churn ² |
| D5 | Rival kick attempt | +pp block chance |
| D6 | Rival QB pass incomplete | Incomplete → sack |
| L1 | Rival gain ≤2 | Draw 1 defensive |
| L2 | Rival run first down | Own power, rest of drive (LB generic) |
| L3 | Rival 3rd/4th conversion by <2 | Spot short of the line |
| L4 | Scheme selection | Reveal rival hand |
| L5 | Rival punt or downs | Next drive start +5 ² |
| L6 | Rival 3rd/4th conversion | Swap active scheme |
| C1 | Rival completion while leading, period 2 | +6 s clock ² |
| C2 | Rival run vs Screen scheme | Create counter |
| C3 | Rival 3rd-down snap | Own power, that snap (CB generic) |
| C4 | Rival Short incomplete | Rival discard, no replacement |
| C5 | Rival completion vs Deep scheme | Yard cap 10 ² |
| C6 | Rival Deep completion | Charge: +pp INT on a family |
| S1 | Rival TD from outside the 5 | Spot at the 1 |
| S2 | Rival 2nd/3rd-down pass vs Medium scheme | +pp incompletion with +yards (tradeoff) |
| S3 | Rival run vs safety scheme | Own power, that snap (S generic) |
| S4 | Rival 3rd/4th-down incomplete | Incomplete → INT |
| S5 | Own takeaway | Draw 1 offensive ² |
| S6 | Rival FG attempt | FG distance +7 |

Patterns used twice: draw 1 offensive (O2 / S5), clock + seconds (O3 / C1),
drive start +5 (O6 / L5), yard cap (D3 / C5), rival churn (W6 defensive hand /
D4 offensive hand), keep card (R4 play / D1 scheme). Q1's "pull" is distinct
from a random draw.

**Per-position checks**

| Position | Generic own +power perks | Effect types present (S / C / Y / T) | Partner-required |
|---|---|---|---|
| QB | 1 (Q5) | S, C, Y, T | 2 |
| RB | 0 | C, Y, T | 6 |
| WR | 1 (W4) | S, C, Y, T | 3 |
| O-line | 1 (O4); O5 is a rival debuff | S, C, Y, T | 4 |
| D-line | 1 (D2) | S, C, Y, T | 1 |
| Linebackers | 1 (L2) | S, C, Y | 0 |
| Cornerbacks | 1 (C3) | S, C, Y, T | 2 |
| Safeties | 1 (S3) | S, C, Y, T | 1 |

**Coach overlap check.** No perk repeats a coach perk or coach upgrade.
Closest neighbors, which complement rather than copy:

| Perk | Neighbor | Difference |
|---|---|---|
| R5 Downhill | Ground and Pound (+3 on first run) | Later runs in a sequence; can stack |
| O4 Pull Lead | Option / Spread (+1 yd on 4th) | Power, 3rd and 4th, ≤3 to go |
| C2 Force & Fold | Run Stop (−2 on matched run) | Creates a counter; Run Stop doesn't fire |
| S2 Safety Blitz / C6 Bait & Jump | Coverage / Pressure (+5 pp on matched pass) | Down- or history-based; S2 has a downside |
| S4 Tip Drill | Ball-Hawk (+10 INT return) | Creates the pick; Ball-Hawk adds the return |
| O1 Pass Pro | Ball Security Clinic (−20% INT) | One full erase per game |
| Q3 Hurry-Up Captain | Tempo Install (−10% clock) | Late halves only, fixed 8 s |
| O3 Four-Minute Drill | Huddle Up (+10% clock) | Runs only, only when leading |
| L5 Short Field | Punt Return Lane (+2) | Covers fair catches, touchbacks, and downs |
| S6 Range Denial | Field-Goal Lab (+5%) | Opposite side; affects the rival |
| D5 Kick Rush | Clean Pocket Protection (−25%) | Opposite side; they offset |

## 5. Balance notes

### How the tiers were measured

A read-only scratch script (not in the repo:
`/private/tmp/claude-501/-Users-jackmarshall--claude-spares-spare-CB0C8x/cee5b61b-cfee-4c90-b880-49bcb1a93a86/scratchpad/perk_freq.py`)
played 2,000 seeded AI-vs-AI games: Standard against a random difficulty, with
decks for a random game 1–10. It recorded every snap with its pre-snap state
and hands, then counted each trigger per team per game after its limit. It
counts trigger conditions only; perk effects were not simulated, so they would
shift some rates slightly (for example, Pylon Reach adds touchdowns).

Baseline per team per game: 42.7 snaps, 5.33 drives, 2.66 TDs, 0.72 punts,
0.36 FG attempts, 0.67 INTs, 0.09 fumbles, 0.18 two-point tries, 5.9
third-down snaps (3.3 converted). The longest observed gain was 22.3 yards, so
"20+ yard TD" style triggers never fire. Families: Short 19%, Medium 20%,
Screen 18%, Deep 18%, Run 16%, PA 10%. The AI rarely runs or calls PA, so
run- and PA-keyed perks read low here and will fire more in a human deck built
around them (bracketed estimates).

### Strongest (watch first)

| Perk | Why |
|---|---|
| S1 Last Line | Saves about 4–6 points once a game; can decide sudden death. |
| W5 Pylon Reach | Turns about 0.6 stalled red-zone trips into TDs. |
| R2 Keep Read | A PA two-point try almost never fails (PA gains about 9 yards; it needs 2). |
| L4 Read Keys | Information on every rival drive. |
| O5 Screen Wall | About 8 snaps × about 1.3 yards ≈ 10 yards per game. |
| C5 Deep Lock | About 2 capped catches × about 2.5 yards, and it changes rival play choice. |
| C4 Bracket | Permanent −1 rival hand until the next redeal. |

### Weakest (may need a bump)

| Perk | Why |
|---|---|
| D5 Kick Rush | About 0.3 blocks per game; offense dominates and punts are rare. |
| S6 Range Denial | About 0.4 rival FG attempts per game. |
| O1 Pass Pro | About 0.4 picks per game to erase. |
| D1 Hold the Front | 0.5 per game unless the deck is full of Run schemes. |
| R6 Fall Forward | About 0.7 per game, worth about +1.5 yards each. |

### Risky interactions

- **Enlarged hands.** Q1, Q2 (2 cards), O2, and S5 add cards on top of the
  uncapped Draw bonus cards; the end-of-drive reset returns hands to 3 and 2.
- **Hand attrition.** C4 (no replacement) plus the Opponent Discard bonus card,
  D4, and W6 can empty a rival hand and force the basic-run or run-fit
  fallback, for the AI and the human alike.
- **Counter rules.** Q6 cancels counters, including one created by C2. Coach
  perks that check matching still follow the play and scheme families (open
  question).
- **Two-point tries.** R2 makes PA two-point tries nearly automatic. The AI
  goes for two only when down 1–2 late, so it would under-use R2.
- **Clock stacking.** Q3 (offense, 8 s) and C1 (defense leading, +6 s) can
  both apply: 14 s. O3 and C1 can never both apply on one snap.
- **Overtime.** S1 and L3 can extend sudden death, and W5 can end it. A D6
  sack inside your own 5 can be a game-ending safety in OT.
- **Challenge.** Challenge restores football state but keeps decks, so card
  effects from a challenged play stay, and perk uses are not refunded.

### Starting values to revisit in playtesting

| Value | Start | Range to try |
|---|---|---|
| Generic power bumps (Q5, W4, O4, D2, L2, C3, S3) | +5 to +10 | ±3 |
| O5 rival D-line debuff | −8, rest of drive | −5 to −10 |
| R1 / R5 / S2 additive yards | +2 / +1–2 / +2 | ±1 |
| R3 big-gain chance / yards | 25% / +8 | 15–30% / +6–10 |
| D3 / C5 yard caps | 6 / 10 | 5–7 / 9–12 |
| Q4 / S2 incompletion | −12 / +10 pp | ±4 pp |
| C6 INT bonus | +8 pp | +5 to +10 pp |
| D5 block bonus | +8 pp | +8 to +15 pp |
| S6 FG distance | +7 yd | +5 to +10 yd |
| Q3 / O3 / C1 clock | 8 s / +10 s / +6 s | ±3 s |
| O6 / L5 field position | +5 / +5 | +3 to +8 |

## 6. Implementation outline (brief)

| Area | Work |
|---|---|
| Catalog | Replace the text-only `FootballPlayerPerk` with a typed perk kind + values; keep the type IDs. Generate the card line and full rules from one source (like `football_coach_perks.py`). Test that every card line is ≤60 characters. |
| Trigger context | A pure helper that rebuilds per-team drive / half / game history from `match_events` (snap index, families used, charges, uses spent). No hidden simulator state. |
| Estimate perks | Power, counter, additive-yard, and odds perks go into `calculate_play_estimate` next to coach perks, so the AI, Hard scoring, and previews match resolution. |
| Resolution perks | Rerolls, result swaps, floors, caps, spots, and clock go into `resolve_offensive_play` in the §2 order; kick perks go into the punt, FG, and PAT paths. |
| Card perks | Small deck helpers (pull by family, keep, scheme return, rival churn, discard without replacement) built on `_cycle_played_card` and `_draw_one_into_hand`, valid for either team. |
| New systems | L4: show the rival hand during scheme choice, plus AI scoring against it. L6: a mid-drive scheme-swap decision (new awaited state or prompt), plus AI rule. |
| Save data | Add typed perk activations to `FootballMatchEvent` / `FootballPlayResult`; bump `CURRENT_SCHEMA_VERSION` with a dict-only migration (empty activations) and a restore-equals-uninterrupted test. |
| UI | Outcome-strip callouts (reuse `perk_effects` strings), live preview notes for estimate perks, card lines on draft cards and the Depth Chart, full rules in inspect panels; remove the "Planned / Inactive" label. |
| Docs | Update AGENTS.md (perks become active), SYSTEM_MAP.md, and FUTURE_WORK.md when built. |

**Suggested build order**

1. Typed catalog, card lines, and the trigger-context helper (no gameplay change).
2. Estimate perks (stats, counters, yards, odds), with AI and preview parity tests.
3. Resolution perks (rerolls, swaps, caps, spots, clock, kicks).
4. Card perks and the hand ceiling.
5. Save activations, schema bump, migration, and determinism tests.
6. UI callouts and text; remove Planned / Inactive.
7. New systems: L4 Read Keys, then L6 Green Dog.
8. Balance pass: rerun `scripts/measure_football_balance.py` with perks on and off.

## 7. Open questions (resolved in §0)

1. **L6 Green Dog** breaks the "one scheme per defensive drive" rule once per
   game. Is that acceptable, or should L6 be redesigned?
2. **L4 Read Keys** shows the AI's hand to the human (and lets the AI read the
   human's). OK as written, or show only part of the hand?
3. **Challenge:** should a challenged play refund the perk uses it spent?
   Proposed: no refund; card effects stay, as with decks today.
4. **Hand ceilings** for perk draws (6 offensive / 4 defensive): keep them, or
   leave perk draws uncapped like bonus cards?
5. **Spot precedence:** offense first and no chaining, so Pylon Reach beats
   Last Line on the same play. Or should the defense get the last word?
6. **Silent Count:** cancel only the base counter modifiers (proposed), or also
   switch off coach perks keyed to matching (Run Stop, Coverage, Pressure)?
7. **Display renames:** Vertical Threat → Field Stretcher, and Screen Outlet →
   Chain Mover. Approve?
8. **AI drafting:** keep the random specialist pick, or make the AI prefer
   partner and deck synergy now that perks matter?
9. **Keep Read on two-point tries:** keep it (encourages going for two), and
   should the AI's two-point rule account for it?
10. **Randomness:** two perks roll dice (R3 big gain, W2 reroll), and D5 / S6
    change existing odds. OK, or prefer fully deterministic versions?
11. **Halftime carry-over:** drive-scoped effects survive halftime because the
    engine continues the drive. Confirm, or end them at halftime?
12. **Tiers** come from AI-vs-AI play. After playtesting, should the "frequent"
    bar move (for example, to ≥1.5 per game)?

## 8. Implementation and first balance measurement

Implemented as outlined in §6 (typed catalog, pure trigger context, estimate
perks, resolution perks in the §2 order, card perks, Read Keys, Green Dog, AI,
save schema 2 with perk activations and the opening receiver, and the UI).
Values are the §3 starting values; none were retuned.

`python -m scripts.measure_football_balance --skip-plays --games 400 --perks off|on`
(Team A Standard against each difficulty, seed 20261114):

| Opponent | Team A win rate off → on | Combined points/game off → on | 2-pt tries/game off → on |
|---|---|---|---|
| Easy | 0.647 → 0.657 | 34.64 → 35.53 | 0.33 → 0.58 |
| Standard | 0.497 → 0.497 | 36.67 → 37.91 | 0.35 → 0.77 |
| Hard | 0.295 → 0.300 | 38.38 → 39.57 | 0.30 → 0.53 |

Perks add about one point per game and leave difficulty win rates unchanged.
Measured fires per carrying team per game mostly match their tiers. Outside
them: Bait & Jump (C6) 4.7 and Keep Read (R2) 2.8 fire far above "rare"
(C6 counts every charged Deep pass, matching its "arms ~4.4×" note; R2 is
driven by the AI's new go-for-two rule). Least frequent: Kick Rush 0.24, Range
Denial 0.26, Pass Pro 0.40, Fall Forward 0.44, Hold the Front 0.48 (the
end-of-drive trim can discard its returned scheme). Suggested follow-ups are
tracked in FUTURE_WORK.md.

### Follow-up: Bait & Jump and Keep Read once per half

Both were limited to once per half (§0.13); no other value changed. Same command
with `--perks on`, same seed:

| Measure | Before | After |
|---|---|---|
| Bait & Jump (C6) fires per carrying team per game | 4.72 | 1.91 |
| Keep Read (R2) fires per carrying team per game | 2.78 | 1.78 |
| 2-pt tries/game (Easy; Standard; Hard) | 0.58; 0.77; 0.53 | 0.46; 0.62; 0.45 |
| Team A win rate (Easy; Standard; Hard) | 0.657; 0.497; 0.300 | 0.650; 0.497; 0.310 |
| Combined points/game (Easy; Standard; Hard) | 35.53; 37.91; 39.57 | 35.54; 37.84; 39.59 |

Both are now inside the "rare" band (at most 2 per game). Bait & Jump fires in
almost every half its team plays, so it sits near its new ceiling; Keep Read is
still the most frequent rare perk after it. Win rates and scoring are unchanged
within sampling noise. Two-point tries remain above the perks-off rate
(0.33; 0.35; 0.30).
