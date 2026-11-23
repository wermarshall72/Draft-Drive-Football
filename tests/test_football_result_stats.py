from src.engine.football import (
    DefensiveSchemeAction,
    FootballBonusCardAction,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchStatus,
    FootballPlayResult,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.ui.football_result_stats import TeamGameStats, match_team_stats

A = FootballTeamSide.TEAM_A
B = FootballTeamSide.TEAM_B
RUN = OffensivePlayAction.RB_RUN
PASS = OffensivePlayAction.SHORT_PASS


def _event(sequence: int, action, possession, **fields) -> FootballMatchEvent:
    return FootballMatchEvent(
        sequence=sequence, action=action, team_a_score=0, team_b_score=0,
        possession=possession, offense_field_position=30.0, down=1,
        yards_to_go=10.0, game_clock_seconds=800, period=1,
        status=FootballMatchStatus.IN_PROGRESS, **fields,
    )


def _snap(sequence: int, play, after_possession, yards: float, **result_fields) -> FootballMatchEvent:
    result = FootballPlayResult(play, yards, 20, **result_fields)
    return _event(sequence, play, after_possession, play_result=result, clock_seconds_used=20)


def _scheme(sequence: int, possession) -> FootballMatchEvent:
    return _event(sequence, DefensiveSchemeAction.RB_RUN, possession)


def test_splits_rushing_and_passing_by_family_for_the_snapping_team() -> None:
    events = (
        _scheme(1, A),
        _snap(2, RUN, A, 6.0),
        _snap(3, OffensivePlayAction.POWER_TOSS, A, -2.0),
        _snap(4, PASS, A, 11.4),
        _snap(5, OffensivePlayAction.DEEP_PASS, A, 0.0, incomplete=True),
        _event(6, FootballFourthDownAction.PUNT, B),
        _scheme(7, B),
        _snap(8, OffensivePlayAction.MEDIUM_PASS, B, 17.0),
    )
    stats = match_team_stats(events)
    assert stats.team_a == TeamGameStats(
        rushing_yards=4, passing_yards=11, plays=4, turnovers=0, longest_play=11,
    )
    assert stats.team_a.total_yards == 15
    assert stats.team_b == TeamGameStats(passing_yards=17, plays=1, longest_play=17)
    assert stats.side(B) is stats.team_b


def test_turnovers_count_interceptions_fumbles_and_downs_for_the_offense() -> None:
    events = (
        _scheme(1, A),
        # Interception: possession flips to B; A threw it and gains no yards.
        _snap(2, PASS, B, 14.0, turnover=True, possession_changed=True,
              turnover_type=FootballTurnoverType.INTERCEPTION),
        _scheme(3, B),
        # Fumble after a 5-yard gain keeps the yards.
        _snap(4, RUN, A, 5.0, turnover=True, possession_changed=True,
              turnover_type=FootballTurnoverType.FUMBLE),
        _scheme(5, A),
        _snap(6, PASS, B, 0.0, incomplete=True, turnover_on_downs=True,
              possession_changed=True),
        # Untyped pass turnovers are treated as interceptions.
        _snap(7, PASS, A, 9.0, turnover=True, possession_changed=True),
    )
    stats = match_team_stats(events)
    assert stats.team_a.turnovers == 2
    assert stats.team_a.passing_yards == 0
    assert stats.team_b == TeamGameStats(rushing_yards=5, plays=2, turnovers=2, longest_play=5)


def test_challenge_overturned_snaps_and_conversion_tries_are_excluded() -> None:
    events = (
        _scheme(1, A),
        _snap(2, RUN, A, 3.0),
        _snap(3, PASS, B, 40.0, turnover=True, possession_changed=True,
              turnover_type=FootballTurnoverType.INTERCEPTION),
        _event(4, FootballBonusCardAction.CHALLENGE, A, reverses_event_sequences=(3,)),
        _snap(5, OffensivePlayAction.DEEP_PASS, A, 45.0),
        _event(6, FootballConversionAction.TWO_POINT, A),
        _snap(7, RUN, A, 2.0, conversion_attempt=True),
    )
    stats = match_team_stats(events)
    assert stats.team_a == TeamGameStats(
        rushing_yards=3, passing_yards=45, plays=2, turnovers=0, longest_play=45,
    )
    assert stats.team_b == TeamGameStats()


def test_empty_log_is_all_zero() -> None:
    stats = match_team_stats(())
    assert stats.team_a == stats.team_b == TeamGameStats()
    assert stats.team_a.longest_play == 0
