"""Full-screen eight-team playoff bracket, in the match-screen kit style.

Columns on the 1280x720 logical surface: quarterfinals (four games), semifinals
(two), championship (one), and the champion slot. The human team's rows carry
the team accent; its next game has a gold outline and a NEXT tag. Undecided
slots read TBD. The footer holds one primary button: the next playoff shop, or
Return to Main Menu once the run has ended.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from src.engine.football_playoffs import (
    FootballPlayoffBracketState,
    FootballPlayoffGame,
    FootballPlayoffRound,
)
from src.ui.football_ui_kit import (
    MATCH_DIM, MATCH_GOLD, MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT, MATCH_TEXT, blit_text, kit_button,
    match_font, mix, plain_font, stadium_backdrop, team_accent,
)
from src.ui.text import fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button

HEADER = pygame.Rect(20, 16, 1240, 52)
BOARD = pygame.Rect(20, 80, 1240, 562)
FOOTER = pygame.Rect(20, 654, 1240, 48)
PRIMARY_RECT = pygame.Rect(0, 0, 380, 48)
PRIMARY_RECT.midtop = (FOOTER.centerx, FOOTER.top)
PAUSE_RECT = pygame.Rect(HEADER.right - 120, HEADER.top, 120, 36)

COLUMN_WIDTH = 262
COLUMN_LEFTS = (44, 354, 664, 974)
CHAMPION_WIDTH = 242
COLUMN_TOP = BOARD.top + 58
COLUMN_HEIGHT = BOARD.bottom - 18 - COLUMN_TOP
ROW_HEIGHT = 34
GAME_HEIGHT = ROW_HEIGHT * 2 + 2

ROUND_TITLES = {
    FootballPlayoffRound.QUARTERFINAL: "QUARTERFINALS",
    FootballPlayoffRound.SEMIFINAL: "SEMIFINALS",
    FootballPlayoffRound.CHAMPIONSHIP: "CHAMPIONSHIP",
}
SHOP_LABELS = {
    FootballPlayoffRound.QUARTERFINAL: "OPEN QUARTERFINAL SHOP",
    FootballPlayoffRound.SEMIFINAL: "OPEN SEMIFINAL SHOP",
    FootballPlayoffRound.CHAMPIONSHIP: "OPEN CHAMPIONSHIP SHOP",
}
RETURN_TO_MENU = "RETURN TO MAIN MENU"


def game_rect(playoff_round: FootballPlayoffRound, slot: int) -> pygame.Rect:
    """The box of one bracket game; later rounds center between their feeders."""
    count = 4 >> (playoff_round.value - 1)
    band = COLUMN_HEIGHT / count
    center_y = COLUMN_TOP + band * (slot + 0.5)
    rect = pygame.Rect(COLUMN_LEFTS[playoff_round.value - 1], 0, COLUMN_WIDTH, GAME_HEIGHT)
    rect.centery = round(center_y)
    return rect


def champion_rect() -> pygame.Rect:
    rect = pygame.Rect(COLUMN_LEFTS[3], 0, CHAMPION_WIDTH, 150)
    rect.centery = game_rect(FootballPlayoffRound.CHAMPIONSHIP, 0).centery
    return rect


class FootballPlayoffBracketView:
    """Draw the bracket and return its buttons."""

    def draw(
        self,
        surface: pygame.Surface,
        bracket: FootballPlayoffBracketState,
        theme: Theme,
        *,
        record: str,
        primary: Callable[[], None],
        request_exit: Callable[[], None] | None,
    ) -> list[Button]:
        accent = team_accent(theme.primary_accent)
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        self._draw_header(surface, bracket, record)
        self._draw_board(surface, bracket, accent)
        self._draw_footer_note(surface, bracket, record)
        next_round = None if bracket.human_eliminated else bracket.next_human_round
        label = SHOP_LABELS[next_round] if next_round is not None else RETURN_TO_MENU
        buttons = [kit_button(label, primary, PRIMARY_RECT, variant="kit-primary")]
        if request_exit is not None:
            buttons.append(Button("PAUSE", request_exit, PAUSE_RECT, variant="run-pause"))
        return buttons

    # -- header ------------------------------------------------------------------

    @staticmethod
    def _draw_header(surface, bracket: FootballPlayoffBracketState, record: str) -> None:
        title = blit_text(surface, plain_font(30), "PLAYOFFS", MATCH_TEXT, HEADER,
                          topleft=(HEADER.left, HEADER.top))
        blit_text(surface, plain_font(30), " · 8-TEAM BRACKET", MATCH_MUTED, HEADER,
                  topleft=(title.right, HEADER.top))
        human = bracket.team(bracket.human_seed)
        line = (f"SINGLE ELIMINATION  ·  {human.name.upper()} IS THE #{human.seed} SEED"
                f"  ·  REGULAR SEASON {record}")
        font = plain_font(13)
        box = pygame.Rect(HEADER.left + 2, HEADER.top + 34, PAUSE_RECT.left - 20 - HEADER.left, 18)
        blit_text(surface, font, fit_text(line, font, box.width), MATCH_DIM, box, topleft=box.topleft)

    # -- board -------------------------------------------------------------------

    def _draw_board(self, surface, bracket: FootballPlayoffBracketState, accent) -> None:
        pygame.draw.rect(surface, MATCH_INK, BOARD.move(0, 4), border_radius=14)
        pygame.draw.rect(surface, MATCH_PANEL, BOARD, border_radius=14)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, BOARD, 2, border_radius=14)
        titles = (*ROUND_TITLES.values(), "CHAMPION")
        for index, title in enumerate(titles):
            width = CHAMPION_WIDTH if index == 3 else COLUMN_WIDTH
            column = pygame.Rect(COLUMN_LEFTS[index], BOARD.top + 16, width, 24)
            blit_text(surface, match_font(14), title, MATCH_MUTED, column, midleft=column.midleft)
            pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (column.left, column.bottom + 4),
                             (column.right, column.bottom + 4))

        self._draw_connectors(surface, bracket)
        next_round = None if bracket.human_eliminated else bracket.next_human_round
        for playoff_round in FootballPlayoffRound:
            games = {game.slot: game for game in bracket.round_games(playoff_round)}
            for slot in range(4 >> (playoff_round.value - 1)):
                rect = game_rect(playoff_round, slot)
                game = games.get(slot)
                is_next = (
                    game is not None and next_round is playoff_round
                    and game.has(bracket.human_seed)
                )
                self._draw_game(surface, rect, bracket, game, accent, is_next)
        self._draw_champion(surface, bracket, accent)

    @staticmethod
    def _draw_connectors(surface, bracket: FootballPlayoffBracketState) -> None:
        for playoff_round in (FootballPlayoffRound.QUARTERFINAL, FootballPlayoffRound.SEMIFINAL):
            next_round = FootballPlayoffRound(playoff_round + 1)
            for slot in range(4 >> playoff_round.value):
                target = game_rect(next_round, slot)
                mid_x = (game_rect(playoff_round, 0).right + target.left) // 2
                for feeder in (2 * slot, 2 * slot + 1):
                    source = game_rect(playoff_round, feeder)
                    points = [(source.right, source.centery), (mid_x, source.centery),
                              (mid_x, target.centery), (target.left, target.centery)]
                    pygame.draw.lines(surface, MATCH_PANEL_EDGE_SOFT, False, points, 2)
        final = game_rect(FootballPlayoffRound.CHAMPIONSHIP, 0)
        champion = champion_rect()
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (final.right, final.centery),
                         (champion.left, final.centery), 2)

    def _draw_game(self, surface, rect: pygame.Rect, bracket: FootballPlayoffBracketState,
                   game: FootballPlayoffGame | None, accent, is_next: bool) -> None:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=8)
        edge = MATCH_GOLD if is_next else MATCH_PANEL_EDGE_SOFT
        pygame.draw.rect(surface, edge, rect, 2, border_radius=8)
        top = pygame.Rect(rect.left, rect.top + 1, rect.width, ROW_HEIGHT)
        bottom = pygame.Rect(rect.left, top.bottom, rect.width, ROW_HEIGHT)
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (rect.left + 8, top.bottom),
                         (rect.right - 8, top.bottom))
        if game is None:
            for row in (top, bottom):
                blit_text(surface, match_font(13), "TBD", MATCH_DIM, row,
                          midleft=(row.left + 44, row.centery))
            return
        for row, seed in ((top, game.high_seed), (bottom, game.low_seed)):
            self._draw_row(surface, row, bracket, game, seed, accent)
        if is_next:
            tag = pygame.Rect(0, 0, 50, 18)
            tag.bottomright = (rect.right - 8, rect.top - 3)
            pygame.draw.rect(surface, MATCH_GOLD, tag, border_radius=5)
            blit_text(surface, match_font(11), "NEXT", MATCH_INK, tag, center=tag.center)

    @staticmethod
    def _draw_row(surface, row: pygame.Rect, bracket: FootballPlayoffBracketState,
                  game: FootballPlayoffGame, seed: int, accent) -> None:
        team = bracket.team(seed)
        lost = game.decided and game.winner_seed != seed
        won = game.decided and game.winner_seed == seed
        if team.is_human:
            band = row.inflate(-6, -6)
            pygame.draw.rect(surface, mix(accent, MATCH_PANEL_DEEP, 0.78), band, border_radius=5)
            pygame.draw.rect(surface, accent, (band.left, band.top, 4, band.height), border_radius=2)
        badge = pygame.Rect(row.left + 10, 0, 26, 22)
        badge.centery = row.centery
        pygame.draw.rect(surface, MATCH_PANEL if not team.is_human else accent, badge, border_radius=5)
        seed_ink = MATCH_INK if team.is_human else MATCH_MUTED
        blit_text(surface, match_font(12), str(seed), seed_ink, badge, center=badge.center)
        ink = MATCH_DIM if lost else MATCH_TEXT
        score = game.score_for(seed)
        score_text = "" if score is None else str(score)
        score_font = plain_font(18)
        score_width = score_font.size("00")[0] + (22 if game.overtime else 0)
        name_box = pygame.Rect(badge.right + 8, row.top, row.right - 12 - score_width - badge.right - 16,
                               row.height)
        name_font = plain_font(16)
        blit_text(surface, name_font, fit_text(team.name.upper(), name_font, name_box.width), ink,
                  name_box, midleft=(name_box.left, row.centery))
        if score_text:
            text = score_text + (" OT" if game.overtime and won else "")
            blit_text(surface, score_font, text, MATCH_GOLD if won else MATCH_DIM, row,
                      midright=(row.right - 12, row.centery))

    @staticmethod
    def _draw_champion(surface, bracket: FootballPlayoffBracketState, accent) -> None:
        rect = champion_rect()
        seed = bracket.champion_seed
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=12)
        edge = MATCH_GOLD if seed is not None else MATCH_PANEL_EDGE
        pygame.draw.rect(surface, edge, rect, 2, border_radius=12)
        _draw_trophy(surface, (rect.centerx, rect.top + 40),
                     MATCH_GOLD if seed is not None else MATCH_PANEL_EDGE_SOFT)
        if seed is None:
            blit_text(surface, plain_font(22), "TBD", MATCH_DIM, rect, center=(rect.centerx, rect.top + 104))
            return
        team = bracket.team(seed)
        font = plain_font(22)
        blit_text(surface, font, fit_text(team.name.upper(), font, rect.width - 24),
                  accent if team.is_human else MATCH_TEXT, rect, center=(rect.centerx, rect.top + 96))
        blit_text(surface, match_font(12), f"#{seed} SEED", MATCH_MUTED, rect,
                  center=(rect.centerx, rect.top + 124))

    # -- footer ------------------------------------------------------------------

    @staticmethod
    def _draw_footer_note(surface, bracket: FootballPlayoffBracketState, record: str) -> None:
        if bracket.champion_seed == bracket.human_seed:
            note = "NATIONAL CHAMPIONS"
        elif bracket.human_eliminated:
            note = "ELIMINATED"
        else:
            note = "ONE LOSS ENDS THE RUN  ·  RIVALS GET TOUGHER EACH ROUND"
        font = match_font(12)
        box = pygame.Rect(FOOTER.left, FOOTER.top, PRIMARY_RECT.left - FOOTER.left - 20, FOOTER.height)
        blit_text(surface, font, fit_text(note, font, box.width), MATCH_DIM, box,
                  midleft=(box.left + 4, PRIMARY_RECT.centery))
        cap = pygame.Rect(0, 0, font.size("ENTER")[0] + 14, 22)
        cap.midleft = (PRIMARY_RECT.right + 16, PRIMARY_RECT.centery)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, cap, border_radius=5)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, cap, 1, border_radius=5)
        blit_text(surface, font, "ENTER", MATCH_DIM, cap, center=cap.center)


def _draw_trophy(surface: pygame.Surface, center: tuple[int, int], color: pygame.Color) -> None:
    """A simple cup: bowl, handles, stem, and base."""
    cx, cy = center
    bowl = pygame.Rect(0, 0, 40, 30)
    bowl.midtop = (cx, cy - 22)
    pygame.draw.rect(surface, color, bowl, border_bottom_left_radius=18, border_bottom_right_radius=18)
    for side in (-1, 1):
        handle = pygame.Rect(0, 0, 16, 18)
        handle.center = (cx + side * 22, cy - 12)
        pygame.draw.ellipse(surface, color, handle, 3)
    pygame.draw.rect(surface, color, (cx - 4, bowl.bottom - 2, 8, 12))
    pygame.draw.rect(surface, color, (cx - 16, bowl.bottom + 9, 32, 7), border_radius=3)
