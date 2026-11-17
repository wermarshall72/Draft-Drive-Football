from src.engine.football import FootballPosition
from src.engine.football_coaches import FootballCoachProfile
from src.engine.football_player_catalog import FootballPlayerType
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


def player_partnership_text(player_type: FootballPlayerType | None) -> tuple[str, str | None]:
    partner = player_type.partner_position if player_type is not None else None
    labels = {
        FootballPosition.QB: "QB", FootballPosition.RB: "RB", FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line", FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebackers",
        FootballPosition.CORNERBACKS: "Cornerbacks", FootballPosition.SAFETIES: "Safeties",
    }
    return (
        f"Partner: {labels[partner] if partner is not None else 'None'}",
        "+10% when both contribute to a play" if partner is not None else None,
    )


def player_perk_text(player_type: FootballPlayerType | None) -> str:
    perk = player_type.perk if player_type is not None else None
    if perk is None:
        return "Perk: None"
    return (f"PLANNED / INACTIVE\nPerk: {perk.name}\nTrigger: {perk.trigger}\n"
            f"Effect: {perk.effect}\nDuration: {perk.duration}\n"
            f"Reset: {perk.reset}\nDependency: {perk.dependency}")
