import pytest

from src.engine.coaching_actions import (
    ACTION_BY_ID,
    COACHING_ACTIONS,
    POSITIONS,
)
from src.engine.shop import Shop
from src.main import create_starter_team


def test_catalog_has_150_valid_actions_and_requested_rarity_weights() -> None:
    assert len(COACHING_ACTIONS) == 150
    assert set(ACTION_BY_ID) == set(range(1, 151))
    assert all(1 <= action.ap_cost <= 6 for action in COACHING_ACTIONS)
    assert {action.rarity for action in COACHING_ACTIONS} == {
        "Common",
        "Uncommon",
        "Rare",
        "Very Rare",
    }
    assert Shop.RARITY_WEIGHTS == (
        ("Common", 40),
        ("Uncommon", 30),
        ("Rare", 20),
        ("Very Rare", 10),
    )
    assert ACTION_BY_ID[55].rarity == "Rare"
    assert ACTION_BY_ID[56].rarity == "Rare"
    assert ACTION_BY_ID[145].rarity == "Very Rare"


def test_every_catalog_action_can_be_purchased_and_applied() -> None:
    for action in COACHING_ACTIONS:
        shop = Shop(create_starter_team(f"Team {action.id}"))
        shop.action_offer = [action]
        target = "QB" if action.choose_position else None

        shop.take_action(action, target_position=target)
        effective = shop.effective_roster()

        assert effective.player_name == f"Team {action.id}"
        assert shop.days == Shop.DAYS_PER_SHOP - action.ap_cost


def test_buying_multiple_actions_multiplies_effects_and_match_effect_expires() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[9], ACTION_BY_ID[25]]

    shop.take_action(ACTION_BY_ID[9])
    shop.take_action(ACTION_BY_ID[25])
    effective = shop.effective_roster()

    assert effective.qb.power == pytest.approx(10 * 1.03 * 1.08)
    assert roster.qb.power == 10.0
    assert effective is not roster

    shop.complete_match(won=False)

    assert shop.effective_roster().qb.power == pytest.approx(10 * 1.03)


def test_stat_caps_and_power_caps_are_applied() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.permanent_actions.extend([(ACTION_BY_ID[9], None)] * 10)
    shop.match_actions.extend([(ACTION_BY_ID[25], None)] * 10)
    shop.permanent_actions.extend([(ACTION_BY_ID[10], None)] * 20)
    shop.match_actions.extend([(ACTION_BY_ID[26], None)] * 20)
    shop.permanent_actions.extend([(ACTION_BY_ID[73], None)] * 20)
    shop.match_actions.extend([(ACTION_BY_ID[28], None)] * 20)

    effective = shop.effective_roster()

    assert effective.qb.power == pytest.approx(12.5)
    assert effective.qb.volatility == pytest.approx(0.05)
    assert effective.rb.stamina == 1.0


def test_position_target_is_required_and_only_affects_chosen_group() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[55]]

    with pytest.raises(ValueError, match="requires a valid position"):
        shop.take_action(ACTION_BY_ID[55])

    shop.take_action(ACTION_BY_ID[55], target_position="RB")
    effective = shop.effective_roster(include_match_effects=False)
    assert effective.rb.power == pytest.approx(roster.rb.power * 1.02)
    assert effective.qb.power == roster.qb.power


def test_move_to_next_day_is_repeatable_and_does_not_repeat_bought_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    monkeypatch.setattr("src.engine.shop.random.choices", lambda values, **_: [values[0]])
    monkeypatch.setattr("src.engine.shop.random.choice", lambda values: values[0])

    first_offer = shop.roll_action_offer()
    bought = first_offer[0]
    shop.take_action(bought)
    shop.move_to_next_day()
    second_offer = shop.move_to_next_day()

    assert shop.days == Shop.DAYS_PER_SHOP - bought.ap_cost - 2
    assert all(action.id != bought.id for action in second_offer)
    assert len(second_offer) == Shop.PORTAL_SIZE


def test_permanent_and_one_time_ap_are_applied_at_the_next_shop() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[145]]

    shop.take_action(ACTION_BY_ID[145], target_position="QB")
    assert shop.days == Shop.DAYS_PER_SHOP - 6
    shop.finish_shop()
    shop.prepare_next_shop()
    assert shop.days == Shop.DAYS_PER_SHOP + 1

    shop.action_offer = [ACTION_BY_ID[145]]
    shop.take_action(ACTION_BY_ID[145], target_position="RB")
    assert shop.permanent_ap == 2
    shop.finish_shop()
    shop.prepare_next_shop()
    assert shop.days == Shop.DAYS_PER_SHOP + 2

    assert ACTION_BY_ID[145] not in shop._eligible_actions()


@pytest.mark.parametrize(
    ("won", "expected_next_shop_ap"),
    [(False, 13), (True, 14)],
)
def test_win_dependent_ap_bank(
    won: bool, expected_next_shop_ap: int
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[98]]

    shop.take_action(ACTION_BY_ID[98])
    shop.complete_match(won=won)
    shop.prepare_next_shop()

    assert shop.days == expected_next_shop_ap


def test_guaranteed_and_win_conditional_ap_share_the_six_ap_bank_cap() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[143], ACTION_BY_ID[144]]

    shop.take_action(ACTION_BY_ID[143])
    shop.take_action(ACTION_BY_ID[144])
    shop.complete_match(won=True)
    shop.prepare_next_shop()

    assert shop.days == Shop.DAYS_PER_SHOP + Shop.MAX_BANKED_AP


def test_carry_unused_ap_banks_up_to_two_points() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[99]]

    shop.take_action(ACTION_BY_ID[99])
    shop.finish_shop()
    shop.prepare_next_shop()

    assert shop.days == Shop.DAYS_PER_SHOP + Shop.MAX_CARRYOVER_AP


def test_last_shop_hides_actions_that_only_pay_out_at_next_shop() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.has_future_shop = False

    eligible_ids = {action.id for action in shop._eligible_actions()}

    assert 95 not in eligible_ids
    assert 99 not in eligible_ids
    assert 145 not in eligible_ids
    assert 146 not in eligible_ids
    assert POSITIONS == Shop.OPENING_ORDER


def test_rare_action_target_cannot_receive_duplicate_permanent_ap_upgrade() -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.action_offer = [ACTION_BY_ID[145]]

    shop.take_action(ACTION_BY_ID[145], target_position="QB")
    shop.finish_shop()
    shop.prepare_next_shop()
    shop.action_offer = [ACTION_BY_ID[145]]

    with pytest.raises(ValueError, match="already has a permanent AP upgrade"):
        shop.take_action(ACTION_BY_ID[145], target_position="QB")


def test_action_offer_cannot_be_refreshed_without_spending_ap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = Shop(create_starter_team("Home Team"))
    monkeypatch.setattr("src.engine.shop.random.choices", lambda values, **_: [values[0]])
    monkeypatch.setattr("src.engine.shop.random.choice", lambda values: values[0])

    shop.roll_action_offer()
    with pytest.raises(RuntimeError, match="Move to next day"):
        shop.roll_action_offer()
    before_move = shop.days

    shop.move_to_next_day()

    assert shop.days == before_move - 1


def test_preparing_an_already_open_shop_is_idempotent() -> None:
    shop = Shop(create_starter_team("Home Team"))
    shop.pending_ap = 2
    shop.prepare_next_shop()
    shop.days = 7
    shop.action_offer = [ACTION_BY_ID[25]]
    shop.take_action(ACTION_BY_ID[25])
    remaining = shop.days

    shop.prepare_next_shop()

    assert shop.days == remaining
    assert len(shop.match_actions) == 1
