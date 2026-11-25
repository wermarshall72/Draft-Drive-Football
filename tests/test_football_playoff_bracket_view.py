"""The playoff bracket screen: buttons per stage and text that always fits."""

from __future__ import annotations

import random

import pygame
import pytest

from src.engine.football_playoffs import FootballPlayoffBracket, FootballPlayoffRound
from src.profile import new_team_profile
from src.ui.football_playoff_bracket import (
    RETURN_TO_MENU,
    FootballPlayoffBracketView,
    champion_rect,
    game_rect,
)
from src.ui.football_ui_kit import text_audit
from src.ui.theme import Theme

QF, SF, CH = FootballPlayoffRound
LONG_NAME = "Northern Plains Agricultural And Mechanical Institute Owls"


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield


def _stages(name: str = "Test Owls"):
    def bracket(*results, losses=1):
        built = FootballPlayoffBracket(name, losses, random.Random(3))
        for playoff_round, score, against in results:
            built.record_human_result(playoff_round, score, against)
        return built.state

    return {
        "seeded": (bracket(), "OPEN QUARTERFINAL SHOP"),
        "after quarterfinal": (bracket((QF, 21, 20)), "OPEN SEMIFINAL SHOP"),
        "after semifinal": (bracket((QF, 21, 20), (SF, 17, 10)), "OPEN CHAMPIONSHIP SHOP"),
        "champion": (bracket((QF, 21, 20), (SF, 17, 10), (CH, 28, 24)), RETURN_TO_MENU),
        "eliminated": (bracket((QF, 21, 20), (SF, 3, 38)), RETURN_TO_MENU),
    }


def _draw(bracket, *, ended: bool = False, color: str = "navy"):
    calls: list[str] = []
    theme = Theme.from_profile(new_team_profile("Test Owls", color, "gold"))
    surface = pygame.Surface((1280, 720))
    with text_audit() as records:
        buttons = FootballPlayoffBracketView().draw(
            surface, bracket, theme, record="9-1",
            primary=lambda: calls.append("primary"),
            request_exit=None if ended else (lambda: calls.append("pause")),
        )
    return buttons, records, calls


@pytest.mark.parametrize("stage", list(_stages()))
def test_each_stage_offers_the_next_shop_or_the_menu(stage: str) -> None:
    bracket, label = _stages()[stage]
    ended = label == RETURN_TO_MENU
    buttons, records, calls = _draw(bracket, ended=ended)
    assert [button.label for button in buttons] == [label] + ([] if ended else ["PAUSE"])
    buttons[0].action()
    assert calls == ["primary"]
    texts = [text for text, _rect, _container in records]
    assert "PLAYOFFS" in texts and "QUARTERFINALS" in texts and "CHAMPION" in texts
    if stage == "seeded":
        assert texts.count("TBD") == 3 * 2 + 1  # 3 empty games and the champion slot
        assert "NEXT" in texts
    if stage == "champion":
        assert "NATIONAL CHAMPIONS" in texts and "TBD" not in texts
    if stage == "eliminated":
        assert "ELIMINATED" in texts and "NEXT" not in texts


@pytest.mark.parametrize("name", ["Test Owls", LONG_NAME])
@pytest.mark.parametrize("color", ["navy", "yellow", "crimson"])
def test_text_fits_every_stage(name: str, color: str) -> None:
    screen = pygame.Rect(0, 0, 1280, 720)
    for bracket, label in _stages(name).values():
        _buttons, records, _calls = _draw(bracket, ended=label == RETURN_TO_MENU, color=color)
        for text, rect, container in records:
            assert container.contains(rect), (text, rect, container)
            assert screen.contains(rect), text


def test_bracket_boxes_stay_on_the_board_without_overlapping() -> None:
    from src.ui import football_playoff_bracket as layout

    boxes = [game_rect(playoff_round, slot) for playoff_round in FootballPlayoffRound
             for slot in range(4 >> (playoff_round.value - 1))]
    boxes.append(champion_rect())
    for index, box in enumerate(boxes):
        assert layout.BOARD.contains(box)
        assert not any(box.colliderect(other) for other in boxes[index + 1:])
    assert not layout.BOARD.colliderect(layout.FOOTER)
