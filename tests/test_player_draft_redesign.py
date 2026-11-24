"""Player draft redesign: coached power, tracker rows, partner links, names, and text fit."""

from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from src.engine.football import FootballPosition
from src.engine.football_coaches import OFFENSIVE_POSITIONS
from src.engine.football_controller import FootballRunPhase
from src.engine.football_player_catalog import (
    BASIC_PLAYER_TYPES, player_contribution_modifier, player_type_for_id,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui import football_player_draft_view as draft_view
from src.ui.football_coach_perks import modifier_text
from src.ui.football_depth_chart import _comparison, modified_player_stats
from src.ui.football_ui_kit import text_audit, team_accent
from src.ui.football_run_screen import COACH_ERROR_RECT
from test_football_desktop import _activate, _new_desktop, _start_run, _surface


def _to_draft(tmp_path: Path, **kwargs):
    desktop = _new_desktop(tmp_path, **kwargs)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    return desktop


def _state(desktop):
    return desktop.football_controller.state


def _pick(desktop, index: int) -> None:
    position = _state(desktop).team_builder.required_position
    _activate(desktop, f"DRAFT {position.value}", index=index)


def _draw(desktop):
    with text_audit() as records:
        desktop.router.draw(_surface())
    return list(records)


def _hover_card(desktop, index: int) -> None:
    desktop.router.draw(_surface())
    card = desktop.run_screen.player_inspection.card_rects[index]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (card.centerx, card.top + 120)}))


def _engine_power(player, modifier: float) -> float:
    return player.power * player_contribution_modifier(player, (player,), modifier)


def _with_modifier(builder, position: FootballPosition, value: float):
    pair = builder.selected_coach_pair
    side = "offense" if position in OFFENSIVE_POSITIONS else "defense"
    coach = getattr(pair, side)
    modifiers = dict(coach.position_modifiers)
    # Swap values so the coach keeps its valid +20/+10/-10/0 spread.
    other = next(p for p, v in modifiers.items() if v == value)
    modifiers[other], modifiers[position] = modifiers[position], value
    coach = replace(coach, position_modifiers=modifiers)
    return replace(builder, selected_coach_pair=replace(pair, **{side: coach}))


@pytest.mark.parametrize("value", [0.2, -0.1, 0.0])
def test_coached_power_on_cards_and_tracker_matches_engine_math(tmp_path: Path, value: float) -> None:
    desktop = _to_draft(tmp_path)
    screen = desktop.run_screen
    state = _state(desktop)
    builder = _with_modifier(state.team_builder, FootballPosition.QB, value)
    offer = builder.current_offer[0]
    expected = _engine_power(offer.player, value)
    assert draft_view.draft_coached_power(builder, offer.player) == expected
    screen.state = replace(state, team_builder=builder)
    records = _draw(desktop)
    card = screen.player_inspection.card_rects[0]
    texts = [text for text, rect, _ in records if card.contains(rect)]
    assert f"{modifier_text(value)} COACH" in texts
    base = f"{offer.player.power:g}"
    coached = draft_view.power_text(expected)
    assert base in texts
    if value == 0:
        assert coached == base and texts.count(base) == 1
    else:
        assert coached in texts and coached != base
    # The drafted tracker row uses the same math.
    drafted = replace(builder, selected_players={FootballPosition.QB: offer.player},
                      required_position=FootballPosition.RB)
    row = draft_view.tracker_row(drafted, FootballPosition.QB)
    assert row.power == coached
    assert row.chip == modifier_text(value)


def test_coached_power_matches_depth_chart_modified_stats_after_draft(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    shown: dict[FootballPosition, str] = {}
    for position in PLAYER_DRAFT_ORDER:
        builder = _state(desktop).team_builder
        offer = builder.current_offer[0]
        records = _draw(desktop)
        card = desktop.run_screen.player_inspection.card_rects[0]
        texts = [text for text, rect, _ in records if card.contains(rect)]
        shown[position] = draft_view.power_text(draft_view.draft_coached_power(builder, offer.player))
        assert shown[position] in texts
        _pick(desktop, 0)
    state = _state(desktop)
    assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
    for position in PLAYER_DRAFT_ORDER:
        power = modified_player_stats(state, position)[0]
        displayed, _color = _comparison(power, state.drafted_players[position].power,
                                        lower_is_better=False, percentage=False)
        assert displayed == shown[position]
        assert draft_view.tracker_row(state.team_builder, position).power == shown[position]


def test_every_tracker_row_shows_its_side_coach_chip(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    builder = _state(desktop).team_builder
    pair = builder.selected_coach_pair
    records = _draw(desktop)
    rows = draft_view.tracker_row_rects()
    for position in PLAYER_DRAFT_ORDER:
        coach = pair.offense if position in OFFENSIVE_POSITIONS else pair.defense
        expected = modifier_text(coach.position_modifiers[position])
        assert draft_view.tracker_row(builder, position).chip == expected
        texts = [text for text, rect, _ in records if rows[position].contains(rect)]
        assert expected in texts
    # Both sides include a non-zero chip, so the side mapping is actually exercised.
    assert {draft_view.tracker_row(builder, p).modifier for p in OFFENSIVE_POSITIONS} != {0.0}


def test_drafted_rows_show_name_power_and_partner_link_state(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    for _ in PLAYER_DRAFT_ORDER[:-1]:
        _pick(desktop, 0)
        builder = _state(desktop).team_builder
        records = _draw(desktop)
        rows = draft_view.tracker_row_rects()
        for position, player in builder.selected_players.items():
            row = draft_view.tracker_row(builder, position)
            partner = player_type_for_id(player.player_type_id).partner_position
            assert row.status == "drafted" and row.name == player.name
            assert row.power == draft_view.power_text(draft_view.draft_coached_power(builder, player))
            assert row.partner_drafted == (partner is not None and partner in builder.selected_players)
            texts = [text for text, rect, _ in records if rows[position].contains(rect)]
            assert f"PWR {row.power}" in texts
            if partner is None:
                assert row.partner is None and draft_view.NO_PARTNER in texts
            else:
                assert f"Partner {row.partner}" in texts
    # QB's partner toggles from muted to drafted once that position is picked.
    desktop = _to_draft(tmp_path / "toggle")
    _pick(desktop, 0)
    qb = _state(desktop).team_builder.selected_players[FootballPosition.QB]
    partner = player_type_for_id(qb.player_type_id).partner_position
    assert partner is not None
    while partner not in _state(desktop).team_builder.selected_players:
        assert not draft_view.tracker_row(_state(desktop).team_builder, FootballPosition.QB).partner_drafted
        _pick(desktop, 0)
    assert draft_view.tracker_row(_state(desktop).team_builder, FootballPosition.QB).partner_drafted


def test_partner_callout_appears_only_when_partner_is_drafted(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    screen = desktop.run_screen
    state = _state(desktop)
    builder = state.team_builder
    candidate = next(c for c in builder.current_offer
                     if player_type_for_id(c.player.player_type_id).partner_position is not None)
    partner = player_type_for_id(candidate.player.player_type_id).partner_position
    label = draft_view._draft_position_label(partner)
    assert draft_view.partner_callout(builder, candidate.player) == (f"{label} pick still to come", False)
    basic_type = next(t for t in BASIC_PLAYER_TYPES if t.position is partner)
    partner_player = replace(candidate.player, name="Partner Person", position=partner,
                             player_type_id=basic_type.type_id)
    linked = replace(builder, selected_players={partner: partner_player})
    text = f"Pairs with Partner Person ({label})"
    assert draft_view.partner_callout(linked, candidate.player) == (text, True)
    screen.state = replace(state, team_builder=replace(builder, current_offer=(candidate,) * 3))
    assert text not in [t for t, _, _ in _draw(desktop)]
    screen.state = replace(state, team_builder=replace(linked, current_offer=(candidate,) * 3))
    assert [t for t, _, _ in _draw(desktop)].count(text) == 3
    basic = next(c for c in builder.current_offer
                 if player_type_for_id(c.player.player_type_id).partner_position is None)
    assert draft_view.partner_callout(linked, basic.player) is None


def test_hovering_a_card_highlights_its_partner_row(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    screen = desktop.run_screen
    offers = _state(desktop).team_builder.current_offer
    accent = team_accent(desktop.theme.primary)
    rows = draft_view.tracker_row_rects()
    for index, candidate in enumerate(offers):
        partner = player_type_for_id(candidate.player.player_type_id).partner_position
        _hover_card(desktop, index)
        canvas = _surface()
        desktop.router.draw(canvas)
        assert screen.player_inspection.partner_row is partner
        for position, row in rows.items():
            lit = canvas.get_at((row.left + 4, row.centery)) == accent
            assert lit == (position is partner)
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    desktop.router.draw(_surface())
    assert screen.player_inspection.partner_row is None


def test_basic_player_display_names() -> None:
    assert {t.type_id: t.name for t in BASIC_PLAYER_TYPES} == {
        "basic_qb": "Basic QB", "basic_rb": "Basic RB", "basic_wr": "Basic WR",
        "basic_o_line": "Basic O-Line", "basic_d_line": "Basic D-Line",
        "basic_linebackers": "Basic Linebackers", "basic_cornerbacks": "Basic Cornerbacks",
        "basic_safeties": "Basic Safeties",
    }


LONG_TEAM = "The Extraordinarily Long Named Northern State University Fighting Owls"
LONG_PLAYER = "Maximilian Bartholomew-Fitzgerald III"


def _assert_fits(records) -> None:
    for text, rect, container in records:
        assert container.inflate(2, 2).contains(rect), (text, rect, container)


@pytest.mark.parametrize("primary", ["navy", "silver", "yellow", "crimson", "purple"])
def test_draft_text_fits_for_team_colors_and_long_names(tmp_path: Path, primary: str) -> None:
    desktop = _to_draft(tmp_path, team_name=LONG_TEAM, primary=primary, secondary="silver"
                        if primary != "silver" else "navy")
    screen = desktop.run_screen
    for pick in range(len(PLAYER_DRAFT_ORDER)):
        state = _state(desktop)
        if pick in (0, 4, 7):
            builder = state.team_builder
            long_offers = tuple(replace(c, player=replace(c.player, name=LONG_PLAYER)) for c in builder.current_offer)
            long_drafted = {p: replace(player, name=LONG_PLAYER) for p, player in builder.selected_players.items()}
            screen.state = replace(state, team_builder=replace(
                builder, current_offer=long_offers, selected_players=long_drafted))
            screen.last_error = "Draft rejected because this very long explanation should still wrap neatly."
            for hover in (None, 0, 1, 2):
                if hover is not None:
                    _hover_card(desktop, hover)
                _assert_fits(_draw(desktop))
            screen.last_error = None
            screen.state = state
        _pick(desktop, 0)


def test_error_banner_sits_in_the_header(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    desktop.run_screen.last_error = "Draft rejected."
    records = _draw(desktop)
    banner = [rect for text, rect, container in records
              if text == "CHECK: Draft rejected." and container == COACH_ERROR_RECT]
    assert banner and banner[0].bottom < draft_view.BODY_TOP


@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_card_button_drafts_its_player(tmp_path: Path, index: int) -> None:
    desktop = _to_draft(tmp_path)
    for position in PLAYER_DRAFT_ORDER[:3]:
        expected = _state(desktop).team_builder.current_offer[index].player
        _activate(desktop, f"DRAFT {position.value}", index=index)
        assert _state(desktop).team_builder.selected_players[position] is expected


def test_pause_button_moves_to_header(tmp_path: Path) -> None:
    desktop = _to_draft(tmp_path)
    desktop.router.draw(_surface())
    pause = next(b for b in desktop.run_screen.buttons if b.label == "PAUSE")
    assert pause.rect == pygame.Rect(1140, 20, 120, 36)
    assert pause.rect.bottom < draft_view.BODY_TOP
