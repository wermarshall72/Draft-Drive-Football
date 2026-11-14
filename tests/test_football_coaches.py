import random
from dataclasses import replace

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballCoachAssignment,
    FootballFourthDownAction,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_coaches import (
    COACH_PAIR_OFFERS,
    COACHES_BY_ID,
    DEFENSIVE_COACHES,
    DEFENSIVE_POSITIONS,
    OFFENSIVE_ACTIONS,
    OFFENSIVE_COACHES,
    OFFENSIVE_POSITIONS,
    FootballCoachPerkKind,
)
from src.engine.football_simulator import FootballMatchSimulator


class FixedRNG(random.Random):
    def __init__(self, rolls: tuple[float, ...] = (0.99,)) -> None:
        super().__init__(0)
        self.rolls = iter(rolls)

    def random(self) -> float:
        return next(self.rolls, 0.99)

    def uniform(self, low: float, high: float) -> float:
        return low


def _roster(
    team_name: str,
    assignment: FootballCoachAssignment | None = None,
    *,
    power: float = 10.0,
) -> FootballRoster:
    return FootballRoster(
        team_name,
        {
            position: FootballPlayer(
                f"{team_name} {position.value}", position, power, 0.2, 1.0
            )
            for position in FootballPosition
        },
        FootballCoach(f"{team_name} Coach"),
        FootballSpecialTeams(),
        assignment,
    )


def _simulator(
    *,
    offense_assignment: FootballCoachAssignment | None = None,
    defense_assignment: FootballCoachAssignment | None = None,
    possession: FootballTeamSide = FootballTeamSide.TEAM_A,
    down: int = 1,
    yards_to_go: float = 10.0,
    field_position: float = 25.0,
    scheme: DefensiveSchemeAction = DefensiveSchemeAction.DEEP_PASS,
    rolls: tuple[float, ...] = (0.99,),
) -> FootballMatchSimulator:
    team_a = _roster("Home", offense_assignment)
    team_b = _roster("Away", defense_assignment)
    state = FootballMatchState(
        team_a=team_a,
        team_b=team_b,
        random_seed=11,
        team_a_score=0,
        team_b_score=0,
        possession=possession,
        down=down,
        yards_to_go=yards_to_go,
        offense_field_position=field_position,
        game_clock_seconds=900,
        period=1,
        awaited_action=(
            FootballAwaitedAction.FOURTH_DOWN_DECISION
            if down == 4
            else FootballAwaitedAction.DEFENSIVE_SCHEME
        ),
        current_drive_defensive_scheme=scheme if down == 4 else None,
    )
    simulator = FootballMatchSimulator(state)
    simulator.rng = FixedRNG(rolls)
    if down != 4:
        simulator.select_defensive_scheme(scheme)
    return simulator


def _assignment(offense: str, defense: str = "balanced_defense") -> FootballCoachAssignment:
    return FootballCoachAssignment(offense, defense)


def test_catalog_is_complete_side_scoped_and_has_all_six_actions() -> None:
    assert len(OFFENSIVE_COACHES) == len(DEFENSIVE_COACHES) == 5
    assert len(COACH_PAIR_OFFERS) == 25
    for coach in OFFENSIVE_COACHES:
        assert set(coach.position_modifiers) == set(OFFENSIVE_POSITIONS)
        assert coach.actions == OFFENSIVE_ACTIONS
        assert set(coach.action_percentages) == set(OFFENSIVE_ACTIONS)
    for coach in DEFENSIVE_COACHES:
        assert set(coach.position_modifiers) == set(DEFENSIVE_POSITIONS)
        assert coach.actions == tuple(DefensiveSchemeAction)
        assert set(coach.action_percentages) == set(DefensiveSchemeAction)


def test_specialists_distribute_position_modifiers_and_balanced_profiles_are_uniform() -> None:
    for coach in (*OFFENSIVE_COACHES[:4], *DEFENSIVE_COACHES[:4]):
        assert sorted(coach.position_modifiers.values()) == [-0.1, 0.0, 0.1, 0.2]
        assert coach.perk is not None
    for coach in (OFFENSIVE_COACHES[-1], DEFENSIVE_COACHES[-1]):
        assert set(coach.position_modifiers.values()) == {0.05}
        assert coach.perk is None


def test_approved_specialist_position_mappings_are_exact_and_evenly_distributed() -> None:
    expected_offense = {
        "ground_and_pound": {
            FootballPosition.O_LINE: 0.2,
            FootballPosition.RB: 0.1,
            FootballPosition.WR: -0.1,
            FootballPosition.QB: 0.0,
        },
        "option_spread": {
            FootballPosition.RB: 0.2,
            FootballPosition.WR: 0.1,
            FootballPosition.QB: -0.1,
            FootballPosition.O_LINE: 0.0,
        },
        "air_raid": {
            FootballPosition.WR: 0.2,
            FootballPosition.QB: 0.1,
            FootballPosition.O_LINE: -0.1,
            FootballPosition.RB: 0.0,
        },
        "pro_style": {
            FootballPosition.QB: 0.2,
            FootballPosition.O_LINE: 0.1,
            FootballPosition.RB: -0.1,
            FootballPosition.WR: 0.0,
        },
    }
    expected_defense = {
        "run_stop": {
            FootballPosition.D_LINE: 0.2,
            FootballPosition.LINEBACKERS: 0.1,
            FootballPosition.CORNERBACKS: -0.1,
            FootballPosition.SAFETIES: 0.0,
        },
        "pressure_blitz": {
            FootballPosition.LINEBACKERS: 0.2,
            FootballPosition.CORNERBACKS: 0.1,
            FootballPosition.SAFETIES: -0.1,
            FootballPosition.D_LINE: 0.0,
        },
        "coverage": {
            FootballPosition.CORNERBACKS: 0.2,
            FootballPosition.SAFETIES: 0.1,
            FootballPosition.D_LINE: -0.1,
            FootballPosition.LINEBACKERS: 0.0,
        },
        "ball_hawk": {
            FootballPosition.SAFETIES: 0.2,
            FootballPosition.D_LINE: 0.1,
            FootballPosition.LINEBACKERS: -0.1,
            FootballPosition.CORNERBACKS: 0.0,
        },
    }
    for coach_id, expected in expected_offense.items():
        assert COACHES_BY_ID[coach_id].position_modifiers == expected
    for coach_id, expected in expected_defense.items():
        assert COACHES_BY_ID[coach_id].position_modifiers == expected
    for positions, coaches in (
        (OFFENSIVE_POSITIONS, OFFENSIVE_COACHES[:-1]),
        (DEFENSIVE_POSITIONS, DEFENSIVE_COACHES[:-1]),
    ):
        for position in positions:
            assert sorted(
                coach.position_modifiers[position] for coach in coaches
            ) == [-0.1, 0.0, 0.1, 0.2]


def test_seeded_builder_generates_distinct_reproducible_pair_offers() -> None:
    from src.engine.football_team_builder import FootballTeamBuilder

    first = FootballTeamBuilder("First", 603)
    replay = FootballTeamBuilder("Replay", 603)
    other_seed = FootballTeamBuilder("Other", 604)

    assert first.coach_offer == replay.coach_offer
    assert first.coach_offer != other_seed.coach_offer
    assert len(first.coach_offer) == 3
    assert len(set(first.coach_offer)) == 3
    assert all(pair in COACH_PAIR_OFFERS for pair in first.coach_offer)


@pytest.mark.parametrize(
    ("coach_id", "expected"),
    [
        ("ground_and_pound", 130),
        ("option_spread", 120),
        ("air_raid", 90),
        ("pro_style", 100),
    ],
)
def test_offensive_play_percentages_are_derived_from_contributing_positions(
    coach_id: str, expected: int
) -> None:
    coach = COACHES_BY_ID[coach_id]
    assert coach.action_percentages[OffensivePlayAction.RB_RUN] == expected


def test_balanced_staff_gives_each_action_110_percent_without_perks() -> None:
    for coach in (OFFENSIVE_COACHES[-1], DEFENSIVE_COACHES[-1]):
        assert set(coach.action_percentages.values()) == {110}


def test_full_action_modifier_tables_are_consistent_with_position_bonuses() -> None:
    expected_offense = {
        "ground_and_pound": (130, 110, 110, 100, 120, 90),
        "option_spread": (120, 110, 110, 130, 90, 100),
        "air_raid": (90, 110, 110, 120, 100, 130),
        "pro_style": (100, 110, 110, 90, 130, 120),
        "balanced_offense": (110, 110, 110, 110, 110, 110),
    }
    expected_defense = {
        "run_stop": (130, 110, 110, 100, 120, 90),
        "pressure_blitz": (120, 110, 110, 130, 90, 100),
        "coverage": (90, 110, 110, 120, 100, 130),
        "ball_hawk": (100, 110, 110, 90, 130, 120),
        "balanced_defense": (110, 110, 110, 110, 110, 110),
    }
    for coach_id, expected in expected_offense.items():
        coach = COACHES_BY_ID[coach_id]
        assert tuple(coach.action_percentages[action] for action in OFFENSIVE_ACTIONS) == expected
    for coach_id, expected in expected_defense.items():
        coach = COACHES_BY_ID[coach_id]
        assert tuple(
            coach.action_percentages[DefensiveSchemeAction(action.value)]
            for action in OFFENSIVE_ACTIONS
        ) == expected


def test_modifier_calculation_is_additive_and_never_mutates_base_players() -> None:
    simulator = _simulator(
        offense_assignment=_assignment("ground_and_pound"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
    )
    base_power = {
        position: player.power
        for position, player in simulator.state.team_a.players.items()
    }

    result_state = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = result_state.match_events[-1].play_result

    assert result is not None
    assert result.offense_power == pytest.approx(23.0)
    assert result.defense_power == pytest.approx(20.0)
    assert {
        position: player.power
        for position, player in result_state.team_a.players.items()
    } == base_power


def test_selected_defensive_scheme_uses_its_positions_even_on_play_mismatch() -> None:
    simulator = _simulator(
        defense_assignment=_assignment("balanced_offense", "run_stop"),
        scheme=DefensiveSchemeAction.RB_RUN,
    )

    result = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    play_result = result.match_events[-1].play_result

    assert play_result is not None
    assert play_result.defense_power == pytest.approx(23.0)


def test_matched_scheme_effect_is_applied_once_after_position_bonuses() -> None:
    simulator = _simulator(
        offense_assignment=_assignment("ground_and_pound"),
        scheme=DefensiveSchemeAction.RB_RUN,
    )

    result = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    play_result = result.match_events[-1].play_result

    assert play_result is not None
    assert play_result.offense_power == pytest.approx(23.0 * 0.96)
    assert play_result.defense_power == pytest.approx(20.0 * 1.12)


def test_ground_and_pound_first_run_bonus_applies_once_and_refreshes_next_drive() -> None:
    simulator = _simulator(
        offense_assignment=_assignment("ground_and_pound"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
    )
    first = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    second = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)

    first_result = first.match_events[-1].play_result
    second_result = second.match_events[-1].play_result
    assert first_result is not None and second_result is not None
    assert first_result.yards_gained - second_result.yards_gained == pytest.approx(3.0)
    assert first_result.perk_effects
    assert not second_result.perk_effects

    next_drive = replace(
        second,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=10.0,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
    )
    simulator.state = next_drive
    simulator.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
    refreshed = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert refreshed.match_events[-1].play_result is not None
    assert refreshed.match_events[-1].play_result.perk_effects


def test_ground_and_pound_spends_first_run_attempt_on_turnover() -> None:
    simulator = _simulator(
        offense_assignment=_assignment("ground_and_pound"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rolls=(0.0,),
    )

    turnover = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = turnover.match_events[-1].play_result

    assert result is not None and result.turnover
    assert any("attempt used" in effect for effect in result.perk_effects)


def test_air_raid_first_completed_pass_skips_incomplete_and_applies_once() -> None:
    simulator = _simulator(
        offense_assignment=_assignment("air_raid"),
        scheme=DefensiveSchemeAction.RB_RUN,
        rolls=(0.0, 0.99, 0.99, 0.99),
    )
    incomplete = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    completed = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)

    incomplete_result = incomplete.match_events[-1].play_result
    completed_result = completed.match_events[-1].play_result
    assert incomplete_result is not None and incomplete_result.incomplete
    assert not incomplete_result.perk_effects
    assert completed_result is not None and not completed_result.turnover
    assert completed_result.perk_effects
    assert completed_result.yards_gained > 3.0
    next_completed = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert next_completed.match_events[-1].play_result is not None
    assert not next_completed.match_events[-1].play_result.perk_effects


def test_pro_style_first_down_pass_and_option_fourth_down_perks_apply() -> None:
    pro_style = _simulator(
        offense_assignment=_assignment("pro_style"),
        scheme=DefensiveSchemeAction.RB_RUN,
        yards_to_go=1.0,
    )
    first_pass = pro_style.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    second_pass = pro_style.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    assert first_pass.match_events[-1].play_result is not None
    assert second_pass.match_events[-1].play_result is not None
    assert first_pass.match_events[-1].play_result.perk_effects
    assert second_pass.match_events[-1].play_result.perk_effects

    option = _simulator(
        offense_assignment=_assignment("option_spread"),
        down=4,
        yards_to_go=2.0,
        rolls=(0.75,),
    )
    option_state = option.resolve_fourth_down(
        FootballFourthDownAction.GO_FOR_IT
    )
    assert option_state.match_events[-1].perk_effects
    assert option_state.possession is FootballTeamSide.TEAM_A


def test_run_stop_pressure_coverage_and_ball_hawk_perks_have_matching_triggers() -> None:
    run_stop = _simulator(
        defense_assignment=_assignment("balanced_offense", "run_stop"),
        scheme=DefensiveSchemeAction.RB_RUN,
    )
    stopped = run_stop.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert stopped.match_events[-1].play_result is not None
    assert stopped.match_events[-1].play_result.perk_effects

    pressure = _simulator(
        defense_assignment=_assignment("balanced_offense", "pressure_blitz"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rolls=(0.48,),
    )
    intercepted = pressure.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert intercepted.match_events[-1].play_result is not None
    assert intercepted.match_events[-1].play_result.turnover
    assert intercepted.match_events[-1].play_result.perk_effects

    coverage = _simulator(
        defense_assignment=_assignment("balanced_offense", "coverage"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rolls=(0.36,),
    )
    incomplete = coverage.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert incomplete.match_events[-1].play_result is not None
    assert incomplete.match_events[-1].play_result.incomplete
    assert incomplete.match_events[-1].play_result.perk_effects

    ball_hawk = _simulator(
        defense_assignment=_assignment("balanced_offense", "ball_hawk"),
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rolls=(0.45,),
    )
    returned = ball_hawk.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert returned.possession is FootballTeamSide.TEAM_B
    assert returned.offense_field_position == pytest.approx(88.0)
    assert returned.match_events[-1].play_result is not None
    assert returned.match_events[-1].play_result.perk_effects


def test_ai_generates_a_reproducible_coach_pair_used_by_the_roster() -> None:
    first = FootballAI(FootballTeamSide.TEAM_B, FootballAIDifficulty.STANDARD, 72)
    replay = FootballAI(FootballTeamSide.TEAM_B, FootballAIDifficulty.STANDARD, 72)

    first_roster = first.generate_opponent_roster()
    replay_roster = replay.generate_opponent_roster()

    assert first_roster == replay_roster
    assert first_roster.coach_assignment is not None
    offense_id = first_roster.coach_assignment.offensive_coach_id
    defense_id = first_roster.coach_assignment.defensive_coach_id
    assert COACHES_BY_ID[offense_id].side.value == "offense"
    assert COACHES_BY_ID[defense_id].side.value == "defense"

    state = FootballMatchState(
        team_a=_roster("Human"),
        team_b=first_roster,
        random_seed=2,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_B,
        down=1,
        yards_to_go=10.0,
        offense_field_position=25.0,
        game_clock_seconds=900,
        period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
    )
    simulator = FootballMatchSimulator(state)
    simulator.rng = FixedRNG()
    simulator.select_defensive_scheme(DefensiveSchemeAction.RB_RUN)
    result = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    play_result = result.match_events[-1].play_result
    offense_profile = COACHES_BY_ID[offense_id]
    assert play_result is not None
    assert play_result.offense_power == pytest.approx(
        sum(
            first_roster.players[position].power
            * (1.0 + offense_profile.position_modifiers[position])
            for position in (FootballPosition.O_LINE, FootballPosition.RB)
        )
        * 0.96
    )


def test_balanced_pair_combines_all_eight_position_bonuses() -> None:
    pair = next(
        pair
        for pair in COACH_PAIR_OFFERS
        if pair.offense.coach_id == "balanced_offense"
        and pair.defense.coach_id == "balanced_defense"
    )
    assert set(pair.offense.position_modifiers.values()) == {0.05}
    assert set(pair.defense.position_modifiers.values()) == {0.05}
    assert set(pair.offense.action_percentages.values()) == {110}
    assert set(pair.defense.action_percentages.values()) == {110}


def test_coach_perk_definitions_include_trigger_effect_duration_and_reset() -> None:
    for coach in (*OFFENSIVE_COACHES[:-1], *DEFENSIVE_COACHES[:-1]):
        assert coach.perk is not None
        assert coach.perk.trigger.strip()
        assert coach.perk.effect.strip()
        assert coach.perk.duration.strip()
        assert coach.perk.reset.strip()
        assert isinstance(coach.perk.kind, FootballCoachPerkKind)
