from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football import (
    DefensiveSchemeAction,
    FootballFourthDownAction,
    FootballMatchResult,
    FootballMatchStatus,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_coaches import (
    DEFENSIVE_COACHES,
    OFFENSIVE_COACHES,
    FootballCoachPair,
    FootballCoachSide,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.engine.football_team_builder import FootballPlayerCandidate
from src.engine.football_player_catalog import (
    PLAYER_TYPES_BY_POSITION,
    player_from_type,
    player_type_for_id,
)
from src.engine.football_shop import FootballShopSection
from src.ui.application import DesktopApplication
from src.ui import coach_art
from src.ui import football_run_screen as football_run_screen_module
from src.ui.layout import LOGICAL_SIZE


def _new_desktop(
    tmp_path: Path,
    *,
    team_name: str = "Test Owls",
    seeds: tuple[int, int, int, int] = (17, 29, 4, 1),
) -> DesktopApplication:
    tmp_path.mkdir(parents=True, exist_ok=True)
    application_controller = ApplicationController(
        tmp_path / "team.json",
        tmp_path / "legacy-game.db",
    )
    application_controller.create_profile(team_name, "navy", "gold")
    seed_values = iter(seeds)
    return DesktopApplication(
        application_controller,
        seed_factory=lambda: next(seed_values),
    )


def _surface() -> pygame.Surface:
    return pygame.Surface(LOGICAL_SIZE)


def _activate(
    desktop: DesktopApplication,
    label: str,
    *,
    index: int = 0,
    keyboard: bool = False,
) -> None:
    desktop.router.draw(_surface())
    screen = desktop.router.current
    matching = [button for button in screen.buttons if button.label == label]
    button = matching[index]
    if keyboard:
        screen.focus_index = screen.buttons.index(button)
        desktop.router.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
        )
    else:
        desktop.router.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"pos": button.rect.center, "button": 1},
            )
        )
        desktop.router.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONUP,
                {"pos": button.rect.center, "button": 1},
            )
        )


def _start_run(
    desktop: DesktopApplication,
    difficulty: FootballAIDifficulty = FootballAIDifficulty.STANDARD,
) -> None:
    _activate(desktop, difficulty.value.upper())
    _activate(desktop, "START RUN")


def _draft_to_shop(desktop: DesktopApplication) -> None:
    _activate(desktop, "CHOOSE STAFF 01")
    for position in PLAYER_DRAFT_ORDER:
        state = desktop.football_controller.state
        assert state.phase is FootballRunPhase.PLAYER_DRAFT
        assert state.team_builder.required_position is position
        button_label = f"DRAFT {position.value}"
        _activate(desktop, button_label, keyboard=True)


def _start_match(desktop: DesktopApplication) -> None:
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "FINISH SHOP / START MATCH")


def _force_result(monkeypatch, winner: FootballTeamSide) -> None:
    def finish(simulator: FootballMatchSimulator, _play: OffensivePlayAction):
        score_a = 7 if winner is FootballTeamSide.TEAM_A else 0
        score_b = 7 if winner is FootballTeamSide.TEAM_B else 0
        result = FootballMatchResult(score_a, score_b, winner, True)
        simulator.state = replace(
            simulator.state,
            team_a_score=score_a,
            team_b_score=score_b,
            status=FootballMatchStatus.COMPLETED,
            awaited_action=None,
            current_drive_defensive_scheme=None,
            final_result=result,
        )
        return simulator.state

    monkeypatch.setattr(FootballMatchSimulator, "resolve_offensive_play", finish)


def test_menu_uses_selected_difficulty_and_four_independent_seeds(
    tmp_path: Path,
) -> None:
    values = iter((101, 202, 303, 404))
    calls = 0

    def seed_factory() -> int:
        nonlocal calls
        calls += 1
        return next(values)

    application_controller = ApplicationController(
        tmp_path / "team.json",
        tmp_path / "legacy-game.db",
    )
    application_controller.create_profile("Difficulty Owls", "crimson", "gold")
    desktop = DesktopApplication(application_controller, seed_factory=seed_factory)

    _activate(desktop, "HARD")
    _activate(desktop, "START RUN")

    assert desktop.router.current_id == "football_run"
    assert desktop.football_controller is not None
    state = desktop.football_controller.state
    assert state.team_builder.current_offer == state.team_builder.coach_offer
    assert state.opponent_difficulty is FootballAIDifficulty.HARD
    assert calls == 4
    assert not (tmp_path / "legacy-game.db").exists()
    with pytest.raises(ValueError, match="Unknown desktop screen"):
        desktop.router.show("roster")


def test_coach_and_eight_position_draft_are_controller_driven(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop, FootballAIDifficulty.EASY)
    controller = desktop.football_controller
    assert controller is not None
    coach_offer = controller.state.team_builder.coach_offer

    _activate(desktop, "CHOOSE STAFF 01", keyboard=True)
    assert controller.state.team_builder.selected_coach_pair is coach_offer[0]
    assert controller.state.selected_coach_pair is coach_offer[0]
    assert controller.state.team_builder.required_position is FootballPosition.QB

    for position in PLAYER_DRAFT_ORDER:
        state = controller.state
        assert state.human_decision is FootballHumanDecision.DRAFT_PLAYER
        assert state.team_builder.required_position is position
        assert len(state.team_builder.current_offer) == 3
        candidates = state.team_builder.current_offer
        assert all(candidate.position is position for candidate in candidates)
        assert all(candidate.description for candidate in candidates)
        _activate(desktop, f"DRAFT {position.value}", keyboard=True)

    state = controller.state
    assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert state.team_builder.completed
    assert set(state.team_builder.selected_players) == set(FootballPosition)
    assert state.shop is not None and state.shop.remaining_budget == 12


def test_player_draft_inspection_tracks_mouse_and_keyboard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text
    original_draw_wrapped_text = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    def capture_wrapped_text(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        original_draw_wrapped_text(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_run_screen_module, "draw_wrapped_text", capture_wrapped_text
    )
    desktop.router.draw(_surface())

    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    offers = controller.state.team_builder.current_offer

    def render() -> str:
        displayed.clear()
        desktop.router.draw(_surface())
        return " ".join(displayed)

    text = render()
    assert "SCOUT THE PROSPECTS" in text
    for candidate in offers:
        assert candidate.name.upper() in text
        assert str(candidate.player.power) in text
        assert football_run_screen_module._draft_percentage(candidate.player.volatility) in text
        assert football_run_screen_module._draft_percentage(candidate.player.stamina) in text

    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[0].center}
    ))
    text = render()
    first_type = player_type_for_id(offers[0].player.player_type_id)
    assert f"SCOUTING  /  {offers[0].name.upper()}" in text
    assert "+10% contribution when both players contribute to the same play" in text
    assert "capped at +30%" in text
    assert "PLANNED, INACTIVE" in text
    assert first_type.perk is not None and first_type.perk.display_text in text

    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[2].center}
    ))
    text = render()
    assert f"SCOUTING  /  {offers[2].name.upper()}" in text
    assert "None. No partnership bonus." in text
    assert "PERK None." in text
    assert first_type.perk.display_text not in text
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    assert "SCOUT THE PROSPECTS" in render()
    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert f"SCOUTING  /  {offers[1].name.upper()}" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    assert "SCOUT THE PROSPECTS" in render()
    assert controller.state.phase is FootballRunPhase.PLAYER_DRAFT


def test_draft_progress_uses_selected_players_and_selection_actions(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    controller = desktop.football_controller
    assert controller is not None
    displayed: list[str] = []
    original_text = football_run_screen_module.draw_text
    original_wrapped = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        original_wrapped(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_run_screen_module, "draw_wrapped_text", capture_wrapped)
    chosen = []
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        displayed.clear()
        desktop.router.draw(_surface())
        assert displayed.count("SIGNED") == index
        assert displayed.count("ON THE CLOCK") == 1
        assert displayed.count("UP NEXT") == len(PLAYER_DRAFT_ORDER) - index - 1
        assert all(name in displayed for name in chosen)
        candidate = controller.state.team_builder.current_offer[1]
        chosen.append(candidate.name)
        _activate(desktop, f"DRAFT {position.value}", index=1, keyboard=index % 2 == 0)
        assert controller.state.team_builder.selected_players[position] is candidate.player
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP


def test_draft_displays_offered_values_and_uses_team_uniform_colors(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    state = screen.state
    assert state is not None
    offer = state.team_builder.current_offer
    player = replace(offer[0].player, power=63.25, volatility=0.125, stamina=0.735)
    changed = replace(offer[0], player=player)
    screen.state = replace(state, team_builder=replace(
        state.team_builder, current_offer=(changed, *offer[1:])
    ))
    displayed: list[str] = []
    colors: list[tuple[pygame.Color, pygame.Color]] = []
    original_text = football_run_screen_module.draw_text
    original_art = football_run_screen_module.draw_draft_player

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    def capture_art(surface, rect, primary, secondary):
        colors.append((primary, secondary))
        original_art(surface, rect, primary, secondary)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_run_screen_module, "draw_draft_player", capture_art)
    desktop.router.draw(_surface())
    assert all(value in displayed for value in ("63.25", "12.5%", "73.5%"))
    assert colors == [(desktop.theme.primary, desktop.theme.secondary)] * 3


def test_all_draft_catalog_text_fits_its_allocated_space(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    surface = _surface()
    original = football_run_screen_module.draw_wrapped_text

    def check_wrapping(surface, text, rect, font, color, **kwargs):
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if current and font.size(trial)[0] > rect.width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        assert all(font.size(line)[0] <= rect.width for line in lines), text
        line_gap = kwargs.get("line_gap", 6)
        assert (len(lines) - 1) * (font.get_height() + line_gap) + font.get_height() <= rect.height, text
        original(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_wrapped_text", check_wrapping)
    detail_rect = pygame.Rect(38, 500, 1204, 190)
    for types in PLAYER_TYPES_BY_POSITION.values():
        for player_type in types:
            assert screen._coach_name_font.size(player_type.name.upper())[0] <= 354
            check_wrapping(surface, player_type.name, pygame.Rect(0, 0, 128, 38),
                           screen._coach_detail_font, pygame.Color("white"), line_gap=0)
            candidate = FootballPlayerCandidate(player_from_type(player_type), "test")
            screen._draw_draft_details(surface, detail_rect, candidate)


@pytest.mark.parametrize("window_size", [(1280, 720), (960, 540), (1024, 768)])
def test_draft_mouse_inspection_and_selection_in_resized_windows(tmp_path: Path, window_size) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    desktop.window_size = window_size
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    selected = controller.state.team_builder.current_offer[2].player
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offsets = ((window_size[0] - round(1280 * scale)) // 2,
               (window_size[1] - round(720 * scale)) // 2)

    def physical(point):
        return tuple(round(offsets[i] + point[i] * scale) for i in range(2))

    motion = pygame.event.Event(pygame.MOUSEMOTION, {"pos": physical(screen._draft_card_rects[2].center)})
    desktop.router.handle_event(desktop._logical_event(motion))
    assert screen._draft_hover_index == 2
    desktop.router.draw(_surface())
    button = screen.buttons[2]
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        event = pygame.event.Event(event_type, {"pos": physical(button.rect.center), "button": 1})
        desktop.router.handle_event(desktop._logical_event(event))
    assert controller.state.team_builder.selected_players[FootballPosition.QB] is selected


def test_coach_inspection_is_side_specific_for_mouse_and_keyboard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    assert controller is not None
    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text
    original_draw_wrapped_text = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    def capture_wrapped_text(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        original_draw_wrapped_text(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_run_screen_module, "draw_wrapped_text", capture_wrapped_text
    )
    desktop.router.draw(_surface())
    pair = controller.state.team_builder.coach_offer[0]

    assert pair.offense.name.upper() in " ".join(displayed)
    assert pair.defense.name.upper() in " ".join(displayed)
    assert "SCOUT THE STAFF" in displayed
    assert "PLAY MODIFIER SUM" not in displayed
    assert "SCHEME MODIFIER SUM" not in displayed

    screen = desktop.run_screen
    offense = next(button for button in screen.buttons if button.label == "INSPECT OFFENSE 1")
    defense = next(button for button in screen.buttons if button.label == "INSPECT DEFENSE 1")

    def render() -> str:
        displayed.clear()
        desktop.router.draw(_surface())
        return " ".join(displayed)

    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": offense.rect.center}))
    text = render()
    assert f"OFFENSE  /  {pair.offense.name.upper()}" in text
    assert "PLAY MODIFIER SUM" in text and "SCHEME MODIFIER SUM" not in text
    assert pair.offense.perk is not None
    assert pair.offense.perk.effect in text
    assert pair.defense.perk is not None
    assert pair.defense.perk.effect not in text
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(
            pygame.event.Event(event_type, {"pos": offense.rect.center, "button": 1})
        )
    assert controller.state.phase is FootballRunPhase.COACH_DRAFT

    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": defense.rect.center}))
    text = render()
    assert f"DEFENSE  /  {pair.defense.name.upper()}" in text
    assert "SCHEME MODIFIER SUM" in text and "PLAY MODIFIER SUM" not in text
    assert pair.defense.perk.effect in text
    assert pair.offense.perk.effect not in text

    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    assert "SCOUT THE STAFF" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": defense.rect.center}))
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    assert "SCOUT THE STAFF" in render()

    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert f"OFFENSE  /  {pair.offense.name.upper()}" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert f"DEFENSE  /  {pair.defense.name.upper()}" in render()
    assert controller.state.phase is FootballRunPhase.COACH_DRAFT
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert "SCOUT THE STAFF" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert controller.state.selected_coach_pair is controller.state.team_builder.coach_offer[1]


@pytest.mark.parametrize("coach", (*OFFENSIVE_COACHES, *DEFENSIVE_COACHES))
def test_coach_detail_contains_all_data_without_clipping(tmp_path: Path, monkeypatch, coach) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    displayed: list[str] = []
    original_text = football_run_screen_module.draw_text
    original_wrapped = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        assert position[0] + font.size(text)[0] <= 1242
        assert position[1] + font.get_height() <= 680
        original_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > rect.width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        assert all(font.size(line)[0] <= rect.width for line in lines)
        assert len(lines) * font.get_height() + max(0, len(lines) - 1) * kwargs.get("line_gap", 6) <= rect.height
        original_wrapped(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_run_screen_module, "draw_wrapped_text", capture_wrapped)
    state = desktop.football_controller.state
    pair = (
        FootballCoachPair(coach, DEFENSIVE_COACHES[0])
        if coach.side is FootballCoachSide.OFFENSE
        else FootballCoachPair(OFFENSIVE_COACHES[0], coach)
    )
    builder = replace(state.team_builder, coach_offer=(pair, pair, pair))
    screen._draw_coach_selection(
        _surface(), pygame.Rect(38, 122, 1204, 558),
        replace(state, team_builder=builder),
    )
    for position, modifier in coach.position_modifiers.items():
        label = football_run_screen_module._coach_position_label(position)
        assert f"{label} {round(modifier * 100):+d}%" in displayed
    displayed.clear()
    screen._draw_coach_details(_surface(), pygame.Rect(38, 496, 1204, 184), coach)
    for action, percentage in coach.action_percentages.items():
        label = football_run_screen_module._coach_action_label(action.value)
        assert f"{label}  {percentage}%" in displayed
    if coach.perk is None:
        assert "No perk." in displayed
    else:
        assert all(part in " ".join(displayed) for part in (
            coach.perk.trigger, coach.perk.effect, coach.perk.duration, coach.perk.reset
        ))


@pytest.mark.parametrize("window_size", [(1280, 720), (960, 540), (1024, 768)])
def test_coach_mouse_targets_work_in_resized_windows(tmp_path: Path, window_size) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.window_size = window_size
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    for coach in (*OFFENSIVE_COACHES, *DEFENSIVE_COACHES):
        assert screen._coach_name_font.size(coach.name.upper())[0] <= 275
        for position, modifier in coach.position_modifiers.items():
            label = football_run_screen_module._coach_position_label(position)
            assert screen._coach_stat_font.size(
                f"{label} {round(modifier * 100):+d}%"
            )[0] < 124
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offset_x = (window_size[0] - round(1280 * scale)) // 2
    offset_y = (window_size[1] - round(720 * scale)) // 2

    def physical_position(button):
        return (
            round(offset_x + button.rect.centerx * scale),
            round(offset_y + button.rect.centery * scale),
        )

    inspect = next(button for button in screen.buttons if button.label == "INSPECT DEFENSE 3")
    event = pygame.event.Event(pygame.MOUSEMOTION, {"pos": physical_position(inspect)})
    desktop.router.handle_event(desktop._logical_event(event))
    assert screen.hover_index == screen.buttons.index(inspect)
    desktop.router.draw(_surface())
    choose = next(button for button in screen.buttons if button.label == "CHOOSE STAFF 03")
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        event = pygame.event.Event(event_type, {"pos": physical_position(choose), "button": 1})
        desktop.router.handle_event(desktop._logical_event(event))
    controller = desktop.football_controller
    assert controller is not None
    assert controller.state.selected_coach_pair is controller.state.team_builder.coach_offer[2]
    assert controller.state.phase is FootballRunPhase.PLAYER_DRAFT


def test_missing_coach_art_uses_visible_fallback_and_logs(tmp_path: Path, monkeypatch, caplog) -> None:
    coach_art.recruiting_table.cache_clear()
    monkeypatch.setattr(coach_art, "_TABLE_PATH", tmp_path / "missing.png")
    try:
        surface = _surface()
        coach_art.draw_recruiting_table(surface)
        assert surface.get_at((10, 10)) == pygame.Color("#282c24")
        assert "Could not load recruiting table artwork" in caplog.text
    finally:
        coach_art.recruiting_table.cache_clear()


def test_coach_selection_error_preserves_offer_and_is_displayed(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state
    displayed: list[str] = []
    original_draw = football_run_screen_module.draw_text

    def reject_choice(_choice):
        raise ValueError("Staff could not be chosen.")

    def capture(surface, text, position, font, color):
        displayed.append(text)
        original_draw(surface, text, position, font, color)

    monkeypatch.setattr(controller, "choose_coach", reject_choice)
    monkeypatch.setattr(football_run_screen_module, "draw_text", capture)
    _activate(desktop, "CHOOSE STAFF 02")
    desktop.router.draw(_surface())
    assert controller.state == before
    assert desktop.run_screen.last_error == "Staff could not be chosen."
    assert "CHECK: Staff could not be chosen." in displayed


def test_shop_purchase_and_finish_start_the_match(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    shop = controller.state.shop
    assert shop is not None
    assert shop.remaining_budget == 12

    _activate(desktop, "BUY", index=0)
    purchased = controller.state.shop
    assert purchased is not None
    assert purchased.remaining_budget == 12 - shop.offer[0].cost
    assert purchased.purchased_upgrades == (shop.offer[0],)
    _activate(desktop, "BUY", index=1)
    purchased_twice = controller.state.shop
    assert purchased_twice is not None
    assert len(purchased_twice.purchased_upgrades) == 2
    assert purchased_twice.remaining_budget < purchased.remaining_budget

    _activate(desktop, "FINISH SHOP / START MATCH")
    state = controller.state
    assert state.phase is FootballRunPhase.MATCH
    assert state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert state.shop is not None and state.shop.finished
    assert state.match is not None
    assert state.match.team_a.team_name == "Test Owls"
    assert state.match.team_b.team_name == "Local AI"


def test_shop_sections_reroll_unlock_and_keyboard_purchase(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None

    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    football_run_screen_module.draw_text = capture_text
    try:
        desktop.router.draw(_surface())
    finally:
        football_run_screen_module.draw_text = original_draw_text

    joined = " ".join(displayed)
    assert "THREE SHOPS  /  ONE SHARED AP BUDGET" in joined
    assert "ACTION POINTS" in joined
    assert "PLAYER UPGRADES" in joined
    assert "PLAYS / SCHEMES" in joined
    assert "COACH UPGRADES" in joined
    assert "No play/scheme cards yet." in joined
    assert "No coach upgrades yet." in joined
    assert "Available after game 3." in joined
    assert all(
        upgrade.rarity.value.replace("_", " ").upper() in joined
        for upgrade in controller.state.shop.offer
    )

    _activate(desktop, "BUY", keyboard=True)
    after_purchase = controller.state.shop
    assert after_purchase is not None and len(after_purchase.purchased_upgrades) == 1
    _activate(desktop, "MOVE TO NEXT DAY  /  1 AP")
    after_reroll = controller.state.shop
    assert after_reroll is not None
    assert after_reroll.day == 2
    assert after_reroll.remaining_ap == 11 - after_purchase.purchased_upgrades[0].cost

    _activate(desktop, "UNLOCK 4 AP", index=0)
    unlocked = controller.state.shop
    assert unlocked is not None
    assert unlocked.section(FootballShopSection.PLAYER_UPGRADES).slots[3].unlocked
    assert unlocked.remaining_ap == after_reroll.remaining_ap - 4
    _activate(desktop, "FINISH SHOP / START MATCH", keyboard=True)
    assert controller.state.phase is FootballRunPhase.MATCH


def test_shop_at_zero_ap_stays_open_until_explicit_finish(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    for _ in range(12):
        _activate(desktop, "MOVE TO NEXT DAY  /  1 AP")
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_ap == 0
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP

    desktop.router.draw(_surface())
    buttons = {button.label: button for button in desktop.run_screen.buttons}
    assert not buttons["MOVE TO NEXT DAY  /  1 AP"].enabled
    assert buttons["FINISH SHOP / START MATCH"].enabled
    _activate(desktop, "FINISH SHOP / START MATCH")
    assert controller.state.phase is FootballRunPhase.MATCH


def test_match_controls_follow_decisions_ai_advances_and_game_finishes(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen
    initial = controller.state.match
    assert initial is not None
    assert initial.team_a.team_name == "Test Owls"
    assert initial.team_b.team_name == "Local AI"

    seen_offense = False
    seen_defense = False
    seen_fourth_down = False
    seen_ai_play = False
    for _ in range(1200):
        state = controller.state
        if state.phase is not FootballRunPhase.MATCH:
            break
        assert state.match is not None
        desktop.router.draw(_surface())
        labels = {button.label: button for button in screen.buttons}
        event_count = len(state.match.match_events)
        if state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            seen_offense = True
            expected = OffensivePlayAction.DEEP_PASS
            allowed = {
                "RB RUN",
                "SCREEN PASS",
                "PLAY-ACTION PASS",
                "SHORT PASS",
                "MEDIUM PASS",
                "DEEP PASS",
            }
            assert set(labels) - {"PAUSE"} == allowed
            labels["DEEP PASS"].action()
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            seen_defense = True
            expected = DefensiveSchemeAction.RB_RUN
            allowed = {
                "RB RUN SCHEME",
                "SCREEN PASS SCHEME",
                "PLAY-ACTION SCHEME",
                "SHORT PASS SCHEME",
                "MEDIUM PASS SCHEME",
                "DEEP PASS SCHEME",
            }
            assert set(labels) - {"PAUSE"} == allowed
            labels["RB RUN SCHEME"].action()
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            seen_fourth_down = True
            expected = FootballFourthDownAction.PUNT
            assert set(labels) - {"PAUSE"} == {
                "GO FOR IT",
                "PUNT",
                "FIELD GOAL",
            }
            labels["PUNT"].action()
        else:
            pytest.fail(f"Unexpected match decision: {state.human_decision}")

        updated = controller.state
        assert updated.match is not None
        new_events = updated.match.match_events[event_count:]
        assert new_events
        assert new_events[0].action is expected
        seen_ai_play = seen_ai_play or any(
            event.possession is FootballTeamSide.TEAM_B
            and isinstance(event.action, OffensivePlayAction)
            for event in new_events
        )
    else:
        pytest.fail("The seeded desktop match did not finish.")

    final = controller.state
    assert final.phase in (
        FootballRunPhase.READY_FOR_NEXT_GAME,
        FootballRunPhase.FIRED,
        FootballRunPhase.PLAYOFFS,
    )
    assert final.match is not None
    assert final.match.status is FootballMatchStatus.COMPLETED
    assert final.match.final_result is not None
    assert seen_offense and seen_defense and seen_fourth_down and seen_ai_play
    desktop.router.draw(_surface())
    assert any(
        button.label in {"OPEN NEXT GAME SHOP", "RETURN TO MAIN MENU"}
        for button in screen.buttons
    )


def test_match_screen_uses_pause_and_numbered_play_calls(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen

    desktop.router.draw(_surface())
    labels = {button.label: button for button in screen.buttons}
    assert set(labels) == {
        "RB RUN",
        "SCREEN PASS",
        "PLAY-ACTION PASS",
        "SHORT PASS",
        "MEDIUM PASS",
        "DEEP PASS",
        "PAUSE",
    }

    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2})
    )
    match = controller.state.match
    assert match is not None
    assert match.match_events[-1].action is OffensivePlayAction.SCREEN_PASS

    desktop.router.draw(_surface())
    next(button for button in screen.buttons if button.label == "PAUSE").action()
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {
        "DISCARD RUN",
        "KEEP PLAYING",
    }


@pytest.mark.parametrize(
    ("winner", "games", "expected_phase", "expected_button"),
    (
        (
            FootballTeamSide.TEAM_B,
            3,
            FootballRunPhase.FIRED,
            "RETURN TO MAIN MENU",
        ),
        (
            FootballTeamSide.TEAM_A,
            10,
            FootballRunPhase.PLAYOFFS,
            "RETURN TO MAIN MENU",
        ),
    ),
)
def test_result_routes_fired_and_game_ten_playoffs_without_bracket(
    tmp_path: Path,
    monkeypatch,
    winner: FootballTeamSide,
    games: int,
    expected_phase: FootballRunPhase,
    expected_button: str,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, winner)
    controller = desktop.football_controller
    assert controller is not None

    for game_number in range(1, games + 1):
        _activate(desktop, "DEEP PASS")
        state = controller.state
        if game_number < games:
            assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
            _activate(desktop, "OPEN NEXT GAME SHOP")
            assert controller.state.game_number == game_number + 1
            assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
            _activate(desktop, "FINISH SHOP / START MATCH")

    final = controller.state
    assert final.phase is expected_phase
    assert final.game_number == games
    assert final.match is not None and final.match.final_result is not None
    desktop.router.draw(_surface())
    assert any(button.label == expected_button for button in desktop.run_screen.buttons)
    assert desktop.run_screen.state == final
    assert not (tmp_path / "legacy-game.db").exists()


def test_ready_for_next_game_button_opens_shop_before_the_next_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    _activate(desktop, "DEEP PASS")

    controller = desktop.football_controller
    assert controller is not None
    assert controller.state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    _activate(desktop, "OPEN NEXT GAME SHOP", keyboard=True)
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_ap == 12
    _activate(desktop, "FINISH SHOP / START MATCH")
    assert controller.state.phase is FootballRunPhase.MATCH
    assert controller.state.game_number == 2
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY


def test_invalid_action_is_visible_and_does_not_change_controller_state(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    coach_button = next(
        button
        for button in desktop.run_screen.buttons
        if button.label == "CHOOSE STAFF 01"
    )
    coach_button.action()
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state

    coach_button.action()

    assert controller.state == before
    assert desktop.run_screen.state == before
    assert desktop.run_screen.last_error is not None
    assert "phase" in desktop.run_screen.last_error
    canvas = _surface()
    desktop.router.draw(canvas)
    assert desktop.run_screen.last_error is not None
    assert desktop.run_screen.state == before
    error_visible = any(
        canvas.get_at((x, y)) == desktop.theme.danger
        for x in range(24, 800)
        for y in range(canvas.get_height() - 55, canvas.get_height() - 35)
    )
    assert error_visible


def test_repeated_draws_do_not_change_state_or_consume_gameplay_rng(
    tmp_path: Path,
) -> None:
    first = _new_desktop(tmp_path / "first", team_name="Same Team")
    replay = _new_desktop(tmp_path / "replay", team_name="Same Team")
    _start_run(first)
    _start_run(replay)
    first_controller = first.football_controller
    replay_controller = replay.football_controller
    assert first_controller is not None and replay_controller is not None
    before = first_controller.state
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == before == replay_controller.state
    for desktop in (first, replay):
        _activate(desktop, "CHOOSE STAFF 01")
    assert first_controller.state == replay_controller.state

    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state
    for position in PLAYER_DRAFT_ORDER:
        _activate(first, f"DRAFT {position.value}")
        _activate(replay, f"DRAFT {position.value}")
        assert first_controller.state == replay_controller.state
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state

    _activate(first, "FINISH SHOP / START MATCH")
    _activate(replay, "FINISH SHOP / START MATCH")
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state
    _activate(first, "DEEP PASS")
    _activate(replay, "DEEP PASS")
    assert first_controller.state == replay_controller.state
    assert not (tmp_path / "first" / "legacy-game.db").exists()
    assert not (tmp_path / "replay" / "legacy-game.db").exists()


def test_escape_requests_explicit_discard_confirmation(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
    )
    assert desktop.router.current_id == "football_run"
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {
        "DISCARD RUN",
        "KEEP PLAYING",
    }

    _activate(desktop, "KEEP PLAYING")
    assert desktop.router.current_id == "football_run"
    assert not screen.confirm_exit
