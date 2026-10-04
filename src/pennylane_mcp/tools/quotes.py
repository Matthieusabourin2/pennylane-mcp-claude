"""Outils MCP : devis (Quotes)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


# Champs du mode compact de la liste des devis.
_COMPACT_FIELDS = (
    "id", "quote_number", "label", "date", "deadline",
    "currency_amount_before_tax", "amount", "status",
)


def _compact_quote(quote: dict) -> dict:
    """Projection compacte d'un devis : ni URL de sous-ressource, ni public_file_url."""
    out = {k: quote.get(k) for k in _COMPACT_FIELDS}
    out["customer_id"] = (quote.get("customer") or {}).get("id")
    return out


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des devis."""

    # ── Lister les devis ──────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_quotes",
        annotations={
            "title": "Lister les devis",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_quotes(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        customer_id: Annotated[Optional[int], Field(default=None, description="Filtrer par ID client.")] = None,
        status: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par statut : 'pending', 'accepted', 'denied', 'invoiced', 'expired'.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
        detail: Annotated[bool, Field(
            default=False,
            description="true = JSON complet de chaque devis au lieu du mode compact.",
        )] = False,
    ) -> str:
        """Liste les devis avec filtres et pagination, en mode compact par défaut.
        Utile pour consulter les devis émis, filtrer par statut ou client.
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

            data = await api_get("/quotes", qp)
            items = data.get("items", [])
            result = {
                "quotes": [
                    {k: v for k, v in q.items() if k != "public_file_url"} if detail else _compact_quote(q)
                    for q in items
                ],
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Détail d'un devis ─────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_quote",
        annotations={
            "title": "Détail d'un devis",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_quote(
        id: Annotated[int, Field(description="Identifiant unique du devis.")],
    ) -> str:
        """Récupère le détail complet d'un devis par son identifiant.
        Retourne toutes les informations : montants, lignes, statut, client.
        """
        try:
            data = await api_get(f"/quotes/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un devis ────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_quote",
        annotations={
            "title": "Créer un devis",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_quote(
        customer_id: Annotated[int, Field(description="ID du client à devisé.")],
        date: Annotated[str, Field(description="Date du devis (YYYY-MM-DD).")],
        deadline: Annotated[str, Field(description="Date limite de validité (YYYY-MM-DD).")],
        invoice_lines: Annotated[list, Field(
            description=(
                "Lignes du devis. Chaque ligne : "
                "{label: str, quantity: number, raw_currency_unit_price: str, "
                "unit: str, vat_rate: str, product_id?: int, description?: str, "
                "section_rank?: int}."
            ),
        )],
        currency: Annotated[Optional[str], Field(default=None, description="Code devise (défaut: EUR).")] = None,
        pdf_invoice_subject: Annotated[Optional[str], Field(default=None, description="Objet du devis PDF.")] = None,
        pdf_invoice_free_text: Annotated[Optional[str], Field(default=None, description="Texte libre du devis PDF.")] = None,
        special_mention: Annotated[Optional[str], Field(default=None, description="Mention spéciale sur le devis.")] = None,
        language: Annotated[Optional[str], Field(
            default=None,
            description="Langue : 'fr_FR' ou 'en_GB' (défaut: fr_FR).",
        )] = None,
    ) -> str:
        """Crée un nouveau devis.
        Nécessite un client, une date, une échéance et au moins une ligne.
        """
        try:
            body: dict = {
                "customer_id": customer_id,
                "date": date,
                "deadline": deadline,
                "invoice_lines": invoice_lines,
            }
            if currency:
                body["currency"] = currency
            if pdf_invoice_subject:
                body["pdf_invoice_subject"] = pdf_invoice_subject
            if pdf_invoice_free_text:
                body["pdf_invoice_free_text"] = pdf_invoice_free_text
            if special_mention:
                body["special_mention"] = special_mention
            if language:
                body["language"] = language

            data = await api_post("/quotes", body)
            return (
                f"✅ Devis créé (id: {data.get('id')}, "
                f"statut: {data.get('status')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Modifier un devis ─────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_quote",
        annotations={
            "title": "Modifier un devis",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_quote(
        id: Annotated[int, Field(description="Identifiant du devis à modifier.")],
        date: Annotated[Optional[str], Field(default=None, description="Nouvelle date (YYYY-MM-DD).")] = None,
        deadline: Annotated[Optional[str], Field(default=None, description="Nouvelle échéance (YYYY-MM-DD).")] = None,
        customer_id: Annotated[Optional[int], Field(default=None, description="Nouvel ID client.")] = None,
        currency: Annotated[Optional[str], Field(default=None, description="Nouvelle devise.")] = None,
        special_mention: Annotated[Optional[str], Field(default=None, description="Mention spéciale.")] = None,
        pdf_invoice_subject: Annotated[Optional[str], Field(default=None, description="Objet du devis PDF.")] = None,
        pdf_invoice_free_text: Annotated[Optional[str], Field(default=None, description="Texte libre PDF.")] = None,
    ) -> str:
        """Modifie un devis existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if date is not None:
                body["date"] = date
            if deadline is not None:
                body["deadline"] = deadline
            if customer_id is not None:
                body["customer_id"] = customer_id
            if currency is not None:
                body["currency"] = currency
            if special_mention is not None:
                body["special_mention"] = special_mention
            if pdf_invoice_subject is not None:
                body["pdf_invoice_subject"] = pdf_invoice_subject
            if pdf_invoice_free_text is not None:
                body["pdf_invoice_free_text"] = pdf_invoice_free_text

            data = await api_put(f"/quotes/{id}", body)
            return f"✅ Devis mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour le statut d'un devis ────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_quote_status",
        annotations={
            "title": "Mettre à jour le statut d'un devis",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_quote_status(
        id: Annotated[int, Field(description="Identifiant du devis.")],
        status: Annotated[str, Field(
            description="Nouveau statut : 'pending', 'accepted', 'denied', 'invoiced', 'expired'.",
        )],
    ) -> str:
        """Met à jour le statut d'un devis (accepté, refusé, facturé, etc.)."""
        try:
            data = await api_put(f"/quotes/{id}/update_status", {"status": status})
            return f"✅ Statut du devis mis à jour : {status}.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Envoyer un devis par email ────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_send_quote_by_email",
        annotations={
            "title": "Envoyer un devis par email",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_send_quote_by_email(
        id: Annotated[int, Field(description="Identifiant du devis à envoyer.")],
        recipients: Annotated[Optional[list], Field(
            default=None,
            description="Liste d'emails destinataires. Si vide, envoi aux emails du client.",
        )] = None,
    ) -> str:
        """Envoie un devis par email au client ou à des destinataires spécifiques."""
        try:
            body: dict = {}
            if recipients:
                body["recipients"] = recipients

            data = await api_post(f"/quotes/{id}/send_by_email", body)
            # L'API renvoie 204 (pas de body) en cas de succès
            if not data:
                return f"✅ Devis #{id} envoyé par email."
            return f"✅ Devis envoyé.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister les lignes d'un devis ──────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_quote_lines",
        annotations={
            "title": "Lignes d'un devis",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_quote_lines(
        quote_id: Annotated[int, Field(description="ID du devis.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes (articles) d'un devis spécifique."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/quotes/{quote_id}/invoice_lines", qp)
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

    # ── Lister les sections d'un devis ────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_quote_sections",
        annotations={
            "title": "Sections d'un devis",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_quote_sections(
        quote_id: Annotated[int, Field(description="ID du devis.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
    ) -> str:
        """Liste les sections de lignes d'un devis."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/quotes/{quote_id}/invoice_line_sections", qp)
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
