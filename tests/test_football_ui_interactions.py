import pygame

from src.ui.football_match_interaction import HandEventKind, MatchInteraction
from src.ui.football_shop_review import ShopReviewInteraction


def test_match_hand_scroll_and_drag_use_visible_owned_copy() -> None:
    interaction = MatchInteraction(
        hand_max_scroll=2,
        hand_area=pygame.Rect(0, 0, 200, 80),
        card_rects={"copy-a": pygame.Rect(10, 10, 50, 50)},
        play_area=pygame.Rect(0, 100, 100, 60),
    )
    wheel = pygame.event.Event(pygame.MOUSEWHEEL, {"y": -4})
    assert interaction.handle_event(wheel).kind is HandEventKind.HANDLED
    assert interaction.hand_scroll == 2
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (20, 20)})
    assert interaction.handle_event(down).kind is HandEventKind.HANDLED
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (20, 120)})
    result = interaction.handle_event(up)
    assert result.kind is HandEventKind.SELECTED
    assert result.copy_id == "copy-a"
    assert interaction.dragging_card_id is None

    assert interaction.handle_event(down).kind is HandEventKind.HANDLED
    invalid = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (300, 300)})
    assert interaction.handle_event(invalid).kind is HandEventKind.INVALID_DROP
    assert interaction.dragging_card_id is None


def test_shop_review_scrolls_independently_and_closes() -> None:
    review = ShopReviewInteraction(depth_max_scroll=75, playbook_max_scroll=3)
    wheel = pygame.event.Event(pygame.MOUSEWHEEL, {"y": -2})
    assert not review.handle_scroll(wheel)
    review.open_depth_chart()
    assert review.handle_scroll(wheel)
    assert review.depth_scroll == 75
    review.open_playbook()
    assert review.handle_scroll(wheel)
    assert review.playbook_scroll == 2
    assert review.depth_scroll == 75
    review.close()
    assert review.mode is None
    assert review.depth_scroll == 0
    assert review.playbook_scroll == 2
