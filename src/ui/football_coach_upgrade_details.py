from src.engine.football import FootballCoachUpgradeKind
from src.engine.football_shop import FootballShopCard


def coach_upgrade_detail_sections(card: FootballShopCard) -> tuple[str, ...]:
    effect = card.coach_upgrade_effect
    if effect is None:
        raise ValueError("Coach upgrade details require a coach-upgrade card.")

    if effect.kind is FootballCoachUpgradeKind.BYE_WEEK:
        duration = "Duration: One scheduled-game skip; no persistent match effect."
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
