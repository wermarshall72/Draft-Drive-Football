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
side's position modifiers and perk. Choose a staff to lock both coaches.
The recruiting-room table is original generated artwork; the anonymous sideline
figures are original Pygame illustrations, not portraits of real coaches.
Individualized coach portrait art remains a future production asset. If the
table artwork is unavailable, the screen logs a warning and draws a fallback.
Coach-screen typography uses Kalam by Indian Type Foundry and Atkinson
Hyperlegible by the Braille Institute, bundled under the SIL Open Font License
1.1. Their full licenses are in `src/ui/assets/fonts/`; missing fonts fall back
to the desktop's existing UI font and produce a warning.

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
