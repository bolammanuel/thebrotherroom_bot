import os
import json
import logging
import asyncio
import csv
import re
import time
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from db_manager import (
    init_db, enroll_learner, get_learner_progress, update_learner_progress, 
    update_quiz_status, update_language_preference, get_language_preference,
    get_connection, increment_ai_questions, increment_first_attempt_quizzes,
    set_voice_responses, get_voice_responses, update_post_test_score,
    save_pledge, get_pending_reminders, update_reminder_sent, get_engagement_leaderboard,
    get_inactive_learners, update_pre_test_score, get_pre_test_score, update_full_name,
    get_due_sunday_checks, init_sunday_checks, update_sunday_check_sent, get_all_learner_reflections,
    reset_learner_data, backup_sqlite_db
)
from openai_utils import get_openai_response, transcribe_voice, synthesize_speech


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load course content
COURSE_CONTENT = {}
with open("course_content.json", "r") as f:
    COURSE_CONTENT = json.load(f)

# Load translations
TRANSLATIONS = {}
with open("translations.json", "r") as f:
    TRANSLATIONS = json.load(f)

COURSE_TITLE = COURSE_CONTENT["course_title"]
COURSE_DESCRIPTION = COURSE_CONTENT["course_description"]
MODULES = COURSE_CONTENT["modules"]

HASHTAGS_MAPPING = {
    "module_1": "#TheBrothersRoom #PositiveMasculinity #GBV",
    "module_2": "#TheBrothersRoom #BreakTheNorm #MenMatter",
    "module_3": "#TheBrothersRoom #EndSGBV #NigerianMen",
    "module_4": "#TheBrothersRoom #RootCauses #EndGBV",
    "module_5": "#TheBrothersRoom #MenAsAllies #BeTheChange",
    "module_6": "#TheBrothersRoom #HealthyRelationships #Consent",
    "module_7": "#TheBrothersRoom #BystanderIntervention #SpeakUp",
    "module_8": "#TheBrothersRoom #LeadWell #MenLeading",
    "module_9": "#TheBrothersRoom #CommunityChange #TogetherWeChange",
    "module_10": "#TheBrothersRoom #MovementBuilding #TogetherWeChange",
    "module_11": "#TheBrothersRoom #ChangeAgent #TheWorkBegins",
}

# ============== TRANSLATION HELPER FUNCTIONS ==============

def get_text(key, lang='en', **kwargs):
    """Get translated text with variable substitution, supporting dotted keys for nested dicts."""
    try:
        # Resolve dotted key path (e.g., 'command_buttons.next')
        parts = key.split('.')
        obj = TRANSLATIONS
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        
        # If successfully found the translation object, get the language value
        if isinstance(obj, dict):
            text = obj.get(lang, obj.get('en', ''))
        else:
            # Fallback to direct top-level key lookup
            text = TRANSLATIONS.get(key, {}).get(lang, TRANSLATIONS.get(key, {}).get('en', ''))
            
        # Replace variables in curly braces
        for var, value in kwargs.items():
            if text:
                text = text.replace('{' + var + '}', str(value))
        return text
    except Exception as e:
        logger.error(f"Translation error for key {key}: {e}")
        return "Error"

def get_command_button(button_name, lang='en'):
    """Get translated command button text."""
    return get_text(f"command_buttons.{button_name}", lang)

def get_localized_field(field_value, lang, default_val=""):
    """
    Get localized string from a dictionary containing language keys.
    If field_value is a string, returns it directly.
    If field_value is a dict, returns key for 'lang', falls back to 'en', or gets any available key.
    """
    if not field_value:
        return default_val
    if isinstance(field_value, dict):
        val = field_value.get(lang)
        if val is not None:
            return val
        val = field_value.get("en")
        if val is not None:
            return val
        for k in ["pcm", "ha", "yo", "ig"]:
            if k in field_value:
                return field_value[k]
        if field_value.values():
            return list(field_value.values())[0]
        return default_val
    return str(field_value)

def get_localized_options(options_value, lang, default_val=None):
    """
    Get localized options list.
    """
    if default_val is None:
        default_val = []
    if not options_value:
        return default_val
    if isinstance(options_value, dict):
        val = options_value.get(lang)
        if val is not None:
            return val
        val = options_value.get("en")
        if val is not None:
            return val
        for k in ["pcm", "ha", "yo", "ig"]:
            if k in options_value:
                return options_value[k]
        if options_value.values():
            return list(options_value.values())[0]
        return default_val
    return options_value

# ============== INLINE BUTTON HELPER ==============

def get_main_menu_buttons(lang='en', user_id=None, show_quiz=None, context=None):
    """Get context-aware main menu buttons with a dynamic accessibility toggle and dynamically hidden quiz button."""
    voice_enabled = False
    
    if show_quiz is None:
        show_quiz = False
        if user_id:
            try:
                voice_enabled = get_voice_responses(user_id)
                progress = get_learner_progress(user_id)
                if progress and progress[0]:
                    current_module_id, current_lesson_id, quiz_completed, _ = progress
                    quiz_completed = int(quiz_completed) if quiz_completed is not None else 0
                    if is_last_lesson_of_module(current_module_id, current_lesson_id) and quiz_completed == 0:
                        show_quiz = True
                        if context and ("awaiting_quote_card" in context.user_data or "awaiting_lessons_complete" in context.user_data):
                            show_quiz = False
            except Exception:
                pass
    else:
        if user_id:
            try:
                voice_enabled = get_voice_responses(user_id)
            except Exception:
                pass
            
    if voice_enabled:
        voice_label = {
            "en": "Voice: ON 🔊",
            "pcm": "Voice: ON 🔊",
            "ha": "Murya: A KUNNE 🔊",
            "yo": "Ohun: MÚ KÚN 🔊",
            "ig": "Olu: MERE 🔊"
        }.get(lang, "Voice: ON 🔊")
    else:
        voice_label = {
            "en": "Voice: OFF 🔇",
            "pcm": "Voice: OFF 🔇",
            "ha": "Murya: A KASHE 🔇",
            "yo": "Ohun: MÚ KÚRÒ 🔇",
            "ig": "Olu: PAA 🔇"
        }.get(lang, "Voice: OFF 🔇")

    buttons = []
    
    # Check if we should show the Back button
    has_back = False
    if user_id:
        try:
            progress = get_learner_progress(user_id)
            if progress and progress[0]:
                current_module_id, current_lesson_id, quiz_completed, _ = progress
                if not (current_module_id == "module_1" and current_lesson_id == "start"):
                    has_back = True
        except Exception:
            pass
            
    nav_row = []
    if has_back:
        nav_row.append(InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"))
    nav_row.append(InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next"))
    buttons.append(nav_row)
    
    # Dynamic Quiz button visibility
    if show_quiz:
        buttons.append([InlineKeyboardButton(get_command_button("quiz", lang), callback_data="cmd_quiz")])
        
    buttons.extend([
        [InlineKeyboardButton(get_command_button("progress", lang), callback_data="cmd_progress"),
         InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")],
        [InlineKeyboardButton(get_command_button("language", lang), callback_data="cmd_language"),
         InlineKeyboardButton(get_command_button("help", lang), callback_data="cmd_help")],
        [InlineKeyboardButton("📖 " + {
            "en": "My Journal",
            "pcm": "My Journal",
            "ha": "Littafin Tunanina",
            "yo": "Iwe Iṣaro Mi",
            "ig": "Akwụkwọ M"
        }.get(lang, "My Journal"), callback_data="cmd_journal")],
        [InlineKeyboardButton(voice_label, callback_data="cmd_accessibility")]
    ])
    return InlineKeyboardMarkup(buttons)

def get_help_keyboard_buttons(lang='en', user_id=None, context=None):
    """Get keyboard buttons specifically for the help menu containing all commands with dynamic quiz visibility."""
    voice_enabled = False
    show_quiz = False
    if user_id:
        try:
            voice_enabled = get_voice_responses(user_id)
            progress = get_learner_progress(user_id)
            if progress and progress[0]:
                current_module_id, current_lesson_id, quiz_completed, _ = progress
                quiz_completed = int(quiz_completed) if quiz_completed is not None else 0
                if is_last_lesson_of_module(current_module_id, current_lesson_id) and quiz_completed == 0:
                    show_quiz = True
                    if context and ("awaiting_quote_card" in context.user_data or "awaiting_lessons_complete" in context.user_data):
                        show_quiz = False
        except Exception:
            pass
            
    if voice_enabled:
        voice_label = {
            "en": "Voice: ON 🔊",
            "pcm": "Voice: ON 🔊",
            "ha": "Murya: A KUNNE 🔊",
            "yo": "Ohun: MÚ KÚN 🔊",
            "ig": "Olu: MERE 🔊"
        }.get(lang, "Voice: ON 🔊")
    else:
        voice_label = {
            "en": "Voice: OFF 🔇",
            "pcm": "Voice: OFF 🔇",
            "ha": "Murya: A KASHE 🔇",
            "yo": "Ohun: MÚ KÚRÒ 🔇",
            "ig": "Olu: PAA 🔇"
        }.get(lang, "Voice: OFF 🔇")

    start_label = {
        "en": "Start / Restart",
        "pcm": "Start / Restart",
        "ha": "Fara / Sake Fara",
        "yo": "Bẹrẹ / Tun Bẹrẹ",
        "ig": "Malite / Malite Ọzọ"
    }.get(lang, "Start / Restart")

    community_label = {
        "en": "Join Telegram Group",
        "pcm": "Join Telegram Group",
        "ha": "Shiga Rukunin Telegram",
        "yo": "Darapọ mọ Agbegbe Telegram",
        "ig": "Soro na Otu Telegram"
    }.get(lang, "Join Telegram Group")

    buttons = [
        [InlineKeyboardButton(start_label, callback_data="cmd_start")]
    ]
    
    # Context-aware commands row
    if show_quiz:
        buttons.append([
            InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next"),
            InlineKeyboardButton(get_command_button("quiz", lang), callback_data="cmd_quiz")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next")
        ])
        
    buttons.extend([
        [InlineKeyboardButton(get_command_button("progress", lang), callback_data="cmd_progress"),
         InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")],
        [InlineKeyboardButton(get_command_button("language", lang), callback_data="cmd_language"),
         InlineKeyboardButton(get_command_button("help", lang), callback_data="cmd_help")],
        [InlineKeyboardButton("📖 " + {
            "en": "My Journal",
            "pcm": "My Journal",
            "ha": "Littafin Tunanina",
            "yo": "Iwe Iṣaro Mi",
            "ig": "Akwụkwọ M"
        }.get(lang, "My Journal"), callback_data="cmd_journal")],
        [InlineKeyboardButton(voice_label, callback_data="cmd_accessibility")],
        [InlineKeyboardButton(community_label, url=os.getenv("TELEGRAM_GROUP_URL", "https://t.me/YOUR_TELEGRAM_GROUP_LINK"))]
    ])
    return InlineKeyboardMarkup(buttons)

def get_language_selection_buttons():
    """Get language selection buttons."""
    buttons = [
        [InlineKeyboardButton("English", callback_data="lang_en")],
        [InlineKeyboardButton("Pidgin", callback_data="lang_pcm")],
        [InlineKeyboardButton("Hausa", callback_data="lang_ha")],
        [InlineKeyboardButton("Yoruba", callback_data="lang_yo")],
        [InlineKeyboardButton("Igbo", callback_data="lang_ig")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_quiz_retry_buttons(lang='en'):
    """Get buttons for retry or move forward after wrong answer."""
    buttons = [
        [InlineKeyboardButton(get_text("quiz_retry_button", lang), callback_data="quiz_retry")],
        [InlineKeyboardButton(get_text("quiz_skip_button", lang), callback_data="quiz_skip")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_quiz_continue_button(lang='en'):
    """Get continue button after correct answer."""
    buttons = [
        [InlineKeyboardButton(get_text("quiz_continue_button", lang), callback_data="cmd_next")]
    ]
    return InlineKeyboardMarkup(buttons)

# ============== COURSE NAVIGATION HELPERS ==============

def get_module_by_id(module_id):
    """Get module by ID."""
    for module in MODULES:
        if module["module_id"] == module_id:
            return module
    return None

def get_module_lesson(module_id, lesson_id):
    """Get module and lesson by IDs."""
    for module in MODULES:
        if module["module_id"] == module_id:
            for lesson in module["lessons"]:
                if lesson["lesson_id"] == lesson_id:
                    return module, lesson
    return None, None

def is_last_lesson_of_module(module_id, lesson_id):
    """Check if lesson is the last in module."""
    module = get_module_by_id(module_id)
    if module and module["lessons"]:
        return lesson_id == module["lessons"][-1]["lesson_id"]
    return False

def get_next_lesson(current_module_id, current_lesson_id):
    """Get next lesson or module."""
    current_module_index = -1
    current_lesson_index = -1

    for i, module in enumerate(MODULES):
        if module["module_id"] == current_module_id:
            current_module_index = i
            for j, lesson in enumerate(module["lessons"]):
                if lesson["lesson_id"] == current_lesson_id:
                    current_lesson_index = j
                    break

    if current_module_index == -1 or current_lesson_index == -1:
        return None, None

    # Try to get next lesson in current module
    if current_lesson_index + 1 < len(MODULES[current_module_index]["lessons"]):
        next_lesson = MODULES[current_module_index]["lessons"][current_lesson_index + 1]
        return current_module_id, next_lesson["lesson_id"]

    # Try to get first lesson in next module
    elif current_module_index + 1 < len(MODULES):
        next_module = MODULES[current_module_index + 1]
        if next_module["lessons"]:
            return next_module["module_id"], next_module["lessons"][0]["lesson_id"]

    return None, None

def get_previous_lesson(current_module_id, current_lesson_id):
    """Get previous lesson or module."""
    if current_lesson_id == "start":
        return None, None
        
    current_module_index = -1
    current_lesson_index = -1

    for i, module in enumerate(MODULES):
        if module["module_id"] == current_module_id:
            current_module_index = i
            for j, lesson in enumerate(module["lessons"]):
                if lesson["lesson_id"] == current_lesson_id:
                    current_lesson_index = j
                    break

    if current_module_index == -1 or current_lesson_index == -1:
        return None, None

    # Try to get previous lesson in current module
    if current_lesson_index - 1 >= 0:
        prev_lesson = MODULES[current_module_index]["lessons"][current_lesson_index - 1]
        return current_module_id, prev_lesson["lesson_id"]

    # Try to get last lesson in previous module
    elif current_module_index - 1 >= 0:
        prev_module = MODULES[current_module_index - 1]
        if prev_module["lessons"]:
            return prev_module["module_id"], prev_module["lessons"][-1]["lesson_id"]

    # If it's Module 1 Lesson 1, going back takes them to "start"
    return "module_1", "start"

def get_quiz_correct_answer(module_id):
    """Helper to get correct answer letter for current module first question."""
    module = get_module_by_id(module_id)
    if module and "quiz" in module:
        if isinstance(module["quiz"], list) and len(module["quiz"]) > 0:
            return module["quiz"][0]["answer"]
        elif isinstance(module["quiz"], dict):
            return module["quiz"]["answer"]
    return "A"

# ============== ACCESSIBILITY VOICE UTILITIES ==============

def clean_text_for_tts(text):
    """Clean raw message text to make it sound natural when spoken by TTS."""
    if not text:
        return ""
    # 1. Replace markdown links [label](url) with just label
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 2. Replace URLs with a natural spoken description
    text = re.sub(r'https?://[^\s]+', 'the link', text)
    
    # 3. Format quiz options "A) ..." to "Option A. "
    text = re.sub(r'\b([A-F])\)', r'Option \1. ', text)
    
    # 4. Remove unwanted symbols/emojis
    symbols_to_remove = [
        '*', '_', '`', '👉', '👇', '✅', '🎉', '📊', '📝', '📖', 
        '📚', '🤜', '🤛', '🔊', '🔇', '🏆', '🥇', '🥈', '🥉', 
        '👤', '🔙', '✍️', '❓', '❌', '🎓', '🌟', '📢'
    ]
    for sym in symbols_to_remove:
        text = text.replace(sym, '')
        
    # 5. Clean up extra whitespaces/newlines
    text = re.sub(r'\n+', '\n', text).strip()
    return text

def extract_option_letter(text):
    """Normalize and extract quiz option letter (A, B, C, D, etc.) from message/transcription."""
    if not text:
        return None
    text_clean = text.strip().upper().rstrip('.')
    
    # Remove common prefix words
    for prefix in ["OPTION ", "CHOICE ", "SELECT ", "CHOOSE ", "ANSWER ", "LETTER "]:
        if text_clean.startswith(prefix):
            text_clean = text_clean[len(prefix):].strip()
            
    # If the remaining is just a letter, or a letter followed by a parenthesis/dot
    if len(text_clean) >= 1 and text_clean[0] in ['A', 'B', 'C', 'D', 'E', 'F']:
        if len(text_clean) == 1 or not text_clean[1].isalnum():
            return text_clean[0]
            
    # Also check if it's a word matching one of the letters in a sentence
    tokens = [t.strip(".,()\"'") for t in text.upper().split()]
    for token in tokens:
        if token in ['A', 'B', 'C', 'D', 'E', 'F']:
            return token
            
    return None

def extract_module_number(text):
    """Normalize and extract a module number (1 to 6) from message/transcription."""
    if not text:
        return None
    text_lower = text.lower()
    
    num_map = {
        "one": 1, "first": 1, "1": 1, "dáya": 1, "daya": 1, "kín-in-ní": 1, "kininni": 1, "mbụ": 1, "mbu": 1,
        "two": 2, "second": 2, "2": 2, "biyu": 2, "kejì": 2, "keji": 2, "abụọ": 2, "abuo": 2,
        "three": 3, "third": 3, "3": 3, "uku": 3, "kẹta": 3, "keta": 3, "atọ": 3, "ato": 3,
        "four": 4, "fourth": 4, "4": 4, "hudu": 4, "kẹrin": 4, "kerin": 4, "anọ": 4, "ano": 4,
        "five": 5, "fifth": 5, "5": 5, "biyar": 5, "kàrún-ún": 5, "karun": 5, "ise": 5, "íse": 5,
        "six": 6, "sixth": 6, "6": 6, "shida": 6, "kẹfà": 6, "kefa": 6, "isii": 6
    }
    
    module_synonyms = ["module", "modul", "modulo", "modulu", "mọdulu", "modúlu"]
    
    # Split into words/tokens
    tokens = re.findall(r'\w+', text_lower)
    
    has_module_keyword = any(syn in tokens for syn in module_synonyms)
    
    for i, token in enumerate(tokens):
        if token in module_synonyms:
            if i + 1 < len(tokens) and tokens[i+1] in num_map:
                return num_map[tokens[i+1]]
            if i - 1 >= 0 and tokens[i-1] in num_map:
                return num_map[tokens[i-1]]
                
    if has_module_keyword:
        for token in tokens:
            if token in num_map:
                return num_map[token]
                
    for syn in module_synonyms:
        for token in tokens:
            if token.startswith(syn) and len(token) > len(syn):
                num_part = token[len(syn):]
                if num_part in num_map:
                    return num_map[num_part]
                    
    for syn in module_synonyms:
        for word, num in num_map.items():
            if f"{syn} {word}" in text_lower or f"{word} {syn}" in text_lower:
                return num
                
    return None

async def jump_to_module(update: Update, context: ContextTypes.DEFAULT_TYPE, module_idx: int) -> None:
    """Jump the user directly to a specific module (0-indexed)."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    if module_idx < 0 or module_idx >= len(MODULES):
        await send_reply(update, get_text("error_generic", lang))
        return
        
    target_module = MODULES[module_idx]
    target_module_id = target_module["module_id"]
    
    # Get the first lesson of the target module
    if target_module["lessons"]:
        target_lesson_id = target_module["lessons"][0]["lesson_id"]
    else:
        target_lesson_id = "start"
        
    # Update learner progress in DB, reset quiz completed status to 0
    update_learner_progress(user_id, target_module_id, target_lesson_id, quiz_completed=0)
    
    # Clear any awaiting states in context.user_data to avoid confusing flow
    for key in ["awaiting_reflection", "awaiting_quote_card", "awaiting_lessons_complete", "story_read", "quiz_question_idx", "quiz_errors", "quiz_module_id"]:
        context.user_data.pop(key, None)
        
    module_num = str(module_idx + 1)
    lesson_num = "1"
    
    # If the target module has an opening story, show that first
    if target_module.get("opening_story"):
        context.user_data["story_read"] = target_module_id
        
        story_header = {
            "en": "📖 *Opening Story*",
            "pcm": "📖 *Opening Story*",
            "ha": "📖 *Labarin Budewa*",
            "yo": "📖 *Itan Ibẹrẹ*",
            "ig": "📖 *Akụkọ Mbido*"
        }.get(lang, "📖 Opening Story")
        
        next_button = InlineKeyboardMarkup([[
            InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
            InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
        ]])
        
        await send_reply(
            update,
            f"{story_header}\n\n{get_localized_field(target_module.get('opening_story'), lang)}",
            reply_markup=next_button,
            parse_mode="Markdown"
        )
    else:
        # Show lesson 1 of the target module directly
        lesson_header = get_text(
            "lesson_header", lang, 
            module_num=module_num, 
            module_title=get_localized_field(target_module.get('title'), lang), 
            lesson_num=lesson_num, 
            lesson_title=get_localized_field(target_module["lessons"][0].get('title'), lang)
        )
        
        video_file_id = target_module["lessons"][0].get("video")
        if video_file_id:
            try:
                chat_msg = update.callback_query.message if update.callback_query else update.message
                await chat_msg.reply_video(
                    video=video_file_id,
                    caption=lesson_header,
                    parse_mode="Markdown"
                )
                await send_reply(
                    update,
                    get_localized_field(target_module["lessons"][0].get('content'), lang),
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                )
            except Exception as e:
                logger.error(f"Error sending lesson video on jump: {e}")
                await send_reply(
                    update,
                    f"{lesson_header}\n\n{get_localized_field(target_module['lessons'][0].get('content'), lang)}",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                )
        else:
            await send_reply(
                update,
                f"{lesson_header}\n\n{get_localized_field(target_module['lessons'][0].get('content'), lang)}",
                parse_mode="Markdown",
                reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
            )

async def process_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, module_id: str, q_idx: int, selected_answer: str) -> None:
    """Process a module quiz answer (called from button callback or voice/text input)."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    query = update.callback_query
    
    module = get_module_by_id(module_id)
    if not module or "quiz" not in module:
        if query:
            await query.edit_message_text(get_text("error_generic", lang))
        else:
            await send_reply(update, get_text("error_generic", lang))
        return
        
    quizzes = module["quiz"]
    if not isinstance(quizzes, list):
        quizzes = [quizzes]
        
    if q_idx >= len(quizzes):
        q_idx = 0
        
    quiz_data = quizzes[q_idx]
    correct_answer = quiz_data["answer"]
    feedback = get_localized_field(quiz_data.get("feedback"), lang)
    
    is_correct = (selected_answer == correct_answer)
    
    if "quiz_errors" not in context.user_data:
        context.user_data["quiz_errors"] = 0
        
    if not is_correct:
        context.user_data["quiz_errors"] += 1
        
    fb_title = {
        "en": "📢 *Feedback:*",
        "pcm": "📢 *Feedback:*",
        "ha": "📢 *Maganar Gaskiya:*",
        "yo": "📢 *Esi Iṣaju:*",
        "ig": "📢 *Azịza na Nkowasi:*"
    }.get(lang, "Feedback:")
    
    ans_status = "✅ Correct!" if is_correct else f"❌ Incorrect (Correct was {correct_answer})"
    
    feedback_text = (
        f"❓ *{get_localized_field(quiz_data.get('question'), lang)}*\n\n"
        f"Your Answer: *{selected_answer}* — {ans_status}\n\n"
        f"{fb_title} {feedback}"
    )
    
    if q_idx + 1 < len(quizzes):
        next_q_idx = q_idx + 1
        buttons = [
            [InlineKeyboardButton("Next Question ➡️", callback_data=f"quiz_q|{module_id}|{next_q_idx}")],
            [InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        if query:
            await query.edit_message_text(feedback_text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await send_reply(update, feedback_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        errors = context.user_data.get("quiz_errors", 0)
        progress = get_learner_progress(user_id)
        
        if errors == 0:
            context.user_data.pop("quiz_question_idx", None)
            context.user_data.pop("quiz_errors", None)
            context.user_data.pop("quiz_module_id", None)
            quiz_comp = int(progress[2]) if (progress and progress[2] is not None) else 0
            if quiz_comp == 0:
                increment_first_attempt_quizzes(user_id)
            update_quiz_status(user_id, 1)
            
            completion_text = (
                f"{feedback_text}\n\n"
                f"🎉 *Quiz Complete!* You scored 3/3 correct!\n\n"
                f"{get_text('quiz_correct', lang)}"
            )
            buttons = [
                [InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")],
                [InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev")]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            
            badge_path = None
            try:
                badge_name = TRANSLATIONS.get("badges", {}).get(module_id, {}).get(lang, "Badge")
                badge_path = generate_badge_image(module_id, badge_name, lang, user_id)
            except Exception as e:
                logger.error(f"Error generating badge image on perfect score: {e}")
            
            if query:
                await query.delete_message()
            
            chat_msg = query.message if query else update.message
            if badge_path and os.path.exists(badge_path):
                try:
                    with open(badge_path, "rb") as bf:
                        await chat_msg.reply_photo(
                            photo=bf,
                            caption=completion_text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                        if get_voice_responses(user_id):
                            output_filename = f"assets/voice_reply_{user_id}.ogg"
                            clean_txt = clean_text_for_tts(completion_text)
                            if len(clean_txt) > 800:
                                clean_txt = clean_txt[:800] + "..."
                            if synthesize_speech(clean_txt, output_filename):
                                try:
                                    with open(output_filename, "rb") as vf:
                                        await chat_msg.reply_voice(voice=vf)
                                except Exception as ve:
                                    logger.error(f"Error sending synthesized voice completion: {ve}")
                                finally:
                                    if os.path.exists(output_filename):
                                        os.remove(output_filename)
                except Exception as e:
                    logger.error(f"Error sending badge photo: {e}")
                    await send_reply(
                        update,
                        text=completion_text,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                finally:
                    try:
                        if badge_path and os.path.exists(badge_path):
                            os.remove(badge_path)
                    except Exception:
                        pass
            else:
                await send_reply(
                    update,
                    text=completion_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        else:
            update_quiz_status(user_id, 2)
            score = 3 - errors
            completion_text = (
                f"{feedback_text}\n\n"
                f"📊 *Quiz Complete!* You scored {score}/3.\n\n"
                f"{get_text('quiz_incorrect', lang, correct_answer=correct_answer)}"
            )
            buttons = [
                [
                    InlineKeyboardButton(get_text("quiz_retry_button", lang), callback_data="quiz_retry"),
                    InlineKeyboardButton(get_text("quiz_skip_button", lang), callback_data="quiz_skip")
                ],
                [
                    InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            if query:
                await query.edit_message_text(completion_text, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await send_reply(update, completion_text, reply_markup=reply_markup, parse_mode="Markdown")

# ============== REPLY HELPER ==============

async def send_reply(update: Update, text, reply_markup=None, parse_mode=None):
    """Send a reply that works for both commands and callback queries, and handles accessibility voice notes if enabled."""
    target_msg = None
    if update.callback_query:
        target_msg = await update.callback_query.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    elif update.message:
        target_msg = await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
    # Check for voice accessibility preference (ENABLED)
    user_id = update.effective_user.id if update.effective_user else None
    if user_id and get_voice_responses(user_id):
        # Clean text of raw markdown formatting for a natural audio reading experience
        clean_text = clean_text_for_tts(text)
        
        # Safe length truncation to optimize TTS request speed
        if len(clean_text) > 800:
            clean_text = clean_text[:800] + "..."
            
        output_filename = f"assets/voice_reply_{user_id}.ogg"
        success = synthesize_speech(clean_text, output_filename)
        if success:
            try:
                chat_msg = update.callback_query.message if update.callback_query else update.message
                with open(output_filename, "rb") as voice_file:
                    await chat_msg.reply_voice(voice=voice_file)
            except Exception as e:
                logger.error(f"Error sending synthesized voice reply: {e}")
            finally:
                if os.path.exists(output_filename):
                    try:
                        os.remove(output_filename)
                    except Exception:
                        pass

# ============== GRADUATION HOOKS FOR A4 CERTIFICATE LIFECYCLE ==============

def is_user_graduated(user_id):
    """Check if the user has successfully passed the course post-test (score >= 35)."""
    # Secure developer/admin bypass
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    if user_id in admin_ids:
        return False  # Admins and developers are never blocked from testing!
        
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT post_test_score FROM learners WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        score = row[0] if row else -1
        return score >= 35
    except Exception as e:
        logger.error(f"Error checking graduation status: {e}")
        return False

async def send_graduation_dashboard(update, context, lang, user_id):
    """Display a warm congratulatory dashboard for graduated champions."""
    grad_msg = {
        "en": "🌟 *Welcome Back, Peer Champion!* 🎓\n\nYou have successfully completed *The Brothers' Room* course and earned your Certificate of Completion!\n\nKeep living as a champion, standing against Gender-Based Violence, and leading by example in your family and community. \n\nUse the menu buttons below to check your outline, review lessons, or ask Tobi any questions in the chat!",
        "pcm": "🌟 *Welcome Back, Peer Champion!* 🎓\n\nHow far brother! You don finish *The Brothers' Room* course and get your Certificate of Completion!\n\nKeep living as champion inside your family and community. You fit use the menu buttons below to see all lessons, or ask Tobi any question here!",
        "ha": "🌟 *Barka da Dawowa, Abokin Alkawari!* 🎓\n\nKun sami nasarar kammala karatun *The Brothers' Room* kuma kun sami Takardar Shaidarku!\n\nCi gaba da zama abin koyi ga al'ummarku da yaki da GBV. Kuna iya duba darussan a cikin *Tsarin Darussa*, ko kuma ku tambaye ni komai a nan!",
        "yo": "🌟 *Ẹ ku abọ, Peer Champion!* 🎓\n\nO ti parí eko *The Brothers' Room* ati gba Iwe-ẹri Ipari rẹ!\n\nTesiwaju lati jẹ apeere rere fun alagbegbe rẹ ati duro lodi si GBV. O le tẹsiwaju lati wo eko rẹ ninu *Ilana Ẹkọ* tabi beere lọwọ mi nibi!",
        "ig": "🌟 *Nnọọ, Onye Mgbanwe!* 🎓\n\nỊ gachasịla akwụkwọ *The Brothers' Room* wee nweta Asambodo Mmezu gị!\n\nGaa n'ihu na-abụ onye ndu n'obodo gị na-eguzogide GBV. Ị nwere ike ịgụ ihe ọmụmụ gị na *Ụkpụrụ Akwụkwọ*, ma ọ bụ jụọ m ajụjụ n'ebe a!"
    }.get(lang, "You have successfully completed the course!")

    await send_reply(
        update,
        grad_msg,
        reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context),
        parse_mode="Markdown"
    )

# ============== COMMAND HANDLERS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - show language selection or welcome back returning learners."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    if is_user_graduated(user_id):
        await send_graduation_dashboard(update, context, lang, user_id)
        return
        
    # Check if learner already has completed profile registration
    from db_manager import is_learner_registered
    if is_learner_registered(user_id):
        # Check if learner already has progress
        result = get_learner_progress(user_id)
        
        if result and result[0]:
            # Returning learner — welcome them back
            current_module_id, current_lesson_id, quiz_completed, lang = result
            quiz_completed = int(quiz_completed) if quiz_completed is not None else 0
            
            # Check if they have completed the entire course (last module, last lesson, quiz completed)
            next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)
            if next_module_id is None and next_lesson_id is None and quiz_completed in [1, 2]:
                # They want to retake the course (as stated in the course_complete message)!
                # Reset progress in database
                reset_learner_data(user_id)
                # Clear user_data and continue to onboarding selection
                context.user_data.clear()
            else:
                module, lesson = get_module_lesson(current_module_id, current_lesson_id)
                if module and lesson:
                    welcome_back = get_text("welcome_back", lang, module_title=get_localized_field(module.get('title'), lang), lesson_title=get_localized_field(lesson.get('title'), lang))
                    await send_reply(
                        update,
                        welcome_back,
                        reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                    )
                    return
    
    # New learner — show language selection
    await send_reply(
        update,
        TRANSLATIONS["language_selection"]["en"],
        reply_markup=get_language_selection_buttons()
    )
    
    # Store that we're waiting for language selection
    context.user_data['awaiting_language_selection'] = True
 
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset learner progress completely."""
    user_id = update.effective_user.id
    
    reset_learner_data(user_id)
    
    context.user_data.clear()
    
    await send_reply(
        update,
        "🔄 Your progress has been reset successfully! Starting a new learning session...",
    )
    # Redirect to the start command directly to show onboarding
    await start(update, context)
 
async def community_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to join the Telegram discussion group."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    group_url = os.getenv("TELEGRAM_GROUP_URL", "https://t.me/YOUR_TELEGRAM_GROUP_LINK")
    
    prompt = {
        "en": f"🤜🤛 *Join The Brothers' Room Telegram Discussion Group!*\n\nContinue the conversation with other brothers, challenge harmful norms together, and collaborate on your learning journey.\n\nJoin here: {group_url}",
        "pcm": f"🤜🤛 *Join The Brothers' Room Telegram Group!*\n\nMake we continue this talk with other brothers, share experiences, and work together.\n\nJoin here: {group_url}",
        "ha": f"🤜🤛 *Shiga Rukunin Tattaunawa na Telegram na The Brothers' Room!*\n\nCi gaba da tattaunawa da sauran 'yan uwa, kalubalanci dabi'un da ba su da kyau tare.\n\nShiga nan: {group_url}",
        "yo": f"🤜🤛 *Darapọ mọ Egbe Ibaraẹnisọrọ Telegram ti The Brothers' Room!*\n\nTẹsiwaju ibaraẹnisọrọ pẹlu awọn arakunrin miiran, ati ifọwọsowọpọ fun rere.\n\nDarapọ mọ nibi: {group_url}",
        "ig": f"🤜🤛 *Soro na Otu Nkata Telegram nke The Brothers' Room!*\n\nGaa n'ihu na nkata gị na ụmụnne gị ndị ọzọ, kọọ ahụmịhe gị, ma rụọ ọrụ ọnụ.\n\nSoro na ebe a: {group_url}"
    }.get(lang, f"🤜🤛 *Join The Brothers' Room Telegram Discussion Group!*\n\nJoin here: {group_url}")
    
    button_label = {
        "en": "Join Telegram Group",
        "pcm": "Join Telegram Group",
        "ha": "Shiga Rukunin Telegram",
        "yo": "Darapọ mọ Egbe Telegram",
        "ig": "Soro na Otu Telegram"
    }.get(lang, "Join Telegram Group")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_label, url=group_url)]
    ])
    
    await send_reply(update, prompt, parse_mode="Markdown", reply_markup=keyboard)
 
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    await send_reply(
        update,
        get_text("help_menu", lang),
        reply_markup=get_help_keyboard_buttons(lang, user_id=user_id, context=context)
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show course outline."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    menu_text = get_text("menu_header", lang) + "\n\n"
    
    for i, module in enumerate(MODULES):
        menu_text += f"*Module {i+1}: {get_localized_field(module.get('title'), lang)}*\n"
        for lesson in module["lessons"]:
            menu_text += f" • {get_localized_field(lesson.get('title'), lang)}\n"
        menu_text += "\n"
    
    menu_text += get_text("menu_continue", lang)
    
    await send_reply(
        update,
        menu_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
    )

async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show learner progress."""
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)
    
    if not result or not result[0]:
        lang = 'en'
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result
    quiz_completed = int(quiz_completed) if quiz_completed is not None else 0

    if current_lesson_id == "start":
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    module, lesson = get_module_lesson(current_module_id, current_lesson_id)

    if module and lesson:
        module_index = 0
        for i, m in enumerate(MODULES):
            if m["module_id"] == current_module_id:
                module_index = i
                break

        total_modules = len(MODULES)
        
        progress_text = get_text(
            "progress_message", lang,
            module_num=module_index + 1,
            total_modules=total_modules,
            module_title=get_localized_field(module.get('title'), lang),
            lesson_title=get_localized_field(lesson.get('title'), lang)
        )
        
        # Calculate completed modules and badges
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT post_test_score FROM learners WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        post_test_score = row[0] if row else -1
        conn.close()
        
        completed_modules = []
        if post_test_score >= 0:
            completed_modules = [m["module_id"] for m in MODULES]
        else:
            for idx in range(module_index):
                completed_modules.append(MODULES[idx]["module_id"])
            if quiz_completed in [1, 2]:
                completed_modules.append(current_module_id)
                
        badges_text = ""
        for m_id in completed_modules:
            badge_name = TRANSLATIONS.get("badges", {}).get(m_id, {}).get(lang, f"[{m_id} Badge]")
            badges_text += f"\n- {badge_name}"
            
        if badges_text:
            progress_text += f"\n\nEarned Badges:{badges_text}"
        else:
            no_badges_msg = {
                "en": "No badges earned yet. Complete your first module quiz to earn a digital badge!",
                "pcm": "You never earn any badge yet. Finish your first module quiz make you get badge!",
                "ha": "Ba a sami lambobin yabo ba tukuna. Kammala gwajin modul na farko don samun lambar yabo!",
                "yo": "Ko si ami ti o ti gba sibẹsibẹ. Pari idanwo module akọkọ rẹ lati gba ami-ẹri!",
                "ig": "Enwebeghị badge ọ bụla ị nwetara. Mezue ajụjụ mbụ gị iji nweta badge!"
            }.get(lang, "No badges earned yet.")
            progress_text += f"\n\nEarned Badges:\n- {no_badges_msg}"
            
        await send_reply(
            update,
            progress_text,
            reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
        )
    else:
        await send_reply(
            update,
            get_text("error_generic", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
        )

async def send_quote_card(update: Update, context: ContextTypes.DEFAULT_TYPE, module_id: str, lang: str, user_id: int) -> None:
    module = get_module_by_id(module_id)
    if not module:
        return
    quote_cards_trans = TRANSLATIONS.get("quote_cards", {}).get(module_id, {})
    quote_text = quote_cards_trans.get(lang, quote_cards_trans.get("en", ""))
    
    quote_card_file = None
    if quote_text:
        try:
            quote_card_file = generate_quote_card_image(module_id, get_localized_field(module.get('title'), lang), quote_text, lang, user_id)
            
            import urllib.parse
            module_num = module_id.replace("module_", "")
            hashtags = HASHTAGS_MAPPING.get(module_id, "")
            raw_share_msg = get_text("quote_card_share_message", lang, module_num=module_num, quote=quote_text)
            if hashtags:
                raw_share_msg = f"{raw_share_msg}\n\n{hashtags}"
            encoded_msg = urllib.parse.quote(raw_share_msg)
            
            whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_msg}"
            twitter_url = f"https://twitter.com/intent/tweet?text={encoded_msg}"
            telegram_url = f"https://t.me/share/url?url=https://t.me/thebrotherroom_bot&text={encoded_msg}"
            
            share_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(get_text("share_whatsapp", lang), url=whatsapp_url),
                    InlineKeyboardButton(get_text("share_x", lang), url=twitter_url)
                ],
                [
                    InlineKeyboardButton(get_text("share_telegram", lang), url=telegram_url)
                ],
                [
                    InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
                    InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
                ]
            ])
            
            caption_text = {
                "en": "🖼 *Here is your Shareable Quote Card for Module {num}!* Save this to your gallery and share it to your WhatsApp Status, Facebook, or Instagram to inspire other young men.",
                "pcm": "🖼 *See your Shareable Quote Card for Module {num}!* Save am to your phone and share am on WhatsApp Status, Facebook, or Instagram make you inspire other men.",
                "ha": "🖼 *Ga Katin Tunaninku na Raba don Modul {num}!* Adana shi a cikin gallery dinku kuma ku raba shi a WhatsApp Status, Facebook, ko Instagram don zaburar da sauran maza.",
                "yo": "🖼 *Eyi ni Kaadi Iṣaro rẹ fun Modulu {num}!* Fi pamọ si ibi aworan rẹ ki o pin lori WhatsApp Status, Facebook, tabi Instagram lati fun awọn ọkunrin miiran ni iyanju.",
                "ig": "🖼 *Nke a bụ Kaadị Ntụgharị uche gị maka Modul {num}!* Chekwaa ya na gallery gị ma kọrọ ya na WhatsApp Status, Facebook, ma ọ bụ Instagram ka ị kpalie ndị ikom ọzọ."
            }.get(lang, "Here is your shareable quote card!").format(num=module_num)
            
            if hashtags:
                caption_text = f"{caption_text}\n\n{hashtags}"
            
            chat_msg = update.callback_query.message if update.callback_query else update.message
            with open(quote_card_file, "rb") as q_photo:
                await chat_msg.reply_photo(
                    photo=q_photo,
                    caption=caption_text,
                    reply_markup=share_keyboard,
                    parse_mode="Markdown"
                )
            context.user_data["awaiting_lessons_complete"] = module_id
        except Exception as e:
            logger.error(f"Error generating or sending quote card: {e}")
            await send_reply(
                update,
                get_text("lessons_complete", lang, module_title=get_localized_field(module.get('title'), lang)),
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )
        finally:
            if quote_card_file and os.path.exists(quote_card_file):
                try:
                    os.remove(quote_card_file)
                except Exception:
                    pass
    else:
        await send_reply(
            update,
            get_text("lessons_complete", lang, module_title=get_localized_field(module.get('title'), lang)),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )

async def prev_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /prev command, /back command, and Back button."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    result = get_learner_progress(user_id)
    if not result or not result[0]:
        await start(update, context)
        return
        
    current_module_id, current_lesson_id, quiz_completed, lang = result
    quiz_completed = int(quiz_completed) if quiz_completed is not None else 0
    
    # 1. State: Awaiting reflection response
    if "awaiting_reflection" in context.user_data:
        module_id = context.user_data.pop("awaiting_reflection")
        # Return to Quiz Correct screen (or Quiz screen depending on status)
        if quiz_completed == 1:
            await send_reply(
                update,
                get_text("quiz_correct", lang),
                reply_markup=get_quiz_continue_button(lang)
            )
        else:
            await send_reply(
                update,
                get_text("quiz_incorrect", lang, correct_answer=get_quiz_correct_answer(module_id)),
                reply_markup=get_quiz_retry_buttons(lang)
            )
        return
        
    # 2. State: Viewing Reflection Share Prompt (saved reflection screen)
    from db_manager import get_learner_reflection
    existing_ref = get_learner_reflection(user_id, current_module_id)
    if quiz_completed in [1, 2] and existing_ref is not None and "story_read" not in context.user_data:
        # Clear reflection from database to allow re-entering
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reflections WHERE user_id = %s AND module_id = %s", (user_id, current_module_id))
        conn.commit()
        conn.close()
        
        # Show Mirror Moment reflection prompt again
        ref_questions = TRANSLATIONS.get("reflections", {}).get("questions", {}).get(current_module_id, {})
        ref_question = ref_questions.get(lang, ref_questions.get("en", "Reflect on this module."))
        prompt_template = TRANSLATIONS.get("reflections", {}).get("prompt", {}).get(lang, "Mirror Moment:\n\n{question}")
        prompt_text = prompt_template.replace("{question}", ref_question)
        
        context.user_data["awaiting_reflection"] = current_module_id
        await send_reply(
            update,
            prompt_text,
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    # 2.5 State: Inside Quiz
    if quiz_completed == 0 and is_last_lesson_of_module(current_module_id, current_lesson_id) and "quiz_question_idx" in context.user_data:
        q_idx = context.user_data.get("quiz_question_idx", 0)
        if q_idx > 0:
            context.user_data["quiz_question_idx"] = q_idx - 1
            await quiz_command(update, context)
            return
        else:
            context.user_data.pop("quiz_question_idx", None)
            context.user_data.pop("quiz_errors", None)
            module = get_module_by_id(current_module_id)
            if module:
                await send_reply(
                    update,
                    get_text("lessons_complete", lang, module_title=get_localized_field(module.get('title'), lang)),
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id, show_quiz=True)
                )
            return

    # 3. State: Ready to take Quiz or viewing Quiz instructions
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and "awaiting_lessons_complete" not in context.user_data and "awaiting_quote_card" not in context.user_data:
        # Go back to Quote Card
        context.user_data["awaiting_lessons_complete"] = current_module_id
        await send_quote_card(update, context, current_module_id, lang, user_id)
        return

    # 4. State: Viewing Quote Card (awaiting lessons complete prompt)
    if "awaiting_lessons_complete" in context.user_data:
        context.user_data.pop("awaiting_lessons_complete", None)
        context.user_data["awaiting_quote_card"] = current_module_id
        module, lesson = get_module_lesson(current_module_id, current_lesson_id)
        if module and lesson:
            module_num = current_module_id.replace("module_", "")
            lesson_num = current_lesson_id.split("_")[-1]
            lesson_header = get_text("lesson_header", lang, module_num=module_num, module_title=get_localized_field(module.get('title'), lang), lesson_num=lesson_num, lesson_title=get_localized_field(lesson.get('title'), lang))
            await send_reply(
                update,
                f"{lesson_header}\n\n{get_localized_field(lesson.get('content'), lang)}",
                parse_mode="Markdown",
                reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
            )
        return

    # 5. State: Clear awaiting_quote_card when navigating back from last lesson
    if "awaiting_quote_card" in context.user_data:
        context.user_data.pop("awaiting_quote_card", None)

    # 6. State: Welcome screen / onboarding start
    if current_lesson_id == "start":
        context.user_data.pop("story_read", None)
        if current_module_id == "module_1":
            pre_score = get_pre_test_score(user_id)
            if pre_score >= 0:
                welcome_real = get_text("pre_test.completed", lang, score=pre_score)
                await send_reply(
                    update,
                    welcome_real,
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id),
                    parse_mode="Markdown"
                )
                return
        await start(update, context)
        return

    # 7. State: Viewing the Opening Story of Module X (X > 1)
    if "story_read" in context.user_data:
        story_mod_id = context.user_data.pop("story_read", None)
        prev_module = get_module_by_id(current_module_id)
        if prev_module:
            existing_ref = get_learner_reflection(user_id, current_module_id)
            if existing_ref:
                module_title = get_localized_field(prev_module.get('title'), lang)
                takeaway_val = existing_ref.strip()
                if len(takeaway_val) > 150:
                    takeaway_val = takeaway_val[:147] + "..."
                import urllib.parse
                share_msg_template = get_text("reflection_share_message", lang)
                share_text = share_msg_template.replace("{module_title}", module_title).replace("{takeaway}", takeaway_val)
                encoded_share = urllib.parse.quote(share_text)
                
                whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_share}"
                twitter_url = f"https://twitter.com/intent/tweet?text={encoded_share}"
                telegram_url = f"https://t.me/share/url?url=https://t.me/thebrotherroom_bot&text={encoded_share}"
                
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(get_text("share_whatsapp", lang), url=whatsapp_url),
                        InlineKeyboardButton(get_text("share_x", lang), url=twitter_url)
                    ],
                    [
                        InlineKeyboardButton(get_text("share_telegram", lang), url=telegram_url)
                    ],
                    [
                        InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
                        InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
                    ]
                ])
                await send_reply(
                    update,
                    get_text("reflection_share_prompt", lang),
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return

    # 8. State: standard lesson pagination back
    prev_module_id, prev_lesson_id = get_previous_lesson(current_module_id, current_lesson_id)
    if prev_module_id and prev_lesson_id:
        if prev_lesson_id == "start":
            # Stepping back to the Opening Story of current_module_id
            context.user_data["story_read"] = current_module_id
            update_learner_progress(user_id, current_module_id, "start")
            
            module = get_module_by_id(current_module_id)
            story_header = {
                "en": "📖 *Opening Story*",
                "pcm": "📖 *Opening Story*",
                "ha": "📖 *Labarin Budewa*",
                "yo": "📖 *Itan Ibẹrẹ*",
                "ig": "📖 *Akụkọ Mbido*"
            }.get(lang, "📖 Opening Story")
            
            next_button = InlineKeyboardMarkup([[
                InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
                InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
            ]])
            await send_reply(
                update,
                f"{story_header}\n\n{get_localized_field(module.get('opening_story'), lang)}",
                reply_markup=next_button,
                parse_mode="Markdown"
            )
        else:
            if prev_module_id != current_module_id:
                update_learner_progress(user_id, prev_module_id, prev_lesson_id, quiz_completed=1)
            else:
                update_learner_progress(user_id, prev_module_id, prev_lesson_id)
                
            module, lesson = get_module_lesson(prev_module_id, prev_lesson_id)
            if module and lesson:
                module_num = prev_module_id.replace("module_", "")
                lesson_num = prev_lesson_id.split("_")[-1]
                lesson_header = get_text("lesson_header", lang, module_num=module_num, module_title=get_localized_field(module.get('title'), lang), lesson_num=lesson_num, lesson_title=get_localized_field(lesson.get('title'), lang))
                
                if is_last_lesson_of_module(prev_module_id, prev_lesson_id):
                    context.user_data["awaiting_quote_card"] = prev_module_id
                else:
                    context.user_data.pop("awaiting_quote_card", None)
                    
                await send_reply(
                    update,
                    f"{lesson_header}\n\n{get_localized_field(lesson.get('content'), lang)}",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id)
                )
    else:
        await start(update, context)

async def next_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /next command and next button."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    # 1. Check if user is awaiting the lessons complete quiz prompt (meaning they just clicked Next on the quote card)
    if "awaiting_lessons_complete" in context.user_data:
        module_id = context.user_data.pop("awaiting_lessons_complete")
        module = get_module_by_id(module_id)
        if module:
            await send_reply(
                update,
                get_text("lessons_complete", lang, module_title=get_localized_field(module.get('title'), lang)),
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )
            return

    # 2. Check if user is awaiting the quote card (meaning they just finished Lesson 3 and clicked Next)
    if "awaiting_quote_card" in context.user_data:
        module_id = context.user_data.pop("awaiting_quote_card")
        await send_quote_card(update, context, module_id, lang, user_id)
        return
    
    
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        lang = 'en'
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result
    quiz_completed = int(quiz_completed) if quiz_completed is not None else 0

    # Block progression to next MODULE if quiz not attempted
    # (They must at least try the quiz — pass or fail doesn't matter)
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and quiz_completed == 0:
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_completed", lang, module_title=get_localized_field(module.get('title'), lang)),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id, show_quiz=True)
        )
        return

    # Check if they need to submit their personal reflection for the module they just completed
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and quiz_completed in [1, 2]:
        from db_manager import get_learner_reflection
        existing_ref = get_learner_reflection(user_id, current_module_id)
        if not existing_ref:
            # Prompt them for the private reflection first
            ref_questions = TRANSLATIONS.get("reflections", {}).get("questions", {}).get(current_module_id, {})
            ref_question = ref_questions.get(lang, ref_questions.get("en", "Reflect on this module."))
            
            prompt_template = TRANSLATIONS.get("reflections", {}).get("prompt", {}).get(lang, "Mirror Moment:\n\n{question}")
            prompt_text = prompt_template.replace("{question}", ref_question)
            
            context.user_data["awaiting_reflection"] = current_module_id
            
            await send_reply(
                update,
                prompt_text,
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )
            return

    # Determine the next lesson first without updating DB progress yet
    if current_lesson_id == "start":
        next_module_id = "module_1"
        next_lesson_id = "lesson_1_1"
    else:
        next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)

    if next_module_id and next_lesson_id:
        module, lesson = get_module_lesson(next_module_id, next_lesson_id)
        if module and lesson:
            module_num = next_module_id.replace("module_", "")
            lesson_num = next_lesson_id.split("_")[-1]

            # If this is the first lesson of a module, check if they need to read the opening story first
            if lesson_num == "1" and module.get("opening_story"):
                if context.user_data.get("story_read") != next_module_id:
                    context.user_data["story_read"] = next_module_id
                    
                    story_header = {
                        "en": "📖 *Opening Story*",
                        "pcm": "📖 *Opening Story*",
                        "ha": "📖 *Labarin Budewa*",
                        "yo": "📖 *Itan Ibẹrẹ*",
                        "ig": "📖 *Akụkọ Mbido*"
                    }.get(lang, "📖 Opening Story")
                    
                    # Next/Prev buttons for the story
                    next_button = InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
                        InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
                    ]])
                    
                    await send_reply(
                        update,
                        f"{story_header}\n\n{get_localized_field(module.get('opening_story'), lang)}",
                        reply_markup=next_button,
                        parse_mode="Markdown"
                    )
                    return
                else:
                    # User clicked Next, story is read, clean up flag and proceed to update progress & deliver lesson
                    context.user_data.pop("story_read", None)

            # Update DB progress now
            if current_lesson_id == "start":
                update_learner_progress(user_id, next_module_id, next_lesson_id)
            else:
                if next_module_id != current_module_id:
                    update_learner_progress(user_id, next_module_id, next_lesson_id, quiz_completed=0)
                else:
                    update_learner_progress(user_id, next_module_id, next_lesson_id)

            # If this is last lesson, set flag so next button triggers quote card (do before rendering so buttons helper knows)
            if is_last_lesson_of_module(next_module_id, next_lesson_id):
                context.user_data["awaiting_quote_card"] = next_module_id

            # Show lesson
            lesson_header = get_text(
                "lesson_header", lang, 
                module_num=module_num, 
                module_title=get_localized_field(module.get('title'), lang), 
                lesson_num=lesson_num, 
                lesson_title=get_localized_field(lesson.get('title'), lang)
            )
            
            # Check if this lesson has a video configured
            video_file_id = lesson.get("video")
            if video_file_id:
                try:
                    chat_msg = update.callback_query.message if update.callback_query else update.message
                    # Send native video with header as caption
                    await chat_msg.reply_video(
                        video=video_file_id,
                        caption=lesson_header,
                        parse_mode="Markdown"
                    )
                    # Send text contents as a follow-up with keyboard buttons
                    await send_reply(
                        update,
                        get_localized_field(lesson.get('content'), lang),
                        parse_mode="Markdown",
                        reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                    )
                except Exception as e:
                    logger.error(f"Error sending lesson video: {e}")
                    # Fallback to standard text layout on error
                    await send_reply(
                        update,
                        f"{lesson_header}\n\n{get_localized_field(lesson.get('content'), lang)}",
                        parse_mode="Markdown",
                        reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                    )
            else:
                # Standard text lesson
                await send_reply(
                    update,
                    f"{lesson_header}\n\n{get_localized_field(lesson.get('content'), lang)}",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
                )
        else:
            await send_reply(
                update,
                get_text("error_generic", lang),
                reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
            )
    else:
        # Course complete — Check if already graduated, otherwise route to scored post-test exam
        if is_user_graduated(user_id):
            await send_graduation_dashboard(update, context, lang, user_id)
        else:
            await send_post_test_welcome(update, context)

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show quiz for current module."""
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        lang = 'en'
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result
    quiz_completed = int(quiz_completed) if quiz_completed is not None else 0

    if quiz_completed == 1:
        await send_reply(
            update,
            get_text("quiz_already_completed", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return
        
    if not is_last_lesson_of_module(current_module_id, current_lesson_id):
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_ready", lang, module_title=get_localized_field(module.get('title'), lang)),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    module = get_module_by_id(current_module_id)

    if module and "quiz" in module:
        quizzes = module["quiz"]
        if not isinstance(quizzes, list):
            quizzes = [quizzes]
            
        # Re-start from 0 if accessing a new module's quiz, via message command (/quiz), or if idx is not set
        quiz_module = context.user_data.get("quiz_module_id")
        if quiz_module != current_module_id or "quiz_question_idx" not in context.user_data or update.message:
            context.user_data["quiz_question_idx"] = 0
            context.user_data["quiz_errors"] = 0
            context.user_data["quiz_module_id"] = current_module_id
            
        q_idx = context.user_data.get("quiz_question_idx", 0)
        if q_idx >= len(quizzes):
            q_idx = 0
            context.user_data["quiz_question_idx"] = 0
            
        quiz_data = quizzes[q_idx]
        options = get_localized_options(quiz_data.get("options"), lang)

        # Create quiz instructions and buttons
        options_text = "\n".join(options)
        question_with_options = f"{get_localized_field(quiz_data.get('question'), lang)}\n\n{options_text}"
        quiz_header = get_text("quiz_instructions", lang, module_title=get_localized_field(module.get('title'), lang), quiz_question=question_with_options)
        
        # Create answer buttons in a single row using short letters
        buttons = [[InlineKeyboardButton(f" {option[0]} ", callback_data=f"quiz|{current_module_id}|{q_idx}|{option[0]}") for option in options]]
        buttons.append([InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev")])
        reply_markup = InlineKeyboardMarkup(buttons)

        await send_reply(
            update,
            quiz_header,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        lang = get_language_preference(user_id)
        await send_reply(
            update,
            get_text("error_generic", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )

async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the learner's private reflections journal with social sharing features."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id and update.callback_query:
        user_id = update.callback_query.from_user.id
        
    lang = get_language_preference(user_id)
    reflections = get_all_learner_reflections(user_id)
    
    if not reflections:
        await send_reply(
            update,
            get_text("journal_empty", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id, context=context)
        )
        return
        
    journal_text = get_text("journal_header", lang)
    for module_id, ref_text in reflections:
        module = get_module_by_id(module_id)
        module_title = get_localized_field(module.get('title'), lang, module_id) if module else module_id
        journal_text += f"📙 *{module_title}*\n_{ref_text}_\n\n"
        
    # Check for custom exit pledge
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pledge_text FROM learners WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    pledge_text = row[0] if row else None
    if pledge_text:
        pledge_label = {
            "en": "My Personal Pledge",
            "pcm": "My Personal Pledge",
            "ha": "Alkawarina na Sirri",
            "yo": "Ipinnu Ara Eni Mi",
            "ig": "Nkwa m"
        }.get(lang, "My Personal Pledge")
        journal_text += f"🏆 *{pledge_label}*\n\"{pledge_text}\"\n\n"
        
    journal_text += get_text("journal_share_prompt", lang)
    
    # URL-encode the share message text
    import urllib.parse
    share_base = {
        "en": "I completed my personal reflections journal on positive masculinity. My pledge: ",
        "pcm": "I don finish my reflection journal for positive masculinity. My pledge: ",
        "ha": "Na kammala littafin tunanina a kan zama namiji na gari. Alkawarina: ",
        "yo": "Mo pari iwe akọsilẹ iṣaro mi lori okunrin rere. Ipinnu mi: ",
        "ig": "Agachasịrị m akwụkwọ ntụgharị uche m. Nkwa m: "
    }.get(lang, "My Pledge: ")
    
    share_val = pledge_text if pledge_text else "Join the movement to stand against GBV!"
    share_text = f"{share_base}\"{share_val}\"\nTake the course here: https://t.me/thebrotherroom_bot"
    encoded_share = urllib.parse.quote(share_text)
    
    whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_share}"
    twitter_url = f"https://twitter.com/intent/tweet?text={encoded_share}"
    telegram_url = f"https://t.me/share/url?url=https://t.me/thebrotherroom_bot&text={encoded_share}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(get_text("share_whatsapp", lang), url=whatsapp_url),
            InlineKeyboardButton(get_text("share_x", lang), url=twitter_url)
        ],
        [
            InlineKeyboardButton(get_text("share_telegram", lang), url=telegram_url)
        ],
        [
            InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_progress"),
            InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")
        ]
    ])
    
    await send_reply(
        update,
        journal_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change language preference."""
    await send_reply(
        update,
        TRANSLATIONS["language_change"]["en"],
        reply_markup=get_language_selection_buttons()
    )

# ============== CERTIFICATE AND ONBOARDING PRE-TEST & EXIT POST-TEST ENGINES ==============

async def send_pre_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_idx: int) -> None:
    """Send a specific pre-test question."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id and update.callback_query:
        user_id = update.callback_query.from_user.id
            
    lang = get_language_preference(user_id)
    
    questions = TRANSLATIONS["post_test"]["questions"]  # We reuse the exact same questions for pre-test baseline
    if question_idx < 0 or question_idx >= len(questions):
        # Done with all questions — grade the pre-test!
        await grade_pre_test(update, context)
        return
        
    question_data = questions[question_idx]
    q_base = f"📝 *Pre-Test Question {question_idx + 1}/5*\n\n" + question_data["question"].get(lang, question_data["question"]["en"])
    options = question_data["options"].get(lang, question_data["options"]["en"])
    
    # Format message to include the options inside the text body
    q_text = q_base + "\n\n" + "\n".join(options)
    
    # Store current question index in user_data
    context.user_data["pretest_current"] = question_idx
    
    # Build buttons in a single horizontal row: [ A ] [ B ] [ C ] [ D ]
    buttons = [[InlineKeyboardButton(f" {option[0]} ", callback_data=f"pretest_ans|{question_idx}|{option[0]}") for option in options]]
    keyboard = InlineKeyboardMarkup(buttons)
    
    await send_reply(update, q_text, reply_markup=keyboard, parse_mode="Markdown")

async def grade_pre_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculate pre-test score and transition to first lesson."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id and update.callback_query:
        user_id = update.callback_query.from_user.id
        
    lang = get_language_preference(user_id)
    
    # Retrieve answers from user_data
    answers = context.user_data.get("pretest_answers", {})
    questions = TRANSLATIONS["post_test"]["questions"]
    
    score = 0
    for idx, q_data in enumerate(questions):
        correct_ans = q_data["answer"]
        user_ans = answers.get(idx)
        if user_ans == correct_ans:
            score += 10 # 10 points per question
            
    # Save pre-test score to database
    update_pre_test_score(user_id, score)
    
    # Clear active test session variables
    context.user_data.pop("pretest_current", None)
    context.user_data.pop("pretest_answers", None)
    
    # Send completion card
    welcome_real = get_text("pre_test.completed", lang, score=score)
    
    await send_reply(
        update,
        welcome_real,
        reply_markup=get_main_menu_buttons(lang, user_id=user_id),
        parse_mode="Markdown"
    )

async def send_post_test_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the welcome message for the exit post-test."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    if is_user_graduated(user_id):
        await send_graduation_dashboard(update, context, lang, user_id)
        return
        
    welcome_text = get_text("post_test.welcome", lang)
    start_label = get_text("post_test.start_button", lang)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(start_label, callback_data="posttest_start")]
    ])
    
    await send_reply(update, welcome_text, reply_markup=keyboard)

async def send_post_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_idx: int) -> None:
    """Send a specific post-test question."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    questions = TRANSLATIONS["post_test"]["questions"]
    if question_idx < 0 or question_idx >= len(questions):
        # Done with all questions — grade the post-test!
        await grade_post_test(update, context)
        return
        
    question_data = questions[question_idx]
    q_base = f"📝 *Question {question_idx + 1}/5*\n\n" + question_data["question"].get(lang, question_data["question"]["en"])
    options = question_data["options"].get(lang, question_data["options"]["en"])
    
    # Format message to include the options inside the text body
    q_text = q_base + "\n\n" + "\n".join(options)
    
    # Store current question index in user_data
    context.user_data["posttest_current"] = question_idx
    
    # Build buttons in a single horizontal row: [ A ] [ B ] [ C ] [ D ]
    buttons = [[InlineKeyboardButton(f" {option[0]} ", callback_data=f"posttest_ans|{question_idx}|{option[0]}") for option in options]]
    keyboard = InlineKeyboardMarkup(buttons)
    
    await send_reply(update, q_text, reply_markup=keyboard, parse_mode="Markdown")

async def grade_post_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculate post-test score and determine pass/fail state."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    # Retrieve answers from user_data
    answers = context.user_data.get("posttest_answers", {})
    questions = TRANSLATIONS["post_test"]["questions"]
    
    score = 0
    for idx, q_data in enumerate(questions):
        correct_ans = q_data["answer"]
        user_ans = answers.get(idx)
        if user_ans == correct_ans:
            score += 10 # 10 points per question
            
    # Save score to database
    update_post_test_score(user_id, score)
    
    # Clear active test session variables
    context.user_data.pop("posttest_current", None)
    context.user_data.pop("posttest_answers", None)
    
    if score >= 35:
        # PASSED (score >= 35)
        passed_text = get_text("post_test.passed", lang, score=score)
        await send_reply(update, passed_text)
        # Put user into a state waiting for their preferred name
        context.user_data["awaiting_cert_name"] = True
    else:
        # FAILED
        failed_text = get_text("post_test.failed", lang, score=score)
        retry_label = get_text("post_test.retry_button", lang)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(retry_label, callback_data="posttest_start")]
        ])
        await send_reply(update, failed_text, reply_markup=keyboard)

def generate_quote_card_image(module_id, module_title, quote_text, lang, user_id):
    """Generate a highly aesthetic, premium, 1080x1080 shareable quote card for a module using Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    import os
    
    width, height = 1080, 1080
    
    # 1. Create linear gradient background
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    
    color1 = (15, 32, 67) # Premium Navy Blue
    color2 = (25, 25, 25) # Dark Charcoal
    for y in range(height):
        r = int(color1[0] + (color2[0] - color1[0]) * y / height)
        g = int(color1[1] + (color2[1] - color1[1]) * y / height)
        b = int(color1[2] + (color2[2] - color1[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        
    # 2. Draw elegant gold border line
    draw.rectangle([45, 45, width - 45, height - 45], outline=(219, 161, 71, 255), width=3)
    
    # 3. Load typography
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    fonts_dir = os.path.join(assets_dir, "fonts")
    try:
        font_header = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 26)
        font_subheader = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 20)
        font_quote = ImageFont.truetype(os.path.join(fonts_dir, "NotoSerif-Bold.ttf"), 38)
        font_quote_large = ImageFont.truetype(os.path.join(fonts_dir, "NotoSerif-Bold.ttf"), 140)
        font_footer = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 20)
    except Exception as e:
        logger.error(f"Quote card font loading error: {e}, falling back to defaults")
        font_header = font_subheader = font_quote = font_footer = ImageFont.load_default()
        font_quote_large = ImageFont.load_default()

    def get_text_size(text, font):
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            return font.getsize(text)

    # 4. Header & Subheader text
    header_text = "T H E   B R O T H E R S '   R O O M"
    draw.text((width // 2, 100), header_text, fill=(219, 161, 71, 255), font=font_header, anchor="mm")
    
    module_num = module_id.replace("module_", "")
    subheader_text = f"MODULE {module_num} : {module_title.upper()}"
    draw.text((width // 2, 145), subheader_text, fill=(245, 240, 230, 255), font=font_subheader, anchor="mm")
    
    # 5. Divider Line
    draw.line([(width // 2 - 250, 185), (width // 2 + 250, 185)], fill=(219, 161, 71, 255), width=2)
    
    # 6. Word-wrapping for quote text
    max_text_width = 800
    words = quote_text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        w, h = get_text_size(test_line, font_quote)
        if w <= max_text_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
        
    # Calculate text rendering Y coordinates
    line_heights = [get_text_size(line, font_quote)[1] for line in lines]
    line_spacing = 20
    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    
    area_center_y = 540
    start_y = area_center_y - (total_text_height // 2)
    
    # 7. Draw large background quote mark (open quote)
    draw.text((90, start_y - 80), "“", fill=(219, 161, 71, 35), font=font_quote_large)
    
    # 8. Draw each quote line centered horizontally
    current_y = start_y
    for i, line in enumerate(lines):
        line_w, line_h = get_text_size(line, font_quote)
        draw.text((width // 2, current_y + (line_h // 2)), line, fill=(245, 240, 230, 255), font=font_quote, anchor="mm")
        current_y += line_h + line_spacing
        
    # Draw closing quote mark at the end of the text
    draw.text((width - 180, current_y - 40), "”", fill=(219, 161, 71, 35), font=font_quote_large)
    
    # 9. Footer text
    footer_text = "Join the conversation: t.me/thebrotherroom_bot"
    draw.text((width // 2, 975), footer_text, fill=(219, 161, 71, 255), font=font_footer, anchor="mm")
    
    # Draw hashtags
    hashtags = HASHTAGS_MAPPING.get(module_id, "")
    if hashtags:
        draw.text((width // 2, 915), hashtags, fill=(219, 161, 71, 255), font=font_footer, anchor="mm")
    
    # 10. Paste Logos in top-right corner horizontally side-by-side (target height = ~45px)
    def paste_logo(filename, x, y, target_w, align_right=False):
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            try:
                logo = Image.open(path).convert("RGBA")
                aspect = logo.height / logo.width
                target_h = int(target_w * aspect)
                logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
                
                final_x = x - target_w if align_right else x
                final_y = y - (target_h // 2)
                img.paste(logo, (final_x, final_y), logo)
                return target_w, target_h
            except Exception as e:
                logger.error(f"Error pasting logo {filename}: {e}")
        return 0, 0
                
    yh_w, yh_h = paste_logo("youthhub_africa_logo.png", width - 75, 110, target_w=41, align_right=True)
    paste_logo("young_mens_foundation_logo.png", width - 75 - yh_w - 15, 110, target_w=54, align_right=True)
    
    # Save PNG image
    output_path = os.path.join(assets_dir, f"quote_card_{module_id}_{user_id}.png")
    final_img = img.convert("RGB")
    final_img.save(output_path, "PNG")
    return output_path

def generate_badge_image(module_id, badge_name, lang, user_id):
    """Generate a highly aesthetic, premium, game-style digital achievement badge using Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    import os
    
    width, height = 512, 512
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Colors
    c_gold = (219, 161, 71, 255)
    c_gold_glow = (219, 161, 71, 40)
    c_navy = (15, 32, 67, 255)
    c_navy_light = (28, 54, 105, 255)
    c_charcoal = (25, 25, 25, 255)
    c_cream = (245, 240, 230, 255)
    c_gray = (160, 160, 160, 255)
    
    # 1. Draw rounded rectangle card background with subtle gradient
    for i in range(12):
        offset = i
        r = int(c_navy[0] + (c_charcoal[0] - c_navy[0]) * i / 12)
        g = int(c_navy[1] + (c_charcoal[1] - c_navy[1]) * i / 12)
        b = int(c_navy[2] + (c_charcoal[2] - c_navy[2]) * i / 12)
        draw.rounded_rectangle(
            [15 + offset, 15 + offset, width - 15 - offset, height - 15 - offset],
            radius=35 - offset,
            fill=(r, g, b, 255)
        )
        
    # 2. Draw outer gold border
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=35, outline=c_gold, width=4)
    
    # 3. Draw inner gold accent line
    draw.rounded_rectangle([25, 25, width - 25, height - 25], radius=27, outline=(219, 161, 71, 80), width=1)
    
    # 4. Load typography
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    fonts_dir = os.path.join(assets_dir, "fonts")
    try:
        font_header = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 14)
        font_badge = ImageFont.truetype(os.path.join(fonts_dir, "NotoSerif-Bold.ttf"), 28)
        font_meta = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 16)
    except Exception as e:
        logger.error(f"Error loading badge fonts: {e}")
        font_header = font_badge = font_meta = ImageFont.load_default()
        
    # Header Text
    draw.text((width // 2, 45), "T H E   B R O T H E R S '   R O O M", fill=c_gold, font=font_header, anchor="mm")
    
    # 5. Draw Emblem / Shield
    shield_pts = [
        (256, 100), # Top point
        (376, 140), # Top right
        (376, 260), # Mid right
        (256, 340), # Bottom point
        (136, 260), # Mid left
        (136, 140)  # Top left
    ]
    
    # Draw glow behind shield
    draw.polygon(shield_pts, fill=c_gold_glow)
    # Draw gold border shield
    draw.polygon(shield_pts, outline=c_gold, width=5)
    # Inner dark fill shield
    inner_shield_pts = [
        (256, 108),
        (364, 144),
        (364, 254),
        (256, 328),
        (148, 254),
        (148, 144)
    ]
    draw.polygon(inner_shield_pts, fill=c_navy_light)
    draw.polygon(inner_shield_pts, outline=(219, 161, 71, 120), width=2)
    
    # 6. Draw central icon based on module_id
    cx, cy = 256, 215
    
    if module_id == "module_1": # Heart with Star
        draw.ellipse([cx - 26, cy - 25, cx, cy + 1], fill=c_gold)
        draw.ellipse([cx, cy - 25, cx + 26, cy + 1], fill=c_gold)
        draw.polygon([(cx - 25, cy - 6), (cx + 25, cy - 6), (cx, cy + 25)], fill=c_gold)
        draw.polygon([(cx, cy - 12), (cx + 3, cy - 3), (cx + 12, cy - 3), (cx + 5, cy + 2), (cx + 8, cy + 11), (cx, cy + 5), (cx - 8, cy + 11), (cx - 5, cy + 2), (cx - 12, cy - 3), (cx - 3, cy - 3)], fill=c_navy)
    elif module_id == "module_2": # Laurel / Diamond
        diamond_pts = [(cx, cy - 30), (cx + 30, cy), (cx, cy + 30), (cx - 30, cy)]
        draw.polygon(diamond_pts, fill=c_gold)
        draw.line([(cx, cy - 30), (cx, cy + 30)], fill=c_navy, width=2)
        draw.line([(cx - 30, cy), (cx + 30, cy)], fill=c_navy, width=2)
    elif module_id == "module_3": # Crown
        crown_pts = [
            (cx - 30, cy + 25),
            (cx + 30, cy + 25),
            (cx + 30, cy - 10),
            (cx + 15, cy + 5),
            (cx, cy - 20),
            (cx - 15, cy + 5),
            (cx - 30, cy - 10)
        ]
        draw.polygon(crown_pts, fill=c_gold)
        draw.rectangle([cx - 32, cy + 25, cx + 32, cy + 30], fill=c_gold)
        draw.ellipse([cx - 32, cy - 15, cx - 28, cy - 11], fill=c_cream)
        draw.ellipse([cx - 2, cy - 25, cx + 2, cy - 21], fill=c_cream)
        draw.ellipse([cx + 28, cy - 15, cx + 32, cy - 11], fill=c_cream)
    elif module_id in ["module_4", "module_5"]: # Lightning
        bolt_pts = [
            (cx + 5, cy - 35),
            (cx + 20, cy - 5),
            (cx + 2, cy - 5),
            (cx + 12, cy + 30),
            (cx - 15, cy + 5),
            (cx + 2, cy + 5)
        ]
        draw.polygon(bolt_pts, fill=c_gold)
    elif module_id == "module_6": # Interlinked Rings
        draw.ellipse([cx - 30, cy - 18, cx - 2, cy + 10], outline=c_gold, width=6)
        draw.ellipse([cx + 2, cy - 18, cx + 30, cy + 10], outline=c_gold, width=6)
    elif module_id == "module_7": # Star inside shield
        star_pts = []
        for i in range(10):
            r_val = 32 if i % 2 == 0 else 14
            import math
            angle = i * math.pi / 5 - math.pi / 2
            star_pts.append((cx + r_val * math.cos(angle), cy + r_val * math.sin(angle)))
        draw.polygon(star_pts, fill=c_gold)
    elif module_id == "module_8": # Compass Rose
        draw.polygon([(cx, cy - 35), (cx + 8, cy - 8), (cx + 35, cy), (cx + 8, cy + 8), (cx, cy + 35), (cx - 8, cy + 8), (cx - 35, cy), (cx - 8, cy - 8)], fill=c_gold)
        draw.polygon([(cx, cy - 35), (cx, cy), (cx + 8, cy - 8)], fill=c_cream)
        draw.polygon([(cx + 35, cy), (cx, cy), (cx + 8, cy + 8)], fill=c_cream)
        draw.polygon([(cx, cy + 35), (cx, cy), (cx - 8, cy + 8)], fill=c_cream)
        draw.polygon([(cx - 35, cy), (cx, cy), (cx - 8, cy - 8)], fill=c_cream)
    elif module_id == "module_9": # Megaphone
        draw.polygon([(cx - 20, cy - 10), (cx + 15, cy - 25), (cx + 15, cy + 15), (cx - 20, cy + 5)], fill=c_gold)
        draw.polygon([(cx - 15, cy + 2), (cx - 15, cy + 22), (cx - 7, cy + 22), (cx - 7, cy + 2)], fill=c_gold)
        draw.arc([cx + 5, cy - 35, cx + 35, cy + 25], start=-60, end=60, fill=c_gold, width=4)
        draw.arc([cx + 15, cy - 45, cx + 45, cy + 35], start=-60, end=60, fill=c_gold, width=4)
    elif module_id == "module_10": # Network nodes
        node_positions = [
            (cx, cy - 25),
            (cx - 28, cy),
            (cx + 28, cy),
            (cx - 15, cy + 28),
            (cx + 15, cy + 28)
        ]
        for i in range(len(node_positions)):
            for j in range(i + 1, len(node_positions)):
                draw.line([node_positions[i], node_positions[j]], fill=c_gold, width=2)
        for pos in node_positions:
            draw.ellipse([pos[0] - 8, pos[1] - 8, pos[0] + 8, pos[1] + 8], fill=c_gold, outline=c_navy, width=1)
    elif module_id == "module_11": # Scales of justice
        draw.line([(cx, cy - 30), (cx, cy + 30)], fill=c_gold, width=4)
        draw.line([(cx - 20, cy + 30), (cx + 20, cy + 30)], fill=c_gold, width=4)
        draw.line([(cx - 30, cy - 20), (cx + 30, cy - 20)], fill=c_gold, width=4)
        draw.line([(cx - 30, cy - 20), (cx - 40, cy + 5)], fill=c_gold, width=2)
        draw.line([(cx - 30, cy - 20), (cx - 20, cy + 5)], fill=c_gold, width=2)
        draw.arc([cx - 43, cy + 5, cx - 17, cy + 20], start=0, end=180, fill=c_gold, width=3)
        draw.line([(cx + 30, cy - 20), (cx + 20, cy + 5)], fill=c_gold, width=2)
        draw.line([(cx + 30, cy - 20), (cx + 40, cy + 5)], fill=c_gold, width=2)
        draw.arc([cx + 17, cy + 5, cx + 43, cy + 20], start=0, end=180, fill=c_gold, width=3)
    else: # Fallback star
        star_pts = []
        for i in range(10):
            r_val = 35 if i % 2 == 0 else 15
            import math
            angle = i * math.pi / 5 - math.pi / 2
            star_pts.append((cx + r_val * math.cos(angle), cy + r_val * math.sin(angle)))
        draw.polygon(star_pts, fill=c_gold)

    # 7. Draw badge name and completion details
    badge_name_clean = badge_name.replace("[", "").replace("]", "").upper()
    draw.text((width // 2, 395), badge_name_clean, fill=c_cream, font=font_badge, anchor="mm")
    
    module_num = module_id.replace("module_", "")
    meta_text = {
        "en": f"MODULE {module_num} COMPLETION",
        "pcm": f"MODULE {module_num} COMPLETE",
        "ha": f"KAMMALA MODUL {module_num}",
        "yo": f"MODULU {module_num} APARI",
        "ig": f"NGACHA MODUL {module_num}"
    }.get(lang, f"MODULE {module_num} COMPLETION")
    draw.text((width // 2, 440), meta_text, fill=c_gold, font=font_meta, anchor="mm")
    
    # Elegant double dots under meta_text
    draw.ellipse([cx - 20, 465, cx - 16, 469], fill=c_gold)
    draw.ellipse([cx - 2, 464, cx + 2, 468], fill=c_gold)
    draw.ellipse([cx + 16, 465, cx + 20, 469], fill=c_gold)
    
    output_path = os.path.join(assets_dir, f"badge_{module_id}_{user_id}.png")
    img.save(output_path, "PNG")
    return output_path

def generate_certificate_image(name, date_str, user_id):
    """Generate a highly aesthetic, premium, high-resolution certificate of completion using Pillow."""
    import hashlib
    from PIL import Image, ImageDraw, ImageFont
    
    width, height = 2000, 1418
    
    # Base background (Cream color matching the sample)
    img = Image.new("RGB", (width, height), (232, 226, 213))
    draw = ImageDraw.Draw(img)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    
    # Helper to paste transparent PNG dynamically scaled
    def paste_transparent_pro(filename, x, y, target_width=None, align_right=False, align_bottom=False):
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            try:
                logo = Image.open(path).convert("RGBA")
                if target_width:
                    aspect = logo.height / logo.width
                    target_height = int(target_width * aspect)
                    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
                else:
                    target_width, target_height = logo.size
                
                final_x = x - target_width if align_right else x
                final_y = y - target_height if align_bottom else y
                img.paste(logo, (final_x, final_y), logo)
                return target_width, target_height
            except Exception as e:
                logger.error(f"Error pasting {filename}: {e}")
        return 0, 0

    # Paste corners
    paste_transparent_pro("top_right_corner.png", 2000, 0, target_width=180, align_right=True)
    paste_transparent_pro("bottom_left_corner.png", 0, 1418, target_width=250, align_bottom=True)
    
    # Paste top-left Ford Foundation logo (scale to width = 240)
    paste_transparent_pro("ford_logo.png", 120, 100, target_width=240)
    
    # Paste top-right organization logos side-by-side
    # 1. YouthHub Africa logo on the right (target height = 130px, aspect is ~1.10, so width is ~118px)
    yh_w, yh_h = paste_transparent_pro("youthhub_africa_logo.png", 2000 - 120, 95, target_width=118, align_right=True)
    # 2. Young Men's Foundation logo to the left (target height = 130px, aspect is ~0.84, so width is ~155px)
    ym_w, ym_h = paste_transparent_pro("young_mens_foundation_logo.png", 2000 - 120 - yh_w - 20, 95, target_width=155, align_right=True)

    # Outer navy border line
    draw.rectangle([40, 40, width - 40, height - 40], outline=(15, 32, 67), width=6)
    # Inner gold border line
    draw.rectangle([52, 52, width - 52, height - 52], outline=(219, 161, 71), width=2)

    # Typography and Colors
    c_green = (44, 145, 70)      # Forest green matching sample
    c_gold = (219, 161, 71)      # Gold lines and badge
    c_charcoal = (30, 30, 30)    # Sleek dark grey text
    c_gray = (100, 100, 100)     # Muted grey text
    c_navy = (15, 32, 67)        # Deep navy headers and course title

    # Load fonts
    fonts_dir = os.path.join(assets_dir, "fonts")
    try:
        font_cert = ImageFont.truetype(os.path.join(fonts_dir, "NotoSerif-Bold.ttf"), 110)
        font_of_completion = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 46)
        font_presented = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 32)
        font_name = ImageFont.truetype(os.path.join(fonts_dir, "DancingScript-Bold.ttf"), 105)
        font_desc = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 26)
        font_course = ImageFont.truetype(os.path.join(fonts_dir, "NotoSerif-Bold.ttf"), 36)
        font_sig_name = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 32)
        font_sig_title = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 26)
        font_footer = ImageFont.truetype(os.path.join(fonts_dir, "Outfit-Regular.ttf"), 20)
    except Exception as e:
        logger.error(f"Font loading error: {e}, falling back to defaults")
        try:
            font_cert = ImageFont.truetype("Arial.ttf", 110)
            font_of_completion = ImageFont.truetype("Arial.ttf", 46)
            font_presented = ImageFont.truetype("Arial.ttf", 32)
            font_name = ImageFont.truetype("Times New Roman.ttf", 105)
            font_desc = ImageFont.truetype("Arial.ttf", 26)
            font_course = ImageFont.truetype("Times New Roman.ttf", 36)
            font_sig_name = ImageFont.truetype("Arial.ttf", 32)
            font_sig_title = ImageFont.truetype("Arial.ttf", 26)
            font_footer = ImageFont.truetype("Arial.ttf", 20)
        except Exception:
            font_cert = font_of_completion = font_presented = font_name = font_desc = font_course = font_sig_name = font_sig_title = font_footer = ImageFont.load_default()

    # Draw Text Elements (Center horizontal = 1000)
    # Header Section
    draw.text((1000, 390), "CERTIFICATE", fill=c_green, font=font_cert, anchor="mm")
    draw.text((1000, 470), "OF COMPLETION", fill=c_charcoal, font=font_of_completion, anchor="mm")
    
    # Recipient Section
    draw.text((1000, 570), "Presented to", fill=c_gray, font=font_presented, anchor="mm")
    draw.text((1000, 700), name.title(), fill=c_navy, font=font_name, anchor="mm")
    
    # Description Section
    draw.text((1000, 840), "for successfully completing the 6-week conversational course on", fill=c_gray, font=font_desc, anchor="mm")
    draw.text((1000, 900), "Positive Masculinity & Gender-Based Violence (GBV) Prevention", fill=c_navy, font=font_course, anchor="mm")
    
    # Bottom Left - Rotimi Olawale (Executive Director) Signatory
    sig_x = 480
    # Paste actual transparent signature of Rotimi Olawale centered at sig_x, and placed nicely ABOVE the gold line (align_bottom=True)
    paste_transparent_pro("rotimi_signature.png", sig_x - 170, 1140, target_width=340, align_bottom=True)
    
    draw.line([(sig_x - 180, 1145), (sig_x + 180, 1145)], fill=c_gold, width=3)
    draw.text((sig_x, 1190), "Rotimi Olawale", fill=c_charcoal, font=font_sig_name, anchor="mm")
    draw.text((sig_x, 1235), "Executive Director", fill=c_green, font=font_sig_title, anchor="mm")
    
    # Bottom Right - Date of Issuance
    date_x = 2000 - 480
    # Line removed as requested by the user!
    draw.text((date_x, 1190), date_str, fill=c_charcoal, font=font_sig_name, anchor="mm")
    draw.text((date_x, 1235), "DATE OF ISSUANCE", fill=c_gray, font=font_sig_title, anchor="mm")
    
    # Verification ID at the very bottom
    v_hash = hashlib.sha256(f"TBR-{user_id}-{date_str}".encode()).hexdigest()[:12].upper()
    draw.text((1000, 1345), f"VERIFICATION ID: TBR-{v_hash}", fill=c_gray, font=font_footer, anchor="mm")
    
    output_path = os.path.join(assets_dir, f"certificate_{user_id}.png")
    img.save(output_path)
    return output_path

async def handle_graduation_and_certificate(update: Update, context: ContextTypes.DEFAULT_TYPE, pledge: str, cert_name: str = None) -> None:
    """Acknowledge pledge, compile dynamic certificate, broadcast to community, and send final graduation card."""
    import datetime
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    processing_msg = {
        "en": "Generating your official Certificate of Completion... 🎓 Please hold on a moment, brother.",
        "pcm": "We dey compile your official Certificate of Completion now... 🎓 Abeg wait small, brother.",
        "ha": "Ana hada Takardar Shaidarku ta kammala karatu... 🎓 Dan Allah jira kadan.",
        "yo": "A n ṣẹda Iwe-ẹri Ipari osise rẹ... 🎓 Jọwọ duro diẹ, arakunrin.",
        "ig": "Anyị na-akwadebe Asambodo Mmezu gị nke ọha... 🎓 Biko nwee ndidi, nwanne m."
    }.get(lang, "Generating your Certificate...")
    
    await update.message.reply_text(processing_msg)
    
    learner_name = cert_name if cert_name else update.effective_user.full_name
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    certificate_file = generate_certificate_image(learner_name, current_date, user_id)
    
    group_url = os.getenv("TELEGRAM_GROUP_URL", "https://t.me/YOUR_TELEGRAM_GROUP_LINK")
    congrats_text = get_text("course_complete", lang).replace("https://t.me/YOUR_TELEGRAM_GROUP_LINK", group_url)
    
    try:
        import urllib.parse
        share_msg = get_text("share_message", lang)
        encoded_msg = urllib.parse.quote(share_msg)
        
        whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_msg}"
        twitter_url = f"https://twitter.com/intent/tweet?text={encoded_msg}"
        telegram_url = f"https://t.me/share/url?url=https://t.me/thebrotherroom_bot&text={encoded_msg}"
        
        share_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(get_text("share_whatsapp", lang), url=whatsapp_url),
                InlineKeyboardButton(get_text("share_x", lang), url=twitter_url)
            ],
            [
                InlineKeyboardButton(get_text("share_telegram", lang), url=telegram_url)
            ],
            [
                InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")
            ]
        ])
        
        with open(certificate_file, "rb") as cert:
            await update.message.reply_photo(
                photo=cert,
                caption=congrats_text + get_text("certificate_share_tip", lang),
                reply_markup=share_keyboard,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error sending certificate photo: {e}")
        await update.message.reply_text(congrats_text)
    finally:
        if os.path.exists(certificate_file):
            try:
                os.remove(certificate_file)
            except Exception:
                pass
                
    community_chat_id_raw = os.getenv("COMMUNITY_CHAT_ID")
    if community_chat_id_raw:
        try:
            val = community_chat_id_raw.strip()
            if (val.startswith("-") and val[1:].isdigit()) or val.isdigit():
                community_chat_id = int(val)
            else:
                community_chat_id = val
        except Exception:
            community_chat_id = community_chat_id_raw
        try:
            broadcast_text = (
                f"🎓 *New Champion Certified!* 🌟\n\n"
                f"Let's celebrate *{learner_name}* who just graduated from *The Brothers' Room*!\n\n"
                f"📝 *Their Personal Pledge:*\n"
                f"_{pledge}_\n\n"
                f"Welcome our new Peer Champion! 🤜🤛"
            )
            await context.application.bot.send_message(
                chat_id=community_chat_id,
                text=broadcast_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error broadcasting pledge to community: {e}")

LAST_BACKUP_TIME = 0

async def reminder_scheduler(application: Application) -> None:
    """Persistent background asynchronous worker for scheduling nudges and weekly reminders."""
    logger.info("Background reminder scheduler started successfully!")
    global LAST_BACKUP_TIME
    while True:
        try:
            # 0. Run database backup once every 24 hours
            current_time = time.time()
            if current_time - LAST_BACKUP_TIME >= 86400:
                success, details = backup_sqlite_db()
                if success:
                    logger.info(f"Automated database backup created successfully: {details}")
                else:
                    logger.error(f"Automated database backup failed: {details}")
                LAST_BACKUP_TIME = current_time
                
            # Initialize Sunday checks for any active learners that don't have them scheduled
            init_sunday_checks()

            # 1. Weekly Pledge Reminders (Clean, Emoji-Free)
            pending_reminders = get_pending_reminders()
            for user_id, reminder_type, pledge_text, reminders_sent, lang in pending_reminders:
                try:
                    reminder_msg = {
                        "en": f"Your Personal Weekly Pledge Reminder\n\nHey brother! Here is the pledge you made to stand against GBV and lead by example:\n\n\"{pledge_text}\"\n\nKeep living as a champion in your family and community!",
                        "pcm": f"Your Personal Weekly Pledge Reminder\n\nHow far brother! See the pledge wey you make to stand against GBV and lead by example:\n\n\"{pledge_text}\"\n\nKeep living as champion inside your family and community!",
                        "ha": f"Tunasar Alkawarinka na Mako-mako\n\nSannu brother! Ga alkawarin da ka dauka don yaki da GBV:\n\n\"{pledge_text}\"\n\nCi gaba da zama abin koyi ga danginka da al'ummarku!",
                        "yo": f"Iranti Ipolongo Ara Eni ti Ose\n\nE ku abo brother! Eyi ni ipinnu ti o se lati duro lodi si GBV:\n\n\"{pledge_text}\"\n\nTesiwaju lati je apeere rere!",
                        "ig": f"Ihe Ncheta Nkwa Gi Nke Izu\n\nKedu nwanne m! Nke a bu nkwa i kweri na i ga-eguzo megide GBV:\n\n\"{pledge_text}\"\n\nGaa n'ihu na-adi ndu di ka ochichich!"
                    }.get(lang, f"Your Pledge Reminder:\n\n\"{pledge_text}\"")
                    
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=reminder_msg,
                        parse_mode="Markdown"
                    )
                    update_reminder_sent(user_id, reminder_type)
                    logger.info(f"Dispatched weekly pledge reminder to user {user_id} ({reminders_sent+1}/4)")
                except Exception as e:
                    logger.error(f"Failed to send weekly reminder to {user_id}: {e}")

            # 2. Inactive Learner Nudges (4 Days) (Clean, Emoji-Free)
            inactive_learners = get_inactive_learners()
            for user_id, current_module, current_lesson, lang in inactive_learners:
                try:
                    nudge_msg = {
                        "en": "Hey brother! Just checking in. I'm here to guide you through the course whenever you are ready. Let's keep learning! Click Next below to continue.",
                        "pcm": "How far brother! Just checking in. I dey here to guide you through the course. Let's continue! Click Next make we continue.",
                        "ha": "Sannu brother! Ina duba ku. Ina nan don ci gaba da taimaka muku. Danna Gida a kasa don ci gaba.",
                        "yo": "Hey brother! Mo kan n sayewo re. Mo wa nibi lati to o si eko naa. Te Atele ni isale lati tesiwaju.",
                        "ig": "Kedu nwanne m! Naani ilele gi. A no m ebe a iji duzie gi na akwukwo. Kpachapu Ozo n'okpuru ebe a iji gaa n'ihu."
                    }.get(lang, "Hey brother! Just checking in. Let's keep learning! Click Next below to continue.")
                    
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=nudge_msg
                    )
                    # Resets activity timestamp by updating current progress state
                    update_learner_progress(user_id, current_module, current_lesson)
                    logger.info(f"Dispatched inactive learner nudge to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send inactive nudge to {user_id}: {e}")

            # 3. Sunday Oga Checks (Clean, Emoji-Free)
            import datetime
            cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
            due_sunday_checks = get_due_sunday_checks()
            for user_id, lang, last_activity in due_sunday_checks:
                try:
                    # Parse last_activity
                    if isinstance(last_activity, str):
                        try:
                            val = last_activity.split(".")[0]
                            dt = datetime.datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            dt = cutoff - datetime.timedelta(days=1)
                    else:
                        dt = last_activity
                        
                    is_active = (dt >= cutoff)
                    
                    if is_active:
                        oga_msg = TRANSLATIONS.get("oga_check", {}).get("active", {}).get(
                            lang, "Hello brother! It's time for our Sunday Check-in. We are celebrating your progress this week. You are doing great work on your learning journey. Keep going!"
                        )
                    else:
                        oga_msg = TRANSLATIONS.get("oga_check", {}).get("inactive", {}).get(
                            lang, "Hello brother! It's Sunday Check-in. We noticed you've been a bit quiet lately. Remember, this journey to positive masculinity is a support space for you. Whenever you are ready to continue, just click Next below."
                        )
                        
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=oga_msg
                    )
                    update_sunday_check_sent(user_id)
                    logger.info(f"Dispatched Sunday check-in to user {user_id} (active={is_active})")
                except Exception as e:
                    logger.error(f"Failed to send Sunday check-in to {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error in background reminder worker loop: {e}")
        
        # Check every 1 hour
        await asyncio.sleep(3600)

# ============== ADMINISTRATIVE DASHBOARD & EXPORTER ==============

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin dashboard command."""
    user_id = update.effective_user.id
    
    # Secure admin authentication
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    
    if admin_ids and user_id not in admin_ids:
        await send_reply(update, "You are not authorized to view the Admin Dashboard.")
        return
        
    dashboard_text = (
        "*The Brothers' Room - Admin Dashboard*\n\n"
        "Welcome to your management command center. Use the controls below to monitor active learners, view baseline shift analytics, and identify Peer Facilitators.\n\n"
        "Select an action:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Peer Facilitator Leaderboard", callback_data="admin_leaderboard")],
        [InlineKeyboardButton("Program Impact Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton("Export Progress Report (CSV)", callback_data="admin_export_csv")],
        [InlineKeyboardButton("Reset Participant Progress", callback_data="admin_reset_prompt")]
    ])
    
    await send_reply(update, dashboard_text, reply_markup=keyboard, parse_mode="Markdown")

async def show_admin_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the Peer Facilitator Leaderboard ranking top learners."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    leaderboard = get_engagement_leaderboard()
    
    if not leaderboard:
        # Secure back button
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="cmd_admin")]])
        await send_reply(update, "📭 No learners registered in the database yet.", reply_markup=keyboard)
        return
        
    text = "🏆 *Peer Facilitator Leaderboard (Engagement Rankings)*\n\n"
    text += "Ranks are computed based on: *Progress (10 pts)* + *First-Attempt Quizzes (5 pts)* + *AI Inquiries (3 pts)*.\n\n"
    
    for idx, item in enumerate(leaderboard[:10]):
        badge = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else "👤"
        text += f"{badge} *Rank {idx + 1}:* {item['full_name']} (ID: `{item['user_id']}`)\n"
        text += f"   • Engagement Score: *{item['engagement_score']}*\n"
        text += f"   • Modules Completed: {item['modules_completed']}/{len(MODULES)}\n"
        text += f"   • First-Attempt Quizzes: {item['first_attempt_quizzes']}\n"
        text += f"   • AI Assistant Queries: {item['ai_questions_count']}\n"
        if item['post_test_score'] >= 0:
            text += f"   • Exit Exam Score: *{item['post_test_score']}/50* (GRADUATED)\n"
        text += "\n"
        
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="cmd_admin")]
    ])
    
    await send_reply(update, text, reply_markup=keyboard, parse_mode="Markdown")

async def show_admin_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the Program Impact Analytics report for funders."""
    user_id = update.effective_user.id
    
    # Secure admin authentication
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    if admin_ids and user_id not in admin_ids:
        await send_reply(update, "You are not authorized to view the Admin Dashboard.")
        return
        
    from db_manager import get_program_impact_analytics
    stats = get_program_impact_analytics()
    
    text = (
        "*Program Impact Analytics Report*\n\n"
        f"Total Enrolled Learners: {stats['total_learners']}\n"
        f"Learners Started Pre-Test: {stats['pre_test_count']}\n"
        f"Average Pre-Test Score: {stats['avg_pre_test']}/50\n\n"
        f"Course Graduates: {stats['graduates_count']}\n"
        f"Average Post-Test Score: {stats['avg_post_test']}/50\n\n"
        f"Average Knowledge Shift: {stats['avg_shift']}/50\n\n"
        "This report aggregates active baseline shift and program engagement to provide evidence for funders and partner organizations."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Back to Admin Menu", callback_data="cmd_admin")]
    ])
    
    await send_reply(update, text, reply_markup=keyboard, parse_mode="Markdown")

async def export_admin_csv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a detailed CSV progress report and send as a Telegram document."""
    user_id = update.effective_user.id
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, full_name, email, state, current_module_id, current_lesson_id, quiz_completed, 
               language_preference, enrollment_date, post_test_score, pledge_text,
               ai_questions_count, first_attempt_quizzes
        FROM learners
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="cmd_admin")]])
        await send_reply(update, "📭 No data available to export.", reply_markup=keyboard)
        return
        
    csv_file_path = "assets/learner_progress_report.csv"
    
    with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "User ID", "Full Name", "Email Address", "State", "Current Module", "Current Lesson", "Quiz Status", 
            "Language Preference", "Enrollment Date", "Post-Test Score", "Personal Pledge",
            "AI Questions Asked", "First-Attempt Quizzes Passed"
        ])
        for row in rows:
            # Format rows nicely (replace None with empty string or 'N/A')
            formatted_row = [x if x is not None else "" for x in row]
            writer.writerow(formatted_row)
            
    try:
        chat_msg = update.callback_query.message if update.callback_query else update.message
        with open(csv_file_path, "rb") as csv_file:
            await chat_msg.reply_document(
                document=csv_file,
                filename="learner_progress_report.csv",
                caption="📁 *The Brothers' Room - Learner Progress CSV Report*\n\nHere is your full data export.",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error sending CSV report: {e}")
        await send_reply(update, "❌ Failed to send the CSV report file.")
    finally:
        if os.path.exists(csv_file_path):
            try:
                os.remove(csv_file_path)
            except Exception:
                pass

# ==================================================================

async def accessibility_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle voice response accessibility for visually impaired users."""
    user_id = update.effective_user.id
    current_status = get_voice_responses(user_id)
    new_status = not current_status
    set_voice_responses(user_id, new_status)
    
    status_text = {
        "en": f"Accessibility Voice Replies have been {'ENABLED' if new_status else 'DISABLED'}. The bot will now {'send audio voice notes alongside text messages' if new_status else 'only send text messages'}.",
        "pcm": f"Accessibility Voice Replies don {'START' if new_status else 'STOP'}. Bot go now {'dey send voice notes as well' if new_status else 'dey send text only'}.",
        "ha": f"Accessibility Voice Replies an {'KUNNA' if new_status else 'KASHE'}.",
        "yo": f"Accessibility Voice Replies ti jẹ́ {'MÚ KÚN' if new_status else 'MÚ KÚRÒ'}.",
        "ig": f"Accessibility Voice Replies abanyela {'MERE' if new_status else 'PAA'}."
    }
    lang = get_language_preference(user_id)
    response_msg = status_text.get(lang, status_text["en"])
    
    await send_reply(update, response_msg)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages by transcribing them via Whisper and piping to text handler."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    try:
        # Download user voice note (.ogg format)
        voice_file = await update.message.voice.get_file()
        ogg_path = f"assets/voice_input_{user_id}.ogg"
        await voice_file.download_to_drive(ogg_path)
        
        # Transcribe using Whisper
        transcription = transcribe_voice(ogg_path)
        
        # Clean up temporary audio file
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            
        if transcription:
            # Automatically enable voice replies since they are interacting via voice!
            is_newly_enabled = False
            if not get_voice_responses(user_id):
                set_voice_responses(user_id, True)
                is_newly_enabled = True
                
            # Display transcribed text back for clarity
            if is_newly_enabled:
                heard_msg = {
                    "en": f"🎤 *I heard:* \"{transcription}\"\n\n🔊 _Voice replies have been automatically enabled for you!_",
                    "pcm": f"🎤 *Wetin I hear:* \"{transcription}\"\n\n🔊 _Voice replies don start automatically for you!_",
                    "ha": f"🎤 *Abin da na ji:* \"{transcription}\"\n\n🔊 _An kunna amsoshin murya ta atomatik a gare ku!_",
                    "yo": f"🎤 *Ohun tí mo gbọ́:* \"{transcription}\"\n\n🔊 _A ti mu ohun ṣiṣẹ laifọwọyi fun ọ!_",
                    "ig": f"🎤 *Ihe m nụrụ:* \"{transcription}\"\n\n🔊 _Agbanyere olu azịza na-akpaghị aka maka gị!_"
                }.get(lang, f"🎤 *I heard:* \"{transcription}\"")
            else:
                heard_msg = {
                    "en": f"🎤 *I heard:* \"{transcription}\"",
                    "pcm": f"🎤 *Wetin I hear:* \"{transcription}\"",
                    "ha": f"🎤 *Abin da na ji:* \"{transcription}\"",
                    "yo": f"🎤 *Ohun tí mo gbọ́:* \"{transcription}\"",
                    "ig": f"🎤 *Ihe m nụrụ:* \"{transcription}\""
                }.get(lang, f"🎤 *I heard:* \"{transcription}\"")
            
            await update.message.reply_text(heard_msg, parse_mode="Markdown")
            
            # Pipe transcription text straight into handle_message handler
            update.message.text = transcription
            await handle_message(update, context)
        else:
            fail_msg = {
                "en": "Sorry, I couldn't understand that voice message. Please try speaking clearly or typing instead.",
                "pcm": "Sorry, I no hear that voice message well. Abeg try talk clear or type am.",
                "ha": "Yi hakuri, ban gane wannan sakon murya ba. Don Allah yi magana a fili ko rubuta maimakon haka.",
                "yo": "Binu, mi o loye ifiranṣẹ ohun yẹn. Jọwọ sọrọ ni kedere tabi kọ ọ dipo.",
                "ig": "Ndo, aghotaghị m ozi olu ahụ. Biko gbalịa kwuo okwu nke ọma ma ọ bụ pịaji."
            }.get(lang, "Sorry, I couldn't understand that voice message.")
            await update.message.reply_text(fail_msg)
            
    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await update.message.reply_text(get_text("error_generic", lang))

# ============== BUTTON CALLBACK HANDLERS ==============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    if update.effective_chat and update.effective_chat.type != "private":
        return
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Language selection
    if data.startswith("lang_"):
        lang_code = data.split("_")[1]
        
        # Check if user is already enrolled (prior to calling enroll_learner)
        progress = get_learner_progress(user_id)
        is_new_user = progress is None
        
        # Save temporary lang code to db by enrolling them (lets commands use correct language)
        full_name = query.from_user.full_name if query.from_user else None
        enroll_learner(user_id, lang_code, full_name=full_name)
        
        from db_manager import is_learner_registered
        if not is_learner_registered(user_id) or context.user_data.get('awaiting_language_selection'):
            context.user_data.pop('awaiting_language_selection', None)
            
            # Start profile registration onboarding
            context.user_data['awaiting_full_name'] = True
            
            ask_name_text = get_text("ask_full_name", lang_code)
            await query.edit_message_text(
                ask_name_text,
                parse_mode="Markdown"
            )
        else:
            # Mid-course language change
            success_msg = get_text("language_changed", lang_code)
            await query.edit_message_text(
                success_msg,
                reply_markup=get_main_menu_buttons(lang_code, user_id=user_id)
            )
        return
    
    # Command buttons
    lang = get_language_preference(user_id)

    # Intercept pre-test callbacks
    if data == "pretest_start":
        await query.delete_message()
        context.user_data["pretest_answers"] = {}
        context.user_data["pretest_current"] = 0
        await send_pre_test_question(update, context, 0)
        return
        
    elif data.startswith("pretest_ans|"):
        parts = data.split("|")
        q_idx = int(parts[1])
        selected_choice = parts[2]
        
        if "pretest_answers" not in context.user_data:
            context.user_data["pretest_answers"] = {}
        context.user_data["pretest_answers"][q_idx] = selected_choice
        
        await query.delete_message()
        await send_pre_test_question(update, context, q_idx + 1)
        return

    # Intercept post-test callbacks
    if data == "posttest_start":
        if is_user_graduated(user_id):
            await query.delete_message()
            await send_graduation_dashboard(update, context, lang, user_id)
            return
            
        await query.delete_message()
        context.user_data["posttest_answers"] = {}
        context.user_data["posttest_current"] = 0
        await send_post_test_question(update, context, 0)
        return
        
    elif data.startswith("posttest_ans|"):
        parts = data.split("|")
        q_idx = int(parts[1])
        selected_choice = parts[2]
        
        if "posttest_answers" not in context.user_data:
            context.user_data["posttest_answers"] = {}
        context.user_data["posttest_answers"][q_idx] = selected_choice
        
        await query.delete_message()
        await send_post_test_question(update, context, q_idx + 1)
        return
        
    elif data == "cmd_admin":
        await query.delete_message()
        await admin_command(update, context)
        return
        
    elif data == "admin_leaderboard":
        await query.delete_message()
        await show_admin_leaderboard(update, context)
        return
        
    elif data == "admin_analytics":
        await query.delete_message()
        await show_admin_analytics(update, context)
        return
        
    elif data == "admin_export_csv":
        await query.delete_message()
        await export_admin_csv(update, context)
        return
        
    elif data == "admin_reset_prompt":
        await query.delete_message()
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
        if admin_ids and user_id not in admin_ids:
            await query.message.reply_text("You are not authorized to perform this action.")
            return
            
        participant_list = ""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, full_name FROM learners ORDER BY last_activity DESC LIMIT 30")
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                participant_list = "\n\n*Registered Participants (Recent Activity):*\n"
                for row in rows:
                    p_id, p_name = row
                    name_str = p_name if p_name else "Anonymous User"
                    participant_list += f"• {name_str} — ID: `{p_id}`\n"
            else:
                participant_list = "\n\n_(No registered participants found)_"
        except Exception as e:
            logger.error(f"Error fetching learners for reset list: {e}")
            participant_list = "\n\n_(Could not fetch participant list)_"

        context.user_data["awaiting_reset_user_id"] = True
        await query.message.reply_text(
            "🔄 *Reset Participant Progress*\n\n"
            "Please type or paste the Telegram User ID of the participant you want to reset. This will completely delete their progress, reflections, and reminders so they can start over."
            f"{participant_list}",
            parse_mode="Markdown"
        )
        return
    
    if data == "cmd_next":
        await query.delete_message()
        # Call next_lesson_handler via update object
        await next_lesson_handler(update, context)
        
    elif data == "cmd_prev":
        await query.delete_message()
        # Call prev_lesson_handler via update object
        await prev_lesson_handler(update, context)
        
    elif data == "cmd_start":
        await query.delete_message()
        await start(update, context)
    
    elif data == "cmd_quiz":
        await query.delete_message()
        await quiz_command(update, context)
    
    elif data == "cmd_progress":
        await query.delete_message()
        await progress_command(update, context)
    
    elif data == "cmd_menu":
        await query.delete_message()
        await menu_command(update, context)
        
    elif data == "cmd_journal":
        await query.delete_message()
        await journal_command(update, context)
    
    elif data == "cmd_language":
        await query.edit_message_text(
            TRANSLATIONS["language_change"]["en"],
            reply_markup=get_language_selection_buttons()
        )
    
    elif data == "cmd_help":
        await query.delete_message()
        await help_command(update, context)
        
    elif data == "cmd_accessibility":
        current_status = get_voice_responses(user_id)
        new_status = not current_status
        set_voice_responses(user_id, new_status)
        
        status_text = {
            "en": f"Voice Replies {'ENABLED' if new_status else 'DISABLED'}! 🔊",
            "pcm": f"Voice Replies {'START' if new_status else 'STOP'}! 🔊",
            "ha": f"An {'KUNNA' if new_status else 'KASHE'} Murya! 🔊",
            "yo": f"Ohun ti jẹ́ {'MÚ KÚN' if new_status else 'MÚ KÚRÒ'}! 🔊",
            "ig": f"Olu abanyela {'MERE' if new_status else 'PAA'}! 🔊"
        }
        toast_msg = status_text.get(lang, status_text["en"])
        
        await query.answer(text=toast_msg, show_alert=True)
        
        message_text = query.message.text or ""
        is_help_menu = "help_menu" in TRANSLATIONS and any(
            h_text[:30] in message_text for h_text in TRANSLATIONS["help_menu"].values() if h_text
        )
        
        if is_help_menu:
            reply_markup = get_help_keyboard_buttons(lang, user_id=user_id, context=context)
        else:
            reply_markup = get_main_menu_buttons(lang, user_id=user_id, context=context)
            
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        
        if new_status:
            voice_status_full = {
                "en": "Accessibility Voice Replies have been ENABLED. The bot will now send audio voice notes alongside text messages.",
                "pcm": "Accessibility Voice Replies don START. Bot go now dey send voice notes as well.",
                "ha": "Accessibility Voice Replies an KUNNA.",
                "yo": "Accessibility Voice Replies ti jẹ́ MÚ KÚN.",
                "ig": "Accessibility Voice Replies abanyela MERE."
            }.get(lang, "Accessibility Voice Replies have been ENABLED.")
            
            output_filename = f"assets/voice_reply_{user_id}.ogg"
            success = synthesize_speech(voice_status_full, output_filename)
            if success:
                try:
                    with open(output_filename, "rb") as voice_file:
                        await query.message.reply_voice(voice=voice_file)
                except Exception as e:
                    logger.error(f"Error sending synthesized voice activation reply: {e}")
                finally:
                    if os.path.exists(output_filename):
                        try:
                            os.remove(output_filename)
                        except Exception:
                            pass
        return
    elif data == "quiz_retry":
        context.user_data["quiz_question_idx"] = 0
        context.user_data["quiz_errors"] = 0
        await query.delete_message()
        await quiz_command(update, context)
        
    # Quiz next question transition
    elif data.startswith("quiz_q|"):
        parts = data.split("|")
        module_id = parts[1]
        next_q_idx = int(parts[2])
        context.user_data["quiz_question_idx"] = next_q_idx
        await query.delete_message()
        await quiz_command(update, context)
    
    # Quiz skip/move forward
    elif data == "quiz_skip":
        await query.delete_message()
        context.user_data.pop("quiz_question_idx", None)
        context.user_data.pop("quiz_errors", None)
        context.user_data.pop("quiz_module_id", None)
        
        # Deliver badge on skip as they are completing the module
        progress = get_learner_progress(user_id)
        if progress and progress[0]:
            current_module_id = progress[0]
            badge_path = None
            try:
                badge_name = TRANSLATIONS.get("badges", {}).get(current_module_id, {}).get(lang, "Badge")
                badge_path = generate_badge_image(current_module_id, badge_name, lang, user_id)
            except Exception as e:
                logger.error(f"Error generating badge image on skip: {e}")
                
            badge_unlocked_text = {
                "en": "🏆 *Badge Unlocked!* You've earned the digital badge for this module.",
                "pcm": "🏆 *Badge Unlocked!* You don earn the digital badge for this module.",
                "ha": "🏆 *An Buɗe Lambar Yabo!* Kun sami lambar yabo ta dijital don wannan modul.",
                "yo": "🏆 *Ami-ẹri Ti Wa Ni Titi!* O ti gba ami-ẹri oni-nọmba fun modulu yii.",
                "ig": "🏆 *Emepeela Badge!* Ị nwetawo badge dijitalụ maka modul a."
            }.get(lang, "🏆 Badge Unlocked!")
            
            if badge_path and os.path.exists(badge_path):
                try:
                    with open(badge_path, "rb") as bf:
                        await query.message.reply_photo(
                            photo=bf,
                            caption=badge_unlocked_text,
                            parse_mode="Markdown"
                        )
                except Exception as e:
                    logger.error(f"Error sending skip badge photo: {e}")
                finally:
                    try:
                        os.remove(badge_path)
                    except Exception:
                        pass
        await next_lesson_handler(update, context)
    
    # Quiz answer
    elif data.startswith("quiz|"):
        parts = data.split("|")
        if len(parts) < 3:
            await query.edit_message_text(get_text("error_generic", lang))
            return
        
        module_id = parts[1]
        if len(parts) == 4:
            q_idx = int(parts[2])
            selected_answer = parts[3]
        else:
            q_idx = context.user_data.get("quiz_question_idx", 0)
            selected_answer = parts[2]
            
        await process_quiz_answer(update, context, module_id, q_idx, selected_answer)
        return
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages and transcribed voice inputs."""
    user_message = update.message.text
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)

    # Intercept full name onboarding step
    if context.user_data.get("awaiting_full_name"):
        context.user_data.pop("awaiting_full_name", None)
        full_name = user_message.strip()
        update_full_name(user_id, full_name)
        
        # Move to email onboarding step
        context.user_data["awaiting_email"] = True
        ask_email_text = get_text("ask_email", lang)
        await send_reply(update, ask_email_text)
        return

    # Intercept email onboarding step
    if context.user_data.get("awaiting_email"):
        context.user_data.pop("awaiting_email", None)
        email = user_message.strip()
        from db_manager import update_email
        update_email(user_id, email)
        
        # Move to state onboarding step
        context.user_data["awaiting_state"] = True
        ask_state_text = get_text("ask_state", lang)
        await send_reply(update, ask_state_text)
        return

    # Intercept state onboarding step
    if context.user_data.get("awaiting_state"):
        context.user_data.pop("awaiting_state", None)
        state_val = user_message.strip()
        from db_manager import update_state
        update_state(user_id, state_val)
        
        # Onboarding registration complete! Now show welcome message and prompt Pre-Test
        welcome_text = get_text("start_welcome", lang, course_title=get_localized_field(COURSE_TITLE, lang, "Young Men Against Gender Based Violence"), course_description=get_localized_field(COURSE_DESCRIPTION, lang, ""))
        pretest_button_label = {
            "en": "✍️ Take Pre-Test Quiz",
            "pcm": "✍️ Start Pre-Test Quiz",
            "ha": "✍️ Fara Jarrabawar Farko",
            "yo": "✍️ Bẹrẹ Idanwo Àkọ́kọ́",
            "ig": "✍️ Malite Ule Mbụ"
        }.get(lang, "✍️ Take Pre-Test Quiz")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(pretest_button_label, callback_data="pretest_start")]
        ])
        await send_reply(
            update,
            welcome_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Intercept private reflections
    if context.user_data.get("awaiting_reflection"):
        module_id = context.user_data.pop("awaiting_reflection", None)
        from db_manager import save_reflection
        save_reflection(user_id, module_id, user_message)
        
        # Build interactive social sharing prompt for this specific reflection
        module = get_module_by_id(module_id)
        module_title = get_localized_field(module.get('title'), lang, module_id) if module else module_id
        
        # Truncate user reflection to keep it safe for X and WhatsApp url lengths
        takeaway_val = user_message.strip()
        if len(takeaway_val) > 150:
            takeaway_val = takeaway_val[:147] + "..."
            
        import urllib.parse
        share_msg_template = get_text("reflection_share_message", lang)
        share_text = share_msg_template.replace("{module_title}", module_title).replace("{takeaway}", takeaway_val)
        encoded_share = urllib.parse.quote(share_text)
        
        whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_share}"
        twitter_url = f"https://twitter.com/intent/tweet?text={encoded_share}"
        telegram_url = f"https://t.me/share/url?url=https://t.me/thebrotherroom_bot&text={encoded_share}"
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(get_text("share_whatsapp", lang), url=whatsapp_url),
                InlineKeyboardButton(get_text("share_x", lang), url=twitter_url)
            ],
            [
                InlineKeyboardButton(get_text("share_telegram", lang), url=telegram_url)
            ],
            [
                InlineKeyboardButton(get_command_button("back", lang), callback_data="cmd_prev"),
                InlineKeyboardButton(get_text("continue_next_lesson", lang), callback_data="cmd_next")
            ]
        ])
        
        saved_msg = get_text("reflection_share_prompt", lang)
        await send_reply(
            update,
            saved_msg,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Intercept preferred name for certificate
    if context.user_data.get("awaiting_cert_name"):
        context.user_data.pop("awaiting_cert_name", None)
        cert_name = user_message.strip()
        context.user_data["cert_name"] = cert_name
        update_full_name(user_id, cert_name)  # Save to DB permanently!
        
        # Move to pledge writing step
        context.user_data["awaiting_pledge"] = True
        pledge_prompt = get_text("post_test.pledge_prompt", lang, name=cert_name)
        await send_reply(update, pledge_prompt)
        return

    # Intercept personal pledges for graduations
    if context.user_data.get("awaiting_pledge"):
        context.user_data.pop("awaiting_pledge", None)
        save_pledge(user_id, user_message)
        cert_name = context.user_data.pop("cert_name", update.effective_user.full_name)
        await handle_graduation_and_certificate(update, context, pledge=user_message, cert_name=cert_name)
        return

    # Intercept admin request to reset a user's progress
    if context.user_data.get("awaiting_reset_user_id"):
        context.user_data.pop("awaiting_reset_user_id", None)
        
        # Double check sender is admin
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
        if admin_ids and user_id not in admin_ids:
            await send_reply(update, "You are not authorized to perform this action.")
            return
            
        target_id_str = user_message.strip()
        if not target_id_str.isdigit():
            await send_reply(
                update,
                "❌ Invalid User ID. Please make sure you enter a purely numeric Telegram User ID.\n\n"
                "Use /admin to open the dashboard again."
            )
            return
            
        target_id = int(target_id_str)
        
        # Perform DB reset
        try:
            reset_learner_data(target_id)
            
            # Send confirmation to admin
            await send_reply(
                update,
                f"✅ *Success!* Progress for user `{target_id}` has been completely reset.\n\n"
                f"They have been removed from progress tracking, and their reflections and reminders have been deleted.",
                parse_mode="Markdown"
            )
            
            # Try to notify the participant
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="🔄 *Your progress has been reset by an administrator.*\n\n"
                         "You can start the course again from the beginning by sending /start!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.info(f"Could not send reset notification to user {target_id}: {e}")
                
        except Exception as e:
            logger.error(f"Error resetting user progress: {e}")
            await send_reply(update, "❌ An error occurred while resetting progress in the database.")
            
        return

    # --- 1. Intercept option letter inputs for active tests or quizzes ---
    option_letter = extract_option_letter(user_message)
    if option_letter:
        # Check active pretest
        if "pretest_current" in context.user_data:
            q_idx = context.user_data["pretest_current"]
            questions = TRANSLATIONS["post_test"]["questions"]
            if q_idx < len(questions):
                options = questions[q_idx]["options"].get(lang, questions[q_idx]["options"]["en"])
                valid_letters = [opt[0].upper() for opt in options]
                if option_letter in valid_letters:
                    if "pretest_answers" not in context.user_data:
                        context.user_data["pretest_answers"] = {}
                    context.user_data["pretest_answers"][q_idx] = option_letter
                    await send_pre_test_question(update, context, q_idx + 1)
                    return

        # Check active posttest
        elif "posttest_current" in context.user_data:
            q_idx = context.user_data["posttest_current"]
            questions = TRANSLATIONS["post_test"]["questions"]
            if q_idx < len(questions):
                options = questions[q_idx]["options"].get(lang, questions[q_idx]["options"]["en"])
                valid_letters = [opt[0].upper() for opt in options]
                if option_letter in valid_letters:
                    if "posttest_answers" not in context.user_data:
                        context.user_data["posttest_answers"] = {}
                    context.user_data["posttest_answers"][q_idx] = option_letter
                    await send_post_test_question(update, context, q_idx + 1)
                    return

        # Check active module quiz
        elif "quiz_module_id" in context.user_data and "quiz_question_idx" in context.user_data:
            module_id = context.user_data["quiz_module_id"]
            q_idx = context.user_data["quiz_question_idx"]
            module = get_module_by_id(module_id)
            if module and "quiz" in module:
                quizzes = module["quiz"]
                if not isinstance(quizzes, list):
                    quizzes = [quizzes]
                if q_idx < len(quizzes):
                    options = quizzes[q_idx]["options"]
                    valid_letters = [opt[0].upper() for opt in options]
                    if option_letter in valid_letters:
                        await process_quiz_answer(update, context, module_id, q_idx, option_letter)
                        return

    # --- 2. Intercept module selection/jumping commands ---
    module_num = extract_module_number(user_message)
    if module_num is not None:
        await jump_to_module(update, context, module_num - 1)
        return

    # --- 3. Check for general navigation and menu command keywords ---
    msg_clean = user_message.lower().strip().rstrip('.')
    
    # Navigation mapping
    if msg_clean in ["next", "continue", "go next", "move on", "forward", "tẹsiwaju", "ci gaba", "gaa n'ihu"]:
        await next_lesson_handler(update, context)
        return
    if msg_clean in ["back", "previous", "go back", "prev", "padà", "koma baya", "gaa n'azụ"]:
        await prev_lesson_handler(update, context)
        return
        
    # Main commands mapping
    if msg_clean in ["menu", "outline", "modules", "course menu", "show menu", "mẹnu", "tsarin darussa", "ihere"]:
        await menu_command(update, context)
        return
    if msg_clean in ["help", "info", "assistance", "support", "get help", "iranwọ", "taimako", "enyemaka"]:
        await help_command(update, context)
        return
    if msg_clean in ["progress", "score", "status", "my progress", "how am I doing", "itẹsiwaju", "ci gaba na koyo", "ọganihu"]:
        await progress_command(update, context)
        return
    if msg_clean in ["journal", "reflections", "my journal", "notes", "diary", "akọsilẹ", "tunanina", "akwụkwọ m"]:
        await journal_command(update, context)
        return
    if msg_clean in ["quiz", "test", "question", "take quiz", "start quiz", "jarrabawa", "idanwo", "ule"]:
        await quiz_command(update, context)
        return
    if msg_clean in ["start", "restart", "begin"]:
        await start(update, context)
        return

    # Increment active AI queries for the peer facilitator calculations
    increment_ai_questions(user_id)
    
    # Use AI to answer questions dynamically
    result = get_learner_progress(user_id)
    full_course_text = json.dumps(COURSE_CONTENT)

    if result and result[0]:
        current_module_id, current_lesson_id, _, _ = result
        module, lesson = get_module_lesson(current_module_id, current_lesson_id)
        if module and lesson:
            current_context = f"Current Module: {get_localized_field(module.get('title'), lang)}. Current Lesson: {get_localized_field(lesson.get('title'), lang)}. Content: {get_localized_field(lesson.get('content'), lang)}"
            context_for_openai = f"Course Overview: {full_course_text}\n\nUser is currently in: {current_context}"
        else:
            context_for_openai = full_course_text
    else:
        context_for_openai = full_course_text

    response = get_openai_response(user_message, context_for_openai, language=lang)
    await send_reply(
        update,
        response,
        reply_markup=get_main_menu_buttons(lang, user_id=user_id)
    )

async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming video/file from admin and reply with the file_id."""
    user_id = update.effective_user.id
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    
    if admin_ids and user_id not in admin_ids:
        return

    file_id = None
    file_type = "File"
    
    if update.message.video:
        file_id = update.message.video.file_id
        file_type = "Video"
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            file_id = doc.file_id
            file_type = "Video Document"
        elif doc.file_name and doc.file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.3gp')):
            file_id = doc.file_id
            file_type = "Video File"
            
    if file_id:
        await update.message.reply_text(
            f"📹 *{file_type} Detected!*\n\n"
            f"Here is the Telegram `file_id`:\n"
            f"`{file_id}`\n\n"
            f"Save this string into the video field of the corresponding lesson in `course_content.json`.",
            parse_mode="Markdown"
        )

async def post_init(application: Application) -> None:
    """Set bot commands in Telegram's menu."""
    from telegram import BotCommandScopeAllPrivateChats, BotCommandScopeDefault
    
    commands = [
        BotCommand("start", "Begin or restart the course"),
        BotCommand("next", "Go to the next lesson"),
        BotCommand("prev", "Go back to the previous lesson"),
        BotCommand("quiz", "Take the quiz for the current module"),
        BotCommand("progress", "Check your current module and lesson"),
        BotCommand("menu", "View the full course outline"),
        BotCommand("language", "Change your language preference"),
        BotCommand("journal", "View your Reflections Journal"),
        # BotCommand("accessibility", "Toggle voice replies for visual accessibility"),
        BotCommand("admin", "Admin Dashboard & Peer Facilitator Leaderboard"),
        BotCommand("community", "Join our Telegram Group"),
        BotCommand("reset", "Reset progress completely and restart"),
        BotCommand("help", "Get help and list commands")
    ]
    
    # Set commands only for private 1-on-1 chats
    await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
    
    # Delete default commands so they don't show up in group chats
    try:
        await application.bot.delete_my_commands(scope=BotCommandScopeDefault())
    except Exception as e:
        logger.error(f"Error clearing default command scope: {e}")
        
    # Start background reminder and nudge scheduler clock
    asyncio.create_task(reminder_scheduler(application))

def main() -> None:
    """Start the bot."""
    init_db()

    # Start the web analytics dashboard in a background daemon thread
    try:
        import threading
        from dashboard import run_dashboard_server
        threading.Thread(target=run_dashboard_server, daemon=True).start()
        logger.info("Background facilitator dashboard web server started successfully!")
    except Exception as e:
        logger.error(f"Failed to start dashboard web server: {e}")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(token).post_init(post_init).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("reset", reset_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("community", community_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("menu", menu_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("progress", progress_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("next", next_lesson_handler, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("prev", prev_lesson_handler, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("back", prev_lesson_handler, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("quiz", quiz_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("language", language_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("journal", journal_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("accessibility", accessibility_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("admin", admin_command, filters=filters.ChatType.PRIVATE))

    # Message, voice, and button handlers
    application.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL) & filters.ChatType.PRIVATE, handle_video_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
