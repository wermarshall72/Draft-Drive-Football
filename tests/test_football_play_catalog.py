from __future__ import annotations

import random

import pytest

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    OFFENSIVE_PLAY_FAMILIES,
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCardFamily,
    FootballCoach,
    FootballConversionAction,
    FootballDeckState,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
    matchup_for_play,
    matchup_for_scheme,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    STARTING_DEFENSIVE_ACTIONS,
    STARTING_OFFENSIVE_ACTIONS,
)
from src.engine.football_shop import (
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
)
from src.engine.football_simulator import (
    FootballMatchSimulator,
    calculate_play_estimate,
    calculate_standardized_play_estimate,
)


class CenteredRng(random.Random):
    def random(self) -> float:
        return 0.99

    def uniform(self, low: float, high: float) -> float:
        return (low + high) / 2


def _roster(name: str, *, power: float = 10.0) -> FootballRoster:
    return FootballRoster(
        team_name=name,
        players={
            position: FootballPlayer(
                name=f"{name} {position.value}",
                position=position,
                power=power,
                volatility=0.0,
                stamina=1.0,
            )
            for position in FootballPosition
        },
        coach=FootballCoach(f"{name} Coach"),
        special_teams=FootballSpecialTeams(f"{name} Special Teams"),
    )


def _shop_card(definition, *, kind: str) -> FootballShopCard:
    return FootballShopCard(
        card_id=f"{kind}:{definition.card_id}",
        name=definition.name,
        description=definition.description,
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        football_card=definition,
    )


def _match_state(**overrides) -> FootballMatchState:
    values = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
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


def test_every_named_card_has_stable_family_identity_and_family_matchups() -> None:
    assert set(OFFENSIVE_PLAY_CATALOG) == {action.value for action in OffensivePlayAction}
    assert set(DEFENSIVE_SCHEME_CATALOG) == {
        action.value for action in DefensiveSchemeAction
    }
    assert len(OFFENSIVE_PLAY_CATALOG) == len(set(OFFENSIVE_PLAY_CATALOG))
    assert len(DEFENSIVE_SCHEME_CATALOG) == len(set(DEFENSIVE_SCHEME_CATALOG))
    assert set(OFFENSIVE_PLAY_FAMILIES) == set(OffensivePlayAction)
    assert set(DEFENSIVE_SCHEME_FAMILIES) == set(DefensiveSchemeAction)

    for action, definition in (
        (action, OFFENSIVE_PLAY_CATALOG[action.value])
        for action in OffensivePlayAction
    ):
        contributors, _ = matchup_for_play(action)
        assert definition.action is action
        assert definition.card_id == action.value
        assert definition.family is OFFENSIVE_PLAY_FAMILIES[action]
        assert definition.contributors == contributors

    for action, definition in (
        (action, DEFENSIVE_SCHEME_CATALOG[action.value])
        for action in DefensiveSchemeAction
    ):
        contributors, counters = matchup_for_scheme(action)
        assert definition.action is action
        assert definition.card_id == action.value
        assert definition.family is DEFENSIVE_SCHEME_FAMILIES[action]
        assert definition.contributors == contributors
        assert definition.counters == counters
        assert {
            OFFENSIVE_PLAY_FAMILIES[play] for play in definition.counters
        } == {definition.family}

    for family in FootballCardFamily:
        assert any(
            definition.family is family
            for definition in OFFENSIVE_PLAY_CATALOG.values()
        )
        assert any(
            definition.family is family
            for definition in DEFENSIVE_SCHEME_CATALOG.values()
        )


def test_migrated_ids_keep_ownership_identity_and_receive_single_family_rules() -> None:
    assert {"qb_sneak", "jet_sweep", "quick_out"} <= set(OFFENSIVE_PLAY_CATALOG)
    assert {
        "goal_line_front",
        "cover_two_shell",
        "fire_zone_blitz",
    } <= set(DEFENSIVE_SCHEME_CATALOG)
    assert OFFENSIVE_PLAY_CATALOG["qb_sneak"].family is FootballCardFamily.RB_RUN
    assert OFFENSIVE_PLAY_CATALOG["jet_sweep"].family is FootballCardFamily.RB_RUN
    assert OFFENSIVE_PLAY_CATALOG["quick_out"].family is FootballCardFamily.SHORT_PASS
    assert DEFENSIVE_SCHEME_CATALOG["goal_line_front"].family is FootballCardFamily.RB_RUN
    assert DEFENSIVE_SCHEME_CATALOG["cover_two_shell"].family is FootballCardFamily.DEEP_PASS
    assert DEFENSIVE_SCHEME_CATALOG["fire_zone_blitz"].family is FootballCardFamily.MEDIUM_PASS
    assert DEFENSIVE_SCHEME_CATALOG["fire_zone_blitz"].counters == frozenset(
        play
        for play, family in OFFENSIVE_PLAY_FAMILIES.items()
        if family is FootballCardFamily.MEDIUM_PASS
    )


def test_bootleg_keeper_description_is_a_pass_without_changing_card_mechanics() -> None:
    definition = OFFENSIVE_PLAY_CATALOG["bootleg_keeper"]
    estimate = calculate_standardized_play_estimate(
        OffensivePlayAction.BOOTLEG_KEEPER
    )
    play_action_estimate = calculate_standardized_play_estimate(
        OffensivePlayAction.PA_PASS
    )

    assert definition.card_id == "bootleg_keeper"
    assert definition.name == "Bootleg Keeper"
    assert "throws" in definition.description.lower()
    assert definition.family is FootballCardFamily.PA_PASS
    assert definition.contributors == matchup_for_play(
        OffensivePlayAction.PA_PASS
    )[0]
    assert definition.base_yards == 6.0
    assert definition.clock_seconds == 30
    assert estimate.family is FootballCardFamily.PA_PASS
    assert estimate.matchup == play_action_estimate.matchup
    assert estimate.incomplete_probability == play_action_estimate.incomplete_probability
    assert estimate.turnover_probability == play_action_estimate.turnover_probability
    assert estimate.expected_yards > play_action_estimate.expected_yards
    assert estimate.incomplete_probability > 0
    assert estimate.turnover_probability > 0


def test_all_play_and_scheme_catalog_offers_are_common_without_changing_player_rarity() -> None:
    shop = FootballShop(_roster("Catalog"), seed=23)
    playbook_cards = tuple(
        card
        for card in shop._catalogs[FootballShopSection.PLAYS_SCHEMES]
        if card.football_card is not None
    )

    assert len(playbook_cards) == (
        len(OFFENSIVE_PLAY_CATALOG) + len(DEFENSIVE_SCHEME_CATALOG)
    )
    assert all(card.rarity is FootballShopRarity.COMMON for card in playbook_cards)
    assert all(card.cost == 2 for card in playbook_cards)
    assert any(
        card.rarity is FootballShopRarity.UNCOMMON
        for card in shop._catalogs[FootballShopSection.PLAYER_UPGRADES]
    )


def test_standardized_expected_yardage_hierarchy_covers_every_variant() -> None:
    expected = {
        definition.action: calculate_standardized_play_estimate(
            definition.action
        ).expected_yards
        for definition in OFFENSIVE_PLAY_CATALOG.values()
    }
    by_family = {
        family: tuple(
            expected[action]
            for action, play_family in OFFENSIVE_PLAY_FAMILIES.items()
            if play_family is family
        )
        for family in FootballCardFamily
    }

    assert min(by_family[FootballCardFamily.DEEP_PASS]) > max(
        by_family[FootballCardFamily.MEDIUM_PASS]
    )
    assert min(by_family[FootballCardFamily.MEDIUM_PASS]) > max(
        by_family[FootballCardFamily.SHORT_PASS]
    )
    assert max(by_family[FootballCardFamily.RB_RUN]) < min(
        by_family[FootballCardFamily.SCREEN_PASS]
    )
    assert abs(
        sum(by_family[FootballCardFamily.SCREEN_PASS])
        / len(by_family[FootballCardFamily.SCREEN_PASS])
        - sum(by_family[FootballCardFamily.SHORT_PASS])
        / len(by_family[FootballCardFamily.SHORT_PASS])
    ) < 2.0
    assert abs(
        sum(by_family[FootballCardFamily.PA_PASS])
        / len(by_family[FootballCardFamily.PA_PASS])
        - sum(by_family[FootballCardFamily.MEDIUM_PASS])
        / len(by_family[FootballCardFamily.MEDIUM_PASS])
    ) < 2.0

    for action in OffensivePlayAction:
        estimate = calculate_standardized_play_estimate(action)
        if estimate.family is FootballCardFamily.RB_RUN:
            lower = estimate.yards_on_success - estimate.yardage_spread
            upper = estimate.yards_on_success + estimate.yardage_spread
            fumble_yards = (
                estimate.yards_on_success
                if upper <= 0
                else 0.0
                if lower >= 0
                else -(lower * lower) / (4.0 * estimate.yardage_spread)
            )
            expected_actual_gain = (
                estimate.yards_on_success * (1.0 - estimate.turnover_probability)
                + fumble_yards * estimate.turnover_probability
            )
        else:
            expected_actual_gain = (
                estimate.yards_on_success
                * (1.0 - estimate.incomplete_probability)
                * (1.0 - estimate.turnover_probability)
            )
        assert estimate.expected_yards == pytest.approx(expected_actual_gain)


def test_standardized_comparison_ranges_allow_screen_and_play_action_overlap() -> None:
    estimates = {
        action: calculate_standardized_play_estimate(action)
        for action in OffensivePlayAction
    }

    def successful_range(family: FootballCardFamily) -> tuple[float, float]:
        values = [
            estimates[action]
            for action, card_family in OFFENSIVE_PLAY_FAMILIES.items()
            if card_family is family
        ]
        return (
            min(item.yards_on_success - item.yardage_spread for item in values),
            max(item.yards_on_success + item.yardage_spread for item in values),
        )

    for left, right in (
        (FootballCardFamily.SCREEN_PASS, FootballCardFamily.SHORT_PASS),
        (FootballCardFamily.PA_PASS, FootballCardFamily.MEDIUM_PASS),
    ):
        left_low, left_high = successful_range(left)
        right_low, right_high = successful_range(right)
        assert max(left_low, right_low) <= min(left_high, right_high)


def test_variants_keep_yardage_and_clock_through_purchase_draw_resolution_and_reshuffle() -> None:
    variants = (
        OFFENSIVE_PLAY_CATALOG["quick_out"],
        OFFENSIVE_PLAY_CATALOG["slot_slant"],
    )
    scheme_variants = (
        DEFENSIVE_SCHEME_CATALOG["cover_two_shell"],
        DEFENSIVE_SCHEME_CATALOG["quarters_coverage"],
    )
    offered_cards = tuple(
        _shop_card(definition, kind=kind)
        for kind, definitions in (
            ("play", variants),
            ("scheme", scheme_variants),
        )
        for definition in definitions
    )
    shop = FootballShop(
        _roster("Shop"),
        seed=29,
        catalogs={
            FootballShopSection.PLAYS_SCHEMES: offered_cards
        },
    )

    for card in offered_cards:
        shop.buy_card(
            FootballShopSection.PLAYS_SCHEMES,
            card.card_id,
        )
    copies = tuple(
        card
        for card in shop.offensive_deck
        if card.card_id in {definition.card_id for definition in variants}
    )
    assert {card.card_id for card in copies} == {
        definition.card_id for definition in variants
    }
    assert len(shop.offensive_deck) == len(STARTING_OFFENSIVE_ACTIONS) + 2
    assert len(shop.defensive_deck) == len(STARTING_DEFENSIVE_ACTIONS) + 2
    assert {
        card.card_id for card in shop.defensive_deck
    } >= {definition.card_id for definition in scheme_variants}

    first, second = (
        next(card for card in copies if card.card_id == definition.card_id)
        for definition in variants
    )
    other_cards = tuple(
        card for card in shop.offensive_deck if card not in (first, second)
    )
    deck = FootballDeckState(
        owned=shop.offensive_deck,
        hand=(first,),
        draw_pile=(second,),
        discard_pile=other_cards,
    )
    defense_card = next(
        card
        for card in shop.defensive_deck
        if card.card_id == scheme_variants[0].card_id
    )
    other_scheme = next(
        card
        for card in shop.defensive_deck
        if card.card_id == scheme_variants[1].card_id
    )
    defense_deck = FootballDeckState(
        owned=shop.defensive_deck,
        hand=(defense_card,),
        draw_pile=(other_scheme,),
        discard_pile=tuple(
            card
            for card in shop.defensive_deck
            if card not in (defense_card, other_scheme)
        ),
    )
    simulator = FootballMatchSimulator(
        _match_state(
            team_a_offense_deck=deck,
            team_b_defense_deck=defense_deck,
        )
    )
    simulator.rng = CenteredRng()
    scheme_state = simulator.select_defensive_scheme(defense_card.copy_id)
    assert scheme_state.current_drive_defensive_scheme is scheme_variants[0].action
    assert scheme_state.match_events[-1].card_id == scheme_variants[0].card_id
    assert scheme_state.match_events[-1].card_copy_id == defense_card.copy_id

    for card, definition in zip((first, second), variants, strict=True):
        if card is second:
            before_reshuffle = simulator.state.team_a_offense_deck
            assert before_reshuffle is not None
            assert not before_reshuffle.draw_pile
            assert first in before_reshuffle.discard_pile
        state = simulator.resolve_offensive_play(card.copy_id)
        event = state.match_events[-1]
        assert event.action is definition.action
        assert event.card_id == definition.card_id
        assert event.card_copy_id == card.copy_id
        assert event.play_result is not None
        assert event.play_result.offensive_play is definition.action
        assert event.play_result.clock_seconds_used == definition.clock_seconds
        assert event.clock_seconds_used == definition.clock_seconds
        assert state.team_a_offense_deck is not None
        zones = (
            state.team_a_offense_deck.hand
            + state.team_a_offense_deck.draw_pile
            + state.team_a_offense_deck.discard_pile
        )
        assert sum(zone_card == card for zone_card in zones) == 1
        if card is first:
            assert second in state.team_a_offense_deck.hand
            assert first in state.team_a_offense_deck.discard_pile
        else:
            assert state.team_a_offense_deck.draw_pile


def test_selected_defensive_variant_stays_active_for_the_drive_and_is_recorded() -> None:
    base = FootballCardCopy("defense:base", "deep_pass")
    variant = FootballCardCopy("defense:variant", "cover_two_shell")
    defensive_deck = FootballDeckState(
        owned=(base, variant),
        hand=(variant,),
        draw_pile=(base,),
    )
    simulator = FootballMatchSimulator(
        _match_state(
            team_b_defense_deck=defensive_deck,
            current_drive_defensive_scheme=None,
        )
    )

    state = simulator.select_defensive_scheme(variant.copy_id)
    event = state.match_events[-1]
    assert state.current_drive_defensive_scheme is DefensiveSchemeAction.COVER_TWO_SHELL
    assert event.card_id == variant.card_id
    assert event.card_copy_id == variant.copy_id
    assert state.team_b_defense_deck is not None
    assert variant in state.team_b_defense_deck.discard_pile


def test_two_point_attempt_records_selected_variant_and_remains_untimed() -> None:
    first = FootballCardCopy("conversion:first", "go_route")
    conversion_card = FootballCardCopy("conversion:next", "deep_dig")
    deck = FootballDeckState(
        owned=(first, conversion_card),
        hand=(first,),
        draw_pile=(conversion_card,),
    )
    simulator = FootballMatchSimulator(
        _match_state(
            offense_field_position=99.0,
            yards_to_go=1.0,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=deck,
        )
    )
    simulator.rng = CenteredRng()

    touchdown = simulator.resolve_offensive_play(first.copy_id)
    assert touchdown.awaited_action is FootballAwaitedAction.CONVERSION
    before_conversion_clock = touchdown.game_clock_seconds
    assert touchdown.team_a_offense_deck is not None
    assert conversion_card in touchdown.team_a_offense_deck.hand

    converted = simulator.resolve_conversion(
        FootballConversionAction.TWO_POINT,
        conversion_card.copy_id,
    )
    event = next(
        event
        for event in reversed(converted.match_events)
        if event.action.value == "two_point"
    )
    assert event.card_id == "deep_dig"
    assert event.card_copy_id == conversion_card.copy_id
    assert event.clock_seconds_used == 0
    assert event.game_clock_seconds == before_conversion_clock
    assert event.description is not None and "deep dig" in event.description


def test_contextual_matchups_still_change_the_same_variant_estimate() -> None:
    play = OffensivePlayAction.SLOT_SLANT
    offense = _roster("Offense")
    defense = _roster("Defense")
    weak_short_defense = _roster("Weak Defense", power=5.0)

    open_estimate = calculate_play_estimate(
        offense,
        defense,
        play,
        DefensiveSchemeAction.RB_RUN,
    )
    countered_estimate = calculate_play_estimate(
        offense,
        defense,
        play,
        DefensiveSchemeAction.SHORT_PASS,
    )
    weak_defense_estimate = calculate_play_estimate(
        offense,
        weak_short_defense,
        play,
        DefensiveSchemeAction.RB_RUN,
    )

    assert not open_estimate.matchup.scheme_matches_play
    assert countered_estimate.matchup.scheme_matches_play
    assert open_estimate.yards_on_success != countered_estimate.yards_on_success
    assert weak_defense_estimate.yards_on_success > open_estimate.yards_on_success
