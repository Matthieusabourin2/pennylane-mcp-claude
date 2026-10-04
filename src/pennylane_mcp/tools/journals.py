"""Outils MCP : gestion des journaux comptables."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les 3 outils journaux."""

    @mcp.tool(
        name="pennylane_list_journals",
        annotations={
            "title": "Lister les journaux comptables",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_journals(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
        type_filter: Annotated[Optional[str], Field(
            default=None,
            description="Type de journal (sales, purchases, bank, payroll, miscellaneous).",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id' ou '-id'.")] = None,
    ) -> str:
        """Liste tous les journaux comptables (ventes, achats, banque, OD, paie...)
        avec filtres optionnels par type.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort
            if type_filter:
                qp["filter"] = json.dumps([{"field": "type", "operator": "eq", "value": type_filter}])

            data = await api_get("/journals", qp)
            items = data.get("items", [])
            result = {
                "journals": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    @mcp.tool(
        name="pennylane_get_journal",
        annotations={
            "title": "Détail d'un journal",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_journal(
        id: Annotated[int, Field(description="Identifiant unique du journal.")],
    ) -> str:
        """Récupère le détail d'un journal comptable par son identifiant."""
        try:
            data = await api_get(f"/journals/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    @mcp.tool(
        name="pennylane_create_journal",
        annotations={
            "title": "Créer un journal comptable",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_journal(
        code: Annotated[str, Field(
            min_length=2,
            max_length=5,
            description="Code du journal (2-5 lettres). Ex: 'VE' ventes, 'HA' achats, 'BQ' banque, 'OD' opérations diverses.",
        )],
        label: Annotated[str, Field(description="Libellé du journal.")],
    ) -> str:
        """Crée un nouveau journal comptable.
        Codes classiques : VE (ventes), HA (achats), BQ (banque),
        OD (opérations diverses), PA (paie), RB (reprise de balance).
        """
        try:
            data = await api_post("/journals", {"code": code, "label": label})
            return (
                f"✅ Journal {data.get('code')} - {data.get('label')} créé "
                f"(id: {data.get('id')}, type: {data.get('type')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"
