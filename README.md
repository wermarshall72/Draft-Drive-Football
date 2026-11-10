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
