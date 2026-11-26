"""Coach selection redesign: perk wording, text fit, Depth Chart wording, inspect panel."""

from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from src.engine.football_coaches import (
    COACHES_BY_ID,
    FootballCoachPair,
    FootballCoachPerkKind,
    coach_for_id,
    coaches_for_assignment,
)
from src.engine.football_controller import FootballRunPhase
from src.ui import football_depth_chart as depth_module
from src.ui.football_coach_perks import coach_perk_rules, coach_perk_short, modifier_text
from src.ui.football_coach_view import SELECT_LABEL, select_button_rect
from src.ui.football_inspect import HOVER_DELAY_MS, coach_inspect
from src.ui.football_ui_kit import plain_font, text_audit
from test_football_desktop import _draft_to_shop, _new_desktop, _start_run, _surface

SCREEN = pygame.Rect(0, 0, 1280, 720)

EXPECTED_SHORT = {
    "ground_and_pound": "First RB Run each drive: +3 yds",
    "option_spread": "Going for it on 4th: +1 yd",
    "air_raid": "First completion each drive: +3 yds",
    "pro_style": "1st-down completions: +2 yds",
    "run_stop": "Stopped RB Runs: −2 yds",
    "pressure_blitz": "Stopped passes: +5% INT chance",
    "coverage": "Stopped passes: +5% incompletion",
    "ball_hawk": "INT returns: +10 yds, can score",
    "balanced_offense": "No perk · steady +5% across the unit",
    "balanced_defense": "No perk · steady +5% across the unit",
}

# Caveats the full rules must keep for each perk kind.
EXPECTED_RULE_DETAILS = {
    FootballCoachPerkKind.FIRST_RUN_YARDS: ("+3 yards", "turnover", "next drive"),
    FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS: ("+1 yard", "fourth down", "Not used on conversions"),
    FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS: ("+3 yards", "Incompletions and interceptions", "next drive"),
    FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS: ("+2 yards", "first down", "Not used on conversions"),
    FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION: ("2 yards", "RB Run defense call", "turnover"),
    FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS: ("+5% interception chance", "stops"),
    FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS: ("+5% incompletion chance", "stops"),
    FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS: ("+10 yards", "touchdown", "two-point conversions"),
}


def pair(offense: str, defense: str) -> FootballCoachPair:
    return FootballCoachPair(coach_for_id(offense), coach_for_id(defense))


OFFER = (pair("ground_and_pound", "ball_hawk"), pair("balanced_offense", "coverage"),
         pair("option_spread", "balanced_defense"))


def _desktop(tmp_path: Path, *, primary="navy", team_name="Test Owls", offer=OFFER):
    desktop = _new_desktop(tmp_path, primary=primary, team_name=team_name)
    _start_run(desktop)
    screen = desktop.run_screen
    clock = [0]
    screen._clock = lambda: clock[0]
    if offer is not None:
        state = desktop.football_controller.state
        changed = replace(state, team_builder=replace(state.team_builder, coach_offer=offer))
        screen._current_state = lambda: changed
    desktop.router.draw(_surface())
    return desktop, screen, clock


def _send(desktop, kind, **values):
    desktop.router.handle_event(pygame.event.Event(kind, values))


def _coach_rect(screen, key):
    return next(rect for k, rect in screen.coach_inspection.coach_rects if k == key)


def _draw_audited(desktop):
    with text_audit() as records:
        desktop.router.draw(_surface())
    return records


# -- wording -----------------------------------------------------------------------

@pytest.mark.parametrize("coach_id", sorted(COACHES_BY_ID))
def test_every_coach_has_short_and_full_wording(coach_id):
    coach = coach_for_id(coach_id)
    short, rules = coach_perk_short(coach), coach_perk_rules(coach)
    assert short == EXPECTED_SHORT[coach_id]
    assert "percentage points" not in rules and "\n" not in short
    assert 1 <= rules.count(".") <= 3
    if coach.perk is None:
        assert "no special perk" in rules and "+5%" in rules
    else:
        for detail in EXPECTED_RULE_DETAILS[coach.perk.kind]:
            assert detail in rules, (coach_id, detail)
    # One line on the card at the largest perk size, with room for the OFF/DEF tag.
    pygame.font.init()
    assert plain_font(14).size(short)[0] <= 250


@pytest.mark.parametrize("coach_id", [c for c in sorted(COACHES_BY_ID) if COACHES_BY_ID[c].perk])
def test_wording_is_built_from_the_perk_value(coach_id):
    coach = coach_for_id(coach_id)
    doubled = replace(coach, perk=replace(coach.perk, value=coach.perk.value * 2))
    assert coach_perk_short(doubled) != coach_perk_short(coach)
    assert coach_perk_rules(doubled) != coach_perk_rules(coach)
    if coach.perk.value < 1:
        assert f"+{round(coach.perk.value * 200):g}%" in coach_perk_short(doubled)
    else:
        assert f"{coach.perk.value * 2:g} yds" in coach_perk_short(doubled)


def test_modifier_text_signs():
    assert [modifier_text(v) for v in (0.2, 0.05, 0.0, -0.1)] == ["+20%", "+5%", "+0%", "−10%"]


# -- coach screen fit and wording ----------------------------------------------------

@pytest.mark.parametrize("primary", ["navy", "silver", "yellow", "crimson"])
@pytest.mark.parametrize("team_name", ["Test Owls", "The Extremely Long Named University Fighting Owls of the North"])
def test_coach_screen_text_fits_for_team_colors_and_names(tmp_path, primary, team_name):
    desktop, screen, clock = _desktop(tmp_path, primary=primary, team_name=team_name)
    records = _draw_audited(desktop)
    for text, rect, container in records:
        assert container.contains(rect), (text, rect, container)
        assert SCREEN.contains(rect), text
    texts = {text for text, _rect, _container in records}
    assert {"SELECT YOUR COACHES", "COACHING IMPACT", "POSITION BOOSTS", "COACH PERK",
            "FOR THE RUN", SELECT_LABEL} <= texts
    for item in OFFER:
        for coach in (item.offense, item.defense):
            assert coach_perk_short(coach) in texts
            assert coach_perk_rules(coach) not in texts
    # Open a panel too: it must fit the same way.
    key = ("coach", 2, "defense")
    _send(desktop, pygame.MOUSEMOTION, pos=_coach_rect(screen, key).center)
    desktop.router.draw(_surface())
    clock[0] += HOVER_DELAY_MS
    for text, rect, container in _draw_audited(desktop):
        assert container.contains(rect) and SCREEN.contains(rect), text
    assert screen.coach_inspection.inspect.shown_key == key


def test_buttons_keep_labels_order_and_focus(tmp_path):
    desktop, screen, _clock = _desktop(tmp_path)
    labels = [button.label for button in screen.buttons]
    assert labels == ["CHOOSE STAFF 01", "CHOOSE STAFF 02", "CHOOSE STAFF 03", "PAUSE"]
    for button, card in zip(screen.buttons, screen.coach_inspection.card_rects):
        assert button.rect == select_button_rect(card) and card.contains(button.rect)


def test_depth_chart_front_and_back_use_the_short_line(tmp_path):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    screen.shop_review.open_depth_chart()
    shop = desktop.football_controller.state.shop
    coaches = coaches_for_assignment(shop.roster.coach_assignment)
    texts = [text for text, _rect, _container in _draw_audited(desktop)]
    for coach in coaches:
        assert coach_perk_short(coach) in texts
        assert coach_perk_rules(coach) not in texts
    for side, coach in zip(("OFFENSE", "DEFENSE"), coaches):
        rows = depth_module.coach_back_rows(side, coach, shop)
        assert ("text", coach_perk_short(coach)) in rows
        assert ("text", coach_perk_rules(coach)) not in rows


# -- inspect panel -------------------------------------------------------------------

def test_hover_opens_panel_after_delay_with_full_rules(tmp_path):
    desktop, screen, clock = _desktop(tmp_path)
    key = ("coach", 0, "defense")  # Ball-Hawk
    coach = OFFER[0].defense
    _send(desktop, pygame.MOUSEMOTION, pos=_coach_rect(screen, key).center)
    desktop.router.draw(_surface())
    assert screen.coach_inspection.inspect.shown_key is None
    clock[0] += HOVER_DELAY_MS
    records = _draw_audited(desktop)
    inspect = screen.coach_inspection.inspect
    assert inspect.shown_key == key
    panel = inspect.panel_rect
    assert SCREEN.contains(panel)
    texts = [text for text, rect, _container in records if panel.contains(rect)]
    assert coach_perk_short(coach) in texts
    joined = " ".join(texts)
    assert "Interceptions on regular plays" in joined and "two-point" in joined
    assert "BALL-HAWK" in texts and "DEFENSE COACH" in texts
    # The panel never covers any SELECT PAIR button.
    for button in screen.buttons[:3]:
        assert not panel.colliderect(button.rect)
    # Hovering the perk row opens the same coach; leaving the coach closes it.
    _send(desktop, pygame.MOUSEMOTION, pos=screen.coach_inspection.card_rects[0].midtop)
    desktop.router.draw(_surface())
    assert screen.coach_inspection.inspect.shown_key is None


def _hover_open(desktop, screen, clock, key):
    _send(desktop, pygame.MOUSEMOTION, pos=_coach_rect(screen, key).center)
    desktop.router.draw(_surface())
    clock[0] += HOVER_DELAY_MS
    return _draw_audited(desktop)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("side", ["offense", "defense"])
def test_open_panel_does_not_block_selection(tmp_path, index, side):
    desktop, screen, clock = _desktop(tmp_path, offer=None)
    offer = desktop.football_controller.state.team_builder.coach_offer
    key = ("coach", index, side)
    _hover_open(desktop, screen, clock, key)
    assert screen.coach_inspection.inspect.shown_key == key
    button = screen.buttons[index]
    assert not screen.coach_inspection.inspect.panel_rect.colliderect(button.rect)
    _send(desktop, pygame.MOUSEBUTTONDOWN, pos=button.rect.center, button=1)
    _send(desktop, pygame.MOUSEBUTTONUP, pos=button.rect.center, button=1)
    state = desktop.football_controller.state
    assert state.phase is FootballRunPhase.PLAYER_DRAFT
    assert state.selected_coach_pair is offer[index]
    assert state.selected_coach_pair.offense is offer[index].offense
    assert state.selected_coach_pair.defense is offer[index].defense


def test_panel_under_pointer_never_takes_clicks(tmp_path):
    desktop, screen, clock = _desktop(tmp_path, offer=None)
    offer = desktop.football_controller.state.team_builder.coach_offer
    _hover_open(desktop, screen, clock, ("coach", 0, "defense"))
    panel = screen.coach_inspection.inspect.panel_rect
    # The panel opens over pair 2's column; a click there still reaches the screen.
    point = next(rect.center for key, rect in screen.coach_inspection.coach_rects
                 if key[1] == 1 and panel.collidepoint(rect.center))
    _send(desktop, pygame.MOUSEBUTTONDOWN, pos=point, button=1)
    _send(desktop, pygame.MOUSEBUTTONUP, pos=point, button=1)
    assert screen.coach_inspection.active_index(screen.focus_index) == 1
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert desktop.football_controller.state.team_builder.coach_offer == offer


def test_i_key_does_nothing_with_or_without_a_panel(tmp_path):
    desktop, screen, clock = _desktop(tmp_path)
    inspect = screen.coach_inspection.inspect
    _send(desktop, pygame.KEYDOWN, key=pygame.K_i)
    desktop.router.draw(_surface())
    clock[0] += HOVER_DELAY_MS
    desktop.router.draw(_surface())
    assert inspect.shown_key is None  # I opened nothing, not even the focus panel
    key = ("coach", 1, "defense")
    _hover_open(desktop, screen, clock, key)
    labels = [b.label for b in screen.buttons]
    _send(desktop, pygame.KEYDOWN, key=pygame.K_i)
    records = _draw_audited(desktop)
    assert inspect.shown_key == key and screen.coach_inspection.hover_coach == key
    assert [b.label for b in screen.buttons] == labels
    assert labels == ["CHOOSE STAFF 01", "CHOOSE STAFF 02", "CHOOSE STAFF 03", "PAUSE"]
    assert not {"PRESS I TO PIN", "CLOSE [ESC]", "I"} & {t for t, _r, _c in records}
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT


def test_keyboard_focused_pair_panel_shows_both_coaches(tmp_path):
    desktop, screen, clock = _desktop(tmp_path)
    inspect = screen.coach_inspection.inspect
    for index in range(3):
        # Tab moves focus: pair 1 -> 2 -> 3; the first press of a fresh screen goes 1 -> 2,
        # so start by tabbing round (PAUSE is the fourth focus stop) back to pair 1.
        for _ in range(4 if index == 0 else 1):
            _send(desktop, pygame.KEYDOWN, key=pygame.K_TAB)
        assert screen.focus_index == index
        desktop.router.draw(_surface())
        assert inspect.shown_key is None  # waits for the delay
        clock[0] += HOVER_DELAY_MS
        records = _draw_audited(desktop)
        assert inspect.shown_key == ("coach", index, "pair")
        panel = inspect.panel_rect
        assert SCREEN.contains(panel)
        assert not panel.colliderect(screen.buttons[index].rect)
        inside = [(text, rect, container) for text, rect, container in records if panel.contains(rect)]
        for text, rect, container in inside:
            assert container.contains(rect), text
        texts = [text for text, _r, _c in inside]
        content = inspect.overlay[0]
        full = " ".join(section[1] for section in content.sections)
        for coach in (OFFER[index].offense, OFFER[index].defense):
            assert f"{coach.side.value.upper()} \u00b7 {coach.name.upper()}" in texts
            assert coach_perk_short(coach) in texts
            assert coach_perk_rules(coach) in full
        assert not {"PRESS I TO PIN", "CLOSE [ESC]"} & set(texts)


def test_escape_hides_panel_before_pausing_and_pause_clears_it(tmp_path):
    desktop, screen, clock = _desktop(tmp_path)
    inspect = screen.coach_inspection.inspect
    _hover_open(desktop, screen, clock, ("coach", 0, "offense"))
    assert inspect.shown_key is not None
    _send(desktop, pygame.KEYDOWN, key=pygame.K_ESCAPE)
    desktop.router.draw(_surface())
    assert inspect.shown_key is None and not screen.pause.is_open
    clock[0] += HOVER_DELAY_MS
    desktop.router.draw(_surface())
    assert inspect.shown_key is None  # stays hidden while the pointer rests there
    _send(desktop, pygame.KEYDOWN, key=pygame.K_ESCAPE)
    assert screen.pause.is_open
    desktop.router.draw(_surface())
    assert inspect.overlay is None and inspect.panel_rect is None
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    # A panel shown on keyboard focus is hidden the same way.
    _send(desktop, pygame.KEYDOWN, key=pygame.K_ESCAPE)
    assert not screen.pause.is_open
    _send(desktop, pygame.KEYDOWN, key=pygame.K_TAB)
    desktop.router.draw(_surface())
    clock[0] += HOVER_DELAY_MS
    desktop.router.draw(_surface())
    assert inspect.shown_key == ("coach", screen.focus_index, "pair")
    _send(desktop, pygame.KEYDOWN, key=pygame.K_ESCAPE)
    desktop.router.draw(_surface())
    assert inspect.shown_key is None and not screen.pause.is_open


def test_window_leave_clears_coach_hover(tmp_path):
    desktop, screen, _clock = _desktop(tmp_path)
    _send(desktop, pygame.MOUSEMOTION, pos=_coach_rect(screen, ("coach", 0, "offense")).center)
    assert screen.coach_inspection.hover_coach == ("coach", 0, "offense")
    _send(desktop, pygame.WINDOWLEAVE)
    assert screen.coach_inspection.hover_coach is None


def test_coach_inspect_content_lists_modifiers_short_line_and_rules():
    coach = coach_for_id("pressure_blitz")
    content = coach_inspect(coach)
    assert content.title == "Pressure / Blitz" and content.tag == "Defense coach"
    assert content.sections[0] == ("Coach perk", coach_perk_short(coach), True)
    rows = {section[0]: section[1] for section in content.sections}
    modifiers = rows["Position modifiers"]
    assert modifiers.splitlines() == ["LINEBACKERS +20%  ·  CORNERBACKS +10%",
                                      "SAFETIES −10%  ·  D-LINE +0%"]
    assert rows["Full rules"] == coach_perk_rules(coach)
