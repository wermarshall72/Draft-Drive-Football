"""The eight-team playoff bracket: seeding, pairings, AI results, and save data."""

from __future__ import annotations

import json
import random

import pytest

from src.engine.football_playoffs import (
    FIRST_ROUND_PAIRS,
    PLAYOFF_TEAM_NAMES,
    FootballPlayoffBracket,
    FootballPlayoffRound,
    game_label,
    human_seed_for_losses,
    playoff_round_for_game,
)
from src.engine.save_data import UnsupportedSave

QF, SF, CH = FootballPlayoffRound


def _bracket(losses: int = 0, seed: int = 7, name: str = "Owls") -> FootballPlayoffBracket:
    return FootballPlayoffBracket(name, losses, random.Random(seed))


@pytest.mark.parametrize(("losses", "seed"), ((0, 1), (1, 2), (2, 3)))
def test_regular_season_losses_set_the_human_seed(losses: int, seed: int) -> None:
    assert human_seed_for_losses(losses) == seed
    bracket = _bracket(losses).state
    assert bracket.human_seed == seed
    assert [team.is_human for team in bracket.teams].count(True) == 1
    assert bracket.team(seed).name == "Owls"


def test_three_losses_cannot_make_the_playoffs() -> None:
    with pytest.raises(ValueError):
        human_seed_for_losses(3)


def test_first_round_pairs_one_v_eight_in_bracket_order_with_unique_names() -> None:
    bracket = _bracket().state
    assert [(game.high_seed, game.low_seed) for game in bracket.games] == list(FIRST_ROUND_PAIRS)
    names = [team.name for team in bracket.teams]
    assert len(set(names)) == 8
    assert all(name in PLAYOFF_TEAM_NAMES for name in names if name != "Owls")
    assert bracket.next_human_round is QF


def test_ai_names_never_repeat_the_human_team_name() -> None:
    for seed in range(40):
        names = [team.name for team in _bracket(seed=seed, name="Ridgeline").state.teams]
        assert names.count("Ridgeline") == 1


def test_each_recorded_round_decides_the_others_and_pairs_winners_in_order() -> None:
    bracket = _bracket()
    bracket.record_human_result(QF, 21, 14)
    state = bracket.state
    quarterfinals = state.round_games(QF)
    assert all(game.decided for game in quarterfinals)
    assert all(game.score_for(game.winner_seed) > game.score_for(game.opponent_of(game.winner_seed))
               for game in quarterfinals)
    semifinals = state.round_games(SF)
    assert len(semifinals) == 2 and not any(game.decided for game in semifinals)
    assert {semifinals[0].high_seed, semifinals[0].low_seed} == {
        quarterfinals[0].winner_seed, quarterfinals[1].winner_seed,
    }
    assert semifinals[0].high_seed < semifinals[0].low_seed
    assert state.next_human_round is SF
    assert bracket.human_opponent(SF).seed == semifinals[0].opponent_of(1)

    bracket.record_human_result(SF, 10, 3, overtime=True)
    assert bracket.state.human_game(SF).overtime
    bracket.record_human_result(CH, 30, 27)
    final = bracket.state
    assert final.champion_seed == 1 and not final.human_eliminated
    assert final.next_human_round is None
    assert len(final.games) == 7


def test_a_human_loss_eliminates_but_the_bracket_still_fills_that_round() -> None:
    bracket = _bracket(losses=1)
    bracket.record_human_result(QF, 3, 17)
    state = bracket.state
    assert state.human_eliminated and state.next_human_round is None
    assert len(state.round_games(SF)) == 2
    with pytest.raises(ValueError):
        bracket.human_opponent(SF)


def test_playoff_games_need_a_winner_and_cannot_be_recorded_twice() -> None:
    bracket = _bracket()
    with pytest.raises(ValueError, match="winner"):
        bracket.record_human_result(QF, 7, 7)
    bracket.record_human_result(QF, 14, 7)
    with pytest.raises(ValueError):
        bracket.record_human_result(QF, 14, 7)


def test_better_seeds_win_ai_games_more_often_but_not_always() -> None:
    upsets = favorites = 0
    for seed in range(400):
        bracket = _bracket(seed=seed)
        bracket.record_human_result(QF, 7, 0)
        # Game 1 (4 v 5) is nearly even; game 3 (2 v 7) favors #2 at 75%.
        two_v_seven = bracket.state.round_games(QF)[3]
        if two_v_seven.winner_seed == 2:
            favorites += 1
        else:
            upsets += 1
    assert 0.68 < favorites / 400 < 0.82 and upsets > 0


def test_simulated_games_have_real_football_scores() -> None:
    """No AI-vs-AI team scores exactly 1, and every winner outscores its loser."""
    simulated = 0
    for seed in range(2000):
        bracket = _bracket(seed=seed)
        for playoff_round in FootballPlayoffRound:
            bracket.record_human_result(playoff_round, 21, 14)
        for game in bracket.state.games:
            if game.has(bracket.state.human_seed):
                continue
            simulated += 1
            winner = game.score_for(game.winner_seed)
            loser = game.score_for(game.opponent_of(game.winner_seed))
            assert 1 not in (winner, loser), game
            assert winner > loser and not game.overtime, game
    assert simulated == 2000 * 4


def test_bracket_round_trips_through_json_and_continues_identically() -> None:
    bracket = _bracket(losses=2, seed=11)
    bracket.record_human_result(QF, 24, 20)
    data = json.loads(json.dumps(bracket.to_save_data()))
    restored = FootballPlayoffBracket.from_save_data(data)
    assert restored.state == bracket.state
    for each in (bracket, restored):
        each.record_human_result(SF, 13, 10)
    assert restored.state == bracket.state
    assert restored.to_save_data() == bracket.to_save_data()


def test_damaged_bracket_saves_are_unsupported() -> None:
    data = _bracket().to_save_data()
    with pytest.raises(UnsupportedSave):
        FootballPlayoffBracket.from_save_data({**data, "teams": data["teams"][:7]})
    broken = json.loads(json.dumps(data))
    broken["games"][0]["winner_seed"] = 5
    with pytest.raises(UnsupportedSave):
        FootballPlayoffBracket.from_save_data(broken)


@pytest.mark.parametrize(
    ("game", "playoff_round", "label", "short"),
    (
        (7, None, "GAME 07", "GAME 7"),
        (10, None, "GAME 10", "GAME 10"),
        (11, QF, "QUARTERFINAL", "QUARTERFINAL"),
        (12, SF, "SEMIFINAL", "SEMIFINAL"),
        (13, CH, "CHAMPIONSHIP", "CHAMPIONSHIP"),
    ),
)
def test_game_numbers_name_their_playoff_round(game, playoff_round, label, short) -> None:
    assert playoff_round_for_game(game) is playoff_round
    assert game_label(game) == label
    assert game_label(game, padded=False) == short
