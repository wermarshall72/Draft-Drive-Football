"""Every specialist perk: trigger, limit, exact effect, caps, partner rule, both teams."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballFourthDownAction,
    FootballConversionAction,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.engine.football_decks import OFFENSIVE_PLAY_CATALOG
from src.engine.football_perk_context import perk_history
from src.engine.football_simulator import (
    calculate_match_play_estimate,
    calculate_play_estimate,
    field_goal_success_probability,
    field_goal_success_probability_for_team,
)
from tests.perk_helpers import (
    A, B, K, ScriptedRNG, ensure_in_hand, fired, last_play, match, roster, simulator, snap, with_hand,
)

P = OffensivePlayAction
S = DefensiveSchemeAction
RUN_SECONDS = OFFENSIVE_PLAY_CATALOG["rb_run"].clock_seconds
MEDIUM_SECONDS = OFFENSIVE_PLAY_CATALOG["medium_pass"].clock_seconds


def _fatigue(sim) -> float:
    """Power left after fatigue for a stamina-0.5 player at this point of the match."""
    prior = sum(event.play_result is not None for event in sim.state.match_events)
    return 1 - min(prior / 30, 1.0) * 0.10 * 0.5


def _estimate(sim, play: str):
    return calculate_match_play_estimate(sim.state, P(play))


def _no_perk_estimate(sim, play: str):
    """The same snap with every player perk ignored."""
    state = sim.state
    offense = state.team_a if state.possession is A else state.team_b
    defense = state.team_b if state.possession is A else state.team_a
    return calculate_play_estimate(
        offense, defense, P(play), state.current_drive_defensive_scheme,
        prior_plays=sum(event.play_result is not None for event in state.match_events),
        down=state.down,
    )


# -- estimate perks: power ---------------------------------------------------------------


@pytest.mark.parametrize("offense", (A, B))
def test_motion_jump_adds_eight_wr_power_on_the_first_wr_play_of_each_drive(offense) -> None:
    sim = simulator((K.MOTION_JUMP,) if offense is A else (), (K.MOTION_JUMP,) if offense is B else (),
                    offense=offense, scheme="deep_pass")
    with_perk, without = _estimate(sim, "screen_pass"), _no_perk_estimate(sim, "screen_pass")
    # Screen: O-line + WR; the WR's partner is the RB, so no partnership bonus here.
    assert with_perk.matchup.offense - without.matchup.offense == pytest.approx(8.0)
    assert [(a.kind, a.team) for a in with_perk.player_perks] == [(K.MOTION_JUMP, offense)]
    # Runs have no WR: no bump and the use is not spent.
    assert not _estimate(sim, "rb_run").player_perks
    snap(sim, "screen_pass", yards=3)
    assert fired(sim.state, K.MOTION_JUMP, offense)
    assert not _estimate(sim, "short_pass").player_perks  # once per drive


def test_pocket_presence_starts_on_the_fifth_snap_of_a_drive() -> None:
    sim = simulator((K.POCKET_PRESENCE,), scheme="rb_run", offense_field_position=10.0)
    for _ in range(4):
        assert not _estimate(sim, "medium_pass").player_perks
        snap(sim, "medium_pass", yards=11)
    estimate = _estimate(sim, "medium_pass")
    assert [(a.kind, a.value) for a in estimate.player_perks] == [(K.POCKET_PRESENCE, 5.0)]
    # Medium: QB + O-line; the Pocket Anchor's partner is the O-line (+10%).
    assert estimate.matchup.offense - _no_perk_estimate(sim, "medium_pass").matchup.offense == pytest.approx(
        5.0 * 1.1 * _fatigue(sim), rel=1e-6
    )
    assert not _estimate(sim, "rb_run").player_perks  # no QB on a run


@pytest.mark.parametrize(("down", "to_go", "fires"), ((3, 3.0, True), (4, 1.0, True), (3, 3.5, False), (2, 1.0, False)))
def test_pull_lead_on_short_yardage_money_downs(down, to_go, fires) -> None:
    sim = simulator((K.PULL_LEAD,), scheme="deep_pass")
    sim.state = replace(sim.state, down=down, yards_to_go=to_go)
    estimate = _estimate(sim, "rb_run")
    assert bool(estimate.player_perks) is fires
    if fires:
        # Run: O-line + RB, and the Pull Guard's partner is the RB (+10%).
        assert estimate.matchup.offense - _no_perk_estimate(sim, "rb_run").matchup.offense == pytest.approx(11.0)
    assert not _estimate(sim, "deep_pass").player_perks  # no O-line on a Deep pass


def test_edge_set_wins_the_first_rival_snap_only_when_the_dline_contributes() -> None:
    sim = simulator((), (K.EDGE_SET,), scheme="rb_run")
    estimate = _estimate(sim, "rb_run")
    assert [(a.kind, a.team) for a in estimate.player_perks] == [(K.EDGE_SET, B)]
    # The rival's counter multiplier (x1.12) applies after the flat bump.
    assert estimate.matchup.defense - _no_perk_estimate(sim, "rb_run").matchup.defense == pytest.approx(
        8.0 * 1.1 * 1.12
    )
    snap(sim, "rb_run", yards=2)
    assert not _estimate(sim, "rb_run").player_perks
    deep = simulator((), (K.EDGE_SET,), scheme="deep_pass")  # Safeties + corners only
    assert not _estimate(deep, "rb_run").player_perks


def test_captains_adjustment_powers_linebackers_after_a_rival_run_first_down() -> None:
    sim = simulator((), (K.CAPTAINS_ADJUSTMENT,), scheme="short_pass")
    assert not _estimate(sim, "short_pass").player_perks
    state = snap(sim, "rb_run", yards=11)
    assert fired(state, K.CAPTAINS_ADJUSTMENT, B, applied=False)
    later = _estimate(sim, "short_pass")
    assert [(a.kind, a.applied) for a in later.player_perks] == [(K.CAPTAINS_ADJUSTMENT, True)]
    assert later.matchup.defense - _no_perk_estimate(sim, "short_pass").matchup.defense == pytest.approx(
        8.0 * 1.12 * _fatigue(sim)
    )
    snap(sim, "short_pass", yards=3)
    snap(sim, "short_pass", yards=3)
    assert len(fired(last_play(sim.state), K.CAPTAINS_ADJUSTMENT, B)) == 1  # applied, never re-triggered


@pytest.mark.parametrize(("down", "fires"), ((3, True), (2, False), (4, False)))
def test_nickel_lock_on_third_down(down, fires) -> None:
    sim = simulator((), (K.NICKEL_LOCK,), scheme="screen_pass")
    sim.state = replace(sim.state, down=down, yards_to_go=4.0)
    estimate = _estimate(sim, "deep_pass")
    assert bool(estimate.player_perks) is fires
    if fires:
        assert estimate.matchup.defense - _no_perk_estimate(sim, "deep_pass").matchup.defense == pytest.approx(8.0)


def test_downhill_fill_powers_safeties_against_runs_in_safety_schemes() -> None:
    sim = simulator((), (K.DOWNHILL_FILL,), scheme="pa_pass")
    estimate = _estimate(sim, "rb_run")
    assert estimate.matchup.defense - _no_perk_estimate(sim, "rb_run").matchup.defense == pytest.approx(11.0)
    assert not _estimate(sim, "short_pass").player_perks
    assert not _estimate(simulator((), (K.DOWNHILL_FILL,), scheme="rb_run"), "rb_run").player_perks


def test_screen_wall_debuffs_the_rival_dline_for_the_rest_of_the_drive() -> None:
    sim = simulator((K.SCREEN_WALL,), scheme="rb_run")
    assert not _estimate(sim, "rb_run").player_perks
    snap(sim, "screen_pass", yards=4)
    assert fired(sim.state, K.SCREEN_WALL, A, applied=False)
    estimate = _estimate(sim, "rb_run")
    assert [(a.kind, a.applied) for a in estimate.player_perks] == [(K.SCREEN_WALL, True)]
    assert _no_perk_estimate(sim, "rb_run").matchup.defense - estimate.matchup.defense == pytest.approx(
        8.0 * 1.12 * _fatigue(sim)
    )
    # An incomplete Screen does not trigger it.
    other = simulator((K.SCREEN_WALL,), scheme="rb_run")
    snap(other, "screen_pass", randoms=(0.0,))
    assert not fired(other.state, K.SCREEN_WALL)


# -- estimate perks: counters, yards, and odds -------------------------------------------


def test_force_and_fold_makes_screen_schemes_counter_runs() -> None:
    sim = simulator((), (K.FORCE_AND_FOLD,), scheme="screen_pass")
    estimate = _estimate(sim, "rb_run")
    plain = _no_perk_estimate(sim, "rb_run")
    assert estimate.matchup.scheme_matches_play and not plain.matchup.scheme_matches_play
    assert estimate.yards_on_success < plain.yards_on_success
    # The counter adds +0.5 pp fumble chance on top of the shifted power edge.
    assert estimate.turnover_probability > plain.turnover_probability + 0.005
    assert not _estimate(simulator((), (K.FORCE_AND_FOLD,), scheme="pa_pass"), "rb_run").player_perks


def test_silent_count_ignores_a_counter_on_money_downs_once_per_half() -> None:
    sim = simulator((K.SILENT_COUNT,), scheme="medium_pass", offense_field_position=10.0)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    estimate = _estimate(sim, "medium_pass")
    assert not estimate.matchup.scheme_matches_play
    assert [a.kind for a in estimate.player_perks] == [K.SILENT_COUNT]
    assert not _estimate(sim, "deep_pass").player_perks  # not countered
    snap(sim, "medium_pass", yards=6)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    assert _estimate(sim, "medium_pass").matchup.scheme_matches_play  # spent this half


def test_silent_count_also_cancels_a_force_and_fold_counter() -> None:
    sim = simulator((K.SILENT_COUNT,), (K.FORCE_AND_FOLD,), scheme="screen_pass")
    sim.state = replace(sim.state, down=4, yards_to_go=1.0)
    estimate = _estimate(sim, "rb_run")
    assert not estimate.matchup.scheme_matches_play
    assert [a.kind for a in estimate.player_perks] == [K.SILENT_COUNT]


def test_checkdown_adds_two_yards_to_the_next_rb_play_after_a_qb_incompletion() -> None:
    sim = simulator((K.CHECKDOWN,), scheme="rb_run")
    snap(sim, "deep_pass", randoms=(0.0,))
    estimate = _estimate(sim, "short_pass")
    assert estimate.yards_on_success - _no_perk_estimate(sim, "short_pass").yards_on_success == pytest.approx(2.0)
    assert not _estimate(sim, "screen_pass").player_perks  # no RB on a Screen
    state = snap(sim, "short_pass", yards=6.0)
    assert last_play(state).play_result.yards_gained == pytest.approx(6.0)
    assert fired(state, K.CHECKDOWN, A)[0].value == 2.0
    assert not _estimate(sim, "short_pass").player_perks  # next snap only


def test_checkdown_needs_the_qb_and_pays_nothing_on_a_turnover() -> None:
    sim = simulator((K.CHECKDOWN,), scheme="deep_pass")
    snap(sim, "screen_pass", randoms=(0.0,))  # no QB on a Screen
    assert not _estimate(sim, "rb_run").player_perks
    sim = simulator((K.CHECKDOWN,), scheme="deep_pass")
    snap(sim, "pa_pass", randoms=(0.0,))
    state = snap(sim, "rb_run", randoms=(0.0,))  # fumble
    assert last_play(state).play_result.turnover and not fired(last_play(state), K.CHECKDOWN)


def test_downhill_rewards_runs_after_rb_plays() -> None:
    sim = simulator((K.DOWNHILL,), scheme="deep_pass")
    assert not _estimate(sim, "rb_run").player_perks
    snap(sim, "short_pass", yards=3)
    assert _estimate(sim, "rb_run").player_perks[0].value == 1.0
    snap(sim, "rb_run", yards=3)
    assert _estimate(sim, "rb_run").player_perks[0].value == 2.0
    snap(sim, "deep_pass", yards=1)  # no RB
    assert not _estimate(sim, "rb_run").player_perks


@pytest.mark.parametrize(("down", "conversion", "fires"), ((3, False, True), (4, False, True), (2, False, False), (1, True, True)))
def test_keep_read_removes_pass_risk_on_money_downs_and_two_point_tries(down, conversion, fires) -> None:
    sim = simulator((K.KEEP_READ,), scheme="deep_pass")
    sim.state = replace(sim.state, down=down, yards_to_go=3.0)
    estimate = calculate_match_play_estimate(sim.state, P.PA_PASS, is_conversion=conversion)
    assert estimate.keep_read is fires
    if fires:
        assert estimate.incomplete_probability == 0.0
        assert 0.003 <= estimate.turnover_probability <= 0.08
        assert estimate.turnover_probability == pytest.approx(0.012, abs=0.001)
        assert estimate.yards_on_success == _no_perk_estimate(sim, "pa_pass").yards_on_success
    assert not calculate_match_play_estimate(sim.state, P.MEDIUM_PASS).keep_read


def test_keep_read_is_once_per_half_and_never_rolls_incompletion() -> None:
    sim = simulator((K.KEEP_READ,), scheme="deep_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=12.0)
    state = snap(sim, "pa_pass", randoms=(0.05,), yards=9.0)  # 0.05 would be an incompletion
    result = last_play(state).play_result
    assert not result.incomplete and not result.turnover and result.yards_gained == pytest.approx(9.0)
    assert fired(last_play(state), K.KEEP_READ, A)
    sim.state = replace(sim.state, down=3, yards_to_go=12.0, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY)
    assert not _estimate(sim, "pa_pass").keep_read
    # The same half's two-point try is blocked too.
    assert not calculate_match_play_estimate(sim.state, P.PA_PASS, is_conversion=True).keep_read
    # A new drive in the same half does not refresh it.
    sim.state = replace(sim.state, down=1, yards_to_go=10.0,
                        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                        current_drive_defensive_scheme=None)
    sim.select_defensive_scheme(S.RB_RUN)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    assert perk_history(sim.state).current_drive > 0
    assert not _estimate(sim, "pa_pass").keep_read


def _keep_read_touchdown(sim):
    """Score from the 95 so Team A faces a conversion."""
    sim.state = replace(sim.state, offense_field_position=95.0, down=1, yards_to_go=5.0)
    state = snap(sim, "short_pass", yards=12.0)
    assert state.awaited_action is FootballAwaitedAction.CONVERSION
    return state


def test_keep_read_on_a_two_point_try_blocks_a_later_money_down_in_the_same_half() -> None:
    sim = simulator((K.KEEP_READ,), scheme="deep_pass")
    _keep_read_touchdown(sim)
    sim.rng = ScriptedRNG(randoms=(0.05,))  # would be an incompletion without Keep Read
    state = sim.resolve_conversion(FootballConversionAction.TWO_POINT, P.PA_PASS)
    try_event = next(event for event in reversed(state.match_events)
                     if event.action is FootballConversionAction.TWO_POINT)
    assert try_event.points_scored == 2 and fired(try_event, K.KEEP_READ, A)
    assert perk_history(state).used(K.KEEP_READ, A, "half")
    # Team A's next drive, still in the first half.
    sim.state = replace(sim.state, possession=A, down=1, yards_to_go=10.0, offense_field_position=40.0,
                        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                        current_drive_defensive_scheme=None, conversion_team=None)
    sim.select_defensive_scheme(S.RB_RUN)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    assert sim.state.period == 1
    assert not _estimate(sim, "pa_pass").keep_read


def test_keep_read_refreshes_in_period_two_and_overtime_is_one_half() -> None:
    sim = simulator((K.KEEP_READ,), scheme="deep_pass", game_clock_seconds=40, opening_possession=B)
    sim.state = replace(sim.state, down=3, yards_to_go=12.0)
    snap(sim, "pa_pass", yards=13.0)
    assert fired(last_play(sim.state), K.KEEP_READ, A)
    sim.state = replace(sim.state, down=3, yards_to_go=20.0)
    assert not _estimate(sim, "pa_pass").keep_read
    snap(sim, "rb_run", yards=1.0)  # the half ends; Team A receives the second-half kickoff
    assert sim.state.period == 2 and sim.state.possession is A
    ensure_in_hand(sim, B, "rb_run", offensive=False)
    sim.select_defensive_scheme(S.RB_RUN)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    assert _estimate(sim, "pa_pass").keep_read
    # Overtime: the first period's use blocks the second overtime period's snaps.
    ot = simulator((K.KEEP_READ,), scheme="deep_pass", period=3, game_clock_seconds=300)
    ot.state = replace(ot.state, down=3, yards_to_go=12.0)
    snap(ot, "pa_pass", yards=13.0)
    assert fired(last_play(ot.state), K.KEEP_READ, A)
    ot.state = replace(ot.state, period=4, down=3, yards_to_go=12.0)
    assert not _estimate(ot, "pa_pass").keep_read
    assert not calculate_match_play_estimate(ot.state, P.PA_PASS, is_conversion=True).keep_read


def test_shot_setup_charges_after_a_deep_miss_and_clears_when_used() -> None:
    sim = simulator((K.SHOT_SETUP,), scheme="rb_run")
    base = _estimate(sim, "deep_pass").incomplete_probability
    snap(sim, "deep_pass", randoms=(0.0,))
    charged = _estimate(sim, "deep_pass")
    assert charged.incomplete_probability == pytest.approx(max(0.12, base - 0.12))
    assert not _estimate(sim, "medium_pass").player_perks
    snap(sim, "deep_pass", yards=5)  # caught: the charge is spent
    assert not _estimate(sim, "deep_pass").player_perks


def test_safety_blitz_trades_incompletions_for_yards_on_second_and_third_down() -> None:
    sim = simulator((), (K.SAFETY_BLITZ,), scheme="medium_pass")
    sim.state = replace(sim.state, down=2, yards_to_go=6.0)
    estimate, plain = _estimate(sim, "deep_pass"), _no_perk_estimate(sim, "deep_pass")
    assert estimate.incomplete_probability == pytest.approx(plain.incomplete_probability + 0.10)
    assert estimate.yards_on_success == pytest.approx(plain.yards_on_success + 2.0)
    assert not _estimate(sim, "rb_run").player_perks
    sim.state = replace(sim.state, down=1)
    assert not _estimate(sim, "deep_pass").player_perks


def test_bait_and_jump_arms_on_an_allowed_deep_catch_and_survives_halftime() -> None:
    sim = simulator((), (K.BAIT_AND_JUMP,), scheme="rb_run", game_clock_seconds=30)
    base = _estimate(sim, "deep_pass").turnover_probability
    snap(sim, "deep_pass", yards=5)
    armed = _estimate(sim, "deep_pass").turnover_probability
    assert armed == pytest.approx(min(0.10, base + 0.08))
    snap(sim, "rb_run", yards=1)  # the half ends; Team B receives the kickoff
    assert sim.state.period == 2
    history = perk_history(sim.state)
    assert history.deep_charge(A, armed_by_completion=True, whole_game=True)


def _bait_status(sim) -> str | None:
    from src.ui.football_match_perks import perk_status_for

    return perk_status_for(sim.state, A, K.BAIT_AND_JUMP)


def test_bait_and_jump_pays_off_once_per_half_and_refreshes_in_period_two() -> None:
    # Team A carries Bait & Jump and defends; Team B receives the second-half kickoff.
    sim = simulator((K.BAIT_AND_JUMP,), (), offense=B, opening_possession=A, scheme="rb_run",
                    offense_field_position=20.0, game_clock_seconds=200)
    assert _bait_status(sim) == "IDLE"
    snap(sim, "deep_pass", yards=5)  # an allowed catch arms the charge
    assert _bait_status(sim) == "ARMED"
    assert _estimate(sim, "deep_pass").player_perks[0].kind is K.BAIT_AND_JUMP
    snap(sim, "deep_pass", yards=5)  # the payoff; the catch re-arms the charge
    assert fired(last_play(sim.state), K.BAIT_AND_JUMP, A)
    assert perk_history(sim.state).deep_charge(B, armed_by_completion=True, whole_game=True)
    assert _bait_status(sim) == "USED"
    base = _no_perk_estimate(sim, "deep_pass").turnover_probability
    assert not _estimate(sim, "deep_pass").player_perks
    assert _estimate(sim, "deep_pass").turnover_probability == pytest.approx(base)
    snap(sim, "deep_pass", yards=5)
    assert not fired(last_play(sim.state), K.BAIT_AND_JUMP)
    # The armed charge carries over halftime and fires again in period 2.
    sim.state = replace(sim.state, game_clock_seconds=1)
    snap(sim, "rb_run", yards=1)
    assert sim.state.period == 2 and sim.state.possession is B
    ensure_in_hand(sim, A, "rb_run", offensive=False)
    sim.select_defensive_scheme(S.RB_RUN)
    assert _bait_status(sim) == "ARMED"
    snap(sim, "deep_pass", yards=5)
    assert fired(last_play(sim.state), K.BAIT_AND_JUMP, A)
    assert _bait_status(sim) == "USED"
    # Its use spent, a rival Deep incompletion leaves it unarmed for later halves.
    snap(sim, "deep_pass", randoms=(0.0,))
    assert _bait_status(sim) == "USED"


def test_bait_and_jump_counts_overtime_as_one_half_and_idles_after_a_deep_miss() -> None:
    sim = simulator((K.BAIT_AND_JUMP,), (), offense=B, scheme="rb_run", period=3,
                    game_clock_seconds=300, offense_field_position=20.0)
    snap(sim, "deep_pass", yards=5)
    snap(sim, "deep_pass", randoms=(0.0,))  # the charge fires on an incompletion
    assert fired(last_play(sim.state), K.BAIT_AND_JUMP, A)
    snap(sim, "deep_pass", yards=5)  # re-armed
    sim.state = replace(sim.state, period=4)  # a later overtime period is the same half
    assert _bait_status(sim) == "USED"
    assert not _estimate(sim, "deep_pass").player_perks
    # A charge consumed without a catch idles while the half's use is still open.
    idle = simulator((K.BAIT_AND_JUMP,), (), offense=B, scheme="rb_run", offense_field_position=20.0)
    snap(idle, "deep_pass", yards=5)
    assert _bait_status(idle) == "ARMED"
    idle.state = replace(idle.state, period=2)
    snap(idle, "deep_pass", randoms=(0.0,))  # fires (period 2's use) and is not re-armed
    assert fired(last_play(idle.state), K.BAIT_AND_JUMP, A)
    fresh = simulator((K.BAIT_AND_JUMP,), (), offense=B, scheme="rb_run", offense_field_position=20.0)
    snap(fresh, "deep_pass", yards=5)
    snap(fresh, "deep_pass", randoms=(0.0,))
    assert _bait_status(fresh) == "USED"
    assert _bait_status(simulator((K.BAIT_AND_JUMP,), (), offense=B, scheme="rb_run")) == "IDLE"


def test_challenge_does_not_refund_a_bait_and_jump_or_keep_read_use() -> None:
    from src.engine.football import FootballBonusCardAction, FootballCardCopy

    def with_challenge(sim):
        challenge = FootballCardCopy("bonus:challenge", FootballBonusCardAction.CHALLENGE.value)
        deck = sim.state.team_a_offense_deck
        sim.state = replace(sim.state, team_a_offense_deck=replace(
            deck, owned=deck.owned + (challenge,), hand=deck.hand + (challenge,)))
        return challenge.copy_id

    bait = simulator((K.KEEP_READ,), (K.BAIT_AND_JUMP,), scheme="rb_run", offense_field_position=20.0)
    challenge = with_challenge(bait)
    snap(bait, "deep_pass", yards=5)
    snap(bait, "deep_pass", yards=5)
    assert fired(last_play(bait.state), K.BAIT_AND_JUMP, B)
    bait.resolve_bonus_card(challenge)
    assert perk_history(bait.state).used(K.BAIT_AND_JUMP, B, "half")
    assert not _estimate(bait, "deep_pass").player_perks

    keep = simulator((K.KEEP_READ,), scheme="deep_pass")
    challenge = with_challenge(keep)
    keep.state = replace(keep.state, down=3, yards_to_go=12.0)
    snap(keep, "pa_pass", yards=9.0)
    assert fired(last_play(keep.state), K.KEEP_READ, A)
    keep.resolve_bonus_card(challenge)
    assert keep.state.down == 3
    assert not _estimate(keep, "pa_pass").keep_read


# -- estimate / resolution / AI parity ----------------------------------------------------


def test_resolution_uses_the_estimate_and_records_its_perks() -> None:
    sim = simulator((K.MOTION_JUMP, K.PULL_LEAD), (K.NICKEL_LOCK,), scheme="screen_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=2.0)
    estimate = _estimate(sim, "screen_pass")
    state = snap(sim, "screen_pass", yards=4)
    result = last_play(state).play_result
    assert result.offense_power == pytest.approx(estimate.matchup.offense)
    assert result.defense_power == pytest.approx(estimate.matchup.defense)
    kinds = [a.kind for a in result.perk_activations]
    assert kinds[:3] == [K.MOTION_JUMP, K.PULL_LEAD, K.NICKEL_LOCK]


def test_hard_ai_scores_plays_with_the_same_perk_estimate() -> None:
    from src.engine.football_ai import FootballAI, FootballAIDifficulty

    sim = simulator((), (K.CHECKDOWN,), offense=B, scheme="rb_run")
    snap(sim, "deep_pass", randoms=(0.0,))
    ai = FootballAI(B, FootballAIDifficulty.HARD, 3)
    score = ai._hard_play_score(sim.state, P.SHORT_PASS)
    estimate = calculate_match_play_estimate(sim.state, P.SHORT_PASS, offense_side=B)
    assert K.CHECKDOWN in [a.kind for a in estimate.player_perks]
    expected = (
        ai._situational_play_score(sim.state, P.SHORT_PASS)
        + 1.2 * estimate.expected_yards
        + 8.0 * estimate.first_down_probability(sim.state.yards_to_go)
        - 12.0 * estimate.turnover_probability
    )
    assert score == pytest.approx(expected)


# -- resolution perks: reroll and result swaps (§2 steps 3-4) ----------------------------


def test_contested_catch_rerolls_one_failed_deep_pass_per_game() -> None:
    sim = simulator((K.CONTESTED_CATCH,), scheme="rb_run")
    state = snap(sim, "deep_pass", randoms=(0.0, 0.99), yards=8.0)
    result = last_play(state).play_result
    assert not result.incomplete and result.yards_gained == pytest.approx(8.0)
    assert fired(last_play(state), K.CONTESTED_CATCH, A)[0].value == 1.0
    state = snap(sim, "deep_pass", randoms=(0.0, 0.99))
    assert last_play(state).play_result.incomplete  # once per game
    other = simulator((K.CONTESTED_CATCH,), scheme="rb_run")
    assert last_play(snap(other, "medium_pass", randoms=(0.0, 0.99))).play_result.incomplete


def test_contested_catch_second_roll_stands() -> None:
    sim = simulator((K.CONTESTED_CATCH,), scheme="rb_run")
    state = snap(sim, "deep_pass", randoms=(0.0, 0.0))
    assert last_play(state).play_result.incomplete
    assert fired(last_play(state), K.CONTESTED_CATCH, A)[0].value == 0.0


def test_pass_pro_erases_the_first_qb_interception() -> None:
    sim = simulator((K.PASS_PRO,), scheme="rb_run")
    state = snap(sim, "deep_pass", randoms=(0.30,))  # interception band
    result = last_play(state).play_result
    assert result.incomplete and not result.turnover and result.clock_seconds_used == 5
    assert state.down == 2 and state.possession is A
    assert fired(last_play(state), K.PASS_PRO, A)
    state = snap(sim, "deep_pass", randoms=(0.30,))
    assert last_play(state).play_result.turnover  # once per game
    screen = simulator((K.PASS_PRO,), scheme="rb_run")
    assert last_play(snap(screen, "screen_pass", randoms=(0.2995,))).play_result.turnover  # no QB


def test_tip_drill_turns_a_money_down_incompletion_into_an_interception() -> None:
    sim = simulator((), (K.TIP_DRILL,), scheme="pa_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=7.0)
    state = snap(sim, "deep_pass", randoms=(0.0,))
    result = last_play(state).play_result
    assert result.turnover and result.turnover_type is FootballTurnoverType.INTERCEPTION
    assert state.possession is B and state.offense_field_position == pytest.approx(60.0)
    assert fired(last_play(state), K.TIP_DRILL, B)
    second_down = simulator((), (K.TIP_DRILL,), scheme="pa_pass")
    second_down.state = replace(second_down.state, down=2)
    assert last_play(snap(second_down, "deep_pass", randoms=(0.0,))).play_result.incomplete
    no_safeties = simulator((), (K.TIP_DRILL,), scheme="rb_run")
    no_safeties.state = replace(no_safeties.state, down=3)
    assert last_play(snap(no_safeties, "deep_pass", randoms=(0.0,))).play_result.incomplete


def test_stunt_sack_turns_a_qb_incompletion_into_a_five_yard_sack() -> None:
    sim = simulator((), (K.STUNT_SACK,), scheme="rb_run")
    state = snap(sim, "medium_pass", randoms=(0.0,))
    result = last_play(state).play_result
    assert not result.incomplete and result.yards_gained == pytest.approx(-5.0)
    assert result.clock_seconds_used == MEDIUM_SECONDS and state.down == 2 and state.yards_to_go == pytest.approx(15.0)
    assert fired(last_play(state), K.STUNT_SACK, B)[0].value == 5.0
    assert last_play(snap(sim, "medium_pass", randoms=(0.0,))).play_result.incomplete  # 1/drive
    screen = simulator((), (K.STUNT_SACK,), scheme="rb_run")
    assert last_play(snap(screen, "screen_pass", randoms=(0.0,))).play_result.incomplete  # no QB


def test_stunt_sack_into_the_end_zone_is_a_safety() -> None:
    sim = simulator((), (K.STUNT_SACK,), scheme="rb_run", offense_field_position=3.0)
    state = snap(sim, "medium_pass", randoms=(0.0,))
    assert last_play(state).points_scored == 2 and state.team_b_score == 2


def test_a_result_is_swapped_at_most_once_offense_first() -> None:
    sim = simulator((K.PASS_PRO,), (K.TIP_DRILL, K.STUNT_SACK), scheme="medium_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=8.0)
    state = snap(sim, "deep_pass", randoms=(0.30,))  # an interception
    result = last_play(state).play_result
    assert result.incomplete and not result.turnover
    kinds = [a.kind for a in last_play(state).perk_activations]
    assert K.PASS_PRO in kinds and K.TIP_DRILL not in kinds and K.STUNT_SACK not in kinds


def test_tip_drill_comes_before_stunt_sack() -> None:
    sim = simulator((), (K.TIP_DRILL, K.STUNT_SACK), scheme="medium_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=8.0)
    state = snap(sim, "medium_pass", randoms=(0.0,))
    kinds = [a.kind for a in last_play(state).perk_activations]
    assert last_play(state).play_result.turnover and K.TIP_DRILL in kinds and K.STUNT_SACK not in kinds


# -- resolution perks: yards (step 5) -------------------------------------------------------


def test_orbit_breakaway_rolls_for_eight_more_yards_once_per_half_when_it_hits() -> None:
    sim = simulator((K.ORBIT_BREAKAWAY,), scheme="rb_run", offense_field_position=20.0)
    state = snap(sim, "short_pass", randoms=(0.99, 0.5), yards=4.0)  # roll misses
    assert last_play(state).play_result.yards_gained == pytest.approx(4.0)
    assert not fired(last_play(state), K.ORBIT_BREAKAWAY)
    state = snap(sim, "short_pass", randoms=(0.99, 0.1), yards=20.0)  # hits, capped at 25
    assert last_play(state).play_result.yards_gained == pytest.approx(25.0)
    assert fired(last_play(state), K.ORBIT_BREAKAWAY, A)[0].value == 8.0
    state = snap(sim, "short_pass", randoms=(0.99, 0.1), yards=4.0)
    assert last_play(state).play_result.yards_gained == pytest.approx(4.0)  # spent this half


def test_fall_forward_floors_one_run_per_drive_and_prevents_a_safety() -> None:
    sim = simulator((K.FALL_FORWARD,), scheme="deep_pass", offense_field_position=0.5)
    state = snap(sim, "rb_run", yards=-2.0)
    assert last_play(state).play_result.yards_gained == pytest.approx(1.0) and not last_play(state).points_scored
    assert fired(last_play(state), K.FALL_FORWARD, A)
    state = snap(sim, "rb_run", yards=-0.5)
    assert last_play(state).play_result.yards_gained == pytest.approx(-0.5)  # 1/drive
    assert not fired(last_play(snap(simulator((K.FALL_FORWARD,), scheme="rb_run"), "rb_run", yards=2.0)),
                     K.FALL_FORWARD)


def test_contain_caps_screens_when_the_dline_contributes() -> None:
    sim = simulator((), (K.CONTAIN,), scheme="rb_run")
    state = snap(sim, "screen_pass", yards=12.0)
    assert last_play(state).play_result.yards_gained == pytest.approx(6.0)
    assert fired(last_play(state), K.CONTAIN, B)[0].value == 6.0
    no_dline = simulator((), (K.CONTAIN,), scheme="pa_pass")
    assert last_play(snap(no_dline, "screen_pass", yards=12.0)).play_result.yards_gained == pytest.approx(12.0)


def test_deep_lock_caps_completions_after_offensive_bonuses() -> None:
    sim = simulator((K.ORBIT_BREAKAWAY,), (K.DEEP_LOCK,), scheme="deep_pass", offense_field_position=20.0)
    state = snap(sim, "short_pass", randoms=(0.99, 0.0), yards=9.0)
    assert last_play(state).play_result.yards_gained == pytest.approx(10.0)
    kinds = [a.kind for a in last_play(state).perk_activations]
    assert kinds.index(K.ORBIT_BREAKAWAY) < kinds.index(K.DEEP_LOCK)
    other = simulator((), (K.DEEP_LOCK,), scheme="medium_pass")
    assert last_play(snap(other, "deep_pass", yards=14.0)).play_result.yards_gained == pytest.approx(14.0)


# -- resolution perks: spot (step 6), defense has the last word ---------------------------


def test_move_the_sticks_reaches_the_line_on_a_short_catch() -> None:
    sim = simulator((K.MOVE_THE_STICKS,), scheme="rb_run")
    state = snap(sim, "short_pass", yards=8.0)
    assert state.down == 1 and last_play(state).play_result.yards_gained == pytest.approx(10.0)
    assert fired(last_play(state), K.MOVE_THE_STICKS, A)
    state = snap(sim, "short_pass", yards=8.0)
    assert state.down == 2  # once per half
    far = simulator((K.MOVE_THE_STICKS,), scheme="rb_run")
    assert snap(far, "short_pass", yards=7.9).down == 2  # more than 2 yards short
    goal = simulator((K.MOVE_THE_STICKS,), scheme="rb_run", offense_field_position=95.0)
    goal.state = replace(goal.state, yards_to_go=5.0)
    assert not fired(last_play(snap(goal, "short_pass", yards=4.0)), K.MOVE_THE_STICKS)  # goal to go


def test_hold_the_line_stops_a_narrow_money_down_conversion() -> None:
    sim = simulator((), (K.HOLD_THE_LINE,), scheme="deep_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=4.0)
    state = snap(sim, "rb_run", yards=5.5)
    assert state.down == 4 and state.yards_to_go == pytest.approx(0.5)
    assert last_play(state).play_result.yards_gained == pytest.approx(3.5)
    assert fired(last_play(state), K.HOLD_THE_LINE, B)
    wide = simulator((), (K.HOLD_THE_LINE,), scheme="deep_pass")
    wide.state = replace(wide.state, down=3, yards_to_go=4.0)
    assert snap(wide, "rb_run", yards=6.0).down == 1  # converted by 2
    early = simulator((), (K.HOLD_THE_LINE,), scheme="deep_pass")
    early.state = replace(early.state, down=2, yards_to_go=4.0)
    assert snap(early, "rb_run", yards=4.5).down == 1


def test_defense_spot_perk_overrides_move_the_sticks() -> None:
    sim = simulator((K.MOVE_THE_STICKS,), (K.HOLD_THE_LINE,), scheme="rb_run")
    sim.state = replace(sim.state, down=3, yards_to_go=10.0)
    state = snap(sim, "short_pass", yards=8.5)
    kinds = [a.kind for a in last_play(state).perk_activations]
    assert kinds.index(K.MOVE_THE_STICKS) < kinds.index(K.HOLD_THE_LINE)
    assert state.down == 4 and state.yards_to_go == pytest.approx(0.5)


def test_pylon_reach_scores_a_wr_catch_that_ends_inside_the_five() -> None:
    sim = simulator((K.PYLON_REACH,), scheme="rb_run", offense_field_position=85.0)
    state = snap(sim, "short_pass", yards=12.0)
    assert last_play(state).points_scored == 6 and fired(last_play(state), K.PYLON_REACH, A)
    run = simulator((K.PYLON_REACH,), scheme="deep_pass", offense_field_position=85.0)
    assert not last_play(snap(run, "rb_run", yards=12.0)).points_scored  # no WR
    short = simulator((K.PYLON_REACH,), scheme="rb_run", offense_field_position=80.0)
    assert not last_play(snap(short, "short_pass", yards=12.0)).points_scored  # ends at the 8


def test_last_line_stops_a_long_touchdown_at_the_one() -> None:
    sim = simulator((), (K.LAST_LINE,), scheme="deep_pass", offense_field_position=80.0)
    state = snap(sim, "rb_run", yards=25.0)
    assert not last_play(state).points_scored
    assert state.offense_field_position == pytest.approx(99.0) and state.down == 1
    assert fired(last_play(state), K.LAST_LINE, B)
    goal = simulator((), (K.LAST_LINE,), scheme="deep_pass", offense_field_position=90.0)
    state = snap(goal, "short_pass", yards=12.0)
    assert state.offense_field_position == pytest.approx(99.0) and state.down == 2
    close = simulator((), (K.LAST_LINE,), scheme="deep_pass", offense_field_position=96.0)
    assert last_play(snap(close, "short_pass", yards=6.0)).points_scored == 6  # from inside the 5


def test_last_line_has_the_last_word_over_pylon_reach() -> None:
    sim = simulator((K.PYLON_REACH,), (K.LAST_LINE,), scheme="rb_run", offense_field_position=85.0)
    state = snap(sim, "short_pass", yards=12.0)
    kinds = [a.kind for a in last_play(state).perk_activations]
    assert kinds.index(K.PYLON_REACH) < kinds.index(K.LAST_LINE)
    assert not last_play(state).points_scored and state.offense_field_position == pytest.approx(99.0)


# -- resolution perks: clock (step 7) -------------------------------------------------------


def test_hurry_up_captain_caps_late_qb_completions_at_eight_seconds() -> None:
    sim = simulator((K.HURRY_UP_CAPTAIN,), scheme="rb_run", game_clock_seconds=180)
    state = snap(sim, "medium_pass", yards=4.0)
    assert last_play(state).play_result.clock_seconds_used == 8
    assert fired(last_play(state), K.HURRY_UP_CAPTAIN, A)[0].value == 8
    early = simulator((K.HURRY_UP_CAPTAIN,), scheme="rb_run", game_clock_seconds=181)
    assert last_play(snap(early, "medium_pass", yards=4.0)).play_result.clock_seconds_used == MEDIUM_SECONDS
    screen = simulator((K.HURRY_UP_CAPTAIN,), scheme="rb_run", game_clock_seconds=100)
    assert last_play(snap(screen, "screen_pass", yards=4.0)).play_result.clock_seconds_used > 8
    overtime = simulator((K.HURRY_UP_CAPTAIN,), scheme="rb_run", game_clock_seconds=100, period=3)
    assert last_play(snap(overtime, "medium_pass", yards=4.0)).play_result.clock_seconds_used == MEDIUM_SECONDS


def test_four_minute_drill_and_keep_it_inbounds_add_clock_for_the_leader() -> None:
    offense = simulator((K.FOUR_MINUTE_DRILL,), scheme="deep_pass", period=2, team_a_score=7)
    base = RUN_SECONDS
    assert last_play(snap(offense, "rb_run", yards=3.0)).play_result.clock_seconds_used == base + 10
    trailing = simulator((K.FOUR_MINUTE_DRILL,), scheme="deep_pass", period=2, team_b_score=7)
    assert last_play(snap(trailing, "rb_run", yards=3.0)).play_result.clock_seconds_used == base
    defense = simulator((), (K.KEEP_IT_INBOUNDS,), scheme="rb_run", period=2, team_b_score=3)
    state = snap(defense, "medium_pass", yards=4.0)
    assert last_play(state).play_result.clock_seconds_used == MEDIUM_SECONDS + 6
    assert fired(last_play(state), K.KEEP_IT_INBOUNDS, B)
    first_half = simulator((), (K.KEEP_IT_INBOUNDS,), scheme="rb_run", team_b_score=3)
    assert last_play(snap(first_half, "medium_pass", yards=4.0)).play_result.clock_seconds_used == MEDIUM_SECONDS


def test_hurry_up_and_keep_it_inbounds_stack_in_order() -> None:
    sim = simulator((K.HURRY_UP_CAPTAIN,), (K.KEEP_IT_INBOUNDS,), scheme="rb_run",
                    period=2, game_clock_seconds=120, team_b_score=3)
    assert last_play(snap(sim, "medium_pass", yards=4.0)).play_result.clock_seconds_used == 14


# -- kick perks ----------------------------------------------------------------------------


def test_kick_rush_adds_block_chance_to_rival_punts_and_extra_points() -> None:
    sim = simulator((), (K.KICK_RUSH,), scheme="rb_run")
    sim.state = replace(sim.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    sim.rng = ScriptedRNG(randoms=(0.05, 0.99))
    state = sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    punt = next(event for event in state.match_events if event.action is FootballFourthDownAction.PUNT)
    assert punt.blocked and fired(punt, K.KICK_RUSH, B)
    plain = simulator(scheme="rb_run")
    plain.state = replace(plain.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    plain.rng = ScriptedRNG(randoms=(0.05, 0.99))
    assert not plain.resolve_fourth_down(FootballFourthDownAction.PUNT).match_events[-1].blocked

    pat = simulator((), (K.KICK_RUSH,), scheme=None, team_a_score=6, offense_field_position=98.0,
                    yards_to_go=2.0, awaited_action=FootballAwaitedAction.CONVERSION,
                    conversion_team=A, current_drive_defensive_scheme=S.RB_RUN)
    pat.rng = ScriptedRNG(randoms=(0.05, 0.99, 0.99))
    state = pat.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    event = next(event for event in state.match_events if event.action is FootballConversionAction.EXTRA_POINT)
    assert event.blocked and fired(event, K.KICK_RUSH, B)


def test_range_denial_makes_rival_field_goals_seven_yards_longer() -> None:
    state = match((), (K.RANGE_DENIAL,), down=4, offense_field_position=73.0,
                  awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
                  current_drive_defensive_scheme=S.RB_RUN)
    assert field_goal_success_probability_for_team(state, A, 37.0) == pytest.approx(
        field_goal_success_probability(44.0)
    )
    assert field_goal_success_probability_for_team(state, B, 37.0) == pytest.approx(
        field_goal_success_probability(37.0)
    )
    sim = simulator((), (K.RANGE_DENIAL,), scheme="rb_run", offense_field_position=73.0)
    sim.state = replace(sim.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    sim.rng = ScriptedRNG(randoms=(0.99, 0.70))  # 70%: good from 37, no good from 44
    kick = sim.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    event = next(event for event in kick.match_events if event.action is FootballFourthDownAction.FIELD_GOAL)
    assert event.field_goal_distance == pytest.approx(37.0) and not event.points_scored
    assert fired(event, K.RANGE_DENIAL, B)[0].value == 7.0


# -- card perks (step 8) ------------------------------------------------------------------


def _hand(state, side, offensive=True):
    return getattr(state, f"{side.value}_{'offense' if offensive else 'defense'}_deck").hand


def _ids(cards):
    return [card.card_id for card in cards]


def test_mesh_read_pulls_an_rb_run_card_after_a_completed_play_action() -> None:
    sim = simulator((K.MESH_READ,), scheme="deep_pass")
    with_hand(sim, A, ("pa_pass", "short_pass", "deep_pass"))
    before = len(_hand(sim.state, A))
    replacement = sim.state.team_a_offense_deck.draw_pile[0]
    state = snap(sim, "pa_pass", yards=4.0)
    hand = _hand(state, A)
    assert len(hand) == before + 1
    assert _ids(hand).count("rb_run") == 1 + (replacement.card_id == "rb_run")
    assert fired(last_play(state), K.MESH_READ, A)
    state = snap(sim, "pa_pass", yards=4.0)
    assert not fired(last_play(state), K.MESH_READ)  # once per drive
    missed = simulator((K.MESH_READ,), scheme="deep_pass")
    assert not fired(last_play(snap(missed, "pa_pass", randoms=(0.0,))), K.MESH_READ)


def test_option_ledger_draws_two_on_the_fourth_family_of_a_drive_once_per_game() -> None:
    sim = simulator((K.OPTION_LEDGER,), scheme="deep_pass", offense_field_position=10.0)
    for play in ("rb_run", "screen_pass", "short_pass"):
        assert not fired(last_play(snap(sim, play, yards=11.0)), K.OPTION_LEDGER)
    before = len(_hand(sim.state, A))
    state = snap(sim, "rb_run", yards=11.0)  # a repeat family
    assert not fired(last_play(state), K.OPTION_LEDGER)
    state = snap(sim, "medium_pass", yards=11.0)
    assert fired(last_play(state), K.OPTION_LEDGER, A)[0].value == 2
    assert len(_hand(state, A)) == before + 2
    assert not fired(last_play(snap(sim, "pa_pass", yards=11.0)), K.OPTION_LEDGER)


def test_outlet_repeat_keeps_a_short_pass_that_moves_the_chains() -> None:
    sim = simulator((K.OUTLET_REPEAT,), scheme="rb_run")
    card = next(card for card in _hand(sim.state, A) if card.card_id == "short_pass")
    state = snap(sim, "short_pass", yards=11.0)
    assert card in _hand(state, A) and card not in state.team_a_offense_deck.discard_pile
    assert fired(last_play(state), K.OUTLET_REPEAT, A)
    state = snap(sim, "short_pass", yards=11.0)
    assert card in state.team_a_offense_deck.discard_pile  # once per drive
    short = simulator((K.OUTLET_REPEAT,), scheme="rb_run")
    assert not fired(last_play(snap(short, "short_pass", yards=4.0)), K.OUTLET_REPEAT)


def test_release_read_churns_a_random_rival_scheme_after_a_long_screen() -> None:
    sim = simulator((K.RELEASE_READ,), scheme="deep_pass")
    rival = _hand(sim.state, B, offensive=False)
    state = snap(sim, "screen_pass", yards=9.0, choices=(1,))
    assert fired(last_play(state), K.RELEASE_READ, A)
    assert rival[1] in state.team_b_defense_deck.discard_pile
    assert len(_hand(state, B, offensive=False)) == len(rival)
    assert state.current_drive_defensive_scheme is S.DEEP_PASS
    short = simulator((K.RELEASE_READ,), scheme="deep_pass")
    assert not fired(last_play(snap(short, "screen_pass", yards=7.0)), K.RELEASE_READ)


def test_tempo_read_draws_after_a_medium_first_down() -> None:
    sim = simulator((K.TEMPO_READ,), scheme="rb_run")
    before = len(_hand(sim.state, A))
    state = snap(sim, "medium_pass", yards=11.0)
    assert fired(last_play(state), K.TEMPO_READ, A) and len(_hand(state, A)) == before + 1
    assert not fired(last_play(snap(sim, "medium_pass", yards=11.0)), K.TEMPO_READ)


def test_collapse_churns_a_rival_play_after_a_third_down_stop() -> None:
    sim = simulator((), (K.COLLAPSE,), scheme="deep_pass")
    sim.state = replace(sim.state, down=3, yards_to_go=8.0)
    state = snap(sim, "rb_run", yards=2.0, choices=(0,))
    assert fired(last_play(state), K.COLLAPSE, B) and state.down == 4
    converted = simulator((), (K.COLLAPSE,), scheme="deep_pass")
    converted.state = replace(converted.state, down=3, yards_to_go=1.0)
    assert not fired(last_play(snap(converted, "rb_run", yards=2.0)), K.COLLAPSE)


def test_bracket_discards_a_rival_play_without_replacement_once_per_game() -> None:
    sim = simulator((), (K.BRACKET,), scheme="short_pass")
    before = len(_hand(sim.state, A))
    state = snap(sim, "short_pass", randoms=(0.0,))
    # The played card cycled with a replacement; Bracket's discard was not replaced.
    assert fired(last_play(state), K.BRACKET, B) and len(_hand(state, A)) == before - 1
    state = snap(sim, "short_pass", randoms=(0.0,))
    assert not fired(last_play(state), K.BRACKET)
    no_corners = simulator((), (K.BRACKET,), scheme="rb_run")
    assert not fired(last_play(snap(no_corners, "short_pass", randoms=(0.0,))), K.BRACKET)


def test_fit_and_shed_draws_a_scheme_after_a_short_rival_gain() -> None:
    sim = simulator((), (K.FIT_AND_SHED,), scheme="rb_run")
    before = len(_hand(sim.state, B, offensive=False))
    state = snap(sim, "rb_run", yards=2.0)
    assert fired(last_play(state), K.FIT_AND_SHED, B)
    assert len(_hand(state, B, offensive=False)) == before + 1
    assert not fired(last_play(snap(sim, "rb_run", yards=1.0)), K.FIT_AND_SHED)
    long = simulator((), (K.FIT_AND_SHED,), scheme="rb_run")
    assert not fired(last_play(snap(long, "rb_run", yards=2.5)), K.FIT_AND_SHED)
    no_lbs = simulator((), (K.FIT_AND_SHED,), scheme="deep_pass")
    assert not fired(last_play(snap(no_lbs, "deep_pass", randoms=(0.0,))), K.FIT_AND_SHED)


def test_sudden_change_feeds_the_defense_a_play_card_on_each_takeaway() -> None:
    sim = simulator((), (K.SUDDEN_CHANGE,), scheme="rb_run")
    before = len(_hand(sim.state, B))
    state = snap(sim, "deep_pass", randoms=(0.30,))  # interception
    assert fired(last_play(state), K.SUDDEN_CHANGE, B)
    assert len(_hand(state, B)) == before + 1  # the offense-hand card survives the trim
    downs = simulator((), (K.SUDDEN_CHANGE,), scheme="deep_pass")
    downs.state = replace(downs.state, down=4, yards_to_go=5.0)
    assert fired(last_play(snap(downs, "rb_run", yards=1.0)), K.SUDDEN_CHANGE, B)


def test_hold_the_front_returns_the_run_scheme_then_the_trim_may_discard_it() -> None:
    sim = simulator((), (K.HOLD_THE_FRONT,), scheme="rb_run")
    scheme_card = sim.state.match_events[-1].card_copy_id
    sim.state = replace(sim.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    sim.rng = ScriptedRNG()
    state = sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    punt = next(event for event in state.match_events if event.action is FootballFourthDownAction.PUNT)
    assert fired(punt, K.HOLD_THE_FRONT, B)
    deck = state.team_b_defense_deck
    assert len(deck.hand) == 2
    assert any(card.copy_id == scheme_card for card in deck.hand + deck.discard_pile)
    pass_scheme = simulator((), (K.HOLD_THE_FRONT,), scheme="deep_pass")
    pass_scheme.state = replace(pass_scheme.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    pass_scheme.rng = ScriptedRNG()
    assert not fired(pass_scheme.resolve_fourth_down(FootballFourthDownAction.PUNT).match_events[-2], K.HOLD_THE_FRONT)


def test_hot_route_swaps_the_weakest_countered_card_at_drive_start() -> None:
    sim = simulator((K.HOT_ROUTE,), scheme=None)
    hand = with_hand(sim, A, ("deep_pass", "rb_run", "deep_pass")).hand
    state = sim.select_defensive_scheme(S.DEEP_PASS)
    assert fired(state.match_events[-1], K.HOT_ROUTE, A)
    assert hand[0] in state.team_a_offense_deck.discard_pile  # ties: leftmost
    assert hand[2] in state.team_a_offense_deck.hand
    calm = simulator((K.HOT_ROUTE,), scheme=None)
    with_hand(calm, A, ("rb_run", "short_pass"))
    assert not fired(calm.select_defensive_scheme(S.DEEP_PASS).match_events[-1], K.HOT_ROUTE)


# -- drive-start field position ------------------------------------------------------------


def test_breathing_room_moves_a_backed_up_drive_five_yards() -> None:
    sim = simulator((K.BREATHING_ROOM,), scheme=None, offense_field_position=18.0)
    state = sim.select_defensive_scheme(S.RB_RUN)
    assert state.offense_field_position == pytest.approx(23.0) and state.yards_to_go == 10.0
    assert fired(state.match_events[-1], K.BREATHING_ROOM, A)[0].value == 5.0
    roomy = simulator((K.BREATHING_ROOM,), scheme=None, offense_field_position=21.0)
    assert roomy.select_defensive_scheme(S.RB_RUN).offense_field_position == pytest.approx(21.0)
    overtime = simulator((K.BREATHING_ROOM,), scheme=None, offense_field_position=18.0, period=3,
                         game_clock_seconds=300)
    assert overtime.select_defensive_scheme(S.RB_RUN).offense_field_position == pytest.approx(18.0)


def test_short_field_follows_a_rival_punt_or_turnover_on_downs() -> None:
    sim = simulator((), (K.SHORT_FIELD,), scheme="rb_run")
    sim.state = replace(sim.state, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION)
    sim.rng = ScriptedRNG(randoms=(0.99, 0.99))  # no block, no return
    after_punt = sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    start = after_punt.offense_field_position
    state = sim.select_defensive_scheme(S.RB_RUN)
    assert state.possession is B and state.offense_field_position == pytest.approx(start + 5.0)
    assert fired(state.match_events[-1], K.SHORT_FIELD, B)
    downs = simulator((), (K.SHORT_FIELD,), scheme="deep_pass")
    downs.state = replace(downs.state, down=4, yards_to_go=5.0)
    snap(downs, "rb_run", yards=1.0)
    start = downs.state.offense_field_position
    assert downs.select_defensive_scheme(S.RB_RUN).offense_field_position == pytest.approx(start + 5.0)
    turnover = simulator((), (K.SHORT_FIELD,), scheme="rb_run")
    snap(turnover, "deep_pass", randoms=(0.30,))
    start = turnover.state.offense_field_position
    assert turnover.select_defensive_scheme(S.RB_RUN).offense_field_position == pytest.approx(start)


# -- end-of-drive hand reset ---------------------------------------------------------------


def test_drive_end_trims_oversized_hands_at_random_into_the_discard() -> None:
    sim = simulator(scheme="rb_run")
    offense_before = _hand(sim.state, A)
    defense_before = _hand(sim.state, B, offensive=False)
    assert len(offense_before) == 6 and len(defense_before) == 6
    state = snap(sim, "deep_pass", randoms=(0.30,))  # interception ends Team A's drive
    offense, defense = state.team_a_offense_deck, state.team_b_defense_deck
    assert len(offense.hand) == 3 and len(defense.hand) == 2
    # Six cards (the played one was replaced) trimmed to three: three go to the discard.
    trimmed = offense.discard_pile[1:]
    assert offense.discard_pile[0].card_id == "deep_pass" and len(trimmed) == 3
    # Untouched hands (Team A defense, Team B offense) keep their size.
    assert len(state.team_a_defense_deck.hand) == 6 and len(state.team_b_offense_deck.hand) == 6
    again = simulator(scheme="rb_run")
    assert snap(again, "deep_pass", randoms=(0.30,)).team_a_offense_deck == offense  # seeded


def test_drive_end_refills_short_hands_and_draws_nothing_when_nothing_is_left() -> None:
    from tests.perk_helpers import deck

    tiny = deck("a:o", ("rb_run", "deep_pass"), 1)
    sim = simulator(scheme="rb_run", a_decks={"offense": tiny, "defense": deck("a:d", ("rb_run",), 1)})
    state = snap(sim, "rb_run", randoms=(0.0,))  # fumble
    # One card was played and replaced; the refill takes the only other card left.
    assert len(state.team_a_offense_deck.hand) == 2 and not state.team_a_offense_deck.draw_pile


def test_conversion_ends_the_scoring_drive_and_normalizes_both_hands() -> None:
    sim = simulator(scheme="rb_run", offense_field_position=90.0)
    state = snap(sim, "short_pass", yards=12.0)
    assert state.awaited_action is FootballAwaitedAction.CONVERSION
    assert len(_hand(state, A)) == 6  # the try still belongs to the drive
    sim.rng = ScriptedRNG()
    state = sim.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    assert len(_hand(state, A)) == 3 and len(_hand(state, B, offensive=False)) == 2


def test_draw_bonus_cards_and_kept_cards_only_last_for_the_drive() -> None:
    from src.engine.football import FootballBonusCardAction
    from src.engine.football import FootballCardCopy

    sim = simulator((K.OUTLET_REPEAT,), scheme="rb_run")
    draw = FootballCardCopy("bonus:draw", FootballBonusCardAction.OFFENSIVE_DRAW.value)
    deck = sim.state.team_a_offense_deck
    sim.state = replace(sim.state, team_a_offense_deck=replace(
        deck, owned=deck.owned + (draw,), hand=deck.hand + (draw,)))
    sim.rng = ScriptedRNG()
    state = sim.resolve_bonus_card(draw.copy_id)
    assert len(_hand(state, A)) == 8  # replaced itself plus one extra
    state = snap(sim, "short_pass", yards=11.0)  # kept by Outlet Repeat
    assert len(_hand(state, A)) == 8
    state = snap(sim, "deep_pass", randoms=(0.30,))  # the drive ends
    assert len(_hand(state, A)) == 3


# -- halftime: the drive ends and the second half opens with a kickoff -----------------------


def test_halftime_ends_the_drive_redeals_and_refreshes_half_limits() -> None:
    sim = simulator((K.MOVE_THE_STICKS,), (K.HOLD_THE_LINE,), scheme="rb_run", game_clock_seconds=40)
    state = snap(sim, "short_pass", yards=8.0)  # Move the Sticks, once this half
    assert fired(last_play(state), K.MOVE_THE_STICKS)
    state = snap(sim, "short_pass", yards=3.0)  # the clock runs out
    kickoff = state.match_events[-1]
    assert state.period == 2 and kickoff.action.value == "kickoff"
    # Team A had the opening possession, so it kicks; Team B receives.
    assert kickoff.possession is B and state.possession is B
    assert state.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert state.current_drive_defensive_scheme is None
    assert len(_hand(state, A)) == 3 and len(_hand(state, B, offensive=False)) == 2
    assert not perk_history(state).used(K.MOVE_THE_STICKS, A, "half")
    assert perk_history(state).used(K.MOVE_THE_STICKS, A, "game")


def test_the_team_that_did_not_receive_the_opening_kickoff_gets_the_second_half_ball() -> None:
    sim = simulator(scheme="rb_run", offense=B, game_clock_seconds=20, opening_possession=B)
    snap(sim, "rb_run", yards=1.0)
    assert sim.state.period == 2 and sim.state.possession is A


def test_a_conversion_pending_at_the_end_of_the_half_still_resolves_first() -> None:
    sim = simulator(scheme="rb_run", offense_field_position=95.0, game_clock_seconds=10)
    state = snap(sim, "short_pass", yards=12.0)
    assert state.period == 1 and state.awaited_action is FootballAwaitedAction.CONVERSION
    sim.rng = ScriptedRNG()
    state = sim.resolve_conversion(FootballConversionAction.EXTRA_POINT)
    actions = [event.action.value for event in state.match_events[-2:]]
    assert actions == ["extra_point", "kickoff"]
    # Only the halftime kickoff: Team A (the opening receiver) kicks to Team B.
    assert sum(event.action.value == "kickoff" for event in state.match_events) == 1
    assert state.period == 2 and state.possession is B


# -- Read Keys (L4) and Green Dog (L6) -------------------------------------------------------


def _ai(side, difficulty):
    from src.engine.football_ai import FootballAI, FootballAIDifficulty

    return FootballAI(side, FootballAIDifficulty(difficulty), 5)


def test_read_keys_reveals_the_rival_hand_only_to_its_owner() -> None:
    state = match((), (K.READ_KEYS,))
    owner, other = _ai(B, "standard"), _ai(A, "standard")
    assert owner.revealed_rival_plays(state) == tuple(P(card.card_id) for card in state.team_a_offense_deck.hand)
    assert other.revealed_rival_plays(state) is None
    sim = simulator((), (K.READ_KEYS,), scheme="rb_run")
    assert fired(sim.state.match_events[-1], K.READ_KEYS, B)


@pytest.mark.parametrize("difficulty", ("standard", "hard"))
def test_standard_and_hard_read_keys_pick_a_scheme_that_counters_the_revealed_hand(difficulty) -> None:
    from tests.perk_helpers import deck

    state = match((), (K.READ_KEYS,), a_decks={
        "offense": deck("a:o", ("deep_pass", "deep_pass", "deep_pass"), 3),
        "defense": deck("a:d", ("rb_run", "deep_pass"), 2),
    }, b_decks={
        "offense": deck("b:o", ("rb_run",), 1),
        "defense": deck("b:d", ("rb_run", "deep_pass", "screen_pass"), 3),
    })
    assert _ai(B, difficulty).choose_action(state) is S.DEEP_PASS


def test_easy_ignores_read_keys() -> None:
    from tests.perk_helpers import deck

    choices = set()
    for seed in range(12):
        from src.engine.football_ai import FootballAI, FootballAIDifficulty

        ai = FootballAI(B, FootballAIDifficulty.EASY, seed)
        state = match((), (K.READ_KEYS,), a_decks={
            "offense": deck("a:o", ("deep_pass",) * 3, 3), "defense": deck("a:d", ("rb_run",), 1),
        }, b_decks={
            "offense": deck("b:o", ("rb_run",), 1),
            "defense": deck("b:d", ("rb_run", "deep_pass", "screen_pass"), 3),
        })
        choices.add(ai.choose_action(state))
    assert len(choices) > 1


def _green_dog_offer(human_defense: bool = False):
    """A rival 3rd-down conversion against a Green Dog defense."""
    offense = B if human_defense else A
    owner = A if human_defense else B
    sim = simulator((K.GREEN_DOG,) if owner is A else (), (K.GREEN_DOG,) if owner is B else (),
                    offense=offense, scheme="rb_run")
    sim.state = replace(sim.state, down=3, yards_to_go=4.0)
    state = snap(sim, "deep_pass", yards=6.0)
    return sim, state, owner


def test_green_dog_is_offered_after_a_money_down_conversion_and_swaps_the_scheme() -> None:
    sim, state, owner = _green_dog_offer()
    assert state.awaited_action is FootballAwaitedAction.GREEN_DOG_DECISION
    card = next(card for card in _hand(state, owner, offensive=False) if card.card_id == "deep_pass")
    state = sim.resolve_green_dog(card.copy_id)
    event = state.match_events[-1]
    assert event.action.value == "green_dog_swap" and fired(event, K.GREEN_DOG, owner)
    assert state.current_drive_defensive_scheme is S.DEEP_PASS
    assert state.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert card in getattr(state, f"{owner.value}_defense_deck").discard_pile
    sim.state = replace(sim.state, down=3, yards_to_go=4.0)
    state = snap(sim, "rb_run", yards=6.0)
    assert state.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY  # once per game


def test_green_dog_decline_keeps_the_scheme_and_is_offered_again() -> None:
    sim, state, owner = _green_dog_offer()
    state = sim.resolve_green_dog(None)
    assert state.match_events[-1].action.value == "green_dog_decline"
    assert state.current_drive_defensive_scheme is S.RB_RUN
    sim.state = replace(sim.state, down=4, yards_to_go=1.0)
    assert snap(sim, "deep_pass", yards=3.0).awaited_action is FootballAwaitedAction.GREEN_DOG_DECISION
    no_conversion = simulator((), (K.GREEN_DOG,), scheme="rb_run")
    no_conversion.state = replace(no_conversion.state, down=2, yards_to_go=4.0)
    assert snap(no_conversion, "deep_pass", yards=6.0).awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY


def test_ai_green_dog_swaps_only_when_a_hand_scheme_outscores_the_active_one() -> None:
    sim, state, owner = _green_dog_offer()
    ai = _ai(owner, "standard")
    choice = ai.choose_green_dog(state)
    scores = {
        card.copy_id: ai._hard_defensive_scheme_score(
            state, S(card.card_id), state.team_a, state.team_b,
        )
        for card in _hand(state, owner, offensive=False)
    }
    active = ai._hard_defensive_scheme_score(state, S.RB_RUN, state.team_a, state.team_b)
    if max(scores.values()) > active:
        assert scores[choice] == max(scores.values())
    else:
        assert choice is None


def test_controller_prompts_the_human_and_saves_mid_prompt() -> None:
    from src.engine.football_controller import FootballGameController, FootballHumanDecision
    from tests.football_run_driver import new_controller, step
    import random

    for seed in range(60):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while controller.state.human_decision is not FootballHumanDecision.GREEN_DOG:
            if not step(controller, rng):
                break
        if controller.state.human_decision is FootballHumanDecision.GREEN_DOG:
            break
    else:
        pytest.skip("No seeded run reached a human Green Dog prompt.")
    restored = FootballGameController.from_save_data(controller.to_save_data())
    assert restored.state.human_decision is FootballHumanDecision.GREEN_DOG
    assert restored.to_save_data() == controller.to_save_data()
    hand = controller.state.match.team_a_defense_deck.hand
    for runner in (controller, restored):
        runner.respond_to_green_dog(hand[0].copy_id)
    assert restored.to_save_data() == controller.to_save_data()
    assert controller.state.match.match_events[
        -1 if controller.state.match.match_events[-1].action.value == "green_dog_swap" else -2
    ]


def test_challenge_restore_keeps_a_green_dog_swap_and_spent_uses() -> None:
    from src.engine.football import FootballBonusCardAction, FootballCardCopy

    sim = simulator((K.MOTION_JUMP,), (K.GREEN_DOG,), scheme="rb_run")
    challenge = FootballCardCopy("bonus:challenge", FootballBonusCardAction.CHALLENGE.value)
    deck = sim.state.team_a_offense_deck
    sim.state = replace(sim.state, team_a_offense_deck=replace(
        deck, owned=deck.owned + (challenge,), hand=deck.hand + (challenge,)))
    sim.state = replace(sim.state, down=3, yards_to_go=4.0)
    snap(sim, "screen_pass", yards=6.0)  # Motion Jump fires; the conversion offers Green Dog
    swap = next(card for card in _hand(sim.state, B, offensive=False) if card.card_id == "deep_pass")
    sim.resolve_green_dog(swap.copy_id)
    sim.resolve_bonus_card(challenge.copy_id)
    state = sim.state
    assert state.down == 3 and state.current_drive_defensive_scheme is S.DEEP_PASS
    assert perk_history(state).used(K.MOTION_JUMP, A, "drive")  # not refunded
    assert perk_history(state).used(K.GREEN_DOG, B, "game")


# -- AI: drafting and Keep Read two-point tries ----------------------------------------------


def test_ai_drafting_prefers_partners_and_deck_fit_but_stays_seeded_and_varied() -> None:
    from src.engine.football_ai import FootballAI, FootballAIDifficulty, draft_weight
    from src.engine.football_coaches import COACH_PAIR_OFFERS
    from src.engine.football_player_catalog import PLAYER_TYPES_BY_ID

    pair = COACH_PAIR_OFFERS[0]
    mesh = PLAYER_TYPES_BY_ID["qb_rb_mesh_reader"]  # partners with the RB
    rb_for_qb = PLAYER_TYPES_BY_ID["rb_qb_checkdown_back"]  # its partner is the QB
    rb_for_wr = PLAYER_TYPES_BY_ID["rb_wr_orbit_runner"]
    assert draft_weight(rb_for_qb, [mesh], pair) > draft_weight(rb_for_wr, [mesh], pair)
    basic = PLAYER_TYPES_BY_ID["basic_rb"]
    assert draft_weight(basic, [mesh], pair) < draft_weight(rb_for_wr, [mesh], pair)

    for difficulty in FootballAIDifficulty:
        rosters = [FootballAI(B, difficulty, seed).generate_opponent_roster() for seed in range(40)]
        again = [FootballAI(B, difficulty, seed).generate_opponent_roster() for seed in range(40)]
        assert rosters == again  # seeded
        types = {tuple(p.player_type_id for p in roster.players.values()) for roster in rosters}
        assert len(types) > 30  # still varied
        linked = sum(
            1 for roster in rosters for player in roster.players.values()
            if PLAYER_TYPES_BY_ID[player.player_type_id].partner_position is not None
            and roster.players[PLAYER_TYPES_BY_ID[player.player_type_id].partner_position].player_type_id
            and PLAYER_TYPES_BY_ID[roster.players[PLAYER_TYPES_BY_ID[player.player_type_id].partner_position].player_type_id].partner_position
            is player.position
        )
        assert linked / len(rosters) > 1.0  # mutual partner pairs are common


def test_ai_goes_for_two_with_keep_read_and_a_play_action_card() -> None:
    from src.engine.football import FootballConversionAction as C
    from tests.perk_helpers import deck

    def conversion(kinds, hand):
        return match(kinds, (), possession=B, team_a_score=0, team_b_score=6, down=1, yards_to_go=2.0,
                     offense_field_position=98.0, awaited_action=FootballAwaitedAction.CONVERSION,
                     conversion_team=B, current_drive_defensive_scheme=S.RB_RUN,
                     team_a=roster("Home"),
                     team_b=roster("Away", *kinds),
                     b_decks={"offense": deck("b:o", hand, len(hand)), "defense": deck("b:d", ("rb_run",), 1)})

    for difficulty in ("easy", "standard", "hard"):
        ai = _ai(B, difficulty)
        state = conversion((K.KEEP_READ,), ("deep_pass", "pa_pass"))
        assert ai.choose_action(state) is C.TWO_POINT
        assert ai.choose_conversion_card(state) == "b:o:1:pa_pass"
        assert ai.choose_action(conversion((K.KEEP_READ,), ("deep_pass", "rb_run"))) is C.EXTRA_POINT
        assert ai.choose_action(conversion((), ("pa_pass",))) is C.EXTRA_POINT


def test_ai_goes_for_two_with_keep_read_only_while_that_halfs_use_is_unused() -> None:
    from src.engine.football import FootballConversionAction as C

    sim = simulator((), (K.KEEP_READ,), offense=B, scheme="deep_pass", offense_field_position=60.0)
    sim.state = replace(sim.state, down=3, yards_to_go=5.0)
    snap(sim, "pa_pass", yards=10.0)
    assert fired(last_play(sim.state), K.KEEP_READ, B)
    sim.state = replace(sim.state, offense_field_position=95.0, down=1, yards_to_go=5.0)
    snap(sim, "short_pass", yards=12.0)
    assert sim.state.awaited_action is FootballAwaitedAction.CONVERSION and sim.state.period == 1
    with_hand(sim, B, ("deep_pass", "pa_pass"))
    for difficulty in ("easy", "standard", "hard"):
        ai = _ai(B, difficulty)
        assert ai.choose_action(sim.state) is C.EXTRA_POINT  # this half's use is spent
        # The same try in a fresh half would go for two.
        assert ai.choose_action(replace(sim.state, period=2)) is C.TWO_POINT


# -- both teams: deck-side card perks work for whichever team owns them ----------------------


def _flip(side):
    return B if side is A else A


@pytest.mark.parametrize("offense", (A, B))
@pytest.mark.parametrize(("kind", "owner_is_offense", "play", "scheme", "yards", "randoms", "check"), (
    (K.TEMPO_READ, True, "medium_pass", "rb_run", 11.0, (), lambda before, after, o: len(after(o, True)) == len(before(o, True)) + 1),
    (K.OUTLET_REPEAT, True, "short_pass", "rb_run", 11.0, (), lambda before, after, o: len(after(o, True)) == len(before(o, True))),
    (K.FIT_AND_SHED, False, "rb_run", "rb_run", 1.0, (), lambda before, after, o: len(after(_flip(o), False)) == len(before(_flip(o), False)) + 1),
    (K.BRACKET, False, "short_pass", "short_pass", None, (0.0,), lambda before, after, o: len(after(o, True)) == len(before(o, True)) - 1),
    (K.RELEASE_READ, True, "screen_pass", "deep_pass", 9.0, (), lambda before, after, o: len(after(_flip(o), False)) == len(before(_flip(o), False))),
    (K.SUDDEN_CHANGE, False, "deep_pass", "rb_run", None, (0.30,), lambda before, after, o: len(after(_flip(o), True)) == len(before(_flip(o), True)) + 1),
))
def test_card_perks_work_for_either_team(offense, kind, owner_is_offense, play, scheme, yards, randoms, check) -> None:
    owner = offense if owner_is_offense else _flip(offense)
    sim = simulator((kind,) if owner is A else (), (kind,) if owner is B else (), offense=offense, scheme=scheme)
    before_state = sim.state

    def hand_of(state):
        return lambda side, offensive: _hand(state, side, offensive)

    state = snap(sim, play, yards=yards, randoms=randoms)
    assert fired(last_play(state), kind, owner)
    assert check(hand_of(before_state), hand_of(state), offense)
