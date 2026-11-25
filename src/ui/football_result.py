"""Full-screen post-game result: scoreboard hero, verdict ribbon, team stats, season tracker.

Layout on the 1280x720 logical surface (see ``HEADER`` .. ``FOOTER``). One layout
serves every result: a regular-season win or loss, Run Over (third loss), the
end of the regular season after game 10 (or its Bye Week, which never shows the
previous match's score or stats), a playoff win, a playoff loss (Eliminated),
and the championship. From game 10 on, the season panel adds the playoff path.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

import pygame

from src.engine.football import FootballMatchState, FootballTeamSide
from src.engine.football_ai_teams import FootballAITeam
from src.engine.football_controller import (
    FootballGameControllerState,
    FootballRunPhase,
    FootballSeasonGame,
    FootballSeasonOutcome,
)
from src.engine.football_playoffs import (
    FootballPlayoffBracketState,
    FootballPlayoffRound,
    game_label,
)
from src.ui.football_ai_team_colors import NEUTRAL_OPPONENT, draw_team_chip, opponent_colors
from src.ui.football_match_events import period_label
from src.ui.football_match_scoreboard import _helmet_sprite
from src.ui.football_result_stats import TeamGameStats, match_team_stats
from src.ui.football_ui_kit import (
    MATCH_DANGER, MATCH_DIM, MATCH_GOLD, MATCH_INK, MATCH_MUTED,
    MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT, MATCH_TEXT,
    PLAY_LINE_PASS, PLAY_LINE_RUN, blit_text, blit_wrapped, draw_message_banner,
    kit_button, match_font, mix, plain_font, stadium_backdrop, team_accent,
)
from src.ui.text import fit_text
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button

HEADER = pygame.Rect(20, 16, 1240, 52)
HERO = pygame.Rect(20, 72, 1240, 190)
RIBBON = pygame.Rect(20, 274, 1240, 44)
STATS = pygame.Rect(20, 330, 760, 310)
SEASON = pygame.Rect(796, 330, 464, 310)
FOOTER = pygame.Rect(20, 654, 1240, 48)
PRIMARY_RECT = pygame.Rect(0, 0, 380, 48)
PRIMARY_RECT.midtop = (FOOTER.centerx, FOOTER.top)
PAUSE_RECT = pygame.Rect(HEADER.right - 120, HEADER.top, 120, 36)

LOSS_TONE = pygame.Color("#8fa6bf")
FIRED_RED = pygame.Color("#d9645b")
COUNT_UP_MS = 700

OPEN_NEXT_SHOP = "OPEN NEXT GAME SHOP"
VIEW_PLAYOFF_BRACKET = "VIEW PLAYOFF BRACKET"
VIEW_BRACKET = "VIEW BRACKET"
RETURN_TO_MENU = "RETURN TO MAIN MENU"
SECONDARY_RECT = pygame.Rect(FOOTER.left, FOOTER.top, 220, 48)


class ResultVariant(Enum):
    REGULAR = "regular"
    FIRED = "fired"
    SEASON_COMPLETE = "season_complete"
    BYE_WEEK = "bye_week"
    PLAYOFF_WIN = "playoff_win"
    ELIMINATED = "eliminated"
    CHAMPION = "champion"


PLAYOFF_VARIANTS = frozenset({
    ResultVariant.PLAYOFF_WIN, ResultVariant.ELIMINATED, ResultVariant.CHAMPION,
})
# Variants whose primary button opens the bracket before the next playoff shop.
BRACKET_NEXT_VARIANTS = frozenset({
    ResultVariant.SEASON_COMPLETE, ResultVariant.BYE_WEEK, ResultVariant.PLAYOFF_WIN,
})


def result_variant(state: FootballGameControllerState) -> ResultVariant:
    if state.phase is FootballRunPhase.FIRED:
        return ResultVariant.FIRED
    if state.phase is FootballRunPhase.ELIMINATED:
        return ResultVariant.ELIMINATED
    if state.phase is FootballRunPhase.CHAMPION:
        return ResultVariant.CHAMPION
    if state.phase is FootballRunPhase.READY_FOR_NEXT_GAME:
        if state.playoff_round is not None:
            return ResultVariant.PLAYOFF_WIN
        if state.playoffs is not None:
            if state.game_number in state.skipped_games:
                return ResultVariant.BYE_WEEK
            return ResultVariant.SEASON_COMPLETE
        return ResultVariant.REGULAR
    raise RuntimeError(f"No result screen for phase {state.phase!r}.")


def _next_rival(bracket: FootballPlayoffBracketState) -> tuple[FootballPlayoffRound, str] | None:
    playoff_round = bracket.next_human_round
    if playoff_round is None:
        return None
    game = bracket.human_game(playoff_round)
    assert game is not None
    return playoff_round, bracket.team(game.opponent_of(bracket.human_seed)).name


def stat_rows(
    team: TeamGameStats, opponent: TeamGameStats
) -> tuple[tuple[str, int | tuple[int, int], int | tuple[int, int], str], ...]:
    """(label, ours, theirs, kind) rows; totals carry (rushing, passing)."""
    return (
        ("TOTAL YARDS", (team.rushing_yards, team.passing_yards),
         (opponent.rushing_yards, opponent.passing_yards), "total"),
        ("RUSHING", team.rushing_yards, opponent.rushing_yards, "run"),
        ("PASSING", team.passing_yards, opponent.passing_yards, "pass"),
        ("PLAYS", team.plays, opponent.plays, "count"),
        ("TURNOVERS", team.turnovers, opponent.turnovers, "turnover"),
        ("LONGEST PLAY", team.longest_play, opponent.longest_play, "long"),
    )


def _row_value(value: int | tuple[int, int]) -> int:
    return sum(value) if isinstance(value, tuple) else value


class FootballResultView:
    """Render a finished game's result and expose the matching next action.

    ``clock`` (milliseconds) drives an optional score count-up; pass ``None``
    to draw final values immediately. The primary button is live on the first
    frame either way.
    """

    def __init__(
        self,
        open_next_shop: Callable[[], None],
        return_to_menu: Callable[[], None],
        request_exit: Callable[[], None],
        *,
        open_bracket: Callable[[], None] = lambda: None,
        clock: Callable[[], int] | None = pygame.time.get_ticks,
    ) -> None:
        self.open_next_shop = open_next_shop
        self.open_bracket = open_bracket
        self.return_to_menu = return_to_menu
        self.request_exit = request_exit
        self.clock = clock
        self._animation_key: tuple | None = None
        self._animation_start = 0

    # -- entry ---------------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
        theme: Theme,
        *,
        error: str | None = None,
    ) -> list[Button]:
        variant = result_variant(state)
        match: FootballMatchState | None = None
        if variant is not ResultVariant.BYE_WEEK:
            match = state.match
            if match is None or match.final_result is None:
                raise RuntimeError("A season result requires the completed match result.")
        accent = team_accent(theme.primary_accent)
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        self._draw_header(surface, state, variant, match)
        if match is None:
            self._draw_bye_hero(surface, state, theme)
        else:
            self._draw_hero(surface, state, match, theme)
        self._draw_ribbon(surface, state, variant)
        if match is None:
            self._draw_bye_panel(surface, state, accent)
        else:
            stats = match_team_stats(match.match_events)
            self._draw_stats(surface, match, stats.team_a, stats.team_b, accent,
                             opponent_colors(state.opponent_team).accent)
        self._draw_season(surface, state, variant, accent)
        if error:
            draw_message_banner(surface, pygame.Rect(FOOTER.left, FOOTER.top, PRIMARY_RECT.left
                                                     - FOOTER.left - 20, FOOTER.height),
                                error, danger=True)
        else:
            self._draw_key_hint(surface)

        if variant is ResultVariant.REGULAR:
            buttons: list[Button] = [
                kit_button(OPEN_NEXT_SHOP, self.open_next_shop, PRIMARY_RECT, variant="kit-primary"),
                Button("PAUSE", self.request_exit, PAUSE_RECT, variant="run-pause"),
            ]
        elif variant in BRACKET_NEXT_VARIANTS:
            buttons = [
                kit_button(VIEW_PLAYOFF_BRACKET, self.open_bracket, PRIMARY_RECT,
                           variant="kit-primary"),
                Button("PAUSE", self.request_exit, PAUSE_RECT, variant="run-pause"),
            ]
        else:
            buttons = [kit_button(RETURN_TO_MENU, self.return_to_menu, PRIMARY_RECT,
                                  variant="kit-primary")]
            if variant is not ResultVariant.FIRED and not error:
                buttons.append(kit_button(VIEW_BRACKET, self.open_bracket, SECONDARY_RECT))
        return buttons

    # -- animation -----------------------------------------------------------------

    def _progress(self, state: FootballGameControllerState) -> float:
        if self.clock is None:
            return 1.0
        now = self.clock()
        key = (state.game_number, state.phase, state.games_played, state.losses)
        if key != self._animation_key:
            self._animation_key = key
            self._animation_start = now
        elapsed = max(0, now - self._animation_start)
        t = min(1.0, elapsed / COUNT_UP_MS)
        return 1 - (1 - t) ** 3

    # -- header --------------------------------------------------------------------

    def _draw_header(self, surface, state, variant, match) -> None:
        font = plain_font(30)
        game = blit_text(surface, font, game_label(state.game_number), MATCH_TEXT, HEADER,
                         topleft=(HEADER.left, HEADER.top))
        if match is None:
            tail = "BYE WEEK"
        elif match.period > 2:
            tail = f"FINAL · {period_label(match.period)}"
        else:
            tail = "FINAL"
        blit_text(surface, font, f" · {tail}", MATCH_MUTED, HEADER, topleft=(game.right, HEADER.top))
        stage = {
            ResultVariant.REGULAR: "REGULAR SEASON",
            ResultVariant.FIRED: "SEASON OVER",
            ResultVariant.SEASON_COMPLETE: "REGULAR SEASON COMPLETE",
            ResultVariant.BYE_WEEK: "REGULAR SEASON COMPLETE",
            ResultVariant.PLAYOFF_WIN: "PLAYOFFS",
            ResultVariant.ELIMINATED: "PLAYOFFS",
            ResultVariant.CHAMPION: "PLAYOFFS",
        }[variant]
        blit_text(surface, plain_font(13), stage, MATCH_DIM, HEADER,
                  topleft=(HEADER.left + 2, HEADER.top + 34))

    # -- hero ----------------------------------------------------------------------

    def _hero_frame(self, surface, edge: pygame.Color) -> None:
        pygame.draw.rect(surface, MATCH_INK, HERO.move(0, 5), border_radius=16)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, HERO, border_radius=16)
        pygame.draw.rect(surface, MATCH_PANEL, HERO.inflate(-6, -6), border_radius=14)
        pygame.draw.rect(surface, edge, HERO, 2, border_radius=16)

    def _draw_badge(self, surface, rect: pygame.Rect, name: str, theme: Theme) -> None:
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=16)
        pygame.draw.rect(surface, theme.primary, rect, border_radius=16)
        pygame.draw.rect(surface, team_accent(theme.primary_accent), rect, 3, border_radius=16)
        pygame.draw.rect(surface, mix(theme.primary, MATCH_INK, 0.35), rect.inflate(-14, -14), 1,
                         border_radius=11)
        initial = (name.strip()[:1] or "?").upper()
        letter = plain_font(78).render(initial, True, readable_ink(theme.primary))
        surface.blit(letter, letter.get_rect(center=(rect.centerx, rect.centery + 2)))

    def _team_block(self) -> tuple[pygame.Rect, pygame.Rect]:
        badge = pygame.Rect(HERO.left + 26, HERO.top + 34, 120, 120)
        block = pygame.Rect(badge.right + 18, HERO.top + 18, HERO.centerx - 170 - badge.right - 18, 160)
        return badge, block

    def _draw_hero(self, surface, state, match: FootballMatchState, theme: Theme) -> None:
        result = match.final_result
        assert result is not None
        won = result.winner is FootballTeamSide.TEAM_A
        tone = MATCH_GOLD if won else LOSS_TONE
        self._hero_frame(surface, mix(tone, MATCH_PANEL_EDGE, 0.5))
        accent = team_accent(theme.primary_accent)
        rail_width = HERO.width // 2 - 190
        pygame.draw.rect(surface, accent if won else mix(accent, MATCH_PANEL, 0.45),
                         (HERO.left + 18, HERO.bottom - 9, rail_width, 4), border_radius=2)
        opponent = opponent_colors(state.opponent_team)
        pygame.draw.rect(surface, mix(opponent.accent, MATCH_PANEL, 0.55 if won else 0.15),
                         (HERO.right - 18 - rail_width, HERO.bottom - 9, rail_width, 4), border_radius=2)

        progress = self._progress(state)
        name_font = plain_font(22)
        score_font = plain_font(104)
        badge, block = self._team_block()
        self._draw_badge(surface, badge, match.team_a.team_name, theme)
        blit_text(surface, name_font, fit_text(match.team_a.team_name.upper(), name_font, block.width),
                  MATCH_TEXT, block, topleft=(block.left, block.top + 6))
        blit_text(surface, score_font, str(round(result.team_a_score * progress)),
                  MATCH_TEXT if won else mix(MATCH_TEXT, MATCH_PANEL, 0.3), HERO,
                  topleft=(block.left - 4, block.top + 30))

        helmet = pygame.Rect(HERO.right - 26 - 140, HERO.top + 34, 140, 120)
        sprite = _helmet_sprite(tuple(opponent.primary[:3]), 110)
        if sprite is not None:
            sprite = pygame.transform.flip(sprite, True, False)
            surface.blit(sprite, sprite.get_rect(center=helmet.center))
        else:
            pygame.draw.ellipse(surface, opponent.primary, helmet.inflate(-16, -14))
        opp_block = pygame.Rect(HERO.centerx + 170, HERO.top + 18,
                                helmet.left - 18 - HERO.centerx - 170, 160)
        blit_text(surface, name_font, fit_text(match.team_b.team_name.upper(), name_font, opp_block.width),
                  MATCH_TEXT, opp_block, topright=(opp_block.right, opp_block.top + 6))
        blit_text(surface, score_font, str(round(result.team_b_score * progress)),
                  MATCH_TEXT if not won else mix(MATCH_TEXT, MATCH_PANEL, 0.3), HERO,
                  topright=(opp_block.right + 4, opp_block.top + 30))

        center = pygame.Rect(0, 0, 300, 160)
        center.center = HERO.center
        final = "FINAL" if match.period <= 2 else f"FINAL · {period_label(match.period)}"
        blit_text(surface, match_font(14), final, MATCH_MUTED, center,
                  midtop=(center.centerx, center.top + 6))
        banner = pygame.Rect(0, 0, 260, 84)
        banner.midtop = (center.centerx, center.top + 32)
        if won:
            pygame.draw.rect(surface, mix(MATCH_GOLD, MATCH_INK, 0.65), banner.move(0, 4), border_radius=12)
            pygame.draw.rect(surface, MATCH_GOLD, banner, border_radius=12)
            ink = MATCH_INK
        else:
            pygame.draw.rect(surface, MATCH_PANEL_DEEP, banner, border_radius=12)
            pygame.draw.rect(surface, LOSS_TONE, banner, 3, border_radius=12)
            ink = LOSS_TONE
        blit_text(surface, plain_font(66), "WIN" if won else "LOSS", ink, banner,
                  center=(banner.centerx, banner.centery + 1))
        difficulty = f"{state.opponent_difficulty.value.upper()} OPPONENT"
        blit_text(surface, match_font(13), difficulty, MATCH_DIM, center,
                  midtop=(center.centerx, banner.bottom + 10))

    def _draw_bye_hero(self, surface, state, theme: Theme) -> None:
        self._hero_frame(surface, MATCH_PANEL_EDGE)
        accent = team_accent(theme.primary_accent)
        rail_width = HERO.width // 2 - 190
        pygame.draw.rect(surface, accent, (HERO.left + 18, HERO.bottom - 9, rail_width, 4),
                         border_radius=2)
        badge, block = self._team_block()
        self._draw_badge(surface, badge, self._team_name(state), theme)
        name_font = plain_font(22)
        blit_text(surface, name_font, fit_text(self._team_name(state).upper(), name_font, block.width),
                  MATCH_TEXT, block, topleft=(block.left, block.top + 6))
        blit_text(surface, plain_font(56), f"{state.wins}-{state.losses}", MATCH_TEXT, HERO,
                  topleft=(block.left - 2, block.top + 40))
        played = "GAME" if state.games_played == 1 else "GAMES"
        blit_text(surface, match_font(14), f"{state.games_played} {played} PLAYED", MATCH_MUTED, block,
                  topleft=(block.left, block.top + 112))

        center = pygame.Rect(0, 0, 320, 160)
        center.center = HERO.center
        blit_text(surface, match_font(14), "NO GAME PLAYED", MATCH_MUTED, center,
                  midtop=(center.centerx, center.top + 6))
        banner = pygame.Rect(0, 0, 300, 84)
        banner.midtop = (center.centerx, center.top + 32)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, banner, border_radius=12)
        pygame.draw.rect(surface, MATCH_MUTED, banner, 3, border_radius=12)
        blit_text(surface, plain_font(50), "BYE WEEK", MATCH_MUTED, banner,
                  center=(banner.centerx, banner.centery + 1))

        slot = pygame.Rect(HERO.right - 26 - 330, HERO.top + 34, 330, 120)
        _dashed_rect(surface, slot, MATCH_PANEL_EDGE_SOFT)
        blit_text(surface, plain_font(22), f"GAME {state.game_number}", MATCH_DIM, slot,
                  center=(slot.centerx, slot.centery - 14))
        blit_text(surface, match_font(14), "SKIPPED · NO SCORE", MATCH_DIM, slot,
                  center=(slot.centerx, slot.centery + 16))

    @staticmethod
    def _team_name(state: FootballGameControllerState) -> str:
        if state.shop is not None:
            return state.shop.roster.team_name
        return state.match.team_a.team_name if state.match is not None else "Team"

    # -- ribbon --------------------------------------------------------------------

    def _draw_ribbon(self, surface, state, variant: ResultVariant) -> None:
        record = f"{state.wins}-{state.losses}"
        bracket = state.playoffs
        rival = _next_rival(bracket) if bracket is not None else None
        next_up = (f"NEXT UP · {rival[0].name} VS {rival[1].upper()}" if rival is not None else "")
        seed = f"#{bracket.human_seed} SEED" if bracket is not None else ""
        gold = False
        if variant is ResultVariant.REGULAR:
            stamp, line, tone = None, f"NEXT UP · SHOP BEFORE GAME {state.game_number + 1}", MATCH_PANEL_EDGE
        elif variant is ResultVariant.FIRED:
            stamp, line, tone = "FIRED", f"RUN OVER · 3 LOSSES  ·  FINAL RECORD {record}", FIRED_RED
        elif variant is ResultVariant.SEASON_COMPLETE:
            stamp, tone, gold = "PLAYOFFS", MATCH_GOLD, True
            line = f"REGULAR SEASON COMPLETE  ·  {record}  ·  {seed}  ·  {next_up}"
        elif variant is ResultVariant.BYE_WEEK:
            stamp, tone = "BYE WEEK", MATCH_MUTED
            line = f"GAME {state.game_number} SKIPPED  ·  {record}  ·  {seed}  ·  {next_up}"
        elif variant is ResultVariant.PLAYOFF_WIN:
            stamp, tone, gold = "ADVANCES", MATCH_GOLD, True
            assert state.playoff_round is not None
            line = f"{state.playoff_round.name} WON  ·  {next_up}"
        elif variant is ResultVariant.CHAMPION:
            stamp, tone, gold = "CHAMPIONS", MATCH_GOLD, True
            line = f"CHAMPIONSHIP WON  ·  {seed}  ·  REGULAR SEASON {record}"
        else:
            stamp, tone = "ELIMINATED", FIRED_RED
            round_name = state.playoff_round.name if state.playoff_round is not None else "PLAYOFF"
            line = f"{round_name} LOSS  ·  RUN OVER  ·  {seed}  ·  REGULAR SEASON {record}"
        fill = MATCH_PANEL_DEEP
        if tone is FIRED_RED:
            fill = mix(FIRED_RED, MATCH_PANEL_DEEP, 0.88)
        if gold:
            fill = mix(MATCH_GOLD, MATCH_PANEL_DEEP, 0.9)
        pygame.draw.rect(surface, fill, RIBBON, border_radius=10)
        pygame.draw.rect(surface, mix(tone, MATCH_PANEL_DEEP, 0.35), RIBBON, 2, border_radius=10)
        x = RIBBON.left + 14
        if stamp is not None:
            font = plain_font(22)
            box = pygame.Rect(0, 0, font.size(stamp)[0] + 28, 32)
            box.midleft = (x, RIBBON.centery)
            if gold:
                pygame.draw.rect(surface, MATCH_GOLD, box, border_radius=6)
                blit_text(surface, font, stamp, MATCH_INK, box, center=box.center)
            else:
                pygame.draw.rect(surface, tone, box, 3, border_radius=6)
                pygame.draw.rect(surface, tone, box.inflate(-8, -8), 1, border_radius=4)
                blit_text(surface, font, stamp, tone, box, center=box.center)
            x = box.right + 16
        font = plain_font(16)
        box = pygame.Rect(x, RIBBON.top, RIBBON.right - 14 - x, RIBBON.height)
        color = MATCH_MUTED if variant is ResultVariant.REGULAR else MATCH_TEXT
        blit_text(surface, font, fit_text(line, font, box.width), color, box, midleft=(x, RIBBON.centery))

    # -- panels --------------------------------------------------------------------

    @staticmethod
    def _panel(surface, rect: pygame.Rect) -> None:
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, MATCH_PANEL, rect, border_radius=12)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=12)

    def _draw_stats(self, surface, match: FootballMatchState, team: TeamGameStats,
                    opponent: TeamGameStats, accent: pygame.Color,
                    opponent_accent: pygame.Color = NEUTRAL_OPPONENT.accent) -> None:
        self._panel(surface, STATS)
        label_width = 150
        bar_max = (STATS.width - 40 - label_width) // 2 - 90
        left_edge = STATS.centerx - label_width // 2
        right_edge = STATS.centerx + label_width // 2
        left_center = left_edge - bar_max // 2 - 40
        right_center = right_edge + bar_max // 2 + 40
        head = plain_font(15)
        name_width = bar_max + 60
        pygame.draw.rect(surface, accent, (STATS.left + 16, STATS.top + 14, 4, 16), border_radius=2)
        blit_text(surface, head, fit_text(match.team_a.team_name.upper(), head, name_width), MATCH_TEXT,
                  STATS, midtop=(left_center, STATS.top + 12))
        blit_text(surface, plain_font(17), "TEAM STATS", MATCH_TEXT, STATS,
                  midtop=(STATS.centerx, STATS.top + 10))
        blit_text(surface, head, fit_text(match.team_b.team_name.upper(), head, name_width), MATCH_TEXT,
                  STATS, midtop=(right_center, STATS.top + 12))
        pygame.draw.rect(surface, opponent_accent, (STATS.right - 20, STATS.top + 14, 4, 16),
                         border_radius=2)

        row_height = 40
        top = STATS.top + 42
        value_font = plain_font(22)
        label_font = match_font(13)
        for index, (label, ours, theirs, kind) in enumerate(stat_rows(team, opponent)):
            y = top + index * row_height
            cy = y + row_height // 2
            if index:
                pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (STATS.left + 16, y), (STATS.right - 16, y))
            blit_text(surface, label_font, label, MATCH_MUTED, STATS, center=(STATS.centerx, cy))
            our_value, their_value = _row_value(ours), _row_value(theirs)
            scale = max(our_value, their_value, 1)
            for side, value, parts in ((0, our_value, ours), (1, their_value, theirs)):
                track = pygame.Rect(left_edge - bar_max if side == 0 else right_edge, cy - 8, bar_max, 16)
                pygame.draw.rect(surface, MATCH_PANEL_DEEP, track, border_radius=4)
                width = round(bar_max * value / scale) if value > 0 else 0
                bar = pygame.Rect(track.right - width if side == 0 else track.left, track.top, width, 16)
                if width and kind == "total":
                    rushing = parts[0]
                    run_width = round(width * rushing / value)
                    # Rushing sits next to the label column on both sides.
                    run = pygame.Rect(bar.right - run_width if side == 0 else bar.left, bar.top, run_width, 16)
                    pygame.draw.rect(surface, PLAY_LINE_PASS, bar, border_radius=4)
                    if run_width:
                        pygame.draw.rect(surface, PLAY_LINE_RUN, run, border_radius=4)
                elif width:
                    color = {
                        "run": PLAY_LINE_RUN, "pass": PLAY_LINE_PASS, "turnover": MATCH_DANGER,
                    }.get(kind, accent if side == 0 else opponent_accent)
                    pygame.draw.rect(surface, color, bar, border_radius=4)
                other = their_value if side == 0 else our_value
                leads = value < other if kind == "turnover" else value > other
                text = f"{value} yd" if kind in ("total", "run", "pass", "long") else str(value)
                color = MATCH_TEXT if leads else MATCH_MUTED
                if side == 0:
                    blit_text(surface, value_font, text, color, STATS, midright=(track.left - 10, cy))
                else:
                    blit_text(surface, value_font, text, color, STATS, midleft=(track.right + 10, cy))
        legend_y = STATS.bottom - 16
        legend_font = match_font(12)
        x = STATS.centerx - 66
        for color, name in ((PLAY_LINE_RUN, "RUN"), (PLAY_LINE_PASS, "PASS")):
            pygame.draw.rect(surface, color, (x, legend_y - 5, 10, 10), border_radius=2)
            label = blit_text(surface, legend_font, name, MATCH_MUTED, STATS, midleft=(x + 15, legend_y))
            x = label.right + 26

    def _draw_bye_panel(self, surface, state, accent: pygame.Color) -> None:
        self._panel(surface, STATS)
        pygame.draw.rect(surface, accent, (STATS.left + 12, STATS.top + 11, 4, 16), border_radius=2)
        blit_text(surface, plain_font(17), f"GAME {state.game_number}", MATCH_TEXT, STATS,
                  topleft=(STATS.left + 22, STATS.top + 8))
        blit_text(surface, plain_font(44), "NO GAME PLAYED", MATCH_MUTED, STATS,
                  center=(STATS.centerx, STATS.top + 104))
        message = state.transition_message or (
            "Bye Week skipped scheduled game 10 without a score or win/loss. "
            "The regular season is complete: on to the playoffs."
        )
        blit_wrapped(surface, message, pygame.Rect(STATS.left + 60, STATS.top + 156, STATS.width - 120, 110),
                     (17, 16, 15, 14), MATCH_MUTED, max_lines=4)

    def _draw_season(self, surface, state, variant: ResultVariant, accent: pygame.Color) -> None:
        self._panel(surface, SEASON)
        pygame.draw.rect(surface, accent, (SEASON.left + 12, SEASON.top + 11, 4, 16), border_radius=2)
        blit_text(surface, plain_font(17), "SEASON", MATCH_TEXT, SEASON,
                  topleft=(SEASON.left + 22, SEASON.top + 8))
        blit_text(surface, plain_font(30), f"{state.wins}-{state.losses}", MATCH_TEXT, SEASON,
                  topright=(SEASON.right - 18, SEASON.top + 4))
        history: dict[int, FootballSeasonGame] = {game.game_number: game for game in state.season_history}
        width, height, gap = 80, 64, 8
        grid_left = SEASON.left + (SEASON.width - (5 * width + 4 * gap)) // 2
        grid_top = SEASON.top + 48
        for number in range(1, 11):
            tile = pygame.Rect(grid_left + (number - 1) % 5 * (width + gap),
                               grid_top + (number - 1) // 5 * (height + gap), width, height)
            rival = (state.regular_season_teams[number - 1]
                     if len(state.regular_season_teams) >= number else None)
            self._draw_tile(surface, tile, number, history.get(number), number == state.game_number,
                            rival)

        strikes_y = grid_top + 2 * height + gap + 34
        if state.playoffs is not None:
            self._draw_playoff_path(surface, state.playoffs, state.playoff_round,
                                    pygame.Rect(SEASON.left + 16, strikes_y - 22, SEASON.width - 32, 50))
        else:
            self._draw_losses(surface, state, variant, strikes_y)

        scored = sum(game.team_score or 0 for game in state.season_history)
        allowed = sum(game.opponent_score or 0 for game in state.season_history)
        totals = f"POINTS FOR {scored}  ·  AGAINST {allowed}"
        totals_box = pygame.Rect(SEASON.left + 16, SEASON.bottom - 40, SEASON.width - 32, 28)
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (totals_box.left, totals_box.top - 6),
                         (totals_box.right, totals_box.top - 6))
        font = match_font(13)
        blit_text(surface, font, fit_text(totals, font, totals_box.width), MATCH_MUTED, totals_box,
                  center=totals_box.center)

    def _draw_losses(self, surface, state, variant: ResultVariant, strikes_y: int) -> None:
        blit_text(surface, plain_font(15), "LOSSES", MATCH_MUTED, SEASON,
                  midleft=(SEASON.left + 22, strikes_y))
        strikes_left = SEASON.left + 104
        for index in range(3):
            strike = pygame.Rect(strikes_left + index * 52, strikes_y - 15, 42, 30)
            filled = index < state.losses
            if filled:
                pygame.draw.rect(surface, mix(FIRED_RED, MATCH_PANEL_DEEP, 0.15), strike, border_radius=6)
                ink = MATCH_INK
            else:
                pygame.draw.rect(surface, MATCH_PANEL_DEEP, strike, border_radius=6)
                pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, strike, 2, border_radius=6)
                ink = MATCH_PANEL_EDGE_SOFT
            cx, cy = strike.center
            pygame.draw.line(surface, ink, (cx - 7, cy - 7), (cx + 7, cy + 7), 4)
            pygame.draw.line(surface, ink, (cx - 7, cy + 7), (cx + 7, cy - 7), 4)
        if variant in (ResultVariant.REGULAR, ResultVariant.FIRED):
            note = {0: "3 LOSSES ENDS THE RUN", 1: "2 MORE ENDS THE RUN",
                    2: "1 MORE ENDS THE RUN"}.get(state.losses, "RUN OVER")
            note_box = pygame.Rect(strikes_left + 3 * 52 + 4, strikes_y - 10,
                                   SEASON.right - 16 - strikes_left - 3 * 52 - 4, 20)
            note_font = match_font(12)
            blit_text(surface, note_font, fit_text(note, note_font, note_box.width),
                      FIRED_RED if state.losses >= 2 else MATCH_DIM, note_box,
                      midleft=(note_box.left, strikes_y))


    @staticmethod
    def _draw_playoff_path(surface, bracket: FootballPlayoffBracketState,
                           current: FootballPlayoffRound | None, rect: pygame.Rect) -> None:
        """PLAYOFFS label and one tile per round: W/L and score, NEXT, or pending."""
        blit_text(surface, plain_font(15), "PLAYOFFS", MATCH_MUTED, SEASON,
                  midleft=(rect.left + 6, rect.centery))
        labels = {FootballPlayoffRound.QUARTERFINAL: "QF", FootballPlayoffRound.SEMIFINAL: "SF",
                  FootballPlayoffRound.CHAMPIONSHIP: "FINAL"}
        left = rect.left + 100
        gap = 8
        width = (rect.right - left - 2 * gap) // 3
        next_round = None if bracket.human_eliminated else bracket.next_human_round
        for index, playoff_round in enumerate(FootballPlayoffRound):
            tile = pygame.Rect(left + index * (width + gap), rect.top, width, rect.height)
            game = bracket.human_game(playoff_round)
            decided = game is not None and game.decided
            won = decided and game.winner_seed == bracket.human_seed
            if decided:
                tone = MATCH_GOLD if won else FIRED_RED
                fill, edge = mix(tone, MATCH_PANEL_DEEP, 0.8), mix(tone, MATCH_PANEL_DEEP, 0.3)
            elif playoff_round is next_round:
                fill, edge = MATCH_PANEL_DEEP, MATCH_GOLD
            else:
                fill, edge = mix(MATCH_PANEL_DEEP, MATCH_PANEL, 0.5), MATCH_PANEL_EDGE_SOFT
            pygame.draw.rect(surface, fill, tile, border_radius=8)
            pygame.draw.rect(surface, edge, tile, 2 if decided or playoff_round is next_round else 1,
                             border_radius=8)
            if playoff_round is current:
                pygame.draw.rect(surface, MATCH_TEXT, tile.inflate(6, 6), 2, border_radius=10)
            blit_text(surface, match_font(11), labels[playoff_round], MATCH_MUTED, tile,
                      topleft=(tile.left + 7, tile.top + 4))
            if game is not None:
                rival = bracket.team(game.opponent_of(bracket.human_seed)).ai_team
                if rival is not None:
                    _draw_rival_tag(surface, tile, rival, dim=False)
            if decided:
                assert game is not None
                opponent = game.opponent_of(bracket.human_seed)
                word = "W" if won else "L"
                blit_text(surface, plain_font(22), word, MATCH_GOLD if won else FIRED_RED, tile,
                          midright=(tile.centerx - 4, tile.centery + 4))
                score = f"{game.score_for(bracket.human_seed)}-{game.score_for(opponent)}"
                score += " OT" if game.overtime else ""
                font = match_font(11)
                blit_text(surface, font, fit_text(score, font, tile.width // 2 - 6), MATCH_MUTED, tile,
                          midleft=(tile.centerx + 2, tile.centery + 5))
            elif playoff_round is next_round:
                blit_text(surface, match_font(13), "NEXT", MATCH_GOLD, tile,
                          center=(tile.centerx, tile.centery + 5))
            else:
                pygame.draw.circle(surface, MATCH_PANEL_EDGE_SOFT, (tile.centerx, tile.centery + 5), 3)


    @staticmethod
    def _draw_tile(surface, tile: pygame.Rect, number: int, game: FootballSeasonGame | None,
                   current: bool, rival: FootballAITeam | None = None) -> None:
        outcome = game.outcome if game is not None else None
        if outcome is FootballSeasonOutcome.WIN:
            fill, edge, ink = (mix(MATCH_GOLD, MATCH_PANEL_DEEP, 0.8),
                               mix(MATCH_GOLD, MATCH_PANEL_DEEP, 0.3), MATCH_GOLD)
        elif outcome is FootballSeasonOutcome.LOSS:
            fill, edge, ink = (mix(FIRED_RED, MATCH_PANEL_DEEP, 0.82),
                               mix(FIRED_RED, MATCH_PANEL_DEEP, 0.4), FIRED_RED)
        elif outcome is FootballSeasonOutcome.BYE:
            fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_MUTED
        else:
            fill, edge, ink = mix(MATCH_PANEL_DEEP, MATCH_PANEL, 0.5), MATCH_PANEL_EDGE_SOFT, MATCH_DIM
        pygame.draw.rect(surface, fill, tile, border_radius=8)
        pygame.draw.rect(surface, edge, tile, 1 if outcome is None else 2, border_radius=8)
        if current:
            pygame.draw.rect(surface, MATCH_TEXT, tile.inflate(6, 6), 2, border_radius=10)
        blit_text(surface, match_font(11), f"G{number}", MATCH_MUTED if game else MATCH_DIM, tile,
                  topleft=(tile.left + 7, tile.top + 4))
        if rival is not None:
            _draw_rival_tag(surface, tile, rival, dim=game is None)
        if outcome is None:
            pygame.draw.circle(surface, MATCH_PANEL_EDGE_SOFT, (tile.centerx, tile.centery + 2), 3)
            return
        word = outcome.value
        blit_text(surface, plain_font(26 if outcome is not FootballSeasonOutcome.BYE else 20), word, ink,
                  tile, center=(tile.centerx, tile.centery + 1))
        if game is not None and game.team_score is not None:
            score = f"{game.team_score}-{game.opponent_score}" + (" OT" if game.overtime else "")
            font = match_font(11)
            blit_text(surface, font, fit_text(score, font, tile.width - 6), MATCH_MUTED, tile,
                      midbottom=(tile.centerx, tile.bottom - 3))

    # -- footer --------------------------------------------------------------------

    @staticmethod
    def _draw_key_hint(surface) -> None:
        font = match_font(12)
        cap = pygame.Rect(0, 0, font.size("ENTER")[0] + 14, 22)
        cap.midleft = (PRIMARY_RECT.right + 16, PRIMARY_RECT.centery)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, cap, border_radius=5)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, cap, 1, border_radius=5)
        blit_text(surface, font, "ENTER", MATCH_DIM, cap, center=cap.center)


def _draw_rival_tag(surface, tile: pygame.Rect, rival: FootballAITeam, *, dim: bool) -> None:
    """The opponent's abbreviation and color chip in a tile's top-right corner."""
    font = match_font(11)
    chip = pygame.Rect(0, 0, 12, 9)
    chip.topright = (tile.right - 7, tile.top + 6)
    draw_team_chip(surface, chip, opponent_colors(rival))
    blit_text(surface, font, rival.abbreviation, MATCH_DIM if dim else MATCH_MUTED, tile,
              topright=(chip.left - 4, tile.top + 4))


def _dashed_rect(surface, rect: pygame.Rect, color: pygame.Color, dash: int = 8) -> None:
    for x in range(rect.left + 10, rect.right - 10, dash * 2):
        end = min(x + dash, rect.right - 10)
        pygame.draw.line(surface, color, (x, rect.top), (end, rect.top), 2)
        pygame.draw.line(surface, color, (x, rect.bottom - 1), (end, rect.bottom - 1), 2)
    for y in range(rect.top + 10, rect.bottom - 10, dash * 2):
        end = min(y + dash, rect.bottom - 10)
        pygame.draw.line(surface, color, (rect.left, y), (rect.left, end), 2)
        pygame.draw.line(surface, color, (rect.right - 1, y), (rect.right - 1, end), 2)
