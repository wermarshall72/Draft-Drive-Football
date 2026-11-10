from typing import Protocol

import pygame


class NavigableScreen(Protocol):
    def on_enter(self) -> None: ...

    def on_exit(self) -> None: ...


class ScreenManager:
    def __init__(self) -> None:
        self._screens: dict[str, NavigableScreen] = {}
        self.current_id: str | None = None

    @property
    def current(self) -> NavigableScreen:
        if self.current_id is None:
            raise RuntimeError("No desktop screen is active.")
        return self._screens[self.current_id]

    def register(self, screen_id: str, screen: NavigableScreen) -> None:
        if screen_id in self._screens:
            raise ValueError(f"Screen {screen_id!r} is already registered.")
        self._screens[screen_id] = screen

    def show(self, screen_id: str) -> None:
        if screen_id not in self._screens:
            raise ValueError(f"Unknown desktop screen: {screen_id}")
        if self.current_id == screen_id:
            return
        if self.current_id is not None:
            self.current.on_exit()
        self.current_id = screen_id
        self.current.on_enter()

    def handle_event(self, event: pygame.event.Event) -> None:
        handler = getattr(self.current, "handle_event", None)
        if handler is not None:
            handler(event)

    def draw(self, surface: pygame.Surface) -> None:
        drawer = getattr(self.current, "draw", None)
        if drawer is None:
            raise RuntimeError("The active desktop screen cannot be drawn.")
        drawer(surface)
