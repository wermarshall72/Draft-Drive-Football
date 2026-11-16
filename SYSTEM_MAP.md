# System map

Start with [AGENTS.md](AGENTS.md) for the current gameplay direction and
[FUTURE_WORK.md](FUTURE_WORK.md) for incomplete systems and open decisions.
The desktop interactive game is the current implementation; the older
auto-battler is a separate legacy reference.

## Launch, navigate, or change profile setup

- [src/desktop.py](src/desktop.py) is the `python -m src.desktop` entry
  point; [src/ui/__main__.py](src/ui/__main__.py) also calls it.
  [DesktopApplication](src/ui/application.py) loads the profile, constructs
  screens, starts runs with independent seeds, and handles the event loop,
  scaling, and transitions. [navigation.py](src/ui/navigation.py) switches
  screens; [screens.py](src/ui/screens.py), [layout.py](src/ui/layout.py),
  [widgets.py](src/ui/widgets.py), and [theme.py](src/ui/theme.py) provide
  shared screen, layout, input, and visual components.
- [main_menu.py](src/ui/main_menu.py) selects difficulty and starts a run;
  [profile_screen.py](src/ui/profile_screen.py) creates or edits the profile.
  Saving flows through `DesktopApplication` and the profile methods of
  [ApplicationController](src/application.py) to validation and JSON storage
  in [profile.py](src/profile.py); the application refreshes the theme and
  screen data. See [test_desktop.py](tests/test_desktop.py) and
  [test_profile.py](tests/test_profile.py).

## Follow a run or change a screen

[football_run_screen.py](src/ui/football_run_screen.py) coordinates run
phases, buttons, input, exit confirmation, view callbacks, and error display.
It renders controller state and submits actions; football rules and progression
belong in [football_controller.py](src/engine/football_controller.py) and the
engine, not Pygame. `begin` resets transient UI state between runs.
[test_football_desktop.py](tests/test_football_desktop.py) covers the
headless run flow, navigation, controls, rendering, and reset;
[test_football_ui_interactions.py](tests/test_football_ui_interactions.py)
covers extracted interaction state.

- **Coach and player draft:** [football_coach_view.py](src/ui/football_coach_view.py)
  and [football_player_draft_view.py](src/ui/football_player_draft_view.py)
  render choices and details; [football_draft_interaction.py](src/ui/football_draft_interaction.py)
  tracks coach inspection and player-card interaction and cosmetic skin tones.
  Player cards display complete inactive perk details without a popup; their
  two team-colored pixel poses are in `assets/draft_players`. Choices pass through the controller to
  [football_team_builder.py](src/engine/football_team_builder.py), using
  [football_coaches.py](src/engine/football_coaches.py) and
  [football_player_catalog.py](src/engine/football_player_catalog.py).
  For artwork and fonts, see [coach_art.py](src/ui/coach_art.py),
  [player_art.py](src/ui/player_art.py), and
  [coach_fonts.py](src/ui/coach_fonts.py). Player perks are displayed but not
  executed. See
  [test_football_team_builder.py](tests/test_football_team_builder.py),
  [test_football_coaches.py](tests/test_football_coaches.py), and
  [test_football_player_catalog.py](tests/test_football_player_catalog.py).
- **Shop and review:** [football_shop_view.py](src/ui/football_shop_view.py)
  renders offers; [football_review_view.py](src/ui/football_review_view.py)
  renders the depth chart and playbook, with review/scroll state in
  [football_shop_review.py](src/ui/football_shop_review.py). A removal purchase
  opens the playbook for explicit copy selection or cancellation; the
  coordinator submits the action through the controller to
  [football_shop.py](src/engine/football_shop.py), which owns offers, AP,
  player upgrades, the run-unique coach-upgrade catalog and effects, decks,
  and removal validation. Coach-upgrade purchase history and descriptions are
  shown in the Depth Chart. [football_coach_upgrade_details.py](src/ui/football_coach_upgrade_details.py)
  supplies complete duration, uniqueness, rarity, and cost details to shop
  inspection and owned-upgrade rows; [text.py](src/ui/text.py) wraps complete
  descriptions and fails if they cannot fit their assigned region. See
  [test_football_shop.py](tests/test_football_shop.py),
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py), and
  the shop/review cases in [test_football_desktop.py](tests/test_football_desktop.py).
- **Match and results:** [football_match_field.py](src/ui/football_match_field.py),
  [football_match_status.py](src/ui/football_match_status.py), and
  [football_match_decision_view.py](src/ui/football_match_decision_view.py)
  render the field, scoreboard/history, and hand/decision controls. Offensive
  hand previews use the simulator's adjusted normal-play clock calculation and
  label incomplete-pass, conversion, and special-teams exceptions.
  [football_match_interaction.py](src/ui/football_match_interaction.py)
  tracks hand scrolling, dragging, and field animation.
  The hand distinguishes printed base card durations from the live normal-play
  clock, with simulator clock exceptions visible.
  [football_result.py](src/ui/football_result.py) renders results and
  progression actions. Tests include
  [test_football_desktop.py](tests/test_football_desktop.py) and
  [test_football_ui_interactions.py](tests/test_football_ui_interactions.py).

## Change cards, simulation, or progression

- **Play and scheme cards:** [football.py](src/engine/football.py) defines
  actions, families, matchups, card copies, and deck/match state;
  [football_decks.py](src/engine/football_decks.py) defines the catalogs and
  starter decks. The shop adds/removes owned copies; the controller passes
  those decks into the simulator, which deals and cycles match hands. UI calls
  use copy IDs, including two-point selections. See
  [test_football_play_catalog.py](tests/test_football_play_catalog.py),
  [test_football_decks.py](tests/test_football_decks.py), and
  [test_football_shop.py](tests/test_football_shop.py).
- **Resolution and AI:** [football_simulator.py](src/engine/football_simulator.py)
  owns matchup estimates, play resolution, clock, scoring, deck cycling, and
  special-teams/conversion outcomes. [football_ai.py](src/engine/football_ai.py)
  generates local opponents and selects actions; the controller advances AI
  turns until a human decision or result. Typed coach-upgrade effects travel
  in the match snapshot and are shared by resolution, previews, and relevant AI
  field-goal estimates. See
  [test_football_simulator.py](tests/test_football_simulator.py),
  [test_football_ai.py](tests/test_football_ai.py),
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py), and
  [test_football_models.py](tests/test_football_models.py).
- **Run progression:** [football_controller.py](src/engine/football_controller.py)
  connects draft, shop, simulator, AI, results, and subsequent shops.
  It tracks actual games played separately from scheduled games skipped by
  Bye Week; [football_result.py](src/ui/football_result.py) renders the
  game-10 skip as a marker without a fabricated score. Coach upgrades are
  implemented as an initial catalog; player perk effects and a playable
  playoff bracket remain unfinished. See
  [test_football_controller.py](tests/test_football_controller.py) and
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py).

## Persistence, legacy, and tooling

The desktop saves the shared profile JSON via [profile.py](src/profile.py);
the interactive run itself is in memory and does not use the snapshot database.
The still-reachable terminal entry point [src/main.py](src/main.py) uses the
legacy run methods in [src/application.py](src/application.py), legacy
[game_run.py](src/engine/game_run.py), [shop.py](src/engine/shop.py),
[simulator.py](src/engine/simulator.py), and
[units.py](src/engine/units.py), with action definitions in
[coaching_actions.py](src/engine/coaching_actions.py). Its snapshot storage is
[schema.py](src/db/schema.py). These are not the redesigned match engine.
See [test_cli.py](tests/test_cli.py), [test_application.py](tests/test_application.py),
and [test_snapshots.py](tests/test_snapshots.py).

[backtest_football_models.py](scripts/backtest_football_models.py) runs model
and full regression tests; [measure_football_balance.py](scripts/measure_football_balance.py)
measures seeded interactive matchups and games. Test setup and launch commands
are in [README.md](README.md).

## Common starting points

- **Add a play card:** start with action/family mappings in
  [football.py](src/engine/football.py) and the catalog in
  [football_decks.py](src/engine/football_decks.py); follow it through the
  shop, simulator, and catalog/deck tests above.
- **Change a shop screen:** start in [football_shop_view.py](src/ui/football_shop_view.py)
  or [football_review_view.py](src/ui/football_review_view.py); trace actions
  through the run coordinator and controller to `FootballShop`.
- **Change match resolution or special teams:** start in
  [football_simulator.py](src/engine/football_simulator.py), then check AI,
  previews, and simulator/controller tests for affected behavior.
- **Adjust profile setup:** start in [profile_screen.py](src/ui/profile_screen.py),
  then follow save and validation through `DesktopApplication`,
  `ApplicationController`, and [profile.py](src/profile.py).
