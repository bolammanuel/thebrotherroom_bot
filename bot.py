import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from db_manager import init_db, enroll_learner, get_learner_progress, update_learner_progress, update_quiz_status
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

COURSE_TITLE = COURSE_CONTENT["course_title"]
COURSE_DESCRIPTION = COURSE_CONTENT["course_description"]
MODULES = COURSE_CONTENT["modules"]

# Helper function to get module and lesson by ID
def get_module_by_id(module_id):
    for module in MODULES:
        if module["module_id"] == module_id:
            return module
    return None

def get_module_lesson(module_id, lesson_id):
    for module in MODULES:
        if module["module_id"] == module_id:
            for lesson in module["lessons"]:
                if lesson["lesson_id"] == lesson_id:
                    return module, lesson
    return None, None

def is_last_lesson_of_module(module_id, lesson_id):
    module = get_module_by_id(module_id)
    if module and module["lessons"]:
        return lesson_id == module["lessons"][-1]["lesson_id"]
    return False

def get_next_lesson(current_module_id, current_lesson_id):
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

    # Try to get the next lesson in the current module
    if current_lesson_index + 1 < len(MODULES[current_module_index]["lessons"]):
        next_lesson = MODULES[current_module_index]["lessons"][current_lesson_index + 1]
        return current_module_id, next_lesson["lesson_id"]

    # Try to get the first lesson in the next module
    elif current_module_index + 1 < len(MODULES):
        next_module = MODULES[current_module_index + 1]
        if next_module["lessons"]:
            return next_module["module_id"], next_module["lessons"][0]["lesson_id"]

    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    enroll_learner(user_id)

    # Show welcome message
    await update.message.reply_text(
        f"\"Ekaabo!\" (Welcome!) to the \"{COURSE_TITLE}\" course, designed just for young Nigerian men like you.\n\n"
        f"{COURSE_DESCRIPTION}\n\n"
        f"Type /next to begin your first lesson or /help for a list of commands."
    )

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    current_module_id, current_lesson_id, quiz_completed = result
    module, lesson = get_module_lesson(current_module_id, current_lesson_id)

    if module and lesson:
        # Count completed modules
        module_index = 0
        for i, m in enumerate(MODULES):
            if m["module_id"] == current_module_id:
                module_index = i
                break

        total_modules = len(MODULES)
        await update.message.reply_text(
            f"📊 Your Progress:\n\n"
            f"📖 Module {module_index + 1}/{total_modules}: {module['title']}\n"
            f"📝 Current Lesson: {lesson['title']}\n\n"
            f"Type /next to continue learning."
        )
    else:
        await update.message.reply_text("Could not retrieve your progress. Please try /start again.")

async def next_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    current_module_id, current_lesson_id, quiz_completed = result

    # Check if we're at the last lesson of a module and quiz is not completed
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
        module = get_module_by_id(current_module_id)
        if module and "quiz" in module:
            # Check if user has already seen this lesson (not first time)
            seen_key = f"seen_{current_module_id}_{current_lesson_id}"
            if context.user_data.get(seen_key):
                await update.message.reply_text(
                    f"You need to complete the quiz for \"{module['title']}\" before moving on.\n\n"
                    f"Type /quiz to take the quiz."
                )
                return

    # Check if we're moving to the next module and quiz hasn't been done
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
        module = get_module_by_id(current_module_id)

        # Show the current lesson first if not seen yet
        seen_key = f"seen_{current_module_id}_{current_lesson_id}"
        if not context.user_data.get(seen_key):
            module, lesson = get_module_lesson(current_module_id, current_lesson_id)
            if module and lesson:
                context.user_data[seen_key] = True
                await update.message.reply_text(
                    f"📖 *Module: {module['title']}*\n"
                    f"📝 *Lesson: {lesson['title']}*\n\n"
                    f"{lesson['content']}",
                    parse_mode="Markdown"
                )

            await update.message.reply_text(
                f"✅ You've completed all lessons in \"{module['title']}\"!\n\n"
                f"Time for a quick quiz to test your knowledge. Type /quiz to begin."
            )
            return
        else:
            await update.message.reply_text(
                f"You need to complete the quiz for \"{module['title']}\" before moving on.\n\n"
                f"Type /quiz to take the quiz."
            )
            return

    # If quiz is completed for current module's last lesson, or we're mid-module, advance
    next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)

    if next_module_id and next_lesson_id:
        # If moving to a new module, reset quiz status
        if next_module_id != current_module_id:
            update_learner_progress(user_id, next_module_id, next_lesson_id, quiz_completed=0)
        else:
            update_learner_progress(user_id, next_module_id, next_lesson_id)

        module, lesson = get_module_lesson(next_module_id, next_lesson_id)
        if module and lesson:
            await update.message.reply_text(
                f"📖 *Module: {module['title']}*\n"
                f"📝 *Lesson: {lesson['title']}*\n\n"
                f"{lesson['content']}",
                parse_mode="Markdown"
            )

            # If this is the last lesson of the module, prompt for quiz
            if is_last_lesson_of_module(next_module_id, next_lesson_id):
                context.user_data[f"seen_{next_module_id}_{next_lesson_id}"] = True
                await update.message.reply_text(
                    f"✅ You've completed all lessons in \"{module['title']}\"!\n\n"
                    f"Time for a quick quiz to test your knowledge. Type /quiz to begin."
                )
        else:
            await update.message.reply_text("Error retrieving next lesson. Please contact support.")
    else:
        # Check if current lesson has been shown
        module, lesson = get_module_lesson(current_module_id, current_lesson_id)
        seen_key = f"seen_{current_module_id}_{current_lesson_id}"

        if not context.user_data.get(seen_key):
            context.user_data[seen_key] = True
            if module and lesson:
                await update.message.reply_text(
                    f"📖 *Module: {module['title']}*\n"
                    f"📝 *Lesson: {lesson['title']}*\n\n"
                    f"{lesson['content']}",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                "🎉 Congratulations! You have completed all available lessons and quizzes!\n\n"
                "You are now a champion for positive masculinity and GBV prevention.\n\n"
                "Type /progress to review your achievement or /start to retake the course."
            )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    result = get_learner_progress(user_id)

    if not result or not result[0]:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    current_module_id, current_lesson_id, quiz_completed = result

    if quiz_completed:
        await update.message.reply_text("You have already completed the quiz for this module. Type /next to continue.")
        return

    module = get_module_by_id(current_module_id)

    if module and "quiz" in module:
        quiz_data = module["quiz"]
        options = quiz_data["options"]
        
        # FIXED: Use pipe (|) separator instead of underscore to avoid conflict with module_id
        keyboard = [[InlineKeyboardButton(option, callback_data=f"quiz|{current_module_id}|{option[0]}")] for option in options]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📝 *Quiz for: {module['title']}*\n\n{quiz_data['question']}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("No quiz available for the current module. Type /next to continue.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    
    # FIXED: Use pipe separator instead of underscore
    data = query.data.split("|")
    
    if len(data) < 3:
        await query.edit_message_text("Error processing quiz. Please try again.")
        return
    
    action = data[0]

    if action == "quiz":
        module_id = data[1]
        selected_answer = data[2]
        module = get_module_by_id(module_id)

        if module and "quiz" in module:
            correct_answer = module["quiz"]["answer"]
            if selected_answer == correct_answer:
                update_quiz_status(user_id, 1)  # Mark quiz as completed
                await query.edit_message_text(
                    "\"Ehen!\" Correct! 🎉 That's the right answer!\n\n"
                    "You've passed the quiz for this module. Type /next to continue your learning journey."
                )
            else:
                await query.edit_message_text(
                    f"\"Chai!\" Not quite right. The correct answer was {correct_answer}.\n\n"
                    f"Don't worry — learning is a journey! Type /quiz to retry."
                )
        else:
            await query.edit_message_text("Error processing quiz. Please try again.")
    else:
        await query.edit_message_text("Error processing quiz. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here are the commands you can use:\n\n"
        "/start - Begin or restart the course\n"
        "/next - Move to the next lesson\n"
        "/quiz - Take the quiz for the current module\n"
        "/progress - Check your current module and lesson\n"
        "/help - Show this help message\n\n"
        "You can also type 'next' or ask me questions about the course content!"
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    menu_text = "📚 *Course Outline*\n\n"

    for i, module in enumerate(MODULES):
        menu_text += f"*Module {i+1}: {module['title']}*\n"
        for lesson in module["lessons"]:
            menu_text += f" • {lesson['title']}\n"
        menu_text += "\n"

    menu_text += "Type /next to continue from where you left off."
    await update.message.reply_text(menu_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id

    # Check for 'next' or similar keywords to advance lesson
    if user_message.lower().strip() in ["next", "continue", "go next", "move on"]:
        await next_lesson_handler(update, context)
        return

    # Get current course context for OpenAI
    result = get_learner_progress(user_id)
    full_course_text = json.dumps(COURSE_CONTENT)

    if result and result[0]:
        current_module_id, current_lesson_id, _ = result
        module, lesson = get_module_lesson(current_module_id, current_lesson_id)
        if module and lesson:
            current_context = f"Current Module: {module['title']}. Current Lesson: {lesson['title']}. Content: {lesson['content']}"
            context_for_openai = f"Course Overview: {full_course_text}\n\nUser is currently in: {current_context}"
        else:
            context_for_openai = full_course_text
    else:
        context_for_openai = full_course_text

    # Generate response using OpenAI
    response = get_openai_response(user_message, context_for_openai)
    await update.message.reply_text(response)

def main() -> None:
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(token).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("progress", progress))
    application.add_handler(CommandHandler("next", next_lesson_handler))
    application.add_handler(CommandHandler("quiz", quiz))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))

    # Message handler for general text and 'next' keyword
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Callback query handler for quiz buttons
    application.add_handler(CallbackQueryHandler(button))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
