# core/config.py

import os
from dotenv import load_dotenv
from openai import OpenAI



load_dotenv()

# -------------------------------------------------
# App info
# -------------------------------------------------
APP_ENV = os.getenv("APP_ENV", "live")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# -------------------------------------------------
# OpenAI / YellowMind
# -------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is missing")

YELLOWMIND_MODEL = os.getenv("YELLOWMIND_MODEL", "o3-mini")

VALID_MODELS = [
    "o3-mini",
    "o1-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o-mini",
]

if YELLOWMIND_MODEL not in VALID_MODELS:
    print(f"?? Onbekend model '{YELLOWMIND_MODEL}' ? fallback naar o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

# onder OPENAI_API_KEY check
client = OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------
# External services
# -------------------------------------------------
SQL_SEARCH_URL = os.getenv(
    "SQL_SEARCH_URL",
    "https://www.askyellow.nl/search_knowledge.php"
)

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Shopify
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = "2025-10"

# Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
