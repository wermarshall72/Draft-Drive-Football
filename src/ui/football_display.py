from src.engine.football import FootballPosition
from src.engine.football_coaches import FootballCoachProfile
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG

_PLAY_LABELS = {
    definition.action: definition.name.upper()
    for definition in OFFENSIVE_PLAY_CATALOG.values()
}
_SCHEME_LABELS = {
    definition.action: definition.name.upper()
    for definition in DEFENSIVE_SCHEME_CATALOG.values()
}

_POSITION_LABELS = {
    FootballPosition.QB: "QB",
    FootballPosition.RB: "RB",
    FootballPosition.WR: "WR",
    FootballPosition.O_LINE: "O-LINE",
    FootballPosition.D_LINE: "D-LINE",
    FootballPosition.LINEBACKERS: "LINEBACKERS",
    FootballPosition.CORNERBACKS: "CORNERBACKS",
    FootballPosition.SAFETIES: "SAFETIES",
}


def _coach_perk_summary(coach: FootballCoachProfile) -> str:
    perk = coach.perk
    if perk is None:
        return "No perk."
    return (
        f"{perk.effect} {perk.trigger} {perk.duration} {perk.reset}"
    )
