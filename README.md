# CFB Auto-Battler

## Run the desktop shell

From the project directory, launch the resizable Pygame shell with:

```sh
python -m src.desktop
```

The desktop shell reads the same saved team profile and color palette as the
terminal client. If no profile exists, the menu explains how to create one.
The current coach, draft, roster, shop, and match pages are visual previews;
opening the shell and browsing them does not initialize or write to the game
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

The terminal client and desktop shell are separate clients of
`ApplicationController` in `src/application.py`. It exposes profile and
main-menu operations, explicit run actions, and immutable state/result views;
the controller does not depend on a windowing or input framework. Game rules,
shop behavior, match simulation, and local snapshot storage remain in the
existing engine and database modules.

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
