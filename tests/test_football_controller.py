from dataclasses import FrozenInstanceError, replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballFourthDownAction,
    FootballMatchResult,
    FootballMatchStatus,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER, FootballPlayerCandidate
from src.engine.football_coaches import FootballCoachPair
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
)


def _controller(
    *,
    difficulty: FootballAIDifficulty = FootballAIDifficulty.EASY,
    builder_seed: int = 17,
    shop_seed: int = 29,
    ai_seed: int = 41,
    match_seed: int = 53,
) -> FootballGameController:
    return FootballGameController(
        "Human Team",
        difficulty=difficulty,
        builder_seed=builder_seed,
        shop_seed=shop_seed,
        ai_seed=ai_seed,
        match_seed=match_seed,
    )


def _draft_to_shop(controller: FootballGameController) -> None:
    assert controller.state.human_decision is FootballHumanDecision.CHOOSE_COACH
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        assert controller.state.human_decision is FootballHumanDecision.DRAFT_PLAYER
        assert controller.state.team_builder.required_position is position
        assert len(controller.state.team_builder.current_offer) == 3
        controller.choose_player(position, 0)


def _start_match(controller: FootballGameController) -> None:
    _draft_to_shop(controller)
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_budget == 12
    assert len(controller.state.shop.offer) == 3
    controller.finish_shop()


def _enter_next_match(controller: FootballGameController) -> None:
    state = controller.enter_next_shop()
    assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert state.shop is not None and state.shop.remaining_ap == 12
    controller.finish_shop()


def _force_match_result(monkeypatch, controller, winner: FootballTeamSide) -> None:
    from src.engine.football_simulator import FootballMatchSimulator

    def finish(simulator, _play):
        score_a = 7 if winner is FootballTeamSide.TEAM_A else 0
        score_b = 7 if winner is FootballTeamSide.TEAM_B else 0
        result = FootballMatchResult(score_a, score_b, winner, True)
        simulator.state = replace(
            simulator.state,
            team_a_score=score_a,
            team_b_score=score_b,
            status=FootballMatchStatus.COMPLETED,
            awaited_action=None,
            current_drive_defensive_scheme=None,
            final_result=result,
        )
        return simulator.state

    monkeypatch.setattr(FootballMatchSimulator, "resolve_offensive_play", finish)


def _complete_forced_match(controller: FootballGameController) -> None:
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    controller.choose_offensive_play(OffensivePlayAction.RB_RUN)


def test_full_draft_shop_and_match_lifecycle_starts_team_a_against_local_ai() -> None:
    controller = _controller(difficulty=FootballAIDifficulty.STANDARD)
    _draft_to_shop(controller)

    state = controller.state
    assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert state.team_builder.completed
    assert state.shop is not None
    selected_pair = state.team_builder.selected_coach_pair
    assert selected_pair is not None
    assert (
        state.shop.roster.coach_assignment
        == selected_pair.assignment
    )
    assert state.shop.remaining_budget == 12
    assert len(state.shop.offer) == 3

    power_upgrade = next(
        upgrade for upgrade in state.shop.offer if upgrade.stat.value == "power"
    )
    stamina_upgrade = next(
        upgrade for upgrade in state.shop.offer if upgrade.stat.value == "stamina"
    )
    controller.buy_upgrade(power_upgrade)
    controller.buy_upgrade(stamina_upgrade)
    assert controller.state.shop is not None
    assert (
        controller.state.shop.roster.coach_assignment
        == selected_pair.assignment
    )
    assert controller.state.shop.remaining_budget == 7
    assert len(controller.state.shop.purchased_upgrades) == 2

    match_view = controller.finish_shop()
    assert match_view.phase is FootballRunPhase.MATCH
    assert match_view.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert match_view.opponent_name == "Local AI"
    assert match_view.opponent_difficulty is FootballAIDifficulty.STANDARD
    assert match_view.match is not None
    assert match_view.match.team_a.team_name == "Human Team"
    assert match_view.match.team_b.team_name == "Local AI"
    assert (
        match_view.match.team_a.coach_assignment
        == selected_pair.assignment
    )
    assert match_view.match.team_b.coach_assignment is not None
    assert match_view.match.possession is FootballTeamSide.TEAM_A
    assert match_view.match.match_events
    assert isinstance(match_view.match.match_events[0].action, DefensiveSchemeAction)
    assert match_view.shop is not None and match_view.shop.finished


def test_human_offense_defense_fourth_down_and_ai_progression_complete_a_real_match() -> None:
    controller = _controller(match_seed=1, ai_seed=4)
    _start_match(controller)
    match = controller.state.match
    assert match is not None
    assert match.awaited_action is not None
    assert match.possession is FootballTeamSide.TEAM_A

    human_defensive_drives = 0
    human_fourth_downs = 0
    for _ in range(1200):
        state = controller.state
        if state.phase is not FootballRunPhase.MATCH:
            break
        assert state.match is not None
        assert state.human_decision is not None
        if state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            controller.choose_offensive_play(OffensivePlayAction.DEEP_PASS)
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            prior_event_count = len(state.match.match_events)
            controller.choose_defensive_scheme(DefensiveSchemeAction.RB_RUN)
            updated = controller.state.match
            assert updated is not None
            first_new_event = updated.match_events[prior_event_count]
            assert first_new_event.action is DefensiveSchemeAction.RB_RUN
            assert first_new_event.possession is FootballTeamSide.TEAM_B
            human_defensive_drives += 1
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            assert state.match.down == 4
            controller.choose_fourth_down(FootballFourthDownAction.PUNT)
            human_fourth_downs += 1
        else:
            raise AssertionError(f"Unexpected decision: {state.human_decision}")

    else:
        pytest.fail("The simulator did not complete the seeded match.")

    final = controller.state
    assert final.phase in (
        FootballRunPhase.READY_FOR_NEXT_GAME,
        FootballRunPhase.FIRED,
        FootballRunPhase.PLAYOFFS,
    )
    assert final.match is not None
    assert final.match.status is FootballMatchStatus.COMPLETED
    assert final.match.final_result is not None
    assert final.match.final_result.winner in (
        FootballTeamSide.TEAM_A,
        FootballTeamSide.TEAM_B,
    )
    assert human_defensive_drives > 0
    assert human_fourth_downs > 0
    ai_offensive_plays = sum(
        isinstance(event.action, OffensivePlayAction)
        and event.possession is FootballTeamSide.TEAM_B
        for event in final.match.match_events
    )
    assert ai_offensive_plays > 0

    events = final.match.match_events
    human_defense_drive_count = 0
    for start in range(len(events)):
        if events[start].possession is not FootballTeamSide.TEAM_B:
            continue
        if start and events[start - 1].possession is FootballTeamSide.TEAM_B:
            continue
        end = start + 1
        while end < len(events) and events[end].possession is FootballTeamSide.TEAM_B:
            end += 1
        drive = events[start:end]
        schemes = [event for event in drive if isinstance(event.action, DefensiveSchemeAction)]
        assert len(schemes) == 1
        human_defense_drive_count += 1
        scheme_index = drive.index(schemes[0])
        assert scheme_index <= 1
        if scheme_index == 1:
            transition = drive[0]
            if isinstance(transition.action, OffensivePlayAction):
                assert transition.play_result is not None
                assert transition.play_result.possession_changed
            else:
                assert isinstance(transition.action, FootballFourthDownAction)
    assert human_defense_drive_count == human_defensive_drives


def test_invalid_and_out_of_turn_actions_preserve_state_and_all_random_streams() -> None:
    controller = _controller()
    initial = controller.state
    builder_rng = controller._builder._rng.getstate()
    with pytest.raises(ValueError, match="phase"):
        controller.start_next_game()
    with pytest.raises(ValueError, match="not included"):
        offered_pair = controller.state.team_builder.coach_offer[0]
        controller.choose_coach(
            FootballCoachPair(offered_pair.offense, offered_pair.defense)
        )
    assert controller.state == initial
    assert controller._builder._rng.getstate() == builder_rng

    controller.choose_coach(0)
    player_state = controller.state
    player_rng = controller._builder._rng.getstate()
    with pytest.raises(ValueError, match="next required position"):
        controller.choose_player(FootballPosition.RB, 0)
    with pytest.raises(ValueError, match="valid offer index"):
        controller.choose_player(FootballPosition.QB, True)
    assert controller.state == player_state
    assert controller._builder._rng.getstate() == player_rng

    for position in PLAYER_DRAFT_ORDER:
        controller.choose_player(position, 0)
    shop = controller._shop
    assert shop is not None
    shop_rng = shop._rng.getstate()
    shop_state = controller.state
    controller.buy_upgrade(0)
    post_purchase = controller.state
    with pytest.raises(ValueError, match="already been purchased"):
        controller.buy_upgrade(0)
    assert controller._shop is not None
    assert controller._shop._rng.getstate() == shop_rng
    assert controller.state == post_purchase
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_budget == 12 - shop.offer[0].cost
    assert controller.state.phase is shop_state.phase

    controller.finish_shop()
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    simulator = controller._simulator
    assert simulator is not None
    before = controller.state
    sim_rng = simulator.rng.getstate()
    ai_rng = controller._ai._rng.getstate()
    match_seed_rng = controller._match_seed_rng.getstate()
    with pytest.raises(ValueError, match="not currently required"):
        controller.choose_defensive_scheme(DefensiveSchemeAction.RB_RUN)
    with pytest.raises(ValueError, match="OffensivePlayAction"):
        controller.choose_offensive_play(DefensiveSchemeAction.RB_RUN)  # type: ignore[arg-type]
    assert controller.state == before
    assert simulator.rng.getstate() == sim_rng
    assert controller._ai._rng.getstate() == ai_rng
    assert controller._match_seed_rng.getstate() == match_seed_rng


def test_seeded_runs_are_reproducible_and_random_streams_are_independent() -> None:
    global_rng_state = random.getstate()
    first = _controller()
    replay = _controller()
    assert first.state == replay.state
    _draft_to_shop(first)
    _draft_to_shop(replay)
    assert first.state == replay.state
    first.buy_upgrade(0)
    replay.buy_upgrade(0)
    first.finish_shop()
    replay.finish_shop()
    assert first.state == replay.state

    other_builder_and_shop = _controller(builder_seed=101, shop_seed=103)
    _start_match(other_builder_and_shop)
    assert other_builder_and_shop.state.match is not None
    assert first.state.match is not None
    assert (
        first.state.match.team_b
        == other_builder_and_shop.state.match.team_b
    )
    assert first.state.match.random_seed == other_builder_and_shop.state.match.random_seed
    assert first._ai._rng.getstate() == other_builder_and_shop._ai._rng.getstate()

    different_ai = _controller(ai_seed=107)
    _start_match(different_ai)
    assert different_ai.state.match is not None
    assert first._simulator is not None and different_ai._simulator is not None
    assert first._simulator.rng.getstate() == different_ai._simulator.rng.getstate()
    assert random.getstate() == global_rng_state


def test_three_losses_immediately_fire_run(monkeypatch) -> None:
    controller = _controller()
    _start_match(controller)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_B)

    for loss_number in range(1, 4):
        _complete_forced_match(controller)
        state = controller.state
        assert state.losses == loss_number
        if loss_number < 3:
            assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
            _enter_next_match(controller)
        else:
            assert state.phase is FootballRunPhase.FIRED
            assert state.human_decision is None
            assert state.shop is not None
            assert state.shop.game_number == 3 and state.shop.finished

    with pytest.raises(ValueError, match="phase"):
        controller.start_next_game()


def test_surviving_tenth_regular_season_game_marks_playoffs_without_bracket(
    monkeypatch,
) -> None:
    controller = _controller()
    _start_match(controller)
    for game_number in range(1, 11):
        _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
        _complete_forced_match(controller)
        state = controller.state
        assert state.game_number == game_number
        assert state.wins == game_number
        if game_number < 10:
            assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
            _enter_next_match(controller)
        else:
            assert state.phase is FootballRunPhase.PLAYOFFS
            assert state.human_decision is None
            assert state.match is not None and state.match.final_result is not None
            assert state.shop is not None
            assert state.shop.game_number == 10 and state.shop.finished

    with pytest.raises(ValueError, match="phase"):
        controller.start_next_game()


def test_next_shop_resets_ap_and_preserves_upgrades_roster_and_slot_unlocks(
    monkeypatch,
) -> None:
    controller = _controller()
    _draft_to_shop(controller)
    first_shop = controller.state.shop
    assert first_shop is not None
    upgrade = first_shop.offer[0]
    original_player = first_shop.roster.players[upgrade.position]
    controller.buy_upgrade(upgrade)
    controller.unlock_shop_slot(FootballShopSection.PLAYER_UPGRADES, 4)
    remaining_ap = controller.state.shop.remaining_ap
    assert remaining_ap > 0

    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    controller.finish_shop()
    _complete_forced_match(controller)
    result = controller.state
    assert result.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    assert result.match is not None
    assert result.match.team_a.players[upgrade.position] != original_player

    next_shop = controller.enter_next_shop()
    assert next_shop.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert next_shop.game_number == 2
    assert next_shop.shop is not None
    assert next_shop.shop.remaining_ap == 12
    assert next_shop.shop.day == 1
    assert next_shop.shop.purchased_cards == ()
    assert next_shop.shop.roster == result.match.team_a
    assert next_shop.shop.roster.players[upgrade.position] == (
        result.match.team_a.players[upgrade.position]
    )
    assert next_shop.shop.section(
        FootballShopSection.PLAYER_UPGRADES
    ).slots[3].unlocked
    assert next_shop.selected_coach_pair == result.selected_coach_pair
    assert next_shop.team_builder.selected_players == result.team_builder.selected_players


def test_coach_slot_unlock_becomes_optional_after_game_three(monkeypatch) -> None:
    coach_cards = tuple(
        FootballShopCard(
            card_id=f"coach-test-{index}",
            name=f"Test coach upgrade {index}",
            description="An injected test-only coach catalog card.",
            section=FootballShopSection.COACH_UPGRADES,
            rarity=FootballShopRarity.RARE,
            cost=1,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
        )
        for index in range(2)
    )
    controller = FootballGameController(
        "Human Team",
        difficulty=FootballAIDifficulty.EASY,
        builder_seed=17,
        shop_seed=29,
        ai_seed=41,
        match_seed=53,
        shop_catalogs={FootballShopSection.COACH_UPGRADES: coach_cards},
    )
    _start_match(controller)

    for game_number in range(1, 4):
        _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
        _complete_forced_match(controller)
        if game_number < 3:
            _enter_next_match(controller)

    assert controller.state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    game_four = controller.enter_next_shop()
    assert game_four.game_number == 4
    assert game_four.shop is not None
    coach = game_four.shop.section(FootballShopSection.COACH_UPGRADES)
    assert coach.slots[0].can_unlock and coach.slots[0].unlock_cost == 4
    assert not coach.slots[1].can_unlock

    unlocked = controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    coach = unlocked.shop.section(FootballShopSection.COACH_UPGRADES)
    assert unlocked.shop.remaining_ap == 8
    assert coach.slots[0].card is not None
    assert coach.slots[1].can_unlock and coach.slots[1].unlock_cost == 6


def test_public_state_is_immutable_and_contains_ui_rendering_data() -> None:
    controller = _controller(difficulty=FootballAIDifficulty.HARD)
    coach_state = controller.state
    assert coach_state.human_decision is FootballHumanDecision.CHOOSE_COACH
    assert len(coach_state.team_builder.coach_offer) == 3
    with pytest.raises(FrozenInstanceError):
        coach_state.phase = FootballRunPhase.MATCH  # type: ignore[misc]

    _start_match(controller)
    state = controller.state
    assert state.phase is FootballRunPhase.MATCH
    assert state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert state.opponent_name == "Local AI"
    assert state.opponent_difficulty is FootballAIDifficulty.HARD
    assert state.game_number == 1
    assert state.wins == 0 and state.losses == 0
    assert state.match is not None
    assert isinstance(state.match.match_events, tuple)
    with pytest.raises(TypeError):
        state.match.team_a.players[FootballPosition.QB] = state.match.team_b.players[
            FootballPosition.QB
        ]
    with pytest.raises(AttributeError):
        state.match.match_events.append(state.match.match_events[0])
