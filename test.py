from src.main import build_dummy_team
from src.engine.shop import Shop
from src.db.schema import init_db, save_snapshot, get_random_snapshot

def test_shop_and_db():
    print("--- 1. INITIALIZING DB ---")
    init_db()
    print("Database created/verified at data/cfb_battler.db\n")

    print("--- 2. CREATING ROSTER ---")
    # Using symmetrical 1.0 modifiers for a baseline test
    my_team = build_dummy_team("Arkansas Razorbacks", coach_off=1.0, coach_def=1.0)
    print(f"Original QB: {my_team.qb.name} (Power: {my_team.qb.power})\n")

    print("--- 3. ROLLING THE PORTAL ---")
    shop = Shop(my_team)
    portal = shop.roll_portal()
    for i, unit in enumerate(portal):
        print(f"Option {i+1}: {unit.name} ({unit.position}) - Power {unit.power}")
    print(f"AP Days remaining: {shop.days}\n")

    print("--- 4. DRAFTING A UNIT ---")
    # We will automatically draft the first unit in the portal array for this test
    drafted_unit = portal[0]
    shop.draft_unit(drafted_unit)
    
    # Dynamically check whichever position we just drafted
    slot_name = shop.ROSTER_SLOTS[drafted_unit.position]
    updated_unit = getattr(my_team, slot_name)
    print(f"Drafted! New {drafted_unit.position} is now: {updated_unit.name} (Power: {updated_unit.power})\n")

    print("--- 5. SAVING TO DATABASE ---")
    snapshot_id = save_snapshot(my_team, round_number=1, wins=0, losses=0)
    print(f"Snapshot saved successfully! ID: {snapshot_id}\n")

    print("--- 6. RETRIEVING ASYNC OPPONENT ---")
    # Attempt to pull a snapshot for Round 1
    opponent = get_random_snapshot(round_number=1)
    if opponent:
        print(f"Success! Loaded opponent: {opponent.player_name}")
        print(f"Opponent's QB: {opponent.qb.name}")
    else:
        print("Error: Could not find opponent in database.")

if __name__ == "__main__":
    test_shop_and_db()