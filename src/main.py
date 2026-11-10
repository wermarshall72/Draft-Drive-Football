from dataclasses import replace
from os import PathLike
from typing import Callable

from src.application import (
    ApplicationController,
    CoachView,
    MatchView,
    MainMenuState,
    RosterView,
    RunState,
    UnitView,
)
from src.db.schema import DB_PATH, DatabasePath
from src.engine.coaching_actions import CoachingAction
from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.engine.units import (
    Coach,
    Position,
    Roster,
    Unit,
    create_starter_team,
)
from src.profile import (
    COLOR_CHOICES,
    PROFILE_PATH,
    ProfileError,
    TeamColor,
    TeamProfile,
    format_color_grid,
    save_profile,
    style_text,
    supports_ansi_color,
    validate_team_name,
)

InputReader = Callable[[str], str]
OutputWriter = Callable[[str], None]


def _read_input(reader: InputReader | None, prompt: str) -> str:
    return (input if reader is None else reader)(prompt)


def _write_output(writer: OutputWriter | None, text: str) -> None:
    (print if writer is None else writer)(text)


def _profile_header(
    text: str, profile: TeamProfile, ansi_enabled: bool | None = None
) -> str:
    return style_text(
        f" {text} ",
        foreground=profile.secondary_color,
        background=profile.primary_color,
        enabled=ansi_enabled,
    )


def _display_team_name(
    name: str, profile: TeamProfile | None, ansi_enabled: bool | None = None
) -> str:
    if profile is None:
        return name
    color = (
        profile.primary_color
        if name == profile.team_name
        else profile.secondary_color
    )
    return style_text(name, foreground=color, enabled=ansi_enabled)


def _prompt_team_name(
    *,
    prompt: str,
    reader: InputReader | None = None,
    writer: OutputWriter | None = None,
) -> str:
    while True:
        try:
            return validate_team_name(_read_input(reader, prompt))
        except ProfileError as error:
            _write_output(writer, str(error))


def _choose_color(
    prompt: str,
    *,
    excluded_color_ids: tuple[str, ...] = (),
    primary_color_id: str | None = None,
    secondary_color_id: str | None = None,
    reader: InputReader | None = None,
    writer: OutputWriter | None = None,
    ansi_enabled: bool | None = None,
) -> TeamColor:
    while True:
        _write_output(
            writer,
            format_color_grid(
                primary_color_id,
                secondary_color_id,
                ansi_enabled=ansi_enabled,
            ),
        )
        selection = _read_input(reader, prompt).strip()
        if not selection.isascii() or not selection.isdecimal():
            _write_output(
                writer,
                f"Please enter a color number from 1 to {len(COLOR_CHOICES)}.",
            )
            continue
        color_number = int(selection)
        if not 1 <= color_number <= len(COLOR_CHOICES):
            _write_output(
                writer,
                f"Please enter a color number from 1 to {len(COLOR_CHOICES)}.",
            )
            continue
        color = COLOR_CHOICES[color_number - 1]
        if color.id in excluded_color_ids:
            _write_output(writer, "Primary and secondary colors must be different.")
            continue
        return color


def _load_or_create_profile(
    profile_path: str | PathLike[str] = PROFILE_PATH,
    *,
    application: ApplicationController | None = None,
    reader: InputReader | None = None,
    writer: OutputWriter | None = None,
    ansi_enabled: bool | None = None,
) -> TeamProfile:
    application = application or ApplicationController(profile_path=profile_path)
    profile = application.load_profile()
    if profile is not None:
        return profile

    _write_output(writer, "\n=== Create your team profile ===")
    team_name = _prompt_team_name(
        prompt="Enter your team name: ", reader=reader, writer=writer
    )
    primary_color = _choose_color(
        "Choose primary color (1-30): ",
        reader=reader,
        writer=writer,
        ansi_enabled=ansi_enabled,
    )
    secondary_color = _choose_color(
        "Choose secondary color (1-30): ",
        excluded_color_ids=(primary_color.id,),
        primary_color_id=primary_color.id,
        reader=reader,
        writer=writer,
        ansi_enabled=ansi_enabled,
    )
    profile = application.create_profile(
        team_name, primary_color.id, secondary_color.id
    )
    _write_output(writer, f"Saved profile for {profile.team_name}.")
    return profile


def _edit_settings(
    profile: TeamProfile,
    profile_path: str | PathLike[str] = PROFILE_PATH,
    *,
    application: ApplicationController | None = None,
    reader: InputReader | None = None,
    writer: OutputWriter | None = None,
    ansi_enabled: bool | None = None,
) -> TeamProfile:
    while True:
        _write_output(
            writer,
            _profile_header(
                f"Settings | {profile.team_name}", profile, ansi_enabled
            ),
        )
        _write_output(
            writer,
            "1. Team name\n"
            "2. Primary color\n"
            "3. Secondary color\n"
            "4. Both colors\n"
            "0. Back",
        )
        selection = _read_input(reader, "Choose a setting: ").strip()
        if selection == "0":
            return profile
        if selection == "1":
            name = _prompt_team_name(
                prompt="Enter your team name: ", reader=reader, writer=writer
            )
            profile = replace(profile, team_name=name)
        elif selection == "2":
            color = _choose_color(
                "Choose primary color (1-30): ",
                excluded_color_ids=(profile.secondary_color_id,),
                primary_color_id=profile.primary_color_id,
                secondary_color_id=profile.secondary_color_id,
                reader=reader,
                writer=writer,
                ansi_enabled=ansi_enabled,
            )
            profile = replace(profile, primary_color_id=color.id)
        elif selection == "3":
            color = _choose_color(
                "Choose secondary color (1-30): ",
                excluded_color_ids=(profile.primary_color_id,),
                primary_color_id=profile.primary_color_id,
                secondary_color_id=profile.secondary_color_id,
                reader=reader,
                writer=writer,
                ansi_enabled=ansi_enabled,
            )
            profile = replace(profile, secondary_color_id=color.id)
        elif selection == "4":
            primary_color = _choose_color(
                "Choose primary color (1-30): ",
                excluded_color_ids=(profile.secondary_color_id,),
                primary_color_id=profile.primary_color_id,
                secondary_color_id=profile.secondary_color_id,
                reader=reader,
                writer=writer,
                ansi_enabled=ansi_enabled,
            )
            secondary_color = _choose_color(
                "Choose secondary color (1-30): ",
                excluded_color_ids=(primary_color.id,),
                primary_color_id=primary_color.id,
                reader=reader,
                writer=writer,
                ansi_enabled=ansi_enabled,
            )
            profile = replace(
                profile,
                primary_color_id=primary_color.id,
                secondary_color_id=secondary_color.id,
            )
        else:
            _write_output(writer, "Please choose 1, 2, 3, 4, or 0.")
            continue
        if application is None:
            save_profile(profile, profile_path)
        else:
            application.save_profile(profile)
        _write_output(writer, "Settings saved.")


def _main_menu_text(
    state: MainMenuState, ansi_enabled: bool | None = None
) -> str:
    profile = state.profile
    header = _profile_header("CFB AUTO-BATTLER", profile, ansi_enabled)
    start_run = style_text(
        "1. Start Run", foreground=profile.primary_color, enabled=ansi_enabled
    )
    settings = style_text(
        "2. Settings",
        foreground=profile.secondary_color,
        enabled=ansi_enabled,
    )
    quit_option = style_text(
        "3. Quit", foreground=profile.primary_color, enabled=ansi_enabled
    )
    team = style_text(
        profile.team_name, foreground=profile.primary_color, enabled=ansi_enabled
    )
    return (
        f"\n{header}\nTeam: {team}\n"
        f"{start_run}\n{settings}\n{quit_option}"
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


def _choose_coach(application: ApplicationController) -> RunState:
    state = application.run_state()
    print("\nChoose your coach:")
    for index, coach in enumerate(state.coach_choices, start=1):
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
            return application.select_coach(int(selection))
        print("Please enter 1, 2, or 3.")


def _format_coach_effects(
    coach: Coach | CoachView, positions: tuple[Position, ...]
) -> str:
    labels: dict[Position, str] = {
        "QB": "QB",
        "RB": "RB",
        "WR": "WR",
        "OLINE": "O-Line",
        "FRONT7": "Front 7",
        "SECONDARY": "Secondary",
    }
    modifiers = dict(coach.position_modifiers)
    effects = [
        f"{labels[position]} x{modifiers[position]:.2f}"
        for position in positions
        if modifiers.get(position, 1.0) != 1.0
    ]
    return ", ".join(effects) if effects else "all groups x1.00"


def _format_card(card: Unit | UnitView) -> str:
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


def _print_opening_lineup(
    roster: Roster | RosterView, profile: TeamProfile | None = None
) -> None:
    heading = "Opening lineup:"
    if profile is not None:
        heading = _profile_header(heading, profile)
    print(f"\n{heading}")
    players = (
        roster.players
        if isinstance(roster, RosterView)
        else tuple(
            getattr(roster, Shop.ROSTER_SLOTS[position])
            for position in Shop.OPENING_ORDER
        )
    )
    for unit in players:
        print(f"- {_format_card(unit)}")


def _run_opening_draft(
    application: ApplicationController, profile: TeamProfile | None = None
) -> None:
    heading = "=== National Signing Day | Opening Draft ==="
    if profile is not None:
        heading = _profile_header(heading, profile)
    print(f"\n{heading}")
    state = application.run_state()
    while state.step == "opening_draft":
        position = state.required_position
        assert position is not None
        offer = application.roll_opening_offer()
        print(f"\nChoose your {position}:")
        for index, card in enumerate(offer, start=1):
            print(f"{index}. {_format_card(card)}")

        while True:
            selection = input("Select 1-3: ").strip()
            if selection in {"1", "2", "3"}:
                selected = offer[int(selection) - 1]
                state = application.select_opening_player(int(selection))
                break
            print("Please enter 1, 2, or 3.")
        print(f"Selected: {_format_card(selected)}")
        opening_days = 0 if state.step != "opening_draft" else state.days_remaining
        print(f"Opening AP remaining: {opening_days}")
        print(f"Roster {position}: {selected.name}")
    _print_opening_lineup(state.roster, profile)


def _run_shop(
    application: ApplicationController,
    phase_title: str,
    profile: TeamProfile | None = None,
) -> None:
    heading = f"=== {phase_title} | Coaching Staff ==="
    if profile is not None:
        heading = _profile_header(heading, profile)
    print(f"\n{heading}")
    state = application.roll_action_offer()
    while state.days_remaining > 0:
        print(f"\nAP remaining: {state.days_remaining}")
        if state.shop_offer:
            print("Available coaching actions:")
            for index, action in enumerate(state.shop_offer, start=1):
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
                state = application.move_to_next_day()
            except RuntimeError as error:
                print(error)
                continue
            print("Moved to the next day. A new coaching offer is available.")
            continue

        if not selection.isdigit():
            print("Please select an offered action, M, or 0.")
            continue
        index = int(selection) - 1
        if not 0 <= index < len(state.shop_offer):
            print("That action is not currently offered.")
            continue
        action = state.shop_offer[index]
        target_position = None
        if action.choose_position:
            available_positions = application.available_action_positions(
                action.id
            )
            print("Choose a position: " + ", ".join(available_positions))
            target_position = input("Position: ").strip().upper()
        try:
            state = application.buy_action(
                action.id, target_position=target_position
            )
        except (RuntimeError, ValueError) as error:
            print(error)
            continue
        print(f"Selected {action.name}; {state.days_remaining} AP remain.")
    application.finish_shop()


def _print_match_result(
    result: MatchView, profile: TeamProfile | None = None
) -> None:
    team_a = result.team_a
    team_b = result.team_b
    print(
        f"\n{_display_team_name(team_a, profile)} vs "
        f"{_display_team_name(team_b, profile)}"
    )
    for event in result.events:
        print(
            f"Drive {event.drive_number:02d} | "
            f"{_display_team_name(event.team, profile)}: "
            f"{event.detail}"
        )
        print(
            f"   Score: {_display_team_name(team_a, profile)} "
            f"{event.team_a_score} - "
            f"{_display_team_name(team_b, profile)} {event.team_b_score}"
        )

    print(
        f"Final score: {_display_team_name(team_a, profile)} "
        f"{result.team_a_score} - "
        f"{_display_team_name(team_b, profile)} {result.team_b_score}"
    )
    print(f"Winner: {_display_team_name(result.winner, profile)}")
    if result.final_momentum > 0:
        momentum_leader = team_a
    elif result.final_momentum < 0:
        momentum_leader = team_b
    else:
        momentum_leader = "Neither team"
    print(
        f"Final momentum: {result.final_momentum:+.1f} "
        f"({_display_team_name(momentum_leader, profile)} favored)"
    )


def _start_run(
    application: ApplicationController,
    profile: TeamProfile,
    ansi_enabled: bool | None = None,
) -> None:
    application.start_run()
    state = _choose_coach(application)
    coach = state.roster.coach

    print(
        f"\nWelcome, {_display_team_name(profile.team_name, profile, ansi_enabled)}! "
        f"Coach {coach.name} is locked for this run."
        f"\nNational Signing Day begins with {state.days_remaining} AP."
    )
    _run_opening_draft(application, profile)
    state = application.run_state()

    while state.outcome is None:
        if state.phase == "regular_season":
            phase_title = (
                f"Week {state.round_number} of {GameRun.REGULAR_SEASON_GAMES}"
            )
        else:
            phase_title = (
                f"Playoff Round {state.playoff_round} of {GameRun.PLAYOFF_ROUNDS}"
            )
        _run_shop(application, phase_title, profile)

        print("\n=== Combat ===")
        result = application.advance_match()
        _print_match_result(result, profile)
        state = application.run_state()
        print(f"Record: {state.wins} wins - {state.losses} losses")

        if state.outcome == "champion":
            print("Championship! You won the run.")
        elif state.outcome == "fired":
            print("Fired! Your run is over.")
        elif state.outcome == "eliminated":
            print("Eliminated! Your playoff run is over.")
        else:
            input("Press Enter to continue...")


def main(
    db_path: DatabasePath = DB_PATH,
    profile_path: str | PathLike[str] = PROFILE_PATH,
) -> None:
    application = ApplicationController(profile_path, db_path)
    profile = _load_or_create_profile(
        profile_path, application=application
    )
    ansi_enabled = supports_ansi_color()
    while True:
        menu_state = application.main_menu_state()
        print(_main_menu_text(menu_state, ansi_enabled))
        selection = input("Choose an option: ").strip()
        menu_action = dict(
            zip(("1", "2", "3"), menu_state.available_actions)
        ).get(selection)
        if menu_action == "start_run":
            _start_run(application, profile, ansi_enabled)
        elif menu_action == "settings":
            profile = _edit_settings(
                profile,
                profile_path,
                application=application,
                ansi_enabled=ansi_enabled,
            )
        elif menu_action == "quit":
            print("Goodbye!")
            return
        else:
            print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
