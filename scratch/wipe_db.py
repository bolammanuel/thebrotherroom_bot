import os
import sys

# Add the parent directory to Python path so we can import db_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import get_connection

def wipe_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    tables = ["learners", "reflections", "reminders"]
    counts = {}
    
    # 1. Count records before deleting
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        except Exception as e:
            print(f"Error counting table {table}: {e}")
            counts[table] = 0
            
    print("Record counts before wipe:")
    for table, count in counts.items():
        print(f"  - {table}: {count} records")
        
    # 2. Delete all records
    print("\nWiping tables...")
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"  - Deleted all rows from {table}")
        except Exception as e:
            print(f"Error wiping table {table}: {e}")
            
    conn.commit()
    conn.close()
    print("\nDatabase wipe complete and changes committed successfully!")

if __name__ == "__main__":
    wipe_database()
