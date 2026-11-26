"""First-time player help: "stops" wording, STOPPED tags, card tooltips, the
defense prompt and scouting line, one-time tips, and the How to Play page."""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCardFamily,
    FootballDeckState,
    FootballTeamSide,
)
from src.engine.football_controller import FootballHumanDecision, FootballRunPhase
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG
from src.engine.football_simulator import (
    adjusted_offensive_play_clock_seconds,
    calculate_match_play_estimate,
)
from src.profile import TeamProfile, load_profile, save_profile
from src.ui.application import DesktopApplication
from src.ui.football_match_hand import STOPPED_TAG
from src.ui.football_match_outcome import (
    DEFENSE_PROMPT,
    DEFENSE_SUBLINE,
    prompt_lines,
    scouting_line,
    status_prompt,
)
from src.ui.football_match_screen import FIELD_RECT, HAND_RECT, SCOREBOARD_RECT, STRIP_RECT
from src.ui.football_tips import (
    GOT_IT,
    TIP_DEFENSE,
    TIP_FOURTH_DOWN,
    TIP_IDS,
    TIP_OFFENSE,
    TIP_SHOP,
    TIP_TEXT,
    TIP_TWO_POINT,
    TipState,
)
from src.ui.football_ui_kit import text_audit
from src.ui.how_to_play import SECTIONS
from src.ui.layout import LOGICAL_SIZE
from src.ui.profile_screen import RESET_TIPS

from test_football_desktop import (
    _activate,
    _assert_text_fits,
    _draft_to_shop,
    _new_desktop,
    _play_human_decision,
    _skip_match_playback,
    _start_match,
    _start_run,
)

UI_DIR = Path(__file__).resolve().parents[1] / "src" / "ui"


def _surface() -> pygame.Surface:
    return pygame.Surface(LOGICAL_SIZE)


def _draw(desktop: DesktopApplication) -> list[tuple[str, pygame.Rect, pygame.Rect]]:
    with text_audit() as records:
        desktop.router.draw(_surface())
    return records


def _texts(records) -> list[str]:
    return [text for text, _rect, _container in records]


def _mark_all_seen(desktop: DesktopApplication) -> None:
    desktop.run_screen.tips.seen.update(TIP_IDS)
    desktop.run_screen.tips.dismiss()


def _drive_to(desktop: DesktopApplication, decision: FootballHumanDecision, limit: int = 400) -> None:
    controller = desktop.football_controller
    for _ in range(limit):
        _skip_match_playback(desktop)
        current = controller.state.human_decision
        if current is decision:
            desktop.router.draw(_surface())
            return
        if current is FootballHumanDecision.GREEN_DOG:
            next(b for b in desktop.run_screen.buttons if b.variant == "strip-primary").action()
        else:
            _play_human_decision(desktop)
    raise AssertionError(f"never reached {decision}")


def _set_offense(desktop: DesktopApplication, scheme: DefensiveSchemeAction,
                 card_ids: tuple[str, ...]) -> None:
    """At a human offensive call, set the rival's defense call and the human's hand."""
    controller = desktop.football_controller
    simulator = controller._simulator
    state = simulator.state
    offense = state.team_a_offense_deck
    hand = tuple(FootballCardCopy(f"help-hand-{i}", card_id) for i, card_id in enumerate(card_ids))
    deck = FootballDeckState(offense.owned + hand, draw_pile=offense.draw_pile + offense.hand,
                             hand=hand, discard_pile=offense.discard_pile)
    simulator.state = replace(state, team_a_offense_deck=deck, current_drive_defensive_scheme=scheme)
    desktop.run_screen.state = controller.state


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


# -- wording ------------------------------------------------------------------------

def test_no_player_facing_counters_wording_remains_in_ui_strings() -> None:
    pattern = re.compile(r"\bcounter(s|ed)?\b", re.IGNORECASE)
    offenders = []
    for path in UI_DIR.glob("*.py"):
        for text in _string_literals(path):
            # Code names in docstrings and the Counter Run play are not player-facing wording.
            cleaned = re.sub(r"counter run", "", text, flags=re.IGNORECASE)
            if pattern.search(cleaned) and "\n" not in text.strip():
                offenders.append((path.name, text))
    assert offenders == []


def test_stops_wording_on_hand_strip_shop_and_playbook(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    shop_texts = _texts(_draw(desktop))
    _activate(desktop, "PLAYBOOK")
    playbook_texts = _texts(_draw(desktop))
    assert "STOPS" in playbook_texts and "DEFENSE CALL" in playbook_texts
    desktop.run_screen._leave_shop_review()
    _activate(desktop, "FINISH SHOP / START MATCH")
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    match_texts = _texts(_draw(desktop))
    assert "STOPS" in match_texts and "DEFENSE CALL" in match_texts
    assert any("· STOPS " in text for text in match_texts)  # "EMBERS · STOPS MEDIUM PASS"
    for texts in (shop_texts, playbook_texts, match_texts):
        assert not [t for t in texts if "COUNTER" in t.upper() and "COUNTER RUN" not in t.upper()]


def test_shop_scheme_cards_say_stops() -> None:
    from src.ui.football_inspect import scheme_inspect
    definition = next(iter(DEFENSIVE_SCHEME_CATALOG.values()))
    content = scheme_inspect(definition, None, 2)
    headings = [section[0] for section in content.sections]
    assert "Stops" in headings and content.tag == "Defense call"


# -- STOPPED tags and the card tooltip ----------------------------------------------

def _stopped(match, card_id: str) -> bool:
    action = OFFENSIVE_PLAY_CATALOG[card_id].action
    return calculate_match_play_estimate(
        match, action, offense_side=FootballTeamSide.TEAM_A,
    ).matchup.scheme_matches_play


def test_stopped_tag_marks_exactly_the_stopped_offense_cards(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _mark_all_seen(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_offense(desktop, DefensiveSchemeAction.DEEP_PASS, ("deep_pass", "rb_run", "short_pass"))
    records = _draw(desktop)
    match = desktop.football_controller.state.match
    cards = {b.label: b.rect for b in desktop.run_screen.buttons if b.variant == "hand-card"}
    tag_rects = [rect for text, rect, _ in records if text == STOPPED_TAG]
    expected = {name for name, card_id in (("DEEP PASS", "deep_pass"), ("INSIDE RUN", "rb_run"),
                                            ("QUICK SLANT", "short_pass")) if _stopped(match, card_id)}
    assert expected == {"DEEP PASS"}
    tagged = {name for name, rect in cards.items()
              if any(rect.inflate(0, 20).contains(tag) for tag in tag_rects)}
    assert tagged == expected
    assert len(tag_rects) == len(expected)
    # Defense cards never carry the tag.
    defense = [b.rect for b in desktop.run_screen.buttons if b.variant == "hand-card"
               and b.label not in cards]
    assert not any(rect.colliderect(tag) for rect in defense for tag in tag_rects)
    _assert_text_fits(records)


def test_no_stopped_tags_during_replays(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_offense(desktop, DefensiveSchemeAction.DEEP_PASS, ("deep_pass", "deep_pass", "rb_run"))
    assert STOPPED_TAG in _texts(_draw(desktop))
    screen = desktop.run_screen.match_screen
    state = desktop.football_controller.state
    with text_audit() as records:
        screen.hand.draw(
            _surface(), HAND_RECT, state, state.match, screen.interaction, input_blocked=True,
            focus_index=0, hover_index=None, pressed_index=None, button_offset=0,
            choose_card=lambda _copy_id: None, choose_fallback=lambda _offensive: None,
        )
    assert STOPPED_TAG not in _texts(records)
    assert screen.hand.tooltip_targets == {}


def test_card_tooltip_lines_match_the_engine_estimate(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_offense(desktop, DefensiveSchemeAction.DEEP_PASS, ("deep_pass", "rb_run", "short_pass"))
    desktop.router.draw(_surface())
    match = desktop.football_controller.state.match
    hand = desktop.run_screen.match_screen.hand
    rival = match.team_b.team_name.upper()
    possessive = f"{rival}'" if rival.endswith("S") else f"{rival}'S"
    for card_id in ("deep_pass", "rb_run", "short_pass"):
        definition = OFFENSIVE_PLAY_CATALOG[card_id]
        estimate = calculate_match_play_estimate(match, definition.action)
        seconds = adjusted_offensive_play_clock_seconds(
            definition.clock_seconds, match.team_a_coach_upgrades)
        lines = hand.card_tooltip(match, card_id)
        assert lines[0] == f"~{estimate.expected_yards:.1f} yds expected"
        if definition.family is FootballCardFamily.RB_RUN:
            assert lines[1].endswith("fumble")
            value = float(lines[1][1:].split("%")[0])
            assert value == pytest.approx(estimate.turnover_probability * 100, abs=0.06)
        else:
            assert lines[1] == f"~{estimate.incomplete_probability * 100:.0f}% incomplete"
        assert lines[2] == f"{seconds}s clock"
        if estimate.matchup.scheme_matches_play:
            assert lines[3] == f"Stopped by {possessive} DEEP SHELL".replace(
                "DEEP SHELL", DEFENSIVE_SCHEME_CATALOG["deep_pass"].name.upper())
        else:
            assert lines[3] == "Open"


def test_card_tooltip_appears_after_a_short_hover_over_the_strip_only(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _mark_all_seen(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_offense(desktop, DefensiveSchemeAction.DEEP_PASS, ("deep_pass", "rb_run", "short_pass"))
    now = [10_000]
    screen = desktop.run_screen.match_screen
    screen.clock = lambda: now[0]
    desktop.router.draw(_surface())
    card = next(b for b in desktop.run_screen.buttons if b.label == "DEEP PASS")
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=card.rect.center))
    texts = _texts(_draw(desktop))
    assert screen.card_tip_rect is None
    now[0] += 500
    texts = _texts(_draw(desktop))
    rect = screen.card_tip_rect
    assert rect is not None and STRIP_RECT.contains(rect)
    assert not rect.colliderect(HAND_RECT) and not rect.colliderect(FIELD_RECT)
    assert any(text.startswith("Stopped by") for text in texts)
    # Esc hides the tooltip before it can pause.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    _draw(desktop)
    assert screen.card_tip_rect is None and not screen.popup.open
    # Keyboard focus shows it too, once the pointer has left the cards.
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(640, 200)))
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    _draw(desktop)
    now[0] += 500
    _draw(desktop)
    focused = desktop.run_screen.buttons[desktop.run_screen.focus_index]
    assert focused.variant == "hand-card" and focused.label != "DEEP PASS"
    assert screen.card_tip_rect is not None


def test_two_point_cards_keep_live_yards(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _mark_all_seen(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    simulator = desktop.football_controller._simulator
    simulator.state = replace(simulator.state, conversion_team=FootballTeamSide.TEAM_A,
                              awaited_action=FootballAwaitedAction.CONVERSION,
                              offense_field_position=98.0, down=1, yards_to_go=2.0)
    desktop.run_screen.state = desktop.football_controller.state
    texts = _texts(_draw(desktop))
    assert "YDS LIVE" in texts and "BASE YDS" not in texts


# -- the defense call -------------------------------------------------------------

def _scouting_match(card_ids: list[str], name: str = "Hounds"):
    owned = tuple(FootballCardCopy(f"c{i}", card_id) for i, card_id in enumerate(card_ids))
    return SimpleNamespace(team_b_offense_deck=SimpleNamespace(owned=owned),
                           team_b=SimpleNamespace(team_name=name))


def test_scouting_line_uses_the_whole_owned_deck() -> None:
    assert scouting_line(_scouting_match(["deep_pass", "deep_pass", "rb_run"])) == \
        "SCOUTING · HOUNDS LEAN DEEP PASS"
    assert scouting_line(_scouting_match(["deep_pass", "rb_run", "power_toss", "seam_pass"])) == \
        "SCOUTING · HOUNDS LEAN RB RUN"
    tie = scouting_line(_scouting_match(["deep_pass", "rb_run"]))
    assert tie == "SCOUTING · HOUNDS LEAN RB RUN OR DEEP PASS"
    assert scouting_line(_scouting_match(["deep_pass", "rb_run", "short_pass"])) == \
        "SCOUTING · HOUNDS SHOW NO CLEAR LEAN"
    assert scouting_line(_scouting_match([])) is None
    assert scouting_line(SimpleNamespace(team_b_offense_deck=None)) is None


def test_defense_prompt_sub_line_and_scouting_render_in_the_strip(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _mark_all_seen(desktop)
    _drive_to(desktop, FootballHumanDecision.DEFENSIVE_SCHEME)
    state = desktop.football_controller.state
    assert status_prompt(state) == DEFENSE_PROMPT == "PICK ONE DEFENSE FOR THIS DRIVE"
    lines = prompt_lines(state)
    assert lines[0] == DEFENSE_SUBLINE == "It stays until they score, punt, or turn it over"
    assert lines[1] == scouting_line(state.match) and lines[1].startswith("SCOUTING · ")
    records = _draw(desktop)
    in_strip = {text for text, rect, _ in records if STRIP_RECT.contains(rect)}
    assert {DEFENSE_PROMPT, DEFENSE_SUBLINE, lines[1]} <= in_strip
    _assert_text_fits(records)


# -- one-time tips ------------------------------------------------------------------

def test_shop_tip_shows_once_and_is_saved_to_the_profile(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    records = _draw(desktop)
    tips = desktop.run_screen.tips
    assert tips.current == TIP_SHOP and TIP_SHOP in tips.seen
    _assert_text_fits(records)
    saved = json.loads((tmp_path / "team.json").read_text())
    assert saved["seen_tips"] == [TIP_SHOP]
    assert desktop.profile.seen_tips == (TIP_SHOP,)
    # A later launch remembers it.
    reopened = DesktopApplication(ApplicationController(tmp_path / "team.json", tmp_path / "legacy.db"))
    assert TIP_SHOP in reopened.run_screen.tips.seen


def test_each_match_tip_shows_once_and_dismisses_on_the_decision(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    tips = desktop.run_screen.tips
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    assert tips.current == TIP_OFFENSE
    texts = _texts(_draw(desktop))
    assert GOT_IT in texts
    _play_human_decision(desktop)
    _skip_match_playback(desktop)
    if desktop.football_controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
        assert tips.current is None  # the second call shows no tip
    _drive_to(desktop, FootballHumanDecision.DEFENSIVE_SCHEME)
    assert tips.current == TIP_DEFENSE
    rect = tips.rect
    assert rect is not None and STRIP_RECT.contains(rect)
    assert not rect.colliderect(HAND_RECT) and not rect.colliderect(FIELD_RECT)
    assert not rect.colliderect(SCOREBOARD_RECT)
    _play_human_decision(desktop)
    desktop.router.draw(_surface())
    assert tips.current != TIP_DEFENSE
    saved = json.loads((tmp_path / "team.json").read_text())["seen_tips"]
    assert TIP_OFFENSE in saved and TIP_DEFENSE in saved and TIP_SHOP in saved


def test_tips_never_block_clicks(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    tips = desktop.run_screen.tips
    assert tips.current == TIP_OFFENSE
    # A click on the tip's text (not GOT IT) passes through.
    point = (tips.rect.left + 30, tips.rect.centery)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        assert not tips.handle_event(pygame.event.Event(kind, pos=point, button=1))
    # A hand card is still playable with the tip showing.
    events_before = len(desktop.football_controller.state.match.match_events)
    card = next(b for b in desktop.run_screen.buttons if b.variant == "hand-card" and b.enabled)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(kind, pos=card.hit_rect.center, button=1))
    assert len(desktop.football_controller.state.match.match_events) > events_before


def test_fourth_down_tip_leaves_the_strip_buttons_clickable(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    simulator = desktop.football_controller._simulator
    simulator.state = replace(simulator.state, down=4,
                              awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    desktop.run_screen.state = desktop.football_controller.state
    desktop.router.draw(_surface())
    tips = desktop.run_screen.tips
    assert tips.current == TIP_FOURTH_DOWN
    strip_buttons = [b for b in desktop.run_screen.buttons if b.variant.startswith("strip")]
    assert strip_buttons and not any(b.rect.colliderect(tips.rect) for b in strip_buttons)
    _activate(desktop, "PUNT")
    desktop.router.draw(_surface())
    assert tips.current != TIP_FOURTH_DOWN


def test_got_it_and_escape_dismiss_without_pausing(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    desktop.router.draw(_surface())
    tips = desktop.run_screen.tips
    assert tips.current == TIP_SHOP
    center = tips.button_rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(kind, pos=center, button=1))
    desktop.router.draw(_surface())
    assert tips.current is None and not desktop.run_screen.pause.is_open

    _activate(desktop, "FINISH SHOP / START MATCH")
    _drive_to(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    assert tips.current == TIP_OFFENSE
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    desktop.router.draw(_surface())
    assert tips.current is None
    assert not desktop.run_screen.match_screen.popup.open
    # With no tip showing, Esc pauses as before.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert desktop.run_screen.match_screen.popup.open


def test_tips_wait_out_replays(tmp_path: Path) -> None:
    state = TipState()
    assert state.update(None) is None  # a replay offers no tip
    assert state.update(TIP_DEFENSE, ("k", 1)) == TIP_DEFENSE
    assert state.update(None) is None and state.current is None
    assert state.update(TIP_DEFENSE, ("k", 1)) is None  # seen
    assert state.update(TIP_TWO_POINT, 1, hold=True) is None and TIP_TWO_POINT not in state.seen


def test_tips_never_show_during_a_real_replay(tmp_path: Path) -> None:
    from src.ui.football_run_screen import MATCH_TIPS
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen.match_screen
    tips = desktop.run_screen.tips
    checked = False
    for _ in range(200):
        tips.seen.clear()
        tips.dismiss()
        desktop.router.draw(_surface())  # no skip: any replay is still running
        if screen.input_blocked() and controller.state.human_decision in MATCH_TIPS:
            texts = _texts(_draw(desktop))
            assert tips.current is None and GOT_IT not in texts
            _skip_match_playback(desktop)
            assert tips.current == MATCH_TIPS[controller.state.human_decision]
            checked = True
            break
        tips.seen.update(TIP_IDS)
        _drive_to(desktop, controller.state.human_decision)
        if controller.state.human_decision is FootballHumanDecision.GREEN_DOG:
            next(b for b in desktop.run_screen.buttons if b.variant == "strip-primary").action()
        else:
            _play_human_decision(desktop)
    assert checked


def test_reset_tips_from_settings(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    desktop.router.draw(_surface())
    assert desktop.profile.seen_tips == (TIP_SHOP,)
    desktop.navigate("settings")
    _activate(desktop, RESET_TIPS)
    assert desktop.profile.seen_tips == ()
    assert desktop.run_screen.tips.seen == set()
    assert json.loads((tmp_path / "team.json").read_text())["seen_tips"] == []


def test_old_profile_without_seen_tips_loads_and_saves_other_fields(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    data = {
        "profile_id": "0f0e8a40-5c1c-4a0b-9f3c-2b2f1b7d8c11",
        "team_name": "Old Owls",
        "primary_color_id": "navy",
        "secondary_color_id": "gold",
    }
    path.write_text(json.dumps(data))
    profile = load_profile(path)
    assert profile is not None and profile.seen_tips == ()
    save_profile(replace(profile, seen_tips=(TIP_SHOP,)), path)
    saved = json.loads(path.read_text())
    assert {key: saved[key] for key in data} == data
    assert saved["seen_tips"] == [TIP_SHOP]
    assert load_profile(path).seen_tips == (TIP_SHOP,)
    # A malformed list is treated as nothing seen rather than an unloadable profile.
    path.write_text(json.dumps({**data, "seen_tips": "shop"}))
    assert load_profile(path).seen_tips == ()
    with pytest.raises(ValueError):
        TeamProfile(data["profile_id"], "Owls", "navy", "gold", seen_tips=["shop"])  # type: ignore[arg-type]


# -- How to Play --------------------------------------------------------------------

def test_how_to_play_opens_from_the_menu_fits_and_closes(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _activate(desktop, "HOW TO PLAY")
    assert desktop.router.current_id == "how_to_play"
    records = _draw(desktop)
    _assert_text_fits(records)
    texts = _texts(records)
    for heading, _paragraphs in SECTIONS:
        assert heading.upper() in texts
    canvas = pygame.Rect((0, 0), LOGICAL_SIZE)
    assert all(canvas.contains(rect) for _text, rect, _ in records)
    joined = " ".join(texts)
    for phrase in ("stop", "volatility", "Stamina", "+10%", "AP"):
        assert phrase.lower() in joined.lower()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert desktop.router.current_id == "main_menu"
    _activate(desktop, "HOW TO PLAY")
    _activate(desktop, "BACK")
    assert desktop.router.current_id == "main_menu"
