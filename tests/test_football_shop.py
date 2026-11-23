from dataclasses import replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_shop import (
    ACTION_POINT_BUDGET,
    CARD_REMOVAL_COST,
    COACH_UPGRADE_CATALOG,
    MIN_PLAYBOOK_DECK_SIZE,
    PLAYER_UPGRADE_CATALOG,
    PLAY_SCHEME_RARITY_WEIGHTS,
    RARITY_WEIGHTS,
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballUpgrade,
    FootballUpgradeDuration,
    FootballUpgradeStat,
    _player_upgrade_catalog,
    apply_player_upgrade,
    apply_player_upgrades,
    player_upgrade_effect_text,
)
from src.engine.football_coaches import COACH_PAIR_OFFERS
from src.engine.football_simulator import (
    FootballMatchSimulator, calculate_matchup_power, calculate_play_estimate,
)
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


class _FixedShopRng(random.Random):
    def __init__(self, roll: float) -> None:
        super().__init__(0)
        self.roll = roll

    def random(self) -> float:
        super().random()
        return self.roll


class _SequenceShopRng(random.Random):
    def __init__(self, rolls: tuple[float, ...]) -> None:
        super().__init__(0)
        self.rolls = iter(rolls)

    def random(self) -> float:
        super().random()
        return next(self.rolls)

    def choice(self, sequence):
        return sequence[0]


def test_complete_player_upgrade_catalog_has_exact_metadata_and_effects() -> None:
    cards = PLAYER_UPGRADE_CATALOG
    names = {
        FootballPosition.QB: "QB", FootballPosition.RB: "RB", FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line", FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebacker", FootballPosition.CORNERBACKS: "Cornerback",
        FootballPosition.SAFETIES: "Safety",
    }
    assert len(cards) == len({card.card_id for card in cards}) == 192
    combinations = set()
    for card in cards:
        upgrade = card.upgrade
        assert upgrade is not None
        key = (upgrade.position, upgrade.stat, upgrade.rarity, upgrade.duration)
        combinations.add(key)
        rank = list(FootballShopRarity).index(upgrade.rarity) + 1
        factor = 2 if upgrade.duration is FootballUpgradeDuration.TEMPORARY else 1
        unit = {FootballUpgradeStat.POWER: 1, FootballUpgradeStat.STAMINA: 0.05,
                FootballUpgradeStat.VOLATILITY: 0.01}[upgrade.stat]
        assert upgrade.amount == pytest.approx(rank * factor * unit)
        assert card.cost == (2 if factor == 2 else 3)
        assert upgrade.duration.value.title() in card.name
        assert upgrade.rarity.value.replace("_", " ").title() in card.name
        assert names[upgrade.position] in card.name
        assert upgrade.stat.value.title() in card.name
        assert player_upgrade_effect_text(upgrade.stat, upgrade.amount) in card.description
        assert f"{card.cost} AP" in card.description
        assert card.eligible(_roster(stamina=1.0))
    assert len(combinations) == 8 * 3 * 4 * 2


def test_player_catalog_offer_rarity_distribution() -> None:
    counts = {rarity: 0 for rarity in FootballShopRarity}
    for seed in range(1000):
        shop = FootballShop(_roster(), seed)
        counts[shop.offer[0].rarity] += 1
        assert len({upgrade.upgrade_id for upgrade in shop.offer}) == 3
    for rarity, weight in RARITY_WEIGHTS.items():
        assert abs(counts[rarity] - weight * 10) < 70


@pytest.mark.parametrize("duration", list(FootballUpgradeDuration))
@pytest.mark.parametrize("stat", list(FootballUpgradeStat))
def test_repeat_after_reroll_stacks_and_clamps(duration, stat) -> None:
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is stat
                and card.upgrade.rarity is FootballShopRarity.VERY_RARE
                and card.upgrade.duration is duration)
    original = _roster(stamina=0.75)
    shop = FootballShop(original, 11, catalogs={FootballShopSection.PLAYER_UPGRADES: (card,)})
    for purchase in range(3):
        slots = shop.state.section(FootballShopSection.PLAYER_UPGRADES).slots
        assert [slot.card for slot in slots[:3]] == [card, None, None]
        shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
        if purchase < 2:
            shop.move_to_next_day()
    assert len(shop.purchased_upgrades) == 3
    permanent = shop.roster.players[FootballPosition.QB]
    effective = shop.match_roster().players[FootballPosition.QB]
    target = permanent if duration is FootballUpgradeDuration.PERMANENT else effective
    if duration is FootballUpgradeDuration.TEMPORARY:
        assert permanent == original.players[FootballPosition.QB]
        assert len(shop.state.pending_player_upgrades) == 3
    if stat is FootballUpgradeStat.POWER:
        assert target.power == pytest.approx(10 + 3 * card.upgrade.amount)
        assert target.power > 20
    elif stat is FootballUpgradeStat.STAMINA:
        assert target.stamina == 1
    else:
        assert target.volatility == pytest.approx(max(0, 0.2 - 3 * card.upgrade.amount))


def test_temporary_stats_feed_match_power_fatigue_and_volatility() -> None:
    original = _roster()
    players = dict(original.players)
    players[FootballPosition.QB] = replace(players[FootballPosition.QB], volatility=0.10)
    original = replace(original, players=players)
    cards = tuple(card for card in PLAYER_UPGRADE_CATALOG
                  if card.upgrade.position is FootballPosition.QB
                  and card.upgrade.rarity is FootballShopRarity.COMMON
                  and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    shop = FootballShop(original, 11, catalogs={FootballShopSection.PLAYER_UPGRADES: cards})
    for card in cards:
        shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    effective = shop.match_roster()
    qb = effective.players[FootballPosition.QB]
    assert (qb.power, qb.stamina, qb.volatility) == pytest.approx((12.0, 0.85, 0.08))
    assert shop.roster == original
    defense = _roster("Defense")
    play, scheme = OffensivePlayAction.PA_PASS, DefensiveSchemeAction.SCREEN_PASS
    before = calculate_play_estimate(original, defense, play, scheme, prior_plays=30)
    after = calculate_play_estimate(effective, defense, play, scheme, prior_plays=30)
    assert after.yardage_spread < before.yardage_spread
    before_power = calculate_matchup_power(original, defense, play, scheme, prior_plays=30)
    after_power = calculate_matchup_power(effective, defense, play, scheme, prior_plays=30)
    assert after_power.offense > before_power.offense


def test_permanent_and_temporary_upgrades_combine_at_bounds() -> None:
    original = _roster(stamina=0.95)
    players = dict(original.players)
    players[FootballPosition.QB] = replace(
        players[FootballPosition.QB], power=1000, volatility=0.01,
    )
    original = replace(original, players=players)
    cards = tuple(card for card in PLAYER_UPGRADE_CATALOG
                  if card.upgrade.position is FootballPosition.QB
                  and card.upgrade.rarity is FootballShopRarity.COMMON
                  and card.upgrade.stat in (FootballUpgradeStat.STAMINA, FootballUpgradeStat.VOLATILITY))
    shop = FootballShop(original, 11, catalogs={FootballShopSection.PLAYER_UPGRADES: cards})
    for card in shop.state.section(FootballShopSection.PLAYER_UPGRADES).slots[:3]:
        shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card.card_id)
    qb = shop.match_roster().players[FootballPosition.QB]
    assert qb.stamina == 1.0 and qb.volatility == 0.0
    power = next(card for card in PLAYER_UPGRADE_CATALOG
                 if card.upgrade.position is FootballPosition.QB
                 and card.upgrade.stat is FootballUpgradeStat.POWER
                 and card.upgrade.duration is FootballUpgradeDuration.PERMANENT
                 and card.upgrade.rarity is FootballShopRarity.VERY_RARE)
    high_power = power.effect(original).players[FootballPosition.QB].power
    assert high_power == 1004


@pytest.mark.parametrize(
    ("stat", "initial", "partial", "permanent", "cap"),
    [
        (FootballUpgradeStat.STAMINA, 0.94, 0.01, 0.01, 1.0),
        (FootballUpgradeStat.VOLATILITY, 0.025, -0.015, -0.01, 0.0),
    ],
)
def test_projection_tracks_partial_and_zero_changes_across_scopes(
    stat, initial, partial, permanent, cap
) -> None:
    position = FootballPosition.QB
    roster = _roster()
    player = replace(roster.players[position], **{stat.value: initial})
    roster = replace(roster, players={**roster.players, position: player})
    cards = {
        duration: next(card for card in PLAYER_UPGRADE_CATALOG
                       if card.upgrade.position is position
                       and card.upgrade.stat is stat
                       and card.rarity is FootballShopRarity.COMMON
                       and card.upgrade.duration is duration)
        for duration in FootballUpgradeDuration
    }
    shop = FootballShop(roster, 1, catalogs={
        FootballShopSection.PLAYER_UPGRADES: tuple(cards.values()),
    })
    perm = cards[FootballUpgradeDuration.PERMANENT]
    temp = cards[FootballUpgradeDuration.TEMPORARY]
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, perm.card_id)
    before = shop.state
    preview = before.project_player_upgrade(temp.upgrade)
    assert preview.run.change == 0
    assert preview.next_match.change == pytest.approx(partial)
    assert preview.next_match.after == pytest.approx(cap)
    assert shop.state == before
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    assert getattr(shop.match_roster().players[position], stat.value) == pytest.approx(cap)
    shop.move_to_next_day()
    next_preview = shop.state.project_player_upgrade(temp.upgrade)
    assert next_preview.next_match.change == pytest.approx(0)
    run_preview = shop.state.project_player_upgrade(perm.upgrade)
    assert run_preview.run.change == pytest.approx(permanent)
    assert run_preview.next_match.change == pytest.approx(0)
    assert temp.eligible(shop.roster) and perm.eligible(shop.roster)
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, perm.card_id)
    assert getattr(shop.roster.players[position], stat.value) == pytest.approx(
        min(1.0, max(0.0, initial + 2 * permanent))
        if stat is FootballUpgradeStat.VOLATILITY else cap
    )
    assert getattr(shop.match_roster().players[position], stat.value) == pytest.approx(cap)
    if stat is FootballUpgradeStat.STAMINA:
        assert shop.state.project_player_upgrade(perm.upgrade).run.change == pytest.approx(0)


@pytest.mark.parametrize("position", [FootballPosition.QB, FootballPosition.D_LINE])
@pytest.mark.parametrize("stat", list(FootballUpgradeStat))
@pytest.mark.parametrize("duration", list(FootballUpgradeDuration))
def test_coached_projection_matches_simulator_with_pending_upgrades(position, stat, duration) -> None:
    offense = position is FootballPosition.QB
    roster = replace(_roster(stamina=0.82), coach_assignment=COACH_PAIR_OFFERS[0].assignment)
    other = _roster("Opponent")
    kinds = (
        (FootballCoachUpgradeKind.OFFENSE_POWER_BOOST, FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST,
         FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION)
        if offense else
        (FootballCoachUpgradeKind.DEFENSE_POWER_BOOST, FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST,
         FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION)
    )
    coaches = tuple(next(card for card in COACH_UPGRADE_CATALOG
                         if card.coach_upgrade_effect.kind is kind) for kind in kinds)
    effects = tuple(card.coach_upgrade_effect for card in coaches)
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is position and card.upgrade.stat is stat
                and card.upgrade.duration is duration and card.rarity is FootballShopRarity.COMMON)
    pending = next(card.upgrade for card in PLAYER_UPGRADE_CATALOG
                   if card.upgrade.position is position and card.upgrade.stat is stat
                   and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                   and card.rarity is FootballShopRarity.COMMON)
    state = replace(FootballShop(roster, 1).state, owned_coach_upgrades=coaches,
                    pending_player_upgrades=(pending,))
    preview = state.project_player_upgrade(card.upgrade)
    before = state.next_match_roster
    after = (apply_player_upgrades(apply_player_upgrade(roster, card.upgrade), (pending,))
             if duration is FootballUpgradeDuration.PERMANENT
             else apply_player_upgrade(before, card.upgrade))
    play, scheme = OffensivePlayAction.DEEP_PASS, DefensiveSchemeAction.RB_RUN

    def estimate(team, prior_plays):
        return calculate_play_estimate(
            team if offense else other, other if offense else team, play, scheme,
            prior_plays=prior_plays,
            offense_coach_upgrades=effects if offense else (),
            defense_coach_upgrades=effects if not offense else (),
        )

    prior = 30 if stat is FootballUpgradeStat.STAMINA else 0
    first, second = estimate(before, prior), estimate(after, prior)
    if stat is FootballUpgradeStat.VOLATILITY:
        contributors = (OFFENSIVE_PLAY_CATALOG[play.value].contributors if offense
                        else DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors)
        actual_change = (second.yardage_spread - first.yardage_spread) * len(contributors) / 6
    else:
        first_power = first.matchup.offense if offense else first.matchup.defense
        second_power = second.matchup.offense if offense else second.matchup.defense
        actual_change = second_power - first_power
        if stat is FootballUpgradeStat.STAMINA:
            baseline_power = state.coached_player_stats(before, position)[0]
            actual_change /= baseline_power * 0.1
    assert preview.effective_next_match.change == pytest.approx(actual_change)
    assert state.roster == roster and state.pending_player_upgrades == (pending,)


@pytest.mark.parametrize("position,coach_id", [
    (FootballPosition.QB, "fourth_quarter_conditioning"),
    (FootballPosition.D_LINE, "iron_lungs"),
])
@pytest.mark.parametrize("stamina,expected", [(0.85, 0.05), (0.90, 0.0)])
@pytest.mark.parametrize("duration", list(FootballUpgradeDuration))
def test_coached_stamina_preview_distinguishes_raw_and_capped_match(
    position, coach_id, stamina, expected, duration
) -> None:
    roster = _roster(stamina=stamina)
    coach = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == coach_id)
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is position
                and card.upgrade.stat is FootballUpgradeStat.STAMINA
                and card.upgrade.duration is duration and card.rarity is FootballShopRarity.COMMON)
    state = replace(FootballShop(roster, 1).state, owned_coach_upgrades=(coach,))
    projection = state.project_player_upgrade(card.upgrade)
    assert projection.next_match.change == pytest.approx(card.upgrade.amount)
    assert projection.effective_next_match.change == pytest.approx(expected)
    if duration is FootballUpgradeDuration.PERMANENT:
        assert projection.run.change == pytest.approx(0.05)


@pytest.mark.parametrize("position,ids", [
    (FootballPosition.QB, ("two_minute_drill", "fourth_quarter_conditioning", "rhythm_install")),
    (FootballPosition.D_LINE, ("front_seven_film", "iron_lungs", "disguise_package")),
])
def test_coached_projection_stacks_effects_with_simulator_caps(position, ids) -> None:
    roster = _roster(stamina=0.6)
    cards = tuple(next(card for card in COACH_UPGRADE_CATALOG if card.card_id == card_id)
                  for card_id in ids)
    effects = tuple(card.coach_upgrade_effect for card in cards for _ in range(5))
    state = replace(FootballShop(roster, 1).state,
                    owned_coach_upgrades=tuple(card for card in cards for _ in range(5)))
    power, volatility, stamina = state.coached_player_stats(roster, position)
    assert power == pytest.approx(12)
    assert volatility == pytest.approx(0.14)
    assert stamina == pytest.approx(0.9)
    offense = position is FootballPosition.QB
    result = calculate_play_estimate(
        roster, roster, OffensivePlayAction.DEEP_PASS, DefensiveSchemeAction.RB_RUN,
        prior_plays=30, offense_coach_upgrades=effects if offense else (),
        defense_coach_upgrades=effects if not offense else (),
    )
    matchup = result.matchup.offense if offense else result.matchup.defense
    assert matchup == pytest.approx(2 * power * (1 - 0.1 * (1 - stamina)))
    assert result.yardage_spread == pytest.approx((0.14 + 0.2) * 6)


def _shop_with_both_upgrade_stats(
    roster: FootballRoster,
    seed: int,
) -> FootballShop:
    cards = tuple(card for card in _player_upgrade_catalog()
                  if card.upgrade.position is FootballPosition.QB
                  and card.upgrade.rarity is FootballShopRarity.COMMON
                  and card.upgrade.duration is FootballUpgradeDuration.PERMANENT
                  and card.upgrade.stat in (FootballUpgradeStat.POWER, FootballUpgradeStat.STAMINA))
    return FootballShop(roster, seed, catalogs={FootballShopSection.PLAYER_UPGRADES: cards})


def test_shop_offer_is_three_distinct_affordable_upgrades_and_seeded() -> None:
    first = FootballShop(_roster(), 12)
    replay = FootballShop(_roster(), 12)

    assert len(first.offer) == 3
    assert len({upgrade.upgrade_id for upgrade in first.offer}) == 3
    assert all(0 < upgrade.cost <= ACTION_POINT_BUDGET for upgrade in first.offer)
    assert first.remaining_ap == ACTION_POINT_BUDGET
    assert all(upgrade.rarity in FootballShopRarity for upgrade in first.offer)
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
    shop.buy_upgrade(power_upgrade)
    powered = shop.roster
    updated_target = powered.players[power_upgrade.position]
    assert updated_target.power == old_target.power + power_upgrade.amount
    assert updated_target.volatility == old_target.volatility
    assert updated_target.stamina == old_target.stamina
    assert shop.remaining_ap == initial_ap - power_upgrade.cost

    old_stamina_target = powered.players[stamina_upgrade.position]
    ap_before_stamina = shop.remaining_ap
    shop.buy_upgrade(stamina_upgrade)
    upgraded = shop.roster.players[stamina_upgrade.position]
    assert upgraded.stamina == pytest.approx(old_stamina_target.stamina + stamina_upgrade.amount)
    assert upgraded.power == old_stamina_target.power
    assert upgraded.volatility == old_stamina_target.volatility
    assert 0 <= upgraded.stamina <= 1
    assert original.players[power_upgrade.position] is old_target
    assert shop.roster.coach is original.coach
    assert shop.roster.special_teams is original.special_teams
    assert shop.roster.team_name == original.team_name
    assert shop.remaining_ap == ap_before_stamina - stamina_upgrade.cost
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
        rng=_FixedShopRng(0.1),
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
        shop.buy_upgrade(fabricated)
    with pytest.raises(ValueError, match="valid index"):
        shop.buy_upgrade(True)
    with pytest.raises(ValueError, match="out of range"):
        shop.buy_upgrade(3)
    assert shop.state == state

    shop.buy_upgrade(offered)
    after_purchase = shop.state
    with pytest.raises(ValueError, match="already been purchased"):
        shop.buy_upgrade(offered)
    assert shop.state == after_purchase

    shop.finish()
    finished_state = shop.state
    with pytest.raises(ValueError, match="shop is finished"):
        shop.buy_upgrade(shop.offer[1])
    with pytest.raises(ValueError, match="shop is finished"):
        shop.finish()
    assert shop.state == finished_state


def test_capped_stamina_upgrades_remain_available_and_stay_capped() -> None:
    roster = _roster(stamina=1.0)
    shop = _shop_with_both_upgrade_stats(roster, 61)
    capped_upgrade = next(upgrade for upgrade in shop.offer if upgrade.stat is FootballUpgradeStat.STAMINA)
    shop.buy_upgrade(capped_upgrade)
    assert shop.roster.players[capped_upgrade.position].stamina == 1.0


def test_roster_updates_are_immutable_valid_and_seeded_outcomes_match() -> None:
    original = _roster()
    first = FootballShop(original, 7)
    replay = FootballShop(original, 7)
    choices = (0, 1)

    for choice in choices:
        first.buy_upgrade(choice)
        replay.buy_upgrade(choice)

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
    card = next(card for card in _player_upgrade_catalog()
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.POWER
                and card.upgrade.duration is FootballUpgradeDuration.PERMANENT)
    shop = FootballShop(original_roster, 19, catalogs={FootballShopSection.PLAYER_UPGRADES: (card,)})
    upgrade = shop.offer[0]
    original_player = original_roster.players[upgrade.position]
    assert original_player.player_type_id is not None
    original_type = player_type_for_id(original_player.player_type_id)

    updated_roster = shop.buy_upgrade(upgrade).roster
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
    shop.buy_upgrade(0)
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
    shop.buy_upgrade(0)

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
        coach_upgrade_effect=(
            FootballCoachUpgradeEffect(
                card_id,
                FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
                0.05,
            )
            if section is FootballShopSection.COACH_UPGRADES
            else None
        ),
    )


def test_three_sections_start_with_requested_slots_and_playbook_cards() -> None:
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
    assert plays.catalog_available
    assert all(slot.card is not None for slot in plays.slots[:4])
    assert all(
        card.eligible(shop.roster)
        for card in shop._catalogs[FootballShopSection.PLAYS_SCHEMES]
    )
    assert plays.slots[4].unlock_cost == 4 and plays.slots[4].can_unlock
    assert plays.slots[5].unlock_cost == 5 and not plays.slots[5].can_unlock
    assert [slot.unlocked for slot in coaches.slots] == [False, False]
    assert coaches.slots[0].unlock_cost == 4
    assert not coaches.slots[0].can_unlock
    assert "after game 3" in coaches.slots[0].disabled_reason
    assert coaches.slots[1].unlock_cost == 6 and not coaches.slots[1].can_unlock

    unlocked = shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 5)
    assert unlocked.remaining_ap == 8
    assert unlocked.section(FootballShopSection.PLAYS_SCHEMES).slots[4].card is not None
    assert unlocked.section(FootballShopSection.PLAYS_SCHEMES).slots[5].can_unlock
    before = shop.state
    rng_before = shop._rng.getstate()
    with pytest.raises(ValueError, match="after game 3"):
        shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    assert shop.state == before
    assert shop._rng.getstate() == rng_before

    after_game_three = FootballShop(_roster(), 5, game_number=4)
    coach_slot = after_game_three.state.section(
        FootballShopSection.COACH_UPGRADES
    ).slots[0]
    assert coach_slot.can_unlock
    assert coach_slot.disabled_reason is None
    assert after_game_three.state.section(
        FootballShopSection.COACH_UPGRADES
    ).catalog_available
    unlocked_coach = after_game_three.unlock_slot(
        FootballShopSection.COACH_UPGRADES, 1
    )
    assert (
        unlocked_coach.section(FootballShopSection.COACH_UPGRADES).slots[0].card
        is not None
    )


@pytest.mark.parametrize(
    ("kind", "definition", "starting_size"),
    [
        ("play", OFFENSIVE_PLAY_CATALOG["qb_sneak"], 6),
        ("scheme", DEFENSIVE_SCHEME_CATALOG["cover_two_shell"], 6),
    ],
)
def test_buying_a_play_or_scheme_adds_one_owned_copy(
    kind, definition, starting_size
) -> None:
    card = FootballShopCard(
        card_id=f"{kind}:{definition.card_id}",
        name=definition.name,
        description=definition.description,
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.RARE,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        football_card=definition,
    )
    shop = FootballShop(
        _roster(),
        41,
        catalogs={FootballShopSection.PLAYS_SCHEMES: (card,)},
    )

    before_ap = shop.remaining_ap
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)
    deck = shop.offensive_deck if kind == "play" else shop.defensive_deck
    assert len(deck) == starting_size + 1
    assert deck[-1].card_id == definition.card_id
    assert shop.remaining_ap == before_ap - card.cost


def test_play_ownership_persists_across_shop_visits_and_upgrade_history_is_run_wide() -> None:
    definition = OFFENSIVE_PLAY_CATALOG["qb_sneak"]
    card = FootballShopCard(
        card_id=f"play:{definition.card_id}",
        name=definition.name,
        description=definition.description,
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        football_card=definition,
    )
    shop = FootballShop(
        _roster(),
        43,
        catalogs={FootballShopSection.PLAYS_SCHEMES: (card,)},
    )
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)
    first_copy = shop.offensive_deck[-1]
    upgrade = shop.offer[0]
    shop.buy_upgrade(upgrade)
    shop.finish()
    shop.open_next_visit(2)
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)

    copies = [
        owned for owned in shop.offensive_deck
        if owned.card_id == definition.card_id
    ]
    assert len(copies) == 2
    assert copies[0].copy_id != copies[1].copy_id
    assert first_copy in copies
    assert shop.state.purchased_upgrades == (upgrade,)


def test_removal_is_transactional_cancelable_and_charges_only_on_confirmation() -> None:
    removal = FootballShopCard(
        card_id="remove-one-card",
        name="Remove One Card",
        description="Remove one owned play or scheme.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.RARE,
        cost=CARD_REMOVAL_COST,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        is_removal=True,
    )
    replacement = _future_catalog_card(
        "very-rare-replacement",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.VERY_RARE,
    )
    shop = FootballShop(
        _roster(),
        rng=_FixedShopRng(0.99),
        catalogs={
            FootballShopSection.PLAYS_SCHEMES: (removal, replacement),
        },
    )
    shop._offers[FootballShopSection.PLAYS_SCHEMES] = [removal, None, None, None]
    initial = shop.state
    copy_to_remove = initial.offensive_deck[-1]
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, removal.card_id)
    pending = shop.state
    assert pending.pending_removal is removal
    assert pending.remaining_ap == initial.remaining_ap
    assert pending.offensive_deck == initial.offensive_deck
    assert not pending.section(FootballShopSection.PLAYS_SCHEMES).slots[0].purchased

    shop.cancel_card_removal()
    assert shop.state == initial

    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, removal.card_id)
    removed = shop.remove_owned_card(copy_to_remove.copy_id)
    assert removed.remaining_ap == initial.remaining_ap - CARD_REMOVAL_COST
    assert copy_to_remove not in removed.offensive_deck
    assert len(removed.offensive_deck) == 5
    assert removed.pending_removal is None
    slot = removed.section(FootballShopSection.PLAYS_SCHEMES).slots[0]
    assert slot.card is removal and slot.purchased
    assert replacement not in (s.card for s in removed.section(FootballShopSection.PLAYS_SCHEMES).slots)


def test_bonus_purchase_stays_in_its_slot_until_next_day() -> None:
    shop = FootballShop(_roster(), rng=_FixedShopRng(0.99))
    section = FootballShopSection.PLAYS_SCHEMES
    catalog = shop._catalogs[section]
    bonus = next(card for card in catalog if card.card_id == "bonus:offensive_draw")
    shop._offers[section] = [bonus, None, None, None]

    state = shop.buy_card(section, bonus.card_id)
    slot = state.section(section).slots[0]
    assert slot.card is bonus and slot.purchased
    with pytest.raises(ValueError, match="already been purchased"):
        shop.buy_card(section, bonus.card_id)
    rerolled = shop.move_to_next_day().section(section).slots[0]
    assert not rerolled.purchased
    assert rerolled.card.rarity is FootballShopRarity.VERY_RARE


def test_removal_respects_four_card_minimum_and_excludes_empty_service_offer() -> None:
    removal = FootballShopCard(
        card_id="remove-one-card",
        name="Remove One Card",
        description="Remove one owned play or scheme.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.RARE,
        cost=CARD_REMOVAL_COST,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        is_removal=True,
    )
    shop = FootballShop(
        _roster(),
        rng=_FixedShopRng(0.9),
        catalogs={FootballShopSection.PLAYS_SCHEMES: (removal,)},
    )
    for visit in range(4):
        state = shop.state
        target = (
            state.offensive_deck[-1]
            if len(state.offensive_deck) > MIN_PLAYBOOK_DECK_SIZE
            else state.defensive_deck[-1]
        )
        shop.buy_card(FootballShopSection.PLAYS_SCHEMES, removal.card_id)
        shop.remove_owned_card(target.copy_id)
        if visit < 3:
            shop.finish()
            shop.open_next_visit(visit + 2)

    shop.finish()
    shop.open_next_visit(5)
    state = shop.state
    assert len(state.offensive_deck) == MIN_PLAYBOOK_DECK_SIZE
    assert len(state.defensive_deck) == MIN_PLAYBOOK_DECK_SIZE
    removal_slot = state.section(FootballShopSection.PLAYS_SCHEMES).slots[0]
    assert removal_slot.card is None
    before = shop.state
    with pytest.raises(ValueError, match="not in the current offer"):
        shop.buy_card(FootballShopSection.PLAYS_SCHEMES, removal.card_id)
    assert shop.state == before


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
        rng=_FixedShopRng(0.6),
        catalogs={FootballShopSection.PLAYS_SCHEMES: cards},
    )

    first = shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 5)
    assert first.remaining_ap == 8
    assert first.section(FootballShopSection.PLAYS_SCHEMES).slots[4].card is not None
    second = shop.unlock_slot(FootballShopSection.PLAYS_SCHEMES, 6)
    section = second.section(FootballShopSection.PLAYS_SCHEMES)
    assert second.remaining_ap == 3
    assert section.slots[5].unlocked and section.slots[5].card is not None
    assert all(
        slot.card is not None and slot.card in cards
        for slot in section.slots[:6]
    )


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


def test_play_scheme_rarity_rolls_are_independent_and_offer_pools_are_respected() -> None:
    assert dict(RARITY_WEIGHTS) == {
        FootballShopRarity.COMMON: 40,
        FootballShopRarity.UNCOMMON: 30,
        FootballShopRarity.RARE: 20,
        FootballShopRarity.VERY_RARE: 10,
    }
    assert dict(PLAY_SCHEME_RARITY_WEIGHTS) == {
        FootballShopRarity.COMMON: 58,
        FootballShopRarity.UNCOMMON: 24,
        FootballShopRarity.RARE: 12,
        FootballShopRarity.VERY_RARE: 6,
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
        assert all(
            slot.card is None or slot.card in all_rarities
            for slot in offer
        )
    for rarity, weight in PLAY_SCHEME_RARITY_WEIGHTS.items():
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
        rng=_FixedShopRng(0.9),
        catalogs={
            FootballShopSection.PLAYS_SCHEMES: (only_rare, ineligible_common)
        },
    )
    slots = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
    assert slots[0].card is only_rare
    assert all(slot.card is only_rare for slot in slots[1:4])


def test_each_play_scheme_offer_slot_rolls_its_own_rarity() -> None:
    cards = tuple(
        _future_catalog_card(
            f"slot-{rarity.value}-{index}",
            FootballShopSection.PLAYS_SCHEMES,
            rarity,
        )
        for rarity in FootballShopRarity
        for index in range(4)
    )
    shop = FootballShop(
        _roster(),
        seed=27,
        catalogs={FootballShopSection.PLAYS_SCHEMES: cards},
    )
    shop._rng = _SequenceShopRng((0.25, 0.7, 0.88, 0.97))
    offer = []
    for _ in range(4):
        card = shop._draw_card(FootballShopSection.PLAYS_SCHEMES, offer)
        assert card is not None
        offer.append(card)

    assert tuple(card.rarity for card in offer) == tuple(FootballShopRarity)
    assert len({card.card_id for card in offer}) == 4


def test_play_scheme_offer_repeats_eligible_cards_after_rarity_pool_exhaustion() -> None:
    common = _future_catalog_card(
        "single-common",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.COMMON,
    )
    ineligible_common = _future_catalog_card(
        "ineligible-common",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.COMMON,
        eligible=lambda _roster: False,
    )
    rare = _future_catalog_card(
        "single-rare",
        FootballShopSection.PLAYS_SCHEMES,
        FootballShopRarity.RARE,
    )
    shop = FootballShop(
        _roster(),
        seed=28,
        catalogs={
            FootballShopSection.PLAYER_UPGRADES: (),
            FootballShopSection.PLAYS_SCHEMES: (
                common,
                ineligible_common,
                rare,
            ),
            FootballShopSection.COACH_UPGRADES: (),
        },
    )
    shop._rng = _SequenceShopRng((0.25, 0.25, 0.88, 0.88))
    shop._reset_offers()

    slots = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
    offers = tuple(slot.card for slot in slots[:4])
    assert offers == (common, common, rare, rare)
    assert all(slot.card is not None for slot in slots[:4])
    assert ineligible_common not in offers

    assert sum(card is common for card in offers) == 2
    assert sum(card is rare for card in offers) == 2


def test_purchased_play_marks_matching_slots_purchased_until_next_day() -> None:
    source_shop = FootballShop(_roster(), 28)
    play_catalog = tuple(
        card
        for card in source_shop._catalogs[FootballShopSection.PLAYS_SCHEMES]
        if card.football_card is not None
    )[:2]
    assert len(play_catalog) == 2
    shop = FootballShop(
        _roster(),
        seed=29,
        catalogs={
            FootballShopSection.PLAYER_UPGRADES: (),
            FootballShopSection.PLAYS_SCHEMES: play_catalog,
            FootballShopSection.COACH_UPGRADES: (),
        },
    )
    shop._rng = _SequenceShopRng((0.0,) * 20)
    shop._reset_offers()

    before = shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots
    purchased_card = before[0].card
    assert purchased_card is not None
    assert all(slot.card is purchased_card for slot in before[:4])

    purchased = shop.buy_card(
        FootballShopSection.PLAYS_SCHEMES,
        purchased_card.card_id,
    )
    refreshed = purchased.section(FootballShopSection.PLAYS_SCHEMES).slots
    assert all(slot.card is purchased_card and slot.purchased for slot in refreshed[:4])
    assert len(purchased.purchased_cards) == 1
    with pytest.raises(ValueError, match="already been purchased"):
        shop.buy_card(
            FootballShopSection.PLAYS_SCHEMES,
            purchased_card.card_id,
        )

    next_day = shop.move_to_next_day()
    assert any(
        slot.card is not None and slot.card.card_id == purchased_card.card_id
        for slot in next_day.section(FootballShopSection.PLAYS_SCHEMES).slots[:4]
    )


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
    assert next_day.section(FootballShopSection.PLAYER_UPGRADES).slots[0].card is card
    assert not next_day.section(FootballShopSection.PLAYER_UPGRADES).slots[0].purchased
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
    first = FootballShop(_roster(), rng=_FixedShopRng(0.6), catalogs=catalogs)
    replay = FootballShop(_roster(), rng=_FixedShopRng(0.6), catalogs=catalogs)
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
        if section_id is FootballShopSection.PLAYER_UPGRADES:
            assert len(ids) == len(set(ids))
        else:
            assert all(card.card_id.startswith("play-reroll-") for card in cards if card)
    assert not first_state.section(FootballShopSection.COACH_UPGRADES).slots[0].unlocked
