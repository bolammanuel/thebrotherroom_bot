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
def get_module_lesson(module_id, lesson_id):
    for module in MODULES:
        if module["module_id"] == module_id:
            for lesson in module["lessons"]:
                if lesson["lesson_id"] == lesson_id:
                    return module, lesson
    return None, None

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
    await update.message.reply_text(
        f"\"Ekaabo!\" (Welcome!) to the \"{COURSE_TITLE}\" course, designed just for young Nigerian men like you.\n\n{COURSE_DESCRIPTION}\n\nType /next to begin your journey or /help for a list of commands."
    )

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_module_id, current_lesson_id, quiz_completed = get_learner_progress(user_id)

    if not current_module_id:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    module, lesson = get_module_lesson(current_module_id, current_lesson_id)
    if module and lesson:
        status = "Completed" if quiz_completed else "Pending"
        await update.message.reply_text(
            f"You are currently on Module: {module["title"]}, Lesson: {lesson["title"]}.\nQuiz for this module: {status}"
        )
    else:
        await update.message.reply_text("Could not retrieve your progress. Please try /start again.")

async def next_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_module_id, current_lesson_id, quiz_completed = get_learner_progress(user_id)

    if not current_module_id:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    # If quiz is pending, prompt user to take quiz first
    if not quiz_completed:
        module, _ = get_module_lesson(current_module_id, current_lesson_id)
        if module and "quiz" in module:
            await update.message.reply_text(
                f"You need to complete the quiz for Module: {module["title"]} before moving to the next lesson. Type /quiz to start the quiz."
            )
            return

    next_module_id, next_lesson_id = get_next_lesson(current_module_id, current_lesson_id)

    if next_module_id and next_lesson_id:
        update_learner_progress(user_id, next_module_id, next_lesson_id)
        module, lesson = get_module_lesson(next_module_id, next_lesson_id)
        if module and lesson:
            await update.message.reply_text(
                f"*Module: {module["title"]}*\n*Lesson: {lesson["title"]}*\n\n{lesson["content"]}",
                parse_mode="Markdown"
            )
            # If it's the last lesson of a module, prompt for quiz
            if lesson["lesson_id"] == module["lessons"][-1]["lesson_id"]:
                await update.message.reply_text(
                    f"You've completed all lessons in Module: {module["title"]}. Time for a quick check! Type /quiz to test your knowledge."
                )
                update_quiz_status(user_id, 0) # Reset quiz status for new module
        else:
            await update.message.reply_text("Error retrieving next lesson. Please contact support.")
    else:
        await update.message.reply_text("You have completed all available lessons! Congratulations!\n\nType /progress to see your achievement.")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_module_id, _, quiz_completed = get_learner_progress(user_id)

    if not current_module_id:
        await update.message.reply_text("It seems you haven't started the course yet. Type /start to begin!")
        return

    if quiz_completed:
        await update.message.reply_text("You have already completed the quiz for this module. Type /next to continue.")
        return

    module, _ = get_module_lesson(current_module_id, "") # Get current module details
    if module and "quiz" in module:
        quiz_data = module["quiz"]
        options = quiz_data["options"]
        keyboard = [[InlineKeyboardButton(option, callback_data=f"quiz_{current_module_id}_{option[0]}")] for option in options]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"*Quiz for Module: {module["title"]}*\n\n{quiz_data["question"]}", reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text("No quiz available for the current module or you have completed it. Type /next to continue.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split("_")
    action = data[0]

    if action == "quiz":
        module_id = data[1]
        selected_answer = data[2]
        module, _ = get_module_lesson(module_id, "")
        if module and "quiz" in module:
            correct_answer = module["quiz"]["answer"]
            if selected_answer == correct_answer:
                update_quiz_status(user_id, 1) # Mark quiz as completed
                await query.edit_message_text("\"Ehen!\" (Correct!) That's the right answer! You've passed the quiz for this module. Type /next to continue your learning journey.")
            else:
                await query.edit_message_text(f"\"Chai!\" (Incorrect!) That's not quite right. The correct answer was {correct_answer}. Please review the lessons and try again.\n\nType /quiz to retry or /next to move on if you're ready.")
        else:
            await query.edit_message_text("Error processing quiz. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here are the commands you can use:\n"
        "/start - Begin or restart the course\n"
        "/progress - Check your current module and lesson\n"
        "/next - Move to the next lesson or module\n"
        "/quiz - Take the quiz for the current module\n"
        "/menu - See the course menu (coming soon!)\n"
        "/help - Show this help message\n\n"
        "You can also ask me questions about the course content, and I'll do my best to answer!"
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # This can be expanded to show a full course menu with inline buttons for modules/lessons
    await update.message.reply_text("The course menu feature is still under development. For now, please use /next to navigate through lessons.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id

    # Check for 'next' or similar keywords to advance lesson
    if user_message.lower() in ["next", "continue", "go next", "move on"]:
        await next_lesson_handler(update, context)
        return

    # Get current course context for OpenAI
    current_module_id, current_lesson_id, _ = get_learner_progress(user_id)
    full_course_text = json.dumps(COURSE_CONTENT) # Send entire course content for context

    if current_module_id and current_lesson_id:
        module, lesson = get_module_lesson(current_module_id, current_lesson_id)
        if module and lesson:
            # Prioritize current lesson content for context
            current_context = f"Current Module: {module['title']}. Current Lesson: {lesson['title']}. Content: {lesson['content']}"
            # Combine with full course content, ensuring it doesn't exceed token limits
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
