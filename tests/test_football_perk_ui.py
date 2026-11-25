"""Perks on screen: callouts, Play Log, preview notes, tray and badges, Read Keys, Green Dog."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballDeckState,
    FootballMatchState,
    FootballPerkDecision,
    FootballPosition,
    FootballPlayerPerkKind as K,
    FootballTeamSide,
)
from src.engine.football_controller import FootballHumanDecision
from src.engine.football_player_catalog import PLAYER_TYPES_BY_PERK, player_from_type
from src.engine.football_simulator import FootballMatchSimulator
from src.ui.football_match_events import snapshot_state
from src.ui.football_match_outcome import CALLOUT_CYCLE_MS, GREEN_DOG_PROMPT
from src.ui.football_match_perks import GREEN_DOG_TITLE, READ_KEYS_TITLE
from src.ui.football_ui_kit import text_audit
from tests.perk_helpers import ScriptedRNG, ensure_in_hand, full_decks, snap
from tests.test_football_desktop import (
    _activate, _assert_text_fits, _draft_to_shop, _new_desktop, _skip_match_playback,
    _start_match, _start_run, _surface,
)

A, B = FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B


def _with_perks(roster, *kinds):
    players = dict(roster.players)
    for kind in kinds:
        player_type = PLAYER_TYPES_BY_PERK[kind]
        players[player_type.position] = player_from_type(player_type, name=player_type.name)
    return replace(roster, players=players)


def _scenario(tmp_path: Path, a_kinds=(), b_kinds=(), **overrides):
    """A real desktop match whose simulator is replaced by a perk scenario."""
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _skip_match_playback(desktop)
    controller = desktop.football_controller
    match = controller.state.match
    a, b = full_decks("a"), full_decks("b")
    values = dict(
        team_a=_with_perks(match.team_a, *a_kinds), team_b=_with_perks(match.team_b, *b_kinds),
        random_seed=4242, team_a_score=0, team_b_score=0, possession=A, down=1, yards_to_go=10.0,
        offense_field_position=40.0, game_clock_seconds=700, period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        team_a_offense_deck=FootballDeckState(a["offense"].owned[:6]),
        team_a_defense_deck=FootballDeckState(a["defense"].owned[:6]),
        team_b_offense_deck=FootballDeckState(b["offense"].owned[:6]),
        team_b_defense_deck=FootballDeckState(b["defense"].owned[:6]),
    )
    values.update(overrides)
    simulator = FootballMatchSimulator(FootballMatchState(**values))
    simulator.rng = ScriptedRNG()
    controller._simulator = simulator
    return desktop, controller, simulator


def _select(simulator, scheme: str) -> None:
    defense = B if simulator.state.possession is A else A
    ensure_in_hand(simulator, defense, scheme, offensive=False)
    simulator.select_defensive_scheme(DefensiveSchemeAction(scheme))


def _show(desktop) -> list:
    desktop.run_screen.state = desktop.football_controller.state
    desktop.run_screen.match_screen.playback.reset()
    _skip_match_playback(desktop)
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    return records


def _texts(records) -> list[str]:
    return [text for text, _rect, _container in records]


def test_outcome_strip_cycles_two_perk_callouts_without_overflow(tmp_path: Path) -> None:
    desktop, controller, simulator = _scenario(tmp_path, (K.MOVE_THE_STICKS,), (K.HOLD_THE_LINE,))
    _select(simulator, "rb_run")
    simulator.state = replace(simulator.state, down=3, yards_to_go=10.0)
    ensure_in_hand(simulator, A, "short_pass")
    snap(simulator, "short_pass", yards=8.5)
    texts = _texts(_show(desktop))
    assert any(text.startswith("MOVE THE STICKS · Chain Mover · FIRST DOWN") and text.endswith("1/2")
               for text in texts)
    assert "+9.5 YARDS" in texts  # stopped just short of the line, so the decimal shows
    screen = desktop.run_screen.match_screen
    started = screen.clock()
    screen.clock = lambda: started + CALLOUT_CYCLE_MS + 50
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    assert any(text.startswith("HOLD THE LINE · Nickel Rover · STOPPED SHORT") for text in _texts(records))


def test_play_log_lists_the_perks_on_each_play(tmp_path: Path) -> None:
    desktop, controller, simulator = _scenario(tmp_path, (K.MOVE_THE_STICKS,), (K.HOLD_THE_LINE,))
    _select(simulator, "rb_run")
    simulator.state = replace(simulator.state, down=3, yards_to_go=10.0)
    ensure_in_hand(simulator, A, "short_pass")
    snap(simulator, "short_pass", yards=8.5)
    _show(desktop)
    desktop.run_screen.match_screen.open_play_log()
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    assert "Perks: Move the Sticks (first down), Hold the Line (stopped short)" in _texts(records)


def test_preview_notes_tray_and_depth_chart_badges_fit(tmp_path: Path) -> None:
    desktop, controller, simulator = _scenario(
        tmp_path, (K.CHECKDOWN, K.PULL_LEAD, K.PYLON_REACH, K.SHOT_SETUP, K.TIP_DRILL), (),
    )
    _select(simulator, "short_pass")
    ensure_in_hand(simulator, A, "deep_pass")
    snap(simulator, "deep_pass", randoms=(0.0,))
    simulator.state = replace(simulator.state, down=3, yards_to_go=2.0)
    for card in ("short_pass", "rb_run"):
        ensure_in_hand(simulator, A, card)
    texts = _texts(_show(desktop))
    joined = " ".join(texts)
    assert "+10 OL Pull" in joined  # Inside Run preview (may wrap onto two lines)
    assert "+2 yd Checkdown" in joined or "+2 yd" in joined  # Short Pass preview
    assert "PERKS" in texts and {"QB", "WR", "S"} <= set(texts)  # the tray's limited perks
    screen = desktop.run_screen.match_screen
    screen.open_depth_chart()
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    depth = _texts(records)
    # The Depth Chart shows the run roster; its limited perks carry live match badges.
    badges = [text for text in depth if text.split(" ")[0] in ("1/DRIVE", "1/HALF", "1/GAME", "CHARGE")]
    # (Players this scenario swapped out of the match roster show no live badge.)
    assert any(text.split(" ")[-1] in ("READY", "USED", "ARMED", "IDLE") for text in badges)


def test_read_keys_shows_the_rival_hand_toggles_with_r_and_closes_on_the_scheme(tmp_path: Path) -> None:
    desktop, controller, simulator = _scenario(tmp_path, (K.READ_KEYS,), (), possession=B)
    assert controller.state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME
    texts = _texts(_show(desktop))
    assert READ_KEYS_TITLE in texts
    rival = [card.card_id for card in controller.state.match.team_b_offense_deck.hand]
    assert len(rival) == 3 and "SHORT PASS" in texts or len(rival) == 3
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r}))
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert READ_KEYS_TITLE not in _texts(records)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r}))
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert READ_KEYS_TITLE in _texts(records)
    # Choosing a scheme (number key 1 = the first playable card) closes it.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_1}))
    assert controller.state.human_decision is not FootballHumanDecision.DEFENSIVE_SCHEME
    _skip_match_playback(desktop)
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert READ_KEYS_TITLE not in _texts(records)


def _green_dog(tmp_path: Path):
    desktop, controller, simulator = _scenario(tmp_path, (K.GREEN_DOG,), (), possession=B)
    _select(simulator, "rb_run")
    simulator.state = replace(simulator.state, down=3, yards_to_go=4.0)
    ensure_in_hand(simulator, B, "deep_pass")
    snap(simulator, "deep_pass", yards=6.0)
    assert controller.state.human_decision is FootballHumanDecision.GREEN_DOG
    return desktop, controller, simulator


def test_green_dog_prompt_keeps_with_key_1(tmp_path: Path) -> None:
    desktop, controller, _simulator = _green_dog(tmp_path)
    texts = _texts(_show(desktop))
    assert GREEN_DOG_TITLE in texts and GREEN_DOG_PROMPT in texts
    assert any(text.startswith("KEEP ") for text in texts)
    count = len(controller.state.match.match_events)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_1}))
    events = controller.state.match.match_events
    assert events[count].action is FootballPerkDecision.GREEN_DOG_DECLINE


def test_green_dog_prompt_swaps_with_key_2(tmp_path: Path) -> None:
    desktop, controller, _simulator = _green_dog(tmp_path)
    _show(desktop)
    hand = controller.state.match.team_a_defense_deck.hand
    count = len(controller.state.match.match_events)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2}))
    event = controller.state.match.match_events[count]
    assert event.action is FootballPerkDecision.GREEN_DOG_SWAP
    assert event.card_copy_id == hand[0].copy_id


def test_green_dog_panel_waits_for_the_replay(tmp_path: Path) -> None:
    desktop, controller, _simulator = _green_dog(tmp_path)
    desktop.run_screen.state = controller.state
    screen = desktop.run_screen.match_screen
    screen.playback.reset()
    desktop.router.draw(_surface())
    events = controller.state.match.match_events
    screen.playback.debug_show(len(events) - 2, screen.clock())
    screen.playback.target = len(events)
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert screen.playback.blocking()
    assert GREEN_DOG_TITLE not in _texts(records) and GREEN_DOG_PROMPT not in _texts(records)


def test_replay_snapshots_show_each_events_callouts_and_the_final_hands(tmp_path: Path) -> None:
    desktop, controller, simulator = _scenario(tmp_path, (K.MOTION_JUMP,), (K.EDGE_SET,))
    _select(simulator, "rb_run")
    ensure_in_hand(simulator, A, "screen_pass")
    snap(simulator, "screen_pass", yards=3.0)
    ensure_in_hand(simulator, A, "rb_run")
    snap(simulator, "rb_run", randoms=(0.0,))  # a fumble ends the drive
    match = controller.state.match
    first_play = next(index for index, event in enumerate(match.match_events) if event.play_result)
    snapshot = snapshot_state(match, first_play + 1)
    assert {a.kind for a in snapshot.match_events[-1].perk_activations} == {K.MOTION_JUMP, K.EDGE_SET}
    # Events carry no deck snapshots: mid-replay hands are the final, trimmed ones.
    assert snapshot.team_a_offense_deck == match.team_a_offense_deck
    assert len(snapshot.team_a_offense_deck.hand) == 3
    assert len(snapshot.team_b_defense_deck.hand) == 2


def test_no_planned_or_inactive_text_on_draft_depth_chart_or_match_screens(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    seen: list[str] = []
    for _ in range(2):
        with text_audit() as records:
            desktop.router.draw(_surface())
        seen += _texts(records)
        _activate(desktop, desktop.run_screen.buttons[0].label, keyboard=True)
    desktop = _new_desktop(tmp_path / "second")
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.shop_review
    interaction.clock = lambda: 10**7
    for position in ("QB", "RB", "WR", "O_LINE", "D_LINE", "LINEBACKERS", "CORNERBACKS", "SAFETIES"):
        interaction.flips[("player", position)] = (True, 0)
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    seen += _texts(records)
    assert not any("PLANNED" in text.upper() or "INACTIVE" in text.upper() for text in seen)


# -- perk headings: the name is never shortened --------------------------------------

_SPECIALISTS_BY_POSITION = {
    position: [player_type for player_type in PLAYER_TYPES_BY_PERK.values() if player_type.position is position]
    for position in FootballPosition
}


def _specialist_rosters(roster):
    """Six rosters that together field all 48 specialists, one per position each."""
    for index in range(6):
        players = dict(roster.players)
        for position, types in _SPECIALISTS_BY_POSITION.items():
            player_type = types[index]
            players[position] = player_from_type(player_type, name=player_type.name)
        yield replace(roster, players=players)


def _assert_full_perk_names(records, roster) -> None:
    texts = _texts(records)
    for player in roster.players.values():
        perk = PLAYER_TYPES_BY_PERK_ID[player.player_type_id].perk
        assert perk.name.upper() in texts, perk.name
    assert not any(text.endswith("...") for text in texts if text.isupper()), texts
    # Card lines are never shortened either: every word of each one is drawn.
    from src.ui.football_player_perks import perk_card_line

    words = " ".join(texts).split()
    for player in roster.players.values():
        line = perk_card_line(PLAYER_TYPES_BY_PERK_ID[player.player_type_id].perk)
        assert not any(text.endswith("...") and line.startswith(text[:-3]) for text in texts), line
        assert all(word in words for word in line.split()), line


PLAYER_TYPES_BY_PERK_ID = {player_type.type_id: player_type for player_type in PLAYER_TYPES_BY_PERK.values()}


def test_depth_chart_fronts_show_every_perk_name_in_full_with_each_status(tmp_path: Path, monkeypatch) -> None:
    import src.ui.football_depth_chart as depth_chart

    assert sum(len(types) for types in _SPECIALISTS_BY_POSITION.values()) == 48
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    shop = desktop.football_controller._shop
    _activate(desktop, "DEPTH CHART")
    for roster in _specialist_rosters(shop.roster):
        shop._roster = roster
        desktop.run_screen.state = desktop.football_controller.state
        with text_audit() as records:
            desktop.router.draw(_surface())
        _assert_text_fits(records)
        _assert_full_perk_names(records, roster)

    desktop = _new_desktop(tmp_path / "match")
    _start_match(desktop)
    _skip_match_playback(desktop)
    shop = desktop.football_controller._shop
    screen = desktop.run_screen.match_screen
    screen.open_depth_chart()
    for status in ("READY", "USED", "ARMED", "IDLE"):
        monkeypatch.setattr(depth_chart, "perk_status_for", lambda *_args, _status=status: _status)
        for roster in _specialist_rosters(shop.roster):
            shop._roster = roster
            desktop.run_screen.state = desktop.football_controller.state
            with text_audit() as records:
                desktop.router.draw(_surface())
            _assert_text_fits(records)
            _assert_full_perk_names(records, roster)
            limited = [p for p in roster.players.values()
                       if PLAYER_TYPES_BY_PERK_ID[p.player_type_id].perk.limit.value != "every"]
            assert sum(text.endswith(f" {status}") for text in _texts(records)) == len(limited)


def test_perk_heading_shrinks_then_stacks_without_shortening_the_name() -> None:
    from src.ui.football_player_draft_view import draw_perk_heading, perk_heading_layout

    perk = PLAYER_TYPES_BY_PERK[K.RELEASE_READ].perk
    assert perk_heading_layout(perk, None, 400) == (14, False)
    size, stacked = perk_heading_layout(perk, "READY", 150)
    assert stacked
    surface = pygame.Surface((200, 80))
    row = pygame.Rect(4, 4, 150, 16)
    with text_audit() as records:
        bottom = draw_perk_heading(surface, row, perk, "READY")
    assert bottom > row.bottom
    texts = _texts(records)
    assert perk.name.upper() in texts and "WITH OL" in texts and "1/DRIVE READY" in texts
    for _text, rect, _container in records:
        assert rect.bottom <= bottom and rect.right <= row.right


def test_draft_cards_show_every_perk_name_in_full(tmp_path: Path) -> None:
    from src.engine.football_team_builder import FootballPlayerCandidate

    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    state = desktop.football_controller.state
    shown = 0
    for types in _SPECIALISTS_BY_POSITION.values():
        for start in (0, 3):
            offer = tuple(
                FootballPlayerCandidate(player_from_type(player_type, name=player_type.name), "")
                for player_type in types[start:start + 3]
            )
            desktop.run_screen.state = replace(state, team_builder=replace(state.team_builder, current_offer=offer))
            with text_audit() as records:
                desktop.run_screen.draw(_surface())
            _assert_text_fits(records)
            texts = _texts(records)
            for player_type in types[start:start + 3]:
                assert player_type.perk.name.upper() in texts, player_type.perk.name
                shown += 1
            assert not any(text.endswith("...") for text in texts), [t for t in texts if t.endswith("...")]
    assert shown == 48
