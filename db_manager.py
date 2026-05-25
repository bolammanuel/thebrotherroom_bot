import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment (Railway provides this automatically)
DATABASE_URL = os.getenv("DATABASE_URL")

class CompatibleCursor:
    def __init__(self, cursor, is_sqlite):
        self.cursor = cursor
        self.is_sqlite = is_sqlite

    def execute(self, query, params=None):
        if self.is_sqlite:
            query = query.replace("%s", "?")
        if params is not None:
            return self.cursor.execute(query, params)
        return self.cursor.execute(query)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()

class CompatibleConnection:
    def __init__(self, conn, is_sqlite):
        self.conn = conn
        self.is_sqlite = is_sqlite

    def cursor(self):
        return CompatibleCursor(self.conn.cursor(), self.is_sqlite)

    def commit(self):
        return self.conn.commit()

    def close(self):
        return self.conn.close()

def get_connection():
    """Get a database connection, falling back to SQLite locally if DATABASE_URL is not set."""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return CompatibleConnection(conn, is_sqlite=False)
    else:
        import sqlite3
        conn = sqlite3.connect("learner_progress.db")
        return CompatibleConnection(conn, is_sqlite=True)

def init_db():
    """Initialize the database with required tables and dynamic column migrations."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create learners table with language preference
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learners (
            user_id BIGINT PRIMARY KEY,
            current_module_id TEXT,
            current_lesson_id TEXT,
            quiz_completed INTEGER DEFAULT 0,
            language_preference TEXT DEFAULT 'en',
            enrollment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create reminders table for persistent scheduling of weekly reminders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id BIGINT,
            reminder_type TEXT,
            pledge_text TEXT,
            reminders_sent INTEGER DEFAULT 0,
            next_send_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, reminder_type)
        )
    """)
    
    # Run dynamic column migrations if columns do not exist
    if conn.is_sqlite:
        cursor.execute("PRAGMA table_info(learners)")
        existing_cols = [r[1] for r in cursor.fetchall()]
    else:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'learners'")
        existing_cols = [r[0] for r in cursor.fetchall()]
        
    new_cols = {
        "post_test_score": "INTEGER DEFAULT -1",
        "pledge_text": "TEXT DEFAULT NULL",
        "ai_questions_count": "INTEGER DEFAULT 0",
        "first_attempt_quizzes": "INTEGER DEFAULT 0",
        "voice_responses_enabled": "INTEGER DEFAULT 0"
    }
    
    for col, col_def in new_cols.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE learners ADD COLUMN {col} {col_def}")
    
    conn.commit()
    conn.close()

def enroll_learner(user_id, language='en'):
    """Enroll a new learner or update language preference."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if learner already exists
    cursor.execute("SELECT user_id FROM learners WHERE user_id = %s", (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        # Update language preference if already enrolled
        cursor.execute(
            "UPDATE learners SET language_preference = %s WHERE user_id = %s",
            (language, user_id)
        )
    else:
        # Enroll new learner
        cursor.execute("""
            INSERT INTO learners (user_id, current_module_id, current_lesson_id, language_preference)
            VALUES (%s, %s, %s, %s)
        """, (user_id, "module_1", "lesson_1_1", language))
    
    conn.commit()
    conn.close()

def get_learner_progress(user_id):
    """Get learner's current progress (module, lesson, quiz status, language)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT current_module_id, current_lesson_id, quiz_completed, language_preference
        FROM learners WHERE user_id = %s
    """, (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result

def update_learner_progress(user_id, module_id, lesson_id, quiz_completed=None):
    """Update learner's progress."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if quiz_completed is not None:
        cursor.execute("""
            UPDATE learners 
            SET current_module_id = %s, current_lesson_id = %s, quiz_completed = %s,
                last_activity = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (module_id, lesson_id, quiz_completed, user_id))
    else:
        cursor.execute("""
            UPDATE learners 
            SET current_module_id = %s, current_lesson_id = %s,
                last_activity = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (module_id, lesson_id, user_id))
    
    conn.commit()
    conn.close()

def update_quiz_status(user_id, quiz_completed):
    """Mark quiz as completed (1) or reset (0)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE learners 
        SET quiz_completed = %s, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (quiz_completed, user_id))
    
    conn.commit()
    conn.close()

def update_language_preference(user_id, language):
    """Update user's language preference."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE learners 
        SET language_preference = %s, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (language, user_id))
    
    conn.commit()
    conn.close()

def get_language_preference(user_id):
    """Get user's language preference."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT language_preference FROM learners WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 'en'

# ============== ADDITIONAL HELPER FUNCTIONS FOR PREMIUM FEATURES ==============

def increment_ai_questions(user_id):
    """Increment AI helper query count for Peer Facilitator calculations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE learners 
        SET ai_questions_count = ai_questions_count + 1, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()

def increment_first_attempt_quizzes(user_id):
    """Increment quizzes correct on first attempt count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE learners 
        SET first_attempt_quizzes = first_attempt_quizzes + 1, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()
    conn.close()

def set_voice_responses(user_id, enabled):
    """Toggle voice response synthesis for visual impairment accessibility."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE learners 
        SET voice_responses_enabled = %s, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()

def get_voice_responses(user_id):
    """Get voice responses preference."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT voice_responses_enabled FROM learners WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result[0]) if result else False

def update_post_test_score(user_id, score):
    """Save exit post-test score."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE learners 
        SET post_test_score = %s, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (score, user_id))
    conn.commit()
    conn.close()

def save_pledge(user_id, pledge_text):
    """Save personal pledge and schedule a 4-week weekly reminder cycle."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Save pledge to learners table
    cursor.execute("""
        UPDATE learners 
        SET pledge_text = %s, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """, (pledge_text, user_id))
    
    # Upsert into reminders table
    if conn.is_sqlite:
        next_send = "datetime('now', '+7 days')"
    else:
        next_send = "CURRENT_TIMESTAMP + INTERVAL '7 days'"
        
    cursor.execute("DELETE FROM reminders WHERE user_id = %s AND reminder_type = 'pledge_reminder'", (user_id,))
    cursor.execute(f"""
        INSERT INTO reminders (user_id, reminder_type, pledge_text, reminders_sent, next_send_time)
        VALUES (%s, 'pledge_reminder', %s, 0, {next_send})
    """, (user_id, pledge_text))
    
    conn.commit()
    conn.close()

def get_pending_reminders():
    """Retrieve reminders whose scheduled send time has arrived."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.user_id, r.reminder_type, r.pledge_text, r.reminders_sent, l.language_preference
        FROM reminders r
        JOIN learners l ON r.user_id = l.user_id
        WHERE r.next_send_time <= CURRENT_TIMESTAMP AND r.reminders_sent < 4
    """)
    results = cursor.fetchall()
    conn.close()
    return results

def update_reminder_sent(user_id, reminder_type):
    """Increment reminders sent count and shift scheduled time to next week."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if conn.is_sqlite:
        next_send = "datetime('now', '+7 days')"
    else:
        next_send = "CURRENT_TIMESTAMP + INTERVAL '7 days'"
        
    cursor.execute(f"""
        UPDATE reminders 
        SET reminders_sent = reminders_sent + 1,
            next_send_time = {next_send}
        WHERE user_id = %s AND reminder_type = %s
    """, (user_id, reminder_type))
    conn.commit()
    conn.close()

def get_engagement_leaderboard():
    """Rank learners by a weighted score of progress, quiz correctness, and assistant interactions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, current_module_id, first_attempt_quizzes, ai_questions_count, post_test_score
        FROM learners
    """)
    rows = cursor.fetchall()
    conn.close()
    
    leaderboard = []
    for row in rows:
        user_id, current_module_id, first_attempt_quizzes, ai_questions_count, post_test_score = row
        
        # Calculate modules completed based on sequential curriculum progress
        modules_completed = 0
        if current_module_id:
            try:
                num = int(current_module_id.split('_')[1])
                if post_test_score >= 0:
                    modules_completed = 12
                else:
                    modules_completed = max(0, num - 1)
            except Exception:
                pass
                
        # Engagement Score = (Modules Completed * 10) + (First Attempt Quizzes * 5) + (AI Questions Asked * 3)
        score = (modules_completed * 10) + (first_attempt_quizzes * 5) + (ai_questions_count * 3)
        
        leaderboard.append({
            "user_id": user_id,
            "modules_completed": modules_completed,
            "first_attempt_quizzes": first_attempt_quizzes,
            "ai_questions_count": ai_questions_count,
            "post_test_score": post_test_score,
            "engagement_score": score
        })
        
    leaderboard.sort(key=lambda x: x["engagement_score"], reverse=True)
    return leaderboard

def get_inactive_learners():
    """Retrieve enrolled learners who have been inactive for more than 4 days and have not completed the course."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if conn.is_sqlite:
        date_check = "datetime('now', '-4 days')"
    else:
        date_check = "CURRENT_TIMESTAMP - INTERVAL '4 days'"
        
    cursor.execute(f"""
        SELECT user_id, current_module_id, current_lesson_id, language_preference
        FROM learners
        WHERE last_activity <= {date_check} AND post_test_score = -1
    """)
    results = cursor.fetchall()
    conn.close()
    return results

