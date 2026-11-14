"""Seeded, framework-independent pre-game shop for interactive football."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType

from src.engine.football import FootballPlayer, FootballPosition, FootballRoster

ACTION_POINT_BUDGET = 12
TRAINING_POINT_BUDGET = ACTION_POINT_BUDGET
POWER_UPGRADE_AMOUNT = 1.0
POWER_UPGRADE_COST = 3
STAMINA_UPGRADE_AMOUNT = 0.1
STAMINA_UPGRADE_COST = 2
PLAY_SCHEME_SLOT_COUNT = 4
PLAYER_UPGRADE_SLOT_COUNT = 3
SHOP_OFFER_SIZE = PLAYER_UPGRADE_SLOT_COUNT
MAX_PLAYER_UPGRADE_SLOTS = 4
MAX_PLAY_SCHEME_SLOTS = 6
MAX_COACH_UPGRADE_SLOTS = 2
class FootballShopSection(str, Enum):
    PLAYER_UPGRADES = "player_upgrades"
    PLAYS_SCHEMES = "plays_schemes"
    COACH_UPGRADES = "coach_upgrades"


class FootballShopRarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    VERY_RARE = "very_rare"


RARITY_WEIGHTS = MappingProxyType(
    {
        FootballShopRarity.COMMON: 40,
        FootballShopRarity.UNCOMMON: 30,
        FootballShopRarity.RARE: 20,
        FootballShopRarity.VERY_RARE: 10,
    }
)


class FootballUpgradeStat(str, Enum):
    POWER = "power"
    STAMINA = "stamina"


@dataclass(frozen=True)
class FootballUpgrade:
    """A fixed-cost, single-player stat increase offered by the shop."""

    upgrade_id: str
    name: str
    description: str
    position: FootballPosition
    stat: FootballUpgradeStat
    amount: float
    cost: int
    rarity: FootballShopRarity = FootballShopRarity.COMMON


FootballShopEligibility = Callable[[FootballRoster], bool]
FootballShopEffect = Callable[[FootballRoster], FootballRoster]


@dataclass(frozen=True)
class FootballShopCard:
    """Typed catalog entry shared by future shop sections and live upgrades."""

    card_id: str
    name: str
    description: str
    section: FootballShopSection
    rarity: FootballShopRarity
    cost: int
    eligible: FootballShopEligibility = field(compare=False, repr=False)
    effect: FootballShopEffect = field(compare=False, repr=False)
    upgrade: FootballUpgrade | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.card_id, str) or not self.card_id.strip():
            raise ValueError("Shop card id must be a non-empty string.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Shop card name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Shop card description must be a non-empty string.")
        if not isinstance(self.section, FootballShopSection):
            raise ValueError("Shop card section must be a FootballShopSection.")
        if not isinstance(self.rarity, FootballShopRarity):
            raise ValueError("Shop card rarity must be a FootballShopRarity.")
        if isinstance(self.cost, bool) or not isinstance(self.cost, int) or self.cost <= 0:
            raise ValueError("Shop card cost must be a positive integer.")
        if not callable(self.eligible) or not callable(self.effect):
            raise ValueError("Shop cards must define eligibility and an effect.")
        if self.upgrade is not None and (
            self.section is not FootballShopSection.PLAYER_UPGRADES
            or not isinstance(self.upgrade, FootballUpgrade)
        ):
            raise ValueError("Player upgrade data is only valid for player cards.")
        if self.upgrade is not None and (
            self.card_id != self.upgrade.upgrade_id
            or self.name != self.upgrade.name
            or self.description != self.upgrade.description
            or self.rarity is not self.upgrade.rarity
            or self.cost != self.upgrade.cost
        ):
            raise ValueError("Player card metadata must match its upgrade.")


@dataclass(frozen=True)
class FootballShopSlotState:
    section: FootballShopSection
    slot_number: int
    unlocked: bool
    card: FootballShopCard | None
    purchased: bool
    unlock_cost: int | None
    can_unlock: bool
    disabled_reason: str | None


@dataclass(frozen=True)
class FootballShopSectionState:
    section: FootballShopSection
    title: str
    slots: tuple[FootballShopSlotState, ...]
    catalog_available: bool


@dataclass(frozen=True)
class FootballShopState:
    game_number: int
    day: int
    remaining_ap: int
    sections: tuple[FootballShopSectionState, ...]
    purchased_cards: tuple[FootballShopCard, ...]
    roster: FootballRoster
    finished: bool

    @property
    def remaining_budget(self) -> int:
        """Compatibility alias for callers from the original Training Point shop."""
        return self.remaining_ap

    @property
    def offer(self) -> tuple[FootballUpgrade, ...]:
        section = self.section(FootballShopSection.PLAYER_UPGRADES)
        return tuple(
            slot.card.upgrade
            for slot in section.slots
            if slot.unlocked and slot.card is not None and slot.card.upgrade is not None
        )

    @property
    def purchased_upgrades(self) -> tuple[FootballUpgrade, ...]:
        return tuple(
            card.upgrade
            for card in self.purchased_cards
            if card.upgrade is not None
        )

    def section(self, section: FootballShopSection) -> FootballShopSectionState:
        for state in self.sections:
            if state.section is section:
                return state
        raise ValueError(f"Unknown shop section: {section!r}.")


class FootballShop:
    """Manage a recurring AP shop while keeping upgrades and unlocks for the run."""

    _SECTION_TITLES = {
        FootballShopSection.PLAYER_UPGRADES: "PLAYER UPGRADES",
        FootballShopSection.PLAYS_SCHEMES: "PLAYS / SCHEMES",
        FootballShopSection.COACH_UPGRADES: "COACH UPGRADES",
    }
    _MAX_SLOTS = {
        FootballShopSection.PLAYER_UPGRADES: MAX_PLAYER_UPGRADE_SLOTS,
        FootballShopSection.PLAYS_SCHEMES: MAX_PLAY_SCHEME_SLOTS,
        FootballShopSection.COACH_UPGRADES: MAX_COACH_UPGRADE_SLOTS,
    }
    _UNLOCK_COSTS = {
        (FootballShopSection.PLAYER_UPGRADES, 4): 4,
        (FootballShopSection.PLAYS_SCHEMES, 5): 4,
        (FootballShopSection.PLAYS_SCHEMES, 6): 5,
        (FootballShopSection.COACH_UPGRADES, 1): 4,
        (FootballShopSection.COACH_UPGRADES, 2): 6,
    }
    _DEFAULT_UNLOCKED = {
        FootballShopSection.PLAYER_UPGRADES: PLAYER_UPGRADE_SLOT_COUNT,
        FootballShopSection.PLAYS_SCHEMES: PLAY_SCHEME_SLOT_COUNT,
        FootballShopSection.COACH_UPGRADES: 0,
    }

    def __init__(
        self,
        roster: FootballRoster,
        seed: int | None = None,
        *,
        game_number: int = 1,
        rng: random.Random | None = None,
        catalogs: Mapping[
            FootballShopSection, tuple[FootballShopCard, ...]
        ] | None = None,
        unlocked_slots: Mapping[FootballShopSection, int] | None = None,
    ) -> None:
        if not isinstance(roster, FootballRoster):
            raise ValueError("Shop requires a FootballRoster.")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError("Shop seed must be an integer.")
        if rng is not None and not isinstance(rng, random.Random):
            raise ValueError("Shop RNG must be a random.Random instance.")
        if seed is None and rng is None:
            raise ValueError("Shop requires a seed or an independent RNG.")
        if seed is not None and rng is not None:
            raise ValueError("Provide either a seed or an RNG, not both.")
        if isinstance(game_number, bool) or not isinstance(game_number, int) or game_number < 1:
            raise ValueError("Shop game number must be a positive integer.")

        self.seed = seed
        self._rng = rng if rng is not None else random.Random(seed)
        self._roster = roster
        self._game_number = game_number
        self._day = 1
        self._remaining_ap = ACTION_POINT_BUDGET
        self._purchased: dict[
            tuple[FootballShopSection, str], FootballShopCard
        ] = {}
        self._finished = False
        self._unlocked_slots = self._validated_unlocked_slots(unlocked_slots)
        self._catalogs = self._validated_catalogs(catalogs)
        self._offers: dict[FootballShopSection, list[FootballShopCard | None]] = {}
        self._reset_offers()

    @property
    def remaining_ap(self) -> int:
        return self._remaining_ap

    @property
    def remaining_budget(self) -> int:
        return self._remaining_ap

    @property
    def offer(self) -> tuple[FootballUpgrade, ...]:
        return tuple(
            card.upgrade
            for card in self._offers[FootballShopSection.PLAYER_UPGRADES]
            if card is not None and card.upgrade is not None
        )

    @property
    def purchased_upgrades(self) -> tuple[FootballUpgrade, ...]:
        return tuple(
            card.upgrade
            for card in self._purchased.values()
            if card.upgrade is not None
        )

    @property
    def roster(self) -> FootballRoster:
        return self._roster

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def game_number(self) -> int:
        return self._game_number

    @property
    def unlocked_slots(self) -> Mapping[FootballShopSection, int]:
        return MappingProxyType(dict(self._unlocked_slots))

    @property
    def state(self) -> FootballShopState:
        sections = tuple(self._section_state(section) for section in FootballShopSection)
        return FootballShopState(
            game_number=self._game_number,
            day=self._day,
            remaining_ap=self._remaining_ap,
            sections=sections,
            purchased_cards=tuple(self._purchased.values()),
            roster=self._roster,
            finished=self._finished,
        )

    def buy_upgrade(self, upgrade: FootballUpgrade | int) -> FootballShopState:
        if isinstance(upgrade, bool):
            raise ValueError("Selection must be an offered upgrade or a valid index.")
        player_cards = self._offers[FootballShopSection.PLAYER_UPGRADES]
        if isinstance(upgrade, int):
            offered_cards = [card for card in player_cards if card is not None]
            if not 0 <= upgrade < len(offered_cards):
                raise ValueError("Upgrade offer index is out of range.")
            card = offered_cards[upgrade]
        elif isinstance(upgrade, FootballUpgrade):
            card = next(
                (
                    item
                    for item in player_cards
                    if item is not None and item.upgrade is upgrade
                ),
                None,
            )
            if card is None:
                raise ValueError(
                    "Upgrade was not offered; capped stamina upgrades are excluded."
                )
        else:
            raise ValueError("Selection must be an offered upgrade or a valid index.")
        return self.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)

    def buy(self, upgrade: FootballUpgrade | int) -> FootballShopState:
        """Compatibility alias for the original player-upgrade purchase API."""
        return self.buy_upgrade(upgrade)

    def buy_card(
        self,
        section: FootballShopSection,
        card_id: str | int,
    ) -> FootballShopState:
        self._require_open()
        if not isinstance(section, FootballShopSection):
            raise ValueError("Shop section must be a FootballShopSection.")
        if isinstance(card_id, bool):
            raise ValueError("Card selection must be a card id or valid slot index.")
        slots = self._offers[section]
        if isinstance(card_id, int):
            if not 0 <= card_id < len(slots):
                raise ValueError("Shop card slot index is out of range.")
            selected = slots[card_id]
        elif isinstance(card_id, str):
            selected = next(
                (
                    card
                    for card in slots
                    if card is not None and card.card_id == card_id
                ),
                None,
            )
        else:
            raise ValueError("Card selection must be a card id or valid slot index.")
        if selected is None:
            raise ValueError("Card is not in the current offer.")
        purchase_key = (section, selected.card_id)
        if purchase_key in self._purchased:
            raise ValueError("This card has already been purchased during this visit.")
        if selected.cost > self._remaining_ap:
            raise ValueError("Card cost exceeds the remaining AP.")
        if not selected.eligible(self._roster):
            raise ValueError("Card is no longer eligible for this roster.")

        updated_roster = selected.effect(self._roster)
        if not isinstance(updated_roster, FootballRoster):
            raise ValueError("Shop card effect must return a FootballRoster.")
        self._remaining_ap -= selected.cost
        self._roster = updated_roster
        self._purchased[purchase_key] = selected
        return self.state

    def unlock_slot(
        self,
        section: FootballShopSection,
        slot_number: int,
    ) -> FootballShopState:
        self._require_open()
        if not isinstance(section, FootballShopSection):
            raise ValueError("Shop section must be a FootballShopSection.")
        if isinstance(slot_number, bool) or not isinstance(slot_number, int):
            raise ValueError("Slot number must be an integer.")
        can_unlock, reason = self._unlock_availability(section, slot_number)
        if not can_unlock:
            raise ValueError(reason)
        cost = self._UNLOCK_COSTS[(section, slot_number)]
        if self._remaining_ap < cost:
            raise ValueError(f"Unlocking this slot requires {cost} AP.")

        new_card = self._draw_card(section, self._offers[section])
        self._remaining_ap -= cost
        self._unlocked_slots[section] = slot_number
        self._offers[section].append(new_card)
        return self.state

    def move_to_next_day(self) -> FootballShopState:
        self._require_open()
        if self._remaining_ap < 1:
            raise ValueError("Moving to the next day requires 1 AP.")
        self._reset_offers()
        self._remaining_ap -= 1
        self._day += 1
        return self.state

    def finish(self) -> FootballShopState:
        self._require_open()
        self._finished = True
        return self.state

    def open_next_visit(self, game_number: int) -> FootballShopState:
        if not self._finished:
            raise ValueError("Finish the current shop before opening another visit.")
        if (
            isinstance(game_number, bool)
            or not isinstance(game_number, int)
            or game_number != self._game_number + 1
        ):
            raise ValueError("The next shop must be for the following game.")

        self._game_number = game_number
        self._day = 1
        self._remaining_ap = ACTION_POINT_BUDGET
        self._purchased.clear()
        self._finished = False
        self._reset_offers()
        return self.state

    def _section_state(
        self, section: FootballShopSection
    ) -> FootballShopSectionState:
        unlocked = self._unlocked_slots[section]
        offers = self._offers[section]
        slots: list[FootballShopSlotState] = []
        for slot_number in range(1, self._MAX_SLOTS[section] + 1):
            if slot_number <= unlocked:
                card = offers[slot_number - 1]
                slots.append(
                    FootballShopSlotState(
                        section=section,
                        slot_number=slot_number,
                        unlocked=True,
                        card=card,
                        purchased=(
                            card is not None and (section, card.card_id) in self._purchased
                        ),
                        unlock_cost=None,
                        can_unlock=False,
                        disabled_reason=(
                            None
                            if card is not None
                            else self._empty_slot_reason(section)
                        ),
                    )
                )
                continue
            can_unlock, reason = self._unlock_availability(section, slot_number)
            slots.append(
                FootballShopSlotState(
                    section=section,
                    slot_number=slot_number,
                    unlocked=False,
                    card=None,
                    purchased=False,
                    unlock_cost=self._UNLOCK_COSTS.get((section, slot_number)),
                    can_unlock=can_unlock,
                    disabled_reason=reason,
                )
            )
        return FootballShopSectionState(
            section=section,
            title=self._SECTION_TITLES[section],
            slots=tuple(slots),
            catalog_available=bool(self._catalogs[section]),
        )

    def _unlock_availability(
        self,
        section: FootballShopSection,
        slot_number: int,
    ) -> tuple[bool, str | None]:
        current = self._unlocked_slots[section]
        if slot_number > self._MAX_SLOTS[section]:
            return False, "All slots in this section are already unlocked."
        if slot_number <= current:
            return False, "This slot is already unlocked."
        if slot_number != current + 1:
            return False, f"Unlock slot {current + 1} first."
        if section is FootballShopSection.COACH_UPGRADES and slot_number == 1:
            if self._game_number < 4:
                return False, "Available after game 3."
            if not self._catalogs[section]:
                return False, "Coach upgrades are not available yet."
        elif section is not FootballShopSection.PLAYER_UPGRADES and not self._catalogs[section]:
            return False, "This catalog is not available yet."
        cost = self._UNLOCK_COSTS.get((section, slot_number))
        if cost is None:
            return False, "There is no unlock for this slot."
        if self._remaining_ap < cost:
            return False, f"Need {cost} AP to unlock this slot."
        return True, None

    def _empty_slot_reason(self, section: FootballShopSection) -> str:
        if not self._catalogs[section]:
            if section is FootballShopSection.PLAYS_SCHEMES:
                return "Play and scheme cards are not available yet."
            if section is FootballShopSection.COACH_UPGRADES:
                return "Coach upgrade cards are not available yet."
        return "No eligible cards are available for this slot."

    def _reset_offers(self) -> None:
        self._offers = {
            section: [None] * self._unlocked_slots[section]
            for section in FootballShopSection
        }
        for section in FootballShopSection:
            for slot_index in range(self._unlocked_slots[section]):
                self._offers[section][slot_index] = self._draw_card(
                    section, self._offers[section]
                )

    def _draw_card(
        self,
        section: FootballShopSection,
        current_offer: list[FootballShopCard | None],
    ) -> FootballShopCard | None:
        current_ids = {
            card.card_id for card in current_offer if card is not None
        }
        eligible = [
            card
            for card in self._catalogs[section]
            if (section, card.card_id) not in self._purchased
            and card.card_id not in current_ids
            and card.eligible(self._roster)
        ]
        if not eligible:
            return None

        by_rarity = {
            rarity: [card for card in eligible if card.rarity is rarity]
            for rarity in FootballShopRarity
        }
        available_rarities = [
            rarity for rarity, cards in by_rarity.items() if cards
        ]
        total_weight = sum(RARITY_WEIGHTS[rarity] for rarity in available_rarities)
        roll = self._rng.random() * total_weight
        for rarity in available_rarities:
            roll -= RARITY_WEIGHTS[rarity]
            if roll < 0:
                return self._rng.choice(by_rarity[rarity])
        return self._rng.choice(by_rarity[available_rarities[-1]])

    def _validated_catalogs(
        self,
        catalogs: Mapping[FootballShopSection, tuple[FootballShopCard, ...]] | None,
    ) -> dict[FootballShopSection, tuple[FootballShopCard, ...]]:
        provided = dict(catalogs or {})
        unknown = set(provided) - set(FootballShopSection)
        if unknown:
            raise ValueError(f"Unknown shop catalog sections: {unknown!r}.")
        if FootballShopSection.PLAYER_UPGRADES not in provided:
            provided[FootballShopSection.PLAYER_UPGRADES] = _player_upgrade_catalog()
        validated: dict[FootballShopSection, tuple[FootballShopCard, ...]] = {}
        for section in FootballShopSection:
            cards = tuple(provided.get(section, ()))
            if any(not isinstance(card, FootballShopCard) for card in cards):
                raise ValueError("Shop catalogs may only contain FootballShopCard items.")
            if any(card.section is not section for card in cards):
                raise ValueError("Shop card section does not match its catalog.")
            card_ids = [card.card_id for card in cards]
            if len(card_ids) != len(set(card_ids)):
                raise ValueError(f"Shop catalog contains duplicate ids for {section.value}.")
            validated[section] = cards
        return validated

    def _validated_unlocked_slots(
        self,
        unlocked_slots: Mapping[FootballShopSection, int] | None,
    ) -> dict[FootballShopSection, int]:
        provided = dict(unlocked_slots or {})
        if set(provided) - set(FootballShopSection):
            raise ValueError("Unlocked slots contain an unknown shop section.")
        unlocked = {**self._DEFAULT_UNLOCKED, **provided}
        for section, count in unlocked.items():
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 0 <= count <= self._MAX_SLOTS[section]
            ):
                raise ValueError(f"Invalid unlocked slot count for {section.value}.")
        if unlocked[FootballShopSection.PLAYER_UPGRADES] < PLAYER_UPGRADE_SLOT_COUNT:
            raise ValueError("The three starting player upgrade slots cannot be locked.")
        if unlocked[FootballShopSection.PLAYS_SCHEMES] < PLAY_SCHEME_SLOT_COUNT:
            raise ValueError("The four starting play/scheme slots cannot be locked.")
        return unlocked

    def _require_open(self) -> None:
        if self._finished:
            raise ValueError("The pre-match shop is finished.")


def _player_upgrade_catalog() -> tuple[FootballShopCard, ...]:
    cards: list[FootballShopCard] = []
    for position in FootballPosition:
        power = FootballUpgrade(
            upgrade_id=f"{position.value.lower()}_power",
            name=f"{position.value} power training",
            description=f"Increase {position.value} player power by 1.0.",
            position=position,
            stat=FootballUpgradeStat.POWER,
            amount=POWER_UPGRADE_AMOUNT,
            cost=POWER_UPGRADE_COST,
            rarity=FootballShopRarity.UNCOMMON,
        )
        stamina = FootballUpgrade(
            upgrade_id=f"{position.value.lower()}_stamina",
            name=f"{position.value} stamina training",
            description=f"Increase {position.value} player stamina by 0.1.",
            position=position,
            stat=FootballUpgradeStat.STAMINA,
            amount=STAMINA_UPGRADE_AMOUNT,
            cost=STAMINA_UPGRADE_COST,
            rarity=FootballShopRarity.COMMON,
        )
        cards.extend(
            (
                _player_upgrade_card(power),
                _player_upgrade_card(stamina),
            )
        )
    return tuple(cards)


def _player_upgrade_card(
    upgrade: FootballUpgrade,
) -> FootballShopCard:
    def eligible(current_roster: FootballRoster) -> bool:
        player = current_roster.players[upgrade.position]
        return (
            upgrade.stat is FootballUpgradeStat.POWER
            or player.stamina + upgrade.amount <= 1.0
        )

    def apply(current_roster: FootballRoster) -> FootballRoster:
        player = current_roster.players[upgrade.position]
        if upgrade.stat is FootballUpgradeStat.POWER:
            updated_player = replace(player, power=player.power + upgrade.amount)
        else:
            stamina = player.stamina + upgrade.amount
            if stamina > 1.0:
                raise ValueError(
                    f"{player.position.value} stamina upgrade would exceed the 1.0 maximum."
                )
            updated_player = replace(player, stamina=stamina)
        players = dict(current_roster.players)
        players[upgrade.position] = updated_player
        return FootballRoster(
            team_name=current_roster.team_name,
            players=players,
            coach=current_roster.coach,
            special_teams=current_roster.special_teams,
            coach_assignment=current_roster.coach_assignment,
        )

    return FootballShopCard(
        card_id=upgrade.upgrade_id,
        name=upgrade.name,
        description=upgrade.description,
        section=FootballShopSection.PLAYER_UPGRADES,
        rarity=upgrade.rarity,
        cost=upgrade.cost,
        eligible=eligible,
        effect=apply,
        upgrade=upgrade,
    )
