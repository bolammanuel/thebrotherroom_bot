import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(prompt, course_content):
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1-mini", # Using the specified model
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
