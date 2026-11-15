from dataclasses import replace

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCardFamily,
    FootballCoach,
    FootballCoachAssignment,
    FootballConversionAction,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballDeckState,
    FootballFourthDownAction,
    FootballMatchResult,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_coaches import COACH_PAIR_OFFERS
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballRunPhase,
)
from src.engine.football_decks import OFFENSIVE_PLAY_CATALOG
from src.engine.football_shop import (
    ACTION_POINT_BUDGET,
    COACH_UPGRADE_CATALOG,
    FootballShop,
    FootballShopRarity,
    FootballShopSection,
    FootballUpgradeStat,
)
from src.engine.football_simulator import (
    FIELD_GOAL_BLOCK_CHANCE,
    FootballMatchSimulator,
    adjusted_offensive_play_clock_seconds,
    blocked_kick_probability,
    calculate_match_play_estimate,
    calculate_matchup_power,
    calculate_play_estimate,
    field_goal_distance_for_position,
    field_goal_success_probability,
    field_goal_success_probability_for_team,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER


def _roster(
    name: str,
    *,
    power: float = 10.0,
    volatility: float = 0.2,
    stamina: float = 0.75,
    coach_assignment: FootballCoachAssignment | None = None,
) -> FootballRoster:
    players = {
        position: FootballPlayer(
            name=f"{name} {position.value}",
            position=position,
            power=power,
            volatility=volatility,
            stamina=stamina,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        name,
        players,
        FootballCoach(f"{name} Coach"),
        FootballSpecialTeams(f"{name} Special Teams"),
        coach_assignment,
    )


def _effect(
    upgrade_id: str,
    kind: FootballCoachUpgradeKind,
    magnitude: float,
    family: FootballCardFamily | None = None,
) -> FootballCoachUpgradeEffect:
    return FootballCoachUpgradeEffect(upgrade_id, kind, magnitude, family)


def _match_state(**overrides) -> FootballMatchState:
    values = {
        "team_a": _roster("Human"),
        "team_b": _roster("AI"),
        "random_seed": 71,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 30.0,
        "game_clock_seconds": 900,
        "period": 1,
        "awaited_action": FootballAwaitedAction.DEFENSIVE_SCHEME,
    }
    values.update(overrides)
    return FootballMatchState(**values)


def _coach_card(card_id: str):
    return next(card for card in COACH_UPGRADE_CATALOG if card.card_id == card_id)


def test_catalog_is_typed_unique_and_includes_required_rarity_and_costs() -> None:
    expected = {
        "two_minute_drill": (FootballShopRarity.UNCOMMON, 3),
        "front_seven_film": (FootballShopRarity.UNCOMMON, 3),
        "rhythm_install": (FootballShopRarity.RARE, 3),
        "disguise_package": (FootballShopRarity.RARE, 3),
        "fourth_quarter_conditioning": (FootballShopRarity.UNCOMMON, 3),
        "iron_lungs": (FootballShopRarity.UNCOMMON, 3),
        "booster_club_drive": (FootballShopRarity.RARE, 4),
        "facilities_fund": (FootballShopRarity.RARE, 5),
        "bye_week": (FootballShopRarity.VERY_RARE, 6),
        "tempo_install": (FootballShopRarity.RARE, 3),
        "huddle_up": (FootballShopRarity.RARE, 3),
        "vertical_threat": (FootballShopRarity.RARE, 3),
        "pattern_match": (FootballShopRarity.RARE, 3),
        "ball_security_clinic": (FootballShopRarity.RARE, 3),
        "field_goal_lab": (FootballShopRarity.RARE, 4),
        "clean_pocket_protection": (FootballShopRarity.UNCOMMON, 3),
        "punt_return_lane": (FootballShopRarity.UNCOMMON, 2),
        "kickoff_return_lane": (FootballShopRarity.UNCOMMON, 2),
    }
    assert {card.card_id for card in COACH_UPGRADE_CATALOG} == set(expected)
    assert len({card.name for card in COACH_UPGRADE_CATALOG}) == len(expected)
    assert all(
        card.section is FootballShopSection.COACH_UPGRADES
        and card.coach_upgrade_effect is not None
        and card.name.strip()
        and card.description.strip()
        and 0 < card.cost <= ACTION_POINT_BUDGET
        and (card.rarity, card.cost) == expected[card.card_id]
        for card in COACH_UPGRADE_CATALOG
    )
    bye_week = _coach_card("bye_week")
    assert bye_week.rarity is FootballShopRarity.VERY_RARE
    assert bye_week.cost == 6
    assert _coach_card("booster_club_drive").cost == 4
    assert _coach_card("facilities_fund").cost == 5


def test_named_coach_upgrade_is_run_unique_across_rerolls_and_shop_visits() -> None:
    card = _coach_card("two_minute_drill")
    shop = FootballShop(
        _roster("Shop"),
        19,
        game_number=4,
        catalogs={FootballShopSection.COACH_UPGRADES: (card,)},
    )
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    assert shop.state.section(FootballShopSection.COACH_UPGRADES).slots[0].card == card

    before_ap = shop.remaining_ap
    shop.buy_card(FootballShopSection.COACH_UPGRADES, card.card_id)
    assert shop.remaining_ap == before_ap - card.cost
    assert shop.state.owned_coach_upgrades == (card,)
    with pytest.raises(ValueError, match="already been purchased"):
        shop.buy_card(FootballShopSection.COACH_UPGRADES, card.card_id)

    shop.move_to_next_day()
    assert shop.state.section(FootballShopSection.COACH_UPGRADES).slots[0].card is None
    shop.finish()
    next_visit = shop.open_next_visit(5)
    assert next_visit.section(FootballShopSection.COACH_UPGRADES).slots[0].card is None
    assert next_visit.owned_coach_upgrades == (card,)


def test_future_shop_ap_stacks_without_changing_the_current_shop() -> None:
    shop = FootballShop(
        _roster("Shop"),
        21,
        game_number=4,
        catalogs={
            FootballShopSection.COACH_UPGRADES: (
                _coach_card("booster_club_drive"),
                _coach_card("facilities_fund"),
            )
        },
    )
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    first = shop.state.section(FootballShopSection.COACH_UPGRADES).slots[0].card
    assert first is not None
    before_purchase = shop.remaining_ap
    shop.buy_card(FootballShopSection.COACH_UPGRADES, first.card_id)
    assert shop.remaining_ap == before_purchase - first.cost
    assert shop.state.future_shop_ap_bonus == 1

    shop.finish()
    next_visit = shop.open_next_visit(5)
    assert next_visit.remaining_ap == ACTION_POINT_BUDGET + 1
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 2)
    second = next(
        slot.card
        for slot in shop.state.section(FootballShopSection.COACH_UPGRADES).slots
        if slot.card is not None
    )
    assert second is not None and second.card_id != first.card_id
    before_second = shop.remaining_ap
    shop.buy_card(FootballShopSection.COACH_UPGRADES, second.card_id)
    assert shop.remaining_ap == before_second - second.cost
    assert shop.state.future_shop_ap_bonus == 2

    shop.finish()
    assert shop.open_next_visit(6).remaining_ap == ACTION_POINT_BUDGET + 2


def test_future_ap_upgrade_is_not_offered_in_the_last_scheduled_shop() -> None:
    shop = FootballShop(
        _roster("Shop"),
        22,
        game_number=10,
        catalogs={
            FootballShopSection.COACH_UPGRADES: (
                _coach_card("booster_club_drive"),
            )
        },
    )
    section = shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1).section(
        FootballShopSection.COACH_UPGRADES
    )
    assert section.slots[0].card is None


def test_bye_week_shop_purchase_is_atomic_and_preserves_run_assets() -> None:
    bye_week = _coach_card("bye_week")
    shop = FootballShop(
        _roster("Shop", stamina=0.75),
        23,
        game_number=3,
        catalogs={FootballShopSection.COACH_UPGRADES: (bye_week,)},
    )
    player_upgrade = shop.offer[0]
    shop.buy_upgrade(player_upgrade)
    play_card = next(
        slot.card
        for slot in shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
        if slot.card is not None and slot.card.football_card is not None
    )
    assert play_card is not None
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, play_card.card_id)
    roster_before = shop.roster
    offense_deck_before = shop.offensive_deck
    defense_deck_before = shop.defensive_deck
    player_history_before = shop.purchased_upgrades

    shop.finish()
    shop.open_next_visit(4)
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    remaining_before_bye = shop.remaining_ap
    shop.buy_card(FootballShopSection.COACH_UPGRADES, bye_week.card_id)
    assert shop.finished
    assert shop.remaining_ap == remaining_before_bye - bye_week.cost
    assert shop.state.owned_coach_upgrades == (bye_week,)
    with pytest.raises(ValueError, match="finished"):
        shop.move_to_next_day()

    next_visit = shop.open_next_visit(5)
    assert next_visit.remaining_ap == ACTION_POINT_BUDGET
    assert next_visit.roster == roster_before
    assert next_visit.offensive_deck == offense_deck_before
    assert next_visit.defensive_deck == defense_deck_before
    assert next_visit.purchased_upgrades == player_history_before
    assert next_visit.owned_coach_upgrades == (bye_week,)
    assert next_visit.section(FootballShopSection.COACH_UPGRADES).slots[0].card is None


def test_bye_week_insufficient_ap_error_does_not_change_shop_or_rng() -> None:
    shop = FootballShop(
        _roster("Shop"),
        24,
        game_number=4,
        catalogs={FootballShopSection.COACH_UPGRADES: (_coach_card("bye_week"),)},
    )
    shop.buy_upgrade(shop.offer[0])
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    assert shop.remaining_ap < _coach_card("bye_week").cost
    before = shop.state
    rng_before = shop._rng.getstate()
    with pytest.raises(ValueError, match="remaining AP"):
        shop.buy_card(FootballShopSection.COACH_UPGRADES, "bye_week")
    assert shop.state == before
    assert shop._rng.getstate() == rng_before
    assert not shop.finished


def test_team_power_effects_apply_after_player_and_existing_coach_modifiers() -> None:
    assignment = COACH_PAIR_OFFERS[0].assignment
    offense = _roster("Offense", coach_assignment=assignment)
    defense = _roster("Defense", coach_assignment=assignment)
    scheme = DefensiveSchemeAction.RB_RUN
    play = OffensivePlayAction.DEEP_PASS
    base = calculate_matchup_power(offense, defense, play, scheme)
    effect = _effect(
        "power",
        FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
        0.05,
    )
    boosted = calculate_matchup_power(
        offense,
        defense,
        play,
        scheme,
        offense_coach_upgrades=(effect,),
    )
    assert boosted.offense == pytest.approx(base.offense * 1.05)
    assert boosted.defense == base.defense

    upgraded_players = dict(offense.players)
    target = upgraded_players[FootballPosition.QB]
    upgraded_players[FootballPosition.QB] = replace(target, power=target.power + 1)
    player_upgraded = replace(offense, players=upgraded_players)
    player_power = calculate_matchup_power(
        player_upgraded, defense, play, scheme
    ).offense
    player_and_coach = calculate_matchup_power(
        player_upgraded,
        defense,
        play,
        scheme,
        offense_coach_upgrades=(effect,),
    ).offense
    assert player_and_coach == pytest.approx(player_power * 1.05)

    defense_effect = _effect(
        "defense_power",
        FootballCoachUpgradeKind.DEFENSE_POWER_BOOST,
        0.05,
    )
    defense_boosted = calculate_matchup_power(
        offense,
        defense,
        play,
        scheme,
        defense_coach_upgrades=(defense_effect,),
    )
    assert defense_boosted.defense == pytest.approx(base.defense * 1.05)


def test_stamina_and_volatility_effects_use_existing_caps_and_fatigue_model() -> None:
    tired_offense = _roster("Tired", stamina=0.9, volatility=0.2)
    rested_defense = _roster("Rested", stamina=1.0, volatility=0.0)
    play = OffensivePlayAction.DEEP_PASS
    scheme = DefensiveSchemeAction.RB_RUN
    base = calculate_play_estimate(
        tired_offense,
        rested_defense,
        play,
        scheme,
        prior_plays=30,
    )
    stamina = _effect(
        "stamina",
        FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST,
        0.1,
    )
    stamina_boosted = calculate_play_estimate(
        tired_offense,
        rested_defense,
        play,
        scheme,
        prior_plays=30,
        offense_coach_upgrades=(stamina,),
    )
    assert stamina_boosted.matchup.offense > base.matchup.offense

    capped_roster = _roster("Capped", stamina=1.0)
    capped = calculate_play_estimate(
        capped_roster,
        rested_defense,
        play,
        scheme,
        prior_plays=30,
        offense_coach_upgrades=(stamina,),
    )
    fully_rested = calculate_play_estimate(
        capped_roster,
        rested_defense,
        play,
        scheme,
        prior_plays=30,
    )
    assert capped.matchup.offense == fully_rested.matchup.offense

    steady = _effect(
        "steady",
        FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
        0.15,
    )
    reduced_spread = calculate_play_estimate(
        tired_offense,
        rested_defense,
        play,
        scheme,
        offense_coach_upgrades=(steady,),
    )
    assert reduced_spread.yardage_spread == pytest.approx(
        base.yardage_spread * 0.85
    )


def test_family_yardage_effects_modify_calculation_after_additive_bonuses() -> None:
    offense = _roster("Offense", volatility=0.0)
    defense = _roster("Defense", volatility=0.0)
    deep_pass = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=2.0,
    )
    vertical = _effect(
        "vertical",
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        0.10,
        FootballCardFamily.DEEP_PASS,
    )
    boosted = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=2.0,
        offense_coach_upgrades=(vertical,),
    )
    assert boosted.yards_on_success == pytest.approx(
        deep_pass.yards_on_success * 1.10
    )
    assert boosted.expected_yards == pytest.approx(deep_pass.expected_yards * 1.10)
    assert boosted.turnover_probability == deep_pass.turnover_probability
    assert boosted.incomplete_probability == deep_pass.incomplete_probability

    negative_bonus = -deep_pass.yards_on_success
    negative_baseline = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=negative_bonus,
    )
    negative = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=negative_bonus,
        offense_coach_upgrades=(vertical,),
    )
    assert negative_baseline.yards_on_success == pytest.approx(-2.0)
    assert negative.yards_on_success == pytest.approx(-1.8)
    assert negative.expected_yards > negative_baseline.expected_yards
    zero_baseline = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
    )
    zero = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=-zero_baseline.yards_on_success,
        offense_coach_upgrades=(vertical,),
    )
    assert zero.yards_on_success == pytest.approx(0.0)

    capped_bonus = _effect(
        "large_deep_bonus",
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        0.90,
        FootballCardFamily.DEEP_PASS,
    )
    uncapped_positive = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
    )
    capped_positive = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.RB_RUN,
        yardage_bonus=20.0 - uncapped_positive.yards_on_success,
        offense_coach_upgrades=(capped_bonus,),
    )
    assert capped_positive.yards_on_success == 25.0

    medium = _effect(
        "medium_defense",
        FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
        0.10,
        FootballCardFamily.MEDIUM_PASS,
    )
    unmodified = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
    )
    reduced = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        defense_coach_upgrades=(medium,),
    )
    assert reduced.yards_on_success == pytest.approx(
        unmodified.yards_on_success * 0.90
    )
    unaffected = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.DEEP_PASS,
        defense_coach_upgrades=(medium,),
    )
    deep_baseline = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.DEEP_PASS,
        DefensiveSchemeAction.DEEP_PASS,
    )
    assert unaffected.yards_on_success == deep_baseline.yards_on_success

    negative_medium_baseline = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        yardage_bonus=-unmodified.yards_on_success - 1.0,
    )
    negative_medium_reduced = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        yardage_bonus=-unmodified.yards_on_success - 1.0,
        defense_coach_upgrades=(medium,),
    )
    assert negative_medium_baseline.yards_on_success == pytest.approx(-1.0)
    assert negative_medium_reduced.yards_on_success == pytest.approx(-1.1)
    assert negative_medium_reduced.expected_yards < negative_medium_baseline.expected_yards
    large_defense = _effect(
        "large_medium_defense",
        FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
        0.90,
        FootballCardFamily.MEDIUM_PASS,
    )
    capped_negative = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        yardage_bonus=-4.0 - unmodified.yards_on_success,
        defense_coach_upgrades=(large_defense,),
    )
    assert capped_negative.yards_on_success == -5.0

    opposed = calculate_play_estimate(
        offense,
        defense,
        OffensivePlayAction.MEDIUM_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        yardage_bonus=-unmodified.yards_on_success - 1.0,
        offense_coach_upgrades=(
            _effect(
                "medium_offense",
                FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
                0.10,
                FootballCardFamily.MEDIUM_PASS,
            ),
        ),
        defense_coach_upgrades=(medium,),
    )
    assert opposed.yards_on_success == pytest.approx(-1.0)


def test_interception_reduction_is_relative_and_human_side_specific() -> None:
    interception = _effect(
        "interception",
        FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
        0.20,
    )
    state = _match_state(
        team_a_coach_upgrades=(interception,),
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
    )
    base_state = replace(state, team_a_coach_upgrades=())
    base = calculate_match_play_estimate(base_state, OffensivePlayAction.DEEP_PASS)
    boosted = calculate_match_play_estimate(state, OffensivePlayAction.DEEP_PASS)
    ai_offense = calculate_match_play_estimate(
        state,
        OffensivePlayAction.DEEP_PASS,
        offense_side=FootballTeamSide.TEAM_B,
    )
    assert boosted.turnover_probability == pytest.approx(
        base.turnover_probability * 0.8
    )
    assert boosted.incomplete_probability == base.incomplete_probability
    assert ai_offense.turnover_probability == base.turnover_probability

    run_base = calculate_match_play_estimate(base_state, OffensivePlayAction.RB_RUN)
    run_boosted = calculate_match_play_estimate(state, OffensivePlayAction.RB_RUN)
    assert run_boosted.turnover_probability == run_base.turnover_probability


def _simulator_for_play(
    play: OffensivePlayAction,
    effects: tuple[FootballCoachUpgradeEffect, ...] = (),
    *,
    scheme: DefensiveSchemeAction | None = None,
    seed: int = 72,
) -> FootballMatchSimulator:
    copy = FootballCardCopy("human:play:1", play.value)
    state = _match_state(
        random_seed=seed,
        team_a_coach_upgrades=effects,
        current_drive_defensive_scheme=scheme or DefensiveSchemeAction.RB_RUN,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        team_a_offense_deck=FootballDeckState((copy,), hand=(copy,)),
    )
    return FootballMatchSimulator(state)


def test_play_clock_modifiers_round_and_preserve_incomplete_turnover_and_conversion_rules() -> None:
    faster = _effect(
        "faster",
        FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
        -0.10,
    )
    slower = _effect(
        "slower",
        FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
        0.10,
    )
    assert adjusted_offensive_play_clock_seconds(15, (faster,)) == 14
    assert adjusted_offensive_play_clock_seconds(15, (slower,)) == 17
    assert adjusted_offensive_play_clock_seconds(1, (faster,)) == 1
    assert adjusted_offensive_play_clock_seconds(20, (faster, slower)) == 20

    run = _simulator_for_play(OffensivePlayAction.RB_RUN, (faster,))
    run.rng.random = lambda: 0.99
    run.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    run_result = run.state.match_events[-1].play_result
    assert run_result is not None
    assert run_result.clock_seconds_used == adjusted_offensive_play_clock_seconds(
        OFFENSIVE_PLAY_CATALOG["rb_run"].clock_seconds, (faster,)
    )

    turnover = _simulator_for_play(OffensivePlayAction.RB_RUN, (faster,))
    rolls = iter((0.99, 0.0))
    turnover.rng.random = lambda: next(rolls)
    turnover.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    turnover_result = turnover.state.match_events[-1].play_result
    assert turnover_result is not None and turnover_result.turnover
    assert turnover_result.clock_seconds_used == adjusted_offensive_play_clock_seconds(
        OFFENSIVE_PLAY_CATALOG["rb_run"].clock_seconds, (faster,)
    )

    deep_copy = FootballCardCopy("human:play:deep", OffensivePlayAction.DEEP_PASS.value)
    incomplete_state = _match_state(
        team_a_coach_upgrades=(
            faster,
            _effect(
                "vertical",
                FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
                0.10,
                FootballCardFamily.DEEP_PASS,
            ),
        ),
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        team_a_offense_deck=FootballDeckState((deep_copy,), hand=(deep_copy,)),
    )
    incomplete = FootballMatchSimulator(incomplete_state)
    rolls = iter((0.99, 0.0))
    incomplete.rng.random = lambda: next(rolls)
    incomplete.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    incomplete_result = incomplete.state.match_events[-1].play_result
    assert incomplete_result is not None and incomplete_result.incomplete
    assert incomplete_result.clock_seconds_used == 5
    assert incomplete_result.yards_gained == 0.0

    interception_state = _match_state(
        team_a_coach_upgrades=(
            _effect(
                "vertical",
                FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
                0.10,
                FootballCardFamily.DEEP_PASS,
            ),
        ),
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        team_a_offense_deck=FootballDeckState((deep_copy,), hand=(deep_copy,)),
    )
    interception_estimate = calculate_match_play_estimate(
        interception_state, OffensivePlayAction.DEEP_PASS
    )
    interception_threshold = interception_estimate.incomplete_probability + (
        1.0 - interception_estimate.incomplete_probability
    ) * interception_estimate.turnover_probability
    interception = FootballMatchSimulator(interception_state)
    interception.rng.uniform = lambda _lower, _upper: 0.0
    interception.rng.random = lambda: (
        interception_estimate.incomplete_probability + interception_threshold
    ) / 2
    interception.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    interception_result = interception.state.match_events[-1].play_result
    assert interception_result is not None and interception_result.turnover
    assert interception_result.turnover_type is not None
    assert interception_result.yards_gained == 0.0

    conversion_state = _match_state(
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=2.0,
        offense_field_position=98.0,
        team_a_coach_upgrades=(faster,),
        awaited_action=FootballAwaitedAction.CONVERSION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        conversion_team=FootballTeamSide.TEAM_A,
        team_a_offense_deck=FootballDeckState((deep_copy,), hand=(deep_copy,)),
    )
    conversion = FootballMatchSimulator(conversion_state)
    conversion.rng.random = lambda: 0.99
    conversion.resolve_conversion(
        action=FootballConversionAction.TWO_POINT,
        play=OffensivePlayAction.DEEP_PASS,
    )
    conversion_event = next(
        event
        for event in conversion.state.match_events
        if event.description is not None and "Two-point" in event.description
    )
    assert conversion_event.clock_seconds_used == 0


@pytest.mark.parametrize(
    "upgrade_ids",
    (
        (),
        ("tempo_install",),
        ("huddle_up",),
        ("tempo_install", "huddle_up"),
    ),
)
def test_normal_play_clock_matches_live_upgrade_calculation(
    upgrade_ids: tuple[str, ...],
) -> None:
    upgrades = tuple(_coach_card(upgrade_id).coach_upgrade_effect for upgrade_id in upgrade_ids)
    simulator = _simulator_for_play(OffensivePlayAction.RB_RUN, upgrades)
    simulator.rng.random = lambda: 0.99
    simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = simulator.state.match_events[-1].play_result
    assert result is not None
    assert result.clock_seconds_used == adjusted_offensive_play_clock_seconds(
        OFFENSIVE_PLAY_CATALOG[OffensivePlayAction.RB_RUN.value].clock_seconds,
        upgrades,
    )


def test_field_goal_lab_is_conditional_on_an_unblocked_kick() -> None:
    upgrade = _coach_card("field_goal_lab").coach_upgrade_effect
    assert upgrade is not None
    state = _match_state(team_a_coach_upgrades=(upgrade,))
    distance = 42.0
    base_conditional = field_goal_success_probability(distance)
    upgraded_conditional = field_goal_success_probability(
        distance, upgrade.magnitude
    )
    base_overall = (1.0 - FIELD_GOAL_BLOCK_CHANCE) * base_conditional
    upgraded_overall = (1.0 - FIELD_GOAL_BLOCK_CHANCE) * upgraded_conditional
    assert upgraded_conditional == pytest.approx(base_conditional + 0.05)
    assert upgraded_overall == pytest.approx(
        (1.0 - FIELD_GOAL_BLOCK_CHANCE) * (base_conditional + 0.05)
    )
    assert upgraded_overall - base_overall == pytest.approx(
        (1.0 - FIELD_GOAL_BLOCK_CHANCE) * 0.05
    )
    assert upgraded_overall - base_overall != pytest.approx(0.05)
    assert blocked_kick_probability(
        state, FootballTeamSide.TEAM_A, FIELD_GOAL_BLOCK_CHANCE
    ) == FIELD_GOAL_BLOCK_CHANCE
    assert field_goal_success_probability(17.0, upgrade.magnitude) == 1.0


def test_simulation_and_estimate_share_family_effects_and_field_goal_probability() -> None:
    vertical = _effect(
        "vertical",
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        0.10,
        FootballCardFamily.DEEP_PASS,
    )
    simulator = _simulator_for_play(
        OffensivePlayAction.DEEP_PASS,
        (vertical,),
        seed=75,
    )
    before = calculate_match_play_estimate(
        simulator.state, OffensivePlayAction.DEEP_PASS
    )
    simulator.rng.random = lambda: 0.99
    simulator.rng.uniform = lambda _low, _high: 0.0
    simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    result = simulator.state.match_events[-1].play_result
    assert result is not None
    assert result.yards_gained == pytest.approx(before.yards_on_success)

    field_goal = _effect(
        "field_goal",
        FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS,
        0.05,
    )
    state = _match_state(team_a_coach_upgrades=(field_goal,))
    distance = field_goal_distance_for_position(30.0)
    boosted = field_goal_success_probability_for_team(
        state, FootballTeamSide.TEAM_A, distance
    )
    base = field_goal_success_probability_for_team(
        replace(state, team_a_coach_upgrades=()),
        FootballTeamSide.TEAM_A,
        distance,
    )
    assert boosted == pytest.approx(min(1.0, base + 0.05))
    assert field_goal_success_probability_for_team(
        state, FootballTeamSide.TEAM_B, distance
    ) == base

    field_goal_state = replace(
        state,
        down=4,
        offense_field_position=60.0,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )
    distance = field_goal_distance_for_position(60.0)
    base_probability = field_goal_success_probability_for_team(
        replace(field_goal_state, team_a_coach_upgrades=()),
        FootballTeamSide.TEAM_A,
        distance,
    )
    roll = base_probability + 0.02
    upgraded_simulator = FootballMatchSimulator(field_goal_state)
    upgraded_rolls = iter((0.5, roll, 0.99, 0.99))
    upgraded_simulator.rng.random = lambda: next(upgraded_rolls)
    upgraded_simulator.rng.gauss = lambda mean, _deviation: mean
    upgraded_simulator.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    upgraded_attempt = next(
        event
        for event in upgraded_simulator.state.match_events
        if event.action is FootballFourthDownAction.FIELD_GOAL
    )
    assert upgraded_attempt.points_scored == 3

    baseline_simulator = FootballMatchSimulator(
        replace(field_goal_state, team_a_coach_upgrades=())
    )
    baseline_rolls = iter((0.5, roll))
    baseline_simulator.rng.random = lambda: next(baseline_rolls)
    baseline_simulator.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    baseline_attempt = next(
        event
        for event in baseline_simulator.state.match_events
        if event.action is FootballFourthDownAction.FIELD_GOAL
    )
    assert baseline_attempt.points_scored == 0


def test_kick_block_risk_and_return_yard_effects_apply_only_to_the_human_team() -> None:
    block_reduction = _effect(
        "blocks",
        FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION,
        0.25,
    )
    punt_return = _effect(
        "punt_return",
        FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS,
        2,
    )
    kickoff_return = _effect(
        "kickoff_return",
        FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
        2,
    )
    effects = (block_reduction, punt_return, kickoff_return)
    state = _match_state(team_a_coach_upgrades=effects)
    assert blocked_kick_probability(state, FootballTeamSide.TEAM_A, 0.007) == pytest.approx(
        0.007 * 0.75
    )
    assert blocked_kick_probability(state, FootballTeamSide.TEAM_B, 0.007) == 0.007

    kicking_state = _match_state(
        possession=FootballTeamSide.TEAM_A,
        down=4,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_coach_upgrades=(block_reduction,),
    )
    protected_punt = FootballMatchSimulator(kicking_state)
    protected_punt.rng.random = lambda: 0.006
    protected_punt.rng.gauss = lambda mean, _deviation: mean
    protected_punt.resolve_fourth_down(FootballFourthDownAction.PUNT)
    protected_event = protected_punt.state.match_events[-1]
    assert not protected_event.blocked

    baseline_punt = FootballMatchSimulator(
        replace(kicking_state, team_a_coach_upgrades=())
    )
    baseline_punt.rng.random = lambda: 0.006
    baseline_punt.rng.gauss = lambda mean, _deviation: mean
    baseline_punt.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert baseline_punt.state.match_events[-1].blocked

    punt_state = _match_state(
        possession=FootballTeamSide.TEAM_B,
        down=4,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_coach_upgrades=effects,
    )
    punt = FootballMatchSimulator(punt_state)
    punt_rolls = iter((0.99, 0.0))
    punt.rng.random = lambda: next(punt_rolls)
    punt.rng.gauss = lambda mean, _deviation: mean
    punt.resolve_fourth_down(FootballFourthDownAction.PUNT)
    punt_event = punt.state.match_events[-1]
    assert punt_event.return_yards == 10.0
    assert not punt_event.blocked

    kickoff = FootballMatchSimulator(state)
    rolls = iter((0.99, 0.99))
    kickoff.rng.random = lambda: next(rolls)
    kickoff.rng.gauss = lambda mean, _deviation: mean
    kickoff.state = kickoff._resolve_kickoff(
        kickoff.state, FootballTeamSide.TEAM_B
    )
    kickoff_event = kickoff.state.match_events[-1]
    assert kickoff_event.return_yards == 27.0


@pytest.mark.parametrize("with_upgrade", (False, True))
@pytest.mark.parametrize(
    ("raw_field_position", "expected_return_yards", "expected_field_position"),
    (
        (98.9, 98.9, 98.9),
        (100.0, 99.0, 99.0),
        (101.0, 99.0, 99.0),
    ),
)
def test_kickoff_returns_stop_before_goal_line(
    raw_field_position: float,
    expected_return_yards: float,
    expected_field_position: float,
    with_upgrade: bool,
) -> None:
    upgrade = _coach_card("kickoff_return_lane").coach_upgrade_effect
    assert upgrade is not None
    bonus = upgrade.magnitude if with_upgrade else 0.0
    state = _match_state(
        team_b_coach_upgrades=(upgrade,) if with_upgrade else (),
    )
    simulator = FootballMatchSimulator(state)
    simulator.rng.random = iter((0.99, 0.99)).__next__
    simulator.rng.gauss = lambda _mean, _deviation: raw_field_position - bonus

    result = simulator._resolve_kickoff(state, FootballTeamSide.TEAM_A)
    event = result.match_events[-1]

    assert event.points_scored == 0
    assert event.scoring_team is None
    assert event.description == f"Kickoff returned {expected_return_yards:.1f} yards"
    assert event.return_yards == pytest.approx(expected_return_yards)
    assert result.team_a_score == result.team_b_score == 0
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == pytest.approx(expected_field_position)
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


@pytest.mark.parametrize("with_upgrade", (False, True))
@pytest.mark.parametrize(
    ("raw_field_position", "expected_return_yards", "expected_field_position"),
    (
        (98.9, 13.9, 98.9),
        (100.0, 14.0, 99.0),
        (101.0, 14.0, 99.0),
    ),
)
def test_punt_returns_stop_before_goal_line(
    raw_field_position: float,
    expected_return_yards: float,
    expected_field_position: float,
    with_upgrade: bool,
) -> None:
    upgrade = _coach_card("punt_return_lane").coach_upgrade_effect
    assert upgrade is not None
    bonus = upgrade.magnitude if with_upgrade else 0.0
    state = _match_state(
        down=4,
        offense_field_position=0.0,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_b_coach_upgrades=(upgrade,) if with_upgrade else (),
    )
    simulator = FootballMatchSimulator(state)
    simulator.rng.random = iter((0.99, 0.0)).__next__
    gauss_values = iter((15.0, raw_field_position - 85.0 - bonus))
    simulator.rng.gauss = lambda _mean, _deviation: next(gauss_values)

    result = simulator.resolve_fourth_down(FootballFourthDownAction.PUNT)
    event = result.match_events[-1]

    assert event.points_scored == 0
    assert event.scoring_team is None
    assert event.description == (
        f"Punt 15.0 yards, returned {expected_return_yards:.1f}"
    )
    assert event.return_yards == pytest.approx(expected_return_yards)
    assert result.team_a_score == result.team_b_score == 0
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == pytest.approx(expected_field_position)
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


def _controller_with_bye(shop_catalogs=None) -> FootballGameController:
    return FootballGameController(
        "Human Team",
        difficulty=FootballAIDifficulty.EASY,
        builder_seed=31,
        shop_seed=37,
        ai_seed=41,
        match_seed=43,
        shop_catalogs=shop_catalogs
        or {
            FootballShopSection.COACH_UPGRADES: (_coach_card("bye_week"),)
        },
    )


def _draft_to_shop(controller: FootballGameController) -> None:
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        controller.choose_player(position, 0)


def _force_wins(monkeypatch) -> None:
    def complete(simulator, _play):
        state = simulator.state
        result = FootballMatchResult(7, 0, FootballTeamSide.TEAM_A, True)
        simulator.state = replace(
            state,
            team_a_score=7,
            team_b_score=0,
            status=FootballMatchStatus.COMPLETED,
            awaited_action=None,
            current_drive_defensive_scheme=None,
            conversion_team=None,
            final_result=result,
        )
        return simulator.state

    monkeypatch.setattr(FootballMatchSimulator, "resolve_offensive_play", complete)


def _finish_game_as_win(controller: FootballGameController) -> None:
    assert controller.state.human_decision is not None
    controller.finish_shop()
    controller.choose_offensive_play(OffensivePlayAction.RB_RUN)
    assert controller.state.phase in (
        FootballRunPhase.READY_FOR_NEXT_GAME,
        FootballRunPhase.PLAYOFFS,
    )


def test_bye_week_skips_a_game_without_match_or_ai_rng_and_run_finishes_after_nine(
    monkeypatch,
) -> None:
    _force_wins(monkeypatch)
    controller = _controller_with_bye()
    _draft_to_shop(controller)
    _finish_game_as_win(controller)
    for _game in (2, 3):
        controller.enter_next_shop()
        _finish_game_as_win(controller)

    controller.enter_next_shop()
    assert controller.state.game_number == 4
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    match_rng_before = controller._match_seed_rng.getstate()
    ai_rng_before = controller._ai._rng.getstate()
    prior_match = controller.state.match
    skipped = controller.buy_shop_card(
        FootballShopSection.COACH_UPGRADES, "bye_week"
    )

    assert skipped.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert skipped.game_number == 5
    assert skipped.games_played == 3
    assert skipped.skipped_games == (4,)
    assert (skipped.wins, skipped.losses) == (3, 0)
    assert skipped.shop is not None and skipped.shop.remaining_ap == ACTION_POINT_BUDGET
    assert skipped.match is prior_match
    assert "scheduled game 4" in (skipped.transition_message or "")
    assert controller._match_seed_rng.getstate() == match_rng_before
    assert controller._ai._rng.getstate() == ai_rng_before
    assert skipped.shop.section(FootballShopSection.COACH_UPGRADES).slots[0].card is None

    for game_number in range(5, 11):
        assert controller.state.game_number == game_number
        _finish_game_as_win(controller)
        if game_number < 10:
            controller.enter_next_shop()
    final = controller.state
    assert final.phase is FootballRunPhase.PLAYOFFS
    assert final.games_played == 9
    assert (final.wins, final.losses) == (9, 0)
    assert final.skipped_games == (4,)
    assert len(final.match.match_events) > 0


def test_bye_week_on_game_ten_reaches_marker_without_a_fake_result(monkeypatch) -> None:
    _force_wins(monkeypatch)
    controller = _controller_with_bye()
    _draft_to_shop(controller)
    _finish_game_as_win(controller)

    for game_number in range(2, 10):
        controller.enter_next_shop()
        if game_number == 4:
            controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
        _finish_game_as_win(controller)
    controller.enter_next_shop()
    assert controller.state.game_number == 10
    match_rng_before = controller._match_seed_rng.getstate()
    ai_rng_before = controller._ai._rng.getstate()
    prior_match = controller.state.match

    final = controller.buy_shop_card(
        FootballShopSection.COACH_UPGRADES, "bye_week"
    )
    assert final.phase is FootballRunPhase.PLAYOFFS
    assert final.game_number == 10
    assert final.skipped_games == (10,)
    assert final.games_played == 9
    assert (final.wins, final.losses) == (9, 0)
    assert final.match is prior_match
    assert final.match is not None and final.match.final_result is not None
    assert "without a match result" in (final.transition_message or "")
    assert controller._match_seed_rng.getstate() == match_rng_before
    assert controller._ai._rng.getstate() == ai_rng_before


def test_purchased_upgrade_reaches_only_human_match_state_and_new_runs_reset(
    monkeypatch,
) -> None:
    _force_wins(monkeypatch)
    catalogs = {
        FootballShopSection.COACH_UPGRADES: (_coach_card("two_minute_drill"),)
    }
    controller = _controller_with_bye(catalogs)
    _draft_to_shop(controller)
    _finish_game_as_win(controller)
    for _game in (2, 3):
        controller.enter_next_shop()
        _finish_game_as_win(controller)
    controller.enter_next_shop()
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    controller.buy_shop_card(
        FootballShopSection.COACH_UPGRADES, "two_minute_drill"
    )
    match_state = controller.finish_shop().match
    assert match_state is not None
    assert tuple(
        upgrade.upgrade_id for upgrade in match_state.team_a_coach_upgrades
    ) == ("two_minute_drill",)
    assert match_state.team_b_coach_upgrades == ()

    fresh_run = _controller_with_bye(catalogs)
    _draft_to_shop(fresh_run)
    assert fresh_run.state.shop is not None
    assert fresh_run.state.shop.owned_coach_upgrades == ()
    assert fresh_run.state.shop.future_shop_ap_bonus == 0
