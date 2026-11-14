from dataclasses import replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_shop import (
    POWER_UPGRADE_AMOUNT,
    STAMINA_UPGRADE_AMOUNT,
    TRAINING_POINT_BUDGET,
    FootballShop,
    FootballUpgrade,
    FootballUpgradeStat,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER, FootballTeamBuilder


def _roster(
    team_name: str = "Shop Team",
    *,
    stamina: float = 0.75,
) -> FootballRoster:
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=10.0,
            volatility=0.2,
            stamina=stamina,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name,
        players,
        FootballCoach(f"{team_name} Coach"),
        FootballSpecialTeams(f"{team_name} Special Teams"),
    )


def _drafted_roster(seed: int = 17) -> FootballRoster:
    builder = FootballTeamBuilder("Built Team", seed)
    builder.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        builder.choose_player(position, 0)
    return builder.build_roster()


def test_shop_offer_is_three_distinct_affordable_upgrades_and_seeded() -> None:
    assert POWER_UPGRADE_AMOUNT == 1.0
    assert STAMINA_UPGRADE_AMOUNT == 0.1
    first = FootballShop(_roster(), 12)
    replay = FootballShop(_roster(), 12)

    assert len(first.offer) == 3
    assert len({upgrade.upgrade_id for upgrade in first.offer}) == 3
    assert all(0 < upgrade.cost <= TRAINING_POINT_BUDGET for upgrade in first.offer)
    assert any(upgrade.stat is FootballUpgradeStat.POWER for upgrade in first.offer)
    assert any(upgrade.stat is FootballUpgradeStat.STAMINA for upgrade in first.offer)
    assert first.offer == replay.offer
    assert first.state == replay.state


def test_power_and_stamina_purchases_change_only_the_targeted_stat() -> None:
    original = _roster()
    shop = FootballShop(original, 5)
    power_upgrade = next(
        upgrade for upgrade in shop.offer
        if upgrade.stat is FootballUpgradeStat.POWER
    )
    stamina_upgrade = next(
        upgrade for upgrade in shop.offer
        if upgrade.stat is FootballUpgradeStat.STAMINA
    )
    old_target = original.players[power_upgrade.position]

    shop.buy(power_upgrade)
    powered = shop.roster
    updated_target = powered.players[power_upgrade.position]
    assert updated_target.power == old_target.power + power_upgrade.amount
    assert updated_target.volatility == old_target.volatility
    assert updated_target.stamina == old_target.stamina
    assert shop.remaining_budget == TRAINING_POINT_BUDGET - power_upgrade.cost

    old_stamina_target = powered.players[stamina_upgrade.position]
    shop.buy(stamina_upgrade)
    upgraded = shop.roster.players[stamina_upgrade.position]
    assert upgraded.stamina == old_stamina_target.stamina + STAMINA_UPGRADE_AMOUNT
    assert upgraded.power == old_stamina_target.power
    assert upgraded.volatility == old_stamina_target.volatility
    assert 0 <= upgraded.stamina <= 1
    assert original.players[power_upgrade.position] is old_target
    assert shop.roster.coach is original.coach
    assert shop.roster.special_teams is original.special_teams
    assert shop.roster.team_name == original.team_name
    assert shop.remaining_budget == TRAINING_POINT_BUDGET - power_upgrade.cost - stamina_upgrade.cost
    assert len(shop.purchased_upgrades) == 2


def test_multiple_purchases_compose_and_overspending_is_atomic() -> None:
    shop = FootballShop(_roster(), 5)
    power = next(u for u in shop.offer if u.stat is FootballUpgradeStat.POWER)
    stamina = next(u for u in shop.offer if u.stat is FootballUpgradeStat.STAMINA)
    remaining = next(u for u in shop.offer if u is not power and u is not stamina)

    shop.buy(power)
    shop.buy(stamina)
    before = shop.state
    with pytest.raises(ValueError, match="exceeds the remaining"):
        shop.buy(remaining)
    assert shop.state == before

    assert shop.roster.players[power.position].power == (
        _roster().players[power.position].power + power.amount
    )
    assert shop.roster.players[stamina.position].stamina == (
        _roster().players[stamina.position].stamina + stamina.amount
    )


def test_unoffered_duplicate_invalid_and_finished_actions_fail_atomically() -> None:
    shop = FootballShop(_roster(), 31)
    state = shop.state
    offered = shop.offer[0]
    fabricated = replace(offered, upgrade_id="not-offered")

    with pytest.raises(ValueError, match="not offered"):
        shop.buy(fabricated)
    with pytest.raises(ValueError, match="valid index"):
        shop.buy(True)
    with pytest.raises(ValueError, match="out of range"):
        shop.buy(3)
    assert shop.state == state

    shop.buy(offered)
    after_purchase = shop.state
    with pytest.raises(ValueError, match="already been purchased"):
        shop.buy(offered)
    assert shop.state == after_purchase

    shop.finish()
    finished_state = shop.state
    with pytest.raises(ValueError, match="shop is finished"):
        shop.buy(shop.offer[1])
    with pytest.raises(ValueError, match="shop is finished"):
        shop.finish()
    assert shop.state == finished_state


def test_capped_stamina_upgrades_are_excluded_and_cannot_be_bought() -> None:
    roster = _roster(stamina=1.0)
    shop = FootballShop(roster, 61)

    assert all(
        upgrade.stat is not FootballUpgradeStat.STAMINA for upgrade in shop.offer
    )
    capped_upgrade = FootballUpgrade(
        upgrade_id="qb_stamina",
        name="QB stamina training",
        description="Increase QB player stamina by 0.1.",
        position=FootballPosition.QB,
        stat=FootballUpgradeStat.STAMINA,
        amount=STAMINA_UPGRADE_AMOUNT,
        cost=2,
    )
    before = shop.state
    with pytest.raises(ValueError, match="capped stamina upgrades are excluded"):
        shop.buy(capped_upgrade)
    assert shop.state == before


def test_roster_updates_are_immutable_valid_and_seeded_outcomes_match() -> None:
    original = _roster()
    first = FootballShop(original, 7)
    replay = FootballShop(original, 7)
    choices = (0, 1)

    for choice in choices:
        first.buy(choice)
        replay.buy(choice)

    assert first.state == replay.state
    assert first.roster == replay.roster
    assert original == _roster()
    upgraded_positions = {upgrade.position for upgrade in first.purchased_upgrades}
    for position in FootballPosition:
        if position not in upgraded_positions:
            assert first.roster.players[position] is original.players[position]
    assert first.roster.coach is original.coach
    assert first.roster.special_teams is original.special_teams
    assert first.roster.team_name == original.team_name
    assert set(first.roster.players) == set(FootballPosition)
    assert all(
        0 <= player.volatility <= 1 and 0 <= player.stamina <= 1
        for player in first.roster.players.values()
    )


def test_shop_upgrade_preserves_specialist_identity_and_inactive_perk_text() -> None:
    original_roster = _drafted_roster()
    shop = FootballShop(original_roster, 19)
    upgrade = shop.offer[0]
    original_player = original_roster.players[upgrade.position]
    assert original_player.player_type_id is not None
    original_type = player_type_for_id(original_player.player_type_id)

    updated_roster = shop.buy(upgrade).roster
    updated_player = updated_roster.players[upgrade.position]

    assert updated_player is not original_player
    assert updated_player.player_type_id == original_player.player_type_id
    updated_type = player_type_for_id(updated_player.player_type_id)
    assert updated_type is original_type
    assert updated_type.partner_position is original_type.partner_position
    assert (
        updated_type.perk.display_text
        if updated_type.perk is not None
        else None
    ) == (
        original_type.perk.display_text if original_type.perk is not None else None
    )


def test_builder_shop_roster_initializes_match_with_local_ai_opponent() -> None:
    built_roster = _drafted_roster()
    shop = FootballShop(built_roster, 9)
    shop.buy(0)
    final_roster = shop.roster
    ai = FootballAI(FootballTeamSide.TEAM_B, FootballAIDifficulty.STANDARD, 44)
    opponent = ai.generate_opponent_roster()
    state = FootballMatchState(
        team_a=final_roster,
        team_b=opponent,
        random_seed=202,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=10.0,
        offense_field_position=25.0,
        game_clock_seconds=900,
        period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
    )

    simulator = FootballMatchSimulator(state)
    scheme = ai.choose_action(simulator.state)
    assert isinstance(scheme, DefensiveSchemeAction)
    simulator.select_defensive_scheme(scheme)
    resolved = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)

    assert resolved.team_a is final_roster
    assert resolved.team_b is opponent
    assert resolved.match_events


def test_builder_and_shop_do_not_consume_ai_match_or_global_random_streams() -> None:
    ai = FootballAI(FootballTeamSide.TEAM_B, FootballAIDifficulty.EASY, 91)
    ai.generate_opponent_roster()
    initial_roster = _roster("Initial")
    match_state = FootballMatchState(
        team_a=initial_roster,
        team_b=_roster("Opponent"),
        random_seed=37,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=10.0,
        offense_field_position=25.0,
        game_clock_seconds=900,
        period=1,
    )
    simulator = FootballMatchSimulator(match_state)
    ai_rng = ai._rng.getstate()
    match_rng = simulator.rng.getstate()
    global_rng = random.getstate()

    builder = FootballTeamBuilder("Independent", 19)
    builder.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        builder.choose_player(position, 0)
    shop = FootballShop(builder.build_roster(), 23)
    shop.buy(0)

    assert ai._rng.getstate() == ai_rng
    assert simulator.rng.getstate() == match_rng
    assert random.getstate() == global_rng
