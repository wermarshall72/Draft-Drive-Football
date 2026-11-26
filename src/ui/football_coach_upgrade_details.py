from src.engine.football import FootballCoachUpgradeKind
from src.engine.football_shop import FootballShopCard


def coach_upgrade_detail_sections(card: FootballShopCard) -> tuple[str, ...]:
    effect = card.coach_upgrade_effect
    if effect is None:
        raise ValueError("Coach upgrade details require a coach-upgrade card.")

    if effect.kind is FootballCoachUpgradeKind.BYE_WEEK:
        duration = "Duration: One scheduled-week skip; no persistent match effect."
        uniqueness = "Use: One time per run; this named event cannot be purchased again."
    elif effect.kind is FootballCoachUpgradeKind.FUTURE_SHOP_AP:
        duration = "Duration: Applies to later shops for the remainder of this run."
        uniqueness = "Uniqueness: This named upgrade can be purchased once per run."
    else:
        duration = "Duration: Active for the remainder of this run."
        uniqueness = "Uniqueness: This named upgrade can be purchased once per run."

    return (
        card.name,
        f"Effect: {card.description}",
        duration,
        uniqueness,
        f"Rarity: {card.rarity.value.replace('_', ' ').title()}  /  Cost: {card.cost} AP",
    )


# One short line per coach upgrade for the shop card face, keyed by the stable card_id.
# The full rules stay in the engine description and the inspect popup.
COACH_UPGRADE_SHORT_LINES = {
    "two_minute_drill": "Offense +5% Power",
    "front_seven_film": "Defense +5% Power",
    "rhythm_install": "Offense -15% Volatility",
    "disguise_package": "Defense -15% Volatility",
    "fourth_quarter_conditioning": "Offense +10% Stamina",
    "iron_lungs": "Defense +10% Stamina",
    "booster_club_drive": "+1 AP in every later shop",
    "facilities_fund": "+1 AP in every later shop",
    "bye_week": "Skip this week - no win or loss",
    "tempo_install": "Offensive plays use 10% less clock",
    "huddle_up": "Offensive plays use 10% more clock",
    "vertical_threat": "Deep Pass yardage +10%",
    "pattern_match": "-10% Medium Pass yards allowed when stopped",
    "ball_security_clinic": "-20% interception chance",
    "field_goal_lab": "+5% field goal accuracy",
    "clean_pocket_protection": "-25% punt & FG block chance",
    "punt_return_lane": "+2 yards on punt returns",
    "kickoff_return_lane": "+2 yards on kickoff returns",
}


def coach_upgrade_short_line(card: FootballShopCard) -> str:
    try:
        return COACH_UPGRADE_SHORT_LINES[card.card_id]
    except KeyError:
        raise ValueError(f"No short line is defined for coach upgrade: {card.card_id}") from None


OFFENSE_KINDS = frozenset({
    FootballCoachUpgradeKind.OFFENSE_POWER_BOOST, FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
    FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST, FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
    FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA, FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
})
DEFENSE_KINDS = frozenset({
    FootballCoachUpgradeKind.DEFENSE_POWER_BOOST, FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION,
    FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST, FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
})
SPECIAL_KINDS = frozenset({
    FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS, FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION,
    FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS, FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
})


def coach_upgrade_area(kind: FootballCoachUpgradeKind) -> str:
    """OFFENSE, DEFENSE, SPECIAL TEAMS, or PROGRAM (team-wide AP and Bye Week)."""
    if kind in OFFENSE_KINDS:
        return "OFFENSE"
    if kind in DEFENSE_KINDS:
        return "DEFENSE"
    if kind in SPECIAL_KINDS:
        return "SPECIAL TEAMS"
    return "PROGRAM"
