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
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchResult,
    FootballMatchStatus,
    FootballPlayResult,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_coaches import (
    DEFENSIVE_COACHES,
    OFFENSIVE_COACHES,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.engine.football_team_builder import FootballPlayerCandidate
from src.engine.football_player_catalog import (
    PLAYER_TYPES_BY_POSITION,
    player_from_type,
    player_type_for_id,
)
from src.ui.theme import readable_ink, relative_luminance
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
)
from src.profile import COLOR_CHOICES
from src.ui.application import DesktopApplication
from src.ui import coach_art
from src.ui import football_run_screen as football_run_screen_module
from src.ui import player_art
from src.ui.layout import LOGICAL_SIZE
from src.ui.widgets import Button
from src.ui.theme import readable_ink


def _new_desktop(
    tmp_path: Path,
    *,
    team_name: str = "Test Owls",
    seeds: tuple[int, int, int, int] = (17, 29, 4, 1),
    primary: str = "navy",
    secondary: str = "gold",
) -> DesktopApplication:
    tmp_path.mkdir(parents=True, exist_ok=True)
    application_controller = ApplicationController(
        tmp_path / "team.json",
        tmp_path / "legacy-game.db",
    )
    application_controller.create_profile(team_name, primary, secondary)
    seed_values = iter(seeds)
    return DesktopApplication(
        application_controller,
        seed_factory=lambda: next(seed_values),
    )


def _new_desktop_with_removal_offer(tmp_path: Path) -> DesktopApplication:
    desktop = _new_desktop(tmp_path)
    removal = FootballShopCard(
        card_id="test-removal",
        name="Remove One Card",
        description="Remove one owned play or scheme.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        is_removal=True,
    )
    controller = FootballGameController(
        "Test Owls",
        difficulty=FootballAIDifficulty.STANDARD,
        builder_seed=17,
        shop_seed=29,
        ai_seed=4,
        match_seed=1,
        shop_catalogs={
            FootballShopSection.PLAYS_SCHEMES: (removal,),
        },
    )
    desktop.football_controller = controller
    desktop.run_screen.begin(controller)
    desktop.router.show("football_run")
    return desktop


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


def _play_first_match_card(desktop: DesktopApplication) -> None:
    desktop.router.draw(_surface())
    button = next(
        button
        for button in desktop.run_screen.buttons
        if button.variant == "hand-card"
    )
    button.action()


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
    assert "Scout a prospect" not in text
    assert "SCOUTING" not in text
    for candidate in offers:
        assert candidate.name in text
        assert candidate.position is controller.state.team_builder.required_position
        assert str(candidate.player.power) in text
        assert football_run_screen_module._draft_percentage(candidate.player.volatility) in text
        assert football_run_screen_module._draft_percentage(candidate.player.stamina) in text

    focus_before = screen.focus_index
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[0].center}
    ))
    text = render()
    assert screen.focus_index == focus_before
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen.buttons[0].rect.center}
    ))
    assert screen.focus_index == focus_before
    assert screen.hover_index == 0
    text = render()
    assert offers[0].name in text
    assert "SCOUTING" in text
    first_type = player_type_for_id(offers[0].player.player_type_id)
    assert "+10% contribution when both players contribute to the same play" in text
    assert "tops out at 130% of base" in text
    assert "PLANNED · INACTIVE" in text
    assert first_type.perk is not None
    for detail in (
        first_type.perk.trigger,
        first_type.perk.effect,
        first_type.perk.duration,
        first_type.perk.reset,
        first_type.perk.dependency,
    ):
        assert detail in text

    for index in (1, 2):
        desktop.router.handle_event(pygame.event.Event(
            pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[index].center}
        ))
        assert offers[index].name in render()
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[0].center}
    ))
    assert offers[0].name in render()

    prospect_title = pygame.Rect(
        screen._draft_card_rects[0].left,
        screen._draft_card_rects[0].top,
        screen._draft_card_rects[0].width,
        34,
    )
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": prospect_title.center}
    ))
    assert offers[0].name in render()
    detail_rect = screen._draft_detail_rect
    assert detail_rect is not None
    assert not detail_rect.colliderect(prospect_title)
    assert all(not detail_rect.colliderect(button.rect) for button in screen.buttons[:3])
    selected_portrait = pygame.Rect(
        screen._draft_card_rects[0].centerx - 130,
        screen._draft_card_rects[0].top + 40,
        260,
        345,
    )
    assert detail_rect.colliderect(selected_portrait)
    assert abs(detail_rect.centerx - selected_portrait.centerx) <= 16
    assert all(
        not detail_rect.colliderect(pygame.Rect(
            rect.left + 4, rect.bottom - 105, rect.width - 8, 62
        ))
        for rect in screen._draft_card_rects
    )
    for point in (
        (screen._draft_card_rects[0].right - 1, detail_rect.top),
        (detail_rect.left, detail_rect.top),
        detail_rect.center,
    ):
        desktop.router.handle_event(pygame.event.Event(
            pygame.MOUSEMOTION, {"pos": point}
        ))
        assert screen._draft_hover_index == 0
        assert offers[0].name in render()
    assert offers[0].name in render()
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(
            event_type, {"pos": detail_rect.center, "button": 1}
        ))
    assert controller.state.phase is FootballRunPhase.PLAYER_DRAFT
    assert not controller.state.team_builder.selected_players

    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen._draft_card_rects[2].center}
    ))
    text = render()
    assert offers[2].name in text
    third_popup = screen._draft_detail_rect
    assert third_popup is not None
    third_portrait = pygame.Rect(
        screen._draft_card_rects[2].centerx - 130,
        screen._draft_card_rects[2].top + 40,
        260,
        345,
    )
    assert third_popup.colliderect(third_portrait)
    assert abs(third_popup.centerx - third_portrait.centerx) <= 16
    assert "None. No partnership bonus." in text
    assert "Perk" in text and "None. This player type has no perk." in text
    assert first_type.perk.effect not in text
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    assert "SCOUTING" not in render()
    assert screen._draft_detail_rect is None
    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert offers[1].name in render()
    assert "KEYBOARD SCOUTING" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert offers[2].name in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert "KEYBOARD SCOUTING" not in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert offers[0].name in render()
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    assert "KEYBOARD SCOUTING" not in render()
    assert controller.state.phase is FootballRunPhase.PLAYER_DRAFT
    assert not controller.state.team_builder.selected_players


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
        assert displayed.count("Drafted") == index
        assert displayed.count("Current pick") == 1
        assert displayed.count("Up next") == len(PLAYER_DRAFT_ORDER) - index - 1
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
    portrait_rects: list[pygame.Rect] = []
    original_text = football_run_screen_module.draw_text
    original_art = football_run_screen_module.draw_draft_player

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    def capture_art(surface, rect, primary, secondary):
        colors.append((primary, secondary))
        portrait_rects.append(rect.copy())
        original_art(surface, rect, primary, secondary)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_run_screen_module, "draw_draft_player", capture_art)
    desktop.router.draw(_surface())
    assert all(value in displayed for value in ("63.25", "12.5%", "73.5%"))
    assert colors == [(desktop.theme.primary, desktop.theme.secondary)] * 3
    assert all(rect.height >= 340 for rect in portrait_rects)
    assert len({rect.size for rect in portrait_rects}) == 1


def test_one_generated_player_sprite_is_reused_and_team_recolored() -> None:
    colors = (
        (pygame.Color("#091b78"), pygame.Color("#eac64a")),
        (pygame.Color("#a12542"), pygame.Color("#f1eadb")),
    )
    rendered: list[pygame.Surface] = []
    for _ in range(3):
        surface = pygame.Surface((220, 220))
        surface.fill("#1b2522")
        player_art.draw_draft_player(surface, pygame.Rect(20, 10, 180, 195), *colors[0])
        rendered.append(surface)
    assert len({pygame.image.tobytes(surface, "RGB") for surface in rendered}) == 1

    recolored = pygame.Surface((220, 220))
    recolored.fill("#1b2522")
    player_art.draw_draft_player(recolored, pygame.Rect(20, 10, 180, 195), *colors[1])
    assert pygame.image.tobytes(recolored, "RGB") != pygame.image.tobytes(
        rendered[0], "RGB"
    )
    assert recolored.get_at((0, 0)) == pygame.Color("#1b2522")


def test_all_draft_catalog_text_fits_its_allocated_space(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    surface = _surface()
    original = football_run_screen_module.draw_wrapped_text
    original_text = football_run_screen_module.draw_text
    displayed: list[str] = []

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)

    def check_wrapping(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
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
    screen._draft_hover_index = 0
    desktop.router.draw(surface)
    detail_rect = screen._draft_detail_rect
    assert detail_rect is not None
    assert detail_rect.left >= 0 and detail_rect.top >= 0
    assert detail_rect.right <= surface.get_width()
    assert detail_rect.bottom <= surface.get_height()
    assert all(
        not detail_rect.colliderect(button.rect)
        for button in screen.buttons[:3]
    )
    for index, choice in enumerate(screen._draft_card_rects):
        popup = screen._draft_popup_rect(index, surface.get_size())
        assert popup.left >= 0 and popup.top >= 0
        assert popup.right <= surface.get_width()
        assert popup.bottom <= surface.get_height()
        assert not popup.colliderect(screen.buttons[index].rect)
        assert not popup.colliderect(pygame.Rect(
            choice.left + 4, choice.bottom - 105, choice.width - 8, 62
        ))
        portrait = pygame.Rect(
            choice.centerx - 130, choice.top + 40, 260, 345
        )
        assert popup.colliderect(portrait)
        assert abs(popup.centerx - portrait.centerx) <= 16
    for types in PLAYER_TYPES_BY_POSITION.values():
        for player_type in types:
            displayed.clear()
            assert screen._draft_name_font.size(player_type.name)[0] <= 354
            check_wrapping(surface, player_type.name, pygame.Rect(0, 0, 128, 26),
                           screen._draft_small_font, pygame.Color("white"), line_gap=0)
            candidate = FootballPlayerCandidate(player_from_type(player_type), "test")
            screen._draw_draft_details(surface, detail_rect, candidate)
            perk_width = (detail_rect.width - 48) // 2
            if player_type.perk is not None:
                perk = player_type.perk
                lines = (
                    f"Name: {perk.name}",
                    f"Trigger: {perk.trigger}",
                    f"Effect: {perk.effect}",
                    f"Duration: {perk.duration}  ·  Reset: {perk.reset}",
                    f"Dependency: {perk.dependency}",
                )
                assert screen._draft_small_font.size("PLANNED · INACTIVE")[0] <= perk_width
                assert all(
                    football_run_screen_module._wrapped_line_count(
                        line, screen._draft_detail_font, perk_width
                    )
                    * screen._draft_detail_font.get_height()
                    <= detail_rect.height - 122
                    for line in lines
                )
                total_lines = sum(
                    football_run_screen_module._wrapped_line_count(
                        line, screen._draft_detail_font, perk_width
                    )
                    for line in lines
                )
                assert (
                    total_lines * screen._draft_detail_font.get_height() + len(lines)
                    <= detail_rect.height - 122
                )
                assert all(line in " ".join(displayed) for line in lines)
                assert "PLANNED · INACTIVE" in " ".join(displayed)
            else:
                assert "None. This player type has no perk." in displayed


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

    third_portrait = pygame.Rect(
        screen._draft_card_rects[2].centerx - 130,
        screen._draft_card_rects[2].top + 40,
        260,
        345,
    )
    motion = pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": physical(third_portrait.center)}
    )
    desktop.router.handle_event(desktop._logical_event(motion))
    assert screen._draft_hover_index == 2
    desktop.router.draw(_surface())
    popup = screen._draft_detail_rect
    assert popup is not None
    assert popup.colliderect(third_portrait)
    assert abs(popup.centerx - third_portrait.centerx) <= 16
    button = screen.buttons[2]
    button_motion = pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": physical(button.rect.center)}
    )
    desktop.router.handle_event(desktop._logical_event(button_motion))
    assert screen._draft_hover_index == 2
    desktop.router.draw(_surface())
    assert screen._draft_detail_rect is not None
    assert abs(screen._draft_detail_rect.centerx - third_portrait.centerx) <= 16
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        event = pygame.event.Event(event_type, {"pos": physical(button.rect.center), "button": 1})
        desktop.router.handle_event(desktop._logical_event(event))
    assert controller.state.team_builder.selected_players[FootballPosition.QB] is selected


@pytest.mark.parametrize(
    ("primary", "secondary"),
    [
        ("yellow", "silver"),
        ("navy", "blue"),
        ("sky-blue", "azure"),
        ("crimson", "rose"),
    ],
)
def test_draft_color_states_keep_action_text_contrasting(
    tmp_path: Path, primary: str, secondary: str,
) -> None:
    application_controller = ApplicationController(
        tmp_path / "team.json", tmp_path / "legacy-game.db"
    )
    application_controller.create_profile("Palette Owls", primary, secondary)
    desktop = DesktopApplication(
        application_controller,
        seed_factory=iter((17, 29, 4, 1)).__next__,
    )
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    canvas = _surface()

    def contrast(first: pygame.Color, second: pygame.Color) -> float:
        high, low = sorted(
            (relative_luminance(first), relative_luminance(second)), reverse=True
        )
        return (high + 0.05) / (low + 0.05)

    assert contrast(desktop.theme.primary, readable_ink(desktop.theme.primary)) >= 4.5
    assert contrast(
        desktop.theme.primary_dark, readable_ink(desktop.theme.primary_dark)
    ) >= 4.5
    desktop.router.draw(canvas)
    button = screen.buttons[0]
    assert canvas.get_at((button.rect.left + 20, button.rect.top + 15)) == pygame.Color("#a600e8")
    assert canvas.get_at((button.rect.left - 3, button.rect.centery)) == pygame.Color("#111416")
    assert canvas.get_at((button.rect.left - 1, button.rect.centery)) == pygame.Color("#ffffff")
    current_tile = pygame.Rect(38, 113, 146, 58)
    assert canvas.get_at((current_tile.left, current_tile.centery)) == pygame.Color("#a600e8")

    screen.hover_index = 0
    screen._draft_hover_index = 0
    desktop.router.draw(canvas)
    button = screen.buttons[0]
    assert canvas.get_at((button.rect.left + 1, button.rect.centery)) == pygame.Color("#f5ead1")

    screen.pressed_index = 0
    desktop.router.draw(canvas)
    button = screen.buttons[0]
    assert canvas.get_at((button.rect.left + 20, button.rect.top + 15)) == pygame.Color("#7800b5")
    assert contrast(pygame.Color("#7800b5"), readable_ink(pygame.Color("#7800b5"))) >= 4.5

    disabled = Button(
        "DRAFT QB",
        lambda: None,
        button.rect.copy(),
        enabled=False,
        variant="draft-select",
    )
    screen.buttons = [disabled]
    screen.pressed_index = None
    screen.hover_index = None
    screen._draw_buttons(canvas)
    disabled_fill = pygame.Color("#b9beb9")
    assert canvas.get_at((disabled.rect.left + 20, disabled.rect.top + 15)) == disabled_fill
    assert contrast(disabled_fill, readable_ink(disabled_fill)) >= 4.5

    controller = desktop.football_controller
    assert controller is not None
    selected_player = controller.state.team_builder.current_offer[0].player
    controller.choose_player(FootballPosition.QB, 0)
    screen.state = controller.state
    desktop.router.draw(canvas)
    progress = pygame.Rect(38, 113, 146, 58)
    assert canvas.get_at((progress.right - 4, progress.top + 6)) == pygame.Color("#a1a8a3")
    assert controller.state.team_builder.selected_players[FootballPosition.QB] is selected_player


def test_draft_draws_do_not_mutate_controller_state_or_consume_offer_rng(
    tmp_path: Path,
) -> None:
    first = _new_desktop(tmp_path / "first")
    second = _new_desktop(tmp_path / "second")
    _start_run(first)
    _start_run(second)
    _activate(first, "CHOOSE STAFF 02")
    _activate(second, "CHOOSE STAFF 02")
    controller = first.football_controller
    other_controller = second.football_controller
    assert controller is not None and other_controller is not None
    initial_state = controller.state
    initial_offer = initial_state.team_builder.current_offer
    for _ in range(10):
        first.router.draw(_surface())
    assert controller.state == initial_state
    assert controller.state.team_builder.current_offer == initial_offer
    controller.choose_player(FootballPosition.QB, 1)
    other_controller.choose_player(FootballPosition.QB, 1)
    assert controller.state.team_builder.current_offer == other_controller.state.team_builder.current_offer


def test_player_draft_error_preserves_state_and_is_visible(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state

    def reject_choice(*_args, **_kwargs):
        raise ValueError("Draft rejected.")

    monkeypatch.setattr(controller, "choose_player", reject_choice)
    next(button for button in screen.buttons if button.label == "DRAFT QB").action()
    assert controller.state == before
    assert screen.state == before
    assert screen.last_error == "Draft rejected."
    canvas = _surface()
    desktop.router.draw(canvas)
    assert any(
        canvas.get_at((x, y)) == desktop.theme.danger
        for x in range(24, 800)
        for y in range(canvas.get_height() - 27, canvas.get_height() - 7)
    )


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

    assert pair.offense.name in " ".join(displayed)
    assert pair.defense.name in " ".join(displayed)
    assert "Hover or tab to scout a coach." in displayed
    assert "How position modifiers apply" not in displayed

    screen = desktop.run_screen
    offense = next(button for button in screen.buttons if button.label == "INSPECT OFFENSE 1")
    defense = next(button for button in screen.buttons if button.label == "INSPECT DEFENSE 1")

    def render() -> str:
        displayed.clear()
        desktop.router.draw(_surface())
        return " ".join(displayed)

    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": offense.rect.center}))
    text = render()
    assert f"Offense {pair.offense.name}" in text
    assert "How position modifiers apply" in text
    assert pair.offense.perk is not None
    assert pair.offense.perk.effect in text
    assert pair.defense.perk is not None
    assert pair.defense.perk.effect not in text
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(
            pygame.event.Event(event_type, {"pos": offense.rect.center, "button": 1})
        )
    assert controller.state.phase is FootballRunPhase.COACH_DRAFT

    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (defense.rect.left + 10, defense.rect.centery)}
    ))
    text = render()
    assert f"Defense {pair.defense.name}" in text
    assert "How position modifiers apply" in text
    assert pair.defense.perk.effect in text
    assert pair.offense.perk.effect not in text

    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    assert "How position modifiers apply" not in render()
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": defense.rect.center}))
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    assert "How position modifiers apply" not in render()

    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert f"Offense {pair.offense.name}" in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert f"Defense {pair.defense.name}" in render()
    assert controller.state.phase is FootballRunPhase.COACH_DRAFT
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    assert "How position modifiers apply" not in render()
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert controller.state.selected_coach_pair is controller.state.team_builder.coach_offer[1]


@pytest.mark.parametrize("staff", range(3))
@pytest.mark.parametrize("side", (1, 2))
@pytest.mark.parametrize("window_size", [(1280, 720), (960, 540), (1024, 768)])
def test_coach_popup_pointer_transfer_and_click_safety(
    tmp_path: Path, staff: int, side: int, window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.window_size = window_size
    surface = _surface()
    desktop.router.draw(surface)
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state
    index = staff * 3 + side
    row = screen.buttons[index].rect
    screen._focus(index)
    desktop.router.draw(surface)
    outline_point = (row.left, row.top + 20)
    original = surface.get_at(outline_point)

    popup = screen._coach_popup_rect(index)
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offsets = ((window_size[0] - round(1280 * scale)) // 2,
               (window_size[1] - round(720 * scale)) // 2)

    def logical_event(event_type, pos, **kwargs):
        physical = tuple(round(offsets[i] + pos[i] * scale) for i in range(2))
        return desktop._logical_event(pygame.event.Event(event_type, {"pos": physical, **kwargs}))

    target = (row.left + 10, row.centery)
    desktop.router.handle_event(logical_event(pygame.MOUSEMOTION, target))
    desktop.router.draw(surface)
    assert screen._coach_hover_index == index
    assert surface.get_at(outline_point) == desktop.theme.secondary
    assert surface.get_at((row.left + 6, row.top + 20)) == original
    assert pygame.Rect((0, 0), LOGICAL_SIZE).contains(popup)
    assert popup.left >= row.left and popup.right <= row.right
    assert popup.centery >= screen.buttons[staff * 3 + 1].rect.top
    assert all(not popup.colliderect(button.rect) for button in screen.buttons
               if button.variant == "coach-select")

    desktop.router.handle_event(logical_event(pygame.MOUSEMOTION, popup.center))
    desktop.router.draw(surface)
    assert screen._coach_hover_index == index
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(logical_event(event_type, popup.center, button=1))
    assert controller.state == before
    other_index = staff * 3 + (3 - side)
    other = screen.buttons[other_index].rect
    desktop.router.handle_event(logical_event(
        pygame.MOUSEMOTION, (other.left + 10, other.centery)
    ))
    assert screen._coach_hover_index == other_index
    desktop.router.draw(surface)
    assert screen._coach_popup_rect(other_index).left == popup.left
    button = screen.buttons[staff * 3]
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(logical_event(event_type, button.rect.center, button=1))
    assert controller.state.selected_coach_pair is before.team_builder.coach_offer[staff]


@pytest.mark.parametrize("staff", range(3))
def test_coach_hover_outline_clears_on_exit(tmp_path: Path, staff: int) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    surface = _surface()
    desktop.router.draw(surface)
    screen = desktop.run_screen
    row = screen.buttons[staff * 3 + 1].rect
    outline_point = (row.left, row.top + 20)
    original = surface.get_at(outline_point)
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    desktop.router.draw(surface)
    assert surface.get_at(outline_point) == desktop.theme.secondary
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    assert screen._coach_hover_index is None
    desktop.router.draw(surface)
    assert surface.get_at(outline_point) == original


@pytest.mark.parametrize("staff", range(3))
def test_coach_popup_keyboard_focus_shows_each_side(tmp_path: Path, staff: int, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    surface = _surface()
    desktop.router.draw(surface)
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state
    displayed: list[str] = []
    original_draw = football_run_screen_module.draw_text

    def capture(surface, text, position, font, color):
        displayed.append(text)
        original_draw(surface, text, position, font, color)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture)
    screen._focus(staff * 3)
    pair = before.team_builder.coach_offer[staff]
    for coach in (pair.offense, pair.defense):
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
        displayed.clear()
        desktop.router.draw(surface)
        assert coach.side.value.title() in displayed and coach.name in displayed
        assert "SCOUTING" in displayed
        assert "Keyboard scouting" in displayed
        popup = screen._coach_popup_rect(screen.focus_index)
        assert surface.get_at((popup.centerx, popup.top)) == desktop.theme.secondary
        assert surface.get_at((popup.centerx, popup.top + 6)) == pygame.Color("white")
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
        assert controller.state == before
    popup = screen._coach_popup_rect(staff * 3 + 2)
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": popup.center}))
    assert screen._coach_hover_index == staff * 3 + 2
    assert not screen._coach_keyboard_inspection


def test_coach_colors_have_readable_contrast() -> None:
    def luminance(color) -> float:
        channels = [component / 255 for component in pygame.Color(color)[:3]]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                  for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(first, second) -> float:
        high, low = sorted((luminance(first), luminance(second)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    module = football_run_screen_module
    for ink in (module._STAFF_INK, module._STAFF_MUTED):
        assert contrast(ink, module._STAFF_PAPER) >= 4.5
    for background, ink in (
        (module._STAFF_CARD, module._COACH_CHALK),
        (module._STAFF_CARD, "#c1c6c4"),
        (module._STAFF_CARD, module._STAFF_POSITIVE),
        (module._STAFF_CARD, module._STAFF_NEGATIVE),
        (module._STAFF_PERK, module._COACH_CHALK),
    ):
        assert contrast(background, ink) >= 4.5
    for color in COLOR_CHOICES:
        assert contrast(color.hex_value, readable_ink(pygame.Color(color.hex_value))) >= 4.5


@pytest.mark.parametrize(("primary", "secondary"), [
    ("navy", "gold"), ("silver", "slate"), ("crimson", "scarlet"),
    ("yellow", "lime"), ("blue", "navy"),
])
def test_coach_uses_saved_team_colors_for_hover_and_focus(
    tmp_path: Path, primary: str, secondary: str, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path, primary=primary, secondary=secondary)
    _start_run(desktop)
    screen = desktop.run_screen
    surface = _surface()
    marks: list[tuple[bool, pygame.Color]] = []
    original = football_run_screen_module.draw_playbook_mark

    def capture(surface, rect, *, offense, color):
        marks.append((offense, color))
        original(surface, rect, offense=offense, color=color)

    monkeypatch.setattr(football_run_screen_module, "draw_playbook_mark", capture)
    desktop.router.draw(surface)
    assert marks == [
        (side, desktop.theme.primary if staff == 0 else desktop.theme.secondary)
        for staff in range(3) for side in (True, False)
    ]
    row = screen.buttons[4].rect
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    desktop.router.draw(surface)
    popup = screen._coach_popup_rect(4)
    assert surface.get_at((row.left, row.top + 20)) == desktop.theme.secondary
    assert surface.get_at((popup.centerx, popup.top)) == desktop.theme.secondary
    button = screen.buttons[3]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": button.rect.center}))
    desktop.router.draw(surface)
    button = screen.buttons[3]
    sample = (button.rect.left + 15, button.rect.centery)
    assert surface.get_at(sample) == desktop.theme.primary
    button.enabled = False
    screen._draw_buttons(surface)
    assert surface.get_at(sample) == pygame.Color("#8b928d")
    button.enabled = True
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": button.rect.center, "button": 1}
    ))
    desktop.router.draw(surface)
    assert surface.get_at((button.rect.left + 15, button.rect.top + 6)) == readable_ink(desktop.theme.primary)
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {"pos": button.rect.center, "button": 1}
    ))
    assert desktop.football_controller.state.selected_coach_pair is not None


def test_hovering_coach_does_not_change_focused_staff(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen.buttons[4].rect.center}
    ))
    assert screen._coach_hover_index == 4
    assert screen.focus_index == 0
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(
            event_type, {"pos": screen.buttons[4].rect.center, "button": 1}
        ))
    assert screen.focus_index == 0
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT


@pytest.mark.parametrize(("primary", "secondary"), [
    ("navy", "gold"), ("silver", "slate"), ("crimson", "scarlet"),
])
def test_staff_mark_colors_follow_highlighted_buttons_and_popup(
    tmp_path: Path, primary: str, secondary: str, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path, primary=primary, secondary=secondary)
    _start_run(desktop)
    screen = desktop.run_screen
    controller = desktop.football_controller
    before = controller.state
    surface = _surface()
    marks: list[tuple[bool, pygame.Color]] = []
    original = football_run_screen_module.draw_playbook_mark

    def capture(surface, rect, *, offense, color):
        marks.append((offense, color))
        original(surface, rect, offense=offense, color=color)

    monkeypatch.setattr(football_run_screen_module, "draw_playbook_mark", capture)

    def check(highlighted: set[int], popup: tuple[int, bool] | None = None) -> None:
        marks.clear()
        desktop.router.draw(surface)
        expected = [
            (side, desktop.theme.primary if staff in highlighted else desktop.theme.secondary)
            for staff in range(3) for side in (True, False)
        ]
        if popup is not None:
            owner, offense = popup
            expected.append((offense, desktop.theme.primary if owner in highlighted
                             else desktop.theme.secondary))
        assert marks == expected
        for staff in range(3):
            rect = screen.buttons[staff * 3].rect
            expected_fill = desktop.theme.primary if staff in highlighted else pygame.Color("#c9ceca")
            assert surface.get_at((rect.left + 15, rect.centery)) == expected_fill
        assert controller.state == before

    check({0})
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen.buttons[6].rect.center}
    ))
    check({2})
    row = screen.buttons[1].rect
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    check({2}, (0, True))
    row = screen.buttons[2].rect
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    check({2}, (0, False))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (1, 1)}))
    screen._focus(3)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    check({1}, (1, True))
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    check({1}, (1, False))
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    check({2})
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": screen.buttons[0].rect.center}
    ))
    check({0})
    for _ in range(3):
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    check({0, 1})


def test_coach_screen_uses_staff_fonts_in_all_text_paths(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    screen.last_error = "Test error"
    used: list[tuple[str, pygame.font.Font]] = []
    buttons: list[pygame.font.Font] = []
    original_text = football_run_screen_module.draw_text
    original_wrapped = football_run_screen_module.draw_wrapped_text
    original_button = football_run_screen_module.Button.draw

    def text(surface, text, position, font, color):
        used.append((text, font))
        original_text(surface, text, position, font, color)

    def wrapped(surface, text, rect, font, color, **kwargs):
        used.append((text, font))
        original_wrapped(surface, text, rect, font, color, **kwargs)

    def button(self, surface, font, theme, **kwargs):
        buttons.append(font)
        original_button(self, surface, font, theme, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", text)
    monkeypatch.setattr(football_run_screen_module, "draw_wrapped_text", wrapped)
    monkeypatch.setattr(football_run_screen_module.Button, "draw", button)
    surface = _surface()
    desktop.router.draw(surface)
    row = screen.buttons[1].rect
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    desktop.router.draw(surface)
    screen.confirm_exit = True
    desktop.router.draw(surface)
    staff_fonts = {
        screen._staff_name_font, screen._staff_label_font, screen._staff_body_font,
        screen._staff_detail_font, screen._staff_stat_font, screen._staff_small_font,
        screen._staff_main_font, screen._staff_button_font, screen._staff_dialog_title_font,
    }
    assert any(text == "Build your staff" and font is screen._coach_title_font
               for text, font in used)
    assert any(text == "CHECK: Test error" and font is screen._staff_small_font
               for text, font in used)
    assert any(text == "End this run?" and font is screen._staff_dialog_title_font
               for text, font in used)
    assert all(font is screen._coach_title_font if text == "Build your staff"
               else font in staff_fonts for text, font in used)
    assert buttons and all(font is screen._staff_button_font for font in buttons)


@pytest.mark.parametrize("offense", [True, False])
def test_playbook_marks_are_deterministic_team_colored_and_contrasted(offense: bool) -> None:
    rect = pygame.Rect(0, 0, 64, 64)
    background = football_run_screen_module._STAFF_PAPER
    color = pygame.Color("#bcbcbc")
    first = pygame.Surface(rect.size)
    second = pygame.Surface(rect.size)
    first.fill(background)
    second.fill(background)
    coach_art.draw_playbook_mark(first, rect, offense=offense, color=color)
    coach_art.draw_playbook_mark(second, rect, offense=offense, color=color)
    assert pygame.image.tobytes(first, "RGB") == pygame.image.tobytes(second, "RGB")
    assert any(all(abs(first.get_at((x, y))[channel] - color[channel]) <= 3
                   for channel in range(3)) for x in range(64) for y in range(64))
    assert any(max(first.get_at((x, y))[:3]) <= 4
               for x in range(64) for y in range(64))
    # The former route and bracket extensions must not return.
    assert first.get_at((60, 32)) == background


@pytest.mark.parametrize("coach", (*OFFENSIVE_COACHES, *DEFENSIVE_COACHES))
def test_coach_detail_contains_all_data_without_clipping(tmp_path: Path, monkeypatch, coach) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    desktop.router.draw(_surface())
    displayed: list[str] = []
    colors: dict[str, pygame.Color] = {}
    original_text = football_run_screen_module.draw_text
    original_wrapped = football_run_screen_module.draw_wrapped_text
    card = pygame.Rect(104, 185, 312, 423)

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        colors[text] = pygame.Color(color)
        assert card.contains(pygame.Rect(position, font.size(text))), text
        original_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        assert card.contains(rect)
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
    screen._draw_coach_details(_surface(), card, coach, staff_index=0)
    for position, modifier in coach.position_modifiers.items():
        label = football_run_screen_module._coach_position_label(position)
        text = f"{label} {round(modifier * 100):+d}%"
        assert text in displayed
        assert colors[text] == (
            football_run_screen_module._STAFF_POSITIVE if modifier > 0 else
            football_run_screen_module._STAFF_NEGATIVE if modifier < 0 else
            football_run_screen_module._COACH_CHALK
        )
    assert "How position modifiers apply" in displayed
    assert any("Modifiers apply per player" in text for text in displayed)
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
        assert screen._staff_name_font.size(coach.name)[0] <= 254
        assert screen._coach_name_font.size(coach.name.upper())[0] <= 275
        for position, modifier in coach.position_modifiers.items():
            label = football_run_screen_module._coach_position_label(position)
            assert screen._staff_stat_font.size(
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
    assert controller.state.shop is not None
    assert controller.state.shop.section(FootballShopSection.PLAYS_SCHEMES).catalog_available
    assert "No play/scheme cards yet." not in joined
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


def test_shop_review_screens_show_run_snapshot_and_owned_playbook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    _activate(desktop, "BUY")
    shop = controller.state.shop
    assert shop is not None and shop.purchased_upgrades

    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text
    wrapped: list[str] = []
    original_draw_wrapped = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, *, line_gap=6):
        wrapped.append(text)
        original_draw_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_run_screen_module, "draw_wrapped_text", capture_wrapped
    )
    _activate(desktop, "DEPTH CHART")
    desktop.router.draw(_surface())
    assert "CURRENT RUN SNAPSHOT" in " ".join(displayed)
    assert "OFFENSE" in " ".join(displayed)
    assert "DEFENSE" in " ".join(displayed)
    assert "PURCHASED UPGRADE HISTORY" in " ".join(displayed)
    assert any("PLANNED / INACTIVE" in text for text in wrapped)
    assert any(shop.purchased_upgrades[0].name in text for text in wrapped)
    assert any(shop.purchased_upgrades[0].description in text for text in wrapped)
    for coach in football_run_screen_module.coaches_for_assignment(
        shop.roster.coach_assignment
    ):
        if coach is not None:
            for position, modifier in coach.position_modifiers.items():
                assert (
                    f"{football_run_screen_module._POSITION_LABELS[position]} "
                    f"{modifier:+.0%}"
                ) in " ".join(wrapped)
            if coach.perk is not None:
                for detail in (
                    coach.perk.trigger,
                    coach.perk.effect,
                    coach.perk.duration,
                    coach.perk.reset,
                ):
                    assert detail in " ".join(wrapped)
    for player in shop.roster.players.values():
        assert player.name in " ".join(displayed)
    assert "BACK TO SHOP" in {button.label for button in desktop.run_screen.buttons}
    assert desktop.run_screen._depth_chart_max_scroll > 0
    desktop.run_screen.handle_event(
        pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
    )
    assert desktop.run_screen._depth_chart_scroll > 0

    displayed.clear()
    _activate(desktop, "BACK TO SHOP")
    _activate(desktop, "PLAYBOOK")
    desktop.router.draw(_surface())
    joined = " ".join(displayed)
    assert "OWNED CARDS" in joined
    current_shop = controller.state.shop
    assert current_shop is not None
    for card in current_shop.offensive_deck:
        assert OFFENSIVE_PLAY_CATALOG[card.card_id].name in joined
    for card in current_shop.defensive_deck:
        assert DEFENSIVE_SCHEME_CATALOG[card.card_id].name in joined


def test_match_history_labels_turnovers_on_downs(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    result = FootballPlayResult(
        offensive_play=OffensivePlayAction.RB_RUN,
        yards_gained=3.0,
        clock_seconds_used=18,
        possession_changed=True,
        turnover_on_downs=True,
    )
    event = FootballMatchEvent(
        sequence=1,
        action=OffensivePlayAction.RB_RUN,
        team_a_score=0,
        team_b_score=0,
        possession=FootballTeamSide.TEAM_B,
        offense_field_position=78.0,
        down=1,
        yards_to_go=10.0,
        game_clock_seconds=882,
        period=1,
        status=FootballMatchStatus.IN_PROGRESS,
        clock_seconds_used=18,
        play_result=result,
    )

    text = desktop.run_screen._format_event(event, "Home", "Away")

    assert "Home" in text
    assert "turnover on downs" in text


def test_match_history_labels_ball_hawk_defensive_touchdown(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    result = FootballPlayResult(
        offensive_play=OffensivePlayAction.DEEP_PASS,
        yards_gained=0.0,
        clock_seconds_used=18,
        points_scored=7,
        turnover=True,
        possession_changed=True,
        defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
        perk_effects=("Ball-Hawk: +10 interception return yards",),
    )
    event = FootballMatchEvent(
        sequence=1,
        action=OffensivePlayAction.DEEP_PASS,
        team_a_score=0,
        team_b_score=7,
        possession=FootballTeamSide.TEAM_A,
        offense_field_position=25.0,
        down=1,
        yards_to_go=10.0,
        game_clock_seconds=882,
        period=1,
        status=FootballMatchStatus.IN_PROGRESS,
        clock_seconds_used=18,
        play_result=result,
        points_scored=7,
        scoring_team=FootballTeamSide.TEAM_B,
        perk_effects=result.perk_effects,
    )

    text = desktop.run_screen._format_event(event, "Home", "Away")

    assert "Away: defensive touchdown" in text
    assert "Home's DEEP PASS interception" in text
    assert "Ball-Hawk: +10 interception return yards" in text


def test_playbook_removal_can_be_cancelled_or_confirmed_in_the_ui(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    before = controller.state.shop

    _activate(desktop, "SELECT CARD")
    assert desktop.run_screen._shop_review_mode == "playbook"
    pending = controller.state.shop
    assert pending is not None and pending.pending_removal is not None
    assert pending.remaining_ap == before.remaining_ap
    desktop.router.draw(_surface())
    _activate(desktop, "CANCEL SELECTION")
    cancelled = controller.state.shop
    assert cancelled is not None and cancelled.pending_removal is None
    assert cancelled.remaining_ap == before.remaining_ap

    _activate(desktop, "SELECT CARD")
    desktop.router.draw(_surface())
    remove_button = next(
        button for button in desktop.run_screen.buttons if button.label == "REMOVE"
    )
    remove_button.action()
    removed = controller.state.shop
    assert removed is not None and removed.pending_removal is None
    assert removed.remaining_ap == before.remaining_ap - 2
    assert len(removed.offensive_deck) + len(removed.defensive_deck) == (
        len(before.offensive_deck) + len(before.defensive_deck) - 1
    )


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
            deck = state.match.team_a_offense_deck
            assert deck is not None and deck.hand
            card = deck.hand[0]
            expected = OFFENSIVE_PLAY_CATALOG[card.card_id].action
            hand_buttons = [
                button for button in screen.buttons if button.variant == "hand-card"
            ]
            assert len(hand_buttons) == min(3, len(deck.hand))
            hand_buttons[0].action()
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            seen_defense = True
            deck = state.match.team_a_defense_deck
            assert deck is not None and deck.hand
            card = deck.hand[0]
            expected = DEFENSIVE_SCHEME_CATALOG[card.card_id].action
            hand_buttons = [
                button for button in screen.buttons if button.variant == "hand-card"
            ]
            assert len(hand_buttons) == min(3, len(deck.hand))
            hand_buttons[0].action()
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            expected = FootballFourthDownAction.PUNT
            assert set(labels) - {"PAUSE"} == {
                "GO FOR IT",
                "PUNT",
                "FIELD GOAL",
            }
            labels["PUNT"].action()
        elif state.human_decision is FootballHumanDecision.CONVERSION:
            expected = FootballConversionAction.EXTRA_POINT
            labels["EXTRA POINT"].action()
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
    assert seen_offense and seen_defense and seen_ai_play
    desktop.router.draw(_surface())
    assert any(
        button.label in {"OPEN NEXT GAME SHOP", "RETURN TO MAIN MENU"}
        for button in screen.buttons
    )


def test_match_screen_previews_matchups_without_showing_roster_ratings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen

    rendered_text: list[str] = []
    draw_text = football_run_screen_module.draw_text

    def capture_text(*args, **kwargs):
        rendered_text.append(str(args[1]))
        return draw_text(*args, **kwargs)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    desktop.router.draw(_surface())
    assert any("1ST" in text and "YDS" in text for text in rendered_text)
    match = controller.state.match
    assert match is not None
    assert not any(
        player.name in " ".join(rendered_text)
        for roster in (match.team_a, match.team_b)
        for player in roster.players.values()
    )
    assert not any("POWER" in text.upper() or "RATING" in text.upper() for text in rendered_text)
    labels = {button.label: button for button in screen.buttons}
    match = controller.state.match
    assert match is not None and match.team_a_offense_deck is not None
    hand = match.team_a_offense_deck.hand
    expected_labels = [
        football_run_screen_module._PLAY_LABELS[
            OFFENSIVE_PLAY_CATALOG[card.card_id].action
        ]
        for card in hand
    ]
    assert [button.label for button in screen.buttons[:-1]] == expected_labels
    assert screen.buttons[-1].label == "PAUSE"

    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2})
    )
    match = controller.state.match
    assert match is not None
    assert match.match_events[-1].action is OFFENSIVE_PLAY_CATALOG[
        hand[1].card_id
    ].action

    desktop.router.draw(_surface())
    next(button for button in screen.buttons if button.label == "PAUSE").action()
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {
        "DISCARD RUN",
        "KEEP PLAYING",
    }


def test_match_cards_support_click_drag_drop_and_reject_invalid_drops(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen
    desktop.router.draw(_surface())
    state = controller.state
    assert state.match is not None and state.match.team_a_offense_deck is not None
    first_copy = state.match.team_a_offense_deck.hand[0]
    first_rect = screen._hand_card_rects[first_copy.copy_id]
    unchanged = controller.state

    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"pos": first_rect.center, "button": 1},
        )
    )
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"pos": (5, 5), "button": 1},
        )
    )
    assert controller.state == unchanged
    assert screen.last_error == "Invalid drop. Place the card in the play area."

    desktop.router.draw(_surface())
    first_rect = screen._hand_card_rects[first_copy.copy_id]
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"pos": first_rect.center, "button": 1},
        )
    )
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"pos": first_rect.center, "button": 1},
        )
    )
    after_click = controller.state
    assert after_click.match is not None
    assert first_copy in after_click.match.team_a_offense_deck.discard_pile

    desktop.router.draw(_surface())
    decision = controller.state.human_decision
    match = controller.state.match
    assert match is not None
    if decision is FootballHumanDecision.OFFENSIVE_PLAY:
        deck = match.team_a_offense_deck
    else:
        assert decision is FootballHumanDecision.DEFENSIVE_SCHEME
        deck = match.team_a_defense_deck
    assert deck is not None and deck.hand
    dragged_copy = deck.hand[0]
    dragged_rect = screen._hand_card_rects[dragged_copy.copy_id]
    assert screen._play_area_rect is not None
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"pos": dragged_rect.center, "button": 1},
        )
    )
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"pos": screen._play_area_rect.center, "button": 1},
        )
    )
    after_drop = controller.state.match
    assert after_drop is not None
    resulting_deck = (
        after_drop.team_a_offense_deck
        if decision is FootballHumanDecision.OFFENSIVE_PLAY
        else after_drop.team_a_defense_deck
    )
    assert resulting_deck is not None
    assert dragged_copy in resulting_deck.discard_pile


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
        _play_first_match_card(desktop)
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
    _play_first_match_card(desktop)

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
        for y in range(canvas.get_height() - 27, canvas.get_height() - 7)
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
    _play_first_match_card(first)
    _play_first_match_card(replay)
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
