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
    FootballCardCopy,
    FootballAwaitedAction,
    FootballCardFamily,
    FootballConversionAction,
    FootballDeckState,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchResult,
    FootballMatchStatus,
    FootballPlayResult,
    FootballPosition,
    FootballTeamSide,
    FootballCoachUpgradeKind,
    FootballCoachAssignment,
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
    OFFENSIVE_POSITIONS,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.engine.football_appearance import POSITION_ART
from src.engine.football_team_builder import FootballPlayerCandidate
from src.engine.football_player_catalog import (
    PLAYER_TYPES_BY_POSITION,
    player_from_type,
    player_type_for_id,
)
from src.ui.theme import readable_ink, relative_luminance
from src.engine.football_shop import (
    COACH_UPGRADE_CATALOG,
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballShopSlotState,
)
from src.profile import COLOR_CHOICES
from src.ui.application import DesktopApplication
from src.ui import coach_art
from src.ui import football_run_screen as football_run_screen_module
from src.ui import football_match_decision_view as football_match_decision_module
from src.ui.football_display import _PLAY_LABELS, _POSITION_LABELS
from src.ui import football_coach_view as football_coach_module
from src.ui import football_review_view as football_review_module
from src.ui import football_depth_chart as football_depth_module
from src.ui import football_result as football_result_module
from src.ui import football_shop_view as football_shop_module
from src.ui import football_player_draft_view as football_player_draft_module
from src.ui.football_match_status import FootballMatchStatusView
from src.ui import player_art
from src.ui.layout import LOGICAL_SIZE
from src.ui.layout import Layout
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.text import wrap_text_lines
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


def test_draft_cards_show_complete_actual_catalog_data(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    state = screen.state
    assert state is not None
    shown = []
    original = football_player_draft_module.draw_complete_wrapped_text

    def capture(surface, text, rect, font, color, **kwargs):
        shown.append((text, rect.copy()))
        return original(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_player_draft_module, "draw_complete_wrapped_text", capture)
    for types in PLAYER_TYPES_BY_POSITION.values():
        for player_type in types:
            player = replace(player_from_type(player_type), power=63.25,
                             volatility=0.125, stamina=0.735)
            candidate = FootballPlayerCandidate(player, "test")
            screen.state = replace(state, team_builder=replace(
                state.team_builder, current_offer=(candidate, candidate, candidate)))
            shown.clear()
            desktop.router.draw(_surface())
            assert len(shown) == 6
            for index in range(3):
                name, name_rect = shown[index * 2]
                text, text_rect = shown[index * 2 + 1]
                assert name == player_type.name
                assert screen.player_inspection.card_rects[index].contains(name_rect)
                assert not text_rect.colliderect(screen.buttons[index].rect)
                if player_type.perk is None:
                    assert text == "Perk: None"
                else:
                    assert "PLANNED / INACTIVE" in text
                    for part in (player_type.perk.name, player_type.perk.trigger,
                                 player_type.perk.effect, player_type.perk.duration,
                                 player_type.perk.reset, player_type.perk.dependency):
                        assert part in text


def test_draft_card_stats_and_partners_are_visible_without_interaction(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    state = screen.state
    assert state is not None
    offers = state.team_builder.current_offer
    changed = tuple(replace(candidate, player=replace(
        candidate.player, power=61.25 + index, volatility=0.125 + index / 100,
        stamina=0.735 + index / 100)) for index, candidate in enumerate(offers))
    screen.state = replace(state, team_builder=replace(state.team_builder, current_offer=changed))
    shown = []
    original = football_player_draft_module.draw_text

    def capture(surface, text, position, font, color):
        shown.append((text, position))
        original(surface, text, position, font, color)

    monkeypatch.setattr(football_player_draft_module, "draw_text", capture)
    desktop.router.draw(_surface())
    for index, candidate in enumerate(changed):
        rect = screen.player_inspection.card_rects[index]
        texts = [text for text, point in shown if rect.collidepoint(point)]
        player_type = player_type_for_id(candidate.player.player_type_id)
        partner = ("None" if player_type.partner_position is None else
                   football_player_draft_module._draft_position_label(player_type.partner_position))
        assert f"Partner: {partner}" in texts
        assert str(candidate.player.power) in texts
        assert football_player_draft_module._draft_percentage(candidate.player.volatility) in texts
        assert football_player_draft_module._draft_percentage(candidate.player.stamina) in texts


def test_each_card_uses_its_actual_candidate_position(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    state = screen.state
    candidates = tuple(
        FootballPlayerCandidate(player_from_type(PLAYER_TYPES_BY_POSITION[position][0]), "test")
        for position in (FootballPosition.WR, FootballPosition.QB, FootballPosition.RB)
    )
    screen.state = replace(state, team_builder=replace(
        state.team_builder, current_offer=candidates))
    drawn = []
    original = football_player_draft_module.draw_draft_player

    def capture(surface, rect, appearance, active=False):
        drawn.append(appearance)
        original(surface, rect, appearance, active)

    monkeypatch.setattr(football_player_draft_module, "draw_draft_player", capture)
    desktop.router.draw(_surface())
    assert [item.asset_key for item in drawn] == ["wide_receiver", "quarterback", "running_back"]
    assert [item.skin for item in drawn] == list(screen.player_inspection.skin_tones)


def test_resized_draft_preserves_smooth_text_and_crisp_portraits(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    canvas = _surface()
    desktop.router.draw(canvas)
    window = pygame.Surface((960, 540))
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    desktop._present(canvas, window, portraits=desktop.run_screen.player_inspection.portraits)
    smooth = pygame.transform.smoothscale(canvas, window.get_size())
    assert pygame.image.tobytes(window.subsurface((0, 0, 960, 100)), "RGB") == (
        pygame.image.tobytes(smooth.subsurface((0, 0, 960, 100)), "RGB")
    )
    portrait = desktop.run_screen.player_inspection.portraits[0][0]
    rect = pygame.Rect(round(portrait.x * 0.75), round(portrait.y * 0.75),
                       round(portrait.width * 0.75), round(portrait.height * 0.75))
    assert pygame.image.tobytes(window.subsurface(rect), "RGB") != (
        pygame.image.tobytes(smooth.subsurface(rect), "RGB")
    )


def test_identically_named_candidates_keep_their_own_appearance(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    controller = desktop.football_controller
    assert controller is not None
    offers = tuple(
        replace(candidate, player=replace(candidate.player, name="Same Name"))
        for candidate in controller.state.team_builder.current_offer
    )
    controller._builder._current_offer = offers
    desktop.run_screen.state = controller.state
    tones = iter(player_art.SKIN_TONES)
    monkeypatch.setattr("src.ui.football_draft_interaction.secrets.choice", lambda _: next(tones))
    desktop.router.draw(_surface())
    button = desktop.run_screen.buttons[2]
    button.action()
    assert controller.state.team_builder.selected_players[FootballPosition.QB] is offers[2].player
    assert controller.state.player_appearances[FootballPosition.QB].skin == player_art.SKIN_TONES[2]
    before = controller.state
    button.action()
    assert controller.state == before
    assert desktop.run_screen.last_error is not None


@pytest.mark.parametrize("window_size", [(1280, 720), (960, 540), (1024, 768)])
def test_draft_button_events_activate_correct_card_at_scaled_sizes(
    tmp_path: Path, monkeypatch, window_size,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    desktop.window_size = window_size
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    selected = controller.state.team_builder.current_offer[2].player
    poses = []
    original = football_player_draft_module.draw_draft_player

    def capture(surface, rect, appearance, active=False):
        poses.append((appearance, active))
        original(surface, rect, appearance, active)

    monkeypatch.setattr(football_player_draft_module, "draw_draft_player", capture)
    canvas = _surface()
    desktop.router.draw(canvas)
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offsets = ((window_size[0] - round(1280 * scale)) // 2,
               (window_size[1] - round(720 * scale)) // 2)

    def mouse(kind, point, **extra):
        pos = tuple(round(offsets[i] + point[i] * scale) for i in range(2))
        desktop.router.handle_event(desktop._logical_event(
            pygame.event.Event(kind, {"pos": pos, **extra})))

    button = screen.buttons[2]
    mouse(pygame.MOUSEMOTION, button.rect.center)
    poses.clear()
    desktop.router.draw(canvas)
    assert all(pose.asset_key == "quarterback" for pose, _ in poses)
    assert all(pose.primary == tuple(desktop.theme.primary[:3])
               and pose.secondary == tuple(desktop.theme.secondary[:3]) for pose, _ in poses)
    assert [active for _, active in poses] == [False, False, True]
    selected_appearance = poses[2][0]
    rect = screen.player_inspection.card_rects[2]
    assert canvas.get_at((rect.left, rect.centery)) == desktop.theme.primary
    assert canvas.get_at((button.rect.left + 12, button.rect.top + 10)) == desktop.theme.primary
    mouse(pygame.MOUSEBUTTONDOWN, button.rect.center, button=1)
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    mouse(pygame.MOUSEBUTTONUP, button.rect.center, button=1)
    assert not controller.state.team_builder.selected_players
    poses.clear()
    desktop.router.draw(canvas)
    assert poses[2] == (selected_appearance, False)
    mouse(pygame.MOUSEBUTTONDOWN, button.rect.center, button=1)
    mouse(pygame.MOUSEBUTTONUP, (1, 1), button=1)
    assert not controller.state.team_builder.selected_players
    assert screen.player_inspection.hover_index is None
    mouse(pygame.MOUSEBUTTONDOWN, button.rect.center, button=1)
    mouse(pygame.MOUSEBUTTONUP, button.rect.center, button=1)
    assert controller.state.team_builder.selected_players[FootballPosition.QB] is selected
    assert controller.state.player_appearances[FootballPosition.QB] == selected_appearance


def test_draft_keyboard_focus_and_skin_tone_lifetime(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    tones = iter(player_art.SKIN_TONES)
    monkeypatch.setattr("src.ui.football_draft_interaction.secrets.choice", lambda _: next(tones))
    screen.player_inspection.offers = ()
    canvas = _surface()
    desktop.router.draw(canvas)
    first = screen.player_inspection.skin_tones
    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
    desktop.router.draw(canvas)
    assert screen.player_inspection.active_index(screen.focus_index) == 1
    assert screen.player_inspection.skin_tones == first
    rect = screen.player_inspection.card_rects[1]
    assert canvas.get_at((rect.left, rect.centery)) == desktop.theme.primary
    selected = desktop.football_controller.state.team_builder.current_offer[1].player
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert desktop.football_controller.state.team_builder.selected_players[FootballPosition.QB] is selected
    assert desktop.football_controller.state.player_appearances[FootballPosition.QB].skin == first[1]
    desktop.router.draw(canvas)
    assert screen.player_inspection.skin_tones != first
    assert screen.player_inspection.skin_tones == player_art.SKIN_TONES[3:]


def test_heisman_pose_tracks_card_hover_and_keyboard_for_every_position(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    controller = desktop.football_controller
    assert controller is not None
    seen = []
    original = football_player_draft_module.draw_draft_player

    def capture(surface, rect, appearance, active=False):
        seen.append((appearance, active))
        original(surface, rect, appearance, active)

    monkeypatch.setattr(football_player_draft_module, "draw_draft_player", capture)
    canvas = _surface()
    for position in PLAYER_DRAFT_ORDER:
        desktop.router.draw(canvas)
        tones = screen.player_inspection.skin_tones
        before = controller.state
        for index, card in enumerate(screen.player_inspection.card_rects):
            point = (card.centerx, card.top + 100)
            desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": point}))
            seen.clear()
            desktop.router.draw(canvas)
            assert [active for _, active in seen] == [i == index for i in range(3)]
            assert [art.skin for art, _ in seen] == list(tones)
            assert all(art.asset_key == POSITION_ART[position] for art, _ in seen)
            assert screen.player_inspection.portraits[index][2]
        desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
        seen.clear()
        desktop.router.draw(canvas)
        assert not any(active for _, active in seen)
        screen._focus(1)
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}))
        seen.clear()
        desktop.router.draw(canvas)
        assert [active for _, active in seen] == [False, False, True]
        assert controller.state == before
        chosen = seen[2][0]
        _activate(desktop, f"DRAFT {position.value}", index=2, keyboard=True)
        assert controller.state.player_appearances[position] == chosen
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP


def test_heisman_pose_is_preserved_in_resized_presentation(tmp_path: Path, monkeypatch) -> None:
    from src.ui import application as application_module

    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    canvas = _surface()
    desktop.router.draw(canvas)
    card = desktop.run_screen.player_inspection.card_rects[1]
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (card.centerx, card.top + 100)}))
    desktop.router.draw(canvas)
    seen = []
    original = application_module.draw_draft_player

    def capture(surface, rect, appearance, active=False):
        seen.append((appearance, active))
        original(surface, rect, appearance, active)

    monkeypatch.setattr(application_module, "draw_draft_player", capture)
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    desktop._present(canvas, pygame.Surface((960, 540)),
                     portraits=desktop.run_screen.player_inspection.portraits)
    assert [active for _, active in seen] == [False, True, False]
    assert [appearance for appearance, _ in seen] == [
        appearance for _, appearance, _ in desktop.run_screen.player_inspection.portraits
    ]


def test_draft_progress_uses_selected_players_and_selection_actions(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen
    displayed: list[str] = []
    original_text = football_run_screen_module.draw_text
    original_wrapped = football_run_screen_module.draw_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, **kwargs):
        displayed.append(text)
        original_wrapped(surface, text, rect, font, color, **kwargs)

    monkeypatch.setattr(football_player_draft_module, "draw_text", capture_text)
    chosen = []
    appearances = {}
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        displayed.clear()
        canvas = _surface()
        desktop.router.draw(canvas)
        assert displayed.count("Drafted") == index
        assert displayed.count("Current pick") == 1
        assert displayed.count("Up next") == len(PLAYER_DRAFT_ORDER) - index - 1
        assert all(name in displayed for name in chosen)
        for row in range(len(PLAYER_DRAFT_ORDER)):
            expected = "#35404b" if row < index else (
                "#214363" if row == index else "#091c30"
            )
            assert canvas.get_at((180, 171 + row * 57 + 40)) == pygame.Color(expected)
        candidate = controller.state.team_builder.current_offer[1]
        appearance = screen.player_inspection.skin_tones[1]
        chosen.append(candidate.name)
        _activate(desktop, f"DRAFT {position.value}", index=1, keyboard=index % 2 == 0)
        assert controller.state.team_builder.selected_players[position] is candidate.player
        appearances[position] = controller.state.player_appearances[position]
        assert appearances[position].asset_key == POSITION_ART[position]
        assert appearances[position].skin == appearance
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert controller.state.player_appearances == appearances
    _activate(desktop, "DEPTH CHART")
    desktop.router.draw(_surface())
    assert controller.state.player_appearances == appearances












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




















@pytest.mark.parametrize("offense", [True, False])
def test_playbook_marks_are_deterministic_team_colored_and_contrasted(offense: bool) -> None:
    rect = pygame.Rect(0, 0, 64, 64)
    background = pygame.Color("#a1a8a3")
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


def test_coach_view_navigation_resets_inspection_and_uses_updated_profile(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path, seeds=(17, 29, 4, 1, 18, 30, 5, 2))
    _start_run(desktop)
    screen = desktop.run_screen
    desktop.router.draw(_surface())
    first_controller = desktop.football_controller
    assert first_controller is not None
    before = first_controller.state
    row = screen.coach_inspection.card_rects[1]
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": (row.left + 10, row.centery)}
    ))
    assert screen.coach_inspection.hover_index == 1
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert screen.confirm_exit
    _activate(desktop, "KEEP PLAYING")
    assert not screen.confirm_exit
    assert first_controller.state == before
    _activate(desktop, "CHOOSE STAFF 02", keyboard=True)
    assert first_controller.state.selected_coach_pair is before.team_builder.coach_offer[1]
    assert first_controller.state.phase is FootballRunPhase.PLAYER_DRAFT

    _activate(desktop, "END RUN")
    _activate(desktop, "DISCARD RUN")
    assert desktop.router.current_id == "main_menu"
    desktop.save_profile("Fresh Coaches", "crimson", "gold")
    displayed: list[str] = []
    original_text = football_coach_module.draw_text

    def capture(surface, text, position, font, color):
        displayed.append(text)
        original_text(surface, text, position, font, color)

    monkeypatch.setattr(football_coach_module, "draw_text", capture)
    _start_run(desktop)
    desktop.router.draw(_surface())
    assert desktop.football_controller is not first_controller
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert screen.coach_inspection.hover_index is None
    assert not screen.coach_inspection.window_left
    assert screen._coach_view().theme == desktop.theme


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
    original_draw_text = football_shop_module.draw_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    football_shop_module.draw_text = capture_text
    try:
        desktop.router.draw(_surface())
    finally:
        football_shop_module.draw_text = original_draw_text

    joined = " ".join(displayed)
    assert "THREE SHOPS  /  ONE SHARED AP BUDGET" in joined
    assert "ACTION POINTS" in joined
    assert "PLAYER UPGRADES" in joined
    assert "PLAYS / SCHEMES" in joined
    assert "COACH UPGRADES" in joined
    assert controller.state.shop is not None
    assert controller.state.shop.section(FootballShopSection.PLAYS_SCHEMES).catalog_available
    assert "No play/scheme cards yet." not in joined
    assert "Available after game 3." in joined
    assert "Two-Minute Drill" not in joined
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
    complete_lines: list[tuple[str, ...]] = []
    original_complete_wrapped = football_depth_module.draw_complete_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, *, line_gap=6):
        wrapped.append(text)
        original_draw_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    def capture_complete_wrapped(
        surface, text, rect, font, color, *, line_gap=2
    ):
        lines = wrap_text_lines(text, font, rect.width)
        assert all(font.size(line)[0] <= rect.width for line in lines)
        assert len(lines) * (font.get_height() + line_gap) - line_gap <= rect.height
        complete_lines.append(lines)
        return original_complete_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_run_screen_module, "draw_wrapped_text", capture_wrapped
    )
    monkeypatch.setattr(football_depth_module, "draw_text", capture_text)
    monkeypatch.setattr(football_review_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_depth_module,
        "draw_complete_wrapped_text",
        capture_complete_wrapped,
    )
    _activate(desktop, "DEPTH CHART")
    desktop.router.draw(_surface())
    assert "CURRENT RUN SNAPSHOT" in " ".join(displayed)
    complete_text = " ".join(line for lines in complete_lines for line in lines)
    assert "OFFENSE" in complete_text and "DEFENSE" in complete_text
    assert "PLANNED / INACTIVE" in complete_text
    for coach in football_depth_module.coaches_for_assignment(
        shop.roster.coach_assignment
    ):
        if coach is not None:
            for position, modifier in coach.position_modifiers.items():
                assert (
                    f"{_POSITION_LABELS[position]} "
                    f"{modifier:+.0%}"
                ) in complete_text
            if coach.perk is not None:
                assert football_coach_module.coach_perk_text(coach) in " ".join(
                    " ".join(lines) for lines in complete_lines
                )
    for player in shop.roster.players.values():
        assert player.name in complete_text
    assert "BACK TO SHOP" in {button.label for button in desktop.run_screen.buttons}
    assert desktop.run_screen.shop_review.depth_max_scroll == 0
    _activate(desktop, "UPGRADES / PERK DETAILS")
    desktop.router.draw(_surface())
    assert "PURCHASED RUN UPGRADES" in " ".join(displayed)
    complete_text = " ".join(line for lines in complete_lines for line in lines)
    assert shop.purchased_upgrades[0].name in complete_text
    assert shop.purchased_upgrades[0].description in complete_text
    assert desktop.run_screen.shop_review.depth_max_scroll > 0
    desktop.run_screen.handle_event(
        pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
    )
    assert desktop.run_screen.shop_review.depth_scroll > 0

    displayed.clear()
    _activate(desktop, "BACK TO SHOP")
    _activate(desktop, "PLAYBOOK")
    desktop.router.draw(_surface())
    assert "OWNED CARDS" in " ".join(displayed)
    for _ in range(desktop.run_screen.shop_review.playbook_max_scroll):
        desktop.run_screen.handle_event(
            pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
        )
        desktop.router.draw(_surface())
    joined = " ".join(displayed)
    current_shop = controller.state.shop
    assert current_shop is not None
    for card in current_shop.offensive_deck:
        assert OFFENSIVE_PLAY_CATALOG[card.card_id].name in joined
    for card in current_shop.defensive_deck:
        assert DEFENSIVE_SCHEME_CATALOG[card.card_id].name in joined


def test_depth_chart_renders_run_art_details_and_router_toggle(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        desktop.router.draw(_surface())
        screen = desktop.run_screen
        tone = player_art.SKIN_TONES[index % len(player_art.SKIN_TONES)]
        screen.player_inspection.skin_tones = (tone,) * 3
        _activate(desktop, f"DRAFT {position.value}", index=2 if index == 0 else 0, keyboard=True)
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state
    assert before.shop is not None
    assert before.team_builder.current_offer == ()
    assert len(before.drafted_players) == len(before.player_appearances) == 8
    art = []
    portraits = []
    text = []
    original_art = football_depth_module.draw_draft_player
    original_portrait = football_depth_module.draw_coach_portrait
    original_text = football_depth_module.draw_complete_wrapped_text

    def capture_art(surface, rect, appearance, active=False):
        art.append(appearance)
        original_art(surface, rect, appearance, active)

    def capture_portrait(surface, rect, coach_id, primary):
        portraits.append((coach_id, tuple(primary[:3])))
        original_portrait(surface, rect, coach_id, primary)

    def capture_text(surface, value, rect, font, color, *, line_gap=2):
        text.append(value)
        return original_text(surface, value, rect, font, color, line_gap=line_gap)

    monkeypatch.setattr(football_depth_module, "draw_draft_player", capture_art)
    monkeypatch.setattr(football_depth_module, "draw_coach_portrait", capture_portrait)
    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture_text)
    desktop.router.draw(_surface())
    old_buy = next(button.rect.center for button in desktop.run_screen.buttons if button.label == "BUY")
    _activate(desktop, "DEPTH CHART")
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(event_type, {"pos": old_buy, "button": 1}))
    assert controller.state == before
    art.clear()
    portraits.clear()
    text.clear()
    desktop.router.draw(_surface())
    assert art == [before.player_appearances[position] for position in PLAYER_DRAFT_ORDER]
    assert [a.asset_key for a in art] == [POSITION_ART[position] for position in PLAYER_DRAFT_ORDER]
    pair = before.selected_coach_pair
    assert pair is not None
    assert portraits == [(pair.offense.coach_id, tuple(desktop.theme.primary[:3])),
                         (pair.defense.coach_id, tuple(desktop.theme.primary[:3]))]
    for coach in (pair.offense, pair.defense):
        assert any(coach.name in item for item in text)
        assert any(football_coach_module.coach_perk_text(coach) in item for item in text)
    for position in PLAYER_DRAFT_ORDER:
        player = before.drafted_players[position]
        assert sum(player.name in item for item in text) == 1
        player_type = player_type_for_id(player.player_type_id)
        from src.ui.football_display import player_partnership_text
        partner, explanation = player_partnership_text(player_type)
        assert partner in text
        assert all(part in text for part in football_depth_module._detail_sections(player)[1])
        if player_type.perk is not None:
            assert all(detail in football_depth_module._compact_player_details(player) for detail in (
                "PLANNED / INACTIVE", player_type.perk.name, player_type.perk.trigger, player_type.perk.effect
            ))
        if explanation:
            assert any(explanation in item for item in text)
    assert "Partner: None" in text and "Perk: None" in text
    assert not desktop.run_screen.shop_review.modified_stats
    _activate(desktop, "STARTING STATS / SHOW MODIFIED STATS", keyboard=True)
    assert desktop.run_screen.shop_review.modified_stats
    text.clear()
    desktop.router.draw(_surface())
    assert controller.state == before
    _activate(desktop, "MODIFIED STATS / SHOW STARTING STATS")
    assert not desktop.run_screen.shop_review.modified_stats
    _activate(desktop, "STARTING STATS / SHOW MODIFIED STATS")
    _activate(desktop, "BACK TO SHOP", keyboard=True)
    _activate(desktop, "DEPTH CHART", keyboard=True)
    assert not desktop.run_screen.shop_review.modified_stats
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_END}))
    assert desktop.run_screen.shop_review.depth_scroll == desktop.run_screen.shop_review.depth_max_scroll
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_HOME}))
    assert desktop.run_screen.shop_review.depth_scroll == 0
    assert controller.state == before


def test_depth_chart_modified_stats_use_only_persistent_effects(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    initial = controller.state
    offered = next(upgrade for upgrade in initial.shop.offer if upgrade.stat.value == "power")
    controller.buy_upgrade(offered)
    after = controller.state
    assert after.shop is not None
    assert after.drafted_players == initial.drafted_players
    assert after.drafted_players[offered.position].power + offered.amount == after.shop.roster.players[offered.position].power
    effects = tuple(card for card in COACH_UPGRADE_CATALOG if card.coach_upgrade_effect is not None)
    state = replace(after, shop=replace(after.shop, owned_coach_upgrades=effects))
    for position in PLAYER_DRAFT_ORDER:
        player = state.shop.roster.players[position]
        offense = position in OFFENSIVE_POSITIONS
        coach = state.selected_coach_pair.offense if offense else state.selected_coach_pair.defense
        power, volatility, stamina = football_depth_module.modified_player_stats(state, position)
        assert power == pytest.approx(player.power * (1 + coach.position_modifiers[position]) * 1.05)
        assert volatility == pytest.approx(player.volatility * 0.85)
        assert stamina == pytest.approx(min(1, player.stamina + 0.1))
    nonstat = tuple(card for card in effects if card.coach_upgrade_effect.kind in (
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
    ))
    without = replace(state, shop=replace(state.shop, owned_coach_upgrades=()))
    with_nonstat = replace(state, shop=replace(state.shop, owned_coach_upgrades=nonstat))
    for position in PLAYER_DRAFT_ORDER:
        assert football_depth_module.modified_player_stats(without, position) == football_depth_module.modified_player_stats(with_nonstat, position)
    capped_cards = []
    for kind in (FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
                 FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
                 FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST):
        card = next(card for card in effects if card.coach_upgrade_effect.kind is kind)
        capped_cards.append(replace(card, coach_upgrade_effect=replace(card.coach_upgrade_effect, magnitude=0.9)))
    capped = replace(state, shop=replace(state.shop, owned_coach_upgrades=tuple(capped_cards)))
    qb = capped.shop.roster.players[FootballPosition.QB]
    coach = capped.selected_coach_pair.offense
    power, volatility, stamina = football_depth_module.modified_player_stats(capped, FootballPosition.QB)
    assert power == pytest.approx(qb.power * (1 + coach.position_modifiers[FootballPosition.QB]) * 1.2)
    assert volatility == pytest.approx(qb.volatility * 0.7)
    assert stamina == pytest.approx(min(1, qb.stamina + 0.3))
    assert controller.state == after


def test_depth_chart_card_geometry_and_stat_comparisons(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    _activate(desktop, "DEPTH CHART")
    cards = []
    portraits = []
    boxes = []
    wrapped = []
    text = []
    original_art = football_depth_module.draw_draft_player
    original_wrapped = football_depth_module.draw_complete_wrapped_text
    original_text = football_depth_module.draw_text
    original_box = football_depth_module._rounded_box

    def capture_art(surface, rect, appearance, active=False):
        portraits.append((rect.copy(), appearance))
        return original_art(surface, rect, appearance, active)

    def capture_wrapped(surface, value, rect, font, color, *, line_gap=2):
        wrapped.append((value, rect.copy()))
        return original_wrapped(surface, value, rect, font, color, line_gap=line_gap)

    def capture_text(surface, value, position, font, color):
        text.append((value, position, font, color))
        return original_text(surface, value, position, font, color)

    def capture_box(surface, rect, fill, edge, radius=6):
        if fill == football_depth_module._PERK_BOX:
            boxes.append(rect.copy())
        if fill == football_depth_module._CARD:
            cards.append(rect.copy())
        return original_box(surface, rect, fill, edge, radius)

    monkeypatch.setattr(football_depth_module, "draw_draft_player", capture_art)
    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture_wrapped)
    monkeypatch.setattr(football_depth_module, "draw_text", capture_text)
    monkeypatch.setattr(football_depth_module, "_rounded_box", capture_box)
    desktop.router.draw(_surface())
    boxes = [box for box in boxes if any(card.contains(box) for card in cards)]
    assert desktop.run_screen.shop_review.depth_max_scroll == 0
    assert len(cards) == len(portraits) == len(boxes) == 8
    assert len({rect.size for rect in cards}) == 1
    state = controller.state
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        card = cards[index]
        art, appearance = portraits[index]
        assert card.inflate(-10, -10).contains(art)
        assert appearance == state.player_appearances[position]
        player = state.shop.roster.players[position]
        name_rect = next(rect for value, rect in wrapped if player.name in value)
        partner, perk = football_depth_module._detail_sections(player)
        detail_rect = next(rect for value, rect in wrapped
                           if value == partner[0] and card.contains(rect))
        box = boxes[index]
        assert card.contains(name_rect) and card.contains(detail_rect)
        assert card.inflate(-6, -6).contains(box)
        assert detail_rect.left > art.right and box.left > art.right
        assert detail_rect.top < art.bottom
        for line in perk:
            assert any(value == line and box.inflate(-12, -8).contains(rect)
                       for value, rect in wrapped)
    assert len([item for item in text if item[0].startswith(("POWER ", "VOLATILITY ", "STAMINA "))
                and any(card.collidepoint(item[1]) for card in cards)]) == 24
    cards.clear()
    text.clear()
    _activate(desktop, "STARTING STATS / SHOW MODIFIED STATS", keyboard=True)
    cards.clear()
    text.clear()
    desktop.router.draw(_surface())
    comparisons = [item for item in text if item[0].startswith("(")]
    assert len(comparisons) == 24
    assert all(font is football_depth_module._font(12, True) for _, _, font, _ in comparisons)
    assert all(value.endswith(")") for value, _, _, _ in comparisons)
    for value, position, font, _ in comparisons:
        rect = pygame.Rect(position, font.size(value))
        assert any(card.contains(rect) for card in cards)
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        starting = state.drafted_players[position]
        current = football_depth_module.modified_player_stats(state, position)
        expected = (
            football_depth_module._comparison(current[0], starting.power, lower_is_better=False, percentage=False),
            football_depth_module._comparison(current[1], starting.volatility, lower_is_better=True, percentage=True),
            football_depth_module._comparison(current[2], starting.stamina, lower_is_better=False, percentage=True),
        )
        assert [(value, color) for value, _, _, color in comparisons[index * 3:index * 3 + 3]] == list(expected)
    volatility_card = next(card for card in COACH_UPGRADE_CATALOG
                           if card.coach_upgrade_effect is not None
                           and card.coach_upgrade_effect.kind is FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION)
    modified_state = replace(state, shop=replace(state.shop, owned_coach_upgrades=(volatility_card,)))
    review = football_review_module.FootballReviewView(
        desktop.theme, desktop.run_screen._small_font, desktop.run_screen._label_font,
        desktop.run_screen.shop_review, lambda: None, lambda _copy_id: None,
    )
    text.clear()
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 1240, 690), modified_state)
    assert any(value == "(-1.5 pp)" and color == football_depth_module._POSITIVE
               for value, _, _, color in text)
    assert controller.state == state
    compare = football_depth_module._comparison
    assert compare(0.08, 0.1, lower_is_better=True, percentage=True) == ("(-2 pp)", football_depth_module._POSITIVE)
    assert compare(0.12, 0.1, lower_is_better=True, percentage=True) == ("(+2 pp)", football_depth_module._NEGATIVE)
    assert compare(0.1, 0.1, lower_is_better=True, percentage=True) == ("(+0 pp)", football_depth_module._NEUTRAL)
    assert compare(53, 50, lower_is_better=False, percentage=False) == ("(+3)", football_depth_module._POSITIVE)
    assert compare(47, 50, lower_is_better=False, percentage=False) == ("(-3)", football_depth_module._NEGATIVE)


def test_depth_chart_coach_modifier_colors_and_sections(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.selected_coach_pair is not None
    pair = controller.state.selected_coach_pair
    captured = []
    boxes = []
    original = football_depth_module.draw_complete_wrapped_text
    original_box = football_depth_module._rounded_box

    def capture(surface, text, rect, font, color, *, line_gap=2):
        captured.append((text, rect.copy(), color))
        return original(surface, text, rect, font, color, line_gap=line_gap)

    def capture_box(surface, rect, fill, edge, radius=6):
        if fill == football_depth_module._PERK_BOX:
            boxes.append(rect.copy())
            assert edge == football_depth_module._PERK_EDGE
        return original_box(surface, rect, fill, edge, radius)

    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture)
    monkeypatch.setattr(football_depth_module, "_rounded_box", capture_box)
    staff = pygame.Rect(20, 71, 300, 579)
    football_depth_module._draw_staff(_surface(), staff, controller.state, desktop.theme)
    assert len(boxes) == 2
    for index, (side, coach) in enumerate((("OFFENSE", pair.offense), ("DEFENSE", pair.defense))):
        assert any(value == f"{side} / {coach.name}" and staff.contains(rect)
                   for value, rect, _ in captured)
        assert any(value == f"PERK / {football_coach_module.coach_perk_text(coach)}"
                   and boxes[index].inflate(-12, -8).contains(rect)
                   and color == football_depth_module._PERK_TEXT for value, rect, color in captured)
        assert staff.inflate(-20, -8).contains(boxes[index])
        for position, modifier in coach.position_modifiers.items():
            color = (football_depth_module._POSITIVE if modifier > 0 else
                     football_depth_module._NEGATIVE if modifier < 0 else football_depth_module._NEUTRAL)
            assert any(value == f"{_POSITION_LABELS[position]} {modifier:+.0%}"
                       and actual == color and staff.contains(rect) for value, rect, actual in captured)
    assert next(rect for value, rect, _ in captured if value == f"OFFENSE / {pair.offense.name}").left == next(
        rect for value, rect, _ in captured if value == f"DEFENSE / {pair.defense.name}").left


@pytest.mark.parametrize("width", (240, 300))
def test_depth_chart_coach_perk_boxes_fit_every_staff(tmp_path: Path, monkeypatch, width: int) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    assert state.shop is not None
    boxes = []
    texts = []
    original_box = football_depth_module._rounded_box
    original_text = football_depth_module.draw_complete_wrapped_text

    def capture_box(surface, rect, fill, edge, radius=6):
        if fill == football_depth_module._PERK_BOX:
            boxes.append(rect.copy())
        return original_box(surface, rect, fill, edge, radius)

    def capture_text(surface, text, rect, font, color, *, line_gap=2):
        if text.startswith("PERK / "):
            texts.append((text, rect.copy()))
        return original_text(surface, text, rect, font, color, line_gap=line_gap)

    monkeypatch.setattr(football_depth_module, "_rounded_box", capture_box)
    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture_text)
    for offense in OFFENSIVE_COACHES:
        for defense in DEFENSIVE_COACHES:
            assignment = FootballCoachAssignment(offense.coach_id, defense.coach_id)
            roster = replace(state.shop.roster, coach_assignment=assignment)
            candidate = replace(state, shop=replace(state.shop, roster=roster))
            staff = pygame.Rect(20, 71, width, 579)
            boxes.clear()
            texts.clear()
            height = football_depth_module._draw_staff(_surface(), staff, candidate, desktop.theme)
            actual = staff.copy()
            actual.height = height
            assert len(boxes) == len(texts) == 2
            assert not boxes[0].colliderect(boxes[1])
            for box, (text, rect), coach in zip(boxes, texts, (offense, defense)):
                assert text == f"PERK / {football_coach_module.coach_perk_text(coach)}"
                assert actual.inflate(-20, -8).contains(box)
                assert box.inflate(-12, -8).contains(rect)
            if width == 300:
                assert height == staff.height


def test_all_catalog_players_fit_standard_depth_chart(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    state = controller.state
    screen = desktop.run_screen
    view = football_review_module.FootballReviewView(
        screen.theme, screen._small_font, screen._label_font, screen.shop_review,
        lambda: None, lambda _copy_id: None,
    )
    screen.shop_review.open_depth_chart()
    area = pygame.Rect(20, 15, 1240, 690)
    for position in PLAYER_DRAFT_ORDER:
        for player_type in PLAYER_TYPES_BY_POSITION[position]:
            player = player_from_type(player_type)
            roster = replace(state.shop.roster, players={**state.shop.roster.players, position: player})
            candidate = replace(state, shop=replace(state.shop, roster=roster),
                                drafted_players={**state.drafted_players, position: player})
            view.draw_depth_chart(_surface(), area, candidate)
            assert screen.shop_review.depth_max_scroll == 0, player_type.name

    long_names = {
        "Silent-Count Caller", "Slot Outlet", "Release Specialist", "Screen Setter",
        "Rush Contain", "Robber Backer", "Underneath Bracket", "Robber Safety",
    }
    longest = {
        position: player_from_type(next(player_type for player_type in PLAYER_TYPES_BY_POSITION[position]
                                        if player_type.name in long_names))
        for position in PLAYER_DRAFT_ORDER
    }
    candidate = replace(state, shop=replace(state.shop, roster=replace(state.shop.roster, players=longest)),
                        drafted_players=longest)
    view.draw_depth_chart(_surface(), area, candidate)
    assert screen.shop_review.depth_max_scroll == 0


@pytest.mark.parametrize(("primary", "secondary"), [
    ("navy", "blue"), ("silver", "gold"), ("green", "teal"),
])
def test_depth_chart_color_contrast_and_navigation(tmp_path: Path, primary: str, secondary: str) -> None:
    desktop = _new_desktop(tmp_path, primary=primary, secondary=secondary)
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "DEPTH CHART", keyboard=True)
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state
    screen = desktop.run_screen
    desktop.router.draw(_surface())
    assert screen.shop_review.depth_max_scroll == 0
    assert screen.buttons[screen.focus_index].focused
    assert all(isinstance(button, football_depth_module.DepthChartButton) for button in screen.buttons)

    def contrast(first, second):
        light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    assert contrast(football_depth_module._PERK_TEXT, football_depth_module._PERK_BOX) >= 4.5
    assert contrast(football_depth_module._TEXT, football_depth_module._CARD) >= 4.5
    assert contrast(football_depth_module._MUTED, football_depth_module._CARD) >= 4.5
    assert contrast(football_depth_module._TEXT, pygame.Color("#173652")) >= 4.5
    _activate(desktop, "UPGRADES / PERK DETAILS")
    assert screen.shop_review.depth_details
    _activate(desktop, "BACK TO DEPTH CHART", keyboard=True)
    assert not screen.shop_review.depth_details
    _activate(desktop, "END RUN", keyboard=True)
    assert screen.confirm_exit
    _activate(desktop, "KEEP PLAYING")
    assert not screen.confirm_exit and controller.state == before
    _activate(desktop, "BACK TO SHOP", keyboard=True)
    assert screen.shop_review.mode is None and controller.state == before


def test_depth_chart_scroll_exposes_complete_details_at_multiple_sizes(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "BUY")
    _activate(desktop, "DEPTH CHART")
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    original = football_depth_module.draw_complete_wrapped_text
    visible = set()
    expected = set()

    def capture(surface, text, rect, font, color, *, line_gap=2):
        for index, line in enumerate(wrap_text_lines(text, font, rect.width)):
            key = (text, index)
            expected.add(key)
            line_rect = pygame.Rect(rect.left, rect.top + index * (font.get_height() + line_gap),
                                    font.size(line)[0], font.get_height())
            if surface.get_clip().contains(line_rect):
                visible.add(key)
        return original(surface, text, rect, font, color, line_gap=line_gap)

    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture)
    for size in (LOGICAL_SIZE, (960, 600), (700, 500)):
        visible.clear()
        expected.clear()
        surface = pygame.Surface(size)
        desktop.router.draw(surface)
        interaction = desktop.run_screen.shop_review
        interaction.depth_scroll = 0
        while True:
            desktop.router.draw(surface)
            if interaction.depth_scroll == interaction.depth_max_scroll:
                break
            desktop.router.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1}))
        assert expected <= visible
        visible.clear()
        expected.clear()
        interaction.toggle_depth_details()
        while True:
            desktop.router.draw(surface)
            if interaction.depth_scroll == interaction.depth_max_scroll:
                break
            desktop.router.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1}))
        assert expected <= visible
        assert any(controller.state.shop.purchased_upgrades[0].name in text for text, _ in visible)
        interaction.toggle_depth_details()
    interaction.depth_scroll = interaction.depth_max_scroll
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    assert interaction.depth_scroll == interaction.depth_max_scroll == 0


def test_coach_upgrade_text_and_bye_week_marker_are_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    card = next(
        card
        for card in COACH_UPGRADE_CATALOG
        if card.card_id == "two_minute_drill"
    )
    shop = FootballShop(
        controller.state.shop.roster,
        51,
        game_number=4,
        catalogs={FootballShopSection.COACH_UPGRADES: (card,)},
    )
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    screen = desktop.run_screen
    area = pygame.Rect(20, 80, 1200, 580)
    wrapped: list[str] = []
    shop_labels: list[str] = []
    original_shop_wrapped = football_shop_module.draw_wrapped_text
    original_shop_text = football_shop_module.draw_text

    def capture_shop_wrapped(surface, text, rect, font, color, *, line_gap=6):
        wrapped.append(text)
        original_shop_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    def capture_shop_text(surface, text, position, font, color):
        shop_labels.append(text)
        original_shop_text(surface, text, position, font, color)

    monkeypatch.setattr(
        football_shop_module, "draw_wrapped_text", capture_shop_wrapped
    )
    monkeypatch.setattr(football_shop_module, "draw_text", capture_shop_text)
    view = screen._shop_view()
    buttons = view.draw(
        _surface(), area, shop.state, "Bye Week skipped scheduled game 3."
    )
    assert "SELECT DETAILS" in shop_labels
    assert "FOCUS DETAILS" not in shop_labels
    details_index = next(
        index for index, button in enumerate(buttons) if button.label == "DETAILS"
    )
    screen._set_buttons(buttons)
    screen.focus_index = details_index
    screen.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
    )
    view.draw(
        _surface(),
        area,
        shop.state,
        "Bye Week skipped scheduled game 3.",
    )
    assert view._coach_detail_sections == coach_upgrade_detail_sections(card)
    assert "Bye Week skipped scheduled game 3." in " ".join(shop_labels)

    shop.buy_card(FootballShopSection.COACH_UPGRADES, card.card_id)
    state = replace(
        controller.state,
        shop=replace(
            shop.state,
            owned_coach_upgrades=COACH_UPGRADE_CATALOG,
        ),
        game_number=4,
    )
    review = football_review_module.FootballReviewView(
        screen.theme,
        screen._small_font,
        screen._label_font,
        screen.shop_review,
        lambda: None,
        lambda _copy_id: None,
    )
    review.interaction.toggle_depth_details()
    review.draw_depth_chart(_surface(), area, state)
    assert review.interaction.depth_max_scroll > 0
    for owned_card in COACH_UPGRADE_CATALOG:
        sections = coach_upgrade_detail_sections(owned_card)
        details = "\n".join((f"COACH  /  {sections[0]}", *sections[1:]))
        lines = wrap_text_lines(details, screen._small_font, area.width - 32)
        assert all(
            screen._small_font.size(line)[0] <= area.width - 32
            for line in lines
        )
    review.interaction.depth_scroll = review.interaction.depth_max_scroll
    review.draw_depth_chart(_surface(), area, state)
    assert review.interaction.depth_scroll == review.interaction.depth_max_scroll

    marker = replace(
        state,
        phase=FootballRunPhase.PLAYOFFS,
        game_number=10,
        games_played=9,
        skipped_games=(10,),
        transition_message=(
            "Bye Week skipped scheduled game 10 without a match result. "
            "You reached the playoffs marker."
        ),
        match=None,
    )
    displayed: list[str] = []
    original_result_text = football_result_module.draw_text

    def capture_result_text(surface, text, position, font, color):
        displayed.append(text)
        original_result_text(surface, text, position, font, color)

    monkeypatch.setattr(
        football_result_module, "draw_text", capture_result_text
    )
    buttons = screen._result_view.draw(_surface(), area, marker, screen.theme)
    assert any("SCHEDULED GAME 10 SKIPPED" in text for text in displayed)
    assert any("9 actual regular-season games played." in text for text in displayed)
    assert "RETURN TO MAIN MENU" == buttons[0].label


@pytest.mark.parametrize(
    "window_size",
    ((1280, 720), (960, 540), (1000, 800)),
)
def test_all_coach_upgrade_details_are_keyboard_and_mouse_accessible(
    tmp_path: Path,
    window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    assert controller is not None and controller.state.shop is not None
    desktop.window_size = window_size
    surface = _surface()
    content = Layout.from_surface(surface).content

    for card in COACH_UPGRADE_CATALOG:
        shop = FootballShop(
            controller.state.shop.roster,
            51,
            game_number=4,
            catalogs={FootballShopSection.COACH_UPGRADES: (card,)},
        )
        shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
        view = screen._shop_view()
        buttons = view.draw(surface, content, shop.state)
        details_index = next(
            index for index, button in enumerate(buttons)
            if button.label == "DETAILS"
        )

        screen.focus_index = 0
        screen._set_buttons(buttons)
        for _ in range(len(buttons)):
            if screen.focus_index == details_index:
                break
            screen.handle_event(
                pygame.event.Event(
                    pygame.KEYDOWN,
                    {"key": pygame.K_TAB, "mod": 0, "unicode": ""},
                )
            )
        assert screen.focus_index == details_index
        screen.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
        )
        view.draw(surface, content, shop.state)
        assert view._coach_detail_sections == coach_upgrade_detail_sections(card)
        detail_rect = view._coach_detail_rect
        assert detail_rect is not None
        assert content.contains(detail_rect)
        inner_width = min(content.width - 24, 2 * ((content.width - 20) // 3) + 10) - 24
        title_lines = wrap_text_lines(
            view._coach_detail_sections[0],
            screen._label_font,
            inner_width,
        )
        body_lines = tuple(
            line
            for section in view._coach_detail_sections[1:]
            for line in wrap_text_lines(section, screen._small_font, inner_width)
        )
        assert all(screen._label_font.size(line)[0] <= inner_width for line in title_lines)
        assert all(screen._small_font.size(line)[0] <= inner_width for line in body_lines)
        expected_height = (
            len(title_lines) * (screen._label_font.get_height() + 2)
            + len(body_lines) * (screen._small_font.get_height() + 2)
            + 28
        )
        assert detail_rect.height >= expected_height
        view.close_coach_details()

    mouse_card = next(
        card for card in COACH_UPGRADE_CATALOG
        if card.card_id == "pattern_match"
    )
    shop = FootballShop(
        controller.state.shop.roster,
        51,
        game_number=4,
        catalogs={FootballShopSection.COACH_UPGRADES: (mouse_card,)},
    )
    shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
    view = screen._shop_view()
    buttons = view.draw(surface, content, shop.state)
    details_index = next(
        index for index, button in enumerate(buttons)
        if button.label == "DETAILS"
    )
    screen._set_buttons(buttons)
    logical_x, logical_y = buttons[details_index].rect.center
    scale = min(
        window_size[0] / LOGICAL_SIZE[0],
        window_size[1] / LOGICAL_SIZE[1],
    )
    rendered_width = round(LOGICAL_SIZE[0] * scale)
    rendered_height = round(LOGICAL_SIZE[1] * scale)
    offset_x = (window_size[0] - rendered_width) // 2
    offset_y = (window_size[1] - rendered_height) // 2
    physical_position = (
        round(logical_x * scale + offset_x),
        round(logical_y * scale + offset_y),
    )
    mouse_event = desktop._logical_event(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {"pos": physical_position, "rel": (0, 0), "buttons": (0, 0, 0)},
        )
    )
    screen.handle_event(mouse_event)
    assert screen.hover_index == details_index
    screen.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"pos": (logical_x, logical_y), "button": 1}
        )
    )
    screen.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP, {"pos": (logical_x, logical_y), "button": 1}
        )
    )
    view.draw(surface, content, shop.state)
    assert view._coach_detail_sections == coach_upgrade_detail_sections(mouse_card)


@pytest.mark.parametrize(
    "window_size",
    ((1280, 720), (1000, 800)),
)
@pytest.mark.parametrize("slot_number", (1, 2))
@pytest.mark.parametrize("input_method", ("mouse", "keyboard"))
@pytest.mark.parametrize("redraw_between_events", (False, True))
def test_coach_upgrade_purchase_through_run_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window_size: tuple[int, int],
    slot_number: int,
    input_method: str,
    redraw_between_events: bool,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    assert controller is not None
    cards = tuple(
        card for card in COACH_UPGRADE_CATALOG
        if card.card_id in ("punt_return_lane", "kickoff_return_lane")
    )
    controller._shop_catalogs = {FootballShopSection.COACH_UPGRADES: cards}
    _draft_to_shop(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    for _ in range(3):
        _activate(desktop, "FINISH SHOP / START MATCH")
        _play_first_match_card(desktop)
        _activate(desktop, "OPEN NEXT GAME SHOP")

    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 2)
    screen.state = controller.state
    shop = controller.state.shop
    assert shop is not None
    card = shop.section(FootballShopSection.COACH_UPGRADES).slots[slot_number - 1].card
    assert card is not None and card.coach_upgrade_effect is not None
    assert shop.remaining_ap == card.cost == 2
    desktop.window_size = window_size
    surface = _surface()
    desktop.router.draw(surface)
    details_buttons = [button for button in screen.buttons if button.label == "DETAILS"]
    details_index = screen.buttons.index(details_buttons[slot_number - 1])
    buy_index = details_index + 1
    buy = screen.buttons[buy_index]
    assert buy.label == "BUY" and buy.enabled

    scale = min(window_size[0] / LOGICAL_SIZE[0], window_size[1] / LOGICAL_SIZE[1])
    offset_x = (window_size[0] - round(LOGICAL_SIZE[0] * scale)) // 2
    offset_y = (window_size[1] - round(LOGICAL_SIZE[1] * scale)) // 2

    def send_mouse(event_type: int, position: tuple[int, int]) -> None:
        physical = (
            round(position[0] * scale + offset_x),
            round(position[1] * scale + offset_y),
        )
        event = pygame.event.Event(event_type, {"pos": physical, "button": 1})
        desktop.router.handle_event(desktop._logical_event(event))

    def redraw() -> None:
        if redraw_between_events:
            desktop.router.draw(surface)

    def key(key_code: int) -> None:
        desktop.router.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": key_code, "mod": 0})
        )
        redraw()

    if input_method == "keyboard":
        for _ in range(len(screen.buttons)):
            if screen.focus_index == details_index:
                break
            key(pygame.K_TAB)
        assert screen.focus_index == details_index
        key(pygame.K_RETURN)
    else:
        for event_type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            send_mouse(event_type, details_buttons[slot_number - 1].rect.center)
            redraw()
    assert screen._shop_view().coach_details_open
    desktop.router.draw(surface)
    assert screen._shop_view()._coach_detail_sections == coach_upgrade_detail_sections(card)
    assert screen.buttons[screen.focus_index].label == "CLOSE DETAILS"
    if input_method == "keyboard":
        key(pygame.K_RETURN)
    else:
        close = next(button for button in screen.buttons if button.label == "CLOSE DETAILS")
        for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            send_mouse(event_type, close.rect.center)
            redraw()
    desktop.router.draw(surface)
    assert not screen._shop_view().coach_details_open

    if input_method == "keyboard":
        for _ in range(len(screen.buttons)):
            if screen.focus_index == buy_index:
                break
            key(pygame.K_TAB)
        assert screen.focus_index == buy_index
        assert not screen._shop_view().coach_details_open
        key(pygame.K_RETURN)
    else:
        for event_type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            send_mouse(event_type, buy.rect.center)
            redraw()

    shop = controller.state.shop
    assert shop is not None
    assert shop.remaining_ap == 0
    assert shop.owned_coach_upgrades == (card,)
    assert shop.section(FootballShopSection.COACH_UPGRADES).slots[slot_number - 1].purchased
    if not redraw_between_events:
        if input_method == "keyboard":
            key(pygame.K_RETURN)
        else:
            send_mouse(pygame.MOUSEBUTTONDOWN, buy.rect.center)
            send_mouse(pygame.MOUSEBUTTONUP, buy.rect.center)
        assert controller.state.shop is not None
        assert controller.state.shop.remaining_ap == 0
        assert controller.state.shop.owned_coach_upgrades == (card,)
    desktop.router.draw(surface)
    remaining_details = [
        button for button in screen.buttons if button.label == "DETAILS"
    ][2 - slot_number]
    remaining_index = screen.buttons.index(remaining_details)
    unavailable_buy = screen.buttons[remaining_index + 1]
    assert unavailable_buy.label == "NEED 2 AP"
    assert not unavailable_buy.enabled
    for _ in range(len(screen.buttons)):
        if screen.focus_index == remaining_index:
            break
        desktop.router.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB, "mod": 0})
        )
    assert screen.focus_index == remaining_index
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})
    )
    assert screen._shop_view().coach_details_open
    desktop.router.draw(surface)
    other_card = shop.section(FootballShopSection.COACH_UPGRADES).slots[2 - slot_number].card
    assert other_card is not None
    assert screen._shop_view()._coach_detail_sections == coach_upgrade_detail_sections(other_card)
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})
    )
    desktop.router.draw(surface)
    assert not screen._shop_view().coach_details_open
    for event_type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        send_mouse(event_type, unavailable_buy.rect.center)
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_ap == 0
    assert controller.state.shop.owned_coach_upgrades == (card,)
    _activate(desktop, "FINISH SHOP / START MATCH")
    assert controller.state.match is not None
    assert controller.state.match.team_a_coach_upgrades == (card.coach_upgrade_effect,)


@pytest.mark.parametrize(
    "window_size",
    ((1280, 720), (1000, 800)),
)
def test_coach_details_do_not_activate_obscured_shop_buttons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    assert controller is not None
    controller._shop_catalogs = {
        FootballShopSection.COACH_UPGRADES: (
            next(
                card
                for card in COACH_UPGRADE_CATALOG
                if card.card_id == "pattern_match"
            ),
        )
    }
    _draft_to_shop(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)

    for game_number in range(1, 4):
        _activate(desktop, "FINISH SHOP / START MATCH")
        _play_first_match_card(desktop)
        if game_number < 4:
            _activate(desktop, "OPEN NEXT GAME SHOP")

    assert controller.state.game_number == 4
    controller.unlock_shop_slot(FootballShopSection.COACH_UPGRADES, 1)
    screen.state = controller.state
    assert controller.state.shop is not None
    assert controller.state.shop.section(
        FootballShopSection.COACH_UPGRADES
    ).slots[0].unlocked
    assert controller.state.shop.section(
        FootballShopSection.COACH_UPGRADES
    ).slots[0].card is not None
    desktop.window_size = window_size
    surface = _surface()

    desktop.router.draw(surface)
    details_index = next(
        index for index, button in enumerate(screen.buttons)
        if button.label == "DETAILS"
    )
    player_buy = next(
        button for button in screen.buttons
        if button.label == "BUY"
    )
    ap_before = controller.state.shop.remaining_ap
    logical_buy_position = player_buy.rect.center

    screen.focus_index = 0
    for _ in range(len(screen.buttons)):
        if screen.focus_index == details_index:
            break
        screen.handle_event(
            pygame.event.Event(
                pygame.KEYDOWN,
                {"key": pygame.K_TAB, "mod": 0, "unicode": ""},
            )
        )
    assert screen.focus_index == details_index
    screen.handle_event(
        pygame.event.Event(
            pygame.KEYDOWN,
            {"key": pygame.K_RETURN, "mod": 0, "unicode": ""},
        )
    )
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        screen.handle_event(
            pygame.event.Event(event_type, {"pos": logical_buy_position, "button": 1})
        )
    assert controller.state.shop.remaining_ap == ap_before
    assert controller.state.shop.purchased_cards == ()
    desktop.router.draw(surface)
    assert screen._shop_view().coach_details_open
    detail_rect = screen._shop_view().coach_details_rect
    assert detail_rect is not None
    assert detail_rect.collidepoint(logical_buy_position)
    assert {button.label for button in screen.buttons} == {
        "CLOSE DETAILS",
        "END RUN",
    }

    def physical_position(logical_position: tuple[int, int]) -> tuple[int, int]:
        scale = min(
            window_size[0] / LOGICAL_SIZE[0],
            window_size[1] / LOGICAL_SIZE[1],
        )
        offset_x = (window_size[0] - round(LOGICAL_SIZE[0] * scale)) // 2
        offset_y = (window_size[1] - round(LOGICAL_SIZE[1] * scale)) // 2
        return (
            round(logical_position[0] * scale + offset_x),
            round(logical_position[1] * scale + offset_y),
        )

    def send_mouse(event_type: int, position: tuple[int, int]) -> None:
        event = pygame.event.Event(
            event_type,
            {"pos": physical_position(position), "button": 1},
        )
        desktop.router.handle_event(desktop._logical_event(event))

    send_mouse(pygame.MOUSEBUTTONDOWN, logical_buy_position)
    send_mouse(pygame.MOUSEBUTTONUP, logical_buy_position)
    assert controller.state.shop.remaining_ap == ap_before
    assert controller.state.shop.purchased_cards == ()

    screen.handle_event(
        pygame.event.Event(
            pygame.KEYDOWN,
            {"key": pygame.K_ESCAPE, "mod": 0, "unicode": ""},
        )
    )
    screen.handle_event(
        pygame.event.Event(
            pygame.KEYDOWN,
            {"key": pygame.K_RETURN, "mod": 0, "unicode": ""},
        )
    )
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        screen.handle_event(
            pygame.event.Event(event_type, {"pos": logical_buy_position, "button": 1})
        )
    assert controller.state.shop.remaining_ap == ap_before
    assert controller.state.shop.purchased_cards == ()
    desktop.router.draw(surface)
    details_button = next(
        button for button in screen.buttons if button.label == "DETAILS"
    )
    details_position = details_button.rect.center
    send_mouse(pygame.MOUSEMOTION, details_position)
    send_mouse(pygame.MOUSEBUTTONDOWN, details_position)
    send_mouse(pygame.MOUSEBUTTONUP, details_position)
    desktop.router.draw(surface)
    send_mouse(pygame.MOUSEBUTTONDOWN, logical_buy_position)
    send_mouse(pygame.MOUSEBUTTONUP, logical_buy_position)
    assert controller.state.shop.remaining_ap == ap_before
    assert controller.state.shop.purchased_cards == ()

    close_button = next(
        button for button in screen.buttons if button.label == "CLOSE DETAILS"
    )
    send_mouse(pygame.MOUSEBUTTONDOWN, close_button.rect.center)
    assert screen.pressed_index == screen.buttons.index(close_button)
    send_mouse(pygame.MOUSEBUTTONUP, close_button.rect.center)
    assert not screen._shop_view().coach_details_open
    desktop.router.draw(surface)
    assert not screen._shop_view().coach_details_open

    details_button = next(
        button for button in screen.buttons if button.label == "DETAILS"
    )
    send_mouse(pygame.MOUSEMOTION, details_button.rect.center)
    send_mouse(pygame.MOUSEBUTTONDOWN, details_button.rect.center)
    send_mouse(pygame.MOUSEBUTTONUP, details_button.rect.center)
    desktop.router.draw(surface)
    assert screen._shop_view().coach_details_open
    screen.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB, "mod": 0})
    )
    assert screen.buttons[screen.focus_index].label == "END RUN"
    screen.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})
    )
    desktop.router.draw(surface)
    assert screen.confirm_exit
    _activate(desktop, "KEEP PLAYING")
    assert not screen.confirm_exit
    desktop.router.draw(surface)
    details_button = next(
        button for button in screen.buttons if button.label == "DETAILS"
    )
    send_mouse(pygame.MOUSEBUTTONDOWN, details_button.rect.center)
    send_mouse(pygame.MOUSEBUTTONUP, details_button.rect.center)
    desktop.router.draw(surface)
    assert screen._shop_view().coach_details_open
    outside_details = (detail_rect.left - 2, detail_rect.centery)
    assert not detail_rect.collidepoint(outside_details)
    send_mouse(pygame.MOUSEMOTION, outside_details)
    desktop.router.draw(surface)
    assert any(button.label == "BUY" for button in screen.buttons)
    player_buy = next(button for button in screen.buttons if button.label == "BUY")
    send_mouse(pygame.MOUSEBUTTONDOWN, player_buy.rect.center)
    send_mouse(pygame.MOUSEBUTTONUP, player_buy.rect.center)
    assert controller.state.shop.remaining_ap < ap_before


def test_match_hand_clock_preview_matches_resolved_play_and_incomplete_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "FINISH SHOP / START MATCH")
    controller = desktop.football_controller
    screen = desktop.run_screen
    assert controller is not None
    base_state = controller.state
    assert base_state.match is not None
    match = base_state.match
    assert match.team_a_offense_deck is not None

    drawn_text: list[str] = []
    original_draw_text = football_match_decision_module.draw_text

    def capture_text(surface, text, position, font, color):
        drawn_text.append(text)
        original_draw_text(surface, text, position, font, color)

    monkeypatch.setattr(
        football_match_decision_module, "draw_text", capture_text
    )
    view = football_match_decision_module.FootballMatchDecisionView(
        screen._small_font,
        screen._label_font,
        screen.match_interaction,
        0,
        None,
        None,
        lambda _copy_id: None,
        lambda _action: None,
        lambda _action, _copy_id: None,
        lambda _offensive: None,
    )
    surface = _surface()
    hand_rect = pygame.Rect(30, 40, LOGICAL_SIZE[0] - 60, 320)
    upgrade_sets = (
        (),
        (_coach_card_effect("tempo_install"),),
        (_coach_card_effect("huddle_up"),),
        (
            _coach_card_effect("tempo_install"),
            _coach_card_effect("huddle_up"),
        ),
    )
    for upgrades in upgrade_sets:
        play = FootballCardCopy("preview:rb_run", OffensivePlayAction.RB_RUN.value)
        other_cards = (
            FootballCardCopy(
                "preview:short_pass",
                OffensivePlayAction.SHORT_PASS.value,
            ),
            FootballCardCopy(
                "preview:medium_pass",
                OffensivePlayAction.MEDIUM_PASS.value,
            ),
        )
        hand = (play, *other_cards)
        match_with_upgrades = replace(
            match,
            possession=FootballTeamSide.TEAM_A,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=replace(
                match.team_a_offense_deck,
                owned=hand,
                draw_pile=(),
                hand=hand,
                discard_pile=(),
            ),
            team_a_coach_upgrades=upgrades,
        )
        state = replace(
            base_state,
            match=match_with_upgrades,
            human_decision=FootballHumanDecision.OFFENSIVE_PLAY,
        )
        simulator = FootballMatchSimulator(match_with_upgrades)
        simulator.rng.random = lambda: 0.99
        simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
        result = simulator.state.match_events[-1].play_result
        assert result is not None and not result.incomplete

        drawn_text.clear()
        view.draw(surface, hand_rect, state)
        preview = next(text for text in drawn_text if text.startswith("LIVE ~"))
        assert f"LIVE NORMAL CLOCK {result.clock_seconds_used}s" in preview
        card_rect = screen.match_interaction.card_rects[play.copy_id]
        assert screen._small_font.size(preview)[0] <= card_rect.width - 12

    tempo = _coach_card_effect("tempo_install")
    deep_pass = FootballCardCopy(
        "preview:deep_pass",
        OffensivePlayAction.DEEP_PASS.value,
    )
    incomplete_hand = (
        deep_pass,
        FootballCardCopy(
            "preview:deep_short",
            OffensivePlayAction.SHORT_PASS.value,
        ),
        FootballCardCopy(
            "preview:deep_medium",
            OffensivePlayAction.MEDIUM_PASS.value,
        ),
    )
    incomplete_match = replace(
        match,
        possession=FootballTeamSide.TEAM_A,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        team_a_offense_deck=replace(
            match.team_a_offense_deck,
            owned=incomplete_hand,
            draw_pile=(),
            hand=incomplete_hand,
            discard_pile=(),
        ),
        team_a_coach_upgrades=(tempo,),
    )
    incomplete_state = replace(
        base_state,
        match=incomplete_match,
        human_decision=FootballHumanDecision.OFFENSIVE_PLAY,
    )
    simulator = FootballMatchSimulator(incomplete_match)
    rolls = iter((0.99, 0.0))
    simulator.rng.random = lambda: next(rolls)
    simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    incomplete_result = simulator.state.match_events[-1].play_result
    assert incomplete_result is not None and incomplete_result.incomplete
    assert incomplete_result.clock_seconds_used == 5

    drawn_text.clear()
    view.draw(surface, hand_rect, incomplete_state)
    preview = next(text for text in drawn_text if text.startswith("LIVE ~"))
    live_normal_seconds = football_match_decision_module.adjusted_offensive_play_clock_seconds(
        OFFENSIVE_PLAY_CATALOG[OffensivePlayAction.DEEP_PASS.value].clock_seconds,
        (tempo,),
    )
    assert f"LIVE NORMAL CLOCK {live_normal_seconds}s" in preview
    incomplete_card_rect = screen.match_interaction.card_rects[deep_pass.copy_id]
    assert screen._small_font.size(preview)[0] <= incomplete_card_rect.width - 12
    assert any(
        "INCOMPLETE PASSES USE SEPARATE 5s RULE" in text
        and "CONVERSIONS & SPECIAL TEAMS UNCHANGED" in text
        for text in drawn_text
    )


def _coach_card_effect(card_id: str):
    card = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == card_id)
    assert card.coach_upgrade_effect is not None
    return card.coach_upgrade_effect


def test_named_variants_show_context_and_standard_details_in_shop_and_playbook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    play = OFFENSIVE_PLAY_CATALOG["slot_slant"]
    scheme = DEFENSIVE_SCHEME_CATALOG["quarters_coverage"]
    cards = (
        FootballShopCard(
            card_id=f"play:{play.card_id}",
            name=play.name,
            description=play.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.COMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            football_card=play,
        ),
        FootballShopCard(
            card_id=f"scheme:{scheme.card_id}",
            name=scheme.name,
            description=scheme.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.COMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            football_card=scheme,
        ),
    )
    controller = FootballGameController(
        "Test Owls",
        difficulty=FootballAIDifficulty.STANDARD,
        builder_seed=17,
        shop_seed=29,
        ai_seed=4,
        match_seed=1,
        shop_catalogs={FootballShopSection.PLAYS_SCHEMES: cards},
    )
    desktop.football_controller = controller
    desktop.run_screen.begin(controller)
    _draft_to_shop(desktop)

    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_review_module, "draw_text", capture_text)
    monkeypatch.setattr(football_shop_module, "draw_text", capture_text)
    desktop.router.draw(_surface())
    shop_copy = " ".join(displayed)
    assert play.name in shop_copy and scheme.name in shop_copy
    assert "COMMON" in shop_copy
    assert "SHORT PASS" in shop_copy
    assert "NEUTRAL ~7.3 / BASE 22s" in shop_copy
    assert "COUNTERS: DEEP PASS" in shop_copy

    desktop.router.draw(_surface())
    buy_buttons = [
        button for button in desktop.run_screen.buttons if button.label == "BUY"
    ]
    assert len(buy_buttons) == 5
    for button in buy_buttons[3:]:
        button.action()
    displayed.clear()
    _activate(desktop, "PLAYBOOK")
    displayed.clear()
    desktop.router.draw(_surface())
    for _ in range(desktop.run_screen.shop_review.playbook_max_scroll):
        desktop.run_screen.handle_event(
            pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
        )
        desktop.router.draw(_surface())
    playbook_copy = " ".join(displayed)
    assert "Slot Slant" in playbook_copy
    assert "SHORT PASS" in playbook_copy
    assert "NEUTRAL ~7.3 YDS / BASE 22s" in playbook_copy
    assert "Quarters Coverage" in playbook_copy
    assert "COUNTERS DEEP PASS" in playbook_copy


@pytest.mark.parametrize("height", (49, 50, 60, 74, 75, 92))
def test_shop_slot_rendering_handles_card_kinds_and_layout_boundaries(
    tmp_path: Path,
    monkeypatch,
    height: int,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    shop = controller.state.shop
    assert shop is not None

    play = OFFENSIVE_PLAY_CATALOG["slot_slant"]
    scheme = DEFENSIVE_SCHEME_CATALOG["quarters_coverage"]
    play_card = FootballShopCard(
        card_id=f"play:{play.card_id}",
        name=play.name,
        description=play.description,
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        football_card=play,
    )
    scheme_card = FootballShopCard(
        card_id=f"scheme:{scheme.card_id}",
        name=scheme.name,
        description=scheme.description,
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        football_card=scheme,
    )
    other_card = FootballShopCard(
        card_id="test-player-card",
        name="Test Player Card",
        description="A non-football shop card.",
        section=FootballShopSection.PLAYER_UPGRADES,
        rarity=FootballShopRarity.COMMON,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
    )
    cases = (
        ("affordable play", play_card, False, 2, "BUY", "NEUTRAL"),
        ("purchased play", play_card, True, 2, "PURCHASED", "PURCHASED"),
        ("unaffordable play", play_card, False, 1, "NEED 1 AP", "NEED"),
        ("defensive scheme", scheme_card, False, 2, "BUY", "COUNTERS"),
        ("non-football card", other_card, False, 2, "BUY", "non-football"),
    )
    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture_text)
    for label, card, purchased, remaining_ap, expected_button, expected_text in cases:
        displayed.clear()
        slot = FootballShopSlotState(
            section=card.section,
            slot_number=1,
            unlocked=True,
            card=card,
            purchased=purchased,
            unlock_cost=None,
            can_unlock=False,
            disabled_reason=None,
        )
        buttons: list[Button] = []
        desktop.run_screen._shop_view().draw_slot(
            _surface(),
            pygame.Rect(10, 10, 700, height),
            slot,
            buttons,
            replace(shop, remaining_ap=remaining_ap),
        )

        assert buttons[0].label == expected_button, (label, height)
        assert expected_text.upper() in " ".join(displayed).upper(), (
            label,
            height,
            displayed,
        )


def test_supported_desktop_layout_renders_the_actual_shop(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)

    desktop.router.draw(_surface())

    assert desktop.run_screen._current_state().shop is not None
    assert any(button.label == "BUY" for button in desktop.run_screen.buttons)


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

    text = FootballMatchStatusView(desktop.run_screen._small_font).format_event(event, "Home", "Away")

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

    text = FootballMatchStatusView(desktop.run_screen._small_font).format_event(event, "Home", "Away")

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
    assert desktop.run_screen.shop_review.mode == "playbook"
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


def test_review_escape_cancels_pending_removal_without_spending_ap(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state.shop
    assert before is not None
    _activate(desktop, "SELECT CARD")
    assert controller.state.shop is not None
    assert controller.state.shop.pending_removal is not None
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
    )
    after = controller.state.shop
    assert after is not None
    assert after.pending_removal is None
    assert after.remaining_ap == before.remaining_ap
    assert after.offensive_deck == before.offensive_deck
    assert after.defensive_deck == before.defensive_deck
    assert desktop.run_screen.shop_review.mode is None
    assert not desktop.run_screen.confirm_exit


def test_match_interaction_animation_and_new_run_reset(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.match is not None
    first = controller.state.match
    interaction = desktop.run_screen.match_interaction
    interaction.visual_state = None
    start = interaction.field_positions(first, 100)
    assert start == (
        first.offense_field_position,
        min(100.0, first.offense_field_position + first.yards_to_go),
    )
    _play_first_match_card(desktop)
    updated = controller.state.match
    assert updated is not None
    assert len(updated.match_events) > len(first.match_events)
    assert interaction.field_positions(updated, 200) == start
    target = (
        updated.offense_field_position,
        min(100.0, updated.offense_field_position + updated.yards_to_go),
    )
    assert interaction.field_positions(updated, 380) == pytest.approx(
        tuple((origin + end) / 2 for origin, end in zip(start, target))
    )
    assert interaction.field_positions(updated, 560) == pytest.approx(target)
    assert not interaction.animation_active

    interaction.hand_scroll = 2
    interaction.dragging_card_id = "unfinished"
    desktop.run_screen.shop_review.open_playbook()
    desktop.run_screen.shop_review.playbook_scroll = 3
    desktop.run_screen.coach_inspection.hover_index = 1
    desktop.run_screen.player_inspection.hover_index = 1
    desktop.run_screen.player_inspection.card_rects.append(pygame.Rect(0, 0, 10, 10))
    desktop.navigate("main_menu")
    desktop.seed_factory = lambda: 17
    _start_run(desktop)
    reset = desktop.run_screen.match_interaction
    assert reset is not interaction
    assert reset.visual_state is None
    assert reset.hand_scroll == 0
    assert reset.dragging_card_id is None
    assert desktop.run_screen.shop_review.mode is None
    assert desktop.run_screen.shop_review.playbook_scroll == 0
    assert desktop.run_screen.coach_inspection.hover_index is None
    assert desktop.run_screen.player_inspection.hover_index is None
    assert desktop.run_screen.player_inspection.card_rects == []


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
    seen_two_point = False
    for _ in range(1200):
        state = controller.state
        if state.phase is not FootballRunPhase.MATCH:
            break
        assert state.match is not None
        desktop.router.draw(_surface())
        labels = {button.label: button for button in screen.buttons}
        event_count = len(state.match.match_events)
        expected_copy_id = None
        if state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            seen_offense = True
            deck = state.match.team_a_offense_deck
            assert deck is not None and deck.hand
            card = deck.hand[0]
            expected_copy_id = card.copy_id
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
            expected_copy_id = card.copy_id
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
            if not seen_two_point:
                deck = state.match.team_a_offense_deck
                assert deck is not None
                if deck.hand:
                    card = deck.hand[0]
                    expected_copy_id = card.copy_id
                    label = f"2PT: {OFFENSIVE_PLAY_CATALOG[card.card_id].name}"
                    assert label in labels
                    labels[label].action()
                else:
                    labels["2PT: BASIC RUN"].action()
                expected = FootballConversionAction.TWO_POINT
                seen_two_point = True
            else:
                expected = FootballConversionAction.EXTRA_POINT
                labels["EXTRA POINT"].action()
        else:
            pytest.fail(f"Unexpected match decision: {state.human_decision}")

        updated = controller.state
        assert updated.match is not None
        new_events = updated.match.match_events[event_count:]
        assert new_events
        assert new_events[0].action is expected
        if expected_copy_id is not None:
            assert new_events[0].card_copy_id == expected_copy_id
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
    assert seen_offense and seen_defense and seen_ai_play and seen_two_point
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
    draw_text = football_match_decision_module.draw_text

    def capture_text(*args, **kwargs):
        rendered_text.append(str(args[1]))
        return draw_text(*args, **kwargs)

    monkeypatch.setattr(football_match_decision_module, "draw_text", capture_text)
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
        _PLAY_LABELS[
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


@pytest.mark.parametrize("offensive", [True, False])
def test_match_decision_view_scrolls_and_selects_exact_card_copies(
    tmp_path: Path, offensive: bool,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    assert match is not None
    catalog = OFFENSIVE_PLAY_CATALOG if offensive else DEFENSIVE_SCHEME_CATALOG
    card_id = next(iter(catalog))
    copies = tuple(FootballCardCopy(f"copy-{index}", card_id) for index in range(7))
    deck = FootballDeckState(copies, hand=copies)
    match = replace(match, **{
        "team_a_offense_deck" if offensive else "team_a_defense_deck": deck,
    })
    state = replace(
        state, match=match,
        human_decision=(
            FootballHumanDecision.OFFENSIVE_PLAY if offensive
            else FootballHumanDecision.DEFENSIVE_SCHEME
        ),
    )
    screen = desktop.run_screen
    interaction = screen.match_interaction
    selected: list[str] = []
    view = football_match_decision_module.FootballMatchDecisionView(
        screen._small_font, screen._label_font, interaction, 0, None, None,
        selected.append, lambda action: None, lambda action, copy_id: None,
        lambda is_offensive: None,
    )
    surface = _surface()
    area = pygame.Rect(30, 400, 900, 150)
    buttons = view.draw(surface, area, state)
    assert list(interaction.card_rects) == [card.copy_id for card in copies[:3]]
    assert interaction.hand_max_scroll == 2
    assert len({button.label for button in buttons}) == 1
    buttons[1].action()
    assert selected == ["copy-1"]

    desktop.run_screen.match_interaction.handle_event(
        pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1})
    )
    buttons = view.draw(surface, area, state)
    assert list(interaction.card_rects) == [card.copy_id for card in copies[3:6]]
    buttons[0].action()
    assert selected == ["copy-1", "copy-3"]
    state = replace(state, human_decision=FootballHumanDecision.FOURTH_DOWN)
    view.draw(surface, area, state)
    assert interaction.hand_area is None
    assert interaction.play_area is None
    assert interaction.card_rects == {}


def test_match_decision_view_conversion_and_empty_hand_actions(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    assert match is not None and match.team_a_offense_deck is not None
    card_id = match.team_a_offense_deck.hand[0].card_id
    copies = (FootballCardCopy("first", card_id), FootballCardCopy("second", card_id))
    deck = FootballDeckState(copies, hand=copies)
    state = replace(
        state, match=replace(match, team_a_offense_deck=deck),
        human_decision=FootballHumanDecision.CONVERSION,
    )
    screen = desktop.run_screen
    conversions: list[tuple[FootballConversionAction, str | None]] = []
    fourth_down: list[FootballFourthDownAction] = []
    fallbacks: list[bool] = []
    view = football_match_decision_module.FootballMatchDecisionView(
        screen._small_font, screen._label_font, screen.match_interaction, 0, None, None,
        lambda copy_id: None, fourth_down.append,
        lambda action, copy_id: conversions.append((action, copy_id)),
        fallbacks.append,
    )
    surface = _surface()
    area = pygame.Rect(30, 400, 900, 150)
    buttons = view.draw(surface, area, state)
    assert [button.label for button in buttons] == [
        "EXTRA POINT", f"2PT: {OFFENSIVE_PLAY_CATALOG[card_id].name}",
        f"2PT: {OFFENSIVE_PLAY_CATALOG[card_id].name}",
    ]
    for button in buttons:
        button.action()
    assert conversions == [
        (FootballConversionAction.EXTRA_POINT, None),
        (FootballConversionAction.TWO_POINT, "first"),
        (FootballConversionAction.TWO_POINT, "second"),
    ]
    empty = FootballDeckState(())
    match = replace(match, team_a_offense_deck=empty, team_a_defense_deck=empty)
    buttons = view.draw(surface, area, replace(state, match=match))
    assert [button.label for button in buttons] == ["EXTRA POINT", "2PT: BASIC RUN"]
    buttons[1].action()
    assert conversions[-1] == (FootballConversionAction.TWO_POINT, None)
    for decision, label, offensive in (
        (FootballHumanDecision.OFFENSIVE_PLAY, "FALLBACK / INSIDE RUN", True),
        (FootballHumanDecision.DEFENSIVE_SCHEME, "FALLBACK / RUN FIT", False),
    ):
        buttons = view.draw(surface, area, replace(state, match=match, human_decision=decision))
        assert [button.label for button in buttons] == [label]
        buttons[0].action()
        assert fallbacks[-1] is offensive
    buttons = view.draw(
        surface, area, replace(state, human_decision=FootballHumanDecision.FOURTH_DOWN)
    )
    for button in buttons:
        button.action()
    assert fourth_down == list(FootballFourthDownAction)


def test_match_decision_callbacks_reach_controller_with_fallback_and_copy_id(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    state = controller.state
    match = state.match
    assert match is not None and match.team_a_offense_deck is not None
    card_id = match.team_a_offense_deck.hand[0].card_id
    copies = (FootballCardCopy("first", card_id), FootballCardCopy("second", card_id))
    empty = FootballDeckState(())
    match = replace(
        match, team_a_offense_deck=empty, team_a_defense_deck=empty,
    )
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(controller, "choose_offensive_play", lambda action: calls.append((action,)))
    monkeypatch.setattr(controller, "choose_defensive_scheme", lambda action: calls.append((action,)))
    monkeypatch.setattr(
        controller, "choose_conversion",
        lambda action, copy_id=None: calls.append((action, copy_id)),
    )
    screen = desktop.run_screen
    for decision, action in (
        (FootballHumanDecision.OFFENSIVE_PLAY, OffensivePlayAction.RB_RUN),
        (FootballHumanDecision.DEFENSIVE_SCHEME, DefensiveSchemeAction.RB_RUN),
    ):
        screen.state = replace(state, match=match, human_decision=decision)
        desktop.router.draw(_surface())
        screen.buttons[0].action()
        assert calls[-1] == (action,)
        assert screen.last_error is None

    match = replace(match, team_a_offense_deck=FootballDeckState(copies, hand=copies))
    screen.state = replace(state, match=match, human_decision=FootballHumanDecision.CONVERSION)
    desktop.router.draw(_surface())
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_3}))
    assert calls[-1] == (FootballConversionAction.TWO_POINT, "second")
    assert screen.last_error is None


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
    first_rect = screen.match_interaction.card_rects[first_copy.copy_id]
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
    first_rect = screen.match_interaction.card_rects[first_copy.copy_id]
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
    dragged_rect = screen.match_interaction.card_rects[dragged_copy.copy_id]
    assert screen.match_interaction.play_area is not None
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"pos": dragged_rect.center, "button": 1},
        )
    )
    desktop.router.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"pos": screen.match_interaction.play_area.center, "button": 1},
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


def test_result_return_then_new_run_uses_updated_profile(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    first_controller = desktop.football_controller
    _force_result(monkeypatch, FootballTeamSide.TEAM_B)
    assert first_controller is not None
    for game_number in range(1, 4):
        _play_first_match_card(desktop)
        if game_number < 3:
            _activate(desktop, "OPEN NEXT GAME SHOP")
            _activate(desktop, "FINISH SHOP / START MATCH")
    assert first_controller.state.phase is FootballRunPhase.FIRED
    _activate(desktop, "RETURN TO MAIN MENU")
    assert desktop.router.current_id == "main_menu"
    desktop.save_profile("Fresh Team", "crimson", "gold")
    desktop.seed_factory = lambda: 17
    _start_run(desktop)

    assert desktop.football_controller is not first_controller
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert desktop.run_screen.team_name == "Fresh Team"
    assert desktop.run_screen.theme == desktop.theme
    assert desktop.run_screen.last_error is None
    assert not desktop.run_screen.confirm_exit
    drawn_colors: list[tuple[pygame.Color, pygame.Color]] = []
    original_art = football_player_draft_module.draw_draft_player

    def capture_art(surface, rect, appearance, active=False):
        drawn_colors.append((appearance.primary, appearance.secondary))
        original_art(surface, rect, appearance, active)

    monkeypatch.setattr(football_player_draft_module, "draw_draft_player", capture_art)
    _activate(desktop, "CHOOSE STAFF 01")
    desktop.router.draw(_surface())
    assert drawn_colors == [(tuple(desktop.theme.primary[:3]), tuple(desktop.theme.secondary[:3]))] * 3
    for position in PLAYER_DRAFT_ORDER:
        _activate(desktop, f"DRAFT {position.value}")
    assert desktop.football_controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert desktop.run_screen._shop_view().theme == desktop.theme
    _activate(desktop, "DEPTH CHART")
    assert desktop.run_screen.shop_review.mode == "depth"
    desktop.router.draw(_surface())


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
        assert replace(first_controller.state, player_appearances={}) == replace(
            replay_controller.state, player_appearances={})
    before = first_controller.state
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == before

    _activate(first, "FINISH SHOP / START MATCH")
    _activate(replay, "FINISH SHOP / START MATCH")
    for _ in range(30):
        first.router.draw(_surface())
    assert replace(first_controller.state, player_appearances={}) == replace(
        replay_controller.state, player_appearances={})
    _play_first_match_card(first)
    _play_first_match_card(replay)
    assert replace(first_controller.state, player_appearances={}) == replace(
        replay_controller.state, player_appearances={})
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
