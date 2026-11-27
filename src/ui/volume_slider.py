"""The one volume slider shared by the Settings screen and the pause menu's AUDIO view.

A ``VolumeSlider`` is a ``Button`` so it joins each screen's Tab/arrow focus
order; ``SliderInput`` turns mouse and key events into value changes. Values
change live while dragging and are committed (saved) on mouse up or after each
keyboard step. Both places read and write the application's one
``AudioSettings`` through an ``AudioBinding``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pygame

from src.audio_settings import VOLUME_MAX, VOLUME_MIN, VOLUME_STEP, AudioSettings, normalize_volume
from src.ui.football_ui_kit import (
    MATCH_FOCUS, MATCH_INK, MATCH_MUTED, MATCH_PANEL_EDGE_SOFT, MATCH_TEXT, blit_text, match_font,
)
from src.ui.text import fit_text
from src.ui.widgets import Button

MUSIC = "music"
EFFECTS = "effects"
MUSIC_LABEL = "Music"
EFFECTS_LABEL = "Sound effects"

LABEL_HEIGHT = 20
ROW_HEIGHT = 32
BLOCK_HEIGHT = LABEL_HEIGHT + 4 + ROW_HEIGHT
ICON_WIDTH = 22
VALUE_WIDTH = 46
TRACK_THICKNESS = 6
THUMB_RADIUS = 9
THUMB_RADIUS_HOT = 11

SliderChange = Callable[[int, bool], None]  # (new value, commit to disk)


@dataclass
class AudioBinding:
    """Read and replace the application's current ``AudioSettings``.

    ``update(settings, commit)`` stores the new value; ``commit`` also saves it.
    """

    get: Callable[[], AudioSettings]
    update: Callable[[AudioSettings, bool], None]


def local_audio_binding(initial: AudioSettings | None = None) -> AudioBinding:
    """An in-memory binding for screens built without an application."""
    box = [initial or AudioSettings()]

    def update(settings: AudioSettings, _commit: bool) -> None:
        box[0] = settings

    return AudioBinding(lambda: box[0], update)


@dataclass(frozen=True)
class SliderPalette:
    fill: pygame.Color
    track: pygame.Color
    thumb: pygame.Color
    thumb_edge: pygame.Color
    focus: pygame.Color
    text: pygame.Color
    icon: pygame.Color
    label_font: pygame.font.Font
    value_font: pygame.font.Font


def match_slider_palette() -> SliderPalette:
    """The one slider look, shared by Settings and the pause AUDIO view (navy match style).

    Built per call rather than cached: the match fonts are rebuilt after pygame restarts.
    """
    return SliderPalette(
        fill=MATCH_FOCUS, track=MATCH_PANEL_EDGE_SOFT, thumb=MATCH_TEXT, thumb_edge=MATCH_INK,
        focus=MATCH_TEXT, text=MATCH_TEXT, icon=MATCH_MUTED,
        label_font=match_font(15), value_font=match_font(16),
    )


@dataclass
class VolumeSlider(Button):
    key: str = MUSIC
    value: int = 0
    palette: SliderPalette | None = None
    on_change: SliderChange = field(default=lambda _value, _commit: None)
    active: bool = False  # being dragged

    @property
    def row(self) -> pygame.Rect:
        return pygame.Rect(self.rect.left, self.rect.bottom - ROW_HEIGHT, self.rect.width, ROW_HEIGHT)

    @property
    def track(self) -> pygame.Rect:
        row = self.row
        left = row.left + ICON_WIDTH + 14
        right = row.right - VALUE_WIDTH - 14
        return pygame.Rect(left, row.centery - TRACK_THICKNESS // 2, max(1, right - left),
                           TRACK_THICKNESS)

    @property
    def thumb_x(self) -> int:
        track = self.track
        return track.left + round(track.width * self.value / VOLUME_MAX)

    def value_at(self, x: int) -> int:
        track = self.track
        fraction = (x - track.left) / max(1, track.width)
        return normalize_volume(fraction * VOLUME_MAX)

    def change(self, value: int, commit: bool) -> None:
        value = normalize_volume(value)
        self.value = value
        self.on_change(value, commit)

    def draw(self, surface, font, theme, *, hovered: bool = False, pressed: bool = False) -> None:
        palette = self.palette
        assert palette is not None
        blit_text(surface, palette.label_font, fit_text(self.label, palette.label_font, self.rect.width),
                  palette.text, self.rect, topleft=self.rect.topleft)
        row = self.row
        if self.focused:
            pygame.draw.rect(surface, palette.focus, row.inflate(14, 8), 2, border_radius=10)
        icon_center = (row.left + ICON_WIDTH // 2, row.centery)
        if self.key == MUSIC:
            draw_music_icon(surface, icon_center, palette.icon)
        else:
            draw_speaker_icon(surface, icon_center, palette.icon)
        track = self.track
        pygame.draw.rect(surface, palette.track, track, border_radius=TRACK_THICKNESS // 2)
        thumb_x = self.thumb_x
        filled = pygame.Rect(track.left, track.top, thumb_x - track.left, track.height)
        if filled.width > 0:
            pygame.draw.rect(surface, palette.fill, filled, border_radius=TRACK_THICKNESS // 2)
        radius = THUMB_RADIUS_HOT if hovered or self.active else THUMB_RADIUS
        pygame.draw.circle(surface, palette.thumb_edge, (thumb_x, track.centery), radius + 2)
        pygame.draw.circle(surface, palette.thumb, (thumb_x, track.centery), radius)
        blit_text(surface, palette.value_font, f"{self.value}%", palette.text, self.rect,
                  midright=(row.right, row.centery))


def audio_sliders(
    binding: AudioBinding, music_rect: pygame.Rect, effects_rect: pygame.Rect,
    palette: SliderPalette, *, dragging: str | None = None,
) -> list[VolumeSlider]:
    """The Music and Sound effects sliders, wired to ``binding``."""
    settings = binding.get()

    def setter(attribute: str) -> SliderChange:
        def change(value: int, commit: bool) -> None:
            binding.update(replace(binding.get(), **{attribute: value}), commit)
        return change

    sliders = []
    for key, label, rect, value, attribute in (
        (MUSIC, MUSIC_LABEL, music_rect, settings.music_volume, "music_volume"),
        (EFFECTS, EFFECTS_LABEL, effects_rect, settings.effects_volume, "effects_volume"),
    ):
        slider = VolumeSlider(label, lambda: None, pygame.Rect(rect), key=key, value=value,
                              palette=palette, on_change=setter(attribute),
                              active=dragging == key)
        track = slider.track
        slider.click_rect = pygame.Rect(track.left - 14, slider.row.top, track.width + 28,
                                        slider.row.height)
        sliders.append(slider)
    return sliders


_KEY_STEPS = {
    pygame.K_LEFT: -VOLUME_STEP, pygame.K_a: -VOLUME_STEP,
    pygame.K_RIGHT: VOLUME_STEP, pygame.K_d: VOLUME_STEP,
}


class SliderInput:
    """Drag and keyboard handling for the sliders in a screen's button list."""

    def __init__(self) -> None:
        self.dragging: str | None = None
        self._slider: VolumeSlider | None = None
        self._value = 0

    def handle_event(
        self, event: pygame.event.Event, buttons: list[Button], focus_index: int,
    ) -> int | None:
        """Return the index of the slider that used the event, else None."""
        sliders = [
            (index, button) for index, button in enumerate(buttons)
            if isinstance(button, VolumeSlider) and button.enabled
        ]
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, slider in sliders:
                if slider.hit_rect.collidepoint(event.pos):
                    self.dragging, self._slider = slider.key, slider
                    self._set(slider, slider.value_at(event.pos[0]), commit=False)
                    return index
            return None
        if self.dragging is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            if event.type == pygame.MOUSEBUTTONUP and event.button != 1:
                return None
            index, slider = next(
                ((index, slider) for index, slider in sliders if slider.key == self.dragging),
                (None, self._slider),
            )
            assert slider is not None
            commit = event.type == pygame.MOUSEBUTTONUP
            self._set(slider, slider.value_at(event.pos[0]), commit=commit)
            if commit:
                self.dragging, self._slider = None, None
            return index if index is not None else focus_index
        if event.type == pygame.KEYDOWN:
            slider = next((s for index, s in sliders if index == focus_index), None)
            if slider is None:
                return None
            if event.key in _KEY_STEPS:
                target = slider.value + _KEY_STEPS[event.key]
            elif event.key == pygame.K_HOME:
                target = VOLUME_MIN
            elif event.key == pygame.K_END:
                target = VOLUME_MAX
            else:
                return None
            target = normalize_volume(target)
            if target != slider.value:
                self._set(slider, target, commit=True)
            return focus_index
        return None

    def release(self) -> None:
        """Commit an unfinished drag (the view closed before mouse up)."""
        if self.dragging is not None and self._slider is not None:
            self._slider.change(self._value, True)
        self.dragging, self._slider = None, None

    def _set(self, slider: VolumeSlider, value: int, *, commit: bool) -> None:
        self._value = normalize_volume(value)
        slider.change(self._value, commit)


# -- icons -------------------------------------------------------------------------


def draw_music_icon(surface: pygame.Surface, center: tuple[int, int], color: pygame.Color) -> None:
    """Two beamed eighth notes, about 20 px."""
    cx, cy = center
    for head_x in (cx - 6, cx + 5):
        pygame.draw.ellipse(surface, color, (head_x - 4, cy + 3, 8, 6))
        pygame.draw.line(surface, color, (head_x + 3, cy + 6), (head_x + 3, cy - 7), 2)
    pygame.draw.polygon(surface, color, [(cx - 3, cy - 7), (cx + 8, cy - 10),
                                         (cx + 8, cy - 7), (cx - 3, cy - 4)])


def draw_speaker_icon(surface: pygame.Surface, center: tuple[int, int], color: pygame.Color) -> None:
    """A speaker cone with two sound waves, about 20 px."""
    cx, cy = center
    pygame.draw.rect(surface, color, (cx - 10, cy - 3, 5, 7))
    pygame.draw.polygon(surface, color, [(cx - 6, cy - 3), (cx, cy - 8), (cx, cy + 8), (cx - 6, cy + 4)])
    for radius in (4, 8):
        box = pygame.Rect(0, 0, radius * 2, radius * 2)
        box.center = (cx + 1, cy)
        pygame.draw.arc(surface, color, box, -math.pi / 3.2, math.pi / 3.2, 2)
