"""Seeded, framework-independent pre-game shop for interactive football."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from src.engine.football_playoffs import FINAL_GAME_NUMBER, REGULAR_SEASON_GAMES
from src.engine.football import (
    FootballBonusCardAction,
    FootballCardCopy,
    FootballCardFamily,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    FootballBonusCardDefinition,
    FootballPlayDefinition,
    FootballSchemeDefinition,
    starting_defensive_deck,
    starting_offensive_deck,
)
from src.engine.football import card_copies_from_save_data, card_copies_to_save_data
from src.engine.football_simulator import coached_player_baseline_stats
from src.engine.save_data import (
    UnsupportedSave,
    build,
    enum_value,
    required,
    items,
    lookup,
    optional,
    rng_from_data,
    rng_to_data,
)

ACTION_POINT_BUDGET = 12
PLAY_SCHEME_SLOT_COUNT = 4
PLAYER_UPGRADE_SLOT_COUNT = 3
MAX_PLAYER_UPGRADE_SLOTS = 4
MAX_PLAY_SCHEME_SLOTS = 6
MAX_COACH_UPGRADE_SLOTS = 2
MAX_FUTURE_SHOP_AP_BONUS = 2
CARD_REMOVAL_COST = 2
MIN_PLAYBOOK_DECK_SIZE = 4
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

PLAY_SCHEME_RARITY_WEIGHTS = MappingProxyType(
    {
        FootballShopRarity.COMMON: 58,
        FootballShopRarity.UNCOMMON: 24,
        FootballShopRarity.RARE: 12,
        FootballShopRarity.VERY_RARE: 6,
    }
)


class FootballUpgradeStat(str, Enum):
    POWER = "power"
    STAMINA = "stamina"
    VOLATILITY = "volatility"


class FootballUpgradeDuration(str, Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"


@dataclass(frozen=True)
class FootballUpgrade:
    """A repeatable single-player stat upgrade."""

    upgrade_id: str
    name: str
    description: str
    position: FootballPosition
    stat: FootballUpgradeStat
    amount: float
    cost: int
    rarity: FootballShopRarity = FootballShopRarity.COMMON
    duration: FootballUpgradeDuration = FootballUpgradeDuration.PERMANENT


@dataclass(frozen=True)
class FootballStatProjection:
    before: float
    after: float

    @property
    def change(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class FootballUpgradeProjection:
    run: FootballStatProjection
    next_match: FootballStatProjection
    effective_next_match: FootballStatProjection


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
    football_card: FootballPlayDefinition | FootballSchemeDefinition | None = None
    bonus_card: FootballBonusCardDefinition | None = None
    is_removal: bool = False
    coach_upgrade_effect: FootballCoachUpgradeEffect | None = None

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
        if not isinstance(self.is_removal, bool):
            raise ValueError("Removal status must be a boolean.")
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
        if self.football_card is not None and (
            self.section is not FootballShopSection.PLAYS_SCHEMES
            or not isinstance(
                self.football_card,
                (FootballPlayDefinition, FootballSchemeDefinition),
            )
        ):
            raise ValueError("Football playbook data is only valid for play/scheme cards.")
        if self.bonus_card is not None and (
            self.section is not FootballShopSection.PLAYS_SCHEMES
            or not isinstance(self.bonus_card, FootballBonusCardDefinition)
            or self.card_id != f"bonus:{self.bonus_card.card_id}"
            or self.name != self.bonus_card.name
        ):
            raise ValueError("Bonus-card data is only valid for matching playbook cards.")
        if self.football_card is not None and self.bonus_card is not None:
            raise ValueError("A shop card cannot be both a play and a bonus card.")
        if self.is_removal and self.section is not FootballShopSection.PLAYS_SCHEMES:
            raise ValueError("Removal offers are only valid in the play/scheme section.")
        if self.section is FootballShopSection.COACH_UPGRADES:
            if (
                not isinstance(
                    self.coach_upgrade_effect, FootballCoachUpgradeEffect
                )
                or self.card_id != self.coach_upgrade_effect.upgrade_id
            ):
                raise ValueError("Coach cards require a matching typed effect.")
        elif self.coach_upgrade_effect is not None:
            raise ValueError("Coach upgrade effects are only valid on coach cards.")


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
    run_purchased_upgrades: tuple[FootballUpgrade, ...]
    offensive_deck: tuple[FootballCardCopy, ...]
    defensive_deck: tuple[FootballCardCopy, ...]
    pending_removal: FootballShopCard | None
    removal_unavailable_reason: str | None
    owned_coach_upgrades: tuple[FootballShopCard, ...] = ()
    future_shop_ap_bonus: int = 0
    pending_player_upgrades: tuple[FootballUpgrade, ...] = ()

    @property
    def next_match_roster(self) -> FootballRoster:
        return apply_player_upgrades(self.roster, self.pending_player_upgrades)

    def coached_player_stats(
        self, roster: FootballRoster, position: FootballPosition
    ) -> tuple[float, float, float]:
        effects = tuple(card.coach_upgrade_effect for card in self.owned_coach_upgrades
                        if card.coach_upgrade_effect is not None)
        return coached_player_baseline_stats(roster, position, effects)

    def coached_player_stat(
        self, roster: FootballRoster, position: FootballPosition, stat: FootballUpgradeStat
    ) -> float:
        index = {FootballUpgradeStat.POWER: 0, FootballUpgradeStat.VOLATILITY: 1,
                 FootballUpgradeStat.STAMINA: 2}[stat]
        return self.coached_player_stats(roster, position)[index]

    def project_player_upgrade(self, upgrade: FootballUpgrade) -> FootballUpgradeProjection:
        """Preview both scopes in the same order used by purchases and matches."""
        before_run = self.roster
        before_match = self.next_match_roster
        if upgrade.duration is FootballUpgradeDuration.PERMANENT:
            after_run = apply_player_upgrade(before_run, upgrade)
            after_match = apply_player_upgrades(after_run, self.pending_player_upgrades)
        else:
            after_run = before_run
            after_match = apply_player_upgrade(before_match, upgrade)

        def value(roster: FootballRoster) -> float:
            return player_upgrade_stat_value(roster.players[upgrade.position], upgrade.stat)

        return FootballUpgradeProjection(
            FootballStatProjection(value(before_run), value(after_run)),
            FootballStatProjection(value(before_match), value(after_match)),
            FootballStatProjection(
                self.coached_player_stat(before_match, upgrade.position, upgrade.stat),
                self.coached_player_stat(after_match, upgrade.position, upgrade.stat),
            ),
        )

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
        return self.run_purchased_upgrades

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
        self._purchased_play_schemes_today: set[str] = set()
        # Play/scheme slots bought today stay visible as purchased until Next Day.
        self._play_slots_purchased: set[int] = set()
        self._run_purchased_upgrades: list[FootballUpgrade] = []
        self._pending_player_upgrades: list[FootballUpgrade] = []
        self._player_offer_purchased: set[str] = set()
        self._owned_coach_upgrades: list[FootballShopCard] = []
        self._future_shop_ap_bonus = 0
        self._offensive_deck = starting_offensive_deck("human")
        self._defensive_deck = starting_defensive_deck("human")
        self._copy_sequence = 1
        self._pending_removal: FootballShopCard | None = None
        self._pending_removal_slot: int | None = None
        self._finished = False
        self._unlocked_slots = self._validated_unlocked_slots(unlocked_slots)
        self._catalogs = self._validated_catalogs(catalogs)
        self._offers: dict[FootballShopSection, list[FootballShopCard | None]] = {}
        self._reset_offers()

    # -- save data -------------------------------------------------------------
    # Saved: every attribute set in ``__init__`` except the catalogs, which are
    # rebuilt from the current game (or the caller's) and resolve every saved
    # card by its stable ID. Purchase sets are stored sorted; they are only used
    # for membership. The RNG is optional because the run controller shares its
    # shop RNG with the shop and saves it once.

    def to_save_data(self, *, include_rng: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "seed": self.seed,
            "roster": self._roster.to_save_data(),
            "game_number": self._game_number,
            "day": self._day,
            "remaining_ap": self._remaining_ap,
            "purchased": [
                [section.value, card_id] for section, card_id in self._purchased
            ],
            "purchased_play_schemes_today": sorted(self._purchased_play_schemes_today),
            "play_slots_purchased": sorted(self._play_slots_purchased),
            "run_purchased_upgrades": [
                upgrade.upgrade_id for upgrade in self._run_purchased_upgrades
            ],
            "pending_player_upgrades": [
                upgrade.upgrade_id for upgrade in self._pending_player_upgrades
            ],
            "player_offer_purchased": sorted(self._player_offer_purchased),
            "owned_coach_upgrades": [card.card_id for card in self._owned_coach_upgrades],
            "future_shop_ap_bonus": self._future_shop_ap_bonus,
            "offensive_deck": card_copies_to_save_data(self._offensive_deck),
            "defensive_deck": card_copies_to_save_data(self._defensive_deck),
            "copy_sequence": self._copy_sequence,
            "pending_removal": (
                self._pending_removal.card_id if self._pending_removal is not None else None
            ),
            "pending_removal_slot": self._pending_removal_slot,
            "finished": self._finished,
            "unlocked_slots": {
                section.value: self._unlocked_slots[section] for section in FootballShopSection
            },
            "offers": {
                section.value: [
                    card.card_id if card is not None else None
                    for card in self._offers[section]
                ]
                for section in FootballShopSection
            },
        }
        if include_rng:
            data["rng"] = rng_to_data(self._rng)
        return data

    @classmethod
    def from_save_data(
        cls,
        data: Any,
        *,
        rng: random.Random | None = None,
        catalogs: Mapping[FootballShopSection, tuple[FootballShopCard, ...]] | None = None,
    ) -> "FootballShop":
        """Restore a shop visit exactly, without drawing new offers.

        ``rng`` supplies a shared generator when the data omits its own.
        """
        what = "Shop"
        shop = cls.__new__(cls)
        shop.seed = optional(data, "seed", int, what)
        if rng is None:
            rng = rng_from_data(required(data, "rng", list, what), "shop RNG")
        shop._rng = rng
        shop._catalogs = build("shop catalogs", lambda: shop._validated_catalogs(catalogs))
        by_id = {
            section: {card.card_id: card for card in cards}
            for section, cards in shop._catalogs.items()
        }

        def card(section: FootballShopSection, card_id: Any) -> FootballShopCard:
            return lookup(by_id[section], card_id, f"{section.value} card")

        def section_of(value: Any) -> FootballShopSection:
            return enum_value(FootballShopSection, value, "shop section")

        def upgrade(upgrade_id: Any) -> FootballUpgrade:
            found = card(FootballShopSection.PLAYER_UPGRADES, upgrade_id).upgrade
            if found is None:
                raise UnsupportedSave(f"Shop card {upgrade_id!r} is not a player upgrade.")
            return found

        def int_set(key: str) -> set[int]:
            values = items(required(data, key, list, what), key)
            if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
                raise UnsupportedSave(f"Shop {key} must list integers.")
            return set(values)

        def str_set(key: str) -> set[str]:
            values = items(required(data, key, list, what), key)
            if any(not isinstance(value, str) for value in values):
                raise UnsupportedSave(f"Shop {key} must list strings.")
            return set(values)

        from src.engine.football import FootballRoster

        shop._roster = FootballRoster.from_save_data(required(data, "roster", dict, what))
        shop._game_number = required(data, "game_number", int, what)
        shop._day = required(data, "day", int, what)
        shop._remaining_ap = required(data, "remaining_ap", int, what)
        shop._purchased = {}
        for entry in items(required(data, "purchased", list, what), "Shop purchases"):
            if not isinstance(entry, list) or len(entry) != 2:
                raise UnsupportedSave("A shop purchase must be [section, card_id].")
            section = section_of(entry[0])
            shop._purchased[(section, entry[1])] = card(section, entry[1])
        shop._purchased_play_schemes_today = str_set("purchased_play_schemes_today")
        shop._play_slots_purchased = int_set("play_slots_purchased")
        shop._run_purchased_upgrades = [
            upgrade(item)
            for item in items(required(data, "run_purchased_upgrades", list, what), "Upgrades")
        ]
        shop._pending_player_upgrades = [
            upgrade(item)
            for item in items(required(data, "pending_player_upgrades", list, what), "Upgrades")
        ]
        shop._player_offer_purchased = str_set("player_offer_purchased")
        shop._owned_coach_upgrades = [
            card(FootballShopSection.COACH_UPGRADES, item)
            for item in items(required(data, "owned_coach_upgrades", list, what), "Upgrades")
        ]
        shop._future_shop_ap_bonus = required(data, "future_shop_ap_bonus", int, what)
        shop._offensive_deck = card_copies_from_save_data(
            required(data, "offensive_deck", list, what), "Offensive deck"
        )
        shop._defensive_deck = card_copies_from_save_data(
            required(data, "defensive_deck", list, what), "Defensive deck"
        )
        shop._copy_sequence = required(data, "copy_sequence", int, what)
        pending = optional(data, "pending_removal", str, what)
        shop._pending_removal = (
            card(FootballShopSection.PLAYS_SCHEMES, pending) if pending is not None else None
        )
        shop._pending_removal_slot = optional(data, "pending_removal_slot", int, what)
        shop._finished = required(data, "finished", bool, what)
        unlocked = required(data, "unlocked_slots", dict, what)
        shop._unlocked_slots = build("unlocked slots", lambda: shop._validated_unlocked_slots(
            {section_of(key): value for key, value in unlocked.items()}
        ))
        offers = required(data, "offers", dict, what)
        shop._offers = {}
        for section in FootballShopSection:
            slots = items(required(offers, section.value, list, what), "Shop offers")
            if len(slots) != shop._unlocked_slots[section]:
                raise UnsupportedSave("Shop offers must fill each unlocked slot.")
            shop._offers[section] = [
                card(section, card_id) if card_id is not None else None
                for card_id in slots
            ]
        return shop

    @property
    def remaining_ap(self) -> int:
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
        return tuple(self._run_purchased_upgrades)

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
    def offensive_deck(self) -> tuple[FootballCardCopy, ...]:
        return self._offensive_deck

    @property
    def defensive_deck(self) -> tuple[FootballCardCopy, ...]:
        return self._defensive_deck

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
            run_purchased_upgrades=tuple(self._run_purchased_upgrades),
            offensive_deck=self._offensive_deck,
            defensive_deck=self._defensive_deck,
            pending_removal=self._pending_removal,
            removal_unavailable_reason=(
                None
                if self._removable_cards()
                else "Both decks are at the 4-card minimum."
            ),
            owned_coach_upgrades=tuple(self._owned_coach_upgrades),
            future_shop_ap_bonus=self._future_shop_ap_bonus,
            pending_player_upgrades=tuple(self._pending_player_upgrades),
        )

    def match_roster(self) -> FootballRoster:
        return apply_player_upgrades(self._roster, self._pending_player_upgrades)

    def complete_match(self) -> None:
        if not self._finished:
            raise ValueError("A match can only complete after the shop is finished.")
        self._pending_player_upgrades.clear()

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
                    "Upgrade was not offered."
                )
        else:
            raise ValueError("Selection must be an offered upgrade or a valid index.")
        return self.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)

    def buy_card(
        self,
        section: FootballShopSection,
        card_id: str | int,
    ) -> FootballShopState:
        self._require_open()
        if self._pending_removal is not None:
            raise ValueError("Finish or cancel the pending card removal first.")
        if not isinstance(section, FootballShopSection):
            raise ValueError("Shop section must be a FootballShopSection.")
        if isinstance(card_id, bool):
            raise ValueError("Card selection must be a card id or valid slot index.")
        slots = self._offers[section]
        slot_index: int | None = None
        if isinstance(card_id, int):
            if not 0 <= card_id < len(slots):
                raise ValueError("Shop card slot index is out of range.")
            selected = slots[card_id]
            slot_index = card_id
        elif isinstance(card_id, str) and section is FootballShopSection.PLAYS_SCHEMES:
            matching = [index for index, card in enumerate(slots)
                        if card is not None and card.card_id == card_id]
            available = [index for index in matching if index not in self._play_slots_purchased]
            slot_index = (available or matching or [None])[0]
            selected = slots[slot_index] if slot_index is not None else None
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
        if (
            section is FootballShopSection.PLAYER_UPGRADES
            and selected.card_id in self._player_offer_purchased
        ) or (
            section is FootballShopSection.PLAYS_SCHEMES
            and slot_index in self._play_slots_purchased
        ) or (
            selected.is_removal
            and purchase_key in self._purchased
        ):
            raise ValueError("This card has already been purchased during this visit.")
        effect = selected.coach_upgrade_effect
        if effect is not None and any(
            card.card_id == effect.upgrade_id
            for card in self._owned_coach_upgrades
        ):
            raise ValueError("This coach upgrade has already been purchased this run.")
        if selected.cost > self._remaining_ap:
            raise ValueError("Card cost exceeds the remaining AP.")
        if not selected.eligible(self._roster):
            raise ValueError("Card is no longer eligible for this roster.")
        if selected.is_removal:
            if not self._removable_cards():
                raise ValueError("Both decks are at the 4-card minimum.")
            if self._pending_removal is not None:
                raise ValueError("A card removal is already pending.")
            self._pending_removal = selected
            self._pending_removal_slot = slot_index
            return self.state

        temporary = (
            selected.upgrade is not None
            and selected.upgrade.duration is FootballUpgradeDuration.TEMPORARY
        )
        updated_roster = self._roster if temporary else selected.effect(self._roster)
        if not isinstance(updated_roster, FootballRoster):
            raise ValueError("Shop card effect must return a FootballRoster.")
        new_copy = None
        if selected.football_card is not None or selected.bonus_card is not None:
            new_copy = FootballCardCopy(
                f"human:purchased:{self._copy_sequence}",
                (
                    selected.football_card.card_id
                    if selected.football_card is not None
                    else selected.bonus_card.card_id
                ),
            )
        self._remaining_ap -= selected.cost
        self._roster = updated_roster
        self._purchased[purchase_key] = selected
        if selected.upgrade is not None:
            self._run_purchased_upgrades.append(selected.upgrade)
            if temporary:
                self._pending_player_upgrades.append(selected.upgrade)
        if section is FootballShopSection.PLAYER_UPGRADES:
            self._player_offer_purchased.add(selected.card_id)
        if section is FootballShopSection.PLAYS_SCHEMES:
            self._mark_play_slot_purchased(selected, slot_index)
        if effect is not None:
            self._owned_coach_upgrades.append(selected)
            if effect.kind is FootballCoachUpgradeKind.FUTURE_SHOP_AP:
                self._future_shop_ap_bonus = min(
                    MAX_FUTURE_SHOP_AP_BONUS,
                    self._future_shop_ap_bonus + int(effect.magnitude),
                )
            if effect.kind is FootballCoachUpgradeKind.BYE_WEEK:
                self._finished = True
        if new_copy is not None:
            if isinstance(selected.football_card, FootballPlayDefinition) or (
                selected.bonus_card is not None
            ):
                self._offensive_deck += (new_copy,)
            else:
                self._defensive_deck += (new_copy,)
            self._copy_sequence += 1
        return self.state

    def remove_owned_card(self, copy_id: str) -> FootballShopState:
        self._require_open()
        pending = self._pending_removal
        if pending is None:
            raise ValueError("Buy the removal offer before selecting a card.")
        if not isinstance(copy_id, str) or not copy_id.strip():
            raise ValueError("Card copy identifier must be a non-empty string.")
        if pending.cost > self._remaining_ap:
            raise ValueError("Card removal cost exceeds the remaining AP.")

        offense_index = next(
            (
                index
                for index, card in enumerate(self._offensive_deck)
                if card.copy_id == copy_id
            ),
            None,
        )
        defense_index = next(
            (
                index
                for index, card in enumerate(self._defensive_deck)
                if card.copy_id == copy_id
            ),
            None,
        )
        if (
            offense_index is not None
            and len(self._offensive_deck) <= MIN_PLAYBOOK_DECK_SIZE
        ):
            raise ValueError("The offensive deck cannot drop below four cards.")
        if (
            defense_index is not None
            and len(self._defensive_deck) <= MIN_PLAYBOOK_DECK_SIZE
        ):
            raise ValueError("The defensive deck cannot drop below four cards.")
        if offense_index is None and defense_index is None:
            raise ValueError("Card copy is not owned by either deck.")

        if offense_index is not None:
            self._offensive_deck = (
                self._offensive_deck[:offense_index]
                + self._offensive_deck[offense_index + 1 :]
            )
        else:
            self._defensive_deck = (
                self._defensive_deck[:defense_index]
                + self._defensive_deck[defense_index + 1 :]
            )
        self._remaining_ap -= pending.cost
        self._purchased[(pending.section, pending.card_id)] = pending
        self._pending_removal = None
        self._mark_play_slot_purchased(pending, self._pending_removal_slot)
        self._pending_removal_slot = None
        return self.state

    def cancel_card_removal(self) -> FootballShopState:
        self._require_open()
        if self._pending_removal is None:
            raise ValueError("There is no card removal to cancel.")
        self._pending_removal = None
        self._pending_removal_slot = None
        return self.state

    def _removable_cards(self) -> tuple[FootballCardCopy, ...]:
        removable = []
        if len(self._offensive_deck) > MIN_PLAYBOOK_DECK_SIZE:
            removable.extend(self._offensive_deck)
        if len(self._defensive_deck) > MIN_PLAYBOOK_DECK_SIZE:
            removable.extend(self._defensive_deck)
        return tuple(removable)

    def _require_no_pending_removal(self) -> None:
        if self._pending_removal is not None:
            raise ValueError("Finish or cancel the pending card removal first.")

    def unlock_slot(
        self,
        section: FootballShopSection,
        slot_number: int,
    ) -> FootballShopState:
        self._require_open()
        self._require_no_pending_removal()
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
        self._require_no_pending_removal()
        if self._remaining_ap < 1:
            raise ValueError("Moving to the next day requires 1 AP.")
        self._player_offer_purchased.clear()
        self._purchased_play_schemes_today.clear()
        self._play_slots_purchased.clear()
        self._reset_offers()
        self._remaining_ap -= 1
        self._day += 1
        return self.state

    def finish(self) -> FootballShopState:
        self._require_open()
        self._require_no_pending_removal()
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
        self._remaining_ap = ACTION_POINT_BUDGET + self._future_shop_ap_bonus
        self._purchased.clear()
        self._player_offer_purchased.clear()
        self._purchased_play_schemes_today.clear()
        self._play_slots_purchased.clear()
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
                            card is not None
                            and (
                                card.card_id in self._player_offer_purchased
                                if section is FootballShopSection.PLAYER_UPGRADES
                                else (
                                    (section, card.card_id) in self._purchased
                                    if card.is_removal
                                    or section is FootballShopSection.COACH_UPGRADES
                                    else slot_number - 1 in self._play_slots_purchased
                                )
                            )
                        ),
                        unlock_cost=None,
                        can_unlock=False,
                        disabled_reason=(
                            self._card_disabled_reason(card)
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

    def _card_disabled_reason(self, card: FootballShopCard) -> str | None:
        if card.is_removal and not self._removable_cards():
            return "Both decks are at the 4-card minimum."
        return None

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

    def _mark_play_slot_purchased(self, purchased: FootballShopCard, slot_index: int | None) -> None:
        """Keep the bought play/scheme/bonus card in its slot until the next reroll."""
        if purchased.football_card is not None:
            self._purchased_play_schemes_today.add(purchased.card_id)
        # Every slot showing the same card is spent: one purchase per card per day.
        self._play_slots_purchased.update(
            index for index, offered in enumerate(self._offers[FootballShopSection.PLAYS_SCHEMES])
            if offered is not None and offered.card_id == purchased.card_id
        )
        if slot_index is not None:
            self._play_slots_purchased.add(slot_index)

    def _draw_card(
        self,
        section: FootballShopSection,
        current_offer: list[FootballShopCard | None],
        *,
        excluded_card_id: str | None = None,
    ) -> FootballShopCard | None:
        current_ids = {
            card.card_id for card in current_offer if card is not None
        }
        eligible = [
            card
            for card in self._catalogs[section]
            if card.card_id != excluded_card_id
            and (
                section is FootballShopSection.PLAYER_UPGRADES
                or section is FootballShopSection.PLAYS_SCHEMES
                or (section, card.card_id) not in self._purchased)
            and (
                section is FootballShopSection.PLAYS_SCHEMES
                or card.card_id not in current_ids
            )
            and not (
                section is FootballShopSection.PLAYS_SCHEMES
                and card.card_id in self._purchased_play_schemes_today
            )
            and self._card_is_available(card)
        ]
        if not eligible:
            return None

        by_rarity = {
            rarity: [card for card in eligible if card.rarity is rarity]
            for rarity in FootballShopRarity
        }
        if section is not FootballShopSection.PLAYS_SCHEMES:
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

        roll = self._rng.random() * 100
        for rarity, weight in PLAY_SCHEME_RARITY_WEIGHTS.items():
            roll -= weight
            if roll < 0:
                rarity_pool = by_rarity[rarity]
                return self._rng.choice(rarity_pool) if rarity_pool else None
        return None

    def _card_is_available(self, card: FootballShopCard) -> bool:
        if card.is_removal and (
            not self._removable_cards()
            # Remove One Card is once per visit: a Next Day reroll (or a new
            # slot unlock) must not offer it again after it was used.
            or (card.section, card.card_id) in self._purchased
        ):
            return False
        effect = card.coach_upgrade_effect
        if effect is not None:
            if any(
                owned.card_id == effect.upgrade_id
                for owned in self._owned_coach_upgrades
            ):
                return False
            # +AP needs a later shop: the last one is before the championship.
            if (
                effect.kind is FootballCoachUpgradeKind.FUTURE_SHOP_AP
                and self._game_number >= FINAL_GAME_NUMBER
            ):
                return False
            # Bye Week skips a scheduled regular-season game, never a playoff game.
            if (
                effect.kind is FootballCoachUpgradeKind.BYE_WEEK
                and self._game_number > REGULAR_SEASON_GAMES
            ):
                return False
        return card.eligible(self._roster)

    def _validated_catalogs(
        self,
        catalogs: Mapping[FootballShopSection, tuple[FootballShopCard, ...]] | None,
    ) -> dict[FootballShopSection, tuple[FootballShopCard, ...]]:
        provided = dict(catalogs or {})
        unknown = set(provided) - set(FootballShopSection)
        if unknown:
            raise ValueError(f"Unknown shop catalog sections: {unknown!r}.")
        if FootballShopSection.PLAYER_UPGRADES not in provided:
            provided[FootballShopSection.PLAYER_UPGRADES] = PLAYER_UPGRADE_CATALOG
        if FootballShopSection.PLAYS_SCHEMES not in provided:
            provided[FootballShopSection.PLAYS_SCHEMES] = _play_scheme_catalog()
        if FootballShopSection.COACH_UPGRADES not in provided:
            provided[FootballShopSection.COACH_UPGRADES] = COACH_UPGRADE_CATALOG
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


def _play_scheme_catalog() -> tuple[FootballShopCard, ...]:
    cards: list[FootballShopCard] = []
    for kind, definitions in (
        ("play", OFFENSIVE_PLAY_CATALOG),
        ("scheme", DEFENSIVE_SCHEME_CATALOG),
    ):
        for definition in definitions.values():
            cards.append(
                FootballShopCard(
                    card_id=f"{kind}:{definition.card_id}",
                    name=definition.name,
                    description=definition.description,
                    section=FootballShopSection.PLAYS_SCHEMES,
                    rarity=FootballShopRarity.COMMON,
                    cost=2,
                    eligible=lambda _roster: True,
                    effect=lambda roster: roster,
                    football_card=definition,
                )
            )
    rarity_by_action = {
        FootballBonusCardAction.OFFENSIVE_DRAW: FootballShopRarity.UNCOMMON,
        FootballBonusCardAction.DEFENSIVE_DRAW: FootballShopRarity.UNCOMMON,
        FootballBonusCardAction.OPPONENT_DISCARD: FootballShopRarity.RARE,
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD: FootballShopRarity.VERY_RARE,
        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD: FootballShopRarity.VERY_RARE,
        FootballBonusCardAction.CHALLENGE: FootballShopRarity.VERY_RARE,
    }
    for definition in BONUS_CARD_CATALOG.values():
        cards.append(
            FootballShopCard(
                card_id=f"bonus:{definition.card_id}",
                name=definition.name,
                description=definition.description,
                section=FootballShopSection.PLAYS_SCHEMES,
                rarity=rarity_by_action[definition.action],
                cost=2,
                eligible=lambda _roster: True,
                effect=lambda roster: roster,
                bonus_card=definition,
            )
        )
    cards.append(
        FootballShopCard(
            card_id="remove-one-card",
            name="Remove One Card",
            description=(
                "Rare shop-only service: choose one owned card to remove "
                "permanently. Costs 2 AP."
            ),
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.RARE,
            cost=CARD_REMOVAL_COST,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            is_removal=True,
        )
    )
    return tuple(cards)


def _playbook_card_rarities() -> Mapping[str, FootballShopRarity]:
    rarities: dict[str, FootballShopRarity] = {}
    for card in _play_scheme_catalog():
        if card.football_card is not None:
            card_id = card.football_card.card_id
        elif card.bonus_card is not None:
            card_id = card.bonus_card.card_id
        else:
            continue
        rarities[card_id] = card.rarity
    return MappingProxyType(rarities)


PLAYBOOK_CARD_RARITIES = _playbook_card_rarities()


def _player_upgrade_catalog() -> tuple[FootballShopCard, ...]:
    cards: list[FootballShopCard] = []
    position_names = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line",
        FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebacker",
        FootballPosition.CORNERBACKS: "Cornerback",
        FootballPosition.SAFETIES: "Safety",
    }
    for position in FootballPosition:
        for stat in FootballUpgradeStat:
            for rank, rarity in enumerate(FootballShopRarity, start=1):
                for duration in FootballUpgradeDuration:
                    factor = 2 if duration is FootballUpgradeDuration.TEMPORARY else 1
                    amount = rank * factor * {
                        FootballUpgradeStat.POWER: 1,
                        FootballUpgradeStat.STAMINA: 0.05,
                        FootballUpgradeStat.VOLATILITY: 0.01,
                    }[stat]
                    amount = round(amount, 4)
                    rarity_name = rarity.value.replace("_", " ").title()
                    duration_name = duration.value.title()
                    position_name = position_names[position]
                    effect = player_upgrade_effect_text(stat, amount)
                    cost = 2 if duration is FootballUpgradeDuration.TEMPORARY else 3
                    lifetime = ("for the next completed match" if factor == 2
                                else "for the rest of the run")
                    bound = {
                        FootballUpgradeStat.POWER: "",
                        FootballUpgradeStat.STAMINA: " Stamina is capped at 100%.",
                        FootballUpgradeStat.VOLATILITY: " Volatility cannot drop below 0%.",
                    }[stat]
                    upgrade = FootballUpgrade(
                        upgrade_id=f"{position.value.lower()}_{stat.value}_{rarity.value}_{duration.value}",
                        name=f"{duration_name} {rarity_name} {position_name} {stat.value.title()} Upgrade",
                        description=f"{position_name}: {effect} {lifetime}.{bound} {cost} AP.",
                        position=position,
                        stat=stat,
                        amount=amount,
                        cost=cost,
                        rarity=rarity,
                        duration=duration,
                    )
                    cards.append(_player_upgrade_card(upgrade))
    return tuple(cards)


def player_upgrade_effect_text(stat: FootballUpgradeStat, amount: float) -> str:
    if stat is FootballUpgradeStat.POWER:
        return f"+{amount:g} Power"
    if stat is FootballUpgradeStat.STAMINA:
        return f"+{amount * 100:g} percentage points Stamina"
    return f"-{amount * 100:g} percentage points Volatility"


def player_upgrade_stat_value(player: FootballPlayer, stat: FootballUpgradeStat) -> float:
    if stat is FootballUpgradeStat.POWER:
        return player.power
    if stat is FootballUpgradeStat.STAMINA:
        return player.stamina
    return player.volatility


def apply_player_upgrade(roster: FootballRoster, upgrade: FootballUpgrade) -> FootballRoster:
    player = roster.players[upgrade.position]
    if upgrade.stat is FootballUpgradeStat.POWER:
        updated_player = replace(player, power=player.power + upgrade.amount)
    elif upgrade.stat is FootballUpgradeStat.STAMINA:
        updated_player = replace(player, stamina=min(1.0, player.stamina + upgrade.amount))
    else:
        updated_player = replace(player, volatility=max(0.0, player.volatility - upgrade.amount))
    players = dict(roster.players)
    players[upgrade.position] = updated_player
    return replace(roster, players=players)


def apply_player_upgrades(
    roster: FootballRoster, upgrades: tuple[FootballUpgrade, ...] | list[FootballUpgrade]
) -> FootballRoster:
    for upgrade in upgrades:
        roster = apply_player_upgrade(roster, upgrade)
    return roster


def _player_upgrade_card(
    upgrade: FootballUpgrade,
) -> FootballShopCard:
    return FootballShopCard(
        card_id=upgrade.upgrade_id,
        name=upgrade.name,
        description=upgrade.description,
        section=FootballShopSection.PLAYER_UPGRADES,
        rarity=upgrade.rarity,
        cost=upgrade.cost,
        eligible=lambda _roster: True,
        effect=lambda roster: apply_player_upgrade(roster, upgrade),
        upgrade=upgrade,
    )


def _coach_upgrade_card(
    upgrade_id: str,
    name: str,
    description: str,
    kind: FootballCoachUpgradeKind,
    magnitude: float,
    rarity: FootballShopRarity,
    cost: int,
    *,
    family: FootballCardFamily | None = None,
) -> FootballShopCard:
    effect = FootballCoachUpgradeEffect(
        upgrade_id=upgrade_id,
        kind=kind,
        magnitude=magnitude,
        family=family,
    )
    return FootballShopCard(
        card_id=upgrade_id,
        name=name,
        description=description,
        section=FootballShopSection.COACH_UPGRADES,
        rarity=rarity,
        cost=cost,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        coach_upgrade_effect=effect,
    )


def _coach_upgrade_catalog() -> tuple[FootballShopCard, ...]:
    uncommon = FootballShopRarity.UNCOMMON
    rare = FootballShopRarity.RARE
    return (
        _coach_upgrade_card(
            "two_minute_drill",
            "Two-Minute Drill",
            "Your QB, RB, WR, and O-line gain +5% power when they contribute. "
            "Relative bonuses stack additively, up to +20%.",
            FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
            0.05,
            uncommon,
            3,
        ),
        _coach_upgrade_card(
            "front_seven_film",
            "Front Seven Film",
            "Your D-line, linebackers, cornerbacks, and safeties gain +5% power "
            "when they contribute. Relative bonuses stack additively, up to +20%.",
            FootballCoachUpgradeKind.DEFENSE_POWER_BOOST,
            0.05,
            uncommon,
            3,
        ),
        _coach_upgrade_card(
            "rhythm_install",
            "Rhythm Install",
            "Reduce volatility of your offensive contributors by 15%, narrowing "
            "play-result spread. Reductions stack additively, capped at 30%.",
            FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
            0.15,
            rare,
            3,
        ),
        _coach_upgrade_card(
            "disguise_package",
            "Disguise Package",
            "Reduce volatility of your defensive contributors by 15%, narrowing "
            "play-result spread. Reductions stack additively, capped at 30%.",
            FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION,
            0.15,
            rare,
            3,
        ),
        _coach_upgrade_card(
            "fourth_quarter_conditioning",
            "Fourth-Quarter Conditioning",
            "Your offensive contributors gain +0.10 effective stamina after "
            "player training. Bonuses stack to +0.30; each player's total is "
            "capped at 1.00.",
            FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST,
            0.10,
            uncommon,
            3,
        ),
        _coach_upgrade_card(
            "iron_lungs",
            "Iron Lungs",
            "Your defensive contributors gain +0.10 effective stamina after "
            "player training. Bonuses stack to +0.30; each player's total is "
            "capped at 1.00.",
            FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST,
            0.10,
            uncommon,
            3,
        ),
        _coach_upgrade_card(
            "booster_club_drive",
            "Booster Club Drive",
            "Add 1 AP to every later shop in this run. Does not change this "
            "shop; future-shop bonuses stack to +2 AP.",
            FootballCoachUpgradeKind.FUTURE_SHOP_AP,
            1,
            rare,
            4,
        ),
        _coach_upgrade_card(
            "facilities_fund",
            "Facilities Fund",
            "Add 1 AP to every later shop in this run. Does not change this "
            "shop; future-shop bonuses stack to +2 AP.",
            FootballCoachUpgradeKind.FUTURE_SHOP_AP,
            1,
            rare,
            5,
        ),
        _coach_upgrade_card(
            "bye_week",
            "Bye Week",
            "Skip this scheduled game without a match result or record change. "
            "Immediately end this shop; this one-time event is available once "
            "per run.",
            FootballCoachUpgradeKind.BYE_WEEK,
            0,
            FootballShopRarity.VERY_RARE,
            6,
        ),
        _coach_upgrade_card(
            "tempo_install",
            "Tempo Install",
            "Normal offensive card plays use 10% less clock, relative to the "
            "printed duration. Changes stack and clamp to 75%-125%; round "
            "half-up to whole seconds, minimum 1. Incomplete passes still use "
            "5 seconds; conversions and special teams keep their timing.",
            FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
            -0.10,
            rare,
            3,
        ),
        _coach_upgrade_card(
            "huddle_up",
            "Huddle Up",
            "Normal offensive card plays use 10% more clock, relative to the "
            "printed duration. Changes stack and clamp to 75%-125%; round "
            "half-up to whole seconds, minimum 1. Incomplete passes still use "
            "5 seconds; conversions and special teams keep their timing.",
            FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
            0.10,
            rare,
            3,
        ),
        _coach_upgrade_card(
            "vertical_threat",
            "Vertical Threat",
            "Deep Pass-family result-calculation yards improve by 10% after "
            "additive perks and before the -5 to 25 yard cap. Negative gains "
            "become 10% less negative; zero stays zero. Opposing family effects "
            "combine additively before the direction is applied. Incomplete "
            "passes and interceptions remain zero; play risks are unchanged.",
            FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
            0.10,
            rare,
            3,
            family=FootballCardFamily.DEEP_PASS,
        ),
        _coach_upgrade_card(
            "pattern_match",
            "Pattern-Match Shell",
            "When your defense selects a Medium Pass-family scheme, reduce "
            "opposing Medium Pass-family result-calculation yards by 10% after "
            "additive perks and before the -5 to 25 yard cap. Negative gains "
            "become 10% more negative; zero stays zero. Opposing family effects "
            "combine additively before the direction is applied. Incomplete "
            "passes and interceptions remain zero; play risks are unchanged.",
            FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
            0.10,
            rare,
            3,
            family=FootballCardFamily.MEDIUM_PASS,
        ),
        _coach_upgrade_card(
            "ball_security_clinic",
            "Ball-Security Clinic",
            "Reduce your offense's conditional interception chance by 20% "
            "relative after matchup and coach adjustments; fumble risk is "
            "unchanged.",
            FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
            0.20,
            rare,
            3,
        ),
        _coach_upgrade_card(
            "field_goal_lab",
            "Field-Goal Lab",
            "Add 5 percentage points to conditional make probability given an "
            "unblocked field goal, at every distance, capped at 100%. "
            "Field-Goal Lab does not change block chance; other upgrades can. "
            "Overall make chance still accounts for the possibility of a block.",
            FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS,
            0.05,
            rare,
            4,
        ),
        _coach_upgrade_card(
            "clean_pocket_protection",
            "Clean-Pocket Protection",
            "Reduce your punt and field-goal block chance by 25% relative. "
            "Reductions stack to a 75% cap. Extra-point block chance is unchanged.",
            FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION,
            0.25,
            uncommon,
            3,
        ),
        _coach_upgrade_card(
            "punt_return_lane",
            "Punt Return Lane",
            "Add 2 yards to each punt return your team makes. Non-scoring "
            "returns stop one yard short of the goal line; return chance is "
            "unchanged.",
            FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS,
            2,
            uncommon,
            2,
        ),
        _coach_upgrade_card(
            "kickoff_return_lane",
            "Kickoff Return Lane",
            "Add 2 yards to each kickoff return your team makes. Non-scoring "
            "returns stop one yard short of the goal line; touchback and "
            "touchdown chances are unchanged.",
            FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
            2,
            uncommon,
            2,
        ),
    )


PLAYER_UPGRADE_CATALOG = _player_upgrade_catalog()
COACH_UPGRADE_CATALOG = _coach_upgrade_catalog()
