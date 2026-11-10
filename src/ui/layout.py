from dataclasses import dataclass

import pygame

LOGICAL_SIZE = (1280, 720)


@dataclass(frozen=True)
class Layout:
    width: int
    height: int

    @classmethod
    def from_surface(cls, surface: pygame.Surface) -> "Layout":
        return cls(*surface.get_size())

    @property
    def margin(self) -> int:
        return max(24, min(round(self.width * 0.045), 56))

    @property
    def header(self) -> pygame.Rect:
        return pygame.Rect(
            self.margin,
            max(20, round(self.height * 0.042)),
            self.width - self.margin * 2,
            max(58, round(self.height * 0.095)),
        )

    @property
    def content(self) -> pygame.Rect:
        top = self.header.bottom + max(68, round(self.height * 0.105))
        return pygame.Rect(
            self.margin,
            top,
            self.width - self.margin * 2,
            self.height - top - self.margin - max(26, round(self.height * 0.045)),
        )

    def centered_panel(self, width_ratio: float, height_ratio: float) -> pygame.Rect:
        width = round(self.width * width_ratio)
        height = round(self.height * height_ratio)
        return pygame.Rect(
            (self.width - width) // 2,
            (self.height - height) // 2,
            width,
            height,
        )
