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

Install the test dependency if needed, then run the test suite with:

```sh
python -m pip install -e ".[test]"
python -m pytest
```
