import os
import json
import time
import openai
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def validate_translation(trans, original_module):
    try:
        for lang in ["pcm", "ha", "yo", "ig"]:
            if lang not in trans:
                print(f"Validation failed: missing language '{lang}'")
                return False
            lang_data = trans[lang]
            if not isinstance(lang_data, dict):
                print(f"Validation failed: '{lang}' is not a dictionary")
                return False
            if "title" not in lang_data or "opening_story" not in lang_data:
                print(f"Validation failed: missing 'title' or 'opening_story' in '{lang}' (keys found: {list(lang_data.keys())})")
                return False
            if "lessons" not in lang_data or not isinstance(lang_data["lessons"], list) or len(lang_data["lessons"]) != len(original_module["lessons"]):
                print(f"Validation failed: 'lessons' is invalid in '{lang}' (expected list of length {len(original_module['lessons'])}, got {type(lang_data.get('lessons'))} with keys/length {len(lang_data.get('lessons')) if isinstance(lang_data.get('lessons'), list) else 'N/A'})")
                return False
            for idx, lesson in enumerate(lang_data["lessons"]):
                if not isinstance(lesson, dict) or "title" not in lesson or "content" not in lesson:
                    print(f"Validation failed: lesson {idx} is invalid in '{lang}' (keys: {list(lesson.keys()) if isinstance(lesson, dict) else type(lesson)})")
                    return False
            if "quiz" not in lang_data or not isinstance(lang_data["quiz"], list) or len(lang_data["quiz"]) != len(original_module["quiz"]):
                print(f"Validation failed: 'quiz' is invalid in '{lang}' (expected list of length {len(original_module['quiz'])})")
                return False
            for idx, q in enumerate(lang_data["quiz"]):
                if not isinstance(q, dict) or "question" not in q or "options" not in q or "feedback" not in q:
                    print(f"Validation failed: quiz {idx} is invalid in '{lang}' (keys: {list(q.keys()) if isinstance(q, dict) else type(q)})")
                    return False
                if not isinstance(q["options"], list) or len(q["options"]) != len(original_module["quiz"][idx]["options"]):
                    print(f"Validation failed: quiz {idx} options list length is invalid in '{lang}'")
                    return False
        return True
    except Exception as e:
        print(f"Validation exception: {e}")
        return False

def translate_module(module_data):
    to_translate = {
        "title": module_data["title"],
        "opening_story": module_data.get("opening_story", ""),
        "lessons": [
            {
                "lesson_id": l["lesson_id"],
                "title": l["title"],
                "content": l["content"]
            } for l in module_data["lessons"]
        ],
        "quiz": [
            {
                "question": q["question"],
                "options": q["options"],
                "feedback": q.get("feedback", "")
            } for q in module_data["quiz"]
        ]
    }
    
    print(f"Translating Module: {module_data['title']}...")
    
    prompt = (
        "Translate the following module content from English into Nigerian Pidgin ('pcm'), Hausa ('ha'), Yoruba ('yo'), and Igbo ('ig').\n"
        "This content is for 'The Brothers' Room' course on positive masculinity and GBV prevention for young Nigerian men.\n"
        "Guidelines:\n"
        "1. Pidgin (pcm) should sound extremely natural, warm, brotherly, using common Nigerian slang where appropriate (e.g., 'how far', 'abeg', 'correct', 'oga').\n"
        "2. Hausa (ha), Yoruba (yo), and Igbo (ig) must be accurate, respectful, and culturally appropriate.\n"
        "3. Maintain original meaning, markdown styling (like * or _), and spacing.\n"
        "4. Return ONLY a valid JSON object matching the requested structure.\n"
        "5. CRITICAL: Keep all JSON keys exactly as defined in English ('title', 'opening_story', 'lessons', 'content', 'quiz', 'question', 'options', 'feedback'). DO NOT translate JSON keys. Only translate their string values.\n\n"
        f"Input Module JSON:\n{json.dumps(to_translate, indent=2)}\n\n"
        "Format your response as a JSON object with the exact language keys: 'pcm', 'ha', 'yo', 'ig'. "
        "Each key must map to an object containing: 'title', 'opening_story', 'lessons' (list of title/content in the same order), and 'quiz' (list of question/options/feedback in the same order)."
    )
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            res_dict = json.loads(response.choices[0].message.content)
            if validate_translation(res_dict, module_data):
                print(f"Successfully translated Module: {module_data['title']}")
                return res_dict
            else:
                print(f"Translation validation failed for '{module_data['title']}'. Retrying... (Attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"Attempt {attempt + 1} for '{module_data['title']}' failed with error: {e}")
        time.sleep(2)
    raise ValueError(f"Failed to translate module {module_data['title']} after {max_retries} attempts.")

def main():
    if not os.path.exists("course_content.json"):
        print("Error: course_content.json not found.")
        return
        
    with open("course_content.json", "r", encoding="utf-8") as f:
        content = json.load(f)
        
    course_title_translations = {
        "en": content["course_title"],
        "pcm": "Young Men Against Gender Based Violence",
        "ha": "Matasa Maza Wajen Yaki Da Cin Zarafin Jinsi",
        "yo": "Awon Odo Okunrin Lodi Si Ijagba Lori Eya",
        "ig": "Ndị Okorobịa Megide Ime Ihe Ike Dabere na Nwoke na Nwanyị"
    }
    
    course_desc_translations = {
        "en": content["course_description"],
        "pcm": "This course dey designed for young Nigerian men to explore positive masculinity and prevent gender-based violence.",
        "ha": "Wannan kwas din an tsara shi ne domin matasan maza na Najeriya su binciki kyakkyawar dabi'a da kuma rigakafin cin zarafi na jinsi.",
        "yo": "Awon eko yii wa fun awon odo okunrin lowo lowo lati se afihan okunrin rere ati dena ijagba lori eya.",
        "ig": "Ezubere ihe ọmụmụ a maka ụmụ okorobịa Nigeria ka ha nyochaa ezi omume nwoke na igbochi ime ihe ike dabere na nwoke na nwanyị."
    }
    
    modules = content["modules"]
    
    def process_and_translate_module(module):
        # Get translations
        trans = translate_module(module)
        
        # Build localized module structure
        new_mod = {
            "module_id": module["module_id"],
            "title": {
                "en": module["title"],
                "pcm": trans["pcm"]["title"],
                "ha": trans["ha"]["title"],
                "yo": trans["yo"]["title"],
                "ig": trans["ig"]["title"]
            }
        }
        
        if "opening_story" in module:
            new_mod["opening_story"] = {
                "en": module["opening_story"],
                "pcm": trans["pcm"]["opening_story"],
                "ha": trans["ha"]["opening_story"],
                "yo": trans["yo"]["opening_story"],
                "ig": trans["ig"]["opening_story"]
            }
            
        # Build lessons list
        new_lessons = []
        for idx, lesson in enumerate(module["lessons"]):
            new_lessons.append({
                "lesson_id": lesson["lesson_id"],
                "video": lesson.get("video"),  # Keep video if configured
                "title": {
                    "en": lesson["title"],
                    "pcm": trans["pcm"]["lessons"][idx]["title"],
                    "ha": trans["ha"]["lessons"][idx]["title"],
                    "yo": trans["yo"]["lessons"][idx]["title"],
                    "ig": trans["ig"]["lessons"][idx]["title"]
                },
                "content": {
                    "en": lesson["content"],
                    "pcm": trans["pcm"]["lessons"][idx]["content"],
                    "ha": trans["ha"]["lessons"][idx]["content"],
                    "yo": trans["yo"]["lessons"][idx]["content"],
                    "ig": trans["ig"]["lessons"][idx]["content"]
                }
            })
        new_mod["lessons"] = new_lessons
        
        # Build quiz list
        new_quiz = []
        for idx, quiz in enumerate(module["quiz"]):
            new_quiz.append({
                "question": {
                    "en": quiz["question"],
                    "pcm": trans["pcm"]["quiz"][idx]["question"],
                    "ha": trans["ha"]["quiz"][idx]["question"],
                    "yo": trans["yo"]["quiz"][idx]["question"],
                    "ig": trans["ig"]["quiz"][idx]["question"]
                },
                "options": {
                    "en": quiz["options"],
                    "pcm": trans["pcm"]["quiz"][idx]["options"],
                    "ha": trans["ha"]["quiz"][idx]["options"],
                    "yo": trans["yo"]["quiz"][idx]["options"],
                    "ig": trans["ig"]["quiz"][idx]["options"]
                },
                "answer": quiz["answer"],
                "feedback": {
                    "en": quiz.get("feedback", ""),
                    "pcm": trans["pcm"]["quiz"][idx].get("feedback", ""),
                    "ha": trans["ha"]["quiz"][idx].get("feedback", ""),
                    "yo": trans["yo"]["quiz"][idx].get("feedback", ""),
                    "ig": trans["ig"]["quiz"][idx].get("feedback", "")
                }
            })
        new_mod["quiz"] = new_quiz
        return new_mod
        
    print("Starting parallel translation of all 11 modules...")
    with ThreadPoolExecutor(max_workers=11) as executor:
        new_modules = list(executor.map(process_and_translate_module, modules))
        
    localized_content = {
        "course_title": course_title_translations,
        "course_description": course_desc_translations,
        "modules": new_modules
    }
    
    with open("course_content.json", "w", encoding="utf-8") as f:
        json.dump(localized_content, f, indent=4, ensure_ascii=False)
        
    print("Success! course_content.json has been fully localized.")

if __name__ == "__main__":
    main()
