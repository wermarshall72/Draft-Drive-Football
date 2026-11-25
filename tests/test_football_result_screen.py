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
from src.engine.football_playoffs import FootballPlayoffBracket, FootballPlayoffRound
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.profile import new_team_profile
from src.ui.football_result import (
    OPEN_NEXT_SHOP,
    RETURN_TO_MENU,
    VIEW_BRACKET,
    VIEW_PLAYOFF_BRACKET,
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
        open_bracket=lambda: calls.append("bracket"),
        clock=clock,
    )
    theme = Theme.from_profile(new_team_profile("Test Owls", color, "gold" if color != "gold" else "navy"))
    surface = pygame.Surface((1280, 720))
    with text_audit() as records:
        buttons = view.draw(surface, state, theme, error=error)
    return buttons, [text for text, _rect, _container in records], records, calls, view


QF, SF, CH = FootballPlayoffRound


def _bracket(*results):
    """A 2-loss (#3 seed) bracket after the human's (round, score, against) results."""
    bracket = FootballPlayoffBracket("Test Owls", 2, __import__("random").Random(5))
    for playoff_round, score, against in results:
        bracket.record_human_result(playoff_round, score, against)
    return bracket.state


def _rival(bracket, playoff_round) -> str:
    game = bracket.human_game(playoff_round)
    return bracket.team(game.opponent_of(bracket.human_seed)).name.upper()


def _playoff(finished, phase, game_number, playoff_round, bracket, score=(31, 17)):
    winner = FootballTeamSide.TEAM_A if score[0] > score[1] else FootballTeamSide.TEAM_B
    match = replace(finished.match, team_a_score=score[0], team_b_score=score[1],
                    final_result=FootballMatchResult(*score, winner, True))
    nine = [_played(n, W if n not in (3, 6) else L) for n in range(1, 10)]
    season = _season(finished, phase, [*nine, _played(10, W, (31, 17))])
    return replace(season, match=match, game_number=game_number, playoffs=bracket,
                   playoff_round=playoff_round)


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
        ResultVariant.SEASON_COMPLETE: replace(_season(
            finished, FootballRunPhase.READY_FOR_NEXT_GAME, [*nine, _played(10, W, (31, 17))],
        ), playoffs=_bracket()),
        ResultVariant.BYE_WEEK: replace(_season(
            finished, FootballRunPhase.READY_FOR_NEXT_GAME, [*nine, FootballSeasonGame(10, BYE)],
            skipped=(10,), message="Bye Week skipped week 10 without a match result.",
        ), playoffs=_bracket()),
        ResultVariant.PLAYOFF_WIN: _playoff(
            finished, FootballRunPhase.READY_FOR_NEXT_GAME, 11, QF, _bracket((QF, 31, 17)),
        ),
        ResultVariant.ELIMINATED: _playoff(
            finished, FootballRunPhase.ELIMINATED, 12, SF,
            _bracket((QF, 31, 17), (SF, 10, 24)), score=(10, 24),
        ),
        ResultVariant.CHAMPION: _playoff(
            finished, FootballRunPhase.CHAMPION, 13, CH,
            _bracket((QF, 31, 17), (SF, 24, 21), (CH, 31, 17)),
        ),
    }


def test_each_variant_has_its_banner_and_primary_action(finished) -> None:
    states = _variants(finished)
    fresh = states[ResultVariant.SEASON_COMPLETE].playoffs
    after_qf = states[ResultVariant.PLAYOFF_WIN].playoffs
    expected = {
        ResultVariant.REGULAR: ("WIN", OPEN_NEXT_SHOP, "shop", "NEXT UP · SHOP BEFORE WEEK 2"),
        ResultVariant.FIRED: ("FIRED", RETURN_TO_MENU, "menu", "RUN OVER · 3 LOSSES  ·  FINAL RECORD 1-3"),
        ResultVariant.SEASON_COMPLETE: (
            "PLAYOFFS", VIEW_PLAYOFF_BRACKET, "bracket",
            f"REGULAR SEASON COMPLETE  ·  8-2  ·  #3 SEED  ·  NEXT UP · QUARTERFINAL VS {_rival(fresh, QF)}",
        ),
        ResultVariant.BYE_WEEK: (
            "BYE WEEK", VIEW_PLAYOFF_BRACKET, "bracket",
            f"WEEK 10 SKIPPED  ·  7-2  ·  #3 SEED  ·  NEXT UP · QUARTERFINAL VS {_rival(fresh, QF)}",
        ),
        ResultVariant.PLAYOFF_WIN: (
            "ADVANCES", VIEW_PLAYOFF_BRACKET, "bracket",
            f"QUARTERFINAL WON  ·  NEXT UP · SEMIFINAL VS {_rival(after_qf, SF)}",
        ),
        ResultVariant.ELIMINATED: (
            "ELIMINATED", RETURN_TO_MENU, "menu",
            "SEMIFINAL LOSS  ·  RUN OVER  ·  #3 SEED  ·  REGULAR SEASON 8-2",
        ),
        ResultVariant.CHAMPION: (
            "CHAMPIONS", RETURN_TO_MENU, "menu",
            "CHAMPIONSHIP WON  ·  #3 SEED  ·  REGULAR SEASON 8-2",
        ),
    }
    for variant, state in states.items():
        assert result_variant(state) is variant
        banner, label, call, ribbon = expected[variant]
        buttons, texts, _records, calls, _view = _draw(state)
        assert banner in texts and ribbon in texts, (variant, texts)
        assert buttons[0].label == label and buttons[0].variant == "kit-primary"
        buttons[0].action()
        assert calls == [call]
        labels = [button.label for button in buttons]
        assert ("PAUSE" in labels) is (
            variant in (ResultVariant.REGULAR, ResultVariant.SEASON_COMPLETE,
                        ResultVariant.BYE_WEEK, ResultVariant.PLAYOFF_WIN)
        )
        assert (VIEW_BRACKET in labels) is (
            variant in (ResultVariant.ELIMINATED, ResultVariant.CHAMPION)
        )
    fired_texts = _draw(states[ResultVariant.FIRED])[1]
    assert "LOSS" in fired_texts and "RUN OVER" in fired_texts


def test_playoff_results_name_the_round_and_show_the_playoff_path(finished) -> None:
    state = _variants(finished)[ResultVariant.ELIMINATED]
    texts = _draw(state)[1]
    assert "SEMIFINAL" in texts and "PLAYOFFS" in texts and "LOSS" in texts
    assert {"QF", "SF", "FINAL", "W", "L", "31-17", "10-24"} <= set(texts)
    # The regular-season tracker and record stay; the loss meter gives way to the path.
    assert "WK10" in texts and "8-2" in texts and "LOSSES" not in texts
    champion = _draw(_variants(finished)[ResultVariant.CHAMPION])[1]
    assert "CHAMPIONSHIP" in champion and "24-21" in champion
    complete = _draw(_variants(finished)[ResultVariant.SEASON_COMPLETE])[1]
    assert "NEXT" in complete and "REGULAR SEASON COMPLETE" in complete


def test_pause_button_opens_the_pause_menu(finished) -> None:
    buttons, _texts, _records, calls, _view = _draw(finished)
    next(button for button in buttons if button.label == "PAUSE").action()
    assert calls == ["exit"]


def test_regular_result_shows_scores_header_stats_and_tracker(finished) -> None:
    _buttons, texts, _records, _calls, _view = _draw(finished)
    assert "WEEK 01" in texts and " · FINAL" in texts
    assert "31" in texts and "17" in texts
    stats = match_team_stats(finished.match.match_events)
    assert f"{stats.team_a.total_yards} yd" in texts
    assert str(stats.team_a.plays) in texts
    for label in ("TOTAL YARDS", "RUSHING", "PASSING", "PLAYS", "TURNOVERS", "LONGEST PLAY"):
        assert label in texts
    assert "1-0" in texts and "WK1" in texts and "WK10" in texts
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
    assert "BYE" in texts and "WEEK 03" in texts and "2-0" in texts


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
        if team is not None and state.game_number not in state.skipped_games:
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


def _widest_abbreviations(count: int):
    from src.engine.football_ai_teams import AI_TEAM_CATALOG
    from src.ui.football_ui_kit import match_font

    font = match_font(11)
    return tuple(sorted(AI_TEAM_CATALOG, key=lambda team: -font.size(team.abbreviation)[0])[:count])


def test_season_tracker_tags_each_game_with_its_rival(finished) -> None:
    rivals = _widest_abbreviations(10)
    state = replace(
        _season(finished, FootballRunPhase.READY_FOR_NEXT_GAME, [_played(1, W), _played(2, L)]),
        regular_season_teams=rivals,
    )
    _buttons, _texts, records, _calls, _view = _draw(state)
    for number, rival in enumerate(rivals, start=1):
        label = next(rect for text, rect, _c in records if text == f"WK{number}")
        tag, container = next((rect, c) for text, rect, c in records if text == rival.abbreviation)
        assert container.contains(tag) and not tag.colliderect(label), rival


def test_playoff_path_tags_each_paired_rival(finished) -> None:
    bracket = _bracket((QF, 24, 20))
    state = replace(finished, phase=FootballRunPhase.READY_FOR_NEXT_GAME, game_number=11,
                    playoffs=bracket, playoff_round=QF)
    _buttons, texts, records, _calls, _view = _draw(state)
    for playoff_round, label in ((QF, "QF"), (SF, "SF")):
        game = bracket.human_game(playoff_round)
        rival = bracket.team(game.opponent_of(bracket.human_seed)).ai_team
        tag = next(rect for text, rect, _c in records if text == rival.abbreviation)
        assert not tag.colliderect(next(rect for text, rect, _c in records if text == label))


def test_hero_and_stats_use_the_rivals_colors(finished) -> None:
    from src.ui.football_ai_team_colors import opponent_colors

    rival = finished.opponent_team
    assert rival is not None and rival.name == finished.match.team_b.team_name
    surface = pygame.Surface((1280, 720))
    FootballResultView(lambda: None, lambda: None, lambda: None).draw(
        surface, finished, Theme.from_profile(new_team_profile("Test Owls", "navy", "gold")))
    from src.ui.football_result import STATS

    marker = surface.get_at((STATS.right - 18, STATS.top + 20))
    assert marker[:3] == tuple(opponent_colors(rival).accent)[:3]


def test_week_tiles_fit_wk10_the_widest_abbreviation_and_the_chip(finished) -> None:
    from src.engine.football_ai_teams import AI_TEAM_CATALOG
    from src.ui.football_result import SEASON, TILE_FONT_SIZE
    from src.ui.football_ui_kit import match_font

    font = match_font(TILE_FONT_SIZE)
    widest = max(AI_TEAM_CATALOG, key=lambda team: font.size(team.abbreviation)[0])
    assert widest.abbreviation == "WRNG"
    history = [_played(number, W if number % 3 else L) for number in range(1, 10)]
    state = replace(_season(finished, FootballRunPhase.READY_FOR_NEXT_GAME, history),
                    regular_season_teams=(widest,) * 10)
    _buttons, _texts, records, _calls, _view = _draw(state)
    tags = [(rect, c) for text, rect, c in records if text == widest.abbreviation]
    assert len(tags) == 10
    for number in range(1, 11):
        label, tile = next((rect, c) for text, rect, c in records if text == f"WK{number}")
        tag = next(rect for rect, c in tags if c == tile)
        chip_left = tile.right - 6 - 12  # _draw_rival_tag's 12px chip, 6px from the edge
        assert SEASON.contains(tile) and tile.contains(label) and tile.contains(tag)
        assert label.right + 2 <= tag.left and tag.right <= chip_left, number


def test_earlier_bye_week_numbers_weeks_not_games_played(finished) -> None:
    history = [_played(1, W), _played(2, W), FootballSeasonGame(3, BYE), _played(4, L), _played(5, W)]
    state = _season(finished, FootballRunPhase.READY_FOR_NEXT_GAME, history, skipped=(3,))
    assert state.games_played == 4
    _buttons, texts, records, _calls, _view = _draw(state)
    # N GAMES PLAYED appears only on the Bye Week result; here the header names the week.
    assert "WEEK 05" in texts and "WEEK 04" not in texts
    assert "NEXT UP · SHOP BEFORE WEEK 6" in texts and "BYE" in texts
    assert not any("GAME 0" in text or "GAME 6" in text for text in texts)


def test_week_ten_bye_week_uses_week_wording(finished) -> None:
    state = _variants(finished)[ResultVariant.BYE_WEEK]
    _buttons, texts, _records, _calls, _view = _draw(replace(state, transition_message=None))
    assert texts.count("WEEK 10") == 3  # header, hero slot, and Bye panel
    assert any(text.startswith("WEEK 10 SKIPPED") for text in texts)
    assert any("skipped week 10" in text for text in texts)
    assert "NO GAME PLAYED" in texts and f"{state.games_played} GAMES PLAYED" in texts
