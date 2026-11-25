from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football import (
    FootballPerkDecision,
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
from src.engine.football_shop import (
    COACH_UPGRADE_CATALOG,
    PLAYER_UPGRADE_CATALOG,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballUpgradeDuration,
    FootballUpgradeStat,
    _player_upgrade_catalog,
)
from src.ui.application import DesktopApplication
from src.ui import football_run_screen as football_run_screen_module
from src.ui.football_display import _PLAY_LABELS
from src.ui import football_review_view as football_review_module
from src.ui import football_depth_chart as football_depth_module
from src.ui.football_card_art import (
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
from src.ui.football_player_perks import partner_tag, perk_card_line, perk_rules
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
                {"pos": button.hit_rect.center, "button": 1},
            )
        )
        desktop.router.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONUP,
                {"pos": button.hit_rect.center, "button": 1},
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
            "challenge_touchdown", "return_to_menu", "quit_run",
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


def _draft_texts(desktop, canvas=None) -> list[tuple[str, pygame.Rect, pygame.Rect]]:
    with text_audit() as records:
        desktop.router.draw(canvas or _surface())
    return list(records)


def test_draft_cards_show_complete_actual_catalog_data(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    screen = desktop.run_screen
    state = screen.state
    assert state is not None
    for types in PLAYER_TYPES_BY_POSITION.values():
        for player_type in types:
            player = replace(player_from_type(player_type), power=63.25,
                             volatility=0.125, stamina=0.735)
            candidate = FootballPlayerCandidate(player, "test")
            screen.state = replace(state, team_builder=replace(
                state.team_builder, current_offer=(candidate, candidate, candidate)))
            records = _draft_texts(desktop)
            for index in range(3):
                card = screen.player_inspection.card_rects[index]
                button = screen.buttons[index].rect
                inside = [(text, rect) for text, rect, _ in records if card.contains(rect)]
                texts = [text for text, _ in inside]
                assert player_type.name in texts
                perk_lines = [text for text, rect in inside
                              if rect.top >= card.top + 364 and not rect.colliderect(button)]
                assert all(not rect.colliderect(button) for text, rect in inside
                           if text in perk_lines)
                joined = " ".join(perk_lines)
                if player_type.perk is None:
                    assert "Perk: None" in joined
                else:
                    assert "PLANNED" not in joined and "INACTIVE" not in joined
                    assert player_type.perk.name.upper() in joined
                    rules = " ".join(perk_rules(player_type.perk).split())
                    assert perk_card_line(player_type.perk) in joined
                    words = joined.split()
                    assert " ".join(words[-len(rules.split()):]) == rules
                    tag = partner_tag(player_type.perk)
                    assert (tag in joined) if tag else "WITH " not in joined


def test_draft_card_stats_and_partners_are_visible_without_interaction(tmp_path: Path) -> None:
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
    records = _draft_texts(desktop)
    for index, candidate in enumerate(changed):
        rect = screen.player_inspection.card_rects[index]
        card_text = [(text, drawn) for text, drawn, _ in records if rect.contains(drawn)]
        texts = [text for text, _ in card_text]
        player_type = player_type_for_id(candidate.player.player_type_id)
        if player_type.partner_position is None:
            assert football_player_draft_module.NO_PARTNER in texts
        else:
            assert "PARTNER" in texts
            assert football_player_draft_module._draft_position_label(player_type.partner_position) in texts
            assert football_player_draft_module.PARTNER_EXPLANATION in texts
        assert f"{candidate.player.power:g}" in texts
        assert football_player_draft_module._draft_percentage(candidate.player.volatility) in texts
        assert football_player_draft_module._draft_percentage(candidate.player.stamina) in texts
        labels = [drawn for text, drawn in card_text if text in ("POWER", "VOLATILITY", "STAMINA")]
        assert len(labels) == 3
        assert all(not first.colliderect(second) for i, first in enumerate(labels) for second in labels[i + 1:])


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
    accent = football_player_draft_module.team_accent(desktop.theme.primary)
    assert canvas.get_at((button.rect.centerx, button.rect.top + 5)) == accent
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
    button = screen.buttons[1].rect
    accent = football_player_draft_module.team_accent(desktop.theme.primary)
    assert canvas.get_at((button.centerx, button.top + 5)) == accent
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


def test_draft_progress_uses_selected_players_and_selection_actions(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen
    chosen = []
    appearances = {}
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        records = _draft_texts(desktop)
        rows = football_player_draft_module.tracker_row_rects()
        displayed = [text for text, _, _ in records]
        assert displayed.count("CURRENT PICK") == 1
        assert displayed.count("UP NEXT") == len(PLAYER_DRAFT_ORDER) - index - 1
        for row_index, row_position in enumerate(PLAYER_DRAFT_ORDER):
            row_texts = [text for text, drawn, _ in records if rows[row_position].contains(drawn)]
            if row_index < index:
                assert any(text.startswith(chosen[row_index][:3]) for text in row_texts)
                assert any(text.startswith("PWR ") for text in row_texts)
            elif row_index == index:
                assert "CURRENT PICK" in row_texts
            else:
                assert "UP NEXT" in row_texts
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
    records = _draft_texts(desktop)
    banner = [(rect, container) for text, rect, container in records if text == "CHECK: Draft rejected."]
    assert banner and all(container.contains(rect) for rect, container in banner)
    assert all(container == football_run_screen_module.COACH_ERROR_RECT for _, container in banner)
    cards = screen.player_inspection.card_rects
    assert all(not rect.colliderect(card) for rect, _ in banner for card in cards)


def test_coach_selection_error_preserves_offer_and_is_displayed(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state

    def reject_choice(_choice):
        raise ValueError("Staff could not be chosen.")

    monkeypatch.setattr(controller, "choose_coach", reject_choice)
    _activate(desktop, "CHOOSE STAFF 02")
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert controller.state == before
    assert desktop.run_screen.last_error == "Staff could not be chosen."
    banner = [(rect, container) for text, rect, container in records
              if text == "CHECK: Staff could not be chosen."]
    assert banner and all(container.contains(rect) for rect, container in banner)
    cards = desktop.run_screen.coach_inspection.card_rects
    assert all(not rect.colliderect(card) for rect, _ in banner for card in cards)


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
    assert screen.pause.is_open
    _activate(desktop, "KEEP PLAYING")
    assert not screen.pause.is_open
    assert first_controller.state == before
    _activate(desktop, "CHOOSE STAFF 02", keyboard=True)
    assert first_controller.state.selected_coach_pair is before.team_builder.coach_offer[1]
    assert first_controller.state.phase is FootballRunPhase.PLAYER_DRAFT

    _activate(desktop, "PAUSE")
    _activate(desktop, "QUIT RUN")
    _activate(desktop, "CONFIRM QUIT")
    assert desktop.router.current_id == "main_menu"
    desktop.save_profile("Fresh Coaches", "crimson", "gold")
    _start_run(desktop)
    with text_audit() as records:
        desktop.router.draw(_surface())
    assert "FRESH COACHES" in [text for text, _rect, _container in records]
    assert desktop.football_controller is not first_controller
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert screen.coach_inspection.hover_index is None
    assert not screen.coach_inspection.window_left
    assert screen._coach_view().theme == desktop.theme


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


def _coach_card_effect(card_id: str):
    card = next(card for card in COACH_UPGRADE_CATALOG if card.card_id == card_id)
    assert card.coach_upgrade_effect is not None
    return card.coach_upgrade_effect


def test_supported_desktop_layout_renders_the_actual_shop(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)

    desktop.router.draw(_surface())

    assert desktop.run_screen._current_state().shop is not None
    assert any(button.variant == "shop-card" and button.purchasable for button in desktop.run_screen.buttons)


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
            FootballRunPhase.READY_FOR_NEXT_GAME,
            "VIEW PLAYOFF BRACKET",
        ),
    ),
)
def test_result_routes_fired_and_game_ten_to_the_playoffs(
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
            _activate(desktop, "OPEN NEXT WEEK SHOP")
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


def _win_to_the_playoffs(desktop: DesktopApplication, monkeypatch) -> None:
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    for game_number in range(1, 11):
        _play_first_match_card(desktop)
        if game_number < 10:
            _activate(desktop, "OPEN NEXT WEEK SHOP")
            _activate(desktop, "FINISH SHOP / START MATCH")


def test_playoff_bracket_leads_each_round_to_its_shop_and_the_title_returns_to_menu(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _win_to_the_playoffs(desktop, monkeypatch)
    controller = desktop.football_controller
    assert controller is not None
    for game_number, shop_label in (
        (11, "OPEN QUARTERFINAL SHOP"),
        (12, "OPEN SEMIFINAL SHOP"),
        (13, "OPEN CHAMPIONSHIP SHOP"),
    ):
        _activate(desktop, "VIEW PLAYOFF BRACKET", keyboard=True)
        assert desktop.run_screen.bracket_open
        # Esc pauses the bracket like any unfinished run screen.
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        assert desktop.run_screen.pause.is_open
        _activate(desktop, "KEEP PLAYING")
        _activate(desktop, shop_label, keyboard=True)
        assert not desktop.run_screen.bracket_open
        state = controller.state
        assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
        assert state.game_number == game_number
        _activate(desktop, "FINISH SHOP / START MATCH")
        _play_first_match_card(desktop)

    assert controller.state.phase is FootballRunPhase.CHAMPION
    desktop.router.draw(_surface())
    labels = [button.label for button in desktop.run_screen.buttons]
    assert labels == ["RETURN TO MAIN MENU", "VIEW BRACKET"]
    assert not desktop.run_screen.resumable
    _activate(desktop, "VIEW BRACKET")
    desktop.router.draw(_surface())
    assert [button.label for button in desktop.run_screen.buttons] == ["RETURN TO MAIN MENU"]
    # Esc on an ended run's bracket goes back to its result.
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert not desktop.run_screen.bracket_open
    _activate(desktop, "RETURN TO MAIN MENU")
    assert desktop.router.current is not desktop.run_screen
    assert desktop.football_controller is None


def test_a_playoff_loss_ends_the_run_as_eliminated(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _win_to_the_playoffs(desktop, monkeypatch)
    _activate(desktop, "VIEW PLAYOFF BRACKET")
    _activate(desktop, "OPEN QUARTERFINAL SHOP")
    _activate(desktop, "FINISH SHOP / START MATCH")
    _force_result(monkeypatch, FootballTeamSide.TEAM_B)
    _play_first_match_card(desktop)
    controller = desktop.football_controller
    assert controller is not None and controller.state.phase is FootballRunPhase.ELIMINATED
    desktop.router.draw(_surface())
    assert [button.label for button in desktop.run_screen.buttons] == [
        "RETURN TO MAIN MENU", "VIEW BRACKET",
    ]


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
    _activate(desktop, "OPEN NEXT WEEK SHOP", keyboard=True)
    assert controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert controller.state.shop is not None
    assert controller.state.shop.remaining_ap == 12
    _activate(desktop, "FINISH SHOP / START MATCH")
    assert controller.state.phase is FootballRunPhase.MATCH
    assert controller.state.game_number == 2
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY


def test_result_screen_is_full_screen_with_focused_primary_and_end_run(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    _play_first_match_card(desktop)
    screen = desktop.run_screen
    screen._result_view.clock = None
    with text_audit() as records:
        desktop.router.draw(_surface())
    texts = [text for text, _, _ in records]
    assert "WEEK 01" in texts and "WIN" in texts and "TEAM STATS" in texts
    assert [button.label for button in screen.buttons] == ["OPEN NEXT WEEK SHOP", "PAUSE"]
    assert screen.buttons[0].focused

    next(button for button in screen.buttons if button.label == "PAUSE").action()
    desktop.router.draw(_surface())
    assert screen.pause.is_open
    assert [button.label for button in screen.buttons] == ["KEEP PLAYING", "RETURN TO MENU", "QUIT RUN"]
    _activate(desktop, "KEEP PLAYING")
    assert not screen.pause.is_open

    desktop.router.draw(_surface())
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert desktop.football_controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP


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
            _activate(desktop, "OPEN NEXT WEEK SHOP")
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
    assert not desktop.run_screen.pause.is_open
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
    records = _draft_texts(desktop)
    assert desktop.run_screen.last_error is not None
    assert desktop.run_screen.state == before
    assert any(text == f"CHECK: {desktop.run_screen.last_error}" for text, _, _ in records)


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


def test_escape_opens_the_pause_menu_with_keep_playing_focused(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
    )
    assert desktop.router.current_id == "football_run"
    desktop.router.draw(_surface())
    assert [button.label for button in screen.buttons] == [
        "KEEP PLAYING", "RETURN TO MENU", "QUIT RUN",
    ]
    assert screen.buttons[0].focused

    _activate(desktop, "KEEP PLAYING")
    assert desktop.router.current_id == "football_run"
    assert not screen.pause.is_open


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


def test_pause_menu_opens_depth_chart_and_play_log_and_quit_needs_confirmation(
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
        "KEEP PLAYING", "DEPTH CHART", "PLAY LOG", "RETURN TO MENU", "QUIT RUN",
    ]
    assert screen.buttons[0].focused
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
    _activate(desktop, "KEEP PLAYING")
    assert not screen.match_screen.popup.open
    _activate(desktop, "PAUSE")
    assert screen.match_screen.popup.kind == "pause"
    _activate(desktop, "QUIT RUN")
    desktop.router.draw(_surface())
    assert screen.buttons[-1].label == "CONFIRM QUIT"
    desktop.router.handle_event(escape)
    assert screen.match_screen.popup.kind == "pause"
    desktop.router.draw(_surface())
    assert screen.buttons[-1].label == "QUIT RUN"
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
    _activate(desktop, "START NEW RUN")
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
    rival = controller.state.regular_season_teams[0]
    assert initial.team_b.team_name == rival.name
    # The schedule never draws a rival wearing the profile's primary color.
    primary = desktop.menu_state.profile.primary_color_id
    assert all(team.primary_color_id != primary for team in controller.state.regular_season_teams)

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
        elif state.human_decision is FootballHumanDecision.GREEN_DOG:
            # Keep is the first strip button; every hand scheme is also selectable.
            deck = state.match.team_a_defense_deck
            assert list(strip)[0].startswith("KEEP ")
            assert len(hand_buttons) == len(deck.hand)
            if hand_buttons:
                expected_copy_id = deck.hand[0].copy_id
                expected = FootballPerkDecision.GREEN_DOG_SWAP
                hand_buttons[0].action()
            else:
                expected = FootballPerkDecision.GREEN_DOG_DECLINE
                list(strip.values())[0].action()
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
        FootballRunPhase.READY_FOR_NEXT_GAME, FootballRunPhase.FIRED,
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
        button.label in {"OPEN NEXT WEEK SHOP", "RETURN TO MAIN MENU"}
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


_BIG_PLAY_IDS = tuple(list(OFFENSIVE_PLAY_CATALOG)[::6][:6] + list(OFFENSIVE_PLAY_CATALOG)[1::6])[:9]
_BIG_SCHEME_IDS = tuple(list(DEFENSIVE_SCHEME_CATALOG)[::4] + list(DEFENSIVE_SCHEME_CATALOG)[1::4])


def _drive_to_decision(desktop: DesktopApplication, decision: FootballHumanDecision) -> None:
    controller = desktop.football_controller
    for _ in range(400):
        _skip_match_playback(desktop)
        if controller.state.human_decision is decision:
            return
        _play_human_decision(desktop)
    raise AssertionError(f"never reached {decision}")


def _set_human_hands(
    desktop: DesktopApplication, offense_ids: tuple[str, ...], defense_ids: tuple[str, ...]
) -> None:
    """Replace both human hands with enlarged ones; prior hand cards move to draw."""
    simulator = desktop.football_controller._simulator
    state = simulator.state
    offense, defense = state.team_a_offense_deck, state.team_a_defense_deck
    offense_hand = tuple(FootballCardCopy(f"big-o-{i}", cid) for i, cid in enumerate(offense_ids))
    defense_hand = tuple(FootballCardCopy(f"big-d-{i}", cid) for i, cid in enumerate(defense_ids))
    simulator.state = replace(
        state,
        team_a_offense_deck=FootballDeckState(
            offense.owned + offense_hand, draw_pile=offense.draw_pile + offense.hand,
            hand=offense_hand, discard_pile=offense.discard_pile,
        ),
        team_a_defense_deck=FootballDeckState(
            defense.owned + defense_hand, draw_pile=defense.draw_pile + defense.hand,
            hand=defense_hand, discard_pile=defense.discard_pile,
        ),
    )
    desktop.run_screen.state = desktop.football_controller.state
    desktop.run_screen.match_screen.interaction.auto_scroll_key = None


def _assert_large_hand_frame(desktop: DesktopApplication) -> None:
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    buttons = desktop.run_screen.buttons
    hand = [b for b in buttons if b.variant in ("hand-card", "hand-fallback")]
    scroll = [b for b in buttons if b.variant == "hand-scroll"]
    for button in hand + scroll:
        assert HAND_RECT.contains(button.rect), button.label
        for other in (LEFT_PILES_RECT, RIGHT_PILES_RECT, STRIP_RECT):
            assert not button.rect.colliderect(other), button.label
    for index, button in enumerate(hand):
        assert button.rect.width >= 72
        for other in hand[index + 1:] + scroll:
            assert not button.rect.colliderect(other.rect), (button.label, other.label)


@pytest.mark.parametrize(
    ("decision", "offense_count", "defense_count"),
    [
        (FootballHumanDecision.OFFENSIVE_PLAY, offense, defense)
        for offense, defense in ((4, 3), (5, 4), (6, 4), (7, 4), (7, 5))
    ] + [(FootballHumanDecision.DEFENSIVE_SCHEME, 7, 5), (FootballHumanDecision.DEFENSIVE_SCHEME, 4, 3)],
)
def test_enlarged_hands_fit_the_match_screen_without_overlap(
    tmp_path: Path, decision, offense_count, defense_count
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to_decision(desktop, decision)
    _set_human_hands(desktop, _BIG_PLAY_IDS[:offense_count], _BIG_SCHEME_IDS[:defense_count])
    _assert_large_hand_frame(desktop)
    match_screen = desktop.run_screen.match_screen
    off, de = layout_groups(HAND_RECT, offense_count, defense_count, {})
    active_before = de.active_slot
    scrolls = {b.label for b in desktop.run_screen.buttons if b.variant == "hand-scroll"}
    if off.max_scroll:
        assert {"SCROLL OFFENSE LEFT", "SCROLL OFFENSE RIGHT"} <= scrolls
    if de.max_scroll:
        assert {"SCROLL DEFENSE LEFT", "SCROLL DEFENSE RIGHT"} <= scrolls
    # Scrolling never moves the fixed ACTIVE scheme slot.
    for group in ("offense", "defense"):
        match_screen.interaction.scroll_group(group, 10)
    _assert_large_hand_frame(desktop)
    _, scrolled_defense = layout_groups(HAND_RECT, offense_count, defense_count,
                                        match_screen.interaction.group_scroll)
    assert scrolled_defense.active_slot == active_before


def test_enlarged_bonus_only_hand_keeps_the_fallback_slot_in_view(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to_decision(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_human_hands(
        desktop,
        ("offensive_draw", "defensive_draw", "opponent_discard", "challenge", "offensive_draw_discard"),
        _BIG_SCHEME_IDS[:4],
    )
    _assert_large_hand_frame(desktop)
    match_screen = desktop.run_screen.match_screen
    match_screen.interaction.scroll_group("offense", 10)
    _assert_large_hand_frame(desktop)
    fallback = [b for b in desktop.run_screen.buttons if b.variant == "hand-fallback"]
    assert [b.label for b in fallback] == ["FALLBACK / INSIDE RUN"]
    assert fallback[0] in match_screen.shortcut_targets()


@pytest.mark.parametrize(
    ("decision", "group", "count"),
    [
        (FootballHumanDecision.OFFENSIVE_PLAY, "OFFENSE", 7),
        (FootballHumanDecision.DEFENSIVE_SCHEME, "DEFENSE", 5),
    ],
)
def test_keyboard_scrolling_and_number_keys_reach_every_enlarged_hand_card(
    tmp_path: Path, decision, group, count
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to_decision(desktop, decision)
    _set_human_hands(desktop, _BIG_PLAY_IDS[:7], _BIG_SCHEME_IDS[:5])
    screen = desktop.run_screen
    match_screen = screen.match_screen
    reached: set[str] = set()
    for _ in range(count + 2):
        desktop.router.draw(_surface())
        targets = match_screen.shortcut_targets()
        cards = [b for b in targets if b.variant == "hand-card"]
        assert 0 < len(cards) <= 9
        reached.update(match_screen.interaction.card_rects)
        scroll_right = next(
            b for b in screen.buttons if b.label == f"SCROLL {group} RIGHT"
        )
        if not scroll_right.enabled:
            break
        screen.focus_index = screen.buttons.index(scroll_right)
        desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    prefix = "big-o-" if group == "OFFENSE" else "big-d-"
    assert {copy_id for copy_id in reached if copy_id.startswith(prefix)} == {
        f"{prefix}{index}" for index in range(count)
    }
    # The last number key in view plays the last card in the hand.
    desktop.router.draw(_surface())
    before = len(desktop.football_controller.state.match.match_events)
    key = pygame.K_1 + len(match_screen.shortcut_targets()) - 1
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key}))
    played = desktop.football_controller.state.match.match_events[before]
    assert played.card_copy_id == f"{prefix}{count - 1}"


def test_offensive_draw_from_the_hand_grows_hand_and_keeps_pile_counts(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _drive_to_decision(desktop, FootballHumanDecision.OFFENSIVE_PLAY)
    _set_human_hands(desktop, ("offensive_draw",) + _BIG_PLAY_IDS[:2], _BIG_SCHEME_IDS[:2])
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    match_before = desktop.football_controller.state.match
    bonus = next(b for b in screen.buttons if b.label == "OFFENSIVE DRAW")
    bonus.action()
    _skip_match_playback(desktop)
    match = desktop.football_controller.state.match
    offense = match.team_a_offense_deck
    assert len(offense.hand) == 4
    assert offense.discard_pile[-1].copy_id == "big-o-0"
    counts = pile_counts(offense)
    assert counts.hand + counts.draw + counts.discard == counts.owned
    assert counts.draw == len(match_before.team_a_offense_deck.draw_pile) - 2
    assert pile_counts(match.team_a_defense_deck).hand == 2
    # Replaying up to the bonus event shows the post-draw decks, not stale ones.
    display = snapshot_state(match, len(match.match_events))
    assert display.team_a_offense_deck == offense
    with text_audit() as records:
        desktop.router.draw(_surface())
    _assert_text_fits(records)
    assert len([b for b in screen.buttons if b.variant == "hand-card"]) == 4
