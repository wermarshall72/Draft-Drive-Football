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
earns a seed in an eight-team, single-elimination playoff bracket, with a shop
before each round. One playoff loss ends the run; three wins take the title.

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

The active run is saved after every decision (and on Return to Menu or
quitting), so closing the game resumes on the same decision. The desktop
gameplay flow uses `FootballGameController` and does not initialize or write
to the legacy game database.

## Save files

The team profile (`profile.json`) and the single saved run (`run.json`, plus
the previous good save in `run.backup.json`) live in the per-user app-data
folder:

- macOS: `~/Library/Application Support/Draft Drive Football/`
- Windows: `%APPDATA%\Draft Drive Football\`
- Linux: `$XDG_DATA_HOME/draft-drive-football/`, or
  `~/.local/share/draft-drive-football/` when `XDG_DATA_HOME` is unset

Set `DDF_DATA_DIR` (or pass `--data-dir` to `python -m src.desktop`) to use
another folder, e.g. for debugging. On first launch a profile from the old
`~/.cfb-auto-battler/profile.json` is copied over; the old file is kept.
Saves are readable JSON with a checksum; damaged or set-aside saves are kept
beside them with a timestamped name.

For code paths, feature ownership, and relevant tests, see the
[system map](SYSTEM_MAP.md).

## Run the terminal client

From the project directory, start the game with:

```sh
python -m src.main
```

The first launch asks for a team name and two different colors. The saved
profile is stored outside the project in the app-data folder listed under
[Save files](#save-files), so it is not tied to the current working directory
or the game's SQLite snapshot database. Profiles can also be created or
edited in the desktop app.

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
