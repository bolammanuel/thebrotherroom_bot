import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(prompt, course_content):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini", # Using the specified model
            messages=[
                {"role": "system", "content": f"You are a helpful assistant for a course titled \"Young Men Against Gender Based Violence\". The course content is: {course_content}"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error communicating with OpenAI: {e}")
        return "I apologize, but I'm having trouble connecting to the AI at the moment. Please try again later."

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

