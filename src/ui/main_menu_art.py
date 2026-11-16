"""Pixel-art stadium and team-colored helmet for the desktop menu."""

from functools import lru_cache
import logging
from pathlib import Path

import pygame

from src.ui.theme import readable_ink

# The controls and their pressed state are inset from this uninterrupted backdrop.
MENU_BACKDROP = pygame.Rect(0, 0, 576, 720)
_ASSET_DIR = Path(__file__).parent / "assets"
_LOG = logging.getLogger(__name__)


def _blend(first: pygame.Color, second: pygame.Color, amount: float) -> pygame.Color:
    return pygame.Color(*(round(a + (b - a) * amount)
                          for a, b in zip(first[:3], second[:3])))


def _floodlight(art: pygame.Surface, x: int, y: int, *, right: bool = False) -> None:
    for radius, alpha in ((67, 3), (55, 5), (44, 8), (34, 13), (25, 20)):
        glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (53, 144, 255, alpha), glow.get_rect())
        art.blit(glow, (x + 24 - radius, y + 15 - radius))
    pygame.draw.polygon(art, "#0b2241", [(x + 18, y + 29), (x + 28, y + 29),
                                        (x + 29, y + 90), (x + 17, y + 90)])
    pygame.draw.rect(art, "#426f9a", (x + 20, y + 29, 6, 62))
    pygame.draw.line(art, "#82aacc", (x + 21, y + 30), (x + 21, y + 89), 1)
    pygame.draw.line(art, "#274e77", (x + 25, y + 30), (x + 25, y + 89), 2)
    slope = -1 if right else 1
    panel = pygame.Surface((56, 38), pygame.SRCALPHA)
    pygame.draw.polygon(panel, "#081931", [(1, 2), (5, 0), (52, 4), (55, 8),
                                           (54, 35), (50, 37), (1, 32)])
    pygame.draw.polygon(panel, "#24558a", [(4, 4), (7, 3), (50, 7),
                                           (51, 33), (5, 29)])
    pygame.draw.polygon(panel, "#4282bb", [(5, 4), (49, 8), (49, 30), (5, 26)], 1)
    for row in range(3):
        for column in range(5):
            lx = 7 + column * 9
            ly = 5 + row * 8 + column // 2
            pygame.draw.rect(panel, "#4c8fc8", (lx - 1, ly - 1, 7, 7))
            pygame.draw.polygon(panel, "#f0f8ff", [(lx + 1, ly), (lx + 4, ly),
                                                     (lx + 5, ly + 1), (lx + 5, ly + 4),
                                                     (lx + 4, ly + 5), (lx, ly + 5),
                                                     (lx, ly + 1)])
            pygame.draw.line(panel, "#ffffff", (lx + 1, ly + 1), (lx + 3, ly + 1), 1)
    art.blit(pygame.transform.flip(panel, slope < 0, False), (x - 3, y - 3))


def _stands(art: pygame.Surface, secondary: pygame.Color) -> None:
    top = [(288, 157), (340, 167), (400, 175), (459, 179),
           (522, 177), (583, 170), (640, 158)]
    pygame.draw.polygon(art, "#091d39", top + [(640, 302), (288, 302)])
    pygame.draw.lines(art, "#315d8a", False, top, 5)
    pygame.draw.lines(art, "#183d67", False,
                      [(288, 164), (350, 176), (413, 184), (478, 186),
                       (550, 181), (640, 165)], 2)

    # Crowd pixels use a fixed integer pattern, not the gameplay random stream.
    crowd_colors = ("#12375f", "#1b416d", "#27517f", "#17345c",
                    "#335983", "#214674", "#364a80", "#3b6590")
    for row in range(30):
        y = 180 + row * 4
        for column in range(88):
            x = 289 + column * 4
            pattern = (column * 37 + row * 73 + column * row * 11) % 23
            if pattern < 8:
                continue
            color = crowd_colors[(column * 3 + row * 5 + pattern) % len(crowd_colors)]
            pygame.draw.rect(art, color, (x + pattern % 2, y + pattern % 2,
                                         2 + pattern % 2, 2 + pattern % 2))

    # Sloping aisles, railings and illuminated advertising ribbon separate tiers.
    for x, end in ((330, 355), (407, 420), (478, 478), (548, 532), (610, 585)):
        pygame.draw.polygon(art, "#0a2545", [(x - 3, 176), (x + 3, 176),
                                             (end + 5, 300), (end - 6, 300)])
        pygame.draw.line(art, "#315c82", (x + 2, 177), (end + 4, 300), 1)
        for step in range(8):
            y = 188 + step * 14
            stair_x = x + round((end - x) * (y - 176) / 124)
            pygame.draw.line(art, "#1c4268", (stair_x - 2, y), (stair_x + 3, y + 1), 1)
    for y in (214, 257, 296):
        line = [(288, y - 8), (352, y + 2), (413, y + 9), (478, y + 11),
                (548, y + 7), (640, y - 6)]
        pygame.draw.lines(art, "#081a32", False, line, 9)
        pygame.draw.lines(art, "#305d8b", False, line, 5)
        pygame.draw.lines(art, "#5280a6", False,
                          [(x, yy - 2) for x, yy in line], 1)
    for x, y, width in ((294, 209, 25), (345, 217, 23), (391, 224, 22),
                        (533, 226, 23), (573, 220, 22), (611, 213, 23)):
        pygame.draw.polygon(art, "#c8def0",
                            [(x, y), (x + width, y + 3),
                             (x + width, y + 6), (x, y + 3)])
        pygame.draw.line(art, "#739abc", (x, y + 4), (x + width, y + 7), 1)

    flag_color = _blend(secondary, pygame.Color("#6c9cce"), 0.35)
    for x, y in ((310, 142), (375, 151), (451, 154), (526, 151), (600, 141)):
        pygame.draw.rect(art, "#638bad", (x, y, 2, 26))
        pygame.draw.polygon(art, "#0b1c38", [(x + 2, y + 2), (x + 17, y + 5),
                                            (x + 12, y + 10), (x + 2, y + 10)])
        pygame.draw.polygon(art, flag_color, [(x + 2, y + 2), (x + 15, y + 5),
                                             (x + 11, y + 8), (x + 2, y + 9)])


def _field(art: pygame.Surface) -> None:
    pygame.draw.rect(art, "#123a39", (288, 301, 352, 59))
    pygame.draw.polygon(art, "#1a514b", [(288, 308), (640, 307), (640, 360), (288, 360)])
    for index in range(7):
        y = 312 + index * 8
        color = "#235d53" if index % 2 == 0 else "#1b514c"
        pygame.draw.polygon(art, color, [(288, y), (640, y - 3),
                                         (640, y + 2), (288, y + 5)])
    pygame.draw.line(art, "#98bba9", (288, 307), (640, 305), 2)
    pygame.draw.line(art, "#4c8b7b", (288, 312), (640, 310), 1)
    for x, y, width in ((294, 319, 47), (351, 317, 35), (550, 316, 44),
                        (602, 318, 31), (298, 337, 63), (555, 334, 57)):
        pygame.draw.line(art, "#87b2a1", (x, y), (x + width, y - 1), 2)
    for row in range(4):
        for col in range(42):
            x = 291 + col * 9 + (row * 7 % 6)
            y = 314 + row * 11 + (col * 13 + row * 7) % 5
            pygame.draw.line(art, "#397b68", (x, y), (x + 3 + col % 5, y), 1)


@lru_cache(maxsize=1)
def _helmet_layers() -> tuple[pygame.Surface, pygame.Surface]:
    base = pygame.image.load(_ASSET_DIR / "menu_helmet_base.png")
    shell = pygame.image.load(_ASSET_DIR / "menu_helmet_shell.png")
    if base.get_size() != shell.get_size():
        raise ValueError("Menu helmet layers have different sizes.")
    return base, shell


@lru_cache(maxsize=32)
def _tinted_helmet(primary_rgb: tuple[int, int, int]) -> pygame.Surface:
    base, shell = _helmet_layers()
    sprite = base.copy()
    primary = pygame.Color(*primary_rgb)
    highlight = pygame.Color("#dcecff")
    for y in range(shell.get_height()):
        for x in range(shell.get_width()):
            intensity, _, _, alpha = shell.get_at((x, y))
            if not alpha:
                continue
            if intensity <= 201:
                factor = max(0.0, intensity / 201)
                color = _blend(pygame.Color("#07152a"), primary, factor)
            else:
                color = _blend(primary, highlight, min(0.55, (intensity - 201) / 115))
            sprite.set_at((x, y), (*color[:3], alpha))
    return sprite


def _helmet(art: pygame.Surface, primary: pygame.Color, secondary: pygame.Color) -> None:
    pygame.draw.ellipse(art, "#0b272d", (383, 312, 208, 12))
    try:
        sprite = _tinted_helmet(tuple(primary[:3]))
    except (OSError, pygame.error, ValueError) as error:
        _LOG.warning("Could not load menu helmet artwork: %s", error)
        _fallback_helmet(art, primary, secondary)
        return
    art.blit(sprite, (398, 190))


def _fallback_helmet(art: pygame.Surface, primary: pygame.Color,
                     secondary: pygame.Color) -> None:
    dark = _blend(primary, pygame.Color("#06142e"), 0.62)
    shadow = _blend(primary, pygame.Color("#07152a"), 0.35)
    light = _blend(primary, pygame.Color("#b5d5f4"), 0.30)
    shine = _blend(primary, pygame.Color("#e5f5ff"), 0.55)
    contrast = readable_ink(primary)

    pygame.draw.ellipse(art, "#0b272d", (383, 312, 208, 12))
    pygame.draw.ellipse(art, "#102f31", (391, 310, 190, 8))
    shell = [(398, 279), (397, 255), (403, 235), (414, 219), (429, 208),
             (447, 201), (470, 200), (489, 204), (506, 214), (519, 229),
             (525, 244), (522, 252), (505, 253), (493, 260), (484, 274),
             (486, 289), (477, 305), (468, 312), (440, 314), (423, 307),
             (411, 297), (405, 287)]
    pygame.draw.polygon(art, "#050f20", shell)
    inner = [(402, 278), (402, 255), (408, 237), (419, 222), (433, 212),
             (448, 206), (469, 205), (487, 209), (503, 218), (515, 232),
             (520, 244), (517, 248), (504, 249), (490, 257), (480, 273),
             (481, 288), (473, 302), (465, 307), (442, 309), (426, 303),
             (415, 294), (408, 285)]
    pygame.draw.polygon(art, primary, inner)
    pygame.draw.polygon(art, _blend(primary, pygame.Color("#193653"), 0.18),
                        [(477, 221), (493, 225), (507, 234), (516, 245),
                         (505, 246), (491, 253), (480, 268), (477, 282),
                         (468, 290), (453, 292), (461, 278), (471, 266),
                         (478, 249)])
    pygame.draw.polygon(art, _blend(primary, pygame.Color("#b5d5f4"), 0.13),
                        [(408, 239), (419, 222), (433, 212), (448, 206),
                         (469, 205), (487, 209), (503, 218), (514, 231),
                         (501, 225), (485, 219), (468, 216), (450, 217),
                         (434, 222), (421, 230), (413, 243)])
    pygame.draw.polygon(art, shadow, [(403, 269), (407, 284), (415, 294),
                                    (426, 303), (442, 309), (465, 307),
                                    (473, 302), (478, 292), (461, 298),
                                    (442, 298), (425, 290), (414, 279)])
    pygame.draw.polygon(art, dark, [(405, 284), (415, 296), (425, 304),
                                  (441, 310), (464, 308), (473, 302),
                                  (466, 304), (444, 304), (428, 298),
                                  (418, 288), (410, 275)])
    pygame.draw.lines(art, light, False, [(407, 246), (413, 231), (422, 220),
                                          (435, 212), (449, 208), (470, 207)], 2)
    pygame.draw.lines(art, shine, False, [(415, 231), (422, 222), (434, 215)], 1)
    pygame.draw.lines(art, light, False, [(405, 250), (403, 259), (403, 271)], 1)
    pygame.draw.lines(art, dark, False, [(482, 211), (500, 220), (511, 233)], 2)

    # The stripe is outlined so similar team colors remain distinguishable.
    pygame.draw.lines(art, contrast, False, [(455, 205), (465, 208), (474, 213)], 7)
    pygame.draw.lines(art, secondary, False, [(455, 205), (465, 208), (474, 213)], 4)

    pygame.draw.circle(art, "#08172a", (455, 280), 9)
    pygame.draw.circle(art, dark, (455, 280), 6)
    pygame.draw.circle(art, "#08172a", (454, 280), 4)
    for x, y in ((438, 299), (470, 298)):
        pygame.draw.circle(art, "#08172a", (x, y), 4)
        pygame.draw.circle(art, "#aac6da", (x, y), 3)
        pygame.draw.circle(art, "#304a63", (x, y), 1)
    pygame.draw.polygon(art, "#172f48", [(407, 300), (420, 302), (423, 310),
                                         (410, 312), (405, 308)])
    pygame.draw.polygon(art, "#aac3d4", [(409, 301), (418, 303), (420, 309),
                                         (411, 309)])

    pygame.draw.polygon(art, "#061322", [(486, 279), (489, 268), (498, 255),
                                        (508, 250), (528, 249), (533, 254),
                                        (525, 259), (514, 259), (504, 267),
                                        (500, 281), (509, 290), (538, 290),
                                        (548, 294), (548, 313), (538, 317),
                                        (506, 314), (497, 307), (491, 293)])
    pygame.draw.polygon(art, "#152b40", [(498, 273), (505, 261), (514, 257),
                                         (526, 257), (528, 284), (511, 285),
                                         (503, 280)])

    def bar(points: list[tuple[int, int]], width: int = 4) -> None:
        pygame.draw.lines(art, "#05101f", False, points, width + 5)
        pygame.draw.lines(art, "#829fb6", False, points, width + 2)
        pygame.draw.lines(art, "#edf7fc", False, points, width)
        pygame.draw.lines(art, "#ffffff", False,
                          [(x, y - 1) for x, y in points], 1)

    bar([(489, 279), (493, 268), (502, 258), (512, 253), (530, 252)])
    bar([(530, 252), (534, 253), (535, 257), (523, 257), (513, 258)], 3)
    bar([(489, 281), (498, 287), (510, 289), (544, 290), (550, 293),
         (550, 313), (546, 316), (512, 316), (503, 311), (498, 303),
         (493, 288)], 3)
    bar([(511, 258), (514, 273), (518, 289), (521, 314)], 3)
    bar([(533, 259), (537, 288)], 3)
    bar([(540, 293), (541, 312)], 3)
    bar([(495, 279), (503, 272), (511, 281)], 3)
    for x, y in ((497, 278), (491, 284), (511, 258), (542, 291)):
        pygame.draw.circle(art, "#10243b", (x, y), 4)
        pygame.draw.circle(art, "#b8d2e3", (x, y), 3)
        pygame.draw.circle(art, "#e9f4fa", (x - 1, y - 1), 1)


@lru_cache(maxsize=32)
def _stadium(primary_rgb: tuple[int, int, int],
             secondary_rgb: tuple[int, int, int]) -> pygame.Surface:
    primary = pygame.Color(*primary_rgb)
    secondary = pygame.Color(*secondary_rgb)
    art = pygame.Surface((640, 360))
    for y in range(0, 180, 6):
        color = _blend(pygame.Color("#07182d"), pygame.Color("#10345e"), y / 240)
        pygame.draw.rect(art, color, (0, y, 640, 6))
    for x, y in ((355, 88), (470, 110), (572, 79)):
        pygame.draw.polygon(art, "#102d50",
                            [(x, y + 12), (x + 10, y + 8), (x + 17, y + 8),
                             (x + 22, y + 3), (x + 34, y + 3), (x + 39, y),
                             (x + 51, y + 1), (x + 54, y + 6), (x + 64, y + 7),
                             (x + 69, y + 12)])
    _floodlight(art, 331, 101)
    _floodlight(art, 570, 96, right=True)
    _stands(art, secondary)
    _field(art)
    _helmet(art, primary, secondary)
    pygame.draw.rect(art, "#061629", (0, 0, MENU_BACKDROP.width // 2, 360))
    return art


def draw_menu_stadium(surface: pygame.Surface, primary: pygame.Color,
                      secondary: pygame.Color) -> None:
    art = _stadium(tuple(primary[:3]), tuple(secondary[:3]))
    surface.blit(pygame.transform.scale(art, surface.get_size()), (0, 0))
