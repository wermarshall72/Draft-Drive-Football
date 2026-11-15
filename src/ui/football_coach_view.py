"""Coach selection presentation and scouting popups."""

from collections.abc import Callable, Sequence

import pygame

from src.engine.football import FootballPosition
from src.engine.football_coaches import FootballCoachProfile, FootballCoachSide
from src.engine.football_controller import FootballGameControllerState
from src.ui.coach_art import draw_playbook_mark, draw_recruiting_table
from src.ui.football_display import _coach_perk_summary
from src.ui.football_draft_interaction import CoachInspection
from src.ui.text import fit_text as _fit_text
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_text, draw_wrapped_text

_STAFF_PAPER = pygame.Color("#a1a8a3")
_STAFF_INK = pygame.Color("#182620")
_STAFF_MUTED = pygame.Color("#303c35")
_COACH_CHALK = pygame.Color("#f5ead1")
_STAFF_CARD = pygame.Color("#242d30")
_STAFF_PERK = pygame.Color("#354044")
_STAFF_POSITIVE = pygame.Color("#9fe4ad")
_STAFF_NEGATIVE = pygame.Color("#ff9d98")


def coach_popup_rect(buttons: Sequence[Button], index: int) -> pygame.Rect:
    row = buttons[index].rect
    return pygame.Rect(row.left + 54, buttons[index // 3 * 3 + 1].rect.top,
                       row.width - 54, 423)


class FootballCoachView:
    def __init__(
        self, theme: Theme, team_name: str, inspection: CoachInspection,
        focus_index: int, hover_index: int | None,
        title_font: pygame.font.Font, name_font: pygame.font.Font,
        label_font: pygame.font.Font, body_font: pygame.font.Font,
        detail_font: pygame.font.Font, stat_font: pygame.font.Font,
        small_font: pygame.font.Font, main_font: pygame.font.Font,
        button_font: pygame.font.Font, choose_coach: Callable[[int], None],
    ) -> None:
        self.theme = theme
        self.team_name = team_name
        self.coach_inspection = inspection
        self.focus_index = focus_index
        self.hover_index = hover_index
        self._coach_title_font = title_font
        self._staff_name_font = name_font
        self._staff_label_font = label_font
        self._staff_body_font = body_font
        self._staff_detail_font = detail_font
        self._staff_stat_font = stat_font
        self._staff_small_font = small_font
        self._staff_main_font = main_font
        self._staff_button_font = button_font
        self.choose_coach = choose_coach

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        draw_recruiting_table(surface)
        draw_text(surface, "Recruiting  /  Staff", (40, 12), self._staff_label_font, _COACH_CHALK)
        draw_text(surface, "Build your staff", (38, 29), self._coach_title_font, _COACH_CHALK)
        draw_text(
            surface, "Hover or tab to scout a coach.", (42, 101),
            self._staff_body_font, _COACH_CHALK,
        )
        team = _fit_text(self.team_name.upper(), self._staff_small_font, 250)
        draw_text(surface, team, (820, 46), self._staff_small_font, _COACH_CHALK)

    def draw(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        coach_pairs = state.team_builder.coach_offer
        gap = 16
        card_top = content.top + 12
        card_height = 546
        card_width = (content.width - gap * 2) // 3
        buttons: list[Button] = []
        for index, pair in enumerate(coach_pairs):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                card_top + (4 if index != 1 else 0),
                card_width,
                card_height - (4 if index != 1 else 0),
            )
            focused = self.focus_index // 3 == index and self.focus_index < 9
            pygame.draw.rect(surface, "#171b17", rect.move(5, 7), border_radius=14)
            pygame.draw.rect(surface, "#7d8580", rect.move(2, 3), border_radius=14)
            pygame.draw.rect(surface, _STAFF_PAPER, rect, border_radius=14)
            pygame.draw.rect(surface, "#151a18" if focused else "#68736c", rect,
                             4 if focused else 1, border_radius=14)
            if focused:
                pygame.draw.rect(surface, self.theme.primary, rect.inflate(-4, -4), 2,
                                 border_radius=12)
                progress = min(1.0, max(0.0, (
                    pygame.time.get_ticks() - self.coach_inspection.focus_changed_at
                ) / 140))
                pygame.draw.line(
                    surface, self.theme.primary, (rect.left + 18, rect.top + 3),
                    (rect.left + 18 + round((rect.width - 36) * progress), rect.top + 3), 2,
                )
            pygame.draw.rect(surface, "#6b746c", (rect.left + 18, rect.top - 5, 54, 10),
                             border_radius=4)
            pygame.draw.circle(surface, "#5d5948", (rect.left + 45, rect.top), 3)
            draw_text(
                surface, f"Staff 0{index + 1}", (rect.left + 18, rect.top + 12),
                self._staff_main_font, _STAFF_INK,
            )
            draw_text(surface, "Position modifiers", (rect.right - 132, rect.top + 15),
                      self._staff_label_font, _STAFF_MUTED)
            draw_text(surface, "Locked for the run", (rect.left + 18, rect.bottom - 82),
                      self._staff_label_font, _STAFF_MUTED)
            button_rect = pygame.Rect(
                rect.left + 17, rect.bottom - 55, rect.width - 34, 40,
            )
            buttons.append(
                Button(
                    f"CHOOSE STAFF 0{index + 1}",
                    lambda choice=index: self.choose_coach(choice),
                    button_rect,
                    variant="coach-select",
                )
            )
            for side_index, coach in enumerate((pair.offense, pair.defense)):
                row = pygame.Rect(
                    rect.left + 12, rect.top + 47 + side_index * 211,
                    rect.width - 24, 198,
                )
                button_index = index * 3 + side_index + 1
                if self.coach_inspection.hover_index == button_index and not self.coach_inspection.keyboard:
                    pygame.draw.rect(surface, readable_ink(self.theme.secondary), row, 5,
                                     border_radius=10)
                    pygame.draw.rect(surface, self.theme.secondary, row, 2, border_radius=10)
                mark = pygame.Rect(row.left - 4, row.top + 44, 64, 64)
                draw_playbook_mark(surface, mark, offense=side_index == 0,
                                   color=self._coach_mark_color(index, buttons[index * 3]))
                text_x = row.left + 100
                draw_text(
                    surface, coach.side.value.title(), (text_x, row.top + 24),
                    self._staff_label_font, _STAFF_INK,
                )
                draw_text(
                    surface, coach.name, (text_x, row.top + 45),
                    self._staff_name_font, _STAFF_INK,
                )
                if self.coach_inspection.keyboard and self.focus_index == button_index:
                    pygame.draw.line(
                        surface, _STAFF_INK, (text_x, row.top + 77),
                        (text_x + self._staff_name_font.size(coach.name)[0], row.top + 77), 2,
                    )
                    draw_text(surface, "SCOUTING", (text_x, row.top + 158),
                              self._staff_small_font, _STAFF_INK)
                for position_index, (position, modifier) in enumerate(
                    coach.position_modifiers.items()
                ):
                    x = text_x + (position_index % 2) * 120
                    y = row.top + 96 + (position_index // 2) * 25
                    draw_text(
                        surface,
                        f"{_coach_position_label(position)} {round(modifier * 100):+d}%",
                        (x, y), self._staff_stat_font,
                        _STAFF_MUTED if modifier == 0 else _STAFF_INK,
                    )
                buttons.append(
                    Button(
                        f"INSPECT {coach.side.value.upper()} {index + 1}",
                        lambda: None, row, variant="coach-inspect",
                    )
                )
        return buttons

    def _coach_button_active(self, index: int, button: Button) -> bool:
        return button.enabled and (
            self.focus_index == index or self.hover_index == index
            or (self.focus_index < 9 and self.focus_index // 3 == index // 3)
        )

    def _coach_mark_color(self, staff_index: int, button: Button) -> pygame.Color:
        return (
            self.theme.primary if self._coach_button_active(staff_index * 3, button)
            else self.theme.secondary
        )

    def draw_details(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        coach: FootballCoachProfile,
        *,
        staff_index: int,
        buttons: Sequence[Button],
    ) -> None:
        pygame.draw.rect(surface, "#111b17", rect.move(5, 7), border_radius=14)
        pygame.draw.rect(surface, _STAFF_CARD, rect, border_radius=14)
        keyboard_focus = (
            self.coach_inspection.keyboard
            and self.focus_index < len(buttons)
            and buttons[self.focus_index].variant == "coach-inspect"
        )
        pygame.draw.rect(surface, readable_ink(self.theme.secondary), rect, 5, border_radius=14)
        pygame.draw.rect(surface, self.theme.secondary, rect, 2, border_radius=14)
        if keyboard_focus:
            pygame.draw.rect(surface, "#ffffff", rect.inflate(-12, -12), 1, border_radius=9)
        mark = pygame.Rect(rect.left + 13, rect.top + 15, 58, 58)
        pygame.draw.rect(surface, "#a1a8a3", mark, border_radius=10)
        draw_playbook_mark(surface, mark.inflate(-5, -5),
                           offense=coach.side is FootballCoachSide.OFFENSE,
                           color=self._coach_mark_color(staff_index, buttons[staff_index * 3]))
        draw_text(
            surface, coach.side.value.title(), (rect.left + 84, rect.top + 17),
            self._staff_label_font, _COACH_CHALK,
        )
        draw_text(surface, coach.name, (rect.left + 84, rect.top + 37),
                  self._staff_main_font, _COACH_CHALK)
        if keyboard_focus:
            draw_text(surface, "Keyboard scouting", (rect.left + 84, rect.top + 61),
                      self._staff_label_font, _COACH_CHALK)
        left = rect.left + 16
        y = rect.top + 88
        draw_text(surface, "Position modifiers", (left, y), self._staff_main_font, _COACH_CHALK)
        for offset, (position, modifier) in enumerate(coach.position_modifiers.items()):
            draw_text(
                surface, f"{_coach_position_label(position)} {round(modifier * 100):+d}%",
                (left + (offset % 2) * 140, y + 21 + (offset // 2) * 23),
                self._staff_stat_font,
                _STAFF_POSITIVE if modifier > 0 else _STAFF_NEGATIVE if modifier < 0
                else _COACH_CHALK,
            )
        perk_rect = pygame.Rect(left, rect.top + 157, rect.width - 32, 135)
        pygame.draw.rect(surface, _STAFF_PERK, perk_rect, border_radius=8)
        draw_text(surface, "Perk", (left + 10, perk_rect.top + 6),
                  self._staff_main_font, _COACH_CHALK)
        draw_wrapped_text(
            surface, _coach_perk_summary(coach),
            pygame.Rect(left + 10, perk_rect.top + 25, perk_rect.width - 20, 105),
            self._staff_detail_font, _COACH_CHALK, line_gap=1,
        )
        action_y = rect.top + 298
        draw_text(
            surface,
            "How position modifiers apply",
            (left, action_y),
            self._staff_main_font,
            _COACH_CHALK,
        )
        draw_wrapped_text(
            surface,
            "Modifiers apply per player; total power varies with roster stats, "
            "partnerships, fatigue, and other effects.",
            pygame.Rect(left, action_y + 23, rect.width - 32, rect.bottom - action_y - 32),
            self._staff_detail_font,
            "#c1c6c4",
            line_gap=1,
        )

    def draw_inspection(
        self, surface: pygame.Surface, state: FootballGameControllerState,
        buttons: Sequence[Button],
    ) -> None:
        index = self.focus_index if self.coach_inspection.keyboard else self.coach_inspection.hover_index
        if (
            index is not None
            and index < len(buttons)
            and buttons[index].variant == "coach-inspect"
        ):
            pair = state.team_builder.coach_offer[index // 3]
            coach = pair.offense if index % 3 == 1 else pair.defense
            self.draw_details(
                surface, coach_popup_rect(buttons, index), coach,
                staff_index=index // 3, buttons=buttons,
            )

    def draw_button(
        self, surface: pygame.Surface, button: Button, index: int, *, pressed: bool,
    ) -> None:
        active = self._coach_button_active(index, button)
        pressed = pressed and button.enabled
        rect = button.rect.move(0, 2) if pressed else button.rect
        fill = self.theme.primary if active else (
            pygame.Color("#c9ceca") if button.enabled else pygame.Color("#8b928d")
        )
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, readable_ink(fill), rect, 1, border_radius=8)
        if button.focused:
            pygame.draw.rect(surface, "#111416", rect.inflate(6, 6), 3, border_radius=11)
            pygame.draw.rect(surface, "#ffffff", rect.inflate(4, 4), 1, border_radius=10)
        if pressed:
            pygame.draw.line(surface, readable_ink(fill), (rect.left + 12, rect.top + 4),
                             (rect.right - 12, rect.top + 4), 2)
        label = self._staff_button_font.render(
            button.label.title(), True, readable_ink(fill),
        )
        surface.blit(label, label.get_rect(center=rect.center))


def _coach_position_label(position: FootballPosition) -> str:
    labels = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-LINE",
        FootballPosition.D_LINE: "D-LINE",
        FootballPosition.LINEBACKERS: "LB",
        FootballPosition.CORNERBACKS: "CB",
        FootballPosition.SAFETIES: "S",
    }
    return labels[position]
