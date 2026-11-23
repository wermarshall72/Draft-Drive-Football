from dataclasses import replace

import pygame
import pytest

from src.engine.football import (
    FootballMatchResult,
    FootballMatchStatus,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballRunPhase,
    FootballSeasonGame,
    FootballSeasonOutcome,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.profile import new_team_profile
from src.ui.football_result import (
    OPEN_NEXT_SHOP,
    RETURN_TO_MENU,
    FootballResultView,
    ResultVariant,
    result_variant,
)
from src.ui.football_result_stats import match_team_stats
from src.ui.football_ui_kit import text_audit
from src.ui.theme import Theme

W, L, BYE = FootballSeasonOutcome.WIN, FootballSeasonOutcome.LOSS, FootballSeasonOutcome.BYE


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield


@pytest.fixture(scope="module")
def finished() -> FootballGameControllerState:
    """A real completed game 1 (31-17 win) with a recorded play log."""
    controller = FootballGameController(
        "Test Owls", difficulty=FootballAIDifficulty.EASY,
        builder_seed=17, shop_seed=29, ai_seed=41, match_seed=53,
    )
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        controller.choose_player(position, 0)
    controller.finish_shop()
    original = FootballMatchSimulator.resolve_offensive_play
    played = {"count": 0}

    def finish_after_a_few(simulator, play):
        state = original(simulator, play)
        played["count"] += 1
        if played["count"] < 6 or simulator.state.status is FootballMatchStatus.COMPLETED:
            return state
        simulator.state = replace(
            simulator.state, team_a_score=31, team_b_score=17,
            status=FootballMatchStatus.COMPLETED, awaited_action=None,
            current_drive_defensive_scheme=None,
            final_result=FootballMatchResult(31, 17, FootballTeamSide.TEAM_A, True),
        )
        return simulator.state

    FootballMatchSimulator.resolve_offensive_play = finish_after_a_few
    try:
        for _ in range(500):
            state = controller.state
            if state.phase is not FootballRunPhase.MATCH:
                break
            if state.match.team_a_offense_deck.hand and state.human_decision.value == "offensive_play":
                controller.choose_offensive_play(state.match.team_a_offense_deck.hand[0].copy_id)
            elif state.human_decision.value == "defensive_scheme":
                controller.choose_defensive_scheme(state.match.team_a_defense_deck.hand[0].copy_id)
            elif state.human_decision.value == "fourth_down":
                from src.engine.football import FootballFourthDownAction
                controller.choose_fourth_down(FootballFourthDownAction.PUNT)
            elif state.human_decision.value == "conversion":
                from src.engine.football import FootballConversionAction
                controller.choose_conversion(FootballConversionAction.EXTRA_POINT)
            else:
                controller.respond_to_challenge(False)
    finally:
        FootballMatchSimulator.resolve_offensive_play = original
    state = controller.state
    assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    assert state.match is not None and len(state.match.match_events) > 6
    return state


def _season(state, phase, history, *, skipped=(), message=None, team=None):
    history = tuple(history)
    match = state.match
    if team is not None:
        match = replace(match, team_a=replace(match.team_a, team_name=team))
    return replace(
        state, phase=phase, game_number=history[-1].game_number,
        wins=sum(game.outcome is W for game in history),
        losses=sum(game.outcome is L for game in history),
        games_played=sum(game.outcome is not BYE for game in history),
        skipped_games=tuple(skipped), season_history=history,
        transition_message=message, match=match,
    )


def _played(number, outcome, score=(24, 17)):
    return FootballSeasonGame(number, outcome, *score)


def _draw(state, *, clock=None, color="navy", error=None):
    calls: list[str] = []
    view = FootballResultView(
        lambda: calls.append("shop"), lambda: calls.append("menu"), lambda: calls.append("exit"),
        clock=clock,
    )
    theme = Theme.from_profile(new_team_profile("Test Owls", color, "gold" if color != "gold" else "navy"))
    surface = pygame.Surface((1280, 720))
    with text_audit() as records:
        buttons = view.draw(surface, state, theme, error=error)
    return buttons, [text for text, _rect, _container in records], records, calls, view


def _variants(finished):
    nine = [_played(n, W if n not in (3, 6) else L) for n in range(1, 10)]
    return {
        ResultVariant.REGULAR: finished,
        ResultVariant.FIRED: _season(
            replace(finished, match=replace(
                finished.match, team_a_score=17, team_b_score=31,
                final_result=FootballMatchResult(17, 31, FootballTeamSide.TEAM_B, True))),
            FootballRunPhase.FIRED,
            [_played(1, L), _played(2, W), _played(3, L), _played(4, L, (17, 31))],
        ),
        ResultVariant.PLAYOFFS: _season(
            finished, FootballRunPhase.PLAYOFFS, [*nine, _played(10, W, (31, 17))],
        ),
        ResultVariant.BYE_WEEK: _season(
            finished, FootballRunPhase.PLAYOFFS, [*nine, FootballSeasonGame(10, BYE)],
            skipped=(10,), message="Bye Week skipped scheduled game 10 without a match result.",
        ),
    }


def test_each_variant_has_its_banner_and_primary_action(finished) -> None:
    expected = {
        ResultVariant.REGULAR: ("WIN", OPEN_NEXT_SHOP, "shop", "NEXT UP · SHOP BEFORE GAME 2"),
        ResultVariant.FIRED: ("FIRED", RETURN_TO_MENU, "menu", "RUN OVER · 3 LOSSES  ·  FINAL RECORD 1-3"),
        ResultVariant.PLAYOFFS: ("PLAYOFFS", RETURN_TO_MENU, "menu",
                                 "REGULAR SEASON COMPLETE  ·  8-2  ·  PLAYOFF GAMES AREN'T AVAILABLE YET"),
        ResultVariant.BYE_WEEK: ("BYE WEEK", RETURN_TO_MENU, "menu",
                                 "GAME 10 SKIPPED  ·  7-2  ·  PLAYOFFS MARKER REACHED"),
    }
    for variant, state in _variants(finished).items():
        assert result_variant(state) is variant
        banner, label, call, ribbon = expected[variant]
        buttons, texts, _records, calls, _view = _draw(state)
        assert banner in texts and ribbon in texts
        assert buttons[0].label == label and buttons[0].variant == "kit-primary"
        buttons[0].action()
        assert calls == [call]
        labels = [button.label for button in buttons]
        assert ("END RUN" in labels) is (variant is ResultVariant.REGULAR)
    fired_texts = _draw(_variants(finished)[ResultVariant.FIRED])[1]
    assert "LOSS" in fired_texts and "RUN OVER" in fired_texts


def test_end_run_requests_the_existing_confirmation(finished) -> None:
    buttons, _texts, _records, calls, _view = _draw(finished)
    next(button for button in buttons if button.label == "END RUN").action()
    assert calls == ["exit"]


def test_regular_result_shows_scores_header_stats_and_tracker(finished) -> None:
    _buttons, texts, _records, _calls, _view = _draw(finished)
    assert "GAME 01" in texts and " · FINAL" in texts
    assert "31" in texts and "17" in texts
    stats = match_team_stats(finished.match.match_events)
    assert f"{stats.team_a.total_yards} yd" in texts
    assert str(stats.team_a.plays) in texts
    for label in ("TOTAL YARDS", "RUSHING", "PASSING", "PLAYS", "TURNOVERS", "LONGEST PLAY"):
        assert label in texts
    assert "1-0" in texts and "G1" in texts and "G10" in texts
    assert "31-17" in texts  # game 1 tile
    assert "Final whistle" not in texts


def test_overtime_is_named_in_header_banner_and_tile(finished) -> None:
    match = replace(finished.match, period=3, game_clock_seconds=0)
    state = replace(finished, match=match,
                    season_history=(FootballSeasonGame(1, W, 31, 17, overtime=True),))
    texts = _draw(state)[1]
    assert " · FINAL · OT" in texts and "FINAL · OT" in texts and "31-17 OT" in texts


def test_bye_week_marker_never_shows_previous_game_score_or_stats(finished) -> None:
    state = _variants(finished)[ResultVariant.BYE_WEEK]
    assert state.match is not None and state.match.final_result.team_a_score == 31
    _buttons, texts, _records, _calls, _view = _draw(state)
    assert "NO GAME PLAYED" in texts and "BYE WEEK" in texts and " · BYE WEEK" in texts
    assert "31" not in texts and "17" not in texts
    assert "TEAM STATS" not in texts and "WIN" not in texts and "LOSS" not in texts
    assert not any(text.endswith(" yd") for text in texts)
    assert any("without a match result" in text for text in texts)
    assert "BYE" in texts  # game-10 tile


def test_earlier_bye_appears_in_tracker(finished) -> None:
    state = _season(finished, FootballRunPhase.READY_FOR_NEXT_GAME,
                    [_played(1, W), FootballSeasonGame(2, BYE), _played(3, W, (31, 17))], skipped=(2,))
    texts = _draw(state)[1]
    assert "BYE" in texts and "GAME 03" in texts and "2-0" in texts


@pytest.mark.parametrize("color", ["navy", "silver", "yellow", "crimson"])
@pytest.mark.parametrize("team", [None, "Northern Plains Agricultural And Mechanical Institute Owls"])
def test_text_fits_every_variant(finished, color, team) -> None:
    for state in _variants(finished).values():
        if team is not None:
            state = replace(state, match=replace(
                state.match, team_a=replace(state.match.team_a, team_name=team)))
        _buttons, texts, records, _calls, _view = _draw(state, color=color, error="Something went wrong")
        assert records
        for text, rect, container in records:
            assert container.contains(rect), (text, rect, container)
            assert pygame.Rect(0, 0, 1280, 720).contains(rect), text
        if team is not None and state.phase is not FootballRunPhase.PLAYOFFS:
            assert any(text.startswith("NORTHERN PLAINS") and text.endswith("...") for text in texts)


def test_layout_regions_do_not_overlap(finished) -> None:
    from src.ui import football_result as layout

    regions = [layout.HEADER, layout.HERO, layout.RIBBON, layout.STATS, layout.SEASON, layout.FOOTER]
    for index, first in enumerate(regions):
        assert pygame.Rect(0, 0, 1280, 720).contains(first)
        for second in regions[index + 1:]:
            assert not first.colliderect(second), (first, second)
    buttons = _draw(finished)[0]
    assert layout.FOOTER.contains(buttons[0].rect)
    assert not buttons[1].rect.colliderect(layout.HERO)


def test_score_count_up_uses_injected_clock_without_blocking_the_button(finished) -> None:
    now = {"t": 1000}
    view_clock = lambda: now["t"]  # noqa: E731
    buttons, texts, _records, calls, view = _draw(finished, clock=view_clock)
    assert "0" in texts and "31" not in texts
    buttons[0].action()
    assert calls == ["shop"]
    theme = Theme.from_profile(new_team_profile("Test Owls", "navy", "gold"))
    now["t"] = 1000 + 700
    with text_audit() as records:
        view.draw(pygame.Surface((1280, 720)), finished, theme)
    assert "31" in [text for text, _r, _c in records]


def test_result_view_rejects_missing_match(finished) -> None:
    with pytest.raises(RuntimeError, match="completed match"):
        _draw(replace(finished, match=None))
