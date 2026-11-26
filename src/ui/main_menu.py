"""The desktop season menu and its profile-aware controls."""

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.application import MainMenuState
from src.engine.football_ai import FootballAIDifficulty
from src.ui.coach_fonts import staff_font
from src.ui.football_pause_menu import MenuEntry, draw_menu_panel
from src.ui.main_menu_art import draw_menu_stadium
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_text

_TEXT = pygame.Color("#eef5ff")
_MUTED = pygame.Color("#b5c8dc")
_EDGE = pygame.Color("#507397")
CONTINUE_RUN = "CONTINUE RUN"
START_RUN = "START RUN"
START_NEW_RUN = "START NEW RUN"
CANCEL = "CANCEL"
REPLACE_TITLE = "START A NEW RUN?"
ABANDON_SAVE = "ABANDON SAVE"
HOW_TO_PLAY = "HOW TO PLAY"
# Half-width buttons (SETTINGS beside HOW TO PLAY) show a shorter detail line.
_SHORT_DETAILS = {
    "SETTINGS": "Team name and colors",
    "CREATE PROFILE": "Create your team",
    HOW_TO_PLAY: "The rules in one page",
}


@dataclass(frozen=True)
class MenuSaveNotice:
    """A short message about the saved run (restored, damaged, or unloadable).

    ``abandonable`` notices describe a save that is kept on disk but can't be
    continued; the menu then offers ABANDON SAVE and confirms START RUN.
    """

    title: str
    message: str
    abandonable: bool = False


def _marquee(surface: pygame.Surface, text: str, rect: pygame.Rect,
             font: pygame.font.Font, color: pygame.Color) -> None:
    """Keep long, unrestricted profile names and error details legible."""
    rendered = font.render(text, True, color)
    old_clip = surface.get_clip()
    surface.set_clip(old_clip.clip(rect))
    if rendered.get_width() <= rect.width:
        x = rect.left
    else:
        distance = rendered.get_width() - rect.width
        # Pause at both ends so the beginning and end are easy to read.
        travel = distance * 35
        phase = pygame.time.get_ticks() % (travel * 2 + 3000)
        if phase < 1500:
            offset = 0
        elif phase < 1500 + travel:
            offset = (phase - 1500) // 35
        elif phase < 3000 + travel:
            offset = distance
        else:
            offset = distance - (phase - 3000 - travel) // 35
        x = rect.left - offset
    surface.blit(rendered, (x, rect.centery - rendered.get_height() // 2))
    surface.set_clip(old_clip)


class FootballMainMenuScreen(Screen):
    def __init__(
        self,
        theme: Theme,
        menu_state: MainMenuState | None,
        profile_error: str | None,
        navigate: Navigate,
        quit_application: Quit,
        on_start_run: Callable[[FootballAIDifficulty], None],
        *,
        on_continue_run: Callable[[], None] = lambda: None,
        run_summary: Callable[[], tuple[str, str] | None] = lambda: None,
        save_notice: Callable[[], MenuSaveNotice | None] = lambda: None,
        on_abandon_save: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.menu_state = menu_state
        self.profile_error = profile_error
        self.on_start_run = on_start_run
        self.on_continue_run = on_continue_run
        # (menu summary, replace-warning summary) for a remembered run, else None.
        self.run_summary = run_summary
        self.save_notice = save_notice
        self.on_abandon_save = on_abandon_save
        self.confirm_replace = False
        self.difficulty = FootballAIDifficulty.STANDARD
        self.title_font = staff_font(48, semibold=True)
        self.menu_font = staff_font(25, semibold=True)
        self.detail_font = staff_font(17)
        self.badge_font = staff_font(21, semibold=True)
        self.small_font = staff_font(15, semibold=True)
        self.overlay: pygame.Surface | None = None
        self.keyboard_focus = True

    def on_enter(self) -> None:
        super().on_enter()
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None
        self.keyboard_focus = True
        self.confirm_replace = False

    def on_exit(self) -> None:
        super().on_exit()
        self.hover_index = None
        self.pressed_index = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.pressed_index = None
            return
        if event.type == pygame.KEYDOWN:
            self.hover_index = None
            self.pressed_index = None
            self.keyboard_focus = True
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.keyboard_focus = False
        if (
            self.confirm_replace
            and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            self._cancel_replace()
            return
        super().handle_event(event)

    def _blocked_save(self) -> bool:
        notice = self.save_notice()
        return notice is not None and notice.abandonable

    def _abandon_save(self) -> None:
        self.on_abandon_save()
        self._reset_focus()

    def _start_run_pressed(self) -> None:
        if self.run_summary() is not None or self._blocked_save():
            self.confirm_replace = True
            self._reset_focus()
            return
        self.on_start_run(self.difficulty)

    def _confirm_replace(self) -> None:
        self.confirm_replace = False
        self.on_start_run(self.difficulty)

    def _cancel_replace(self) -> None:
        self.confirm_replace = False
        self._reset_focus(focus=1)

    def _reset_focus(self, focus: int = 0) -> None:
        self.buttons = []
        self.focus_index = focus
        self.hover_index = None
        self.pressed_index = None

    def draw(self, surface: pygame.Surface) -> None:
        draw_menu_stadium(surface, self.theme.primary, self.theme.secondary)
        self.overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._draw_overlay(self.overlay)
        surface.blit(self.overlay, (0, 0))

    def _draw_overlay(self, surface: pygame.Surface) -> None:
        draw_text(surface, "COLLEGE FOOTBALL", (36, 20), self.title_font, _TEXT)
        draw_text(surface, "BUILD YOUR PROGRAM  /  CALL THE GAME", (39, 78),
                  self.detail_font, _MUTED)
        pygame.draw.line(surface, _EDGE, (39, 107), (618, 107), 2)

        badge = pygame.Rect(855, 25, 389, 68)
        pygame.draw.rect(surface, "#102e4a", badge, border_radius=6)
        pygame.draw.rect(surface, _EDGE, badge, 2, border_radius=6)
        pygame.draw.rect(surface, self.theme.primary, (badge.left + 13, badge.top + 13, 9, 42))
        pygame.draw.rect(surface, self.theme.secondary, (badge.left + 25, badge.top + 13, 5, 42))
        draw_text(surface, "YOUR PROGRAM", (badge.left + 42, badge.top + 8),
                  self.small_font, _MUTED)
        team_name = self.menu_state.profile.team_name if self.menu_state else "NEW TEAM"
        _marquee(surface, team_name.upper(),
                 pygame.Rect(badge.left + 42, badge.top + 30, badge.width - 54, 29),
                 self.badge_font, _TEXT)

        summary = self.run_summary() if self.menu_state is not None else None
        continuing = summary is not None
        if not continuing and not self._blocked_save():
            self.confirm_replace = False
        # With a remembered run, CONTINUE RUN leads and the rest compress to fit.
        start_rect, panel_rect, difficulty_y, settings_rect, quit_rect, warning_y = (
            (pygame.Rect(40, 222, 500, 62), pygame.Rect(40, 296, 500, 80), 326,
             pygame.Rect(40, 388, 500, 62), pygame.Rect(40, 462, 500, 62), 536)
            if continuing else
            (pygame.Rect(40, 139, 500, 77), pygame.Rect(40, 228, 500, 86), 262,
             pygame.Rect(40, 323, 500, 77), pygame.Rect(40, 415, 500, 77), 511)
        )
        buttons: list[Button] = []
        if continuing:
            buttons.append(Button(CONTINUE_RUN, self.on_continue_run,
                                  pygame.Rect(40, 124, 500, 86), variant="continue"))
        buttons.append(Button(START_RUN, self._start_run_pressed, start_rect,
                              enabled=self.menu_state is not None))
        first_difficulty = len(buttons)
        for index, difficulty in enumerate(FootballAIDifficulty):
            buttons.append(Button(
                difficulty.value.upper(),
                lambda choice=difficulty: self._select_difficulty(choice),
                pygame.Rect(53 + index * 159, difficulty_y,
                            151, 38 if continuing else 42),
                variant="primary" if difficulty is self.difficulty else "quiet",
            ))
        half = (settings_rect.width - 12) // 2
        buttons.extend((
            Button("SETTINGS" if self.menu_state else "CREATE PROFILE",
                   lambda: self.navigate("settings"),
                   pygame.Rect(settings_rect.left, settings_rect.top, half, settings_rect.height),
                   enabled=self.profile_error is None),
            Button(HOW_TO_PLAY, lambda: self.navigate("how_to_play"),
                   pygame.Rect(settings_rect.right - half, settings_rect.top, half,
                               settings_rect.height)),
            Button("QUIT", self.quit_application, quit_rect),
        ))
        notice = self.save_notice() if self.menu_state is not None else None
        show_notice = notice is not None and not self.profile_error
        notice_rect = pygame.Rect(40, warning_y, 650, 96 if continuing else 105)
        if show_notice and notice.abandonable:
            buttons.append(Button(
                ABANDON_SAVE, self._abandon_save,
                pygame.Rect(notice_rect.right - 196, notice_rect.top + 12, 182, 40),
                variant="abandon",
            ))
        if self.focus_index == 0 and self.menu_state is None:
            self.focus_index = 4 if self.profile_error is None else 6
        if not self.confirm_replace:
            self._set_buttons(buttons)
        else:
            for button in buttons:
                button.focused = False
        pygame.draw.rect(surface, "#102b47", panel_rect, border_radius=6)
        pygame.draw.rect(surface, _EDGE, panel_rect, 2, border_radius=6)
        draw_text(surface, "OPPONENT DIFFICULTY", (panel_rect.left + 14, panel_rect.top + 7),
                  self.small_font, _MUTED)

        details = {
            CONTINUE_RUN: summary[0] if summary else "",
            START_RUN: (
                "Abandon the current run and draft a new team."
                if continuing
                else "Set the saved run aside and draft a new team."
                if self._blocked_save()
                else "Draft your team and begin a new run."
            ),
            ABANDON_SAVE: "Set the saved run aside (its file is kept) and start fresh.",
            "SETTINGS": "Edit your team name and colors.",
            HOW_TO_PLAY: "Learn the basics: the run, the shop, offense vs defense, and players.",
            "CREATE PROFILE": "Create a team before starting a run.",
            "QUIT": "Exit the game.",
        }
        menu_active = not self.confirm_replace
        for index, button in enumerate(buttons):
            active = menu_active and (
                (self.keyboard_focus and button.focused)
                or self.hover_index == index
                or self.pressed_index == index
            )
            pressed = menu_active and self.pressed_index == index
            if first_difficulty <= index < first_difficulty + len(FootballAIDifficulty):
                self._draw_difficulty(surface, button, active, pressed)
            elif button.variant == "continue":
                self._draw_continue_button(surface, button, details[CONTINUE_RUN], active, pressed)
            elif button.variant == "abandon":
                continue  # drawn on its notice panel below
            else:
                self._draw_menu_button(surface, button, details[button.label], active, pressed)

        if show_notice:
            self._draw_save_notice(
                surface, notice_rect, notice,
                next((b for b in buttons if b.variant == "abandon"), None),
                menu_active, buttons,
            )
        elif self.profile_error or (self.theme.warning and self.menu_state):
            warning = pygame.Rect(40, warning_y, 650, 96 if continuing else 105)
            pygame.draw.rect(surface, "#182c40", warning, border_radius=6)
            pygame.draw.rect(surface, "#e29c82", warning, 2, border_radius=6)
            top = warning.top
            if self.profile_error:
                draw_text(surface, "PROFILE COULD NOT LOAD", (54, top + 9),
                          self.small_font, pygame.Color("#ffb4a3"))
                draw_text(surface, "Resolve the saved file outside the game; it will not be overwritten.",
                          (54, top + 31), self.detail_font, _TEXT)
                _marquee(surface, self.profile_error,
                         pygame.Rect(54, top + 57, warning.width - 28, 27),
                         self.detail_font, _MUTED)
            else:
                draw_text(surface, "COLOR FALLBACK", (54, top + 9),
                          self.small_font, pygame.Color("#ffb4a3"))
                _marquee(surface, self.theme.warning or "",
                         pygame.Rect(54, top + 34, warning.width - 28, 30),
                         self.detail_font, _TEXT)

        footer = pygame.Rect(40, 642, 1200, 49)
        pygame.draw.rect(surface, "#0b223c", footer, border_radius=5)
        pygame.draw.rect(surface, _EDGE, footer, 2, border_radius=5)
        pygame.draw.circle(surface, self.theme.primary, (62, footer.centery), 8)
        active_index = self.focus_index if self.keyboard_focus else self.hover_index
        active_button = (
            buttons[active_index]
            if active_index is not None and 0 <= active_index < len(buttons) else None
        )
        if active_button and active_button.enabled:
            message = details.get(active_button.label, "Select the local opponent's difficulty.")
        else:
            message = "Choose a difficulty, then start a new run."
        _marquee(surface, message, pygame.Rect(80, 650, 1128, 32), self.detail_font, _TEXT)
        if self.confirm_replace and summary is not None:
            self._draw_replace_confirmation(
                surface, f"Your current run ({summary[1]}) will be lost."
            )
        elif self.confirm_replace and self._blocked_save():
            self._draw_replace_confirmation(
                surface, "The saved run will be set aside; its file is kept."
            )
        else:
            self.confirm_replace = False

    def _draw_save_notice(
        self, surface: pygame.Surface, rect: pygame.Rect, notice: MenuSaveNotice,
        abandon: Button | None, menu_active: bool, buttons: list[Button],
    ) -> None:
        pygame.draw.rect(surface, "#182c40", rect, border_radius=6)
        pygame.draw.rect(surface, "#e29c82", rect, 2, border_radius=6)
        text_width = rect.width - 28 - (abandon.rect.width + 14 if abandon else 0)
        draw_text(surface, notice.title, (rect.left + 14, rect.top + 9),
                  self.small_font, pygame.Color("#ffb4a3"))
        lines = _wrap(notice.message, self.detail_font, text_width)[:3]
        for index, line in enumerate(lines):
            draw_text(surface, line, (rect.left + 14, rect.top + 31 + index * 21),
                      self.detail_font, _TEXT)
        if abandon is None:
            return
        index = buttons.index(abandon)
        active = menu_active and (
            (self.keyboard_focus and abandon.focused)
            or self.hover_index == index or self.pressed_index == index
        )
        button_rect = abandon.rect.move(0, 2 if menu_active and self.pressed_index == index else 0)
        fill = pygame.Color("#c2412d") if active else pygame.Color("#3a2430")
        pygame.draw.rect(surface, fill, button_rect, border_radius=5)
        pygame.draw.rect(surface, "#e29c82", button_rect, 2, border_radius=5)
        label = self.small_font.render(ABANDON_SAVE, True, _TEXT)
        surface.blit(label, label.get_rect(center=button_rect.center))

    def _draw_replace_confirmation(self, surface: pygame.Surface, message: str) -> None:
        entries = (
            MenuEntry(CANCEL, self._cancel_replace, "popup-primary"),
            MenuEntry(START_NEW_RUN, self._confirm_replace, "popup-danger"),
        )
        buttons = draw_menu_panel(
            surface, REPLACE_TITLE, message, entries,
            focus_index=self.focus_index if self.focus_index < len(entries) else 0,
            hover_index=self.hover_index, pressed_index=self.pressed_index,
            width=460, button_width=380,
        )
        self._set_buttons(buttons)

    def _draw_menu_button(self, surface: pygame.Surface, button: Button,
                          detail: str, active: bool, pressed: bool) -> None:
        rect = button.rect.move(0, 2 if pressed else 0)
        compact = rect.height < 70
        fill = self.theme.primary if active and button.enabled else pygame.Color("#102e4a")
        text = readable_ink(fill) if active and button.enabled else _TEXT
        if not button.enabled:
            fill, text = pygame.Color("#122638"), pygame.Color("#8093a4")
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, _EDGE, rect, 2, border_radius=6)
        if active and button.enabled:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-4, -4), 3, border_radius=5)
            pygame.draw.rect(surface, self.theme.primary, rect.inflate(-10, -10), 2, border_radius=4)
        narrow = rect.width < 300
        if narrow:
            detail = _SHORT_DETAILS.get(button.label, detail)
        if self.keyboard_focus and button.focused and button.enabled and not narrow:
            focus_label = self.small_font.render("FOCUS", True, text)
            surface.blit(focus_label, (rect.right - focus_label.get_width() - 18,
                                       rect.top + (8 if compact else 13)))
        draw_text(surface, button.label, (rect.left + 25, rect.top + (4 if compact else 8)),
                  self.menu_font, text)
        draw_text(surface, detail, (rect.left + 26, rect.top + (34 if compact else 43)),
                  self.detail_font, text)

    def _draw_continue_button(self, surface: pygame.Surface, button: Button,
                              summary: str, active: bool, pressed: bool) -> None:
        """Always lit in the team color; the focus ring marks keyboard/hover state."""
        rect = button.rect.move(0, 2 if pressed else 0)
        fill = self.theme.primary
        ink = readable_ink(fill)
        pygame.draw.rect(surface, "#061629", rect.move(0, 4), border_radius=7)
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, self.theme.secondary, (rect.left, rect.top + 10, 8, rect.height - 20))
        pygame.draw.rect(surface, ink if active else _EDGE, rect, 3 if active else 2, border_radius=6)
        if active:
            pygame.draw.rect(surface, fill, rect.inflate(-10, -10), 2, border_radius=4)
        tag = self.small_font.render("RESUME", True, fill)
        tag_rect = tag.get_rect().inflate(16, 6)
        tag_rect.topright = (rect.right - 16, rect.top + 12)
        pygame.draw.rect(surface, ink, tag_rect, border_radius=4)
        surface.blit(tag, tag.get_rect(center=tag_rect.center))
        draw_text(surface, button.label, (rect.left + 25, rect.top + 10), self.menu_font, ink)
        _marquee(surface, summary, pygame.Rect(rect.left + 26, rect.top + 48, rect.width - 52, 26),
                 self.badge_font, ink)

    def _draw_difficulty(self, surface: pygame.Surface, button: Button,
                         active: bool, pressed: bool) -> None:
        rect = button.rect.move(0, 2 if pressed else 0)
        selected = button.variant == "primary"
        fill = self.theme.primary if selected or active else pygame.Color("#0a2037")
        text = readable_ink(fill) if selected or active else _TEXT
        pygame.draw.rect(surface, fill, rect, border_radius=4)
        pygame.draw.rect(surface, _EDGE, rect, 2, border_radius=4)
        if active:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-4, -4), 2, border_radius=3)
        if self.keyboard_focus and button.focused:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-10, -10), 1, border_radius=2)
        label = self.small_font.render(button.label, True, text)
        surface.blit(label, label.get_rect(center=rect.center))
        if selected:
            pygame.draw.line(surface, text, (rect.left + 12, rect.bottom - 6),
                             (rect.right - 12, rect.bottom - 6), 2)

    def _select_difficulty(self, difficulty: FootballAIDifficulty) -> None:
        self.difficulty = difficulty


def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
