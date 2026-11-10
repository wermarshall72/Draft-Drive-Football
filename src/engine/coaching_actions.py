from dataclasses import dataclass
from typing import Literal

from src.engine.units import Position

Rarity = Literal["Common", "Uncommon", "Rare", "Very Rare"]
Duration = Literal["match", "run", "next_shop", "carry"]

POSITIONS: tuple[Position, ...] = (
    "QB",
    "RB",
    "WR",
    "OLINE",
    "FRONT7",
    "SECONDARY",
)
OFFENSE: tuple[Position, ...] = ("QB", "RB", "WR", "OLINE")
DEFENSE: tuple[Position, ...] = ("FRONT7", "SECONDARY")


@dataclass(frozen=True)
class CoachingAction:
    id: int
    name: str
    description: str
    ap_cost: int
    rarity: Rarity
    duration: Duration
    target: str
    power: tuple[tuple[str, float], ...] = ()
    volatility: tuple[tuple[str, float], ...] = ()
    stamina: tuple[tuple[str, float], ...] = ()
    swing_chance: float = 0.0
    field_goal_reliability: float = 0.0
    swing_magnitude: float = 0.0
    opponent_swing_reduction: float = 0.0
    bank_ap: int = 0
    bank_ap_on_win: int = 0
    permanent_ap: int = 0
    position_ap: bool = False
    carry_unused: bool = False
    drive_count: int | None = None
    fatigue_limit: float | None = None
    choose_position: bool = False
    once_per_run: bool = False
    last_shop_excluded: bool = False
    replaces: str | None = None


def _effects(
    positions: tuple[Position, ...], value: float
) -> tuple[tuple[str, float], ...]:
    return tuple((position, value) for position in positions)


def _action(
    action_id: int,
    name: str,
    ap_cost: int,
    description: str,
    rarity: Rarity,
    duration: Duration,
    target: str,
    *,
    power: tuple[tuple[str, float], ...] = (),
    volatility: tuple[tuple[str, float], ...] = (),
    stamina: tuple[tuple[str, float], ...] = (),
    swing_chance: float = 0.0,
    field_goal_reliability: float = 0.0,
    swing_magnitude: float = 0.0,
    opponent_swing_reduction: float = 0.0,
    bank_ap: int = 0,
    bank_ap_on_win: int = 0,
    permanent_ap: int = 0,
    position_ap: bool = False,
    carry_unused: bool = False,
    drive_count: int | None = None,
    fatigue_limit: float | None = None,
    choose_position: bool = False,
    once_per_run: bool = False,
    last_shop_excluded: bool = False,
    replaces: str | None = None,
) -> CoachingAction:
    return CoachingAction(
        id=action_id,
        name=name,
        description=description,
        ap_cost=ap_cost,
        rarity=rarity,
        duration=duration,
        target=target,
        power=power,
        volatility=volatility,
        stamina=stamina,
        swing_chance=swing_chance,
        field_goal_reliability=field_goal_reliability,
        swing_magnitude=swing_magnitude,
        opponent_swing_reduction=opponent_swing_reduction,
        bank_ap=bank_ap,
        bank_ap_on_win=bank_ap_on_win,
        permanent_ap=permanent_ap,
        position_ap=position_ap,
        carry_unused=carry_unused,
        drive_count=drive_count,
        fatigue_limit=fatigue_limit,
        choose_position=choose_position,
        once_per_run=once_per_run,
        last_shop_excluded=last_shop_excluded,
        replaces=replaces,
    )


def build_catalog() -> tuple[CoachingAction, ...]:
    actions = [
        _action(1, "Blind-Spot Audit", 2, "Find the leak before it becomes a landslide.", "Common", "match", "Team defense", power=(("FRONT7", 1.05), ("SECONDARY", 1.05), ("QB", 0.98), ("RB", 0.98), ("WR", 0.98), ("OLINE", 0.98))),
        _action(2, "Scripted Opening", 3, "Start with a rehearsed identity.", "Common", "match", "Team offense", power=_effects(OFFENSE, 1.06)),
        _action(3, "Chaos-to-Clipboard", 2, "Give the roster a calmer plan.", "Common", "match", "Team", volatility=_effects(POSITIONS, -0.03)),
        _action(4, "Four-Quarter Load Sheet", 3, "Budget energy for the finish.", "Common", "match", "Team", stamina=_effects(POSITIONS, 0.10)),
        _action(5, "Aggressive Call Sheet", 2, "Chase the ceiling and accept the swing.", "Common", "match", "Team offense", power=_effects(OFFENSE, 1.07), volatility=_effects(OFFENSE, 0.03)),
        _action(6, "Defense-First Script", 3, "Win the field-position tug-of-war.", "Common", "match", "Team", power=(("FRONT7", 1.05), ("SECONDARY", 1.05), ("QB", 0.98), ("RB", 0.98), ("WR", 0.98), ("OLINE", 0.98))),
        _action(7, "Simplify the Reads", 2, "Fewer moving parts, fewer wild drives.", "Common", "match", "Team offense", power=_effects(OFFENSE, 0.97), volatility=_effects(OFFENSE, -0.04)),
        _action(8, "All Gas, No Brakes", 4, "Trade late-game legs for early punch.", "Common", "match", "Team", power=_effects(POSITIONS, 1.05), stamina=_effects(POSITIONS, -0.10)),
        _action(9, "QB Footwork Lab", 4, "Build a sturdier foundation.", "Uncommon", "run", "QB", power=(("QB", 1.03),)),
        _action(10, "QB Decision Reps", 4, "Make the same talent more dependable.", "Uncommon", "run", "QB", volatility=(("QB", -0.02),)),
        _action(11, "RB Contact Balance", 4, "Turn extra reps into sturdier runs.", "Uncommon", "run", "RB", power=(("RB", 1.03),)),
        _action(12, "RB Conditioning Circuit", 4, "Keep the workhorse fresh.", "Uncommon", "run", "RB", stamina=(("RB", 0.04),)),
        _action(13, "WR Release Clinic", 4, "Sharpen the first step.", "Uncommon", "run", "WR", power=(("WR", 1.03),)),
        _action(14, "WR Route Repetition", 4, "Make production less volatile.", "Uncommon", "run", "WR", volatility=(("WR", -0.02),)),
        _action(15, "O-Line Strength Block", 4, "Add force to the unit's contribution.", "Uncommon", "run", "O-Line", power=(("OLINE", 1.03),)),
        _action(16, "O-Line Endurance Work", 4, "Keep the unit's legs under it.", "Uncommon", "run", "O-Line", stamina=(("OLINE", 0.04),)),
        _action(17, "Front Seven Strength Room", 4, "Add force up front.", "Uncommon", "run", "Front 7", power=(("FRONT7", 1.03),)),
        _action(18, "Front Seven Conditioning", 4, "Sustain the push late.", "Uncommon", "run", "Front 7", stamina=(("FRONT7", 0.04),)),
        _action(19, "Secondary Film Reps", 4, "Improve the unit's baseline contribution.", "Uncommon", "run", "Secondary", power=(("SECONDARY", 1.03),)),
        _action(20, "Coverage Communication", 4, "Reduce drive-to-drive variance.", "Uncommon", "run", "Secondary", volatility=(("SECONDARY", -0.02),)),
        _action(21, "Front Seven Technique", 4, "Make the unit's output steadier.", "Uncommon", "run", "Front 7", volatility=(("FRONT7", -0.02),)),
        _action(22, "Front Seven Power Clean", 4, "Train for a sharper ceiling at a cost.", "Uncommon", "run", "Front 7", power=(("FRONT7", 1.04),), volatility=(("FRONT7", 0.02),)),
        _action(23, "Secondary Recovery Plan", 4, "Preserve legs through the final drives.", "Uncommon", "run", "Secondary", stamina=(("SECONDARY", 0.04),)),
        _action(24, "Secondary Disruption Reps", 4, "Raise output, accept more variance.", "Uncommon", "run", "Secondary", power=(("SECONDARY", 1.04),), volatility=(("SECONDARY", 0.02),)),
        _action(25, "QB Pocket Session", 2, "Prime the passer's power.", "Common", "match", "QB", power=(("QB", 1.08),)),
        _action(26, "QB Calm-Down Reps", 2, "Narrow the QB's swing range.", "Common", "match", "QB", volatility=(("QB", -0.04),)),
        _action(27, "RB Heavy-Bag Prep", 2, "Load the back for a bigger day.", "Common", "match", "RB", power=(("RB", 1.08),)),
        _action(28, "RB Fresh-Legs Treatment", 2, "Save energy for late drives.", "Common", "match", "RB", stamina=(("RB", 0.12),)),
        _action(29, "WR Timing Session", 2, "Give the receiver a temporary lift.", "Common", "match", "WR", power=(("WR", 1.08),)),
        _action(30, "WR Hands-and-Rhythm Work", 2, "Reduce the unit's variance.", "Common", "match", "WR", volatility=(("WR", -0.04),)),
        _action(31, "O-Line Fast Start", 2, "Prepare for an energetic opening.", "Common", "match", "O-Line", power=(("OLINE", 1.08),)),
        _action(32, "O-Line Recovery Tubs", 2, "Preserve the unit's late-game output.", "Common", "match", "O-Line", stamina=(("OLINE", 0.12),)),
        _action(33, "Front Seven Get-Off Drill", 2, "Prime the front's power.", "Common", "match", "Front 7", power=(("FRONT7", 1.08),)),
        _action(34, "Front Seven Assignment Review", 2, "Reduce the unit's swing range.", "Common", "match", "Front 7", volatility=(("FRONT7", -0.04),)),
        _action(35, "Secondary Matchup Reps", 2, "Lift the secondary's contribution.", "Common", "match", "Secondary", power=(("SECONDARY", 1.08),)),
        _action(36, "Secondary Communication Check", 2, "Make the unit steadier.", "Common", "match", "Secondary", volatility=(("SECONDARY", -0.04),)),
        _action(37, "Front Seven Fresh Rotation", 2, "Keep energy for late drives.", "Common", "match", "Front 7", stamina=(("FRONT7", 0.12),)),
        _action(38, "Secondary Recovery Session", 2, "Protect late-match stamina.", "Common", "match", "Secondary", stamina=(("SECONDARY", 0.12),)),
        _action(39, "High-Pressure Front", 3, "Raise power but risk more variance.", "Common", "match", "Front 7", power=(("FRONT7", 1.10),), volatility=(("FRONT7", 0.03),)),
        _action(40, "High-Risk Secondary Plan", 3, "Seek a bigger swing from the back end.", "Common", "match", "Secondary", power=(("SECONDARY", 1.10),), volatility=(("SECONDARY", 0.03),)),
        _action(41, "Whole-Roster Recovery Day", 3, "Let every unit recharge.", "Common", "match", "Team", stamina=_effects(POSITIONS, 0.08)),
        _action(42, "Quiet the Locker Room", 2, "Turn nerves into a steadier performance.", "Common", "match", "Team", volatility=_effects(POSITIONS, -0.03)),
        _action(43, "Two-a-Day Challenge", 3, "Gain power now, spend stamina doing it.", "Common", "match", "Team", power=_effects(POSITIONS, 1.04), stamina=_effects(POSITIONS, -0.08)),
        _action(44, "Offensive Recovery Block", 2, "Restore the offense as a group.", "Common", "match", "Team offense", stamina=_effects(OFFENSE, 0.10)),
        _action(45, "Defensive Recovery Block", 2, "Restore the defense as a group.", "Common", "match", "Team defense", stamina=_effects(DEFENSE, 0.10)),
        _action(46, "Low-Variance Week", 3, "Trade a little ceiling for dependable drives.", "Common", "match", "Team", power=_effects(POSITIONS, 0.97), volatility=_effects(POSITIONS, -0.05)),
        _action(47, "Rally Speech", 2, "Boost belief, represented as steadier play.", "Common", "match", "Team", volatility=_effects(POSITIONS, -0.02)),
        _action(48, "High-Tempo Camp", 4, "Push the whole team into a higher gear.", "Common", "match", "Team", power=_effects(POSITIONS, 1.05), volatility=_effects(POSITIONS, 0.03)),
        _action(49, "Air-Raid Install", 3, "Favor QB/WR output over the run game.", "Common", "match", "QB, WR, RB", power=(("QB", 1.05), ("WR", 1.05), ("RB", 0.97))),
        _action(50, "Ground-Game Install", 3, "Lean on the back and line.", "Common", "match", "RB, O-Line, QB, WR", power=(("RB", 1.05), ("OLINE", 1.05), ("QB", 0.97), ("WR", 0.97))),
        _action(51, "Pressure Package", 3, "Favor the front over the secondary.", "Common", "match", "Front 7, Secondary", power=(("FRONT7", 1.06), ("SECONDARY", 0.97))),
        _action(52, "Shell Coverage Package", 3, "Favor the secondary over the front.", "Common", "match", "Secondary, Front 7", power=(("SECONDARY", 1.06), ("FRONT7", 0.97))),
        _action(53, "Balanced Alignment", 4, "Smooth out the team's overall contribution.", "Common", "match", "Team", power=_effects(POSITIONS, 1.03)),
        _action(54, "Disguise and Disrupt", 3, "Trade defensive volatility for a steadier plan.", "Common", "match", "Team defense", power=_effects(DEFENSE, 0.98), volatility=_effects(DEFENSE, -0.04)),
        _action(55, "Promote a Position Coach", 5, "Build a permanent group advantage.", "Rare", "run", "One position group, chosen at purchase", power=(("*", 1.02),), choose_position=True),
        _action(56, "Culture of Fundamentals", 4, "Make one group more consistent for the run.", "Rare", "run", "One position group, chosen at purchase", volatility=(("*", -0.01),), choose_position=True),
        _action(57, "QB Heisman Run", 6, "A once-in-a-run leap in quarterback production.", "Rare", "run", "Current QB", power=(("QB", 1.10),), volatility=(("QB", 0.02),), once_per_run=True),
        _action(58, "RB Workhorse Breakout", 6, "The back becomes a run-defining force.", "Rare", "run", "Current RB", power=(("RB", 1.10),), stamina=(("RB", -0.03),), once_per_run=True),
        _action(59, "WR Star Turn", 6, "A receiver's ceiling rises dramatically.", "Rare", "run", "Current WR", power=(("WR", 1.10),), volatility=(("WR", 0.02),), once_per_run=True),
        _action(60, "O-Line Brotherhood", 6, "The line makes a lasting leap together.", "Rare", "run", "Current O-Line player", power=(("OLINE", 1.10),), stamina=(("OLINE", -0.03),), once_per_run=True),
        _action(61, "Front Seven Game-Wrecker", 6, "Turn the front into a stronger anchor.", "Rare", "run", "Current Front 7 player", power=(("FRONT7", 1.10),), volatility=(("FRONT7", 0.02),), once_per_run=True),
        _action(62, "Secondary Ballhawk Season", 6, "Make the secondary a bigger factor.", "Rare", "run", "Current Secondary player", power=(("SECONDARY", 1.10),), volatility=(("SECONDARY", 0.02),), once_per_run=True),
        _action(63, "Complete Player Transformation", 6, "Improve the chosen player without a volatility penalty.", "Rare", "run", "Any current player", power=(("*", 1.08),), stamina=(("*", 0.05),), choose_position=True, once_per_run=True),
        _action(64, "Viral Hot Streak", 5, "A bigger leap with a bigger variance bill.", "Rare", "run", "Any current player", power=(("*", 1.12),), volatility=(("*", 0.05),), choose_position=True, once_per_run=True),
        _action(65, "Return-Unit Clinic", 3, "Create a few more chances for a momentum flip.", "Rare", "match", "Special Teams", swing_chance=0.02),
        _action(66, "Punt-Coverage Blitz", 3, "Increase the unit's disruption chance.", "Rare", "match", "Special Teams", swing_chance=0.02),
        _action(67, "Return Specialist Signing", 5, "Improve return chances for the run.", "Rare", "run", "Special Teams", swing_chance=0.01, once_per_run=True),
        _action(68, "Special Teams Film Study", 4, "Make the next game's swing chance meaningfully higher.", "Rare", "match", "Special Teams", swing_chance=0.03),
        _action(69, "Field-Goal Mechanics", 4, "Improve reliability on stalled drives.", "Rare", "match", "Special Teams", field_goal_reliability=0.05),
        _action(70, "Kicker Confidence Program", 5, "Improve reliability for the rest of the run.", "Rare", "run", "Special Teams", field_goal_reliability=0.02, once_per_run=True),
        _action(71, "Clutch-Kick Package", 4, "Trade return upside for more reliable kicks.", "Rare", "match", "Special Teams", field_goal_reliability=0.08, swing_chance=-0.01),
        _action(72, "Special Teams Rally", 6, "A small, lasting boost to both phases.", "Rare", "run", "Special Teams", field_goal_reliability=0.03, swing_chance=0.01, once_per_run=True),
        _action(73, "QB Gas-Tank Program", 4, "Build stamina for the long season.", "Uncommon", "run", "QB", stamina=(("QB", 0.04),)),
        _action(74, "RB Ball-Security Reps", 4, "Make the back's output more dependable.", "Uncommon", "run", "RB", volatility=(("RB", -0.02),)),
        _action(75, "WR Endurance Routes", 4, "Build legs for every drive.", "Uncommon", "run", "WR", stamina=(("WR", 0.04),)),
        _action(76, "O-Line Synchronization", 4, "Reduce drive-to-drive variance.", "Uncommon", "run", "O-Line", volatility=(("OLINE", -0.02),)),
        _action(77, "Front Seven Assignment Mastery", 4, "Turn chaos into consistency.", "Uncommon", "run", "Front 7", volatility=(("FRONT7", -0.02),)),
        _action(78, "Secondary Conditioning Block", 4, "Keep the back end fresh.", "Uncommon", "run", "Secondary", stamina=(("SECONDARY", 0.04),)),
        _action(79, "Captain's Standard", 4, "Let one group set the tone.", "Uncommon", "run", "One position group", volatility=(("*", -0.01),), choose_position=True),
        _action(80, "Sports Science Partnership", 5, "Bring better recovery tools to one group.", "Uncommon", "run", "One position group", stamina=(("*", 0.03),), choose_position=True),
        _action(81, "Offensive Identity Reps", 5, "Drill the offense until it moves as one.", "Uncommon", "run", "Team offense", power=_effects(OFFENSE, 1.02)),
        _action(82, "Defensive Identity Reps", 5, "Build a shared defensive standard.", "Uncommon", "run", "Team defense", power=_effects(DEFENSE, 1.02)),
        _action(83, "High-Octane Position Drill", 4, "Chase a higher ceiling, accept messier drives.", "Uncommon", "run", "One position group", power=(("*", 1.04),), volatility=(("*", 0.02),), choose_position=True),
        _action(84, "Precision Technique Camp", 4, "Sacrifice a little punch for reliable execution.", "Uncommon", "run", "One position group", power=(("*", 0.98),), volatility=(("*", -0.03),), choose_position=True),
        _action(85, "Return-Unit Installation", 4, "Put more emphasis on field-flipping plays.", "Uncommon", "run", "Special Teams", swing_chance=0.01),
        _action(86, "Program-Wide Recovery Culture", 6, "Make recovery part of the routine.", "Uncommon", "run", "All player positions", stamina=_effects(POSITIONS, 0.02)),
        _action(87, "Coordinator's Signature Install", 6, "Give one group a lasting coaching edge.", "Rare", "run", "One position group", power=(("*", 1.05),), choose_position=True),
        _action(88, "Statement Game", 5, "Spotlight a player for the next contest.", "Rare", "match", "One player", power=(("*", 1.14),), volatility=(("*", 0.03),), choose_position=True),
        _action(89, "Defensive Takeover", 6, "Let defense carry the game plan.", "Rare", "match", "Team", power=(("FRONT7", 1.08), ("SECONDARY", 1.08), ("QB", 0.97), ("RB", 0.97), ("WR", 0.97), ("OLINE", 0.97))),
        _action(90, "Program Renaissance", 6, "A rare, lasting lift for the whole roster.", "Rare", "run", "All player positions", power=_effects(POSITIONS, 1.03), once_per_run=True),
        _action(91, "Return Unit Breakthrough", 5, "The return game becomes a genuine threat.", "Rare", "match", "Special Teams", swing_chance=0.03),
        _action(92, "Kicker's Clutch Week", 5, "Raise the odds on stalled drives.", "Rare", "match", "Special Teams", field_goal_reliability=0.08),
        _action(93, "Autograph Signing", 3, "Turn a player appearance into next week's gate.", "Rare", "next_shop", "Team / next shop", bank_ap=3, last_shop_excluded=True),
        _action(94, "Fourth-Quarter Conditioning Breakthrough", 6, "A rare, lasting stamina leap.", "Rare", "run", "One position group", stamina=(("*", 0.08),), choose_position=True, once_per_run=True),
        _action(95, "Star Autograph Signing", 2, "Turn a player appearance into next week's gate.", "Common", "next_shop", "Team / next shop", bank_ap=2, last_shop_excluded=True),
        _action(96, "Student Section Rally", 3, "Pack the stands and bring in extra revenue.", "Common", "next_shop", "Team / next shop", bank_ap=3, last_shop_excluded=True),
        _action(97, "Booster Breakfast", 4, "Alumni support funds an extra day of preparation.", "Rare", "next_shop", "Team / next shop", bank_ap=4, last_shop_excluded=True),
        _action(98, "Rivalry Ticket Surge", 2, "A rivalry win pays off at the gate.", "Common", "next_shop", "Team / next shop", bank_ap_on_win=1, bank_ap=1, last_shop_excluded=True),
        _action(99, "Reserve the Calendar", 1, "Save up to two unused days for the next shop.", "Uncommon", "carry", "Unspent AP", carry_unused=True, last_shop_excluded=True),
        _action(100, "Alumni Matching Gift", 3, "A donor matches preparation and rewards a win.", "Rare", "next_shop", "Team / next shop", bank_ap=3, bank_ap_on_win=1, last_shop_excluded=True),
        _action(101, "Slow the Game Down", 3, "Fewer drives favor a deliberate, lower-variance contest.", "Common", "match", "Match format", drive_count=8, replaces="drive_count"),
        _action(102, "Track Meet", 3, "Add possessions and amplify the stamina contest.", "Common", "match", "Match format", drive_count=12, replaces="drive_count"),
        _action(103, "Fatigue-Resistant Rotation", 4, "Keep more power late in the game.", "Common", "match", "Team", fatigue_limit=0.06, replaces="fatigue_limit"),
        _action(104, "Exhausting Pace", 4, "Push both teams into a longer stamina test.", "Common", "match", "Match format", drive_count=12, replaces="drive_count"),
        _action(105, "House-Call Return", 4, "Make a successful Special Teams swing hit harder.", "Rare", "match", "Special Teams", swing_magnitude=3.0),
        _action(106, "Safe-Hands Coverage", 4, "Reduce the size of opposing return swings.", "Uncommon", "match", "Special Teams", opponent_swing_reduction=3.0),
        _action(107, "Kicking Mechanics Tune-Up", 3, "Improve scoring chances on stalled drives.", "Uncommon", "match", "Special Teams", field_goal_reliability=0.05),
        _action(108, "Pressure-Proof Kicker", 5, "Make that reliability boost last.", "Rare", "run", "Special Teams", field_goal_reliability=0.02, once_per_run=True),
        _action(109, "Quick-Count Offense", 2, "Catch the defense before it settles.", "Common", "match", "Team offense", power=_effects(OFFENSE, 1.05), volatility=_effects(OFFENSE, 0.02)),
        _action(110, "Red-Zone Patience", 2, "Trade some explosiveness for steadier drives.", "Common", "match", "Team offense", power=_effects(OFFENSE, 0.98), volatility=_effects(OFFENSE, -0.05)),
        _action(111, "Heavy Personnel Package", 2, "Lean on the line and the back.", "Common", "match", "RB, O-Line", power=(("RB", 1.06), ("OLINE", 1.06))),
        _action(112, "Spread the Field", 2, "Give the passing game more room to work.", "Common", "match", "QB, WR", power=(("QB", 1.06), ("WR", 1.06)), stamina=(("QB", -0.03), ("WR", -0.03))),
        _action(113, "Defensive Rally Point", 2, "Set the tone with a steadier defense.", "Common", "match", "Front 7, Secondary", volatility=_effects(DEFENSE, -0.04)),
        _action(114, "Press-and-Pursue", 2, "Make the defense more forceful, less predictable.", "Common", "match", "Front 7, Secondary", power=_effects(DEFENSE, 1.04), volatility=_effects(DEFENSE, 0.03)),
        _action(115, "Sideline Hydration Plan", 2, "Keep the offense fresh late.", "Common", "match", "Team offense", stamina=_effects(OFFENSE, 0.08)),
        _action(116, "Defensive Rotation Chart", 2, "Preserve the defense's legs.", "Common", "match", "Team defense", stamina=_effects(DEFENSE, 0.08)),
        _action(117, "QB No-Huddle Rehearsal", 3, "Raise the pace and the quarterback's output.", "Common", "match", "QB", power=(("QB", 1.08),), stamina=(("QB", -0.05),)),
        _action(118, "RB Cutback Reads", 2, "Make the back's performance more consistent.", "Common", "match", "RB", power=(("RB", 0.98),), volatility=(("RB", -0.05),)),
        _action(119, "WR Sideline Awareness", 2, "Reduce wild swings in the receiving game.", "Common", "match", "WR", volatility=(("WR", -0.05),)),
        _action(120, "O-Line Fast Tempo", 2, "Add an early surge at the expense of stamina.", "Common", "match", "O-Line", power=(("OLINE", 1.07),), stamina=(("OLINE", -0.06),)),
        _action(121, "Front Seven Gap Discipline", 2, "Favor control over raw force.", "Common", "match", "Front 7", power=(("FRONT7", 0.98),), volatility=(("FRONT7", -0.05),)),
        _action(122, "Secondary Ball-Tracking Reps", 2, "Sharpen the secondary's next outing.", "Common", "match", "Secondary", power=(("SECONDARY", 1.04),), volatility=(("SECONDARY", -0.02),)),
        _action(123, "QB Film-Study Habit", 4, "Build steadier decisions over time.", "Uncommon", "run", "QB", volatility=(("QB", -0.02),)),
        _action(124, "RB Footwork Foundation", 4, "Improve the back's baseline contribution.", "Uncommon", "run", "RB", power=(("RB", 1.02),)),
        _action(125, "WR Conditioning Routes", 4, "Build stamina through repetition.", "Uncommon", "run", "WR", stamina=(("WR", 0.04),)),
        _action(126, "O-Line Hand Placement", 4, "Reduce drive-to-drive inconsistency.", "Uncommon", "run", "O-Line", volatility=(("OLINE", -0.02),)),
        _action(127, "Front Seven Leverage School", 4, "Build a stronger front.", "Uncommon", "run", "Front 7", power=(("FRONT7", 1.02),)),
        _action(128, "Secondary Recovery Routine", 4, "Improve lasting stamina.", "Uncommon", "run", "Secondary", stamina=(("SECONDARY", 0.04),)),
        _action(129, "QB Scramble Conditioning", 4, "Improve stamina, with a volatility tradeoff.", "Uncommon", "run", "QB", stamina=(("QB", 0.06),), volatility=(("QB", 0.01),)),
        _action(130, "RB Vision Work", 4, "Trade some raw punch for repeatability.", "Uncommon", "run", "RB", power=(("RB", 0.98),), volatility=(("RB", -0.03),)),
        _action(131, "WR Separation Reps", 4, "Add power, but make results less predictable.", "Uncommon", "run", "WR", power=(("WR", 1.03),), volatility=(("WR", 0.02),)),
        _action(132, "O-Line Mobility Program", 4, "Build stamina through movement drills.", "Uncommon", "run", "O-Line", stamina=(("OLINE", 0.04),)),
        _action(133, "Front Seven Film Routine", 4, "Make assignments more consistent.", "Uncommon", "run", "Front 7", volatility=(("FRONT7", -0.02),)),
        _action(134, "Secondary Strength Program", 4, "Add lasting power to the unit.", "Uncommon", "run", "Secondary", power=(("SECONDARY", 1.02),)),
        _action(135, "QB Command of the Huddle", 5, "Give the QB a lasting edge in steadiness and output.", "Rare", "run", "QB", power=(("QB", 1.04),), volatility=(("QB", -0.02),)),
        _action(136, "RB Breakaway Season", 5, "A major development with a stamina cost.", "Rare", "run", "RB", power=(("RB", 1.07),), stamina=(("RB", -0.03),)),
        _action(137, "WR Route-Tree Breakthrough", 5, "Raise the receiver's ceiling and consistency.", "Rare", "run", "WR", power=(("WR", 1.04),), volatility=(("WR", -0.02),)),
        _action(138, "O-Line Veteran Cohesion", 5, "Build reliable play across the line.", "Rare", "run", "O-Line", power=(("OLINE", 1.03),), volatility=(("OLINE", -0.03),)),
        _action(139, "Front Seven Identity", 5, "Make the front tougher and more dependable.", "Rare", "run", "Front 7", power=(("FRONT7", 1.04),), volatility=(("FRONT7", -0.02),)),
        _action(140, "Secondary Takeaway Mindset", 5, "Raise output, but add variance.", "Rare", "run", "Secondary", power=(("SECONDARY", 1.07),), volatility=(("SECONDARY", 0.03),)),
        _action(141, "Coordinator's Pressure Package", 4, "Bring a more aggressive defensive plan.", "Rare", "match", "Team defense", power=_effects(DEFENSE, 1.08), stamina=_effects(DEFENSE, -0.05)),
        _action(142, "Perfect-Tempo Week", 5, "Get a team-wide lift by spending energy up front.", "Rare", "match", "Team", power=_effects(POSITIONS, 1.05), stamina=_effects(POSITIONS, -0.04)),
        _action(143, "Booster Club Matching Drive", 3, "A strong turnout funds extra preparation next week.", "Rare", "next_shop", "Team / next shop", bank_ap=4, last_shop_excluded=True),
        _action(144, "Sellout Week", 4, "A one-time burst of ticket revenue.", "Rare", "next_shop", "Team / next shop", bank_ap=5, last_shop_excluded=True),
        _action(145, "Stud Player Program", 6, "Turn one position into a weekly source of resources.", "Very Rare", "run", "One position group", permanent_ap=1, position_ap=True, choose_position=True, last_shop_excluded=True),
        _action(146, "Stadium Naming Partnership", 6, "A major sponsor funds weekly preparation.", "Very Rare", "run", "Team", permanent_ap=1, once_per_run=True, last_shop_excluded=True),
        _action(147, "Generational Breakout", 6, "A current player becomes the centerpiece of the run.", "Very Rare", "run", "One current player", power=(("*", 1.15),), stamina=(("*", 0.05),), choose_position=True, once_per_run=True),
        _action(148, "Championship Culture", 6, "The entire roster takes a lasting step forward.", "Very Rare", "run", "Team", power=_effects(POSITIONS, 1.04), once_per_run=True),
        _action(149, "Heisman Hype Tour", 5, "The star brings a crowd and next-week revenue.", "Very Rare", "next_shop", "Team / next shop", bank_ap=6, last_shop_excluded=True),
        _action(150, "Unbreakable Rotation", 6, "Make the whole team dramatically more durable.", "Very Rare", "run", "Team", stamina=_effects(POSITIONS, 0.10), once_per_run=True),
    ]
    if len(actions) != 150 or {action.id for action in actions} != set(range(1, 151)):
        raise ValueError("The coaching action catalog must contain IDs 1 through 150.")
    if any(not 1 <= action.ap_cost <= 6 for action in actions):
        raise ValueError("Coaching action AP costs must be between 1 and 6.")
    return tuple(actions)


COACHING_ACTIONS = build_catalog()
ACTION_BY_ID = {action.id: action for action in COACHING_ACTIONS}
