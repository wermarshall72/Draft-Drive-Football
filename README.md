# CFB Auto-Battler

## Run from a terminal

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

The terminal client and future desktop clients can drive the same game flow
through `ApplicationController` in `src/application.py`. It exposes profile and
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

This installs Pygame Community Edition, the Python library planned for the
desktop game window, drawing, and input handling. The current game is still
played in the terminal; the dependency alone does not add a graphical UI.

Run the test suite with:

```sh
python -m pytest
```
