"""Outils MCP : lignes d'écriture, lettrage, catégories analytiques."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_delete, api_get, api_post, api_put
from ..models import CategoryWeight
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les 7 outils lignes d'écriture."""

    # ── Lister toutes les lignes ────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_all_entry_lines",
        annotations={
            "title": "Lister les lignes d'écriture",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_all_entry_lines(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        journal_id: Annotated[Optional[int], Field(default=None, description="Filtrer par ID de journal.")] = None,
        ledger_account_id: Annotated[Optional[int], Field(default=None, description="Filtrer par ID de compte comptable.")] = None,
        date_from: Annotated[Optional[str], Field(default=None, description="Date de début (YYYY-MM-DD).")] = None,
        date_to: Annotated[Optional[str], Field(default=None, description="Date de fin (YYYY-MM-DD).")] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id'.")] = None,
    ) -> str:
        """Liste toutes les lignes d'écriture comptable avec filtres par
        journal, compte et période. Utile pour analyser les mouvements
        d'un compte ou d'un journal sur une période.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if journal_id:
                filters.append({"field": "journal_id", "operator": "eq", "value": journal_id})
            if ledger_account_id:
                filters.append({"field": "ledger_account_id", "operator": "eq", "value": ledger_account_id})
            if date_from:
                filters.append({"field": "date", "operator": "gteq", "value": date_from})
            if date_to:
                filters.append({"field": "date", "operator": "lteq", "value": date_to})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/ledger_entry_lines", qp)
            items = data.get("items", [])
            result = {
                "lines": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Détail d'une ligne ──────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_entry_line",
        annotations={
            "title": "Détail d'une ligne d'écriture",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_entry_line(
        id: Annotated[int, Field(description="Identifiant unique de la ligne d'écriture.")],
    ) -> str:
        """Récupère le détail d'une ligne d'écriture comptable."""
        try:
            data = await api_get(f"/ledger_entry_lines/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lettrer ─────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_letter_lines",
        annotations={
            "title": "Lettrer des lignes d'écriture",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_letter_lines(
        line_ids: Annotated[list[int], Field(
            min_length=2,
            description="IDs des lignes à lettrer (min 2, même compte, équilibrées débit/crédit).",
        )],
        allow_partial: Annotated[bool, Field(
            default=False,
            description="Autoriser le lettrage partiel (déséquilibré). Défaut: false.",
        )] = False,
    ) -> str:
        """Lettre (rapproche) des lignes d'écriture entre elles. Permet de
        pointer des factures avec des règlements. Les lignes doivent appartenir
        au même compte (ex: 411xxx client). Par défaut, débit total = crédit total.
        """
        try:
            body = {
                "unbalanced_lettering_strategy": "partial" if allow_partial else "none",
                "ledger_entry_lines": [{"id": lid} for lid in line_ids],
            }
            data = await api_post("/ledger_entry_lines/lettering", body)
            return f"✅ Lettrage effectué pour {len(line_ids)} lignes.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Délettrer ───────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_unletter_lines",
        annotations={
            "title": "Délettrer des lignes",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_unletter_lines(
        line_ids: Annotated[list[int], Field(
            min_length=1,
            description="IDs des lignes à délettrer.",
        )],
        strategy: Annotated[str, Field(
            default="none",
            description="Stratégie de délettrage : 'none' (erreur si déséquilibre) ou 'partial' (autorisé).",
        )] = "none",
    ) -> str:
        """Supprime le lettrage de lignes d'écriture. Utile pour corriger un
        rapprochement erroné.
        """
        try:
            body = {
                "unbalanced_lettering_strategy": strategy,
                "ledger_entry_lines": [{"id": lid} for lid in line_ids],
            }
            await api_delete("/ledger_entry_lines/lettering", body)
            return f"✅ Délettrage effectué pour {len(line_ids)} ligne(s)."
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lier des catégories analytiques ─────────────────────────────────────

    @mcp.tool(
        name="pennylane_link_categories",
        annotations={
            "title": "Associer catégories analytiques",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_link_categories(
        line_id: Annotated[int, Field(description="ID de la ligne d'écriture.")],
        categories: Annotated[list[CategoryWeight], Field(
            min_length=1,
            description="Catégories analytiques avec poids. Chaque élément : {id: int, weight: str}. Poids de 0 à 1, somme = 1.",
        )],
    ) -> str:
        """Associe des catégories analytiques à une ligne d'écriture.
        Chaque catégorie a un poids (0 à 1, somme = 1).
        """
        try:
            cats = [c.model_dump() for c in categories]
            data = await api_put(
                f"/ledger_entry_lines/{line_id}/categories", cats
            )
            return f"✅ Catégories associées à la ligne {line_id}.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister catégories d'une ligne ───────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_line_categories",
        annotations={
            "title": "Catégories d'une ligne",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_line_categories(
        line_id: Annotated[int, Field(description="ID de la ligne d'écriture.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les catégories analytiques associées à une ligne d'écriture."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(
                f"/ledger_entry_lines/{line_id}/categories", qp
            )
            items = data.get("items", [])
            result = {
                "categories": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister lignes lettrées ──────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_lettered_lines",
        annotations={
            "title": "Lignes lettrées ensemble",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_lettered_lines(
        line_id: Annotated[int, Field(description="ID de la ligne de référence.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes lettrées (rapprochées) avec une ligne donnée.
        Permet de voir quels règlements sont pointés avec quelles factures.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(
                f"/ledger_entry_lines/{line_id}/lettered_ledger_entry_lines", qp
            )
            items = data.get("items", [])
            result = {
                "lettered_lines": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"
