import json
import config
from google import genai
from google.genai import types
from analyze import SYSTEM_PROMPT, _build_user_prompt

client = genai.Client(api_key=config.GEMINI_API_KEY)
prompt = _build_user_prompt("Byliśmy tam w sobotę. Kelner Kacper był miły. Polecił pierogi z kaczką — wyśmienite! Atmosfera przytulna.", "Restauracja Testowa", 4)

response = client.models.generate_content(
    model=config.GEMINI_MODEL,
    contents=prompt,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.1,
        max_output_tokens=1024,
        response_mime_type="application/json",
    ),
)
print("Raw text:", repr(response.text))
