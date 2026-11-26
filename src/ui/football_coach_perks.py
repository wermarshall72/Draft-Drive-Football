"""Single source for coach-perk wording: a one-line card summary and the full rules.

Every string is built from the coach's own data (``perk.value`` or, for perk-less
coaches, their position modifiers), so the wording cannot drift from the engine.
The short line appears on coach selection cards and Depth Chart coach cards; the
full rules appear only in the coach selection inspect panel.
"""

from __future__ import annotations

from src.engine.football_coaches import FootballCoachPerkKind, FootballCoachProfile


def _number(value: float) -> str:
    return f"{value:g}"


def _percent(value: float) -> str:
    return f"{round(value * 100, 4):g}%"


def _yards(value: float) -> str:
    return f"{_number(value)} {'yd' if value == 1 else 'yds'}"


def _yard_words(value: float) -> str:
    return f"{_number(value)} {'yard' if value == 1 else 'yards'}"


# kind -> (short line, full rules); each receives the perk value.
_PERK_WORDING = {
    FootballCoachPerkKind.FIRST_RUN_YARDS: (
        lambda v: f"First RB Run each drive: +{_yards(v)}",
        lambda v: f"Your first RB Run each drive gains +{_yard_words(v)} unless it is a turnover. "
                  "A turnover still uses the attempt. Resets on the next drive.",
    ),
    FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS: (
        lambda v: f"Going for it on 4th: +{_yards(v)}",
        lambda v: f"When you go for it on fourth down, a run or completed pass gains "
                  f"+{_yard_words(v)} unless it is a turnover. Not used on conversions.",
    ),
    FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS: (
        lambda v: f"First completion each drive: +{_yards(v)}",
        lambda v: f"Your first completed pass each drive gains +{_yard_words(v)}. "
                  "Incompletions and interceptions don't use it. Resets on the next drive.",
    ),
    FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS: (
        lambda v: f"1st-down completions: +{_yards(v)}",
        lambda v: f"Every completed pass called on first down gains +{_yard_words(v)}. "
                  "Not used on conversions.",
    ),
    FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION: (
        lambda v: f"Stopped RB Runs: \u2212{_yards(v)}",
        lambda v: f"When your RB Run defense call stops the opponent's RB Run, the play loses "
                  f"{_yard_words(v)} unless it is a turnover. Applies on every stopped snap.",
    ),
    FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS: (
        lambda v: f"Stopped passes: +{_percent(v)} INT chance",
        lambda v: f"When your defense call stops the opponent's pass play, that pass gets "
                  f"+{_percent(v)} interception chance. Applies on every stopped pass.",
    ),
    FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS: (
        lambda v: f"Stopped passes: +{_percent(v)} incompletion",
        lambda v: f"When your defense call stops the opponent's pass play, that pass gets "
                  f"+{_percent(v)} incompletion chance. Applies on every stopped pass.",
    ),
    FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS: (
        lambda v: f"INT returns: +{_yards(v)}, can score",
        lambda v: f"Interceptions on regular plays gain +{_yard_words(v)} of return. A return "
                  "that reaches the goal line scores a touchdown. Not used on two-point conversions.",
    ),
}


def modifier_text(value: float) -> str:
    """A coach position modifier as '+20%', '\u221210%', or '+0%'."""
    percent = round(value * 100)
    sign = "+" if percent >= 0 else "\u2212"
    return f"{sign}{abs(percent)}%"


def _steady_bonus(coach: FootballCoachProfile) -> str:
    values = set(coach.position_modifiers.values())
    if len(values) == 1:
        value = values.pop()
        return f"{'+' if value >= 0 else '-'}{_percent(abs(value))}"
    return "bonus"


def coach_perk_short(coach: FootballCoachProfile | None) -> str:
    """One card-width line, e.g. 'First RB Run each drive: +3 yds'."""
    if coach is None:
        return "No coach"
    if coach.perk is None:
        return f"No perk · steady {_steady_bonus(coach)} across the unit"
    return _PERK_WORDING[coach.perk.kind][0](coach.perk.value)


def coach_perk_rules(coach: FootballCoachProfile | None) -> str:
    """The complete rules in one to three plain sentences."""
    if coach is None:
        return "No coach is assigned."
    if coach.perk is None:
        return (f"This coach has no special perk. Instead, every position on the unit gets a "
                f"steady {_steady_bonus(coach)}.")
    return _PERK_WORDING[coach.perk.kind][1](coach.perk.value)
