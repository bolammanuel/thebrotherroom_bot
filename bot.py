import os
import json
import logging
import asyncio
import csv
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
    get_due_sunday_checks, init_sunday_checks, update_sunday_check_sent, get_all_learner_reflections
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

# ============== INLINE BUTTON HELPER ==============

def get_main_menu_buttons(lang='en', user_id=None):
    """Get context-aware main menu buttons with a dynamic accessibility toggle and dynamically hidden quiz button."""
    voice_enabled = False
    show_quiz = False
    if user_id:
        try:
            voice_enabled = get_voice_responses(user_id)
            progress = get_learner_progress(user_id)
            if progress and progress[0]:
                current_module_id, current_lesson_id, quiz_completed, _ = progress
                if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
                    show_quiz = True
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
    
    # Only show Next button if we aren't displaying the Quiz as the primary next action
    buttons.append([InlineKeyboardButton(get_command_button("next", lang), callback_data="cmd_next")])
    
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
        }.get(lang, "My Journal"), callback_data="cmd_journal")]
        # [InlineKeyboardButton(voice_label, callback_data="cmd_accessibility")]
    ])
    return InlineKeyboardMarkup(buttons)

def get_help_keyboard_buttons(lang='en', user_id=None):
    """Get keyboard buttons specifically for the help menu containing all commands with dynamic quiz visibility."""
    voice_enabled = False
    show_quiz = False
    if user_id:
        try:
            voice_enabled = get_voice_responses(user_id)
            progress = get_learner_progress(user_id)
            if progress and progress[0]:
                current_module_id, current_lesson_id, quiz_completed, _ = progress
                if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
                    show_quiz = True
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
        "en": "Join WhatsApp Community",
        "pcm": "Join WhatsApp Group",
        "ha": "Shiga Rukunin WhatsApp",
        "yo": "Darapọ mọ Agbegbe WhatsApp",
        "ig": "Soro na Otu WhatsApp"
    }.get(lang, "Join WhatsApp Community")

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
        # [InlineKeyboardButton(voice_label, callback_data="cmd_accessibility")],
        [InlineKeyboardButton(community_label, url="https://chat.whatsapp.com/YOUR_GROUP_LINK")]
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
        
    # Check for voice accessibility preference (disabled for now)
    user_id = update.effective_user.id if update.effective_user else None
    if False:  # user_id and get_voice_responses(user_id):
        # Clean text of raw markdown formatting for a natural audio reading experience
        clean_text = text.replace('*', '').replace('_', '').replace('`', '').replace('👉', '').replace('👇', '').replace('✅', '').replace('🎉', '').replace('📊', '').replace('📝', '').replace('📖', '').replace('📚', '').replace('🤛', '').replace('🤜', '')
        
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
        reply_markup=get_main_menu_buttons(lang, user_id=user_id),
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
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id)
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
 
async def community_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to join the WhatsApp community."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    prompt = {
        "en": "🤜🤛 *Join The Brothers' Room WhatsApp Community!*\n\nContinue the conversation with other brothers, challenge harmful norms together, and get access to exclusive events.\n\nJoin here: https://chat.whatsapp.com/YOUR_GROUP_LINK",
        "pcm": "🤜🤛 *Join The Brothers' Room WhatsApp Group!*\n\nMake we continue this talk with other brothers, work together, and get beta information.\n\nJoin here: https://chat.whatsapp.com/YOUR_GROUP_LINK",
        "ha": "🤜🤛 *Shiga Rukunin WhatsApp na The Brothers' Room!*\n\nCi gaba da tattaunawa da sauran 'yan uwa, ƙalubalanci al'adun da ba su da kyau tare.\n\nShiga nan: https://chat.whatsapp.com/YOUR_GROUP_LINK",
        "yo": "🤜🤛 *Darapọ mọ Agbegbe WhatsApp ti The Brothers' Room!*\n\nTẹsiwaju ibaraẹnisọrọ pẹlu awọn arakunrin miiran, ati ifọwọsowọpọ fun rere.\n\nDarapọ mọ nibi: https://chat.whatsapp.com/YOUR_GROUP_LINK",
        "ig": "🤜🤛 *Soro na Otu WhatsApp nke The Brothers' Room!*\n\nGaa n'ihu na nkata gị na ụmụnne gị ndị ọzọ, ma rụọ ọrụ ọnụ.\n\nSoro na ebe a: https://chat.whatsapp.com/YOUR_GROUP_LINK"
    }.get(lang, "en")
    
    button_label = {
        "en": "Join WhatsApp Community",
        "pcm": "Join WhatsApp Group",
        "ha": "Shiga Rukunin WhatsApp",
        "yo": "Darapọ mọ Agbegbe WhatsApp",
        "ig": "Soro na Otu WhatsApp"
    }.get(lang, "Join WhatsApp Community")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_label, url="https://chat.whatsapp.com/YOUR_GROUP_LINK")]
    ])
    
    await send_reply(update, prompt, parse_mode="Markdown", reply_markup=keyboard)
 
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    await send_reply(
        update,
        get_text("help_menu", lang),
        reply_markup=get_help_keyboard_buttons(lang, user_id=user_id)
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
        reply_markup=get_main_menu_buttons(lang, user_id=user_id)
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
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
    else:
        await send_reply(
            update,
            get_text("error_generic", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )

async def next_lesson_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /next command and next button."""
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)
    
    if is_user_graduated(user_id):
        await send_graduation_dashboard(update, context, lang, user_id)
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

    # Block progression to next MODULE if quiz not attempted
    # (They must at least try the quiz — pass or fail doesn't matter)
    if is_last_lesson_of_module(current_module_id, current_lesson_id) and not quiz_completed:
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_completed", lang, module_title=module['title']),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
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
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )

            # If this is last lesson, prompt for quiz
            if is_last_lesson_of_module(next_module_id, next_lesson_id):
                await send_reply(
                    update,
                    get_text("lessons_complete", lang, module_title=module['title']),
                    reply_markup=get_main_menu_buttons(lang, user_id=user_id)
                )
        else:
            await send_reply(
                update,
                get_text("error_generic", lang),
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )
    else:
        # Course complete — Route to the scored exit post-test exam!
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

    if quiz_completed == 1:
        await send_reply(
            update,
            get_text("quiz_already_completed", lang),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return
  # ✅ NEW: Check if at last lesson
    if not is_last_lesson_of_module(current_module_id, current_lesson_id):
        module = get_module_by_id(current_module_id)
        await send_reply(
            update,
            get_text("quiz_not_ready", lang, module_title=module['title']),
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return

    module = get_module_by_id(current_module_id)

    if module and "quiz" in module:
        quiz_data = module["quiz"]
        options = quiz_data["options"]

        # Create quiz instructions and buttons
        options_text = "\n".join(options)
        question_with_options = f"{quiz_data['question']}\n\n{options_text}"
        quiz_header = get_text("quiz_instructions", lang, module_title=module['title'], quiz_question=question_with_options)
        
        # Create answer buttons in a single row using short letters
        buttons = [[InlineKeyboardButton(f" {option[0]} ", callback_data=f"quiz|{current_module_id}|{option[0]}") for option in options]]
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
            reply_markup=get_main_menu_buttons(lang, user_id=user_id)
        )
        return
        
    journal_text = get_text("journal_header", lang)
    for module_id, ref_text in reflections:
        module = get_module_by_id(module_id)
        module_title = module["title"] if module else module_id
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

def generate_certificate_image(name, date_str, user_id):
    """Generate a highly aesthetic, premium, high-resolution certificate of completion using Pillow."""
    import hashlib
    from PIL import Image, ImageDraw, ImageFont
    
    width, height = 2000, 1418
    
    # Base background (Cream color matching the sample)
    img = Image.new("RGB", (width, height), (232, 226, 213))
    draw = ImageDraw.Draw(img)
    
    assets_dir = "assets"
    
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
    fonts_dir = "assets/fonts"
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
    
    output_path = f"assets/certificate_{user_id}.png"
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
    
    congrats_text = get_text("course_complete", lang)
    
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
                
    community_chat_id = os.getenv("COMMUNITY_CHAT_ID")
    if community_chat_id:
        try:
            broadcast_text = f"🤜🤛 *New Brother Pledge Posted!*\n\n*Learner:* {learner_name}\n*Pledge:* \"{pledge}\"\n\nWelcome our new graduate and Peer Champion!"
            await context.application.bot.send_message(
                chat_id=community_chat_id,
                text=broadcast_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error broadcasting pledge to community: {e}")

async def reminder_scheduler(application: Application) -> None:
    """Persistent background asynchronous worker for scheduling nudges and weekly reminders."""
    logger.info("Background reminder scheduler started successfully!")
    while True:
        try:
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
        [InlineKeyboardButton("Export Progress Report (CSV)", callback_data="admin_export_csv")]
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
        text += f"   • Modules Completed: {item['modules_completed']}/12\n"
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
        SELECT user_id, full_name, current_module_id, current_lesson_id, quiz_completed, 
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
            "User ID", "Full Name", "Current Module", "Current Lesson", "Quiz Status", 
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
        
        full_name = query.from_user.full_name if query.from_user else None
        enroll_learner(user_id, lang_code, full_name=full_name)
        
        if is_new_user or context.user_data.get('awaiting_language_selection'):
            context.user_data.pop('awaiting_language_selection', None)
            # Show welcome message encouraging Pre-Test
            welcome_text = get_text("start_welcome", lang_code, course_title=COURSE_TITLE, course_description=COURSE_DESCRIPTION)
            pretest_button_label = {
                "en": "✍️ Take Pre-Test Quiz",
                "pcm": "✍️ Start Pre-Test Quiz",
                "ha": "✍️ Fara Jarrabawar Farko",
                "yo": "✍️ Bẹrẹ Idanwo Àkọ́kọ́",
                "ig": "✍️ Malite Ule Mbụ"
            }.get(lang_code, "✍️ Take Pre-Test Quiz")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(pretest_button_label, callback_data="pretest_start")]
            ])
            await query.edit_message_text(
                welcome_text,
                reply_markup=keyboard,
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
            reply_markup = get_help_keyboard_buttons(lang, user_id=user_id)
        else:
            reply_markup = get_main_menu_buttons(lang, user_id=user_id)
            
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
                # Check if this is the first attempt (quiz_completed == 0)
                progress = get_learner_progress(user_id)
                if progress and progress[2] == 0:
                    increment_first_attempt_quizzes(user_id)
                
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
                reply_markup=get_main_menu_buttons(lang, user_id=user_id)
            )
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    user_message = update.message.text
    user_id = update.effective_user.id
    lang = get_language_preference(user_id)

    # Intercept private reflections
    if context.user_data.get("awaiting_reflection"):
        module_id = context.user_data.pop("awaiting_reflection", None)
        from db_manager import save_reflection
        save_reflection(user_id, module_id, user_message)
        
        saved_msg = TRANSLATIONS.get("reflections", {}).get("saved", {}).get(lang, "Reflection saved privately in your journal.")
        await update.message.reply_text(saved_msg)
        
        # Move forward automatically
        await next_lesson_handler(update, context)
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
        await update.message.reply_text(pledge_prompt)
        return

    # Intercept personal pledges for graduations
    if context.user_data.get("awaiting_pledge"):
        context.user_data.pop("awaiting_pledge", None)
        save_pledge(user_id, user_message)
        cert_name = context.user_data.pop("cert_name", update.effective_user.full_name)
        await handle_graduation_and_certificate(update, context, pledge=user_message, cert_name=cert_name)
        return

    # Check for navigation keywords
    if user_message.lower().strip() in ["next", "continue", "go next", "move on"]:
        await next_lesson_handler(update, context)
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
            current_context = f"Current Module: {module['title']}. Current Lesson: {lesson['title']}. Content: {lesson['content']}"
            context_for_openai = f"Course Overview: {full_course_text}\n\nUser is currently in: {current_context}"
        else:
            context_for_openai = full_course_text
    else:
        context_for_openai = full_course_text

    response = get_openai_response(user_message, context_for_openai, language=lang)
    await update.message.reply_text(
        response,
        reply_markup=get_main_menu_buttons(lang, user_id=user_id)
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
        BotCommand("journal", "View your Reflections Journal"),
        # BotCommand("accessibility", "Toggle voice replies for visual accessibility"),
        BotCommand("admin", "Admin Dashboard & Peer Facilitator Leaderboard"),
        BotCommand("community", "Join our WhatsApp community"),
        BotCommand("reset", "Reset progress completely and restart"),
        BotCommand("help", "Get help and list commands")
    ]
    await application.bot.set_my_commands(commands)
    # Start background reminder and nudge scheduler clock
    asyncio.create_task(reminder_scheduler(application))

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
    application.add_handler(CommandHandler("community", community_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("next", next_lesson_handler))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("journal", journal_command))
    # application.add_handler(CommandHandler("accessibility", accessibility_command))
    application.add_handler(CommandHandler("admin", admin_command))

    # Message, voice, and button handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
