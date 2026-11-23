from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Literal

import pygame

from src.engine.football import FootballPosition
from src.engine.football_shop import FootballShopRarity
from src.ui.football_inspect import InspectState

FLIP_MS = 360
BACK_SCROLL_STEP = 24
ReviewMode = Literal["depth", "playbook"]
PlaybookCategory = Literal["all", "offense", "defense", "special"]

_PLAYBOOK_CATEGORIES: tuple[PlaybookCategory, ...] = (
    "all",
    "offense",
    "defense",
    "special",
)
_PLAYBOOK_POSITIONS: tuple[FootballPosition | None, ...] = (
    None,
    *tuple(FootballPosition),
)
_PLAYBOOK_RARITIES: tuple[FootballShopRarity | None, ...] = (
    None,
    *tuple(FootballShopRarity),
)


@dataclass
class ShopReviewInteraction:
    """Own the active shop review and its independent scroll positions."""

    mode: ReviewMode | None = None
    playbook_scroll: int = 0
    playbook_max_scroll: int = 0
    playbook_page_size: int = 1
    playbook_category: PlaybookCategory = "all"
    playbook_position: FootballPosition | None = None
    playbook_rarity: FootballShopRarity | None = None
    depth_scroll: int = 0
    depth_max_scroll: int = 0
    modified_stats: bool = False
    # Depth Chart card flips: key -> (back showing after the flip, flip start in ms).
    flips: dict[Hashable, tuple[bool, int]] = field(default_factory=dict, compare=False, repr=False)
    team_popup: bool = False
    # Scrollable card backs: per-card scroll, this frame's (card rect, max scroll, page),
    # the last pointer position, and the card whose flip arrow has keyboard focus.
    back_scroll: dict[Hashable, int] = field(default_factory=dict, compare=False, repr=False)
    back_areas: dict[Hashable, tuple] = field(default_factory=dict, compare=False, repr=False)
    pointer: tuple[int, int] | None = field(default=None, compare=False, repr=False)
    focused_flip: Hashable | None = field(default=None, compare=False, repr=False)
    clock: Callable[[], int] = field(default=pygame.time.get_ticks, compare=False, repr=False)
    depth_viewport_size: tuple[int, int] | None = None
    inspect: InspectState = field(default_factory=InspectState, compare=False, repr=False)

    def open_depth_chart(self) -> None:
        self.mode = "depth"
        self.depth_scroll = 0
        self.modified_stats = False
        self.flips.clear()
        self.back_scroll.clear()
        self.back_areas.clear()
        self.team_popup = False
        self.depth_viewport_size = None

    def toggle_stats(self) -> None:
        self.modified_stats = not self.modified_stats

    def toggle_flip(self, key: Hashable) -> None:
        """Start rotating a Depth Chart card to its other face."""
        back, _started = self.flips.get(key, (False, -FLIP_MS))
        self.flips[key] = (not back, self.clock())
        self.back_scroll[key] = 0

    def _scroll_back(self, key: Hashable, step: int) -> bool:
        area = self.back_areas.get(key)
        if area is None or not area[1]:
            return False
        self.back_scroll[key] = max(0, min(area[1], self.back_scroll.get(key, 0) + step))
        return True

    def _back_under_pointer(self) -> Hashable | None:
        if self.pointer is None:
            return None
        return next((key for key, (rect, max_scroll, _page) in self.back_areas.items()
                     if max_scroll and rect.collidepoint(self.pointer)), None)

    def flip_progress(self, key: Hashable) -> tuple[bool, float]:
        """(back showing at the end of the flip, progress from 0 to 1)."""
        back, started = self.flips.get(key, (False, -FLIP_MS))
        return back, max(0.0, min(1.0, (self.clock() - started) / FLIP_MS))

    def open_team_upgrades(self) -> None:
        self.team_popup = True

    def close_team_upgrades(self) -> None:
        self.team_popup = False

    def open_playbook(self) -> None:
        self.mode = "playbook"
        self.inspect.reset()
        self.playbook_scroll = 0
        self.playbook_category = "all"
        self.playbook_position = None
        self.playbook_rarity = None

    def close(self) -> None:
        self.mode = None
        self.inspect.reset()
        self.depth_scroll = 0

    def cycle_playbook_category(self) -> None:
        index = _PLAYBOOK_CATEGORIES.index(self.playbook_category)
        self.playbook_category = _PLAYBOOK_CATEGORIES[
            (index + 1) % len(_PLAYBOOK_CATEGORIES)
        ]
        self.playbook_scroll = 0

    def cycle_playbook_position(self) -> None:
        index = _PLAYBOOK_POSITIONS.index(self.playbook_position)
        self.playbook_position = _PLAYBOOK_POSITIONS[
            (index + 1) % len(_PLAYBOOK_POSITIONS)
        ]
        self.playbook_scroll = 0

    def cycle_playbook_rarity(self) -> None:
        index = _PLAYBOOK_RARITIES.index(self.playbook_rarity)
        self.playbook_rarity = _PLAYBOOK_RARITIES[
            (index + 1) % len(_PLAYBOOK_RARITIES)
        ]
        self.playbook_scroll = 0

    def handle_scroll(self, event: pygame.event.Event) -> bool:
        if self.mode == "depth" and event.type == pygame.MOUSEMOTION:
            self.pointer = event.pos
            return False
        if self.mode == "depth" and event.type == pygame.MOUSEWHEEL and not self.team_popup:
            key = self._back_under_pointer()
            if key is not None:
                return self._scroll_back(key, -event.y * BACK_SCROLL_STEP)
        if (self.mode == "depth" and event.type == pygame.KEYDOWN and not self.team_popup
                and self.focused_flip in self.back_areas
                and event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END)):
            _rect, max_scroll, page = self.back_areas[self.focused_flip]
            if max_scroll:
                step = {pygame.K_PAGEUP: -(page - 30), pygame.K_PAGEDOWN: page - 30,
                        pygame.K_HOME: -10**6, pygame.K_END: 10**6}[event.key]
                return self._scroll_back(self.focused_flip, step)
        if self.mode == "depth" and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                if event.key == pygame.K_HOME:
                    self.depth_scroll = 0
                elif event.key == pygame.K_END:
                    self.depth_scroll = self.depth_max_scroll
                else:
                    direction = -1 if event.key == pygame.K_PAGEUP else 1
                    self.depth_scroll = max(
                        0, min(self.depth_max_scroll, self.depth_scroll + direction * 240)
                    )
                return True
        if self.mode == "playbook" and event.type == pygame.KEYDOWN:
            if event.key in (
                pygame.K_PAGEUP,
                pygame.K_PAGEDOWN,
                pygame.K_HOME,
                pygame.K_END,
            ):
                if event.key == pygame.K_HOME:
                    self.playbook_scroll = 0
                elif event.key == pygame.K_END:
                    self.playbook_scroll = self.playbook_max_scroll
                else:
                    direction = -1 if event.key == pygame.K_PAGEUP else 1
                    self.playbook_scroll = max(
                        0,
                        min(
                            self.playbook_max_scroll,
                            self.playbook_scroll
                            + direction * self.playbook_page_size,
                        ),
                    )
                return True
        if event.type != pygame.MOUSEWHEEL:
            return False
        if self.mode == "playbook":
            self.playbook_scroll = max(
                0, min(self.playbook_max_scroll, self.playbook_scroll - event.y)
            )
            return True
        if self.mode == "depth":
            self.depth_scroll = max(
                0, min(self.depth_max_scroll, self.depth_scroll - event.y * 40)
            )
            return True
        return False
