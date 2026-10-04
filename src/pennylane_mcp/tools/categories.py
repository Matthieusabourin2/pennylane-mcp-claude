"""Outils MCP : catégories analytiques (Analytics / Categories)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des catégories analytiques."""

    # ── Lister les groupes de catégories ──────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_category_groups",
        annotations={
            "title": "Lister les groupes de catégories",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_category_groups(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
    ) -> str:
        """Liste tous les groupes de catégories analytiques.
        Chaque groupe contient des catégories utilisées pour la ventilation analytique.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get("/category_groups", qp)
            items = data.get("items", [])
            result = {
                "category_groups": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Détail d'un groupe de catégories ──────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_category_group",
        annotations={
            "title": "Détail d'un groupe de catégories",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_category_group(
        id: Annotated[int, Field(description="Identifiant du groupe de catégories.")],
    ) -> str:
        """Récupère le détail d'un groupe de catégories par son identifiant."""
        try:
            data = await api_get(f"/category_groups/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister les catégories ─────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_categories",
        annotations={
            "title": "Lister les catégories analytiques",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_categories(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        category_group_id: Annotated[Optional[int], Field(
            default=None,
            description="Filtrer par ID de groupe de catégories.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les catégories analytiques avec filtres et pagination.
        Utile pour consulter les axes analytiques disponibles.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if category_group_id is not None:
                filters.append({"field": "category_group_id", "operator": "eq", "value": category_group_id})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/categories", qp)
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

    # ── Détail d'une catégorie ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_category",
        annotations={
            "title": "Détail d'une catégorie",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_category(
        id: Annotated[int, Field(description="Identifiant de la catégorie.")],
    ) -> str:
        """Récupère le détail d'une catégorie analytique par son identifiant."""
        try:
            data = await api_get(f"/categories/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Catégories d'un groupe ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_group_categories",
        annotations={
            "title": "Catégories d'un groupe",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_group_categories(
        category_group_id: Annotated[int, Field(description="ID du groupe de catégories.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
    ) -> str:
        """Liste les catégories appartenant à un groupe spécifique."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/category_groups/{category_group_id}/categories", qp)
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

    # ── Créer une catégorie ───────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_category",
        annotations={
            "title": "Créer une catégorie analytique",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_category(
        label: Annotated[str, Field(description="Libellé de la catégorie.")],
        category_group_id: Annotated[int, Field(description="ID du groupe de catégories.")],
        direction: Annotated[Optional[str], Field(
            default=None,
            description="Direction : 'cash_in' ou 'cash_out' (catégories trésorerie uniquement).",
        )] = None,
        analytical_code: Annotated[Optional[str], Field(
            default=None,
            description="Code analytique.",
        )] = None,
    ) -> str:
        """Crée une nouvelle catégorie analytique dans un groupe.
        Le libellé et l'ID de groupe sont obligatoires.
        """
        try:
            body: dict = {"label": label, "category_group_id": category_group_id}
            if direction:
                body["direction"] = direction
            if analytical_code is not None:
                body["analytical_code"] = analytical_code

            data = await api_post("/categories", body)
            return (
                f"✅ Catégorie '{data.get('label')}' créée "
                f"(id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Modifier une catégorie ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_category",
        annotations={
            "title": "Modifier une catégorie",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_category(
        id: Annotated[int, Field(description="Identifiant de la catégorie à modifier.")],
        label: Annotated[Optional[str], Field(default=None, description="Nouveau libellé.")] = None,
        direction: Annotated[Optional[str], Field(
            default=None,
            description="Direction : 'cash_in', 'cash_out' (trésorerie uniquement).",
        )] = None,
        analytical_code: Annotated[Optional[str], Field(default=None, description="Code analytique.")] = None,
    ) -> str:
        """Modifie une catégorie analytique existante. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if label is not None:
                body["label"] = label
            if direction is not None:
                body["direction"] = direction
            if analytical_code is not None:
                body["analytical_code"] = analytical_code

            data = await api_put(f"/categories/{id}", body)
            return f"✅ Catégorie mise à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
