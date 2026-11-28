"""The end of a rival drive: detection, drive chart rows, the held possession change,
the result box, and the field's SKIP button."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAutomaticAction,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchStatus,
    FootballPerkDecision,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.engine.football_controller import FootballHumanDecision
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG
from src.ui.football_match_drive import (
    BOX_BUTTON_VARIANT, SKIP_DRIVE_LABEL, SKIP_LABEL, box_rect, skip_button_rect,
)
from src.ui.football_match_events import (
    CONTINUE_BUTTON,
    KICKOFF_BUTTON,
    TAKE_BALL_BUTTON,
    drive_chart_lines,
    rival_drive_end,
)
from src.ui.football_match_field import field_geometry
from src.ui.football_match_palette import text_audit
from src.ui.football_match_playback import EVENT_DURATION_MS, MatchPlayback
from src.ui.football_match_screen import FIELD_RECT

from test_football_desktop import (
    _new_desktop, _play_human_decision, _start_match, _surface,
)
from test_football_match_presentation import _event, _snap

A = FootballTeamSide.TEAM_A
B = FootballTeamSide.TEAM_B
RUN = OffensivePlayAction.RB_RUN
PASS = OffensivePlayAction.SHORT_PASS


def _drive_opening() -> list:
    """The human's punt hands the ball to the rival, the human sets a defense, two snaps."""
    return [
        _event(1, FootballFourthDownAction.PUNT, B, 25.0, gross_yards=40.0),
        _event(2, DefensiveSchemeAction.RB_RUN, B, 25.0),
        _snap(3, RUN, B, 31.0, 6.0),
        _snap(4, PASS, B, 43.0, 12.0, down=1),
    ]


class _Match:
    def __init__(self, events, seed: int = 1) -> None:
        self.match_events = tuple(events)
        self.random_seed = seed
        self.team_a = type("T", (), {"team_name": "Owls"})()
        self.team_b = type("T", (), {"team_name": "Hawks"})()


# -- detection ------------------------------------------------------------------------


def test_punt_is_held_back_and_the_drive_starts_at_the_scheme_call() -> None:
    events = _drive_opening() + [
        _event(5, FootballFourthDownAction.PUNT, A, 20.0, gross_yards=45.0),
        _event(6, DefensiveSchemeAction.SHORT_PASS, A, 20.0),  # the rival's secret call
    ]
    drive = rival_drive_end(tuple(events), 1, "Hawks")
    assert drive is not None
    assert (drive.start, drive.hold) == (1, 4)
    assert (drive.headline, drive.detail, drive.button) == ("HAWKS PUNT", "", TAKE_BALL_BUTTON)
    # The chart is the two snaps; the punt is not part of it.
    assert len(drive_chart_lines(tuple(events), drive.start, drive.hold)) == 2


def test_touchdown_keeps_its_conversion_and_holds_the_kickoff() -> None:
    events = _drive_opening() + [
        _snap(5, PASS, B, 98.0, 57.0, points=6, scoring_team=B, score=(0, 6)),
        _event(6, FootballConversionAction.EXTRA_POINT, A, 25.0, points_scored=1,
               scoring_team=B, score=(0, 7)),
        _event(7, FootballAutomaticAction.KICKOFF, A, 25.0, gross_yards=65.0),
    ]
    drive = rival_drive_end(tuple(events), 1, "Hawks")
    assert drive is not None and drive.hold == 6
    assert (drive.headline, drive.detail, drive.button) == (
        "HAWKS TOUCHDOWN", "EXTRA POINT GOOD", KICKOFF_BUTTON,
    )
    assert len(drive_chart_lines(tuple(events), drive.start, drive.hold)) == 4  # 3 snaps + PAT


@pytest.mark.parametrize(
    ("last", "headline", "detail", "button", "held"),
    [
        (_event(5, FootballFourthDownAction.FIELD_GOAL, A, 25.0, points_scored=3,
                scoring_team=B, field_goal_distance=40.0),
         "HAWKS FIELD GOAL", "", KICKOFF_BUTTON, False),
        (_event(5, FootballFourthDownAction.FIELD_GOAL, A, 40.0, field_goal_distance=50.0),
         "HAWKS MISSED FIELD GOAL", "", TAKE_BALL_BUTTON, True),
        (_snap(5, PASS, A, 60.0, 3.0, turnover=True, possession_changed=True,
               turnover_type=FootballTurnoverType.INTERCEPTION),
         "HAWKS TURNOVER", "INTERCEPTION", TAKE_BALL_BUTTON, True),
        (_snap(5, RUN, A, 55.0, 2.0, turnover_on_downs=True, possession_changed=True),
         "HAWKS TURNOVER ON DOWNS", "", TAKE_BALL_BUTTON, True),
    ],
)
def test_each_drive_ending_names_the_rival_and_its_button(last, headline, detail, button, held) -> None:
    events = _drive_opening() + [last, _event(6, FootballAutomaticAction.KICKOFF, A, 25.0)]
    drive = rival_drive_end(tuple(events), 1, "Hawks")
    assert drive is not None
    assert (drive.headline, drive.detail, drive.button) == (headline, detail, button)
    assert drive.hold == (4 if held else 5)


def test_defensive_touchdown_is_the_last_play_and_nothing_is_held() -> None:
    events = _drive_opening() + [
        _snap(5, PASS, A, 98.0, 2.0, turnover=True, possession_changed=True,
              turnover_type=FootballTurnoverType.INTERCEPTION, points=6, scoring_team=A,
              score=(6, 0)),
    ]
    drive = rival_drive_end(tuple(events), 1, "Hawks")
    assert drive is not None and drive.hold == drive.end == 5
    assert (drive.headline, drive.button) == ("DEFENSIVE TOUCHDOWN", CONTINUE_BUTTON)


def test_halftime_and_end_of_game_end_the_drive_with_continue() -> None:
    half = _drive_opening() + [
        replace(_snap(5, RUN, B, 25.0, 4.0), period=2),  # the snapshot is already the second half
        _event(6, FootballAutomaticAction.KICKOFF, A, 25.0, period=2),
    ]
    drive = rival_drive_end(tuple(half), 1, "Hawks")
    assert drive is not None and drive.headline == "HALFTIME" and drive.hold == 5
    assert drive.button == CONTINUE_BUTTON
    final = _drive_opening() + [
        replace(_snap(5, RUN, B, 47.0, 4.0), status=FootballMatchStatus.COMPLETED),
    ]
    drive = rival_drive_end(tuple(final), 1, "Hawks")
    assert drive is not None and drive.headline == "END OF GAME" and drive.hold == 5


def test_a_drive_split_by_green_dog_charts_plays_from_before_the_decision() -> None:
    events = _drive_opening() + [
        _event(5, FootballPerkDecision.GREEN_DOG_DECLINE, B, 43.0),
        _snap(6, RUN, B, 50.0, 7.0),
        _event(7, FootballFourthDownAction.PUNT, A, 15.0, gross_yards=40.0),
    ]
    drive = rival_drive_end(tuple(events), 4, "Hawks")  # the second update starts at Green Dog
    assert drive is not None and drive.start == 1 and drive.hold == 6
    assert len(drive_chart_lines(tuple(events), drive.start, drive.hold)) == 3


def test_human_offense_never_ends_a_rival_drive() -> None:
    events = [
        _event(1, DefensiveSchemeAction.RB_RUN, A, 25.0),
        _snap(2, RUN, A, 31.0, 6.0),
        _event(3, FootballFourthDownAction.PUNT, B, 30.0, gross_yards=40.0),
    ]
    assert rival_drive_end(tuple(events), 0, "Hawks") is None


# -- playback ---------------------------------------------------------------------------


def _punt_drive_match() -> _Match:
    return _Match(_drive_opening() + [
        _event(5, FootballFourthDownAction.PUNT, A, 20.0, gross_yards=45.0),
        _event(6, DefensiveSchemeAction.SHORT_PASS, A, 20.0),
    ])


def test_replay_stops_before_the_possession_change_and_skip_opens_the_box() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(_drive_opening()[:1]), 0)
    match = _punt_drive_match()
    playback.sync(match, 1000)
    assert playback.rival_drive_replay and not playback.box_open
    for step in range(1, 10):
        playback.sync(match, 1000 + step * EVENT_DURATION_MS)
        assert playback.shown <= 4  # the punt never animates before the box
    assert playback.box_open and playback.blocking() and playback.shown == 4
    assert playback.chart_range() == (1, 4)

    skipped = MatchPlayback()
    skipped.sync(_Match(_drive_opening()[:1]), 0)
    skipped.sync(match, 1000)
    skipped.skip()
    assert skipped.box_open and skipped.shown == 4
    skipped.skip()  # SKIP never goes past the box
    assert skipped.box_open and skipped.shown == 4


def test_release_plays_the_possession_change_as_one_step_then_unblocks() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(_drive_opening()[:1]), 0)
    match = _punt_drive_match()
    playback.sync(match, 1000)
    playback.skip()
    playback.release(5000, match.match_events)
    assert not playback.box_open and playback.blocking()
    assert playback.shown == 6 and playback.current_step_start() == 4
    assert playback.chart_range() == (1, 6)  # the punt joins the chart while it animates
    assert not playback.rival_drive_replay
    playback.sync(match, 5000 + EVENT_DURATION_MS)
    assert not playback.blocking()
    assert playback.chart_visible  # until the human's next play
    match = _Match(match.match_events + (_snap(7, RUN, A, 30.0, 4.0),))
    playback.sync(match, 7000)
    assert not playback.chart_visible


def test_finish_skips_the_box_for_resume() -> None:
    playback = MatchPlayback()
    playback.sync(_Match(_drive_opening()[:1]), 0)
    match = _punt_drive_match()
    playback.sync(match, 1000)
    playback.skip()
    playback.finish()
    assert not playback.blocking() and playback.shown == 6 and playback.drive is None


def test_skip_button_sits_in_the_fields_bottom_right_clear_of_end_zone_and_numbers() -> None:
    pygame.font.init()
    geometry = field_geometry(FIELD_RECT)
    for label in (SKIP_DRIVE_LABEL, SKIP_LABEL):
        rect = skip_button_rect(FIELD_RECT, label)
        assert FIELD_RECT.contains(rect)
        assert rect.right <= geometry.right_end_zone.left
        # The yard numbers sit at 83% of the turf height (center) in a 26px font.
        assert rect.top > geometry.playing.top + round(geometry.playing.height * 0.83) + 13
    assert FIELD_RECT.contains(box_rect(FIELD_RECT))


# -- the real match screen ----------------------------------------------------------------


def _reach_drive_box(desktop, now):
    controller = desktop.football_controller
    screen = desktop.run_screen
    for _ in range(400):
        desktop.router.draw(_surface())
        playback = screen.match_screen.playback
        if playback.box_open:
            return playback
        if playback.blocking():
            screen.match_screen.playback.skip()
            continue
        if controller.state.human_decision is FootballHumanDecision.GREEN_DOG:
            controller.respond_to_green_dog(None)
            screen.state = controller.state
        else:
            _play_human_decision(desktop)
        if controller.state.match is None:
            break
    pytest.fail("No rival drive ended in the seeded match.")


def test_desktop_drive_box_shows_result_score_and_releases_on_enter(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    now = [100_000]
    screen.match_screen.clock = lambda: now[0]
    playback = _reach_drive_box(desktop, now)
    drive = playback.drive
    match = desktop.football_controller.state.match
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert drive.headline in texts and drive.button in texts
    # Only the box's button and PAUSE take input; no hand card can be played.
    assert [button.variant for button in screen.buttons] == [BOX_BUTTON_VARIANT, "match-pause"]
    # Lines and symbols only on the chart, and the rival's call stays secret.
    assert not {"TURNOVER", "BLOCKED"} & set(texts)  # no chart tags
    secret = {scheme.name.upper() for scheme in DEFENSIVE_SCHEME_CATALOG.values()}
    field_texts = [text for text, rect, _ in records if FIELD_RECT.contains(rect)]
    assert not any(name in text for text in field_texts for name in secret
                   if "YOUR DEFENSE" not in text)
    unchanged = desktop.football_controller.state
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_1}))
    assert desktop.football_controller.state == unchanged and playback.box_open
    # Esc opens the pause menu over the box; closing it returns to the box.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert screen.match_screen.popup.kind == "pause"
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    desktop.router.draw(_surface())
    assert playback.box_open
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert not playback.box_open
    now[0] += EVENT_DURATION_MS
    desktop.router.draw(_surface())
    assert not playback.blocking()
    assert len(screen.match_screen.display_match(match).match_events) == len(match.match_events)
    decision = desktop.football_controller.state.human_decision
    if decision is FootballHumanDecision.OFFENSIVE_PLAY:
        assert any(button.variant == "hand-card" and button.enabled for button in screen.buttons)


def test_returning_to_the_menu_while_the_box_shows_resumes_at_the_decision(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    now = [100_000]
    screen.match_screen.clock = lambda: now[0]
    _reach_drive_box(desktop, now)
    screen.match_screen.settle()
    desktop.router.draw(_surface())
    assert not screen.match_screen.playback.blocking()
    assert not any(button.variant == BOX_BUTTON_VARIANT for button in screen.buttons)


@pytest.mark.parametrize("count", [1, 6, 12, 40, 150])
def test_chart_rows_stack_top_to_bottom_and_compress_to_fit_the_field(count) -> None:
    from src.ui.football_match_field import chart_rows

    geometry = field_geometry(FIELD_RECT)
    rows, _spacing = chart_rows(geometry, count)
    assert len(rows) == count and rows == sorted(rows)
    assert geometry.turf.top < rows[0] and rows[-1] < geometry.turf.bottom
