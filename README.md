# Young Men Against Gender Based Violence - Conversational LMS Telegram Bot

This project is a Telegram bot designed to serve as a conversational Learning Management System (LMS) for young Nigerian men, focusing on positive masculinity and Gender-Based Violence (GBV) prevention.

## Features

- **Welcoming & Enrollment**: Greets new learners and enrolls them automatically.
- **Structured Lessons**: Delivers course content step-by-step, allowing learners to progress by typing "next" or similar commands.
- **Modular Course Structure**: Organizes content into modules, each containing multiple lessons.
- **Module Quizzes**: Quizzes learners after each module to test their understanding.
- **Progress Tracking**: Tracks individual learner progress, including current lesson/module and quiz completion status.
- **Conversational Tone**: Engages learners with a tone suited for young Nigerian men.
- **Commands**: Supports `/start`, `/progress`, `/next`, `/quiz`, `/help`, and `/menu`.
- **Contextual Responses**: Uses OpenAI API (gpt-4.1-mini) to generate contextual responses to learner questions based on course content.

## Course Details

- **Title**: "Young Men Against Gender Based Violence"
- **Topic**: Positive masculinity & GBV prevention
- **Audience**: Young Nigerian men

## Technical Stack

- **Language**: Python
- **Telegram Bot Library**: `python-telegram-bot`
- **Database**: SQLite (for learner progress tracking)
- **Course Content Storage**: JSON file (`course_content.json`)
- **AI Integration**: OpenAI API (gpt-4.1-mini)
- **Deployment**: Railway (with `Procfile` and `railway.json`)

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

**Module 1: Understanding Gender-Based Violence**
- What is GBV?
- Types and Forms of GBV

**Module 2: Exploring Positive Masculinity**
- Defining Masculinity
- Traits of Positive Masculinity
- Challenging Harmful Stereotypes

**Module 3: The Role of Young Men in Prevention**
- Being an Ally
- Promoting Equality

**Module 4: Building Healthy Relationships**
- Communication and Consent
- Conflict Resolution without Violence
