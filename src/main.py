from src.engine.units import Roster, Unit, Coach, SpecialTeams
from src.engine.simulator import simulate_match

def build_dummy_team(name: str, coach_off: float, coach_def: float) -> Roster:
    return Roster(
        player_name=name,
        qb=Unit(name="Basic QB", position="QB", power=12.0),
        rb=Unit(name="Basic RB", position="RB", power=10.0),
        wr=Unit(name="Basic WR", position="WR", power=10.0),
        oline=Unit(name="Basic OLINE", position="OLINE", power=15.0),
        front7=Unit(name="Basic FRONT7", position="FRONT7", power=14.0),
        secondary=Unit(name="Basic SEC", position="SECONDARY", power=12.0),
        coach=Coach(name="Head Coach", off_scheme="Scheme", def_scheme="Scheme", 
                    off_modifier=coach_off, def_modifier=coach_def),
        special_teams=SpecialTeams()
    )

if __name__ == "__main__":
    # Team A has a +20% offense buff, -10% defense penalty
    team_a = build_dummy_team("Air Raid Monsters", coach_off=1.2, coach_def=0.9)
    
    # Team B has a -10% offense penalty, +30% defense buff
    team_b = build_dummy_team("Grind & Pound", coach_off=0.9, coach_def=1.3)
    
    print(f"Simulating 1,000 matches: {team_a.player_name} vs {team_b.player_name}...\n")
    
    results = {team_a.player_name: 0, team_b.player_name: 0, "Tie": 0}
    
    for _ in range(1000):
        match_result = simulate_match(team_a, team_b)
        results[match_result["winner"]] += 1
            
    print("Results after 1,000 games:")
    print(f"{team_a.player_name}: {results[team_a.player_name]} wins")
    print(f"{team_b.player_name}: {results[team_b.player_name]} wins")
    print(f"Ties: {results['Tie']}")
