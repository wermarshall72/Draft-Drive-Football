import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardFamily,
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
from src.engine import football_ai as football_ai_module
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    STARTING_DEFENSIVE_ACTIONS,
    STARTING_OFFENSIVE_ACTIONS,
)
from src.engine.football_ai import (
    EASY_POWER_ADJUSTMENT,
    FootballAI,
    FootballAIDifficulty,
    HARD_POWER_ADJUSTMENT,
    STANDARD_POWER_ADJUSTMENT,
)
from src.engine.football_player_catalog import (
    PLAYER_BASE_POWER,
    PLAYER_BASE_STAMINA,
    PLAYER_BASE_VOLATILITY,
    player_type_for_id,
)
from src.engine.football_simulator import FootballMatchSimulator


def _roster(
    team_name: str,
    *,
    default_power: float = 10.0,
    powers: dict[FootballPosition, float] | None = None,
) -> FootballRoster:
    power_by_position = powers or {}
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=power_by_position.get(position, default_power),
            volatility=0.2,
            stamina=0.75,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=team_name,
        players=players,
        coach=FootballCoach(f"{team_name} Coach"),
        special_teams=FootballSpecialTeams(f"{team_name} Special Teams"),
    )


def _state(**overrides: object) -> FootballMatchState:
    offense_a = tuple(
        FootballCardCopy(f"test:a:offense:{card_id}", card_id)
        for card_id in OFFENSIVE_PLAY_CATALOG
    )
    offense_b = tuple(
        FootballCardCopy(f"test:b:offense:{card_id}", card_id)
        for card_id in OFFENSIVE_PLAY_CATALOG
    )
    defense_a = tuple(
        FootballCardCopy(f"test:a:defense:{card_id}", card_id)
        for card_id in DEFENSIVE_SCHEME_CATALOG
    )
    defense_b = tuple(
        FootballCardCopy(f"test:b:defense:{card_id}", card_id)
        for card_id in DEFENSIVE_SCHEME_CATALOG
    )
    values: dict[str, object] = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
        "random_seed": 1234,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 25.0,
        "game_clock_seconds": 900,
        "period": 1,
        "team_a_offense_deck": FootballDeckState(offense_a, hand=offense_a),
        "team_a_defense_deck": FootballDeckState(defense_a, hand=defense_a),
        "team_b_offense_deck": FootballDeckState(offense_b, hand=offense_b),
        "team_b_defense_deck": FootballDeckState(defense_b, hand=defense_b),
    }
    values.update(overrides)
    if values.get("awaited_action") in (
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    ):
        values.setdefault(
            "current_drive_defensive_scheme", DefensiveSchemeAction.DEEP_PASS
        )
    return FootballMatchState(**values)  # type: ignore[arg-type]


def _ai(
    difficulty: FootballAIDifficulty,
    *,
    side: FootballTeamSide = FootballTeamSide.TEAM_A,
    seed: int = 17,
) -> FootballAI:
    return FootballAI(side, difficulty, seed, "Local Opponent")


@pytest.mark.parametrize(
    "difficulty",
    list(FootballAIDifficulty),
)
def test_generated_roster_is_complete_valid_and_keeps_non_player_slots_separate(
    difficulty: FootballAIDifficulty,
) -> None:
    roster = _ai(difficulty).generate_opponent_roster()

    assert set(roster.players) == set(FootballPosition)
    assert len(roster.players) == 8
    expected_power = PLAYER_BASE_POWER + {
        FootballAIDifficulty.EASY: -0.5,
        FootballAIDifficulty.STANDARD: 0.0,
        FootballAIDifficulty.HARD: 0.5,
    }[difficulty]
    for position, player in roster.players.items():
        assert player.position is position
        assert player.power == expected_power
        assert player.volatility == PLAYER_BASE_VOLATILITY
        assert player.stamina == PLAYER_BASE_STAMINA
        assert player.player_type_id is not None
        assert player_type_for_id(player.player_type_id).position is position
    assert isinstance(roster.coach, FootballCoach)
    assert isinstance(roster.special_teams, FootballSpecialTeams)
    assert roster.coach not in roster.players.values()
    assert roster.special_teams not in roster.players.values()


def test_roster_generation_is_reproducible_and_seeded_differently() -> None:
    first = _ai(FootballAIDifficulty.STANDARD, seed=121).generate_opponent_roster()
    replay = _ai(FootballAIDifficulty.STANDARD, seed=121).generate_opponent_roster()
    other_seed = _ai(FootballAIDifficulty.STANDARD, seed=122).generate_opponent_roster()

    assert first == replay
    assert first != other_seed


def test_difficulty_applies_only_the_documented_small_power_adjustment() -> None:
    assert EASY_POWER_ADJUSTMENT == -0.5
    assert STANDARD_POWER_ADJUSTMENT == 0.0
    assert HARD_POWER_ADJUSTMENT == 0.5
    rosters = {
        difficulty: _ai(difficulty, seed=7).generate_opponent_roster()
        for difficulty in FootballAIDifficulty
    }
    position = FootballPosition.QB

    assert (
        rosters[FootballAIDifficulty.HARD].players[position].power
        - rosters[FootballAIDifficulty.STANDARD].players[position].power
        == pytest.approx(HARD_POWER_ADJUSTMENT)
    )


@pytest.mark.parametrize(
    ("difficulty", "awaited_action", "possession", "down", "expected_types"),
    [
        (
            difficulty,
            FootballAwaitedAction.DEFENSIVE_SCHEME,
            FootballTeamSide.TEAM_B,
            1,
            DefensiveSchemeAction,
        )
        for difficulty in FootballAIDifficulty
    ]
    + [
        (
            difficulty,
            FootballAwaitedAction.OFFENSIVE_PLAY,
            FootballTeamSide.TEAM_A,
            2,
            OffensivePlayAction,
        )
        for difficulty in FootballAIDifficulty
    ]
    + [
        (
            difficulty,
            FootballAwaitedAction.FOURTH_DOWN_DECISION,
            FootballTeamSide.TEAM_A,
            4,
            FootballFourthDownAction,
        )
        for difficulty in FootballAIDifficulty
    ],
)
def test_each_difficulty_selects_only_supported_action_for_awaited_state(
    difficulty: FootballAIDifficulty,
    awaited_action: FootballAwaitedAction,
    possession: FootballTeamSide,
    down: int,
    expected_types: type,
) -> None:
    state = _state(
        awaited_action=awaited_action,
        possession=possession,
        down=down,
    )

    action = _ai(difficulty).choose_action(state)

    assert isinstance(action, expected_types)
    if isinstance(action, OffensivePlayAction):
        assert action in tuple(OffensivePlayAction)
    elif isinstance(action, DefensiveSchemeAction):
        assert action in tuple(DefensiveSchemeAction)
    else:
        assert action in tuple(FootballFourthDownAction)


@pytest.mark.parametrize(
    ("awaited_action", "possession", "down"),
    [
        (FootballAwaitedAction.DEFENSIVE_SCHEME, FootballTeamSide.TEAM_A, 1),
        (FootballAwaitedAction.OFFENSIVE_PLAY, FootballTeamSide.TEAM_B, 2),
        (FootballAwaitedAction.FOURTH_DOWN_DECISION, FootballTeamSide.TEAM_B, 4),
    ],
)
def test_ai_rejects_actions_when_it_does_not_own_the_turn(
    awaited_action: FootballAwaitedAction,
    possession: FootballTeamSide,
    down: int,
) -> None:
    state = _state(
        awaited_action=awaited_action,
        possession=possession,
        down=down,
    )

    with pytest.raises(ValueError, match="AI cannot"):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_ai_rejects_missing_awaited_action() -> None:
    state = _state(
        awaited_action=None,
        possession=FootballTeamSide.TEAM_A,
        down=1,
    )

    with pytest.raises(ValueError):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_ai_choices_do_not_mutate_match_state_events_or_simulator_rng() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        match_events=(),
    )
    simulator = FootballMatchSimulator(state)
    before_rng = simulator.rng.getstate()
    before_events = state.match_events

    action = _ai(FootballAIDifficulty.EASY).choose_action(state)

    assert isinstance(action, OffensivePlayAction)
    assert simulator.state is state
    assert simulator.state.match_events is before_events
    assert simulator.rng.getstate() == before_rng


def test_easy_decision_stream_replays_from_the_same_ai_seed() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
    )
    first = _ai(FootballAIDifficulty.EASY, seed=918)
    replay = _ai(FootballAIDifficulty.EASY, seed=918)

    assert [first.choose_action(state) for _ in range(12)] == [
        replay.choose_action(state) for _ in range(12)
    ]
    assert first._rng.getstate() == replay._rng.getstate()


def test_standard_fourth_down_policy_distinguishes_long_and_short_yardage() -> None:
    ai = _ai(FootballAIDifficulty.STANDARD)
    long_distance = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=9.0,
        offense_field_position=25.0,
    )
    short_yardage = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=1.0,
        offense_field_position=25.0,
    )

    assert ai.choose_action(long_distance) is FootballFourthDownAction.PUNT
    assert ai.choose_action(short_yardage) is FootballFourthDownAction.GO_FOR_IT


def test_easy_fourth_down_choices_exclude_out_of_range_field_goals() -> None:
    ai = _ai(FootballAIDifficulty.EASY)
    state = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=4.0,
        offense_field_position=25.0,
    )

    assert {
        ai.choose_action(state) for _ in range(20)
    } <= {FootballFourthDownAction.GO_FOR_IT, FootballFourthDownAction.PUNT}


def test_ai_go_for_it_then_selects_a_legal_card_from_its_own_hand() -> None:
    ai = _ai(FootballAIDifficulty.STANDARD, side=FootballTeamSide.TEAM_B)
    ai_card = FootballCardCopy("ai:fourth:jet", OffensivePlayAction.JET_SWEEP.value)
    hidden_card = FootballCardCopy(
        "human:hidden:deep", OffensivePlayAction.DEEP_PASS.value
    )
    state = _state(
        possession=FootballTeamSide.TEAM_B,
        down=4,
        yards_to_go=1.0,
        offense_field_position=75.0,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_offense_deck=FootballDeckState(
            (hidden_card,), hand=(hidden_card,)
        ),
        team_b_offense_deck=FootballDeckState((ai_card,), hand=(ai_card,)),
    )
    simulator = FootballMatchSimulator(state)
    assert ai.choose_action(state) is FootballFourthDownAction.GO_FOR_IT

    pending = simulator.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    assert pending.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    selected = ai.choose_action(pending)
    assert selected is OffensivePlayAction.JET_SWEEP
    resolved = simulator.resolve_offensive_play(selected)
    assert resolved.match_events[-1].action is OffensivePlayAction.JET_SWEEP
    assert resolved.match_events[-1].possession is FootballTeamSide.TEAM_B


def test_ai_rejects_an_expired_period_clock() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        game_clock_seconds=0,
    )

    with pytest.raises(ValueError, match="clock"):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_hard_offense_uses_the_simulator_matchup_strengths() -> None:
    strong_matchup = {
        FootballPosition.QB: 10.0,
        FootballPosition.RB: 10.0,
        FootballPosition.WR: 20.0,
        FootballPosition.O_LINE: 10.0,
        FootballPosition.D_LINE: 10.0,
        FootballPosition.LINEBACKERS: 10.0,
        FootballPosition.CORNERBACKS: 10.0,
        FootballPosition.SAFETIES: 10.0,
    }
    state = _state(
        team_a=_roster("Home", powers=strong_matchup),
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        down=3,
        yards_to_go=8.0,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )

    selected = _ai(FootballAIDifficulty.HARD).choose_action(state)
    assert OFFENSIVE_PLAY_CATALOG[selected.value].family is FootballCardFamily.DEEP_PASS


def test_hard_ai_scores_exact_hand_variants_and_uses_clock_tempo() -> None:
    ai = _ai(FootballAIDifficulty.HARD)
    quick_out = FootballCardCopy("ai:tempo:quick", OffensivePlayAction.QUICK_OUT.value)
    slot_slant = FootballCardCopy("ai:tempo:slant", OffensivePlayAction.SLOT_SLANT.value)
    deck = FootballDeckState(
        owned=(quick_out, slot_slant),
        hand=(quick_out, slot_slant),
    )
    base = _state(
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_offense_deck=deck,
        game_clock_seconds=900,
        period=1,
        team_a_score=0,
        team_b_score=0,
    )
    late_lead = _state(
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_offense_deck=deck,
        game_clock_seconds=100,
        period=2,
        team_a_score=7,
        team_b_score=0,
    )

    quick_score = ai._hard_play_score(base, OffensivePlayAction.QUICK_OUT)
    slant_score = ai._hard_play_score(base, OffensivePlayAction.SLOT_SLANT)
    assert quick_score != slant_score
    selected = ai.choose_action(late_lead)
    assert selected in (OffensivePlayAction.QUICK_OUT, OffensivePlayAction.SLOT_SLANT)
    expected = max(
        (OffensivePlayAction.QUICK_OUT, OffensivePlayAction.SLOT_SLANT),
        key=lambda play: ai._hard_play_score(late_lead, play),
    )
    assert selected is expected
    for play in (OffensivePlayAction.QUICK_OUT, OffensivePlayAction.SLOT_SLANT):
        tempo_delta = (
            ai._hard_play_score(late_lead, play)
            - ai._hard_play_score(base, play)
        )
        assert tempo_delta == pytest.approx(
            0.03 * OFFENSIVE_PLAY_CATALOG[play.value].clock_seconds
        )


def test_hard_offense_uses_active_scheme_and_selects_only_legal_hand_cards() -> None:
    ai = _ai(FootballAIDifficulty.HARD)
    offense = _roster(
        "Home",
        powers={
            FootballPosition.RB: 80.0,
            FootballPosition.O_LINE: 80.0,
            FootballPosition.QB: 10.0,
            FootballPosition.WR: 10.0,
        },
    )
    defense = _roster(
        "Away",
        powers={
            FootballPosition.D_LINE: 1.0,
            FootballPosition.LINEBACKERS: 1.0,
            FootballPosition.CORNERBACKS: 50.0,
            FootballPosition.SAFETIES: 50.0,
        },
    )
    rb_card = FootballCardCopy("ai:legal:run", OffensivePlayAction.RB_RUN.value)
    pass_card = FootballCardCopy("ai:legal:pass", OffensivePlayAction.DEEP_PASS.value)
    hidden_card = FootballCardCopy(
        "human:hidden", OffensivePlayAction.SHORT_PASS.value
    )
    run_scheme_state = _state(
        team_a=offense,
        team_b=defense,
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        down=3,
        yards_to_go=8.0,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_offense_deck=FootballDeckState(
            (rb_card, pass_card), hand=(rb_card, pass_card)
        ),
        team_b_offense_deck=FootballDeckState((hidden_card,), hand=(hidden_card,)),
    )
    pass_scheme_state = _state(
        team_a=offense,
        team_b=defense,
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        down=3,
        yards_to_go=8.0,
        current_drive_defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
        team_a_offense_deck=FootballDeckState(
            (rb_card, pass_card), hand=(rb_card, pass_card)
        ),
        team_b_offense_deck=FootballDeckState((hidden_card,), hand=(hidden_card,)),
    )

    run_scheme_score = ai._hard_play_score(run_scheme_state, OffensivePlayAction.RB_RUN)
    pass_scheme_score = ai._hard_play_score(pass_scheme_state, OffensivePlayAction.RB_RUN)
    assert pass_scheme_score != run_scheme_score
    chosen = ai.choose_action(pass_scheme_state)
    assert chosen in (OffensivePlayAction.RB_RUN, OffensivePlayAction.DEEP_PASS)
    assert chosen is not OffensivePlayAction.SHORT_PASS


def test_hard_defensive_score_prefers_schemes_with_stronger_contributors(
    monkeypatch,
) -> None:
    ai = _ai(FootballAIDifficulty.HARD, side=FootballTeamSide.TEAM_B)
    state = _state(
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        down=1,
        yards_to_go=5.0,
    )
    offense = _roster("Offense", default_power=10.0)
    defense = _roster(
        "Defense",
        powers={
            FootballPosition.D_LINE: 100.0,
            FootballPosition.LINEBACKERS: 100.0,
            FootballPosition.CORNERBACKS: 1.0,
            FootballPosition.SAFETIES: 1.0,
        },
    )
    monkeypatch.setattr(
        ai, "_likely_offensive_play_score", lambda _state, _scheme: 1.0
    )
    strong_defense = ai._hard_defensive_scheme_score(
        state,
        DefensiveSchemeAction.RB_RUN,
        offense,
        defense,
    )
    weak_defense = ai._hard_defensive_scheme_score(
        state,
        DefensiveSchemeAction.DEEP_PASS,
        offense,
        defense,
    )

    assert strong_defense > weak_defense


def test_hard_defense_breaks_tied_variant_scores_deterministically(
    monkeypatch,
) -> None:
    ai = _ai(FootballAIDifficulty.HARD, side=FootballTeamSide.TEAM_B)
    state = _state(
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        down=1,
        yards_to_go=5.0,
    )
    offense = _roster("Offense")
    defense = _roster("Defense")
    selected_plays: list[OffensivePlayAction] = []
    calculate_estimate = football_ai_module.calculate_match_play_estimate

    def record_estimate(state, play, **kwargs):
        selected_plays.append(play)
        return calculate_estimate(state, play, **kwargs)

    monkeypatch.setattr(
        ai,
        "_situational_play_score",
        lambda _state, _play: 1.0,
    )
    monkeypatch.setattr(
        football_ai_module,
        "calculate_match_play_estimate",
        record_estimate,
    )

    ai._hard_defensive_scheme_score(
        state,
        DefensiveSchemeAction.DEEP_PASS,
        offense,
        defense,
    )

    expected_play = max(
        DEFENSIVE_SCHEME_CATALOG["deep_pass"].counters,
        key=lambda action: action.value,
    )
    assert selected_plays == [expected_play]


def test_ai_rejects_invalid_constructor_values() -> None:
    with pytest.raises(ValueError, match="team side"):
        FootballAI("team_a", FootballAIDifficulty.STANDARD, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="difficulty"):
        FootballAI(FootballTeamSide.TEAM_A, "hard", 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="seed"):
        FootballAI(FootballTeamSide.TEAM_A, FootballAIDifficulty.STANDARD, True)


def test_easy_ai_random_stream_is_independent_from_match_simulator_stream() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        possession=FootballTeamSide.TEAM_B,
    )
    simulator = FootballMatchSimulator(state)
    ai = _ai(FootballAIDifficulty.EASY, seed=44)
    match_rng = random.Random(state.random_seed)

    ai.choose_action(state)

    assert simulator.rng.getstate() == match_rng.getstate()


@pytest.mark.parametrize(
    ("difficulty", "game_number", "expected_extra"),
    [
        (FootballAIDifficulty.EASY, 1, 1),
        (FootballAIDifficulty.EASY, 10, 2),
        (FootballAIDifficulty.STANDARD, 10, 3),
        (FootballAIDifficulty.HARD, 10, 4),
    ],
)
def test_ai_decks_scale_reproducibly_without_consuming_decision_rng(
    difficulty, game_number, expected_extra
) -> None:
    first = _ai(difficulty, seed=201)
    replay = _ai(difficulty, seed=201)
    roster = first.generate_opponent_roster()
    replay_roster = replay.generate_opponent_roster()
    decision_rng = first._rng.getstate()

    offense, defense = first.generate_opponent_decks(game_number, roster)
    replay_decks = replay.generate_opponent_decks(game_number, replay_roster)

    assert len(offense) == len(STARTING_OFFENSIVE_ACTIONS) + expected_extra
    assert len(defense) == len(STARTING_DEFENSIVE_ACTIONS) + expected_extra
    assert (offense, defense) == replay_decks
    assert first._rng.getstate() == decision_rng


def test_ai_uses_only_its_hand_or_basic_fallback() -> None:
    ai = _ai(FootballAIDifficulty.STANDARD, side=FootballTeamSide.TEAM_B)
    team_b_play = FootballCardCopy("ai:hand:play", OffensivePlayAction.JET_SWEEP.value)
    team_a_play = FootballCardCopy("human:hidden:play", OffensivePlayAction.DEEP_PASS.value)
    team_b_scheme = FootballCardCopy(
        "ai:hand:scheme", DefensiveSchemeAction.COVER_TWO_SHELL.value
    )
    state = _state(
        possession=FootballTeamSide.TEAM_B,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        team_a_offense_deck=FootballDeckState((team_a_play,), hand=(team_a_play,)),
        team_b_offense_deck=FootballDeckState((team_b_play,), hand=(team_b_play,)),
        team_b_defense_deck=FootballDeckState((team_b_scheme,), hand=(team_b_scheme,)),
    )

    assert ai.choose_action(state) is OffensivePlayAction.JET_SWEEP
    empty_hand = FootballDeckState((team_b_play,), draw_pile=(team_b_play,))
    fallback_state = _state(
        possession=FootballTeamSide.TEAM_B,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        team_b_offense_deck=empty_hand,
    )
    assert ai.choose_action(fallback_state) is OffensivePlayAction.RB_RUN


@pytest.mark.parametrize("difficulty", tuple(FootballAIDifficulty))
def test_ai_two_point_card_choice_is_from_its_current_hand(
    difficulty: FootballAIDifficulty,
) -> None:
    legal = FootballCardCopy("conversion:legal", OffensivePlayAction.SHORT_PASS.value)
    deck = FootballDeckState((legal,), hand=(legal,))
    state = _state(
        possession=FootballTeamSide.TEAM_B,
        conversion_team=FootballTeamSide.TEAM_B,
        awaited_action=FootballAwaitedAction.CONVERSION,
        down=1,
        yards_to_go=2.0,
        offense_field_position=98.0,
        current_drive_defensive_scheme=DefensiveSchemeAction.GOAL_LINE_FRONT,
        team_b_offense_deck=deck,
    )
    ai = FootballAI(FootballTeamSide.TEAM_B, difficulty, 14)
    assert ai.choose_conversion_card(state) == legal.copy_id

    empty_state = _state(
        possession=FootballTeamSide.TEAM_B,
        conversion_team=FootballTeamSide.TEAM_B,
        awaited_action=FootballAwaitedAction.CONVERSION,
        down=1,
        yards_to_go=2.0,
        offense_field_position=98.0,
        current_drive_defensive_scheme=DefensiveSchemeAction.GOAL_LINE_FRONT,
        team_b_offense_deck=FootballDeckState((legal,)),
    )
    assert ai.choose_conversion_card(empty_state) is None


@pytest.mark.parametrize("difficulty", list(FootballAIDifficulty))
def test_ai_chooses_from_enlarged_hands_of_any_size(
    difficulty: FootballAIDifficulty,
) -> None:
    plays = tuple(
        FootballCardCopy(f"big:offense:{card_id}", card_id)
        for card_id in OFFENSIVE_PLAY_CATALOG
    )
    schemes = tuple(
        FootballCardCopy(f"big:defense:{card_id}", card_id)
        for card_id in DEFENSIVE_SCHEME_CATALOG
    )
    for offense_size, defense_size in ((4, 3), (7, 5)):
        offense = FootballDeckState(
            plays, draw_pile=plays[offense_size:], hand=plays[:offense_size]
        )
        defense = FootballDeckState(
            schemes, draw_pile=schemes[defense_size:], hand=schemes[:defense_size]
        )
        hand_actions = {
            OFFENSIVE_PLAY_CATALOG[card.card_id].action for card in offense.hand
        }
        scheme_actions = {
            DEFENSIVE_SCHEME_CATALOG[card.card_id].action for card in defense.hand
        }
        ai = _ai(difficulty, seed=offense_size)
        play_state = _state(
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            team_a_offense_deck=offense,
        )
        assert ai.choose_action(play_state) in hand_actions
        scheme_state = _state(
            possession=FootballTeamSide.TEAM_B,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            team_a_defense_deck=defense,
        )
        assert ai.choose_action(scheme_state) in scheme_actions
