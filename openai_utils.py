import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(prompt, course_content, language='en'):
    try:
        # Construct supportive system prompt that handles Nigerian languages and redirects off-topic questions
        system_content = (
            f"You are Tobi, a friendly, professional, and supportive AI facilitator for a course titled "
            f"\"Young Men Against Gender Based Violence\" (The Brothers' Room) targeted at young Nigerian men. "
            f"The course content is: {course_content}\n\n"
            f"Guidelines:\n"
            f"1. You must answer the user's question politely and constructively in their chosen language (the current language code is '{language}'). "
            f"2. Your tone must be supportive, brotherly, non-judgmental, clean, and professional. "
            f"3. Do not use emojis in your response.\n"
            f"4. If the question is completely unrelated to positive masculinity, GBV prevention, relationship communication, consent, or the course content, "
            f"gently and politely guide the user back to these course topics, explaining that this is a focused space for us brothers to grow together."
        )
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error communicating with OpenAI: {e}")
        fallbacks = {
            "en": "I'm taking a quick moment to reflect on that, brother. Ask me again shortly, or let's keep moving with the lessons!",
            "pcm": "I dey think about this one small, my brother. Ask me again just now, or make we continue with the lessons!",
            "ha": "Ina dan yin tunani a kan wannan, brother. Sake tambaya ta nan da kankanin lokaci, ko kuma mu ci gaba da darussan!",
            "yo": "Mo n ronu lori eyi die, brother. Beere lọwọ mi lẹẹkansi laipẹ, tabi jẹ ki a tẹsiwaju pẹlu awọn ẹkọ!",
            "ig": "M na-eche echiche banyere nke a obere, nwanne m. Jụọ m ajụjụ ọzọ n'oge na-adịghị anya, ma ọ bụ ka anyị gaa n'ihu na ihe ọmụmụ!"
        }
        return fallbacks.get(language, fallbacks["en"])

def transcribe_voice(audio_file_path):
    """Transcribe a voice note (.ogg/.mp3/etc.) using OpenAI Whisper-1."""
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        with open(audio_file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            return transcript.text.strip()
    except Exception as e:
        print(f"Error transcribing voice note with Whisper: {e}")
        return None

def synthesize_speech(text, output_file_path):
    """Synthesize text into speech (.ogg/.mp3) using OpenAI TTS tts-1."""
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy", # Warm, professional, neutral voice
            input=text
        )
        response.write_to_file(output_file_path)
        return True
    except Exception as e:
        print(f"Error synthesizing speech with OpenAI TTS: {e}")
        return False

