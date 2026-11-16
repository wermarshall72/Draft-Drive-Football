"""Run-local player artwork identifiers and immutable appearance descriptions."""

from dataclasses import dataclass
from types import MappingProxyType

from src.engine.football import FootballPosition


POSITION_ART = MappingProxyType({
    FootballPosition.QB: "quarterback",
    FootballPosition.RB: "running_back",
    FootballPosition.WR: "wide_receiver",
    FootballPosition.O_LINE: "lineman",
    FootballPosition.D_LINE: "lineman",
    FootballPosition.LINEBACKERS: "linebacker",
    FootballPosition.CORNERBACKS: "defensive_back",
    FootballPosition.SAFETIES: "defensive_back",
})


@dataclass(frozen=True)
class FootballPlayerAppearance:
    asset_key: str
    skin: tuple[int, int, int]
    primary: tuple[int, int, int]
    secondary: tuple[int, int, int]

    def __post_init__(self) -> None:
        if self.asset_key not in POSITION_ART.values():
            raise ValueError("Unknown player artwork identifier.")
        for color in (self.skin, self.primary, self.secondary):
            if (not isinstance(color, tuple) or len(color) != 3
                    or any(isinstance(c, bool) or not isinstance(c, int)
                           or not 0 <= c <= 255 for c in color)):
                raise ValueError("Appearance colors must be RGB tuples.")
