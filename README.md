# CFB Auto-Battler

## Run the desktop shell

From the project directory, launch the resizable Pygame shell with:

```sh
python -m src.desktop
```

The desktop shell reads the same saved team profile and color palette as the
terminal client. If no profile exists, choose **Create Profile** from the menu,
enter a team name, and choose different primary and secondary colors. Use
**Settings** to edit an existing profile. Changes are saved only when you
select **Save Profile**; canceling leaves the saved profile unchanged. If a
profile cannot be loaded, the desktop does not overwrite it.
Start an offline run by choosing a local AI difficulty, selecting a coach, and
drafting one player at each of the eight positions. Before each game, visit
the shop with 12 Action Points shared across its sections; unspent points
expire when the visit ends. Call offensive plays and defensive schemes during
matches. Three losses end the run; surviving all ten regular-season games
reaches a playoffs marker, without a playoff bracket.

On the coach screen, hover over a coach or tab to their name to inspect that
side's position modifiers and perk in a scouting popup. Move between the X and
O marks to switch coaches, or move off the card to dismiss it. Choose a staff to
lock both coaches. The recruiting-room table is original generated artwork and the
X/O playbook marks are programmatically drawn in the saved team colors. Staff
buttons and scouting outlines also use the team's primary and secondary colors.
If the table artwork is unavailable, the screen logs a warning and draws a fallback.
During the player draft, hover a prospect or use Tab / arrow keys to inspect
their partnership and planned, inactive perk in a compact scouting card; move
to another prospect or outside the choice area to dismiss it. The card remains
open while the pointer moves onto it, and clicking it does not draft. Enter or
Space activates the focused draft button. The draft uses three open prospect
presentations over the playbook backdrop, with actual roster progress and
compact stat strips. Prospect choices share one enlarged full-body standing-
player illustration, generated as original artwork and stored as a transparent
base sprite with separate primary and secondary color masks so the uniform uses
the saved team colors. The purple draft controls remain a consistent UI
accent. The generic illustration is not a portrait of a real player.
Coach-screen typography uses Kalam by Indian Type Foundry and Atkinson
Hyperlegible by the Braille Institute, and Barlow by Jeremy Tribby (from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlow)), bundled
under the SIL Open Font License 1.1. The coach title uses Kalam and supporting
coach-screen and player-draft text uses Barlow; Atkinson remains in use for
other desktop UI.
Their full licenses are in `src/ui/assets/fonts/`; missing fonts fall back to
the desktop's existing UI font and produce a warning.

Desktop run state is in memory only. The desktop gameplay flow uses
`FootballGameController` and does not initialize or write to the legacy game
database.

The run UI is coordinated by `src/ui/football_run_screen.py`. Coach selection,
player draft, shop, depth-chart/playbook review, and completed-game results have
dedicated renderers in `football_coach_view.py`, `football_player_draft_view.py`,
`football_shop_view.py`, `football_review_view.py`, and `football_result.py`
under `src/ui/`. Match field, scoreboard/history, and hand/decision rendering
live in `football_match_field.py`, `football_match_status.py`, and
`football_match_decision_view.py`. The coordinator connects these views to
controller actions and shared navigation; `football_match_palette.py` holds
their shared colors.

Match hand input, scrolling and field animation state live in
`src/ui/football_match_interaction.py`; shop review mode and scrolling live in
`src/ui/football_shop_review.py`. Coach and player inspection input state lives
in `src/ui/football_draft_interaction.py`. Shared display labels and text
fitting live in `src/ui/football_display.py` and `src/ui/text.py`.

## Run the terminal client

From the project directory, start the game with:

```sh
python -m src.main
```

The first launch asks for a team name and two different colors. The saved
profile is stored outside the project in
`~/.cfb-auto-battler/profile.json` (under the current user's home directory),
so it is not tied to the current working directory or the game's SQLite
snapshot database. Profiles can also be created or edited in the desktop app.

## Application boundary

The terminal client uses `ApplicationController` in `src/application.py` for
its game flow. The desktop shell uses that boundary for saved profile and menu
data, and uses the framework-independent `FootballGameController` for its
interactive gameplay. It does not route desktop runs through the legacy game,
shop, simulator, or database persistence.

## Tests

Install the project and its test dependency in your active virtual environment
with:

```sh
python -m pip install -e ".[test]"
```

This installs Pygame Community Edition, used for the desktop shell's window,
drawing, and input handling.

Run the test suite with:

```sh
python -m pytest
```
