"""Outils MCP : gestion des factures fournisseurs (Supplier Invoices)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des factures fournisseurs."""

    # ── Lister les factures fournisseurs ─────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_supplier_invoices",
        annotations={
            "title": "Lister les factures fournisseurs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_supplier_invoices(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        status: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par statut : 'pending', 'accounted', 'paid'.",
        )] = None,
        supplier_id: Annotated[Optional[int], Field(
            default=None,
            description="Filtrer par ID fournisseur.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les factures fournisseurs avec filtres et pagination.
        Utile pour consulter les factures reçues, filtrer par statut ou fournisseur.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if status:
                filters.append({"field": "status", "operator": "eq", "value": status})
            if supplier_id:
                filters.append({"field": "supplier_id", "operator": "eq", "value": supplier_id})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/supplier_invoices", qp)
            items = data.get("items", [])
            result = {
                "supplier_invoices": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer une facture fournisseur ────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_supplier_invoice",
        annotations={
            "title": "Détail d'une facture fournisseur",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_supplier_invoice(
        id: Annotated[int, Field(description="Identifiant unique de la facture fournisseur.")],
    ) -> str:
        """Récupère le détail complet d'une facture fournisseur.
        Retourne toutes les informations : montants, lignes, statut, fournisseur.
        """
        try:
            data = await api_get(f"/supplier_invoices/{id}")
            return truncate_if_needed(to_json(data))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour une facture fournisseur ────────────────────────────────

    @mcp.tool(
        name="pennylane_update_supplier_invoice",
        annotations={
            "title": "Modifier une facture fournisseur",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_supplier_invoice(
        id: Annotated[int, Field(description="Identifiant de la facture fournisseur à modifier.")],
        date: Annotated[Optional[str], Field(default=None, description="Nouvelle date (YYYY-MM-DD).")] = None,
        deadline: Annotated[Optional[str], Field(default=None, description="Nouvelle échéance (YYYY-MM-DD).")] = None,
        supplier_id: Annotated[Optional[int], Field(default=None, description="Nouvel ID fournisseur.")] = None,
        invoice_number: Annotated[Optional[str], Field(default=None, description="Numéro de facture.")] = None,
    ) -> str:
        """Modifie une facture fournisseur. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if date is not None:
                body["date"] = date
            if deadline is not None:
                body["deadline"] = deadline
            if supplier_id is not None:
                body["supplier_id"] = supplier_id
            if invoice_number is not None:
                body["invoice_number"] = invoice_number

            data = await api_put(f"/supplier_invoices/{id}", body)
            return f"✅ Facture fournisseur {id} mise à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister les lignes d'une facture fournisseur ──────────────────────────

    @mcp.tool(
        name="pennylane_list_supplier_invoice_lines",
        annotations={
            "title": "Lignes d'une facture fournisseur",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_supplier_invoice_lines(
        supplier_invoice_id: Annotated[int, Field(description="ID de la facture fournisseur.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes (articles) d'une facture fournisseur spécifique."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/supplier_invoices/{supplier_invoice_id}/invoice_lines", qp)
            items = data.get("items", [])
            result = {
                "invoice_lines": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour le statut de paiement ──────────────────────────────────

    @mcp.tool(
        name="pennylane_update_supplier_invoice_payment_status",
        annotations={
            "title": "Modifier le statut de paiement d'une facture fournisseur",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_supplier_invoice_payment_status(
        supplier_invoice_id: Annotated[int, Field(description="ID de la facture fournisseur.")],
        payment_status: Annotated[str, Field(
            description="Nouveau statut : 'unpaid', 'paid', 'partially_paid'.",
        )],
    ) -> str:
        """Met à jour le statut de paiement d'une facture fournisseur."""
        try:
            body = {"payment_status": payment_status}
            data = await api_put(
                f"/supplier_invoices/{supplier_invoice_id}/payment_status",
                body,
            )
            return (
                f"✅ Statut de paiement de la facture fournisseur {supplier_invoice_id} "
                f"mis à jour → {payment_status}.\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"
