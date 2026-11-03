import random
from src.engine.units import Roster

def apply_volatility(base_power: float, volatility: float = 0.2) -> float:
    """Applies RNG variance to base power (e.g., 0.2 means +/- 20% swing)."""
    modifier = random.uniform(1.0 - volatility, 1.0 + volatility)
    return base_power * modifier

def simulate_drive(offense: Roster, defense: Roster) -> float:
    """
    Simulates a single drive. 
    Returns a float representing the momentum shift:
    Positive number = Offense wins the drive.
    Negative number = Defense wins the drive.
    """
    # 1. Special Teams Wildcard (Random momentum flips)
    if random.random() < offense.special_teams.momentum_swing_chance:
        return 15.0  # Massive swing (e.g., massive kick return)
    if random.random() < defense.special_teams.momentum_swing_chance:
        return -15.0 # Defense gets a huge swing (e.g., blocked punt)

    # 2. Retrieve base power (already scaled by Coach modifiers in the Roster class)
    base_off = offense.get_offensive_power()
    base_def = defense.get_defensive_power()

    # 3. Apply RNG to simulate drive chaos
    active_off = apply_volatility(base_off)
    active_def = apply_volatility(base_def)

    # 4. Tug-of-War Math
    momentum_shift = active_off - active_def
    
    return momentum_shift
