"""Original placeholder football figure, drawn in the selected team colors."""

import pygame


def draw_draft_player(
    surface: pygame.Surface,
    rect: pygame.Rect,
    primary: pygame.Color,
    secondary: pygame.Color,
) -> None:
    """Draw a stylized, anonymous uniformed player; this is not production art."""
    figure = pygame.Surface((180, 230), pygame.SRCALPHA)
    dark = pygame.Color("#202a27")
    light = pygame.Color("#f0e8d4")
    shadow = pygame.Color("#17221e")

    pygame.draw.ellipse(figure, (23, 34, 30, 65), (29, 215, 122, 11))
    # Cleats, legs, pants, and jersey are separate pieces of equipment.
    pygame.draw.polygon(figure, dark, [(57, 204), (77, 204), (76, 218), (48, 218)])
    pygame.draw.polygon(figure, dark, [(103, 204), (123, 204), (132, 218), (104, 218)])
    pygame.draw.polygon(figure, light, [(59, 144), (83, 146), (78, 208), (57, 208)])
    pygame.draw.polygon(figure, light, [(97, 146), (121, 144), (123, 208), (102, 208)])
    pygame.draw.line(figure, secondary, (60, 158), (59, 200), 4)
    pygame.draw.line(figure, secondary, (120, 158), (121, 200), 4)
    pygame.draw.polygon(figure, secondary, [(56, 125), (124, 125), (121, 162),
                                           (96, 165), (90, 151), (84, 165), (59, 162)])
    pygame.draw.polygon(figure, light, [(32, 81), (46, 83), (39, 132), (31, 147),
                                       (20, 141), (23, 125)])
    pygame.draw.polygon(figure, light, [(148, 81), (134, 83), (141, 132), (149, 147),
                                       (160, 141), (157, 125)])
    pygame.draw.polygon(figure, primary, [(59, 53), (44, 58), (27, 74), (31, 101),
                                         (48, 104), (53, 141), (127, 141),
                                         (132, 104), (149, 101), (153, 74),
                                         (136, 58), (121, 53)])
    pygame.draw.polygon(figure, secondary, [(29, 79), (46, 70), (49, 91), (31, 99)])
    pygame.draw.polygon(figure, secondary, [(151, 79), (134, 70), (131, 91), (149, 99)])
    pygame.draw.line(figure, light, (55, 134), (125, 134), 2)
    pygame.draw.polygon(figure, light, [(73, 82), (83, 82), (83, 112), (72, 112),
                                       (72, 105), (76, 105), (76, 90), (73, 92)])
    pygame.draw.polygon(figure, light, [(94, 82), (109, 82), (109, 112), (94, 112)])
    pygame.draw.rect(figure, primary, (99, 88, 5, 18))
    pygame.draw.polygon(figure, shadow, [(70, 51), (110, 51), (117, 61),
                                        (104, 68), (76, 68), (63, 61)])
    pygame.draw.ellipse(figure, primary, (59, 4, 62, 58))
    pygame.draw.polygon(figure, secondary, [(84, 5), (96, 5), (97, 43), (83, 43)])
    pygame.draw.polygon(figure, dark, [(63, 31), (117, 31), (113, 48),
                                     (103, 57), (77, 57), (67, 48)])
    pygame.draw.polygon(figure, light, [(70, 36), (110, 36), (106, 44), (74, 44)])
    pygame.draw.lines(figure, light, False, [(65, 34), (64, 51), (76, 60),
                                            (104, 60), (116, 51), (115, 34)], 3)
    pygame.draw.line(figure, light, (68, 48), (112, 48), 3)
    pygame.draw.line(figure, light, (76, 39), (76, 56), 2)
    pygame.draw.line(figure, light, (104, 39), (104, 56), 2)
    scaled = pygame.transform.smoothscale(figure, rect.size)
    surface.blit(scaled, rect)
