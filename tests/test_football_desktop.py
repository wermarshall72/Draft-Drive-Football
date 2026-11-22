from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football import (
    FootballAutomaticAction,
    FootballCardFamily,
    DefensiveSchemeAction,
    FootballBonusCardAction,
    FootballCardCopy,
    FootballAwaitedAction,
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
    BONUS_CARD_CATALOG,
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
    coaches_for_assignment,
)
from src.engine.football_simulator import FootballMatchSimulator, calculate_standardized_play_estimate
from src.engine.football_decks import FootballPlayDefinition
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.engine.football_appearance import POSITION_ART
from src.engine.football_team_builder import FootballPlayerCandidate
from src.engine.football_player_catalog import (
    PLAYER_TYPES_BY_POSITION,
    player_from_type,
    player_type_for_id,
)
from src.ui.theme import relative_luminance
from src.engine.football_shop import (
    COACH_UPGRADE_CATALOG,
    PLAYER_UPGRADE_CATALOG,
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballShopSlotState,
    FootballUpgradeDuration,
    FootballUpgradeStat,
    _player_upgrade_catalog,
)
from src.ui.application import DesktopApplication
from src.ui import coach_art
from src.ui import football_run_screen as football_run_screen_module
from src.ui.football_display import _PLAY_LABELS, _POSITION_LABELS
from src.ui import football_coach_view as football_coach_module
from src.ui import football_review_view as football_review_module
from src.ui import football_depth_chart as football_depth_module
from src.ui import football_result as football_result_module
from src.ui import football_shop_view as football_shop_module
from src.ui.football_card_art import (
    bonus_card_art,
    play_card_art,
    scheme_card_art,
)
from src.ui import football_player_draft_view as football_player_draft_module
from src.engine.football_simulator import adjusted_offensive_play_clock_seconds
from src.ui.football_match_events import OutcomeEmphasis, PlayLineKind, outcome
from src.ui.football_match_hand import HandView, layout_groups
from src.ui.football_match_outcome import draw_outcome_strip
from src.ui.football_match_playback import EVENT_DURATION_MS
from src.ui.football_match_palette import match_font, plain_font, text_audit
from src.ui.football_match_piles import pile_cards, pile_counts
from src.ui.football_match_events import is_real_play, kickoff_pending, replay_label, snapshot_state
from src.ui.football_match_field import FieldOverlay, draw_match_field
from src.ui.football_match_hand import FALLBACK_DISPLAY_ID
from src.ui.football_match_scoreboard import (
    ball_spot_text, down_text, draw_scoreboard, opponent_hand_counts,
)
from src.ui.football_match_screen import (
    FIELD_RECT, HAND_RECT, LEFT_PILES_RECT, POST_REPLAY_NOTE, RIGHT_PILES_RECT,
    SCOREBOARD_RECT as SCOREBOARD_RECT_FOR_TESTS, STRIP_RECT, FootballMatchScreen, MatchActions,
)
from src.ui import player_art
from src.ui.layout import LOGICAL_SIZE
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.text import wrap_text_lines
from src.ui.widgets import Button


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
    if screen is desktop.run_screen and label != "SKIP >>":
        if screen.match_screen.playback.blocking() and not screen.match_screen.popup.open:
            screen.match_screen.playback.skip()
            desktop.router.draw(_surface())
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


def _skip_match_playback(desktop: DesktopApplication) -> None:
    """Press Skip if an AI replay is blocking input, leaving the screen drawn."""
    desktop.router.draw(_surface())
    match_screen = desktop.run_screen.match_screen
    if match_screen.playback.blocking():
        match_screen.playback.skip()
        desktop.router.draw(_surface())


def _play_human_decision(desktop: DesktopApplication) -> None:
    _skip_match_playback(desktop)
    screen = desktop.run_screen
    decision = desktop.football_controller.state.human_decision
    buttons = screen.buttons
    if decision in (FootballHumanDecision.OFFENSIVE_PLAY, FootballHumanDecision.DEFENSIVE_SCHEME):
        next(b for b in buttons if b.variant in ("hand-card", "hand-fallback") and b.enabled).action()
    elif decision is FootballHumanDecision.FOURTH_DOWN:
        next(b for b in buttons if b.label == "PUNT").action()
    elif decision is FootballHumanDecision.CONVERSION:
        next(b for b in buttons if b.label == "EXTRA POINT").action()
    elif decision is FootballHumanDecision.CHALLENGE:
        next(b for b in buttons if b.label == "DECLINE").action()


def _recording_actions(**overrides) -> MatchActions:
    def ignore(*_args) -> None:
        return None

    fields = {
        name: ignore
        for name in (
            "play_card", "fallback", "fourth_down", "conversion", "challenge",
            "challenge_touchdown", "end_run",
        )
    }
    fields.update(overrides)
    return MatchActions(**fields)


def _assert_text_fits(records) -> None:
    for text, rect, container in records:
        assert container.inflate(2, 2).contains(rect), (text, rect, container)


def _play_first_match_card(desktop: DesktopApplication) -> None:
    _skip_match_playback(desktop)
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
    assert state.shop is not None and state.shop.remaining_ap == 12


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
        shown.append((text, position, font))
        original(surface, text, position, font, color)

    monkeypatch.setattr(football_player_draft_module, "draw_text", capture)
    desktop.router.draw(_surface())
    for index, candidate in enumerate(changed):
        rect = screen.player_inspection.card_rects[index]
        card_text = [(text, point, font) for text, point, font in shown
                     if rect.collidepoint(point)]
        texts = [text for text, _, _ in card_text]
        player_type = player_type_for_id(candidate.player.player_type_id)
        partner = ("None" if player_type.partner_position is None else
                   football_player_draft_module._draft_position_label(player_type.partner_position))
        assert f"Partner: {partner}" in texts
        assert str(candidate.player.power) in texts
        assert football_player_draft_module._draft_percentage(candidate.player.volatility) in texts
        assert football_player_draft_module._draft_percentage(candidate.player.stamina) in texts
        strip_left = rect.left + 10
        strip_width = rect.width - 20
        column_width = strip_width // 3
        for column, label in enumerate(("POWER", "VOLATILITY", "STAMINA")):
            _, point, font = next(item for item in card_text if item[0] == label)
            label_rect = pygame.Rect(point, font.size(label))
            next_column = strip_left + 7 + (column + 1) * column_width
            assert label_rect.right <= min(strip_left + strip_width, next_column)


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
    assert shop.remaining_ap == 12

    _activate(desktop, "BUY", index=0)
    purchased = controller.state.shop
    assert purchased is not None
    assert purchased.remaining_ap == 12 - shop.offer[0].cost
    assert purchased.purchased_upgrades == (shop.offer[0],)
    _activate(desktop, "BUY", index=1)
    purchased_twice = controller.state.shop
    assert purchased_twice is not None
    assert len(purchased_twice.purchased_upgrades) == 2
    assert purchased_twice.remaining_ap < purchased.remaining_ap

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


def test_shop_landing_slots_show_saved_art_and_all_complete_coach_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    state = screen.state
    assert state is not None and state.shop is not None
    view = screen._shop_view()
    surface = _surface()
    content = pygame.Rect(20, 16, 1240, 688)
    portraits = []
    coach_portraits = []
    circles = []
    labels = []
    slots = []
    insets = []
    original_player = football_shop_module.draw_draft_player
    original_coach = football_shop_module.draw_coach_portrait
    original_circle = pygame.draw.circle
    original_text = football_shop_module.draw_text
    original_slot = view._landing_slot
    original_inset = view._inset

    def player_art(surface, rect, appearance):
        portraits.append((rect.copy(), appearance))
        original_player(surface, rect, appearance)

    def coach_art(surface, rect, coach_id, primary):
        coach_portraits.append(coach_id)
        original_coach(surface, rect, coach_id, primary)

    def circle(surface, color, center, radius, *args, **kwargs):
        circles.append((color, center, radius))
        return original_circle(surface, color, center, radius, *args, **kwargs)

    def capture_text(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        original_text(surface, text, position, font, color)

    def capture_slot(surface, rect, slot, buttons, shop, run_state, team_name):
        start_labels, start_buttons, start_insets = len(labels), len(buttons), len(insets)
        original_slot(surface, rect, slot, buttons, shop, run_state, team_name)
        slots.append((rect.copy(), slot, labels[start_labels:], buttons[start_buttons:],
                      insets[start_insets:]))

    def capture_inset(surface, rect):
        insets.append(rect.copy())
        original_inset(surface, rect)

    monkeypatch.setattr(football_shop_module, "draw_draft_player", player_art)
    monkeypatch.setattr(football_shop_module, "draw_coach_portrait", coach_art)
    monkeypatch.setattr(pygame.draw, "circle", circle)
    monkeypatch.setattr(football_shop_module, "draw_text", capture_text)
    monkeypatch.setattr(view, "_landing_slot", capture_slot)
    monkeypatch.setattr(view, "_inset", capture_inset)

    view.draw(surface, content, state.shop, run_state=state, team_name="Test Owls")
    player_slots = [item for item in slots if item[1].section is FootballShopSection.PLAYER_UPGRADES]
    play_slots = [item for item in slots if item[1].section is FootballShopSection.PLAYS_SCHEMES]
    assert len(player_slots) == 4 and len(play_slots) == 6
    assert [item[1].unlocked for item in play_slots] == [True] * 4 + [False] * 2
    assert [item[1].unlock_cost for item in play_slots[-2:]] == [4, 5]
    assert [item[0].topleft for item in play_slots] == sorted(
        (item[0].topleft for item in play_slots), key=lambda point: (point[1], point[0])
    )
    assert not player_slots[3][1].unlocked and player_slots[3][1].unlock_cost == 4
    for index, (_, slot, text, _, boxes) in enumerate(player_slots[:3]):
        assert slot.card is not None and slot.card.upgrade is not None
        upgrade = slot.card.upgrade
        assert portraits[index][1] == state.player_appearances[upgrade.position]
        rendered = " ".join(line for line, _ in text)
        assert _POSITION_LABELS[upgrade.position] in rendered
        assert upgrade.duration.value.upper() in rendered
        assert upgrade.stat.value.upper() in rendered
        sign = "-" if upgrade.stat is FootballUpgradeStat.VOLATILITY else "+"
        amount = upgrade.amount if upgrade.stat is FootballUpgradeStat.POWER else upgrade.amount * 100
        assert f"{sign}{amount:g}" in rendered
        assert slot.card.rarity.value.replace("_", " ").upper() in rendered
        assert f"{upgrade.cost} AP" in rendered
        assert len(boxes) == 1
        effect_rect = next(bounds for line, bounds in text if f"{sign}{amount:g}" in line)
        assert boxes[0].contains(effect_rect)

    for card in COACH_UPGRADE_CATALOG:
        shop = FootballShop(state.shop.roster, 51, game_number=4,
                            catalogs={FootballShopSection.COACH_UPGRADES: (card,)})
        shop.unlock_slot(FootballShopSection.COACH_UPGRADES, 1)
        assert shop.state.section(FootballShopSection.COACH_UPGRADES).slots[1].can_unlock
        slots.clear()
        labels.clear()
        coach_portraits.clear()
        circles.clear()
        view.draw(surface, content, shop.state, run_state=state, team_name="Test Owls")
        for rect, slot, text, buttons, boxes in slots:
            for index, (_, text_rect) in enumerate(text):
                assert rect.contains(text_rect), (card.name, text_rect, rect)
                assert not any(text_rect.colliderect(button.rect) for button in buttons), card.name
                assert not any(text_rect.colliderect(other) for _, other in text[index + 1:]), (card.name, text)
            for button in buttons:
                assert rect.contains(button.rect), (card.name, button.label)
        coach_slot = next(item for item in slots if item[1].card == card)
        rendered = " ".join(line for line, _ in coach_slot[2])
        assert card.description in rendered
        assert "unique" in rendered and f"{card.cost} AP" in rendered
        assert card.rarity.value.replace("_", " ").upper() in rendered
        assert len(coach_slot[4]) == 1
        box = coach_slot[4][0]
        body_rects = [bounds for _, bounds in coach_slot[2] if box.colliderect(bounds)]
        assert body_rects and all(box.contains(bounds) for bounds in body_rects)
        assert not any(box.colliderect(button.rect) for button in coach_slot[3])
        if card.coach_upgrade_effect.kind in {
            FootballCoachUpgradeKind.FUTURE_SHOP_AP, FootballCoachUpgradeKind.BYE_WEEK,
            FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS,
            FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION,
            FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS,
            FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
        }:
            assert not coach_portraits and len(circles) == 1
        else:
            defense_kinds = {
                FootballCoachUpgradeKind.DEFENSE_POWER_BOOST,
                FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION,
                FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST,
                FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
            }
            side = 1 if card.coach_upgrade_effect.kind in defense_kinds else 0
            selected = coaches_for_assignment(state.shop.roster.coach_assignment)[side]
            assert selected is not None
            assert coach_portraits == [selected.coach_id] and not circles


@pytest.mark.parametrize("window_size", [(1280, 720), (1000, 800)])
def test_shop_all_play_and_scheme_cards_render_complete_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    state = screen.state
    assert state is not None and state.shop is not None
    view = screen._shop_view()
    labels = []
    insets = []
    images: list[tuple[str, pygame.Rect]] = []
    original_text = football_shop_module.draw_text
    original_inset = view._inset
    original_draw_art = football_shop_module.draw_card_art

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        original_text(surface, text, position, font, color)

    def capture_inset(surface, rect):
        insets.append(rect.copy())
        original_inset(surface, rect)

    def capture_art(surface, filename, rect):
        images.append((filename, pygame.Rect(rect)))
        return original_draw_art(surface, filename, rect)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    monkeypatch.setattr(view, "_inset", capture_inset)
    monkeypatch.setattr(football_shop_module, "draw_card_art", capture_art)
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offset_x = (window_size[0] - round(1280 * scale)) // 2
    offset_y = (window_size[1] - round(720 * scale)) // 2
    for definition in (*OFFENSIVE_PLAY_CATALOG.values(), *DEFENSIVE_SCHEME_CATALOG.values()):
        card = FootballShopCard(
            card_id=definition.card_id, name=definition.name, description=definition.description,
            section=FootballShopSection.PLAYS_SCHEMES, rarity=FootballShopRarity.COMMON,
            cost=2, eligible=lambda roster: True, effect=lambda roster: roster,
            football_card=definition,
        )
        slot = FootballShopSlotState(FootballShopSection.PLAYS_SCHEMES, 1, True, card,
                                     False, None, False, None)
        rect = pygame.Rect(10, 10, 295, 166)
        buttons = []
        labels.clear()
        insets.clear()
        images.clear()
        view._landing_slot(_surface(), rect, slot, buttons, state.shop, state, "Test Owls")
        rendered = " ".join(line for line, _ in labels)
        assert definition.name in rendered
        contributors = " / ".join(
            football_shop_module._COMPACT_POSITION_LABELS[p] for p in definition.contributors
        )
        assert f"POSITIONS: {contributors}" in rendered
        assert f"PLAY TYPE: {definition.family.label.upper()}" in rendered
        if isinstance(definition, FootballPlayDefinition):
            estimate = calculate_standardized_play_estimate(definition.action).expected_yards
            expected_rows = [f"POSITIONS: {contributors}", f"PLAY TYPE: {definition.family.label.upper()}",
                             f"EXPECTED YARDAGE: ~{estimate:.1f} YDS", f"TIME: {definition.clock_seconds}s"]
        else:
            expected_rows = [f"POSITIONS: {contributors}", f"PLAY TYPE: {definition.family.label.upper()}",
                             f"COUNTERS: {definition.family.label.upper()}"]
            assert "YARDAGE" not in rendered and "TIME:" not in rendered
        assert len(insets) == len(images) == 1
        box = insets[0]
        art_name, art = images[0]
        assert art.size == (70, 70) and art.centery == rect.centery
        assert art_name == (
            play_card_art(definition.family)
            if isinstance(definition, FootballPlayDefinition)
            else scheme_card_art(definition.family)
        )
        assert rect.contains(art) and rect.contains(box) and not art.colliderect(box)
        assert not any(art.colliderect(button.rect) or box.colliderect(button.rect) for button in buttons)
        for row in expected_rows:
            row_matches = [bounds for line, bounds in labels if line == row]
            assert len(row_matches) == 1 and box.contains(row_matches[0]), (definition.name, row)
            bounds = row_matches[0]
            assert 0 <= offset_x + bounds.left * scale
            assert offset_x + bounds.right * scale <= window_size[0]
            assert 0 <= offset_y + bounds.top * scale
            assert offset_y + bounds.bottom * scale <= window_size[1]
        assert [next(bounds.y for line, bounds in labels if line == row) for row in expected_rows] == sorted(
            next(bounds.y for line, bounds in labels if line == row) for row in expected_rows
        )
        for index, (_, bounds) in enumerate(labels):
            assert rect.contains(bounds)
            assert not any(bounds.colliderect(button.rect) for button in buttons)
            assert not any(bounds.colliderect(other) for _, other in labels[index + 1:])
            assert not art.colliderect(bounds)


@pytest.mark.parametrize("window_size", [(1280, 720), (1000, 800)])
def test_bonus_cards_fit_shop_and_playbook_layouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    state = screen.state
    assert state is not None and state.shop is not None
    shop_view = screen._shop_view()
    displayed: list[tuple[str, pygame.Rect]] = []
    shop_art: list[tuple[str, pygame.Rect]] = []
    original_shop_draw_art = football_shop_module.draw_card_art
    original_shop_draw_text = football_shop_module.draw_text

    def capture_shop_art(surface, filename, rect):
        shop_art.append((filename, pygame.Rect(rect)))
        return original_shop_draw_art(surface, filename, rect)

    def capture_shop_text(surface, text, position, font, color):
        bounds = pygame.Rect(position, font.size(text))
        displayed.append((text, bounds))
        original_shop_draw_text(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_card_art", capture_shop_art)
    monkeypatch.setattr(football_shop_module, "draw_text", capture_shop_text)
    bonus_copies = []
    for definition in BONUS_CARD_CATALOG.values():
        card = FootballShopCard(
            card_id=f"bonus:{definition.card_id}",
            name=definition.name,
            description=definition.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.UNCOMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            bonus_card=definition,
        )
        slot = FootballShopSlotState(
            section=FootballShopSection.PLAYS_SCHEMES,
            slot_number=1,
            unlocked=True,
            card=card,
            purchased=False,
            unlock_cost=None,
            can_unlock=False,
            disabled_reason=None,
        )
        rect = pygame.Rect(10, 10, 295, 166)
        buttons: list[Button] = []
        displayed.clear()
        shop_view._landing_slot(
            _surface(), rect, slot, buttons, state.shop, state, "Test Owls"
        )
        rendered = " ".join(text for text, _ in displayed)
        assert definition.name in rendered
        assert definition.description in rendered
        assert all(rect.contains(bounds) for _, bounds in displayed)
        assert len(buttons) == 1 and rect.contains(buttons[0].rect)
        art_name, art_rect = shop_art[-1]
        assert art_name == bonus_card_art(definition.action)
        assert rect.contains(art_rect)
        assert not any(art_rect.colliderect(bounds) for _, bounds in displayed)
        assert not art_rect.colliderect(buttons[0].rect)
        bonus_copies.append(
            FootballCardCopy(
                f"bonus-copy:{definition.card_id}",
                definition.card_id,
            )
        )

    removal_card = FootballShopCard(
        card_id="remove-one-card",
        name="Remove One Card",
        description="Select one owned card to remove.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.RARE,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        is_removal=True,
    )
    removal_slot = FootballShopSlotState(
        section=FootballShopSection.PLAYS_SCHEMES,
        slot_number=1,
        unlocked=True,
        card=removal_card,
        purchased=False,
        unlock_cost=None,
        can_unlock=False,
        disabled_reason=None,
    )
    shop_art.clear()
    shop_view._landing_slot(
        _surface(),
        pygame.Rect(10, 10, 295, 166),
        removal_slot,
        [],
        state.shop,
        state,
        "Test Owls",
    )
    assert shop_art[0][0] == "shop_remove_one_card.png"

    playbook_shop = replace(state.shop, offensive_deck=tuple(bonus_copies))
    review = football_review_module.FootballReviewView(
        screen.theme,
        screen._small_font,
        screen._label_font,
        screen.shop_review,
        lambda: None,
        lambda _copy_id: None,
    )
    displayed.clear()
    descriptions: list[str] = []
    description_rects: list[pygame.Rect] = []
    playbook_art: list[tuple[str, pygame.Rect]] = []
    original_review_draw_art = football_review_module.draw_card_art
    original_review_draw_text = football_review_module.draw_text
    original_complete_wrapped = football_review_module.draw_complete_wrapped_text

    def capture_review_text(surface, text, position, font, color):
        bounds = pygame.Rect(position, font.size(text))
        displayed.append((text, bounds))
        original_review_draw_text(surface, text, position, font, color)

    def capture_review_art(surface, filename, rect):
        playbook_art.append((filename, pygame.Rect(rect)))
        return original_review_draw_art(surface, filename, rect)

    def capture_review_description(
        surface, text, rect, font, color, *, line_gap=2
    ):
        descriptions.append(text)
        description_rects.append(rect.copy())
        return original_complete_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    monkeypatch.setattr(football_review_module, "draw_text", capture_review_text)
    monkeypatch.setattr(football_review_module, "draw_card_art", capture_review_art)
    monkeypatch.setattr(
        football_review_module,
        "draw_complete_wrapped_text",
        capture_review_description,
    )
    content = pygame.Rect(20, 16, 1240, 688)
    review.interaction.open_playbook()
    review.draw_playbook(_surface(), content, playbook_shop)
    playbook_art.clear()
    displayed.clear()
    descriptions.clear()
    description_rects.clear()
    for page in range(review.interaction.playbook_max_scroll + 1):
        if page:
            review.interaction.handle_scroll(
                pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
            )
        playbook_buttons = review.draw_playbook(
            _surface(), content, playbook_shop
        )
    rendered = " ".join(text for text, _ in displayed)
    for definition in BONUS_CARD_CATALOG.values():
        assert definition.name in rendered
        assert definition.description in descriptions
    assert all(content.contains(bounds) for _, bounds in displayed)
    assert {filename for filename, _ in playbook_art} == {
        bonus_card_art(definition.action)
        for definition in BONUS_CARD_CATALOG.values()
    } | {
        scheme_card_art(DEFENSIVE_SCHEME_CATALOG[card.card_id].family)
        for card in playbook_shop.defensive_deck
    }
    for _, art_rect in playbook_art:
        assert content.contains(art_rect)
        assert not any(art_rect.colliderect(bounds) for _, bounds in displayed)
        assert not any(art_rect.colliderect(bounds) for bounds in description_rects)
        assert not any(art_rect.colliderect(button.rect) for button in playbook_buttons)
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offset_x = (window_size[0] - round(1280 * scale)) // 2
    offset_y = (window_size[1] - round(720 * scale)) // 2
    for _, bounds in displayed:
        assert 0 <= offset_x + bounds.left * scale
        assert offset_x + bounds.right * scale <= window_size[0]
        assert 0 <= offset_y + bounds.top * scale
        assert offset_y + bounds.bottom * scale <= window_size[1]


@pytest.mark.parametrize(
    ("rarity", "edge"),
    [
        (FootballShopRarity.COMMON, "#abb6c2"),
        (FootballShopRarity.UNCOMMON, "#68c58a"),
        (FootballShopRarity.RARE, "#65b5ff"),
        (FootballShopRarity.VERY_RARE, "#c18be8"),
    ],
)
@pytest.mark.parametrize("section", list(FootballShopSection))
@pytest.mark.parametrize("status", ["available", "purchased", "unaffordable"])
def test_shop_rarity_outline_and_label_follow_offered_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    rarity: FootballShopRarity, edge: str, section: FootballShopSection, status: str,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.run_screen.state
    assert state is not None and state.shop is not None
    view = desktop.run_screen._shop_view()
    if section is FootballShopSection.PLAYER_UPGRADES:
        original = state.shop.section(section).slots[0].card
        assert original is not None and original.upgrade is not None
        upgrade = replace(original.upgrade, rarity=rarity)
        card = replace(original, rarity=rarity, upgrade=upgrade)
        rect = pygame.Rect(10, 10, 144, 182)
    elif section is FootballShopSection.COACH_UPGRADES:
        card = replace(COACH_UPGRADE_CATALOG[0], rarity=rarity)
        rect = pygame.Rect(10, 10, 296, 277)
    else:
        definition = OFFENSIVE_PLAY_CATALOG["slot_slant"]
        card = FootballShopCard(
            card_id=definition.card_id, name=definition.name, description=definition.description,
            section=section, rarity=rarity, cost=2, eligible=lambda roster: True,
            effect=lambda roster: roster, football_card=definition,
        )
        rect = pygame.Rect(10, 10, 295, 166)
    slot = FootballShopSlotState(section, 1, True, card, status == "purchased", None, False, None)
    shop = replace(state.shop, remaining_ap=0 if status == "unaffordable" else 12)
    labels = []
    original_text = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        original_text(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    surface = _surface()
    buttons = []
    view._landing_slot(surface, rect, slot, buttons, shop, state, "Test Owls")
    assert surface.get_at((rect.centerx, rect.top)) == pygame.Color(edge)
    rarity_label = rarity.value.replace("_", " ").upper()
    label_rect = next(bounds for text, bounds in labels if rarity_label in text)
    assert rect.contains(label_rect)
    assert not any(label_rect.colliderect(button.rect) for button in buttons)
    buy = buttons[-1]
    assert buy.enabled == (status == "available")
    assert buy.label == (
        "PURCHASED" if status == "purchased" else
        f"NEED {card.cost} AP" if status == "unaffordable" else "BUY"
    )


def test_shop_empty_locked_and_unmapped_rarity_keep_neutral_outline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.run_screen.state
    assert state is not None and state.shop is not None
    view = desktop.run_screen._shop_view()
    section = state.shop.section(FootballShopSection.PLAYER_UPGRADES)
    offered = section.slots[0]
    assert offered.card is not None
    monkeypatch.setattr(football_shop_module, "_RARITY_OUTLINE_COLORS", {})
    labels = []
    original_text = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        labels.append(text)
        original_text(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    slots = (offered, section.slots[3], replace(offered, card=None))
    for slot in slots:
        surface = _surface()
        rect = pygame.Rect(10, 10, 144, 182)
        labels.clear()
        view._landing_slot(surface, rect, slot, [], state.shop, state, "Test Owls")
        assert surface.get_at((rect.centerx, rect.top)) == pygame.Color("#507397")
        if slot.card is not None:
            assert slot.card.rarity.value.replace("_", " ").upper() in " ".join(labels)


@pytest.mark.parametrize("rarity", list(FootballShopRarity))
@pytest.mark.parametrize("input_method", ["mouse", "keyboard"])
def test_shop_rarity_controls_keep_contrasting_focus_and_activation(
    tmp_path: Path, rarity: FootballShopRarity, input_method: str,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    state = screen.state
    assert state is not None and state.shop is not None
    view = screen._shop_view()
    slot = state.shop.section(FootballShopSection.PLAYER_UPGRADES).slots[0]
    assert slot.card is not None and slot.card.upgrade is not None
    card = replace(slot.card, rarity=rarity, upgrade=replace(slot.card.upgrade, rarity=rarity))
    slot = replace(slot, card=card)
    calls = []
    view.purchase = lambda section, card_id, removal: calls.append((section, card_id, removal))
    buttons = []
    view._landing_slot(_surface(), pygame.Rect(10, 10, 144, 182), slot, buttons,
                       state.shop, state, "Test Owls")
    screen._set_buttons(buttons)
    button = buttons[0]
    button.focused = False
    normal, hover, focus = _surface(), _surface(), _surface()
    button.draw(normal, screen._main_font, screen.theme)
    button.draw(hover, screen._main_font, screen.theme, hovered=True)
    button.focused = True
    button.draw(focus, screen._main_font, screen.theme)
    point = (button.rect.centerx, button.rect.top + 2)
    assert hover.get_at(point) == focus.get_at(point) == pygame.Color("#ffffff")
    assert normal.get_at(point) != hover.get_at(point)
    button.focused = False
    if input_method == "keyboard":
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    else:
        for event_type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            desktop.router.handle_event(
                pygame.event.Event(event_type, {"pos": button.rect.center, "button": 1})
            )
    assert calls == [(FootballShopSection.PLAYER_UPGRADES, card.card_id, False)]


@pytest.mark.parametrize("window_size", [(1280, 720), (1000, 800)])
def test_shop_same_frame_purchase_and_unlock_invalidate_stale_controls(
    tmp_path: Path, window_size: tuple[int, int],
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    desktop.window_size = window_size
    desktop.router.draw(_surface())
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    button = next(button for button in desktop.run_screen.buttons if button.label == "UNLOCK 4 AP")
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offset = ((window_size[0] - round(1280 * scale)) // 2,
              (window_size[1] - round(720 * scale)) // 2)
    position = (round(button.rect.centerx * scale + offset[0]),
                round(button.rect.centery * scale + offset[1]))
    for _ in range(2):
        for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            event = pygame.event.Event(event_type, {"pos": position, "button": 1})
            desktop.router.handle_event(desktop._logical_event(event))
    shop = controller.state.shop
    assert shop is not None and shop.remaining_ap == 8
    assert shop.section(FootballShopSection.PLAYER_UPGRADES).slots[3].unlocked
    assert not shop.purchased_cards
    desktop.router.draw(_surface())
    assert desktop.run_screen.buttons


@pytest.mark.parametrize("purchase_bye", (False, True))
def test_coach_unlock_and_bye_week_through_shop_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, purchase_bye: bool,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    assert controller is not None
    card = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "bye_week")
    controller._shop_catalogs = {FootballShopSection.COACH_UPGRADES: (card,)}
    _draft_to_shop(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    for _ in range(3):
        _activate(desktop, "FINISH SHOP / START MATCH")
        _play_first_match_card(desktop)
        _activate(desktop, "OPEN NEXT GAME SHOP")
    desktop.router.draw(_surface())
    coach_section = controller.state.shop.section(FootballShopSection.COACH_UPGRADES)
    assert coach_section.slots[0].can_unlock
    unlock = [button for button in desktop.run_screen.buttons
              if button.label == "UNLOCK 4 AP" and button.rect.top > 300][0]
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(event_type, {"pos": unlock.rect.center, "button": 1}))
    desktop.router.draw(_surface())
    second = next(button for button in desktop.run_screen.buttons if button.label == "UNLOCK 6 AP")
    assert second.enabled
    if not purchase_bye:
        desktop.run_screen.focus_index = desktop.run_screen.buttons.index(second)
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
        assert controller.state.shop.section(FootballShopSection.COACH_UPGRADES).slots[1].unlocked
        assert not controller.state.shop.owned_coach_upgrades
        return
    detail = next(index for index, button in enumerate(desktop.run_screen.buttons)
                  if button.label == "DETAILS")
    buy = desktop.run_screen.buttons[detail + 1]
    assert buy.label == "BUY" and buy.enabled
    for _ in range(2):
        for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            desktop.router.handle_event(pygame.event.Event(event_type, {"pos": buy.rect.center, "button": 1}))
    assert controller.state.game_number == 5
    assert controller.state.skipped_games == (4,)
    assert controller.state.wins == 3 and controller.state.losses == 0
    assert controller.state.shop.remaining_ap == 12
    desktop.router.draw(_surface())


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
    assert "END RUN" not in {button.label for button in desktop.run_screen.buttons}
    assert "BACK TO SHOP" in {button.label for button in desktop.run_screen.buttons}
    assert "OWNED COPIES" in " ".join(displayed)
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
    card = next(card for card in _player_upgrade_catalog()
                if card.upgrade.stat is FootballUpgradeStat.POWER
                and card.upgrade.duration is FootballUpgradeDuration.PERMANENT)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    offered = card.upgrade
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


def test_temporary_upgrade_pending_display_and_pause_resume(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.VOLATILITY
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    before = controller.state
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    after = controller.state
    assert after.shop.roster == before.shop.roster
    assert football_depth_module.modified_player_stats(after, FootballPosition.QB) == (
        football_depth_module.modified_player_stats(before, FootballPosition.QB)
    )
    labels = []
    original = football_depth_module.draw_complete_wrapped_text

    def capture(surface, text, *args, **kwargs):
        labels.append(text)
        return original(surface, text, *args, **kwargs)

    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture)
    desktop.run_screen.state = after
    _activate(desktop, "DEPTH CHART")
    desktop.router.draw(_surface())
    _activate(desktop, "UPGRADES / PERK DETAILS")
    desktop.router.draw(_surface())
    assert any("PENDING NEXT MATCH" in text and "Volatility" in text for text in labels)
    _activate(desktop, "BACK TO DEPTH CHART")
    _activate(desktop, "BACK TO SHOP")
    _activate(desktop, "FINISH SHOP / START MATCH")
    started = controller.state
    assert started.shop.pending_player_upgrades == (card.upgrade,)
    assert started.match.team_a.players[FootballPosition.QB].volatility == pytest.approx(
        max(0, before.shop.roster.players[FootballPosition.QB].volatility - card.upgrade.amount)
    )
    _activate(desktop, "PAUSE")
    assert desktop.run_screen.match_screen.popup.kind == "pause"
    _activate(desktop, "DEPTH CHART")
    _activate(desktop, "UPGRADES / PERK DETAILS")
    labels.clear()
    desktop.router.draw(_surface())
    # In the match the temporary upgrade is labeled as active for this match.
    assert any("ACTIVE THIS MATCH" in text and "Volatility" in text for text in labels)
    assert not any("PENDING NEXT MATCH" in text for text in labels)
    _activate(desktop, "CLOSE [ESC]")
    _activate(desktop, "END RUN")
    assert desktop.run_screen.confirm_exit
    desktop.run_screen._keep_playing()
    assert controller.state == started


def test_pending_upgrades_do_not_force_standard_depth_chart_scrolling(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    desktop.run_screen.state = controller.state
    cards = []
    original = football_depth_module._rounded_box

    def capture(surface, rect, fill, edge, radius=6):
        if fill == football_depth_module._CARD:
            cards.append(rect.copy())
        return original(surface, rect, fill, edge, radius)

    monkeypatch.setattr(football_depth_module, "_rounded_box", capture)
    _activate(desktop, "DEPTH CHART")
    cards.clear()
    desktop.router.draw(_surface())
    viewport = pygame.Rect(20, 71, 1240, 579)
    assert desktop.run_screen.shop_review.depth_max_scroll == 0
    assert len(cards) == 8 and all(viewport.contains(card) for card in cards)


@pytest.mark.parametrize(
    ("stat", "initial", "nominal"),
    [
        (FootballUpgradeStat.STAMINA, 0.97, "STAMINA +10%"),
        (FootballUpgradeStat.VOLATILITY, 0.015, "VOLATILITY -2%"),
    ],
)
def test_shop_renders_nominal_effects_even_at_stat_caps(
    tmp_path: Path, monkeypatch, stat, initial, nominal
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    position = FootballPosition.QB
    player = replace(state.shop.roster.players[position], **{stat.value: initial})
    roster = replace(state.shop.roster, players={**state.shop.roster.players, position: player})
    temp = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is position and card.upgrade.stat is stat
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                and card.rarity is FootballShopRarity.COMMON)
    perm = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is position and card.upgrade.stat is stat
                and card.upgrade.duration is FootballUpgradeDuration.PERMANENT
                and card.rarity is FootballShopRarity.COMMON)
    shop = FootballShop(roster, 1, catalogs={FootballShopSection.PLAYER_UPGRADES: (temp, perm)})
    labels = []
    original = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        return original(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    rect = pygame.Rect(28, 107, 141, 183)
    view = desktop.run_screen._shop_view()

    def render(card):
        labels.clear()
        slot = FootballShopSlotState(FootballShopSection.PLAYER_UPGRADES, 1, True,
                                     card, False, None, False, None)
        buttons = []
        view._landing_slot(_surface(), rect, slot, buttons, shop.state, state, "Team")
        for index, (_, bounds) in enumerate(labels):
            assert rect.contains(bounds)
            assert not any(bounds.colliderect(other) for _, other in labels[index + 1:])
            assert not any(bounds.colliderect(button.rect) for button in buttons)
        assert buttons[-1].enabled
        return " ".join(text for text, _ in labels)

    rendered = render(temp)
    assert nominal in rendered and "2 AP" in rendered
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    shop.move_to_next_day()
    rendered = render(temp)
    assert nominal in rendered
    permanent_display = render(perm)
    assert "3 AP" in permanent_display
    assert all(scope not in rendered and scope not in permanent_display
               for scope in ("RUN ", "NEXT ", "MATCH "))
    shop.buy_card(FootballShopSection.PLAYER_UPGRADES, temp.card_id)
    assert len(shop.state.pending_player_upgrades) == 2


@pytest.mark.parametrize("duration", list(FootballUpgradeDuration))
def test_shop_shows_nominal_stamina_with_coach_cap(tmp_path: Path, monkeypatch, duration) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    qb = replace(state.shop.roster.players[FootballPosition.QB], stamina=0.90)
    roster = replace(state.shop.roster, players={**state.shop.roster.players, FootballPosition.QB: qb})
    coach = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "fourth_quarter_conditioning")
    shop = replace(state.shop, roster=roster, owned_coach_upgrades=(coach,))
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.STAMINA
                and card.upgrade.duration is duration
                and card.rarity is FootballShopRarity.COMMON)
    captured = []
    original = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        captured.append(text)
        original(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    slot = FootballShopSlotState(FootballShopSection.PLAYER_UPGRADES, 1, True, card, False, None, False, None)
    desktop.run_screen._shop_view()._landing_slot(
        _surface(), pygame.Rect(28, 107, 141, 183), slot, [], shop, state, "Team"
    )
    if duration is FootballUpgradeDuration.PERMANENT:
        assert "STAMINA +5%" in captured
    else:
        assert "STAMINA +10%" in captured
    assert not any(text.startswith(("RUN ", "NEXT ", "MATCH ")) for text in captured)


def test_pending_details_distinguish_raw_and_coached_stacked_effects(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    qb = replace(state.shop.roster.players[FootballPosition.QB], stamina=0.85)
    roster = replace(state.shop.roster, players={**state.shop.roster.players, FootballPosition.QB: qb})
    coach = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == "fourth_quarter_conditioning")
    temp = next(card.upgrade for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.STAMINA
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                and card.rarity is FootballShopRarity.COMMON)
    shop = replace(state.shop, roster=roster, owned_coach_upgrades=(coach,),
                   pending_player_upgrades=(temp, temp))
    candidate = replace(state, shop=shop)
    interaction = desktop.run_screen.shop_review
    interaction.open_depth_chart()
    interaction.toggle_depth_details()
    review = football_review_module.FootballReviewView(
        desktop.theme, desktop.run_screen._small_font, desktop.run_screen._label_font,
        interaction, lambda: None, lambda _: None,
    )
    labels = []
    original = football_depth_module.draw_complete_wrapped_text

    def capture(surface, text, *args, **kwargs):
        labels.append(text)
        return original(surface, text, *args, **kwargs)

    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture)
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 1240, 690), candidate)
    joined = "\n".join(labels)
    assert "Nominal total: +20 percentage points Stamina" in joined
    assert "Raw run roster 85% -> raw next match 100%; change +15%" in joined
    assert "Coached next match 95% -> 100%; change +5%" in joined
    assert "Changes in % are percentage points." in joined
    assert "Not permanent." in joined
    assert interaction.depth_max_scroll > 0


def test_pending_combined_details_and_small_viewport_scrolling(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    position = FootballPosition.QB
    player = replace(state.shop.roster.players[position], stamina=0.94, volatility=0.03)
    roster = replace(state.shop.roster, players={**state.shop.roster.players, position: player})
    cards = tuple(card for card in PLAYER_UPGRADE_CATALOG
                  if card.upgrade.position is position
                  and card.upgrade.stat in (FootballUpgradeStat.STAMINA, FootballUpgradeStat.VOLATILITY)
                  and card.upgrade.rarity is FootballShopRarity.COMMON
                  and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    shop = FootballShop(roster, 2, catalogs={FootballShopSection.PLAYER_UPGRADES: cards})
    for card in cards:
        shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    shop.move_to_next_day()
    for card in cards:
        shop.buy_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    candidate = replace(state, shop=shop.state)
    interaction = desktop.run_screen.shop_review
    interaction.open_depth_chart()
    review = football_review_module.FootballReviewView(
        desktop.theme, desktop.run_screen._small_font, desktop.run_screen._label_font,
        interaction, lambda: None, lambda _: None,
    )
    labels = []
    original = football_depth_module.draw_complete_wrapped_text

    def capture(surface, text, *args, **kwargs):
        labels.append(text)
        return original(surface, text, *args, **kwargs)

    monkeypatch.setattr(football_depth_module, "draw_complete_wrapped_text", capture)
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 1240, 690), candidate)
    assert interaction.depth_max_scroll == 0
    interaction.toggle_depth_details()
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 1240, 690), candidate)
    joined = "\n".join(labels)
    assert "Nominal total: +20 percentage points Stamina" in joined
    assert "Raw run roster 94% -> raw next match 100%; change +6%" in joined
    assert "Coached next match 94% -> 100%; change +6%" in joined
    assert "Nominal total: -4 percentage points Volatility" in joined
    assert "Raw run roster 3% -> raw next match 0%; change -3%" in joined
    assert "Coached next match 3% -> 0%; change -3%" in joined
    assert "Changes in % are percentage points." in joined
    assert ("Play yardage spread depends on contributors on both teams and the 1-yard minimum; "
            "some plays may not become less variable.") in joined
    assert "Not permanent." in joined and interaction.depth_max_scroll > 0
    interaction.handle_scroll(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_END}))
    assert interaction.depth_scroll == interaction.depth_max_scroll
    interaction.toggle_depth_details()
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 600, 500), candidate)
    assert interaction.depth_max_scroll > 0
    interaction.handle_scroll(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1, "x": 0}))
    assert interaction.depth_scroll > 0


@pytest.mark.parametrize("message", [None, "CHECK: " + "A long transition message " * 4])
def test_shop_landing_excludes_projections_and_explanations(tmp_path: Path, monkeypatch, message) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    card = next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is FootballPosition.QB
                and card.upgrade.stat is FootballUpgradeStat.VOLATILITY
                and card.upgrade.rarity is FootballShopRarity.COMMON
                and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    qb = replace(state.shop.roster.players[FootballPosition.QB], volatility=0.02)
    roster = replace(state.shop.roster, players={**state.shop.roster.players, FootballPosition.QB: qb})
    shop = FootballShop(roster, 1, catalogs={FootballShopSection.PLAYER_UPGRADES: (card,)}).state
    labels = []
    original = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        return original(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    content = pygame.Rect(20, 15, 1240, 690)
    buttons = desktop.run_screen._shop_view().draw(
        _surface(), content, shop, transition_message=message, run_state=state
    )
    joined = " ".join(text for text, _ in labels)
    assert "VOLATILITY -2%" in joined and "2 AP" in joined
    assert "Volatility is a coached player stat" not in joined
    assert "RUN / NEXT: RAW" not in joined and "STA MAX 100%" not in joined
    assert not any(text.startswith(("RUN ", "NEXT ", "MATCH ")) for text, _ in labels)
    assert all(content.contains(bounds) and not any(bounds.colliderect(button.rect) for button in buttons)
               for _, bounds in labels)


def test_all_player_upgrade_cards_render_details_without_clipping(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    view = desktop.run_screen._shop_view()
    surface = _surface()
    labels = []
    icons = []
    art = []
    original = football_shop_module.draw_text
    original_icon = football_shop_module._duration_icon
    original_art = football_shop_module.draw_draft_player

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        return original(surface, text, position, font, color)

    def capture_icon(duration):
        image = original_icon(duration)
        icons.append((duration, image))
        return image

    def capture_art(surface, rect, appearance, *args, **kwargs):
        art.append(rect.copy())
        return original_art(surface, rect, appearance, *args, **kwargs)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    monkeypatch.setattr(football_shop_module, "_duration_icon", capture_icon)
    monkeypatch.setattr(football_shop_module, "draw_draft_player", capture_art)
    slot_rect = pygame.Rect(28, 107, 141, 183)
    for card in PLAYER_UPGRADE_CATALOG:
        labels.clear()
        icons.clear()
        art.clear()
        slot = FootballShopSlotState(FootballShopSection.PLAYER_UPGRADES, 1, True,
                                     card, False, None, False, None)
        buttons = []
        view._landing_slot(surface, slot_rect, slot, buttons, state.shop, state, "Team")
        rendered = [text for text, _ in labels]
        upgrade = card.upgrade
        assert _POSITION_LABELS[upgrade.position] in rendered
        assert upgrade.duration.value.upper() in rendered
        assert f"{card.rarity.value.replace('_', ' ').upper()} / {card.cost} AP" in rendered
        sign = "-" if upgrade.stat is FootballUpgradeStat.VOLATILITY else "+"
        amount = upgrade.amount if upgrade.stat is FootballUpgradeStat.POWER else upgrade.amount * 100
        suffix = "" if upgrade.stat is FootballUpgradeStat.POWER else "%"
        assert f"{upgrade.stat.value.upper()} {sign}{amount:g}{suffix}" in rendered
        assert len(icons) == 1 and icons[0][0] is upgrade.duration
        assert len(art) == 1 and slot_rect.contains(art[0])
        duration_rect = next(bounds for text, bounds in labels if text == upgrade.duration.value.upper())
        icon = icons[0][1]
        icon_rect = icon.get_rect(topright=(duration_rect.left - 4, duration_rect.top))
        assert icon.get_height() == duration_rect.height
        assert slot_rect.contains(icon_rect) and not icon_rect.colliderect(buttons[-1].rect)
        assert not any(icon_rect.colliderect(bounds) for _, bounds in labels)
        assert not icon_rect.colliderect(art[0])
        opaque = [(x, y) for y in range(icon.get_height()) for x in range(icon.get_width())
                  if icon.get_at((x, y)).a == 255]
        assert opaque
        assert all(surface.get_at((icon_rect.left + x, icon_rect.top + y)) == icon.get_at((x, y))
                   for x, y in opaque)
        assert not any(text.startswith(("RUN ", "NEXT ", "MATCH ")) for text in rendered)
        assert all(slot_rect.contains(rect) for _, rect in labels)
        assert all(not rect.colliderect(button.rect) for _, rect in labels for button in buttons)
        assert all(not first.colliderect(second)
                   for index, (_, first) in enumerate(labels)
                   for _, second in labels[index + 1:])


def test_duration_assets_are_transparent_trimmed_and_distinct() -> None:
    from importlib.resources import files

    assets = files("src.ui").joinpath("assets")
    images = []
    for duration, filename in (
        (FootballUpgradeDuration.TEMPORARY, "upgrade_temporary.png"),
        (FootballUpgradeDuration.PERMANENT, "upgrade_permanent.png"),
    ):
        asset = assets.joinpath(filename)
        assert asset.is_file()
        image = pygame.image.load(str(asset))
        assert image.get_bounding_rect() == image.get_rect()
        assert image.get_at((0, 0)).a == 0
        for y in range(image.get_height()):
            for x in range(image.get_width()):
                color = image.get_at((x, y))
                assert not (color.a and color.g > 155
                            and color.g > color.r * 1.65 and color.g > color.b * 1.65)
        rendered = football_shop_module._duration_icon(duration)
        assert rendered.get_height() == football_shop_module.staff_font(14).get_height()
        expected = pygame.transform.scale(image, rendered.get_size())
        assert pygame.image.tobytes(rendered, "RGBA") == pygame.image.tobytes(expected, "RGBA")
        images.append(pygame.image.tobytes(image, "RGBA"))
    assert images[0] != images[1]


def test_coached_shop_cards_remain_nominal_without_overlaps(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    state = desktop.football_controller.state
    coach_ids = {"two_minute_drill", "front_seven_film", "fourth_quarter_conditioning",
                 "iron_lungs", "rhythm_install", "disguise_package"}
    coaches = tuple(card for card in COACH_UPGRADE_CATALOG if card.card_id in coach_ids)
    pending = tuple(card.upgrade for card in PLAYER_UPGRADE_CATALOG
                    if card.rarity is FootballShopRarity.COMMON
                    and card.upgrade.duration is FootballUpgradeDuration.TEMPORARY)
    shop = replace(state.shop, owned_coach_upgrades=coaches, pending_player_upgrades=pending)
    view = desktop.run_screen._shop_view()
    labels = []
    original = football_shop_module.draw_text

    def capture(surface, text, position, font, color):
        labels.append((text, pygame.Rect(position, font.size(text))))
        return original(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture)
    rect = pygame.Rect(28, 107, 141, 183)
    for card in PLAYER_UPGRADE_CATALOG:
        labels.clear()
        slot = FootballShopSlotState(FootballShopSection.PLAYER_UPGRADES, 1, True,
                                     card, False, None, False, None)
        buttons = []
        view._landing_slot(_surface(), rect, slot, buttons, shop, state, "Team")
        assert not any(text.startswith(("RUN ", "NEXT ", "MATCH ")) for text, _ in labels)
        assert all(rect.contains(bounds) and not bounds.colliderect(buttons[-1].rect)
                   for _, bounds in labels)
        assert all(not first.colliderect(second)
                   for index, (_, first) in enumerate(labels)
                   for _, second in labels[index + 1:])


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
    assert any(value == "(8.5%)" and color == football_depth_module._POSITIVE
               for value, _, _, color in text)
    assert controller.state == state
    compare = football_depth_module._comparison
    assert compare(0.08, 0.1, lower_is_better=True, percentage=True) == ("(8%)", football_depth_module._POSITIVE)
    assert compare(0.12, 0.1, lower_is_better=True, percentage=True) == ("(12%)", football_depth_module._NEGATIVE)
    assert compare(0.1, 0.1, lower_is_better=True, percentage=True) == ("(10%)", football_depth_module._NEUTRAL)
    assert compare(53, 50, lower_is_better=False, percentage=False) == ("(53)", football_depth_module._POSITIVE)
    assert compare(47, 50, lower_is_better=False, percentage=False) == ("(47)", football_depth_module._NEGATIVE)


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
    pending = tuple(card.upgrade for card in PLAYER_UPGRADE_CATALOG
                    if card.upgrade.duration is FootballUpgradeDuration.TEMPORARY
                    and card.upgrade.rarity is FootballShopRarity.COMMON)
    state = replace(state, shop=replace(state.shop, pending_player_upgrades=pending))
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
    screen.shop_review.modified_stats = True
    view.draw_depth_chart(_surface(), area, candidate)
    assert screen.shop_review.depth_max_scroll == 0


@pytest.mark.parametrize(("label", "base", "value", "percentage", "expected", "color"), [
    ("POWER", 50, 51, False, "(51)", "_POSITIVE"),
    ("POWER", 50, 49, False, "(49)", "_NEGATIVE"),
    ("POWER", 50, 50, False, "(50)", "_NEUTRAL"),
    ("STAMINA", 0.5, 0.525, True, "(52.5%)", "_POSITIVE"),
    ("STAMINA", 0.5, 0.49, True, "(49%)", "_NEGATIVE"),
    ("STAMINA", 0.5, 0.5, True, "(50%)", "_NEUTRAL"),
    ("VOLATILITY", 0.1, 0.085, True, "(8.5%)", "_POSITIVE"),
    ("VOLATILITY", 0.1, 0.12, True, "(12%)", "_NEGATIVE"),
    ("VOLATILITY", 0.1, 0.1, True, "(10%)", "_NEUTRAL"),
])
def test_depth_chart_actual_modified_value_and_color(
    monkeypatch, label, base, value, percentage, expected, color
) -> None:
    pygame.font.init()
    rendered = []
    monkeypatch.setattr(football_depth_module, "draw_text",
                        lambda surface, text, position, font, ink: rendered.append((text, font, ink)))
    football_depth_module._draw_stat(_surface(), 10, 10, label, base, value, True, percentage)
    assert rendered[1] == (expected, football_depth_module._font(12, True),
                           getattr(football_depth_module, color))
    rendered.clear()
    football_depth_module._draw_stat(_surface(), 10, 10, label, base, value, False, percentage)
    assert len(rendered) == 1 and not rendered[0][0].endswith(")")


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
    area = pygame.Rect(20, 16, 1240, 688)
    shop_labels: list[str] = []
    original_shop_text = football_shop_module.draw_text

    def capture_shop_text(surface, text, position, font, color):
        shop_labels.append(text)
        original_shop_text(surface, text, position, font, color)

    monkeypatch.setattr(football_shop_module, "draw_text", capture_shop_text)
    view = screen._shop_view()
    buttons = view.draw(
        _surface(), area, shop.state, "Bye Week skipped scheduled game 3."
    )
    assert card.description in " ".join(shop_labels)
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
    content = pygame.Rect(20, 16, 1240, 688)

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
    player_buy = [button for button in screen.buttons if button.label == "BUY"][1]
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
    playbook_details: list[str] = []
    original_draw_text = football_run_screen_module.draw_text
    original_review_complete = football_review_module.draw_complete_wrapped_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    def capture_review_complete(
        surface, text, rect, font, color, *, line_gap=2
    ):
        playbook_details.append(text)
        return original_review_complete(
            surface, text, rect, font, color, line_gap=line_gap
        )

    monkeypatch.setattr(football_run_screen_module, "draw_text", capture_text)
    monkeypatch.setattr(football_review_module, "draw_text", capture_text)
    monkeypatch.setattr(
        football_review_module,
        "draw_complete_wrapped_text",
        capture_review_complete,
    )
    monkeypatch.setattr(football_shop_module, "draw_text", capture_text)
    desktop.router.draw(_surface())
    shop_copy = " ".join(displayed)
    assert play.name in shop_copy and scheme.name in shop_copy
    assert "COMMON" in shop_copy
    assert "SHORT PASS" in shop_copy
    assert "YARDAGE: STANDARDIZED NEUTRAL ESTIMATE" in shop_copy
    assert "EXPECTED YARDAGE: ~7.3 YDS" in shop_copy
    assert "TIME: 22s" in shop_copy
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
    assert any("NEUTRAL ~7.3 YDS" in detail and "BASE 22s" in detail
               for detail in playbook_details)
    assert "Quarters Coverage" in playbook_copy
    assert any("COUNTERS DEEP PASS" in detail for detail in playbook_details)


def test_shop_slot_rendering_handles_card_kinds_at_live_slot_sizes(
    tmp_path: Path,
    monkeypatch,
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
    cases = (
        ("affordable play", play_card, False, 2, "BUY", "EXPECTED YARDAGE"),
        ("purchased play", play_card, True, 2, "PURCHASED", "Slot Slant"),
        ("unaffordable play", play_card, False, 1, "NEED 1 AP", "Slot Slant"),
        ("defensive scheme", scheme_card, False, 2, "BUY", "COUNTERS"),
    )
    displayed: list[str] = []
    original_draw_text = football_run_screen_module.draw_text

    def capture_text(surface, text, position, font, color):
        displayed.append(text)
        original_draw_text(surface, text, position, font, color)

    view = desktop.run_screen._shop_view()
    live_rects: dict[FootballShopSection, pygame.Rect] = {}
    original_landing_slot = view._landing_slot

    def capture_slot_rect(surface, rect, slot, *args):
        live_rects.setdefault(slot.section, rect.copy())
        original_landing_slot(surface, rect, slot, *args)

    monkeypatch.setattr(view, "_landing_slot", capture_slot_rect)
    desktop.router.draw(_surface())
    monkeypatch.setattr(view, "_landing_slot", original_landing_slot)
    assert FootballShopSection.PLAYS_SCHEMES in live_rects

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
        view._landing_slot(
            _surface(),
            live_rects[card.section],
            slot,
            buttons,
            replace(shop, remaining_ap=remaining_ap),
            controller.state,
            "Team",
        )

        assert buttons[-1].label == expected_button, label
        assert expected_text.upper() in " ".join(displayed).upper(), (
            label,
            displayed,
        )


def test_supported_desktop_layout_renders_the_actual_shop(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)

    desktop.router.draw(_surface())

    assert desktop.run_screen._current_state().shop is not None
    assert any(button.label == "BUY" for button in desktop.run_screen.buttons)








def test_playbook_removal_can_be_cancelled_or_confirmed_in_the_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.shop is not None
    before = controller.state.shop
    pending_art: list[pygame.Rect] = []
    original_draw_art = football_review_module.draw_card_art

    def capture_art(surface, filename, rect):
        pending_art.append(pygame.Rect(rect))
        return original_draw_art(surface, filename, rect)

    monkeypatch.setattr(football_review_module, "draw_card_art", capture_art)

    _activate(desktop, "SELECT CARD")
    assert desktop.run_screen.shop_review.mode == "playbook"
    desktop.router.draw(_surface())
    assert "END RUN" not in {button.label for button in desktop.run_screen.buttons}
    pending = controller.state.shop
    assert pending is not None and pending.pending_removal is not None
    assert pending.remaining_ap == before.remaining_ap
    _activate(desktop, "CATEGORY: ALL CATEGORIES")
    desktop.router.draw(_surface())
    assert pending_art
    remove_buttons = [
        button for button in desktop.run_screen.buttons if button.label == "REMOVE"
    ]
    assert remove_buttons
    assert all(
        not art_rect.colliderect(button.rect)
        for art_rect in pending_art
        for button in remove_buttons
    )
    _activate(desktop, "CANCEL SELECTION")
    cancelled = controller.state.shop
    assert cancelled is not None and cancelled.pending_removal is None
    assert cancelled.remaining_ap == before.remaining_ap

    _activate(desktop, "SELECT CARD")
    _activate(desktop, "CATEGORY: ALL CATEGORIES")
    desktop.router.draw(_surface())
    expected_offense = before.offensive_deck[1:]
    _activate(desktop, "REMOVE")
    removed = controller.state.shop
    assert removed is not None and removed.pending_removal is None
    assert removed.remaining_ap == before.remaining_ap - 2
    assert removed.offensive_deck == expected_offense
    assert removed.defensive_deck == before.defensive_deck
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


def test_match_hand_clock_preview_matches_resolved_play_and_incomplete_rule(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    base_state = controller.state
    match = base_state.match
    assert match is not None and match.team_a_offense_deck is not None
    view = HandView()
    upgrade_sets = (
        (),
        (_coach_card_effect("tempo_install"),),
        (_coach_card_effect("huddle_up"),),
        (_coach_card_effect("tempo_install"), _coach_card_effect("huddle_up")),
    )
    hand = (
        FootballCardCopy("preview:rb_run", OffensivePlayAction.RB_RUN.value),
        FootballCardCopy("preview:short_pass", OffensivePlayAction.SHORT_PASS.value),
        FootballCardCopy("preview:deep_pass", OffensivePlayAction.DEEP_PASS.value),
    )
    for upgrades in upgrade_sets:
        live_match = replace(
            match,
            possession=FootballTeamSide.TEAM_A,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            team_a_offense_deck=FootballDeckState(hand, hand=hand),
            team_a_coach_upgrades=upgrades,
        )
        simulator = FootballMatchSimulator(live_match)
        simulator.rng.random = lambda: 0.99
        simulator.resolve_offensive_play(OffensivePlayAction.RB_RUN)
        result = simulator.state.match_events[-1].play_result
        assert result is not None and not result.incomplete
        preview = view.card_preview(live_match, OffensivePlayAction.RB_RUN.value)
        assert preview.live
        assert preview.clock == f"{result.clock_seconds_used}s"
        assert preview.yards.startswith("~")

        # An incomplete pass uses the separate 5s rule; the card shows the live normal clock.
        simulator = FootballMatchSimulator(live_match)
        rolls = iter((0.99, 0.0))
        simulator.rng.random = lambda: next(rolls)
        simulator.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
        incomplete = simulator.state.match_events[-1].play_result
        assert incomplete is not None and incomplete.incomplete
        assert incomplete.clock_seconds_used == 5
        deep = view.card_preview(live_match, OffensivePlayAction.DEEP_PASS.value)
        assert deep.clock == "{}s".format(adjusted_offensive_play_clock_seconds(
            OFFENSIVE_PLAY_CATALOG[OffensivePlayAction.DEEP_PASS.value].clock_seconds, upgrades,
        ))

    # Off the ball the cards fall back to printed values, labeled as base.
    defending = replace(match, possession=FootballTeamSide.TEAM_B)
    base = view.card_preview(defending, OffensivePlayAction.DEEP_PASS.value)
    assert not base.live
    assert base.clock == f"{OFFENSIVE_PLAY_CATALOG['deep_pass'].clock_seconds}s"

    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert any(text.startswith("~") for text in texts)
    assert "YDS LIVE" in texts and "CLOCK" in texts
    assert not any("1ST" in text and "%" in text for text in texts)


def test_match_outcome_labels_turnovers_on_downs() -> None:
    result = FootballPlayResult(
        offensive_play=OffensivePlayAction.RB_RUN,
        yards_gained=3.0,
        clock_seconds_used=18,
        possession_changed=True,
        turnover_on_downs=True,
    )
    event = FootballMatchEvent(
        sequence=1, action=OffensivePlayAction.RB_RUN, team_a_score=0, team_b_score=0,
        possession=FootballTeamSide.TEAM_B, offense_field_position=78.0, down=1,
        yards_to_go=10.0, game_clock_seconds=882, period=1,
        status=FootballMatchStatus.IN_PROGRESS, clock_seconds_used=18, play_result=result,
    )
    text = outcome(event, None, "Home", "Away")
    assert text.headline == "+3 YARDS · TURNOVER ON DOWNS"
    assert text.detail == f"{OFFENSIVE_PLAY_CATALOG['rb_run'].name.upper()} · HOME"
    assert text.kind is PlayLineKind.RUN


def test_match_outcome_play_name_does_not_get_a_power_stat_icon() -> None:
    pygame.font.init()
    result = FootballPlayResult(
        offensive_play=OffensivePlayAction.POWER_TOSS, yards_gained=4.0, clock_seconds_used=18,
    )
    event = FootballMatchEvent(
        sequence=1, action=OffensivePlayAction.POWER_TOSS, team_a_score=0, team_b_score=0,
        possession=FootballTeamSide.TEAM_A, offense_field_position=25.0, down=1,
        yards_to_go=10.0, game_clock_seconds=882, period=1,
        status=FootballMatchStatus.IN_PROGRESS, clock_seconds_used=18, play_result=result,
    )
    text = outcome(event, None, "Home", "Away")
    assert text.detail == "POWER TOSS · HOME"
    with text_audit() as records:
        draw_outcome_strip(
            _surface(), pygame.Rect(16, 400, 1248, 64), text,
            prompt="", actions=[], playback_label=None, elapsed_ms=0,
        )
    detail_rect = next(rect for value, rect, _ in records if value == text.detail)
    assert detail_rect.width == plain_font(14).size(text.detail)[0]
    assert match_font(14).size(text.detail) != plain_font(14).size(text.detail)


def test_match_outcome_and_log_label_ball_hawk_defensive_touchdown() -> None:
    pygame.font.init()
    result = FootballPlayResult(
        offensive_play=OffensivePlayAction.DEEP_PASS, yards_gained=0.0, clock_seconds_used=18,
        points_scored=6, turnover=True, possession_changed=True,
        defensive_scheme=DefensiveSchemeAction.DEEP_PASS,
        perk_effects=("Ball-Hawk: +10 interception return yards",),
    )
    event = FootballMatchEvent(
        sequence=1, action=OffensivePlayAction.DEEP_PASS, team_a_score=0, team_b_score=6,
        possession=FootballTeamSide.TEAM_B, offense_field_position=98.0, down=1,
        yards_to_go=2.0, game_clock_seconds=882, period=1,
        status=FootballMatchStatus.IN_PROGRESS, clock_seconds_used=18, play_result=result,
        points_scored=6, scoring_team=FootballTeamSide.TEAM_B, perk_effects=result.perk_effects,
    )
    text = outcome(event, None, "Home", "Away")
    assert text.headline == "INTERCEPTION · RETURNED FOR TD!"
    assert text.detail == "DEEP PASS · HOME"
    assert text.emphasis is OutcomeEmphasis.TURNOVER


def test_match_playback_replays_ai_drive_in_order_blocks_input_and_skips(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    now = [100_000]
    screen.match_screen.clock = lambda: now[0]
    for _ in range(200):
        _skip_match_playback(desktop)
        state = controller.state
        if state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            before = len(state.match.match_events)
            card = next(b for b in screen.buttons if b.variant == "hand-card")
            card.action()
            if len(controller.state.match.match_events) - before >= 3:
                break
        else:
            _play_human_decision(desktop)
    else:
        pytest.fail("No multi-event AI drive followed a defensive call.")
    match = controller.state.match
    total = len(match.match_events)
    desktop.router.draw(_surface())
    playback = screen.match_screen.playback
    assert playback.blocking()
    shown = [len(screen.match_screen.display_match(match).match_events)]
    labels = [button.label for button in screen.buttons]
    assert labels[0] == "SKIP >>"
    assert not any(button.variant == "hand-card" for button in screen.buttons)
    assert screen.match_interaction.card_rects == {}
    unchanged = controller.state
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2}))
    first_hand_card = HAND_RECT.center
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(event_type, {"pos": first_hand_card, "button": 1}))
    assert controller.state == unchanged
    for _ in range(3):
        now[0] += EVENT_DURATION_MS
        desktop.router.draw(_surface())
        shown.append(len(screen.match_screen.display_match(match).match_events))
    assert shown == sorted(shown) and shown[0] == before + 1 and shown[1] == before + 2
    # The displayed scoreboard snapshot is that event's recorded snapshot.
    display = screen.match_screen.display_match(match)
    event = match.match_events[len(display.match_events) - 1]
    assert (display.team_a_score, display.team_b_score) == (event.team_a_score, event.team_b_score)
    assert display.game_clock_seconds == event.game_clock_seconds
    if playback.blocking():
        with text_audit() as records:
            desktop.router.draw(_surface())
        assert POST_REPLAY_NOTE in [text for text, _, _ in records]
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_s}))
    assert not playback.blocking()
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert POST_REPLAY_NOTE not in [text for text, _, _ in records]
    assert len(screen.match_screen.display_match(match).match_events) == total
    assert any(button.variant == "hand-card" for button in screen.buttons)


def test_match_screen_shows_both_hands_with_only_the_active_group_selectable(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    seen = set()
    for _ in range(200):
        _skip_match_playback(desktop)
        state = controller.state
        decision = state.human_decision
        match = state.match
        if decision in (FootballHumanDecision.OFFENSIVE_PLAY, FootballHumanDecision.DEFENSIVE_SCHEME):
            with text_audit() as records:
                desktop.router.draw(_surface())
            texts = {text for text, _, _ in records}
            offense = [OFFENSIVE_PLAY_CATALOG[c.card_id].name.upper() for c in match.team_a_offense_deck.hand]
            defense = [DEFENSIVE_SCHEME_CATALOG[c.card_id].name.upper() for c in match.team_a_defense_deck.hand]
            for name in offense + defense:
                assert any(name.startswith(text) or text in name for text in texts), name
            selectable = [b.label for b in screen.buttons if b.variant == "hand-card"]
            assert selectable == (offense if decision is FootballHumanDecision.OFFENSIVE_PLAY else defense)
            assert "OFFENSE HAND" in texts and "DEFENSE HAND" in texts
            seen.add(decision)
            if len(seen) == 2:
                break
        _play_human_decision(desktop)
    assert len(seen) == 2


def test_match_piles_match_owned_cards_and_open_read_only_popups(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    for _ in range(6):
        _skip_match_playback(desktop)
        _play_human_decision(desktop)
    _skip_match_playback(desktop)
    match = controller.state.match
    for deck in (match.team_a_offense_deck, match.team_a_defense_deck):
        counts = pile_counts(deck)
        assert counts.consistent
        assert counts.owned == len(deck.owned)
    with text_audit() as records:
        desktop.router.draw(_surface())
    for rect, deck in ((LEFT_PILES_RECT, match.team_a_offense_deck),
                       (RIGHT_PILES_RECT, match.team_a_defense_deck)):
        numbers = [text for text, drawn, _ in records if rect.contains(drawn) and text.isdigit()]
        assert numbers == [str(len(deck.draw_pile)), str(len(deck.discard_pile))]
        assert any(text == f"{len(deck.owned)} OWNED" for text, drawn, _ in records if rect.contains(drawn))
    unchanged = controller.state
    _activate(desktop, "OFFENSE DISCARD")
    desktop.router.draw(_surface())
    assert screen.match_screen.popup.kind == "pile"
    assert [button.label for button in screen.buttons] == ["CLOSE [ESC]"]
    discard = pile_cards(match.team_a_offense_deck, "offense_discard", offensive=True)
    assert discard == tuple(reversed(match.team_a_offense_deck.discard_pile))
    draw = pile_cards(match.team_a_offense_deck, "offense_draw", offensive=True)
    assert sorted(card.copy_id for card in draw) == sorted(c.copy_id for c in match.team_a_offense_deck.draw_pile)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert not screen.match_screen.popup.open
    _activate(desktop, "DEFENSE DRAW")
    _activate(desktop, "CLOSE [ESC]")
    assert not screen.match_screen.popup.open
    assert controller.state == unchanged


def test_opponent_hand_shows_counts_without_revealing_card_identities(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    simulator = controller._simulator
    secret_offense = tuple(
        FootballCardCopy(f"ai-off-{index}", card_id)
        for index, card_id in enumerate(("go_ball", "double_move", "corner_route", "seam_pass"))
    )
    secret_defense = tuple(
        FootballCardCopy(f"ai-def-{index}", card_id)
        for index, card_id in enumerate(("prevent_coverage", "robber_coverage"))
    )
    simulator.state = replace(
        simulator.state,
        team_b_offense_deck=FootballDeckState(secret_offense, hand=secret_offense),
        team_b_defense_deck=FootballDeckState(secret_defense, hand=secret_defense),
    )
    desktop.run_screen.state = controller.state
    assert opponent_hand_counts(controller.state.match) == (4, 2)
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert "OFF ×4" in texts and "DEF ×2" in texts
    secrets = [OFFENSIVE_PLAY_CATALOG[c.card_id].name.upper() for c in secret_offense] + [
        DEFENSIVE_SCHEME_CATALOG[c.card_id].name.upper() for c in secret_defense
    ]
    joined = " | ".join(text.upper() for text in texts)
    assert not any(secret in joined for secret in secrets)


def test_pause_menu_opens_depth_chart_and_play_log_and_keeps_exit_confirmation(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    unchanged = controller.state
    escape = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
    desktop.router.handle_event(escape)
    desktop.router.draw(_surface())
    assert [button.label for button in screen.buttons] == [
        "RESUME", "DEPTH CHART", "PLAY LOG", "END RUN",
    ]
    _activate(desktop, "DEPTH CHART")
    desktop.router.draw(_surface())
    assert screen.match_screen.popup.kind == "depth"
    assert "CLOSE [ESC]" in [button.label for button in screen.buttons]
    desktop.router.handle_event(escape)
    assert screen.match_screen.popup.kind == "pause"
    _activate(desktop, "PLAY LOG")
    assert screen.match_screen.popup.kind == "log"
    _activate(desktop, "CLOSE [ESC]")
    assert screen.match_screen.popup.kind == "pause"
    _activate(desktop, "RESUME")
    assert not screen.match_screen.popup.open
    _activate(desktop, "PAUSE")
    assert screen.match_screen.popup.kind == "pause"
    _activate(desktop, "END RUN")
    assert screen.confirm_exit
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {"DISCARD RUN", "KEEP PLAYING"}
    _activate(desktop, "KEEP PLAYING")
    assert not screen.confirm_exit
    assert screen.match_screen.popup.kind == "pause"
    desktop.router.handle_event(escape)
    assert not screen.match_screen.popup.open
    assert controller.state == unchanged
    assert desktop.router.current_id != "main_menu"


def test_match_interaction_reset_between_runs(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    match_screen = screen.match_screen
    match_screen.interaction.group_scroll["offense"] = 2
    match_screen.interaction.dragging_card_id = "unfinished"
    match_screen.open_play_log()
    screen.shop_review.open_playbook()
    screen.shop_review.playbook_scroll = 3
    screen.coach_inspection.hover_index = 1
    screen.player_inspection.hover_index = 1
    screen.player_inspection.card_rects.append(pygame.Rect(0, 0, 10, 10))
    desktop.navigate("main_menu")
    desktop.seed_factory = lambda: 17
    _start_run(desktop)
    assert screen.match_screen is match_screen
    assert match_screen.interaction.group_scroll["offense"] == 0
    assert match_screen.interaction.dragging_card_id is None
    assert not match_screen.popup.open
    assert match_screen.playback.match_key is None
    assert screen.shop_review.mode is None
    assert screen.shop_review.playbook_scroll == 0
    assert screen.coach_inspection.hover_index is None
    assert screen.player_inspection.hover_index is None
    assert screen.player_inspection.card_rects == []


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

    seen_offense = seen_defense = seen_ai_play = seen_two_point = False
    for _ in range(1200):
        state = controller.state
        if state.phase is not FootballRunPhase.MATCH:
            break
        assert state.match is not None
        _skip_match_playback(desktop)
        strip = {b.label: b for b in screen.buttons if b.variant.startswith("strip")}
        hand_buttons = [b for b in screen.buttons if b.variant == "hand-card"]
        event_count = len(state.match.match_events)
        expected_copy_id = None
        if state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            seen_offense = True
            deck = state.match.team_a_offense_deck
            assert deck is not None and deck.hand and not strip
            card = deck.hand[0]
            expected_copy_id = card.copy_id
            expected = OFFENSIVE_PLAY_CATALOG[card.card_id].action
            assert len(hand_buttons) == len(deck.hand)
            hand_buttons[0].action()
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            seen_defense = True
            deck = state.match.team_a_defense_deck
            assert deck is not None and deck.hand and not strip
            card = deck.hand[0]
            expected_copy_id = card.copy_id
            expected = DEFENSIVE_SCHEME_CATALOG[card.card_id].action
            assert len(hand_buttons) == len(deck.hand)
            hand_buttons[0].action()
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            expected = FootballFourthDownAction.PUNT
            assert list(strip)[:2] == ["GO FOR IT", "PUNT"]
            assert list(strip)[2].startswith("FIELD GOAL · ")
            assert hand_buttons == []  # both hands stay visible but not playable
            strip["PUNT"].action()
        elif state.human_decision is FootballHumanDecision.CONVERSION:
            assert "EXTRA POINT" in strip
            if not seen_two_point:
                deck = state.match.team_a_offense_deck
                assert deck is not None
                if any(c.card_id in OFFENSIVE_PLAY_CATALOG for c in deck.hand):
                    card = next(c for c in deck.hand if c.card_id in OFFENSIVE_PLAY_CATALOG)
                    expected_copy_id = card.copy_id
                    button = next(
                        b for b in hand_buttons
                        if b.label == OFFENSIVE_PLAY_CATALOG[card.card_id].name.upper()
                    )
                    button.action()
                else:
                    strip["2-PT · BASIC RUN"].action()
                expected = FootballConversionAction.TWO_POINT
                seen_two_point = True
            else:
                expected = FootballConversionAction.EXTRA_POINT
                strip["EXTRA POINT"].action()
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
        FootballRunPhase.READY_FOR_NEXT_GAME, FootballRunPhase.FIRED, FootballRunPhase.PLAYOFFS,
    )
    assert final.match is not None and final.match.final_result is not None
    assert seen_offense and seen_defense and seen_ai_play and seen_two_point
    # The final plays replay on the match screen before the result appears.
    desktop.router.draw(_surface())
    if screen.match_screen.playback.blocking():
        assert screen.buttons[0].label == "SKIP >>"
        screen.buttons[0].action()
    desktop.router.draw(_surface())
    assert any(
        button.label in {"OPEN NEXT GAME SHOP", "RETURN TO MAIN MENU"}
        for button in screen.buttons
    )


def test_match_screen_previews_matchups_without_showing_roster_ratings(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert any(text.startswith("~") for text in texts)
    match = controller.state.match
    joined = " ".join(texts)
    assert not any(
        player.name in joined
        for roster in (match.team_a, match.team_b)
        for player in roster.players.values()
    )
    assert not any("POWER" == text.upper() or "RATING" in text.upper() for text in texts)
    hand = match.team_a_offense_deck.hand
    cards = [button for button in screen.buttons if button.variant == "hand-card"]
    assert [button.label for button in cards] == [
        _PLAY_LABELS[OFFENSIVE_PLAY_CATALOG[card.card_id].action] for card in hand
    ]
    assert screen.buttons[-1].label == "PAUSE"
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2}))
    match = controller.state.match
    played = next(
        event for event in reversed(match.match_events)
        if event.card_copy_id == hand[1].copy_id
    )
    assert played.action is OFFENSIVE_PLAY_CATALOG[hand[1].card_id].action


@pytest.mark.parametrize("offensive", [True, False])
def test_match_hand_scrolls_and_selects_exact_card_copies(
    tmp_path: Path, offensive: bool,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    catalog = OFFENSIVE_PLAY_CATALOG if offensive else DEFENSIVE_SCHEME_CATALOG
    card_id = next(iter(catalog))
    copies = tuple(FootballCardCopy(f"copy-{index}", card_id) for index in range(12))
    deck = FootballDeckState(copies, hand=copies)
    match = replace(match, **{"team_a_offense_deck" if offensive else "team_a_defense_deck": deck})
    if not offensive:
        match = replace(match, possession=FootballTeamSide.TEAM_B,
                        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                        current_drive_defensive_scheme=None)
    state = replace(
        state, match=match,
        human_decision=(
            FootballHumanDecision.OFFENSIVE_PLAY if offensive
            else FootballHumanDecision.DEFENSIVE_SCHEME
        ),
    )
    selected: list[str] = []
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 0)
    actions = _recording_actions(play_card=selected.append)
    surface = _surface()

    def draw():
        return match_screen.draw(surface, state, actions, focus_index=0, hover_index=None,
                                 pressed_index=None, error=None)

    buttons = draw()
    interaction = match_screen.interaction
    group = "offense" if offensive else "defense"
    visible = list(interaction.card_rects)
    assert visible == [card.copy_id for card in copies[: len(visible)]]
    assert 1 <= len(visible) < len(copies)
    assert interaction.group_max_scroll[group] == len(copies) - len(visible)
    rects = list(interaction.card_rects.values())
    assert all(HAND_RECT.contains(rect) for rect in rects)
    assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])
    cards = [b for b in buttons if b.variant == "hand-card"]
    cards[1].action()
    assert selected == ["copy-1"]
    interaction.pointer = interaction.group_areas[group].center
    interaction.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1}))
    draw()
    assert list(interaction.card_rects)[0] == "copy-1"
    scroll_right = next(b for b in match_screen.buttons if b.label == f"SCROLL {group.upper()} RIGHT")
    scroll_right.action()
    buttons = draw()
    assert list(interaction.card_rects)[0] == "copy-2"
    [b for b in buttons if b.variant == "hand-card"][0].action()
    assert selected == ["copy-1", "copy-2"]
    state = replace(state, human_decision=FootballHumanDecision.FOURTH_DOWN)
    draw()
    assert interaction.card_rects == {}


def test_large_mixed_hand_fits_without_overlap(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    offense = tuple(
        FootballCardCopy(f"o{index}", card_id)
        for index, card_id in enumerate(("rb_run", "offensive_draw", "challenge", "deep_pass", "go_ball", "inside_zone"))
    )
    defense = tuple(
        FootballCardCopy(f"d{index}", card_id)
        for index, card_id in enumerate(("rb_run", "deep_pass", "prevent_coverage"))
    )
    match = replace(
        match,
        team_a_offense_deck=FootballDeckState(offense, hand=offense),
        team_a_defense_deck=FootballDeckState(defense, hand=defense),
    )
    for decision in (FootballHumanDecision.OFFENSIVE_PLAY, FootballHumanDecision.CONVERSION):
        view = replace(state, match=match, human_decision=decision)
        match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                           desktop.run_screen._label_font, clock=lambda: 0)
        with text_audit() as records:
            buttons = match_screen.draw(_surface(), view, _recording_actions(), focus_index=0,
                                        hover_index=None, pressed_index=None, error=None)
        offense_layout, defense_layout = layout_groups(HAND_RECT, len(offense), len(defense), {})
        rects = list(offense_layout.card_rects) + list(defense_layout.card_rects) + [defense_layout.active_slot]
        assert len(offense_layout.card_rects) + len(defense_layout.card_rects) >= 8
        # Nine cards do not all fit, so the offense group scrolls to reach the rest.
        assert offense_layout.max_scroll + defense_layout.max_scroll == 1
        assert all(HAND_RECT.contains(rect) for rect in rects)
        assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])
        assert not offense_layout.area.colliderect(defense_layout.area)
        cards = {b.label: b for b in buttons if b.variant == "hand-card"}
        assert set(cards) >= {"OFFENSIVE DRAW", "CHALLENGE"}
        if decision is FootballHumanDecision.CONVERSION:
            # Two-point tries take a legal play card only; bonus cards stay visible but disabled.
            assert not cards["OFFENSIVE DRAW"].enabled
            assert cards[OFFENSIVE_PLAY_CATALOG["rb_run"].name.upper()].enabled
        else:
            assert cards["OFFENSIVE DRAW"].enabled
            assert not cards["CHALLENGE"].enabled
        # Bonus cards show their 10-second cost even at the narrowest card width.
        assert any(text.startswith("10s") for text, _, _ in records)
        _assert_text_fits(records)


def test_outcome_strip_holds_decisions_while_hands_stay_visible(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    card_id = match.team_a_offense_deck.hand[0].card_id
    copies = (FootballCardCopy("first", card_id), FootballCardCopy("second", card_id))
    challenge = FootballCardCopy("challenge-copy", FootballBonusCardAction.CHALLENGE.value)
    calls: list[tuple] = []
    actions = _recording_actions(
        play_card=lambda copy_id: calls.append(("card", copy_id)),
        fallback=lambda offensive: calls.append(("fallback", offensive)),
        fourth_down=lambda action: calls.append(("fourth", action)),
        conversion=lambda action, copy_id: calls.append(("conversion", action, copy_id)),
        challenge=lambda accept: calls.append(("challenge", accept)),
        challenge_touchdown=lambda: calls.append(("challenge_td",)),
    )
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 0)

    def draw(view_state):
        with text_audit() as records:
            buttons = match_screen.draw(_surface(), view_state, actions, focus_index=0,
                                        hover_index=None, pressed_index=None, error=None)
        _assert_text_fits(records)
        strip = [b for b in buttons if b.variant.startswith("strip")]
        assert all(STRIP_RECT.contains(b.rect) for b in strip)
        return strip, [b for b in buttons if b.variant == "hand-card"], {t for t, _, _ in records}

    fourth = replace(state, human_decision=FootballHumanDecision.FOURTH_DOWN,
                     match=replace(match, down=4, awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION))
    strip, cards, texts = draw(fourth)
    assert [b.label for b in strip][:2] == ["GO FOR IT", "PUNT"]
    assert cards == []
    assert any(name in texts for name in ("OFFENSE HAND", "OFFENSE"))
    for button in strip:
        button.action()
    assert [call[1] for call in calls] == list(FootballFourthDownAction)

    calls.clear()
    conversion_match = replace(match, team_a_offense_deck=FootballDeckState(copies + (challenge,), hand=copies + (challenge,)))
    conversion = replace(state, human_decision=FootballHumanDecision.CONVERSION,
                         match=conversion_match, challenge_available=True)
    strip, cards, _ = draw(conversion)
    assert [b.label for b in strip] == ["EXTRA POINT", "CHALLENGE TD"]
    assert [b.label for b in cards if b.enabled] == [OFFENSIVE_PLAY_CATALOG[card_id].name.upper()] * 2
    strip[0].action()
    [b for b in cards if b.enabled][1].action()
    strip[1].action()
    assert calls == [
        ("conversion", FootballConversionAction.EXTRA_POINT, None),
        ("card", "second"),
        ("challenge_td",),
    ]

    calls.clear()
    empty = FootballDeckState(())
    empty_match = replace(match, team_a_offense_deck=empty, team_a_defense_deck=empty)
    strip, cards, _ = draw(replace(conversion, match=empty_match, challenge_available=False))
    assert [b.label for b in strip] == ["EXTRA POINT", "2-PT · BASIC RUN"]
    strip[1].action()
    assert calls[-1] == ("conversion", FootballConversionAction.TWO_POINT, None)
    for decision, label, offensive in (
        (FootballHumanDecision.OFFENSIVE_PLAY, "FALLBACK / INSIDE RUN", True),
        (FootballHumanDecision.DEFENSIVE_SCHEME, "FALLBACK / RUN FIT", False),
    ):
        buttons = match_screen.draw(_surface(), replace(state, match=empty_match, human_decision=decision),
                                    actions, focus_index=0, hover_index=None, pressed_index=None, error=None)
        fallback = [b for b in buttons if b.variant == "hand-fallback"]
        assert [b.label for b in fallback] == [label]
        fallback[0].action()
        assert calls[-1] == ("fallback", offensive)

    calls.clear()
    strip, cards, _ = draw(replace(state, human_decision=FootballHumanDecision.CHALLENGE))
    assert [b.label for b in strip] == ["CHALLENGE", "DECLINE"]
    assert cards == []
    for button in strip:
        button.action()
    assert calls == [("challenge", True), ("challenge", False)]


def test_match_cards_support_click_drag_drop_and_reject_invalid_drops(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    desktop.router.draw(_surface())
    state = controller.state
    first_copy = state.match.team_a_offense_deck.hand[0]
    first_rect = screen.match_interaction.card_rects[first_copy.copy_id]
    unchanged = controller.state
    for event_type, pos in ((pygame.MOUSEBUTTONDOWN, first_rect.center),
                            (pygame.MOUSEMOTION, (5, 700)),
                            (pygame.MOUSEBUTTONUP, (5, 700))):
        payload = {"pos": pos, "button": 1} if event_type != pygame.MOUSEMOTION else {"pos": pos, "rel": (0, 0), "buttons": (1, 0, 0)}
        desktop.router.handle_event(pygame.event.Event(event_type, payload))
    assert controller.state == unchanged
    assert screen.last_error == "Drop the card on the field to play it."

    desktop.router.draw(_surface())
    first_rect = screen.match_interaction.card_rects[first_copy.copy_id]
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(event_type, {"pos": first_rect.center, "button": 1}))
    assert first_copy in controller.state.match.team_a_offense_deck.discard_pile

    _skip_match_playback(desktop)
    decision = controller.state.human_decision
    match = controller.state.match
    if decision is FootballHumanDecision.OFFENSIVE_PLAY:
        deck = match.team_a_offense_deck
    else:
        assert decision is FootballHumanDecision.DEFENSIVE_SCHEME
        deck = match.team_a_defense_deck
    dragged_copy = deck.hand[0]
    dragged_rect = screen.match_interaction.card_rects[dragged_copy.copy_id]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": dragged_rect.center, "button": 1}))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": FIELD_RECT.center, "rel": (0, 0), "buttons": (1, 0, 0)}))
    assert screen.match_interaction.dragging
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert "RELEASE TO PLAY" in {text for text, _, _ in records}
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": FIELD_RECT.center, "button": 1}))
    after = controller.state.match
    resulting = after.team_a_offense_deck if decision is FootballHumanDecision.OFFENSIVE_PLAY else after.team_a_defense_deck
    assert dragged_copy in resulting.discard_pile


def test_match_screen_text_fits_across_states_and_team_names(tmp_path: Path) -> None:
    for name in ("Test Owls", "Northwestern Mountain Ridgeback Thunder"):
        desktop = _new_desktop(tmp_path / name.replace(" ", "_"), team_name=name)
        _start_match(desktop)
        controller = desktop.football_controller
        screen = desktop.run_screen
        screen.match_screen.clock = lambda: 50_000
        checked = 0
        for _ in range(140):
            if controller.state.phase is not FootballRunPhase.MATCH:
                break
            with text_audit() as records:
                desktop.router.draw(_surface())
            _assert_text_fits(records)
            checked += 1
            _skip_match_playback(desktop)
            _play_human_decision(desktop)
        match = controller.state.match
        # Every recorded outcome type renders within the strip when replayed.
        for index in range(1, len(match.match_events)):
            screen.match_screen.playback.debug_show(index, 49_000)
            with text_audit() as records:
                desktop.router.draw(_surface())
            _assert_text_fits(records)
        assert checked > 20


def _set_human_offense_hand(desktop: DesktopApplication, card_ids: tuple[str, ...], *, defense_all_in_hand: bool = False) -> None:
    """Drive to a human offensive call and replace the offensive hand with ``card_ids``."""
    controller = desktop.football_controller
    for _ in range(200):
        _skip_match_playback(desktop)
        if controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            break
        _play_human_decision(desktop)
    simulator = controller._simulator
    state = simulator.state
    offense = state.team_a_offense_deck
    hand = tuple(FootballCardCopy(f"bonus-hand-{i}", card_id) for i, card_id in enumerate(card_ids))
    # Keep the play cards owned (in the draw pile) so the deck stays valid and cycles.
    replaced = FootballDeckState(offense.owned + hand, draw_pile=offense.draw_pile + offense.hand,
                                 hand=hand, discard_pile=offense.discard_pile)
    defense = state.team_a_defense_deck
    if defense_all_in_hand:
        defense = FootballDeckState(defense.owned, hand=defense.owned)
    simulator.state = replace(state, team_a_offense_deck=replaced, team_a_defense_deck=defense)
    desktop.run_screen.state = controller.state
    desktop.router.draw(_surface())


@pytest.mark.parametrize(
    ("card_ids", "defense_all_in_hand", "bonus_enabled"),
    (
        (("challenge",), False, False),
        (("defensive_draw",), True, False),
        (("offensive_draw",), False, True),
    ),
)
def test_bonus_only_offense_hand_offers_the_basic_run_fallback(
    tmp_path: Path, card_ids, defense_all_in_hand, bonus_enabled,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _set_human_offense_hand(desktop, card_ids, defense_all_in_hand=defense_all_in_hand)
    controller = desktop.football_controller
    screen = desktop.run_screen
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert not controller.state.challenge_available
    cards = [b for b in screen.buttons if b.variant == "hand-card"]
    fallback = [b for b in screen.buttons if b.variant == "hand-fallback"]
    assert [b.label for b in fallback] == ["FALLBACK / INSIDE RUN"]
    assert [b.enabled for b in cards] == [bonus_enabled]
    assert fallback[0].enabled
    assert not cards[0].rect.colliderect(fallback[0].rect)
    assert HAND_RECT.contains(fallback[0].rect)
    assert any(b.enabled and b.variant in ("hand-card", "hand-fallback") for b in screen.buttons)
    # The fallback is reachable by keyboard focus + Enter.
    before = len(controller.state.match.match_events)
    screen.focus_index = screen.buttons.index(fallback[0])
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    played = controller.state.match.match_events[before]
    assert played.action is OffensivePlayAction.RB_RUN
    assert played.card_copy_id is None
    assert screen.last_error is None


def test_bonus_only_fallback_is_a_number_key_target(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _set_human_offense_hand(desktop, ("challenge",))
    controller = desktop.football_controller
    targets = desktop.run_screen.match_screen.shortcut_targets()
    assert [b.label for b in targets] == ["FALLBACK / INSIDE RUN"]
    before = len(controller.state.match.match_events)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_1}))
    assert controller.state.match.match_events[before].action is OffensivePlayAction.RB_RUN


def test_fallback_slot_layout_fits_at_any_hand_size() -> None:
    for offense in range(0, 9):
        for defense in range(0, 7):
            off, de = layout_groups(HAND_RECT, offense, defense, {}, offense_fallback=True)
            rects = [*off.card_rects, off.fallback_slot, *de.card_rects, de.active_slot]
            assert all(HAND_RECT.contains(rect) for rect in rects), (offense, defense)
            assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])
            assert not off.area.colliderect(de.area)


def test_scoreboard_shows_conversion_wording_for_human_and_ai_tries(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    match = desktop.football_controller.state.match
    for side in (FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B):
        conversion = replace(
            match, possession=side, down=1, yards_to_go=2.0, offense_field_position=98.0,
            awaited_action=FootballAwaitedAction.CONVERSION, conversion_team=side,
            current_drive_defensive_scheme=DefensiveSchemeAction.GOAL_LINE_FRONT,
        )
        with text_audit() as records:
            draw_scoreboard(_surface(), SCOREBOARD_RECT_FOR_TESTS, conversion, desktop.run_screen.theme,
                            game_number=1, wins=0, losses=0)
        texts = [text for text, _, _ in records]
        situation = next(text for text in texts if "PAT / 2-PT TRY" in text)
        assert "1ST & GOAL" not in situation and "BALL ON" not in situation
        _assert_text_fits(records)
    # Replay snapshots of a touchdown use the same wording.
    touchdown = FootballMatchEvent(
        sequence=1, action=OffensivePlayAction.SHORT_PASS, team_a_score=6, team_b_score=0,
        possession=FootballTeamSide.TEAM_A, offense_field_position=98.0, down=1, yards_to_go=2.0,
        game_clock_seconds=800, period=1, status=FootballMatchStatus.IN_PROGRESS,
        clock_seconds_used=20, points_scored=6, scoring_team=FootballTeamSide.TEAM_A,
        play_result=FootballPlayResult(OffensivePlayAction.SHORT_PASS, 9.0, 20, points_scored=6,
                                       possession_changed=True),
    )
    later = replace(touchdown, sequence=2, action=FootballConversionAction.EXTRA_POINT,
                    play_result=None, team_a_score=7, points_scored=1,
                    offense_field_position=25.0, yards_to_go=10.0, clock_seconds_used=0,
                    possession=FootballTeamSide.TEAM_B)
    full = replace(match, match_events=(touchdown, later), team_a_score=7)
    snapshot = snapshot_state(full, 1)
    assert down_text(snapshot) == "PAT / 2-PT TRY"


def test_replay_label_counts_real_plays_and_indicator_tracks_blocking(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    screen = desktop.run_screen
    now = [100_000]
    screen.match_screen.clock = lambda: now[0]
    for _ in range(200):
        _skip_match_playback(desktop)
        state = controller.state
        before = len(state.match.match_events)
        if state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            next(b for b in screen.buttons if b.variant == "hand-card").action()
            events = controller.state.match.match_events
            new = events[before:]
            if len(new) >= 3 and isinstance(new[0].action, DefensiveSchemeAction):
                break
        else:
            _play_human_decision(desktop)
    else:
        pytest.fail("No replay starting with a scheme call was found.")
    plays = [event for event in new if is_real_play(event)]
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert screen.match_screen.playback.blocking()
    # The first replayed event is the scheme call, which is not counted as a play.
    assert f"REPLAYING · {len(plays)} PLAYS · [S] SKIP" in texts or f"REPLAYING · {len(plays)} PLAY · [S] SKIP" in texts
    assert POST_REPLAY_NOTE in texts
    assert not any(text.startswith("REPLAYING · PLAY 1 OF") and "DEFENSE" in text for text in texts)
    first_play = next(index for index, event in enumerate(new) if is_real_play(event))
    now[0] += EVENT_DURATION_MS * first_play
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert f"REPLAYING · PLAY 1 OF {len(plays)} · [S] SKIP" in texts
    assert POST_REPLAY_NOTE in texts
    assert "SKIP >>" in [b.label for b in screen.buttons]
    # The note disappears once the replay finishes on its own.
    now[0] += EVENT_DURATION_MS * len(new)
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert not screen.match_screen.playback.blocking()
    assert POST_REPLAY_NOTE not in [text for text, _, _ in records]
    assert replay_label(new, 0, 1, 1) == "REPLAYING · [S] SKIP"  # scheme-only replays


def test_only_the_first_challenge_copy_is_playable(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    copies = (FootballCardCopy("challenge-a", "challenge"), FootballCardCopy("challenge-b", "challenge"))
    deck = FootballDeckState(copies, hand=copies)
    view = replace(state, match=replace(match, team_a_offense_deck=deck), challenge_available=True)
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 0)
    buttons = match_screen.draw(_surface(), view, _recording_actions(), focus_index=0,
                                hover_index=None, pressed_index=None, error=None)
    challenges = [b for b in buttons if b.label == "CHALLENGE"]
    assert [b.enabled for b in challenges] == [True, False]


def test_hand_scrolls_once_to_reveal_a_playable_card(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    blocked = tuple(FootballCardCopy(f"c{i}", "challenge") for i in range(7))
    play = FootballCardCopy("the-play", "deep_pass")
    deck = FootballDeckState(blocked + (play,), hand=blocked + (play,))
    view = replace(state, match=replace(match, team_a_offense_deck=deck), challenge_available=False)
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 0)

    def draw():
        return match_screen.draw(_surface(), view, _recording_actions(), focus_index=0,
                                 hover_index=None, pressed_index=None, error=None)

    draw()
    assert "the-play" in match_screen.interaction.card_rects
    # A manual scroll away afterwards is respected for the rest of the decision.
    match_screen.interaction.scroll_group("offense", -10)
    draw()
    assert "the-play" not in match_screen.interaction.card_rects


def _draw_hand_capturing_art(match_screen, view, monkeypatch, *, hover_label: str | None = None):
    from src.ui import football_match_hand as hand_module

    art: list[tuple[str, pygame.Rect]] = []
    original = hand_module.draw_card_art

    def capture(surface, filename, rect):
        art.append((filename, pygame.Rect(rect)))
        return original(surface, filename, rect)

    monkeypatch.setattr(hand_module, "draw_card_art", capture)
    buttons = match_screen.draw(_surface(), view, _recording_actions(), focus_index=99,
                                hover_index=None, pressed_index=None, error=None)
    hover = None
    if hover_label is not None:
        hover = next(i for i, b in enumerate(buttons) if b.label == hover_label)
        art.clear()
    with text_audit() as records:
        buttons = match_screen.draw(_surface(), view, _recording_actions(), focus_index=99,
                                    hover_index=hover, pressed_index=None, error=None)
    return buttons, art, records


def test_offense_fallback_is_drawn_as_a_playable_run_card(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = state.match
    # Eight bonus cards force the narrowest card width, plus the fixed fallback slot.
    hand = tuple(FootballCardCopy(f"c{i}", "challenge") for i in range(8))
    view = replace(state, match=replace(match, team_a_offense_deck=FootballDeckState(hand, hand=hand)),
                   challenge_available=False)
    for hovered in (None, "FALLBACK / INSIDE RUN"):
        match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                           desktop.run_screen._label_font, clock=lambda: 0)
        buttons, art, records = _draw_hand_capturing_art(match_screen, view, monkeypatch,
                                                         hover_label=hovered)
        fallback = next(b for b in buttons if b.variant == "hand-fallback")
        assert fallback.rect.width >= 72 - 1
        assert fallback.label == "FALLBACK / INSIDE RUN"
        face = fallback.rect.move(0, -8) if hovered else fallback.rect
        assert any(name == play_card_art(FootballCardFamily.RB_RUN) and face.contains(rect)
                   for name, rect in art)
        inside = [text for text, rect, _ in records if face.contains(rect)]
        assert "INSIDE RUN" in " ".join(inside)  # may wrap at the narrowest width
        assert any(text in ("BASIC FALLBACK", "FALLBACK") for text in inside)
        assert any(text.startswith("~") for text in inside)  # live yards preview
        assert any(text.endswith("s") and text[:-1].isdigit() for text in inside)  # live clock
        assert "EMPTY HAND" not in inside and "NO PLAY CARDS" not in inside
        assert fallback not in [b for b in buttons if b.variant == "hand-card"]
        assert FALLBACK_DISPLAY_ID not in match_screen.interaction.card_rects
        _assert_text_fits(records)
    # Number keys reach it like a playable card.
    assert match_screen.shortcut_targets()[0].label == "FALLBACK / INSIDE RUN"


def test_empty_defense_hand_fallback_is_drawn_as_run_fit_card(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    match = replace(state.match, possession=FootballTeamSide.TEAM_B,
                    awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                    current_drive_defensive_scheme=None, team_a_defense_deck=FootballDeckState(()))
    view = replace(state, match=match, human_decision=FootballHumanDecision.DEFENSIVE_SCHEME)
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 0)
    buttons, art, records = _draw_hand_capturing_art(match_screen, view, monkeypatch)
    fallback = next(b for b in buttons if b.variant == "hand-fallback")
    assert fallback.label == "FALLBACK / RUN FIT"
    assert any(name == scheme_card_art(FootballCardFamily.RB_RUN) and fallback.rect.contains(rect)
               for name, rect in art)
    inside = [text for text, rect, _ in records if fallback.rect.contains(rect)]
    assert "RUN FIT" in inside and "COUNTERS" in inside and "RB RUN" in inside
    assert any(text in ("BASIC FALLBACK", "FALLBACK") for text in inside)
    _assert_text_fits(records)


def _scoring_then_kickoff(match, scoring_event):
    kickoff = FootballMatchEvent(
        sequence=scoring_event.sequence + 1, action=FootballAutomaticAction.KICKOFF,
        team_a_score=scoring_event.team_a_score, team_b_score=scoring_event.team_b_score,
        possession=FootballTeamSide.TEAM_B, offense_field_position=27.0, down=1, yards_to_go=10.0,
        game_clock_seconds=780, period=1, status=FootballMatchStatus.IN_PROGRESS,
        clock_seconds_used=10, gross_yards=65.0, return_yards=27.0,
        description="Kickoff returned 27.0 yards",
    )
    scheme = FootballMatchEvent(
        sequence=scoring_event.sequence + 2, action=DefensiveSchemeAction.RB_RUN,
        team_a_score=scoring_event.team_a_score, team_b_score=scoring_event.team_b_score,
        possession=FootballTeamSide.TEAM_B, offense_field_position=27.0, down=1, yards_to_go=10.0,
        game_clock_seconds=780, period=1, status=FootballMatchStatus.IN_PROGRESS,
    )
    events = (scoring_event, kickoff, scheme)
    return replace(match, match_events=events, team_a_score=scoring_event.team_a_score,
                   team_b_score=scoring_event.team_b_score)


def _placeholder(sequence, action, points, *, play_result=None, scoring=FootballTeamSide.TEAM_A, **fields):
    return FootballMatchEvent(
        sequence=sequence, action=action, team_a_score=points if scoring is FootballTeamSide.TEAM_A else 0,
        team_b_score=points if scoring is FootballTeamSide.TEAM_B else 0,
        possession=FootballTeamSide.TEAM_B, offense_field_position=25.0, down=1, yards_to_go=10.0,
        game_clock_seconds=790, period=1, status=FootballMatchStatus.IN_PROGRESS,
        points_scored=points, scoring_team=scoring, play_result=play_result,
        clock_seconds_used=play_result.clock_seconds_used if play_result else fields.pop("clock_seconds_used", 0),
        **fields,
    )


def test_scores_followed_by_a_kickoff_show_kickoff_pending_not_a_placeholder_drive(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    match = desktop.football_controller.state.match
    theme = desktop.run_screen.theme
    safety_result = FootballPlayResult(OffensivePlayAction.RB_RUN, -3.0, 20, points_scored=2,
                                       possession_changed=True)
    scoring_events = {
        "extra point": _placeholder(1, FootballConversionAction.EXTRA_POINT, 1, description="Extra point good"),
        "two point": _placeholder(1, FootballConversionAction.TWO_POINT, 2, card_id="rb_run",
                                  gross_yards=3.0, description="Two-point rb run successful"),
        "field goal": _placeholder(1, FootballFourthDownAction.FIELD_GOAL, 3, field_goal_distance=30.0,
                                   description="Field goal good from 30 yards", clock_seconds_used=5),
        # Team B is tackled in its own end zone; Team A scores and Team B kicks.
        "safety": replace(_placeholder(1, OffensivePlayAction.RB_RUN, 2, play_result=safety_result),
                          possession=FootballTeamSide.TEAM_A),
    }
    for name, scoring in scoring_events.items():
        full = _scoring_then_kickoff(match, scoring)
        kicking = kickoff_pending(full, 1)
        assert kicking is FootballTeamSide.TEAM_A, name
        snapshot = snapshot_state(full, 1)
        assert snapshot.possession is FootballTeamSide.TEAM_A
        assert (snapshot.team_a_score, snapshot.team_b_score) == (scoring.team_a_score, scoring.team_b_score)
        with text_audit() as records:
            draw_scoreboard(_surface(), SCOREBOARD_RECT_FOR_TESTS, snapshot, theme,
                            game_number=1, wins=0, losses=0, kickoff_next=True)
            draw_match_field(_surface(), FIELD_RECT, snapshot, theme.primary, FieldOverlay(),
                             human_scheme_highlight=True, kickoff_pending=True)
        texts = [text for text, _, _ in records]
        situation = next(text for text in texts if "KICKOFF NEXT" in text)
        assert situation.endswith(f"{match.team_a.team_name.upper()} KICKS"), name
        assert not any("& 10" in text or "BALL ON" in text for text in texts), (name, texts)
        _assert_text_fits(records)
        # The kickoff's own snapshot shows the receiving team's real drive.
        kickoff_view = snapshot_state(full, 2)
        assert kickoff_pending(full, 2) is None
        assert kickoff_view.possession is FootballTeamSide.TEAM_B
        assert down_text(kickoff_view) == "1ST & 10"
        assert ball_spot_text(kickoff_view) == "BALL ON OWN 27"
    # The last recorded event (no kickoff follows) keeps the normal display.
    assert kickoff_pending(_scoring_then_kickoff(match, scoring_events["field goal"]), 3) is None


def test_match_screen_uses_kickoff_pending_during_replay_and_keeps_conversion_text(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    state = desktop.football_controller.state
    full = _scoring_then_kickoff(state.match, _placeholder(
        1, FootballConversionAction.EXTRA_POINT, 1, description="Extra point good"))
    view = replace(state, match=full, human_decision=None)
    match_screen = FootballMatchScreen(desktop.run_screen.theme, desktop.run_screen._small_font,
                                       desktop.run_screen._label_font, clock=lambda: 10_000)
    match_screen.draw(_surface(), view, _recording_actions(), focus_index=0, hover_index=None,
                      pressed_index=None, error=None)
    match_screen.playback.debug_show(0, 9_500)
    with text_audit() as records:
        match_screen.draw(_surface(), view, _recording_actions(), focus_index=0, hover_index=None,
                          pressed_index=None, error=None)
    texts = [text for text, _, _ in records]
    assert any("KICKOFF NEXT" in text for text in texts)
    assert not any("1ST & 10" in text for text in texts)
    # A real conversion decision is unaffected.
    conversion = replace(state.match, down=1, yards_to_go=2.0, offense_field_position=98.0,
                         awaited_action=FootballAwaitedAction.CONVERSION,
                         conversion_team=FootballTeamSide.TEAM_A,
                         current_drive_defensive_scheme=DefensiveSchemeAction.GOAL_LINE_FRONT)
    with text_audit() as records:
        match_screen.draw(_surface(), replace(state, match=conversion,
                                              human_decision=FootballHumanDecision.CONVERSION),
                          _recording_actions(), focus_index=0, hover_index=None,
                          pressed_index=None, error=None)
    texts = [text for text, _, _ in records]
    assert any("PAT / 2-PT TRY" in text for text in texts)
    assert not any("KICKOFF NEXT" in text for text in texts)
