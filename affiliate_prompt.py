def build_affiliate_prompt(constraints: dict) -> list:
    system_prompt = """
Je bent een productspecialist.

Geef exact 3 concrete bestaande producten.
Voor elk product geef:
- brand
- model (exact modelnaam of modelnummer)
- short_reason (max 20 woorden)

Geen prijzen.
Geen links.
Geen voorbeelden.
Geen uitleg buiten JSON.

Geef uitsluitend geldige JSON array.
"""

    user_prompt = f"""
Budget: {constraints.get('budget')}
Gebruik: {constraints.get('use_case')}
Type: {constraints.get('type')}
Extra voorkeuren: {constraints.get('extra')}

Geef 3 geschikte modellen.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
