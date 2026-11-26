# Future Work

This tracker records unfinished redesign work and open decisions. It is not a
commitment to implement every idea as written. Update it when work is completed
or the design changes.

## Player redesign

- [x] Propose and approve six specialized player types per position, plus a
  basic type. Each specialist has a same-side partner position and a distinct
  proposed perk; the basic type has neither.
- [x] Agree on the partnership bonus and its stacking formula, including the
  130% cap for combined coach and player partnership bonuses.
- [x] Implement the approved player catalog, draft offers, partnership effects,
  AI roster generation, and player-selection UI.
- [x] Review and approve the proposed player perks. Initially, show them as
  text only; their effects do not execute in matches.
- [x] Redesign the specialist perks so each one meaningfully interacts with
  play calling, cards, yards, clock, or turnovers
  ([docs/player-perks-proposal.md](docs/player-perks-proposal.md)).
- [x] Make player perk descriptions fully readable: a card line on draft cards
  and Depth Chart fronts, the full rules in the draft perk box and on card backs.
- [x] Implement the approved player perk effects for both teams, with typed
  activations on match events, outcome-strip callouts, Play Log entries,
  preview notes, ready/used badges, Read Keys (L4), and Green Dog (L6).
- [x] Bring Bait & Jump (C6) and Keep Read (R2) back into their Rare tier: both
  are now once per half (C6 4.7 → 1.9, R2 2.8 → 1.8 fires per game; proposal §8).
- [ ] Balance follow-up for the least frequent rare perks (proposal §8): Kick
  Rush (D5), Range Denial (S6), Pass Pro (O1), Fall Forward (R6), and Hold the
  Front (D1). Revisit after human playtesting; values are unchanged.
- [ ] Playtest the end-of-drive hand reset with Draw bonus cards, Hold the
  Front, Outlet Repeat, and Fit & Shed, whose extra cards now last one drive.
- [ ] Decide whether the AI should read Read Keys during a Green Dog swap too
  (the human's Green Dog panel already shows the revealed hand) and whether the
  Easy AI should keep using the estimate rule for Green Dog.
- [x] Define and implement the approved Option / Spread fourth-down perk:
  +1 yard on a non-turnover run or completed pass when going for it. This value
  is provisional and should be revisited during balance work.
- [ ] Revisit AI difficulty and shop upgrade balance after the player base
  ratings change. Existing offsets and upgrade values are to remain unchanged
  for the initial player redesign.

## Later game systems

- [x] Implement the recurring three-part pre-game shop framework with shared
  AP, seeded rarity offers, player upgrades, and permanent slot unlocks.
- [x] Add the individual-player Power, Stamina, and Volatility upgrade
  catalog, including run-long and next-match effects.
- [ ] Design and implement group/all-position and synergy player upgrades;
  these are deferred beyond the individual-player catalog.
- [x] Add an initial named offensive-play and defensive-scheme catalog to the
  shop, with exactly 36 offensive plays (six per family) and 24 defensive
  schemes (four per family). Preserve stable identities, family contributors,
  neutral expected-yardage estimates, play clocks, and scheme counters; retain
  six-card starter decks and the four-card deck minimum.
- [x] Add six human-only tactical bonus cards with Uncommon, Rare, and Very
  Rare shop offers, independent per-slot rarity rolls, repeatable owned copies,
  cross-deck draws, opponent-hand discards, and Challenge rollback. Keep
  Remove One Card a Rare shop-only service, not a playable deck card.
- [x] Implement match-local hands, draw/discard cycling, empty-hand fallbacks,
  period-boundary resets, a shared active-hand UI, and hand-limited AI choices.
- [x] Make offensive and defensive hands independent: every played card replaces
  itself, Draw bonus cards add one extra card with no hand-size cap, and
  halftime/overtime redeal to three and two.
- [x] Reset hands at the end of each drive: the offense's offensive hand returns
  to three and the defense's defensive hand to two (random trim with the deck's
  own RNG, or a refill), after any two-point try.
- [x] End the drive at halftime and open period 2 with a kickoff by the team
  that received the opening kickoff.
- [x] Resolve "Go For It" through a normal offensive card play using the active
  defensive scheme; failed fourth-down plays turn the ball over at the play
  spot, while punts and field goals remain separate special-teams actions.
- [x] Restore two 900-second regulation periods and apply each offensive card's
  clock duration; incomplete passes, turnovers, untimed conversions, special
  teams, and actions without a duration have explicit clock behavior.
- [x] Make two-point attempts use a legal current-hand card for both the human
  and AI, preserving deck cycling and the empty-hand basic-run fallback.
- [x] Resolve blocked punts and field goals through deterministic-seedable
  recovery and return outcomes, including return touchdowns and conversion
  sequences.
- [x] Use the same context-aware coach-perk matchup estimates in play
  resolution, Hard AI decisions, and desktop previews.
- [x] Add shop Depth Chart and Playbook review screens and a match UI for the
  human hand, card selection, matchup previews, and drag/drop calls.
- [x] Redesign the match screen: navy stadium theme, detailed scoreboard and
  field, latest-play lines colored by run/pass/other, an outcome strip that
  also holds fourth-down/conversion/Challenge calls, sequential AI playback
  with Skip, both hands visible, an ACTIVE scheme slot, deck/discard piles,
  opponent hand counts, and a pause menu with Depth Chart and Play Log.
- [x] Redesign the pre-match shop, Depth Chart, and Playbook in the match-screen
  style: cost-only price buttons, one rarity palette (Rare blue), icon-only
  player upgrade cards, coach short lines, shared play/scheme card faces, and
  hover/focus inspect panels with the full rules.
- [x] Keep purchased plays, schemes, and bonus cards visible as purchased until
  Next Day; replace the Depth Chart details page with flippable player and
  coach cards and a Team upgrades popup.
- [x] Redesign the post-game result screen in the match-screen style: full
  screen scoreboard hero, run/pass team-stat comparison from the play log, a
  10-game season tracker with a 3-strike loss meter (backed by a read-only
  per-game controller history), and distinct Run Over, Playoffs, and Bye Week
  endings.
- [x] Replace the legacy "End this run?" dialog with one pause menu on every
  run screen (KEEP PLAYING, RETURN TO MENU, two-step QUIT RUN; the match adds
  DEPTH CHART and PLAY LOG), PAUSE [ESC] buttons, and an in-memory Continue
  Run on the main menu with a replace-run confirmation.
- [x] Redesign the coach selection screen in the match-screen style: kit
  panels and stadium backdrop, Depth Chart-style modifiers, one short perk line
  per coach (shared with the Depth Chart coach cards), and hover/focus
  inspect panels with the full perk rules.
- [x] Redesign the player draft screen in the match-screen style: kit header
  and PAUSE [ESC] placement shared with coach selection, a draft tracker with
  each position's coach bonus, coached power, and partner links, candidate
  cards showing base and coached power plus a callout for an already-drafted
  partner, and display names such as "Basic O-Line" for basic players.
- [x] Save the single active run to disk so it survives closing and reopening
  the game: a versioned, checksummed JSON save in the OS app-data folder,
  written atomically after every decision and on Return to Menu or quit, with
  a rotated backup, step-by-step schema migrations, exact random-number state,
  and safe handling of missing, damaged, newer-version, and unloadable saves.
  The team profile moved to the same folder.
- [x] Move the legacy SQLite snapshot database out of the install folder (moved,
  not retired): the terminal client now opens `cfb_battler.db` in the app-data
  folder (`legacy_database_path` in `src/persistence/paths.py`), and the
  desktop never creates it. An old `data/cfb_battler.db` in the project folder
  is not migrated or used and can be deleted by hand.
- [ ] Steam Cloud: configure Steamworks Auto-Cloud for the app-data folder's
  `profile.json`, `run.json`, and `run.backup.json` on each OS, and decide on
  cloud-conflict UI. Multiple save slots are out of scope for now.
- [ ] Player-draft prospect skin tones are cosmetic UI picks, not saved; a run
  restored mid-draft re-rolls them for the current offer (drafted players keep
  their saved appearance).
- [ ] Drafted players keep the jersey colors chosen at draft time; a profile
  color edit while a run is saved recolors the UI theme on resume but not
  those saved appearances. Decide whether saved runs should follow the profile.
- [x] Give local AI opponents their own names and team colors: a 100-team
  catalog, a per-run draw of ten scheduled rivals and ten playoff reserves,
  rival colors on the match, result, bracket, and shop screens, and save
  format 4.
- [ ] AI team follow-ups: decide whether AI teams should keep persistent
  rosters or coaches across a run, whether a profile color edit mid-run should
  redraw clashing rivals (the draw only checks the color at run start), and
  whether the bracket should mark playoff rematches. Runs migrated from save
  format 3 get a fixed legacy draw, so their already-played games show that
  draw's rivals in the season tracker.
- [ ] Shop polish ideas: number-key shortcuts for shop cards, and a live-app
  pass on hover timing and keyboard flow (verified headless so far).
- [ ] Match screen polish ideas: on-card number-key hints, a play-log filter
  by drive or team, and an optional playback-speed setting.
- [x] Add the first named coach-upgrade catalog, run-unique purchase history,
  typed effects in match resolution/estimates, future-shop AP bonuses, and a
  one-time Bye Week purchase that skips a scheduled week without a match.
- [x] Make coach-upgrade effects fully inspectable in the shop and Depth Chart,
  preview live normal-play clock values, apply family yardage upgrades in the
  beneficial direction for positive and negative gains, and clarify conditional
  Field-Goal Lab probability.
- [ ] Expand the coach-upgrade catalog and tune its provisional costs and
  effect magnitudes through balance measurement and playtesting.
- [ ] Expand the play/scheme catalog toward 100+ named ideas without changing
  the six-family invariants.
- [ ] Design future player synergies and AP-saving actions. Unspent AP
  currently expires at the end of each shop visit.
- [x] Implement an eight-team, single-elimination playoff bracket after week
  10: seeding by regular-season losses, a shop before each round, tougher
  rivals each round, AI-vs-AI results, a bracket screen, CHAMPION and
  ELIMINATED endings, and save format 3.
- [ ] Tune playoff difficulty. Each round adds +0.25 rival power and one deck
  card; a Standard AI proxy's win rate fell from about 0.49 (week 10) to 0.41
  (championship) in a 400-game sample, with wide noise. Revisit after
  playtesting, and decide whether seeds should change rival strength.
- [ ] Decide whether playoff results should feed a career record, and whether
  the bracket should be viewable from the pause menu mid-shop.
- [ ] Revisit asynchronous opponents, accounts, and career history after the
  offline-first game loop is established.

## First-time player evaluation (2026-11-25)

A fresh playthrough of the desktop app plus 360 simulated runs (random,
"biggest number", and Hard-AI-logic players; shop choices were random). Goal:
one run should take 15-30 minutes, so defense stays light.

- [ ] Difficulty: simulated players rarely survive (Standard: 0/40 random,
  0/40 "biggest number", 3/40 expert runs reached the playoffs), but a human
  playtester reached the playoffs on the first try. The simulation's random
  shopping likely understates real players. Don't retune until more human
  playtests; consider a quick "try again" on the Fired screen.
- [ ] Play calling often has one obvious answer: the rival's defense is visible
  before the call, every pass family misses about 29% of the time (so Deep
  Pass is the biggest number with no extra risk), runs average 3.7 yards
  against 6.0 for a countered Deep Pass, and cards show no risk. (Risk is now
  shown: a hand card's hover/focus tooltip gives the miss or fumble chance. The
  rival's defense call is now secret, so the call is no longer obvious; the
  balance question remains open.)
- [x] Defense is one call per drive followed by watching the AI drive replay
  (up to 9 plays); keep it light, but make the one call clear and informed.
  The strip now reads "PICK ONE DEFENSE FOR THIS DRIVE" with how long it lasts
  and a scouting line from the rival's whole deck.
- [x] No onboarding: no how-to-play or first-time hints. Unexplained terms
  include counters, "matched passes", "+20% QB", volatility, stamina, AP, Day,
  partner, and PAT. Added a How to Play page, five one-time tips, and "stops" /
  "stopped" / "defense call" wording in place of counters and matched passes.
  "PAT" still appears in the conversion prompt and scoreboard (the two-point tip
  says "Kick for 1").
- [ ] Draft: prospects at a position have identical stats, so the perkless
  Basic player is always the worst pick.
- [x] Cards switched from "YDS LIVE" to "BASE YDS" on two-point tries; they now
  keep the live estimate.
- [ ] Smaller UI issues: two of three coach pairs share a coach; temporary and
  permanent upgrades look alike apart from a small icon; result-screen bar colors mix
  run/pass and team colors; no halftime moment; the "Hands & piles update
  after replay" notice covers the hand.
- [ ] Visual polish: the profile screen still uses the old grey style; the
  title says "COLLEGE FOOTBALL" while the app is "Draft Drive Football"; a
  "FOCUS" tag shows on the main menu; play and bonus card art is text codes
  ("OL+RB", "OFF DRAW").
- [ ] Measure real run length against the 15-30 minute goal (a match has about
  33 offensive calls, 6 defensive calls, and the AI drive replays).

## Secret defense calls and the perk tray (2026-11-25)

- [x] The defense call is secret from the offense (see AGENTS.md): the field,
  strip, hand, tooltip, Play Log, replays, and perk callouts never reveal the
  AI's call; previews and AI offense use `calculate_blind_play_estimate` (a
  deck-weighted average over the defender's owned calls). Read Keys still shows
  its owner the rival's hand.
- [x] The perk tray shows every drafted specialist's perk (always-on ones with
  no status dot) in two rows, with a hover tooltip and a click/Enter rules popup.
- Balance, `scripts/measure_football_balance.py --skip-plays` (300 games each,
  Team A Standard against the listed difficulty; both AIs are blind on offense
  after the change; nothing retuned):

  | Opponent | Team A win rate before → after | Points/game A; B before → after | Combined before → after |
  |---|---|---|---|
  | Easy | 0.627 → 0.623 | 19.84; 15.80 → 19.86; 15.62 | 35.64 → 35.48 |
  | Standard | 0.500 → 0.513 | 19.07; 19.23 → 19.10; 19.08 | 38.30 → 38.19 |
  | Hard | 0.317 → 0.350 | 17.03; 22.73 → 17.34; 22.30 | 39.76 → 39.64 |

  Scoring is unchanged; Hard loses a little of its edge over Standard (its
  offense no longer sees the call). The script now takes about 2 minutes
  instead of 45 seconds because each AI offensive estimate averages over the
  defender's calls.
- [ ] Watch whether Hard still feels distinct now that its offense is blind;
  revisit only after human playtests.

## Known bugs

- [x] Opponent Discard (Rare) and Offensive Draw & Discard (Very Rare) resolved
  identically. Fixed by the independent-hand rules: every card replaces itself,
  and Draw bonus cards add one extra card, so Offensive Draw & Discard now also
  draws an extra offensive card while Opponent Discard only replaces itself.
- [x] After Remove One Card is used in a shop visit, a Next Day reroll could
  offer it again. It is now excluded from rerolled offers (and new slot
  unlocks) for the rest of that visit and returns at the next visit.
