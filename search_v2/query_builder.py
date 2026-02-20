import json
import re
from openai import OpenAI

client = OpenAI()

def ai_build_search_decision(conversation_history: list[str]) -> dict:
    prompt = f"""
Je bent een intelligente e-commerce zoekassistent.

Analyseer de volledige conversatie:

{conversation_history}

Je taak:
1. Begrijp wat de gebruiker zoekt.
2. Integreer alle antwoorden.
3. Bouw één optimale zoekzin voor webshops.
4. Stel alleen een verduidelijkingsvraag als het écht nodig is.

Antwoord uitsluitend in JSON met:

- action: "search" of "clarify"
- search_query: string of null
- clarification_question: string of null

Before choosing "search", evaluate whether the essential product-defining attributes are sufficiently clear.

If major variables that significantly influence product type are still unknown,
choose "clarify" instead of "search".

Examples:
- For paint: surface type, indoor/outdoor, moisture exposure.
- For wood: outdoor exposure, soil contact, load-bearing needs.
- For mattresses: sleeping position.
- For electronics: compatibility requirements.

Only return "search" if you are confident that the generated search_query will likely return relevant products without major ambiguity.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    content = response.choices[0].message.content.strip()
    content = re.sub(r"```json", "", content)
    content = re.sub(r"```", "", content).strip()

    return json.loads(content)
