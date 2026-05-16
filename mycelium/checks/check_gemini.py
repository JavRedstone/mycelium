from dotenv import load_dotenv
import os
import requests

load_dotenv()

try:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": "This is an API test call. Please respond with the single word: ok"}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 16},
        },
    )
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    print(f"[OK] Gemini — response: {text.strip()}")
except Exception as e:
    print(f"[FAIL] Gemini — {e}")
