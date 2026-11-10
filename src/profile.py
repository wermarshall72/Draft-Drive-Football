import json
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TextIO

PROFILE_PATH = Path.home() / ".cfb-auto-battler" / "profile.json"


@dataclass(frozen=True)
class TeamColor:
    id: str
    display_name: str
    hex_value: str
    ansi_foreground_code: str
    ansi_background_code: str


COLOR_CHOICES = (
    TeamColor("crimson", "Crimson", "#D70000", "38;5;160", "48;5;160"),
    TeamColor("scarlet", "Scarlet", "#FF0000", "38;5;196", "48;5;196"),
    TeamColor("rose", "Rose", "#FF005F", "38;5;197", "48;5;197"),
    TeamColor("coral", "Coral", "#FF5F5F", "38;5;203", "48;5;203"),
    TeamColor("salmon", "Salmon", "#FF8787", "38;5;210", "48;5;210"),
    TeamColor("hot-pink", "Hot Pink", "#FF0087", "38;5;198", "48;5;198"),
    TeamColor("orange", "Orange", "#FF8700", "38;5;208", "48;5;208"),
    TeamColor("amber", "Amber", "#FFAF00", "38;5;214", "48;5;214"),
    TeamColor("gold", "Gold", "#FFD700", "38;5;220", "48;5;220"),
    TeamColor("yellow", "Yellow", "#FFFF00", "38;5;226", "48;5;226"),
    TeamColor("lime", "Lime", "#AFFF00", "38;5;154", "48;5;154"),
    TeamColor("green", "Green", "#00FF00", "38;5;46", "48;5;46"),
    TeamColor("emerald", "Emerald", "#00D700", "38;5;40", "48;5;40"),
    TeamColor("teal", "Teal", "#00D7AF", "38;5;43", "48;5;43"),
    TeamColor("cyan", "Cyan", "#00FFFF", "38;5;51", "48;5;51"),
    TeamColor("sky-blue", "Sky Blue", "#00AFFF", "38;5;39", "48;5;39"),
    TeamColor("azure", "Azure", "#0087FF", "38;5;33", "48;5;33"),
    TeamColor("blue", "Blue", "#0000FF", "38;5;21", "48;5;21"),
    TeamColor("royal-blue", "Royal Blue", "#005FFF", "38;5;27", "48;5;27"),
    TeamColor("navy", "Navy", "#00005F", "38;5;17", "48;5;17"),
    TeamColor("indigo", "Indigo", "#5F00FF", "38;5;57", "48;5;57"),
    TeamColor("violet", "Violet", "#8700FF", "38;5;93", "48;5;93"),
    TeamColor("purple", "Purple", "#AF00FF", "38;5;129", "48;5;129"),
    TeamColor("magenta", "Magenta", "#FF00FF", "38;5;201", "48;5;201"),
    TeamColor("lavender", "Lavender", "#D7AFFF", "38;5;183", "48;5;183"),
    TeamColor("brown", "Brown", "#AF5F00", "38;5;130", "48;5;130"),
    TeamColor("copper", "Copper", "#D75F00", "38;5;166", "48;5;166"),
    TeamColor("olive", "Olive", "#878700", "38;5;100", "48;5;100"),
    TeamColor("slate", "Slate", "#5F8787", "38;5;67", "48;5;67"),
    TeamColor("silver", "Silver", "#BCBCBC", "38;5;250", "48;5;250"),
)
COLOR_BY_ID = {color.id: color for color in COLOR_CHOICES}

_BLOCKED_NAME_WORDS = frozenset(
    {"ass", "asshole", "bastard", "bitch", "damn", "fuck", "shit"}
)
_NAME_WORDS = re.compile(r"[a-z0-9]+")


class ProfileError(ValueError):
    """Raised when a team profile is invalid or cannot be loaded."""


@dataclass(frozen=True)
class TeamProfile:
    profile_id: str
    team_name: str
    primary_color_id: str
    secondary_color_id: str

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.profile_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise ProfileError("Profile ID must be a UUID.") from error
        validate_team_name(self.team_name)
        if self.primary_color_id not in COLOR_BY_ID:
            raise ProfileError("Unknown primary color.")
        if self.secondary_color_id not in COLOR_BY_ID:
            raise ProfileError("Unknown secondary color.")
        if self.primary_color_id == self.secondary_color_id:
            raise ProfileError("Primary and secondary colors must be different.")

    @property
    def primary_color(self) -> TeamColor:
        return COLOR_BY_ID[self.primary_color_id]

    @property
    def secondary_color(self) -> TeamColor:
        return COLOR_BY_ID[self.secondary_color_id]


def validate_team_name(team_name: str) -> str:
    if not isinstance(team_name, str):
        raise ProfileError("Team name must be text.")
    name = team_name.strip()
    if not name:
        raise ProfileError("Team name cannot be empty.")
    if any(
        unicodedata.category(character) in {"Cc", "Cs", "Zl", "Zp"}
        for character in name
    ):
        raise ProfileError("Team name cannot contain terminal control characters.")
    normalized = unicodedata.normalize("NFKC", name).casefold()
    words = set(_NAME_WORDS.findall(normalized))
    if words & _BLOCKED_NAME_WORDS:
        raise ProfileError(
            "Team name contains profanity. This local filter checks a small "
            "list of terms and may not catch every variation."
        )
    return name


def new_team_profile(
    team_name: str, primary_color_id: str, secondary_color_id: str
) -> TeamProfile:
    return TeamProfile(
        profile_id=str(uuid.uuid4()),
        team_name=validate_team_name(team_name),
        primary_color_id=primary_color_id,
        secondary_color_id=secondary_color_id,
    )


def load_profile(
    profile_path: str | os.PathLike[str] = PROFILE_PATH,
) -> TeamProfile | None:
    path = Path(profile_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ProfileError("Saved profile must contain a JSON object.")
        return TeamProfile(
            profile_id=data["profile_id"],
            team_name=data["team_name"],
            primary_color_id=data["primary_color_id"],
            secondary_color_id=data["secondary_color_id"],
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ProfileError(
            f"Unable to load team profile from {path}: {error}"
        ) from error


def save_profile(
    profile: TeamProfile, profile_path: str | os.PathLike[str] = PROFILE_PATH
) -> None:
    path = Path(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "profile_id": profile.profile_id,
                "team_name": profile.team_name,
                "primary_color_id": profile.primary_color_id,
                "secondary_color_id": profile.secondary_color_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def supports_ansi_color(
    stream: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    terminal = sys.stdout if stream is None else stream
    environment = os.environ if environ is None else environ
    if "NO_COLOR" in environment or environment.get("TERM") == "dumb":
        return False
    return bool(getattr(terminal, "isatty", lambda: False)())


def style_text(
    text: str,
    *,
    foreground: TeamColor | None = None,
    background: TeamColor | None = None,
    enabled: bool | None = None,
) -> str:
    use_color = supports_ansi_color() if enabled is None else enabled
    if not use_color:
        return text
    codes = []
    if foreground is not None:
        codes.append(foreground.ansi_foreground_code)
    if background is not None:
        codes.append(background.ansi_background_code)
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def format_color_grid(
    primary_color_id: str | None = None,
    secondary_color_id: str | None = None,
    *,
    ansi_enabled: bool | None = None,
) -> str:
    rows = []
    for row_start in range(0, len(COLOR_CHOICES), 6):
        cells = []
        for index, color in enumerate(
            COLOR_CHOICES[row_start : row_start + 6], start=row_start + 1
        ):
            marker = (
                "P"
                if color.id == primary_color_id
                else "S"
                if color.id == secondary_color_id
                else "-"
            )
            label = f"{index:02d} {color.display_name:<10} {marker}"
            swatch = style_text("  ", background=color, enabled=ansi_enabled)
            cells.append(label + swatch)
        rows.append("  ".join(cells))
    return "\n".join(rows)
