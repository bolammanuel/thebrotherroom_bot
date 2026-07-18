import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Load local environment variables if available
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    if DATABASE_URL:
        print("Connecting to live PostgreSQL database...")
        return psycopg2.connect(DATABASE_URL), False
    else:
        print("DATABASE_URL not found in environment. Connecting to local SQLite (learner_progress.db)...")
        db_path = "learner_progress.db"
        if not os.path.exists(db_path) and os.path.exists("backups/learner_progress_backup_20260701_081815.db"):
            db_path = "backups/learner_progress_backup_20260701_081815.db"
            print(f"Using backup SQLite database: {db_path}")
        return sqlite3.connect(db_path), True

def main():
    try:
        conn, is_sqlite = get_connection()
        cursor = conn.cursor()
        
        # 1. Total Enrolled Users
        cursor.execute("SELECT COUNT(*) FROM learners")
        total_learners = cursor.fetchone()[0]
        
        # 2. Total Graduates (post_test_score >= 0 or similar indicator)
        cursor.execute("SELECT COUNT(*) FROM learners WHERE post_test_score >= 0")
        graduates = cursor.fetchone()[0]
        
        # 3. AI chatbot queries sum
        if is_sqlite:
            cursor.execute("SELECT SUM(ai_questions_count) FROM learners")
        else:
            cursor.execute("SELECT SUM(ai_questions_count) FROM learners")
        total_ai_queries = cursor.fetchone()[0] or 0
        
        # 4. Activity timestamps (timeline)
        cursor.execute("SELECT MIN(enrollment_date), MAX(last_activity) FROM learners")
        first_enrollment, last_activity = cursor.fetchone()
        
        print("\n" + "="*50)
        print("               APPLICATION STATISTICS")
        print("="*50)
        print(f"Total Enrolled Users:     {total_learners}")
        print(f"Total Completed/Grads:    {graduates}")
        print(f"Total AI Conversations:   {total_ai_queries}")
        print(f"First Active Date:        {first_enrollment}")
        print(f"Last Activity Date:       {last_activity}")
        print("="*50)
        print("\nUse these numbers to replace the placeholders in your Medium article!")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"\nError fetching database stats: {e}")
        print("Ensure your DATABASE_URL is set in your environment or .env file.")

if __name__ == "__main__":
    main()
