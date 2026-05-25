import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from db_manager import (
    init_db, enroll_learner, get_learner_progress, update_learner_progress, 
    update_quiz_status, update_language_preference, get_language_preference,
    get_connection
)
from openai_utils import get_openai_response 

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

# ============== TRANSLATION HELPER FUNCTIONS ==============

def get_text(key, lang='en', **kwargs):
    """Get translated text with variable substitution."""
    try:
        text = TRANSLATIONS.get(key, {}).get(lang, TRANSLATIONS.get(key, {}).get('en', ''))
        # Replace variables in curly braces
        for var, value in kwargs.items():
            text = text.replace('{' + var + '}', str(value))
        return text
    except Exception as e:
        logger.error(f"Translation error for key {key}: {e}")
        return "Error"

def get_command_button(button_name, lang='en'):
    """Get translated command button text."""
    return get_text(f"command_buttons.{button_name}", lang)

# ============== INLINE BUTTON HELPER ==============

def get_main_menu_buttons(lang='en'):
    """Get context-aware main menu buttons."""
    buttons = [
        [InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next")],
        [InlineKeyboardButton(get_command_button("quiz", lang), callback_data="cmd_quiz")],
        [InlineKeyboardButton(get_command_button("progress", lang), callback_data="cmd_progress"),
         InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")],
        [InlineKeyboardButton(get_command_button("language", lang), callback_data="cmd_language"),
         InlineKeyboardButton(get_command_button("help", lang), callback_data="cmd_help")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_help_keyboard_buttons(lang='en'):
    """Get keyboard buttons specifically for the help menu containing all commands."""
    start_label = {
        "en": "Start / Restart",
        "pcm": "Start / Restart",
        "ha": "Fara / Sake Fara",
        "yo": "Bẹrẹ / Tun Bẹrẹ",
        "ig": "Malite / Malite Ọzọ"
    }.get(lang, "Start / Restart")

    buttons = [
        [InlineKeyboardButton(start_label, callback_data="cmd_start")],
        [InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next"),
         InlineKeyboardButton(get_command_button("quiz", lang), callback_data="cmd_quiz")],
        [InlineKeyboardButton(get_command_button("progress", lang), callback_data="cmd_progress"),
         InlineKeyboardButton(get_command_button("menu", lang), callback_data="cmd_menu")],
        [InlineKeyboardButton(get_command_button("language", lang), callback_data="cmd_language"),
         InlineKeyboardButton(get_command_button("help", lang), callback_data="cmd_help")]
    ]
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

# ============== REPLY HELPER ==============

async def send_reply(update: Update, text, reply_markup=None, parse_mode=None):
    """Send a reply that works for both commands and callback queries."""
    if update.callback_query:
        # Called from a button click — send new message via chat
        await update.callback_query.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

# ============== COMMAND HANDLERS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - show language selection or welcome back returning learners."""
    user_id = update.effective_user.id
    
    # Check if learner already has progress
    result = get_learner_progress(user_id)
    
    if result and result[0]:
        # Returning learner — welcome them back
        current_module_id, current_lesson_id, quiz_completed, lang = result
        
        # Check if they have completed the entire course (last module, last lesson, quiz completed)
        next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)
        if next_module_id is None and next_lesson_id is None and quiz_completed in [1, 2]:
            # They want to retake the course (as stated in the course_complete message)!
            # Reset progress in database
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM learners WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            # Clear user_data and continue to onboarding selection
            context.user_data.clear()
        else:
            module, lesson = get_module_lesson(current_module_id, current_lesson_id)
            if module and lesson:
                welcome_back = get_text("welcome_back", lang, module_title=module['title'], lesson_title=lesson['title'])
                await send_reply(
                    update,
                    welcome_back,
                    reply_markup=get_main_menu_buttons(lang)
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
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM learners WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()
    
    context.user_data.clear()
    
    await send_reply(
        update,
        "🔄 Your progress has been reset successfully! Starting a new learning session...",
    )
    # Redirect to the start command directly to show onboarding
    await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    await send_reply(
        update,
        get_text("help_menu", lang),
        reply_markup=get_help_keyboard_buttons(lang)
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show course outline."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    menu_text = get_text("menu_header", lang) + "\n\n"
    
    for i, module in enumerate(MODULES):
        menu_text += f"*Module {i+1}: {module['title']}*\n"
        for lesson in module["lessons"]:
            menu_text += f" • {lesson['title']}\n"
        menu_text += "\n"
    
    menu_text += get_text("menu_continue", lang)
    
    await send_reply(
        update,
        menu_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_buttons(lang)
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
            reply_markup=get_main_menu_buttons(lang)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result
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
            module_title=module['title'],
            lesson_title=lesson['title']
        )
        
        await send_reply(
            update,
            progress_text,
            reply_markup=get_main_menu_buttons(lang)
        )
    else:
        await send_reply(
            update,
            get_text("error_generic", lang),
            reply_markup=get_main_menu_buttons(lang)
        )

async def next_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /next command and next button."""
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        lang = 'en'
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result

    # Block progression to next MODULE if quiz not attempted
    # (They must at least try the quiz — pass or fail doesn't matter)
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_completed", lang, module_title=module['title']),
            reply_markup=get_main_menu_buttons(lang)
        )
        return

    # Get next lesson
    next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)

    if next_module_id and next_lesson_id:
        # If moving to new module, reset quiz status
        if next_module_id != current_module_id:
            update_learner_progress(user_id, next_module_id, next_lesson_id, quiz_completed=0)
        else:
            update_learner_progress(user_id, next_module_id, next_lesson_id)

        module, lesson = get_module_lesson(next_module_id, next_lesson_id)
        
        if module and lesson:
            # Show lesson
            lesson_header = get_text("lesson_header", lang, module_title=module['title'], lesson_title=lesson['title'])
            
            await send_reply(
                update,
                f"{lesson_header}\n\n{lesson['content']}",
                parse_mode="Markdown",
                reply_markup=get_main_menu_buttons(lang)
            )

            # If this is last lesson, prompt for quiz
            if is_last_lesson_of_module(next_module_id, next_lesson_id):
                await send_reply(
                    update,
                    get_text("lessons_complete", lang, module_title=module['title']),
                    reply_markup=get_main_menu_buttons(lang)
                )
        else:
            await send_reply(
                update,
                get_text("error_generic", lang),
                reply_markup=get_main_menu_buttons(lang)
            )
    else:
        # Course complete
        await send_reply(
            update,
            get_text("course_complete", lang),
            reply_markup=get_main_menu_buttons(lang)
        )

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show quiz for current module."""
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        lang = 'en'
        await send_reply(
            update,
            get_text("not_started", lang),
            reply_markup=get_main_menu_buttons(lang)
        )
        return

    # FIXED: Unpack 4 values (module, lesson, quiz_status, language)
    current_module_id, current_lesson_id, quiz_completed, lang = result

    if quiz_completed == 1:
        await send_reply(
            update,
            get_text("quiz_already_completed", lang),
            reply_markup=get_main_menu_buttons(lang)
        )
        return
  # ✅ NEW: Check if at last lesson
    if not is_last_lesson_of_module(current_module_id, current_lesson_id):
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_ready", lang, module_title=module['title']),
            reply_markup=get_main_menu_buttons(lang)
        )
        return

    module = get_module_by_id(current_module_id)

    if module and "quiz" in module:
        quiz_data = module["quiz"]
        options = quiz_data["options"]

        # Create quiz instructions and buttons
        quiz_header = get_text("quiz_instructions", lang, module_title=module['title'], quiz_question=quiz_data['question'])
        
        # Create answer buttons
        buttons = [[InlineKeyboardButton(option, callback_data=f"quiz|{current_module_id}|{option[0]}")] for option in options]
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
            reply_markup=get_main_menu_buttons(lang)
        )

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change language preference."""
    await send_reply(
        update,
        TRANSLATIONS["language_change"]["en"],
        reply_markup=get_language_selection_buttons()
    )

# ============== BUTTON CALLBACK HANDLERS ==============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Language selection
    if data.startswith("lang_"):
        lang_code = data.split("_")[1]
        enroll_learner(user_id, lang_code)
        
        # Show welcome message
        welcome_text = get_text("start_welcome", lang_code, course_title=COURSE_TITLE, course_description=COURSE_DESCRIPTION)
        
        await query.edit_message_text(
            welcome_text,
            reply_markup=get_main_menu_buttons(lang_code)
        )
        return
    
    # Command buttons
    lang = get_language_preference(user_id)
    
    if data == "cmd_next":
        await query.delete_message()
        # Call next_lesson_handler via update object
        await next_lesson_handler(update, context)
        
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
    
    elif data == "cmd_language":
        await query.edit_message_text(
            TRANSLATIONS["language_change"]["en"],
            reply_markup=get_language_selection_buttons()
        )
    
    elif data == "cmd_help":
        await query.delete_message()
        await help_command(update, context)
    
    # Quiz retry - show quiz again
    elif data == "quiz_retry":
        await query.delete_message()
        await quiz_command(update, context)
    
    # Quiz skip/move forward
    elif data == "quiz_skip":
        await query.delete_message()
        await next_lesson_handler(update, context)
    
    # Quiz answer
    elif data.startswith("quiz|"):
        parts = data.split("|")
        if len(parts) < 3:
            await query.edit_message_text(get_text("error_generic", lang))
            return
        
        module_id = parts[1]
        selected_answer = parts[2]
        module = get_module_by_id(module_id)

        if module and "quiz" in module:
            correct_answer = module["quiz"]["answer"]
            if selected_answer == correct_answer:
                # CORRECT ANSWER
                update_quiz_status(user_id, 1)
                await query.edit_message_text(
                    get_text("quiz_correct", lang),
                    reply_markup=get_quiz_continue_button(lang)
                )
            else:
                # WRONG ANSWER - Mark quiz as attempted so they can proceed
                update_quiz_status(user_id, 2)
                await query.edit_message_text(
                    get_text("quiz_incorrect", lang, correct_answer=correct_answer),
                    reply_markup=get_quiz_retry_buttons(lang)
                )
        else:
            await query.edit_message_text(
                get_text("error_generic", lang),
                reply_markup=get_main_menu_buttons(lang)
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    user_message = update.message.text
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)

    # Check for navigation keywords
    if user_message.lower().strip() in ["next", "continue", "go next", "move on"]:
        await next_lesson_handler(update, context)
        return

    # Course-related keywords to check if the message is about the course
    course_keywords = [
        "gbv", "gender", "violence", "masculinity", "masculine", "man", "men",
        "woman", "women", "abuse", "consent", "relationship", "equality",
        "norm", "toxic", "positive", "harm", "prevent", "prevention",
        "module", "lesson", "course", "learn", "teach", "explain",
        "what is", "what are", "how", "why", "tell me", "define",
        "example", "meaning", "understand", "sex", "power", "control",
        "respect", "emotion", "stereotype", "bystander", "ally",
        "community", "advocacy", "intervention", "healthy", "unhealthy"
    ]

    # Check if message seems course-related
    message_lower = user_message.lower()
    is_course_related = any(keyword in message_lower for keyword in course_keywords)

    if is_course_related:
        # Use AI to answer course-related questions
        result = get_learner_progress(user_id)
        full_course_text = json.dumps(COURSE_CONTENT)

        if result and result[0]:
            current_module_id, current_lesson_id, _, _ = result
            module, lesson = get_module_lesson(current_module_id, current_lesson_id)
            if module and lesson:
                current_context = f"Current Module: {module['title']}. Current Lesson: {lesson['title']}. Content: {lesson['content']}"
                context_for_openai = f"Course Overview: {full_course_text}\n\nUser is currently in: {current_context}"
            else:
                context_for_openai = full_course_text
        else:
            context_for_openai = full_course_text

        response = get_openai_response(user_message, context_for_openai)
        await update.message.reply_text(
            response,
            reply_markup=get_main_menu_buttons(lang)
        )
    else:
        # Friendly nudge for non-course messages
        nudge = get_text("friendly_nudge", lang)
        await update.message.reply_text(
            nudge,
            reply_markup=get_main_menu_buttons(lang)
        )

async def post_init(application: Application) -> None:
    """Set bot commands in Telegram's menu."""
    commands = [
        BotCommand("start", "Begin or restart the course"),
        BotCommand("next", "Go to the next lesson"),
        BotCommand("quiz", "Take the quiz for the current module"),
        BotCommand("progress", "Check your current module and lesson"),
        BotCommand("menu", "View the full course outline"),
        BotCommand("language", "Change your language preference"),
        BotCommand("reset", "Reset progress completely and restart"),
        BotCommand("help", "Get help and list commands")
    ]
    await application.bot.set_my_commands(commands)

def main() -> None:
    """Start the bot."""
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(token).post_init(post_init).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("next", next_lesson_handler))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("language", language_command))

    # Message and button handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
