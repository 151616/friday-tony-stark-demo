from __future__ import annotations

from friday.routing.domains import ALWAYS_LOADED_DOMAINS, DOMAINS, OPTIONAL_DOMAINS


def classify_domains(text: str, *, max_optional_domains: int = 2) -> list[str]:
    """Return always-loaded domains plus the highest-confidence optional matches."""
    normalized = (text or "").lower().strip()
    if not normalized:
        return list(ALWAYS_LOADED_DOMAINS)

    scored: list[tuple[str, int]] = []
    for idx, name in enumerate(OPTIONAL_DOMAINS):
        domain = DOMAINS[name]
        score = 0
        for keyword in domain.keywords:
            if keyword in normalized:
                score += 2 if " " in keyword else 1
        if score > 0:
            # Preserve declaration order as the tie-breaker.
            scored.append((name, score * 100 - idx))

    scored.sort(key=lambda item: item[1], reverse=True)
    optional = [name for name, _ in scored[:max_optional_domains]]
    return list(ALWAYS_LOADED_DOMAINS) + optional
