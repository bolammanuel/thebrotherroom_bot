import os
import sys

# Add the parent directory to Python path so we can import db_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import get_connection

def wipe_users_by_ids(user_ids):
    """Completely wipe progress, reflections, and reminders/pledges for a list of user IDs."""
    if not user_ids:
        print("No user IDs provided.")
        return
        
    conn = get_connection()
    cursor = conn.cursor()
    
    deleted_counts = {"learners": 0, "reflections": 0, "reminders": 0}
    
    print(f"Starting wipe for {len(user_ids)} User ID(s): {user_ids}\n")
    
    for user_id in user_ids:
        try:
            # 1. Learners
            cursor.execute("DELETE FROM learners WHERE user_id = %s", (user_id,))
            deleted_counts["learners"] += cursor.rowcount
            
            # 2. Reflections
            cursor.execute("DELETE FROM reflections WHERE user_id = %s", (user_id,))
            deleted_counts["reflections"] += cursor.rowcount
            
            # 3. Reminders
            cursor.execute("DELETE FROM reminders WHERE user_id = %s", (user_id,))
            deleted_counts["reminders"] += cursor.rowcount
            
            print(f"  - Cleaned user ID {user_id}")
        except Exception as e:
            print(f"  - Error wiping user ID {user_id}: {e}")
            
    conn.commit()
    conn.close()
    
    print("\nWipe complete!")
    print(f"  - Deleted from learners: {deleted_counts['learners']} row(s)")
    print(f"  - Deleted from reflections: {deleted_counts['reflections']} row(s)")
    print(f"  - Deleted from reminders: {deleted_counts['reminders']} row(s)")

if __name__ == "__main__":
    # If user IDs are passed as arguments
    if len(sys.argv) > 1:
        ids = []
        for arg in sys.argv[1:]:
            # Handle comma-separated arguments or individual space-separated arguments
            for part in arg.split(","):
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
        if ids:
            wipe_users_by_ids(ids)
        else:
            print("No valid numeric User IDs found in arguments.")
    else:
        # Prompt user for input
        user_input = input("Enter Telegram User ID(s) to wipe (separated by commas): ").strip()
        if user_input:
            ids = []
            for part in user_input.split(","):
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
            if ids:
                wipe_users_by_ids(ids)
            else:
                print("No valid numeric User IDs entered.")
        else:
            print("No User IDs entered.")
