import sqlite3
import os

DB_FILE = "learner_progress.db"

def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create learners table with language preference
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learners (
            user_id INTEGER PRIMARY KEY,
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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if learner already exists
    cursor.execute("SELECT user_id FROM learners WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        # Update language preference if already enrolled
        cursor.execute(
            "UPDATE learners SET language_preference = ? WHERE user_id = ?",
            (language, user_id)
        )
    else:
        # Enroll new learner
        cursor.execute("""
            INSERT INTO learners (user_id, current_module_id, current_lesson_id, language_preference)
            VALUES (?, ?, ?, ?)
        """, (user_id, "module_1", "lesson_1_1", language))
    
    conn.commit()
    conn.close()

def get_learner_progress(user_id):
    """Get learner's current progress (module, lesson, quiz status, language)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT current_module_id, current_lesson_id, quiz_completed, language_preference
        FROM learners WHERE user_id = ?
    """, (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result

def update_learner_progress(user_id, module_id, lesson_id, quiz_completed=None):
    """Update learner's progress."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if quiz_completed is not None:
        cursor.execute("""
            UPDATE learners 
            SET current_module_id = ?, current_lesson_id = ?, quiz_completed = ?,
                last_activity = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (module_id, lesson_id, quiz_completed, user_id))
    else:
        cursor.execute("""
            UPDATE learners 
            SET current_module_id = ?, current_lesson_id = ?,
                last_activity = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (module_id, lesson_id, user_id))
    
    conn.commit()
    conn.close()

def update_quiz_status(user_id, quiz_completed):
    """Mark quiz as completed (1) or reset (0)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE learners 
        SET quiz_completed = ?, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (quiz_completed, user_id))
    
    conn.commit()
    conn.close()

def update_language_preference(user_id, language):
    """Update user's language preference."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE learners 
        SET language_preference = ?, last_activity = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (language, user_id))
    
    conn.commit()
    conn.close()

def get_language_preference(user_id):
    """Get user's language preference."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT language_preference FROM learners WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 'en'
