import pytest

from src.engine.shop import Shop
from src.engine.coaching_actions import ACTION_BY_ID
from src.engine.units import (
    COACH_PAIRINGS,
    DEFENSIVE_STYLES,
    OFFENSIVE_STYLES,
    Coach,
    Unit,
    random_coach_options,
)
from src.main import create_starter_team


def test_player_pool_has_six_distinct_archetypes_per_position() -> None:
    for position in Shop.OPENING_ORDER:
        players = [card for card in Shop.UNIT_POOL if card[1] == position]

        assert len(players) == 6
        assert len({player[0] for player in players}) == 6
        assert all(0.0 <= player[3] <= 1.0 for player in players)
        assert all(0.0 <= player[4] <= 1.0 for player in players)
        for player in players:
            description = player[5].lower()
            assert all(stat in description for stat in ("power", "variance", "stamina"))
            assert not any(
                mechanic in description
                for mechanic in ("accuracy", "touchdown", "blocking", "injury")
            )


def test_coach_pairings_cover_all_offensive_and_defensive_styles() -> None:
    expected = {}
    for offense in OFFENSIVE_STYLES:
        for defense in DEFENSIVE_STYLES:
            expected[(offense.name, defense.name)] = {
                **offense.position_modifiers,
                **defense.position_modifiers,
            }

    assert len(OFFENSIVE_STYLES) == 5
    assert len(DEFENSIVE_STYLES) == 5
    assert len(COACH_PAIRINGS) == 25
    for coach in COACH_PAIRINGS:
        pairing = (coach.off_scheme, coach.def_scheme)
        assert pairing in expected
        assert coach.position_modifiers == expected[pairing]


def test_position_specific_coach_modifiers_change_only_listed_positions() -> None:
    roster = create_starter_team(
        "Home Team",
        Coach(
            name="Ground-and-Pound / Bend-Don't-Break",
            off_scheme="Ground-and-Pound",
            def_scheme="Bend-Don't-Break",
            position_modifiers={
                "RB": 1.2,
                "WR": 0.8,
                "FRONT7": 0.8,
                "SECONDARY": 1.2,
            },
        ),
    )

    assert roster.get_offensive_power() == pytest.approx(40.0)
    assert roster.get_defensive_power() == pytest.approx(40.0)

    roster.coach.off_modifier = 1.5
    roster.coach.def_modifier = 1.5
    roster.coach.position_modifiers = {"RB": 1.2}

    assert roster.get_offensive_power() == pytest.approx(42.0)
    assert roster.get_defensive_power() == pytest.approx(40.0)


def test_shop_offers_three_unique_actions_without_spending_ap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    monkeypatch.setattr("src.engine.shop.random.choices", lambda values, **_: [values[0]])
    monkeypatch.setattr("src.engine.shop.random.choice", lambda values: values[0])

    offer = shop.roll_action_offer()

    assert len(offer) == Shop.PORTAL_SIZE
    assert len({action.id for action in offer}) == Shop.PORTAL_SIZE
    assert all(action.rarity == "Common" for action in offer)
    assert shop.days == Shop.DAYS_PER_SHOP

    shop.take_action(offer[0])
    assert shop.days == Shop.DAYS_PER_SHOP - offer[0].ap_cost
    assert offer[0] not in shop.action_offer


def test_opening_draft_offers_each_position_and_spends_one_ap_per_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster, days=Shop.OPENING_AP)
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )

    for expected_position in Shop.OPENING_ORDER:
        offer = shop.roll_opening_offer(expected_position)
        assert len(offer) == Shop.PORTAL_SIZE
        assert {unit.position for unit in offer} == {expected_position}
        assert len({unit.name for unit in offer}) == Shop.PORTAL_SIZE
        assert all(unit.stamina > 0 for unit in offer)
        shop.draft_opening_unit(offer[0])
        assert getattr(roster, Shop.ROSTER_SLOTS[expected_position]) is offer[0]

    assert shop.days == 0
    assert shop.opening_picks == len(Shop.OPENING_ORDER)
    assert not shop.opening_offer


def test_opening_draft_enforces_position_order_and_excludes_special_teams() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)

    with pytest.raises(ValueError, match="next opening pick"):
        shop.roll_opening_offer("RB")

    offer = shop.roll_opening_offer("QB")
    assert all(isinstance(card, Unit) for card in offer)


def test_move_to_next_day_costs_one_ap_and_preserves_purchased_effects() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[25], ACTION_BY_ID[26]]
    shop.take_action(ACTION_BY_ID[25])
    remaining = shop.days

    offer = shop.move_to_next_day()

    assert shop.days == remaining - 1
    assert len(offer) == Shop.PORTAL_SIZE
    assert all(action.id != 25 for action in offer)
    assert len(shop.match_actions) == 1


def test_shop_rejects_exhausted_ap_and_unoffered_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster, days=0)

    with pytest.raises(RuntimeError, match="Not enough AP"):
        shop.move_to_next_day()

    shop = Shop(roster)
    monkeypatch.setattr("src.engine.shop.random.choices", lambda values, **_: [values[0]])
    monkeypatch.setattr("src.engine.shop.random.choice", lambda values: values[0])
    shop.roll_action_offer()
    with pytest.raises(ValueError, match="current offer"):
        shop.take_action(ACTION_BY_ID[150])


def test_coach_cannot_be_replaced_through_coaching_actions() -> None:
    roster = create_starter_team(
        "Home Team",
        Coach(name="Locked", off_scheme="Air Raid", def_scheme="Zone"),
    )
    shop = Shop(roster)
    coach = roster.coach
    shop.action_offer = [ACTION_BY_ID[25]]
    shop.take_action(ACTION_BY_ID[25])

    assert roster.coach is coach
    assert roster.coach.name == "Locked"


def test_run_setup_offers_three_distinct_coaches() -> None:
    options = random_coach_options()

    assert len(options) == 3
    assert len({coach.name for coach in options}) == 3
