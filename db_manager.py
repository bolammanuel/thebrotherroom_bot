import os
import psycopg2
from psycopg2 import sql

# Get database URL from environment (Railway provides this automatically)
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Get a database connection."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    else:
        raise Exception("DATABASE_URL environment variable not set. Please add a PostgreSQL database to your Railway project.")

def init_db():
    """Initialize the database with required tables."""
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
