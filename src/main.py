from src.db.schema import DB_PATH, DatabasePath, init_db
from src.engine.game_run import GameRun
from src.engine.shop import PortalCard, Shop
from src.engine.units import (
    Coach,
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
        print(
            f"{index}. {coach.name} "
            f"(offense x{coach.off_modifier:.2f}, defense x{coach.def_modifier:.2f})"
        )
    while True:
        selection = input("Select 1-3: ").strip()
        if selection in {"1", "2", "3"}:
            return options[int(selection) - 1]
        print("Please enter 1, 2, or 3.")


def _format_card(card: PortalCard) -> str:
    if isinstance(card, Unit):
        return f"{card.name} ({card.position}) - Power {card.power:.1f}"
    return (
        f"{card.name} (Special Teams) - "
        f"Momentum-swing chance {card.momentum_swing_chance:.0%}"
    )


def _run_shop(game: GameRun, phase_title: str) -> None:
    print(f"\n=== {phase_title} | Transfer Portal ===")
    while game.shop.days > 0:
        print(f"\nDays remaining: {game.shop.days}")
        action = input("Enter 1 to Roll Portal or 2 to Finish Shop: ").strip()
        if action == "2":
            return
        if action != "1":
            print("Please enter 1 or 2.")
            continue

        portal = game.shop.roll_portal()
        print("\nTransfer portal:")
        for index, card in enumerate(portal, start=1):
            print(f"{index}. {_format_card(card)}")

        while game.shop.portal:
            selection = input(
                "Enter 1-3 to draft a card, or 4 to keep browsing: "
            ).strip()
            if selection in {"1", "2", "3"}:
                index = int(selection) - 1
                if index >= len(game.shop.portal):
                    print("That card is no longer available.")
                    continue
                card = game.shop.portal[index]
                game.shop.draft_unit(card)
                print(f"Drafted {card.name}!")
                for index, remaining in enumerate(game.shop.portal, start=1):
                    print(f"{index}. {_format_card(remaining)}")
            elif selection == "4":
                break
            else:
                print("Please enter 1, 2, 3, or 4.")


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
    _run_shop(game, "National Signing Day")
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
