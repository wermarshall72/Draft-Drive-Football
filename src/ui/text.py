import pygame


def wrap_text_lines(
    text: str, font: pygame.font.Font, width: int
) -> tuple[str, ...]:
    if not isinstance(text, str) or width <= 0:
        raise ValueError("Text wrapping requires text and a positive width.")

    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.size(candidate)[0] <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            if font.size(word)[0] <= width:
                line = word
                continue
            fragment = ""
            for character in word:
                candidate = fragment + character
                if fragment and font.size(candidate)[0] > width:
                    lines.append(fragment)
                    fragment = character
                else:
                    fragment = candidate
            line = fragment
        if line:
            lines.append(line)
    return tuple(lines)


def draw_complete_wrapped_text(
    surface: pygame.Surface,
    text: str,
    rect: pygame.Rect,
    font: pygame.font.Font,
    color: pygame.Color,
    *,
    line_gap: int = 2,
) -> int:
    lines = wrap_text_lines(text, font, rect.width)
    line_height = font.get_height() + line_gap
    required_height = max(0, len(lines) * line_height - line_gap)
    if required_height > rect.height:
        raise ValueError("Wrapped text does not fit in the supplied rectangle.")
    for index, line in enumerate(lines):
        surface.blit(
            font.render(line, True, color),
            (rect.left, rect.top + index * line_height),
        )
    return required_height


def fit_text(text: str, font: pygame.font.Font, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    shortened = text
    while shortened and font.size(f"{shortened}...")[0] > width:
        shortened = shortened[:-1]
    return f"{shortened}..."
