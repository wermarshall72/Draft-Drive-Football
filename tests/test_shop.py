import pytest

from src.engine.shop import Shop
from src.engine.units import Coach, SpecialTeams, Unit, random_coach_options
from src.main import create_starter_team


def test_player_pool_has_six_distinct_archetypes_per_position() -> None:
    for position in Shop.OPENING_ORDER:
        players = [card for card in Shop.UNIT_POOL if card[1] == position]

        assert len(players) == 6
        assert len({player[0] for player in players}) == 6
        assert all(0.0 <= player[3] <= 1.0 for player in players)
        assert all(0.0 <= player[4] <= 1.0 for player in players)


def test_shop_spends_ap_on_roll_not_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    coach = roster.coach
    shop = Shop(roster, days=Shop.OPENING_AP)
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )

    portal = shop.roll_portal()
    assert len(portal) == Shop.PORTAL_SIZE
    assert shop.days == 5

    shop.draft_unit(portal[0])
    assert shop.days == 5
    assert roster.coach is coach
    assert roster.qb.name == "Pocket Passer"


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
        assert all(unit.stamina > 0 for unit in offer)
        shop.draft_opening_unit(offer[0])

    assert shop.days == 0
    assert shop.opening_picks == len(Shop.OPENING_ORDER)
    assert not shop.portal


def test_opening_draft_enforces_position_order_and_excludes_special_teams() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)

    with pytest.raises(ValueError, match="next opening pick"):
        shop.roll_opening_offer("RB")

    offer = shop.roll_opening_offer("QB")
    assert all(isinstance(card, Unit) for card in offer)


def test_special_teams_card_fills_its_roster_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    special_teams = Shop.SPECIAL_TEAMS_POOL[0]
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: [
            special_teams,
            *list(population)[: count - 1],
        ],
    )

    card = shop.roll_portal()[0]
    assert isinstance(card, SpecialTeams)
    shop.draft_unit(card)

    assert roster.special_teams is card
    assert card not in shop.portal


def test_shop_rejects_exhausted_ap_and_unoffered_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster, days=0)

    with pytest.raises(RuntimeError, match="Not enough Days"):
        shop.roll_portal()

    shop = Shop(roster)
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )
    shop.roll_portal()
    with pytest.raises(ValueError, match="current portal"):
        shop.draft_unit(Unit(name="Not offered", position="QB"))


def test_coach_cannot_be_replaced_through_the_shop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team(
        "Home Team",
        Coach(name="Locked", off_scheme="Air Raid", def_scheme="Zone"),
    )
    shop = Shop(roster)
    coach = roster.coach
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )
    shop.roll_portal()
    for card in tuple(shop.portal):
        shop.draft_unit(card)

    assert roster.coach is coach
    assert roster.coach.name == "Locked"


def test_run_setup_offers_three_distinct_coaches() -> None:
    options = random_coach_options()

    assert len(options) == 3
    assert len({coach.name for coach in options}) == 3
