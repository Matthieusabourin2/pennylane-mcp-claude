"""Outils MCP : gestion des comptes comptables (Ledger Accounts)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les 4 outils comptes comptables."""

    # ── Lister ──────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_accounts",
        annotations={
            "title": "Lister les comptes comptables",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_accounts(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=1000, description="Nombre de résultats (1-1000, défaut: 50).")] = 50,
        number_prefix: Annotated[Optional[str], Field(
            default=None,
            description="Filtre par préfixe de numéro de compte "
            "(ex: '411' clients, '401' fournisseurs, '512' banque).",
        )] = None,
        enabled_only: Annotated[bool, Field(default=True, description="Retourner uniquement les comptes actifs (défaut: true).")] = True,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id' ou '-id'.")] = None,
    ) -> str:
        """Liste les comptes du plan comptable avec filtres et pagination.
        Utile pour consulter le plan comptable, chercher un compte par préfixe
        (411=clients, 401=fournisseurs, 512=banque, 6=charges, 7=produits).
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if number_prefix:
                filters.append({"field": "number", "operator": "start_with", "value": number_prefix})
            if enabled_only:
                filters.append({"field": "enabled", "operator": "eq", "value": True})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/ledger_accounts", qp)
            items = data.get("items", [])
            result = {
                "accounts": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer ───────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_account",
        annotations={
            "title": "Détail d'un compte comptable",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_account(
        id: Annotated[int, Field(description="Identifiant unique du compte comptable.")],
    ) -> str:
        """Récupère le détail d'un compte comptable par son identifiant."""
        try:
            data = await api_get(f"/ledger_accounts/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer ───────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_account",
        annotations={
            "title": "Créer un compte comptable",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_account(
        number: Annotated[str, Field(
            description="Numéro du compte (ex: '411001' client, '401001' fournisseur, '512000' banque). "
            "401→fournisseur auto-créé, 411→client auto-créé.",
        )],
        label: Annotated[str, Field(description="Libellé du compte comptable.")],
        vat_rate: Annotated[Optional[str], Field(
            default=None,
            description="Taux de TVA (ex: 'FR_200' pour 20%, 'FR_100' pour 10%, 'exempt').",
        )] = None,
        country_alpha2: Annotated[Optional[str], Field(
            default=None, description="Code pays ISO alpha-2 (ex: 'FR'). Défaut: FR.",
        )] = None,
    ) -> str:
        """Crée un nouveau compte dans le plan comptable.
        Un numéro commençant par 401 crée automatiquement un fournisseur,
        par 411 un client.
        """
        try:
            body: dict = {"number": number, "label": label}
            if vat_rate:
                body["vat_rate"] = vat_rate
            if country_alpha2:
                body["country_alpha2"] = country_alpha2

            data = await api_post("/ledger_accounts", body)
            return (
                f"✅ Compte {data.get('number')} - {data.get('label')} créé "
                f"(id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Modifier ────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_account",
        annotations={
            "title": "Modifier un compte comptable",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_account(
        id: Annotated[int, Field(description="Identifiant du compte à modifier.")],
        label: Annotated[Optional[str], Field(default=None, description="Nouveau libellé du compte.")] = None,
        letterable: Annotated[Optional[bool], Field(default=None, description="Activer/désactiver le lettrage.")] = None,
    ) -> str:
        """Modifie le libellé ou le statut lettrable d'un compte existant."""
        try:
            body: dict = {}
            if label is not None:
                body["label"] = label
            if letterable is not None:
                body["letterable"] = letterable

            data = await api_put(f"/ledger_accounts/{id}", body)
            return f"✅ Compte {data.get('number')} mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
