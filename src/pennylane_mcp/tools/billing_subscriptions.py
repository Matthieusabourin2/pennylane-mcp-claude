"""Outils MCP : abonnements de facturation (Billing Subscriptions)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des abonnements de facturation."""

    # ── Lister les abonnements ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_billing_subscriptions",
        annotations={
            "title": "Lister les abonnements",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_billing_subscriptions(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        customer_id: Annotated[Optional[int], Field(default=None, description="Filtrer par ID client.")] = None,
        status: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par statut.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les abonnements de facturation récurrente avec filtres et pagination.
        Utile pour consulter les abonnements actifs, filtrer par client ou statut.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if customer_id is not None:
                filters.append({"field": "customer_id", "operator": "eq", "value": customer_id})
            if status:
                filters.append({"field": "status", "operator": "eq", "value": status})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/billing_subscriptions", qp)
            items = data.get("items", [])
            result = {
                "billing_subscriptions": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Détail d'un abonnement ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_billing_subscription",
        annotations={
            "title": "Détail d'un abonnement",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_billing_subscription(
        id: Annotated[int, Field(description="Identifiant de l'abonnement.")],
    ) -> str:
        """Récupère le détail complet d'un abonnement de facturation."""
        try:
            data = await api_get(f"/billing_subscriptions/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un abonnement ───────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_billing_subscription",
        annotations={
            "title": "Créer un abonnement de facturation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_billing_subscription(
        customer_id: Annotated[int, Field(description="ID du client.")],
        start: Annotated[str, Field(description="Date de début de l'abonnement (YYYY-MM-DD).")],
        recurring_rule: Annotated[dict, Field(
            description=(
                "Règle de récurrence. Ex: "
                "{'type': 'monthly', 'interval': 1} ou "
                "{'type': 'yearly', 'interval': 1, 'day_of_month': 1}. "
                "Types: 'weekly', 'monthly', 'yearly'."
            ),
        )],
        payment_conditions: Annotated[str, Field(
            description=(
                "Conditions de paiement : 'upon_receipt', '7_days', '15_days', "
                "'30_days', '30_days_end_of_month', '45_days', '45_days_end_of_month', '60_days'."
            ),
        )],
        payment_method: Annotated[str, Field(
            description="Méthode de paiement : 'offline' ou 'gocardless_direct_debit'.",
        )],
        invoice_lines: Annotated[list, Field(
            description=(
                "Lignes de facturation. Chaque ligne : "
                "{label: str, quantity: number, raw_currency_unit_price: str, "
                "unit: str, vat_rate: str, product_id?: int, description?: str}."
            ),
        )],
        mode: Annotated[Optional[dict], Field(
            default=None,
            description=(
                "Mode de facturation : {'type': 'email', 'email_settings': {...}} "
                "ou {'type': 'awaiting_validation'} ou {'type': 'finalized'}."
            ),
        )] = None,
        label: Annotated[Optional[str], Field(default=None, description="Libellé de l'abonnement.")] = None,
    ) -> str:
        """Crée un nouvel abonnement de facturation récurrente.
        Nécessite un client, une date de début, une règle de récurrence et des lignes.
        """
        try:
            body: dict = {
                "customer_id": customer_id,
                "start": start,
                "recurring_rule": recurring_rule,
                "payment_conditions": payment_conditions,
                "payment_method": payment_method,
                "customer_invoice_data": {"invoice_lines": invoice_lines},
            }
            if mode:
                body["mode"] = mode
            else:
                body["mode"] = {"type": "awaiting_validation"}
            if label:
                body["label"] = label

            data = await api_post("/billing_subscriptions", body)
            return (
                f"✅ Abonnement créé (id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Modifier un abonnement ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_billing_subscription",
        annotations={
            "title": "Modifier un abonnement",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_billing_subscription(
        id: Annotated[int, Field(description="Identifiant de l'abonnement à modifier.")],
        start: Annotated[Optional[str], Field(default=None, description="Nouvelle date de début (YYYY-MM-DD).")] = None,
        recurring_rule: Annotated[Optional[dict], Field(default=None, description="Nouvelle règle de récurrence.")] = None,
        payment_conditions: Annotated[Optional[str], Field(default=None, description="Nouvelles conditions de paiement.")] = None,
        payment_method: Annotated[Optional[str], Field(default=None, description="Nouvelle méthode de paiement.")] = None,
        label: Annotated[Optional[str], Field(default=None, description="Nouveau libellé.")] = None,
    ) -> str:
        """Modifie un abonnement de facturation existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if start is not None:
                body["start"] = start
            if recurring_rule is not None:
                body["recurring_rule"] = recurring_rule
            if payment_conditions is not None:
                body["payment_conditions"] = payment_conditions
            if payment_method is not None:
                body["payment_method"] = payment_method
            if label is not None:
                body["label"] = label

            data = await api_put(f"/billing_subscriptions/{id}", body)
            return f"✅ Abonnement mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lignes d'un abonnement ────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_subscription_lines",
        annotations={
            "title": "Lignes d'un abonnement",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_subscription_lines(
        subscription_id: Annotated[int, Field(description="ID de l'abonnement.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes de facturation d'un abonnement."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/billing_subscriptions/{subscription_id}/invoice_lines", qp)
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

    # ── Sections d'un abonnement ──────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_subscription_sections",
        annotations={
            "title": "Sections d'un abonnement",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_subscription_sections(
        subscription_id: Annotated[int, Field(description="ID de l'abonnement.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
    ) -> str:
        """Liste les sections de lignes d'un abonnement de facturation."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/billing_subscriptions/{subscription_id}/invoice_line_sections", qp)
            items = data.get("items", [])
            result = {
                "invoice_line_sections": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"
