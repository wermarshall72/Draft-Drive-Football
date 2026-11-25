from dataclasses import FrozenInstanceError, replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballAutomaticAction,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchResult,
    FootballMatchStatus,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_playoffs import FootballPlayoffRound
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
    FootballRunPhase,
    FootballSeasonGame,
    FootballSeasonOutcome,
)
from src.engine.football_simulator import REGULATION_PERIOD_SECONDS
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.engine.football_appearance import FootballPlayerAppearance, POSITION_ART
from src.engine.football_coaches import FootballCoachPair
from src.engine.football_shop import (
    COACH_UPGRADE_CATALOG,
    PLAYER_UPGRADE_CATALOG,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballUpgradeDuration,
    FootballUpgradeStat,
    _player_upgrade_catalog,
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


def test_appearance_is_run_local_and_does_not_change_gameplay_streams() -> None:
    first, second = _controller(), _controller()
    first.choose_coach(0)
    second.choose_coach(0)
    saved = {}
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        assert first.state.team_builder.current_offer == second.state.team_builder.current_offer
        candidate = first.state.team_builder.current_offer[1]
        appearance = FootballPlayerAppearance(
            POSITION_ART[position], (90 + index, 80, 60), (1, 2, 3), (4, 5, 6)
        )
        first.choose_player(position, candidate, appearance=appearance)
        second.choose_player(position, 1)
        saved[position] = appearance
        assert first.state.player_appearances == saved
    assert first.state.team_builder.selected_players == second.state.team_builder.selected_players
    assert first.state.shop == second.state.shop
    assert first._builder._rng.getstate() == second._builder._rng.getstate()
    assert first._shop_rng.getstate() == second._shop_rng.getstate()
    assert first._ai._rng.getstate() == second._ai._rng.getstate()
    assert first._match_seed_rng.getstate() == second._match_seed_rng.getstate()
    first.finish_shop()
    second.finish_shop()
    assert first.state.match == second.state.match
    assert first.state.player_appearances == saved


def test_invalid_appearance_and_choice_do_not_change_run() -> None:
    controller = _controller()
    controller.choose_coach(0)
    before = controller.state
    wrong = FootballPlayerAppearance("lineman", (1, 2, 3), (4, 5, 6), (7, 8, 9))
    with pytest.raises(ValueError, match="match the draft position"):
        controller.choose_player(FootballPosition.QB, 0, appearance=wrong)
    correct = replace(wrong, asset_key="quarterback")
    with pytest.raises(ValueError):
        controller.choose_player(FootballPosition.QB, 99, appearance=correct)
    assert controller.state == before


def test_draft_stats_and_appearance_survive_upgrades_and_later_shops(monkeypatch) -> None:
    controller = _controller()
    controller.choose_coach(0)
    drafted = {}
    appearances = {}
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        candidate = controller.state.team_builder.current_offer[0]
        candidate = replace(candidate, player=replace(
            candidate.player, power=40 + index, volatility=0.05 + index * 0.01,
            stamina=0.3 + index * 0.02,
        ))
        controller._builder._current_offer = (
            candidate, *controller.state.team_builder.current_offer[1:],
        )
        appearance = FootballPlayerAppearance(
            POSITION_ART[position], (90 + index, 80, 60), (1, 2, 3), (4, 5, 6)
        )
        controller.choose_player(position, candidate, appearance=appearance)
        drafted[position] = candidate.player
        appearances[position] = appearance
        assert controller.state.drafted_players == drafted
    shop = controller.state.shop
    assert shop is not None
    card = next(card for card in _player_upgrade_catalog()
                if card.upgrade.stat is FootballUpgradeStat.POWER
                and card.upgrade.duration is FootballUpgradeDuration.PERMANENT)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    upgrade = card.upgrade
    controller.buy_upgrade(upgrade)
    assert controller.state.drafted_players == drafted
    assert controller.state.shop.roster.players[upgrade.position].power > drafted[upgrade.position].power
    controller.finish_shop()
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    _complete_forced_match(controller)
    controller.enter_next_shop()
    assert controller.state.drafted_players == drafted
    assert controller.state.player_appearances == appearances
    assert controller.state.team_builder.current_offer == ()
    assert controller.state.shop.roster.players[upgrade.position].power > drafted[upgrade.position].power


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
    assert controller.state.shop.remaining_ap == 12
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


def test_temporary_upgrades_survive_bye_and_expire_only_after_completed_match(monkeypatch) -> None:
    def card(duration):
        return next(card for card in PLAYER_UPGRADE_CATALOG
                    if card.upgrade.position is FootballPosition.QB
                    and card.upgrade.stat is FootballUpgradeStat.POWER
                    and card.upgrade.rarity is FootballShopRarity.COMMON
                    and card.upgrade.duration is duration)

    permanent = card(FootballUpgradeDuration.PERMANENT)
    temporary = card(FootballUpgradeDuration.TEMPORARY)
    bye = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "bye_week")
    controller = FootballGameController(
        "Human Team", difficulty=FootballAIDifficulty.EASY,
        builder_seed=17, shop_seed=29, ai_seed=41, match_seed=53,
        shop_catalogs={
            FootballShopSection.PLAYER_UPGRADES: (permanent, temporary),
            FootballShopSection.COACH_UPGRADES: (bye,),
        },
    )
    _draft_to_shop(controller)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    for game in range(1, 4):
        if game == 3:
            controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, permanent.card_id)
        controller.finish_shop()
        _complete_forced_match(controller)
        controller.enter_next_shop()
    original = controller.state.shop.roster.players[FootballPosition.QB]
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, temporary.card_id)
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    skipped = controller.buy_shop_card(FootballShopSection.COACH_UPGRADES, bye.card_id)
    assert skipped.game_number == 5 and skipped.skipped_games == (4,)
    assert skipped.shop.pending_player_upgrades == (temporary.upgrade,)
    assert skipped.shop.roster.players[FootballPosition.QB] == original
    started = controller.finish_shop()
    assert started.phase is FootballRunPhase.MATCH
    assert started.shop.pending_player_upgrades == (temporary.upgrade,)
    assert started.shop.roster.players[FootballPosition.QB] == original
    assert started.match.team_a.players[FootballPosition.QB].power == original.power + temporary.upgrade.amount
    with pytest.raises(RuntimeError, match="decisive"):
        controller._record_match_result(started.match)
    assert controller.state.shop.pending_player_upgrades == (temporary.upgrade,)
    _complete_forced_match(controller)
    assert controller.state.shop.pending_player_upgrades == ()
    controller.enter_next_shop()
    assert controller.state.shop.roster.players[FootballPosition.QB] == original
    next_match = controller.finish_shop().match
    assert next_match.team_a.players[FootballPosition.QB] == original


def test_temporary_upgrade_survives_interrupted_match_initialization(monkeypatch) -> None:
    controller = _controller()
    _draft_to_shop(controller)
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    with monkeypatch.context() as patch:
        def interrupt():
            raise RuntimeError("Interrupted")
        patch.setattr(controller, "_advance_match", interrupt)
        with pytest.raises(RuntimeError, match="Interrupted"):
            controller.finish_shop()
    assert controller.state.phase is FootballRunPhase.MATCH
    assert controller.state.shop.pending_player_upgrades == (card.upgrade,)
    controller._advance_match()
    assert controller.state.shop.pending_player_upgrades == (card.upgrade,)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    _complete_forced_match(controller)
    assert controller.state.shop.pending_player_upgrades == ()


def test_stacked_capped_temporary_projections_survive_bye(monkeypatch) -> None:
    temp = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.STAMINA
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                and card.rarity is FootballShopRarity.COMMON)
    bye = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "bye_week")
    controller = FootballGameController(
        "Human Team", difficulty=FootballAIDifficulty.EASY,
        builder_seed=17, shop_seed=29, ai_seed=41, match_seed=53,
        shop_catalogs={FootballShopSection.PLAYER_UPGRADES: (temp,),
                       FootballShopSection.COACH_UPGRADES: (bye,)},
    )
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        if position is FootballPosition.QB:
            candidate = controller.state.team_builder.current_offer[0]
            candidate = replace(candidate, player=replace(candidate.player, stamina=0.94))
            controller._builder._current_offer = (
                candidate, *controller.state.team_builder.current_offer[1:],
            )
        controller.choose_player(position, 0)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    for game in range(1, 5):
        if game == 4:
            controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
        controller.finish_shop()
        _complete_forced_match(controller)
        controller.enter_next_shop()
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    controller.move_to_next_day()
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    before = controller.state.shop
    skipped = controller.buy_shop_card(FootballShopSection.COACH_UPGRADES, bye.card_id)
    assert skipped.game_number == 6 and skipped.skipped_games == (5,)
    assert skipped.shop.pending_player_upgrades == (temp.upgrade, temp.upgrade)
    assert skipped.shop.next_match_roster == before.next_match_roster
    assert skipped.shop.next_match_roster.players[FootballPosition.QB].stamina == 1
    assert skipped.shop.project_player_upgrade(temp.upgrade) == before.project_player_upgrade(temp.upgrade)
    assert skipped.shop.project_player_upgrade(temp.upgrade).next_match.change == 0
    started = controller.finish_shop()
    assert started.match.team_a == skipped.shop.next_match_roster
    _complete_forced_match(controller)
    assert controller.state.shop.pending_player_upgrades == ()


def test_coached_pending_projection_survives_bye_until_match_completes(monkeypatch) -> None:
    temp = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.STAMINA
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                and card.rarity is FootballShopRarity.COMMON)
    conditioning = next(card for card in COACH_UPGRADE_CATALOG
                        if card.card_id == "fourth_quarter_conditioning")
    bye = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "bye_week")
    controller = FootballGameController(
        "Human Team", difficulty=FootballAIDifficulty.EASY,
        builder_seed=17, shop_seed=29, ai_seed=41, match_seed=53,
        shop_catalogs={FootballShopSection.PLAYER_UPGRADES: (temp,),
                       FootballShopSection.COACH_UPGRADES: (conditioning, bye)},
    )
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        if position is FootballPosition.QB:
            candidate = controller.state.team_builder.current_offer[0]
            candidate = replace(candidate, player=replace(candidate.player, stamina=0.85))
            controller._builder._current_offer = (
                candidate, *controller.state.team_builder.current_offer[1:],
            )
        controller.choose_player(position, 0)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    for game in range(1, 5):
        if game == 4:
            controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
            controller._shop._offers[FootballShopSection.COACH_UPGRADES][0] = conditioning
            controller.buy_shop_card(FootballShopSection.COACH_UPGRADES, conditioning.card_id)
        controller.finish_shop()
        _complete_forced_match(controller)
        controller.enter_next_shop()
    initial = controller.state.shop.project_player_upgrade(temp.upgrade)
    assert initial.next_match.change == pytest.approx(0.10)
    assert initial.effective_next_match.change == pytest.approx(0.05)
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    controller.move_to_next_day()
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    before = controller.state.shop
    controller._shop._offers[FootballShopSection.COACH_UPGRADES][0] = bye
    skipped = controller.buy_shop_card(FootballShopSection.COACH_UPGRADES, bye.card_id)
    assert skipped.shop.pending_player_upgrades == (temp.upgrade, temp.upgrade)
    assert skipped.shop.project_player_upgrade(temp.upgrade) == before.project_player_upgrade(temp.upgrade)
    assert skipped.shop.project_player_upgrade(temp.upgrade).effective_next_match.change == pytest.approx(0)
    started = controller.finish_shop()
    assert started.match.team_a.players[FootballPosition.QB].stamina == 1.0
    assert conditioning.coach_upgrade_effect in started.match.team_a_coach_upgrades
    assert started.shop.pending_player_upgrades == (temp.upgrade, temp.upgrade)
    _complete_forced_match(controller)
    assert controller.state.shop.pending_player_upgrades == ()


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
    assert state.shop.remaining_ap == 12
    assert len(state.shop.offer) == 3

    first_upgrade, second_upgrade = state.shop.offer[:2]
    controller.buy_upgrade(first_upgrade)
    controller.buy_upgrade(second_upgrade)
    assert controller.state.shop is not None
    assert (
        controller.state.shop.roster.coach_assignment
        == selected_pair.assignment
    )
    assert controller.state.shop.remaining_ap == 12 - first_upgrade.cost - second_upgrade.cost
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
    assert match_view.match.game_clock_seconds == REGULATION_PERIOD_SECONDS
    assert match_view.match.match_events
    assert isinstance(match_view.match.match_events[0].action, DefensiveSchemeAction)
    assert match_view.shop is not None and match_view.shop.finished


def test_controller_carries_bought_named_play_and_scheme_into_match_decks() -> None:
    play = OFFENSIVE_PLAY_CATALOG["slot_slant"]
    scheme = DEFENSIVE_SCHEME_CATALOG["quarters_coverage"]
    cards = (
        FootballShopCard(
            card_id=f"play:{play.card_id}",
            name=play.name,
            description=play.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.COMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            football_card=play,
        ),
        FootballShopCard(
            card_id=f"scheme:{scheme.card_id}",
            name=scheme.name,
            description=scheme.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.COMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            football_card=scheme,
        ),
    )
    controller = FootballGameController(
        "Human Team",
        difficulty=FootballAIDifficulty.EASY,
        builder_seed=17,
        shop_seed=29,
        ai_seed=41,
        match_seed=53,
        shop_catalogs={FootballShopSection.PLAYS_SCHEMES: cards},
    )
    _draft_to_shop(controller)

    for card in cards:
        controller.buy_shop_card(FootballShopSection.PLAYS_SCHEMES, card.card_id)
    shop = controller.state.shop
    assert shop is not None
    purchased_play = next(card for card in shop.offensive_deck if card.card_id == play.card_id)
    purchased_scheme = next(
        card for card in shop.defensive_deck if card.card_id == scheme.card_id
    )

    match = controller.finish_shop().match
    assert match is not None
    assert match.team_a_offense_deck is not None
    assert match.team_a_defense_deck is not None
    assert purchased_play in match.team_a_offense_deck.owned
    assert purchased_scheme in match.team_a_defense_deck.owned
    assert purchased_play in (
        match.team_a_offense_deck.hand
        + match.team_a_offense_deck.draw_pile
        + match.team_a_offense_deck.discard_pile
    )
    assert purchased_scheme in (
        match.team_a_defense_deck.hand
        + match.team_a_defense_deck.draw_pile
        + match.team_a_defense_deck.discard_pile
    )


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
            hand = state.match.team_a_offense_deck
            assert hand is not None and hand.hand
            controller.choose_offensive_play(hand.hand[0].copy_id)
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            hand = state.match.team_a_defense_deck
            assert hand is not None and hand.hand
            selected = hand.hand[0]
            expected_scheme = DEFENSIVE_SCHEME_CATALOG[selected.card_id].action
            prior_event_count = len(state.match.match_events)
            controller.choose_defensive_scheme(selected.copy_id)
            updated = controller.state.match
            assert updated is not None
            first_new_event = updated.match_events[prior_event_count]
            assert first_new_event.action is expected_scheme
            assert first_new_event.possession is FootballTeamSide.TEAM_B
            human_defensive_drives += 1
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            assert state.match.down == 4
            controller.choose_fourth_down(FootballFourthDownAction.PUNT)
            human_fourth_downs += 1
        elif state.human_decision is FootballHumanDecision.CONVERSION:
            controller.choose_conversion(FootballConversionAction.EXTRA_POINT)
        elif state.human_decision is FootballHumanDecision.GREEN_DOG:
            controller.respond_to_green_dog(None)
        else:
            raise AssertionError(f"Unexpected decision: {state.human_decision}")

    else:
        pytest.fail("The simulator did not complete the seeded match.")

    final = controller.state
    assert final.phase in (
        FootballRunPhase.READY_FOR_NEXT_GAME,
        FootballRunPhase.FIRED,
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
    # Every human defensive drive starts with exactly one scheme call, right after
    # the event that gave Team B the ball (a change of possession, a kick, a
    # conversion, or a period change such as halftime or overtime).
    scheme_indexes = [
        index for index, event in enumerate(events)
        if isinstance(event.action, DefensiveSchemeAction)
        and event.possession is FootballTeamSide.TEAM_B
    ]
    for index in scheme_indexes:
        if index == 0:
            continue
        transition = events[index - 1]
        assert transition.possession is FootballTeamSide.TEAM_B
        if isinstance(transition.action, OffensivePlayAction):
            assert transition.play_result is not None
            period_changed = index >= 2 and events[index - 2].period != transition.period
            assert transition.play_result.possession_changed or period_changed
        elif isinstance(transition.action, FootballAutomaticAction):
            assert transition.action is FootballAutomaticAction.KICKOFF
        else:
            assert isinstance(
                transition.action, (FootballFourthDownAction, FootballConversionAction)
            )
    human_defense_drive_count = len(scheme_indexes)
    assert human_defense_drive_count == human_defensive_drives


def test_human_go_for_it_transitions_to_a_legal_offensive_card() -> None:
    controller = _controller()
    _start_match(controller)
    simulator = controller._simulator
    assert simulator is not None
    simulator.state = replace(
        simulator.state,
        down=4,
        yards_to_go=1.0,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )
    assert controller.state.human_decision is FootballHumanDecision.FOURTH_DOWN
    before_events = len(simulator.state.match_events)
    controller.choose_fourth_down(FootballFourthDownAction.GO_FOR_IT)

    pending = controller.state
    assert pending.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert pending.match is not None
    assert pending.match.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert pending.match.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert pending.match.match_events[before_events].action is (
        FootballFourthDownAction.GO_FOR_IT
    )
    hand = pending.match.team_a_offense_deck
    assert hand is not None and hand.hand
    card = hand.hand[0]
    controller.choose_offensive_play(card.copy_id)

    resolved = controller.state.match
    assert resolved is not None
    play_event = next(
        event
        for event in resolved.match_events[before_events + 1 :]
        if isinstance(event.action, OffensivePlayAction)
    )
    assert play_event.action is OFFENSIVE_PLAY_CATALOG[card.card_id].action
    assert play_event.play_result is not None
    assert play_event.play_result.defensive_scheme is DefensiveSchemeAction.RB_RUN
    event_possession = play_event.possession
    if play_event.play_result.possession_changed:
        event_possession = (
            FootballTeamSide.TEAM_B
            if event_possession is FootballTeamSide.TEAM_A
            else FootballTeamSide.TEAM_A
        )
    assert event_possession is FootballTeamSide.TEAM_A


def test_invalid_and_out_of_turn_actions_preserve_state_and_all_random_streams() -> None:
    controller = _controller()
    initial = controller.state
    builder_rng = controller._builder._rng.getstate()
    with pytest.raises(ValueError, match="phase"):
        controller.enter_next_shop()
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
    assert controller.state.shop.remaining_ap == 12 - shop.offer[0].cost
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
        controller.enter_next_shop()


def _win_regular_season(monkeypatch, controller, *, lose_games: tuple[int, ...] = ()) -> None:
    _start_match(controller)
    for game_number in range(1, 11):
        winner = FootballTeamSide.TEAM_B if game_number in lose_games else FootballTeamSide.TEAM_A
        _force_match_result(monkeypatch, controller, winner)
        _complete_forced_match(controller)
        if game_number < 10:
            _enter_next_match(controller)


def test_surviving_game_ten_seeds_the_bracket_and_the_title_ends_the_run(monkeypatch) -> None:
    controller = _controller()
    _win_regular_season(monkeypatch, controller)
    state = controller.state
    assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    assert state.human_decision is FootballHumanDecision.OPEN_NEXT_SHOP
    assert state.playoff_round is None
    bracket = state.playoffs
    assert bracket is not None and bracket.human_seed == 1
    assert bracket.team(1).name == "Human Team" and bracket.team(1).is_human
    assert len({team.name for team in bracket.teams}) == 8
    assert [(game.high_seed, game.low_seed) for game in bracket.games] == [
        (1, 8), (4, 5), (3, 6), (2, 7),
    ]

    for game_number, playoff_round in zip((11, 12, 13), FootballPlayoffRound):
        state = controller.enter_next_shop()
        assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
        assert state.game_number == game_number and state.playoff_round is playoff_round
        rival = bracket_rival(state)
        assert state.opponent_name == rival
        controller.finish_shop()
        assert controller.state.match.team_b.team_name == rival
        _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
        _complete_forced_match(controller)
        state = controller.state
        assert (state.wins, state.losses, state.games_played) == (10, 0, 10)
        assert len(state.season_history) == 10
        game = state.playoffs.human_game(playoff_round)
        assert game.winner_seed == 1 and game.score_for(1) == 7
        # Every other game in the round is decided with the human's.
        assert all(other.decided for other in state.playoffs.round_games(playoff_round))
        if playoff_round is not FootballPlayoffRound.CHAMPIONSHIP:
            assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
            assert state.human_decision is FootballHumanDecision.OPEN_NEXT_SHOP

    assert state.phase is FootballRunPhase.CHAMPION
    assert state.human_decision is None
    assert state.playoffs.champion_seed == 1
    with pytest.raises(ValueError, match="phase"):
        controller.enter_next_shop()


def bracket_rival(state) -> str:
    game = state.playoffs.human_game(state.playoff_round)
    return state.playoffs.team(game.opponent_of(state.playoffs.human_seed)).name


def test_a_playoff_loss_eliminates_and_regular_season_losses_set_the_seed(monkeypatch) -> None:
    controller = _controller()
    _win_regular_season(monkeypatch, controller, lose_games=(2, 5))
    state = controller.state
    assert (state.wins, state.losses) == (8, 2)
    assert state.playoffs.human_seed == 3
    assert state.playoffs.human_game(FootballPlayoffRound.QUARTERFINAL).opponent_of(3) == 6
    controller.enter_next_shop()
    controller.finish_shop()
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_B)
    _complete_forced_match(controller)
    state = controller.state
    assert state.phase is FootballRunPhase.ELIMINATED
    assert state.human_decision is None
    assert state.losses == 2  # playoff results live in the bracket
    assert state.playoffs.human_eliminated
    with pytest.raises(ValueError, match="phase"):
        controller.enter_next_shop()


def test_playoff_rivals_get_tougher_each_round(monkeypatch) -> None:
    from src.engine.football_ai import FootballAI

    calls = []
    roster = FootballAI.generate_opponent_roster
    decks = FootballAI.generate_opponent_decks

    def spy_roster(self, **kwargs):
        calls.append(("roster", kwargs.get("power_bonus", 0.0)))
        return roster(self, **kwargs)

    def spy_decks(self, game_number, opponent, **kwargs):
        offense, defense = decks(self, game_number, opponent, **kwargs)
        calls.append(("decks", len(offense)))
        return offense, defense

    monkeypatch.setattr(FootballAI, "generate_opponent_roster", spy_roster)
    monkeypatch.setattr(FootballAI, "generate_opponent_decks", spy_decks)
    controller = _controller(difficulty=FootballAIDifficulty.STANDARD)
    _win_regular_season(monkeypatch, controller)
    for _round in FootballPlayoffRound:
        controller.enter_next_shop()
        controller.finish_shop()
        _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
        _complete_forced_match(controller)
    powers = [value for kind, value in calls if kind == "roster"]
    sizes = [value for kind, value in calls if kind == "decks"]
    assert powers[:10] == [0.0] * 10 and powers[10:] == [0.25, 0.5, 0.75]
    # Standard caps regular-season extras at 3; each round adds one more.
    assert sizes[9] == 6 + 3 and sizes[10:] == [6 + 4, 6 + 5, 6 + 6]
    final = controller.state.match.team_b
    assert all(player.power == 50.75 for player in final.players.values())


def test_next_shop_resets_ap_and_preserves_upgrades_roster_and_slot_unlocks(
    monkeypatch,
) -> None:
    controller = _controller()
    _draft_to_shop(controller)
    first_shop = controller.state.shop
    assert first_shop is not None
    card = next(card for card in _player_upgrade_catalog()
                if card.upgrade.stat is FootballUpgradeStat.POWER
                and card.upgrade.duration is FootballUpgradeDuration.PERMANENT)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    upgrade = card.upgrade
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
            coach_upgrade_effect=FootballCoachUpgradeEffect(
                f"coach-test-{index}",
                FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
                0.05,
            ),
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


def _bye_controller() -> tuple[FootballGameController, FootballShopCard]:
    bye = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "bye_week")
    controller = FootballGameController(
        "Human Team", difficulty=FootballAIDifficulty.EASY,
        builder_seed=17, shop_seed=29, ai_seed=41, match_seed=53,
        shop_catalogs={FootballShopSection.COACH_UPGRADES: (bye,)},
    )
    return controller, bye


def _buy_bye(controller: FootballGameController, bye: FootballShopCard):
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    return controller.buy_shop_card(FootballShopSection.COACH_UPGRADES, bye.card_id)


def test_season_history_records_each_played_result_and_ends_at_three_losses(monkeypatch) -> None:
    controller = _controller()
    assert controller.state.season_history == ()
    _start_match(controller)
    winners = (FootballTeamSide.TEAM_B, FootballTeamSide.TEAM_A,
               FootballTeamSide.TEAM_B, FootballTeamSide.TEAM_B)
    for index, winner in enumerate(winners):
        _force_match_result(monkeypatch, controller, winner)
        _complete_forced_match(controller)
        if index < len(winners) - 1:
            _enter_next_match(controller)
    state = controller.state
    assert state.phase is FootballRunPhase.FIRED
    assert state.season_history == (
        FootballSeasonGame(1, FootballSeasonOutcome.LOSS, 0, 7),
        FootballSeasonGame(2, FootballSeasonOutcome.WIN, 7, 0),
        FootballSeasonGame(3, FootballSeasonOutcome.LOSS, 0, 7),
        FootballSeasonGame(4, FootballSeasonOutcome.LOSS, 0, 7),
    )
    assert (state.wins, state.losses, state.games_played) == (1, 3, 4)
    with pytest.raises(FrozenInstanceError):
        state.season_history[0].team_score = 3  # type: ignore[misc]


def test_season_history_marks_bye_week_skip_without_a_score(monkeypatch) -> None:
    controller, bye = _bye_controller()
    _draft_to_shop(controller)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    for _game in range(1, 4):
        controller.finish_shop()
        _complete_forced_match(controller)
        controller.enter_next_shop()
    skipped = _buy_bye(controller, bye)
    assert skipped.skipped_games == (4,)
    assert skipped.season_history[-1] == FootballSeasonGame(4, FootballSeasonOutcome.BYE)
    assert skipped.season_history[-1].team_score is None
    assert (skipped.wins, skipped.losses) == (3, 0)
    controller.finish_shop()
    _complete_forced_match(controller)
    assert [game.game_number for game in controller.state.season_history] == [1, 2, 3, 4, 5]
    assert controller.state.season_history[-1].outcome is FootballSeasonOutcome.WIN


def test_season_history_marks_game_ten_bye_and_reaches_playoffs(monkeypatch) -> None:
    controller, bye = _bye_controller()
    _draft_to_shop(controller)
    _force_match_result(monkeypatch, controller, FootballTeamSide.TEAM_A)
    for _game in range(1, 10):
        controller.finish_shop()
        _complete_forced_match(controller)
        controller.enter_next_shop()
    state = _buy_bye(controller, bye)
    assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    assert state.playoffs is not None and state.playoffs.human_seed == 1
    assert state.human_decision is FootballHumanDecision.OPEN_NEXT_SHOP
    assert len(state.season_history) == 10
    assert state.season_history[-1] == FootballSeasonGame(10, FootballSeasonOutcome.BYE)
    assert (state.wins, state.losses, state.games_played) == (9, 0, 9)


def test_season_history_flags_overtime_results(monkeypatch) -> None:
    from src.engine.football_simulator import FootballMatchSimulator

    def finish(simulator, _play):
        simulator.state = replace(
            simulator.state, team_a_score=23, team_b_score=20, period=3, game_clock_seconds=120,
            status=FootballMatchStatus.COMPLETED, awaited_action=None,
            current_drive_defensive_scheme=None,
            final_result=FootballMatchResult(23, 20, FootballTeamSide.TEAM_A, True),
        )
        return simulator.state

    controller = _controller()
    _start_match(controller)
    monkeypatch.setattr(FootballMatchSimulator, "resolve_offensive_play", finish)
    _complete_forced_match(controller)
    assert controller.state.season_history == (
        FootballSeasonGame(1, FootballSeasonOutcome.WIN, 23, 20, overtime=True),
    )
