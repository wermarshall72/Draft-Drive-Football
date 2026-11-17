"""Card-based player draft presentation."""

from collections.abc import Callable
from decimal import Decimal

import pygame

from src.engine.football import FootballPosition
from src.engine.football_appearance import FootballPlayerAppearance, POSITION_ART
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER, FootballPlayerCandidate
from src.ui.coach_fonts import staff_font
from src.ui.football_draft_interaction import PlayerInspection
from src.ui.football_display import player_partnership_text, player_perk_text
from src.ui.player_art import draw_draft_player
from src.ui.text import draw_complete_wrapped_text, wrap_text_lines
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_text

_TEXT = pygame.Color("#edf3fa")
_MUTED = pygame.Color("#b5c5d5")
_EDGE = pygame.Color("#52697c")
_PERK_BOX = pygame.Color("#35404b")


class FootballPlayerDraftView:
    def __init__(
        self, theme: Theme, inspection: PlayerInspection, focus_index: int,
        title_font: pygame.font.Font, name_font: pygame.font.Font,
        label_font: pygame.font.Font, small_font: pygame.font.Font,
        stat_font: pygame.font.Font, detail_font: pygame.font.Font,
        choose_player: Callable[[FootballPosition, FootballPlayerCandidate, FootballPlayerAppearance], None],
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

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        surface.fill("#07111b")

    def draw(
        self, surface: pygame.Surface, content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        builder = state.team_builder
        completed = len(builder.selected_players)
        sidebar = pygame.Rect(content.left, content.top, 290, content.height)
        pygame.draw.rect(surface, "#102b47", sidebar, border_radius=8)
        pygame.draw.rect(surface, "#365574", sidebar, 2, border_radius=8)
        draw_text(surface, "BUILD YOUR ROSTER", (sidebar.left + 15, sidebar.top + 16),
                  staff_font(25, semibold=True), _TEXT)
        position = builder.required_position
        current = _draft_position_label(position) if position is not None else "Complete"
        draw_text(surface, f"Pick {completed + 1} of 8: {current}",
                  (sidebar.left + 16, sidebar.top + 58), self._draft_label_font, _TEXT)
        draw_text(surface, f"{8 - completed} picks remaining",
                  (sidebar.left + 16, sidebar.top + 79), self._draft_small_font, _MUTED)
        draw_text(surface, "DRAFT TRACKER", (sidebar.left + 16, sidebar.top + 126),
                  self._draft_label_font, _MUTED)
        for index, position in enumerate(PLAYER_DRAFT_ORDER):
            rect = pygame.Rect(sidebar.left + 12, sidebar.top + 151 + index * 57,
                               sidebar.width - 24, 50)
            selected = builder.selected_players.get(position)
            is_current = position is builder.required_position
            fill = _PERK_BOX if selected else ("#214363" if is_current else "#091c30")
            pygame.draw.rect(surface, fill, rect,
                             border_radius=5)
            pygame.draw.rect(surface, self.theme.primary if is_current else _EDGE, rect,
                             2 if is_current else 1, border_radius=5)
            draw_text(surface, _draft_position_label(position).upper(),
                      (rect.left + 9, rect.top + 5), self._draft_label_font, _TEXT)
            status = "Drafted" if selected else ("Current pick" if is_current else "Up next")
            draw_text(surface, status, (rect.right - 9 - self._draft_small_font.size(status)[0],
                                       rect.top + 6), self._draft_small_font, _MUTED)
            if selected:
                draw_text(surface, selected.name, (rect.left + 9, rect.top + 26),
                          self._draft_small_font, _MUTED)

        offers = tuple(candidate for candidate in builder.current_offer
                       if isinstance(candidate, FootballPlayerCandidate))
        if len(offers) != len(builder.current_offer):
            raise RuntimeError("The controller returned a non-player draft offer.")
        self.player_inspection.set_offers(offers)
        right = sidebar.right + 24
        draw_text(surface, f"DRAFT POOL: {current.upper()}",
                  (right, content.top + 8), self._draft_title_font, _TEXT)
        gap = 12
        card_width = (content.right - right - 2 * gap) // 3
        card_top = content.top + 58
        self.player_inspection.card_rects = [
            pygame.Rect(right + index * (card_width + gap), card_top,
                        card_width, content.bottom - card_top)
            for index in range(len(offers))
        ]
        active = self.player_inspection.active_index(self.focus_index)
        buttons = []
        self.player_inspection.portraits = []
        for index, (candidate, rect) in enumerate(zip(offers, self.player_inspection.card_rects)):
            pygame.draw.rect(surface, "#13283b", rect, border_radius=8)
            pygame.draw.rect(surface, self.theme.primary if active == index else _EDGE,
                             rect, 3 if active == index else 2, border_radius=8)
            if active == index:
                pygame.draw.rect(surface, self.theme.primary_accent, rect.inflate(-6, -6),
                                 1, border_radius=5)
            name_font = self._draft_name_font
            if name_font.size(candidate.name)[0] > rect.width - 24:
                name_font = staff_font(20, semibold=True)
            draw_complete_wrapped_text(surface, candidate.name,
                pygame.Rect(rect.left + 12, rect.top + 10, rect.width - 24, 30),
                name_font, _TEXT, line_gap=0)
            draw_text(surface, _draft_position_label(candidate.position).upper(),
                      (rect.left + 12, rect.top + 39), self._draft_small_font, _MUTED)
            portrait = pygame.Rect(rect.left + 15, rect.top + 57, rect.width - 30, 190)
            appearance = FootballPlayerAppearance(
                POSITION_ART[candidate.position], self.player_inspection.skin_tones[index],
                tuple(self.theme.primary[:3]), tuple(self.theme.secondary[:3]),
            )
            draw_draft_player(surface, portrait, appearance, active == index)
            self.player_inspection.portraits.append((portrait, appearance, active == index))
            strip = pygame.Rect(rect.left + 10, rect.top + 252, rect.width - 20, 52)
            pygame.draw.rect(surface, "#0b1c2b", strip, border_radius=4)
            for column, (label, value) in enumerate((
                ("POWER", str(candidate.player.power)),
                ("VOLATILITY", _draft_percentage(candidate.player.volatility)),
                ("STAMINA", _draft_percentage(candidate.player.stamina)),
            )):
                x = strip.left + 7 + column * (strip.width // 3)
                draw_text(surface, label, (x, strip.top + 5), self._draft_small_font, _MUTED)
                draw_text(surface, value, (x, strip.top + 22), self._draft_label_font, _TEXT)
            if candidate.player.player_type_id is None:
                raise RuntimeError("Drafted players must have a catalog player type.")
            player_type = player_type_for_id(candidate.player.player_type_id)
            partner, explanation = player_partnership_text(player_type)
            draw_text(surface, partner, (rect.left + 12, rect.top + 314),
                      self._draft_label_font, _TEXT)
            if explanation is not None:
                draw_text(surface, explanation,
                          (rect.left + 12, rect.top + 335), self._draft_small_font, _MUTED)
            box = pygame.Rect(rect.left + 10, rect.top + 356, rect.width - 20,
                              rect.height - 410)
            pygame.draw.rect(surface, _PERK_BOX, box, border_radius=5)
            text = player_perk_text(player_type)
            text_rect = box.inflate(-16, -14)
            font = self._draft_detail_font
            for size in (14, 13, 12, 11):
                font = staff_font(size)
                lines = wrap_text_lines(text, font, text_rect.width)
                if len(lines) * font.get_height() <= text_rect.height:
                    break
            draw_complete_wrapped_text(surface, text, text_rect, font, _TEXT, line_gap=0)
            buttons.append(Button(
                f"DRAFT {candidate.position.value}",
                lambda player=candidate, art=appearance: self.choose_player(player.position, player, art),
                pygame.Rect(rect.left + 10, rect.bottom - 42, rect.width - 20, 32),
                variant="draft-select",
            ))
        return buttons


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
