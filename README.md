# CFB Auto-Battler

## Run the desktop shell

From the project directory, launch the resizable Pygame shell with:

```sh
python -m src.desktop
```

The desktop shell reads the same saved team profile and color palette as the
terminal client. If no profile exists, the menu explains how to create one.
Start an offline run by choosing a local AI difficulty, selecting a coach, and
drafting one player at each of the eight positions. Spend the six Training
Points in the one-time shop, then call offensive plays and defensive schemes
during matches. Three losses end the run; surviving all ten regular-season
games reaches a playoffs marker, without a playoff bracket.

On the coach screen, hover over a coach or tab to their name to inspect that
side's position modifiers and perk in a scouting popup. Move between the X and
O marks to switch coaches, or move off the card to dismiss it. Choose a staff to
lock both coaches. The recruiting-room table is original generated artwork and the
X/O playbook marks are programmatically drawn in the saved team colors. Staff
buttons and scouting outlines also use the team's primary and secondary colors.
If the table artwork is unavailable, the screen logs a warning and draws a fallback.
During the player draft, hover a prospect or use Tab / arrow keys to inspect
their partnership and planned, inactive perk; activate the draft button to
make the pick. The uniformed player figures are original, programmatically
drawn placeholders in the saved team colors, not production player artwork.
Coach-screen typography uses Kalam by Indian Type Foundry and Atkinson
Hyperlegible by the Braille Institute, and Barlow by Jeremy Tribby (from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlow)), bundled
under the SIL Open Font License 1.1. The coach title uses Kalam and supporting
coach-screen text uses Barlow; Atkinson remains in use for the player draft.
Their full licenses are in `src/ui/assets/fonts/`; missing fonts fall back to
the desktop's existing UI font and produce a warning.

Desktop run state is in memory only. The desktop gameplay flow uses
`FootballGameController` and does not initialize or write to the legacy game
database.

## Run the terminal client

From the project directory, start the game with:

```sh
python -m src.main
```

The first launch asks for a team name and two different colors. The saved
profile is stored outside the project in
`~/.cfb-auto-battler/profile.json` (under the current user's home directory),
so it is not tied to the current working directory or the game's SQLite
snapshot database. Choose **Settings** from the main menu to edit the profile.

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
