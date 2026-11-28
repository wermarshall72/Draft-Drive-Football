"""Single source for specialist-perk wording: card line, full rules, callouts, notes.

Every string is built from the perk's own ``values`` (``src/engine/football_player_catalog.py``),
so the wording cannot drift from the engine. The card line (at most 60 characters)
appears on draft cards and Depth Chart fronts; the full rules appear in the draft
card's perk box, on Depth Chart backs, and in inspect panels. Callouts and preview
notes describe one ``FootballPerkActivation``.
"""

from __future__ import annotations

from src.engine.football import (
    FootballPerkActivation,
    FootballPlayerPerkKind as K,
    FootballPosition,
)
from src.engine.football_player_catalog import (
    FootballPerkLimit,
    FootballPlayerPerk,
    PLAYER_TYPES_BY_PERK,
    player_perk,
)

CARD_LINE_LIMIT = 60
MINUS = "−"

POSITION_SHORT = {
    FootballPosition.QB: "QB",
    FootballPosition.RB: "RB",
    FootballPosition.WR: "WR",
    FootballPosition.O_LINE: "OL",
    FootballPosition.D_LINE: "DL",
    FootballPosition.LINEBACKERS: "LB",
    FootballPosition.CORNERBACKS: "CB",
    FootballPosition.SAFETIES: "S",
}


def _n(value: float) -> str:
    return f"{value:g}"


def _pct(value: float) -> str:
    return f"{round(abs(value) * 100, 4):g}%"


def _yd(value: float) -> str:
    return f"{_n(value)} {'yard' if value == 1 else 'yards'}"


def _clock(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"


def _ordinal(value: float) -> str:
    number = int(value)
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


# kind -> (card line, full rules); each receives the perk's values mapping.
_WORDING = {
    K.MESH_READ: (
        lambda v: "Completed PA: pull an RB Run card into hand (1/drive)",
        lambda v: "When your Play-Action Pass is completed, the first RB Run card in your draw "
                  "pile (else your discard pile) joins your hand as an extra card. Nothing "
                  "happens if you have none. Once per drive.",
    ),
    K.OPTION_LEDGER: (
        lambda v: f"{_ordinal(v['families'])} different play family in a drive: draw {_n(v['cards'])} (1/game)",
        lambda v: f"When you snap your {_ordinal(v['families'])} different play family in one "
                  f"drive, draw {_n(v['cards'])} offensive cards. Once per game.",
    ),
    K.HURRY_UP_CAPTAIN: (
        lambda v: f"Final {_clock(v['window_seconds'])} of a half: QB completions use {_n(v['seconds'])} seconds",
        lambda v: f"A completed pass the QB contributes to (Play-Action, Medium, Deep) with "
                  f"{_clock(v['window_seconds'])} or less left in either half uses at most "
                  f"{_n(v['seconds'])} seconds. Every such play; regulation only.",
    ),
    K.SHOT_SETUP: (
        lambda v: f"Deep incompletion: next Deep this half {MINUS}{_pct(v['incompletion'])} incomplete",
        lambda v: f"After your Deep Pass falls incomplete, your next Deep Pass this half gets "
                  f"{MINUS}{_pct(v['incompletion'])} incompletion chance (12% floor). One charge; "
                  "it clears at halftime, at overtime, or when used.",
    ),
    K.POCKET_PRESENCE: (
        lambda v: f"From snap {_n(v['from_snap'])} of a drive: QB +{_n(v['power'])} power",
        lambda v: f"On the {_ordinal(v['from_snap'])} and later snaps of a drive (not two-point "
                  f"tries), your QB gets +{_n(v['power'])} power. Lasts the rest of the drive.",
    ),
    K.SILENT_COUNT: (
        lambda v: "3rd/4th down when stopped: ignore it (1/half)",
        lambda v: "On a 3rd- or 4th-down snap where the rival's defense call stops your play, the "
                  "snap is treated as not stopped (no power, yardage, or risk penalty). "
                  "Coach perks keyed to stopped plays still apply. Once per half.",
    ),
    K.CHECKDOWN: (
        lambda v: f"After a QB incompletion: next RB play +{_n(v['yards'])} yards",
        lambda v: f"After a pass the QB contributes to falls incomplete, if your next snap this "
                  f"drive is an RB play (Run, Play-Action, Short) and not a turnover, it gains "
                  f"+{_yd(v['yards'])}. Next snap only.",
    ),
    K.KEEP_READ: (
        lambda v: "PA on 3rd/4th or 2-pt: no inc or INT roll (1/half)",
        lambda v: "Your Play-Action Pass on 3rd or 4th down, or as a two-point try, has no "
                  "incompletion or interception roll; it uses the RB Run fumble chance "
                  "instead. Yards are unchanged. Once per half (overtime is one half; a "
                  "two-point try counts in its touchdown's half).",
    ),
    K.ORBIT_BREAKAWAY: (
        lambda v: f"Completed Short pass: {_pct(v['chance'])} chance of +{_n(v['yards'])} yards (1/half)",
        lambda v: f"When your Short Pass is completed, roll a {_pct(v['chance'])} chance of "
                  f"+{_yd(v['yards'])} (25-yard cap; defensive caps apply after). Once per "
                  "half, spent only when it hits.",
    ),
    K.OUTLET_REPEAT: (
        lambda v: "Short pass first down: keep the card (1/drive)",
        lambda v: "When your Short Pass earns a first down or a touchdown, the card returns to "
                  "your hand instead of the discard pile, with no replacement draw. Once per drive.",
    ),
    K.DOWNHILL: (
        lambda v: f"RB Run after an RB play: +{_n(v['yards'])} yard (+{_n(v['run_yards'])} after a run)",
        lambda v: f"Your RB Run on the snap right after an RB play (Run, Play-Action, Short) in "
                  f"the same drive gains +{_yd(v['yards'])}, or +{_yd(v['run_yards'])} if that "
                  "snap was an RB Run. Not on turnovers. Every such snap.",
    ),
    K.FALL_FORWARD: (
        lambda v: f"RB Run under {_n(v['yards'])} yard gains {_n(v['yards'])} instead (1/drive)",
        lambda v: f"When your non-turnover RB Run would gain under {_yd(v['yards'])} (including "
                  f"losses), it gains exactly {_yd(v['yards'])}. This also prevents a safety. "
                  "Once per drive.",
    ),
    K.HOT_ROUTE: (
        lambda v: "Drive start: swap your weakest stopped card",
        lambda v: "At your first offensive decision of each drive, if the rival's defense call "
                  "stops a card in your hand, the stopped card with the lowest expected "
                  "yards is discarded and replaced from your draw pile. Once per drive.",
    ),
    K.CONTESTED_CATCH: (
        lambda v: "Failed Deep pass: reroll the catch (1/game)",
        lambda v: "When your Deep Pass rolls incomplete or intercepted, reroll the catch once "
                  "with the same odds; the yards are kept and the second result stands. "
                  "Once per game.",
    ),
    K.MOVE_THE_STICKS: (
        lambda v: f"Short catch {_n(v['yards'])} yds or less shy: move the chains (1/half)",
        lambda v: f"When your completed Short Pass ends {_yd(v['yards'])} or less short of the "
                  "line to gain (any down, not goal-to-go), it gains exactly enough for a first "
                  "down. Once per half.",
    ),
    K.MOTION_JUMP: (
        lambda v: f"First WR play of each drive: WR +{_n(v['power'])} power",
        lambda v: f"On the first snap of each drive that your WR contributes to (Screen, Short, "
                  f"Deep), the WR gets +{_n(v['power'])} power. Once per drive.",
    ),
    K.PYLON_REACH: (
        lambda v: f"WR catch ending inside the {_n(v['yards'])} scores (1/game)",
        lambda v: f"When a completed pass your WR contributes to would end inside the rival "
                  f"{_n(v['yards'])} without scoring, it is a touchdown. Once per game.",
    ),
    K.RELEASE_READ: (
        lambda v: f"Screen of {_n(v['yards'])}+ yds: rival swaps a random scheme (1/drive)",
        lambda v: f"When your completed Screen Pass gains {_n(v['yards'])}+ yards, the rival "
                  "discards a random scheme from its hand and draws a replacement. The active "
                  "scheme is unaffected. Once per drive.",
    ),
    K.PASS_PRO: (
        lambda v: "First QB interception each game is incomplete instead",
        lambda v: "The first time a pass your QB contributes to would be intercepted, it is "
                  "incomplete instead (5 seconds; the down advances). Once per game.",
    ),
    K.TEMPO_READ: (
        lambda v: f"Medium pass first down: draw {_n(v['cards'])} (1/drive)",
        lambda v: f"When your Medium Pass earns a first down, draw {_n(v['cards'])} offensive "
                  "card. Once per drive.",
    ),
    K.FOUR_MINUTE_DRILL: (
        lambda v: f"Leading in 2nd half: RB Runs use +{_n(v['seconds'])} seconds",
        lambda v: f"Your non-turnover RB Run in the second half while you lead uses "
                  f"+{_n(v['seconds'])} seconds of clock. Every such run.",
    ),
    K.PULL_LEAD: (
        lambda v: f"3rd/4th & {_n(v['distance'])} or less, O-line play: O-line +{_n(v['power'])} power",
        lambda v: f"On 3rd or 4th down with {_yd(v['distance'])} or less to go, on a play your "
                  f"O-line contributes to (Run, Screen, Medium), the O-line gets "
                  f"+{_n(v['power'])} power. Every such snap.",
    ),
    K.SCREEN_WALL: (
        lambda v: f"Completed Screen: rival D-line {MINUS}{_n(v['power'])} power this drive",
        lambda v: f"After your Screen Pass is completed, the rival D-line gets "
                  f"{MINUS}{_n(v['power'])} power on every later snap of this drive where it "
                  "contributes. Once per drive; ends when possession changes.",
    ),
    K.BREATHING_ROOM: (
        lambda v: f"Drive starts at your {_n(v['threshold'])} or worse: +{_n(v['yards'])} yards",
        lambda v: f"When your drive starts at or inside your own {_n(v['threshold'])}, the ball "
                  f"moves {_yd(v['yards'])} upfield before the first snap; still 1st & 10. "
                  "Never in overtime.",
    ),
    K.HOLD_THE_FRONT: (
        lambda v: "Run-scheme drive ends without a TD: keep the scheme",
        lambda v: "When a rival drive against your Run-family scheme ends without a touchdown, "
                  "that scheme card returns from your discard pile to your hand. The end-of-"
                  "drive hand trim can still discard it. Once per rival drive.",
    ),
    K.EDGE_SET: (
        lambda v: f"Rival's first snap of each drive: D-line +{_n(v['power'])} power",
        lambda v: f"On the rival's first snap of each drive, when your D-line contributes "
                  f"(Run, Screen, Medium scheme), the D-line gets +{_n(v['power'])} power. "
                  "Once per rival drive.",
    ),
    K.CONTAIN: (
        lambda v: f"Screens vs your D-line schemes gain at most {_n(v['cap'])} yards",
        lambda v: f"A completed rival Screen Pass gains at most {_yd(v['cap'])} when your "
                  "D-line contributes to the scheme. Every such snap.",
    ),
    K.COLLAPSE: (
        lambda v: "3rd-down stop: rival swaps a random play (1/drive)",
        lambda v: "When a rival 3rd-down snap ends with no first down, turnover, or score, the "
                  "rival discards a random offensive card and draws a replacement. Once per "
                  "rival drive.",
    ),
    K.KICK_RUSH: (
        lambda v: f"Rival punts, FGs, and extra points: +{_pct(v['block'])} block chance",
        lambda v: f"Rival punts, field goals, and extra points get +{_pct(v['block'])} block "
                  "chance (before the kicker's block-risk reduction on punts and field goals). "
                  "Blocks use the normal recovery and return rules.",
    ),
    K.STUNT_SACK: (
        lambda v: f"QB incompletion vs D-line scheme: sack, {MINUS}{_n(v['yards'])} (1/drive)",
        lambda v: f"When a rival pass the QB contributes to would be incomplete while your "
                  f"D-line contributes, it becomes a sack: {MINUS}{_yd(v['yards'])}, the card's "
                  "full clock, and the down advances. Once per rival drive.",
    ),
    K.FIT_AND_SHED: (
        lambda v: f"Rival gains {_n(v['yards'])} or less: draw a scheme (1/drive)",
        lambda v: f"When a rival non-turnover snap gains {_yd(v['yards'])} or less "
                  "(incompletions count) while your linebackers contribute, draw "
                  f"{_n(v['cards'])} defense call. Once per rival drive.",
    ),
    K.CAPTAINS_ADJUSTMENT: (
        lambda v: f"Rival run first down: LB +{_n(v['power'])} power rest of drive",
        lambda v: f"After the rival earns a first down with an RB Run, your linebackers get "
                  f"+{_n(v['power'])} power for the rest of that drive when they contribute. "
                  "Once per rival drive.",
    ),
    K.HOLD_THE_LINE: (
        lambda v: f"3rd/4th-down first down by <{_n(v['margin'])} yds: stop short (1/half)",
        lambda v: f"When a rival 3rd- or 4th-down snap would earn a first down by under "
                  f"{_yd(v['margin'])} (not a touchdown), the ball is spotted "
                  f"{_n(v['short'])} yards short of the line: no first down. Once per half.",
    ),
    K.READ_KEYS: (
        lambda v: "See the rival's play hand when you pick a scheme",
        lambda v: "Whenever you choose a defense call, the rival's whole offensive hand is "
                  "shown to you. Every rival drive.",
    ),
    K.SHORT_FIELD: (
        lambda v: f"Rival punts or fails on 4th: your drive +{_n(v['yards'])} yards",
        lambda v: f"When a rival drive ends in a punt or a turnover on downs, your next drive "
                  f"starts {_yd(v['yards'])} further upfield, after any return.",
    ),
    K.GREEN_DOG: (
        lambda v: "Rival converts 3rd/4th: swap your scheme (1/game)",
        lambda v: "When the rival converts a 3rd or 4th down, you may swap the active scheme "
                  "for one in your hand; the old one is discarded and you draw a replacement. "
                  "Offered on each conversion until used. Once per game.",
    ),
    K.KEEP_IT_INBOUNDS: (
        lambda v: f"Leading in 2nd half: rival completions +{_n(v['seconds'])} seconds",
        lambda v: f"While you lead in the second half, each completed rival pass uses "
                  f"+{_n(v['seconds'])} seconds of clock. Every such play.",
    ),
    K.FORCE_AND_FOLD: (
        lambda v: "Your Screen defenses also stop RB Runs",
        lambda v: "A rival RB Run against your Screen-family defense call counts as stopped: "
                  "defense power ×1.12, offense ×0.96, −0.5 yards, and +0.5% fumble "
                  "chance. Every such snap.",
    ),
    K.NICKEL_LOCK: (
        lambda v: f"3rd down vs your CB scheme: CB +{_n(v['power'])} power",
        lambda v: f"On a rival 3rd-down snap when your cornerbacks contribute (Screen, Short, "
                  f"Deep scheme), they get +{_n(v['power'])} power. Every such snap.",
    ),
    K.BRACKET: (
        lambda v: "Short incompletion: rival discards a play (1/game)",
        lambda v: "When a rival Short Pass falls incomplete while your cornerbacks contribute, "
                  "the rival discards a random offensive card with no replacement until its "
                  "drive ends. Once per game.",
    ),
    K.DEEP_LOCK: (
        lambda v: f"Your Deep schemes: rival catches gain at most {_n(v['cap'])}",
        lambda v: f"While your Deep-family scheme is active, a completed rival pass gains at "
                  f"most {_yd(v['cap'])} (after any offensive bonus). Every such snap.",
    ),
    K.BAIT_AND_JUMP: (
        lambda v: f"Allow a Deep catch: next rival Deep +{_pct(v['interception'])} INT (1/half)",
        lambda v: f"When the rival completes a Deep Pass against you, its next Deep Pass this "
                  f"game gets +{_pct(v['interception'])} interception chance. One charge, "
                  "renewed by each allowed Deep catch; it survives halftime. The bonus "
                  "applies at most once per half (overtime is one half).",
    ),
    K.LAST_LINE: (
        lambda v: f"Rival TD from {_n(v['distance'])}+ yds out: stopped at the 1 (1/game)",
        lambda v: f"When a rival snap from outside your {_n(v['distance'])} would score a "
                  "touchdown, the runner is stopped at your 1: a first down if the line to gain "
                  "was crossed, otherwise the next down. Once per game.",
    ),
    K.SAFETY_BLITZ: (
        lambda v: f"2nd/3rd-down pass vs Medium scheme: +{_pct(v['incompletion'])} inc, +{_n(v['yards'])} on catch",
        lambda v: f"A rival pass on 2nd or 3rd down against your Medium-family scheme gets "
                  f"+{_pct(v['incompletion'])} incompletion chance, but a completed pass gains "
                  f"+{_yd(v['yards'])}. Every such snap.",
    ),
    K.DOWNHILL_FILL: (
        lambda v: f"Rival RB Run vs your S scheme: safety +{_n(v['power'])} power",
        lambda v: f"On a rival RB Run when your safeties contribute (Play-Action, Medium, Deep "
                  f"scheme), they get +{_n(v['power'])} power. Every such snap.",
    ),
    K.TIP_DRILL: (
        lambda v: "3rd/4th-down incompletion becomes an INT (1/game)",
        lambda v: "When a rival pass on 3rd or 4th down falls incomplete while your safeties "
                  "contribute, it becomes an interception at the line of scrimmage. Once per game.",
    ),
    K.SUDDEN_CHANGE: (
        lambda v: f"Your takeaway: draw {_n(v['cards'])} play card for your drive",
        lambda v: f"When your defense makes a takeaway (interception, fumble, or turnover on "
                  f"downs, including perk-made ones), draw {_n(v['cards'])} offensive card. "
                  "Every takeaway.",
    ),
    K.RANGE_DENIAL: (
        lambda v: f"Rival field goals kick as if {_n(v['yards'])} yards longer",
        lambda v: f"Rival field-goal success is computed as if the kick were {_yd(v['yards'])} "
                  "longer. Every attempt.",
    ),
}

_LIMIT_LABELS = {
    FootballPerkLimit.DRIVE: "1/DRIVE",
    FootballPerkLimit.HALF: "1/HALF",
    FootballPerkLimit.GAME: "1/GAME",
    FootballPerkLimit.CHARGE: "CHARGE",
}


def perk_card_line(perk: FootballPlayerPerk) -> str:
    """One card-width line (at most 60 characters)."""
    return _WORDING[perk.kind][0](perk.values)


def perk_rules(perk: FootballPlayerPerk) -> str:
    """The complete trigger, effect, and limit in plain sentences."""
    return _WORDING[perk.kind][1](perk.values)


def partner_tag(perk: FootballPlayerPerk) -> str | None:
    """'WITH WR' for perks that need the partner position on the play or scheme."""
    if not perk.partner_required:
        return None
    partner = PLAYER_TYPES_BY_PERK[perk.kind].partner_position
    assert partner is not None
    return f"WITH {POSITION_SHORT[partner]}"


def limit_label(perk: FootballPlayerPerk) -> str | None:
    """'1/DRIVE', '1/HALF', '1/GAME', or 'CHARGE' for limited perks."""
    return _LIMIT_LABELS.get(perk.limit)


def _signed(value: float, unit: str) -> str:
    sign = "+" if value >= 0 else MINUS
    return f"{sign}{_n(abs(round(value, 1)))}{unit}"


def activation_result(activation: FootballPerkActivation) -> str:
    """Short upper-case effect for an outcome-strip callout."""
    perk = player_perk(activation.kind)
    value = activation.value
    kind = activation.kind
    power_kinds = {
        K.POCKET_PRESENCE: "QB", K.MOTION_JUMP: "WR", K.PULL_LEAD: "OL", K.EDGE_SET: "DL",
        K.NICKEL_LOCK: "CB", K.DOWNHILL_FILL: "S",
    }
    if kind is K.CAPTAINS_ADJUSTMENT and activation.applied:
        return f"LB +{_n(perk.value('power'))} POWER"
    if kind in power_kinds:
        return f"{power_kinds[kind]} +{_n(perk.value('power'))} POWER"
    if kind is K.SCREEN_WALL:
        return (f"RIVAL DL {MINUS}{_n(perk.value('power'))}" if activation.applied
                else f"RIVAL DL {MINUS}{_n(perk.value('power'))} THIS DRIVE")
    if kind is K.CAPTAINS_ADJUSTMENT:
        return f"LB +{_n(perk.value('power'))} REST OF DRIVE"
    text = {
        K.MESH_READ: lambda: "PULLED AN RB RUN",
        K.OPTION_LEDGER: lambda: f"DREW {_n(value)}",
        K.HURRY_UP_CAPTAIN: lambda: f"CLOCK {_n(value)}s",
        K.SHOT_SETUP: lambda: f"{MINUS}{_pct(perk.value('incompletion'))} INCOMPLETE",
        K.SILENT_COUNT: lambda: "STOP IGNORED",
        K.CHECKDOWN: lambda: f"+{_n(value)} YDS",
        K.KEEP_READ: lambda: "NO INC / INT ROLL",
        K.ORBIT_BREAKAWAY: lambda: f"+{_n(value)} YDS",
        K.OUTLET_REPEAT: lambda: "CARD KEPT",
        K.DOWNHILL: lambda: f"+{_n(value)} YDS",
        K.FALL_FORWARD: lambda: "+1 YARD FLOOR",
        K.HOT_ROUTE: lambda: "SWAPPED A CARD",
        K.CONTESTED_CATCH: lambda: "REROLL: CAUGHT" if value > 0 else "REROLL: NO CATCH",
        K.MOVE_THE_STICKS: lambda: "FIRST DOWN",
        K.PYLON_REACH: lambda: "TD",
        K.RELEASE_READ: lambda: "RIVAL SCHEME SWAPPED",
        K.PASS_PRO: lambda: "INT ERASED",
        K.TEMPO_READ: lambda: f"DREW {_n(value)}",
        K.FOUR_MINUTE_DRILL: lambda: f"+{_n(value)}s CLOCK",
        K.BREATHING_ROOM: lambda: f"+{_n(value)} YDS FIELD",
        K.HOLD_THE_FRONT: lambda: "SCHEME KEPT",
        K.CONTAIN: lambda: f"CAPPED AT {_n(perk.value('cap'))}",
        K.COLLAPSE: lambda: "RIVAL PLAY SWAPPED",
        K.KICK_RUSH: lambda: "BLOCKED",
        K.STUNT_SACK: lambda: f"SACK {MINUS}{_n(perk.value('yards'))}",
        K.FIT_AND_SHED: lambda: "DREW A SCHEME",
        K.HOLD_THE_LINE: lambda: "STOPPED SHORT",
        K.READ_KEYS: lambda: "RIVAL HAND READ",
        K.SHORT_FIELD: lambda: f"+{_n(value)} YDS FIELD",
        K.GREEN_DOG: lambda: "SCHEME SWAPPED",
        K.KEEP_IT_INBOUNDS: lambda: f"+{_n(value)}s CLOCK",
        K.FORCE_AND_FOLD: lambda: "RUN STOPPED",
        K.BRACKET: lambda: "RIVAL DISCARDS",
        K.DEEP_LOCK: lambda: f"CAPPED AT {_n(perk.value('cap'))}",
        K.BAIT_AND_JUMP: lambda: f"+{_pct(perk.value('interception'))} INT",
        K.LAST_LINE: lambda: "STOPPED AT THE 1",
        K.SAFETY_BLITZ: lambda: f"+{_pct(perk.value('incompletion'))} INC",
        K.TIP_DRILL: lambda: "INT",
        K.SUDDEN_CHANGE: lambda: f"DREW {_n(value or 1)}",
        K.RANGE_DENIAL: lambda: f"+{_n(perk.value('yards'))} YD KICK",
    }[kind]()
    return text


def activation_player_name(activation: FootballPerkActivation) -> str:
    return PLAYER_TYPES_BY_PERK[activation.kind].name


def activation_callout(activation: FootballPerkActivation) -> str:
    """'PYLON REACH · Boundary Route · TD'."""
    perk = player_perk(activation.kind)
    return f"{perk.name.upper()} · {activation_player_name(activation)} · {activation_result(activation)}"


def activation_log_text(activation: FootballPerkActivation) -> str:
    """A compact Play Log entry: 'Pylon Reach (TD)'."""
    perk = player_perk(activation.kind)
    return f"{perk.name} ({activation_result(activation).lower()})"


def activation_preview_note(activation: FootballPerkActivation) -> str:
    """A short preview note for an estimate perk, e.g. '+10 OL Pull Lead'."""
    perk = player_perk(activation.kind)
    kind = activation.kind
    name = perk.name
    power = {
        K.POCKET_PRESENCE: "QB", K.MOTION_JUMP: "WR", K.PULL_LEAD: "OL", K.EDGE_SET: "DL",
        K.CAPTAINS_ADJUSTMENT: "LB", K.NICKEL_LOCK: "CB", K.DOWNHILL_FILL: "S",
    }
    if kind in power:
        sign = "+"
        return f"{sign}{_n(perk.value('power'))} {power[kind]} {name}"
    if kind is K.SCREEN_WALL:
        return f"{MINUS}{_n(perk.value('power'))} DL {name}"
    if kind in (K.CHECKDOWN, K.DOWNHILL):
        return f"+{_n(activation.value)} yd {name}"
    if kind is K.SAFETY_BLITZ:
        return f"+{_pct(perk.value('incompletion'))} inc {name}"
    if kind is K.SHOT_SETUP:
        return f"{MINUS}{_pct(perk.value('incompletion'))} inc {name}"
    if kind is K.BAIT_AND_JUMP:
        return f"+{_pct(perk.value('interception'))} INT {name}"
    if kind is K.KEEP_READ:
        return f"No inc/INT {name}"
    if kind is K.SILENT_COUNT:
        return f"Not stopped {name}"
    if kind is K.FORCE_AND_FOLD:
        return f"Stopped {name}"
    return name
