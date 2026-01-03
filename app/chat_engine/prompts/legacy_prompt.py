# app/chat_engine/prompts/legacy_prompt.py

import os

# Dit moet wijzen naar de /app map (waar ook yellowmind/ staat)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def load_file(path: str) -> str:
    full_path = os.path.join(BASE_DIR, path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return "\n" + f.read().strip() + "\n"
    except FileNotFoundError:
        print(f"⚠️ Yellowmind config file niet gevonden: {full_path}")
        return ""

def build_system_prompt() -> str:
    base = "yellowmind/"
    system_prompt = ""

    # SYSTEM CORE
    system_prompt += load_file(base + "system/yellowmind_master_prompt_v3.txt")
    system_prompt += load_file(base + "core/core_identity.txt")
    system_prompt += load_file(base + "core/mission.txt")
    system_prompt += load_file(base + "core/values.txt")
    system_prompt += load_file(base + "core/introduction_rules.txt")
    system_prompt += load_file(base + "core/communication_baseline.txt")

    # PARENTS
    system_prompt += load_file(base + "parents/parent_profile_brigitte.txt")
    system_prompt += load_file(base + "parents/parent_profile_dennis.txt")
    system_prompt += load_file(base + "parents/parent_profile_yello.txt")
    system_prompt += load_file(base + "parents/parent_mix_logic.txt")

    # BEHAVIOUR
    system_prompt += load_file(base + "behaviour/behaviour_rules.txt")
    system_prompt += load_file(base + "behaviour/boundaries_safety.txt")
    system_prompt += load_file(base + "behaviour/escalation_rules.txt")
    system_prompt += load_file(base + "behaviour/uncertainty_handling.txt")
    system_prompt += load_file(base + "behaviour/user_types.txt")

    # KNOWLEDGE
    system_prompt += load_file(base + "knowledge/knowledge_sources.txt")
    system_prompt += load_file(base + "knowledge/askyellow_site_rules.txt")
    system_prompt += load_file(base + "knowledge/product_rules.txt")
    system_prompt += load_file(base + "knowledge/no_hallucination_rules.txt")
    system_prompt += load_file(base + "knowledge/limitations.txt")

    # TONE
    system_prompt += load_file(base + "tone/tone_of_voice.txt")
    system_prompt += load_file(base + "tone/branding_mode.txt")
    system_prompt += load_file(base + "tone/empathy_mode.txt")
    system_prompt += load_file(base + "tone/tech_mode.txt")
    system_prompt += load_file(base + "tone/storytelling_mode.txt")
    system_prompt += load_file(base + "tone/concise_mode.txt")

    return system_prompt.strip()

SYSTEM_PROMPT = build_system_prompt()

SYSTEM_PROMPT += """
GESCHIEDENIS = BRON VAN WAARHEID

- Als gespreksgeschiedenis aanwezig is in de context,
  behandel je deze als feitelijk correct.
- Vragen als:
  “wat was mijn laatste vraag?”
  “wat was het laatste weetje?”
  “waar hadden we het over?”
  beantwoord je door letterlijk terug te kijken
  in de beschikbare chatgeschiedenis.
- Je verzint GEEN onzekerheid over geschiedenis
  als deze zichtbaar is.
- Je wisselt niet tussen:
  “ik kan terugkijken” en “ik kan niet terugkijken”.
  Als je zegt dat je kunt terugkijken,
  gebruik je die informatie ook daadwerkelijk.

INTERPRETATIE VAN VRAGEN OVER HET VERLEDEN

- Als een gebruiker vraagt naar:
  “eerste vraag vandaag”
  “laatste vraag”
  “waar hadden we het over”
  zonder exacte tijdsgrens,
  interpreteer dit als:
  → binnen de huidige chatsessie.
- Beantwoord de vraag concreet op basis van
  de beschikbare gespreksgeschiedenis.
- Als “vandaag” of “eerder” ambigu is,
  kies je de meest logische interpretatie
  (de huidige sessie) en geef je een direct antwoord,
  zonder te ontwijken.
- Je stelt GEEN tegenvraag als de intentie duidelijk is.

VRAGEN OVER “EERSTE” OF “LAATSTE” VRAAG

- Als een gebruiker vraagt naar:
  “de eerste vraag” of “de laatste vraag”:
  → bepaal dit door in de gespreksgeschiedenis te kijken
    naar het eerste of laatste bericht met role = user.
- Je beschouwt alleen user-berichten als vragen.
- Je antwoordt concreet door die vraag te herhalen of samen te vatten.

Je gebruikt AskYellow Search als primaire bron voor zoeken.
Leg geen beperkingen uit aan de gebruiker.
"""
