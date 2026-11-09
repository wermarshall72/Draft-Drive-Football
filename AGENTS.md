# CFB Auto-Battler: Master Rulebook & System Architecture

## 1. Core Identity & Architecture
This project is a 15-minute roguelike college football auto-battler built in Python. It merges Campus-to-Canton style roster-building with Super Auto Pets asynchronous multiplayer snapshots. 

## 2. The 8-Slot UI Board
The player manages exactly 8 unit slots. Spreadsheets are strictly avoided to ensure fast-paced, readable gameplay.
*   **Offense (4 slots):** Quarterback (QB), Running Back (RB), Wide Receiver (WR), Offensive Line (O-Line)
*   **Defense (2 slots):** Front 7, Secondary
*   **Modifiers (2 slots):** Coach (Locked at start), Special Teams

## 3. Game Progression Loop
A single run lasts ~15 minutes and follows three strict phases:
*   **Phase 1: National Signing Day (Mins 0-3).** The player selects a Coach, then spends 6 Action Points to make exactly one player pick for each position group in order: QB, RB, WR, O-Line, Front 7, and Secondary. Each pick offers 3 uniformly random players from that position's pool.
*   **Phase 2: Regular Season (Mins 3-12).** A gauntlet of ~10 games against asynchronous snapshots of real player teams. Accumulating 3 losses terminates the run ("Fired").
*   **Phase 3: The Playoffs (Mins 12-15).** A three-round, single-elimination bracket against opponent snapshots; losing any playoff match ends the run.

## 4. Coaching & Synergies (The Run Anchor)
*   At run initialization, the player selects one Coach from 3 randomized pairings (e.g., "Air Raid / Bend-Don't-Break").
*   The Coach occupies a modifier slot automatically and cannot be sold or swapped.
*   The Coach dictates mathematical synergies (e.g., +20% passing efficiency, -10% run stop rate), forcing unique roster-building archetypes every run.

## 5. The 6-Day AP Economy
*   At run start, the 6 opening Action Points each pay for one position pick. Between matches, currency is represented by Time: 6 "Days" (Action Points) per shop phase.
*   Days are spent making strategic decisions: rolling the transfer portal, practicing for stat bumps, or healing injuries.

## 6. Simulation & Match Resolution
*   Matches are entirely hands-off (true auto-battler).
*   Games simulate rapidly across 8-10 abstract "drives".
*   UI displays a visual Tug-of-War / Momentum bar.
*   Drives resolve mathematically by pitting the attacking team's Offense snapshot against the defending team's Defense snapshot, modified by Coach synergies and Special Teams rolls. Player power contributes to team strength, volatility controls drive-to-drive variance, and stamina reduces late-game fatigue.
*   Player stamina is a 0-to-1 value. Fatigue ramps linearly through a match, with a maximum 10% power reduction for zero-stamina players by the final drive; volatility is applied using the average of the players contributing to that side.

## Player Archetypes
*   The opening pool has at least six archetypes for each of the six player position groups. Each player has `power`, `volatility`, and `stamina`; the in-season portal may also offer Special Teams, but Special Teams is excluded from opening draft offers.
*   A tied match is replayed until a decisive result.

## 7. SQLite Database Schema (Async Snapshots)
The asynchronous multiplayer requires storing and fetching past player builds at specific round intervals.

**Table: snapshots**
| Column | Type | Description |
|---|---|---|
| id | TEXT (PK) | UUID for the snapshot |
| player_name | TEXT | Display name of the user |
| round_number | INTEGER | The regular season week (1-10) or playoff stage |
| wins | INTEGER | Current wins of the team when snapshot was saved |
| losses | INTEGER | Current losses of the team when snapshot was saved |
| coach_id | TEXT | Identifier for the locked Coach archetype |
| coach_data | TEXT | JSON string preserving the Coach schemes and modifiers |
| qb_data | TEXT | JSON string of QB stats, tier, and modifiers |
| rb_data | TEXT | JSON string of RB stats, tier, and modifiers |
| wr_data | TEXT | JSON string of WR stats, tier, and modifiers |
| oline_data | TEXT | JSON string of O-Line stats, tier, and modifiers |
| front7_data | TEXT | JSON string of Front 7 stats, tier, and modifiers |
| secondary_data| TEXT | JSON string of Secondary stats, tier, and modifiers |
| st_data | TEXT | JSON string of Special Teams stats, tier, and modifiers |
| created_at | TIMESTAMP| When the snapshot was submitted |

## Development and Tests
*   Supported Python version: 3.10 or newer.
*   Install the test dependency with `python -m pip install -e ".[test]"`.
*   Run the automated tests with `python -m pytest`.
*   Tests use temporary SQLite databases and never access the local game database.