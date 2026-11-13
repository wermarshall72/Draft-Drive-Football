from collections.abc import Callable

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    FootballMatchEvent,
    FootballFourthDownAction,
    FootballPosition,
    FootballRoster,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_shop import FootballShopState
from src.engine.football_team_builder import (
    PLAYER_DRAFT_ORDER,
    FootballPlayerCandidate,
)
from src.ui.layout import Layout
from src.ui.screens import Navigate, Quit, Screen, _ui_font
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

_PLAY_LABELS = {
    OffensivePlayAction.RB_RUN: "RB RUN",
    OffensivePlayAction.SCREEN_PASS: "SCREEN PASS",
    OffensivePlayAction.PA_PASS: "PLAY-ACTION PASS",
    OffensivePlayAction.SHORT_PASS: "SHORT PASS",
    OffensivePlayAction.MEDIUM_PASS: "MEDIUM PASS",
    OffensivePlayAction.DEEP_PASS: "DEEP PASS",
}

_SCHEME_LABELS = {
    DefensiveSchemeAction.RB_RUN: "RB RUN SCHEME",
    DefensiveSchemeAction.SCREEN_PASS: "SCREEN PASS SCHEME",
    DefensiveSchemeAction.PA_PASS: "PLAY-ACTION SCHEME",
    DefensiveSchemeAction.SHORT_PASS: "SHORT PASS SCHEME",
    DefensiveSchemeAction.MEDIUM_PASS: "MEDIUM PASS SCHEME",
    DefensiveSchemeAction.DEEP_PASS: "DEEP PASS SCHEME",
}


class FootballRunScreen(Screen):
    """Render the current immutable controller state and submit human choices."""

    def __init__(
        self,
        theme: Theme,
        team_name: str,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.team_name = team_name
        self.controller: FootballGameController | None = None
        self.state: FootballGameControllerState | None = None
        self.last_error: str | None = None
        self.confirm_exit = False

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self.confirm_exit = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_exit = not self.confirm_exit
            return
        super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        state = self._current_state()
        titles = {
            FootballRunPhase.COACH_DRAFT: ("Choose your coach", "RUN SETUP / IDENTITY"),
            FootballRunPhase.PLAYER_DRAFT: ("Build your roster", "DRAFT / POSITION ORDER"),
            FootballRunPhase.PRE_MATCH_SHOP: ("Training room", "PRE-MATCH / SIX TRAINING POINTS"),
            FootballRunPhase.MATCH: ("Game day", "LOCAL AI / INTERACTIVE MATCH"),
            FootballRunPhase.READY_FOR_NEXT_GAME: ("Final whistle", "REGULAR SEASON / NEXT GAME READY"),
            FootballRunPhase.FIRED: ("Run ended", "THREE LOSSES / FIRED"),
            FootballRunPhase.PLAYOFFS: ("Season milestone", "GAME 10 / PLAYOFFS"),
        }
        title, eyebrow = titles[state.phase]
        layout = self._header(surface, title, eyebrow, self.team_name)
        content = layout.content

        content = pygame.Rect(
            content.left,
            content.top + 42,
            content.width,
            content.height - 42,
        )
        if state.phase is FootballRunPhase.COACH_DRAFT:
            self._draw_coach_selection(surface, content, state)
        elif state.phase is FootballRunPhase.PLAYER_DRAFT:
            self._draw_player_draft(surface, content, state)
        elif state.phase is FootballRunPhase.PRE_MATCH_SHOP:
            self._draw_shop(surface, content, state.shop)
        elif state.phase is FootballRunPhase.MATCH:
            self._draw_match(surface, content, state)
        else:
            self._draw_result(surface, content, state)

        exit_rect = pygame.Rect(layout.content.right - 128, layout.content.top, 128, 32)
        self.buttons.append(
            Button("END RUN", self._request_exit, exit_rect, variant="quiet")
        )
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)

        if self.last_error is not None:
            draw_text(
                surface,
                f"ERROR: {self.last_error}",
                (layout.margin, layout.height - 49),
                self._small_font,
                self.theme.danger,
            )
        if self.confirm_exit:
            self._draw_exit_confirmation(surface)

    def _draw_coach_selection(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        coaches = state.team_builder.coach_offer
        draw_text(
            surface,
            "Choose one coach identity. Coaches have no gameplay effects in this model.",
            (content.left + 2, content.top + 1),
            self._body_font,
            self.theme.muted,
        )
        gap = 16
        card_top = content.top + 36
        card_height = content.height - 42
        card_width = (content.width - gap * 2) // 3
        buttons: list[Button] = []
        for index, coach in enumerate(coaches):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                card_top,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme)
            draw_text(
                surface,
                f"COACH 0{index + 1}",
                (rect.left + 22, rect.top + 24),
                self._small_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                coach.name,
                (rect.left + 22, rect.top + 72),
                self._title_font,
                self.theme.text,
            )
            draw_wrapped_text(
                surface,
                "Identity choice only",
                pygame.Rect(rect.left + 22, rect.top + 120, rect.width - 44, 58),
                self._body_font,
                self.theme.muted,
            )
            button_rect = pygame.Rect(
                rect.left + 20,
                rect.bottom - 58,
                rect.width - 40,
                40,
            )
            buttons.append(
                Button(
                    f"CHOOSE {coach.name.upper()}",
                    lambda choice=index: self._submit(
                        lambda: self._require_controller().choose_coach(choice)
                    ),
                    button_rect,
                    variant="primary" if index == 0 else "quiet",
                )
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_player_draft(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        builder = state.team_builder
        required = builder.required_position
        completed = len(builder.selected_players)
        remaining = len(PLAYER_DRAFT_ORDER) - completed
        required_label = required.value if required is not None else "COMPLETE"
        draw_text(
            surface,
            f"NEXT POSITION: {required_label}    |    {remaining} POSITION(S) REMAINING",
            (content.left + 2, content.top),
            self._label_font,
            self.theme.secondary_accent,
        )
        if builder.selected_coach is not None:
            draw_text(
                surface,
                f"COACH: {builder.selected_coach.name}  (IDENTITY ONLY)",
                (content.left + 2, content.top + 21),
                self._small_font,
                self.theme.muted,
            )
        progress_top = content.top + 42
        gap = 8
        cell_width = (content.width - gap * 7) // 8
        for index, position in enumerate(PLAYER_DRAFT_ORDER):
            rect = pygame.Rect(
                content.left + index * (cell_width + gap),
                progress_top,
                cell_width,
                30,
            )
            is_done = position in builder.selected_players
            is_current = position is required
            draw_panel(
                surface,
                rect,
                self.theme,
                selected=is_current,
                fill=self.theme.panel_alt if is_done else self.theme.panel,
            )
            draw_text(
                surface,
                position.value,
                (rect.left + 5, rect.top + 8),
                _ui_font(11, bold=True),
                self.theme.primary_accent if is_done else self.theme.text,
            )

        offers = tuple(
            candidate
            for candidate in builder.current_offer
            if isinstance(candidate, FootballPlayerCandidate)
        )
        gap = 14
        cards_top = progress_top + 44
        card_width = (content.width - gap * 2) // 3
        card_height = content.bottom - cards_top
        buttons: list[Button] = []
        for index, candidate in enumerate(offers):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                cards_top,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                f"PLAYER 0{index + 1}  /  {candidate.position.value}",
                (rect.left + 18, rect.top + 18),
                self._small_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                candidate.name,
                (rect.left + 18, rect.top + 53),
                self._label_font,
                self.theme.text,
            )
            player = candidate.player
            stat_lines = (
                f"Power       {player.power:.1f}",
                f"Volatility  {player.volatility:.2f}",
                f"Stamina     {player.stamina:.2f}",
            )
            for stat_index, line in enumerate(stat_lines):
                draw_text(
                    surface,
                    line,
                    (rect.left + 18, rect.top + 92 + stat_index * 24),
                    self._body_font,
                    self.theme.text,
                )
            draw_wrapped_text(
                surface,
                candidate.description,
                pygame.Rect(
                    rect.left + 18,
                    rect.top + 176,
                    rect.width - 36,
                    max(42, card_height - 244),
                ),
                self._body_font,
                self.theme.muted,
            )
            button_rect = pygame.Rect(
                rect.left + 16,
                rect.bottom - 54,
                rect.width - 32,
                38,
            )
            buttons.append(
                Button(
                    f"DRAFT {candidate.position.value}",
                    lambda choice=index, position=candidate.position: self._submit(
                        lambda: self._require_controller().choose_player(position, choice)
                    ),
                    button_rect,
                    variant="primary" if index == 0 else "quiet",
                )
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_shop(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
    ) -> None:
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")
        draw_text(
            surface,
            f"REMAINING: {shop.remaining_budget} TRAINING POINT(S)",
            (content.left + 2, content.top),
            self._label_font,
            self.theme.secondary_accent,
        )
        purchased_text = (
            "Purchased: "
            + ", ".join(upgrade.name for upgrade in shop.purchased_upgrades)
            if shop.purchased_upgrades
            else "Purchased: none"
        )
        draw_text(
            surface,
            purchased_text[:130],
            (content.left + 2, content.top + 25),
            self._small_font,
            self.theme.muted,
        )
        gap = 14
        cards_top = content.top + 50
        card_width = (content.width - gap * 2) // 3
        card_height = content.bottom - cards_top - 48
        buttons: list[Button] = []
        for index, upgrade in enumerate(shop.offer):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                cards_top,
                card_width,
                card_height,
            )
            purchased = upgrade in shop.purchased_upgrades
            affordable = upgrade.cost <= shop.remaining_budget
            draw_panel(
                surface,
                rect,
                self.theme,
                selected=purchased,
                fill=self.theme.panel_alt if purchased else self.theme.panel,
            )
            draw_text(
                surface,
                upgrade.name,
                (rect.left + 18, rect.top + 19),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                f"Target: {upgrade.position.value}",
                (rect.left + 18, rect.top + 58),
                self._body_font,
                self.theme.muted,
            )
            draw_text(
                surface,
                f"Stat: {upgrade.stat.value.upper()}  +{upgrade.amount:g}",
                (rect.left + 18, rect.top + 87),
                self._body_font,
                self.theme.primary_accent,
            )
            draw_text(
                surface,
                f"Cost: {upgrade.cost} Training Point(s)",
                (rect.left + 18, rect.top + 118),
                self._body_font,
                self.theme.text,
            )
            draw_wrapped_text(
                surface,
                upgrade.description,
                pygame.Rect(rect.left + 18, rect.top + 157, rect.width - 36, 54),
                self._small_font,
                self.theme.muted,
            )
            reason = (
                "Already purchased"
                if purchased
                else "Not enough Training Points"
                if not affordable
                else "Available"
            )
            draw_text(
                surface,
                reason,
                (rect.left + 18, rect.bottom - 68),
                self._small_font,
                self.theme.muted if affordable and not purchased else self.theme.danger,
            )
            button_rect = pygame.Rect(
                rect.left + 14,
                rect.bottom - 48,
                rect.width - 28,
                34,
            )
            buttons.append(
                Button(
                    "PURCHASED" if purchased else "BUY UPGRADE",
                    lambda choice=index: self._submit(
                        lambda: self._require_controller().buy_upgrade(choice)
                    ),
                    button_rect,
                    enabled=affordable and not purchased,
                    variant="primary",
                )
            )

        finish_rect = pygame.Rect(
            content.right - 244,
            content.bottom - 40,
            244,
            36,
        )
        buttons.append(
            Button(
                "FINISH SHOP / START MATCH",
                lambda: self._submit(self._require_controller().finish_shop),
                finish_rect,
                variant="primary",
            )
        )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_match(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")

        gap = 12
        team_width = (content.width - gap) // 2
        team_height = 136
        self._draw_team_panel(
            surface,
            pygame.Rect(content.left, content.top, team_width, team_height),
            match.team_a,
            match.team_a_score,
            FootballTeamSide.TEAM_A,
        )
        self._draw_team_panel(
            surface,
            pygame.Rect(content.left + team_width + gap, content.top, team_width, team_height),
            match.team_b,
            match.team_b_score,
            FootballTeamSide.TEAM_B,
        )

        details = pygame.Rect(
            content.left,
            content.top + team_height + 8,
            content.width,
            65,
        )
        draw_panel(surface, details, self.theme, fill=self.theme.panel_alt)
        possession_name = (
            match.team_a.team_name
            if match.possession is FootballTeamSide.TEAM_A
            else match.team_b.team_name
        )
        clock = f"{match.game_clock_seconds // 60:02d}:{match.game_clock_seconds % 60:02d}"
        draw_text(
            surface,
            f"PERIOD {match.period}  {clock}    |    POSSESSION: {possession_name}",
            (details.left + 16, details.top + 11),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            f"DOWN {match.down} & {match.yards_to_go:.1f}    |    "
            f"OWN {match.offense_field_position:.1f}-YARD LINE    |    "
            f"DRIVE SCHEME: {match.current_drive_defensive_scheme.value if match.current_drive_defensive_scheme else 'NOT SET'}",
            (details.left + 16, details.top + 35),
            self._small_font,
            self.theme.text,
        )

        history = pygame.Rect(
            content.left,
            details.bottom + 8,
            content.width,
            62,
        )
        draw_panel(surface, history, self.theme)
        draw_text(
            surface,
            "RECENT MATCH EVENTS",
            (history.left + 14, history.top + 8),
            self._small_font,
            self.theme.muted,
        )
        recent_events = match.match_events[-2:]
        if recent_events:
            for index, event in enumerate(recent_events):
                draw_text(
                    surface,
                    self._format_event(event, match.team_a.team_name, match.team_b.team_name),
                    (history.left + 14, history.top + 27 + index * 17),
                    self._small_font,
                    self.theme.text,
                )
        else:
            draw_text(
                surface,
                "The opening drive is ready.",
                (history.left + 14, history.top + 31),
                self._small_font,
                self.theme.text,
            )

        action_top = history.bottom + 8
        actions_rect = pygame.Rect(
            content.left,
            action_top,
            content.width,
            max(1, content.bottom - action_top),
        )
        self._draw_match_decision(surface, actions_rect, state)

    def _draw_team_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        roster: FootballRoster,
        score: int,
        side: FootballTeamSide,
    ) -> None:
        draw_panel(
            surface,
            rect,
            self.theme,
            fill=self.theme.panel_alt if side is FootballTeamSide.TEAM_A else self.theme.panel,
        )
        draw_text(
            surface,
            _fit_text(
                f"{'TEAM A / YOU' if side is FootballTeamSide.TEAM_A else 'TEAM B / LOCAL AI'}  -  {roster.team_name}",
                self._label_font,
                rect.width - 92,
            ),
            (rect.left + 14, rect.top + 10),
            self._label_font,
            self.theme.text,
        )
        score_surface = _ui_font(30, bold=True).render(str(score), True, self.theme.primary_accent)
        surface.blit(score_surface, score_surface.get_rect(topright=(rect.right - 14, rect.top + 7)))
        staff_line = _fit_text(
            f"COACH: {roster.coach.name}  |  SPECIAL TEAMS: {roster.special_teams.name}",
            self._small_font,
            rect.width - 28,
        )
        draw_text(
            surface,
            staff_line,
            (rect.left + 14, rect.top + 31),
            self._small_font,
            self.theme.muted,
        )
        positions = tuple(FootballPosition)
        column_width = (rect.width - 28) // 2
        for index, position in enumerate(positions):
            column, row = divmod(index, 4)
            x = rect.left + 14 + column * column_width
            y = rect.top + 51 + row * 18
            position_label = _fit_text(position.value, self._small_font, 106)
            draw_text(surface, position_label, (x, y), self._small_font, self.theme.muted)
            name_x = x + 110
            name_width = column_width - 114
            player_name = _fit_text(roster.players[position].name, self._small_font, name_width)
            draw_text(surface, player_name, (name_x, y), self._small_font, self.theme.text)

    def _draw_match_decision(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        decision = state.human_decision
        if decision is FootballHumanDecision.OFFENSIVE_PLAY:
            labels = tuple(_PLAY_LABELS.items())
            heading = "YOUR OFFENSE  /  CHOOSE A PLAY"
            actions = [
                (label, lambda action=action: self._submit(
                    lambda: self._require_controller().choose_offensive_play(action)
                ))
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            labels = tuple(_SCHEME_LABELS.items())
            heading = "TEAM B DRIVE  /  CHOOSE ONE SCHEME FOR THE DRIVE"
            actions = [
                (label, lambda action=action: self._submit(
                    lambda: self._require_controller().choose_defensive_scheme(action)
                ))
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.FOURTH_DOWN:
            heading = "FOURTH DOWN  /  CHOOSE AN ACTION"
            actions = [
                (action.value.replace("_", " ").upper(), lambda action=action: self._submit(
                    lambda: self._require_controller().choose_fourth_down(action)
                ))
                for action in FootballFourthDownAction
            ]
        else:
            heading = "LOCAL AI IS RESOLVING ITS DRIVE"
            actions = []

        draw_text(
            surface,
            heading,
            (rect.left + 2, rect.top + 1),
            self._small_font,
            self.theme.secondary_accent,
        )
        buttons: list[Button] = []
        if actions:
            gap = 8
            button_width = (rect.width - gap * 2) // 3
            button_height = min(43, max(32, (rect.height - 26) // 2))
            for index, (label, callback) in enumerate(actions):
                row, column = divmod(index, 3)
                button_rect = pygame.Rect(
                    rect.left + column * (button_width + gap),
                    rect.top + 23 + row * (button_height + 6),
                    button_width,
                    button_height,
                )
                buttons.append(
                    Button(
                        label,
                        callback,
                        button_rect,
                        variant="primary" if index == 0 else "quiet",
                    )
                )
        else:
            draw_text(
                surface,
                "No human action is currently required.",
                (rect.left + 2, rect.top + 25),
                self._small_font,
                self.theme.muted,
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_result(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        match = state.match
        if match is None or match.final_result is None:
            raise RuntimeError("A season result requires the completed match result.")
        result = match.final_result
        won = result.winner is FootballTeamSide.TEAM_A
        result_panel = pygame.Rect(
            content.left + 40,
            content.top + 15,
            content.width - 80,
            content.height - 58,
        )
        draw_panel(surface, result_panel, self.theme, fill=self.theme.panel)
        draw_text(
            surface,
            "VICTORY" if won else "DEFEAT",
            (result_panel.left + 30, result_panel.top + 25),
            self._display_font,
            self.theme.primary_accent if won else self.theme.danger,
        )
        draw_text(
            surface,
            f"{match.team_a.team_name}  {result.team_a_score}  -  "
            f"{result.team_b_score}  {match.team_b.team_name}",
            (result_panel.left + 34, result_panel.top + 96),
            self._title_font,
            self.theme.text,
        )
        draw_text(
            surface,
            f"GAME {state.game_number}  |  RECORD {state.wins}-{state.losses}",
            (result_panel.left + 34, result_panel.top + 145),
            self._label_font,
            self.theme.secondary_accent,
        )

        if state.phase is FootballRunPhase.READY_FOR_NEXT_GAME:
            explanation = "You are still in the regular season. Start the next game when ready."
            primary_label = "NEXT REGULAR-SEASON GAME"
            primary_action = self._start_next_game
        elif state.phase is FootballRunPhase.FIRED:
            explanation = "Three losses ended this run. Start a new run from the main menu."
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self._return_to_menu
        else:
            explanation = (
                "You survived game 10 and reached the playoffs marker. "
                "This prototype does not include a playoff bracket."
            )
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self._return_to_menu
        draw_wrapped_text(
            surface,
            explanation,
            pygame.Rect(
                result_panel.left + 34,
                result_panel.top + 190,
                result_panel.width - 68,
                72,
            ),
            self._body_font,
            self.theme.muted,
        )
        primary_rect = pygame.Rect(
            result_panel.left + 34,
            result_panel.bottom - 58,
            min(360, result_panel.width - 68),
            42,
        )
        buttons = [
            Button(primary_label, primary_action, primary_rect, variant="primary")
        ]
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _format_event(
        self, event: FootballMatchEvent, team_a_name: str, team_b_name: str
    ) -> str:
        if isinstance(event.action, DefensiveSchemeAction):
            defense = team_a_name if event.possession is FootballTeamSide.TEAM_B else team_b_name
            description = f"{defense} sets {_SCHEME_LABELS[event.action]}"
        elif isinstance(event.action, OffensivePlayAction):
            offense = team_a_name if event.possession is FootballTeamSide.TEAM_A else team_b_name
            result = event.play_result
            if result is None:
                description = f"{offense}: {_PLAY_LABELS[event.action]}"
            elif result.turnover:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - turnover"
            elif result.incomplete:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - incomplete"
            else:
                description = (
                    f"{offense}: {_PLAY_LABELS[event.action]} - "
                    f"{result.yards_gained:+.1f} yd"
                )
        else:
            offense = team_a_name if event.possession is FootballTeamSide.TEAM_A else team_b_name
            description = f"{offense}: {event.action.value.replace('_', ' ').upper()}"
        return _fit_text(description, self._small_font, 1080)

    def _draw_exit_confirmation(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))
        rect = Layout.from_surface(surface).centered_panel(0.52, 0.30)
        draw_panel(surface, rect, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "End this run?",
            (rect.left + 28, rect.top + 24),
            self._title_font,
            self.theme.text,
        )
        draw_wrapped_text(
            surface,
            "Your current draft, upgrades, and season progress will be discarded.",
            pygame.Rect(rect.left + 28, rect.top + 70, rect.width - 56, 48),
            self._body_font,
            self.theme.muted,
        )
        button_width = (rect.width - 76) // 2
        button_y = rect.bottom - 62
        buttons = [
            Button(
                "DISCARD RUN",
                self._return_to_menu,
                pygame.Rect(rect.left + 28, button_y, button_width, 42),
                variant="primary",
            ),
            Button(
                "KEEP PLAYING",
                self._keep_playing,
                pygame.Rect(rect.left + 48 + button_width, button_y, button_width, 42),
            ),
        ]
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _submit(self, action: Callable[[], object]) -> None:
        self.last_error = None
        try:
            action()
        except ValueError as error:
            self.last_error = str(error)
        finally:
            self.state = self._require_controller().state

    def _start_next_game(self) -> None:
        self._submit(self._require_controller().start_next_game)

    def _request_exit(self) -> None:
        self.confirm_exit = True

    def _keep_playing(self) -> None:
        self.confirm_exit = False

    def _return_to_menu(self) -> None:
        self.confirm_exit = False
        self.navigate("main_menu")

    def _current_state(self) -> FootballGameControllerState:
        if self.state is None:
            raise RuntimeError("A football run has not been started.")
        return self.state

    def _require_controller(self) -> FootballGameController:
        if self.controller is None:
            raise RuntimeError("A football run has not been started.")
        return self.controller


def _fit_text(text: str, font: pygame.font.Font, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    shortened = text
    while shortened and font.size(f"{shortened}...")[0] > width:
        shortened = shortened[:-1]
    return f"{shortened}..."
