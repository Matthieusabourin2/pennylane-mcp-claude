"""Outils MCP : gestion des écritures comptables (Ledger Entries)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..models import EntryLineInput, EntryLineUpdateItem
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les 5 outils écritures comptables."""

    # ── Lister ──────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_entries",
        annotations={
            "title": "Lister les écritures comptables",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_entries(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        journal_id: Annotated[Optional[int], Field(default=None, description="Filtrer par ID de journal.")] = None,
        date_from: Annotated[Optional[str], Field(default=None, description="Date de début (YYYY-MM-DD).")] = None,
        date_to: Annotated[Optional[str], Field(default=None, description="Date de fin (YYYY-MM-DD).")] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id', 'date', '-date'.")] = None,
    ) -> str:
        """Liste les écritures comptables (pièces) avec filtres par journal et
        période. Chaque écriture contient des lignes équilibrées (débit = crédit).
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
            if date_from:
                filters.append({"field": "date", "operator": "gteq", "value": date_from})
            if date_to:
                filters.append({"field": "date", "operator": "lteq", "value": date_to})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/ledger_entries", qp)
            items = data.get("items", [])
            result = {
                "entries": items,
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
        name="pennylane_get_entry",
        annotations={
            "title": "Détail d'une écriture comptable",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_entry(
        id: Annotated[int, Field(description="Identifiant unique de l'écriture comptable.")],
    ) -> str:
        """Récupère le détail complet d'une écriture comptable avec toutes ses lignes."""
        try:
            data = await api_get(f"/ledger_entries/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer ───────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_entry",
        annotations={
            "title": "Créer une écriture comptable",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_entry(
        date: Annotated[str, Field(description="Date de l'écriture (YYYY-MM-DD).")],
        label: Annotated[str, Field(description="Libellé de l'écriture.")],
        journal_id: Annotated[int, Field(description="ID du journal comptable.")],
        ledger_entry_lines: Annotated[list[EntryLineInput], Field(
            min_length=1,
            max_length=1000,
            description="Lignes d'écriture. Chaque ligne : {ledger_account_id: int, debit: str, credit: str, label?: str, piece_number?: str}. TOTAL DÉBIT = TOTAL CRÉDIT obligatoire.",
        )],
        currency: Annotated[str, Field(default="EUR", description="Code devise (défaut: EUR).")] = "EUR",
        due_date: Annotated[Optional[str], Field(default=None, description="Date d'échéance (YYYY-MM-DD).")] = None,
        piece_number: Annotated[Optional[str], Field(default=None, description="Numéro de pièce.")] = None,
    ) -> str:
        """Crée une nouvelle écriture comptable avec ses lignes.
        RÈGLE FONDAMENTALE : total débits = total crédits.
        Les montants sont des strings (ex: '1500.00').
        """
        try:
            body: dict = {
                "date": date,
                "label": label,
                "journal_id": journal_id,
                "currency": currency,
                "ledger_entry_lines": [
                    line.model_dump(exclude_none=True)
                    for line in ledger_entry_lines
                ],
            }
            if due_date:
                body["due_date"] = due_date
            if piece_number:
                body["piece_number"] = piece_number

            data = await api_post("/ledger_entries", body)
            journal = data.get("journal", {})
            return (
                f"✅ Écriture créée (id: {data.get('id')}, date: {data.get('date')}, "
                f"journal: {journal.get('code')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Modifier ────────────────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_entry",
        annotations={
            "title": "Modifier une écriture comptable",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_entry(
        id: Annotated[int, Field(description="Identifiant de l'écriture à modifier.")],
        date: Annotated[Optional[str], Field(default=None, description="Nouvelle date (YYYY-MM-DD).")] = None,
        label: Annotated[Optional[str], Field(default=None, description="Nouveau libellé.")] = None,
        journal_id: Annotated[Optional[int], Field(default=None, description="Nouvel ID de journal.")] = None,
        currency: Annotated[Optional[str], Field(default=None, description="Nouvelle devise.")] = None,
        piece_number: Annotated[Optional[str], Field(default=None, description="Numéro de pièce.")] = None,
        lines_to_create: Annotated[Optional[list[EntryLineInput]], Field(
            default=None, description="Nouvelles lignes à ajouter.",
        )] = None,
        lines_to_update: Annotated[Optional[list[EntryLineUpdateItem]], Field(
            default=None, description="Lignes existantes à modifier (chaque élément doit contenir l'id de la ligne).",
        )] = None,
        lines_to_delete: Annotated[Optional[list[int]], Field(
            default=None, description="IDs des lignes à supprimer.",
        )] = None,
    ) -> str:
        """Modifie une écriture existante. Permet de changer l'en-tête
        et de créer/modifier/supprimer des lignes. L'écriture doit rester équilibrée.
        """
        try:
            body: dict = {}
            if date:
                body["date"] = date
            if label:
                body["label"] = label
            if journal_id:
                body["journal_id"] = journal_id
            if currency:
                body["currency"] = currency
            if piece_number:
                body["piece_number"] = piece_number

            lines_ops: dict = {}
            if lines_to_create:
                lines_ops["create"] = [l.model_dump(exclude_none=True) for l in lines_to_create]
            if lines_to_update:
                lines_ops["update"] = [l.model_dump(exclude_none=True) for l in lines_to_update]
            if lines_to_delete:
                lines_ops["delete"] = [{"id": lid} for lid in lines_to_delete]
            if lines_ops:
                body["ledger_entry_lines"] = lines_ops

            data = await api_put(f"/ledger_entries/{id}", body)
            return f"✅ Écriture {data.get('id')} mise à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Lister les lignes d'une écriture ────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_entry_lines",
        annotations={
            "title": "Lignes d'une écriture",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_entry_lines(
        ledger_entry_id: Annotated[int, Field(description="ID de l'écriture comptable.")],
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=50, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 50).")] = 50,
    ) -> str:
        """Liste les lignes d'écriture d'une pièce comptable spécifique."""
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor

            data = await api_get(
                f"/ledger_entries/{ledger_entry_id}/ledger_entry_lines", qp
            )
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
