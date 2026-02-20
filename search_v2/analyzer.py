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

Also return:
- should_refine (boolean): true only if ONE extra question would significantly narrow results.
- refine_question (string or null): exactly 1 short Dutch question if should_refine is true, otherwise null.

Rules:
- Only consider refinement if category is known AND price_max is known.
- Ask about ONE high-impact attribute (e.g. "elektrisch of niet?" for fatbike, "stoom of droog?" for strijkijzer).
- Never ask about budget again if price_max is already present.
- If user input is a negative like "nee", do not invent refinement; set should_refine false.

intent can be:
- product_search (clear buying intent)
- assisted_search (user asks which type of product they need before buying)
- general_question

Classify as assisted_search when:
- the user asks which type, variant or specification they should choose
- the user seeks guidance before selecting a product

Examples:
- "wat voor verf moet ik gebruiken"
- "welke boormachine heb ik nodig"
- "wat voor matras past bij mij"

Do not classify based on product name.
Classify based on intent pattern.

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

def ai_generate_refinement_question(state: dict) -> str:
    prompt = f"""
Je bent een slimme e-commerce assistent.

De gebruiker zoekt naar:
Categorie: {state.get("category")}
Maximale prijs: {state["constraints"].get("price_max")}

Stel EXACT 1 korte, natuurlijke vervolgvraag
die de zoekresultaten significant verfijnt.

Vraag niet opnieuw naar budget.
Geen uitleg.
Alleen de vraag.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()
