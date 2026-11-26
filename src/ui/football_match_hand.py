"""Both human hands as labeled card groups, plus the active-scheme slot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    FootballBonusCardAction,
    FootballCardCopy,
    FootballCardFamily,
    FootballMatchState,
    FootballTeamSide,
)
from src.engine.football_controller import FootballGameControllerState, FootballHumanDecision
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.ui.football_player_perks import activation_preview_note
from src.engine.football_simulator import (
    adjusted_offensive_play_clock_seconds,
    calculate_blind_play_estimate,
)
from src.ui.football_card_art import (
    bonus_card_art,
    draw_card_art,
    play_card_art,
    scheme_card_art,
)
from src.ui.football_match_events import bonus_effect, play_family_kind
from src.ui.football_match_field import PLAY_LINE_COLORS
from src.ui.football_match_interaction import MatchInteraction
from src.ui.football_match_palette import (
    MATCH_CANVAS, MATCH_DIM, MATCH_FOCUS, MATCH_GOLD, MATCH_INK, MATCH_MUTED,
    MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH, MATCH_TEXT, blit_text, match_font, mix, plain_font,
)
from src.ui.football_ui_kit import draw_card_shell, draw_two_cells, fit_wrapped  # noqa: F401
from src.ui.text import fit_text, wrap_text_lines
from src.ui.widgets import Button

GROUP_LABEL_HEIGHT = 22
CARD_GAP = 8
GROUP_GAP = 28
MAX_CARD_WIDTH = 116
MIN_CARD_WIDTH = 72
OFFENSE = "offense"
DEFENSE = "defense"
# The fallback resolves OffensivePlayAction.RB_RUN / DefensiveSchemeAction.RB_RUN, whose
# catalog ids are both "rb_run"; it is drawn from that definition but never enters a deck.
FALLBACK_CARD_ID = "rb_run"
FALLBACK_DISPLAY_ID = "basic-fallback-display"
# The tooltip's last line: the rival's defense call is secret, so previews
# average over every call the rival owns.
SECRET_DEFENSE_LINE = "Rival call: secret"


@dataclass(frozen=True)
class CardPreview:
    yards: str
    clock: str
    live: bool
    notes: tuple[str, ...] = ()  # player perks the live estimate includes
    # Compact tooltip lines: expected yards, miss/fumble chance, clock, secret call.
    tooltip: tuple[str, ...] = ()


def _percent(probability: float) -> str:
    """'30%', '2%', or '0.5%' for small chances that would otherwise round to zero."""
    value = probability * 100
    if value >= 9.5 or value == 0:
        return f"{value:.0f}%"
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def preview_is_live(match: FootballMatchState) -> bool:
    """A live estimate exists while the human has the ball (or a two-point try) and
    the rival has set its (secret) defense call."""
    if match.current_drive_defensive_scheme is None or match.status.value == "completed":
        return False
    if match.conversion_team is not None:
        return match.conversion_team is FootballTeamSide.TEAM_A
    return match.possession is FootballTeamSide.TEAM_A


def tooltip_lines(match: FootballMatchState, estimate, seconds: int | None) -> tuple[str, ...]:
    """One short line each: expected yards, miss or fumble chance, clock, secret call.

    ``estimate`` is the blind estimate: it never says whether the rival's call
    stops the card.
    """
    fumble = estimate.family is FootballCardFamily.RB_RUN or estimate.keep_read
    risk = (
        f"~{_percent(estimate.turnover_probability)} fumble" if fumble
        else f"~{_percent(estimate.incomplete_probability)} incomplete"
    )
    clock = f"{seconds}s clock" if seconds is not None else "No clock on a 2-pt try"
    return (f"~{estimate.expected_yards:.1f} yds expected", risk, clock, SECRET_DEFENSE_LINE)


@dataclass(frozen=True)
class GroupLayout:
    name: str
    area: pygame.Rect
    card_rects: tuple[pygame.Rect, ...]
    first_visible: int
    active_slot: pygame.Rect | None
    max_scroll: int
    fallback_slot: pygame.Rect | None = None


def active_group(
    state: FootballGameControllerState, *, input_blocked: bool
) -> str | None:
    if input_blocked:
        return None
    decision = state.human_decision
    if decision in (FootballHumanDecision.OFFENSIVE_PLAY, FootballHumanDecision.CONVERSION):
        return OFFENSE
    if decision in (FootballHumanDecision.DEFENSIVE_SCHEME, FootballHumanDecision.GREEN_DOG):
        return DEFENSE
    return None


def layout_groups(
    rect: pygame.Rect,
    offense_count: int,
    defense_count: int,
    scroll: dict[str, int],
    *,
    offense_fallback: bool = False,
) -> tuple[GroupLayout, GroupLayout]:
    """Place both groups without overlap, shrinking cards and then scrolling.

    The defense group always ends in a fixed active-scheme slot. With
    ``offense_fallback`` the offense group ends in a fixed basic-run slot; fixed
    slots never scroll out of view.
    """
    offense_slots = max(0 if offense_fallback else 1, offense_count)
    defense_slots = max(1, defense_count)
    fixed = 1 + (1 if offense_fallback else 0)
    total_slots = offense_slots + defense_slots + fixed
    available = rect.width - GROUP_GAP - CARD_GAP * (total_slots - 2) - 6
    width = min(MAX_CARD_WIDTH, available // total_slots)
    card_top = rect.top + GROUP_LABEL_HEIGHT + 6
    height = min(rect.bottom - card_top - 2, round(MAX_CARD_WIDTH * 1.84))
    if width >= MIN_CARD_WIDTH:
        visible_offense, visible_defense = offense_slots, defense_slots
    else:
        width = MIN_CARD_WIDTH
        fits = (rect.width - GROUP_GAP - 6 + CARD_GAP * 2) // (width + CARD_GAP) - fixed
        minimum_offense = 0 if offense_slots == 0 else 1
        scrollable = offense_slots + defense_slots
        visible_offense = max(minimum_offense, min(offense_slots, round(fits * offense_slots / scrollable)))
        visible_defense = max(1, min(defense_slots, fits - visible_offense))
        visible_offense = max(minimum_offense, min(offense_slots, fits - visible_defense))
    offense_cells = visible_offense + (1 if offense_fallback else 0)
    offense_width = offense_cells * width + CARD_GAP * (offense_cells - 1)
    defense_width = (visible_defense + 1) * width + CARD_GAP * visible_defense + 6
    used = offense_width + GROUP_GAP + defense_width
    left = rect.left + max(0, (rect.width - used) // 2)

    def build(name: str, x: int, count: int, visible: int, *, with_active: bool,
              with_fallback: bool) -> GroupLayout:
        max_scroll = max(0, count - visible)
        first = max(0, min(scroll.get(name, 0), max_scroll))
        rects = tuple(
            pygame.Rect(x + index * (width + CARD_GAP), card_top, width, height)
            for index in range(min(visible, max(count, 0)))
        )
        group_width = visible * width + CARD_GAP * (visible - 1)
        active = fallback = None
        if with_fallback:
            fallback = pygame.Rect(x + visible * (width + CARD_GAP), card_top, width, height)
            group_width = fallback.right - x
        if with_active:
            active = pygame.Rect(x + group_width + CARD_GAP + 6, card_top, width, height)
            group_width = active.right - x
        area = pygame.Rect(x, rect.top, group_width, rect.bottom - rect.top)
        return GroupLayout(name, area, rects, first, active, max_scroll, fallback)

    offense = build(OFFENSE, left, offense_count, visible_offense,
                    with_active=False, with_fallback=offense_fallback)
    defense = build(DEFENSE, left + offense_width + GROUP_GAP, defense_count, visible_defense,
                    with_active=True, with_fallback=False)
    return offense, defense


def needs_offense_fallback(state: FootballGameControllerState, *, input_blocked: bool) -> bool:
    """The engine allows the basic inside run whenever the hand holds no play card."""
    match = state.match
    if input_blocked or match is None or state.human_decision is not FootballHumanDecision.OFFENSIVE_PLAY:
        return False
    deck = match.team_a_offense_deck
    return deck is not None and not any(card.card_id in OFFENSIVE_PLAY_CATALOG for card in deck.hand)


@dataclass
class HandView:
    """Stateless per frame apart from a small estimate cache."""

    _estimate_cache: dict | None = None
    # Button index -> (copy id, card id, card rect) for offense cards with a live
    # estimate this frame; the match screen shows their tooltip after a short hover.
    tooltip_targets: dict | None = None

    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
        display_match: FootballMatchState,
        interaction: MatchInteraction,
        *,
        input_blocked: bool,
        focus_index: int,
        hover_index: int | None,
        pressed_index: int | None,
        button_offset: int,
        choose_card: Callable[[str], None],
        choose_fallback: Callable[[bool], None],
    ) -> list[Button]:
        match = state.match
        assert match is not None
        offense_deck = match.team_a_offense_deck
        defense_deck = match.team_a_defense_deck
        if offense_deck is None or defense_deck is None:
            raise RuntimeError("The controller did not provide the human's match decks.")
        active = active_group(state, input_blocked=input_blocked)
        # Replays show post-replay hands, so they never carry tooltips.
        self.tooltip_targets = {}
        live = not input_blocked and preview_is_live(display_match)
        offense_fallback = needs_offense_fallback(state, input_blocked=input_blocked)
        offense_layout, defense_layout = layout_groups(
            rect, len(offense_deck.hand), len(defense_deck.hand), interaction.group_scroll,
            offense_fallback=offense_fallback,
        )
        if active is not None and self._reveal_playable(
            state, match, active, offense_layout if active == OFFENSE else defense_layout,
            offense_deck if active == OFFENSE else defense_deck, interaction,
        ):
            offense_layout, defense_layout = layout_groups(
                rect, len(offense_deck.hand), len(defense_deck.hand), interaction.group_scroll,
                offense_fallback=offense_fallback,
            )
        interaction.group_areas = {OFFENSE: offense_layout.area, DEFENSE: defense_layout.area}
        interaction.group_max_scroll = {
            OFFENSE: offense_layout.max_scroll, DEFENSE: defense_layout.max_scroll,
        }
        for layout in (offense_layout, defense_layout):
            interaction.group_scroll[layout.name] = layout.first_visible
        interaction.card_rects = {}
        buttons: list[Button] = []
        dragged_face: tuple[FootballCardCopy, str] | None = None

        for layout, deck in ((offense_layout, offense_deck), (defense_layout, defense_deck)):
            is_active = layout.name == active
            self._draw_group_label(surface, layout, len(deck.hand), is_active)
            visible = deck.hand[layout.first_visible:layout.first_visible + len(layout.card_rects)]
            if not deck.hand and layout.card_rects == () and layout.fallback_slot is None:
                slot = pygame.Rect(layout.area.left, rect.top + GROUP_LABEL_HEIGHT + 6,
                                   (layout.active_slot.left - layout.area.left - CARD_GAP - 6)
                                   if layout.active_slot else layout.area.width,
                                   rect.bottom - rect.top - GROUP_LABEL_HEIGHT - 8)
                slot.height = min(slot.height, round(MAX_CARD_WIDTH * 1.84))
                fallback = is_active and state.human_decision in (
                    FootballHumanDecision.OFFENSIVE_PLAY, FootballHumanDecision.DEFENSIVE_SCHEME,
                )
                if fallback:
                    index = button_offset + len(buttons)
                    label = "FALLBACK / INSIDE RUN" if layout.name == OFFENSE else "FALLBACK / RUN FIT"
                    button = Button(
                        label,
                        lambda offensive=layout.name == OFFENSE: choose_fallback(offensive),
                        slot,
                        variant="hand-fallback",
                    )
                    buttons.append(button)
                    self._draw_fallback(
                        surface, slot, layout.name, display_match,
                        focused=focus_index == index, hovered=hover_index == index,
                        pressed=pressed_index == index,
                    )
                else:
                    self._draw_empty(surface, slot, "EMPTY HAND", "DRAWS NEXT SNAP", focused=False)
            for card, card_rect in zip(visible, layout.card_rects):
                selectable, enabled, reason = self._card_rules(
                    card, layout.name, is_active, state, match
                )
                index = button_offset + len(buttons)
                focused = selectable and focus_index == index
                hovered = selectable and hover_index == index
                pressed = selectable and pressed_index == index
                being_dragged = interaction.dragging_card_id == card.copy_id and interaction.dragging
                face_rect = card_rect.move(0, -8 if (focused or hovered) and enabled and not pressed else 0)
                self._draw_card(
                    surface, face_rect, card, layout.name, display_match,
                    selectable=selectable, enabled=enabled, reason=reason,
                    highlighted=(focused or hovered) and enabled, ghost=being_dragged,
                )
                if being_dragged:
                    dragged_face = (card, layout.name)
                if selectable:
                    if enabled:
                        interaction.card_rects[card.copy_id] = card_rect
                    if live and layout.name == OFFENSE and card.card_id in OFFENSIVE_PLAY_CATALOG:
                        self.tooltip_targets[index] = (card.copy_id, card.card_id, face_rect)
                    buttons.append(
                        Button(
                            self._card_name(card, layout.name).upper(),
                            lambda copy_id=card.copy_id: choose_card(copy_id),
                            card_rect,
                            enabled=enabled,
                            variant="hand-card",
                        )
                    )
            if layout.fallback_slot is not None:
                index = button_offset + len(buttons)
                if live:
                    self.tooltip_targets[index] = (
                        FALLBACK_DISPLAY_ID, FALLBACK_CARD_ID, layout.fallback_slot,
                    )
                buttons.append(
                    Button(
                        "FALLBACK / INSIDE RUN",
                        lambda: choose_fallback(True),
                        layout.fallback_slot,
                        variant="hand-fallback",
                    )
                )
                self._draw_fallback(
                    surface, layout.fallback_slot, OFFENSE, display_match,
                    focused=focus_index == index, hovered=hover_index == index,
                    pressed=pressed_index == index,
                )
            if layout.active_slot is not None:
                self._draw_active_slot(surface, layout.active_slot, display_match)
            if layout.max_scroll:
                buttons.extend(
                    self._scroll_buttons(surface, layout, interaction, button_offset + len(buttons),
                                         focus_index, hover_index)
                )

        if dragged_face is not None and interaction.pointer is not None:
            card, group = dragged_face
            sample = next(iter(offense_layout.card_rects or defense_layout.card_rects))
            ghost = sample.copy()
            ghost.center = interaction.pointer
            self._draw_card(surface, ghost, card, group, display_match, selectable=True,
                            enabled=True, reason=None, highlighted=True, ghost=False)
        return buttons

    def _reveal_playable(
        self,
        state: FootballGameControllerState,
        match: FootballMatchState,
        group: str,
        layout: GroupLayout,
        deck,
        interaction: MatchInteraction,
    ) -> bool:
        """Once per decision, scroll so a playable card is in view if none is."""
        key = (len(match.match_events), state.human_decision, group)
        if interaction.auto_scroll_key == key:
            return False
        interaction.auto_scroll_key = key
        if not layout.max_scroll:
            return False
        enabled = [
            index for index, card in enumerate(deck.hand)
            if self._card_rules(card, group, True, state, match)[1]
        ]
        window = range(layout.first_visible, layout.first_visible + len(layout.card_rects))
        if not enabled or any(index in window for index in enabled):
            return False
        interaction.group_scroll[group] = min(enabled[0], layout.max_scroll)
        return True

    # -- rules -----------------------------------------------------------------

    @staticmethod
    def _card_rules(
        card: FootballCardCopy,
        group: str,
        is_active: bool,
        state: FootballGameControllerState,
        match: FootballMatchState,
    ) -> tuple[bool, bool, str | None]:
        """(selectable, enabled, disabled reason) for one card."""
        if not is_active:
            return False, False, None
        if group == DEFENSE:
            return True, True, None
        bonus = BONUS_CARD_CATALOG.get(card.card_id)
        if state.human_decision is FootballHumanDecision.CONVERSION:
            if bonus is not None:
                return True, False, "NOT ON A 2-PT TRY"
            return True, True, None
        if bonus is None:
            return True, True, None
        if bonus.action is FootballBonusCardAction.CHALLENGE:
            if not state.challenge_available:
                return True, False, "AFTER YOUR NEXT PLAY"
            # The engine accepts only the first Challenge copy in hand.
            deck = match.team_a_offense_deck
            first = next(
                (c.copy_id for c in deck.hand if c.card_id == FootballBonusCardAction.CHALLENGE.value),
                None,
            ) if deck is not None else None
            if card.copy_id != first:
                return True, False, "ONE CHALLENGE PER PLAY"
            return True, True, None
        if bonus.action in (
            FootballBonusCardAction.DEFENSIVE_DRAW,
            FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
        ):
            deck = match.team_a_defense_deck
            if deck is None or not (deck.draw_pile or deck.discard_pile):
                return True, False, "NO SCHEME TO DRAW"
        return True, True, None

    @staticmethod
    def _card_name(card: FootballCardCopy, group: str) -> str:
        if card.card_id in BONUS_CARD_CATALOG:
            return BONUS_CARD_CATALOG[card.card_id].name
        catalog = OFFENSIVE_PLAY_CATALOG if group == OFFENSE else DEFENSIVE_SCHEME_CATALOG
        return catalog[card.card_id].name

    def card_preview(self, match: FootballMatchState, card_id: str) -> "CardPreview":
        """Live expected yards and clock for an offensive card, or printed base values."""
        definition = OFFENSIVE_PLAY_CATALOG[card_id]
        if not preview_is_live(match):
            return CardPreview(f"{definition.base_yards:.0f}", f"{definition.clock_seconds}s", False)
        key = (id(match), match.match_events[-1].sequence if match.match_events else 0, card_id)
        if self._estimate_cache is None or len(self._estimate_cache) > 64:
            self._estimate_cache = {}
        cached = self._estimate_cache.get(key)
        # ``id`` values are reused after garbage collection, so the cached entry
        # keeps its match and is used only for that very object.
        if cached is None or cached[0] is not match:
            conversion = match.conversion_team is not None
            # The rival's call is secret: average over every call it owns.
            estimate = calculate_blind_play_estimate(
                match, definition.action, offense_side=FootballTeamSide.TEAM_A,
                is_conversion=conversion,
            )
            # Two-point tries are untimed.
            seconds = None if conversion else adjusted_offensive_play_clock_seconds(
                definition.clock_seconds, match.team_a_coach_upgrades
            )
            # Your own perks first, then the rival's that change this card.
            ordered = sorted(
                estimate.player_perks,
                key=lambda activation: activation.team is not FootballTeamSide.TEAM_A,
            )
            notes = tuple(activation_preview_note(activation) for activation in ordered)
            cached = (match, CardPreview(
                f"~{estimate.expected_yards:.1f}", f"{seconds or 0}s", True, notes,
                tooltip=tooltip_lines(match, estimate, seconds),
            ))
            self._estimate_cache[key] = cached
        return cached[1]

    # -- drawing ---------------------------------------------------------------

    @staticmethod
    def _draw_group_label(
        surface: pygame.Surface, layout: GroupLayout, count: int, active: bool
    ) -> None:
        title = "OFFENSE" if layout.name == OFFENSE else "DEFENSE"
        font = match_font(15)
        color = MATCH_TEXT if active else MATCH_MUTED
        reserved = 60 if layout.max_scroll else 0  # room for the scroll arrows
        text = f"{title} HAND"
        if font.size(text)[0] + 40 + (90 if active else 0) + reserved > layout.area.width:
            text = title
        y = layout.area.top + GROUP_LABEL_HEIGHT // 2
        label_box = pygame.Rect(layout.area.left, layout.area.top, layout.area.width - reserved,
                                GROUP_LABEL_HEIGHT)
        label_rect = blit_text(surface, font, text, color, label_box,
                               midleft=(layout.area.left + 2, y))
        chip_font = match_font(12)
        chip_rect = pygame.Rect((0, 0), chip_font.size(str(count))).inflate(12, 2)
        chip_rect.midleft = (label_rect.right + 8, y)
        pygame.draw.rect(surface, MATCH_TEXT if active else MATCH_DIM, chip_rect, border_radius=8)
        blit_text(surface, chip_font, str(count), MATCH_INK, chip_rect.inflate(2, 2), center=chip_rect.center)
        if active and chip_rect.right + 90 + reserved <= layout.area.right:
            call_rect = pygame.Rect((0, 0), chip_font.size("YOUR CALL")).inflate(14, 2)
            call_rect.midleft = (chip_rect.right + 8, y)
            pygame.draw.rect(surface, MATCH_FOCUS, call_rect, border_radius=8)
            blit_text(surface, chip_font, "YOUR CALL", MATCH_INK, call_rect, center=call_rect.center)
        pygame.draw.line(
            surface, MATCH_FOCUS if active else MATCH_PANEL_EDGE_SOFT,
            (layout.area.left, layout.area.top + GROUP_LABEL_HEIGHT + 1),
            (layout.area.right, layout.area.top + GROUP_LABEL_HEIGHT + 1),
            2 if active else 1,
        )

    def _draw_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        card: FootballCardCopy,
        group: str,
        match: FootballMatchState,
        *,
        selectable: bool,
        enabled: bool,
        reason: str | None,
        highlighted: bool,
        ghost: bool,
        active_slot: bool = False,
        fallback: bool = False,
    ) -> None:
        bonus = BONUS_CARD_CATALOG.get(card.card_id) if group == OFFENSE else None
        if bonus is not None:
            band = MATCH_GOLD
            art = bonus_card_art(bonus.action)
            family_label = "BONUS CARD"
        elif group == OFFENSE:
            definition = OFFENSIVE_PLAY_CATALOG[card.card_id]
            band = PLAY_LINE_COLORS[play_family_kind(definition.family)]
            art = play_card_art(definition.family)
            family_label = definition.family.label.upper()
        else:
            definition = DEFENSIVE_SCHEME_CATALOG[card.card_id]
            band = PLAY_LINE_COLORS[play_family_kind(definition.family)]
            art = scheme_card_art(definition.family)
            family_label = "DEFENSE CALL"
        fill = MATCH_PANEL_HIGH if bonus is None else mix(MATCH_PANEL_HIGH, MATCH_GOLD, 0.12)
        edge = MATCH_FOCUS if highlighted or active_slot else (
            MATCH_GOLD if bonus is not None else MATCH_PANEL_EDGE)
        border = 3 if highlighted or active_slot else 2
        inner, tile, stats = draw_card_shell(
            surface, rect, art=art, band=band, fill=fill, edge=edge, border=border,
            tile_height=min(round((rect.width - 12) * 0.78), 90), stats_height=42,
            stats_bottom_gap=6,
            art_drawer=lambda target, name, tile_rect: draw_card_art(target, name, tile_rect),
        )
        text_box = pygame.Rect(inner.left, tile.bottom, inner.width, stats.top - tile.bottom)
        y = tile.bottom + 5
        name = self._card_name(card, group).upper()
        # 9 and 8 only apply to the narrowest (scrolling) cards, so long words
        # such as QUARTERBACK never split mid-word.
        name_font, lines = fit_wrapped(name, inner.width, (14, 13, 12, 11, 10, 9, 8), 2)
        for line in lines:
            blit_text(surface, name_font, line, MATCH_TEXT, text_box, midtop=(rect.centerx, y))
            y += name_font.get_height() - 1
        family_color = MATCH_MUTED
        if fallback:
            family_label, family_color = "BASIC FALLBACK", MATCH_FOCUS
        family_font = next(
            (plain_font(size, False) for size in (11, 10, 9)
             if plain_font(size, False).size(family_label)[0] <= inner.width),
            None,
        )
        if family_font is None:
            family_label = {
                "DEFENSE CALL": "DEFENSE", "BONUS CARD": "BONUS", "BASIC FALLBACK": "FALLBACK",
            }.get(
                family_label, family_label
            )
            family_font = plain_font(10, False)
        notes = (
            self.card_preview(match, card.card_id).notes
            if group == OFFENSE and bonus is None and not fallback else ()
        )
        if notes:
            # Perk preview notes take the family line (the art and name already show
            # the family): the first note, plus a count of any others, in up to two lines.
            extra = f" (+{len(notes) - 1})" if len(notes) > 1 else ""
            room = stats.top - (y + 1)
            lines_allowed = 2 if room >= 2 * plain_font(9).get_height() else 1
            note_font, note_lines = fit_wrapped(notes[0] + extra, inner.width, (10, 9), lines_allowed)
            for line in note_lines:
                blit_text(surface, note_font, line, MATCH_GOLD, text_box, midtop=(rect.centerx, y + 1))
                y += note_font.get_height() - 1
        else:
            blit_text(surface, family_font, fit_text(family_label, family_font, inner.width),
                      family_color, text_box, midtop=(rect.centerx, y + 1))

        pygame.draw.rect(surface, MATCH_PANEL_DEEP, stats, border_radius=6)
        if bonus is not None:
            effect_font, effect_lines = fit_wrapped(bonus_effect(bonus.action), stats.width - 8, (11, 10, 9), 2)
            ey = stats.top + 3
            for line in effect_lines:
                blit_text(surface, effect_font, line, MATCH_TEXT, stats, midtop=(stats.centerx, ey))
                ey += effect_font.get_height() - 3
            cost_font = plain_font(11)
            options = (
                ("NO TIME",) if bonus.action is FootballBonusCardAction.CHALLENGE
                else ("10s · NO SNAP", "10s COST", "10s")
            )
            cost = next((text for text in options if cost_font.size(text)[0] <= stats.width - 6), options[-1])
            blit_text(surface, cost_font, cost, MATCH_GOLD, stats,
                      midbottom=(stats.centerx, stats.bottom - 1))
        elif group == OFFENSE:
            preview = self.card_preview(match, card.card_id)
            rows = (
                (preview.yards, "YDS LIVE" if preview.live else "BASE YDS"),
                (preview.clock, "CLOCK" if preview.live else "BASE CLOCK"),
            )
            if stats.width >= 84:
                draw_two_cells(surface, stats, rows)
            else:
                # Narrow cards stack the two values as rows.
                for index, (value, caption) in enumerate(rows):
                    cell = pygame.Rect(stats.left + 4, stats.top + 2 + index * 19, stats.width - 8, 19)
                    value_font = plain_font(14)
                    value_rect = blit_text(surface, value_font, value, MATCH_TEXT, cell,
                                           midleft=(cell.left, cell.centery))
                    caption_font = plain_font(8)
                    caption_box = pygame.Rect(value_rect.right + 2, cell.top,
                                              max(1, cell.right - value_rect.right - 2), cell.height)
                    short = caption.replace("BASE ", "").replace(" LIVE", "")
                    blit_text(surface, caption_font, fit_text(short, caption_font, caption_box.width),
                              MATCH_MUTED, caption_box, midright=(cell.right, cell.centery))
        else:
            blit_text(surface, plain_font(9), "STOPS", MATCH_MUTED, stats,
                      midtop=(stats.centerx, stats.top + 4))
            counter_label = definition.family.label.upper()
            counter_font, counter_lines = fit_wrapped(counter_label, stats.width - 6, (13, 12, 11, 10), 1)
            if counter_font.size(counter_lines[0])[0] > stats.width - 6 or counter_lines[0].endswith("..."):
                counter_font, counter_lines = fit_wrapped(counter_label, stats.width - 6, (11, 10), 2)
            line_height = counter_font.get_height() - 2
            bottom = stats.bottom - 3
            for line in reversed(counter_lines):
                blit_text(surface, counter_font, line, band, stats, midbottom=(stats.centerx, bottom))
                bottom -= line_height

        if not selectable and not active_slot:
            veil = pygame.Surface(rect.size, pygame.SRCALPHA)
            veil.fill((*MATCH_CANVAS[:3], 120))
            surface.blit(veil, rect.topleft)
        elif selectable and not enabled:
            veil = pygame.Surface(rect.size, pygame.SRCALPHA)
            veil.fill((*MATCH_CANVAS[:3], 150))
            surface.blit(veil, rect.topleft)
            if reason:
                font, reason_lines = fit_wrapped(reason, rect.width - 16, (10, 9), 2)
                line_height = font.get_height()
                plate = pygame.Rect(0, 0, max(font.size(line)[0] for line in reason_lines) + 8,
                                    line_height * len(reason_lines) + 4)
                plate.center = (rect.centerx, tile.centery)
                pygame.draw.rect(surface, MATCH_INK, plate, border_radius=4)
                for index, line in enumerate(reason_lines):
                    blit_text(surface, font, line, MATCH_TEXT, rect,
                              midtop=(plate.centerx, plate.top + 2 + index * line_height))
        if ghost:
            veil = pygame.Surface(rect.size, pygame.SRCALPHA)
            veil.fill((*MATCH_CANVAS[:3], 170))
            surface.blit(veil, rect.topleft)

    def card_tooltip(self, match: FootballMatchState, card_id: str) -> tuple[str, ...]:
        """The hover/focus tooltip lines for an offense card (empty without a live estimate)."""
        return self.card_preview(match, card_id).tooltip

    def _draw_fallback(
        self,
        surface: pygame.Surface,
        slot: pygame.Rect,
        group: str,
        match: FootballMatchState,
        *,
        focused: bool,
        hovered: bool,
        pressed: bool,
    ) -> None:
        """The engine's basic action, drawn as a playable card that is not in the deck."""
        card = FootballCardCopy(FALLBACK_DISPLAY_ID, FALLBACK_CARD_ID)
        face = slot.move(0, -8 if (focused or hovered) and not pressed else 0)
        self._draw_card(
            surface, face, card, group, match, selectable=True, enabled=True, reason=None,
            highlighted=focused or hovered, ghost=False, fallback=True,
        )

    def _draw_active_slot(
        self, surface: pygame.Surface, rect: pygame.Rect, match: FootballMatchState
    ) -> None:
        scheme = match.current_drive_defensive_scheme
        human_defending = (
            match.possession is FootballTeamSide.TEAM_B
            and match.conversion_team is None
            and match.status.value != "completed"
        )
        if scheme is not None and human_defending and isinstance(scheme, DefensiveSchemeAction):
            card = FootballCardCopy("active-scheme-display", scheme.value)
            glow = rect.inflate(8, 8)
            pygame.draw.rect(surface, mix(MATCH_FOCUS, MATCH_CANVAS, 0.55), glow, border_radius=12)
            self._draw_card(surface, rect, card, DEFENSE, match, selectable=False, enabled=True,
                            reason=None, highlighted=False, ghost=False, active_slot=True)
            ribbon_fill = MATCH_FOCUS
            ribbon_text = "ACTIVE"
        else:
            self._draw_empty(surface, rect, "ACTIVE", "SET ON DEFENSE", focused=False, dashed=True)
            return
        font = match_font(12)
        text = font.render(ribbon_text, True, MATCH_INK)
        ribbon = text.get_rect().inflate(16, 4)
        ribbon.midtop = (rect.centerx, rect.top - 9)
        pygame.draw.rect(surface, MATCH_INK, ribbon.inflate(2, 2), border_radius=6)
        pygame.draw.rect(surface, ribbon_fill, ribbon, border_radius=5)
        surface.blit(text, text.get_rect(center=ribbon.center))

    @staticmethod
    def _draw_empty(
        surface: pygame.Surface,
        rect: pygame.Rect,
        title: str,
        subtitle: str,
        *,
        focused: bool,
        dashed: bool = False,
    ) -> None:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=9)
        edge = MATCH_FOCUS if focused else MATCH_PANEL_EDGE_SOFT
        if dashed:
            for x in range(rect.left + 6, rect.right - 6, 12):
                pygame.draw.line(surface, edge, (x, rect.top), (min(x + 6, rect.right - 6), rect.top), 2)
                pygame.draw.line(surface, edge, (x, rect.bottom - 1), (min(x + 6, rect.right - 6), rect.bottom - 1), 2)
            for y in range(rect.top + 6, rect.bottom - 6, 12):
                pygame.draw.line(surface, edge, (rect.left, y), (rect.left, min(y + 6, rect.bottom - 6)), 2)
                pygame.draw.line(surface, edge, (rect.right - 1, y), (rect.right - 1, min(y + 6, rect.bottom - 6)), 2)
        else:
            pygame.draw.rect(surface, edge, rect, 3 if focused else 2, border_radius=9)
        title_font = plain_font(13)
        lines = wrap_text_lines(title, title_font, rect.width - 10)
        y = rect.centery - 18
        for line in lines[:2]:
            rendered = title_font.render(line, True, MATCH_MUTED if not focused else MATCH_TEXT)
            surface.blit(rendered, rendered.get_rect(midtop=(rect.centerx, y)))
            y += title_font.get_height()
        sub_font = plain_font(10)
        for line in wrap_text_lines(subtitle, sub_font, rect.width - 10)[:2]:
            rendered = sub_font.render(line, True, MATCH_DIM if not focused else MATCH_FOCUS)
            surface.blit(rendered, rendered.get_rect(midtop=(rect.centerx, y + 2)))
            y += sub_font.get_height()

    @staticmethod
    def _scroll_buttons(
        surface: pygame.Surface,
        layout: GroupLayout,
        interaction: MatchInteraction,
        first_index: int,
        focus_index: int,
        hover_index: int | None,
    ) -> list[Button]:
        y = layout.area.top
        right = layout.area.right
        size = 20
        title = "OFFENSE" if layout.name == OFFENSE else "DEFENSE"
        buttons = [
            Button(f"SCROLL {title} LEFT", lambda: interaction.scroll_group(layout.name, -1),
                   pygame.Rect(right - size * 2 - 4, y, size, size),
                   enabled=layout.first_visible > 0, variant="hand-scroll"),
            Button(f"SCROLL {title} RIGHT", lambda: interaction.scroll_group(layout.name, 1),
                   pygame.Rect(right - size, y, size, size),
                   enabled=layout.first_visible < layout.max_scroll, variant="hand-scroll"),
        ]
        for offset, button in enumerate(buttons):
            index = first_index + offset
            highlighted = button.enabled and (focus_index == index or hover_index == index)
            fill = MATCH_PANEL_HIGH if highlighted else MATCH_PANEL
            pygame.draw.rect(surface, fill, button.rect, border_radius=5)
            pygame.draw.rect(surface, MATCH_FOCUS if highlighted else MATCH_PANEL_EDGE, button.rect,
                             2 if highlighted else 1, border_radius=5)
            color = MATCH_TEXT if button.enabled else MATCH_DIM
            cx, cy = button.rect.center
            heading = -1 if offset == 0 else 1
            pygame.draw.polygon(surface, color, ((cx + heading * 4, cy), (cx - heading * 3, cy - 5),
                                                 (cx - heading * 3, cy + 5)))
        return buttons
