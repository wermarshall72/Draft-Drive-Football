from collections.abc import Callable

import pygame

from src.profile import COLOR_BY_ID, COLOR_CHOICES, ProfileError, TeamProfile
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

SaveProfile = Callable[[str, str, str], None]


class ProfileScreen(Screen):
    """Create or edit the shared team profile without changing it until saved."""

    def __init__(
        self,
        theme: Theme,
        profile: TeamProfile | None,
        navigate: Navigate,
        quit_application: Quit,
        save_profile: SaveProfile,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.profile = profile
        self.save_profile = save_profile
        self.name = ""
        self.primary_color_id = "crimson"
        self.secondary_color_id = "navy"
        self.selected_side = "primary"
        self.error: str | None = None

    def on_enter(self) -> None:
        self.name = self.profile.team_name if self.profile else ""
        self.primary_color_id = self.profile.primary_color_id if self.profile else "crimson"
        self.secondary_color_id = self.profile.secondary_color_id if self.profile else "navy"
        self.selected_side = "primary"
        self.error = None
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.hover_index = next(
                (
                    index for index, button in enumerate(self.buttons)
                    if button.enabled and button.rect.collidepoint(event.pos)
                ),
                None,
            )
            return
        if self.buttons and self.focus_index == 0:
            if event.type == pygame.TEXTINPUT:
                self.name += event.text
                self.error = None
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.name = self.name[:-1]
                    self.error = None
                    return
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._move_focus(1)
                    return
                if event.key == pygame.K_SPACE:
                    return
        super().handle_event(event)

    def _select_side(self, side: str) -> None:
        self.selected_side = side

    def _select_color(self, color_id: str) -> None:
        if self.selected_side == "primary":
            self.primary_color_id = color_id
        else:
            self.secondary_color_id = color_id
        self.error = None

    def _save(self) -> None:
        try:
            self.save_profile(self.name, self.primary_color_id, self.secondary_color_id)
        except (ProfileError, OSError) as error:
            self.error = str(error)

    def draw(self, surface: pygame.Surface) -> None:
        title = "Edit team profile" if self.profile else "Create team profile"
        layout = self._header(surface, title, "TEAM PROFILE", self.name or "NEW TEAM")
        panel = layout.content
        draw_panel(surface, panel, self.theme, fill=self.theme.panel)

        left = panel.left + 24
        top = panel.top + 22
        left_width = min(360, panel.width // 3)
        palette_left = left + left_width + 32
        palette_width = panel.right - 24 - palette_left
        draw_text(surface, "TEAM NAME", (left, top), self._small_font, self.theme.muted)
        name_rect = pygame.Rect(left, top + 23, left_width, 44)
        buttons = [
            Button(self.name or "TYPE TEAM NAME", lambda: None, name_rect),
        ]
        draw_text(
            surface, "Type a name; choose a side, then a color", (left, top + 88),
            self._body_font, self.theme.muted,
        )
        for index, (side, color_id) in enumerate(
            (("primary", self.primary_color_id), ("secondary", self.secondary_color_id))
        ):
            color = COLOR_BY_ID[color_id]
            rect = pygame.Rect(left, top + 116 + index * 52, left_width, 42)
            buttons.append(
                Button(
                    f"{side.upper()}  /  {color.display_name.upper()}",
                    lambda side=side: self._select_side(side),
                    rect,
                    variant="primary" if self.selected_side == side else "quiet",
                )
            )
        draw_text(
            surface, f"SELECT {self.selected_side.upper()} COLOR",
            (palette_left, top), self._small_font, self.theme.muted,
        )
        gap = 7
        cell_width = (palette_width - gap * 5) // 6
        for index, color in enumerate(COLOR_CHOICES):
            row, column = divmod(index, 6)
            rect = pygame.Rect(
                palette_left + column * (cell_width + gap),
                top + 25 + row * 43,
                cell_width,
                36,
            )
            buttons.append(
                Button(
                    color.display_name.upper(),
                    lambda color_id=color.id: self._select_color(color_id),
                    rect,
                    variant="quiet",
                )
            )

        if self.error:
            draw_wrapped_text(
                surface, self.error,
                pygame.Rect(left, panel.bottom - 128, panel.width - 48, 65),
                self._small_font, self.theme.danger,
            )
        buttons.extend(
            (
                Button(
                    "SAVE PROFILE", self._save,
                    pygame.Rect(panel.right - 360, panel.bottom - 55, 160, 36),
                    variant="primary",
                ),
                Button(
                    "CANCEL", lambda: self.navigate("main_menu"),
                    pygame.Rect(panel.right - 184, panel.bottom - 55, 160, 36),
                ),
            )
        )
        self._set_buttons(buttons)
        self._draw_buttons(surface)
        for index, color in enumerate(COLOR_CHOICES):
            rect = buttons[index + 3].rect
            pygame.draw.circle(
                surface, pygame.Color(color.hex_value), (rect.left + 9, rect.top + 9), 5,
            )
