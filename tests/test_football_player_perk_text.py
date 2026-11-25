"""Typed player-perk catalog and its single-source wording."""

from __future__ import annotations

import pytest

from src.engine.football import FootballPlayerPerkKind
from src.engine.football_player_catalog import (
    PLAYER_TYPES,
    PLAYER_TYPES_BY_ID,
    PLAYER_TYPES_BY_PERK,
    FootballPerkLimit,
    player_perk,
)
from src.ui.football_player_perks import (
    CARD_LINE_LIMIT,
    activation_callout,
    activation_preview_note,
    limit_label,
    partner_tag,
    perk_card_line,
    perk_rules,
)
from src.engine.football import FootballPerkActivation, FootballTeamSide

SPECIALISTS = [item for item in PLAYER_TYPES if item.perk is not None]


@pytest.mark.parametrize("player_type", SPECIALISTS, ids=lambda item: item.type_id)
def test_every_card_line_fits_and_rules_are_sentences(player_type) -> None:
    perk = player_type.perk
    line = perk_card_line(perk)
    assert 0 < len(line) <= CARD_LINE_LIMIT
    rules = perk_rules(perk)
    assert rules.endswith(".") and len(rules) > len(line)
    assert "planned" not in (line + rules).lower() and "inactive" not in (line + rules).lower()


def test_catalog_has_one_typed_perk_per_specialist_and_19_partner_requirements() -> None:
    assert len(SPECIALISTS) == 48
    assert set(PLAYER_TYPES_BY_PERK) == set(FootballPlayerPerkKind)
    assert sum(item.perk.partner_required for item in SPECIALISTS) == 19
    assert all(item.perk is None for item in PLAYER_TYPES if item.partner_position is None)


def test_renames_keep_type_ids() -> None:
    assert PLAYER_TYPES_BY_ID["wr_qb_vertical_threat"].name == "Field Stretcher"
    assert PLAYER_TYPES_BY_ID["wr_rb_screen_outlet"].name == "Chain Mover"


def test_card_lines_come_from_perk_values() -> None:
    assert perk_card_line(player_perk(FootballPlayerPerkKind.PULL_LEAD)) == (
        "3rd/4th & 3 or less, O-line play: O-line +10 power"
    )
    assert perk_card_line(player_perk(FootballPlayerPerkKind.RANGE_DENIAL)) == (
        "Rival field goals kick as if 7 yards longer"
    )
    assert "−8 power" in perk_card_line(player_perk(FootballPlayerPerkKind.SCREEN_WALL))


def test_partner_and_limit_tags() -> None:
    pylon = player_perk(FootballPlayerPerkKind.PYLON_REACH)
    assert partner_tag(pylon) is None and limit_label(pylon) == "1/GAME"
    mesh = player_perk(FootballPlayerPerkKind.MESH_READ)
    assert partner_tag(mesh) == "WITH RB" and limit_label(mesh) == "1/DRIVE"
    assert limit_label(player_perk(FootballPlayerPerkKind.SHOT_SETUP)) == "CHARGE"
    assert player_perk(FootballPlayerPerkKind.CONTAIN).limit is FootballPerkLimit.EVERY


def test_callout_and_preview_note_text() -> None:
    activation = FootballPerkActivation(FootballPlayerPerkKind.PYLON_REACH, FootballTeamSide.TEAM_A)
    assert activation_callout(activation) == "PYLON REACH · Boundary Route · TD"
    pull = FootballPerkActivation(FootballPlayerPerkKind.PULL_LEAD, FootballTeamSide.TEAM_A, 10)
    assert activation_preview_note(pull) == "+10 OL Pull Lead"
    checkdown = FootballPerkActivation(FootballPlayerPerkKind.CHECKDOWN, FootballTeamSide.TEAM_A, 2)
    assert activation_preview_note(checkdown) == "+2 yd Checkdown"
    for kind in FootballPlayerPerkKind:
        text = activation_callout(FootballPerkActivation(kind, FootballTeamSide.TEAM_B, 1.0))
        assert text.count(" · ") == 2
