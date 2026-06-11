import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(prompt, course_content, language='en'):
    try:
        # Construct language guidance to make Tobi speak natural local dialects (especially Pidgin)
        language_guidance = ""
        if language == "pcm":
            language_guidance = (
                "You must respond in highly fluent, natural, and authentic Nigerian Pidgin. "
                "Act like a supportive, wise elder brother (an 'oga' or senior brother) in a respectful way. "
                "Use natural local phrases like 'How far my brother', 'Wetin dey occur', 'no shake', 'make we follow-talk', 'wetin you think', 'abeg'. "
                "Do NOT use literal translations of formal English idioms. Keep the sentence structure natural and punchy, e.g., use 'dey' instead of 'is/are', 'wetin' instead of 'what', 'fit' instead of 'can', 'gatz' instead of 'have to'. "
                "Make the tone brotherly and relatable, yet serious about gender-based violence and positive masculinity."
            )
        elif language == "yo":
            language_guidance = "You must respond in clean, culturally appropriate, and natural Yoruba. Act like a supportive older brother (Yegbon)."
        elif language == "ha":
            language_guidance = "You must respond in clean, respectful, and natural Hausa. Act like a supportive brother (Yaya)."
        elif language == "ig":
            language_guidance = "You must respond in clean, respectful, and natural Igbo. Act like a supportive brother (Deede/Nwanne)."
        else:
            language_guidance = "You must respond in a supportive, friendly, and brotherly tone in English. Act like a mentor or wise elder brother."

        system_content = (
            f"You are Tobi, a friendly, professional, and supportive AI facilitator for a course titled "
            f"\"Young Men Against Gender Based Violence\" (The Brothers' Room) targeted at young Nigerian men.\n\n"
            f"Course Curriculum:\n{course_content}\n\n"
            f"AI Facilitator Guidelines:\n"
            f"1. You must answer the user's question politely and constructively in their chosen language (the current language code is '{language}').\n"
            f"2. Language & Tone Guide: {language_guidance}\n"
            f"3. Your tone must be supportive, brotherly, non-judgmental, clean, and professional.\n"
            f"4. Do not use emojis in your response.\n"
            f"5. DEEPEN KNOWLEDGE: The Course Curriculum provided above contains the core references and outlines. "
            f"However, you should NOT limit your answers to just repeating the short text in the curriculum. "
            f"Instead, act as an expert facilitator: elaborate on the topics, explain concepts in detail, provide real-world relatable examples, "
            f"and share deep insights about positive masculinity, consent, bystander intervention (like the 5Ds), healthy communication, and GBV prevention.\n"
            f"6. FOCUS: If the question is completely unrelated to positive masculinity, GBV prevention, relationship communication, consent, or the course content, "
            f"gently and politely guide the user back to these course topics, explaining in a brotherly way that this is a focused space for us brothers to learn and grow together."
        )
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250
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

def transcribe_voice(audio_file_path, language='en'):
    """Transcribe a voice note (.ogg/.mp3/etc.) using OpenAI Whisper-1 with language guiding prompts."""
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Whisper uses ISO-639-1 language codes.
        # Pidgin doesn't have an official code, so we use English ('en') with a Pidgin prompt.
        whisper_lang = language
        if language == "pcm":
            whisper_lang = "en"
            
        prompts = {
            "en": "This is a conversation about positive masculinity, gender-based violence, respect, relationships, and consent in The Brothers' Room.",
            "pcm": "How far, my brother. Wetin we dey talk for here na about positive masculinity, respect, consent, and Gender-Based Violence for inside The Brothers' Room.",
            "ha": "Sannu brother. Wannan tattaunawa ce game da kyakkyawar dabi'a ta namiji, yaki da cin zarafi, girmamawa, da yarda a The Brothers' Room.",
            "yo": "A ti gba ètò yìí gbọ́. Ẹ jẹ́ kọ́ sọ̀rọ̀ nípa ọkùnrin rere, ìfẹ́, ọ̀wọ̀, àti ìfohùnṣọ̀kan. Ẹ̀kọ́ The Brothers' Room nìyí.",
            "ig": "Nnọọ nwanne. Nke a bụ mkparịta ụka gbasara ezi omume nwoke, ime ihe ike, ugwu, mmekọrịta, na nkwenye na The Brothers' Room."
        }
        
        prompt = prompts.get(language, prompts["en"])
        
        with open(audio_file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=whisper_lang,
                prompt=prompt
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

