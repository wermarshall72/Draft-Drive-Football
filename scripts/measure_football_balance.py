"""Reproducible seeded matchup and full-game balance measurements."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from math import sqrt

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCoach,
    FootballCoachAssignment,
    FootballConversionAction,
    FootballDeckState,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    FootballPlayFamily,
)
from src.engine.football_simulator import (
    FootballMatchSimulator,
    REGULATION_PERIOD_SECONDS,
)
from src.engine.football_player_catalog import player_types_for_position


@dataclass(frozen=True)
class Scenario:
    name: str
    offense_power: float
    defense_power: float
    prior_plays: int = 0
    stamina: float = 0.75
    coach_and_partnership: bool = False


SCENARIOS = (
    Scenario("equal, uncountered", 50.0, 50.0),
    Scenario("equal, countered", 50.0, 50.0),
    Scenario("offense +30% / defense +10%", 65.0, 55.0),
    Scenario("same edge, countered", 65.0, 55.0),
    Scenario("offense -20% / defense +20%", 40.0, 60.0),
    Scenario("equal, late fatigue", 50.0, 50.0, prior_plays=30, stamina=0.5),
    Scenario("Ground and Pound + Run Stop + RB/O-line partners", 50.0, 50.0, coach_and_partnership=True),
)

PLAYS = (
    OffensivePlayAction.RB_RUN,
    OffensivePlayAction.JET_SWEEP,
    OffensivePlayAction.SCREEN_PASS,
    OffensivePlayAction.MEDIUM_PASS,
    OffensivePlayAction.DEEP_PASS,
)


def _roster(
    name: str,
    power: float,
    stamina: float,
    *,
    coached: bool = False,
    offense: bool = False,
) -> FootballRoster:
    partner_types = {
        position: next(
            player_type
            for player_type in player_types_for_position(position)
            if player_type.partner_position
            is (
                FootballPosition.O_LINE
                if position is FootballPosition.RB
                else FootballPosition.RB
            )
        )
        for position in (FootballPosition.RB, FootballPosition.O_LINE)
    } if coached else {}
    players = {
        position: FootballPlayer(
            name=f"{name} {position.value}",
            position=position,
            power=power,
            volatility=0.1,
            stamina=stamina,
            player_type_id=(
                partner_types[position].type_id
                if position in partner_types
                else None
            ),
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=name,
        players=players,
        coach=FootballCoach(name),
        special_teams=FootballSpecialTeams(name),
        coach_assignment=(
            FootballCoachAssignment("ground_and_pound", "run_stop")
            if coached
            else None
        ),
    )


def _one_play(
    *,
    seed: int,
    scenario: Scenario,
    play: OffensivePlayAction,
    distance: float = 10.0,
) -> tuple[float, bool, bool, bool, bool]:
    matching_scheme = next(
        scheme
        for scheme in DefensiveSchemeAction
        if play in DEFENSIVE_SCHEME_CATALOG[scheme.value].counters
    )
    unmatching_scheme = next(
        scheme
        for scheme in DefensiveSchemeAction
        if play not in DEFENSIVE_SCHEME_CATALOG[scheme.value].counters
    )
    scenario_index = SCENARIOS.index(scenario)
    scheme = (
        matching_scheme
        if scenario_index in (1, 3, 6)
        else unmatching_scheme
    )
    offense_card = FootballCardCopy(f"offense:{play.value}", play.value)
    defense_card = FootballCardCopy(f"defense:{scheme.value}", scheme.value)
    state = FootballMatchState(
        team_a=_roster(
            "Offense",
            scenario.offense_power,
            scenario.stamina,
            coached=scenario.coach_and_partnership,
            offense=True,
        ),
        team_b=_roster(
            "Defense",
            scenario.defense_power,
            scenario.stamina,
            coached=scenario.coach_and_partnership,
        ),
        random_seed=seed,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=distance,
        offense_field_position=30.0,
        game_clock_seconds=REGULATION_PERIOD_SECONDS,
        period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        team_a_offense_deck=FootballDeckState((offense_card,), hand=(offense_card,)),
        team_a_defense_deck=FootballDeckState(()),
        team_b_offense_deck=FootballDeckState(()),
        team_b_defense_deck=FootballDeckState((defense_card,), hand=(defense_card,)),
    )
    simulator = FootballMatchSimulator(state)
    simulator.select_defensive_scheme(scheme)
    result_state = simulator.resolve_offensive_play(play)
    result = result_state.match_events[-1].play_result
    if result is None:
        raise RuntimeError("The simulator did not record the sampled play.")
    converted = not result.turnover and not result.incomplete and result.yards_gained >= distance
    is_pass = OFFENSIVE_PLAY_CATALOG[play.value].family is FootballPlayFamily.PASS
    is_run = not is_pass
    return (
        result.yards_gained,
        result.yards_gained >= 4.0,
        result.yards_gained < 0,
        converted,
        result.incomplete if is_pass else result.turnover if is_run else False,
    )


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - margin, center + margin


def _mean_ci(values: list[float]) -> tuple[float, float, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 1.96 * sqrt(variance / len(values))
    return mean, mean - margin, mean + margin


def measure_plays(samples: int, seed: int) -> None:
    print("SINGLE-PLAY MATCHUP SAMPLES")
    print(
        "scenario | play | n | mean yd (95% CI) | 4+ yd (95% CI) | "
        "negative | distance conversions | pass incompletions | run fumbles lost"
    )
    for scenario_index, scenario in enumerate(SCENARIOS[:-1]):
        for play_index, play in enumerate(PLAYS):
            yards: list[float] = []
            useful = negative = converted = incompletions = fumbles = 0
            for index in range(samples):
                result = _one_play(
                    seed=seed + scenario_index * 1_000_000 + play_index * 100_000 + index,
                    scenario=scenario,
                    play=play,
                    distance=10.0,
                )
                yards.append(result[0])
                useful += result[1]
                negative += result[2]
                converted += result[3]
                is_pass = OFFENSIVE_PLAY_CATALOG[play.value].family is FootballPlayFamily.PASS
                if is_pass:
                    incompletions += result[4]
                else:
                    fumbles += result[4]
            mean, low, high = _mean_ci(yards)
            useful_low, useful_high = _wilson(useful, samples)
            conversions_low, conversions_high = _wilson(converted, samples)
            print(
                f"{scenario.name} | {play.value} | {samples} | "
                f"{mean:.2f} [{low:.2f}, {high:.2f}] | "
                f"{useful / samples:.3f} [{useful_low:.3f}, {useful_high:.3f}] | "
                f"{negative / samples:.3f} | {converted / samples:.3f} "
                f"[{conversions_low:.3f}, {conversions_high:.3f}] | "
                f"{incompletions / samples:.3f} | {fumbles / samples:.3f}"
            )
    coached = SCENARIOS[-1]
    yards: list[float] = []
    useful = fumbles = 0
    for index in range(samples):
        result = _one_play(
            seed=seed + 3_000_000 + index,
            scenario=coached,
            play=OffensivePlayAction.RB_RUN,
        )
        yards.append(result[0])
        useful += result[1]
        fumbles += result[4]
    mean, low, high = _mean_ci(yards)
    useful_low, useful_high = _wilson(useful, samples)
    print(
        f"{coached.name} | rb_run | {samples} | "
        f"{mean:.2f} [{low:.2f}, {high:.2f}] | "
        f"{useful / samples:.3f} [{useful_low:.3f}, {useful_high:.3f}] | "
        f"0.000 | n/a | 0.000 | {fumbles / samples:.3f}"
    )

    print("\nCONDITIONAL FIRST-DOWN CONVERSIONS (same card and matchup)")
    for play in PLAYS:
        for distance in (1.0, 3.0, 7.0, 10.0):
            converted = 0
            for index in range(samples):
                converted += _one_play(
                    seed=seed + 2_000_000 + list(PLAYS).index(play) * 1_000_000
                    + int(distance * 10_000) + index,
                    scenario=SCENARIOS[2],
                    play=play,
                    distance=distance,
                )[3]
            low, high = _wilson(converted, samples)
            print(
                f"{play.value} & {distance:g} yd: "
                f"{converted}/{samples} = {converted / samples:.3f} "
                f"[{low:.3f}, {high:.3f}]"
            )


def _full_game(seed: int, difficulty: FootballAIDifficulty) -> tuple[object, tuple[object, object]]:
    ais = (
        FootballAI(FootballTeamSide.TEAM_A, FootballAIDifficulty.STANDARD, seed + 1, "Team A"),
        FootballAI(FootballTeamSide.TEAM_B, difficulty, seed + 2, "Team B"),
    )
    rosters = tuple(ai.generate_opponent_roster() for ai in ais)
    decks = tuple(ai.generate_opponent_decks(1, roster) for ai, roster in zip(ais, rosters))
    state = FootballMatchState(
        team_a=rosters[0],
        team_b=rosters[1],
        random_seed=seed,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=10.0,
        offense_field_position=25.0,
        game_clock_seconds=REGULATION_PERIOD_SECONDS,
        period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        team_a_offense_deck=FootballDeckState(decks[0][0]),
        team_a_defense_deck=FootballDeckState(decks[0][1]),
        team_b_offense_deck=FootballDeckState(decks[1][0]),
        team_b_defense_deck=FootballDeckState(decks[1][1]),
    )
    simulator = FootballMatchSimulator(state)
    actions = 0
    while simulator.state.status is FootballMatchStatus.IN_PROGRESS:
        current = simulator.state
        if current.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            actor = 1 if current.possession is FootballTeamSide.TEAM_A else 0
        else:
            actor = 0 if current.possession is FootballTeamSide.TEAM_A else 1
        action = ais[actor].choose_action(current)
        if current.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            simulator.select_defensive_scheme(action)
        elif current.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            simulator.resolve_offensive_play(action)
        elif current.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            simulator.resolve_fourth_down(action)
        elif current.awaited_action is FootballAwaitedAction.CONVERSION:
            simulator.resolve_conversion(action)
        else:
            raise RuntimeError(f"Unexpected action state: {current.awaited_action!r}")
        actions += 1
        if actions > 1000:
            raise RuntimeError("A seeded game exceeded 1,000 actions.")
    return simulator.state, (ais[0], ais[1])


def measure_games(games: int, seed: int) -> None:
    print("\nSEEDED FULL-GAME AI SAMPLES")
    print(
        "opponent difficulty | games | Team A win% (95% CI) | points/team-game "
        "(mean; median; 10th-90th pct) | plays/game | drives/team-game | pass INT/attempt | "
        "run fumbles lost/rush | fumbles lost/team-game | drive endings"
    )
    for difficulty in FootballAIDifficulty:
        wins: list[float] = []
        points: list[float] = []
        plays: list[float] = []
        drive_count = 0
        pass_attempts = interceptions = rushes = lost_fumbles = 0
        drive_endings = {
            "touchdown": 0,
            "field goal": 0,
            "punt": 0,
            "pass interception": 0,
            "lost fumble": 0,
            "downs": 0,
            "other": 0,
        }
        for index in range(games):
            state, _ = _full_game(
                seed + (list(FootballAIDifficulty).index(difficulty) * 1_000_000)
                + index,
                difficulty,
            )
            result = state.final_result
            if result is None:
                raise RuntimeError("A sampled game has no final result.")
            wins.append(1.0 if result.winner is FootballTeamSide.TEAM_A else 0.0)
            points.extend((float(result.team_a_score), float(result.team_b_score)))
            plays.append(float(sum(event.play_result is not None for event in state.match_events)))
            drive_events: list[object] = []

            def finish_drive() -> None:
                if not drive_events:
                    return
                ending = drive_events[-1]
                if any(event.points_scored in (6, 7) for event in drive_events):
                    drive_endings["touchdown"] += 1
                elif any(event.action.value == "field_goal" and event.points_scored == 3 for event in drive_events):
                    drive_endings["field goal"] += 1
                elif ending.action.value == "punt":
                    drive_endings["punt"] += 1
                elif ending.play_result is not None and ending.play_result.turnover:
                    key = "pass interception" if ending.play_result.offensive_play in (
                        OffensivePlayAction.SCREEN_PASS,
                        OffensivePlayAction.PA_PASS,
                        OffensivePlayAction.SHORT_PASS,
                        OffensivePlayAction.MEDIUM_PASS,
                        OffensivePlayAction.DEEP_PASS,
                        OffensivePlayAction.QUICK_OUT,
                    ) else "lost fumble"
                    drive_endings[key] += 1
                elif ending.play_result is not None and ending.play_result.turnover_on_downs:
                    drive_endings["downs"] += 1
                else:
                    drive_endings["other"] += 1

            for event in state.match_events:
                if isinstance(event.action, DefensiveSchemeAction):
                    drive_count += 1
                    if drive_events:
                        finish_drive()
                    drive_events = []
                else:
                    drive_events.append(event)
            finish_drive()
            for event in state.match_events:
                play_result = event.play_result
                if play_result is None:
                    continue
                family = OFFENSIVE_PLAY_CATALOG[event.action.value].family
                if family is FootballPlayFamily.PASS:
                    pass_attempts += 1
                    interceptions += (
                        play_result.turnover_type
                        is FootballTurnoverType.INTERCEPTION
                    )
                else:
                    rushes += 1
                    lost_fumbles += (
                        play_result.turnover_type is FootballTurnoverType.FUMBLE
                    )
        win_count = int(sum(wins))
        low, high = _wilson(win_count, games)
        ordered_points = sorted(points)
        median = ordered_points[len(ordered_points) // 2]
        p10 = ordered_points[int((len(ordered_points) - 1) * 0.10)]
        p90 = ordered_points[int((len(ordered_points) - 1) * 0.90)]
        print(
            f"{difficulty.value} | {games} | {win_count / games:.3f} "
            f"[{low:.3f}, {high:.3f}] | {sum(points) / len(points):.2f}; "
            f"{median}; {p10}-{p90} | "
            f"{sum(plays) / len(plays):.1f} | "
            f"{drive_count / (games * 2):.2f} | "
            f"{interceptions}/{pass_attempts} = {interceptions / max(1, pass_attempts):.4f} | "
            f"{lost_fumbles}/{rushes} = {lost_fumbles / max(1, rushes):.4f} | "
            f"{lost_fumbles}/{games * 2} = {lost_fumbles / (games * 2):.3f} | "
            + ", ".join(f"{key}={value}" for key, value in drive_endings.items())
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5_000)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    if args.samples < 1 or args.games < 1:
        parser.error("--samples and --games must be positive.")
    measure_plays(args.samples, args.seed)
    measure_games(args.games, args.seed)


if __name__ == "__main__":
    main()
