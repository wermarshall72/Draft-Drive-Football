"""Player draft presentation, scouting details, and selection controls."""

from collections.abc import Callable
from decimal import Decimal

import pygame

from src.engine.football import FootballPosition
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_player_catalog import (
    MAX_COMBINED_PLAYER_MODIFIER, PARTNERSHIP_BONUS, player_type_for_id,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER, FootballPlayerCandidate
from src.ui.coach_art import draw_recruiting_table
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_draft_interaction import PlayerInspection
from src.ui.player_art import draw_draft_player
from src.ui.text import fit_text as _fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_text, draw_wrapped_text

_STAFF_PAPER = pygame.Color("#a1a8a3")
_STAFF_INK = pygame.Color("#182620")
_COACH_GOLD = pygame.Color("#f1ce7b")
_COACH_CHALK = pygame.Color("#f5ead1")
_DRAFT_PURPLE = pygame.Color("#a600e8")


class FootballPlayerDraftView:
    def __init__(
        self, theme: Theme, inspection: PlayerInspection, focus_index: int,
        title_font: pygame.font.Font, name_font: pygame.font.Font,
        label_font: pygame.font.Font, small_font: pygame.font.Font,
        stat_font: pygame.font.Font, detail_font: pygame.font.Font,
        choose_player: Callable[[FootballPosition, int], None],
    ) -> None:
        self.theme = theme
        self.player_inspection = inspection
        self.focus_index = focus_index
        self._draft_title_font = title_font
        self._draft_name_font = name_font
        self._draft_label_font = label_font
        self._draft_small_font = small_font
        self._draft_stat_font = stat_font
        self._draft_detail_font = detail_font
        self.choose_player = choose_player

    def draw(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        builder = state.team_builder
        completed = len(builder.selected_players)
        required = builder.required_position
        current_label = (
            _draft_position_label(required) if required is not None else "Complete"
        )
        draw_text(
            surface,
            f"Pick {completed + 1} of {len(PLAYER_DRAFT_ORDER)}  ·  {current_label}",
            (content.left + 2, content.top),
            self._draft_label_font,
            _COACH_CHALK,
        )
        remaining_label = f"{len(PLAYER_DRAFT_ORDER) - completed} picks remaining"
        draw_text(
            surface,
            remaining_label,
            (content.right - self._draft_small_font.size(remaining_label)[0],
             content.top + 2),
            self._draft_small_font,
            _COACH_CHALK,
        )

        gap = 5
        cell_width = (
            content.width - gap * (len(PLAYER_DRAFT_ORDER) - 1)
        ) // len(PLAYER_DRAFT_ORDER)
        progress_top = content.top + 22
        progress_height = 58
        for index, position in enumerate(PLAYER_DRAFT_ORDER):
            rect = pygame.Rect(
                content.left + index * (cell_width + gap),
                progress_top,
                cell_width,
                progress_height,
            )
            selected = builder.selected_players.get(position)
            current = position is builder.required_position
            fill = _STAFF_PAPER if selected else (
                pygame.Color("#253932") if current else pygame.Color("#202a27")
            )
            pygame.draw.rect(surface, fill, rect, border_radius=6)
            pygame.draw.rect(
                surface,
                _DRAFT_PURPLE if current else pygame.Color("#64706a"),
                rect,
                2 if current else 1,
                border_radius=6,
            )
            text_color = _STAFF_INK if selected else _COACH_CHALK
            status = "Drafted" if selected else ("Current pick" if current else "Up next")
            draw_text(
                surface,
                _draft_position_label(position),
                (rect.left + 7, rect.top + 4),
                self._draft_label_font,
                text_color,
            )
            draw_text(
                surface,
                status,
                (rect.left + 7, rect.top + 21),
                self._draft_small_font,
                _STAFF_INK if selected else (
                    _DRAFT_PURPLE if current else pygame.Color("#c0c6c2")
                ),
            )
            if selected:
                draw_wrapped_text(
                    surface,
                    selected.name,
                    pygame.Rect(rect.left + 7, rect.top + 37, rect.width - 14, 18),
                    self._draft_small_font,
                    _STAFF_INK,
                    line_gap=0,
                )

        offers = tuple(candidate for candidate in builder.current_offer
                       if isinstance(candidate, FootballPlayerCandidate))
        gap = 16
        card_top = progress_top + progress_height + 10
        card_width = (content.width - gap * 2) // 3
        choice_bottom = content.bottom - 8
        self.player_inspection.card_rects = [
            pygame.Rect(
                content.left + index * (card_width + gap),
                card_top,
                card_width,
                choice_bottom - card_top,
            )
            for index in range(len(offers))
        ]
        inspected_index = self.focus_index if self.player_inspection.keyboard else self.player_inspection.hover_index
        self.player_inspection.detail_rect = (
            self.popup_rect(inspected_index, surface.get_size())
            if inspected_index is not None and 0 <= inspected_index < len(offers)
            else None
        )
        buttons: list[Button] = []
        for index, (candidate, rect) in enumerate(zip(offers, self.player_inspection.card_rects)):
            title_width = rect.width - 80
            draw_text(
                surface,
                _fit_text(candidate.name, self._draft_name_font, title_width),
                (rect.left + 4, rect.top + 1),
                self._draft_name_font,
                _COACH_CHALK,
            )
            name_width = 62
            name_rect = pygame.Rect(
                rect.right - name_width - 4,
                rect.top + 2,
                name_width,
                27,
            )
            pygame.draw.rect(surface, "#202a27", name_rect, border_radius=7)
            pygame.draw.rect(
                surface, "#64706a", name_rect, 1, border_radius=7
            )
            draw_text(
                surface,
                _draft_position_label(candidate.position).upper(),
                (name_rect.left + 7, name_rect.top + 6),
                self._draft_small_font,
                _COACH_CHALK,
            )

            if inspected_index == index:
                pygame.draw.line(
                    surface,
                    _DRAFT_PURPLE,
                    (rect.left + 4, rect.top + 31),
                    (rect.left + min(title_width, 174), rect.top + 31),
                    3,
                )
            portrait = pygame.Rect(rect.centerx - 130, rect.top + 40, 260, 345)
            draw_draft_player(surface, portrait, self.theme.primary, self.theme.secondary)

            strip = pygame.Rect(rect.left + 4, rect.bottom - 105, rect.width - 8, 62)
            pygame.draw.rect(surface, "#111b20", strip, border_radius=10)
            pygame.draw.rect(surface, "#718087", strip, 2, border_radius=10)
            player = candidate.player
            metrics = (
                ("Power", str(player.power)),
                ("Volatility", _draft_percentage(player.volatility)),
                ("Stamina", _draft_percentage(player.stamina)),
            )
            for stat_index, (label, value) in enumerate(metrics):
                stat_width = strip.width // 3
                x = strip.left + 12 + stat_index * stat_width
                draw_text(
                    surface,
                    label,
                    (x, strip.top + 7),
                    self._draft_small_font,
                    pygame.Color("#c0c9c8"),
                )
                draw_text(
                    surface,
                    value,
                    (x, strip.top + 27),
                    self._draft_stat_font,
                    _COACH_CHALK,
                )
                if stat_index < len(metrics) - 1:
                    pygame.draw.line(
                        surface,
                        pygame.Color("#4b5a5f"),
                        (strip.left + (stat_index + 1) * stat_width, strip.top + 10),
                        (strip.left + (stat_index + 1) * stat_width, strip.bottom - 10),
                        1,
                    )
            buttons.append(Button(
                f"DRAFT {candidate.position.value}",
                lambda choice=index, position=candidate.position: self.choose_player(position, choice),
                pygame.Rect(rect.left + 10, rect.bottom - 40, rect.width - 20, 34),
                variant="draft-select",
            ))
        return buttons

    def popup_rect(
        self,
        index: int,
        surface_size: tuple[int, int],
    ) -> pygame.Rect:
        choice = self.player_inspection.card_rects[index]
        width = min(460, surface_size[0] - 32)
        height = min(320, choice.height - 140)
        left = min(
            max(choice.centerx - width // 2, 16),
            surface_size[0] - width - 16,
        )
        strip_top = choice.bottom - 105
        top = min(choice.top + 46, strip_top - height - 12)
        top = max(12, top)
        return pygame.Rect(left, top, width, height)

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        draw_recruiting_table(surface)
        draw_text(
            surface,
            "Build your roster",
            (38, 8),
            self._draft_title_font,
            _COACH_CHALK,
        )

    def draw_details(
        self, surface: pygame.Surface, rect: pygame.Rect,
        candidate: FootballPlayerCandidate,
        *,
        keyboard_inspected: bool = False,
    ) -> None:
        if candidate.player.player_type_id is None:
            raise RuntimeError("Drafted players must have a catalog player type.")
        player_type = player_type_for_id(candidate.player.player_type_id)
        pygame.draw.rect(surface, "#111b20", rect.move(5, 7), border_radius=10)
        pygame.draw.rect(surface, "#1c2729", rect, border_radius=10)
        pygame.draw.rect(surface, "#718087", rect, 1, border_radius=10)
        pygame.draw.rect(surface, _DRAFT_PURPLE, rect, 2, border_radius=10)
        if keyboard_inspected:
            pygame.draw.rect(surface, "#ffffff", rect.inflate(-10, -10), 1, border_radius=7)
        draw_text(
            surface,
            "KEYBOARD SCOUTING" if keyboard_inspected else "SCOUTING",
            (rect.left + 16, rect.top + 9),
            self._draft_small_font,
            _COACH_GOLD,
        )
        draw_text(
            surface,
            _fit_text(candidate.name, self._draft_name_font, rect.width - 145),
            (rect.left + 16, rect.top + 25),
            self._draft_name_font,
            _COACH_CHALK,
        )
        position_label = _draft_position_label(candidate.position).upper()
        draw_text(
            surface,
            position_label,
            (rect.right - self._draft_label_font.size(position_label)[0] - 16,
             rect.top + 31),
            self._draft_label_font,
            _COACH_CHALK,
        )
        stats = (
            f"Power {candidate.player.power}   ·   "
            f"Volatility {_draft_percentage(candidate.player.volatility)}   ·   "
            f"Stamina {_draft_percentage(candidate.player.stamina)}"
        )
        draw_text(
            surface,
            stats,
            (rect.left + 16, rect.top + 57),
            self._draft_small_font,
            pygame.Color("#c1c6c4"),
        )
        divider_y = rect.top + 79
        pygame.draw.line(
            surface, pygame.Color("#566367"),
            (rect.left + 16, divider_y), (rect.right - 16, divider_y), 1,
        )
        column_width = (rect.width - 48) // 2
        left = rect.left + 16
        right = left + column_width + 16
        section_y = rect.top + 88
        body_top = rect.top + 110
        body_height = rect.bottom - body_top - 12
        draw_text(
            surface,
            "Partnership",
            (left, section_y),
            self._draft_label_font,
            _COACH_GOLD,
        )
        draw_text(
            surface,
            "Perk",
            (right, section_y),
            self._draft_label_font,
            _COACH_GOLD,
        )
        if player_type.perk is not None:
            status = "PLANNED · INACTIVE"
            draw_text(
                surface,
                status,
                (rect.right - 16 - self._draft_small_font.size(status)[0],
                 section_y + 2),
                self._draft_small_font,
                pygame.Color("#c1c6c4"),
            )
        if player_type.partner_position is None:
            partnership = "None. No partnership bonus."
        else:
            partnership = (
                f"{_POSITION_LABELS[player_type.partner_position]} partner: "
                f"+{PARTNERSHIP_BONUS:.0%} contribution when both players contribute "
                "to the same play. Combined coach and partnership contribution "
                f"tops out at {MAX_COMBINED_PLAYER_MODIFIER:.0%} of base."
            )
        draw_wrapped_text(
            surface,
            partnership,
            pygame.Rect(left, body_top, column_width, body_height),
            self._draft_detail_font,
            _COACH_CHALK,
            line_gap=0,
        )
        if player_type.perk is None:
            draw_text(
                surface,
                "None. This player type has no perk.",
                (right, body_top),
                self._draft_detail_font,
                _COACH_CHALK,
            )
        else:
            perk = player_type.perk
            perk_lines = (
                f"Name: {perk.name}",
                f"Trigger: {perk.trigger}",
                f"Effect: {perk.effect}",
                f"Duration: {perk.duration}  ·  Reset: {perk.reset}",
                f"Dependency: {perk.dependency}",
            )
            detail_y = body_top
            for line in perk_lines:
                wrapped_lines = _wrapped_line_count(
                    line, self._draft_detail_font, column_width
                )
                draw_wrapped_text(
                    surface,
                    line,
                    pygame.Rect(
                        right,
                        detail_y,
                        column_width,
                        rect.bottom - 12 - detail_y,
                    ),
                    self._draft_detail_font,
                    _COACH_CHALK,
                    line_gap=0,
                )
                detail_y += wrapped_lines * self._draft_detail_font.get_height() + 1


def _wrapped_line_count(text: str, font: pygame.font.Font, width: int) -> int:
    lines = 0
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > width:
            lines += 1
            current = word
        else:
            current = candidate
    return lines + int(bool(current))


def _draft_percentage(value: float) -> str:
    percentage = format(Decimal(str(value)) * 100, "f")
    if "." in percentage:
        percentage = percentage.rstrip("0").rstrip(".")
    return f"{percentage}%"


def _draft_position_label(position: FootballPosition) -> str:
    labels = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line",
        FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebackers",
        FootballPosition.CORNERBACKS: "Cornerbacks",
        FootballPosition.SAFETIES: "Safeties",
    }
    return labels[position]


