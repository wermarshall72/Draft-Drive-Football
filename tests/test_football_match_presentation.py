"""Pure match-screen presentation: play lines, outcome wording, and playback."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from src.engine.football import (
    OFFENSIVE_PLAY_FAMILIES,
    DefensiveSchemeAction,
    FootballAutomaticAction,
    FootballBonusCardAction,
    FootballCardFamily,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchStatus,
    FootballPlayResult,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.ui.football_match_events import (
    CLEAR_LINE,
    OutcomeEmphasis,
    PlayLineKind,
    active_scheme,
    format_yards,
    latest_play_line,
    outcome,
    period_banner,
    play_line,
)
from src.ui.football_match_field import PLAY_LINE_COLORS
from src.ui.football_match_palette import (
    MATCH_OPPONENT,
    PLAY_LINE_CASING,
    TURF_DARK,
    TURF_LIGHT,
)
from src.ui.football_match_playback import EVENT_DURATION_MS, MatchPlayback
from src.ui.theme import relative_luminance

A = FootballTeamSide.TEAM_A
B = FootballTeamSide.TEAM_B


def _event(
    sequence: int,
    action,
    possession: FootballTeamSide,
    position: float,
    *,
    down: int = 1,
    yards_to_go: float = 10.0,
    period: int = 1,
    score: tuple[int, int] = (0, 0),
    status: FootballMatchStatus = FootballMatchStatus.IN_PROGRESS,
    **fields,
) -> FootballMatchEvent:
    return FootballMatchEvent(
        sequence=sequence,
        action=action,
        team_a_score=score[0],
        team_b_score=score[1],
        possession=possession,
        offense_field_position=position,
        down=down,
        yards_to_go=yards_to_go,
        game_clock_seconds=800,
        period=period,
        status=status,
        **fields,
    )


def _snap(
    sequence: int,
    play: OffensivePlayAction,
    possession: FootballTeamSide,
    position: float,
    yards: float,
    **result_fields,
) -> FootballMatchEvent:
    points = result_fields.pop("points", 0)
    scoring_team = result_fields.pop("scoring_team", None)
    score = result_fields.pop("score", (0, 0))
    down = result_fields.pop("down", 2)
    result = FootballPlayResult(
        offensive_play=play,
        yards_gained=yards,
        clock_seconds_used=20,
        points_scored=points,
        **result_fields,
    )
    return _event(
        sequence, play, possession, position, down=down, score=score,
        clock_seconds_used=20, play_result=result, points_scored=points,
        scoring_team=scoring_team, perk_effects=result.perk_effects,
    )


def _scheme(sequence: int, possession=A, position=25.0) -> FootballMatchEvent:
    return _event(sequence, DefensiveSchemeAction.RB_RUN, possession, position)


@pytest.mark.parametrize("play", list(OffensivePlayAction))
def test_play_line_color_follows_family_for_every_offensive_card(play) -> None:
    before = _scheme(1, A, 30.0)
    event = _snap(2, play, A, 34.0, 4.0)
    line = play_line(event, before)
    assert line is not None and len(line.segments) == 1
    expected = (
        PlayLineKind.RUN
        if OFFENSIVE_PLAY_FAMILIES[play] is FootballCardFamily.RB_RUN
        else PlayLineKind.PASS
    )
    assert line.segments[0].kind is expected
    assert (line.segments[0].start, line.segments[0].end) == pytest.approx((30.0, 34.0))


def test_qb_keeper_play_action_variants_draw_as_passes() -> None:
    for play in (OffensivePlayAction.QB_KEEPER_PA, OffensivePlayAction.BOOTLEG_KEEPER):
        line = play_line(_snap(2, play, A, 33.0, 3.0), _scheme(1, A, 30.0))
        assert line is not None and line.segments[0].kind is PlayLineKind.PASS


def test_lost_yardage_draws_backward_for_both_directions() -> None:
    line = play_line(_snap(2, OffensivePlayAction.RB_RUN, A, 27.0, -3.0), _scheme(1, A, 30.0))
    assert line is not None
    assert line.segments[0].start == pytest.approx(30.0)
    assert line.segments[0].end == pytest.approx(27.0)
    # Team B attacks toward absolute 0, so its loss moves the line toward 100.
    line = play_line(_snap(2, OffensivePlayAction.RB_RUN, B, 37.0, -3.0), _scheme(1, B, 40.0))
    assert line is not None
    assert line.segments[0].start == pytest.approx(60.0)
    assert line.segments[0].end == pytest.approx(63.0)


def test_incomplete_pass_draws_only_an_x_at_the_line_of_scrimmage() -> None:
    event = _snap(2, OffensivePlayAction.DEEP_PASS, A, 30.0, 0.0, incomplete=True)
    line = play_line(event, _scheme(1, A, 30.0))
    assert line is not None
    assert line.segments == ()
    assert line.incomplete_at == pytest.approx(30.0)
    assert outcome(event, _scheme(1, A, 30.0), "Home", "Away").headline == "INCOMPLETE"


def test_interception_with_return_draws_turnover_then_grey_return() -> None:
    before = _scheme(1, A, 40.0)
    # Ball-Hawk: the defense takes over 10 yards beyond the line of scrimmage.
    event = _snap(
        2, OffensivePlayAction.DEEP_PASS, B, 70.0, 0.0,
        turnover=True, possession_changed=True, down=1,
        turnover_type=FootballTurnoverType.INTERCEPTION,
        perk_effects=("Ball-Hawk: +10 interception return yards",),
    )
    line = play_line(event, before)
    assert line is not None
    assert line.turnover_at == pytest.approx(40.0)
    assert [segment.kind for segment in line.segments] == [PlayLineKind.OTHER]
    assert (line.segments[0].start, line.segments[0].end) == pytest.approx((40.0, 30.0))
    result = outcome(event, before, "Home", "Away")
    assert result.headline == "INTERCEPTION · RETURNED 10"
    assert result.emphasis is OutcomeEmphasis.TURNOVER


def test_fumble_draws_the_run_to_the_turnover_spot() -> None:
    before = _scheme(1, A, 40.0)
    event = _snap(
        2, OffensivePlayAction.RB_RUN, B, 62.0, -2.0,
        turnover=True, possession_changed=True, down=1,
        turnover_type=FootballTurnoverType.FUMBLE,
    )
    line = play_line(event, before)
    assert line is not None
    assert line.segments[0].kind is PlayLineKind.RUN
    assert (line.segments[0].start, line.segments[0].end) == pytest.approx((40.0, 38.0))
    assert line.turnover_at == pytest.approx(38.0)
    assert len(line.segments) == 1  # no return beyond the recovery spot
    assert outcome(event, before, "Home", "Away").headline == "FUMBLE"


def test_touchdown_and_field_goal_flash_the_scoring_end_zone() -> None:
    before = _scheme(1, A, 90.0)
    touchdown = _snap(
        2, OffensivePlayAction.SHORT_PASS, A, 98.0, 12.0,
        points=6, scoring_team=A, possession_changed=True, score=(6, 0), down=1,
    )
    line = play_line(touchdown, before)
    assert line is not None
    assert line.flash_end_zone == 100.0
    assert line.segments[0].end == 100.0
    assert outcome(touchdown, before, "Home", "Away").emphasis is OutcomeEmphasis.SCORE

    fourth = _event(1, FootballFourthDownAction.GO_FOR_IT, B, 70.0, down=4)
    made = _event(
        2, FootballFourthDownAction.FIELD_GOAL, A, 25.0, score=(0, 3),
        field_goal_distance=40.0, points_scored=3, scoring_team=B, clock_seconds_used=5,
    )
    line = play_line(made, fourth)
    assert line is not None
    assert line.flash_end_zone == 0.0
    assert line.segments[0].kind is PlayLineKind.OTHER
    assert outcome(made, fourth, "Home", "Away").headline == "FIELD GOAL GOOD · 40 YDS"
    missed = _event(
        2, FootballFourthDownAction.FIELD_GOAL, A, 70.0, field_goal_distance=40.0,
        clock_seconds_used=5,
    )
    line = play_line(missed, fourth)
    assert line is not None and line.flash_end_zone is None
    assert outcome(missed, fourth, "Home", "Away").headline == "FIELD GOAL MISSED · 40 YDS"


def test_punt_kickoff_and_blocked_kick_lines_are_grey() -> None:
    before = _event(1, FootballFourthDownAction.GO_FOR_IT, A, 30.0, down=4)
    punt = _event(
        2, FootballFourthDownAction.PUNT, B, 35.0, gross_yards=43.0, return_yards=8.0,
        clock_seconds_used=10, description="Punt 43.0 yards, returned 8.0",
    )
    line = play_line(punt, before)
    assert line is not None
    assert [segment.kind for segment in line.segments] == [PlayLineKind.OTHER] * 2
    assert (line.segments[0].start, line.segments[0].end) == pytest.approx((30.0, 73.0))
    assert (line.segments[1].start, line.segments[1].end) == pytest.approx((73.0, 65.0))
    assert outcome(punt, before, "Home", "Away").headline == "PUNT · 43 YARDS"

    kickoff = _event(
        3, FootballAutomaticAction.KICKOFF, A, 25.0, gross_yards=65.0, return_yards=0.0,
        clock_seconds_used=10, description="Kickoff touchback",
    )
    line = play_line(kickoff, punt)
    assert line is not None
    assert all(segment.kind is PlayLineKind.OTHER for segment in line.segments)
    assert (line.segments[0].start, line.segments[0].end) == pytest.approx((65.0, 0.0))
    assert outcome(kickoff, punt, "Home", "Away").headline == "KICKOFF · TOUCHBACK"

    blocked = _event(
        2, FootballFourthDownAction.PUNT, B, 72.0, gross_yards=0.0, return_yards=2.0,
        blocked=True, clock_seconds_used=10,
        description="Blocked kick recovered and returned 2.0 yards",
    )
    line = play_line(blocked, before)
    assert line is not None
    assert line.blocked_at == pytest.approx(30.0)
    assert all(segment.kind is PlayLineKind.OTHER for segment in line.segments)
    assert outcome(blocked, before, "Home", "Away").headline == "BLOCKED KICK"


def test_challenge_clears_the_line_and_non_snaps_keep_the_previous_line() -> None:
    before = _scheme(1, A, 30.0)
    snap = _snap(2, OffensivePlayAction.RB_RUN, A, 34.0, 4.0)
    go = _event(3, FootballFourthDownAction.GO_FOR_IT, A, 34.0, down=4)
    assert play_line(go, snap) is None
    assert latest_play_line((before, snap, go))[0] == 1
    challenge = _event(
        4, FootballBonusCardAction.CHALLENGE, A, 30.0,
        card_id="challenge", description="Challenge accepted",
        reverses_event_sequences=(2,),
    )
    assert play_line(challenge, go) == CLEAR_LINE
    assert latest_play_line((before, snap, go, challenge)) is None
    assert outcome(challenge, go, "Home", "Away").headline == "CHALLENGE · PLAY OVERTURNED"


def test_outcome_wording_for_yards_first_downs_and_conversions() -> None:
    before = _scheme(1, A, 30.0)
    first = _snap(2, OffensivePlayAction.SLOT_SLANT, A, 42.0, 12.0, down=1)
    result = outcome(first, before, "Molly", "Local AI")
    assert result.headline == "+12 YARDS · FIRST DOWN"
    assert result.detail == "SLOT SLANT · MOLLY"
    assert result.kind is PlayLineKind.PASS
    assert outcome(_snap(2, OffensivePlayAction.RB_RUN, A, 31.0, 1.0), before, "M", "L").headline == "+1 YARD"
    assert outcome(_snap(2, OffensivePlayAction.RB_RUN, A, 30.0, 0.0), before, "M", "L").headline == "NO GAIN"
    assert format_yards(-3.2) == "-3 YARDS"
    downs = _snap(
        2, OffensivePlayAction.RB_RUN, B, 67.0, 3.0,
        possession_changed=True, turnover_on_downs=True, down=1,
    )
    assert outcome(downs, before, "Home", "Away").headline == "+3 YARDS · TURNOVER ON DOWNS"
    # Without a previous event the offense is inferred from the possession change.
    assert "HOME" in outcome(downs, None, "Home", "Away").detail

    conversion_before = _snap(
        2, OffensivePlayAction.SHORT_PASS, A, 98.0, 5.0,
        points=6, scoring_team=A, possession_changed=True, score=(6, 0), down=1,
    )
    extra = _event(3, FootballConversionAction.EXTRA_POINT, B, 25.0, score=(7, 0),
                   points_scored=1, scoring_team=A, description="Extra point good")
    assert outcome(extra, conversion_before, "Home", "Away").headline == "EXTRA POINT GOOD"
    two = _event(3, FootballConversionAction.TWO_POINT, B, 25.0, score=(8, 0),
                 points_scored=2, scoring_team=A, description="Two-point rb run successful",
                 card_id="rb_run", gross_yards=3.0)
    result = outcome(two, conversion_before, "Home", "Away")
    assert result.headline == "2-PT GOOD" and result.kind is PlayLineKind.RUN
    line = play_line(two, conversion_before)
    assert line is not None and line.segments[0].kind is PlayLineKind.RUN


def test_scheme_events_and_period_banners() -> None:
    scheme = _scheme(1, A, 25.0)
    # The rival (Team B) defends: its call stays secret.
    result = outcome(scheme, None, "Home", "Away")
    assert result.headline == "AWAY SET THEIR DEFENSE"
    assert "RUN FIT" not in result.headline + result.detail
    assert "STOPS" not in result.headline + result.detail
    assert result.kind is PlayLineKind.OTHER
    own = outcome(_scheme(1, B, 25.0), None, "Home", "Away")
    assert own.headline == "DEFENSE SET · RUN FIT"
    assert own.detail == "HOME · STOPS RB RUN"
    assert active_scheme((scheme,)) is DefensiveSchemeAction.RB_RUN
    punt = _event(2, FootballFourthDownAction.PUNT, B, 30.0, gross_yards=40.0,
                  return_yards=0.0, clock_seconds_used=10)
    assert active_scheme((scheme, punt)) is None
    half = _event(2, FootballAutomaticAction.KICKOFF, A, 25.0, period=2,
                  gross_yards=65.0, return_yards=0.0)
    assert period_banner(half, scheme) == "HALFTIME"
    overtime = _event(3, DefensiveSchemeAction.RB_RUN, A, 25.0, period=3)
    assert period_banner(overtime, half) == "OVERTIME"


def _contrast(first: pygame.Color, second: pygame.Color) -> float:
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_play_line_colors_are_distinct_and_read_on_turf_and_end_zones() -> None:
    colors = list(PLAY_LINE_COLORS.values())
    assert len({tuple(color) for color in colors}) == 3
    for color in colors:
        # Hue separates red/blue from turf; the casing below guarantees edge contrast.
        assert _contrast(color, TURF_DARK) >= 2.0
        assert _contrast(color, TURF_LIGHT) >= 1.6
        # The dark casing separates every line from any end-zone color.
        assert _contrast(color, PLAY_LINE_CASING) >= 4.5
    assert _contrast(PLAY_LINE_COLORS[PlayLineKind.OTHER], MATCH_OPPONENT) >= 1.5


class _Match:
    """Just enough of a match for MatchPlayback."""

    def __init__(self, events: int, seed: int = 1) -> None:
        # Human-offense snapshots: no rival drive, so no result box.
        self.match_events = tuple(
            _event(index + 1, DefensiveSchemeAction.RB_RUN, FootballTeamSide.TEAM_A, 25.0)
            for index in range(events)
        )
        self.random_seed = seed
        self.team_a = type("T", (), {"team_name": "Home"})()
        self.team_b = type("T", (), {"team_name": "Away"})()


def test_playback_replays_new_events_in_order_and_blocks_until_done() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(3), 0)
    assert playback.shown == 3 and not playback.blocking()

    playback.sync(_Match(7), 1000)
    assert playback.blocking()
    assert playback.shown == 4 and playback.replay_position == (1, 4)
    shown = []
    for step in range(1, 5):
        playback.sync(_Match(7), 1000 + step * EVENT_DURATION_MS - 1)
        shown.append(playback.shown)
    assert shown == [4, 5, 6, 7]
    assert playback.blocking()  # the final event still plays its full duration
    playback.sync(_Match(7), 1000 + 4 * EVENT_DURATION_MS)
    assert not playback.blocking() and playback.shown == 7


def test_single_new_event_animates_without_blocking_and_skip_jumps_to_latest() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(3), 0)
    playback.sync(_Match(4), 500)
    assert not playback.blocking() and playback.shown == 4
    assert playback.line_progress(500) == 0.0
    assert playback.line_progress(1000) == 1.0

    playback.sync(_Match(9), 2000)
    assert playback.blocking()
    playback.skip()
    assert not playback.blocking() and playback.shown == 9
    assert playback.line_progress(2000) == 1.0


def test_final_events_replay_even_when_single_and_new_matches_start_settled() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(3), 0)
    playback.sync(_Match(4), 100, force_replay=True)
    assert playback.blocking() and playback.shown == 4
    playback.sync(_Match(2, seed=99), 200)
    assert playback.shown == 2 and not playback.blocking()


def test_bonus_effect_wording_matches_the_new_draw_rules() -> None:
    from src.ui.football_match_events import bonus_effect

    assert "DRAW" not in bonus_effect(FootballBonusCardAction.OPPONENT_DISCARD)
    assert bonus_effect(FootballBonusCardAction.OPPONENT_DISCARD) != bonus_effect(
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD
    )
    for action in (
        FootballBonusCardAction.OFFENSIVE_DRAW,
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD,
        FootballBonusCardAction.DEFENSIVE_DRAW,
        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
    ):
        assert bonus_effect(action).startswith("+1")


def test_replay_snapshot_after_a_draw_card_keeps_live_hand_and_pile_counts() -> None:
    from src.engine.football import FootballCardCopy, FootballDeckState
    from src.engine.football_simulator import FootballMatchSimulator
    from src.ui.football_match_events import snapshot_state
    from src.ui.football_match_piles import pile_counts
    from tests.test_football_bonus_cards import _deck, _match_state

    bonus = FootballCardCopy("human:draw", FootballBonusCardAction.OFFENSIVE_DRAW.value)
    plays = tuple(
        FootballCardCopy(f"human:play:{index}", OffensivePlayAction.RB_RUN.value)
        for index in range(5)
    )
    simulator = FootballMatchSimulator(
        _match_state(_deck((bonus,) + plays, (bonus,) + plays[:2], plays[2:]))
    )
    simulator.resolve_bonus_card(bonus.copy_id)
    after_draw = simulator.resolve_offensive_play(plays[0].copy_id)
    deck = after_draw.team_a_offense_deck
    assert isinstance(deck, FootballDeckState)
    for shown in range(1, len(after_draw.match_events) + 1):
        display = snapshot_state(after_draw, shown)
        assert display.team_a_offense_deck == deck
        counts = pile_counts(display.team_a_offense_deck)
        assert counts.hand + counts.draw + counts.discard == counts.owned
    # The enlarged hand (3 -> 4) survived the following normal play.
    assert len(deck.hand) == 4
