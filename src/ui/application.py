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

    TRANSITION_MS = 260
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
        self._transition_started: int | None = None
        team_name = self.profile.team_name if self.profile is not None else "NEW TEAM"
        navigate = self.navigate
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

    def navigate(self, screen_id: str) -> None:
        if screen_id == self.router.current_id:
            return
        self.router.show(screen_id)
        if self.running and pygame.display.get_surface() is not None:
            self._transition_started = pygame.time.get_ticks()

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
                    elif not self._transition_is_active(pygame.time.get_ticks()):
                        active_screen = self.router.current_id
                        self.router.handle_event(self._logical_event(event))
                        if self.router.current_id != active_screen:
                            self.router.draw(canvas)

                if not self.running:
                    break
                self.router.draw(canvas)
                self._draw_transition(canvas, pygame.time.get_ticks())
                self._present(canvas, window)
                clock.tick(60)
        finally:
            self.running = False
            pygame.quit()

    def _logical_event(self, event: pygame.event.Event) -> pygame.event.Event:
        if event.type not in (
            pygame.MOUSEMOTION,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
        ):
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

    def _transition_is_active(self, now: int) -> bool:
        if self._transition_started is None:
            return False
        if now - self._transition_started >= self.TRANSITION_MS:
            self._transition_started = None
            return False
        return True

    def _draw_transition(self, canvas: pygame.Surface, now: int) -> None:
        if not self._transition_is_active(now):
            return

        assert self._transition_started is not None
        elapsed = (now - self._transition_started) / self.TRANSITION_MS
        progress = min(1.0, max(0.0, elapsed))
        eased = progress * progress * (3 - 2 * progress)
        width, height = canvas.get_size()
        cover_width = round(width * (1 - eased))
        if cover_width <= 0:
            return

        curtain = pygame.Surface((cover_width, height))
        for y in range(0, height, 4):
            position = y / max(1, height - 1)
            if position < 0.5:
                color = _mix_color(
                    self.theme.canvas_lift,
                    self.theme.canvas,
                    position * 2,
                )
            else:
                color = _mix_color(
                    self.theme.canvas,
                    self.theme.primary_dark,
                    (position - 0.5) * 2,
                )
            pygame.draw.line(curtain, color, (0, y), (cover_width, y), 4)

        fieldline_color = self.theme.border_soft
        for fraction in (0.23, 0.77):
            y = round(height * fraction)
            pygame.draw.line(
                curtain,
                (*fieldline_color[:3], 110),
                (0, y),
                (cover_width, y),
                1,
            )
        for x_fraction in (0.2, 0.4, 0.6, 0.8):
            x = round(width * x_fraction)
            if x < cover_width:
                pygame.draw.line(
                    curtain,
                    fieldline_color,
                    (x, 0),
                    (x, height),
                    1,
                )

        canvas.blit(curtain, (0, 0))
        edge = cover_width - 1
        for distance in range(min(10, cover_width)):
            alpha = round(50 * (1 - distance / 10))
            pygame.draw.line(
                canvas,
                (*self.theme.primary_accent[:3], alpha),
                (edge - distance, 0),
                (edge - distance, height),
                1,
            )
        pygame.draw.line(
            canvas,
            self.theme.secondary_accent,
            (edge, 0),
            (edge, height),
            1,
        )

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


def _mix_color(
    first: pygame.Color, second: pygame.Color, amount: float
) -> pygame.Color:
    return pygame.Color(
        round(first.r + (second.r - first.r) * amount),
        round(first.g + (second.g - first.g) * amount),
        round(first.b + (second.b - first.b) * amount),
    )
