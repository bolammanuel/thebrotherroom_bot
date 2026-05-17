import sqlite3

DATABASE_NAME = 'lms_bot.db'

def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learners (
            user_id INTEGER PRIMARY KEY,
            current_module TEXT,
            current_lesson TEXT,
            quiz_completed INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def enroll_learner(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO learners (user_id, current_module, current_lesson) VALUES (?, ?, ?)',
                   (user_id, 'module_1', 'lesson_1_1'))
    conn.commit()
    conn.close()

def get_learner_progress(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT current_module, current_lesson, quiz_completed FROM learners WHERE user_id = ?', (user_id,))
    progress = cursor.fetchone()
    conn.close()
    return progress

def update_learner_progress(user_id, module_id, lesson_id, quiz_completed=0):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE learners SET current_module = ?, current_lesson = ?, quiz_completed = ? WHERE user_id = ?',
                   (module_id, lesson_id, quiz_completed, user_id))
    conn.commit()
    conn.close()

def update_quiz_status(user_id, quiz_completed_status):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE learners SET quiz_completed = ? WHERE user_id = ?',
                   (quiz_completed_status, user_id))
    conn.commit()
    conn.close()
