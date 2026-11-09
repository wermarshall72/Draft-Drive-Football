import pytest

from src.engine.shop import Shop
from src.engine.units import Coach, SpecialTeams, Unit, random_coach_options
from src.main import create_starter_team


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
