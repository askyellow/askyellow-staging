def build_affiliate_prompt(constraints: dict) -> list:
    system_prompt = """
Je bent een productspecialist.

BELANGRIJK:
- Geef uitsluitend producten binnen de opgegeven categorie.
- Geef GEEN producten uit een andere categorie.
- Als categorie 'stofzuiger' is, geef alleen stofzuigers.
- Geen smartphones.
- Geen koptelefoons.
- Geen elektronica tenzij het binnen de categorie valt.

Geef exact 3 bestaande producten.
Voor elk product:
- brand
- model
- short_reason (max 20 woorden)

Geen prijzen.
Geen links.
Geen uitleg.
Geef uitsluitend geldige JSON array.
"""

    user_prompt = f"""
Categorie: {constraints.get("category")}
Budget max: {constraints.get("budget_max")}
Vereisten: {constraints.get("requirements")}
Voorkeuren: {constraints.get("preferences")}

Geef 3 geschikte modellen.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
