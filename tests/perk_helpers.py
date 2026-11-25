"""Builders for player-perk scenarios: rosters with chosen specialists, scripted RNGs."""

from __future__ import annotations

import random
from dataclasses import replace

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballCoach,
    FootballDeckState,
    FootballMatchState,
    FootballPerkActivation,
    FootballPlayerPerkKind,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_player_catalog import (
    PLAYER_TYPES_BY_PERK,
    player_from_type,
    player_types_for_position,
)
from src.engine.football_simulator import FootballMatchSimulator, calculate_match_play_estimate

A, B = FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B
K = FootballPlayerPerkKind
BASIC_PLAYS = ("rb_run", "screen_pass", "pa_pass", "short_pass", "medium_pass", "deep_pass")
BASIC_SCHEMES = BASIC_PLAYS


def type_id(kind: FootballPlayerPerkKind) -> str:
    return PLAYER_TYPES_BY_PERK[kind].type_id


def roster(name: str, *kinds: FootballPlayerPerkKind) -> FootballRoster:
    """All basic players except one specialist per listed perk."""
    players = {}
    for position in FootballPosition:
        basic = next(item for item in player_types_for_position(position) if item.perk is None)
        players[position] = player_from_type(basic, name=f"{name} {position.value}")
    for kind in kinds:
        player_type = PLAYER_TYPES_BY_PERK[kind]
        players[player_type.position] = player_from_type(player_type, name=f"{name} {player_type.name}")
    return FootballRoster(name, players, FootballCoach(f"{name} Coach"), FootballSpecialTeams())


def deck(prefix: str, card_ids, hand: int) -> FootballDeckState:
    copies = tuple(FootballCardCopy(f"{prefix}:{index}:{card_id}", card_id)
                   for index, card_id in enumerate(card_ids))
    return FootballDeckState(copies, draw_pile=copies[hand:], hand=copies[:hand])


def full_decks(side_prefix: str) -> dict[str, FootballDeckState]:
    """Every basic play and scheme in hand, plus a second copy of each to draw."""
    return {
        "offense": deck(f"{side_prefix}:o", BASIC_PLAYS * 2, 6),
        "defense": deck(f"{side_prefix}:d", BASIC_SCHEMES * 2, 6),
    }


class ScriptedRNG(random.Random):
    """Queued results for the match RNG; defaults keep plays clean and kicks simple.

    ``random()`` defaults to 0.99 (a catch, no fumble, no block, no touchback),
    ``uniform()`` to the midpoint (expected yards), ``gauss()`` to its mean, and
    ``choice()`` to the first item.
    """

    def __init__(self, randoms=(), uniforms=(), gausses=(), choices=()):
        super().__init__(0)
        self.randoms = list(randoms)
        self.uniforms = list(uniforms)
        self.gausses = list(gausses)
        self.choices = list(choices)
        self.random_calls = 0

    def random(self) -> float:
        self.random_calls += 1
        return self.randoms.pop(0) if self.randoms else 0.99

    def uniform(self, low: float, high: float) -> float:
        return self.uniforms.pop(0) if self.uniforms else (low + high) / 2

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self.gausses.pop(0) if self.gausses else mu

    def choice(self, seq):
        index = self.choices.pop(0) if self.choices else 0
        return seq[index]


def match(
    a=(), b=(), *, a_decks=None, b_decks=None, **overrides,
) -> FootballMatchState:
    a_decks = a_decks or full_decks("a")
    b_decks = b_decks or full_decks("b")
    values = dict(
        team_a=roster("Home", *a),
        team_b=roster("Away", *b),
        random_seed=11,
        team_a_score=0,
        team_b_score=0,
        possession=A,
        down=1,
        yards_to_go=10.0,
        offense_field_position=40.0,
        game_clock_seconds=800,
        period=1,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        team_a_offense_deck=a_decks["offense"],
        team_a_defense_deck=a_decks["defense"],
        team_b_offense_deck=b_decks["offense"],
        team_b_defense_deck=b_decks["defense"],
    )
    values.update(overrides)
    return FootballMatchState(**values)


def simulator(a=(), b=(), *, scheme: DefensiveSchemeAction | str | None = "rb_run",
              offense: FootballTeamSide = A, **overrides) -> FootballMatchSimulator:
    """A simulator whose drive has started with ``scheme`` (unless None)."""
    sim = FootballMatchSimulator(match(a, b, possession=offense, **overrides))
    sim.rng = ScriptedRNG()
    if scheme is not None:
        sim.select_defensive_scheme(DefensiveSchemeAction(scheme) if isinstance(scheme, str) else scheme)
    return sim


def ensure_in_hand(sim: FootballMatchSimulator, side: FootballTeamSide, card_id: str,
                   *, offensive: bool = True) -> None:
    """Move a copy of ``card_id`` into the hand from the draw or discard pile if needed."""
    field = f"{side.value}_{'offense' if offensive else 'defense'}_deck"
    current = getattr(sim.state, field)
    if any(card.card_id == card_id for card in current.hand):
        return
    for zone in ("draw_pile", "discard_pile"):
        card = next((card for card in getattr(current, zone) if card.card_id == card_id), None)
        if card is not None:
            sim.state = replace(sim.state, **{field: replace(
                current,
                hand=current.hand + (card,),
                **{zone: tuple(other for other in getattr(current, zone) if other != card)},
            )})
            return
    raise AssertionError(f"No {card_id} copy to put in hand.")


def snap(sim: FootballMatchSimulator, play: str, *, yards: float | None = None,
         randoms=(), choices=()) -> FootballMatchState:
    """Resolve one play with exact pre-cap yards (when given) and queued rolls."""
    action = OffensivePlayAction(play)
    ensure_in_hand(sim, sim.state.possession, play)
    estimate = calculate_match_play_estimate(sim.state, action)
    uniforms = [] if yards is None else [yards - estimate.yards_on_success]
    sim.rng = ScriptedRNG(randoms=randoms, uniforms=uniforms, choices=choices)
    return sim.resolve_offensive_play(action)


def fired(state_or_event, kind: FootballPlayerPerkKind, team: FootballTeamSide | None = None,
          *, applied: bool | None = None) -> list[FootballPerkActivation]:
    event = state_or_event.match_events[-1] if isinstance(state_or_event, FootballMatchState) else state_or_event
    return [
        activation for activation in event.perk_activations
        if activation.kind is kind
        and (team is None or activation.team is team)
        and (applied is None or activation.applied is applied)
    ]


def last_play(state: FootballMatchState):
    return next(event for event in reversed(state.match_events) if event.play_result is not None)


def with_hand(sim: FootballMatchSimulator, side: FootballTeamSide, card_ids, *, offensive=True):
    """Replace one hand (keeping zones consistent) with fresh copies of ``card_ids``."""
    field = f"{side.value}_{'offense' if offensive else 'defense'}_deck"
    current = getattr(sim.state, field)
    extra = tuple(FootballCardCopy(f"extra:{field}:{index}:{card_id}", card_id)
                  for index, card_id in enumerate(card_ids))
    new = FootballDeckState(
        current.owned + extra,
        draw_pile=current.draw_pile + current.hand,
        hand=extra,
        discard_pile=current.discard_pile,
    )
    sim.state = replace(sim.state, **{field: new})
    return new
