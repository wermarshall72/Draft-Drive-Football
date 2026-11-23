from dataclasses import replace

import pygame
import pytest

from src.engine.football_coaches import COACH_PAIR_OFFERS
from src.engine.football_controller import FootballRunPhase
from src.ui import coach_art, football_coach_view
from src.ui.text import wrap_text_lines
from src.ui.theme import readable_ink, relative_luminance
from scripts.process_coach_portraits import GRASS_TOP, is_background
from test_football_desktop import _new_desktop, _start_run, _surface


EXPECTED_PORTRAITS = {
    "ground_and_pound": "ground_and_pound", "option_spread": "option_spread",
    "air_raid": "air_raid", "pro_style": "pro_style", "run_stop": "run_stop",
    "pressure_blitz": "pressure_blitz", "coverage": "coverage", "ball_hawk": "ball_hawk",
    "balanced_offense": "balanced", "balanced_defense": "balanced",
}


def test_portrait_mapping_assets_and_color_isolation():
    assert coach_art.COACH_PORTRAITS == EXPECTED_PORTRAITS
    for coach_id in EXPECTED_PORTRAITS:
        base, mask = coach_art.coach_portrait_layers(coach_id)
        assert base.get_size() == mask.get_size()
        assert base.get_at((0, 0)).a == mask.get_at((0, 0)).a == 0
        assert mask.get_bounding_rect().width > 0
        red = coach_art._colored_coach(coach_id, (230, 25, 30))
        blue = coach_art._colored_coach(coach_id, (20, 50, 220))
        changed = unchanged = 0
        for y in range(0, base.get_height(), 3):
            for x in range(0, base.get_width(), 3):
                if mask.get_at((x, y)).a:
                    changed += red.get_at((x, y)) != blue.get_at((x, y))
                elif base.get_at((x, y)).a:
                    assert red.get_at((x, y)) == blue.get_at((x, y)) == base.get_at((x, y))
                    unchanged += 1
        assert changed > 100 and unchanged > 100
    assert coach_art.coach_portrait_layers("balanced_offense")[0].get_size() == (
        coach_art.coach_portrait_layers("balanced_defense")[0].get_size()
    )
    assert pygame.image.tobytes(coach_art.coach_portrait_layers("balanced_offense")[0], "RGBA") == (
        pygame.image.tobytes(coach_art.coach_portrait_layers("balanced_defense")[0], "RGBA")
    )


@pytest.mark.parametrize("coach_id", EXPECTED_PORTRAITS)
def test_coach_portraits_have_clean_edges_and_connected_details(coach_id):
    base, clothing = coach_art.coach_portrait_layers(coach_id)
    combined = base.copy()
    combined.blit(clothing, (0, 0))
    components = pygame.mask.from_surface(combined).connected_components()
    assert len(components) == 1
    for y in range(combined.get_height() * 7 // 10):
        for x in range(combined.get_width()):
            r, g, b, alpha = base.get_at((x, y))
            assert not (alpha and g > 12 and g > r * 2 and g > b * 2)


@pytest.mark.parametrize("name", GRASS_TOP)
def test_coach_green_key_preserves_dark_grass(name):
    assert is_background(3, 80, 3, GRASS_TOP[name] - 1, name)
    assert not is_background(3, 80, 3, GRASS_TOP[name], name)
    assert not is_background(8, 8, 8, GRASS_TOP[name] - 1, name)


def test_blitz_headset_boom_remains_opaque_without_green_spill():
    base, _ = coach_art.coach_portrait_layers("pressure_blitz")
    for position in ((289, 89), (295, 95), (296, 99)):
        pixel = base.get_at(position)
        assert pixel.a == 255 and max(pixel[:3]) <= 12


def test_missing_portrait_fails_instead_of_showing_another_coach(tmp_path, monkeypatch):
    coach_art.coach_portrait_layers.cache_clear()
    monkeypatch.setattr(coach_art, "_COACH_DIR", tmp_path)
    with pytest.raises((FileNotFoundError, pygame.error)):
        coach_art.coach_portrait_layers("ground_and_pound")
    coach_art.coach_portrait_layers.cache_clear()


@pytest.mark.parametrize("pair", COACH_PAIR_OFFERS)
def test_every_pair_renders_complete_inline_data(tmp_path, monkeypatch, pair):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    state = desktop.football_controller.state
    state = replace(state, team_builder=replace(state.team_builder, coach_offer=(pair,) * 3))
    view = desktop.run_screen._coach_view()
    texts = []
    portraits = []
    original_text = football_coach_view.draw_text
    original_wrapped = football_coach_view.draw_complete_wrapped_text

    def capture(surface, text, position, font, color):
        texts.append((text, pygame.Color(color)))
        return original_text(surface, text, position, font, color)

    def wrapped(surface, text, rect, font, color, **kwargs):
        texts.append((text, pygame.Color(color)))
        lines = wrap_text_lines(text, font, rect.width)
        assert len(lines) * font.get_height() + max(0, len(lines) - 1) * kwargs.get("line_gap", 2) <= rect.height
        return original_wrapped(surface, text, rect, font, color, **kwargs)

    def portrait(surface, rect, coach_id, primary):
        portraits.append(coach_id)
        return coach_art.draw_coach_portrait(surface, rect, coach_id, primary)

    monkeypatch.setattr(football_coach_view, "draw_text", capture)
    monkeypatch.setattr(football_coach_view, "draw_complete_wrapped_text", wrapped)
    monkeypatch.setattr(football_coach_view, "draw_coach_portrait", portrait)
    buttons = view.draw(_surface(), pygame.Rect(38, 122, 1204, 558), state)
    assert portraits == [pair.offense.coach_id, pair.defense.coach_id] * 3
    assert all(not a.rect.colliderect(b.rect) for a, b in zip(buttons, buttons[1:]))
    for coach in (pair.offense, pair.defense):
        assert sum(text == coach.name for text, _ in texts) == 3
        summary = f"{coach.side.value.title()}: {football_coach_view.coach_perk_text(coach)}"
        assert sum(text == summary for text, _ in texts) == 3
        if coach.perk is None:
            assert "No perk." in summary
        for position, modifier in coach.position_modifiers.items():
            label = f"{football_coach_view._coach_position_label(position)} {round(modifier * 100):+d}%"
            color = (football_coach_view._POSITIVE if modifier > 0 else
                     football_coach_view._NEGATIVE if modifier < 0 else football_coach_view._NEUTRAL)
            assert (label, color) in texts


@pytest.mark.parametrize("window_size", [(1280, 720), (960, 540), (1024, 768)])
@pytest.mark.parametrize("index", range(3))
def test_scaled_pointer_and_batched_selection(tmp_path, window_size, index):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.window_size = window_size
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    before = desktop.football_controller.state
    scale = min(window_size[0] / 1280, window_size[1] / 720)
    offset = ((window_size[0] - round(1280 * scale)) // 2,
              (window_size[1] - round(720 * scale)) // 2)

    def send(kind, pos, **kw):
        physical = tuple(round(offset[i] + pos[i] * scale) for i in range(2))
        desktop.router.handle_event(desktop._logical_event(
            pygame.event.Event(kind, {"pos": physical, **kw})))

    card = screen.coach_inspection.card_rects[index]
    send(pygame.MOUSEMOTION, (card.centerx, card.top + 55))
    assert screen.coach_inspection.active_index(screen.focus_index) == index
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        send(kind, (card.centerx, card.top + 55), button=1)
    assert desktop.football_controller.state == before
    button = screen.buttons[index]
    send(pygame.MOUSEBUTTONDOWN, button.rect.center, button=1)
    desktop.router.draw(_surface())
    send(pygame.MOUSEBUTTONUP, button.rect.center, button=1)
    assert desktop.football_controller.state.selected_coach_pair is before.team_builder.coach_offer[index]
    assert desktop.football_controller.state.phase is FootballRunPhase.PLAYER_DRAFT
    send(pygame.MOUSEBUTTONDOWN, button.rect.center, button=1)
    send(pygame.MOUSEBUTTONUP, button.rect.center, button=1)
    assert not desktop.football_controller.state.team_builder.selected_players


def test_keyboard_window_leave_and_confirmation_batch(tmp_path):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    button = screen.buttons[1]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=button.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=button.rect.center, button=1))
    assert screen.coach_inspection.hover_index is None and screen.pressed_index is None
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    screen._focus(0)
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    assert screen.coach_inspection.active_index(screen.focus_index) == 1
    desktop.router.draw(_surface())
    expected = desktop.football_controller.state.team_builder.coach_offer[1]
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert desktop.football_controller.state.selected_coach_pair is expected


def test_cancelled_drag_and_exit_confirmation_block_stale_buttons(tmp_path):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    before = desktop.football_controller.state
    first, second = screen.buttons[:2]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=first.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=second.rect.center))
    assert screen.coach_inspection.active_index(screen.focus_index) == 1
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=second.rect.center, button=1))
    assert desktop.football_controller.state == before
    exit_button = screen.buttons[-1]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=exit_button.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=exit_button.rect.center, button=1))
    assert screen.pause.is_open
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=first.rect.center, button=1))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=first.rect.center, button=1))
    assert desktop.football_controller.state == before
    desktop.router.draw(_surface())
    assert [button.label for button in screen.buttons] == ["KEEP PLAYING", "RETURN TO MENU", "QUIT RUN"]


def test_hover_then_enter_in_same_frame_chooses_highlighted_pair(tmp_path):
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    screen = desktop.run_screen
    expected = desktop.football_controller.state.team_builder.coach_offer[2]
    card = screen.coach_inspection.card_rects[2]
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(card.centerx, card.top + 55)))
    assert screen.coach_inspection.active_index(screen.focus_index) == 2
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert desktop.football_controller.state.selected_coach_pair is expected


def test_primary_and_stat_colors_are_readable():
    from src.profile import COLOR_CHOICES
    def contrast(a, b):
        light, dark = sorted((relative_luminance(pygame.Color(a)),
                              relative_luminance(pygame.Color(b))), reverse=True)
        return (light + .05) / (dark + .05)
    for item in COLOR_CHOICES:
        color = pygame.Color(item.hex_value)
        assert contrast(color, readable_ink(color)) >= 4.5
    for color in (football_coach_view._POSITIVE, football_coach_view._NEGATIVE,
                  football_coach_view._NEUTRAL):
        assert contrast(color, "#102e4a") >= 4.5
