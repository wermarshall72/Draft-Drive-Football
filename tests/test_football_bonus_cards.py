from dataclasses import replace
import random
from types import SimpleNamespace

import pygame
import pytest

from src.engine.football import (
    FootballAwaitedAction,
    FootballBonusCardAction,
    FootballCardCopy,
    FootballCoach,
    FootballConversionAction,
    FootballDeckState,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    starting_defensive_deck,
)
from src.engine.football_shop import (
    FootballShop,
    FootballShopRarity,
    FootballShopSection,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui.football_match_decision_view import FootballMatchDecisionView
from src.ui.football_match_interaction import MatchInteraction


def _roster(name: str) -> FootballRoster:
    return FootballRoster(
        name,
        {
            position: FootballPlayer(
                f"{name} {position.value}", position, 10.0, 0.0, 1.0
            )
            for position in FootballPosition
        },
        coach=FootballCoach(f"{name} Coach"),
        special_teams=FootballSpecialTeams(f"{name} Special Teams"),
    )


def _deck(
    owned: tuple[FootballCardCopy, ...],
    hand: tuple[FootballCardCopy, ...],
    draw: tuple[FootballCardCopy, ...] = (),
    discard: tuple[FootballCardCopy, ...] = (),
) -> FootballDeckState:
    return FootballDeckState(owned, draw, hand, discard)


def _match_state(
    offense: FootballDeckState,
    *,
    defense: FootballDeckState | None = None,
    opponent_defense: FootballDeckState | None = None,
    field_position: float = 30.0,
    down: int = 2,
    yards_to_go: float = 7.0,
) -> FootballMatchState:
    return FootballMatchState(
        team_a=_roster("Home"),
        team_b=_roster("Away"),
        random_seed=81,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_A,
        down=down,
        yards_to_go=yards_to_go,
        offense_field_position=field_position,
        game_clock_seconds=900,
        period=1,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=(
            next(iter(DEFENSIVE_SCHEME_CATALOG.values())).action
        ),
        team_a_offense_deck=offense,
        team_a_defense_deck=defense,
        team_b_defense_deck=opponent_defense,
    )


def _owned_bonus_and_plays(
    action: FootballBonusCardAction,
) -> tuple[FootballCardCopy, FootballCardCopy, FootballCardCopy]:
    bonus = FootballCardCopy(f"human:{action.value}", action.value)
    play = FootballCardCopy("human:play:rb", OffensivePlayAction.RB_RUN.value)
    reserve = FootballCardCopy("human:play:screen", OffensivePlayAction.SCREEN_PASS.value)
    return bonus, play, reserve


class _NoTurnoverRng(random.Random):
    def random(self) -> float:
        super().random()
        return 0.99

    def uniform(self, low: float, high: float) -> float:
        return (low + high) / 2


class _TurnoverRng(random.Random):
    def random(self) -> float:
        super().random()
        return 0.0

    def uniform(self, low: float, high: float) -> float:
        return (low + high) / 2


def test_bonus_catalog_rarities_costs_and_shop_only_removal() -> None:
    shop = FootballShop(_roster("Shop"), seed=104)
    catalog = shop._catalogs[FootballShopSection.PLAYS_SCHEMES]
    cards = {card.card_id: card for card in catalog}

    assert len(BONUS_CARD_CATALOG) == 6
    expected_rarities = {
        FootballBonusCardAction.OFFENSIVE_DRAW: FootballShopRarity.UNCOMMON,
        FootballBonusCardAction.DEFENSIVE_DRAW: FootballShopRarity.UNCOMMON,
        FootballBonusCardAction.OPPONENT_DISCARD: FootballShopRarity.RARE,
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD: FootballShopRarity.VERY_RARE,
        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD: FootballShopRarity.VERY_RARE,
        FootballBonusCardAction.CHALLENGE: FootballShopRarity.VERY_RARE,
    }
    for action, rarity in expected_rarities.items():
        card = cards[f"bonus:{action.value}"]
        assert card.bonus_card is BONUS_CARD_CATALOG[action.value]
        assert card.rarity is rarity
        assert card.cost == 2
        assert card.football_card is None
        assert not card.is_removal

    removal = cards["remove-one-card"]
    assert removal.rarity is FootballShopRarity.RARE
    assert removal.cost == 2
    assert removal.is_removal
    assert removal.football_card is None and removal.bonus_card is None
    assert all(
        card.card_id != "remove-one-card"
        for card in shop.offensive_deck + shop.defensive_deck
    )


def test_all_bonus_types_render_as_tactical_cards_in_the_shared_match_hand() -> None:
    pygame.font.init()
    font = pygame.font.Font(None, 14)
    surface = pygame.Surface((900, 420))
    defensive_cards = starting_defensive_deck("human")
    exhausted_drawable_defense = FootballDeckState(
        defensive_cards,
        hand=defensive_cards,
    )
    for action, definition in BONUS_CARD_CATALOG.items():
        card = FootballCardCopy(f"ui:{action}", action)
        offense = FootballDeckState((card,), hand=(card,))
        match = _match_state(offense, defense=exhausted_drawable_defense)
        view = FootballMatchDecisionView(
            font,
            font,
            MatchInteraction(),
            0,
            None,
            None,
            lambda _copy_id: None,
            lambda _action: None,
            lambda _action, _copy_id: None,
            lambda _offensive: None,
            lambda _accept: None,
        )
        buttons = view.draw(
            surface,
            pygame.Rect(10, 10, 880, 390),
            SimpleNamespace(
                human_decision=FootballHumanDecision.OFFENSIVE_PLAY,
                match=match,
                challenge_available=True,
            ),
        )
        assert len(buttons) == 1
        assert buttons[0].label == definition.name.upper()
        assert buttons[0].enabled is not (
            action
            in (
                FootballBonusCardAction.DEFENSIVE_DRAW,
                FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
            )
        )
        if buttons[0].enabled:
            assert view.match_interaction.card_rects[card.copy_id].right <= 890
        else:
            assert card.copy_id not in view.match_interaction.card_rects


def test_bonus_shop_purchases_repeat_with_independent_copy_ids_and_offense_ownership() -> None:
    shop = FootballShop(_roster("Shop"), seed=105)
    card = next(
        card
        for card in shop._catalogs[FootballShopSection.PLAYS_SCHEMES]
        if card.card_id == f"bonus:{FootballBonusCardAction.OFFENSIVE_DRAW.value}"
    )
    shop._offers[FootballShopSection.PLAYS_SCHEMES] = [card, None, None, None]

    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)
    shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)
    copies = tuple(
        owned
        for owned in shop.offensive_deck
        if owned.card_id == FootballBonusCardAction.OFFENSIVE_DRAW.value
    )

    assert len(copies) == 2
    assert len({copy.copy_id for copy in copies}) == 2
    assert len(shop.defensive_deck) == 6
    assert shop.remaining_ap == 8
    assert not shop.state.section(FootballShopSection.PLAYS_SCHEMES).slots[0].purchased


@pytest.mark.parametrize(
    ("action", "draws_defense", "discards_opponent"),
    [
        (FootballBonusCardAction.OFFENSIVE_DRAW, False, False),
        (FootballBonusCardAction.DEFENSIVE_DRAW, True, False),
        (FootballBonusCardAction.OPPONENT_DISCARD, False, True),
        (FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD, False, True),
        (FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD, True, True),
    ],
)
def test_bonus_effects_cycle_once_and_preserve_football_situation(
    action: FootballBonusCardAction,
    draws_defense: bool,
    discards_opponent: bool,
) -> None:
    bonus, play, reserve = _owned_bonus_and_plays(action)
    offense = _deck((bonus, play, reserve), (bonus, play), (reserve,))
    defense_cards = starting_defensive_deck("human")
    defense = _deck(defense_cards, defense_cards[:2], defense_cards[2:])
    opponent_cards = starting_defensive_deck("ai")
    if discards_opponent:
        opponent_defense = _deck(opponent_cards, opponent_cards[:2], opponent_cards[2:])
    else:
        opponent_defense = _deck(opponent_cards, (), opponent_cards)
    simulator = FootballMatchSimulator(
        _match_state(
            offense,
            defense=defense,
            opponent_defense=opponent_defense,
        )
    )
    before = simulator.state
    opponent_hand = before.team_b_defense_deck.hand

    result = simulator.resolve_bonus_card(bonus.copy_id)
    next_offense = result.team_a_offense_deck
    assert next_offense is not None
    assert bonus in next_offense.discard_pile
    assert len(next_offense.hand) == len(offense.hand) - int(draws_defense)
    assert len(next_offense.hand) + len(next_offense.draw_pile) + len(
        next_offense.discard_pile
    ) == len(next_offense.owned)
    assert result.game_clock_seconds == before.game_clock_seconds - 10
    assert (
        result.possession,
        result.down,
        result.yards_to_go,
        result.offense_field_position,
        result.team_a_score,
        result.team_b_score,
    ) == (
        before.possession,
        before.down,
        before.yards_to_go,
        before.offense_field_position,
        before.team_a_score,
        before.team_b_score,
    )
    assert result.match_events[-1].action is action
    assert result.match_events[-1].card_copy_id == bonus.copy_id

    next_defense = result.team_a_defense_deck
    assert next_defense is not None
    if draws_defense:
        assert len(next_defense.hand) == len(defense.hand) + 1
    else:
        assert next_defense == defense
    opponent_after = result.team_b_defense_deck
    assert opponent_after is not None
    if discards_opponent and opponent_hand:
        assert len(opponent_after.hand) == len(opponent_hand) - 1
        assert len(opponent_after.discard_pile) == len(opponent_defense.discard_pile) + 1
    else:
        assert opponent_after.hand == opponent_hand


def test_cross_deck_draw_reshuffles_and_fails_atomically_when_empty() -> None:
    bonus, play, reserve = _owned_bonus_and_plays(
        FootballBonusCardAction.DEFENSIVE_DRAW
    )
    offense = _deck((bonus, play, reserve), (bonus, play), (reserve,))
    defense_cards = starting_defensive_deck("human")
    defense = _deck(defense_cards, defense_cards[:2], (), defense_cards[2:])
    simulator = FootballMatchSimulator(_match_state(offense, defense=defense))
    result = simulator.resolve_bonus_card(bonus.copy_id)
    assert result.team_a_defense_deck is not None
    assert len(result.team_a_defense_deck.hand) == 3
    assert len(result.team_a_defense_deck.discard_pile) == 0

    empty_simulator = FootballMatchSimulator(
        _match_state(offense, defense=FootballDeckState(()))
    )
    before = empty_simulator.state
    with pytest.raises(ValueError, match="no drawable card"):
        empty_simulator.resolve_bonus_card(bonus.copy_id)
    assert empty_simulator.state is before


def test_opponent_discard_is_seeded_and_empty_hand_does_not_block_own_draw() -> None:
    bonus, play, reserve = _owned_bonus_and_plays(
        FootballBonusCardAction.OPPONENT_DISCARD
    )
    offense = _deck((bonus, play, reserve), (bonus, play), (reserve,))
    opponent_cards = starting_defensive_deck("ai")
    opponent = _deck(opponent_cards, opponent_cards[:2], opponent_cards[2:])
    initial = _match_state(offense, opponent_defense=opponent)

    simulations = [FootballMatchSimulator(initial) for _ in range(2)]
    results = [sim.resolve_bonus_card(bonus.copy_id) for sim in simulations]
    discarded = [
        result.team_b_defense_deck.discard_pile[-1] for result in results
    ]
    assert discarded[0] == discarded[1]
    assert results[0].team_a_offense_deck.hand == results[1].team_a_offense_deck.hand

    empty_opponent = _deck(opponent_cards, (), opponent_cards)
    empty_simulator = FootballMatchSimulator(
        _match_state(offense, opponent_defense=empty_opponent)
    )
    result = empty_simulator.resolve_bonus_card(bonus.copy_id)
    assert result.team_b_defense_deck.hand == ()
    assert bonus in result.team_a_offense_deck.discard_pile
    assert len(result.team_a_offense_deck.hand) == len(offense.hand)


def test_challenge_restores_play_state_but_keeps_clock_draw_and_both_events() -> None:
    run = FootballCardCopy("human:play:run", OffensivePlayAction.RB_RUN.value)
    challenge = FootballCardCopy(
        "human:bonus:challenge", FootballBonusCardAction.CHALLENGE.value
    )
    reserve = FootballCardCopy("human:play:reserve", OffensivePlayAction.SCREEN_PASS.value)
    extra = FootballCardCopy("human:play:extra", OffensivePlayAction.PA_PASS.value)
    offense = _deck((run, challenge, reserve, extra), (run, challenge), (reserve, extra))
    state = _match_state(offense, field_position=99.0, down=1, yards_to_go=1.0)
    simulator = FootballMatchSimulator(state)
    simulator.rng = _TurnoverRng(81)

    after_play = simulator.resolve_offensive_play(run.copy_id)
    result = after_play.match_events[-1].play_result
    assert result is not None and (result.turnover or result.turnover_on_downs)
    clock_after_play = after_play.game_clock_seconds
    post_play_draw = next(
        card
        for card in after_play.team_a_offense_deck.hand
        if card.copy_id == reserve.copy_id
    )
    rng_after_play = simulator.rng.getstate()

    challenged = simulator.resolve_bonus_card(challenge.copy_id)
    deck = challenged.team_a_offense_deck
    assert deck is not None
    assert challenged.team_a_score == 0
    assert challenged.possession is FootballTeamSide.TEAM_A
    assert challenged.down == 1
    assert challenged.yards_to_go == 1.0
    assert challenged.offense_field_position == 99.0
    assert challenged.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert challenged.game_clock_seconds == clock_after_play
    assert post_play_draw in deck.hand
    assert run in deck.discard_pile
    assert challenge in deck.discard_pile
    assert [event.action for event in challenged.match_events] == [
        OffensivePlayAction.RB_RUN,
        FootballBonusCardAction.CHALLENGE,
    ]
    assert challenged.match_events[-1].reverses_event_sequences == (1,)
    assert simulator.rng.getstate() == rng_after_play


def test_challenge_restores_state_after_an_ordinary_non_turnover_play() -> None:
    play = FootballCardCopy("human:play:run", OffensivePlayAction.RB_RUN.value)
    bonus = FootballCardCopy(
        "human:bonus:challenge", FootballBonusCardAction.CHALLENGE.value
    )
    reserve = FootballCardCopy(
        "human:play:reserve", OffensivePlayAction.SCREEN_PASS.value
    )
    extra = FootballCardCopy(
        "human:play:extra", OffensivePlayAction.PA_PASS.value
    )
    offense = _deck(
        (bonus, play, reserve, extra),
        (bonus, play),
        (reserve, extra),
    )
    before = _match_state(offense)
    simulator = FootballMatchSimulator(before)
    simulator.rng = _NoTurnoverRng(82)

    after_play = simulator.resolve_offensive_play(play.copy_id)

    result = after_play.match_events[-1].play_result
    assert result is not None
    assert not result.turnover and not result.turnover_on_downs
    assert simulator.available_challenge_copy_id == bonus.copy_id
    post_play_deck = after_play.team_a_offense_deck
    assert post_play_deck is not None
    rng_after_play = simulator.rng.getstate()

    challenged = simulator.resolve_bonus_card(bonus.copy_id)

    deck = challenged.team_a_offense_deck
    assert deck is not None
    assert (
        challenged.possession,
        challenged.down,
        challenged.yards_to_go,
        challenged.offense_field_position,
        challenged.team_a_score,
        challenged.team_b_score,
    ) == (
        before.possession,
        before.down,
        before.yards_to_go,
        before.offense_field_position,
        before.team_a_score,
        before.team_b_score,
    )
    assert challenged.game_clock_seconds == after_play.game_clock_seconds
    assert all(
        card in deck.hand
        for card in post_play_deck.hand
        if card != bonus
    )
    assert len(deck.hand) == len(post_play_deck.hand)
    assert play in deck.discard_pile and bonus in deck.discard_pile
    assert challenged.match_events[-1].action is FootballBonusCardAction.CHALLENGE
    assert challenged.match_events[-1].reverses_event_sequences == (1,)
    assert simulator.rng.getstate() == rng_after_play


def test_challenge_expires_when_turnover_crosses_period_boundary() -> None:
    bonus, play, reserve = _owned_bonus_and_plays(
        FootballBonusCardAction.CHALLENGE
    )
    offense = _deck(
        (bonus, play, reserve),
        (bonus, play),
        (reserve,),
    )
    state = replace(_match_state(offense), game_clock_seconds=10)
    simulator = FootballMatchSimulator(state)
    simulator.rng = _TurnoverRng(83)

    after_play = simulator.resolve_offensive_play(play.copy_id)

    result = after_play.match_events[-1].play_result
    assert result is not None and result.turnover
    assert after_play.period == 2
    assert after_play.game_clock_seconds == 900
    assert simulator.available_challenge_copy_id is None
    with pytest.raises(ValueError, match="current human offensive decision"):
        simulator.resolve_bonus_card(bonus.copy_id)
    assert simulator.state is after_play


def test_challenge_restores_touchdown_before_conversion() -> None:
    play = FootballCardCopy("human:play:run", OffensivePlayAction.RB_RUN.value)
    challenge = FootballCardCopy(
        "human:bonus:challenge", FootballBonusCardAction.CHALLENGE.value
    )
    reserve = FootballCardCopy(
        "human:play:reserve", OffensivePlayAction.SCREEN_PASS.value
    )
    extra = FootballCardCopy(
        "human:play:extra", OffensivePlayAction.PA_PASS.value
    )
    offense = _deck(
        (play, challenge, reserve, extra),
        (play, challenge),
        (reserve, extra),
    )
    before = replace(
        _match_state(offense, field_position=99.0, down=1, yards_to_go=1.0),
        current_drive_defensive_scheme=next(
            iter(DEFENSIVE_SCHEME_CATALOG.values())
        ).action,
    )
    simulator = FootballMatchSimulator(before)
    simulator.rng = _NoTurnoverRng(85)

    touchdown = simulator.resolve_offensive_play(play.copy_id)

    result = touchdown.match_events[-1].play_result
    assert result is not None and result.points_scored == 6
    assert touchdown.awaited_action is FootballAwaitedAction.CONVERSION
    assert simulator.available_challenge_copy_id == challenge.copy_id
    clock_after_touchdown = touchdown.game_clock_seconds
    deck_after_touchdown = touchdown.team_a_offense_deck
    assert deck_after_touchdown is not None
    rng_after_touchdown = simulator.rng.getstate()

    challenged = simulator.resolve_bonus_card(challenge.copy_id)

    challenged_deck = challenged.team_a_offense_deck
    assert challenged_deck is not None
    assert challenged.team_a_score == before.team_a_score
    assert challenged.team_b_score == before.team_b_score
    assert challenged.possession is before.possession
    assert challenged.offense_field_position == before.offense_field_position
    assert challenged.down == before.down
    assert challenged.yards_to_go == before.yards_to_go
    assert challenged.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert challenged.game_clock_seconds == clock_after_touchdown
    assert play in challenged_deck.discard_pile
    assert challenge in challenged_deck.discard_pile
    assert all(
        card in challenged_deck.hand
        for card in deck_after_touchdown.hand
        if card != challenge
    )
    assert challenged.match_events[-1].action is FootballBonusCardAction.CHALLENGE
    assert challenged.match_events[-1].reverses_event_sequences == (
        touchdown.match_events[-1].sequence,
    )
    assert simulator.rng.getstate() == rng_after_touchdown


def _controller_with_challenge_in_hand() -> tuple[
    FootballGameController,
    FootballCardCopy,
    FootballCardCopy,
    OffensivePlayAction,
]:
    controller = FootballGameController(
        "Home",
        difficulty=FootballAIDifficulty.EASY,
        builder_seed=11,
        shop_seed=12,
        ai_seed=13,
        match_seed=14,
    )
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        controller.choose_player(position, 0)
    controller.finish_shop()
    simulator = controller._simulator
    assert simulator is not None
    old_deck = simulator.state.team_a_offense_deck
    assert old_deck is not None
    action = OffensivePlayAction.RB_RUN
    run = next(card for card in old_deck.owned if card.card_id == action.value)
    challenge = FootballCardCopy(
        "human:prompt:challenge", FootballBonusCardAction.CHALLENGE.value
    )
    other_cards = tuple(card for card in old_deck.owned if card != run)
    new_deck = _deck(old_deck.owned + (challenge,), (run, challenge), other_cards)
    simulator.state = replace(simulator.state, team_a_offense_deck=new_deck)
    simulator.rng = _TurnoverRng(14)
    return controller, run, challenge, action


def test_turnover_prompts_for_challenge_and_acceptance_returns_human_to_snap() -> None:
    controller, run, _challenge, _action = _controller_with_challenge_in_hand()
    before_position = controller.state.match.offense_field_position

    prompt = controller.choose_offensive_play(run.copy_id)
    assert prompt.human_decision is FootballHumanDecision.CHALLENGE
    assert prompt.match.match_events[-1].play_result.turnover

    resumed = controller.respond_to_challenge(True)
    assert resumed.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert resumed.match.possession is FootballTeamSide.TEAM_A
    assert resumed.match.offense_field_position == before_position


def test_ordinary_play_keeps_challenge_available_without_prompt() -> None:
    controller, run, challenge, _action = _controller_with_challenge_in_hand()
    simulator = controller._simulator
    assert simulator is not None
    simulator.rng = _NoTurnoverRng(84)
    before = controller.state.match
    assert before is not None

    after_play = controller.choose_offensive_play(run.copy_id)

    result = after_play.match.match_events[-1].play_result
    assert result is not None and not result.turnover and not result.turnover_on_downs
    assert after_play.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert after_play.challenge_available

    challenged = controller.choose_offensive_play(challenge.copy_id)

    assert challenged.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert challenged.match.possession is before.possession
    assert challenged.match.down == before.down
    assert challenged.match.yards_to_go == before.yards_to_go
    assert challenged.match.offense_field_position == before.offense_field_position
    assert challenged.match.team_a_score == before.team_a_score
    assert challenged.match.team_b_score == before.team_b_score
    assert challenged.match.game_clock_seconds == after_play.match.game_clock_seconds
    assert challenged.match.match_events[-1].action is FootballBonusCardAction.CHALLENGE
    assert challenged.match.match_events[-1].reverses_event_sequences == (
        after_play.match.match_events[-1].sequence,
    )


def test_controller_challenge_after_touchdown_returns_to_offensive_decision() -> None:
    controller, run, challenge, _action = _controller_with_challenge_in_hand()
    simulator = controller._simulator
    assert simulator is not None
    simulator.rng = _NoTurnoverRng(86)
    before = replace(
        simulator.state,
        team_a=replace(
            simulator.state.team_a,
            players={
                position: replace(player, power=1000.0)
                if position in (FootballPosition.RB, FootballPosition.O_LINE)
                else player
                for position, player in simulator.state.team_a.players.items()
            },
        ),
        down=1,
        yards_to_go=1.0,
        offense_field_position=99.0,
        current_drive_defensive_scheme=next(
            iter(DEFENSIVE_SCHEME_CATALOG.values())
        ).action,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
    )
    simulator.state = before

    conversion = controller.choose_offensive_play(run.copy_id)

    assert conversion.human_decision is FootballHumanDecision.CONVERSION
    assert conversion.match.team_a_score == before.team_a_score + 6
    assert conversion.challenge_available
    clock_after_touchdown = conversion.match.game_clock_seconds

    resumed = controller.challenge_touchdown()

    assert resumed.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert resumed.match.team_a_score == before.team_a_score
    assert resumed.match.team_b_score == before.team_b_score
    assert resumed.match.possession is before.possession
    assert resumed.match.offense_field_position == before.offense_field_position
    assert resumed.match.down == before.down
    assert resumed.match.yards_to_go == before.yards_to_go
    assert resumed.match.game_clock_seconds == clock_after_touchdown
    assert resumed.match.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert resumed.match.match_events[-1].action is FootballBonusCardAction.CHALLENGE
    assert resumed.match.match_events[-1].reverses_event_sequences == (
        conversion.match.match_events[-1].sequence,
    )
    assert challenge in resumed.match.team_a_offense_deck.discard_pile


def test_conversion_without_available_challenge_keeps_conversion_flow() -> None:
    controller, _run, _challenge, _action = _controller_with_challenge_in_hand()
    simulator = controller._simulator
    assert simulator is not None
    simulator.state = replace(
        simulator.state,
        awaited_action=FootballAwaitedAction.CONVERSION,
        conversion_team=FootballTeamSide.TEAM_A,
        possession=FootballTeamSide.TEAM_A,
        down=1,
        yards_to_go=2.0,
        offense_field_position=98.0,
    )
    assert not controller.state.challenge_available

    with pytest.raises(ValueError, match="No Challenge card is available"):
        controller.challenge_touchdown()

    resolved = controller.choose_conversion(FootballConversionAction.EXTRA_POINT)
    assert resolved.human_decision is not FootballHumanDecision.CONVERSION
    assert not any(
        event.action is FootballBonusCardAction.CHALLENGE
        for event in resolved.match.match_events
    )


def test_declining_turnover_challenge_continues_normal_defensive_decision() -> None:
    controller, run, _challenge, _action = _controller_with_challenge_in_hand()
    prompt = controller.choose_offensive_play(run.copy_id)
    assert prompt.human_decision is FootballHumanDecision.CHALLENGE

    continued = controller.respond_to_challenge(False)
    assert continued.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME
    assert continued.match.possession is FootballTeamSide.TEAM_B
    assert controller._simulator.available_challenge_copy_id is None


def test_failed_fourth_down_also_prompts_before_the_opponent_advances() -> None:
    controller, _run, challenge, _old_action = _controller_with_challenge_in_hand()
    simulator = controller._simulator
    assert simulator is not None
    deck = simulator.state.team_a_offense_deck
    assert deck is not None
    short_pass = next(
        card
        for card in deck.owned
        if card.card_id == OffensivePlayAction.SHORT_PASS.value
    )
    owned = deck.owned
    updated_deck = _deck(
        owned,
        (short_pass, challenge),
        tuple(card for card in owned if card not in (short_pass, challenge)),
    )
    simulator.state = replace(
        simulator.state,
        down=4,
        yards_to_go=10.0,
        team_a_offense_deck=updated_deck,
    )
    controller_start = controller.state.match
    prompt = controller.choose_offensive_play(short_pass.copy_id)

    assert prompt.human_decision is FootballHumanDecision.CHALLENGE
    result = prompt.match.match_events[-1].play_result
    assert result is not None and result.turnover_on_downs
    assert not result.turnover
    resumed = controller.respond_to_challenge(True)
    assert resumed.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert resumed.match.down == 4
    assert resumed.match.yards_to_go == controller_start.yards_to_go
