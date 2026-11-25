"""Short, pure descriptions of where a remembered run was left, for the main menu."""

from __future__ import annotations

from src.engine.football_controller import FootballGameControllerState, FootballRunPhase
from src.engine.football_playoffs import game_label
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui.football_match_events import period_label


def run_summary(state: FootballGameControllerState) -> str:
    """e.g. ``WEEK 4 · SHOP DAY 2 · 3-0 · HARD`` or ``WEEK 6 · 2ND HALF · 14-10 · HARD``."""
    record = f"{state.wins}-{state.losses}"
    phase = state.phase
    if phase is FootballRunPhase.COACH_DRAFT:
        parts = ["DRAFT", "COACHES"]
    elif phase is FootballRunPhase.PLAYER_DRAFT:
        picked = len(state.team_builder.selected_players)
        parts = ["DRAFT", f"PLAYERS {picked}/{len(PLAYER_DRAFT_ORDER)}"]
    elif phase is FootballRunPhase.PRE_MATCH_SHOP:
        shop = f"SHOP DAY {state.shop.day}" if state.shop is not None else "SHOP"
        parts = [game_label(state.game_number, padded=False), shop, record]
    elif phase is FootballRunPhase.MATCH and state.match is not None:
        match = state.match
        parts = [
            game_label(state.game_number, padded=False),
            period_label(match.period),
            f"{match.team_a_score}-{match.team_b_score}",
        ]
    else:
        parts = [game_label(state.game_number, padded=False), "FINAL", record]
    return " · ".join((*parts, state.opponent_difficulty.value.upper()))


def replace_run_summary(state: FootballGameControllerState) -> str:
    """The compact ``Week 4 · 3-0 · Hard`` used in the replace-run warning."""
    if state.phase in (FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT):
        where = "Draft"
    else:
        where = game_label(state.game_number, padded=False).title()
    return f"{where} · {state.wins}-{state.losses} · {state.opponent_difficulty.value.title()}"
