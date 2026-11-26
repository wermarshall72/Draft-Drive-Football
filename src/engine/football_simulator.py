"""Caller-driven interactive football match resolution.

All randomness belongs to one ``FootballMatchSimulator`` instance for the
entire match. Yardage, clock, fatigue, and probability constants are prototype
values informed by available historical FBS summaries and arcade tuning.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from functools import lru_cache
from math import floor, isfinite
from numbers import Real
from typing import Any

from src.engine.football import (
    FootballBonusCardAction,
    DEFENSIVE_SCHEME_FAMILIES,
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardFamily,
    FootballCardCopy,
    FootballCoach,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballDeckState,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchResult,
    FootballMatchState,
    FootballMatchStatus,
    FootballPerkActivation,
    FootballPerkDecision,
    FootballPlayer,
    FootballPlayerPerkKind,
    FootballPosition,
    FootballPlayResult,
    FootballRoster,
    FootballSpecialTeams,
    FootballAutomaticAction,
    FootballConversionAction,
    FootballTeamSide,
    FootballTurnoverType,
    OFFENSIVE_PLAY_FAMILIES,
    OffensivePlayAction,
    match_state_from_save_data,
    match_state_to_save_data,
    matchup_for_scheme,
)
from src.engine.save_data import (
    required,
    optional,
    rng_from_data,
    rng_to_data,
)
from src.engine.football_coaches import (
    FootballCoachPerkKind,
    OFFENSIVE_POSITIONS,
    coaches_for_assignment,
)
from src.engine.football_player_catalog import coached_player_power, player_contribution_modifier
from src.engine.football_perk_context import (
    NO_PERK_INPUTS,
    QB_PASS_FAMILIES,
    FootballPerkEstimateInputs,
    estimate_perk_inputs,
    perk_history,
    scheme_keyed_defense,
    team_perks,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    starting_defensive_deck,
    starting_offensive_deck,
)

REGULATION_PERIOD_SECONDS = 900
OVERTIME_PERIOD_SECONDS = 300
FIRST_DOWN_YARDS = 10.0
GOAL_LINE_YARDS = 100.0
FIELD_GOAL_DISTANCE_BUFFER = 10.0

# Broad historical distance bands shape this provisional curve; it is not a
# verified 2022-2024 FBS distance-stratified aggregate.
FIELD_GOAL_POINTS = 3
TOUCHDOWN_POINTS = 6
SAFETY_POINTS = 2
INCOMPLETE_PASS_CLOCK_SECONDS = 5
PUNT_CLOCK_SECONDS = 10
FIELD_GOAL_CLOCK_SECONDS = 5
KICKOFF_CLOCK_SECONDS = 10
KICKOFF_GROSS_YARDS = 65.0
PUNT_GROSS_MEAN_YARDS = 43.0
PUNT_GROSS_STANDARD_DEVIATION = 5.0
PUNT_RETURN_CHANCE = 0.48
PUNT_RETURN_MEAN_YARDS = 8.0
PUNT_RETURN_STANDARD_DEVIATION = 4.0
PUNT_BLOCK_CHANCE = 0.007
FIELD_GOAL_BLOCK_CHANCE = 0.005
BLOCKED_KICK_RECOVERY_CHANCE = 0.5
BLOCKED_KICK_OWN_RECOVERY_MEAN_YARDS = 4.0
BLOCKED_KICK_OWN_RECOVERY_STANDARD_DEVIATION = 3.0
BLOCKED_KICK_RETURN_MEAN_YARDS = 15.0
BLOCKED_KICK_RETURN_STANDARD_DEVIATION = 8.0
EXTRA_POINT_BLOCK_CHANCE = 0.003
KICKOFF_TOUCHBACK_CHANCE = 0.58
KICKOFF_RETURN_MEAN_YARDS = 25.0
KICKOFF_RETURN_STANDARD_DEVIATION = 6.0
KICKOFF_RETURN_TOUCHDOWN_CHANCE = 0.002
EXTRA_POINT_SUCCESS_CHANCE = 0.94
TWO_POINT_RETURN_TOUCHDOWN_CHANCE = 0.01
TOUCHBACK_START_YARDS = 25.0
MIN_PLAY_YARDAGE_SPREAD = 1.0
VOLATILITY_SPREAD_MULTIPLIER = 6.0
FATIGUE_RAMP_PLAYS = 30
MAX_FATIGUE_POWER_REDUCTION = 0.10
MAX_COACH_POWER_BONUS = 0.20
MAX_COACH_VOLATILITY_REDUCTION = 0.30
MAX_COACH_STAMINA_BONUS = 0.30
MAX_COACH_YARDAGE_DELTA = 0.50
MAX_COACH_RISK_REDUCTION = 0.75
MIN_COACH_CLOCK_MULTIPLIER = 0.75
MAX_COACH_CLOCK_MULTIPLIER = 1.25
MATCHED_SCHEME_DEFENSE_MULTIPLIER = 1.12
MATCHED_SCHEME_OFFENSE_MULTIPLIER = 0.96
MATCHED_SCHEME_YARDAGE_PENALTY = 0.5
PLAY_DEFENSE_BASELINE_YARDAGE_REDUCTION = 0.0
OFFENSIVE_BASELINE_YARDAGE_BONUS = 3.5
RUN_BASELINE_YARDAGE_ADJUSTMENT = -3.75
PASS_BASELINE_YARDAGE_ADJUSTMENT = 1.0
POWER_YARDAGE_MULTIPLIER = 0.16
PASS_INCOMPLETE_BASE_PROBABILITY = 0.29
MATCHED_SCHEME_INCOMPLETE_BONUS = 0.04
MATCHUP_INCOMPLETE_SENSITIVITY = 0.16
MATCHUP_TURNOVER_SENSITIVITY = 0.04
MATCHED_SCHEME_TURNOVER_BONUS = 0.005
MIN_PLAY_YARDAGE = -5.0
MAX_PLAY_YARDAGE = 25.0
MAX_NONSCORING_RETURN_FIELD_POSITION = GOAL_LINE_YARDS - 1.0
PASS_INTERCEPTION_PROBABILITIES = {
    FootballCardFamily.SCREEN_PASS: 0.015,
    FootballCardFamily.PA_PASS: 0.025,
    FootballCardFamily.SHORT_PASS: 0.015,
    FootballCardFamily.MEDIUM_PASS: 0.025,
    FootballCardFamily.DEEP_PASS: 0.04,
}
RUN_FUMBLE_PROBABILITIES = {
    FootballCardFamily.RB_RUN: 0.012,
}

_OFFENSIVE_EXTRA_DRAW_ACTIONS = frozenset(
    (
        FootballBonusCardAction.OFFENSIVE_DRAW,
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD,
    )
)
_PASS_PLAYS = frozenset(
    definition.action
    for definition in OFFENSIVE_PLAY_CATALOG.values()
    if definition.family is not FootballCardFamily.RB_RUN
)
_BASE_YARDAGE = {
    definition.action: definition.base_yards
    for definition in OFFENSIVE_PLAY_CATALOG.values()
}
_FIELD_GOAL_DISTANCE_RATES = (
    (17.0, 0.950),
    (22.0, 0.936),
    (27.0, 0.880),
    (32.0, 0.813),
    (37.0, 0.744),
    (42.0, 0.652),
    (47.0, 0.588),
    (52.0, 0.486),
    (57.0, 0.387),
    (62.0, 0.385),
    (67.0, 0.10),
)


def field_goal_distance_for_position(field_position: float) -> float:
    if (
        isinstance(field_position, bool)
        or not isinstance(field_position, Real)
        or not isfinite(field_position)
    ):
        raise ValueError("Field position must be a finite number from 0 to 100.")
    if not 0 <= field_position <= GOAL_LINE_YARDS:
        raise ValueError("Field position must be between 0 and 100.")
    return (GOAL_LINE_YARDS - field_position) + FIELD_GOAL_DISTANCE_BUFFER


def field_goal_success_probability(
    distance: float, bonus_percentage_points: float = 0.0
) -> float:
    if (
        isinstance(distance, bool)
        or not isinstance(distance, Real)
        or not isfinite(distance)
        or distance < 0
    ):
        raise ValueError("Field-goal distance must be a non-negative number.")
    if (
        isinstance(bonus_percentage_points, bool)
        or not isinstance(bonus_percentage_points, Real)
        or not isfinite(bonus_percentage_points)
        or bonus_percentage_points < 0
    ):
        raise ValueError("Field-goal bonus must be a finite non-negative probability.")
    if distance <= _FIELD_GOAL_DISTANCE_RATES[0][0]:
        return _clamp(0.97 + bonus_percentage_points, 0.0, 1.0)
    for (lower_distance, lower_rate), (upper_distance, upper_rate) in zip(
        _FIELD_GOAL_DISTANCE_RATES,
        _FIELD_GOAL_DISTANCE_RATES[1:],
    ):
        if distance <= upper_distance:
            fraction = (distance - lower_distance) / (
                upper_distance - lower_distance
            )
            return _clamp(
                lower_rate + fraction * (upper_rate - lower_rate)
                + bonus_percentage_points,
                0.0,
                1.0,
            )
    return _clamp(
        _FIELD_GOAL_DISTANCE_RATES[-1][1] + bonus_percentage_points,
        0.0,
        1.0,
    )


def coach_upgrade_magnitude(
    upgrades: tuple[FootballCoachUpgradeEffect, ...],
    kind: FootballCoachUpgradeKind,
    *,
    family: FootballCardFamily | None = None,
) -> float:
    if (
        not isinstance(upgrades, tuple)
        or any(not isinstance(upgrade, FootballCoachUpgradeEffect) for upgrade in upgrades)
        or not isinstance(kind, FootballCoachUpgradeKind)
    ):
        raise ValueError("Coach effect lookup requires typed immutable upgrades.")
    return sum(
        upgrade.magnitude
        for upgrade in upgrades
        if upgrade.kind is kind
        and (family is None or upgrade.family is family)
    )


def coach_power_multiplier(
    upgrades: tuple[FootballCoachUpgradeEffect, ...], *, offense: bool
) -> float:
    kind = (FootballCoachUpgradeKind.OFFENSE_POWER_BOOST if offense
            else FootballCoachUpgradeKind.DEFENSE_POWER_BOOST)
    return 1.0 + min(MAX_COACH_POWER_BONUS, coach_upgrade_magnitude(upgrades, kind))


def coach_volatility_multiplier(
    upgrades: tuple[FootballCoachUpgradeEffect, ...], *, offense: bool
) -> float:
    kind = (FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION if offense
            else FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION)
    return 1.0 - min(MAX_COACH_VOLATILITY_REDUCTION, coach_upgrade_magnitude(upgrades, kind))


def coach_stamina_bonus(
    upgrades: tuple[FootballCoachUpgradeEffect, ...], *, offense: bool
) -> float:
    kind = (FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST if offense
            else FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST)
    return min(MAX_COACH_STAMINA_BONUS, coach_upgrade_magnitude(upgrades, kind))


def effective_player_stamina(player: FootballPlayer, stamina_bonus: float) -> float:
    return min(1.0, player.stamina + min(stamina_bonus, MAX_COACH_STAMINA_BONUS))


def coached_player_baseline_stats(
    roster: FootballRoster,
    position: FootballPosition,
    upgrades: tuple[FootballCoachUpgradeEffect, ...],
) -> tuple[float, float, float]:
    """Power, volatility and stamina without play-specific effects or fatigue."""
    player = roster.players[position]
    offense = position in OFFENSIVE_POSITIONS
    coach = coaches_for_assignment(roster.coach_assignment)[0 if offense else 1]
    modifier = coach.position_modifiers[position] if coach is not None else 0.0
    power = coached_player_power(player, modifier) * coach_power_multiplier(upgrades, offense=offense)
    volatility = player.volatility * coach_volatility_multiplier(upgrades, offense=offense)
    stamina = effective_player_stamina(player, coach_stamina_bonus(upgrades, offense=offense))
    return power, volatility, stamina


def field_goal_success_probability_for_team(
    state: FootballMatchState,
    team: FootballTeamSide,
    distance: float,
) -> float:
    if not isinstance(state, FootballMatchState) or not isinstance(team, FootballTeamSide):
        raise ValueError("Field-goal estimate requires a match and team side.")
    upgrades = (
        state.team_a_coach_upgrades
        if team is FootballTeamSide.TEAM_A
        else state.team_b_coach_upgrades
    )
    bonus = coach_upgrade_magnitude(
        upgrades, FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS
    )
    return field_goal_success_probability(distance + range_denial_yards(state, team), bonus)


def range_denial_yards(state: FootballMatchState, kicking_team: FootballTeamSide) -> float:
    """Range Denial (S6): the rival kicks as if the field goal were longer."""
    entry = team_perks(state, _opponent(kicking_team)).get(FootballPlayerPerkKind.RANGE_DENIAL)
    return entry[1].value("yards") if entry is not None else 0.0


def adjusted_offensive_play_clock_seconds(
    base_seconds: int,
    upgrades: tuple[FootballCoachUpgradeEffect, ...],
) -> int:
    if isinstance(base_seconds, bool) or not isinstance(base_seconds, int) or base_seconds < 1:
        raise ValueError("Offensive play clock duration must be a positive integer.")
    delta = coach_upgrade_magnitude(
        upgrades, FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA
    )
    multiplier = _clamp(
        1.0 + delta,
        MIN_COACH_CLOCK_MULTIPLIER,
        MAX_COACH_CLOCK_MULTIPLIER,
    )
    return max(1, floor(base_seconds * multiplier + 0.5))


def blocked_kick_probability(
    state: FootballMatchState,
    kicking_team: FootballTeamSide,
    base_probability: float,
) -> float:
    if (
        not isinstance(state, FootballMatchState)
        or not isinstance(kicking_team, FootballTeamSide)
        or isinstance(base_probability, bool)
        or not isinstance(base_probability, Real)
        or not isfinite(base_probability)
        or not 0.0 <= base_probability <= 1.0
    ):
        raise ValueError("Blocked-kick estimate requires a valid match, team, and chance.")
    upgrades = (
        state.team_a_coach_upgrades
        if kicking_team is FootballTeamSide.TEAM_A
        else state.team_b_coach_upgrades
    )
    reduction = min(
        MAX_COACH_RISK_REDUCTION,
        coach_upgrade_magnitude(
            upgrades, FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION
        ),
    )
    return _clamp(base_probability * (1.0 - reduction), 0.0, 1.0)


def _opponent(side: FootballTeamSide) -> FootballTeamSide:
    return (
        FootballTeamSide.TEAM_B
        if side is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _drive_yards_remaining(position: float) -> float:
    return max(0.0, GOAL_LINE_YARDS - position)


def _scheme_matches_play(
    scheme: DefensiveSchemeAction | None, play: OffensivePlayAction
) -> bool:
    return scheme is not None and play in matchup_for_scheme(scheme)[1]


@dataclass(frozen=True)
class FootballMatchupPower:
    offense: float
    defense: float
    scheme_matches_play: bool


@dataclass(frozen=True)
class FootballPlayEstimate:
    """Expected play result from the same matchup and risk model as resolution."""

    matchup: FootballMatchupPower
    family: FootballCardFamily
    yards_on_success: float
    yardage_spread: float
    incomplete_probability: float
    turnover_probability: float
    interception_return_yards: float = 0.0
    active_perks: frozenset[FootballCoachPerkKind] = frozenset()
    # Player perks that shaped this estimate (power, counters, yards, odds).
    player_perks: tuple[FootballPerkActivation, ...] = ()
    keep_read: bool = False

    @property
    def expected_yards(self) -> float:
        if self.family is not FootballCardFamily.RB_RUN:
            return (
                self.yards_on_success
                * (1.0 - self.incomplete_probability)
                * (1.0 - self.turnover_probability)
            )
        lower = self.yards_on_success - self.yardage_spread
        upper = self.yards_on_success + self.yardage_spread
        if upper <= 0:
            fumble_yards = self.yards_on_success
        elif lower >= 0:
            fumble_yards = 0.0
        else:
            fumble_yards = -(lower * lower) / (4.0 * self.yardage_spread)
        return (
            self.yards_on_success * (1.0 - self.turnover_probability)
            + fumble_yards * self.turnover_probability
        )

    def first_down_probability(self, yards_to_go: float) -> float:
        if yards_to_go <= 0:
            raise ValueError("First-down distance must be positive.")
        if yards_to_go <= self.yards_on_success - self.yardage_spread:
            yardage_probability = 1.0
        elif yards_to_go >= self.yards_on_success + self.yardage_spread:
            yardage_probability = 0.0
        else:
            yardage_probability = (
                self.yards_on_success + self.yardage_spread - yards_to_go
            ) / (2 * self.yardage_spread)
        return yardage_probability * (
            1.0
            - self.incomplete_probability
            - (1.0 - self.incomplete_probability) * self.turnover_probability
        )


def _play_risk_probabilities(
    play: OffensivePlayAction,
    matchup: FootballMatchupPower,
    *,
    incomplete_bonus: float = 0.0,
    turnover_bonus: float = 0.0,
    interception_risk_reduction: float = 0.0,
    keep_read: bool = False,
    fumble_bonus: float = 0.0,
) -> tuple[float, float]:
    power_total = max(1.0, matchup.offense + matchup.defense)
    defensive_edge = (matchup.defense - matchup.offense) / power_total
    family = OFFENSIVE_PLAY_FAMILIES[play]
    if keep_read:
        # Keep Read: no incompletion or interception roll; the RB Run fumble chance.
        family = FootballCardFamily.RB_RUN
        turnover_bonus = fumble_bonus
    if family is not FootballCardFamily.RB_RUN:
        incomplete = (
            PASS_INCOMPLETE_BASE_PROBABILITY
            + defensive_edge * MATCHUP_INCOMPLETE_SENSITIVITY
            + (
                MATCHED_SCHEME_INCOMPLETE_BONUS
                if matchup.scheme_matches_play
                else 0.0
            )
            + incomplete_bonus
        )
        interception = (
            PASS_INTERCEPTION_PROBABILITIES[family]
            + defensive_edge * MATCHUP_TURNOVER_SENSITIVITY
            + (
                MATCHED_SCHEME_TURNOVER_BONUS
                if matchup.scheme_matches_play
                else 0.0
            )
            + turnover_bonus
        )
        incomplete = _clamp(incomplete, 0.12, 0.52)
        interception = _clamp(interception, 0.005, 0.10)
        interception = _clamp(
            interception
            * (1.0 - min(interception_risk_reduction, MAX_COACH_RISK_REDUCTION)),
            0.0,
            0.10,
        )
        return incomplete, interception
    fumble = (
        RUN_FUMBLE_PROBABILITIES[family]
        + defensive_edge * MATCHUP_TURNOVER_SENSITIVITY
        + (
            MATCHED_SCHEME_TURNOVER_BONUS
            if matchup.scheme_matches_play
            else 0.0
        )
        + turnover_bonus
    )
    return 0.0, _clamp(fumble, 0.003, 0.08)


def _active_play_perks(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    down: int,
    drive_events: tuple[FootballMatchEvent, ...],
    is_conversion: bool,
) -> tuple[float, float, float, float, frozenset[FootballCoachPerkKind]]:
    offense_coach, _ = coaches_for_assignment(offense_roster.coach_assignment)
    _, defense_coach = coaches_for_assignment(defense_roster.coach_assignment)
    offense_perk = offense_coach.perk if offense_coach is not None else None
    defense_perk = defense_coach.perk if defense_coach is not None else None
    family = OFFENSIVE_PLAY_CATALOG[play.value].family
    is_run = family is FootballCardFamily.RB_RUN
    active: set[FootballCoachPerkKind] = set()
    yardage_bonus = 0.0
    incomplete_bonus = 0.0
    turnover_bonus = 0.0
    interception_return_yards = 0.0

    if (
        is_run
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_RUN_YARDS
        and not any(
            isinstance(event.action, OffensivePlayAction)
            and OFFENSIVE_PLAY_CATALOG[event.action.value].family
            is FootballCardFamily.RB_RUN
            for event in drive_events
        )
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS
        and not any(
            event.play_result is not None
            and isinstance(event.action, OffensivePlayAction)
            and OFFENSIVE_PLAY_CATALOG[event.action.value].family
            is not FootballCardFamily.RB_RUN
            and not event.play_result.incomplete
            and not event.play_result.turnover
            for event in drive_events
        )
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and not is_conversion
        and down == 1
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        is_run
        and DEFENSIVE_SCHEME_FAMILIES[scheme] is FootballCardFamily.RB_RUN
        and defense_perk is not None
        and defense_perk.kind is FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION
    ):
        active.add(defense_perk.kind)
        yardage_bonus -= defense_perk.value
    if (
        not is_conversion
        and down == 4
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and play in matchup_for_scheme(scheme)[1]
        and defense_perk.kind
        is FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS
    ):
        active.add(defense_perk.kind)
        incomplete_bonus += defense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and play in matchup_for_scheme(scheme)[1]
        and defense_perk.kind
        is FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS
    ):
        active.add(defense_perk.kind)
        turnover_bonus += defense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and defense_perk.kind is FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS
    ):
        active.add(defense_perk.kind)
        interception_return_yards = defense_perk.value

    return (
        yardage_bonus,
        incomplete_bonus,
        turnover_bonus,
        interception_return_yards,
        frozenset(active),
    )


def calculate_play_estimate(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    prior_plays: int = 0,
    down: int = 1,
    drive_events: tuple[FootballMatchEvent, ...] = (),
    is_conversion: bool = False,
    yardage_bonus: float = 0.0,
    completion_bonus: float = 0.0,
    offense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    defense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    perk_inputs: FootballPerkEstimateInputs = NO_PERK_INPUTS,
) -> FootballPlayEstimate:
    if not isinstance(perk_inputs, FootballPerkEstimateInputs):
        raise ValueError("Player-perk inputs must be FootballPerkEstimateInputs.")
    if not isfinite(yardage_bonus) or not isfinite(completion_bonus):
        raise ValueError("Play bonuses must be finite numbers.")
    if any(
        not isinstance(upgrades, tuple)
        or any(
            not isinstance(upgrade, FootballCoachUpgradeEffect)
            for upgrade in upgrades
        )
        for upgrades in (offense_coach_upgrades, defense_coach_upgrades)
    ):
        raise ValueError("Play estimates require typed immutable coach upgrades.")
    matchup = calculate_matchup_power(
        offense_roster,
        defense_roster,
        play,
        scheme,
        prior_plays=prior_plays,
        offense_coach_upgrades=offense_coach_upgrades,
        defense_coach_upgrades=defense_coach_upgrades,
        perk_inputs=perk_inputs,
    )
    (
        contextual_yardage_bonus,
        incomplete_bonus,
        turnover_bonus,
        interception_return_yards,
        active_perks,
    ) = _active_play_perks(
        offense_roster,
        defense_roster,
        play,
        scheme,
        down=down,
        drive_events=drive_events,
        is_conversion=is_conversion,
    )
    offense_players = tuple(
        offense_roster.players[position]
        for position in OFFENSIVE_PLAY_CATALOG[play.value].contributors
    )
    defense_players = tuple(
        defense_roster.players[position]
        for position in DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
    )
    offense_volatility_multiplier = coach_volatility_multiplier(offense_coach_upgrades, offense=True)
    defense_volatility_multiplier = coach_volatility_multiplier(defense_coach_upgrades, offense=False)
    spread = max(
        MIN_PLAY_YARDAGE_SPREAD,
        (
            sum(player.volatility for player in offense_players)
            * offense_volatility_multiplier
            / len(offense_players)
            + sum(player.volatility for player in defense_players)
            * defense_volatility_multiplier
            / len(defense_players)
        )
        * VOLATILITY_SPREAD_MULTIPLIER,
    )
    offensive_family = OFFENSIVE_PLAY_CATALOG[play.value].family
    defensive_family = DEFENSIVE_SCHEME_FAMILIES[scheme]
    family_yardage_delta = coach_upgrade_magnitude(
        offense_coach_upgrades,
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        family=offensive_family,
    )
    if defensive_family is offensive_family:
        family_yardage_delta -= coach_upgrade_magnitude(
            defense_coach_upgrades,
            FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
            family=offensive_family,
        )
    yards = (
        _BASE_YARDAGE[play]
        - PLAY_DEFENSE_BASELINE_YARDAGE_REDUCTION
        + OFFENSIVE_BASELINE_YARDAGE_BONUS
        + (
            RUN_BASELINE_YARDAGE_ADJUSTMENT
            if offensive_family is FootballCardFamily.RB_RUN
            else PASS_BASELINE_YARDAGE_ADJUSTMENT
        )
        + (matchup.offense - matchup.defense) * POWER_YARDAGE_MULTIPLIER
        - (
            MATCHED_SCHEME_YARDAGE_PENALTY
            if matchup.scheme_matches_play
            else 0.0
        )
        + yardage_bonus
        + completion_bonus
        + contextual_yardage_bonus
        + perk_inputs.yards
    )
    family_yardage_multiplier = _clamp(
        1.0 + (
            family_yardage_delta
            if yards >= 0.0
            else -family_yardage_delta
        ),
        1.0 - MAX_COACH_YARDAGE_DELTA,
        1.0 + MAX_COACH_YARDAGE_DELTA,
    )
    yards *= family_yardage_multiplier
    yards = _clamp(yards, MIN_PLAY_YARDAGE, MAX_PLAY_YARDAGE)
    interception_risk_reduction = coach_upgrade_magnitude(
        offense_coach_upgrades,
        FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
    )
    incomplete, conditional_turnover = _play_risk_probabilities(
        play,
        matchup,
        incomplete_bonus=incomplete_bonus + perk_inputs.incomplete,
        turnover_bonus=turnover_bonus + perk_inputs.interception,
        interception_risk_reduction=interception_risk_reduction,
        keep_read=perk_inputs.keep_read,
    )
    return FootballPlayEstimate(
        matchup,
        OFFENSIVE_PLAY_CATALOG[play.value].family,
        yards,
        spread,
        incomplete,
        conditional_turnover,
        interception_return_yards,
        active_perks,
        perk_inputs.activations,
        perk_inputs.keep_read,
    )


@lru_cache(maxsize=None)
def calculate_standardized_play_estimate(
    play: OffensivePlayAction,
) -> FootballPlayEstimate:
    """Estimate a card against equal, rested, uncoached players and a non-counter."""
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Standardized play estimate requires an OffensivePlayAction.")

    def neutral_roster(name: str) -> FootballRoster:
        players = {
            position: FootballPlayer(
                name=f"{name} {position.value}",
                position=position,
                power=10.0,
                volatility=0.0,
                stamina=1.0,
            )
            for position in FootballPosition
        }
        return FootballRoster(
            team_name=name,
            players=players,
            coach=FootballCoach(f"{name} Coach"),
            special_teams=FootballSpecialTeams(f"{name} Special Teams"),
        )

    family = OFFENSIVE_PLAY_FAMILIES[play]
    scheme = next(
        scheme
        for scheme, scheme_family in DEFENSIVE_SCHEME_FAMILIES.items()
        if scheme_family is not family
    )
    return calculate_play_estimate(
        neutral_roster("Neutral Offense"),
        neutral_roster("Neutral Defense"),
        play,
        scheme,
        prior_plays=0,
        down=1,
    )


def _drive_events_for_state(
    state: FootballMatchState,
    possession: FootballTeamSide,
) -> tuple[FootballMatchEvent, ...]:
    if state.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
        return ()  # the next drive has not started yet
    for index in range(len(state.match_events) - 1, -1, -1):
        event = state.match_events[index]
        if (
            isinstance(event.action, DefensiveSchemeAction)
            and event.possession is possession
        ):
            return state.match_events[index + 1 :]
    return ()


def calculate_match_play_estimate(
    state: FootballMatchState,
    play: OffensivePlayAction,
    *,
    scheme: DefensiveSchemeAction | None = None,
    offense_side: FootballTeamSide | None = None,
    is_conversion: bool = False,
) -> FootballPlayEstimate:
    if not isinstance(state, FootballMatchState):
        raise ValueError("Play estimate requires a FootballMatchState.")
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Play estimate requires an offensive play.")
    side = offense_side or state.possession
    active_scheme = scheme or state.current_drive_defensive_scheme
    if active_scheme is None:
        raise ValueError("Play estimate requires a defensive scheme.")
    offense = state.team_a if side is FootballTeamSide.TEAM_A else state.team_b
    defense = state.team_b if side is FootballTeamSide.TEAM_A else state.team_a
    prior_plays = sum(
        event.play_result is not None for event in state.match_events
    )
    return calculate_play_estimate(
        offense,
        defense,
        play,
        active_scheme,
        prior_plays=prior_plays,
        down=state.down,
        drive_events=_drive_events_for_state(state, side),
        is_conversion=is_conversion,
        perk_inputs=estimate_perk_inputs(
            state, side, play, active_scheme, is_conversion=is_conversion,
        ),
        offense_coach_upgrades=(
            state.team_a_coach_upgrades
            if side is FootballTeamSide.TEAM_A
            else state.team_b_coach_upgrades
        ),
        defense_coach_upgrades=(
            state.team_b_coach_upgrades
            if side is FootballTeamSide.TEAM_A
            else state.team_a_coach_upgrades
        ),
    )


@dataclass(frozen=True)
class FootballBlindPlayEstimate:
    """The offense's expected result when it cannot see the defense's call.

    ``components`` pairs each defense-call family the defending team owns with its
    share of that team's whole owned defensive deck and the ordinary estimate
    against that family. Every figure is the weighted average of those estimates.
    ``player_perks`` keeps only perks whose firing does not depend on the call.
    """

    family: FootballCardFamily
    components: tuple[tuple[float, FootballPlayEstimate], ...]
    player_perks: tuple[FootballPerkActivation, ...] = ()
    keep_read: bool = False

    def _average(self, value) -> float:
        return sum(weight * value(estimate) for weight, estimate in self.components)

    @property
    def expected_yards(self) -> float:
        return self._average(lambda estimate: estimate.expected_yards)

    @property
    def yards_on_success(self) -> float:
        return self._average(lambda estimate: estimate.yards_on_success)

    @property
    def incomplete_probability(self) -> float:
        return self._average(lambda estimate: estimate.incomplete_probability)

    @property
    def turnover_probability(self) -> float:
        return self._average(lambda estimate: estimate.turnover_probability)

    def first_down_probability(self, yards_to_go: float) -> float:
        return self._average(lambda estimate: estimate.first_down_probability(yards_to_go))


def defense_call_weights(
    state: FootballMatchState, defense_side: FootballTeamSide
) -> tuple[tuple[DefensiveSchemeAction, float], ...]:
    """One representative call per family the defense owns, weighted by its copies.

    Counts every owned scheme copy in the defending team's deck (never its hand or
    its active call). Without a deck, each family counts once.
    """
    deck = getattr(state, f"{defense_side.value}_defense_deck")
    counts: dict[FootballCardFamily, int] = {}
    representative: dict[FootballCardFamily, DefensiveSchemeAction] = {}
    if isinstance(deck, FootballDeckState):
        for card in deck.owned:
            definition = DEFENSIVE_SCHEME_CATALOG.get(card.card_id)
            if definition is None:
                continue
            family = DEFENSIVE_SCHEME_FAMILIES[definition.action]
            counts[family] = counts.get(family, 0) + 1
            representative.setdefault(family, definition.action)
    if not counts:
        for scheme, family in DEFENSIVE_SCHEME_FAMILIES.items():
            if family not in counts:
                counts[family] = 1
                representative[family] = scheme
    total = sum(counts.values())
    return tuple(
        (representative[family], counts[family] / total)
        for family in FootballCardFamily
        if family in counts
    )


def calculate_blind_play_estimate(
    state: FootballMatchState,
    play: OffensivePlayAction,
    *,
    offense_side: FootballTeamSide | None = None,
    is_conversion: bool = False,
) -> FootballBlindPlayEstimate:
    """The offense's estimate without knowing the defense's real call.

    Averages ``calculate_match_play_estimate`` over the defending team's possible
    calls, weighted by its whole owned defensive deck. It never reads the active
    call (``current_drive_defensive_scheme``), so changing that call leaves the
    result unchanged. Previews and AI offense use this; resolution uses the real
    call.
    """
    if not isinstance(state, FootballMatchState):
        raise ValueError("Play estimate requires a FootballMatchState.")
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Play estimate requires an offensive play.")
    side = offense_side or state.possession
    components = tuple(
        (
            weight,
            calculate_match_play_estimate(
                state, play, scheme=scheme, offense_side=side, is_conversion=is_conversion,
            ),
        )
        for scheme, weight in defense_call_weights(state, _opponent(side))
    )
    first = components[0][1]
    return FootballBlindPlayEstimate(
        family=first.family,
        components=components,
        player_perks=tuple(
            activation for activation in first.player_perks
            if scheme_keyed_defense(activation) is None
        ),
        keep_read=first.keep_read,
    )


# Coach-perk effect lines that fire only when the defense's call stops the play;
# the offense must not see them while the defense's call is secret.
SCHEME_KEYED_COACH_EFFECT_PREFIXES = ("Coverage:", "Pressure / Blitz:", "Run Stop:")


def _play_perk_effect_messages(
    estimate: FootballPlayEstimate,
    play: OffensivePlayAction,
    *,
    incomplete: bool,
    turnover: bool,
) -> tuple[str, ...]:
    active = estimate.active_perks
    effects: list[str] = []
    if FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS in active:
        effects.append("Coverage: +5 percentage points to incompletion chance")
    if FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS in active:
        effects.append("Pressure / Blitz: +5 percentage points to interception chance")
    if FootballCoachPerkKind.FIRST_RUN_YARDS in active:
        effects.append(
            "Ground and Pound: first run attempt used; turnover prevented the bonus"
            if turnover
            else "Ground and Pound: +3 yards on the first run"
        )
    if not incomplete and not turnover:
        if FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS in active:
            effects.append("Air Raid: +3 yards on the first completed pass")
        if FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS in active:
            effects.append("Pro Style: +2 yards on a first-down pass")
        if (
            estimate.family is FootballCardFamily.RB_RUN
            and FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION in active
        ):
            effects.append("Run Stop: -2 yards on RB Run vs. RB Run scheme")
        if FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS in active:
            effects.append("Option / Spread: +1 yard on a fourth-down play")
    return tuple(effects)


def _adjusted_player_power(
    player: FootballPlayer,
    prior_plays: int,
    *,
    stamina_bonus: float = 0.0,
    power_delta: float = 0.0,
) -> float:
    """Base power plus flat perk power (floor 0), then fatigue."""
    ramp = min(prior_plays / FATIGUE_RAMP_PLAYS, 1.0)
    effective_stamina = effective_player_stamina(player, stamina_bonus)
    reduction = ramp * MAX_FATIGUE_POWER_REDUCTION * (1.0 - effective_stamina)
    return max(0.0, player.power + power_delta) * (1.0 - reduction)


def calculate_matchup_power(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    prior_plays: int = 0,
    offense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    defense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    perk_inputs: FootballPerkEstimateInputs = NO_PERK_INPUTS,
) -> FootballMatchupPower:
    if not isinstance(offense_roster, FootballRoster) or not isinstance(
        defense_roster, FootballRoster
    ):
        raise ValueError("Matchup power requires two football rosters.")
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Matchup power requires an offensive play.")
    if not isinstance(scheme, DefensiveSchemeAction):
        raise ValueError("Matchup power requires a defensive scheme.")
    if isinstance(prior_plays, bool) or not isinstance(prior_plays, int) or prior_plays < 0:
        raise ValueError("Prior plays must be a non-negative integer.")

    offense_positions = OFFENSIVE_PLAY_CATALOG[play.value].contributors
    defense_positions = DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
    offense_players = tuple(
        offense_roster.players[position] for position in offense_positions
    )
    defense_players = tuple(
        defense_roster.players[position] for position in defense_positions
    )
    offense_coach, _ = coaches_for_assignment(offense_roster.coach_assignment)
    _, defense_coach = coaches_for_assignment(defense_roster.coach_assignment)
    offense_stamina_bonus = coach_stamina_bonus(offense_coach_upgrades, offense=True)
    defense_stamina_bonus = coach_stamina_bonus(defense_coach_upgrades, offense=False)
    offense_power = sum(
        _adjusted_player_power(
            player,
            prior_plays,
            stamina_bonus=offense_stamina_bonus,
            power_delta=perk_inputs.power_delta("offense", player.position),
        )
        * player_contribution_modifier(
            player,
            offense_players,
            offense_coach.position_modifiers[player.position]
            if offense_coach is not None
            else 0.0,
        )
        for player in offense_players
    )
    defense_power = sum(
        _adjusted_player_power(
            player,
            prior_plays,
            stamina_bonus=defense_stamina_bonus,
            power_delta=perk_inputs.power_delta("defense", player.position),
        )
        * player_contribution_modifier(
            player,
            defense_players,
            defense_coach.position_modifiers[player.position]
            if defense_coach is not None
            else 0.0,
        )
        for player in defense_players
    )
    matches = (
        _scheme_matches_play(scheme, play)
        if perk_inputs.counter is None
        else perk_inputs.counter
    )
    if matches:
        defense_power *= MATCHED_SCHEME_DEFENSE_MULTIPLIER
        offense_power *= MATCHED_SCHEME_OFFENSE_MULTIPLIER
    offense_power *= coach_power_multiplier(offense_coach_upgrades, offense=True)
    defense_power *= coach_power_multiplier(defense_coach_upgrades, offense=False)
    return FootballMatchupPower(offense_power, defense_power, matches)


def _complete_match(state: FootballMatchState) -> FootballMatchState:
    if state.team_a_score == state.team_b_score:
        raise ValueError("A completed match cannot end in a tie.")
    winner = (
        FootballTeamSide.TEAM_A
        if state.team_a_score > state.team_b_score
        else FootballTeamSide.TEAM_B
    )
    return replace(
        state,
        status=FootballMatchStatus.COMPLETED,
        awaited_action=None,
        current_drive_defensive_scheme=None,
        final_result=FootballMatchResult(
            team_a_score=state.team_a_score,
            team_b_score=state.team_b_score,
            winner=winner,
            completed=True,
        ),
    )


def _advance_period_if_expired(
    state: FootballMatchState, rng: random.Random
) -> FootballMatchState:
    if (
        state.status is FootballMatchStatus.COMPLETED
        or state.game_clock_seconds > 0
        or state.awaited_action is FootballAwaitedAction.CONVERSION
    ):
        return state
    if state.period == 1:
        # Halftime ends the drive. The team that received the opening kickoff
        # kicks to start period 2 (``_reset_for_period_boundary`` resolves the
        # kickoff); until then the receiving team holds a placeholder spot.
        assert state.opening_possession is not None
        return replace(
            state,
            period=2,
            game_clock_seconds=REGULATION_PERIOD_SECONDS,
            possession=_opponent(state.opening_possession),
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
            conversion_team=None,
        )
    if state.period == 2 and state.team_a_score != state.team_b_score:
        return _complete_match(state)
    if state.period >= 2:
        return replace(
            state,
            period=state.period + 1,
            game_clock_seconds=OVERTIME_PERIOD_SECONDS,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            possession=rng.choice((FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B)),
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
        )
    raise ValueError(f"Unsupported match period: {state.period}")


def _redeals_hands(previous_period: int, period: int) -> bool:
    """Halftime and the start of overtime reshuffle and redeal every hand."""
    return previous_period in (1, 2) and period == previous_period + 1


def kick_rush_bonus(state: FootballMatchState, kicking_team: FootballTeamSide) -> float:
    """Kick Rush (D5): extra block chance from the receiving team's D-line."""
    entry = team_perks(state, _opponent(kicking_team)).get(FootballPlayerPerkKind.KICK_RUSH)
    return entry[1].value("block") if entry is not None else 0.0


def _after_possession_change(
    state: FootballMatchState,
    *,
    possession: FootballTeamSide,
    field_position: float,
    clock_cost: int,
) -> FootballMatchState:
    field_position = _clamp(field_position, 0.0, GOAL_LINE_YARDS)
    if field_position == GOAL_LINE_YARDS:
        # A non-scoring drive cannot start on the goal line with positive yards to go.
        field_position = MAX_NONSCORING_RETURN_FIELD_POSITION
    return replace(
        state,
        possession=possession,
        down=1,
        yards_to_go=min(FIRST_DOWN_YARDS, _drive_yards_remaining(field_position)),
        offense_field_position=field_position,
        game_clock_seconds=max(0, state.game_clock_seconds - clock_cost),
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
    )


def _record_event(
    state: FootballMatchState,
    *,
    action: (
        OffensivePlayAction
        | FootballBonusCardAction
        | DefensiveSchemeAction
        | FootballFourthDownAction
        | FootballConversionAction
        | FootballAutomaticAction
        | FootballPerkDecision
    ),
    play_result: FootballPlayResult | None = None,
    points_scored: int = 0,
    scoring_team: FootballTeamSide | None = None,
    field_goal_distance: float | None = None,
    clock_seconds_used: int = 0,
    perk_effects: tuple[str, ...] = (),
    description: str | None = None,
    gross_yards: float | None = None,
    return_yards: float | None = None,
    blocked: bool = False,
    card_id: str | None = None,
    card_copy_id: str | None = None,
    reverses_event_sequences: tuple[int, ...] = (),
    perk_activations: tuple[FootballPerkActivation, ...] = (),
) -> FootballMatchState:
    event = FootballMatchEvent(
        sequence=len(state.match_events) + 1,
        action=action,
        team_a_score=state.team_a_score,
        team_b_score=state.team_b_score,
        possession=state.possession,
        offense_field_position=state.offense_field_position,
        down=state.down,
        yards_to_go=state.yards_to_go,
        game_clock_seconds=state.game_clock_seconds,
        period=state.period,
        status=state.status,
        clock_seconds_used=clock_seconds_used,
        play_result=play_result,
        points_scored=points_scored,
        scoring_team=scoring_team,
        field_goal_distance=field_goal_distance,
        perk_effects=perk_effects,
        description=description,
        gross_yards=gross_yards,
        return_yards=return_yards,
        blocked=blocked,
        card_id=card_id,
        card_copy_id=card_copy_id,
        reverses_event_sequences=reverses_event_sequences,
        perk_activations=perk_activations,
    )
    events = state.match_events + (event,)
    first = events[0]
    score_a = first.team_a_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_A else 0
    )
    score_b = first.team_b_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_B else 0
    )
    reversed_sequences: set[int] = set()
    for recorded_event in events:
        for sequence in recorded_event.reverses_event_sequences:
            if sequence in reversed_sequences:
                continue
            reversed_event = events[sequence - 1]
            if reversed_event.scoring_team is FootballTeamSide.TEAM_A:
                score_a -= reversed_event.points_scored
            elif reversed_event.scoring_team is FootballTeamSide.TEAM_B:
                score_b -= reversed_event.points_scored
            reversed_sequences.add(sequence)
        if recorded_event.sequence not in reversed_sequences:
            if recorded_event.scoring_team is FootballTeamSide.TEAM_A:
                score_a += recorded_event.points_scored
            elif recorded_event.scoring_team is FootballTeamSide.TEAM_B:
                score_b += recorded_event.points_scored
        if (recorded_event.team_a_score, recorded_event.team_b_score) != (
            score_a,
            score_b,
        ):
            raise ValueError("Match event scores do not reconcile with scoring events.")
    if (state.team_a_score, state.team_b_score) != (score_a, score_b):
        raise ValueError("Match state scores do not match the recorded event history.")
    return replace(state, match_events=events)


def _add_score(
    state: FootballMatchState, team: FootballTeamSide, points: int
) -> FootballMatchState:
    return replace(
        state,
        team_a_score=state.team_a_score + (points if team is FootballTeamSide.TEAM_A else 0),
        team_b_score=state.team_b_score + (points if team is FootballTeamSide.TEAM_B else 0),
    )


class FootballMatchSimulator:
    """Resolve caller-provided match actions against a persistent seeded RNG."""

    def __init__(self, match_state: FootballMatchState):
        if not isinstance(match_state, FootballMatchState):
            raise ValueError("Match state must be a FootballMatchState.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.game_clock_seconds == 0
        ):
            raise ValueError("An in-progress match cannot start with an expired period clock.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.period >= 3
            and match_state.team_a_score != match_state.team_b_score
        ):
            raise ValueError("An in-progress overtime match must start tied.")
        self.state = match_state
        self.rng = random.Random(match_state.random_seed)
        self._deck_rngs = {
            "team_a_offense": random.Random(match_state.random_seed ^ 0xA110),
            "team_a_defense": random.Random(match_state.random_seed ^ 0xA120),
            "team_b_offense": random.Random(match_state.random_seed ^ 0xB110),
            "team_b_defense": random.Random(match_state.random_seed ^ 0xB120),
        }
        self._challenge_snapshot: FootballMatchState | None = None
        self._challenge_play_copy_id: str | None = None
        self._initialize_decks()

    # -- save data -------------------------------------------------------------
    # Every attribute set in ``__init__`` is saved: the match state, the play
    # RNG, all four deck RNGs (exact states, so shuffles continue identically),
    # and the pending Challenge rollback snapshot and its played card copy.

    _DECK_RNG_KEYS = ("team_a_offense", "team_a_defense", "team_b_offense", "team_b_defense")

    def to_save_data(self) -> dict[str, Any]:
        return {
            "state": match_state_to_save_data(self.state),
            "rng": rng_to_data(self.rng),
            "deck_rngs": {key: rng_to_data(self._deck_rngs[key]) for key in self._DECK_RNG_KEYS},
            "challenge_snapshot": (
                match_state_to_save_data(
                    self._challenge_snapshot, events_prefix_of=self.state
                )
                if self._challenge_snapshot is not None else None
            ),
            "challenge_play_copy_id": self._challenge_play_copy_id,
        }

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballMatchSimulator":
        """Restore a simulator mid-match without re-dealing or re-seeding anything."""
        what = "Match simulator"
        state = match_state_from_save_data(required(data, "state", dict, what))
        deck_rngs = required(data, "deck_rngs", dict, what)
        snapshot = optional(data, "challenge_snapshot", dict, what)
        simulator = cls.__new__(cls)
        simulator.state = state
        simulator.rng = rng_from_data(required(data, "rng", list, what), "match RNG")
        simulator._deck_rngs = {
            key: rng_from_data(required(deck_rngs, key, list, what), f"{key} deck RNG")
            for key in cls._DECK_RNG_KEYS
        }
        simulator._challenge_snapshot = (
            match_state_from_save_data(snapshot, events_prefix_of=state)
            if snapshot is not None else None
        )
        simulator._challenge_play_copy_id = optional(
            data, "challenge_play_copy_id", str, what
        )
        return simulator

    def _initialize_decks(self) -> None:
        changes: dict[str, FootballDeckState] = {}
        for side in FootballTeamSide:
            for offensive in (True, False):
                group = "offense" if offensive else "defense"
                field_name = f"{side.value}_{group}_deck"
                deck = getattr(self.state, field_name)
                if deck is None:
                    owned = (
                        starting_offensive_deck(side.value)
                        if offensive
                        else starting_defensive_deck(side.value)
                    )
                    deck = FootballDeckState(owned)
                catalog_ids = (
                    set(OFFENSIVE_PLAY_CATALOG)
                    | (
                        set(BONUS_CARD_CATALOG)
                        if side is FootballTeamSide.TEAM_A
                        else set()
                    )
                    if offensive
                    else set(DEFENSIVE_SCHEME_CATALOG)
                )
                if any(card.card_id not in catalog_ids for card in deck.owned):
                    raise ValueError(f"{group.title()} deck contains an unknown card.")
                if not (deck.draw_pile or deck.hand or deck.discard_pile):
                    deck = self._deal_deck(
                        deck.owned,
                        self._deck_rngs[f"{side.value}_{group}"],
                        3 if offensive else 2,
                    )
                changes[field_name] = deck
        if any(getattr(self.state, field) != deck for field, deck in changes.items()):
            self.state = replace(self.state, **changes)

    @staticmethod
    def _deck_field(side: FootballTeamSide, *, offensive: bool) -> str:
        return f"{side.value}_{'offense' if offensive else 'defense'}_deck"

    def _deck_for(
        self, side: FootballTeamSide, *, offensive: bool
    ) -> FootballDeckState:
        deck = getattr(self.state, self._deck_field(side, offensive=offensive))
        if not isinstance(deck, FootballDeckState):
            raise RuntimeError("The match deck was not initialized.")
        return deck

    def _set_deck(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        deck: FootballDeckState,
    ) -> None:
        self.state = replace(
            self.state,
            **{self._deck_field(side, offensive=offensive): deck},
        )

    @staticmethod
    def _deal_deck(
        owned: tuple[FootballCardCopy, ...],
        rng: random.Random,
        hand_size: int,
    ) -> FootballDeckState:
        cards = list(owned)
        rng.shuffle(cards)
        hand = tuple(cards[:hand_size])
        return FootballDeckState(
            owned=owned,
            draw_pile=tuple(cards[hand_size:]),
            hand=hand,
        )

    def _select_offensive_card(
        self, selection: OffensivePlayAction | str | None
    ) -> tuple[OffensivePlayAction, FootballCardCopy | None]:
        deck = self._deck_for(self.state.possession, offensive=True)
        selected: FootballCardCopy | None = None
        action: OffensivePlayAction | None = None
        if isinstance(selection, OffensivePlayAction):
            action = selection
            selected = next(
                (
                    card
                    for card in deck.hand
                    if card.card_id in OFFENSIVE_PLAY_CATALOG
                    and OFFENSIVE_PLAY_CATALOG[card.card_id].action is action
                ),
                None,
            )
            if selected is None and any(
                card.card_id in OFFENSIVE_PLAY_CATALOG for card in deck.hand
            ):
                raise ValueError("Offensive play is not available in the current hand.")
        elif isinstance(selection, str):
            selected = next(
                (card for card in deck.hand if card.copy_id == selection),
                None,
            )
            if selected is None:
                raise ValueError("Offensive card is not in the current hand.")
            definition = OFFENSIVE_PLAY_CATALOG.get(selected.card_id)
            if definition is None:
                raise ValueError("A bonus action cannot be used as a football play.")
            action = definition.action
        elif selection is not None:
            raise ValueError("Offensive selection must be a card id, play, or None.")

        if selected is None:
            if any(card.card_id in OFFENSIVE_PLAY_CATALOG for card in deck.hand):
                raise ValueError("The fallback is available only when the hand is empty.")
            if action not in (None, OffensivePlayAction.RB_RUN):
                raise ValueError("The empty-hand fallback is the basic inside run.")
            return OffensivePlayAction.RB_RUN, None
        return action, selected

    def _select_scheme_card(
        self, selection: DefensiveSchemeAction | str | None
    ) -> tuple[DefensiveSchemeAction, FootballCardCopy | None]:
        side = _opponent(self.state.possession)
        deck = self._deck_for(side, offensive=False)
        selected: FootballCardCopy | None = None
        action: DefensiveSchemeAction | None = None
        if isinstance(selection, DefensiveSchemeAction):
            action = selection
            selected = next(
                (
                    card
                    for card in deck.hand
                    if DEFENSIVE_SCHEME_CATALOG[card.card_id].action is action
                ),
                None,
            )
            if selected is None and deck.hand:
                raise ValueError("Defensive scheme is not available in the current hand.")
        elif isinstance(selection, str):
            selected = next(
                (card for card in deck.hand if card.copy_id == selection),
                None,
            )
            if selected is None:
                raise ValueError("Defensive card is not in the current hand.")
            action = DEFENSIVE_SCHEME_CATALOG[selected.card_id].action
        elif selection is not None:
            raise ValueError("Defensive selection must be a card id, scheme, or None.")

        if selected is None:
            if deck.hand:
                raise ValueError("The fallback is available only when the hand is empty.")
            if action not in (None, DefensiveSchemeAction.RB_RUN):
                raise ValueError("The empty-hand fallback is the basic run-fit scheme.")
            return DefensiveSchemeAction.RB_RUN, None
        return action, selected

    def _cycle_played_card(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        card: FootballCardCopy | None,
        draw_replacement: bool = True,
    ) -> None:
        deck = self._deck_for(side, offensive=offensive)
        hand = list(deck.hand)
        discard = list(deck.discard_pile)
        if card is not None:
            hand.remove(card)
            discard.append(card)
        rng = self._deck_rngs[
            f"{side.value}_{'offense' if offensive else 'defense'}"
        ]
        draw_pile = list(deck.draw_pile)
        if draw_replacement and not draw_pile and discard:
            rng.shuffle(discard)
            draw_pile, discard = discard, []
        if draw_replacement and draw_pile:
            hand.append(draw_pile.pop(0))
        self._set_deck(
            side,
            offensive=offensive,
            deck=FootballDeckState(
                owned=deck.owned,
                draw_pile=tuple(draw_pile),
                hand=tuple(hand),
                discard_pile=tuple(discard),
            ),
        )

    def _draw_one_into_hand(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        excluded_copy_ids: frozenset[str] = frozenset(),
    ) -> bool:
        deck = self._deck_for(side, offensive=offensive)
        draw_pile = [
            card
            for card in deck.draw_pile
            if card.copy_id not in excluded_copy_ids
        ]
        discard = list(deck.discard_pile) + [
            card
            for card in deck.draw_pile
            if card.copy_id in excluded_copy_ids
        ]
        if not draw_pile and discard:
            rng = self._deck_rngs[
                f"{side.value}_{'offense' if offensive else 'defense'}"
            ]
            eligible_discard = [
                card
                for card in discard
                if card.copy_id not in excluded_copy_ids
            ]
            protected_discard = [
                card
                for card in discard
                if card.copy_id in excluded_copy_ids
            ]
            rng.shuffle(eligible_discard)
            draw_pile, discard = eligible_discard, protected_discard
        if not draw_pile:
            return False
        hand = list(deck.hand)
        hand.append(draw_pile.pop(0))
        self._set_deck(
            side,
            offensive=offensive,
            deck=FootballDeckState(
                owned=deck.owned,
                draw_pile=tuple(draw_pile),
                hand=tuple(hand),
                discard_pile=tuple(discard),
            ),
        )
        return True

    def _has_drawable_card(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        excluded_copy_ids: frozenset[str] = frozenset(),
    ) -> bool:
        deck = self._deck_for(side, offensive=offensive)
        return any(
            card.copy_id not in excluded_copy_ids
            for card in deck.draw_pile + deck.discard_pile
        )

    # -- card perks and the end-of-drive trim ------------------------------------
    # These work for either team; every draw goes through the existing
    # draw/reshuffle helpers and every random pick uses the deck's own RNG,
    # except perks whose "random card" is the rival's (match RNG, like Opponent
    # Discard).

    def _with_current_decks(self, state: FootballMatchState) -> FootballMatchState:
        return replace(
            state,
            team_a_offense_deck=self.state.team_a_offense_deck,
            team_a_defense_deck=self.state.team_a_defense_deck,
            team_b_offense_deck=self.state.team_b_offense_deck,
            team_b_defense_deck=self.state.team_b_defense_deck,
        )

    def _draw_cards(self, side: FootballTeamSide, *, offensive: bool, count: int) -> int:
        drawn = 0
        for _ in range(count):
            if not self._draw_one_into_hand(side, offensive=offensive):
                break
            drawn += 1
        return drawn

    def _pull_family_card(self, side: FootballTeamSide, family: FootballCardFamily) -> bool:
        """Mesh Read: the first ``family`` card in the draw pile, else the discard, joins the hand."""
        deck = self._deck_for(side, offensive=True)

        def matches(card: FootballCardCopy) -> bool:
            definition = OFFENSIVE_PLAY_CATALOG.get(card.card_id)
            return definition is not None and definition.family is family

        for zone in ("draw_pile", "discard_pile"):
            cards = getattr(deck, zone)
            card = next((card for card in cards if matches(card)), None)
            if card is not None:
                self._set_deck(side, offensive=True, deck=replace(
                    deck,
                    hand=deck.hand + (card,),
                    **{zone: tuple(other for other in cards if other != card)},
                ))
                return True
        return False

    def _churn_random_card(
        self, side: FootballTeamSide, *, offensive: bool, replace_card: bool = True
    ) -> bool:
        """The rival discards a random hand card (match RNG) and, usually, draws a replacement."""
        deck = self._deck_for(side, offensive=offensive)
        if not deck.hand:
            return False
        discarded = self.rng.choice(deck.hand)
        self._set_deck(side, offensive=offensive, deck=replace(
            deck,
            hand=tuple(card for card in deck.hand if card != discarded),
            discard_pile=deck.discard_pile + (discarded,),
        ))
        if replace_card:
            self._draw_one_into_hand(
                side, offensive=offensive, excluded_copy_ids=frozenset((discarded.copy_id,))
            )
        return True

    def _normalize_hand(self, side: FootballTeamSide, *, offensive: bool) -> None:
        """Trim a hand to its deal size at random (deck RNG), or refill it by drawing."""
        size = 3 if offensive else 2
        deck = self._deck_for(side, offensive=offensive)
        if len(deck.hand) > size:
            rng = self._deck_rngs[f"{side.value}_{'offense' if offensive else 'defense'}"]
            extras = rng.sample(deck.hand, len(deck.hand) - size)
            self._set_deck(side, offensive=offensive, deck=replace(
                deck,
                hand=tuple(card for card in deck.hand if card not in extras),
                discard_pile=deck.discard_pile + tuple(extras),
            ))
            return
        for _ in range(size - len(deck.hand)):
            if not self._draw_one_into_hand(side, offensive=offensive):
                break

    def _end_drive(
        self,
        offensive_side: FootballTeamSide,
        scheme: DefensiveSchemeAction | None,
        *,
        touchdown_scored: bool,
        redeal: bool,
    ) -> list[FootballPerkActivation]:
        """End-of-drive card work: Hold the Front, then both hands back to 3 and 2.

        Halftime and overtime redeal every hand instead, so they skip it.
        """
        if redeal:
            return []
        activations: list[FootballPerkActivation] = []
        defensive_side = _opponent(offensive_side)
        entry = team_perks(self.state, defensive_side).get(FootballPlayerPerkKind.HOLD_THE_FRONT)
        if (
            entry is not None
            and not touchdown_scored
            and scheme is not None
            and DEFENSIVE_SCHEME_FAMILIES[scheme] is FootballCardFamily.RB_RUN
        ):
            copy_id = self._active_scheme_copy_id()
            deck = self._deck_for(defensive_side, offensive=False)
            card = next((card for card in deck.discard_pile if card.copy_id == copy_id), None)
            if card is not None:
                self._set_deck(defensive_side, offensive=False, deck=replace(
                    deck,
                    hand=deck.hand + (card,),
                    discard_pile=tuple(other for other in deck.discard_pile if other != card),
                ))
                activations.append(FootballPerkActivation(
                    FootballPlayerPerkKind.HOLD_THE_FRONT, defensive_side,
                ))
        self._normalize_hand(offensive_side, offensive=True)
        self._normalize_hand(defensive_side, offensive=False)
        return activations

    def _active_scheme_copy_id(self) -> str | None:
        """The card copy of the scheme in force (its drive's scheme event or Green Dog swap)."""
        for event in reversed(self.state.match_events):
            if event.action is FootballPerkDecision.GREEN_DOG_SWAP:
                return event.card_copy_id
            if isinstance(event.action, DefensiveSchemeAction):
                return event.card_copy_id
        return None

    def _offer_green_dog(
        self,
        pre: FootballMatchState,
        defensive_side: FootballTeamSide,
        *,
        converted: bool,
        previous_period: int,
    ) -> None:
        """Green Dog (L6): after a rival 3rd/4th-down conversion, offer a scheme swap."""
        state = self.state
        if (
            not converted
            or state.status is not FootballMatchStatus.IN_PROGRESS
            or state.period != previous_period
            or state.game_clock_seconds <= 0
            or state.awaited_action is not FootballAwaitedAction.OFFENSIVE_PLAY
            or state.possession is not pre.possession
            or FootballPlayerPerkKind.GREEN_DOG not in team_perks(state, defensive_side)
            or perk_history(state).used(FootballPlayerPerkKind.GREEN_DOG, defensive_side, "game")
            or not self._deck_for(defensive_side, offensive=False).hand
        ):
            return
        self.state = replace(state, awaited_action=FootballAwaitedAction.GREEN_DOG_DECISION)

    def resolve_green_dog(self, selection: str | DefensiveSchemeAction | None) -> FootballMatchState:
        """Answer a Green Dog offer: a scheme card (copy id or action) to swap in, or None."""
        self._require_action(FootballAwaitedAction.GREEN_DOG_DECISION)
        defensive_side = _opponent(self.state.possession)
        deck = self._deck_for(defensive_side, offensive=False)
        resumed = replace(self.state, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY)
        if selection is None:
            self.state = _record_event(resumed, action=FootballPerkDecision.GREEN_DOG_DECLINE)
            return self.state
        if isinstance(selection, DefensiveSchemeAction):
            card = next(
                (card for card in deck.hand
                 if DEFENSIVE_SCHEME_CATALOG[card.card_id].action is selection),
                None,
            )
        elif isinstance(selection, str):
            card = next((card for card in deck.hand if card.copy_id == selection), None)
        else:
            raise ValueError("Green Dog selection must be a scheme card, scheme, or None.")
        if card is None:
            raise ValueError("Green Dog can only swap in a scheme from the defense's hand.")
        new_scheme = DEFENSIVE_SCHEME_CATALOG[card.card_id].action
        self.state = _record_event(
            replace(resumed, current_drive_defensive_scheme=new_scheme),
            action=FootballPerkDecision.GREEN_DOG_SWAP,
            card_id=card.card_id,
            card_copy_id=card.copy_id,
            perk_activations=(
                FootballPerkActivation(FootballPlayerPerkKind.GREEN_DOG, defensive_side),
            ),
        )
        self._cycle_played_card(defensive_side, offensive=False, card=card)
        return self.state

    @property
    def available_challenge_copy_id(self) -> str | None:
        if (
            self._challenge_snapshot is None
            or self.state.status is FootballMatchStatus.COMPLETED
            or self.state.game_clock_seconds <= 0
            or self._challenge_snapshot.period != self.state.period
        ):
            return None
        deck = self._deck_for(FootballTeamSide.TEAM_A, offensive=True)
        card = next(
            (
                card.copy_id
                for card in deck.hand
                if card.card_id == FootballBonusCardAction.CHALLENGE.value
            ),
            None,
        )
        excluded = frozenset(
            copy_id
            for copy_id in (card, self._challenge_play_copy_id)
            if copy_id is not None
        )
        return (
            card
            if card is not None
            and self._has_drawable_card(
                FootballTeamSide.TEAM_A,
                offensive=True,
                excluded_copy_ids=excluded,
            )
            else None
        )

    def resolve_bonus_card(self, copy_id: str) -> FootballMatchState:
        if not isinstance(copy_id, str) or not copy_id.strip():
            raise ValueError("Bonus-card selection must be a card copy id.")
        deck = self._deck_for(FootballTeamSide.TEAM_A, offensive=True)
        selected = next((card for card in deck.hand if card.copy_id == copy_id), None)
        if selected is None or selected.card_id not in BONUS_CARD_CATALOG:
            raise ValueError("Bonus card is not in the current offensive hand.")
        definition = BONUS_CARD_CATALOG[selected.card_id]
        action = definition.action
        if (
            self.state.status is FootballMatchStatus.COMPLETED
            and action is not FootballBonusCardAction.CHALLENGE
        ):
            raise ValueError("A completed match cannot accept a bonus card.")
        is_defensive_draw = action in (
            FootballBonusCardAction.DEFENSIVE_DRAW,
            FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
        )
        if action is FootballBonusCardAction.CHALLENGE:
            if copy_id != self.available_challenge_copy_id:
                raise ValueError(
                    "Challenge is not available for the current human offensive decision."
                )
            excluded = frozenset(
                copy_id
                for copy_id in (selected.copy_id, self._challenge_play_copy_id)
                if copy_id is not None
            )
            if not self._has_drawable_card(
                FootballTeamSide.TEAM_A,
                offensive=True,
                excluded_copy_ids=excluded,
            ):
                raise ValueError("The offensive deck has no card to replace Challenge.")
        elif self.state.possession is not FootballTeamSide.TEAM_A or (
            self.state.awaited_action is not FootballAwaitedAction.OFFENSIVE_PLAY
        ):
            raise ValueError("Bonus cards can only be played at a human offensive decision.")

        before = self.state
        clock_cost = 0 if action is FootballBonusCardAction.CHALLENGE else 10
        self._cycle_played_card(
            FootballTeamSide.TEAM_A,
            offensive=True,
            card=selected,
            draw_replacement=False,
        )
        if action is FootballBonusCardAction.CHALLENGE:
            if not self._draw_one_into_hand(
                FootballTeamSide.TEAM_A,
                offensive=True,
                excluded_copy_ids=excluded,
            ):
                raise RuntimeError("The offensive deck replacement became unavailable.")
        else:
            # Every other bonus card replaces itself, then a Draw card adds one
            # extra card on top. Neither draw may return the bonus card itself;
            # an empty draw (every other card already in hand) is a no-op.
            own_copy = frozenset((selected.copy_id,))
            self._draw_one_into_hand(
                FootballTeamSide.TEAM_A,
                offensive=True,
                excluded_copy_ids=own_copy,
            )
            if action in _OFFENSIVE_EXTRA_DRAW_ACTIONS:
                self._draw_one_into_hand(
                    FootballTeamSide.TEAM_A,
                    offensive=True,
                    excluded_copy_ids=own_copy,
                )
            elif is_defensive_draw:
                self._draw_one_into_hand(
                    FootballTeamSide.TEAM_A,
                    offensive=False,
                )
        if action in (
            FootballBonusCardAction.OPPONENT_DISCARD,
            FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD,
            FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
        ):
            opponent_deck = self._deck_for(FootballTeamSide.TEAM_B, offensive=False)
            if opponent_deck.hand:
                discarded = self.rng.choice(opponent_deck.hand)
                self._set_deck(
                    FootballTeamSide.TEAM_B,
                    offensive=False,
                    deck=FootballDeckState(
                        owned=opponent_deck.owned,
                        draw_pile=opponent_deck.draw_pile,
                        hand=tuple(
                            card for card in opponent_deck.hand if card != discarded
                        ),
                        discard_pile=opponent_deck.discard_pile + (discarded,),
                    ),
                )

        updated = replace(
            self.state,
            game_clock_seconds=max(0, self.state.game_clock_seconds - clock_cost),
        )
        if action is FootballBonusCardAction.CHALLENGE:
            snapshot = self._challenge_snapshot
            if snapshot is None:
                raise RuntimeError("The challenge snapshot is unavailable.")
            if updated.game_clock_seconds == 0:
                raise ValueError("Challenge cannot restore an expired match clock.")
            reversed_sequences = tuple(
                range(len(snapshot.match_events) + 1, len(self.state.match_events) + 1)
            )
            # Card moves stay after a Challenge, and a Green Dog swap is one: the
            # swapped-in scheme stays active for the restored drive.
            swapped_scheme = next(
                (
                    DEFENSIVE_SCHEME_CATALOG[event.card_id].action
                    for event in reversed(self.state.match_events[len(snapshot.match_events):])
                    if event.action is FootballPerkDecision.GREEN_DOG_SWAP and event.card_id
                ),
                None,
            )
            if swapped_scheme is not None and snapshot.current_drive_defensive_scheme is not None:
                snapshot = replace(snapshot, current_drive_defensive_scheme=swapped_scheme)
            updated = replace(
                snapshot,
                game_clock_seconds=updated.game_clock_seconds,
                team_a_offense_deck=updated.team_a_offense_deck,
                team_a_defense_deck=updated.team_a_defense_deck,
                team_b_offense_deck=updated.team_b_offense_deck,
                team_b_defense_deck=updated.team_b_defense_deck,
                match_events=self.state.match_events,
            )
            description = "Challenge accepted; restored the situation before the last human play."
            self._challenge_snapshot = None
            self._challenge_play_copy_id = None
        else:
            updated = self._finish_action(updated)
            self.state = updated
            self._reset_for_period_boundary(before.period, before.possession)
            updated = self.state
            if (
                self._challenge_snapshot is not None
                and (
                    self.state.status is FootballMatchStatus.COMPLETED
                    or self.state.period != self._challenge_snapshot.period
                )
            ):
                self._challenge_snapshot = None
                self._challenge_play_copy_id = None
            description = definition.description
        self.state = _record_event(
            updated,
            action=action,
            card_id=selected.card_id,
            card_copy_id=selected.copy_id,
            clock_seconds_used=min(before.game_clock_seconds, clock_cost),
            description=description,
            reverses_event_sequences=(
                reversed_sequences
                if action is FootballBonusCardAction.CHALLENGE
                else ()
            ),
        )
        return self.state

    def decline_challenge(self) -> None:
        if self._challenge_snapshot is None:
            raise ValueError("There is no human offensive play available to challenge.")
        self._challenge_snapshot = None
        self._challenge_play_copy_id = None

    def _finish_play_action(
        self,
        state: FootballMatchState,
        offensive_side: FootballTeamSide,
        card: FootballCardCopy | None,
        *,
        previous_period: int,
        challengeable: bool = False,
    ) -> FootballMatchState:
        self.state = state
        self._reset_for_period_boundary(previous_period, offensive_side)
        has_next_human_offensive_decision = (
            self._challenge_snapshot is not None
            and offensive_side is FootballTeamSide.TEAM_A
            and self.state.status is FootballMatchStatus.IN_PROGRESS
            and self.state.period == self._challenge_snapshot.period
            and self.state.possession is FootballTeamSide.TEAM_A
            and self.state.awaited_action
            in (
                FootballAwaitedAction.OFFENSIVE_PLAY,
                FootballAwaitedAction.FOURTH_DOWN_DECISION,
                FootballAwaitedAction.CONVERSION,
                FootballAwaitedAction.GREEN_DOG_DECISION,
            )
        )
        has_immediate_challenge_prompt = (
            challengeable
            and offensive_side is FootballTeamSide.TEAM_A
            and self._challenge_snapshot is not None
            and self.state.status is FootballMatchStatus.IN_PROGRESS
            and self.state.period == self._challenge_snapshot.period
        )
        if not has_immediate_challenge_prompt and not has_next_human_offensive_decision:
            self._challenge_snapshot = None
            self._challenge_play_copy_id = None
        return self.state

    def _reset_for_period_boundary(
        self, previous_period: int, previous_possession: FootballTeamSide | None = None
    ) -> None:
        """After a period ends: redeal (halftime, overtime), kick off period 2,
        or end the drive cut short by a later overtime period."""
        if self.state.period == previous_period:
            return
        if _redeals_hands(previous_period, self.state.period):
            self._reset_all_decks()
            if previous_period == 1 and self.state.status is FootballMatchStatus.IN_PROGRESS:
                assert self.state.opening_possession is not None
                self.state = self._resolve_kickoff(self.state, self.state.opening_possession)
        elif (
            previous_possession is not None
            and self.state.status is FootballMatchStatus.IN_PROGRESS
        ):
            self._end_drive(previous_possession, None, touchdown_scored=False, redeal=False)

    def _reset_all_decks(self) -> None:
        changes: dict[str, FootballDeckState] = {}
        for side in FootballTeamSide:
            for offensive in (True, False):
                group = "offense" if offensive else "defense"
                field_name = self._deck_field(side, offensive=offensive)
                current = getattr(self.state, field_name)
                if not isinstance(current, FootballDeckState):
                    raise RuntimeError("The match deck was not initialized.")
                changes[field_name] = self._deal_deck(
                    current.owned,
                    self._deck_rngs[f"{side.value}_{group}"],
                    3 if offensive else 2,
                )
        self.state = replace(self.state, **changes)

    def _require_action(self, expected: FootballAwaitedAction) -> None:
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not expected:
            raise ValueError(f"Action is not legal while awaiting {self.state.awaited_action!r}.")
        if (
            self.state.game_clock_seconds == 0
            and expected is not FootballAwaitedAction.CONVERSION
        ):
            raise ValueError("No action is legal after the period clock has expired.")

    def select_defensive_scheme(
        self, scheme: DefensiveSchemeAction | str | None
    ) -> FootballMatchState:
        if self.state.current_drive_defensive_scheme is not None:
            raise ValueError("A defensive scheme cannot be replaced mid-drive.")
        self._require_action(FootballAwaitedAction.DEFENSIVE_SCHEME)
        selected_scheme, selected_card = self._select_scheme_card(scheme)
        offense = self.state.possession
        defense = _opponent(offense)
        activations = self._drive_start_perks(offense, selected_scheme)
        updated = replace(
            self.state,
            current_drive_defensive_scheme=selected_scheme,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        self.state = _record_event(
            updated,
            action=selected_scheme,
            card_id=selected_scheme.value,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
            perk_activations=tuple(activations),
        )
        self._cycle_played_card(defense, offensive=False, card=selected_card)
        if FootballPlayerPerkKind.HOT_ROUTE in team_perks(self.state, offense):
            swapped = self._hot_route(offense, selected_scheme)
            if swapped:
                event = self.state.match_events[-1]
                events = self.state.match_events[:-1] + (replace(
                    event,
                    perk_activations=event.perk_activations + (
                        FootballPerkActivation(FootballPlayerPerkKind.HOT_ROUTE, offense),
                    ),
                ),)
                self.state = replace(self.state, match_events=events)
        return self.state

    def _drive_start_perks(
        self, offense: FootballTeamSide, scheme: DefensiveSchemeAction
    ) -> list[FootballPerkActivation]:
        """Short Field (L5), Breathing Room (O6), and Read Keys (L4) as a drive starts."""
        state = self.state
        defense = _opponent(offense)
        offense_perks = team_perks(state, offense)
        activations: list[FootballPerkActivation] = []
        start = state.offense_field_position
        position = start
        entry = offense_perks.get(FootballPlayerPerkKind.SHORT_FIELD)
        if entry is not None and self._previous_drive_punted_or_downs(offense):
            position += entry[1].value("yards")
            activations.append(FootballPerkActivation(
                FootballPlayerPerkKind.SHORT_FIELD, offense, entry[1].value("yards"),
            ))
        entry = offense_perks.get(FootballPlayerPerkKind.BREATHING_ROOM)
        if entry is not None and state.period <= 2 and start <= entry[1].value("threshold"):
            position += entry[1].value("yards")
            activations.append(FootballPerkActivation(
                FootballPlayerPerkKind.BREATHING_ROOM, offense, entry[1].value("yards"),
            ))
        if position != start:
            position = min(position, MAX_NONSCORING_RETURN_FIELD_POSITION)
            self.state = replace(
                state,
                offense_field_position=position,
                yards_to_go=min(FIRST_DOWN_YARDS, _drive_yards_remaining(position)),
            )
        if FootballPlayerPerkKind.READ_KEYS in team_perks(state, defense):
            activations.append(FootballPerkActivation(FootballPlayerPerkKind.READ_KEYS, defense))
        return activations

    def _previous_drive_punted_or_downs(self, offense: FootballTeamSide) -> bool:
        """Did the rival's drive just end in a punt or on downs (with no kickoff since)?"""
        for event in reversed(self.state.match_events):
            if event.action is FootballAutomaticAction.KICKOFF or isinstance(
                event.action, FootballConversionAction
            ):
                return False
            if event.action is FootballFourthDownAction.PUNT:
                return event.possession is offense
            if event.play_result is not None and event.play_result.turnover_on_downs:
                return event.possession is offense
            if isinstance(event.action, DefensiveSchemeAction):
                return False
        return False

    def _hot_route(self, offense: FootballTeamSide, scheme: DefensiveSchemeAction) -> bool:
        """Hot Route (W1): discard the countered hand card with the lowest expected yards."""
        deck = self._deck_for(offense, offensive=True)
        force_fold = (
            FootballPlayerPerkKind.FORCE_AND_FOLD in team_perks(self.state, _opponent(offense))
            and DEFENSIVE_SCHEME_FAMILIES[scheme] is FootballCardFamily.SCREEN_PASS
        )
        countered = []
        for index, card in enumerate(deck.hand):
            definition = OFFENSIVE_PLAY_CATALOG.get(card.card_id)
            if definition is None:
                continue
            if definition.family is DEFENSIVE_SCHEME_FAMILIES[scheme] or (
                force_fold and definition.family is FootballCardFamily.RB_RUN
            ):
                expected = calculate_match_play_estimate(
                    self.state, definition.action, scheme=scheme
                ).expected_yards
                countered.append((expected, index, card))
        if not countered:
            return False
        _, _, card = min(countered, key=lambda item: (item[0], item[1]))
        self._cycle_played_card(offense, offensive=True, card=card)
        return True

    def resolve_offensive_play(
        self, play: OffensivePlayAction | str | None
    ) -> FootballMatchState:
        if isinstance(play, str):
            offense_deck = self._deck_for(self.state.possession, offensive=True)
            selected_bonus = next(
                (card for card in offense_deck.hand if card.copy_id == play),
                None,
            )
            if selected_bonus is not None and selected_bonus.card_id in BONUS_CARD_CATALOG:
                return self.resolve_bonus_card(play)
        self._require_action(FootballAwaitedAction.OFFENSIVE_PLAY)
        scheme = self.state.current_drive_defensive_scheme
        if scheme is None:
            raise ValueError("A defensive scheme must be chosen before the snap.")
        previous_period = self.state.period
        offensive_side = self.state.possession
        defensive_side = _opponent(offensive_side)
        play, selected_card = self._select_offensive_card(play)
        if offensive_side is FootballTeamSide.TEAM_A:
            self._challenge_snapshot = self.state
            self._challenge_play_copy_id = (
                selected_card.copy_id if selected_card is not None else None
            )

        pre = self.state
        history = perk_history(pre)
        offense_perks = team_perks(pre, offensive_side)
        defense_perks = team_perks(pre, defensive_side)
        K = FootballPlayerPerkKind

        def perk_of(perks, kind):
            entry = perks.get(kind)
            return entry[1] if entry is not None else None

        play_definition = OFFENSIVE_PLAY_CATALOG[play.value]
        family = play_definition.family
        defense_family = DEFENSIVE_SCHEME_FAMILIES[scheme]
        offense_slots = play_definition.contributors
        defense_slots = DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
        estimate = calculate_match_play_estimate(pre, play, scheme=scheme)
        activations: list[FootballPerkActivation] = list(estimate.player_perks)

        def fire(kind, team, value=0.0) -> None:
            activations.append(FootballPerkActivation(kind, team, float(value)))

        def unused(perks, kind, team, scope):
            perk = perk_of(perks, kind)
            if perk is None or history.used(kind, team, scope):
                return None
            return perk

        offense_power = estimate.matchup.offense
        defense_power = estimate.matchup.defense
        # Steps 1-2: the estimate already holds every input perk; roll with the match RNG.
        yards = estimate.yards_on_success + self.rng.uniform(
            -estimate.yardage_spread,
            estimate.yardage_spread,
        )
        turnover = False
        incomplete = False
        sack = False
        turnover_type: FootballTurnoverType | None = None
        if family is not FootballCardFamily.RB_RUN and not estimate.keep_read:
            interception_threshold = (
                estimate.incomplete_probability
                + (1.0 - estimate.incomplete_probability)
                * estimate.turnover_probability
            )

            def roll_catch() -> str:
                roll = self.rng.random()
                if roll < estimate.incomplete_probability:
                    return "incomplete"
                if roll < interception_threshold:
                    return "interception"
                return "catch"

            catch = roll_catch()
            # Step 3: completion reroll.
            if (
                catch != "catch"
                and family is FootballCardFamily.DEEP_PASS
                and unused(offense_perks, K.CONTESTED_CATCH, offensive_side, "game")
            ):
                catch = roll_catch()
                fire(K.CONTESTED_CATCH, offensive_side, 1.0 if catch == "catch" else 0.0)
            # Step 4: result swaps, offense first, then the defense; at most one swap.
            swapped = False
            if (
                catch == "interception"
                and FootballPosition.QB in offense_slots
                and unused(offense_perks, K.PASS_PRO, offensive_side, "game")
            ):
                catch, swapped = "incomplete", True
                fire(K.PASS_PRO, offensive_side)
            if (
                not swapped
                and catch == "incomplete"
                and pre.down >= 3
                and FootballPosition.SAFETIES in defense_slots
                and unused(defense_perks, K.TIP_DRILL, defensive_side, "game")
            ):
                catch, swapped = "interception", True
                fire(K.TIP_DRILL, defensive_side)
            stunt = unused(defense_perks, K.STUNT_SACK, defensive_side, "drive")
            if (
                not swapped
                and catch == "incomplete"
                and stunt is not None
                and FootballPosition.QB in offense_slots
                and FootballPosition.D_LINE in defense_slots
            ):
                catch, swapped = "sack", True
                fire(K.STUNT_SACK, defensive_side, stunt.value("yards"))
            if catch == "incomplete":
                incomplete = True
                yards = 0.0
            elif catch == "interception":
                turnover = True
                turnover_type = FootballTurnoverType.INTERCEPTION
                yards = 0.0
            elif catch == "sack":
                sack = True
                yards = -stunt.value("yards")
        elif self.rng.random() < estimate.turnover_probability:
            turnover = True
            turnover_type = FootballTurnoverType.FUMBLE
            yards = min(yards, 0.0)

        completed = (
            family is not FootballCardFamily.RB_RUN
            and not incomplete and not turnover and not sack
        )
        clean_run = family is FootballCardFamily.RB_RUN and not turnover
        if turnover or incomplete or sack:
            # Additive-yard perks only pay on a gain.
            activations = [
                activation for activation in activations
                if activation.kind not in (K.CHECKDOWN, K.DOWNHILL)
            ]
        # Step 5: yards. Big gain, then the run floor, then defensive caps (which win).
        perk = unused(offense_perks, K.ORBIT_BREAKAWAY, offensive_side, "half")
        if completed and family is FootballCardFamily.SHORT_PASS and perk is not None:
            if self.rng.random() < perk.value("chance"):
                yards = min(MAX_PLAY_YARDAGE, yards + perk.value("yards"))
                fire(K.ORBIT_BREAKAWAY, offensive_side, perk.value("yards"))
        perk = unused(offense_perks, K.FALL_FORWARD, offensive_side, "drive")
        if clean_run and perk is not None and yards < perk.value("yards"):
            yards = perk.value("yards")
            fire(K.FALL_FORWARD, offensive_side, yards)
        perk = perk_of(defense_perks, K.CONTAIN)
        if (
            completed and family is FootballCardFamily.SCREEN_PASS and perk is not None
            and FootballPosition.D_LINE in defense_slots and yards > perk.value("cap")
        ):
            yards = perk.value("cap")
            fire(K.CONTAIN, defensive_side, yards)
        perk = perk_of(defense_perks, K.DEEP_LOCK)
        if (
            completed and defense_family is FootballCardFamily.DEEP_PASS and perk is not None
            and FootballPosition.CORNERBACKS in defense_slots and yards > perk.value("cap")
        ):
            yards = perk.value("cap")
            fire(K.DEEP_LOCK, defensive_side, yards)

        # Step 6: spot. Offense first, then the defense has the last word.
        remaining = _drive_yards_remaining(pre.offense_field_position)
        line_to_gain = max(0.1, min(pre.yards_to_go, remaining))
        goal_to_go = pre.yards_to_go >= remaining
        if completed:
            perk = unused(offense_perks, K.MOVE_THE_STICKS, offensive_side, "half")
            pylon = unused(offense_perks, K.PYLON_REACH, offensive_side, "game")
            if (
                perk is not None and family is FootballCardFamily.SHORT_PASS
                and not goal_to_go and yards < line_to_gain
                and line_to_gain - yards <= perk.value("yards")
            ):
                yards = line_to_gain
                fire(K.MOVE_THE_STICKS, offensive_side)
            elif (
                pylon is not None and FootballPosition.WR in offense_slots
                and yards < remaining
                and pre.offense_field_position + yards >= GOAL_LINE_YARDS - pylon.value("yards")
            ):
                yards = remaining
                fire(K.PYLON_REACH, offensive_side)
        if not turnover and not incomplete:
            perk = unused(defense_perks, K.HOLD_THE_LINE, defensive_side, "half")
            last_line = unused(defense_perks, K.LAST_LINE, defensive_side, "game")
            if (
                perk is not None and pre.down >= 3
                and line_to_gain <= yards < remaining
                and yards - line_to_gain < perk.value("margin")
            ):
                yards = line_to_gain - perk.value("short")
                fire(K.HOLD_THE_LINE, defensive_side)
            elif (
                last_line is not None and yards >= remaining
                and remaining >= last_line.value("distance")
            ):
                yards = remaining - 1.0
                fire(K.LAST_LINE, defensive_side)

        perk_effects = list(_play_perk_effect_messages(
            estimate,
            play,
            incomplete=incomplete,
            turnover=turnover,
        ))

        # Step 7: clock. Card time x coach multiplier, Hurry-Up cap, added seconds.
        offense_upgrades = (
            pre.team_a_coach_upgrades
            if offensive_side is FootballTeamSide.TEAM_A
            else pre.team_b_coach_upgrades
        )
        if incomplete:
            clock_cost = INCOMPLETE_PASS_CLOCK_SECONDS
        else:
            clock_cost = adjusted_offensive_play_clock_seconds(
                play_definition.clock_seconds, offense_upgrades,
            )
            offense_score, defense_score = (
                (pre.team_a_score, pre.team_b_score)
                if offensive_side is FootballTeamSide.TEAM_A
                else (pre.team_b_score, pre.team_a_score)
            )
            perk = perk_of(offense_perks, K.HURRY_UP_CAPTAIN)
            if (
                perk is not None and completed and family in QB_PASS_FAMILIES
                and pre.period <= 2 and pre.game_clock_seconds <= perk.value("window_seconds")
                and clock_cost > perk.value("seconds")
            ):
                clock_cost = int(perk.value("seconds"))
                fire(K.HURRY_UP_CAPTAIN, offensive_side, clock_cost)
            perk = perk_of(offense_perks, K.FOUR_MINUTE_DRILL)
            if perk is not None and clean_run and pre.period == 2 and offense_score > defense_score:
                clock_cost += int(perk.value("seconds"))
                fire(K.FOUR_MINUTE_DRILL, offensive_side, perk.value("seconds"))
            perk = perk_of(defense_perks, K.KEEP_IT_INBOUNDS)
            if perk is not None and completed and pre.period == 2 and defense_score > offense_score:
                clock_cost += int(perk.value("seconds"))
                fire(K.KEEP_IT_INBOUNDS, defensive_side, perk.value("seconds"))
            clock_cost = max(1, clock_cost)

        positive_gain = yards > 0
        if positive_gain:
            yards = min(yards, remaining)
        new_position = pre.offense_field_position + yards
        touchdown = False
        first_down = False
        turnover_on_downs = False
        points_scored = 0
        scoring_team: FootballTeamSide | None = None
        drive_ended = True
        after_safety_kickoff = False
        if new_position <= 0 and yards < 0:
            scoring_team = defensive_side
            points_scored = SAFETY_POINTS
            scored = _add_score(pre, scoring_team, SAFETY_POINTS)
            next_state = _after_possession_change(
                scored,
                possession=scoring_team,
                field_position=TOUCHBACK_START_YARDS,
                clock_cost=clock_cost,
            )
            next_state = self._finish_action(next_state, points=SAFETY_POINTS)
            after_safety_kickoff = True
        elif new_position >= GOAL_LINE_YARDS and positive_gain:
            touchdown = True
            drive_ended = False  # the conversion still belongs to this drive
            scoring_team = offensive_side
            points_scored = TOUCHDOWN_POINTS
            scored = _add_score(pre, scoring_team, TOUCHDOWN_POINTS)
            next_state = self._conversion_state(
                replace(
                    scored,
                    game_clock_seconds=max(0, pre.game_clock_seconds - clock_cost),
                ),
                scoring_team,
                scheme,
            )
        elif turnover:
            return_yards = (
                estimate.interception_return_yards
                if play in _PASS_PLAYS
                else 0.0
            )
            if return_yards:
                perk_effects.append("Ball-Hawk: +10 interception return yards")
            return_field_position = 100.0 - new_position + return_yards
            if return_yards and return_field_position >= GOAL_LINE_YARDS:
                scoring_team = defensive_side
                points_scored = TOUCHDOWN_POINTS
                scored = _add_score(pre, scoring_team, points_scored)
                next_state = self._conversion_state(
                    replace(
                        scored,
                        game_clock_seconds=max(0, pre.game_clock_seconds - clock_cost),
                    ),
                    scoring_team,
                    scheme,
                )
            else:
                next_state = _after_possession_change(
                    pre,
                    possession=defensive_side,
                    field_position=return_field_position,
                    clock_cost=clock_cost,
                )
        else:
            first_down = yards >= line_to_gain
            remaining_goal_distance = _drive_yards_remaining(new_position)
            if first_down:
                next_yards_to_go = min(FIRST_DOWN_YARDS, remaining_goal_distance)
                if next_yards_to_go <= 0:
                    next_yards_to_go = FIRST_DOWN_YARDS
                next_state = replace(
                    pre,
                    down=1,
                    yards_to_go=next_yards_to_go,
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, pre.game_clock_seconds - clock_cost),
                    awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
                )
                drive_ended = False
            elif pre.down == 4:
                turnover_on_downs = True
                next_state = _after_possession_change(
                    pre,
                    possession=defensive_side,
                    field_position=100.0 - new_position,
                    clock_cost=clock_cost,
                )
            else:
                next_down = min(pre.down + 1, 4)
                next_state = replace(
                    pre,
                    down=next_down,
                    yards_to_go=max(0.1, line_to_gain - yards),
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, pre.game_clock_seconds - clock_cost),
                    awaited_action=(
                        FootballAwaitedAction.FOURTH_DOWN_DECISION
                        if next_down == 4
                        else FootballAwaitedAction.OFFENSIVE_PLAY
                    ),
                )
                drive_ended = False
        if not points_scored:
            next_state = self._finish_action(next_state)

        # Step 8: cards. The played card cycles (Outlet Repeat keeps it), then
        # offensive card perks, then defensive ones, then the end-of-drive trim.
        takeaway = turnover or turnover_on_downs
        perk = unused(offense_perks, K.OUTLET_REPEAT, offensive_side, "drive")
        if (
            perk is not None and selected_card is not None
            and family is FootballCardFamily.SHORT_PASS and (first_down or touchdown)
        ):
            fire(K.OUTLET_REPEAT, offensive_side)
        else:
            self._cycle_played_card(offensive_side, offensive=True, card=selected_card)
        if completed and family is FootballCardFamily.PA_PASS and unused(
            offense_perks, K.MESH_READ, offensive_side, "drive"
        ):
            if self._pull_family_card(offensive_side, FootballCardFamily.RB_RUN):
                fire(K.MESH_READ, offensive_side, 1)
        perk = unused(offense_perks, K.OPTION_LEDGER, offensive_side, "game")
        if perk is not None:
            families = {snap.family for snap in history.drive_snaps(offensive_side)}
            if len(families) < perk.value("families") <= len(families | {family}):
                drawn = self._draw_cards(offensive_side, offensive=True, count=int(perk.value("cards")))
                if drawn:
                    fire(K.OPTION_LEDGER, offensive_side, drawn)
        perk = unused(offense_perks, K.RELEASE_READ, offensive_side, "drive")
        if (
            perk is not None and completed and family is FootballCardFamily.SCREEN_PASS
            and yards >= perk.value("yards")
        ):
            if self._churn_random_card(defensive_side, offensive=False):
                fire(K.RELEASE_READ, offensive_side)
        perk = unused(offense_perks, K.TEMPO_READ, offensive_side, "drive")
        if perk is not None and first_down and family is FootballCardFamily.MEDIUM_PASS:
            drawn = self._draw_cards(offensive_side, offensive=True, count=int(perk.value("cards")))
            if drawn:
                fire(K.TEMPO_READ, offensive_side, drawn)
        if completed and family is FootballCardFamily.SCREEN_PASS and unused(
            offense_perks, K.SCREEN_WALL, offensive_side, "drive"
        ):
            fire(K.SCREEN_WALL, offensive_side)
        if (
            pre.down == 3 and not first_down and not touchdown and not takeaway
            and not points_scored
            and unused(defense_perks, K.COLLAPSE, defensive_side, "drive")
        ):
            if self._churn_random_card(offensive_side, offensive=True):
                fire(K.COLLAPSE, defensive_side)
        if (
            incomplete and family is FootballCardFamily.SHORT_PASS
            and FootballPosition.CORNERBACKS in defense_slots
            and unused(defense_perks, K.BRACKET, defensive_side, "game")
        ):
            if self._churn_random_card(offensive_side, offensive=True, replace_card=False):
                fire(K.BRACKET, defensive_side)
        perk = unused(defense_perks, K.FIT_AND_SHED, defensive_side, "drive")
        if (
            perk is not None and not turnover and not touchdown
            and (incomplete or yards <= perk.value("yards"))
            and FootballPosition.LINEBACKERS in defense_slots
        ):
            drawn = self._draw_cards(defensive_side, offensive=False, count=int(perk.value("cards")))
            if drawn:
                fire(K.FIT_AND_SHED, defensive_side, drawn)
        if (
            first_down and family is FootballCardFamily.RB_RUN
            and unused(defense_perks, K.CAPTAINS_ADJUSTMENT, defensive_side, "drive")
        ):
            fire(K.CAPTAINS_ADJUSTMENT, defensive_side)
        perk = perk_of(defense_perks, K.SUDDEN_CHANGE)
        if perk is not None and takeaway:
            drawn = self._draw_cards(defensive_side, offensive=True, count=int(perk.value("cards")))
            if drawn:
                fire(K.SUDDEN_CHANGE, defensive_side, drawn)
        if drive_ended:
            activations.extend(self._end_drive(
                offensive_side, scheme, touchdown_scored=False,
                redeal=_redeals_hands(previous_period, next_state.period),
            ))

        result = FootballPlayResult(
            offensive_play=play,
            yards_gained=yards,
            clock_seconds_used=min(pre.game_clock_seconds, clock_cost),
            points_scored=points_scored,
            turnover=turnover,
            possession_changed=turnover or turnover_on_downs or bool(points_scored),
            defensive_scheme=scheme,
            incomplete=incomplete,
            offense_power=offense_power,
            defense_power=defense_power,
            perk_effects=tuple(perk_effects),
            turnover_on_downs=turnover_on_downs,
            turnover_type=turnover_type,
            perk_activations=tuple(activations),
        )
        self.state = _record_event(
            self._with_current_decks(next_state),
            action=play,
            play_result=result,
            points_scored=points_scored,
            scoring_team=scoring_team,
            clock_seconds_used=result.clock_seconds_used,
            perk_effects=result.perk_effects,
            perk_activations=result.perk_activations,
            card_id=play.value,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
        )
        if after_safety_kickoff and self.state.period == previous_period:
            self.state = self._resolve_kickoff(self.state, offensive_side)
        self._offer_green_dog(
            pre, defensive_side, converted=pre.down >= 3 and first_down,
            previous_period=previous_period,
        )
        return self._finish_play_action(
            self.state,
            offensive_side,
            selected_card,
            previous_period=previous_period,
            challengeable=result.turnover or result.turnover_on_downs,
        )

    def _finish_action(
        self,
        state: FootballMatchState,
        *,
        points: int = 0,
    ) -> FootballMatchState:
        if (
            points
            and state.period >= 3
            and state.awaited_action is not FootballAwaitedAction.CONVERSION
        ):
            return _complete_match(state)
        return _advance_period_if_expired(state, self.rng)

    @staticmethod
    def _conversion_state(
        state: FootballMatchState,
        team: FootballTeamSide,
        defensive_scheme: DefensiveSchemeAction,
    ) -> FootballMatchState:
        return replace(
            state,
            possession=team,
            down=1,
            yards_to_go=2.0,
            offense_field_position=98.0,
            awaited_action=FootballAwaitedAction.CONVERSION,
            current_drive_defensive_scheme=defensive_scheme,
            conversion_team=team,
        )

    def _resolve_kickoff(
        self,
        state: FootballMatchState,
        kicking_team: FootballTeamSide,
        *,
        clock_seconds_used: int = KICKOFF_CLOCK_SECONDS,
    ) -> FootballMatchState:
        if state.status is FootballMatchStatus.COMPLETED or state.period >= 3:
            return state
        clock_seconds_used = min(state.game_clock_seconds, clock_seconds_used)
        receiving_team = _opponent(kicking_team)
        if self.rng.random() < KICKOFF_TOUCHBACK_CHANCE:
            return_yards = 0.0
            field_position = TOUCHBACK_START_YARDS
            description = "Kickoff touchback"
            return_touchdown = False
        else:
            receiving_upgrades = (
                state.team_a_coach_upgrades
                if receiving_team is FootballTeamSide.TEAM_A
                else state.team_b_coach_upgrades
            )
            return_bonus = coach_upgrade_magnitude(
                receiving_upgrades,
                FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
            )
            return_yards = _clamp(
                self.rng.gauss(
                    KICKOFF_RETURN_MEAN_YARDS,
                    KICKOFF_RETURN_STANDARD_DEVIATION,
                ) + return_bonus,
                0.0,
                100.0,
            )
            return_touchdown = (
                self.rng.random() < KICKOFF_RETURN_TOUCHDOWN_CHANCE
            )
            if not return_touchdown:
                return_yards = min(
                    return_yards,
                    MAX_NONSCORING_RETURN_FIELD_POSITION,
                )
            field_position = 100.0 if return_touchdown else return_yards
            description = (
                "Kickoff return touchdown"
                if return_touchdown
                else f"Kickoff returned {return_yards:.1f} yards"
            )
        if return_touchdown:
            state = _add_score(state, receiving_team, TOUCHDOWN_POINTS)
            state = self._conversion_state(
                state,
                receiving_team,
                DefensiveSchemeAction.GOAL_LINE_FRONT,
            )
            state = replace(
                state,
                game_clock_seconds=max(
                    0, state.game_clock_seconds - clock_seconds_used
                ),
            )
        else:
            state = _after_possession_change(
                state,
                possession=receiving_team,
                field_position=field_position,
                clock_cost=clock_seconds_used,
            )
            state = replace(state, conversion_team=None)
        state = _advance_period_if_expired(state, self.rng)
        return _record_event(
            state,
            action=FootballAutomaticAction.KICKOFF,
            points_scored=TOUCHDOWN_POINTS if return_touchdown else 0,
            scoring_team=receiving_team if return_touchdown else None,
            clock_seconds_used=clock_seconds_used,
            description=description,
            gross_yards=KICKOFF_GROSS_YARDS,
            return_yards=return_yards,
        )

    def _resolve_blocked_kick(
        self, state: FootballMatchState, *, clock_cost: int
    ) -> tuple[
        FootballMatchState,
        float,
        int,
        FootballTeamSide | None,
        str,
    ]:
        kicking_team = state.possession
        return_team = _opponent(kicking_team)
        if self.rng.random() >= BLOCKED_KICK_RECOVERY_CHANCE:
            setback = max(
                0.0,
                self.rng.gauss(
                    BLOCKED_KICK_OWN_RECOVERY_MEAN_YARDS,
                    BLOCKED_KICK_OWN_RECOVERY_STANDARD_DEVIATION,
                ),
            )
            recovery_position = max(1.0, state.offense_field_position - setback)
            state = _after_possession_change(
                state,
                possession=return_team,
                field_position=100.0 - recovery_position,
                clock_cost=clock_cost,
            )
            return (
                state,
                0.0,
                0,
                None,
                "Blocked kick recovered by kicking team; turnover on downs",
            )

        starting_position = 100.0 - state.offense_field_position
        return_yards = _clamp(
            self.rng.gauss(
                BLOCKED_KICK_RETURN_MEAN_YARDS,
                BLOCKED_KICK_RETURN_STANDARD_DEVIATION,
            ),
            0.0,
            100.0 - starting_position,
        )
        return_position = starting_position + return_yards
        if return_position >= GOAL_LINE_YARDS:
            state = _add_score(state, return_team, TOUCHDOWN_POINTS)
            state = self._conversion_state(
                state,
                return_team,
                DefensiveSchemeAction.GOAL_LINE_FRONT,
            )
            state = replace(
                state,
                game_clock_seconds=max(0, state.game_clock_seconds - clock_cost),
            )
            return (
                state,
                return_yards,
                TOUCHDOWN_POINTS,
                return_team,
                "Blocked kick returned for a touchdown",
            )
        state = _after_possession_change(
            state,
            possession=return_team,
            field_position=return_position,
            clock_cost=clock_cost,
        )
        return (
            state,
            return_yards,
            0,
            None,
            f"Blocked kick recovered and returned {return_yards:.1f} yards",
        )

    def _finish_scoring_sequence(
        self,
        state: FootballMatchState,
        *,
        kickoff_team: FootballTeamSide,
        previous_period: int,
    ) -> FootballMatchState:
        self.state = state
        if (
            state.status is FootballMatchStatus.IN_PROGRESS
            and state.period < 3
            and state.period == previous_period
        ):
            state = self._resolve_kickoff(state, kickoff_team)
            self.state = state
        self._reset_for_period_boundary(previous_period)
        return self.state

    def resolve_conversion(
        self,
        action: FootballConversionAction,
        play: OffensivePlayAction | str | None = None,
    ) -> FootballMatchState:
        if not isinstance(action, FootballConversionAction):
            raise ValueError("Conversion choice must be a FootballConversionAction.")
        if action is FootballConversionAction.EXTRA_POINT and play is not None:
            raise ValueError("An extra-point attempt cannot select an offensive card.")
        self._require_action(FootballAwaitedAction.CONVERSION)
        team = self.state.conversion_team
        scheme = self.state.current_drive_defensive_scheme
        if team is None or scheme is None:
            raise RuntimeError("The conversion state is missing its team or defense.")
        previous_period = self.state.period
        scoring_team: FootballTeamSide | None = None
        points = 0
        blocked = False
        gross_yards: float | None = None
        perk_effects: tuple[str, ...] = ()
        description: str
        selected_play: OffensivePlayAction | None = None
        selected_card: FootballCardCopy | None = None

        activations: list[FootballPerkActivation] = []
        if action is FootballConversionAction.EXTRA_POINT:
            rush = kick_rush_bonus(self.state, team)
            blocked = self.rng.random() < EXTRA_POINT_BLOCK_CHANCE + rush
            if blocked and rush:
                activations.append(FootballPerkActivation(
                    FootballPlayerPerkKind.KICK_RUSH, _opponent(team),
                ))
            if blocked:
                description = "Extra point blocked"
                if self.rng.random() < TWO_POINT_RETURN_TOUCHDOWN_CHANCE:
                    scoring_team = _opponent(team)
                    points = 2
                    description = "Blocked extra point returned for two"
            elif self.rng.random() < EXTRA_POINT_SUCCESS_CHANCE:
                scoring_team = team
                points = 1
                description = "Extra point good"
            else:
                description = "Extra point missed"
        else:
            play, selected_card = self._select_offensive_card(play)
            selected_play = play
            estimate = calculate_match_play_estimate(
                self.state,
                play,
                scheme=scheme,
                is_conversion=True,
            )
            activations.extend(estimate.player_perks)
            gross_yards = max(
                0.0,
                estimate.yards_on_success
                + self.rng.uniform(
                    -estimate.yardage_spread,
                    estimate.yardage_spread,
                ),
            )
            incomplete = False
            turnover = False
            if play in _PASS_PLAYS and not estimate.keep_read:
                roll = self.rng.random()
                incomplete = roll < estimate.incomplete_probability
                turnover = (
                    not incomplete
                    and roll
                    < estimate.incomplete_probability
                    + (1.0 - estimate.incomplete_probability)
                    * estimate.turnover_probability
                )
            else:
                turnover = self.rng.random() < estimate.turnover_probability
            pass_turnover = play in _PASS_PLAYS and not estimate.keep_read
            if turnover and self.rng.random() < TWO_POINT_RETURN_TOUCHDOWN_CHANCE:
                scoring_team = _opponent(team)
                points = 2
                description = "Two-point attempt returned for two"
            elif not incomplete and not turnover and gross_yards >= 2.0:
                scoring_team = team
                points = 2
                description = f"Two-point {play.value.replace('_', ' ')} successful"
            else:
                result = (
                    "intercepted"
                    if turnover and pass_turnover
                    else "fumbled"
                    if turnover
                    else "incomplete"
                    if incomplete
                    else f"stopped at {gross_yards:.1f} yards"
                )
                description = (
                    f"Two-point {play.value.replace('_', ' ')} {result}"
                )
            perk_effects = _play_perk_effect_messages(
                estimate,
                play,
                incomplete=incomplete,
                turnover=turnover,
            )
            if selected_card is not None:
                self._cycle_played_card(team, offensive=True, card=selected_card)

        state = self.state
        if points:
            if scoring_team is None:
                raise RuntimeError("A successful conversion must identify its scorer.")
            state = _add_score(state, scoring_team, points)
        state = replace(
            state,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
            conversion_team=None,
        )
        if state.period >= 3 and state.team_a_score != state.team_b_score:
            state = _complete_match(state)
        else:
            state = _advance_period_if_expired(state, self.rng)
        if state.status is FootballMatchStatus.IN_PROGRESS:
            # The two-point try (or PAT) ends the scoring drive.
            activations.extend(self._end_drive(
                team, scheme, touchdown_scored=True,
                redeal=_redeals_hands(previous_period, state.period),
            ))
            state = self._with_current_decks(state)
        self.state = _record_event(
            state,
            action=action,
            points_scored=points,
            scoring_team=scoring_team,
            description=description,
            gross_yards=gross_yards,
            blocked=blocked,
            clock_seconds_used=0,
            perk_effects=perk_effects,
            perk_activations=tuple(activations),
            card_id=selected_play.value if selected_play is not None else None,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
        )
        self._challenge_snapshot = None
        self._challenge_play_copy_id = None
        if self.state.status is FootballMatchStatus.COMPLETED:
            return self.state
        return self._finish_scoring_sequence(
            self.state,
            kickoff_team=team,
            previous_period=previous_period,
        )

    def resolve_fourth_down(
        self, decision: FootballFourthDownAction
    ) -> FootballMatchState:
        if not isinstance(decision, FootballFourthDownAction):
            raise ValueError("Fourth-down decision must be a FootballFourthDownAction.")
        self._require_action(FootballAwaitedAction.FOURTH_DOWN_DECISION)
        if self.state.down != 4:
            raise ValueError("Fourth-down decisions are only legal on fourth down.")

        previous_period = self.state.period
        state = self.state
        points = 0
        scoring_team: FootballTeamSide | None = None
        distance: float | None = None
        clock_cost = 0
        gross_yards: float | None = None
        return_yards: float | None = None
        description: str | None = None
        blocked = False
        if decision is FootballFourthDownAction.GO_FOR_IT:
            self.state = _record_event(
                replace(state, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY),
                action=decision,
            )
            return self.state
        kicking_team = state.possession
        activations: list[FootballPerkActivation] = []
        rush = kick_rush_bonus(state, kicking_team)
        if decision is FootballFourthDownAction.PUNT:
            clock_cost = PUNT_CLOCK_SECONDS
            blocked = self.rng.random() < blocked_kick_probability(
                state, state.possession, PUNT_BLOCK_CHANCE + rush
            )
            if blocked and rush:
                activations.append(FootballPerkActivation(
                    FootballPlayerPerkKind.KICK_RUSH, _opponent(kicking_team),
                ))
            if blocked:
                gross_yards = 0.0
                (
                    state,
                    return_yards,
                    points,
                    scoring_team,
                    description,
                ) = self._resolve_blocked_kick(state, clock_cost=clock_cost)
            else:
                gross_yards = _clamp(
                    self.rng.gauss(
                        PUNT_GROSS_MEAN_YARDS,
                        PUNT_GROSS_STANDARD_DEVIATION,
                    ),
                    15.0,
                    70.0,
                )
                return_yards = (
                    _clamp(
                        self.rng.gauss(
                            PUNT_RETURN_MEAN_YARDS,
                            PUNT_RETURN_STANDARD_DEVIATION,
                        )
                        + coach_upgrade_magnitude(
                            (
                                state.team_a_coach_upgrades
                                if _opponent(state.possession)
                                is FootballTeamSide.TEAM_A
                                else state.team_b_coach_upgrades
                            ),
                            FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS,
                        ),
                        0.0,
                        40.0,
                    )
                    if self.rng.random() < PUNT_RETURN_CHANCE
                    else 0.0
                )
                max_non_scoring_return = max(
                    0.0,
                    state.offense_field_position
                    + gross_yards
                    - (GOAL_LINE_YARDS - MAX_NONSCORING_RETURN_FIELD_POSITION),
                )
                return_yards = min(return_yards, max_non_scoring_return)
                punt_end_position = (
                    state.offense_field_position + gross_yards - return_yards
                )
                touchback = punt_end_position >= GOAL_LINE_YARDS
                receiving_position = (
                    TOUCHBACK_START_YARDS
                    if touchback
                    else 100.0 - punt_end_position
                )
                description = (
                    "Punt touchback"
                    if touchback
                    else f"Punt {gross_yards:.1f} yards, returned {return_yards:.1f}"
                )
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=_clamp(receiving_position, 0.0, GOAL_LINE_YARDS),
                    clock_cost=clock_cost,
                )
        elif decision is FootballFourthDownAction.FIELD_GOAL:
            clock_cost = FIELD_GOAL_CLOCK_SECONDS
            distance = field_goal_distance_for_position(state.offense_field_position)
            longer = range_denial_yards(state, kicking_team)
            if longer:
                activations.append(FootballPerkActivation(
                    FootballPlayerPerkKind.RANGE_DENIAL, _opponent(kicking_team), longer,
                ))
            blocked = self.rng.random() < blocked_kick_probability(
                state, state.possession, FIELD_GOAL_BLOCK_CHANCE + rush
            )
            if blocked and rush:
                activations.append(FootballPerkActivation(
                    FootballPlayerPerkKind.KICK_RUSH, _opponent(kicking_team),
                ))
            made = (
                not blocked
                and self.rng.random()
                < field_goal_success_probability_for_team(
                    state, state.possession, distance
                )
            )
            if blocked:
                (
                    state,
                    return_yards,
                    points,
                    scoring_team,
                    description,
                ) = self._resolve_blocked_kick(state, clock_cost=clock_cost)
            elif made:
                description = f"Field goal good from {distance:.0f} yards"
                scoring_team = state.possession
                points = FIELD_GOAL_POINTS
                state = _add_score(state, scoring_team, points)
                state = _after_possession_change(
                    state,
                    possession=_opponent(scoring_team),
                    field_position=TOUCHBACK_START_YARDS,
                    clock_cost=clock_cost,
                )
            else:
                description = f"Field goal missed from {distance:.0f} yards"
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=100.0 - state.offense_field_position,
                    clock_cost=clock_cost,
                )

        if (
            points
            and state.period >= 3
            and state.awaited_action is not FootballAwaitedAction.CONVERSION
        ):
            state = _complete_match(state)
        else:
            state = _advance_period_if_expired(state, self.rng)
        if state.status is FootballMatchStatus.IN_PROGRESS:
            activations.extend(self._end_drive(
                kicking_team, self.state.current_drive_defensive_scheme,
                touchdown_scored=False,
                redeal=_redeals_hands(previous_period, state.period),
            ))
            state = self._with_current_decks(state)
        self.state = _record_event(
            state,
            action=decision,
            points_scored=points,
            scoring_team=scoring_team,
            field_goal_distance=distance,
            clock_seconds_used=min(self.state.game_clock_seconds, clock_cost),
            description=description,
            gross_yards=gross_yards,
            return_yards=return_yards,
            blocked=blocked,
            perk_activations=tuple(activations),
        )
        if (
            decision is FootballFourthDownAction.FIELD_GOAL
            and points == FIELD_GOAL_POINTS
            and self.state.status is FootballMatchStatus.IN_PROGRESS
            and self.state.period == previous_period
        ):
            self.state = self._resolve_kickoff(self.state, scoring_team)
        self._reset_for_period_boundary(previous_period, kicking_team)
        if decision is not FootballFourthDownAction.GO_FOR_IT:
            self._challenge_snapshot = None
            self._challenge_play_copy_id = None
        return self.state
