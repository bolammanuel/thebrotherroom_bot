import os
import openai
from dotenv import load_dotenv

load_dotenv()
print("API Key exists:", bool(os.getenv("OPENAI_API_KEY")))
print("Key prefix:", os.getenv("OPENAI_API_KEY")[:10])

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

try:
    print("Sending test request to OpenAI...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello! Say hi."}],
        timeout=10.0
    )
    print("Response received successfully!")
    print(response.choices[0].message.content)
except Exception as e:
    print("Failed with error:", e)
