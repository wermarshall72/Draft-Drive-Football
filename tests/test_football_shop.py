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
    ACTION_POINT_BUDGET,
    POWER_UPGRADE_AMOUNT,
    RARITY_WEIGHTS,
    STAMINA_UPGRADE_AMOUNT,
    TRAINING_POINT_BUDGET,
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
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


def _shop_with_both_upgrade_stats(
    roster: FootballRoster,
    seed: int,
) -> FootballShop:
    shop = FootballShop(roster, seed)
    for _ in range(10):
        stats = {upgrade.stat for upgrade in shop.offer}
        if {
            FootballUpgradeStat.POWER,
            FootballUpgradeStat.STAMINA,
        } <= stats:
            return shop
        shop.move_to_next_day()
    raise AssertionError("The seeded shop did not offer both upgrade stats.")


def test_shop_offer_is_three_distinct_affordable_upgrades_and_seeded() -> None:
    assert POWER_UPGRADE_AMOUNT == 1.0
    assert STAMINA_UPGRADE_AMOUNT == 0.1
    first = FootballShop(_roster(), 12)
    replay = FootballShop(_roster(), 12)

    assert len(first.offer) == 3
    assert len({upgrade.upgrade_id for upgrade in first.offer}) == 3
    assert all(0 < upgrade.cost <= TRAINING_POINT_BUDGET for upgrade in first.offer)
    assert first.remaining_ap == ACTION_POINT_BUDGET
    assert all(
        upgrade.rarity
        is (
            FootballShopRarity.UNCOMMON
            if upgrade.stat is FootballUpgradeStat.POWER
            else FootballShopRarity.COMMON
        )
        for upgrade in first.offer
    )
    assert first.offer == replay.offer
    assert first.state == replay.state


def test_power_and_stamina_purchases_change_only_the_targeted_stat() -> None:
    original = _roster()
    shop = _shop_with_both_upgrade_stats(original, 5)
    power_upgrade = next(
        upgrade for upgrade in shop.offer
        if upgrade.stat is FootballUpgradeStat.POWER
    )
    stamina_upgrade = next(
        upgrade for upgrade in shop.offer
        if upgrade.stat is FootballUpgradeStat.STAMINA
    )
    old_target = original.players[power_upgrade.position]

    initial_ap = shop.remaining_ap
    shop.buy(power_upgrade)
    powered = shop.roster
    updated_target = powered.players[power_upgrade.position]
    assert updated_target.power == old_target.power + power_upgrade.amount
    assert updated_target.volatility == old_target.volatility
    assert updated_target.stamina == old_target.stamina
    assert shop.remaining_budget == initial_ap - power_upgrade.cost

    old_stamina_target = powered.players[stamina_upgrade.position]
    ap_before_stamina = shop.remaining_ap
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
    assert shop.remaining_budget == ap_before_stamina - stamina_upgrade.cost
    assert len(shop.purchased_upgrades) == 2


def test_multiple_purchases_compose_and_overspending_is_atomic() -> None:
    expensive_card = FootballShopCard(
        card_id="expensive-play",
        name="Test play",
        description="A test-only catalog card.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=ACTION_POINT_BUDGET + 1,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
    )
    shop = FootballShop(
        _roster(),
        5,
        catalogs={FootballShopSection.PLAYS_SCHEMES: (expensive_card,)},
    )
    before = shop.state
    rng_before = shop._rng.getstate()
    with pytest.raises(ValueError, match="exceeds the remaining"):
        shop.buy_card(FootballShopSection.PLAYS_SCHEMES, expensive_card.card_id)
    assert shop.state == before
    assert shop._rng.getstate() == rng_before


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


def _future_catalog_card(
    card_id: str,
    section: FootballShopSection,
    rarity: FootballShopRarity = FootballShopRarity.COMMON,
    *,
    eligible=lambda _roster: True,
) -> FootballShopCard:
    return FootballShopCard(
        card_id=card_id,
        name=f"Test {card_id}",
        description="A test-only future catalog card.",
        section=section,
        rarity=rarity,
        cost=1,
        eligible=eligible,
        effect=lambda roster: roster,
    )


def test_three_sections_start_with_requested_slots_and_no_future_cards() -> None:
    shop = FootballShop(_roster(), 4)
    state = shop.state

    player = state.section(FootballShopSection.PLAYER_UPGRADES)
    plays = state.section(FootballShopSection.PLAYS_SCHEMES)
    coaches = state.section(FootballShopSection.COACH_UPGRADES)
    assert state.remaining_ap == 12 and state.game_number == 1 and state.day == 1
    assert [slot.unlocked for slot in player.slots] == [True, True, True, False]
    assert player.slots[3].unlock_cost == 4 and player.slots[3].can_unlock
    assert len([slot for slot in player.slots if slot.unlocked and slot.card]) == 3
    assert [slot.unlocked for slot in plays.slots] == [True] * 4 + [False] * 2
    assert all(slot.card is None for slot in plays.slots)
    assert plays.slots[4].unlock_cost == 4 and not plays.slots[4].can_unlock
    assert plays.slots[5].unlock_cost == 5 and not plays.slots[5].can_unlock
    assert [slot.unlocked for slot in coaches.slots] == [False, False]
    assert coaches.slots[0].unlock_cost == 4
    assert not coaches.slots[0].can_unlock
    assert "after game 3" in coaches.slots[0].disabled_reason
    assert coaches.slots[1].unlock_cost == 6 and not coaches.slots[1].can_unlock

    before = shop.state
    rng_before = shop._rng.getstate()
    with pytest.raises(ValueError, match="catalog is not available"):
        shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 5)
    with pytest.raises(ValueError, match="after game 3"):
        shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    assert shop.state == before
    assert shop._rng.getstate() == rng_before

    after_game_three = FootballShop(_roster(), 5, game_number=4)
    coach_slot = after_game_three.state.section(
        FootballShopSection.COACH_UPGRADES
    ).slots[0]
    assert not coach_slot.can_unlock
    assert "not available yet" in coach_slot.disabled_reason


def test_player_slot_unlock_is_affordable_and_immediately_offered() -> None:
    shop = FootballShop(_roster(), 12)
    before_ap = shop.remaining_ap

    state = shop.unlock_slot(FootballShopSection.PLAYER_UPGRADES, 4)
    section = state.section(FootballShopSection.PLAYER_UPGRADES)

    assert state.remaining_ap == before_ap - 4
    assert section.slots[3].unlocked
    assert section.slots[3].card is not None
    assert len({slot.card.card_id for slot in section.slots if slot.card}) == 4
    with pytest.raises(ValueError, match="already unlocked"):
        shop.unlock_slot(FootballShopSection.PLAYER_UPGRADES, 4)


def test_targeted_power_upgrades_have_distinct_position_identities() -> None:
    upgrades = tuple(
        FootballUpgrade(
            upgrade_id=f"{position.value.lower()}_power",
            name=f"{position.value} power",
            description=f"Increase {position.value} power.",
            position=position,
            stat=FootballUpgradeStat.POWER,
            amount=1.0,
            cost=3,
            rarity=FootballShopRarity.UNCOMMON,
        )
        for position in (FootballPosition.QB, FootballPosition.RB)
    )
    cards = tuple(
        FootballShopCard(
            card_id=upgrade.upgrade_id,
            name=upgrade.name,
            description=upgrade.description,
            section=FootballShopSection.PLAYER_UPGRADES,
            rarity=upgrade.rarity,
            cost=upgrade.cost,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            upgrade=upgrade,
        )
        for upgrade in upgrades
    )
    shop = FootballShop(
        _roster(),
        13,
        catalogs={FootballShopSection.PLAYER_UPGRADES: cards},
    )

    offered = shop.state.offer
    assert {upgrade.upgrade_id for upgrade in offered} == {
        "qb_power",
        "rb_power",
    }
    assert {upgrade.position for upgrade in offered} == {
        FootballPosition.QB,
        FootballPosition.RB,
    }


def test_play_slot_unlock_costs_and_catalog_cards_fill_each_new_slot() -> None:
    cards = tuple(
        _future_catalog_card(
            f"play-{index}",
            FootballShopSection.PLAYS_SCHEMES,
            FootballShopRarity.UNCOMMON,
        )
        for index in range(6)
    )
    shop = FootballShop(
        _roster(),
        19,
        catalogs={FootballShopSection.PLAYS_SCHEMES: cards},
    )

    first = shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 5)
    assert first.remaining_ap == 8
    assert first.section(FootballShopSection.PLAYS_SCHEMES).slots[4].card is not None
    second = shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 6)
    section = second.section(FootballShopSection.PLAYS_SCHEMES)
    assert second.remaining_ap == 3
    assert section.slots[5].unlocked and section.slots[5].card is not None
    assert len({slot.card.card_id for slot in section.slots if slot.card}) == 6


def test_coach_slot_unlock_is_available_after_game_three_and_can_be_deferred() -> None:
    cards = tuple(
        _future_catalog_card(
            f"coach-{index}",
            FootballShopSection.COACH_UPGRADES,
            FootballShopRarity.RARE,
        )
        for index in range(2)
    )
    shop = FootballShop(
        _roster(),
        20,
        game_number=3,
        catalogs={FootballShopSection.COACH_UPGRADES: cards},
    )
    shop.finish()
    game_four = shop.open_next_visit(4)
    coach_section = game_four.section(FootballShopSection.COACH_UPGRADES)
    assert coach_section.slots[0].can_unlock
    assert coach_section.slots[0].unlock_cost == 4

    shop.finish()
    game_five = shop.open_next_visit(5)
    assert game_five.section(FootballShopSection.COACH_UPGRADES).slots[0].can_unlock
    unlocked = shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    section = unlocked.section(FootballShopSection.COACH_UPGRADES)
    assert unlocked.remaining_ap == 8
    assert section.slots[0].unlocked and section.slots[0].card is not None
    assert section.slots[1].can_unlock and section.slots[1].unlock_cost == 6

    second = shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 2)
    section = second.section(FootballShopSection.COACH_UPGRADES)
    assert second.remaining_ap == 2
    assert section.slots[1].unlocked and section.slots[1].card is not None
    with pytest.raises(ValueError, match="already unlocked"):
        shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 2)


def test_rarity_weights_and_offer_eligibility_are_renormalized() -> None:
    assert dict(RARITY_WEIGHTS) == {
        FootballShopRarity.COMMON: 40,
        FootballShopRarity.UNCOMMON: 30,
        FootballShopRarity.RARE: 20,
        FootballShopRarity.VERY_RARE: 10,
    }
    all_rarities = tuple(
        _future_catalog_card(
            f"rarity-{rarity.value}",
            FootballShopSection.PLAYS_SCHEMES,
            rarity,
        )
        for rarity in FootballShopRarity
    )
    counts = {rarity: 0 for rarity in FootballShopRarity}
    for seed in range(1000):
        shop = FootballShop(
            _roster(),
            seed,
            catalogs={FootballShopSection.PLAYS_SCHEMES: all_rarities},
        )
        first_card = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots[0].card
        assert first_card is not None
        counts[first_card.rarity] += 1
        offer = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
        ids = [slot.card.card_id for slot in offer if slot.card is not None]
        assert len(ids) == len(set(ids))
    for rarity, weight in RARITY_WEIGHTS.items():
        assert abs(counts[rarity] - weight * 10) < 70

    only_rare = _future_catalog_card(
        "only-rare",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.RARE,
    )
    ineligible_common = _future_catalog_card(
        "ineligible-common",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.COMMON,
        eligible=lambda _roster: False,
    )
    shop = FootballShop(
        _roster(),
        21,
        catalogs={
            FootballShopSection.PLAYS_SCHEMES: (only_rare, ineligible_common)
        },
    )
    slots = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
    assert slots[0].card is only_rare
    assert all(slot.card is None for slot in slots[1:4])


def test_purchase_stays_visible_until_reroll_and_is_eligible_next_visit() -> None:
    upgrade = FootballUpgrade(
        upgrade_id="qb_power",
        name="QB power",
        description="Increase QB power.",
        position=FootballPosition.QB,
        stat=FootballUpgradeStat.POWER,
        amount=1.0,
        cost=3,
        rarity=FootballShopRarity.UNCOMMON,
    )

    def apply(roster: FootballRoster) -> FootballRoster:
        players = dict(roster.players)
        player = players[FootballPosition.QB]
        players[FootballPosition.QB] = replace(player, power=player.power + 1.0)
        return FootballRoster(
            roster.team_name,
            players,
            roster.coach,
            roster.special_teams,
            roster.coach_assignment,
        )

    card = FootballShopCard(
        card_id=upgrade.upgrade_id,
        name=upgrade.name,
        description=upgrade.description,
        section=FootballShopSection.PLAYER_UPGRADES,
        rarity=upgrade.rarity,
        cost=upgrade.cost,
        eligible=lambda _roster: True,
        effect=apply,
        upgrade=upgrade,
    )
    shop = FootballShop(
        _roster(),
        22,
        catalogs={FootballShopSection.PLAYER_UPGRADES: (card,)},
    )
    initial_power = shop.roster.players[FootballPosition.QB].power
    purchased = shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    player_slots = purchased.section(FootballShopSection.PLAYER_UPGRADES).slots
    assert player_slots[0].card is card and player_slots[0].purchased
    assert purchased.roster.players[FootballPosition.QB].power == initial_power + 1

    next_day = shop.move_to_next_day()
    assert next_day.day == 2 and next_day.remaining_ap == 8
    assert all(slot.card is None for slot in next_day.section(
        FootballShopSection.PLAYER_UPGRADES
    ).slots[:3])
    assert next_day.purchased_cards == (card,)

    shop.finish()
    later_visit = shop.open_next_visit(2)
    assert later_visit.remaining_ap == 12 and later_visit.day == 1
    assert later_visit.purchased_cards == ()
    assert later_visit.section(FootballShopSection.PLAYER_UPGRADES).slots[0].card is card


def test_reroll_and_unlock_rejections_preserve_ap_state_and_shop_rng() -> None:
    shop = FootballShop(_roster(), 23)
    for _ in range(11):
        shop.move_to_next_day()
    assert shop.remaining_ap == 1

    before = shop.state
    rng_before = shop._rng.getstate()
    with pytest.raises(ValueError, match="Need 4 AP"):
        shop.unlock_slot(FootballShopSection.PLAYER_UPGRADES, 4)
    assert shop.state == before
    assert shop._rng.getstate() == rng_before

    shop.move_to_next_day()
    assert shop.remaining_ap == 0
    before_empty = shop.state
    rng_empty = shop._rng.getstate()
    with pytest.raises(ValueError, match="requires 1 AP"):
        shop.move_to_next_day()
    assert shop.state == before_empty
    assert shop._rng.getstate() == rng_empty
    assert shop.finish().finished


def test_reroll_refreshes_all_active_sections_deterministically() -> None:
    play_cards = tuple(
        _future_catalog_card(
            f"play-reroll-{index}",
            FootballShopSection.PLAYS_SCHEMES,
            FootballShopRarity.UNCOMMON,
        )
        for index in range(6)
    )
    catalogs = {FootballShopSection.PLAYS_SCHEMES: play_cards}
    first = FootballShop(_roster(), 24, catalogs=catalogs)
    replay = FootballShop(_roster(), 24, catalogs=catalogs)
    first_rng = first._rng.getstate()

    first_state = first.move_to_next_day()
    replay_state = replay.move_to_next_day()

    assert first_state == replay_state
    assert first._rng.getstate() != first_rng
    assert first_state.day == 2 and first_state.remaining_ap == 11
    for section_id in (
        FootballShopSection.PLAYER_UPGRADES,
        FootballShopSection.PLAYS_SCHEMES,
    ):
        section = first_state.section(section_id)
        cards = [slot.card for slot in section.slots if slot.unlocked]
        assert all(card is not None for card in cards)
        ids = [card.card_id for card in cards if card is not None]
        assert len(ids) == len(set(ids))
    assert not first_state.section(FootballShopSection.COACH_UPGRADES).slots[0].unlocked
