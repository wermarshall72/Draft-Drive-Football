"""Formatting for player-upgrade projections and pending effects."""

from src.engine.football_shop import FootballUpgradeStat
from src.engine.football_simulator import MIN_PLAY_YARDAGE_SPREAD
from src.ui.football_player_draft_view import _draft_percentage


VOLATILITY_SPREAD_EXPLANATION = (
    "Volatility is a coached player stat. Play yardage spread depends on contributors "
    f"on both teams and the {MIN_PLAY_YARDAGE_SPREAD:g}-yard minimum; "
    "some plays may not become less variable."
)


def stat_value(stat: FootballUpgradeStat, value: float) -> str:
    value = round(value, 8)
    if stat is FootballUpgradeStat.POWER:
        return f"{value:g}"
    return _draft_percentage(value)


def stat_change(stat: FootballUpgradeStat, change: float) -> str:
    change = round(change, 8)
    if not change:
        return "NO EFFECT"
    if stat is FootballUpgradeStat.POWER:
        return f"{change:+g}"
    return f"{change * 100:+g}%"
