"""Outils MCP : suivi des modifications (ChangeLogs / Change Events)."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de suivi des changements."""

    # Factorisation : toutes les entités suivent le même pattern
    _entities = {
        "customers": {
            "name": "pennylane_changelog_customers",
            "title": "Changements clients",
            "doc": "clients",
        },
        "suppliers": {
            "name": "pennylane_changelog_suppliers",
            "title": "Changements fournisseurs",
            "doc": "fournisseurs",
        },
        "products": {
            "name": "pennylane_changelog_products",
            "title": "Changements produits",
            "doc": "produits",
        },
        "customer_invoices": {
            "name": "pennylane_changelog_customer_invoices",
            "title": "Changements factures clients",
            "doc": "factures clients",
        },
        "supplier_invoices": {
            "name": "pennylane_changelog_supplier_invoices",
            "title": "Changements factures fournisseurs",
            "doc": "factures fournisseurs",
        },
        "quotes": {
            "name": "pennylane_changelog_quotes",
            "title": "Changements devis",
            "doc": "devis",
        },
        "ledger_entry_lines": {
            "name": "pennylane_changelog_entry_lines",
            "title": "Changements lignes d'écriture",
            "doc": "lignes d'écriture comptable",
        },
        "transactions": {
            "name": "pennylane_changelog_transactions",
            "title": "Changements transactions",
            "doc": "transactions bancaires",
        },
    }

    for entity_key, meta in _entities.items():
        # Utiliser une closure pour capturer les variables
        _register_changelog_tool(mcp, entity_key, meta)


def _register_changelog_tool(mcp: FastMCP, entity_key: str, meta: dict) -> None:
    """Enregistre un outil changelog pour une entité donnée."""

    @mcp.tool(
        name=meta["name"],
        annotations={
            "title": meta["title"],
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def changelog_tool(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id'.")] = None,
    ) -> str:
        f"""Récupère les événements de changement sur les {meta['doc']}.
        Utile pour le suivi des modifications (création, mise à jour, suppression).
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            # L'endpoint est /changelogs/{entity}
            # ex: /changelogs/customers, /changelogs/suppliers
            endpoint = f"/changelogs/{entity_key}"

            data = await api_get(endpoint, qp)
            items = data.get("items", [])
            result = {
                "change_events": items,
                "entity": entity_key,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # Mettre le bon docstring
    changelog_tool.__doc__ = (
        f"Récupère les événements de changement sur les {meta['doc']}.\n"
        f"Utile pour le suivi des modifications (création, mise à jour, suppression)."
    )
