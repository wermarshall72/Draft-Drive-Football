"""Settings: the team profile (name, colors, helmet preview), audio volumes, and tips.

Team name and colors change only on SAVE PROFILE (CANCEL discards them). The
volume sliders save instantly through the application's ``AudioBinding`` and are
not undone by CANCEL. The GAMEPLAY card (SHOW TIPS AGAIN) shows once a profile exists.
"""

from collections.abc import Callable

import pygame

from src.profile import COLOR_BY_ID, COLOR_CHOICES, ProfileError, TeamProfile
from src.ui.football_ui_kit import (
    MATCH_DIM, MATCH_FOCUS, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE,
    MATCH_PANEL_EDGE_SOFT, MATCH_PANEL_HIGH, MATCH_TEXT, PaintedButton, blit_text, draw_card,
    draw_message_banner, kit_button, match_font, mix, plain_font, stadium_backdrop, team_accent,
)
from src.ui.screens import Navigate, Quit, Screen
from src.ui.team_helmet import draw_team_helmet
from src.ui.text import fit_text
from src.ui.theme import Theme
from src.ui.volume_slider import (
    BLOCK_HEIGHT, AudioBinding, SliderInput, audio_sliders, local_audio_binding,
    match_slider_palette,
)
from src.ui.widgets import Button

SaveProfile = Callable[[str, str, str], None]
RESET_TIPS = "SHOW TIPS AGAIN"
TIPS_RESET_NOTE = "Tips will pop up again."
TIPS_LABEL = "Help tips"
TIPS_SUBLINE = "Pop-up hints for new players"
NAME_PLACEHOLDER = "Type a team name"
SWATCH_HINT = "Hover a color to see its name"
SOUND_NOTE = "Sound coming soon"
SAVE_PROFILE = "SAVE PROFILE"
CANCEL = "CANCEL"
SETTINGS_TITLE = "SETTINGS"
CREATE_TITLE = "CREATE YOUR TEAM"
HEADER_TAIL = "  ·  Team, colors, and audio"
FOOTER_HINT = "VOLUME SAVES INSTANTLY · ESC TO CANCEL"

# Page layout at 1280x720, matching the run screens (How to Play's margins).
MARGIN = 28
HEADER_TOP = 16
CARDS_TOP = 100
FOOTER_HEIGHT = 42  # the shop's bottom-row buttons
FOOTER_BOTTOM_GAP = 22  # below the footer, as in the shop (656 + 42 = 698)
GAP = 20  # between cards
PAD = 22  # inside cards (lines up with the card headings)
CARD_BODY = 52  # card top to its first row, below the heading
HELMET_HEIGHT = 108
SWATCH_COLUMNS = 10
SWATCH_GAP = 8
ERROR_HEIGHT = 52
# Button order: name field, the two side toggles, then the 30 swatches.
FIRST_SWATCH = 3


def side_label(side: str, color_id: str) -> str:
    return f"{side.upper()} · {COLOR_BY_ID[color_id].display_name.upper()}"


class ProfileScreen(Screen):
    """Create or edit the shared team profile without changing it until saved."""

    def __init__(
        self,
        theme: Theme,
        profile: TeamProfile | None,
        navigate: Navigate,
        quit_application: Quit,
        save_profile: SaveProfile,
        *,
        reset_tips: Callable[[], None] | None = None,
        audio: AudioBinding | None = None,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.profile = profile
        self.save_profile = save_profile
        self.reset_tips = reset_tips
        self.audio = audio or local_audio_binding()
        self.slider_input = SliderInput()
        self.tips_reset = False
        self.name = ""
        self.primary_color_id = "crimson"
        self.secondary_color_id = "navy"
        self.selected_side = "primary"
        self.error: str | None = None
        self.hover_swatch: str | None = None
        self._swatch_rects: list[tuple[str, pygame.Rect]] = []
        # Drawn bounds of the last preview, for tests and layout checks.
        self.helmet_rect: pygame.Rect | None = None
        self.letter_rect: pygame.Rect | None = None
        self.error_rect: pygame.Rect | None = None

    def on_enter(self) -> None:
        self.name = self.profile.team_name if self.profile else ""
        self.primary_color_id = self.profile.primary_color_id if self.profile else "crimson"
        self.secondary_color_id = self.profile.secondary_color_id if self.profile else "navy"
        self.selected_side = "primary"
        self.error = None
        self.tips_reset = False
        self.hover_swatch = None
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def on_exit(self) -> None:
        self.slider_input.release()
        super().on_exit()

    # -- state -------------------------------------------------------------------

    @property
    def active_color_id(self) -> str:
        return self.primary_color_id if self.selected_side == "primary" else self.secondary_color_id

    @property
    def other_color_id(self) -> str:
        return self.secondary_color_id if self.selected_side == "primary" else self.primary_color_id

    def swatch_caption(self) -> str:
        color_id = self.hover_swatch
        if color_id is None:
            focused = self.focus_index - FIRST_SWATCH
            if 0 <= focused < len(COLOR_CHOICES) and self.focus_index < len(self.buttons):
                color_id = COLOR_CHOICES[focused].id
        if color_id is None:
            return SWATCH_HINT
        name = COLOR_BY_ID[color_id].display_name
        if color_id == self.other_color_id:
            other = "secondary" if self.selected_side == "primary" else "primary"
            return f"{name} · used for {other}"
        return name

    # -- input -------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        slider = self.slider_input.handle_event(event, self.buttons, self.focus_index)
        if slider is not None:
            self._focus(slider)
            return
        if event.type == pygame.MOUSEMOTION:
            self.hover_index = next(
                (
                    index for index, button in enumerate(self.buttons)
                    if button.enabled and button.rect.collidepoint(event.pos)
                ),
                None,
            )
            self.hover_swatch = next(
                (color_id for color_id, rect in self._swatch_rects if rect.collidepoint(event.pos)),
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

    def _reset_tips(self) -> None:
        if self.reset_tips is not None:
            self.reset_tips()
            self.tips_reset = True

    # -- drawing -----------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        page = surface.get_rect()
        primary = pygame.Color(COLOR_BY_ID[self.primary_color_id].hex_value)
        accent = team_accent(primary)
        self._draw_header(surface, page, primary, accent)

        footer_top = page.bottom - FOOTER_BOTTOM_GAP - FOOTER_HEIGHT
        cards_bottom = footer_top - GAP + 4
        content = pygame.Rect(MARGIN, CARDS_TOP, page.width - MARGIN * 2, cards_bottom - CARDS_TOP)
        team = pygame.Rect(content.left, content.top, round((content.width - GAP) * 0.55),
                           content.height)
        column = pygame.Rect(team.right + GAP, content.top, content.right - team.right - GAP,
                             content.height)

        buttons = self._team_card(surface, team, accent)
        audio_card, sliders = self._audio_card(surface, column, accent)
        buttons.extend(sliders)
        column_bottom = audio_card.bottom
        if self.profile is not None and self.reset_tips is not None:
            area = pygame.Rect(column.left, audio_card.bottom + GAP, column.width, 0)
            reset, gameplay_card = self._gameplay_card(surface, area, accent)
            buttons.append(reset)
            column_bottom = gameplay_card.bottom
        self.error_rect = pygame.Rect(
            column.left, max(column_bottom + GAP, cards_bottom - ERROR_HEIGHT),
            column.width, ERROR_HEIGHT,
        )
        if self.error:
            draw_message_banner(surface, self.error_rect, self.error, danger=True)

        save = pygame.Rect(page.right - MARGIN - 200, footer_top, 200, FOOTER_HEIGHT)
        cancel = pygame.Rect(save.left - 12 - 150, footer_top, 150, FOOTER_HEIGHT)
        hint_font = plain_font(12)
        hint_box = pygame.Rect(MARGIN, footer_top, cancel.left - 16 - MARGIN, FOOTER_HEIGHT)
        blit_text(surface, hint_font, fit_text(FOOTER_HINT, hint_font, hint_box.width), MATCH_MUTED,
                  hint_box, midright=(hint_box.right, hint_box.centery))
        buttons.append(kit_button(CANCEL, lambda: self.navigate("main_menu"), cancel))
        buttons.append(kit_button(SAVE_PROFILE, self._save, save, variant="kit-primary"))
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_header(self, surface: pygame.Surface, page: pygame.Rect,
                     primary: pygame.Color, accent: pygame.Color) -> None:
        """The run screens' header: big title and accent dash, then a team subline."""
        header = pygame.Rect(MARGIN, HEADER_TOP, page.width - MARGIN * 2, 70)
        title = blit_text(surface, plain_font(32), self.title, MATCH_TEXT, header,
                          topleft=header.topleft)
        pygame.draw.rect(surface, accent, (title.right + 10, title.centery - 2, 34, 4),
                         border_radius=2)
        sub_y = header.top + 46
        swatch = pygame.Rect(header.left, sub_y + 1, 12, 12)
        pygame.draw.rect(surface, primary, swatch, border_radius=3)
        pygame.draw.rect(surface, mix(accent, MATCH_TEXT, 0.4), swatch, 1, border_radius=3)
        font = plain_font(14)
        name = fit_text((self.name.strip() or "NEW TEAM").upper(), font, 420)
        name_rect = blit_text(surface, font, name, MATCH_TEXT, header,
                              topleft=(swatch.right + 8, sub_y - 2))
        blit_text(surface, font, HEADER_TAIL, MATCH_MUTED, header,
                  topleft=(name_rect.right, sub_y - 2))

    @property
    def title(self) -> str:
        return SETTINGS_TITLE if self.profile else CREATE_TITLE

    def _team_card(self, surface: pygame.Surface, card: pygame.Rect,
                   accent: pygame.Color) -> list[Button]:
        draw_card(surface, card, "TEAM", accent)
        y = card.top + CARD_BODY
        x = card.left + PAD
        inner = card.width - PAD * 2
        primary = pygame.Color(COLOR_BY_ID[self.primary_color_id].hex_value)
        secondary = pygame.Color(COLOR_BY_ID[self.secondary_color_id].hex_value)

        helmet_box = pygame.Rect(x, y, 140, HELMET_HEIGHT)
        self.helmet_rect, self.letter_rect = draw_team_helmet(
            surface, helmet_box, self.name, primary, secondary, height=HELMET_HEIGHT,
        )
        field_left = helmet_box.right + PAD
        field = pygame.Rect(field_left, y + 42, card.right - PAD - field_left, 44)
        blit_text(surface, plain_font(12), "TEAM NAME", MATCH_MUTED, card,
                  bottomleft=(field.left, field.top - 7))
        buttons: list[Button] = [
            PaintedButton(self.name or NAME_PLACEHOLDER, lambda: None, field,
                          painter=self._paint_name_field),
        ]

        track = pygame.Rect(x, helmet_box.bottom + 24, inner, 44)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, track, border_radius=10)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, track, 1, border_radius=10)
        inside = track.inflate(-8, -8)
        half = inside.width // 2
        for index, (side, color_id) in enumerate(
            (("primary", self.primary_color_id), ("secondary", self.secondary_color_id))
        ):
            rect = pygame.Rect(inside.left + index * half, inside.top,
                               half if index == 0 else inside.width - half, inside.height)
            buttons.append(PaintedButton(
                side_label(side, color_id), lambda side=side: self._select_side(side), rect,
                painter=lambda s, b, h, p, side=side, color_id=color_id:
                    self._paint_toggle(s, b, h, side, color_id),
            ))

        grid_top = track.bottom + 26
        caption_font = match_font(13, False)
        available = card.bottom - PAD - caption_font.get_height() - 10 - grid_top
        size = max(12, min(
            (inner - SWATCH_GAP * (SWATCH_COLUMNS - 1)) // SWATCH_COLUMNS,
            (available - SWATCH_GAP * 2) // 3,
        ))
        # Spread the columns so the grid's right edge lines up with the toggle's.
        step = (inner - size) / (SWATCH_COLUMNS - 1)
        self._swatch_rects = []
        for index, color in enumerate(COLOR_CHOICES):
            row, column = divmod(index, SWATCH_COLUMNS)
            rect = pygame.Rect(x + round(column * step),
                               grid_top + row * (size + SWATCH_GAP), size, size)
            self._swatch_rects.append((color.id, rect))
            buttons.append(PaintedButton(
                color.display_name.upper(),
                lambda color_id=color.id: self._select_color(color_id),
                rect,
                enabled=color.id != self.other_color_id,
                painter=lambda s, b, h, p, color_id=color.id: self._paint_swatch(s, b, h, color_id),
            ))
        grid_bottom = grid_top + 3 * size + 2 * SWATCH_GAP
        blit_text(surface, caption_font, fit_text(self.swatch_caption(), caption_font, inner),
                  MATCH_MUTED, card, topleft=(x, grid_bottom + 10))
        return buttons

    def _audio_card(
        self, surface: pygame.Surface, column: pygame.Rect, accent: pygame.Color,
    ) -> tuple[pygame.Rect, list[Button]]:
        note_font = match_font(13, False)
        height = CARD_BODY + BLOCK_HEIGHT * 2 + 18 + 12 + note_font.get_height() + PAD
        card = pygame.Rect(column.left, column.top, column.width, height)
        draw_card(surface, card, "AUDIO", accent)
        x = card.left + PAD
        music = pygame.Rect(x, card.top + CARD_BODY, card.width - PAD * 2, BLOCK_HEIGHT)
        effects = music.move(0, BLOCK_HEIGHT + 18)
        sliders = audio_sliders(self.audio, music, effects, match_slider_palette(),
                                dragging=self.slider_input.dragging)
        blit_text(surface, note_font, SOUND_NOTE, MATCH_MUTED, card,
                  topleft=(x, effects.bottom + 12))
        return card, list(sliders)

    def _gameplay_card(
        self, surface: pygame.Surface, area: pygame.Rect, accent: pygame.Color,
    ) -> tuple[Button, pygame.Rect]:
        card = pygame.Rect(area.left, area.top, area.width, CARD_BODY + FOOTER_HEIGHT + PAD)
        draw_card(surface, card, "GAMEPLAY", accent)
        x, y = card.left + PAD, card.top + CARD_BODY
        rect = pygame.Rect(card.right - PAD - 190, y, 190, FOOTER_HEIGHT)
        text_room = rect.left - 12 - x
        label_font, note_font = plain_font(16), match_font(13, False)
        blit_text(surface, label_font, fit_text(TIPS_LABEL, label_font, text_room), MATCH_TEXT,
                  card, topleft=(x, y))
        subline = TIPS_RESET_NOTE if self.tips_reset else TIPS_SUBLINE
        blit_text(surface, note_font, fit_text(subline, note_font, text_room), MATCH_MUTED, card,
                  topleft=(x, y + 22))
        return kit_button(RESET_TIPS, self._reset_tips, rect), card

    # -- painters ----------------------------------------------------------------

    def _paint_name_field(self, surface, button, hovered, pressed) -> None:
        rect = button.rect
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=8)
        if button.focused:
            pygame.draw.rect(surface, MATCH_FOCUS, rect, 2, border_radius=8)
        else:
            edge = MATCH_PANEL_EDGE if hovered else MATCH_PANEL_EDGE_SOFT
            pygame.draw.rect(surface, edge, rect, 1, border_radius=8)
        font = plain_font(18)
        text_left = rect.left + 14
        room = rect.width - 30
        if self.name:
            shown = self.name
            while len(shown) > 1 and font.size(shown)[0] > room:
                shown = shown[1:]  # keep the end visible while typing
            label = blit_text(surface, font, shown, MATCH_TEXT, rect,
                              midleft=(text_left, rect.centery))
        else:
            label = blit_text(surface, font, NAME_PLACEHOLDER, MATCH_DIM, rect,
                              midleft=(text_left, rect.centery))
        if button.focused and (pygame.time.get_ticks() // 530) % 2 == 0:
            caret_x = label.right + 2 if self.name else text_left
            pygame.draw.line(surface, MATCH_TEXT, (caret_x, rect.centery - 11),
                             (caret_x, rect.centery + 11), 2)

    def _paint_toggle(self, surface, button, hovered, side: str, color_id: str) -> None:
        rect = button.rect
        chosen = self.selected_side == side
        lit = hovered or button.focused
        if button.focused:
            pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=10)
        if chosen:
            # The kit's "kit-toggle-on" look.
            pygame.draw.rect(surface, mix(MATCH_PANEL_HIGH, MATCH_FOCUS, 0.22 if lit else 0.14),
                             rect, border_radius=7)
            pygame.draw.rect(surface, MATCH_FOCUS, rect, 2, border_radius=7)
        elif lit:
            pygame.draw.rect(surface, MATCH_PANEL_HIGH, rect, border_radius=7)
        font = match_font(15)
        text = fit_text(button.label, font, rect.width - 40)
        total = 12 + 9 + font.size(text)[0]
        left = rect.centerx - total // 2
        dot = (left + 6, rect.centery)
        pygame.draw.circle(surface, pygame.Color(COLOR_BY_ID[color_id].hex_value), dot, 6)
        pygame.draw.circle(surface, MATCH_PANEL_EDGE, dot, 6, 1)
        blit_text(surface, font, text, MATCH_TEXT if chosen else MATCH_MUTED, rect,
                  midleft=(left + 21, rect.centery))

    def _paint_swatch(self, surface, button, hovered, color_id: str) -> None:
        rect = button.rect
        color = pygame.Color(COLOR_BY_ID[color_id].hex_value)
        if not button.enabled:
            color = mix(color, MATCH_PANEL, 0.72)
        elif hovered:
            rect = rect.inflate(2, 2)
        pygame.draw.rect(surface, color, rect, border_radius=6)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 1, border_radius=6)
        if not button.enabled:
            # A thin slash reads as "taken" even when the dimmed color is hard to see.
            pygame.draw.line(surface, MATCH_MUTED, (rect.left + 7, rect.bottom - 8),
                             (rect.right - 8, rect.top + 7), 2)
        selected = color_id == self.active_color_id
        if selected:
            pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=9)
        if button.focused:
            grow = 12 if selected else 6
            pygame.draw.rect(surface, MATCH_FOCUS, rect.inflate(grow, grow), 2, border_radius=11)
