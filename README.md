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

Each coach pair shows both coaches' team-colored portraits, position
modifiers, and active perks inline; hover a pair or use Tab / arrow keys to
highlight it, and choose a staff to lock both coaches. During the player draft,
each prospect card shows its stats, partnership, and planned, inactive perk
without a popup. Prospects use original position-specific pixel-art sprites
with separate primary, secondary, and skin-tone masks so uniforms use the saved
team colors; the highlighted prospect switches to a shared Heisman pose. Enter
or Space activates the focused button. The illustrations are not portraits of
real players.
Most desktop screens use Barlow by Jeremy Tribby (from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlow)), bundled
under the SIL Open Font License 1.1; remaining UI text uses a system font.
Its full license is in `src/ui/assets/fonts/`; if the font is missing, the
desktop falls back to its system UI font and logs a warning.

Desktop run state is in memory only. The desktop gameplay flow uses
`FootballGameController` and does not initialize or write to the legacy game
database.

For code paths, feature ownership, and relevant tests, see the
[system map](SYSTEM_MAP.md).

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
