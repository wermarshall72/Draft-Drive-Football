from dataclasses import dataclass
from os import PathLike
from typing import Literal

from src.db.schema import DB_PATH, DatabasePath, init_db
from src.engine.coaching_actions import POSITIONS, CoachingAction
from src.engine.game_run import GameRun, RunPhase
from src.engine.shop import Shop
from src.engine.simulator import DriveOutcome, MatchResult
from src.engine.units import (
    Coach,
    Position,
    Roster,
    Unit,
    create_starter_team,
    random_coach_options,
)
from src.profile import (
    PROFILE_PATH,
    TeamProfile,
    load_profile,
    new_team_profile,
    save_profile,
)

RunStep = Literal["coach_selection", "opening_draft", "shop", "match", "terminal"]
RunOutcome = Literal["champion", "fired", "eliminated"]


@dataclass(frozen=True)
class MainMenuState:
    profile: TeamProfile
    available_actions: tuple[str, ...] = ("start_run", "settings", "quit")


@dataclass(frozen=True)
class UnitView:
    name: str
    position: Position
    tier: int
    power: float
    volatility: float
    stamina: float
    synergy_tags: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class CoachView:
    name: str
    off_scheme: str
    def_scheme: str
    off_description: str
    def_description: str
    position_modifiers: tuple[tuple[Position, float], ...]


@dataclass(frozen=True)
class SpecialTeamsView:
    name: str
    tier: int
    momentum_swing_chance: float
    field_goal_reliability: float
    momentum_swing_magnitude: float
    opponent_swing_reduction: float


@dataclass(frozen=True)
class RosterView:
    player_name: str
    players: tuple[UnitView, ...]
    coach: CoachView
    special_teams: SpecialTeamsView


@dataclass(frozen=True)
class RunState:
    step: RunStep
    phase: RunPhase
    roster: RosterView
    coach_choices: tuple[CoachView, ...]
    required_position: Position | None
    opening_offer: tuple[UnitView, ...]
    days_remaining: int
    shop_offer: tuple[CoachingAction, ...]
    available_actions: tuple[str, ...]
    wins: int
    losses: int
    round_number: int
    playoff_round: int
    outcome: RunOutcome | None


@dataclass(frozen=True)
class DriveEventView:
    drive_number: int
    cycle_number: int
    team: str
    opponent: str
    outcome: DriveOutcome
    detail: str
    points: int
    team_a_score: int
    team_b_score: int


@dataclass(frozen=True)
class MatchView:
    team_a: str
    team_b: str
    team_a_score: int
    team_b_score: int
    winner: str
    final_momentum: float
    events: tuple[DriveEventView, ...]


class ApplicationController:
    """Framework-agnostic interface for profile and game-run operations."""

    def __init__(
        self,
        profile_path: str | PathLike[str] = PROFILE_PATH,
        db_path: DatabasePath = DB_PATH,
    ) -> None:
        self.profile_path = profile_path
        self.db_path = db_path
        self._profile: TeamProfile | None = None
        self._coach_choices: tuple[Coach, ...] = ()
        self._roster: Roster | None = None
        self._shop: Shop | None = None
        self._game: GameRun | None = None
        self._step: RunStep | None = None

    def load_profile(self) -> TeamProfile | None:
        self._profile = load_profile(self.profile_path)
        return self._profile

    def create_profile(
        self, team_name: str, primary_color_id: str, secondary_color_id: str
    ) -> TeamProfile:
        profile = new_team_profile(
            team_name, primary_color_id, secondary_color_id
        )
        save_profile(profile, self.profile_path)
        self._profile = profile
        return profile

    def save_profile(self, profile: TeamProfile) -> None:
        save_profile(profile, self.profile_path)
        self._profile = profile

    def main_menu_state(self) -> MainMenuState:
        profile = self._profile if self._profile is not None else self.load_profile()
        if profile is None:
            raise RuntimeError("Load or create a team profile before opening the menu.")
        return MainMenuState(profile=profile)

    def start_run(self) -> RunState:
        profile = self._profile if self._profile is not None else self.load_profile()
        if profile is None:
            raise RuntimeError("Load or create a team profile before starting a run.")
        if self._game is not None and not self._game.is_game_over():
            raise RuntimeError("A run is already in progress.")

        init_db(self.db_path)
        self._coach_choices = tuple(random_coach_options())
        self._roster = create_starter_team(profile.team_name)
        self._shop = Shop(self._roster, days=Shop.OPENING_AP)
        self._game = GameRun(self._roster, self._shop, db_path=self.db_path)
        self._step = "coach_selection"
        return self.run_state()

    def select_coach(self, choice: int) -> RunState:
        self._require_step("coach_selection")
        if (
            not isinstance(choice, int)
            or isinstance(choice, bool)
            or not 1 <= choice <= len(self._coach_choices)
        ):
            raise ValueError(f"Choose a coach from 1 to {len(self._coach_choices)}.")
        roster, _, _ = self._components()
        roster.coach = self._coach_choices[choice - 1]
        self._step = "opening_draft"
        return self.run_state()

    def roll_opening_offer(self) -> tuple[UnitView, ...]:
        self._require_step("opening_draft")
        _, shop, _ = self._components()
        if shop.opening_offer:
            raise RuntimeError("Choose a player from the current opening offer first.")
        position = shop.OPENING_ORDER[shop.opening_picks]
        return tuple(self._unit_view(unit) for unit in shop.roll_opening_offer(position))

    def select_opening_player(self, choice: int) -> RunState:
        self._require_step("opening_draft")
        _, shop, game = self._components()
        if not shop.opening_offer:
            raise RuntimeError("Roll the opening offer before selecting a player.")
        if (
            not isinstance(choice, int)
            or isinstance(choice, bool)
            or not 1 <= choice <= len(shop.opening_offer)
        ):
            raise ValueError(
                f"Choose a player from 1 to {len(shop.opening_offer)} in the current offer."
            )
        shop.draft_opening_unit(shop.opening_offer[choice - 1])
        if shop.opening_picks == len(shop.OPENING_ORDER):
            game.start_regular_season()
            self._step = "shop"
        return self.run_state()

    def roll_action_offer(self) -> RunState:
        self._require_step("shop")
        _, shop, _ = self._components()
        shop.roll_action_offer()
        return self.run_state()

    def buy_action(
        self, action_id: int, target_position: Position | None = None
    ) -> RunState:
        self._require_step("shop")
        _, shop, _ = self._components()
        shop.take_action(action_id, target_position=target_position)
        return self.run_state()

    def available_action_positions(self, action_id: int) -> tuple[Position, ...]:
        self._require_step("shop")
        _, shop, _ = self._components()
        action = next(
            (action for action in shop.action_offer if action.id == action_id), None
        )
        if action is None:
            raise ValueError("Action must be selected from the current offer.")
        if not action.choose_position:
            raise ValueError("This action does not require a position target.")
        if action.position_ap:
            return tuple(
                position
                for position in POSITIONS
                if position not in shop.ap_upgrade_positions
            )
        return POSITIONS

    def move_to_next_day(self) -> RunState:
        self._require_step("shop")
        _, shop, _ = self._components()
        if not shop.action_offer_created:
            raise RuntimeError("Roll the current action offer before moving to the next day.")
        shop.move_to_next_day()
        return self.run_state()

    def finish_shop(self) -> RunState:
        self._require_step("shop")
        _, shop, _ = self._components()
        shop.finish_shop()
        self._step = "match"
        return self.run_state()

    def advance_match(self) -> MatchView:
        self._require_step("match")
        _, _, game = self._components()
        result = game.combat_phase()
        if game.is_game_over():
            self._step = "terminal"
        else:
            game.prep_phase()
            self._step = "shop"
        return self._match_view(result)

    def run_state(self) -> RunState:
        roster, shop, game = self._components()
        opening_offer = tuple(self._unit_view(unit) for unit in shop.opening_offer)
        shop_offer = tuple(shop.action_offer)

        if self._step == "coach_selection":
            required_position = None
            available_actions = ("select_coach",)
        elif self._step == "opening_draft":
            required_position = shop.OPENING_ORDER[shop.opening_picks]
            available_actions = (
                ("select_opening_player",)
                if opening_offer
                else ("roll_opening_offer",)
            )
        elif self._step == "shop":
            required_position = None
            if not shop.action_offer_created:
                available_actions = ("roll_action_offer", "finish_shop")
            else:
                actions = ["buy_action"] if shop.action_offer else []
                if shop.days > 0:
                    actions.append("move_to_next_day")
                actions.append("finish_shop")
                available_actions = tuple(actions)
        elif self._step == "match":
            required_position = None
            available_actions = ("advance_match",)
        else:
            required_position = None
            available_actions = ()

        outcome: RunOutcome | None = None
        if game.phase == "won":
            outcome = "champion"
        elif game.phase == "lost":
            outcome = "fired" if game.playoff_round == 0 else "eliminated"

        return RunState(
            step=self._step or "coach_selection",
            phase=game.phase,
            roster=self._roster_view(roster),
            coach_choices=tuple(
                self._coach_view(coach) for coach in self._coach_choices
            ),
            required_position=required_position,
            opening_offer=opening_offer,
            days_remaining=shop.days,
            shop_offer=shop_offer,
            available_actions=available_actions,
            wins=game.wins,
            losses=game.losses,
            round_number=game.round_number,
            playoff_round=game.playoff_round,
            outcome=outcome,
        )

    def _require_step(self, expected: RunStep) -> None:
        if self._step != expected:
            raise RuntimeError(
                f"This action requires the {expected.replace('_', ' ')} step; "
                f"the current step is {self._step or 'menu'}."
            )

    def _components(self) -> tuple[Roster, Shop, GameRun]:
        if self._roster is None or self._shop is None or self._game is None:
            raise RuntimeError("Start a run before performing game actions.")
        return self._roster, self._shop, self._game

    @staticmethod
    def _unit_view(unit: Unit) -> UnitView:
        return UnitView(
            name=unit.name,
            position=unit.position,
            tier=unit.tier,
            power=unit.power,
            volatility=unit.volatility,
            stamina=unit.stamina,
            synergy_tags=tuple(unit.synergy_tags),
            description=unit.description,
        )

    @classmethod
    def _coach_view(cls, coach: Coach) -> CoachView:
        return CoachView(
            name=coach.name,
            off_scheme=coach.off_scheme,
            def_scheme=coach.def_scheme,
            off_description=coach.off_description,
            def_description=coach.def_description,
            position_modifiers=tuple(coach.position_modifiers.items()),
        )

    @classmethod
    def _roster_view(cls, roster: Roster) -> RosterView:
        special_teams = roster.special_teams
        return RosterView(
            player_name=roster.player_name,
            players=tuple(
                cls._unit_view(getattr(roster, Shop.ROSTER_SLOTS[position]))
                for position in Shop.OPENING_ORDER
            ),
            coach=cls._coach_view(roster.coach),
            special_teams=SpecialTeamsView(
                name=special_teams.name,
                tier=special_teams.tier,
                momentum_swing_chance=special_teams.momentum_swing_chance,
                field_goal_reliability=special_teams.field_goal_reliability,
                momentum_swing_magnitude=special_teams.momentum_swing_magnitude,
                opponent_swing_reduction=special_teams.opponent_swing_reduction,
            ),
        )

    @staticmethod
    def _match_view(result: MatchResult) -> MatchView:
        return MatchView(
            team_a=result["team_a"],
            team_b=result["team_b"],
            team_a_score=result["team_a_score"],
            team_b_score=result["team_b_score"],
            winner=result["winner"],
            final_momentum=result["final_momentum"],
            events=tuple(
                DriveEventView(
                    drive_number=event["drive_number"],
                    cycle_number=event["cycle_number"],
                    team=event["team"],
                    opponent=event["opponent"],
                    outcome=event["outcome"],
                    detail=event["detail"],
                    points=event["points"],
                    team_a_score=event["team_a_score"],
                    team_b_score=event["team_b_score"],
                )
                for event in result["events"]
            ),
        )
