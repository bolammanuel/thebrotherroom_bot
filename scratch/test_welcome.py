import asyncio
import sys
import os

# Add parent directory (workspace root) to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

# Overwrite bot.get_text to test the new implementation
def get_text_fixed(key, lang='en', **kwargs):
    """Get translated text with variable substitution, supporting dotted keys for nested dicts."""
    try:
        parts = key.split('.')
        obj = bot.TRANSLATIONS
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        
        if isinstance(obj, dict):
            text = obj.get(lang, obj.get('en', ''))
        else:
            text = bot.TRANSLATIONS.get(key, {}).get(lang, bot.TRANSLATIONS.get(key, {}).get('en', ''))
            
        for var, value in kwargs.items():
            if text:
                text = text.replace('{' + var + '}', str(value))
        return text
    except Exception as e:
        return "Error"

bot.get_text = get_text_fixed

async def test():
    # Set default language
    import db_manager
    db_manager.init_db()
    db_manager.enroll_learner(12345, "en")
    
    # Run welcome text generation
    welcome_text = bot.get_text("start_welcome", "en", course_title=bot.COURSE_TITLE, course_description=bot.COURSE_DESCRIPTION)
    print("WELCOME TEXT:")
    print(welcome_text)
    
    # Get main menu buttons
    buttons = bot.get_main_menu_buttons("en")
    print("BUTTONS:")
    for row in buttons.inline_keyboard:
        print([b.text for b in row])

asyncio.run(test())
