from src.db.schema import DB_PATH, DatabasePath, init_db
from src.engine.coaching_actions import POSITIONS, CoachingAction
from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.engine.units import (
    Coach,
    Position,
    Roster,
    SpecialTeams,
    Unit,
    random_coach_options,
)


def create_starter_team(name: str, coach: Coach | None = None) -> Roster:
    return Roster(
        player_name=name,
        qb=Unit(name="Walk-on QB", position="QB", power=10.0),
        rb=Unit(name="Walk-on RB", position="RB", power=10.0),
        wr=Unit(name="Walk-on WR", position="WR", power=10.0),
        oline=Unit(name="Walk-on O-Line", position="OLINE", power=10.0),
        front7=Unit(name="Walk-on Front 7", position="FRONT7", power=20.0),
        secondary=Unit(name="Walk-on Secondary", position="SECONDARY", power=20.0),
        coach=coach
        or Coach(
            name="Balanced",
            off_scheme="Balanced",
            def_scheme="Balanced",
        ),
        special_teams=SpecialTeams(),
    )


def build_dummy_team(name: str, coach_off: float, coach_def: float) -> Roster:
    roster = create_starter_team(name)
    roster.qb = Unit(name="Basic QB", position="QB", power=12.0)
    roster.rb = Unit(name="Basic RB", position="RB", power=10.0)
    roster.wr = Unit(name="Basic WR", position="WR", power=10.0)
    roster.oline = Unit(name="Basic OLINE", position="OLINE", power=15.0)
    roster.front7 = Unit(name="Basic FRONT7", position="FRONT7", power=25.0)
    roster.secondary = Unit(name="Basic SEC", position="SECONDARY", power=22.0)
    roster.coach.off_scheme = "Scheme"
    roster.coach.def_scheme = "Scheme"
    roster.coach.off_modifier = coach_off
    roster.coach.def_modifier = coach_def
    return roster


def _choose_coach() -> Coach:
    options = random_coach_options()
    print("\nChoose your coach:")
    for index, coach in enumerate(options, start=1):
        offensive_effects = _format_coach_effects(
            coach, ("QB", "RB", "WR", "OLINE")
        )
        defensive_effects = _format_coach_effects(
            coach, ("FRONT7", "SECONDARY")
        )
        print(
            f"{index}. {coach.name}\n"
            f"   Offense: {coach.off_description} Effects: {offensive_effects}\n"
            f"   Defense: {coach.def_description} Effects: {defensive_effects}"
        )
    while True:
        selection = input("Select 1-3: ").strip()
        if selection in {"1", "2", "3"}:
            return options[int(selection) - 1]
        print("Please enter 1, 2, or 3.")


def _format_coach_effects(
    coach: Coach, positions: tuple[Position, ...]
) -> str:
    labels: dict[Position, str] = {
        "QB": "QB",
        "RB": "RB",
        "WR": "WR",
        "OLINE": "O-Line",
        "FRONT7": "Front 7",
        "SECONDARY": "Secondary",
    }
    effects = [
        f"{labels[position]} x{coach.position_modifiers[position]:.2f}"
        for position in positions
        if coach.position_modifiers.get(position, 1.0) != 1.0
    ]
    return ", ".join(effects) if effects else "all groups x1.00"


def _format_card(card: Unit) -> str:
    stats = (
        f"{card.name} ({card.position}) - Power {card.power:.1f}, "
        f"Volatility {card.volatility:.0%}, Stamina {card.stamina:.0%}"
    )
    return f"{stats} | {card.description}" if card.description else stats


def _format_action(action: CoachingAction) -> str:
    effects: list[str] = []
    for label, modifiers in (
        ("Power", action.power),
        ("Volatility", action.volatility),
        ("Stamina", action.stamina),
    ):
        for position, value in modifiers:
            target = "chosen group" if position == "*" else position
            if label == "Power":
                effect = f"{label} x{value:.2f}"
            else:
                effect = f"{label} {value:+.0%}"
            effects.append(f"{target} {effect}")
    if action.swing_chance:
        effects.append(f"ST swing chance {action.swing_chance:+.0%}")
    if action.field_goal_reliability:
        effects.append(f"FG reliability {action.field_goal_reliability:+.0%}")
    if action.swing_magnitude:
        effects.append(f"ST swing magnitude +{action.swing_magnitude:.0f}")
    if action.opponent_swing_reduction:
        effects.append(
            f"Opponent ST swing reduction "
            f"{action.opponent_swing_reduction:.0f}"
        )
    if action.bank_ap:
        effects.append(f"Next shop +{action.bank_ap} AP")
    if action.bank_ap_on_win:
        effects.append(f"Next shop +{action.bank_ap_on_win} AP on a win")
    if action.permanent_ap:
        effects.append(f"+{action.permanent_ap} AP per future shop")
    if action.carry_unused:
        effects.append("Carry up to 2 unused AP")
    if action.drive_count is not None:
        effects.append(f"{action.drive_count} drives")
    if action.fatigue_limit is not None:
        effects.append(f"Maximum fatigue penalty {action.fatigue_limit:.0%}")
    duration = {
        "match": "next match",
        "run": "permanent for the run",
        "next_shop": "next shop",
        "carry": "through next shop",
    }[action.duration]
    effect_text = "; ".join(effects) if effects else "No direct stat effect"
    return (
        f"{action.name} [{action.rarity}] - {action.ap_cost} AP | "
        f"Target: {action.target} | {effect_text} | {duration}\n"
        f"   {action.description}"
    )


def _print_opening_lineup(roster: Roster) -> None:
    print("\nOpening lineup:")
    for position in Shop.OPENING_ORDER:
        unit = getattr(roster, Shop.ROSTER_SLOTS[position])
        print(f"- {_format_card(unit)}")


def _run_opening_draft(game: GameRun) -> None:
    print("\n=== National Signing Day | Opening Draft ===")
    for position in Shop.OPENING_ORDER:
        offer = game.shop.roll_opening_offer(position)
        print(f"\nChoose your {position}:")
        for index, card in enumerate(offer, start=1):
            print(f"{index}. {_format_card(card)}")

        while True:
            selection = input("Select 1-3: ").strip()
            if selection in {"1", "2", "3"}:
                selected = offer[int(selection) - 1]
                game.shop.draft_opening_unit(selected)
                break
            print("Please enter 1, 2, or 3.")
        print(f"Selected: {_format_card(selected)}")
        print(f"Opening AP remaining: {game.shop.days}")
        print(f"Roster {position}: {selected.name}")


def _run_shop(game: GameRun, phase_title: str) -> None:
    print(f"\n=== {phase_title} | Coaching Staff ===")
    game.shop.roll_action_offer()
    while game.shop.days > 0:
        print(f"\nAP remaining: {game.shop.days}")
        if game.shop.action_offer:
            print("Available coaching actions:")
            for index, action in enumerate(game.shop.action_offer, start=1):
                print(f"{index}. {_format_action(action)}")
        else:
            print("No affordable actions are currently offered.")
        selection = input(
            "Choose an offered action, M to Move to next day (1 AP), "
            "or 0 to finish the shop: "
        ).strip().upper()
        if selection == "0":
            break
        if selection == "M":
            try:
                game.shop.move_to_next_day()
            except RuntimeError as error:
                print(error)
                continue
            print("Moved to the next day. A new coaching offer is available.")
            continue

        if not selection.isdigit():
            print("Please select an offered action, M, or 0.")
            continue
        index = int(selection) - 1
        if not 0 <= index < len(game.shop.action_offer):
            print("That action is not currently offered.")
            continue
        action = game.shop.action_offer[index]
        target_position = None
        if action.choose_position:
            available_positions = [
                position
                for position in POSITIONS
                if not (
                    action.position_ap
                    and position in game.shop.ap_upgrade_positions
                )
            ]
            print("Choose a position: " + ", ".join(available_positions))
            target_position = input("Position: ").strip().upper()
        try:
            game.shop.take_action(action, target_position=target_position)
        except (RuntimeError, ValueError) as error:
            print(error)
            continue
        print(f"Selected {action.name}; {game.shop.days} AP remain.")
    game.shop.finish_shop()


def main(db_path: DatabasePath = DB_PATH) -> None:
    init_db(db_path)

    team_name = input("Enter your team name: ").strip()
    while not team_name:
        print("Team name cannot be empty.")
        team_name = input("Enter your team name: ").strip()

    coach = _choose_coach()
    roster = create_starter_team(team_name, coach)
    shop = Shop(roster, days=Shop.OPENING_AP)
    game = GameRun(roster, shop, db_path=db_path)

    print(
        f"\nWelcome, {team_name}! Coach {coach.name} is locked for this run."
        f"\nNational Signing Day begins with {shop.days} AP."
    )
    _run_opening_draft(game)
    _print_opening_lineup(roster)
    game.start_regular_season()

    while not game.is_game_over():
        if game.phase == "regular_season":
            phase_title = f"Week {game.round_number} of {game.REGULAR_SEASON_GAMES}"
        else:
                phase_title = f"Playoff Round {game.playoff_round} of {game.PLAYOFF_ROUNDS}"
        game.prep_phase()
        _run_shop(game, phase_title)

        print("\n=== Combat ===")
        result = game.combat_phase()
        print(
            f"Winner: {result['winner']} | "
            f"Final momentum: {result['final_momentum']:.1f}"
        )
        print(f"Record: {game.wins} wins - {game.losses} losses")

        if game.phase == "won":
            print("Championship! You won the run.")
        elif game.phase == "lost":
            if game.losses >= game.LOSSES_TO_BE_FIRED and game.playoff_round == 0:
                print("Fired! Your run is over.")
            else:
                print("Eliminated! Your playoff run is over.")
        else:
            input("Press Enter to continue...")


if __name__ == "__main__":
    main()
