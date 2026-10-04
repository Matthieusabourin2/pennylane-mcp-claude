"""Outils MCP : gestion des factures clients (Customer Invoices)."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


# Champs du mode compact : de quoi répondre à « qui me doit combien depuis quand ».
_COMPACT_FIELDS = (
    "id", "invoice_number", "label", "date", "deadline",
    "currency_amount_before_tax", "amount", "remaining_amount_with_tax",
    "status", "paid", "draft",
)
_MAX_PAGES = 10  # 1 000 documents ; l'API limite à 25 requêtes par fenêtre.
_SERVER_SORTS = ("id", "-id", "date", "-date")
_LOCAL_SORTS = _SERVER_SORTS + ("deadline", "-deadline")


def _compact_invoice(inv: dict) -> dict:
    """Projection compacte d'une facture : ni URL de sous-ressource, ni public_file_url."""
    out = {k: inv.get(k) for k in _COMPACT_FIELDS}
    out["customer_id"] = (inv.get("customer") or {}).get("id")
    return out


def _without_file_url(inv: dict) -> dict:
    """Retire public_file_url : chaque lecture en régénère un et invalide les précédents."""
    return {k: v for k, v in inv.items() if k != "public_file_url"}


def _is_unpaid(inv: dict) -> bool:
    """Impayée = non rapprochée dans Pennylane : ni brouillon, ni archivée, ni annulée,
    reste dû TTC > 0. Le champ `paid` ne fait pas foi (les annulées ont paid=true)."""
    if inv.get("draft") or inv.get("status") in ("archived", "cancelled"):
        return False
    try:
        return float(inv.get("remaining_amount_with_tax") or 0) > 0
    except (TypeError, ValueError):
        return False


def _select(
    items: list[dict], unpaid_only: bool, deadline_before: str | None, sort: str,
    status: str | None = None,
) -> list[dict]:
    """Filtre local (statut, impayées, échéance strictement antérieure) puis tri."""
    kept = [
        i for i in items
        if (not status or i.get("status") == status)
        and (not unpaid_only or _is_unpaid(i))
        and (not deadline_before or (i.get("deadline") and i["deadline"] < deadline_before))
    ]
    field = sort.lstrip("-")
    present = [i for i in kept if i.get(field) is not None]
    missing = [i for i in kept if i.get(field) is None]
    return sorted(present, key=lambda i: i[field], reverse=sort.startswith("-")) + missing


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des factures clients."""

    # ── Lister les factures clients ──────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_customer_invoices",
        annotations={
            "title": "Lister les factures clients",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_customer_invoices(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination (ignoré en filtrage local).")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20 ; ignoré en filtrage local).")] = 20,
        customer_id: Annotated[Optional[int], Field(
            default=None,
            description="Filtrer par ID client (côté Pennylane).",
        )] = None,
        date_from: Annotated[Optional[str], Field(
            default=None,
            description="Date de facture minimale incluse, YYYY-MM-DD (côté Pennylane).",
        )] = None,
        date_to: Annotated[Optional[str], Field(
            default=None,
            description="Date de facture maximale incluse, YYYY-MM-DD (côté Pennylane).",
        )] = None,
        unpaid_only: Annotated[bool, Field(
            default=False,
            description="Seulement les impayées : ni brouillon, ni archivée, ni annulée, "
            "reste dû TTC > 0 (filtrage local).",
        )] = False,
        status: Annotated[Optional[str], Field(
            default=None,
            description="Statut exact (filtrage local) : 'upcoming', 'late', 'paid', 'cancelled', "
            "'archived', 'draft', 'credit_note'.",
        )] = None,
        deadline_before: Annotated[Optional[str], Field(
            default=None,
            description="Échéance strictement antérieure à cette date, YYYY-MM-DD (filtrage local). "
            "Avec unpaid_only=true et la date du jour : les factures en retard.",
        )] = None,
        sort: Annotated[Optional[str], Field(
            default=None,
            description="Tri : 'id', '-id', 'date', '-date' (défaut : '-id'). "
            "En filtrage local, aussi 'deadline', '-deadline' (défaut : 'deadline').",
        )] = None,
        detail: Annotated[bool, Field(
            default=False,
            description="true = JSON complet de chaque facture au lieu du mode compact.",
        )] = False,
    ) -> str:
        """Liste les factures clients (et avoirs, montant négatif), en mode compact par défaut.

        Filtré côté Pennylane : customer_id, date_from, date_to. L'API ne filtre ni par
        statut, ni par échéance, ni par montant.
        Filtré localement : status, unpaid_only, deadline_before. Dans ce cas l'outil pagine seul
        (plafond 1 000 documents), renvoie toutes les correspondances et indique
        `is_complete` ; limit et cursor sont ignorés.

        « Payé » : le champ `paid` ne fait pas foi (les factures annulées ont paid=true).
        Seuls `status` et `remaining_amount_with_tax` comptent. « Impayée » veut dire
        « non rapprochée dans Pennylane » : pour savoir si l'argent est arrivé, voir Qonto.
        """
        try:
            for name, value in (("date_from", date_from), ("date_to", date_to), ("deadline_before", deadline_before)):
                if value:
                    try:
                        date.fromisoformat(value)
                    except ValueError:
                        return f"❌ {name} doit être au format YYYY-MM-DD (reçu : '{value}')."

            local = unpaid_only or bool(deadline_before) or bool(status)
            allowed = _LOCAL_SORTS if local else _SERVER_SORTS
            if sort and sort not in allowed:
                return (
                    f"❌ Tri '{sort}' non pris en charge ici. Valeurs possibles : {', '.join(allowed)}. "
                    "Le tri par échéance exige status, unpaid_only ou deadline_before."
                )

            filters: list[dict] = []
            if customer_id:
                filters.append({"field": "customer_id", "operator": "eq", "value": customer_id})
            if date_from:
                filters.append({"field": "date", "operator": "gteq", "value": date_from})
            if date_to:
                filters.append({"field": "date", "operator": "lteq", "value": date_to})
            base: dict = {"filter": json.dumps(filters)} if filters else {}
            shape = _without_file_url if detail else _compact_invoice

            if not local:
                qp: dict = {**base, "limit": limit}
                if cursor:
                    qp["cursor"] = cursor
                if sort:
                    qp["sort"] = sort
                data = await api_get("/customer_invoices", qp)
                items = data.get("items", [])
                result = {
                    "customer_invoices": [shape(i) for i in items],
                    "pagination": pagination_summary(
                        data.get("has_more"), data.get("next_cursor"),
                        data.get("total_items"), len(items),
                    ),
                    "next_cursor": data.get("next_cursor"),
                }
                return truncate_if_needed(to_json(result))

            fetched: list[dict] = []
            page_cursor: str | None = None
            pages = 0
            is_complete = False
            while pages < _MAX_PAGES:
                qp = {**base, "limit": 100}
                if page_cursor:
                    qp["cursor"] = page_cursor
                data = await api_get("/customer_invoices", qp)
                fetched.extend(data.get("items", []))
                pages += 1
                if not data.get("has_more"):
                    is_complete = True
                    break
                page_cursor = data.get("next_cursor")
                if not page_cursor:
                    break

            matched = _select(fetched, unpaid_only, deadline_before, sort or "deadline", status)
            # Compteurs en tête : une troncature éventuelle coupe la liste, pas eux.
            result = {
                "count": len(matched),
                "scanned": len(fetched),
                "pages_fetched": pages,
                "is_complete": is_complete,
                "customer_invoices": [shape(i) for i in matched],
            }
            return truncate_if_needed(
                to_json(result),
                hint="Resserrez la période (date_from, date_to) ou filtrez par client.",
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer une facture client ─────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_customer_invoice",
        annotations={
            "title": "Détail d'une facture client",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_customer_invoice(
        id: Annotated[int, Field(description="Identifiant unique de la facture client.")],
    ) -> str:
        """Récupère le détail complet d'une facture client par son identifiant, en un appel.
        Les lignes (`invoice_lines`), les paiements (`payments`) et les transactions
        bancaires rapprochées (`matched_transactions`) sont intégrés, au lieu de leurs URL.
        Listes `payments` et `matched_transactions` vides = facture non rapprochée dans
        Pennylane ; pour savoir si l'argent est arrivé, voir Qonto.
        """
        try:
            base = f"/customer_invoices/{id}"
            keys = ("invoice_lines", "payments", "matched_transactions")
            inv, *subs = await asyncio.gather(
                api_get(base),
                *(api_get(f"{base}/{key}", {"limit": 100}) for key in keys),
                return_exceptions=True,
            )
            if isinstance(inv, Exception):
                raise inv
            data = _without_file_url(inv)
            for key, sub in zip(keys, subs):
                if isinstance(sub, Exception):
                    data[key] = None
                    data[f"{key}_error"] = str(sub)
                    continue
                data[key] = [_without_file_url(x) for x in sub.get("items", [])]
                if sub.get("has_more"):
                    data[f"{key}_has_more"] = True
            return truncate_if_needed(to_json(data))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer une facture client ─────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_customer_invoice",
        annotations={
            "title": "Créer une facture client",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_customer_invoice(
        customer_id: Annotated[int, Field(description="ID du client à facturer.")],
        date: Annotated[str, Field(description="Date de la facture (YYYY-MM-DD).")],
        deadline: Annotated[str, Field(description="Date d'échéance (YYYY-MM-DD).")],
        invoice_lines: Annotated[list, Field(
            description="Lignes de facture. Chaque ligne : "
            "{product_id: int, quantity: number, label: str, unit: str, "
            "vat_rate: str, price_before_tax: str, discount: str (optionnel)}.",
        )],
        currency: Annotated[Optional[str], Field(default=None, description="Code devise (défaut: EUR).")] = None,
        special_mention: Annotated[Optional[str], Field(default=None, description="Mention spéciale sur la facture.")] = None,
        draft: Annotated[bool, Field(default=True, description="Créer en brouillon (défaut: true).")] = True,
    ) -> str:
        """Crée une nouvelle facture client (brouillon par défaut).
        Nécessite un client, une date, une échéance et au moins une ligne.
        """
        try:
            body: dict = {
                "customer_id": customer_id,
                "date": date,
                "deadline": deadline,
                "invoice_lines": invoice_lines,
                "draft": draft,
            }
            if currency:
                body["currency"] = currency
            if special_mention:
                body["special_mention"] = special_mention

            data = await api_post("/customer_invoices", body)
            status_label = "brouillon" if data.get("draft") or data.get("status") == "draft" else "finalisée"
            return (
                f"✅ Facture client créée ({status_label}) — "
                f"id: {data.get('id')}, numéro: {data.get('invoice_number', 'N/A')}.\n\n"
                f"{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour une facture client ─────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_customer_invoice",
        annotations={
            "title": "Modifier une facture client",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_customer_invoice(
        id: Annotated[int, Field(description="Identifiant de la facture à modifier.")],
        date: Annotated[Optional[str], Field(default=None, description="Nouvelle date (YYYY-MM-DD).")] = None,
        deadline: Annotated[Optional[str], Field(default=None, description="Nouvelle échéance (YYYY-MM-DD).")] = None,
        customer_id: Annotated[Optional[int], Field(default=None, description="Nouvel ID client.")] = None,
        special_mention: Annotated[Optional[str], Field(default=None, description="Mention spéciale.")] = None,
        invoice_lines: Annotated[Optional[list], Field(
            default=None,
            description="Nouvelles lignes de facture (remplace les existantes).",
        )] = None,
    ) -> str:
        """Modifie une facture client (brouillon uniquement).
        Seuls les champs fournis sont mis à jour.
        """
        try:
            body: dict = {}
            if date is not None:
                body["date"] = date
            if deadline is not None:
                body["deadline"] = deadline
            if customer_id is not None:
                body["customer_id"] = customer_id
            if special_mention is not None:
                body["special_mention"] = special_mention
            if invoice_lines is not None:
                body["invoice_lines"] = invoice_lines

            data = await api_put(f"/customer_invoices/{id}", body)
            return f"✅ Facture client {id} mise à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister les lignes d'une facture client ───────────────────────────────

    @mcp.tool(
        name="pennylane_list_customer_invoice_lines",
        annotations={
            "title": "Lignes d'une facture client",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_customer_invoice_lines(
        customer_invoice_id: Annotated[int, Field(description="ID de la facture client.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes (articles) d'une facture client spécifique."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(f"/customer_invoices/{customer_invoice_id}/invoice_lines", qp)
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

    # ── Finaliser une facture client ─────────────────────────────────────────

    @mcp.tool(
        name="pennylane_finalize_customer_invoice",
        annotations={
            "title": "Finaliser une facture client",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_finalize_customer_invoice(
        id: Annotated[int, Field(description="Identifiant de la facture brouillon à finaliser.")],
    ) -> str:
        """Transforme un brouillon de facture client en facture finalisée.
        Attention : cette action est irréversible. La facture reçoit un numéro définitif.
        """
        try:
            data = await api_put(f"/customer_invoices/{id}/finalize", {})
            return (
                f"✅ Facture client {id} finalisée — "
                f"numéro: {data.get('invoice_number', 'N/A')}.\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Marquer comme payée ──────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_mark_customer_invoice_paid",
        annotations={
            "title": "Marquer une facture client comme payée",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_mark_customer_invoice_paid(
        id: Annotated[int, Field(description="Identifiant de la facture à marquer comme payée.")],
    ) -> str:
        """Marque une facture client finalisée comme payée."""
        try:
            data = await api_put(f"/customer_invoices/{id}/mark_as_paid", {})
            return f"✅ Facture client {id} marquée comme payée.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
