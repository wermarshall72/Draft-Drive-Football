import pytest

from src.engine.football import (
    FootballCoach,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
)
from src.engine.football_team_builder import (
    PLAYER_DRAFT_ORDER,
    FootballPlayerCandidate,
    FootballTeamBuilder,
)


def _draft(
    seed: int,
) -> tuple[FootballTeamBuilder, tuple[tuple[FootballPlayerCandidate, ...], ...]]:
    builder = FootballTeamBuilder("Draft Team", seed)
    builder.choose_coach(0)
    offers = []
    for position in PLAYER_DRAFT_ORDER:
        offers.append(builder.current_offer)
        builder.choose_player(position, 0)
    return builder, tuple(offers)


def test_draft_order_offers_three_valid_distinct_players_per_position() -> None:
    builder = FootballTeamBuilder("Draft Team", 4)

    assert builder.required_position is None
    assert builder.current_offer == builder.coach_offer
    builder.choose_coach(builder.current_offer[1])

    for position in PLAYER_DRAFT_ORDER:
        assert builder.required_position is position
        offer = builder.current_offer
        assert len(offer) == 3
        assert len(set(offer)) == 3
        assert all(isinstance(candidate, FootballPlayerCandidate) for candidate in offer)
        assert all(candidate.position is position for candidate in offer)
        assert all(candidate.description for candidate in offer)
        assert all(candidate.player.power >= 0 for candidate in offer)
        assert all(0 <= candidate.player.volatility <= 1 for candidate in offer)
        assert all(0 <= candidate.player.stamina <= 1 for candidate in offer)
        builder.choose_player(position, offer[0])

    roster = builder.build_roster()
    assert builder.completed
    assert builder.required_position is None
    assert builder.current_offer == ()
    assert set(roster.players) == set(PLAYER_DRAFT_ORDER)
    assert roster.coach is builder.selected_coach
    assert isinstance(roster.special_teams, FootballSpecialTeams)
    assert len(roster.players) == 8
    assert roster.coach not in roster.players.values()
    assert roster.special_teams not in roster.players.values()
    assert isinstance(roster, FootballRoster)


def test_equal_seeds_reproduce_offers_roster_and_different_seeds_vary_offers() -> None:
    first, first_offers = _draft(41)
    replay, replay_offers = _draft(41)
    other_seed, other_offers = _draft(42)

    assert first_offers == replay_offers
    assert first.build_roster() == replay.build_roster()
    assert first_offers != other_offers


def test_invalid_actions_preserve_state_and_random_stream() -> None:
    builder = FootballTeamBuilder("Draft Team", 71)
    state = builder.state
    rng_state = builder._rng.getstate()

    with pytest.raises(ValueError, match="Choose a coach"):
        builder.choose_player(FootballPosition.QB, 0)
    with pytest.raises(ValueError, match="valid offer index"):
        builder.choose_coach(True)
    with pytest.raises(ValueError, match="out of range"):
        builder.choose_coach(3)

    assert builder.state == state
    assert builder._rng.getstate() == rng_state

    builder.choose_coach(0)
    state = builder.state
    rng_state = builder._rng.getstate()
    qb_offer = builder.current_offer
    unoffered = FootballPlayerCandidate(
        FootballPlayer("Unoffered QB", FootballPosition.QB, 10, 0.2, 0.8),
        "A valid player not in this offer.",
    )
    with pytest.raises(ValueError, match="next required position"):
        builder.choose_player(FootballPosition.RB, 0)
    with pytest.raises(ValueError, match="FootballPosition"):
        builder.choose_player("QB", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="valid offer index"):
        builder.choose_player(FootballPosition.QB, True)
    with pytest.raises(ValueError, match="out of range"):
        builder.choose_player(FootballPosition.QB, 3)
    with pytest.raises(ValueError, match="not included"):
        builder.choose_player(FootballPosition.QB, unoffered)
    with pytest.raises(ValueError, match="offered item"):
        builder.choose_player(FootballPosition.QB, FootballCoach("Other Coach"))  # type: ignore[arg-type]

    assert builder.state == state
    assert builder.current_offer == qb_offer
    assert builder._rng.getstate() == rng_state


def test_completion_rejects_more_draft_actions_without_mutation() -> None:
    builder, _ = _draft(88)
    state = builder.state
    roster = builder.build_roster()
    rng_state = builder._rng.getstate()

    with pytest.raises(ValueError, match="already complete"):
        builder.choose_player(FootballPosition.SAFETIES, 0)
    with pytest.raises(ValueError, match="already complete"):
        builder.choose_coach(0)

    assert builder.state == state
    assert builder.build_roster() is roster
    assert builder._rng.getstate() == rng_state


def test_building_before_all_positions_are_selected_fails() -> None:
    builder = FootballTeamBuilder("Draft Team", 2)

    with pytest.raises(ValueError, match="not complete"):
        builder.build_roster()
