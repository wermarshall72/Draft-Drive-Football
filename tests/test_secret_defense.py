"""The rival's defense call is secret, previews and AI offense are blind, and the
perk tray shows every perk with a hover tooltip and a click/Enter rules popup."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballDeckState,
    FootballPerkActivation,
    FootballPerkDecision,
)
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG
from src.engine.football_perk_context import (
    DEFENSE_SCHEME_KEYED_PERKS,
    OFFENSE_SCHEME_KEYED_PERKS,
    scheme_keyed_defense,
)
from src.engine.football_simulator import (
    calculate_blind_play_estimate,
    calculate_match_play_estimate,
    defense_call_weights,
)
from src.ui.football_match_events import outcome, perk_callouts, perk_log_text, shown_perk_effects
from src.ui.football_match_perks import ALWAYS_ON, tray_perks
from src.ui.football_match_screen import (
    FIELD_RECT, HAND_RECT, PERK_TRAY_RECT, SCOREBOARD_RECT, STRIP_RECT,
)
from src.ui.football_player_perks import perk_card_line, perk_rules
from src.ui.football_tips import TIP_IDS
from src.ui.football_ui_kit import text_audit
from src.ui.layout import LOGICAL_SIZE

from perk_helpers import A, B, K, deck, ensure_in_hand, fired, roster, simulator, snap
from test_football_desktop import _skip_match_playback
from test_football_perk_ui import _scenario, _select, _show, _texts

DEEP_CALL = DEFENSIVE_SCHEME_CATALOG["deep_pass"].name.upper()
RUN_ONLY_SCHEMES = ("rb_run", "goal_line_front", "spill_front", "bear_front")


def _surface() -> pygame.Surface:
    return pygame.Surface(LOGICAL_SIZE)


def _draw(desktop) -> list:
    with text_audit() as records:
        desktop.router.draw(_surface())
    return records


def _assert_no_reveal(texts: list[str], call: str = DEEP_CALL, family: str = "DEEP PASS") -> None:
    joined = "\n".join(texts)
    assert call not in joined.upper()
    assert f"STOPS {family}" not in joined.upper()
    assert "STOPPED" not in joined
    assert "Stopped by" not in joined and "Open" not in texts


def _ai_defends_deep(tmp_path: Path, a_kinds=(), b_kinds=(K.DEEP_LOCK, K.EDGE_SET)):
    """The human (Team A) has the ball; the rival's secret call is Deep. The human's
    defense deck holds only run-front calls, so no Deep call name is on screen.
    The human's roster carries exactly ``a_kinds`` (everyone else is Basic)."""
    desktop, controller, sim = _scenario(
        tmp_path, (), b_kinds,
        team_a=roster("Test Owls", *a_kinds),
        team_a_defense_deck=FootballDeckState(deck("ad", RUN_ONLY_SCHEMES, 0).owned),
    )
    desktop.run_screen.tips.seen.update(TIP_IDS)  # one-time tips would cover the strip
    desktop.run_screen.tips.dismiss()
    _select(sim, "deep_pass")
    for card in ("deep_pass", "short_pass", "rb_run"):
        ensure_in_hand(sim, A, card)
    return desktop, controller, sim


# -- what the human never sees ------------------------------------------------------------

def test_rival_call_never_shows_on_strip_field_hand_tooltip_or_log(tmp_path: Path) -> None:
    desktop, controller, sim = _ai_defends_deep(tmp_path)
    texts = _texts(_show(desktop))
    assert any(text.endswith("SET THEIR DEFENSE") for text in texts)
    assert not any(text.endswith("DEFENSE: " + DEEP_CALL) for text in texts)
    _assert_no_reveal(texts)
    # A stopped Deep catch capped by the rival's Deep Lock: neither shows.
    snap(sim, "deep_pass", yards=14.0)
    assert fired(sim.state, K.DEEP_LOCK, B)
    texts = _texts(_show(desktop))
    _assert_no_reveal(texts)
    assert not any("DEEP LOCK" in text for text in texts)
    # The hover tooltip on an offense card.
    screen = desktop.run_screen.match_screen
    now = [50_000]
    screen.clock = lambda: now[0]
    card = next(b for b in desktop.run_screen.buttons if b.variant == "hand-card")
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=card.rect.center))
    _draw(desktop)
    now[0] += 600
    texts = _texts(_draw(desktop))
    assert screen.card_tip_rect is not None
    _assert_no_reveal(texts)
    # The Play Log renders each event's outcome, coach effects, and perk line.
    screen.open_play_log()
    _draw(desktop)
    events = controller.state.match.match_events
    log = []
    for index, event in enumerate(events):
        previous = events[index - 1] if index else None
        result = outcome(event, previous, "Test Owls", "Embers")
        log += [result.headline, result.detail, perk_log_text(event),
                *shown_perk_effects(event, previous)]
    assert any(text.endswith("SET THEIR DEFENSE") for text in log)
    assert not any("Deep Lock" in text for text in log)
    _assert_no_reveal(log)


def test_replay_text_never_names_the_rival_call(tmp_path: Path) -> None:
    desktop, controller, sim = _ai_defends_deep(tmp_path)
    screen = desktop.run_screen.match_screen
    now = [10_000]
    screen.clock = lambda: now[0]
    _show(desktop)
    snap(sim, "deep_pass", yards=14.0)
    snap(sim, "short_pass")
    desktop.run_screen.state = controller.state
    seen = []
    for _ in range(6):
        seen += _texts(_draw(desktop))
        now[0] += 1_000
    assert any(text.startswith("REPLAYING") for text in seen)
    _assert_no_reveal(seen)


def test_green_dog_swap_by_the_rival_says_only_that_it_changed() -> None:
    sim = simulator(scheme="deep_pass")
    template = sim.state.match_events[-1]
    swap = replace(template, action=FootballPerkDecision.GREEN_DOG_SWAP, card_id="medium_pass",
                   possession=A, perk_activations=(FootballPerkActivation(K.GREEN_DOG, B),))
    result = outcome(swap, template, "Home", "Away")
    text = f"{result.headline} {result.detail} {' '.join(result.callouts)}"
    assert result.headline == "GREEN DOG · DEFENSE CHANGED"
    assert "AWAY CHANGED THEIR DEFENSE" in text
    assert DEFENSIVE_SCHEME_CATALOG["medium_pass"].name.upper() not in text
    assert "STOPS" not in text
    keep = replace(swap, action=FootballPerkDecision.GREEN_DOG_DECLINE, card_id=None,
                   card_copy_id=None, perk_activations=())
    kept = outcome(keep, template, "Home", "Away")
    assert "STOPS" not in kept.detail and "KEPT THEIR DEFENSE" in kept.detail
    # The human's own swap still names the new call.
    own = outcome(replace(swap, possession=B), template, "Home", "Away")
    assert DEFENSIVE_SCHEME_CATALOG["medium_pass"].name.upper() in own.headline


@pytest.mark.parametrize("kind", sorted(DEFENSE_SCHEME_KEYED_PERKS, key=lambda kind: kind.value))
def test_rival_defensive_perks_keyed_to_its_call_are_hidden(kind) -> None:
    event = simulator().state.match_events[-1]
    for applied in (False, True):
        rival = replace(event, perk_activations=(FootballPerkActivation(kind, B, 1.0, applied),))
        own = replace(event, perk_activations=(FootballPerkActivation(kind, A, 1.0, applied),))
        if kind is K.CAPTAINS_ADJUSTMENT and not applied:
            assert perk_callouts(rival)  # the trigger (a rival run first down) needs no call
            continue
        assert perk_callouts(rival) == () and perk_log_text(rival) == ""
        assert perk_callouts(own) and perk_log_text(own)  # the human's own defense shows


def test_human_offense_perks_that_fire_only_against_a_stop_are_hidden() -> None:
    event = simulator().state.match_events[-1]
    hidden = (
        FootballPerkActivation(K.SILENT_COUNT, A),
        FootballPerkActivation(K.SCREEN_WALL, A, 8.0, True),
    )
    for activation in hidden:
        assert perk_callouts(replace(event, perk_activations=(activation,))) == ()
        # The rival's version runs into the human's own call, so it shows.
        rival = replace(activation, team=B)
        assert perk_callouts(replace(event, perk_activations=(rival,)))
    trigger = replace(event, perk_activations=(FootballPerkActivation(K.SCREEN_WALL, A),))
    assert perk_callouts(trigger)  # a completed Screen needs no call
    hot = perk_callouts(replace(event, perk_activations=(FootballPerkActivation(K.HOT_ROUTE, A),)))
    assert hot == ("HOT ROUTE · Route Technician · SWAPPED A CARD",)
    assert OFFENSE_SCHEME_KEYED_PERKS == {K.SILENT_COUNT, K.HOT_ROUTE, K.SCREEN_WALL}


def test_coach_effects_that_reveal_a_stop_are_hidden_from_the_offense() -> None:
    sim = simulator(scheme="deep_pass")
    before = sim.state.match_events[-1]
    snap(sim, "deep_pass")
    effects = (
        "Coverage: +5 percentage points to incompletion chance",
        "Pressure / Blitz: +5 percentage points to interception chance",
        "Run Stop: -2 yards on RB Run vs. RB Run scheme",
        "Pro Style: +2 yards on a first-down pass",
    )
    event = sim.state.match_events[-1]
    play = replace(event, perk_effects=effects,
                   play_result=replace(event.play_result, perk_effects=effects))
    assert shown_perk_effects(play, before) == ("Pro Style: +2 yards on a first-down pass",)
    defending = simulator(scheme="deep_pass", offense=B)
    before = defending.state.match_events[-1]
    snap(defending, "deep_pass")
    event = defending.state.match_events[-1]
    rival_play = replace(event, perk_effects=effects,
                         play_result=replace(event.play_result, perk_effects=effects))
    assert len(shown_perk_effects(rival_play, before)) == 4  # the human's own call


# -- what the human still sees --------------------------------------------------------------

def test_human_defense_still_shows_its_own_call_and_stops(tmp_path: Path) -> None:
    desktop, controller, sim = _scenario(tmp_path, (), (), possession=B)
    _select(sim, "medium_pass")
    texts = _texts(_show(desktop))
    name = DEFENSIVE_SCHEME_CATALOG["medium_pass"].name.upper()
    assert f"YOUR DEFENSE: {name}" in texts
    assert f"DEFENSE SET · {name}" in texts
    assert any(text.endswith("· STOPS MEDIUM PASS") for text in texts)


# -- the blind estimate -----------------------------------------------------------------------

def test_blind_estimate_is_the_deck_weighted_average_and_ignores_the_real_call() -> None:
    owned = ("deep_pass", "deep_pass", "deep_pass", "rb_run", "medium_pass", "goal_line_front")
    sim = simulator((K.MOTION_JUMP,), (K.EDGE_SET, K.NICKEL_LOCK), scheme="deep_pass",
                    b_decks={"offense": deck("bo", ("rb_run",) * 6, 3),
                             "defense": deck("bd", owned, 2)})
    state = sim.state
    weights = dict(defense_call_weights(state, B))
    assert weights == pytest.approx({
        DefensiveSchemeAction.RB_RUN: 2 / 6,
        DefensiveSchemeAction.MEDIUM_PASS: 1 / 6,
        DefensiveSchemeAction.DEEP_PASS: 3 / 6,
    })
    for play_id in ("short_pass", "rb_run", "deep_pass", "screen_pass"):
        play = OFFENSIVE_PLAY_CATALOG[play_id].action
        blind = calculate_blind_play_estimate(state, play)
        expected = sum(
            weight * calculate_match_play_estimate(state, play, scheme=scheme).expected_yards
            for scheme, weight in weights.items()
        )
        assert blind.expected_yards == pytest.approx(expected)
        for hidden in DefensiveSchemeAction:
            other = calculate_blind_play_estimate(replace(state, current_drive_defensive_scheme=hidden), play)
            assert other.expected_yards == pytest.approx(blind.expected_yards)
            assert other.first_down_probability(10.0) == pytest.approx(blind.first_down_probability(10.0))
        # Only perks that fire whatever the call is are previewed.
        assert all(scheme_keyed_defense(activation) is None for activation in blind.player_perks)


def test_card_numbers_use_the_blind_estimate(tmp_path: Path) -> None:
    desktop, controller, sim = _ai_defends_deep(tmp_path)
    texts = _texts(_show(desktop))
    match_state = controller.state.match
    for card_id in ("deep_pass", "short_pass", "rb_run"):
        blind = calculate_blind_play_estimate(match_state, OFFENSIVE_PLAY_CATALOG[card_id].action)
        assert f"~{blind.expected_yards:.1f}" in texts
    real = calculate_match_play_estimate(match_state, OFFENSIVE_PLAY_CATALOG["deep_pass"].action)
    blind = calculate_blind_play_estimate(match_state, OFFENSIVE_PLAY_CATALOG["deep_pass"].action)
    assert f"~{real.expected_yards:.1f}" != f"~{blind.expected_yards:.1f}"


# -- the AI's offense is blind ----------------------------------------------------------------

@pytest.mark.parametrize("difficulty", [FootballAIDifficulty.STANDARD, FootballAIDifficulty.HARD])
def test_ai_offense_choices_do_not_depend_on_the_human_call(difficulty) -> None:
    kinds = (K.SILENT_COUNT, K.MOTION_JUMP, K.CHECKDOWN, K.PULL_LEAD, K.KEEP_READ)
    for down, distance, position in ((1, 10.0, 40.0), (3, 2.0, 70.0), (3, 9.0, 30.0), (4, 1.0, 92.0)):
        sim = simulator((K.EDGE_SET, K.FORCE_AND_FOLD, K.SAFETY_BLITZ), kinds, scheme="rb_run",
                        offense=B)
        sim.state = replace(sim.state, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
                            down=down, yards_to_go=distance, offense_field_position=position)
        choices = set()
        conversions = set()
        for hidden in DefensiveSchemeAction:
            state = replace(sim.state, current_drive_defensive_scheme=hidden)
            choices.add(FootballAI(B, difficulty, 5).choose_action(state))
            conversion = replace(state, awaited_action=FootballAwaitedAction.CONVERSION,
                                 conversion_team=B, offense_field_position=98.0, down=1,
                                 yards_to_go=2.0)
            conversions.add(FootballAI(B, difficulty, 5).choose_conversion_card(conversion))
        assert len(choices) == 1
        assert len(conversions) == 1


# -- the perk tray ----------------------------------------------------------------------------

EIGHT = (K.SILENT_COUNT, K.KEEP_READ, K.HOT_ROUTE, K.PULL_LEAD,
         K.EDGE_SET, K.READ_KEYS, K.DEEP_LOCK, K.TIP_DRILL)


def _tray_desktop(tmp_path: Path):
    desktop, controller, sim = _ai_defends_deep(tmp_path, EIGHT, ())
    _show(desktop)
    return desktop, controller, sim


def _chips(desktop):
    return [b for b in desktop.run_screen.buttons if b.variant == "perk-chip"]


def test_tray_shows_every_specialist_with_status_and_fits(tmp_path: Path) -> None:
    desktop, controller, sim = _tray_desktop(tmp_path)
    records = _draw(desktop)
    texts = _texts(records)
    chips = _chips(desktop)
    assert len(chips) == 8 and "PERKS" in texts
    assert [b.label for b in chips] == [
        f"PERK {item.perk.name.upper()}" for item in tray_perks(controller.state.match)
    ]
    for label in ("QB", "RB", "WR", "OL", "DL", "LB", "CB", "S"):
        assert label in texts
    statuses = {item.perk.kind: item.status for item in tray_perks(controller.state.match)}
    assert statuses[K.SILENT_COUNT] == "READY" and statuses[K.KEEP_READ] == "READY"
    assert statuses[K.PULL_LEAD] is None and statuses[K.DEEP_LOCK] is None  # always on
    assert not any(text.startswith("+") and text[1:].isdigit() for text in texts)  # no "+N"
    rects = [b.rect for b in chips]
    assert all(rect.height >= 22 for rect in rects)
    assert all(PERK_TRAY_RECT.contains(rect) and SCOREBOARD_RECT.contains(rect) for rect in rects)
    assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])
    clock_panel = pygame.Rect(0, 0, 360, SCOREBOARD_RECT.height - 4)
    clock_panel.midtop = (SCOREBOARD_RECT.centerx, SCOREBOARD_RECT.top + 2)
    team = controller.state.match.team_a.team_name.upper()
    name_rect = next(rect for text, rect, _ in records if text == team)
    score_rect = next(rect for text, rect, _ in records
                      if text == "0" and rect.left < PERK_TRAY_RECT.left and rect.height > 40)
    for rect in rects:
        assert not rect.colliderect(clock_panel)
        assert not rect.colliderect(name_rect) and not rect.colliderect(score_rect)
        assert rect.left > score_rect.right + 40  # clear of the football icon too
    # Basic players carry no chip.
    desktop2, controller2, _ = _ai_defends_deep(tmp_path / "two", (K.SILENT_COUNT, K.TIP_DRILL), ())
    _show(desktop2)
    assert len(_chips(desktop2)) == 2


def test_tray_hover_tooltip_appears_after_the_delay(tmp_path: Path) -> None:
    desktop, controller, sim = _tray_desktop(tmp_path)
    screen = desktop.run_screen.match_screen
    now = [20_000]
    screen.clock = lambda: now[0]
    _draw(desktop)
    chip = _chips(desktop)[0]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=chip.rect.center))
    _draw(desktop)
    assert screen.perk_tip_rect is None
    now[0] += 600
    records = _draw(desktop)
    texts = _texts(records)
    rect = screen.perk_tip_rect
    perk = tray_perks(controller.state.match)[0].perk
    assert rect is not None
    assert perk.name.upper() in texts and perk_card_line(perk) in texts
    assert "QB · 1/HALF · READY" in texts
    assert rect.top >= SCOREBOARD_RECT.bottom and not rect.colliderect(HAND_RECT)
    assert not rect.colliderect(STRIP_RECT)
    # Esc hides it without pausing.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    _draw(desktop)
    assert screen.perk_tip_rect is None and not screen.popup.open


def _rules_lines_shown(texts, perk) -> bool:
    words = " ".join(texts)
    return all(word in words for word in perk_rules(perk).split()[:6])


def test_tray_click_and_enter_open_the_rules_popup_and_esc_closes(tmp_path: Path) -> None:
    desktop, controller, sim = _tray_desktop(tmp_path)
    screen = desktop.run_screen.match_screen
    events_before = len(controller.state.match.match_events)
    decision = controller.state.human_decision
    chip = _chips(desktop)[6]  # CB: Deep Lock (always on)
    perk = tray_perks(controller.state.match)[6].perk
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=chip.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=chip.rect.center, button=1))
    records = _draw(desktop)
    texts = _texts(records)
    assert screen.perk_popup_rect is not None
    assert _rules_lines_shown(texts, perk)
    assert "PARTNER  SAFETIES" in texts and f"STATUS  {ALWAYS_ON}" in texts
    assert not screen.perk_popup_rect.colliderect(HAND_RECT)
    assert not screen.perk_popup_rect.colliderect(STRIP_RECT)
    # A click on a hand card only closes the popup: no play is made.
    card = next(b for b in desktop.run_screen.buttons if b.variant == "hand-card")
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=card.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=card.rect.center, button=1))
    _draw(desktop)
    assert screen.perk_popup_key is None
    assert len(controller.state.match.match_events) == events_before
    # Keyboard: Tab to the first chip (after the hand), Enter opens, Esc closes.
    buttons = desktop.run_screen.buttons
    first_chip = next(i for i, b in enumerate(buttons) if b.variant == "perk-chip")
    assert all(b.variant != "hand-card" for b in buttons[first_chip:])
    desktop.run_screen._focus(first_chip)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    texts = _texts(_draw(desktop))
    first = tray_perks(controller.state.match)[0].perk
    assert screen.perk_popup_rect is not None and _rules_lines_shown(texts, first)
    # Number keys and Enter never play a card while the popup is open.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
    assert len(controller.state.match.match_events) == events_before
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    _draw(desktop)
    assert screen.perk_popup_key is None and not screen.popup.open
    assert not desktop.run_screen.pause.is_open
    assert controller.state.human_decision is decision
    assert len(controller.state.match.match_events) == events_before


def test_tray_works_during_replays_without_advancing_them(tmp_path: Path) -> None:
    desktop, controller, sim = _tray_desktop(tmp_path)
    screen = desktop.run_screen.match_screen
    now = [30_000]
    screen.clock = lambda: now[0]
    _draw(desktop)
    snap(sim, "short_pass")
    snap(sim, "short_pass")
    desktop.run_screen.state = controller.state
    _draw(desktop)
    assert screen.playback.blocking()
    shown = screen.playback.shown
    chip = _chips(desktop)[1]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=chip.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=chip.rect.center, button=1))
    _draw(desktop)
    assert screen.perk_popup_rect is not None
    assert screen.playback.blocking() and screen.playback.shown == shown
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
    assert screen.playback.blocking()  # keys go to the open popup, not the replay
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    _draw(desktop)
    assert screen.perk_popup_key is None
    _skip_match_playback(desktop)
