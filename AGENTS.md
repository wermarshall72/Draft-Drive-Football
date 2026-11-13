# Project Guidance

## Current Gameplay Direction
* The game is offline-first against local AI. Asynchronous player snapshots are a later goal.
* Matches are interactive: the user chooses each offensive play and one defensive scheme at the start of each defensive drive; that scheme remains active for the drive. AI controls the side the user is not controlling.
* Drives use football downs and first downs, not a fixed number of plays.
* The roster has exactly eight player positions: QB, RB, WR, O-line, D-line, linebackers, cornerbacks, and safeties. Coach and special teams are separate from those player slots.
* Three losses end a run immediately. Surviving game 10 advances to the playoffs.
* The desktop app is the main experience; Steam and a possible Apple app are long-term goals.
* `src/engine/football_controller.py` exposes `FootballGameController` and immutable state views for the interactive flow; keep UI and framework dependencies out of this module.

The existing auto-battler engine, controller, shop, and snapshot code are legacy reference implementations, not gameplay compatibility requirements. Reuse them only where they fit the current direction. Do not infer redesigned mechanics from their old behavior.

## Development and Tests
* Supported Python version: 3.10 or newer.
* Install the test dependency with `python -m pip install -e ".[test]"`.
* Run the automated tests with `python -m pytest`.
* Tests use temporary SQLite databases and never access the local game database.
