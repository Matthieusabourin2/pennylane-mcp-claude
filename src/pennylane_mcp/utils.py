"""Utilitaires partagés : formatage, troncature, pagination."""

from __future__ import annotations

import json
from typing import Any, Optional

from .constants import CHARACTER_LIMIT


def truncate_if_needed(text: str, hint: str | None = None) -> str:
    """Tronque la réponse si elle dépasse CHARACTER_LIMIT."""
    if len(text) <= CHARACTER_LIMIT:
        return text
    truncated = text[: CHARACTER_LIMIT - 200]
    msg = (
        "\n\n---\n⚠️ Réponse tronquée. "
        + (hint or "Utilisez les paramètres de pagination (limit, cursor) ou des filtres.")
    )
    return truncated + msg


def pagination_summary(
    has_more: bool | None,
    next_cursor: str | None,
    total_items: int | None = None,
    item_count: int | None = None,
) -> str:
    """Construit un résumé de pagination lisible."""
    parts: list[str] = []
    if item_count is not None:
        parts.append(f"{item_count} résultat(s) retourné(s)")
    if total_items is not None:
        parts.append(f"sur {total_items} au total")
    if has_more:
        parts.append(f'— Il reste des résultats. Utilisez cursor="{next_cursor}" pour la page suivante.')
    else:
        parts.append("— Tous les résultats ont été retournés.")
    return " ".join(parts)


def to_json(data: Any) -> str:
    """Sérialise en JSON indenté."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)
