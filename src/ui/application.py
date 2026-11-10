from collections.abc import Callable, Iterable

import pygame

from src.application import ApplicationController
from src.profile import ProfileError, TeamProfile
from src.ui.layout import LOGICAL_SIZE
from src.ui.navigation import ScreenManager
from src.ui.screens import (
    SCREEN_COPY,
    MainMenuScreen,
    PlaceholderScreen,
)
from src.ui.theme import Theme

EventSource = Callable[[], Iterable[pygame.event.Event]]


class DesktopApplication:
    """Resizable, framework-isolated desktop shell around the application boundary."""

    def __init__(
        self,
        controller: ApplicationController | None = None,
        *,
        window_size: tuple[int, int] = LOGICAL_SIZE,
    ) -> None:
        self.controller = controller or ApplicationController()
        self.window_size = window_size
        self.running = False
        self.profile: TeamProfile | None = None
        self.profile_error: str | None = None
        try:
            self.profile = self.controller.load_profile()
        except ProfileError as error:
            self.profile_error = str(error)

        self.menu_state = (
            self.controller.main_menu_state() if self.profile is not None else None
        )
        self.theme = Theme.from_profile(self.profile)
        self.router = ScreenManager()
        team_name = self.profile.team_name if self.profile is not None else "NEW TEAM"
        navigate = self.router.show
        self.router.register(
            "main_menu",
            MainMenuScreen(
                self.theme,
                self.menu_state,
                self.profile_error,
                navigate,
                self.quit,
            ),
        )
        for screen_id, definition in SCREEN_COPY.items():
            self.router.register(
                screen_id,
                PlaceholderScreen(
                    self.theme,
                    definition,
                    team_name,
                    navigate,
                    self.quit,
                ),
            )
        self.router.show("main_menu")

    def quit(self) -> None:
        self.running = False

    def run(self, event_source: EventSource | None = None) -> None:
        pygame.init()
        try:
            pygame.display.set_caption("CFB Auto-Battler")
            window = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
            canvas = pygame.Surface(LOGICAL_SIZE)
            clock = pygame.time.Clock()
            self.running = True
            source = pygame.event.get if event_source is None else event_source
            self.router.draw(canvas)
            while self.running:
                for event in source():
                    if event.type == pygame.QUIT:
                        self.quit()
                    elif event.type == pygame.VIDEORESIZE:
                        self.window_size = (max(1, event.w), max(1, event.h))
                        window = pygame.display.set_mode(
                            self.window_size, pygame.RESIZABLE
                        )
                    else:
                        active_screen = self.router.current_id
                        self.router.handle_event(self._logical_event(event))
                        if self.router.current_id != active_screen:
                            self.router.draw(canvas)

                if not self.running:
                    break
                self.router.draw(canvas)
                self._present(canvas, window)
                clock.tick(60)
        finally:
            self.running = False
            pygame.quit()

    def _logical_event(self, event: pygame.event.Event) -> pygame.event.Event:
        if event.type not in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            return event
        logical_width, logical_height = LOGICAL_SIZE
        window_width, window_height = self.window_size
        scale = min(window_width / logical_width, window_height / logical_height)
        rendered_width = round(logical_width * scale)
        rendered_height = round(logical_height * scale)
        offset_x = (window_width - rendered_width) // 2
        offset_y = (window_height - rendered_height) // 2
        physical_x, physical_y = event.pos
        position = (
            round((physical_x - offset_x) / scale),
            round((physical_y - offset_y) / scale),
        )
        return pygame.event.Event(event.type, {**event.dict, "pos": position})

    @staticmethod
    def _present(canvas: pygame.Surface, window: pygame.Surface) -> None:
        window.fill((0, 0, 0))
        logical_width, logical_height = LOGICAL_SIZE
        window_width, window_height = window.get_size()
        scale = min(window_width / logical_width, window_height / logical_height)
        size = (
            max(1, round(logical_width * scale)),
            max(1, round(logical_height * scale)),
        )
        scaled = pygame.transform.smoothscale(canvas, size)
        window.blit(
            scaled,
            ((window_width - size[0]) // 2, (window_height - size[1]) // 2),
        )
        pygame.display.flip()
