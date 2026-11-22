import pygame

from src.ui.football_match_interaction import HandEventKind, MatchInteraction
from src.ui.football_shop_review import ShopReviewInteraction


def test_match_hand_scroll_and_drag_use_visible_owned_copy() -> None:
    interaction = MatchInteraction(
        group_max_scroll={"offense": 2, "defense": 0},
        group_areas={
            "offense": pygame.Rect(0, 0, 200, 80),
            "defense": pygame.Rect(220, 0, 200, 80),
        },
        card_rects={"copy-a": pygame.Rect(10, 10, 50, 50)},
        play_areas=(pygame.Rect(0, 100, 100, 60),),
    )
    # The wheel scrolls the group under the pointer, clamped to its range.
    interaction.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (20, 20)}))
    wheel = pygame.event.Event(pygame.MOUSEWHEEL, {"y": -4})
    assert interaction.handle_event(wheel).kind is HandEventKind.HANDLED
    assert interaction.group_scroll == {"offense": 2, "defense": 0}
    interaction.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (300, 20)}))
    assert interaction.handle_event(wheel).kind is HandEventKind.IGNORED

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (20, 20)})
    assert interaction.handle_event(down).kind is HandEventKind.HANDLED
    assert not interaction.dragging
    interaction.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (20, 120)}))
    assert interaction.dragging
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (20, 120)})
    result = interaction.handle_event(up)
    assert result.kind is HandEventKind.SELECTED
    assert result.copy_id == "copy-a"
    assert interaction.dragging_card_id is None

    # Releasing on the card itself is a click.
    assert interaction.handle_event(down).kind is HandEventKind.HANDLED
    click = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (25, 25)})
    assert interaction.handle_event(click).kind is HandEventKind.SELECTED

    assert interaction.handle_event(down).kind is HandEventKind.HANDLED
    invalid = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (300, 300)})
    assert interaction.handle_event(invalid).kind is HandEventKind.INVALID_DROP
    assert interaction.dragging_card_id is None
    interaction.handle_event(down)
    interaction.cancel_drag()
    assert interaction.dragging_card_id is None and not interaction.dragging


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
