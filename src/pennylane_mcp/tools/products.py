"""Outils MCP : gestion des produits (Products)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des produits."""

    # ── Lister les produits ──────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_products",
        annotations={
            "title": "Lister les produits",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_products(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        label: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par libellé du produit.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les produits/services du catalogue avec filtres et pagination.
        Utile pour consulter le catalogue, rechercher un produit par nom.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if label:
                filters.append({"field": "label", "operator": "eq", "value": label})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/products", qp)
            items = data.get("items", [])
            result = {
                "products": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer un produit ─────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_product",
        annotations={
            "title": "Détail d'un produit",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_product(
        id: Annotated[int, Field(description="Identifiant unique du produit.")],
    ) -> str:
        """Récupère le détail d'un produit par son identifiant.
        Retourne : libellé, prix HT, TVA, unité, compte comptable associé.
        """
        try:
            data = await api_get(f"/products/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un produit ─────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_product",
        annotations={
            "title": "Créer un produit",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_product(
        label: Annotated[str, Field(description="Libellé du produit/service.")],
        price_before_tax: Annotated[str, Field(description="Prix unitaire HT (ex: '100.00').")],
        vat_rate: Annotated[str, Field(
            description="Code taux de TVA (ex: 'FR_200' pour 20%, 'FR_100' pour 10%, "
            "'FR_55' pour 5.5%, 'exempt' pour exonéré).",
        )],
        description: Annotated[Optional[str], Field(default=None, description="Description (max 5000 caractères).")] = None,
        unit: Annotated[Optional[str], Field(default=None, description="Unité (ex: 'piece', 'hour', 'kg').")] = None,
        currency: Annotated[Optional[str], Field(default=None, description="Devise (défaut: EUR).")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Référence interne.")] = None,
        ledger_account_id: Annotated[Optional[int], Field(default=None, description="ID du compte comptable de vente associé.")] = None,
    ) -> str:
        """Crée un nouveau produit/service dans le catalogue.
        Le libellé, le prix HT et le taux de TVA sont obligatoires.
        """
        try:
            body: dict = {
                "label": label,
                "price_before_tax": price_before_tax,
                "vat_rate": vat_rate,
            }
            if description:
                body["description"] = description
            if unit:
                body["unit"] = unit
            if currency:
                body["currency"] = currency
            if reference:
                body["reference"] = reference
            if ledger_account_id:
                body["ledger_account_id"] = ledger_account_id

            data = await api_post("/products", body)
            return (
                f"✅ Produit '{data.get('label')}' créé — "
                f"prix HT: {data.get('price_before_tax')}, "
                f"id: {data.get('id')}.\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour un produit ─────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_product",
        annotations={
            "title": "Modifier un produit",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_product(
        id: Annotated[int, Field(description="Identifiant du produit à modifier.")],
        label: Annotated[Optional[str], Field(default=None, description="Nouveau libellé.")] = None,
        price_before_tax: Annotated[Optional[str], Field(default=None, description="Nouveau prix HT.")] = None,
        vat_rate: Annotated[Optional[str], Field(default=None, description="Nouveau taux de TVA.")] = None,
        description: Annotated[Optional[str], Field(default=None, description="Nouvelle description.")] = None,
        unit: Annotated[Optional[str], Field(default=None, description="Nouvelle unité.")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Nouvelle référence.")] = None,
        ledger_account_id: Annotated[Optional[int], Field(default=None, description="Nouvel ID de compte comptable.")] = None,
    ) -> str:
        """Modifie un produit existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if label is not None:
                body["label"] = label
            if price_before_tax is not None:
                body["price_before_tax"] = price_before_tax
            if vat_rate is not None:
                body["vat_rate"] = vat_rate
            if description is not None:
                body["description"] = description
            if unit is not None:
                body["unit"] = unit
            if reference is not None:
                body["reference"] = reference
            if ledger_account_id is not None:
                body["ledger_account_id"] = ledger_account_id

            data = await api_put(f"/products/{id}", body)
            return f"✅ Produit {id} mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
