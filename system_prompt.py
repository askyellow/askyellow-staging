import os
from pathlib import Path


# =============================================================
# 3. HELPERS: LOAD FILES & PROMPT
# =============================================================
BASE_DIR = Path(__file__).resolve().parent

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
    system_prompt += load_file(base + "system/yellowmind_master_prompt_v2.txt")
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
#KNOWLEDGE_ENTRIES = load_knowledge()