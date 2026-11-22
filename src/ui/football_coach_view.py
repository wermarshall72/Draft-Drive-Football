"""Inline paired-coach draft cards."""

from collections.abc import Callable

import pygame

from src.engine.football import FootballPosition
from src.engine.football_coaches import FootballCoachPerkKind, FootballCoachProfile
from src.engine.football_controller import FootballGameControllerState
from src.ui.coach_art import draw_coach_portrait
from src.ui.coach_fonts import staff_font
from src.ui.football_draft_interaction import CoachInspection
from src.ui.text import draw_complete_wrapped_text
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_text

_TEXT = pygame.Color("#eef5ff")
_MUTED = pygame.Color("#b5c8dc")
_EDGE = pygame.Color("#507397")
_POSITIVE = pygame.Color("#9fe4ad")
_NEGATIVE = pygame.Color("#ff9d98")
_NEUTRAL = pygame.Color("#c1cbd5")


def _coach_position_label(position: FootballPosition) -> str:
    return {
        FootballPosition.QB: "QB", FootballPosition.RB: "RB",
        FootballPosition.WR: "WR", FootballPosition.O_LINE: "O-LINE",
        FootballPosition.D_LINE: "D-LINE", FootballPosition.LINEBACKERS: "LB",
        FootballPosition.CORNERBACKS: "CB", FootballPosition.SAFETIES: "S",
    }[position]


def coach_perk_text(coach: FootballCoachProfile) -> str:
    perk = coach.perk
    if perk is None:
        return "No perk."
    value = f"{perk.value:g}"
    percentage = f"{perk.value * 100:g}"
    descriptions = {
        FootballCoachPerkKind.FIRST_RUN_YARDS:
            f"First RB Run per drive: +{value} yards unless turnover. "
            "A turnover uses the attempt; resets next drive.",
        FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS:
            f"Every fourth-down go-for-it: +{value} yard on a non-turnover run "
            "or completed pass; not conversions.",
        FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS:
            f"First completed pass per drive: +{value} yards. Incompletions and "
            "interceptions do not use it; resets next drive.",
        FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS:
            f"Every completed first-down pass: +{value} yards; not conversions.",
        FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION:
            f"Every RB Run against the RB Run scheme: -{value} yards on "
            "non-turnovers.",
        FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS:
            f"Every pass matched by the scheme: +{percentage} percentage points "
            "interception chance.",
        FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS:
            f"Every pass matched by the scheme: +{percentage} percentage points "
            "incompletion chance.",
        FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS:
            f"Regular-play interceptions: +{value} return yards; reaching the goal "
            "line scores a TD. Not two-point conversions.",
    }
    return descriptions[perk.kind]


class FootballCoachView:
    def __init__(
        self, theme: Theme, inspection: CoachInspection, focus_index: int,
        body_font: pygame.font.Font, stat_font: pygame.font.Font,
        small_font: pygame.font.Font, main_font: pygame.font.Font,
        button_font: pygame.font.Font, choose_coach: Callable[[int], None],
    ) -> None:
        self.theme = theme
        self.inspection = inspection
        self.focus_index = focus_index
        self.choose_coach = choose_coach
        self.title_font = staff_font(34, semibold=True)
        self.name_font = staff_font(16, semibold=True)
        self.body_font = body_font
        self.detail_font = staff_font(14)
        self.stat_font = stat_font
        self.small_font = small_font
        self.main_font = main_font
        self.button_font = button_font

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        surface.fill("#061629")
        for y in range(70, 116, 10):
            pygame.draw.line(surface, "#102e49", (0, y), (1280, y), 1)
        for x in range(35, 1280, 80):
            pygame.draw.line(surface, "#14334e", (x, 82), (x, 114), 2)
        pygame.draw.rect(surface, "#102e4c", (20, 12, 480, 56), border_radius=5)
        pygame.draw.rect(surface, _EDGE, (20, 12, 480, 56), 2, border_radius=5)
        draw_text(surface, "SELECT YOUR COACHES", (36, 18), self.title_font, _TEXT)
        draw_text(surface, "Choose a coaching staff to lead your program.",
                  (25, 82), self.body_font, _MUTED)

    def draw(self, surface: pygame.Surface, content: pygame.Rect,
             state: FootballGameControllerState) -> list[Button]:
        sidebar = pygame.Rect(20, 122, 224, 550)
        pygame.draw.rect(surface, "#0e2b47", sidebar, border_radius=6)
        pygame.draw.rect(surface, _EDGE, sidebar, 2, border_radius=6)
        draw_text(surface, "COACHING IMPACT", (34, 138), self.main_font, _TEXT)
        draw_complete_wrapped_text(
            surface,
            "Each pair shapes your offense and defense through position "
            "modifiers and active coach perks.",
            pygame.Rect(34, 174, 193, 128), self.body_font, _MUTED, line_gap=3,
        )
        pygame.draw.line(surface, _EDGE, (34, 317), (229, 317), 2)
        draw_complete_wrapped_text(
            surface,
            "Modifiers apply to individual positions, not flat team-wide bonuses. "
            "Your staff stays for the run.",
            pygame.Rect(34, 338, 193, 170), self.body_font, _MUTED, line_gap=3,
        )
        draw_complete_wrapped_text(
            surface, "Choose one complete pair to get started.",
            pygame.Rect(34, 574, 193, 65), self.body_font, _MUTED,
        )
        gap = 12
        left = 258
        width = (1258 - left - 2 * gap) // 3
        cards = [pygame.Rect(left + i * (width + gap), 122, width, 550)
                 for i in range(len(state.team_builder.coach_offer))]
        self.inspection.card_rects = cards
        active = self.inspection.active_index(self.focus_index)
        buttons = []
        for index, (pair, rect) in enumerate(zip(state.team_builder.coach_offer, cards)):
            pygame.draw.rect(surface, "#102e4a", rect, border_radius=6)
            pygame.draw.rect(surface, _EDGE, rect, 2, border_radius=6)
            if active == index:
                # A light keyline keeps dark primary colors visible against navy.
                pygame.draw.rect(surface, "#dceaf7", rect.inflate(-2, -2), 4, border_radius=5)
                pygame.draw.rect(surface, self.theme.primary, rect.inflate(-4, -4), 2,
                                 border_radius=4)
            draw_text(surface, f"PAIR 0{index + 1}", (rect.left + 12, rect.top + 10),
                      self.main_font, _TEXT)
            half = (rect.width - 26) // 2
            for side_index, coach in enumerate((pair.offense, pair.defense)):
                x = rect.left + 10 + side_index * half
                draw_coach_portrait(surface, pygame.Rect(x + 4, rect.top + 34, half - 8, 124),
                                    coach.coach_id, self.theme.primary)
                draw_complete_wrapped_text(
                    surface, coach.name, pygame.Rect(x + 3, rect.top + 160, half - 6, 40),
                    self.name_font, _TEXT, line_gap=0,
                )
                draw_text(surface, coach.side.value.upper(), (x + 3, rect.top + 200),
                          self.small_font, _MUTED)
                for row, (position, modifier) in enumerate(coach.position_modifiers.items()):
                    color = _POSITIVE if modifier > 0 else _NEGATIVE if modifier < 0 else _NEUTRAL
                    draw_text(surface, f"{_coach_position_label(position)} {round(modifier * 100):+d}%",
                              (x + 3, rect.top + 225 + row * 20), self.stat_font, color)
            pygame.draw.line(surface, _EDGE, (rect.left + 10, rect.top + 310),
                             (rect.right - 10, rect.top + 310), 1)
            draw_text(surface, "COACH PERKS", (rect.left + 12, rect.top + 316),
                      self.small_font, _MUTED)
            for row, coach in enumerate((pair.offense, pair.defense)):
                y = rect.top + 336 + row * 81
                box = pygame.Rect(rect.left + 10, y, rect.width - 20, 76)
                pygame.draw.rect(surface, "#0a2037", box, border_radius=4)
                draw_complete_wrapped_text(
                    surface, f"{coach.side.value.title()}: {coach_perk_text(coach)}",
                    box.inflate(-12, -8), self.detail_font, _TEXT, line_gap=1,
                )
            buttons.append(Button(
                f"CHOOSE STAFF 0{index + 1}", lambda choice=index: self.choose_coach(choice),
                pygame.Rect(rect.left + 12, rect.bottom - 42, rect.width - 24, 32),
                variant="coach-select",
            ))
        return buttons

    def draw_button(self, surface: pygame.Surface, button: Button, index: int, *,
                    pressed: bool) -> None:
        active = self.inspection.active_index(self.focus_index) == index
        rect = button.rect.move(0, 2) if pressed and button.enabled else button.rect
        fill = self.theme.primary if active else pygame.Color("#234b70")
        pygame.draw.rect(surface, fill, rect, border_radius=5)
        pygame.draw.rect(surface, "#e1edf9" if active else _EDGE, rect, 2, border_radius=5)
        if self.inspection.keyboard and button.focused:
            pygame.draw.rect(surface, "#ffffff", rect.inflate(6, 6), 2, border_radius=7)
        label = self.button_font.render("Select This Pair", True, readable_ink(fill))
        surface.blit(label, label.get_rect(center=rect.center))
