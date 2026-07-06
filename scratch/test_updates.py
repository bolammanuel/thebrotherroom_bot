import sys
import os

# Set up module resolution path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import init_db, save_vote, get_vote_stats, init_midweek_checks, get_due_midweek_checks

def run_tests():
    print("--- Starting Database Upgrades Verification ---")
    
    print("1. Running database initialization & migrations...")
    init_db()
    
    print("2. Inserting mock waitlist choices...")
    save_vote("Emmanuel Test", "emmanuel@example.com", "WhatsApp")
    save_vote("Ademola Bot", "+234 812 345 6789", "Telegram")
    save_vote("Daniel Victor", "daniel@example.com", "WhatsApp")
    
    print("3. Fetching waitlist statistics...")
    stats = get_vote_stats()
    print(f"   Platform stats received: {stats}")
    assert stats["Telegram"] >= 1, "Telegram vote count incorrect"
    assert stats["WhatsApp"] >= 2, "WhatsApp vote count incorrect"
    
    print("4. Testing midweek checks initialization...")
    init_midweek_checks()
    due = get_due_midweek_checks()
    print(f"   Due midweek checks fetched count: {len(due)}")
    
    print("--- All Verification Checks Passed Successfully! ---")

if __name__ == "__main__":
    run_tests()
