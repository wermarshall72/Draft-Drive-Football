"""A seeded driver that plays a football run through its human decisions.

Shared by the run-save tests. Each step makes one human decision (including
shop purchases, unlocks, Next Day, removals, bonus cards, fourth downs,
conversions, and Challenge responses) chosen only from the controller state
and the given ``random.Random``, so two controllers in the same state given
identically seeded drivers make identical choices.
"""

from __future__ import annotations

import random

from src.engine.football import (
    FootballConversionAction,
    FootballFourthDownAction,
    FootballPosition,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_appearance import POSITION_ART, FootballPlayerAppearance
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
)
from src.engine.football_shop import MIN_PLAYBOOK_DECK_SIZE


def new_controller(seed: int, difficulty: FootballAIDifficulty = FootballAIDifficulty.STANDARD
                   ) -> FootballGameController:
    rng = random.Random(seed)
    return FootballGameController(
        "Save Owls",
        difficulty=difficulty,
        builder_seed=rng.getrandbits(64),
        shop_seed=rng.getrandbits(64),
        ai_seed=rng.getrandbits(64),
        match_seed=rng.getrandbits(64),
    )


def _appearance(position: FootballPosition, rng: random.Random) -> FootballPlayerAppearance:
    def color() -> tuple[int, int, int]:
        return (rng.randrange(256), rng.randrange(256), rng.randrange(256))

    return FootballPlayerAppearance(POSITION_ART[position], color(), color(), color())


def _shop_step(controller: FootballGameController, rng: random.Random) -> None:
    shop = controller.state.shop
    assert shop is not None
    if shop.pending_removal is not None:
        removable = [
            card
            for deck in (shop.offensive_deck, shop.defensive_deck)
            if len(deck) > MIN_PLAYBOOK_DECK_SIZE
            for card in deck
        ]
        if removable and rng.random() < 0.7:
            controller.remove_owned_card(rng.choice(removable).copy_id)
        else:
            controller.cancel_card_removal()
        return
    roll = rng.random()
    if roll < 0.55:
        offers = [
            (slot.section, slot.slot_number - 1)
            for section in shop.sections
            for slot in section.slots
            if slot.unlocked and slot.card is not None and not slot.purchased
            and slot.card.cost <= shop.remaining_ap
        ]
        if offers:
            section, index = rng.choice(offers)
            try:
                controller.buy_shop_card(section, index)
                return
            except ValueError:
                pass
    elif roll < 0.7:
        unlocks = [
            (slot.section, slot.slot_number)
            for section in shop.sections
            for slot in section.slots
            if slot.can_unlock
        ]
        if unlocks:
            controller.unlock_shop_slot(*rng.choice(unlocks))
            return
    elif roll < 0.8 and shop.remaining_ap >= 1:
        controller.move_to_next_day()
        return
    controller.finish_shop()


def step(controller: FootballGameController, rng: random.Random) -> bool:
    """Make one human decision; False once the run has no decision left."""
    state = controller.state
    decision = state.human_decision
    if decision is None:
        return False
    match = state.match
    if decision is FootballHumanDecision.CHOOSE_COACH:
        controller.choose_coach(rng.randrange(3))
    elif decision is FootballHumanDecision.DRAFT_PLAYER:
        position = state.team_builder.required_position
        assert position is not None
        controller.choose_player(
            position, rng.randrange(3), appearance=_appearance(position, rng)
        )
    elif decision is FootballHumanDecision.SHOP:
        _shop_step(controller, rng)
    elif decision is FootballHumanDecision.OPEN_NEXT_SHOP:
        controller.enter_next_shop()
    elif decision is FootballHumanDecision.OFFENSIVE_PLAY:
        assert match is not None and match.team_a_offense_deck is not None
        hand = [card.copy_id for card in match.team_a_offense_deck.hand]
        rng.shuffle(hand)
        for copy_id in hand:
            try:
                controller.choose_offensive_play(copy_id)
                return True
            except ValueError:
                continue
        controller.choose_offensive_play(None)
    elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
        assert match is not None and match.team_a_defense_deck is not None
        hand = match.team_a_defense_deck.hand
        controller.choose_defensive_scheme(rng.choice(hand).copy_id if hand else None)
    elif decision is FootballHumanDecision.GREEN_DOG:
        assert match is not None and match.team_a_defense_deck is not None
        hand = match.team_a_defense_deck.hand
        controller.respond_to_green_dog(
            rng.choice(hand).copy_id if hand and rng.random() < 0.5 else None
        )
    elif decision is FootballHumanDecision.FOURTH_DOWN:
        # Mostly sensible calls (so seeded runs last long enough to reach late-run
        # phases), with a random call now and then.
        assert match is not None
        if rng.random() < 0.2:
            choice = rng.choice(list(FootballFourthDownAction))
        elif match.yards_to_go <= 2 or match.offense_field_position >= 65:
            choice = (
                FootballFourthDownAction.FIELD_GOAL
                if match.yards_to_go > 2 and match.offense_field_position >= 70
                else FootballFourthDownAction.GO_FOR_IT
            )
        else:
            choice = FootballFourthDownAction.PUNT
        controller.choose_fourth_down(choice)
    elif decision is FootballHumanDecision.CONVERSION:
        if state.challenge_available and rng.random() < 0.5:
            controller.challenge_touchdown()
        elif rng.random() < 0.5:
            controller.choose_conversion(FootballConversionAction.EXTRA_POINT)
        else:
            assert match is not None and match.team_a_offense_deck is not None
            from src.engine.football_decks import OFFENSIVE_PLAY_CATALOG

            plays = [
                card.copy_id for card in match.team_a_offense_deck.hand
                if card.card_id in OFFENSIVE_PLAY_CATALOG
            ]
            controller.choose_conversion(
                FootballConversionAction.TWO_POINT, rng.choice(plays) if plays else None
            )
    elif decision is FootballHumanDecision.CHALLENGE:
        controller.respond_to_challenge(rng.random() < 0.6)
    else:  # pragma: no cover - every decision is handled above
        raise AssertionError(decision)
    return True
