"""Draft offers (three distinct types, equal odds from seven), per-type base stats
with a seeded per-prospect spread, Basic always weakest, and save format 5."""

import json
import random
from collections import Counter
from dataclasses import replace
from types import MappingProxyType

import pytest

from src.engine import football_player_catalog as catalog
from src.engine.football import FootballPosition, FootballTeamSide
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_controller import FootballGameController, FootballRunPhase
from src.engine.football_player_catalog import (
    BASIC_PLAYER_TYPES,
    PLAYER_TYPES,
    PLAYER_TYPES_BY_ID,
    PLAYER_TYPES_BY_POSITION,
    player_type_for_id,
    player_type_offer,
    prospect_score,
    prospect_score_range,
    roll_prospect,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER, FootballTeamBuilder
from src.persistence import migrations
from src.persistence.migrations import migrate_payload

from football_run_driver import new_controller

# type id: (power, volatility %, stamina %), from the approved table.
TABLE = {
    "qb_rb_mesh_reader": (52, 9, 56), "qb_rb_option_ledger": (51, 8, 55),
    "qb_wr_boundary_captain": (52, 10, 60), "qb_wr_vertical_architect": (58, 14, 48),
    "qb_oline_pocket_anchor": (53, 7, 52), "qb_oline_silent_count": (52, 7, 54),
    "rb_qb_checkdown_back": (50, 8, 58), "rb_qb_option_keeper": (53, 11, 54),
    "rb_wr_orbit_runner": (57, 15, 52), "rb_wr_slot_outlet": (50, 8, 56),
    "rb_oline_gap_runner": (59, 14, 44), "rb_oline_pull_guard_back": (55, 10, 52),
    "wr_qb_route_technician": (51, 7, 55), "wr_qb_vertical_threat": (58, 15, 48),
    "wr_rb_screen_outlet": (52, 8, 56), "wr_rb_motion_receiver": (54, 10, 55),
    "wr_oline_boundary_route": (56, 12, 50), "wr_oline_release_specialist": (53, 9, 57),
    "oline_qb_pass_set_guard": (52, 7, 55), "oline_qb_pocket_tempo": (51, 8, 58),
    "oline_rb_drive_blocker": (54, 10, 60), "oline_rb_pull_guard": (58, 13, 48),
    "oline_wr_screen_setter": (52, 9, 55), "oline_wr_space_creator": (55, 11, 52),
    "dline_lb_a_gap_plug": (57, 9, 46), "dline_lb_edge_setter": (55, 10, 54),
    "dline_cb_contain_end": (52, 7, 55), "dline_cb_rush_contain": (54, 11, 54),
    "dline_s_interior_rusher": (58, 13, 46), "dline_s_stunt_tackle": (56, 14, 50),
    "lb_dline_front_fit_back": (54, 10, 56), "lb_dline_run_fit_captain": (54, 9, 54),
    "lb_cb_nickel_rover": (51, 8, 58), "lb_cb_hook_curl_reader": (50, 7, 56),
    "lb_s_robber_backer": (53, 11, 56), "lb_s_green_dog_blitzer": (58, 15, 50),
    "cb_dline_edge_corner": (52, 8, 56), "cb_dline_force_corner": (55, 10, 52),
    "cb_lb_nickel_matcher": (53, 9, 55), "cb_lb_underneath_bracket": (51, 7, 54),
    "cb_s_deep_half_corner": (54, 8, 50), "cb_s_trail_corner": (57, 15, 50),
    "s_dline_post_safety": (51, 7, 55), "s_dline_blitz_safety": (58, 14, 48),
    "s_lb_box_safety": (57, 11, 50), "s_lb_robber_safety": (54, 12, 52),
    "s_cb_boundary_safety": (52, 9, 58), "s_cb_range_safety": (53, 8, 54),
}


def _basic(position: FootballPosition):
    return next(item for item in PLAYER_TYPES_BY_POSITION[position] if item.partner_position is None)


# -- offers -----------------------------------------------------------------------------


def test_every_offer_is_three_distinct_types_from_its_position() -> None:
    rng = random.Random(5)
    for _ in range(200):
        for position in FootballPosition:
            offer = player_type_offer(position, rng)
            assert len({item.type_id for item in offer}) == 3
            assert all(item.position is position for item in offer)


@pytest.mark.parametrize("position", list(FootballPosition))
def test_all_seven_types_appear_with_equal_odds_in_every_slot(position) -> None:
    rng = random.Random(1234)
    trials = 7000
    seen, slots = Counter(), Counter()
    for _ in range(trials):
        for slot, item in enumerate(player_type_offer(position, rng)):
            seen[item.type_id] += 1
            slots[(item.type_id, slot)] += 1
    assert set(seen) == {item.type_id for item in PLAYER_TYPES_BY_POSITION[position]}
    for type_id, count in seen.items():
        assert count / trials == pytest.approx(3 / 7, abs=0.03), type_id
        for slot in range(3):
            assert slots[(type_id, slot)] / trials == pytest.approx(1 / 7, abs=0.025)
    basic = _basic(position).type_id
    assert slots[(basic, 0)] and slots[(basic, 1)]  # Basic is not pinned last


def test_offers_are_deterministic_for_a_seed() -> None:
    def offers(seed):
        builder = FootballTeamBuilder("Owls", seed)
        builder.choose_coach(0)
        picks = []
        for position in PLAYER_DRAFT_ORDER:
            picks.append(tuple(candidate.player for candidate in builder.current_offer))
            builder.choose_player(position, 0)
        return picks

    assert offers(9) == offers(9)
    assert offers(9) != offers(10)


# -- stats ------------------------------------------------------------------------------


def test_each_type_has_the_approved_base_stats() -> None:
    for player_type in PLAYER_TYPES:
        expected = TABLE.get(player_type.type_id, (46, 12, 45))
        assert player_type.partner_position is not None or player_type.type_id.startswith("basic_")
        assert (player_type.base_power, player_type.base_volatility_pct,
                player_type.base_stamina_pct) == expected
    assert set(TABLE) | {item.type_id for item in BASIC_PLAYER_TYPES} == set(PLAYER_TYPES_BY_ID)


def test_today_score_is_60_and_basic_is_weakest_even_with_the_spread() -> None:
    assert prospect_score(50, 0.10, 0.50) == pytest.approx(60)
    for position, player_types in PLAYER_TYPES_BY_POSITION.items():
        best_basic = prospect_score_range(_basic(position))[1]
        for item in player_types:
            if item.partner_position is not None:
                worst = prospect_score_range(item)[0]
                assert worst > best_basic, (item.type_id, worst, best_basic)
    # The worst roll: base minus the full spread in every stat.
    gap_runner = PLAYER_TYPES_BY_ID["rb_oline_gap_runner"]
    assert prospect_score_range(gap_runner)[0] == pytest.approx(57 + 40 * 0.41 - 15)


def test_catalog_validation_rejects_a_specialist_that_can_roll_below_basic(monkeypatch) -> None:
    weak = replace(PLAYER_TYPES_BY_ID["qb_rb_mesh_reader"], base_power=45)
    patched = dict(PLAYER_TYPES_BY_POSITION)
    patched[FootballPosition.QB] = tuple(
        weak if item.type_id == weak.type_id else item for item in patched[FootballPosition.QB]
    )
    monkeypatch.setattr(catalog, "PLAYER_TYPES_BY_POSITION", MappingProxyType(patched))
    with pytest.raises(RuntimeError, match="weakest overall"):
        catalog._validate_catalog()


def test_spread_stays_within_bounds_over_whole_steps() -> None:
    rng = random.Random(77)
    for player_type in PLAYER_TYPES:
        powers, volatilities, staminas = set(), set(), set()
        for _ in range(300):
            player = roll_prospect(player_type, rng)
            powers.add(player.power - player_type.base_power)
            volatilities.add(round(player.volatility * 100) - player_type.base_volatility_pct)
            staminas.add(round(player.stamina * 100) - player_type.base_stamina_pct)
            assert player.power == int(player.power)
        assert powers == {-2, -1, 0, 1, 2}
        assert volatilities == {-1, 0, 1}
        assert staminas == set(range(-3, 4))


def test_spread_clamps_volatility_and_stamina(monkeypatch) -> None:
    edge = replace(PLAYER_TYPES_BY_ID["basic_qb"], base_volatility_pct=1, base_stamina_pct=99)
    monkeypatch.setattr(catalog, "player_type_for_id", lambda _type_id: edge)

    class Extreme(random.Random):
        def __init__(self, low: bool) -> None:
            super().__init__(0)
            self.low = low

        def randint(self, a, b):
            return a if self.low else b

    low = roll_prospect(edge, Extreme(True))
    high = roll_prospect(edge, Extreme(False))
    assert low.volatility == 0.01  # never below 1%
    assert high.stamina == 1.0  # never above 100%


# -- AI rosters ---------------------------------------------------------------------------


def test_ai_rosters_use_rolled_prospects_and_stay_deterministic() -> None:
    def roster(seed):
        return FootballAI(FootballTeamSide.TEAM_B, FootballAIDifficulty.STANDARD, seed,
                          "Rivals").generate_opponent_roster()

    assert roster(3) == roster(3)
    rosters = [roster(seed) for seed in range(40)]
    assert len({repr(r.players) for r in rosters}) > 1
    basics = sum(
        player.player_type_id.startswith("basic_")
        for r in rosters for player in r.players.values()
    )
    assert basics  # Basic can be drafted now that it is offered like any type
    for r in rosters:
        for player in r.players.values():
            base = player_type_for_id(player.player_type_id)
            assert abs(player.power - base.base_power) <= 2


# -- saves --------------------------------------------------------------------------------


def _mid_draft_controller(seed: int = 4) -> FootballGameController:
    controller = new_controller(seed)
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER[:3]:
        controller.choose_player(position, 0)
    assert controller.state.phase is FootballRunPhase.PLAYER_DRAFT
    return controller


def _offer_players(controller):
    return tuple(candidate.player for candidate in controller.state.team_builder.current_offer)


def test_a_mid_draft_offer_round_trips_with_identical_stats() -> None:
    controller = _mid_draft_controller()
    data = json.loads(json.dumps(controller.to_save_data()))
    offer = data["builder"]["current_offer"]
    assert all(set(item) == {"type_id", "power", "volatility", "stamina"} for item in offer)
    restored = FootballGameController.from_save_data(data)
    assert _offer_players(restored) == _offer_players(controller)
    assert restored._builder._rng.getstate() == controller._builder._rng.getstate()
    # Drafting from the restored offer continues exactly like the original.
    position = controller.state.team_builder.required_position
    assert restored.choose_player(position, 1) == controller.choose_player(position, 1)
    assert _offer_players(restored) == _offer_players(controller)


def test_migration_4_to_5_turns_offered_type_ids_into_base_stat_prospects() -> None:
    controller = _mid_draft_controller()
    run = json.loads(json.dumps(controller.to_save_data()))
    old_offer = ["rb_oline_gap_runner", "rb_qb_checkdown_back", "basic_rb"]
    run["builder"]["current_offer"] = old_offer
    for player in run["builder"]["selected_players"]:  # a version 4 run's uniform players
        player.update(power=50.0, volatility=0.1, stamina=0.5)
    migrated = migrate_payload({"run": run}, 4)
    assert migrated["run"]["builder"]["current_offer"] == [
        {"type_id": "rb_oline_gap_runner", "power": 59.0, "volatility": 0.14, "stamina": 0.44},
        {"type_id": "rb_qb_checkdown_back", "power": 50.0, "volatility": 0.08, "stamina": 0.58},
        {"type_id": "basic_rb", "power": 46.0, "volatility": 0.12, "stamina": 0.45},
    ]
    restored = FootballGameController.from_save_data(migrated["run"])
    offer = restored.state.team_builder.current_offer
    assert [c.player.player_type_id for c in offer] == old_offer  # Basic stays last
    # Drafted players keep their saved 50 / 10% / 50%, never recomputed.
    drafted = restored.state.team_builder.selected_players.values()
    assert drafted and all(
        (p.power, p.volatility, p.stamina) == (50.0, 0.1, 0.5) for p in drafted
    )
    # The coach offer and finished drafts pass through untouched.
    assert migrate_payload({"run": {"builder": {"current_offer": "coach_offer"}}}, 4) == {
        "run": {"builder": {"current_offer": "coach_offer"}}
    }


def test_migration_table_is_the_version_5_catalog() -> None:
    assert migrations._V5_BASE_STATS == {
        item.type_id: (item.base_power, item.base_volatility_pct, item.base_stamina_pct)
        for item in PLAYER_TYPES
    }


# -- the desktop draft ------------------------------------------------------------------


def test_basic_can_be_drafted_by_keyboard_from_any_slot(tmp_path) -> None:
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from test_football_desktop import _activate, _new_desktop, _start_run, _surface

    from src.ui.football_ui_kit import text_audit

    drafted_slots: set[int] = set()
    for seed in range(40):
        desktop = _new_desktop(tmp_path / str(seed), seeds=(seed, seed + 1, seed + 2, seed + 3))
        _start_run(desktop)
        _activate(desktop, "CHOOSE STAFF 01")
        controller = desktop.football_controller
        for position in PLAYER_DRAFT_ORDER:
            offer = [c.player for c in controller.state.team_builder.current_offer]
            slot = next((i for i, p in enumerate(offer) if p.player_type_id.startswith("basic_")), 0)
            is_basic = offer[slot].player_type_id.startswith("basic_")
            if is_basic:
                with text_audit() as records:
                    desktop.router.draw(_surface())
                texts = [text for text, _rect, _box in records]
                assert "No partner" in texts and "Perk: None" in texts
            _activate(desktop, f"DRAFT {position.value}", index=slot, keyboard=True)
            # The drafted player is exactly the card that was focused and drafted.
            assert controller.state.team_builder.selected_players[position] == offer[slot] \
                if controller.state.phase is FootballRunPhase.PLAYER_DRAFT \
                else controller.state.shop.roster.players[position] == offer[slot]
            if is_basic:
                drafted_slots.add(slot)
        if drafted_slots == {0, 1, 2}:
            break
    assert drafted_slots == {0, 1, 2}
