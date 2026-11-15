from dataclasses import dataclass
from typing import Literal

import pygame

ReviewMode = Literal["depth", "playbook"]


@dataclass
class ShopReviewInteraction:
    """Own the active shop review and its independent scroll positions."""

    mode: ReviewMode | None = None
    playbook_scroll: int = 0
    playbook_max_scroll: int = 0
    depth_scroll: int = 0
    depth_max_scroll: int = 0

    def open_depth_chart(self) -> None:
        self.mode = "depth"
        self.depth_scroll = 0

    def open_playbook(self) -> None:
        self.mode = "playbook"

    def close(self) -> None:
        self.mode = None
        self.depth_scroll = 0

    def handle_scroll(self, event: pygame.event.Event) -> bool:
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
