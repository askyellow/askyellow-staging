from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import openai
import os

load_dotenv()

# Check API key
key = os.getenv("OPENAI_API_KEY")
print("✅ API key loaded successfully!" if key else "❌ API key NOT found!")

# Init FastAPI
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI setup
openai.api_key = key

@app.post("/api/vraag")
async def vraag_ai(data: dict):
    vraag = data.get("vraag", "")
    datum = data.get("datum", "")  # ✅ datum ophalen van frontend

    if not vraag:
        return {"antwoord": "Geen vraag ontvangen."}

    # Combineer datum + vraag in één duidelijke prompt
    prompt = f"Vandaag is het {datum}. Beantwoord de volgende vraag accuraat en actueel: {vraag}"

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        antwoord = response.choices[0].message.content.strip()
        return {"antwoord": antwoord}
    except Exception as e:
        return {"antwoord": f"Fout: {e}"}
