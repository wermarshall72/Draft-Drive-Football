from dataclasses import replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCoach,
    FootballCoachAssignment,
    FootballAutomaticAction,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchState,
    FootballMatchStatus,
    FootballDeckState,
    FootballPlayer,
    FootballPlayResult,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
    matchup_for_scheme,
)
from src.engine.football_simulator import (
    FATIGUE_RAMP_PLAYS,
    MAX_FATIGUE_POWER_REDUCTION,
    MIN_PLAY_YARDAGE_SPREAD,
    FootballMatchSimulator,
    REGULATION_PERIOD_SECONDS,
    calculate_play_estimate,
    field_goal_distance_for_position,
    field_goal_success_probability,
    matchup_for_play,
)
from src.engine.football_player_catalog import (
    PLAYER_BASE_POWER,
    PLAYER_BASE_STAMINA,
    PLAYER_BASE_VOLATILITY,
    player_from_type,
    player_types_for_position,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_shop import (
    PLAYER_UPGRADE_CATALOG, FootballShop, FootballShopRarity, FootballUpgradeDuration,
    FootballUpgradeStat, apply_player_upgrade,
)


class SequenceRNG(random.Random):
    def __init__(
        self,
        random_values: tuple[float, ...] = (),
        uniform_values: tuple[float, ...] = (),
        choice_value: FootballTeamSide = FootballTeamSide.TEAM_A,
        gauss_values: tuple[float, ...] = (),
    ):
        super().__init__(0)
        self.random_values = random_values
        self.uniform_values = uniform_values
        self.choice_value = choice_value
        self.gauss_values = gauss_values
        self.random_calls = 0
        self.uniform_calls = 0
        self.choice_calls = 0
        self.gauss_calls = 0

    def random(self) -> float:
        value = self.random_values[self.random_calls] if self.random_calls < len(self.random_values) else 0.99
        self.random_calls += 1
        return value

    def uniform(self, low: float, high: float) -> float:
        value = self.uniform_values[self.uniform_calls] if self.uniform_calls < len(self.uniform_values) else (low + high) / 2
        self.uniform_calls += 1
        return value

    def choice(self, values):
        self.choice_calls += 1
        return self.choice_value

    def gauss(self, mu: float, sigma: float) -> float:
        if self.gauss_calls < len(self.gauss_values):
            value = self.gauss_values[self.gauss_calls]
        else:
            value = mu
        self.gauss_calls += 1
        return value


def _roster(
    team_name: str,
    *,
    power: float = 10.0,
    stamina: float = 0.75,
) -> FootballRoster:
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=power,
            volatility=0.2,
            stamina=stamina,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=team_name,
        players=players,
        coach=FootballCoach(f"{team_name} Coach"),
        special_teams=FootballSpecialTeams(),
    )


@pytest.mark.parametrize(
    ("other_volatility", "expected_before", "expected_after"),
    [(0.10, 1.0, 1.0), (0.20, 1.86, 1.8)],
)
def test_volatility_upgrade_can_be_limited_by_play_spread_floor(
    other_volatility, expected_before, expected_after
) -> None:
    original = _roster("Offense")
    players = {position: replace(player, volatility=other_volatility)
               for position, player in original.players.items()}
    players[FootballPosition.QB] = replace(players[FootballPosition.QB], volatility=0.02)
    offense = replace(original, players=players)
    opponent = _roster("Defense")
    opponent = replace(opponent, players={
        position: replace(player, volatility=other_volatility)
        for position, player in opponent.players.items()
    })
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.VOLATILITY
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                and card.rarity is FootballShopRarity.COMMON)
    upgraded = apply_player_upgrade(offense, card.upgrade)
    assert upgraded.players[FootballPosition.QB].volatility == pytest.approx(0.0)
    def spread(roster):
        return calculate_play_estimate(
            roster, opponent, OffensivePlayAction.PA_PASS, DefensiveSchemeAction.RB_RUN
        ).yardage_spread
    assert spread(offense) == pytest.approx(expected_before)
    assert spread(upgraded) == pytest.approx(expected_after)
    assert expected_after >= MIN_PLAY_YARDAGE_SPREAD


def _match_state(**overrides) -> FootballMatchState:
    offense_copies = tuple(
        FootballCardCopy(f"test:offense:{card_id}", card_id)
        for card_id in OFFENSIVE_PLAY_CATALOG
    )
    defense_copies = tuple(
        FootballCardCopy(f"test:defense:{card_id}", card_id)
        for card_id in DEFENSIVE_SCHEME_CATALOG
    )
    values = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
        "random_seed": 17,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 25.0,
        "game_clock_seconds": 900,
        "period": 1,
        "team_a_offense_deck": FootballDeckState(
            offense_copies, hand=offense_copies
        ),
        "team_a_defense_deck": FootballDeckState(
            defense_copies, hand=defense_copies
        ),
        "team_b_offense_deck": FootballDeckState(
            tuple(
                replace(card, copy_id=f"away:{card.copy_id}")
                for card in offense_copies
            ),
            hand=tuple(
                replace(card, copy_id=f"away:{card.copy_id}")
                for card in offense_copies
            ),
        ),
        "team_b_defense_deck": FootballDeckState(
            tuple(
                replace(card, copy_id=f"away:{card.copy_id}")
                for card in defense_copies
            ),
            hand=tuple(
                replace(card, copy_id=f"away:{card.copy_id}")
                for card in defense_copies
            ),
        ),
        "awaited_action": FootballAwaitedAction.DEFENSIVE_SCHEME,
    }
    values.update(overrides)
    if "game_clock_seconds" not in overrides and values["period"] >= 3:
        values["game_clock_seconds"] = 300
    if values["awaited_action"] in (
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    ):
        values.setdefault(
            "current_drive_defensive_scheme", DefensiveSchemeAction.DEEP_PASS
        )
    if values["awaited_action"] is FootballAwaitedAction.CONVERSION:
        values["current_drive_defensive_scheme"] = values.get(
            "current_drive_defensive_scheme", DefensiveSchemeAction.GOAL_LINE_FRONT
        )
        values.setdefault("conversion_team", values["possession"])
        values["offense_field_position"] = 98.0
        values["yards_to_go"] = 2.0
    return FootballMatchState(**values)


def _ball_hawk_interception_simulator(
    *,
    offense_side: FootballTeamSide = FootballTeamSide.TEAM_A,
    field_position: float = 25.0,
    period: int = 1,
    game_clock_seconds: int = 900,
    ball_hawk: bool = True,
    random_seed: int = 17,
    fixed_rolls: bool = True,
) -> tuple[FootballMatchSimulator, FootballCardCopy]:
    interception_card = FootballCardCopy("interception:deep-pass", "deep_pass")
    remaining_cards = (
        FootballCardCopy("interception:rb-run", "rb_run"),
        FootballCardCopy("interception:short-pass", "short_pass"),
    )
    offense_deck = FootballDeckState(
        owned=(interception_card, *remaining_cards),
        hand=(interception_card,),
        draw_pile=remaining_cards,
    )
    team_a = _roster("Home")
    team_b = _roster("Away")
    defense_roster = team_b if offense_side is FootballTeamSide.TEAM_A else team_a
    if ball_hawk:
        defense_roster = replace(
            defense_roster,
            coach_assignment=FootballCoachAssignment(
                "balanced_offense", "ball_hawk"
            ),
        )
        if offense_side is FootballTeamSide.TEAM_A:
            team_b = defense_roster
        else:
            team_a = defense_roster
    state = _match_state(
        team_a=team_a,
        team_b=team_b,
        possession=offense_side,
        offense_field_position=field_position,
        period=period,
        game_clock_seconds=game_clock_seconds,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
        random_seed=random_seed,
        **{
            "team_a_offense_deck" if offense_side is FootballTeamSide.TEAM_A
            else "team_b_offense_deck": offense_deck
        },
    )
    simulator = FootballMatchSimulator(state)
    if fixed_rolls:
        simulator.rng = SequenceRNG((0.36,), (0.0,))
    simulator.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
    return simulator, interception_card


def _sim_with_scheme(
    *,
    scheme: DefensiveSchemeAction = DefensiveSchemeAction.SHORT_PASS,
    rng: SequenceRNG | None = None,
    **state_overrides,
) -> FootballMatchSimulator:
    sim = FootballMatchSimulator(_match_state(**state_overrides))
    if rng is not None:
        sim.rng = rng
    sim.select_defensive_scheme(scheme)
    return sim


def _roster_with_mutual_partners(
    team_name: str,
    positions: tuple[FootballPosition, FootballPosition],
    coach_assignment: FootballCoachAssignment,
) -> FootballRoster:
    players = dict(_roster(team_name, power=PLAYER_BASE_POWER, stamina=1.0).players)
    for position, partner in (positions, positions[::-1]):
        player_type = next(
            item
            for item in player_types_for_position(position)
            if item.partner_position is partner
        )
        players[position] = player_from_type(
            player_type,
            name=f"{team_name} {player_type.name}",
            power=PLAYER_BASE_POWER,
            volatility=PLAYER_BASE_VOLATILITY,
            stamina=PLAYER_BASE_STAMINA,
        )
    return FootballRoster(
        team_name,
        players,
        FootballCoach(f"{team_name} Coach"),
        FootballSpecialTeams(),
        coach_assignment,
    )


def test_all_six_play_matchups_use_the_required_positions():
    expected = {
        OffensivePlayAction.RB_RUN: (
            (FootballPosition.O_LINE, FootballPosition.RB),
            (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
        ),
        OffensivePlayAction.SCREEN_PASS: (
            (FootballPosition.O_LINE, FootballPosition.WR),
            (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
        ),
        OffensivePlayAction.PA_PASS: (
            (FootballPosition.QB, FootballPosition.RB),
            (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
        ),
        OffensivePlayAction.SHORT_PASS: (
            (FootballPosition.RB, FootballPosition.WR),
            (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
        ),
        OffensivePlayAction.MEDIUM_PASS: (
            (FootballPosition.QB, FootballPosition.O_LINE),
            (FootballPosition.SAFETIES, FootballPosition.D_LINE),
        ),
        OffensivePlayAction.DEEP_PASS: (
            (FootballPosition.QB, FootballPosition.WR),
            (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
        ),
    }
    for play, pairing in expected.items():
        assert matchup_for_play(play) == pairing


@pytest.mark.parametrize(
    ("play", "scheme"),
    [
        (play, scheme)
        for play in OffensivePlayAction
        for scheme in DefensiveSchemeAction
    ],
)
def test_partnerships_use_play_and_selected_scheme_contributors(
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
) -> None:
    offense_positions, _ = matchup_for_play(play)
    defense_positions, matched_plays = matchup_for_scheme(scheme)
    offense = _roster_with_mutual_partners(
        "Home",
        offense_positions,
        FootballCoachAssignment("balanced_offense", "balanced_defense"),
    )
    defense = _roster_with_mutual_partners(
        "Away",
        defense_positions,
        FootballCoachAssignment("balanced_offense", "balanced_defense"),
    )
    simulator = FootballMatchSimulator(
        _match_state(team_a=offense, team_b=defense)
    )
    simulator.select_defensive_scheme(scheme)
    result = simulator.resolve_offensive_play(play).match_events[-1].play_result

    assert result is not None
    assert result.offense_power == pytest.approx(
        115.0 * (0.96 if play in matched_plays else 1.0)
    )
    assert result.defense_power == pytest.approx(
        115.0 * (1.12 if play in matched_plays else 1.0)
    )


def test_shop_coach_partnership_and_fatigue_stack_once_before_scheme_modifier() -> None:
    offense = _roster_with_mutual_partners(
        "Home",
        (FootballPosition.QB, FootballPosition.RB),
        FootballCoachAssignment("pro_style", "balanced_defense"),
    )
    shop = next(
        (
            candidate
            for seed in range(100)
            for candidate in (FootballShop(offense, seed),)
            if any(
                item.position is FootballPosition.QB
                and item.stat is FootballUpgradeStat.POWER
                and item.duration is FootballUpgradeDuration.PERMANENT
                for item in candidate.offer
            )
        ),
        None,
    )
    assert shop is not None
    qb_upgrade = next(
        item
        for item in shop.offer
        if item.position is FootballPosition.QB
        and item.stat is FootballUpgradeStat.POWER
        and item.duration is FootballUpgradeDuration.PERMANENT
    )
    upgraded_roster = shop.buy(qb_upgrade).roster

    history = tuple(
        FootballMatchEvent(
            sequence=index,
            action=OffensivePlayAction.RB_RUN,
            team_a_score=0,
            team_b_score=0,
            possession=FootballTeamSide.TEAM_A,
            offense_field_position=25.0,
            down=1,
            yards_to_go=10.0,
            game_clock_seconds=900,
            period=1,
            status=FootballMatchStatus.IN_PROGRESS,
            clock_seconds_used=18,
            play_result=FootballPlayResult(
                OffensivePlayAction.RB_RUN,
                1.0,
                18,
                defensive_scheme=DefensiveSchemeAction.RB_RUN,
            ),
        )
        for index in range(1, 16)
    )
    simulator = FootballMatchSimulator(
        _match_state(
            team_a=upgraded_roster,
            team_b=_roster("Away", power=50.0, stamina=1.0),
            match_events=history,
        )
    )
    simulator.select_defensive_scheme(DefensiveSchemeAction.SCREEN_PASS)
    result = simulator.resolve_offensive_play(
        OffensivePlayAction.PA_PASS
    ).match_events[-1].play_result

    assert result is not None
    upgraded_power = 50.0 + qb_upgrade.amount
    assert upgraded_roster.players[FootballPosition.QB].power == upgraded_power
    assert result.offense_power == pytest.approx(
        (upgraded_power * 0.975 * 1.30) + (50.0 * 0.975 * 1.0)
    )


def test_player_perk_text_does_not_affect_match_resolution() -> None:
    qb_types = tuple(
        item
        for item in player_types_for_position(FootballPosition.QB)
        if item.partner_position is FootballPosition.RB
    )
    rosters = []
    for player_type in qb_types:
        players = dict(_roster("Home").players)
        players[FootballPosition.QB] = player_from_type(
            player_type,
            name="Home QB",
            power=10.0,
            volatility=0.2,
            stamina=0.75,
        )
        rosters.append(
            FootballRoster(
                "Home",
                players,
                FootballCoach("Home Coach"),
                FootballSpecialTeams(),
            )
        )

    results = []
    for roster in rosters:
        simulator = FootballMatchSimulator(_match_state(team_a=roster))
        simulator.select_defensive_scheme(DefensiveSchemeAction.SCREEN_PASS)
        results.append(
            simulator.resolve_offensive_play(
                OffensivePlayAction.PA_PASS
            ).match_events[-1].play_result
        )

    assert results[0] is not None and results[1] is not None
    assert results[0].offense_power == results[1].offense_power
    assert results[0].defense_power == results[1].defense_power
    assert results[0].yards_gained == results[1].yards_gained
    assert results[0].perk_effects == results[1].perk_effects == ()


@pytest.mark.parametrize("play", list(OffensivePlayAction))
def test_matching_scheme_changes_power_but_mismatching_scheme_does_not(play):
    matching_scheme = next(
        scheme
        for scheme in DefensiveSchemeAction
        if play in matchup_for_scheme(scheme)[1]
    )
    matching = _sim_with_scheme(
        scheme=matching_scheme,
        rng=SequenceRNG((0.99,), (0.0,)),
    )
    mismatching_scheme = next(
        scheme
        for scheme in DefensiveSchemeAction
        if play not in matchup_for_scheme(scheme)[1]
    )
    mismatching = _sim_with_scheme(
        scheme=mismatching_scheme,
        rng=SequenceRNG((0.99,), (0.0,)),
    )

    matched_result = matching.resolve_offensive_play(play).match_events[-1].play_result
    mismatched_result = mismatching.resolve_offensive_play(play).match_events[-1].play_result
    assert matched_result is not None and mismatched_result is not None
    assert matched_result.offense_power == pytest.approx(19.2)
    assert matched_result.defense_power == pytest.approx(22.4)
    assert mismatched_result.offense_power == 20.0
    assert mismatched_result.defense_power == 20.0


def test_normal_run_and_completed_pass_advance_clock_and_down():
    run = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    run_state = run.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert run_state.offense_field_position == 28.75
    assert run_state.down == 2
    assert run_state.yards_to_go == 6.25
    assert run_state.game_clock_seconds == 874

    pass_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    pass_state = pass_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert pass_state.offense_field_position == 37.5
    assert pass_state.down == 1
    assert pass_state.game_clock_seconds == 872


@pytest.mark.parametrize("play", tuple(OffensivePlayAction))
def test_completed_offensive_card_uses_its_catalog_clock_duration(
    play: OffensivePlayAction,
) -> None:
    simulator = _sim_with_scheme(
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rng=SequenceRNG((0.99,), (0.0,)),
    )
    result = simulator.resolve_offensive_play(play)
    event = result.match_events[-1]
    assert event.play_result is not None
    expected = OFFENSIVE_PLAY_CATALOG[play.value].clock_seconds
    assert event.clock_seconds_used == event.play_result.clock_seconds_used == expected
    assert result.game_clock_seconds == 900 - expected


def test_incomplete_pass_is_lossless_and_uses_less_clock_than_a_completion():
    incomplete_sim = _sim_with_scheme(rng=SequenceRNG((0.0,), (0.0,)))
    before_position = incomplete_sim.state.offense_field_position
    incomplete = incomplete_sim.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    incomplete_result = incomplete.match_events[-1].play_result
    assert incomplete_result is not None
    assert incomplete_result.incomplete
    assert incomplete_result.yards_gained == 0
    assert incomplete.offense_field_position == before_position
    assert incomplete.game_clock_seconds == 895
    assert incomplete.down == 2

    complete_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    completed = complete_sim.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    assert completed.game_clock_seconds == 876


def test_first_down_and_goal_to_go_use_the_shorter_distance():
    first_down_sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        yards_to_go=3.0,
    )
    first_down = first_down_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert first_down.down == 1
    assert first_down.offense_field_position == 37.5
    assert first_down.yards_to_go == 10.0

    goal_sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-0.5,)),
        offense_field_position=97.0,
        yards_to_go=10.0,
    )
    goal_state = goal_sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert goal_state.team_a_score == 6
    assert goal_state.awaited_action is FootballAwaitedAction.CONVERSION
    assert goal_state.match_events[-1].points_scored == 6


def test_negative_yardage_increases_distance_and_turnover_flips_field_position():
    negative_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (-10.0,)))
    negative = negative_sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert negative.offense_field_position == 18.75
    assert negative.yards_to_go == 16.25
    assert negative.down == 2

    turnover_sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.RB_RUN,
        rng=SequenceRNG((0.31,), (0.0,)),
    )
    turnover = turnover_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert turnover.match_events[-1].play_result.turnover
    assert turnover.possession is FootballTeamSide.TEAM_B
    assert turnover.offense_field_position == 75.0
    assert turnover.down == 1
    assert turnover.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert turnover.current_drive_defensive_scheme is None


@pytest.mark.parametrize("kind", ("interception", "downs"))
def test_turnover_inside_ten_starts_first_and_goal(kind: str) -> None:
    if kind == "interception":
        simulator = _sim_with_scheme(
            scheme=DefensiveSchemeAction.RB_RUN,
            rng=SequenceRNG((0.31,), (0.0,)),
            offense_field_position=5.0,
        )
        result = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
        assert result.match_events[-1].play_result.turnover
    else:
        simulator = FootballMatchSimulator(
            _match_state(
                down=4,
                offense_field_position=5.0,
                awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
                current_drive_defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
            )
        )
        simulator.rng = SequenceRNG((0.99,), (-3.75,))
        simulator.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
        result = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
        assert result.match_events[-1].play_result.turnover_on_downs
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == 95.0
    assert result.down == 1 and result.yards_to_go == 5.0
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert (result.team_a_score, result.team_b_score) == (0, 0)


def test_long_yardage_requires_the_actual_distance_on_later_downs() -> None:
    simulator = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-10.0,)),
        yards_to_go=10.0,
    )
    negative = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert negative.down == 2
    assert negative.yards_to_go == 16.25

    simulator.rng = SequenceRNG((0.99,), (6.0,))
    short = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = short.match_events[-1].play_result
    assert result is not None
    assert result.yards_gained == 9.75
    assert short.down == 3
    assert short.yards_to_go == 6.5


@pytest.mark.parametrize(
    ("gain", "converted"),
    [(10.0, False), (15.0, True)],
)
def test_fourth_and_fifteen_requires_fifteen_yards(
    gain: float, converted: bool
) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=15.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
        )
    )
    simulator.rng = SequenceRNG((0.99,), (gain - 3.75,))
    simulator.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    state = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = state.match_events[-1].play_result
    assert result is not None
    assert result.yards_gained == gain
    assert result.turnover_on_downs is not converted
    assert state.possession is (
        FootballTeamSide.TEAM_A if converted else FootballTeamSide.TEAM_B
    )
    if converted:
        assert state.down == 1
        assert state.offense_field_position == 40.0
        assert state.yards_to_go == 10.0
    else:
        assert state.offense_field_position == 65.0


def test_goal_to_go_exact_line_gain_scores_and_updates_possession() -> None:
    simulator = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-1.75,)),
        yards_to_go=2.0,
        offense_field_position=98.0,
    )
    state = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = state.match_events[-1].play_result
    assert result is not None
    assert result.yards_gained == 2.0
    assert state.team_a_score == 6
    assert state.possession is FootballTeamSide.TEAM_A
    assert state.awaited_action is FootballAwaitedAction.CONVERSION


@pytest.mark.parametrize("down", (1, 4))
@pytest.mark.parametrize("ball_hawk", (False, True))
@pytest.mark.parametrize(
    "offense_side",
    (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B),
)
@pytest.mark.parametrize("field_position", (2.0, 10.0, 20.0, 98.0))
def test_interceptions_near_goal_lines_are_not_safeties_and_cycle_cards(
    field_position: float,
    down: int,
    ball_hawk: bool,
    offense_side: FootballTeamSide,
) -> None:
    pass_card = FootballCardCopy("interception:deep-pass", "deep_pass")
    other_cards = (
        FootballCardCopy("interception:rb-run", "rb_run"),
        FootballCardCopy("interception:short-pass", "short_pass"),
    )
    offense_deck = FootballDeckState(
        owned=(pass_card, *other_cards),
        hand=(pass_card,),
        draw_pile=other_cards,
    )
    home = _roster("Home")
    if offense_side is FootballTeamSide.TEAM_A:
        away = _roster("Away")
        if ball_hawk:
            away = replace(
                away,
                coach_assignment=FootballCoachAssignment(
                    "balanced_offense", "ball_hawk"
                ),
            )
        teams = {"team_a": home, "team_b": away}
        deck_override = {"team_a_offense_deck": offense_deck}
    else:
        if ball_hawk:
            home = replace(
                home,
                coach_assignment=FootballCoachAssignment(
                    "balanced_offense", "ball_hawk"
                ),
            )
        teams = {"team_a": home, "team_b": _roster("Away")}
        deck_override = {"team_b_offense_deck": offense_deck}
    simulator = FootballMatchSimulator(
        _match_state(
            **teams,
            possession=offense_side,
            down=down,
            yards_to_go=8.0,
            offense_field_position=field_position,
            awaited_action=(
                FootballAwaitedAction.FOURTH_DOWN_DECISION
                if down == 4
                else FootballAwaitedAction.DEFENSIVE_SCHEME
            ),
            current_drive_defensive_scheme=(
                DefensiveSchemeAction.DEEP_PASS if down == 4 else None
            ),
            **deck_override,
        )
    )
    simulator.rng = SequenceRNG((0.36,), (0.0,))
    if down == 1:
        simulator.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
    else:
        simulator.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)

    state = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    result = state.match_events[-1].play_result
    defense_side = (
        FootballTeamSide.TEAM_B
        if offense_side is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )
    expected_return = 10.0 if ball_hawk else 0.0
    defensive_touchdown = ball_hawk and field_position <= 10.0
    assert result is not None and result.turnover
    assert result.yards_gained == 0.0
    assert result.points_scored == (6 if defensive_touchdown else 0)
    assert not result.turnover_on_downs
    expected_score_a = 6 if defensive_touchdown and defense_side is FootballTeamSide.TEAM_A else 0
    expected_score_b = 6 if defensive_touchdown and defense_side is FootballTeamSide.TEAM_B else 0
    assert (state.team_a_score, state.team_b_score) == (
        expected_score_a,
        expected_score_b,
    )
    assert state.possession is (
        defense_side
    )
    assert state.offense_field_position == (
        98.0
        if defensive_touchdown
        else min(100.0, 100.0 - field_position + expected_return)
    )
    assert state.game_clock_seconds == 872
    assert state.current_drive_defensive_scheme is (
        DefensiveSchemeAction.DEEP_PASS if defensive_touchdown else None
    )
    assert state.match_events[-1].scoring_team == (
        defense_side if defensive_touchdown else None
    )
    assert state.match_events[-1].points_scored == result.points_scored
    assert state.match_events[-1].team_a_score == state.team_a_score
    assert state.match_events[-1].team_b_score == state.team_b_score
    assert state.match_events[-1].status is state.status
    assert state.status is FootballMatchStatus.IN_PROGRESS
    assert state.awaited_action is (
        FootballAwaitedAction.CONVERSION
        if defensive_touchdown
        else FootballAwaitedAction.DEFENSIVE_SCHEME
    )
    assert state.match_events[-1].clock_seconds_used == 28
    assert state.match_events[-1].action is OffensivePlayAction.DEEP_PASS
    assert sum(
        event.action is OffensivePlayAction.DEEP_PASS
        for event in state.match_events
    ) == 1
    assert result.defensive_scheme is DefensiveSchemeAction.DEEP_PASS
    assert any(
        "Ball-Hawk: +10 interception return yards" in effect
        for effect in result.perk_effects
    ) is ball_hawk
    deck = (
        state.team_a_offense_deck
        if offense_side is FootballTeamSide.TEAM_A
        else state.team_b_offense_deck
    )
    assert deck is not None
    assert deck.discard_pile == (pass_card,)
    assert pass_card not in deck.hand
    assert set(
        deck.hand + deck.draw_pile + deck.discard_pile
    ) == set(deck.owned)


@pytest.mark.parametrize(
    ("period", "clock", "expected_period", "expected_clock", "status"),
    (
        (1, 900, 1, 872, FootballMatchStatus.IN_PROGRESS),
        (1, 18, 1, 0, FootballMatchStatus.IN_PROGRESS),
        (2, 18, 2, 0, FootballMatchStatus.IN_PROGRESS),
        (3, 300, 3, 272, FootballMatchStatus.IN_PROGRESS),
    ),
)
@pytest.mark.parametrize(
    "offense_side",
    (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B),
)
def test_ball_hawk_touchdown_uses_match_score_and_clock_conventions(
    period: int,
    clock: int,
    expected_period: int,
    expected_clock: int,
    status: FootballMatchStatus,
    offense_side: FootballTeamSide,
) -> None:
    simulator, _ = _ball_hawk_interception_simulator(
        offense_side=offense_side,
        field_position=10.0,
        period=period,
        game_clock_seconds=clock,
    )
    state = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    event = state.match_events[-1]
    defense_side = (
        FootballTeamSide.TEAM_B
        if offense_side is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )
    result = event.play_result
    assert result is not None
    assert result.turnover and result.possession_changed
    assert result.points_scored == event.points_scored == 6
    assert event.scoring_team is defense_side
    assert (event.team_a_score, event.team_b_score) == (
        (6, 0) if defense_side is FootballTeamSide.TEAM_A else (0, 6)
    )
    assert state.possession is defense_side
    assert state.offense_field_position == 98.0
    assert state.period == event.period == expected_period
    assert state.game_clock_seconds == event.game_clock_seconds == expected_clock
    assert state.status is event.status is status
    assert result.clock_seconds_used == event.clock_seconds_used == min(clock, 28)
    assert state.current_drive_defensive_scheme is DefensiveSchemeAction.DEEP_PASS
    assert state.conversion_team is defense_side
    assert state.awaited_action is FootballAwaitedAction.CONVERSION
    assert state.final_result is None
    assert any("Ball-Hawk" in item for item in result.perk_effects)
    offense_deck = (
        state.team_a_offense_deck
        if offense_side is FootballTeamSide.TEAM_A
        else state.team_b_offense_deck
    )
    assert offense_deck is not None
    assert set(
        offense_deck.hand + offense_deck.draw_pile + offense_deck.discard_pile
    ) == set(offense_deck.owned)


def test_ball_hawk_interception_touchdown_is_seeded_and_reproducible() -> None:
    fingerprints = []
    for _ in range(2):
        simulator, _ = _ball_hawk_interception_simulator(
            field_position=2.0,
            random_seed=9,
            fixed_rolls=False,
        )
        state = simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
        result = state.match_events[-1].play_result
        assert result is not None
        assert result.turnover and result.points_scored == 6
        fingerprints.append(
            (
                state.team_a_score,
                state.team_b_score,
                state.possession,
                state.offense_field_position,
                state.game_clock_seconds,
                state.period,
                state.status,
                state.match_events,
                state.team_a_offense_deck,
            )
        )
    assert fingerprints[0] == fingerprints[1]


def test_negative_yardage_from_goal_to_go_uses_actual_line_to_gain():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-13.0,)),
        offense_field_position=95.0,
        yards_to_go=10.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.PA_PASS)
    assert result.offense_field_position == 91.5
    assert result.yards_to_go == 8.5


def test_incomplete_play_at_goal_line_does_not_score_without_positive_gain():
    incomplete = _sim_with_scheme(
        scheme=DefensiveSchemeAction.SHORT_PASS,
        rng=SequenceRNG((0.0,), (0.0,)),
        offense_field_position=100.0,
    )
    incomplete_state = incomplete.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    assert incomplete_state.team_a_score == 0
    assert incomplete_state.match_events[-1].play_result.incomplete

    completed = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        offense_field_position=100.0,
    )
    completed_state = completed.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert completed_state.team_a_score == 6
    assert completed_state.awaited_action is FootballAwaitedAction.CONVERSION


def test_safety_scores_two_and_gives_opponent_own_twenty_five():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99, 0.0), (-10.0,)),
        offense_field_position=2.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert result.team_b_score == 2
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == 25.0
    assert result.down == 1
    assert result.current_drive_defensive_scheme is None
    assert result.match_events[-2].scoring_team is FootballTeamSide.TEAM_B


def test_go_for_it_uses_a_normal_card_play_and_converts_fourth_down():
    cards = tuple(
        FootballCardCopy(f"fourth:offense:{index}", play.value)
        for index, play in enumerate(OffensivePlayAction)
    )
    offense_deck = FootballDeckState(
        cards,
        hand=(cards[0],),
        draw_pile=cards[1:],
    )
    success = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=1.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=offense_deck,
        )
    )
    success.rng = SequenceRNG((0.99,), (0.0,))
    decision_state = success.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    assert decision_state.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert decision_state.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert decision_state.game_clock_seconds == 900
    assert decision_state.match_events[-1].action is FootballFourthDownAction.GO_FOR_IT
    assert decision_state.team_a_offense_deck == offense_deck

    before_invalid = success.state
    before_rng = success.rng.getstate()
    with pytest.raises(ValueError, match="not in the current hand"):
        success.resolve_offensive_play("not-a-current-card")
    assert success.state is before_invalid
    assert success.rng.getstate() == before_rng

    converted = success.resolve_offensive_play(cards[0].copy_id)
    assert converted.possession is FootballTeamSide.TEAM_A
    assert converted.down == 1
    assert converted.offense_field_position > 25.0
    assert converted.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert converted.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert converted.game_clock_seconds == 874
    result = converted.match_events[-1].play_result
    assert result is not None and not result.turnover_on_downs
    assert result.defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert converted.team_a_offense_deck is not None
    deck = converted.team_a_offense_deck
    assert set(deck.hand + deck.draw_pile + deck.discard_pile) == set(cards)


def test_go_for_it_empty_hand_fallback_and_discard_reshuffle_conserve_cards():
    fallback_card = FootballCardCopy("fallback:draw", OffensivePlayAction.DEEP_PASS.value)
    fallback_deck = FootballDeckState(
        (fallback_card,),
        draw_pile=(fallback_card,),
    )
    fallback = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=1.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=fallback_deck,
        )
    )
    fallback.rng = SequenceRNG((0.99,), (0.0,))
    fallback.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    fallback_state = fallback.resolve_offensive_play(None)
    assert fallback_state.match_events[-1].action is OffensivePlayAction.RB_RUN
    assert fallback_state.team_a_offense_deck is not None
    assert fallback_state.team_a_offense_deck.hand == (fallback_card,)
    assert not fallback_state.team_a_offense_deck.draw_pile
    assert not fallback_state.team_a_offense_deck.discard_pile

    played_card = FootballCardCopy("reshuffle:run", OffensivePlayAction.RB_RUN.value)
    one_card_deck = FootballDeckState((played_card,), hand=(played_card,))
    reshuffle = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=1.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=one_card_deck,
        )
    )
    reshuffle.rng = SequenceRNG((0.99,), (0.0,))
    reshuffle.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    reshuffled_state = reshuffle.resolve_offensive_play(played_card.copy_id)
    assert reshuffled_state.team_a_offense_deck is not None
    assert reshuffled_state.team_a_offense_deck.hand == (played_card,)
    assert not reshuffled_state.team_a_offense_deck.draw_pile
    assert not reshuffled_state.team_a_offense_deck.discard_pile


def test_go_for_it_play_respects_halftime_and_overtime_boundaries():
    halftime = FootballMatchSimulator(
        _match_state(
            period=1,
            game_clock_seconds=4,
            down=4,
            yards_to_go=1.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    halftime.rng = SequenceRNG((0.99,), (0.0,))
    halftime.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    second_period = halftime.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert second_period.period == 2
    assert second_period.game_clock_seconds == REGULATION_PERIOD_SECONDS
    assert second_period.possession is FootballTeamSide.TEAM_A
    assert second_period.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert second_period.team_a_offense_deck is not None
    assert len(second_period.team_a_offense_deck.hand) == 3

    overtime = FootballMatchSimulator(
        _match_state(
            period=3,
            game_clock_seconds=4,
            down=4,
            yards_to_go=10.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    overtime.rng = SequenceRNG((0.99,), (-10.0,))
    overtime.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    next_period = overtime.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert next_period.period == 4
    assert next_period.game_clock_seconds == 300
    assert next_period.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert next_period.current_drive_defensive_scheme is None


def test_fourth_down_failure_turns_over_at_play_spot_and_incomplete_pass_uses_normal_clock():
    failure = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=10.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    failure.rng = SequenceRNG((0.99,), (-10.0,))
    failure.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    flipped = failure.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = flipped.match_events[-1].play_result
    assert result is not None and result.turnover_on_downs
    assert not result.turnover and result.possession_changed
    assert flipped.possession is FootballTeamSide.TEAM_B
    assert flipped.offense_field_position == pytest.approx(
        100.0 - (25.0 + result.yards_gained)
    )
    assert flipped.game_clock_seconds == 874
    assert flipped.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert flipped.current_drive_defensive_scheme is None

    incomplete = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=7.0,
            offense_field_position=40.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.SHORT_PASS,
        )
    )
    incomplete.rng = SequenceRNG((0.0,), (0.0,))
    incomplete.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    stopped = incomplete.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    result = stopped.match_events[-1].play_result
    assert result is not None and result.incomplete and result.turnover_on_downs
    assert result.clock_seconds_used == 5
    assert stopped.possession is FootballTeamSide.TEAM_B
    assert stopped.offense_field_position == 60.0
    assert stopped.game_clock_seconds == 895


def test_fourth_down_turnover_and_touchdown_follow_normal_play_resolution():
    interception = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=8.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
        )
    )
    interception.rng = SequenceRNG((0.36,), (0.0,))
    interception.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    turned = interception.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    result = turned.match_events[-1].play_result
    assert result is not None and result.turnover and not result.turnover_on_downs
    assert turned.possession is FootballTeamSide.TEAM_B
    assert turned.game_clock_seconds == 872

    safety = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=10.0,
            offense_field_position=2.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    safety.rng = SequenceRNG((0.99,), (-10.0,))
    safety.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    safety_state = safety.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    safety_event = next(
        event
        for event in reversed(safety_state.match_events)
        if event.action is OffensivePlayAction.RB_RUN
    )
    safety_result = safety_event.play_result
    assert safety_state.team_b_score == 2
    assert safety_state.possession is FootballTeamSide.TEAM_B
    assert safety_state.offense_field_position == 25.0
    assert safety_result is not None
    assert safety_result.points_scored == 2
    assert not safety_result.turnover_on_downs

    touchdown = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=1.0,
            offense_field_position=99.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    touchdown.rng = SequenceRNG((0.99,), (0.0,))
    touchdown.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    scored = touchdown.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert scored.team_a_score == 6
    assert scored.possession is FootballTeamSide.TEAM_A
    assert scored.awaited_action is FootballAwaitedAction.CONVERSION
    assert scored.match_events[-1].points_scored == 6


def test_punt_records_gross_and_return_yardage_and_touchback():
    normal = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=4.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    normal.rng = SequenceRNG((0.99, 0.99), gauss_values=(43.0, 8.0))
    punted = normal.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert punted.possession is FootballTeamSide.TEAM_B
    assert punted.offense_field_position == 32.0
    assert punted.down == 1
    assert punted.current_drive_defensive_scheme is None
    assert punted.match_events[-1].gross_yards == 43.0
    assert punted.match_events[-1].return_yards == 0.0
    assert not punted.match_events[-1].blocked

    touchback = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=4.0,
            offense_field_position=60.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    touchback.rng = SequenceRNG((0.99, 0.99), gauss_values=(43.0, 8.0))
    touchback_state = touchback.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert touchback_state.possession is FootballTeamSide.TEAM_B
    assert touchback_state.offense_field_position == 25.0

    blocked = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    blocked.rng = SequenceRNG((0.0, 0.0), gauss_values=(15.0,))
    blocked_state = blocked.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert blocked_state.match_events[-1].blocked
    assert blocked_state.possession is FootballTeamSide.TEAM_B
    assert blocked_state.offense_field_position == 90.0


@pytest.mark.parametrize(
    "decision",
    (FootballFourthDownAction.PUNT, FootballFourthDownAction.FIELD_GOAL),
)
@pytest.mark.parametrize(
    "kicking_team",
    (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B),
)
def test_blocked_kick_defensive_recovery_returns_from_both_sides(
    decision: FootballFourthDownAction,
    kicking_team: FootballTeamSide,
) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            possession=kicking_team,
            down=4,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = SequenceRNG((0.0, 0.0), gauss_values=(15.0,))
    result = simulator.resolve_fourth_down(decision)
    event = result.match_events[-1]

    assert event.blocked
    assert event.return_yards == 15.0
    assert "returned 15.0 yards" in event.description
    assert result.possession is (
        FootballTeamSide.TEAM_B
        if kicking_team is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )
    assert result.offense_field_position == 90.0
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    expected_clock_cost = (
        10 if decision is FootballFourthDownAction.PUNT else 5
    )
    assert result.game_clock_seconds == 900 - expected_clock_cost


@pytest.mark.parametrize(
    "decision",
    (FootballFourthDownAction.PUNT, FootballFourthDownAction.FIELD_GOAL),
)
@pytest.mark.parametrize(
    ("field_position", "yards_to_go", "setback", "expected_receiving_position"),
    (
        (40.0, 10.0, 5.0, 65.0),
        (40.0, 10.0, 0.0, 60.0),
        (40.0, 10.0, 50.0, 99.0),
        (98.0, 2.0, 5.0, 7.0),
    ),
)
@pytest.mark.parametrize(
    "kicking_team",
    (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B),
)
def test_blocked_kick_can_be_recovered_by_the_kicking_team(
    decision: FootballFourthDownAction,
    field_position: float,
    yards_to_go: float,
    setback: float,
    expected_receiving_position: float,
    kicking_team: FootballTeamSide,
) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            possession=kicking_team,
            down=4,
            yards_to_go=yards_to_go,
            offense_field_position=field_position,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    initial_state = simulator.state
    simulator.rng = SequenceRNG((0.0, 0.99), gauss_values=(setback,))
    result = simulator.resolve_fourth_down(decision)

    receiving_team = (
        FootballTeamSide.TEAM_B
        if kicking_team is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )
    assert result.possession is receiving_team
    assert result.offense_field_position == expected_receiving_position
    assert result.down == 1
    assert result.yards_to_go == min(10.0, 100.0 - expected_receiving_position)
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert result.current_drive_defensive_scheme is None
    assert result.conversion_team is None
    assert result.game_clock_seconds == initial_state.game_clock_seconds - (
        10 if decision is FootballFourthDownAction.PUNT else 5
    )
    assert result.match_events[-1].description == (
        "Blocked kick recovered by kicking team; turnover on downs"
    )
    assert result.team_a_score == initial_state.team_a_score
    assert result.team_b_score == initial_state.team_b_score
    for deck_name in (
        "team_a_offense_deck",
        "team_a_defense_deck",
        "team_b_offense_deck",
        "team_b_defense_deck",
    ):
        assert getattr(result, deck_name).owned == getattr(initial_state, deck_name).owned


@pytest.mark.parametrize(
    ("period", "clock", "team_b_score", "expected_period", "expected_status"),
    (
        (1, 1, 0, 2, FootballMatchStatus.IN_PROGRESS),
        (2, 1, 0, 3, FootballMatchStatus.IN_PROGRESS),
        (2, 1, 3, 2, FootballMatchStatus.COMPLETED),
    ),
)
@pytest.mark.parametrize(
    "decision",
    (FootballFourthDownAction.PUNT, FootballFourthDownAction.FIELD_GOAL),
)
def test_blocked_kicking_team_recovery_preserves_period_transitions_and_decks(
    period: int,
    clock: int,
    team_b_score: int,
    expected_period: int,
    expected_status: FootballMatchStatus,
    decision: FootballFourthDownAction,
) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=40.0,
            game_clock_seconds=clock,
            period=period,
            team_b_score=team_b_score,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    initial_state = simulator.state
    simulator.rng = SequenceRNG((0.0, 0.99), gauss_values=(5.0,))
    result = simulator.resolve_fourth_down(decision)

    assert result.period == expected_period
    assert result.status is expected_status
    assert result.match_events[-1].clock_seconds_used == 1
    if expected_status is FootballMatchStatus.COMPLETED:
        assert result.final_result is not None
        assert result.final_result.completed
    elif expected_period == 2:
        assert result.game_clock_seconds == REGULATION_PERIOD_SECONDS
        assert result.possession is FootballTeamSide.TEAM_B
        assert result.offense_field_position == 65.0
    elif expected_period == 3:
        assert result.game_clock_seconds == 300
        assert result.down == 1
        assert result.yards_to_go == 10.0
        assert result.offense_field_position == 25.0
        assert result.possession is FootballTeamSide.TEAM_A
        assert result.current_drive_defensive_scheme is None
        assert (result.team_a_score, result.team_b_score) == (0, 0)

    for deck_name in (
        "team_a_offense_deck",
        "team_a_defense_deck",
        "team_b_offense_deck",
        "team_b_defense_deck",
    ):
        initial_deck = getattr(initial_state, deck_name)
        final_deck = getattr(result, deck_name)
        assert final_deck.owned == initial_deck.owned
        assert len(final_deck.owned) == len(initial_deck.owned)
        assert sorted(
            card.copy_id
            for card in (*final_deck.hand, *final_deck.draw_pile, *final_deck.discard_pile)
        ) == sorted(card.copy_id for card in final_deck.owned)


@pytest.mark.parametrize(
    ("return_yards", "touchdown"),
    ((97.0, False), (98.0, True)),
)
@pytest.mark.parametrize(
    "decision",
    (FootballFourthDownAction.PUNT, FootballFourthDownAction.FIELD_GOAL),
)
def test_blocked_kick_return_respects_goal_line_and_conversion_flow(
    return_yards: float,
    touchdown: bool,
    decision: FootballFourthDownAction,
) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=98.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = SequenceRNG(
        (0.0, 0.0, 0.99, 0.0, 0.0),
        gauss_values=(return_yards,),
    )
    result = simulator.resolve_fourth_down(decision)
    event = result.match_events[-1]
    assert event.blocked
    if not touchdown:
        assert event.points_scored == 0
        assert result.possession is FootballTeamSide.TEAM_B
        assert result.offense_field_position == 99.0
        assert result.down == 1 and result.yards_to_go == 1.0
        assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
        return

    assert event.points_scored == 6
    assert event.scoring_team is FootballTeamSide.TEAM_B
    assert result.team_b_score == 6
    assert result.conversion_team is FootballTeamSide.TEAM_B
    assert result.awaited_action is FootballAwaitedAction.CONVERSION
    converted = simulator.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert converted.team_b_score == 7
    assert converted.possession is FootballTeamSide.TEAM_A
    assert converted.match_events[-1].action is FootballAutomaticAction.KICKOFF


def test_field_goal_distance_is_goal_distance_plus_ten_and_made_or_missed():
    position = 45.0
    distance = field_goal_distance_for_position(position)
    assert distance == 100.0 - position + 10.0
    assert distance == 65.0
    assert field_goal_success_probability(distance) > 0.18

    made = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=5.0,
            offense_field_position=position,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    made.rng = SequenceRNG((0.99, 0.0, 0.0))
    made_state = made.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert made_state.team_a_score == 3
    assert made_state.possession is FootballTeamSide.TEAM_B
    assert made_state.offense_field_position == 25.0
    field_goal_event = next(
        event
        for event in reversed(made_state.match_events)
        if event.action is FootballFourthDownAction.FIELD_GOAL
    )
    assert field_goal_event.field_goal_distance == 65.0

    missed = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=5.0,
            offense_field_position=45.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    missed.rng = SequenceRNG((0.99, 0.99))
    missed_state = missed.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert missed_state.team_a_score == 0
    assert missed_state.possession is FootballTeamSide.TEAM_B
    assert missed_state.offense_field_position == 55.0


@pytest.mark.parametrize("position", (0.0, 1.0, 5.0, 10.0, 12.0))
def test_missed_field_goal_sets_new_drive_distance_to_goal(position: float) -> None:
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=position,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = SequenceRNG((0.99, 0.99))
    result = simulator.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    receiving_position = min(99.0, 100.0 - position)
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == receiving_position
    assert result.down == 1
    assert result.yards_to_go == min(10.0, 100.0 - receiving_position)
    assert (result.team_a_score, result.team_b_score) == (0, 0)
    assert result.match_events[-1].action is FootballFourthDownAction.FIELD_GOAL
    assert "missed" in result.match_events[-1].description


def test_conversion_at_expired_clock_is_untimed_and_completes_after_touchdown():
    simulator = _sim_with_scheme(
        scheme=DefensiveSchemeAction.RB_RUN,
        rng=SequenceRNG((0.99, 0.99, 0.0), (0.5,)),
        period=2,
        game_clock_seconds=18,
        offense_field_position=97.0,
    )
    touchdown = simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert touchdown.awaited_action is FootballAwaitedAction.CONVERSION
    assert touchdown.game_clock_seconds == 0
    completed = simulator.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert completed.status is FootballMatchStatus.COMPLETED
    assert completed.team_a_score == 7
    assert completed.game_clock_seconds == 0
    assert completed.match_events[-1].clock_seconds_used == 0


def test_two_point_attempt_uses_and_cycles_an_offensive_hand_card():
    run = FootballCardCopy("conversion:run", OffensivePlayAction.RB_RUN.value)
    pass_card = FootballCardCopy(
        "conversion:pass", OffensivePlayAction.SHORT_PASS.value
    )
    deck = FootballDeckState(
        owned=(run, pass_card),
        hand=(run, pass_card),
    )
    simulator = FootballMatchSimulator(
        _match_state(
            team_a_score=6,
            awaited_action=FootballAwaitedAction.CONVERSION,
            possession=FootballTeamSide.TEAM_A,
            conversion_team=FootballTeamSide.TEAM_A,
            team_a_offense_deck=deck,
        )
    )
    simulator.rng = SequenceRNG((0.99, 0.0), (0.0,))
    before_invalid = simulator.state
    with pytest.raises(ValueError, match="fallback is available only"):
        simulator.resolve_conversion(FootballConversionAction.TWO_POINT)
    assert simulator.state is before_invalid
    result = simulator.resolve_conversion(
        FootballConversionAction.TWO_POINT,
        run.copy_id,
    )
    conversion_event = next(
        event
        for event in result.match_events
        if event.action is FootballConversionAction.TWO_POINT
    )
    assert conversion_event.points_scored == 2
    assert conversion_event.scoring_team is FootballTeamSide.TEAM_A
    assert conversion_event.gross_yards is not None
    assert conversion_event.gross_yards >= 2.0
    assert result.team_a_score == 8
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == 25.0
    assert result.match_events[-1].action is FootballAutomaticAction.KICKOFF
    updated_deck = result.team_a_offense_deck
    assert updated_deck is not None
    assert updated_deck.hand == (pass_card, run)
    assert updated_deck.discard_pile == ()


def test_two_point_attempt_uses_basic_run_when_the_hand_is_empty() -> None:
    basic_run = FootballCardCopy(
        "conversion:empty-hand-basic-run",
        OffensivePlayAction.RB_RUN.value,
    )
    deck = FootballDeckState((basic_run,), discard_pile=(basic_run,))
    simulator = FootballMatchSimulator(
        _match_state(
            team_a_score=6,
            awaited_action=FootballAwaitedAction.CONVERSION,
            conversion_team=FootballTeamSide.TEAM_A,
            team_a_offense_deck=deck,
        )
    )
    simulator.rng = SequenceRNG((0.99,), (0.0,))
    result = simulator.resolve_conversion(FootballConversionAction.TWO_POINT)
    event = next(
        event
        for event in result.match_events
        if event.action is FootballConversionAction.TWO_POINT
    )

    assert event.points_scored == 2
    assert "two-point rb run successful" in event.description.lower()
    assert result.team_a_offense_deck == deck


def test_two_point_turnover_without_a_return_scores_no_points() -> None:
    run = FootballCardCopy("conversion:turnover-run", OffensivePlayAction.RB_RUN.value)
    deck = FootballDeckState((run,), hand=(run,))
    simulator = FootballMatchSimulator(
        _match_state(
            team_a_score=6,
            awaited_action=FootballAwaitedAction.CONVERSION,
            conversion_team=FootballTeamSide.TEAM_A,
            team_a_offense_deck=deck,
        )
    )
    simulator.rng = SequenceRNG((0.0, 0.99, 0.0))
    result = simulator.resolve_conversion(
        FootballConversionAction.TWO_POINT,
        run.copy_id,
    )
    event = next(
        event
        for event in result.match_events
        if event.action is FootballConversionAction.TWO_POINT
    )

    assert event.points_scored == 0
    assert "fumbled" in event.description
    assert result.team_a_score == 6
    assert result.possession is FootballTeamSide.TEAM_B


@pytest.mark.parametrize(
    "conversion",
    (
        FootballConversionAction.EXTRA_POINT,
        FootballConversionAction.TWO_POINT,
    ),
)
@pytest.mark.parametrize(
    "touchdown_team",
    (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B),
)
def test_conversion_defensive_return_kicks_off_for_original_touchdown_team(
    conversion: FootballConversionAction,
    touchdown_team: FootballTeamSide,
) -> None:
    run = FootballCardCopy("conversion:return-run", OffensivePlayAction.RB_RUN.value)
    score_a = 6 if touchdown_team is FootballTeamSide.TEAM_A else 0
    score_b = 6 if touchdown_team is FootballTeamSide.TEAM_B else 0
    deck = FootballDeckState((run,), hand=(run,))
    simulator = FootballMatchSimulator(
        _match_state(
            team_a_score=score_a,
            team_b_score=score_b,
            possession=touchdown_team,
            conversion_team=touchdown_team,
            awaited_action=FootballAwaitedAction.CONVERSION,
            team_a_offense_deck=(
                deck if touchdown_team is FootballTeamSide.TEAM_A else None
            ),
            team_b_offense_deck=(
                deck if touchdown_team is FootballTeamSide.TEAM_B else None
            ),
        )
    )
    simulator.rng = SequenceRNG((0.0, 0.0, 0.0))
    result = simulator.resolve_conversion(conversion, run.copy_id if conversion is FootballConversionAction.TWO_POINT else None)

    return_team = (
        FootballTeamSide.TEAM_B
        if touchdown_team is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )
    assert result.team_a_score == score_a + (2 if return_team is FootballTeamSide.TEAM_A else 0)
    assert result.team_b_score == score_b + (2 if return_team is FootballTeamSide.TEAM_B else 0)
    assert result.match_events[-1].action is FootballAutomaticAction.KICKOFF
    assert result.possession is return_team


def test_conversion_attempt_is_untimed_at_regulation_boundary() -> None:
    run = FootballCardCopy("conversion:boundary-run", OffensivePlayAction.RB_RUN.value)
    deep_pass = FootballCardCopy(
        "conversion:boundary-pass",
        OffensivePlayAction.DEEP_PASS.value,
    )
    deck = FootballDeckState((run, deep_pass), hand=(run, deep_pass))
    simulator = FootballMatchSimulator(
        _match_state(
            period=2,
            game_clock_seconds=1,
            awaited_action=FootballAwaitedAction.CONVERSION,
            conversion_team=FootballTeamSide.TEAM_A,
            team_a_offense_deck=deck,
        )
    )
    simulator.state = replace(simulator.state, game_clock_seconds=0)
    simulator.rng = SequenceRNG((0.0,))
    result = simulator.resolve_conversion(
        FootballConversionAction.TWO_POINT,
        deep_pass.copy_id,
    )

    assert result.match_events[-1].clock_seconds_used == 0
    assert result.period == 3
    assert result.game_clock_seconds == 300
    assert result.status is FootballMatchStatus.IN_PROGRESS
    assert result.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


def test_scoring_kickoff_can_be_returned_for_a_touchdown():
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=90.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = SequenceRNG((0.99, 0.0, 0.99, 0.0))
    result = simulator.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    kickoff = result.match_events[-1]
    assert kickoff.action is FootballAutomaticAction.KICKOFF
    assert kickoff.points_scored == 6
    assert kickoff.scoring_team is FootballTeamSide.TEAM_B
    assert kickoff.gross_yards == 65.0
    assert result.team_a_score == 3
    assert result.team_b_score == 6
    assert result.awaited_action is FootballAwaitedAction.CONVERSION
    assert result.conversion_team is FootballTeamSide.TEAM_B
    assert result.current_drive_defensive_scheme is (
        DefensiveSchemeAction.GOAL_LINE_FRONT
    )


def test_field_goal_block_turns_possession_over_without_scoring():
    simulator = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = SequenceRNG((0.0, 0.0), gauss_values=(15.0,))
    result = simulator.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    field_goal = result.match_events[-1]
    assert field_goal.blocked
    assert "returned 15.0 yards" in field_goal.description
    assert result.team_a_score == 0
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == 90.0


def test_scheme_is_fixed_for_drive_and_cleared_on_all_possession_changes():
    sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    original = sim.state
    with pytest.raises(ValueError, match="cannot be replaced mid-drive"):
        sim.select_defensive_scheme(DefensiveSchemeAction.RB_RUN)
    assert sim.state is original

    play_turnover = _sim_with_scheme(rng=SequenceRNG((0.31,), (0.0,)))
    turned = play_turnover.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert turned.current_drive_defensive_scheme is None

    for action, expected_position in (
        (FootballFourthDownAction.PUNT, 32.0),
        (FootballFourthDownAction.FIELD_GOAL, 75.0),
    ):
        sim = FootballMatchSimulator(
            _match_state(
                down=4,
                offense_field_position=25.0,
                awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
                current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            )
        )
        sim.rng = SequenceRNG(
            (0.99,) if action is not FootballFourthDownAction.FIELD_GOAL else (0.99,)
        )
        changed = sim.resolve_fourth_down(action)
        assert changed.possession is FootballTeamSide.TEAM_B
        assert changed.offense_field_position == expected_position
        assert changed.current_drive_defensive_scheme is None

    go_for_it = FootballMatchSimulator(
        _match_state(
            down=4,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    decision = go_for_it.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    assert decision.possession is FootballTeamSide.TEAM_A
    assert decision.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert decision.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN


def test_clock_is_capped_and_first_period_expiry_preserves_drive_state():
    capped = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        game_clock_seconds=4,
    )
    capped_state = capped.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = capped_state.match_events[-1].play_result
    assert result.clock_seconds_used == 4
    assert capped_state.period == 2
    assert capped_state.game_clock_seconds == REGULATION_PERIOD_SECONDS
    assert capped_state.possession is FootballTeamSide.TEAM_A
    assert capped_state.down == 2
    assert capped_state.offense_field_position == 28.75
    assert capped_state.current_drive_defensive_scheme is DefensiveSchemeAction.SHORT_PASS


def test_special_teams_clock_is_capped_and_field_goal_at_expiry_completes():
    punt = FootballMatchSimulator(
        _match_state(
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            game_clock_seconds=3,
        )
    )
    punt_state = punt.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert punt_state.period == 2
    assert punt_state.game_clock_seconds == REGULATION_PERIOD_SECONDS
    assert punt_state.match_events[-1].clock_seconds_used == 3

    field_goal = FootballMatchSimulator(
        _match_state(
            period=2,
            down=4,
            offense_field_position=45.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            game_clock_seconds=4,
        )
    )
    field_goal.rng = SequenceRNG((0.99, 0.0))
    completed = field_goal.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert completed.status is FootballMatchStatus.COMPLETED
    assert completed.team_a_score == 3
    assert completed.match_events[-1].clock_seconds_used == 4
    assert completed.final_result.team_a_score == completed.team_a_score
    assert completed.final_result.winner is FootballTeamSide.TEAM_A


def test_regulation_completes_at_expiry_and_tied_regulation_starts_overtime():
    ahead = FootballMatchSimulator(
        _match_state(
            team_a_score=3,
            team_b_score=0,
            period=2,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    done = ahead.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert done.status is FootballMatchStatus.COMPLETED
    assert done.final_result.winner is FootballTeamSide.TEAM_A

    tied = FootballMatchSimulator(
        _match_state(
            period=2,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    tied.rng = SequenceRNG(choice_value=FootballTeamSide.TEAM_B)
    overtime = tied.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert overtime.period == 3
    assert overtime.game_clock_seconds == 300
    assert overtime.possession is FootballTeamSide.TEAM_B
    assert overtime.offense_field_position == 25.0
    assert overtime.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


@pytest.mark.parametrize(
    ("period", "play", "uniform"),
    [
        (3, OffensivePlayAction.RB_RUN, 1.0),
        (3, OffensivePlayAction.DEEP_PASS, 0.0),
    ],
)
def test_overtime_first_touchdown_ends_match(period, play, uniform):
    sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rng=SequenceRNG((0.99,), (uniform,)),
        period=period,
        offense_field_position=97.0,
    )
    result = sim.resolve_offensive_play(play)
    assert result.awaited_action is FootballAwaitedAction.CONVERSION
    result = sim.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert result.status is FootballMatchStatus.COMPLETED
    assert result.final_result.winner is FootballTeamSide.TEAM_A


def test_overtime_first_field_goal_and_safety_end_match():
    field_goal = FootballMatchSimulator(
        _match_state(
            period=3,
            down=4,
            offense_field_position=90.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    field_goal.rng = SequenceRNG((0.99, 0.0))
    fg_state = field_goal.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert fg_state.status is FootballMatchStatus.COMPLETED
    assert fg_state.final_result.winner is FootballTeamSide.TEAM_A

    safety = _sim_with_scheme(
        scheme=DefensiveSchemeAction.RB_RUN,
        rng=SequenceRNG((0.99,), (-10.0,)),
        period=3,
        offense_field_position=2.0,
    )
    safety_state = safety.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert safety_state.status is FootballMatchStatus.COMPLETED
    assert safety_state.final_result.winner is FootballTeamSide.TEAM_B


def test_tied_overtime_expiry_starts_another_overtime_iteratively():
    sim = FootballMatchSimulator(
        _match_state(
            period=3,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    rng = SequenceRNG(choice_value=FootballTeamSide.TEAM_A)
    sim.rng = rng
    next_period = sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert next_period.period == 4
    assert next_period.game_clock_seconds == 300
    assert next_period.possession is FootballTeamSide.TEAM_A
    assert rng.choice_calls == 1


def test_scoring_play_at_regulation_expiry_keeps_score_and_completes_match():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        period=2,
        game_clock_seconds=4,
        offense_field_position=97.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert result.awaited_action is FootballAwaitedAction.CONVERSION
    result = sim.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert result.status is FootballMatchStatus.COMPLETED
    assert result.team_a_score == 6
    assert result.match_events[-1].status is FootballMatchStatus.COMPLETED


def test_event_history_is_immutable_ordered_and_reconciles_scores_and_result():
    sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rng=SequenceRNG((0.99,), (0.0,)),
        period=3,
        offense_field_position=97.0,
    )
    scored = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert scored.awaited_action is FootballAwaitedAction.CONVERSION
    scored = sim.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert tuple(event.sequence for event in scored.match_events) == (1, 2, 3)
    assert scored.match_events[0].action is DefensiveSchemeAction.DEEP_PASS
    assert scored.match_events[1].action is OffensivePlayAction.RB_RUN
    assert scored.match_events[2].action is FootballConversionAction.EXTRA_POINT
    assert sum(
        event.points_scored
        for event in scored.match_events
        if event.scoring_team is FootballTeamSide.TEAM_A
    ) == scored.team_a_score
    assert sum(
        event.points_scored
        for event in scored.match_events
        if event.scoring_team is FootballTeamSide.TEAM_B
    ) == scored.team_b_score
    assert scored.final_result is not None
    assert (
        scored.final_result.team_a_score,
        scored.final_result.team_b_score,
        scored.final_result.winner,
    ) == (
        scored.team_a_score,
        scored.team_b_score,
        FootballTeamSide.TEAM_A,
    )
    with pytest.raises(AttributeError):
        scored.match_events[0].points_scored = 10


def test_stamina_fatigue_is_deterministic_bounded_and_affects_later_power():
    low_stamina_players = dict(_roster("Home", stamina=0.0).players)
    high_stamina_players = dict(_roster("Away", stamina=1.0).players)
    state = _match_state(
        team_a=FootballRoster("Home", low_stamina_players, _roster("Home").coach, FootballSpecialTeams()),
        team_b=FootballRoster("Away", high_stamina_players, _roster("Away").coach, FootballSpecialTeams()),
    )
    sim = FootballMatchSimulator(state)
    sim.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
    rng = SequenceRNG((0.99,) * (FATIGUE_RAMP_PLAYS + 2), (0.0,) * (FATIGUE_RAMP_PLAYS + 2))
    sim.rng = rng
    first_power = sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS).match_events[-1].play_result.offense_power
    for _ in range(FATIGUE_RAMP_PLAYS - 1):
        sim.state = replace(
            sim.state,
            down=1,
            yards_to_go=1.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    sim.state = replace(
        sim.state,
        down=1,
        yards_to_go=1.0,
        offense_field_position=25.0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
    )
    later_power = sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS).match_events[-1].play_result.offense_power
    assert later_power < first_power
    assert later_power >= first_power * (1.0 - MAX_FATIGUE_POWER_REDUCTION)
    assert later_power == pytest.approx(17.28)


def test_seeded_match_instance_replays_identical_actions_and_advances_one_rng():
    def play_sequence():
        sim = FootballMatchSimulator(_match_state(random_seed=291))
        sim.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
        sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
        sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
        return sim.state

    assert play_sequence() == play_sequence()

    stream = _sim_with_scheme(rng=SequenceRNG((0.99, 0.99), (0.0, 0.0)))
    stream.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert stream.rng.random_calls == 1
    stream.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert stream.rng.random_calls == 2


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda sim: sim.resolve_offensive_play(OffensivePlayAction.RB_RUN), "awaiting"),
        (lambda sim: sim.resolve_fourth_down(FootballFourthDownAction.PUNT), "awaiting"),
        (lambda sim: sim.select_defensive_scheme("bad"), "not in the current hand"),
        (lambda sim: sim.resolve_offensive_play("bad"), "awaiting"),
        (lambda sim: sim.resolve_fourth_down("bad"), "FootballFourthDownAction"),
    ],
)
def test_invalid_or_unawaited_actions_do_not_change_state_or_rng(operation, message):
    sim = FootballMatchSimulator(_match_state())
    before_state = sim.state
    before_rng = sim.rng.getstate()
    with pytest.raises(ValueError, match=message):
        operation(sim)
    assert sim.state is before_state
    assert sim.rng.getstate() == before_rng


def test_invalid_fourth_down_call_preserves_state_and_rng():
    sim = FootballMatchSimulator(
        _match_state(down=3, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY)
    )
    before = sim.state
    rng_state = sim.rng.getstate()
    with pytest.raises(ValueError, match="awaiting"):
        sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert sim.state is before
    assert sim.rng.getstate() == rng_state


def test_illegal_fourth_down_state_and_invalid_matchup_are_rejected():
    with pytest.raises(ValueError, match="fourth down"):
        FootballMatchState(
            **{
                "team_a": _roster("Home"),
                "team_b": _roster("Away"),
                "random_seed": 1,
                "team_a_score": 0,
                "team_b_score": 0,
                "possession": FootballTeamSide.TEAM_A,
                "down": 3,
                "yards_to_go": 10.0,
                "offense_field_position": 25.0,
                "game_clock_seconds": 900,
                "period": 1,
                "awaited_action": FootballAwaitedAction.FOURTH_DOWN_DECISION,
                "current_drive_defensive_scheme": DefensiveSchemeAction.RB_RUN,
            }
        )
    with pytest.raises(ValueError, match="Unsupported play"):
        matchup_for_play("not-a-play")


def test_expired_clock_and_non_tied_overtime_cannot_start_a_simulator():
    with pytest.raises(ValueError, match="expired period clock"):
        FootballMatchSimulator(_match_state(game_clock_seconds=0))
    with pytest.raises(ValueError, match="must start tied"):
        FootballMatchSimulator(
            _match_state(
                period=3,
                team_a_score=3,
                game_clock_seconds=300,
            )
        )
