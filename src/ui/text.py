import pygame


def fit_text(text: str, font: pygame.font.Font, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    shortened = text
    while shortened and font.size(f"{shortened}...")[0] > width:
        shortened = shortened[:-1]
    return f"{shortened}..."
