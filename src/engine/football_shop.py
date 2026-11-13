"""One-time seeded pre-match Training Point shop for interactive football."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from enum import Enum

from src.engine.football import FootballPlayer, FootballPosition, FootballRoster

TRAINING_POINT_BUDGET = 6
POWER_UPGRADE_AMOUNT = 1.0
POWER_UPGRADE_COST = 3
STAMINA_UPGRADE_AMOUNT = 0.1
STAMINA_UPGRADE_COST = 2
SHOP_OFFER_SIZE = 3


class FootballUpgradeStat(str, Enum):
    POWER = "power"
    STAMINA = "stamina"


@dataclass(frozen=True)
class FootballUpgrade:
    """A fixed-cost, single-player stat increase offered by the pre-match shop."""

    upgrade_id: str
    name: str
    description: str
    position: FootballPosition
    stat: FootballUpgradeStat
    amount: float
    cost: int


@dataclass(frozen=True)
class FootballShopState:
    remaining_budget: int
    offer: tuple[FootballUpgrade, ...]
    purchased_upgrades: tuple[FootballUpgrade, ...]
    roster: FootballRoster
    finished: bool


class FootballShop:
    """Create one immutable offer and apply affordable purchases to new rosters."""

    def __init__(self, roster: FootballRoster, seed: int) -> None:
        if not isinstance(roster, FootballRoster):
            raise ValueError("Shop requires a FootballRoster.")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("Shop seed must be an integer.")

        self.seed = seed
        self._rng = random.Random(seed)
        self._roster = roster
        self._remaining_budget = TRAINING_POINT_BUDGET
        self._purchased: list[FootballUpgrade] = []
        self._finished = False
        self._offer = self._create_offer(roster)

    @property
    def remaining_budget(self) -> int:
        return self._remaining_budget

    @property
    def offer(self) -> tuple[FootballUpgrade, ...]:
        return self._offer

    @property
    def purchased_upgrades(self) -> tuple[FootballUpgrade, ...]:
        return tuple(self._purchased)

    @property
    def roster(self) -> FootballRoster:
        return self._roster

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def state(self) -> FootballShopState:
        return FootballShopState(
            remaining_budget=self.remaining_budget,
            offer=self.offer,
            purchased_upgrades=self.purchased_upgrades,
            roster=self.roster,
            finished=self.finished,
        )

    def buy(self, upgrade: FootballUpgrade | int) -> FootballShopState:
        self._require_open()
        selected = self._offered_upgrade(upgrade)
        if selected in self._purchased:
            raise ValueError("This upgrade has already been purchased.")
        if selected.cost > self._remaining_budget:
            raise ValueError("Upgrade cost exceeds the remaining Training Points.")

        current_player = self._roster.players[selected.position]
        updated_player = self._apply_upgrade(current_player, selected)
        updated_players = dict(self._roster.players)
        updated_players[selected.position] = updated_player
        updated_roster = FootballRoster(
            team_name=self._roster.team_name,
            players=updated_players,
            coach=self._roster.coach,
            special_teams=self._roster.special_teams,
        )

        self._remaining_budget -= selected.cost
        self._purchased.append(selected)
        self._roster = updated_roster
        return self.state

    def finish(self) -> FootballShopState:
        self._require_open()
        self._finished = True
        return self.state

    def _create_offer(self, roster: FootballRoster) -> tuple[FootballUpgrade, ...]:
        catalog = _catalog(roster)
        power_upgrades = [
            upgrade
            for upgrade in catalog
            if upgrade.stat is FootballUpgradeStat.POWER
        ]
        stamina_upgrades = [
            upgrade
            for upgrade in catalog
            if upgrade.stat is FootballUpgradeStat.STAMINA
        ]
        selected_power = self._rng.choice(power_upgrades)
        if stamina_upgrades:
            selected_stamina = self._rng.choice(stamina_upgrades)
        else:
            selected_stamina = self._rng.choice(
                [upgrade for upgrade in power_upgrades if upgrade is not selected_power]
            )
        selected = [selected_power, selected_stamina]
        remaining = [upgrade for upgrade in catalog if upgrade not in selected]
        selected.extend(
            self._rng.sample(remaining, SHOP_OFFER_SIZE - len(selected))
        )
        return tuple(selected)

    def _offered_upgrade(self, upgrade: FootballUpgrade | int) -> FootballUpgrade:
        if isinstance(upgrade, bool):
            raise ValueError("Selection must be an offered upgrade or a valid index.")
        if isinstance(upgrade, int):
            if not 0 <= upgrade < len(self._offer):
                raise ValueError("Upgrade offer index is out of range.")
            return self._offer[upgrade]
        if not isinstance(upgrade, FootballUpgrade):
            raise ValueError("Selection must be an offered upgrade or a valid index.")
        selected = next((item for item in self._offer if item is upgrade), None)
        if selected is None:
            raise ValueError(
                "Upgrade was not offered; capped stamina upgrades are excluded from offers."
            )
        return selected

    @staticmethod
    def _apply_upgrade(
        player: FootballPlayer, upgrade: FootballUpgrade
    ) -> FootballPlayer:
        if upgrade.stat is FootballUpgradeStat.POWER:
            return replace(player, power=player.power + upgrade.amount)
        updated_stamina = player.stamina + upgrade.amount
        if updated_stamina > 1.0:
            raise ValueError(
                f"{player.position.value} stamina upgrade would exceed the 1.0 maximum."
            )
        return replace(player, stamina=updated_stamina)

    def _require_open(self) -> None:
        if self._finished:
            raise ValueError("The pre-match shop is finished.")


def _catalog(roster: FootballRoster) -> tuple[FootballUpgrade, ...]:
    upgrades: list[FootballUpgrade] = []
    for position in FootballPosition:
        player = roster.players[position]
        upgrades.append(
            FootballUpgrade(
                upgrade_id=f"{position.value.lower()}_power",
                name=f"{position.value} power training",
                description=f"Increase {position.value} player power by 1.0.",
                position=position,
                stat=FootballUpgradeStat.POWER,
                amount=POWER_UPGRADE_AMOUNT,
                cost=POWER_UPGRADE_COST,
            )
        )
        if player.stamina + STAMINA_UPGRADE_AMOUNT <= 1.0:
            upgrades.append(
                FootballUpgrade(
                    upgrade_id=f"{position.value.lower()}_stamina",
                    name=f"{position.value} stamina training",
                    description=f"Increase {position.value} player stamina by 0.1.",
                    position=position,
                    stat=FootballUpgradeStat.STAMINA,
                    amount=STAMINA_UPGRADE_AMOUNT,
                    cost=STAMINA_UPGRADE_COST,
                )
            )
    return tuple(upgrades)
