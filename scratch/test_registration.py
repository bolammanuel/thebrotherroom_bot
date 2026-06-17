import asyncio
import sys
import os
import sqlite3

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db_manager
import bot

def test_db_migration():
    print("Initializing DB...")
    db_manager.init_db()
    
    # Check if age column exists in local database
    conn = db_manager.get_connection()
    cursor = conn.conn.cursor()
    cursor.execute("PRAGMA table_info(learners)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    
    print(f"Table columns: {columns}")
    assert "age" in columns, "Error: 'age' column is missing from learners table!"
    print("✅ DB Migration test passed: 'age' column exists.")

def test_registration_flow_helpers():
    user_id = 99999
    
    # Reset any previous test data
    db_manager.reset_learner_data(user_id)
    
    # Check registration on blank learner
    assert not db_manager.is_learner_registered(user_id), "Should not be registered on empty database entry"
    
    # Enroll learner
    db_manager.enroll_learner(user_id, "en", "Test Learner")
    assert not db_manager.is_learner_registered(user_id), "Should not be registered with only name"
    
    # Update email
    db_manager.update_email(user_id, "test@example.com")
    assert not db_manager.is_learner_registered(user_id), "Should not be registered without age and state"
    
    # Update age
    db_manager.update_age(user_id, 30)
    assert not db_manager.is_learner_registered(user_id), "Should not be registered without state"
    
    # Update state
    db_manager.update_state(user_id, "Lagos")
    
    # Now registration should be complete
    assert db_manager.is_learner_registered(user_id), "Should be fully registered now that name, email, state, and age are set"
    print("✅ Registration helper validation tests passed.")
    
    # Clean up test data
    db_manager.reset_learner_data(user_id)

def test_translations():
    # Verify we can retrieve the added keys
    for lang in ["en", "pcm", "ha", "yo", "ig"]:
        ask_text = bot.get_text("ask_age", lang)
        err_text = bot.get_text("invalid_age_error", lang)
        assert ask_text is not None and len(ask_text) > 0, f"Missing ask_age for {lang}"
        assert err_text is not None and len(err_text) > 0, f"Missing invalid_age_error for {lang}"
    print("✅ Translation key validation tests passed.")

if __name__ == "__main__":
    test_db_migration()
    test_registration_flow_helpers()
    test_translations()
    print("\n🎉 All tests passed successfully!")
