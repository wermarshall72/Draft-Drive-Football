# System map

Start with [AGENTS.md](AGENTS.md) for the current gameplay direction and
[FUTURE_WORK.md](FUTURE_WORK.md) for incomplete systems and open decisions.
The desktop interactive game is the current implementation; the older
auto-battler is a separate legacy reference.

## Launch, navigate, or change profile setup

- [src/desktop.py](src/desktop.py) is the `python -m src.desktop` entry
  point (`--data-dir`, `--profile-path`); [src/ui/__main__.py](src/ui/__main__.py) also calls it.
  [DesktopApplication](src/ui/application.py) loads the profile and any saved
  run, constructs screens, starts runs with independent seeds, saves and
  deletes the run (`save_run`, `_forget_run`, `abandon_saved_run`), and
  handles the event loop, scaling, and transitions. [navigation.py](src/ui/navigation.py) switches
  screens; [screens.py](src/ui/screens.py), [layout.py](src/ui/layout.py),
  [widgets.py](src/ui/widgets.py), and [theme.py](src/ui/theme.py) provide
  shared screen, layout, input, and visual components.
- [main_menu.py](src/ui/main_menu.py) presents profile status and selects
  difficulty to start a run. While `DesktopApplication` remembers an unfinished
  run it leads with a focused CONTINUE RUN button whose summary comes from
  [football_run_summary.py](src/ui/football_run_summary.py), and START RUN
  opens a replace-run confirmation drawn with the shared pause-menu panel.
  The remembered run is the in-memory fast path within a session; the disk
  save (see Persistence below) restores it at startup (`continue_run`,
  `remembered_run_summary`, `_load_saved_run`). A `MenuSaveNotice` reports a
  restored backup, damaged save, or unloadable save; unloadable ones add
  ABANDON SAVE and make START RUN confirm first. [main_menu_art.py](src/ui/main_menu_art.py)
  draws its procedural stadium and tints the user-supplied helmet layers in
  `src/ui/assets/menu_helmet_*.png` to the team's primary color.
  [profile_screen.py](src/ui/profile_screen.py) creates or edits the profile.
  Saving flows through `DesktopApplication` and the profile methods of
  [ApplicationController](src/application.py) to validation and JSON storage
  in [profile.py](src/profile.py); the application refreshes the theme and
  screen data; a remembered run keeps its own team name. See
  [test_desktop.py](tests/test_desktop.py),
  [test_profile.py](tests/test_profile.py),
  [test_main_menu.py](tests/test_main_menu.py), and
  [test_pause_menu.py](tests/test_pause_menu.py).

## Follow a run or change a screen

[football_run_screen.py](src/ui/football_run_screen.py) coordinates run
phases, buttons, input, the pause menu, view callbacks, and error display.
It renders controller state and submits actions; football rules and progression
belong in [football_controller.py](src/engine/football_controller.py) and the
engine, not Pygame. `begin` resets transient UI state for a new run; `restore`
starts on a run loaded from disk (settled, reopening a pending removal's
Playbook); `resume` returns to a remembered run without resetting it (draft
step, shop sub-screen and pending removal, match with any replay settled,
regular result, and focus). `_submit` calls `on_save_point` after every
successful decision, as does Return to Menu; `show_save_notice` draws the
transient save-failure banner.
[football_pause_menu.py](src/ui/football_pause_menu.py) owns `PauseMenu`
(open state, saved focus, and the 3-second two-step QUIT RUN on an injectable
clock), the shared veil/panel/button drawing, and the PAUSE [ESC] button look.
Every run screen shows PAUSE [ESC] and opens the same menu on Esc (KEEP
PLAYING, RETURN TO MENU, QUIT RUN; the match variant adds DEPTH CHART and PLAY
LOG); inner popups, visible inspect panels, and a pending removal take Esc
first. FIRED and PLAYOFFS runs have ended: no pause, and leaving discards them.
[test_pause_menu.py](tests/test_pause_menu.py) covers the menu, resume, Quit
Run, and the replace-run confirmation.
[test_football_desktop.py](tests/test_football_desktop.py) covers the
headless run flow, navigation, controls, rendering, and reset;
[test_football_ui_interactions.py](tests/test_football_ui_interactions.py)
covers extracted interaction state.

- **Coach and player draft:** [football_coach_view.py](src/ui/football_coach_view.py)
  and [football_player_draft_view.py](src/ui/football_player_draft_view.py)
  render choices and details; [football_draft_interaction.py](src/ui/football_draft_interaction.py)
  tracks coach pair highlighting, the coach inspect panel (`CoachInspection`:
  a hovered coach column/perk row shows that coach; a keyboard-focused pair
  shows both coaches' perk lines and full rules), and
  player-card interaction and cosmetic skin tones. The coach screen uses the
  shared kit look (stadium backdrop, kit panels, team accent only on the active
  pair outline and SELECT PAIR fill); each card shows Depth Chart-style position
  modifiers and one short perk line per coach, and the full rules open in the
  shared `football_inspect` panel (`coach_inspect`, `coach_pair_inspect`). Perk wording has one source,
  [football_coach_perks.py](src/ui/football_coach_perks.py): `coach_perk_short`
  for cards (coach selection and both faces of the Depth Chart coach card),
  `coach_perk_rules` for the panel, and `modifier_text`. The fixed portraits
  and primary-color clothing masks are in `assets/draft_coaches`.
  The player draft uses the same kit header, PAUSE [ESC] spot, and header
  error banner as coach selection. Its sidebar tracker shows each position's
  coach-bonus chip and, once drafted, coached power and partner link
  (`tracker_row`); the active card's partner row is lit
  (`PlayerInspection.partner_row`). Cards show base and coached power
  (`draft_coached_power`, built on the engine's `coached_player_power`, which
  the Depth Chart's Modified Stats also use), a partner callout
  (`partner_callout`), and the perk (name with WITH/limit tags, card line, full
  rules; `draw_perk_heading`) without a popup. Six
  position-mapped, team-colored sprites and a shared Heisman hover/focus pose
  and their masks are in
  `assets/draft_players`; [process_player_art.py](scripts/process_player_art.py)
  prepares the supplied source images. [football_appearance.py](src/engine/football_appearance.py)
  defines appearance descriptors, and the controller retains selected appearances
  by roster position for the current run. Choices pass through the controller to
  [football_team_builder.py](src/engine/football_team_builder.py), using
  [football_coaches.py](src/engine/football_coaches.py) and
  [football_player_catalog.py](src/engine/football_player_catalog.py).
  For artwork and fonts, see [coach_art.py](src/ui/coach_art.py),
  [player_art.py](src/ui/player_art.py), and
  [coach_fonts.py](src/ui/coach_fonts.py). Player-perk wording has one source,
  [football_player_perks.py](src/ui/football_player_perks.py) (card line,
  full rules, partner and limit tags, callouts, preview notes). AI drafting is a
  seeded weighted choice that favors partners and deck fit (`draft_weight` in
  [football_ai.py](src/engine/football_ai.py)). See
  [test_football_team_builder.py](tests/test_football_team_builder.py),
  [test_football_coaches.py](tests/test_football_coaches.py), and
  [test_coach_draft_redesign.py](tests/test_coach_draft_redesign.py),
  [test_coach_selection_screen.py](tests/test_coach_selection_screen.py) (perk
  wording, text fit, Depth Chart wording, inspect panel),
  [test_player_draft_redesign.py](tests/test_player_draft_redesign.py)
  (coached power, tracker rows, partner links, text fit), and
  [test_football_player_catalog.py](tests/test_football_player_catalog.py),
  [test_football_player_perk_text.py](tests/test_football_player_perk_text.py), and
  [test_player_art.py](tests/test_player_art.py).
- **Shop and review:** [football_shop_view.py](src/ui/football_shop_view.py)
  renders the shop landing (AP badge, PLAYER UPGRADES 4 slots, COACH UPGRADES
  2 slots, PLAYS & SCHEMES 3x2 grid, kit-style footer) using the run's saved
  appearances and coach assignment. Each offer or locked slot is one focusable
  `ShopCardButton` whose `click_rect` is its price button, so only the price
  buys; prices show cost, PURCHASED, or a dimmed cost, and unlocks show a lock
  plus cost or a short reason. Coach cards show a portrait and the short line
  from `COACH_UPGRADE_SHORT_LINES` in
  [football_coach_upgrade_details.py](src/ui/football_coach_upgrade_details.py),
  which also supplies the full detail sections. Play, scheme, bonus, and Remove
  One Card faces come from [football_card_faces.py](src/ui/football_card_faces.py)
  (shared with the Playbook). [football_inspect.py](src/ui/football_inspect.py)
  owns hover/focus inspect panels (`InspectState`) and their content for
  every card type: a panel appears after a short delay, hides when the pointer
  or focus moves away or on Esc, sits beside its card, and never takes clicks. [football_ui_kit.py](src/ui/football_ui_kit.py) holds the shared
  navy palette, fonts, `text_audit`, stadium backdrop, popup panel and buttons,
  kit/painted buttons, card shell, and the single rarity palette (Rare blue);
  `football_match_palette.py` re-exports it for the match modules.
  [football_review_view.py](src/ui/football_review_view.py) renders the
  filterable 6-column Playbook grid with rarity-colored borders and labels,
  copy badges, inspect panels, and the removal mode's exact-copy REMOVE
  buttons; it delegates the Depth Chart to
  [football_depth_chart.py](src/ui/football_depth_chart.py), which draws staff
  cards, a 4x2 roster with stat icons and pending badges, and a
  STARTING/MODIFIED toggle (also used read-only by the in-match popup). Each
  player and coach card has a flip-arrow button that rotates it to a back face:
  players list their permanent and pending upgrades, partnership, and planned
  perk; coaches list their perk and that side's coach upgrades. Backs never
  drop content: overflow scrolls inside the card (wheel while hovered, Page
  Up/Down/Home/End while its flip arrow is focused) with a scroll bar and MORE
  hint, and front pending chips end in a "+N" chip when they do not all fit. The header's
  Team upgrades button opens a popup with special-teams and program (AP, Bye
  Week) coach upgrades; `coach_upgrade_area` in the coach-upgrade details module
  decides the split. The flip arrow and info icons in `src/ui/assets` come
  from [process_ui_icons.py](scripts/process_ui_icons.py). Review
  filters/scrolling, stat-toggle and flip state, the Team upgrades popup flag,
  and the Playbook's `InspectState` live in
  [football_shop_review.py](src/ui/football_shop_review.py).
  A removal purchase
  opens the same Playbook layout for exact-copy selection or cancellation; the
  coordinator submits the action through the controller to
  [football_shop.py](src/engine/football_shop.py), which owns offers, AP,
  player upgrades, the run-unique coach-upgrade catalog and effects, decks,
  repeatable bonus-card purchases, independent 58/24/12/6 playbook rarity
  rolls, and removal validation. A bought play, scheme, or bonus card stays in
  its slot (and in any slot offering the same card) as purchased until Next Day
  or the next visit, like player upgrades; other shop sections keep their
  existing rarity weights. Remove One Card
  is a Rare shop-only service, not a deck
  card. Its 192 individual-player cards apply permanent upgrades to the roster
  and retain temporary upgrades as pending run-local state. The shop state
  projects raw run and next-match roster effects and
  coach-adjusted next-match effects; the Depth Chart separates pending
  summaries from permanent modified stats, with combined effects in details.
  [football_simulator.py](src/engine/football_simulator.py) shares the coach
  bonus, cap, and baseline player-stat calculations with these projections.
  Power projections exclude play-specific fatigue, partnership, and scheme.
  Player-upgrade cards show the stat icon and nominal value plus the duration
  icon, with no stat or duration words;
  [football_player_upgrade_details.py](src/ui/football_player_upgrade_details.py)
  formats pending changes and roster values in Depth Chart details.
  [text.py](src/ui/text.py) wraps text. See
  [test_football_shop_screens.py](tests/test_football_shop_screens.py) for the
  shop landing, price states, inspect panels, rarity colors, text fit, Depth
  Chart, and removal flow;
  [test_football_playbook_view.py](tests/test_football_playbook_view.py) for
  Playbook filtering, rarity colors, removal mode, inspect panels, and bounds.
  [football_card_art.py](src/ui/football_card_art.py) maps play/scheme families,
  bonus actions, and the removal service to packaged pixel-art tiles used by
  the shop, Playbook, match hand, piles, and Challenge action buttons. Assets come from
  [process_football_card_art.py](scripts/process_football_card_art.py). See
  [test_football_card_art.py](tests/test_football_card_art.py),
  [test_football_shop.py](tests/test_football_shop.py), and
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py).
- **Stat icons:** [stat_icons.py](src/ui/stat_icons.py) wraps every UI font (built only in
  [screens.py](src/ui/screens.py) and [coach_fonts.py](src/ui/coach_fonts.py)) so any rendered or
  measured text places the Power, Stamina, or Volatility icon from `assets/stat_icons/` inline
  before its word; text without those words renders unchanged. Assets come from
  [process_stat_icons.py](scripts/process_stat_icons.py); see
  [test_stat_icons.py](tests/test_stat_icons.py).
- **Match and results:** [football_match_screen.py](src/ui/football_match_screen.py)
  composes the 1280x720 match layout (92px scoreboard, 286px field, 64px
  outcome strip, hands in the middle 60% and deck/discard piles in each outer
  20%), owns playback and popup state, and forwards choices to the run screen
  through `MatchActions`; the run screen only submits them to the controller.
  [football_match_events.py](src/ui/football_match_events.py) is pure: it
  turns recorded events into absolute-yard play lines (run red, pass blue,
  other grey; incomplete X, turnover/return, blocked, scoring end-zone flash),
  outcome-strip wording, period banners, and display snapshots, including a
  kickoff-pending view in place of the placeholder drive the simulator records
  between a score and its automatic kickoff.
  [football_match_playback.py](src/ui/football_match_playback.py) replays
  multi-event updates one event per second, blocks input until done or skipped,
  and always replays a match's final events before the result screen; its
  label counts only snaps and kicks, and hands, piles, and opponent counts are
  dimmed with a note because they already show the post-replay decks.
  [football_match_scoreboard.py](src/ui/football_match_scoreboard.py) draws
  badges, scores, clock, situation, and the opponent's face-down hand counts
  (never identities); [football_match_field.py](src/ui/football_match_field.py)
  draws turf, markers, the active scheme tag, and the latest play line;
  [football_match_outcome.py](src/ui/football_match_outcome.py) draws the
  result and the fourth-down, conversion, Challenge, and Skip buttons;
  [football_match_hand.py](src/ui/football_match_hand.py) draws both hands
  (only the group for the current decision is selectable; two-point tries use
  offensive play cards), live yard/clock previews, bonus cards, the ACTIVE
  scheme slot, the basic-run fallback slot whenever the offensive hand has no
  play card, and per-group scrolling that reveals a playable card once per
  decision;
  [football_match_piles.py](src/ui/football_match_piles.py) draws draw and
  discard piles; [football_match_popups.py](src/ui/football_match_popups.py)
  draws the in-match Depth Chart (temporary upgrades labeled active this match), the play log,
  and read-only pile lists (the match pause menu is the shared
  `football_pause_menu` panel with Depth Chart and Play Log added).
  [football_match_interaction.py](src/ui/football_match_interaction.py)
  tracks drag, drop areas, and group scroll. Colors, fonts, and the
  `text_audit` fit recorder are re-exported by [football_match_palette.py](src/ui/football_match_palette.py)
  from the shared [football_ui_kit.py](src/ui/football_ui_kit.py).
  [football_result.py](src/ui/football_result.py) owns the full-screen
  result (no shared app header): a compact GAME/FINAL header, scoreboard hero
  with WIN/LOSS banner and OT label, a verdict ribbon (next shop, FIRED,
  PLAYOFFS, or BYE WEEK), team stats, the 10-game season tracker with the
  3-strike loss meter, and the primary action plus PAUSE [ESC] (regular-season
  results only). An injectable clock drives a score count-up that never
  blocks the button; the Bye Week game-10 marker never shows the retained
  previous match. [football_result_stats.py](src/ui/football_result_stats.py)
  is the pure team-stat helper (offensive snaps only, Challenge-overturned
  plays and two-point tries excluded). The run screen routes result phases
  to `_draw_result_screen`. Tests include
  [test_football_result_screen.py](tests/test_football_result_screen.py)
  (variants, Bye Week, text fit, count-up),
  [test_football_result_stats.py](tests/test_football_result_stats.py),
  [test_football_match_presentation.py](tests/test_football_match_presentation.py)
  (lines, wording, playback), [test_football_desktop.py](tests/test_football_desktop.py)
  (hands, piles, popups, strip decisions, text fit), and
  [test_football_ui_interactions.py](tests/test_football_ui_interactions.py).

## Change cards, simulation, or progression

- **Play and scheme cards:** [football.py](src/engine/football.py) defines
  actions, families, matchups, card copies, and deck/match state;
  [football_decks.py](src/engine/football_decks.py) defines the 36-play,
  24-scheme, and six-bonus-card catalogs plus the starter decks. The shop adds
  repeatable owned copies and removes explicitly selected copies. The
  controller passes those decks into the simulator, which deals and cycles
  match hands (`_deal_deck`, `_cycle_played_card`, `_draw_one_into_hand`;
  bonus effects in `resolve_bonus_card`). Every card replaces itself in its own
  hand; Draw bonus cards add one extra offensive or defensive card with no
  hand-size cap, and the hand UI shrinks then scrolls to fit. Each drive's end
  trims or refills the offense's offensive hand to three and the defense's
  defensive hand to two (`_end_drive`, `_normalize_hand`); halftime and
  overtime redeal instead (`_reset_for_period_boundary`, which also resolves the
  second-half kickoff by `opening_possession`). Challenge restores
  football state while retaining the post-play clock, card cycling, and event
  history. AI decks remain limited to named plays and schemes. UI calls use
  copy IDs, including two-point selections. See
  [test_football_play_catalog.py](tests/test_football_play_catalog.py),
  [test_football_decks.py](tests/test_football_decks.py),
  [test_football_bonus_cards.py](tests/test_football_bonus_cards.py), and
  [test_football_shop.py](tests/test_football_shop.py).
- **Resolution and AI:** [football_simulator.py](src/engine/football_simulator.py)
  owns matchup estimates, play resolution, tactical bonus effects, Challenge
  rollback, clock, scoring, deck cycling, and special-teams/conversion
  outcomes.
- **Player perks:** the typed catalog (`FootballPlayerPerk`, kind, limit, values)
  is in [football_player_catalog.py](src/engine/football_player_catalog.py);
  `FootballPlayerPerkKind` and `FootballPerkActivation` (recorded on events and
  play results) are in [football.py](src/engine/football.py).
  [football_perk_context.py](src/engine/football_perk_context.py) rebuilds
  per-team drive/half/game history from events (`perk_history`, `team_perks`)
  and computes estimate perks (`estimate_perk_inputs`: power, counters, yards,
  odds) that `calculate_match_play_estimate` applies, so resolution, Hard AI,
  and previews agree. `resolve_offensive_play` applies resolution perks in the
  proposal's order (reroll, swaps, yards, spot with the defense last, clock,
  cards); drive-start perks run in `select_defensive_scheme`; kick perks use
  `kick_rush_bonus` and `range_denial_yards`; Green Dog is
  `FootballAwaitedAction.GREEN_DOG_DECISION` / `resolve_green_dog`. AI Read
  Keys, Green Dog, and Keep Read logic are in [football_ai.py](src/engine/football_ai.py).
  Match UI: callouts and Play Log text in
  [football_match_events.py](src/ui/football_match_events.py), the tray, Read
  Keys, and Green Dog panels in [football_match_perks.py](src/ui/football_match_perks.py),
  preview notes in [football_match_hand.py](src/ui/football_match_hand.py).
  See [test_football_player_perks.py](tests/test_football_player_perks.py)
  (helpers in [perk_helpers.py](tests/perk_helpers.py)) and
  [test_football_perk_ui.py](tests/test_football_perk_ui.py). [football_ai.py](src/engine/football_ai.py) generates local
  opponents and selects actions; AI uses the expanded named catalogs but never
  receives bonus cards. The controller advances AI turns until a human decision
  and pauses for an available turnover Challenge before continuing; it routes
  an available touchdown Challenge from conversion decisions through the same
  simulator rollback path. Typed
  coach-upgrade effects travel in the match snapshot and are shared by
  resolution, previews, and relevant AI field-goal estimates. See
  [test_football_simulator.py](tests/test_football_simulator.py),
  [test_football_ai.py](tests/test_football_ai.py),
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py), and
  [test_football_models.py](tests/test_football_models.py).
- **Run progression:** [football_controller.py](src/engine/football_controller.py)
  connects draft, shop, simulator, AI, results, and subsequent shops.
  It tracks actual games played separately from scheduled games skipped by
  Bye Week, and keeps a read-only per-game `season_history`
  (`FootballSeasonGame`: W/L with score and overtime flag, or BYE). Pending player upgrades are applied to the human match roster and
  cleared only when a match result is recorded, not on a Bye Week;
  [football_result.py](src/ui/football_result.py) renders the
  game-10 skip as a marker without a fabricated score. Coach upgrades are
  implemented as an initial catalog; a playable playoff bracket remains
  unfinished. The controller routes Green Dog offers (`respond_to_green_dog`,
  `FootballHumanDecision.GREEN_DOG`). See
  [test_football_controller.py](tests/test_football_controller.py) and
  [test_football_coach_upgrades.py](tests/test_football_coach_upgrades.py).

## Persistence, legacy, and tooling

[src/persistence/](src/persistence/__init__.py) does all save-file I/O and
imports no Pygame. [paths.py](src/persistence/paths.py) resolves the per-OS
app-data folder (`APP_DATA_NAME`, `DDF_DATA_DIR`, `app_data_dir`);
[atomic_io.py](src/persistence/atomic_io.py) writes temp-fsync-replace files
(also used by [profile.py](src/profile.py), whose `default_profile_path`
copies a legacy `~/.cfb-auto-battler` profile once);
[run_save.py](src/persistence/run_save.py) owns `RunSaveStore`, the
checksummed envelope, `run.json`/`run.backup.json` rotation, load fallbacks
(`LoadResult`/`LoadStatus`), moving damaged or abandoned files aside, and the
`save_run`/`load_run`/`delete_run` helpers; [migrations.py](src/persistence/migrations.py)
holds `CURRENT_SCHEMA_VERSION` and the `N -> N+1` registry (version 2 added
the match's `opening_possession` and per-event perk activations). The engine owns
the payload: `to_save_data`/`from_save_data` on the controller, team builder,
shop, AI, simulator, and match models in [football.py](src/engine/football.py),
with shared helpers and `UnsupportedSave` in [save_data.py](src/engine/save_data.py).
See [test_run_save.py](tests/test_run_save.py) (round trips, determinism,
envelope, atomic writes, migrations), [test_run_save_desktop.py](tests/test_run_save_desktop.py)
(restart, Continue Run, replace, quit, failures, notices),
[test_persistence_paths.py](tests/test_persistence_paths.py), the seeded
driver [football_run_driver.py](tests/football_run_driver.py), and
[conftest.py](tests/conftest.py), which isolates every test's folders.
The interactive run does not use the snapshot database.
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
measures seeded interactive matchups and games (`--perks on|off` compares
player perks; with perks on it reports each perk's fire rate against its tier).
Test setup and launch commands
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
- **Add run state or change the save format:** add the field to the owning
  engine object's `to_save_data`/`from_save_data`, bump the schema version and
  add a migration in [migrations.py](src/persistence/migrations.py), then
  extend [test_run_save.py](tests/test_run_save.py).
