"""The catalog of local AI opponent identities and each run's draw from it.

An AI team is cosmetic: a mascot name, a 2-4 letter abbreviation for tight
spaces, and primary/secondary colors given as ``COLOR_CHOICES`` ids from
``src/profile.py`` (kept as plain ids here so the engine needs no profile or UI
import). Rosters, coaches, and decks are still generated per game by
``FootballAI``. The catalog was reviewed in ``docs/ai-team-names.md``; keep
team ids stable because saves store them.

A run draws its AI teams once, at the start: the ten regular-season rivals in
schedule order, then ten reserve teams. The playoff bracket fills its seven AI
seeds from the rivals actually played plus the reserves, so the field mixes
rematches and fresh teams. Teams named like the human's team, or sharing its
primary color, are left out of the draw.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from src.engine.save_data import UnsupportedSave, lookup

SCHEDULED_AI_TEAMS = 10
RESERVE_AI_TEAMS = 10
RUN_AI_TEAMS = SCHEDULED_AI_TEAMS + RESERVE_AI_TEAMS


@dataclass(frozen=True)
class FootballAITeam:
    team_id: str
    name: str
    abbreviation: str
    primary_color_id: str
    secondary_color_id: str


def _team(
    team_id: str, name: str, abbreviation: str, primary: str, secondary: str
) -> FootballAITeam:
    return FootballAITeam(team_id, name, abbreviation, primary, secondary)


AI_TEAM_CATALOG: tuple[FootballAITeam, ...] = (
    _team("antelopes", "Antelopes", "ANTE", "amber", "brown"),
    _team("anvils", "Anvils", "ANVL", "slate", "orange"),
    _team("auroras", "Auroras", "AURA", "teal", "violet"),
    _team("barracudas", "Barracudas", "BARR", "azure", "silver"),
    _team("bighorns", "Bighorns", "BGHN", "brown", "gold"),
    _team("bison", "Bison", "BISN", "brown", "silver"),
    _team("blacksmiths", "Blacksmiths", "SMTH", "copper", "slate"),
    _team("blizzards", "Blizzards", "BLIZ", "silver", "indigo"),
    _team("boars", "Boars", "BOAR", "olive", "silver"),
    _team("bobcats", "Bobcats", "BCAT", "orange", "slate"),
    _team("breakers", "Breakers", "BRKR", "royal-blue", "silver"),
    _team("bulldogs", "Bulldogs", "BDOG", "emerald", "silver"),
    _team("bulls", "Bulls", "BULL", "scarlet", "slate"),
    _team("cannons", "Cannons", "CANN", "slate", "gold"),
    _team("cardinals", "Cardinals", "CARD", "crimson", "silver"),
    _team("centaurs", "Centaurs", "CENT", "violet", "amber"),
    _team("cobras", "Cobras", "COBR", "lime", "slate"),
    _team("comets", "Comets", "COMT", "indigo", "gold"),
    _team("condors", "Condors", "COND", "slate", "coral"),
    _team("corsairs", "Corsairs", "CORS", "navy", "gold"),
    _team("cougars", "Cougars", "COUG", "teal", "gold"),
    _team("coyotes", "Coyotes", "COYO", "coral", "slate"),
    _team("cranes", "Cranes", "CRNE", "silver", "scarlet"),
    _team("crocodiles", "Crocodiles", "CROC", "emerald", "amber"),
    _team("dragons", "Dragons", "DRGN", "crimson", "amber"),
    _team("eagles", "Eagles", "EAGL", "amber", "royal-blue"),
    _team("embers", "Embers", "EMBR", "orange", "gold"),
    _team("falcons", "Falcons", "FALC", "slate", "rose"),
    _team("firebirds", "Firebirds", "FIRE", "scarlet", "amber"),
    _team("flamingos", "Flamingos", "FLAM", "hot-pink", "teal"),
    _team("foxes", "Foxes", "FOX", "orange", "lavender"),
    _team("gargoyles", "Gargoyles", "GARG", "purple", "silver"),
    _team("glaciers", "Glaciers", "GLAC", "cyan", "indigo"),
    _team("gladiators", "Gladiators", "GLAD", "gold", "crimson"),
    _team("golems", "Golems", "GOLM", "lime", "indigo"),
    _team("griffins", "Griffins", "GRIF", "gold", "royal-blue"),
    _team("grizzlies", "Grizzlies", "GRIZ", "brown", "sky-blue"),
    _team("hailstorms", "Hailstorms", "HAIL", "cyan", "violet"),
    _team("hammerheads", "Hammerheads", "HMHD", "blue", "silver"),
    _team("hammers", "Hammers", "HAMR", "silver", "orange"),
    _team("harriers", "Harriers", "HARR", "sky-blue", "copper"),
    _team("hawks", "Hawks", "HAWK", "azure", "gold"),
    _team("herons", "Herons", "HERN", "lavender", "teal"),
    _team("honey-badgers", "Honey Badgers", "HNYB", "amber", "silver"),
    _team("hornets", "Hornets", "HORN", "yellow", "slate"),
    _team("hounds", "Hounds", "HNDS", "crimson", "cyan"),
    _team("huskies", "Huskies", "HUSK", "sky-blue", "silver"),
    _team("hydras", "Hydras", "HYDR", "emerald", "violet"),
    _team("jackals", "Jackals", "JACK", "coral", "indigo"),
    _team("javelins", "Javelins", "JAVS", "rose", "gold"),
    _team("kestrels", "Kestrels", "KEST", "salmon", "emerald"),
    _team("kingfishers", "Kingfishers", "KING", "azure", "orange"),
    _team("knights", "Knights", "KNGT", "indigo", "silver"),
    _team("lanterns", "Lanterns", "LANT", "yellow", "violet"),
    _team("locomotives", "Locomotives", "LOCO", "blue", "orange"),
    _team("lumberjacks", "Lumberjacks", "LJ", "green", "brown"),
    _team("lynx", "Lynx", "LYNX", "teal", "amber"),
    _team("magpies", "Magpies", "MAGS", "silver", "royal-blue"),
    _team("meteors", "Meteors", "METR", "rose", "indigo"),
    _team("miners", "Miners", "MINE", "amber", "slate"),
    _team("minotaurs", "Minotaurs", "MINO", "copper", "silver"),
    _team("monsoons", "Monsoons", "MONS", "indigo", "teal"),
    _team("moose", "Moose", "MOOS", "olive", "sky-blue"),
    _team("navigators", "Navigators", "NAVS", "royal-blue", "yellow"),
    _team("orcas", "Orcas", "ORCA", "silver", "blue"),
    _team("ospreys", "Ospreys", "OSPR", "teal", "coral"),
    _team("otters", "Otters", "OTTR", "copper", "teal"),
    _team("panthers", "Panthers", "PNTH", "violet", "silver"),
    _team("peregrines", "Peregrines", "PRGN", "royal-blue", "amber"),
    _team("pilots", "Pilots", "PLTS", "sky-blue", "scarlet"),
    _team("pioneers", "Pioneers", "PION", "green", "amber"),
    _team("prospectors", "Prospectors", "PROS", "gold", "brown"),
    _team("puffins", "Puffins", "PUFF", "coral", "azure"),
    _team("pumas", "Pumas", "PUMA", "rose", "slate"),
    _team("redwoods", "Redwoods", "RDWD", "copper", "emerald"),
    _team("rhinos", "Rhinos", "RHNO", "cyan", "crimson"),
    _team("riveters", "Riveters", "RIVT", "royal-blue", "rose"),
    _team("roadrunners", "Roadrunners", "RR", "purple", "gold"),
    _team("roughnecks", "Roughnecks", "RNKS", "olive", "orange"),
    _team("scorpions", "Scorpions", "SCRP", "purple", "amber"),
    _team("sharks", "Sharks", "SHRK", "blue", "cyan"),
    _team("skippers", "Skippers", "SKIP", "salmon", "azure"),
    _team("smokejumpers", "Smokejumpers", "SMKJ", "orange", "royal-blue"),
    _team("squalls", "Squalls", "SQLS", "lavender", "azure"),
    _team("stallions", "Stallions", "STAL", "emerald", "copper"),
    _team("stingrays", "Stingrays", "RAYS", "magenta", "cyan"),
    _team("sunbursts", "Sunbursts", "SUNB", "yellow", "hot-pink"),
    _team("thunderheads", "Thunderheads", "THDR", "violet", "yellow"),
    _team("tigers", "Tigers", "TGRS", "orange", "teal"),
    _team("tornadoes", "Tornadoes", "TORN", "slate", "lavender"),
    _team("tremors", "Tremors", "TRMR", "coral", "brown"),
    _team("typhoons", "Typhoons", "TYPH", "azure", "lime"),
    _team("vipers", "Vipers", "VIPR", "lime", "violet"),
    _team("voyagers", "Voyagers", "VOYG", "sky-blue", "coral"),
    _team("wildcats", "Wildcats", "WILD", "scarlet", "gold"),
    _team("wildfires", "Wildfires", "WLDF", "amber", "crimson"),
    _team("wolves", "Wolves", "WOLF", "silver", "emerald"),
    _team("wranglers", "Wranglers", "WRNG", "salmon", "brown"),
    _team("wyverns", "Wyverns", "WYVN", "green", "purple"),
    _team("yetis", "Yetis", "YETI", "lavender", "royal-blue"),
)

AI_TEAMS_BY_ID: Mapping[str, FootballAITeam] = MappingProxyType(
    {team.team_id: team for team in AI_TEAM_CATALOG}
)


def ai_team(team_id: str) -> FootballAITeam:
    """The catalog team for a saved id; raises ``UnsupportedSave`` if unknown."""
    return lookup(AI_TEAMS_BY_ID, team_id, "AI team")


def eligible_ai_teams(
    human_name: str, human_primary_color_id: str | None = None
) -> tuple[FootballAITeam, ...]:
    """Catalog teams that can face this human team (catalog order)."""
    name = human_name.strip().casefold()
    return tuple(
        team for team in AI_TEAM_CATALOG
        if team.name.casefold() != name
        and (human_primary_color_id is None or team.primary_color_id != human_primary_color_id)
    )


def draw_run_ai_teams(
    rng: random.Random, human_name: str, human_primary_color_id: str | None = None
) -> tuple[str, ...]:
    """Draw a run's 20 distinct AI team ids: ten scheduled rivals, then ten reserves."""
    pool = eligible_ai_teams(human_name, human_primary_color_id)
    return tuple(team.team_id for team in rng.sample(pool, RUN_AI_TEAMS))


def validate_run_ai_teams(team_ids: Sequence[str]) -> tuple[FootballAITeam, ...]:
    """Resolve a saved run draw; raises ``UnsupportedSave`` if it is malformed."""
    teams = tuple(ai_team(team_id) for team_id in team_ids)
    if len(teams) != RUN_AI_TEAMS or len(set(teams)) != len(teams):
        raise UnsupportedSave(f"A run lists {RUN_AI_TEAMS} distinct AI teams.")
    return teams


def playoff_pool(
    run_team_ids: Sequence[str], played_games: Iterable[int]
) -> tuple[str, ...]:
    """Ids eligible for the playoff field: rivals from ``played_games`` plus the reserves."""
    played = sorted(set(played_games))
    if any(not 1 <= game <= SCHEDULED_AI_TEAMS for game in played):
        raise ValueError("Played games must be regular-season game numbers.")
    rivals = tuple(run_team_ids[game - 1] for game in played)
    return rivals + tuple(run_team_ids[SCHEDULED_AI_TEAMS:])
