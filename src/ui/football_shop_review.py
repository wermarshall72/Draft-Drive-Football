from dataclasses import dataclass
from typing import Literal

import pygame

from src.engine.football import FootballPosition
from src.engine.football_shop import FootballShopRarity

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
    depth_details: bool = False
    depth_viewport_size: tuple[int, int] | None = None

    def open_depth_chart(self) -> None:
        self.mode = "depth"
        self.depth_scroll = 0
        self.modified_stats = False
        self.depth_details = False
        self.depth_viewport_size = None

    def toggle_stats(self) -> None:
        self.modified_stats = not self.modified_stats

    def toggle_depth_details(self) -> None:
        self.depth_details = not self.depth_details
        self.depth_scroll = 0

    def open_playbook(self) -> None:
        self.mode = "playbook"
        self.playbook_scroll = 0
        self.playbook_category = "all"
        self.playbook_position = None
        self.playbook_rarity = None

    def close(self) -> None:
        self.mode = None
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
