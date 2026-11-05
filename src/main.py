from src.db.schema import init_db
from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.engine.units import Coach, Roster, SpecialTeams, Unit


def create_starter_team(name: str) -> Roster:
    return Roster(
        player_name=name,
        qb=Unit(name="Walk-on QB", position="QB", power=10.0),
        rb=Unit(name="Walk-on RB", position="RB", power=10.0),
        wr=Unit(name="Walk-on WR", position="WR", power=10.0),
        oline=Unit(name="Walk-on O-Line", position="OLINE", power=10.0),
        front7=Unit(name="Walk-on Front 7", position="FRONT7", power=20.0),
        secondary=Unit(name="Walk-on Secondary", position="SECONDARY", power=20.0),
        coach=Coach(
            name="Head Coach",
            off_scheme="Balanced",
            def_scheme="Balanced",
            off_modifier=1.0,
            def_modifier=1.0,
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


def main() -> None:
    init_db()

    team_name = input("Enter your team name: ").strip()
    while not team_name:
        print("Team name cannot be empty.")
        team_name = input("Enter your team name: ").strip()

    roster = create_starter_team(team_name)
    shop = Shop(roster)
    game = GameRun(roster, shop)

    print(f"\nWelcome, {team_name}! Build your roster and take on the season.")
    while not game.is_game_over():
        game.prep_phase()
        print(f"\n=== Week {game.round_number} | Transfer Portal ===")

        while game.shop.days > 0:
            print(f"\nDays remaining: {game.shop.days}")
            action = input("Enter 1 to Roll Portal or 2 to Skip to Match: ").strip()

            if action == "1":
                portal = game.shop.roll_portal()
                print("\nTransfer portal:")
                for index, unit in enumerate(portal, start=1):
                    print(
                        f"{index}. {unit.name} ({unit.position}) - "
                        f"Power {unit.power:.1f}"
                    )

                while True:
                    selection = input(
                        "Enter 1-3 to draft a unit, or 4 to pass: "
                    ).strip()
                    if selection in {"1", "2", "3"}:
                        drafted_unit = portal[int(selection) - 1]
                        game.shop.draft_unit(drafted_unit)
                        print(f"Drafted {drafted_unit.name}!")
                        break
                    if selection == "4":
                        print("Passed on the portal units.")
                        break
                    print("Please enter 1, 2, 3, or 4.")
            elif action == "2":
                break
            else:
                print("Please enter 1 or 2.")

        print("\n=== Combat ===")
        result = game.combat_phase()
        match_summary = {
            "Final Score": result["final_momentum"],
            "Winner": result["winner"],
        }
        print(match_summary)
        print(f"Record: {game.wins} wins - {game.losses} losses")
        input("Press Enter to continue...")


if __name__ == "__main__":
    main()
