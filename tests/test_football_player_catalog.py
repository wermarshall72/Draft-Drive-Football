import random

import pytest

from src.engine.football import FootballPlayer, FootballPosition
from src.engine.football_player_catalog import (
    BASIC_PLAYER_TYPES,
    DEFENSIVE_POSITIONS,
    OFFENSIVE_POSITIONS,
    PARTNERSHIP_BONUS,
    PLAYER_TYPES,
    PLAYER_TYPES_BY_POSITION,
    FootballPlayerPerk,
    player_contribution_modifier,
    player_from_type,
    player_type_for_id,
    player_type_offer,
)


def test_catalog_has_six_specialists_and_one_basic_per_position() -> None:
    assert len(PLAYER_TYPES) == 56
    assert len(BASIC_PLAYER_TYPES) == 8
    for position, player_types in PLAYER_TYPES_BY_POSITION.items():
        specialists = tuple(item for item in player_types if item.partner_position)
        basics = tuple(item for item in player_types if item.partner_position is None)
        partners = OFFENSIVE_POSITIONS if position in OFFENSIVE_POSITIONS else DEFENSIVE_POSITIONS

        assert len(specialists) == 6
        assert len(basics) == 1
        assert all(
            sum(item.partner_position is partner for item in specialists) == 2
            for partner in partners
            if partner is not position
        )
        assert basics[0].perk is None


def test_perks_are_distinct_within_each_side_and_informational_only() -> None:
    for positions in (OFFENSIVE_POSITIONS, DEFENSIVE_POSITIONS):
        perks = [
            item.perk
            for item in PLAYER_TYPES
            if item.position in positions and item.perk is not None
        ]
        assert len(perks) == 24
        assert len({perk.name for perk in perks}) == 24
        assert all(
            isinstance(perk, FootballPlayerPerk)
            and perk.trigger
            and perk.effect
            and perk.duration
            and perk.reset
            and "future" in perk.dependency.lower()
            for perk in perks
        )


def test_player_type_validation_rejects_unknown_and_wrong_position_ids() -> None:
    qb_type = PLAYER_TYPES_BY_POSITION[FootballPosition.QB][0]
    with pytest.raises(ValueError, match="Unknown player type"):
        player_type_for_id("missing")
    with pytest.raises(ValueError, match="must match"):
        FootballPlayer(
            "Wrong position",
            FootballPosition.RB,
            50,
            0.1,
            0.5,
            qb_type.type_id,
        )


def test_offer_has_two_distinct_specialists_then_guaranteed_basic() -> None:
    for position in FootballPosition:
        offer = player_type_offer(position, random.Random(23))
        assert len(offer) == 3
        assert offer[0].type_id != offer[1].type_id
        assert all(item.partner_position is not None for item in offer[:2])
        assert offer[2].partner_position is None
        assert offer[2].perk is None
        assert all(item.position is position for item in offer)


def test_specialist_offer_can_contain_two_types_with_the_same_partner() -> None:
    class FirstTwoRandom(random.Random):
        def sample(self, population, k):
            return list(population)[:k]

    offer = player_type_offer(FootballPosition.QB, FirstTwoRandom())
    assert offer[0].partner_position is offer[1].partner_position


def test_partnership_is_independent_and_modifier_cap_is_upper_only() -> None:
    qb_type = next(
        item
        for item in PLAYER_TYPES_BY_POSITION[FootballPosition.QB]
        if item.partner_position is FootballPosition.RB
    )
    rb_basic = next(
        item
        for item in PLAYER_TYPES_BY_POSITION[FootballPosition.RB]
        if item.partner_position is None
    )
    rb_mutual = next(
        item
        for item in PLAYER_TYPES_BY_POSITION[FootballPosition.RB]
        if item.partner_position is FootballPosition.QB
    )
    wr_basic = next(
        item
        for item in PLAYER_TYPES_BY_POSITION[FootballPosition.WR]
        if item.partner_position is None
    )
    qb = player_from_type(qb_type)
    basic_rb = player_from_type(rb_basic)
    mutual_rb = player_from_type(rb_mutual)
    basic_wr = player_from_type(wr_basic)

    assert PARTNERSHIP_BONUS == pytest.approx(0.10)
    assert player_contribution_modifier(qb, (qb, basic_rb), 0.0) == pytest.approx(1.10)
    assert player_contribution_modifier(basic_rb, (qb, basic_rb), 0.0) == 1.0
    assert player_contribution_modifier(mutual_rb, (qb, mutual_rb), 0.0) == pytest.approx(1.10)
    assert player_contribution_modifier(qb, (qb, basic_wr), 0.0) == 1.0
    assert player_contribution_modifier(qb, (qb, basic_rb), 0.20) == pytest.approx(1.30)
    assert player_contribution_modifier(qb, (qb, basic_rb), 0.50) == pytest.approx(1.30)
    assert player_contribution_modifier(qb, (qb, basic_rb), -0.10) == 1.0
    assert player_contribution_modifier(qb, (qb, basic_wr), -0.10) == pytest.approx(0.90)


def test_partnership_requires_the_partner_to_be_a_different_contributor() -> None:
    qb_type = next(
        item
        for item in PLAYER_TYPES_BY_POSITION[FootballPosition.QB]
        if item.partner_position is FootballPosition.RB
    )
    qb = player_from_type(qb_type)
    assert player_contribution_modifier(qb, (qb, qb), 0.0) == 1.0
