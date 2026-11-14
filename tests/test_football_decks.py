from dataclasses import replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCoach,
    FootballDeckState,
    FootballFourthDownAction,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_decks import (
    OFFENSIVE_PLAY_CATALOG,
    STARTING_DEFENSIVE_ACTIONS,
    STARTING_OFFENSIVE_ACTIONS,
)
from src.engine.football_simulator import FootballMatchSimulator


def _roster(name: str) -> FootballRoster:
    return FootballRoster(
        name,
        {
            position: FootballPlayer(
                f"{name} {position.value}", position, 10.0, 0.2, 0.75
            )
            for position in FootballPosition
        },
        FootballCoach(f"{name} Coach"),
        FootballSpecialTeams(f"{name} Special Teams"),
    )


def _state(**overrides: object) -> FootballMatchState:
    fields: dict[str, object] = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
        "random_seed": 1337,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 25.0,
        "game_clock_seconds": 900,
        "period": 1,
        "awaited_action": FootballAwaitedAction.DEFENSIVE_SCHEME,
    }
    fields.update(overrides)
    if fields["period"] >= 3 and "game_clock_seconds" not in overrides:
        fields["game_clock_seconds"] = 300
    if fields["awaited_action"] in (
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    ):
        fields.setdefault(
            "current_drive_defensive_scheme", DefensiveSchemeAction.DEEP_PASS
        )
    return FootballMatchState(**fields)  # type: ignore[arg-type]


def _copies(side: str, actions, *, group: str) -> tuple[FootballCardCopy, ...]:
    return tuple(
        FootballCardCopy(f"{side}:{group}:{action.value}:{index}", action.value)
        for index, action in enumerate(actions, 1)
    )


class _DeterministicMatchRng(random.Random):
    def random(self) -> float:
        return 0.99

    def uniform(self, low: float, high: float) -> float:
        return (low + high) / 2

    def choice(self, values):
        return values[0]


def test_match_starts_with_six_owned_basics_and_independent_three_two_hands() -> None:
    simulator = FootballMatchSimulator(_state())
    match = simulator.state

    for side in ("team_a", "team_b"):
        offense = getattr(match, f"{side}_offense_deck")
        defense = getattr(match, f"{side}_defense_deck")
        assert offense is not None and defense is not None
        assert {card.card_id for card in offense.owned} == {
            action.value for action in STARTING_OFFENSIVE_ACTIONS
        }
        assert {card.card_id for card in defense.owned} == {
            action.value for action in STARTING_DEFENSIVE_ACTIONS
        }
        assert len(offense.hand) == 3
        assert len(defense.hand) == 2
        assert len(offense.draw_pile) == 3
        assert len(defense.draw_pile) == 4
        assert not ({card.copy_id for card in offense.owned} & {
            card.copy_id for card in defense.owned
        })


def test_selection_rejects_cards_outside_the_hand_without_mutating_match() -> None:
    simulator = FootballMatchSimulator(_state())
    initial = simulator.state
    defender = initial.team_b_defense_deck
    offense = initial.team_a_offense_deck
    assert defender is not None and offense is not None
    hidden_scheme = next(
        card for card in defender.owned if card not in defender.hand
    )
    hidden_play = next(card for card in offense.owned if card not in offense.hand)
    match_rng = simulator.rng.getstate()

    with pytest.raises(ValueError, match="not in the current hand"):
        simulator.select_defensive_scheme(hidden_scheme.copy_id)
    assert simulator.state is initial
    assert simulator.rng.getstate() == match_rng

    playable_scheme = defender.hand[0]
    simulator.select_defensive_scheme(playable_scheme.copy_id)
    assert simulator.rng.getstate() == match_rng
    before_play = simulator.state
    with pytest.raises(ValueError, match="not in the current hand"):
        simulator.resolve_offensive_play(hidden_play.copy_id)
    assert simulator.state is before_play
    assert simulator.state.current_drive_defensive_scheme is not None


def test_playing_a_card_discards_one_copy_draws_one_and_keeps_drive_scheme() -> None:
    simulator = FootballMatchSimulator(_state())
    defense = simulator.state.team_b_defense_deck
    assert defense is not None
    scheme_card = defense.hand[0]
    simulator.select_defensive_scheme(scheme_card.copy_id)

    offense = simulator.state.team_a_offense_deck
    assert offense is not None
    selected = offense.hand[0]
    action = OFFENSIVE_PLAY_CATALOG[selected.card_id].action
    before_hand = len(offense.hand)
    after_play = simulator.resolve_offensive_play(selected.copy_id)
    next_offense = after_play.team_a_offense_deck
    assert next_offense is not None
    assert selected in next_offense.discard_pile
    assert len(next_offense.hand) == before_hand
    assert after_play.current_drive_defensive_scheme is not None
    assert after_play.match_events[-1].action is action

    next_defense = after_play.team_b_defense_deck
    assert next_defense is not None
    assert scheme_card in next_defense.discard_pile
    assert len(next_defense.hand) == 2


def test_duplicate_copy_reshuffles_independently_and_fallback_still_draws() -> None:
    first = FootballCardCopy("dup:first", OffensivePlayAction.RB_RUN.value)
    second = FootballCardCopy("dup:second", OffensivePlayAction.RB_RUN.value)
    duplicate_deck = FootballDeckState((first, second), hand=(first,), discard_pile=(second,))
    simulator = FootballMatchSimulator(
        _state(
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            team_a_offense_deck=duplicate_deck,
        )
    )

    result = simulator.resolve_offensive_play(first.copy_id)
    deck = result.team_a_offense_deck
    assert deck is not None
    assert len(deck.hand) == 1
    assert len(deck.draw_pile) == 1
    assert len(deck.discard_pile) == 0
    assert len({card.copy_id for card in deck.owned}) == 2
    assert {card.copy_id for card in deck.hand} | {
        card.copy_id for card in deck.discard_pile
    } | {card.copy_id for card in deck.draw_pile} == {
        first.copy_id,
        second.copy_id,
    }

    empty = FootballDeckState(())
    fallback = FootballMatchSimulator(
        _state(
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            team_a_offense_deck=empty,
        )
    )
    fallback_state = fallback.resolve_offensive_play(None)
    assert fallback_state.match_events[-1].action is OffensivePlayAction.RB_RUN
    assert fallback_state.team_a_offense_deck == empty


def test_period_resets_follow_play_draw_and_preserve_halftime_scheme() -> None:
    offense = _copies("home", STARTING_OFFENSIVE_ACTIONS, group="offense")
    defense = _copies("away", STARTING_DEFENSIVE_ACTIONS, group="defense")
    offensive_deck = FootballDeckState(offense, hand=(offense[0],), draw_pile=offense[1:])
    defensive_deck = FootballDeckState(defense, hand=(defense[0],), draw_pile=defense[1:])
    simulator = FootballMatchSimulator(
        _state(
            game_clock_seconds=4,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            current_drive_defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
            team_a_offense_deck=offensive_deck,
            team_b_defense_deck=defensive_deck,
        )
    )
    simulator.rng = _DeterministicMatchRng(1)
    simulator.resolve_offensive_play(offense[0].copy_id)

    halftime = simulator.state
    assert halftime.period == 2
    assert halftime.current_drive_defensive_scheme is DefensiveSchemeAction.DEEP_PASS
    reset_offense = halftime.team_a_offense_deck
    reset_defense = halftime.team_b_defense_deck
    assert reset_offense is not None and reset_defense is not None
    assert len(reset_offense.hand) == 3 and not reset_offense.discard_pile
    assert len(reset_defense.hand) == 2 and not reset_defense.discard_pile


def test_overtime_resets_once_and_later_overtime_periods_do_not_reset_again() -> None:
    simulator = FootballMatchSimulator(
        _state(
            period=2,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    simulator.rng = _DeterministicMatchRng(1)
    simulator.resolve_fourth_down(FootballFourthDownAction.PUNT)
    first_overtime = simulator.state
    assert first_overtime.period == 3
    for side in ("team_a", "team_b"):
        offense = getattr(first_overtime, f"{side}_offense_deck")
        defense = getattr(first_overtime, f"{side}_defense_deck")
        assert offense is not None and defense is not None
        assert len(offense.hand) == 3
        assert len(defense.hand) == 2

    simulator.state = replace(
        simulator.state,
        game_clock_seconds=4,
        down=4,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )
    before_next_overtime = simulator.state
    simulator.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert simulator.state.period == 4
    assert simulator.state.team_a_offense_deck == before_next_overtime.team_a_offense_deck
    assert simulator.state.team_a_defense_deck == before_next_overtime.team_a_defense_deck
