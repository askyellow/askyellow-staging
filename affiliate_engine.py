import json
from affiliate_prompt import build_affiliate_prompt
from openai import OpenAI
from urllib.parse import quote_plus
import re

client = OpenAI()

def generate_affiliate_models(constraints: dict, session_id: str) -> list:
    messages = build_affiliate_prompt(constraints)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.4
    )

    content = response.choices[0].message.content.strip()

    print("=== RAW AI RESPONSE ===")
    print(content)
    print("=======================")

    try:
        models = safe_json_extract(content)
        return models  # 🔥 belangrijk
    except Exception as e:
        print("JSON PARSE ERROR:", e)
        print("RAW CONTENT:", content)
        return []      # 🔥 altijd lijst teruggeven


def safe_json_extract(content: str):
    content = content.strip()

    # strip markdown codeblocks
    content = re.sub(r"```json\s*", "", content)
    content = re.sub(r"```", "", content).strip()

    # 1) als het al een array is
    if content.startswith("["):
        return json.loads(content)

    # 2) anders: zoek eerste JSON-array (ook lege [])
    match = re.search(r"\[[\s\S]*?\]", content)  # non-greedy
    if match:
        return json.loads(match.group())

    raise ValueError("No JSON array found")


def build_amazon_search_link(model_name: str, tag: str) -> str:
    query = quote_plus(model_name)
    return f"https://www.amazon.nl/s?k={query}&tag={tag}"
