import json
from affiliate_prompt import build_affiliate_prompt
from openai import OpenAI
from urllib.parse import quote_plus


client = OpenAI()

def generate_affiliate_models(constraints: dict, session_id: str) -> list:
    messages = build_affiliate_prompt(constraints)

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # jouw standaard model
        messages=messages,
        temperature=0.4
    )

    content = response.choices[0].message.content
    print("RAW AI RESPONSE:", content)

    try:
        models = json.loads(content)
    except Exception:
        return []

    return models


def build_amazon_search_link(model_name: str, tag: str) -> str:
    query = quote_plus(model_name)
    return f"https://www.amazon.nl/s?k={query}&tag={tag}"
