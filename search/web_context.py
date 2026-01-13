# search/web_context.py

def build_web_context(web_results: list) -> str:
    """
    Fase 1 (super basic):
    Pak 1–2 webresultaten en maak er een korte contextzin van.
    """

    if not web_results:
        return ""

    context_lines = []

    for r in web_results[:2]:
        title = r.get("title")
        snippet = r.get("snippet")
        source = r.get("source") or r.get("url")

        if snippet:
            context_lines.append(
                f"- {snippet} (bron: {source})"
            )

    if not context_lines:
        return ""

    return (
        "Gebruik onderstaande recente webinformatie bij het beantwoorden:\n"
        + "\n".join(context_lines)
    )
