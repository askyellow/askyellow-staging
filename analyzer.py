import json
import re
from openai import OpenAI

client = OpenAI()

SYSTEM_PROMPT = """
You analyze Dutch user input for an e-commerce search engine.

Return ONLY valid JSON with:
- intent (string)
- category (string or null)
- new_constraints (object)
- is_negative (boolean)
- missing_info (array)

Rules:
- Detect product search intent.
- Extract price_max if mentioned.
- Extract relevant keywords.
- If the answer is like "nee", set is_negative true.
- Do not invent products.
- No explanations. Only JSON.
"""

def ai_analyze_input(user_input: str):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    content = re.sub(r"```json", "", content)
    content = re.sub(r"```", "", content).strip()

    return json.loads(content)
