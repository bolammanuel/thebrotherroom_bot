# Young Men Against Gender Based Violence - Conversational LMS Telegram Bot

This project is a Telegram bot designed to serve as a conversational Learning Management System (LMS) for young Nigerian men, focusing on positive masculinity and Gender-Based Violence (GBV) prevention.

## Features

- **Multilingual Localization**: Full support for 5 native languages: English, Pidgin, Hausa, Yoruba, and Igbo. Onboarding, lessons, quizzes, and help documentation are dynamically translated based on learner preferences.
- **Visual Accessibility Toggle**: Dynamic inline buttons (**Voice: ON 🔊 / Voice: OFF 🔇**) automatically localized in all 5 languages are embedded in both the main menu and help keyboards. Tapping them toggles spoken audio replies on/off immediately.
- **Speech-to-Text & Text-to-Speech**: Visually impaired or low-literacy users can speak directly to the bot by sending standard Telegram voice notes (transcribed via Whisper). When voice mode is enabled, the bot synthesizes all lessons and quiz alerts into audio voice notes using OpenAI TTS.
- **Structured Lessons & Progress Tracking**: Delivers modular learning content step-by-step. Automatically enrolls learners and saves progress (current module, lesson, and quiz completion status) in a persistent SQLite database.
- **Dynamic Module Quizzes**: Quick, context-aware interactive quizzes at the end of each module to validate learning, complete with retry and skip mechanisms.
- **Scored Exit Post-Test Exam**: A comprehensive 5-question final exam covering key course themes. Requires a cutoff mark of at least 35/50 (4 out of 5 correct) to pass and graduate.
- **Custom Pledge & Peer Broadcast**: Prompts successful graduates to make a personal commitment pledge to stand against GBV, which is automatically broadcasted to the community group.
- **Dynamic Certificate Generation**: Dynamically compiles and renders a high-quality, professional Certificate of Completion using Pillow, featuring the learner's full name, completion date, and a secure verification ID.
- **WhatsApp Community Integration**: Encourages graduates to join a WhatsApp community group via post-course completion cards and the `/community` command to sustain engagement.
- **Background Reminders & Nudges**: 
  - **Weekly Pledge Reminders**: Automatically messages graduates with their personal pledges to remind them of their commitment.
  - **Inactivity Nudges**: Automatically sends gentle check-in reminders to inactive learners after 4 days of inactivity.
- **Conversational AI Companion**: Leverages OpenAI API (`gpt-4-mini`) to answer learner questions contextually based on the course materials, supporting both text and speech-to-text voice interactions.

## Interactive Commands

The bot supports the following persistent commands in the menu:
- `/start` - Start or restart the onboarding flow, including language selection.
- `/next` - Progress to the next structured lesson or module quiz.
- `/quiz` - Trigger the module quiz (available at the end of each module).
- `/progress` - View detailed module and lesson progress.
- `/language` - Change translation preference (English, Pidgin, Hausa, Yoruba, or Igbo) at any point.
- `/menu` - View the interactive course syllabus/outline.
- `/community` - Retrieve quick-join links to the WhatsApp group.
- `/help` - Show a comprehensive list of commands with quick-action buttons.
- `/reset` - Completely reset all database progress to start the course brand new.

## Technical Stack

- **Language**: Python 3
- **Telegram Bot Library**: `python-telegram-bot` (v20+)
- **Database**: SQLite (for persistent user progress, pledges, score history, and activity timestamps)
- **Course Content**: Modular JSON storage (`course_content.json`)
- **Localization**: Native translations file (`translations.json`)
- **AI Integration**: OpenAI API (`gpt-4o-mini` / Whisper for voice transcripts / TTS for audio accessibility)
- **Graphics Rendering**: Pillow (PIL) for certificate generation using beautiful custom fonts
- **Deployment**: Configured for Railway using `Procfile` and `railway.json`

## Project Structure

```
lms-bot/
├── bot.py
├── db_manager.py
├── openai_utils.py
├── course_content.json
├── requirements.txt
├── Procfile
├── railway.json
└── README.md
```

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/bolammanuel/lms-bot.git # Replace with actual repo URL
cd lms-bot
```

### 2. Set up Environment Variables

You need to set the following environment variables:

- `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API Token. You can get this from BotFather on Telegram.
- `OPENAI_API_KEY`: Your OpenAI API Key.

For local development, you can create a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

When deploying to Railway, you will configure these variables directly in the Railway dashboard.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Locally

```bash
python bot.py
```

### 5. Deployment on Railway

This project is configured for easy deployment on Railway. The `Procfile` and `railway.json` files are included.

1. **Create a new project on Railway.**
2. **Connect your GitHub repository.**
3. **Configure Environment Variables**: Add `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY` in your Railway project settings.
4. **Deploy**: Railway will automatically detect the `Procfile` and `railway.json` and deploy your bot.

## Usage

Once the bot is running (either locally or deployed):

- Send `/start` to the bot to begin the course.
- Use `/next` to move through lessons.
- Use `/quiz` to take the module quiz.
- Use `/progress` to check your current standing.
- Use `/help` for a list of commands.
- Ask questions related to the course content, and the bot will respond contextually.

## Sample Course Content (from `course_content.json`)

(This section provides a brief overview of the modules and lessons defined in `course_content.json`)

**Module 1: Understanding Gender & Masculinity**
- Sex vs Gender
- The Key Insight
- What is Positive Masculinity?

**Module 2: Harmful Norms & Toxic Masculinity**
- What Are Harmful Gender Norms?
- What is Toxic Masculinity?
- The Cost of Toxic Norms

**Module 3: Introduction to SGBV**
- What is SGBV?
- Who Are the Victims?
- The Impact of SGBV

**Module 4: Root Causes of SGBV**
- Power Imbalance
- Culture and Socialisation
- Economic Factors

**Module 5: Role of Men as Change Agents**
- Why Men Must Be Part of the Solution
- What Allyship Looks Like
- Personal Responsibility

**Module 6: Healthy Masculinity & Relationships**
- Consent — The Foundation of Everything
- Communication and Conflict
- Emotional Intelligence

**Module 7: Bystander Intervention**
- Recognising Abuse
- How to Intervene Safely — The 5Ds
- Supporting Survivors

**Module 8: Peer Influence & Leadership**
- Understanding Your Influence
- Leading by Example
- Becoming an Advocate

**Module 9: Community Action & Advocacy**
- Why Community Action Matters
- The Power of Storytelling
- How to Engage Your Community

**Module 10: Networks & Movement Building**
- Why Networks Matter
- Collaboration Over Competition
- Sustaining the Movement

**Module 11: Personal Action Plan**
- What You Now Know
- Building Your Personal Action Plan
- Accountability and the Pledge
