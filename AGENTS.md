# Project Guidance

## Current Gameplay Direction
* The game is offline-first against local AI. Asynchronous player snapshots are a later goal.
* Matches are interactive: the user chooses each offensive play and one defensive scheme at the start of each defensive drive; that scheme remains active for the drive. AI controls the side the user is not controlling.
* Offensive plays and defensive schemes are selected from separate run-owned decks. The opening playbook contains the six basic actions per side; match hands are dealt independently, played cards cycle through discard/draw, and only the human's current hand is shown as selectable in the desktop match screen. The shop can add catalog cards or permanently remove a selected owned copy, while preserving a four-card minimum per deck.
* The pre-match shop's Depth Chart and Playbook reviews are read-only except for the explicit pending-removal flow. Keep those screens tied to the current run's roster, coach assignment, upgrades, and owned deck copies.
* Drives use football downs and first downs, not a fixed number of plays.
* The roster has exactly eight player positions: QB, RB, WR, O-line, D-line, linebackers, cornerbacks, and safeties. Coach and special teams are separate from those player slots.
* Three losses end a run immediately. Surviving game 10 advances to the playoffs.
* The desktop app is the main experience; Steam and a possible Apple app are long-term goals.
* `src/engine/football_controller.py` exposes `FootballGameController` and immutable state views for the interactive flow; keep UI and framework dependencies out of this module.
* Coach selection offers three seeded, distinct offense/defense pairs from five styles per side. The selected pair is locked for the run; position bonuses and active typed perks resolve centrally in the simulator, with defensive positions determined by the selected scheme even on a mismatch. Ground and Pound triggers on the first RB Run attempt per offensive drive; Run Stop triggers only on RB Run against the RB Run scheme. Ball-Hawk adds 10 interception-return yards and scores a defensive touchdown immediately if the return reaches the opponent's goal line. Option / Spread adds 1 yard to a non-turnover run or completed pass when the offense goes for it on fourth down; this value is provisional for later balance work. Match actions are limited to the current hand, with an empty-hand basic-action fallback. Player perks remain informational and must be labeled planned/inactive.
* Regulation uses two 900-second periods. Offensive card durations are read from their definitions; incomplete passes use five seconds, turnovers use the played card's duration, punts and kickoffs use ten seconds, field goals use five seconds, conversions are untimed, and other actions without an assigned duration do not consume clock. A two-point attempt uses a legal card in the acting team's current hand (or the basic-run fallback when empty) and cycles that card. After a defensive conversion return, the original touchdown team kicks. Blocked punts and field goals resolve automatic recovery/return outcomes, including a possible defensive return touchdown and conversion. Kicking-team recoveries are modeled at or behind the original line of scrimmage; because they occur on fourth down and no forward recovery is simulated, they are turnovers on downs at the mirrored recovery spot, not automatic first downs.

The existing auto-battler engine, controller, shop, and snapshot code are legacy reference implementations, not gameplay compatibility requirements. Reuse them only where they fit the current direction. Do not infer redesigned mechanics from their old behavior.

See [FUTURE_WORK.md](FUTURE_WORK.md) for deferred redesign work and open decisions; update it when work is completed or the design changes.

## Development and Tests
* Supported Python version: 3.10 or newer.
* Install the test dependency with `python -m pip install -e ".[test]"`.
* Run the automated tests with `python -m pytest`.
* Tests use temporary SQLite databases and never access the local game database.
