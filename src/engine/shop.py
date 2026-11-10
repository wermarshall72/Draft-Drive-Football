import random
from copy import deepcopy

from src.engine.coaching_actions import (
    ACTION_BY_ID,
    COACHING_ACTIONS,
    POSITIONS,
    CoachingAction,
    Rarity,
)
from src.engine.units import Position, Roster, Unit

AppliedAction = tuple[CoachingAction, Position | None]


class Shop:
    """Coaching-action shop with a twelve-AP budget."""

    DAYS_PER_SHOP = 12
    OPENING_AP = 6
    PORTAL_SIZE = 3
    RARITY_WEIGHTS: tuple[tuple[Rarity, int], ...] = (
        ("Common", 40),
        ("Uncommon", 30),
        ("Rare", 20),
        ("Very Rare", 10),
    )
    MAX_BANKED_AP = 6
    MAX_CARRYOVER_AP = 2
    MAX_PERMANENT_AP = 2
    OPENING_ORDER: tuple[Position, ...] = (
        "QB",
        "RB",
        "WR",
        "OLINE",
        "FRONT7",
        "SECONDARY",
    )
    UNIT_POOL: tuple[
        tuple[str, Position, float, float, float, str], ...
    ] = (
        ("Pocket Passer", "QB", 12.4, 0.14, 0.90, "Top-end power with steady variance and strong stamina."),
        ("Dual-Threat QB", "QB", 12.1, 0.20, 0.78, "Above-average power with moderate variance and stamina."),
        ("Game Manager", "QB", 11.7, 0.10, 0.92, "Lower power traded for the steadiest variance and top stamina."),
        ("Scrambler", "QB", 11.8, 0.28, 0.62, "Lower power with high variance and limited stamina."),
        ("Improviser", "QB", 12.2, 0.30, 0.58, "Near-top power with the highest variance and lowest stamina."),
        ("Rushing QB", "QB", 12.0, 0.26, 0.65, "Midrange power with high variance and limited stamina."),
        ("Power Back", "RB", 11.4, 0.24, 0.72, "Top-end power with above-average variance and lower stamina."),
        ("Receiving Back", "RB", 10.9, 0.18, 0.80, "Middle power, variance, and stamina; a balanced profile."),
        ("One-Cut Runner", "RB", 11.2, 0.12, 0.88, "Strong power, low variance, and high stamina."),
        ("Speed Back", "RB", 10.7, 0.30, 0.56, "Lowest power and stamina, with the highest variance."),
        ("Ball-Security Back", "RB", 10.8, 0.10, 0.94, "Lower power traded for the steadiest variance and top stamina."),
        ("Workhorse Back", "RB", 11.3, 0.19, 0.86, "High power and stamina with moderate variance."),
        ("Deep Threat", "WR", 11.8, 0.30, 0.60, "Near-top power and highest variance, with low stamina."),
        ("Possession Receiver", "WR", 11.5, 0.10, 0.91, "Midrange power with steadiest variance and top stamina."),
        ("Route Technician", "WR", 11.7, 0.16, 0.84, "Top-end power, low variance, and strong stamina."),
        ("YAC Receiver", "WR", 11.4, 0.24, 0.70, "Lower power and stamina with above-average variance."),
        ("Contested-Catch Target", "WR", 11.9, 0.28, 0.64, "Top-end power with high variance and reduced stamina."),
        ("Slot Separator", "WR", 11.2, 0.12, 0.89, "Lower power offset by low variance and high stamina."),
        ("Pass Protector", "OLINE", 13.6, 0.10, 0.94, "Midrange power with steadiest variance and top stamina."),
        ("Run Blocker", "OLINE", 13.9, 0.24, 0.78, "Near-top power with higher variance and lower stamina."),
        ("Zone-Mobility Lineman", "OLINE", 13.2, 0.22, 0.72, "Lowest power with high variance and limited stamina."),
        ("Mauler", "OLINE", 14.0, 0.30, 0.62, "Highest power but highest variance and lowest stamina."),
        ("Anchor Tackle", "OLINE", 13.8, 0.12, 0.90, "High power, low variance, and high stamina."),
        ("Balanced Lineman", "OLINE", 13.5, 0.18, 0.84, "Lower power, with moderate variance and stamina."),
        ("Edge Rusher", "FRONT7", 26.8, 0.30, 0.60, "Top-end power with highest variance and limited stamina."),
        ("Run Stuffer", "FRONT7", 26.7, 0.12, 0.92, "Near-top power with low variance and high stamina."),
        ("Blitzing Linebacker", "FRONT7", 25.8, 0.28, 0.64, "Lower power with high variance and reduced stamina."),
        ("Coverage Linebacker", "FRONT7", 25.3, 0.10, 0.90, "Lowest power offset by steadiest variance and strong stamina."),
        ("Interior Disruptor", "FRONT7", 26.4, 0.23, 0.74, "High power with above-average variance and lower stamina."),
        ("Balanced Front", "FRONT7", 26.0, 0.18, 0.82, "Midrange power and variance with good stamina."),
        ("Shutdown Corner", "SECONDARY", 23.8, 0.12, 0.92, "Top-end power with low variance and high stamina."),
        ("Ball Hawk", "SECONDARY", 22.8, 0.30, 0.58, "Lower power and stamina with the highest variance."),
        ("Press Corner", "SECONDARY", 23.4, 0.26, 0.68, "Strong power with high variance and reduced stamina."),
        ("Zone Safety", "SECONDARY", 23.0, 0.10, 0.94, "Lower power offset by steadiest variance and top stamina."),
        ("Run-Support Safety", "SECONDARY", 22.9, 0.20, 0.80, "Lower power with moderate variance and stamina."),
        ("Nickel Defender", "SECONDARY", 23.3, 0.17, 0.84, "Above-average power with low variance and strong stamina."),
    )
    ROSTER_SLOTS = {
        "QB": "qb",
        "RB": "rb",
        "WR": "wr",
        "OLINE": "oline",
        "FRONT7": "front7",
        "SECONDARY": "secondary",
    }

    def __init__(self, roster: Roster, days: int = DAYS_PER_SHOP) -> None:
        if days < 0:
            raise ValueError("Days cannot be negative.")
        self.roster = roster
        self.days = days
        self.opening_offer: list[Unit] = []
        self.opening_picks = 0
        self.action_offer: list[CoachingAction] = []
        self.action_offer_created = False
        self.permanent_actions: list[AppliedAction] = []
        self.match_actions: list[AppliedAction] = []
        self.selected_this_shop: set[int] = set()
        self.used_run_actions: set[int] = set()
        self.pending_ap = 0
        self.pending_win_ap = 0
        self.permanent_ap = 0
        self.ap_upgrade_positions: set[Position] = set()
        self.carry_unused_ap = False
        self.has_future_shop = True
        self.shop_closed = False
        self.prepared = False
        self.move_count = 0

    def roll_opening_offer(self, position: Position) -> list[Unit]:
        """Offer three random players for the next opening-draft position."""
        if self.opening_picks >= len(self.OPENING_ORDER):
            raise RuntimeError("The opening draft is complete.")
        expected_position = self.OPENING_ORDER[self.opening_picks]
        if position != expected_position:
            raise ValueError(f"The next opening pick must be for {expected_position}.")
        if self.days < 1:
            raise RuntimeError("Not enough Days to make an opening pick.")
        if self.opening_offer:
            raise RuntimeError("Choose a card from the current opening offer first.")

        pool = [choice for choice in self.UNIT_POOL if choice[1] == position]
        self.opening_offer = [
            Unit(
                name=name,
                position=card_position,
                power=power,
                volatility=volatility,
                stamina=stamina,
                description=description,
            )
            for name, card_position, power, volatility, stamina, description in random.sample(
                pool, self.PORTAL_SIZE
            )
        ]
        return list(self.opening_offer)

    def draft_opening_unit(self, unit: Unit) -> None:
        """Select one offered player and spend one opening Action Point."""
        if self.opening_picks >= len(self.OPENING_ORDER):
            raise RuntimeError("The opening draft is complete.")
        if not any(offered is unit for offered in self.opening_offer):
            raise ValueError("Unit must be selected from the current opening offer.")
        if unit.position != self.OPENING_ORDER[self.opening_picks]:
            raise ValueError("Unit does not match the current opening position.")
        if self.days < 1:
            raise RuntimeError("Not enough Days to make an opening pick.")

        self._place_unit(unit)
        self.opening_offer.clear()
        self.opening_picks += 1
        self.days -= 1

    def roll_action_offer(self) -> list[CoachingAction]:
        """Create a three-action offer using the catalog's rarity weights."""
        if self.shop_closed:
            raise RuntimeError("The shop is already closed.")
        if self.action_offer_created:
            raise RuntimeError("Use Move to next day to get another offer.")
        self.action_offer_created = True
        return self._create_action_offer()

    def _create_action_offer(self) -> list[CoachingAction]:
        self.action_offer = []
        self.action_offer_created = True
        offered_ids: set[int] = set()
        for _ in range(self.PORTAL_SIZE):
            eligible = self._eligible_actions()
            eligible = [
                action for action in eligible if action.id not in offered_ids
            ]
            if not eligible:
                break
            available_rarities = {
                action.rarity for action in eligible
            }
            rarities = [
                (rarity, weight)
                for rarity, weight in self.RARITY_WEIGHTS
                if rarity in available_rarities
            ]
            rarity = random.choices(
                [item[0] for item in rarities],
                weights=[item[1] for item in rarities],
                k=1,
            )[0]
            pool = [action for action in eligible if action.rarity == rarity]
            selected = random.choice(pool)
            self.action_offer.append(selected)
            offered_ids.add(selected.id)
        return list(self.action_offer)

    def move_to_next_day(self) -> list[CoachingAction]:
        """Spend one AP to discard the current offer and reveal three actions."""
        if self.days < 1:
            raise RuntimeError("Not enough AP to move to the next day.")
        if self.shop_closed:
            raise RuntimeError("The shop is already closed.")
        self.days -= 1
        self.move_count += 1
        return self._create_action_offer()

    def take_action(
        self,
        action: CoachingAction | int,
        target_position: Position | None = None,
    ) -> None:
        """Purchase an offered action and apply it to this run or match."""
        action_id = action.id if isinstance(action, CoachingAction) else action
        offered = next(
            (item for item in self.action_offer if item.id == action_id), None
        )
        if offered is None:
            raise ValueError("Action must be selected from the current offer.")
        action = ACTION_BY_ID[action_id]
        if action.ap_cost > self.days:
            raise RuntimeError("Not enough AP to take this coaching action.")
        if action.choose_position:
            if target_position not in POSITIONS:
                raise ValueError("This action requires a valid position target.")
        elif target_position is not None:
            raise ValueError("This action does not accept a position target.")
        if action.once_per_run and action_id in self.used_run_actions:
            raise ValueError("This action can only be taken once per run.")
        if action.last_shop_excluded and not self.has_future_shop:
            raise ValueError("This action has no future shop to benefit.")
        if action.position_ap:
            if target_position in self.ap_upgrade_positions:
                raise ValueError("That position already has a permanent AP upgrade.")
            if self.permanent_ap >= self.MAX_PERMANENT_AP:
                raise ValueError("The permanent AP bonus is already at its cap.")
        elif action.permanent_ap and (
            self.permanent_ap + action.permanent_ap > self.MAX_PERMANENT_AP
        ):
            raise ValueError("The permanent AP bonus is already at its cap.")

        self.days -= action.ap_cost
        self.action_offer.remove(offered)
        self.selected_this_shop.add(action_id)
        if action.once_per_run:
            self.used_run_actions.add(action_id)
        if action.duration == "match":
            if action.replaces:
                self.match_actions = [
                    applied
                    for applied in self.match_actions
                    if applied[0].replaces != action.replaces
                ]
            self.match_actions.append((action, target_position))
        elif action.duration == "run":
            self.permanent_actions.append((action, target_position))
        elif action.duration == "next_shop":
            self.pending_ap = min(
                self.MAX_BANKED_AP - self.pending_win_ap,
                self.pending_ap + action.bank_ap,
            )
            self.pending_win_ap = min(
                self.MAX_BANKED_AP - self.pending_ap,
                self.pending_win_ap + action.bank_ap_on_win,
            )
        elif action.duration == "carry":
            self.carry_unused_ap = True

        if action.permanent_ap:
            self.permanent_ap += action.permanent_ap
            if target_position is not None and action.position_ap:
                self.ap_upgrade_positions.add(target_position)

    def finish_shop(self) -> None:
        """Close the shop and bank up to two unused AP if enabled."""
        if self.shop_closed:
            return
        if self.carry_unused_ap:
            self.pending_ap = min(
                self.MAX_BANKED_AP,
                self.pending_ap + min(self.days, self.MAX_CARRYOVER_AP),
            )
        self.days = 0
        self.action_offer.clear()
        self.shop_closed = True
        self.prepared = False

    def prepare_next_shop(self) -> None:
        """Restore the base budget and apply one-time and permanent AP gains."""
        if self.prepared and not self.shop_closed:
            return
        self.days = self.DAYS_PER_SHOP + self.permanent_ap + self.pending_ap
        self.pending_ap = 0
        self.carry_unused_ap = False
        self.selected_this_shop.clear()
        self.action_offer.clear()
        self.match_actions.clear()
        self.move_count = 0
        self.action_offer_created = False
        self.shop_closed = False
        self.prepared = True

    def complete_match(self, won: bool) -> None:
        """Expire match-only effects and bank conditional post-win AP."""
        if won:
            self.pending_ap = min(
                self.MAX_BANKED_AP, self.pending_ap + self.pending_win_ap
            )
        self.pending_win_ap = 0
        self.match_actions.clear()
        self.finish_shop()

    def effective_roster(
        self, include_match_effects: bool = True
    ) -> Roster:
        """Return a roster copy with currently applicable action effects."""
        roster = deepcopy(self.roster)
        selected = self.permanent_actions + (
            self.match_actions if include_match_effects else []
        )
        for position in POSITIONS:
            unit = getattr(roster, self.ROSTER_SLOTS[position])
            run_power = min(
                1.15,
                max(0.85, self._power_modifier(position, self.permanent_actions)),
            )
            match_power = (
                min(
                    1.10,
                    max(0.85, self._power_modifier(position, self.match_actions)),
                )
                if include_match_effects
                else 1.0
            )
            unit.power *= min(1.25, max(0.85, run_power * match_power))
            unit.volatility = min(
                0.45,
                max(
                    0.05,
                    unit.volatility
                    + self._stat_delta(position, "volatility", selected),
                ),
            )
            unit.stamina = min(
                1.0,
                max(
                    0.0,
                    unit.stamina + self._stat_delta(position, "stamina", selected),
                ),
            )

        special_teams = roster.special_teams
        run_swing = self._special_delta("swing_chance", self.permanent_actions)
        match_swing = (
            self._special_delta("swing_chance", self.match_actions)
            if include_match_effects
            else 0.0
        )
        run_swing = min(0.04, max(-0.05, run_swing))
        match_swing = min(0.04, max(-0.05, match_swing))
        special_teams.momentum_swing_chance = min(
            0.20,
            max(
                0.0,
                special_teams.momentum_swing_chance + run_swing + match_swing,
            ),
        )
        special_teams.field_goal_reliability = min(
            1.0,
            max(
                0.0,
                special_teams.field_goal_reliability
                + self._special_delta(
                    "field_goal_reliability", self.permanent_actions
                )
                + (
                    self._special_delta(
                        "field_goal_reliability", self.match_actions
                    )
                    if include_match_effects
                    else 0.0
                ),
            ),
        )
        special_teams.momentum_swing_magnitude = max(
            0.0,
            special_teams.momentum_swing_magnitude
            + self._special_delta("swing_magnitude", self.match_actions)
            if include_match_effects
            else special_teams.momentum_swing_magnitude,
        )
        special_teams.opponent_swing_reduction = max(
            0.0,
            self._special_delta("opponent_swing_reduction", self.match_actions)
            if include_match_effects
            else 0.0,
        )
        drive_count, fatigue_limit = self.match_parameters()
        if not include_match_effects:
            drive_count, fatigue_limit = 10, 0.10
        roster.match_drive_count = drive_count
        roster.match_fatigue_limit = fatigue_limit
        return roster

    def match_parameters(self) -> tuple[int, float]:
        """Return the selected drive count and fatigue limit for this match."""
        drive_count = 10
        fatigue_limit = 0.10
        for action, _ in self.match_actions:
            if action.drive_count is not None:
                drive_count = action.drive_count
            if action.fatigue_limit is not None:
                fatigue_limit = action.fatigue_limit
        return drive_count, fatigue_limit

    def _eligible_actions(self) -> list[CoachingAction]:
        eligible = [
            action
            for action in COACHING_ACTIONS
            if action.ap_cost <= self.days
            and action.id not in self.selected_this_shop
            and not (action.once_per_run and action.id in self.used_run_actions)
            and not (action.last_shop_excluded and not self.has_future_shop)
        ]
        eligible = [
            action
            for action in eligible
            if self.permanent_ap + action.permanent_ap
            <= self.MAX_PERMANENT_AP
        ]
        if len(self.ap_upgrade_positions) >= self.MAX_PERMANENT_AP:
            eligible = [
                action
                for action in eligible
                if not action.position_ap
            ]
        return eligible

    def _power_modifier(
        self, position: Position, actions: list[AppliedAction]
    ) -> float:
        result = 1.0
        for action, target in actions:
            for affected, modifier in action.power:
                if affected == position or (
                    affected == "*" and target == position
                ):
                    result *= modifier
        return result

    @staticmethod
    def _stat_delta(
        position: Position,
        stat: str,
        actions: list[AppliedAction],
    ) -> float:
        result = 0.0
        for action, target in actions:
            effects = getattr(action, stat)
            result += sum(
                value
                for affected, value in effects
                if affected == position or (affected == "*" and target == position)
            )
        return result

    @staticmethod
    def _special_delta(stat: str, actions: list[AppliedAction]) -> float:
        return sum(getattr(action, stat) for action, _ in actions)

    def _place_unit(self, unit: Unit) -> None:
        slot = self.ROSTER_SLOTS.get(unit.position)
        if slot is None:
            raise ValueError(f"Unsupported roster position: {unit.position}")
        setattr(self.roster, slot, unit)
