"""Outils MCP : gestion des fournisseurs (Suppliers)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des fournisseurs."""

    # ── Lister les fournisseurs ──────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_suppliers",
        annotations={
            "title": "Lister les fournisseurs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_suppliers(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        name: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par nom du fournisseur.",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les fournisseurs avec filtres et pagination.
        Utile pour consulter la base fournisseurs, rechercher un fournisseur par nom.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if name:
                filters.append({"field": "name", "operator": "eq", "value": name})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/suppliers", qp)
            items = data.get("items", [])
            result = {
                "suppliers": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer un fournisseur ─────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_supplier",
        annotations={
            "title": "Détail d'un fournisseur",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_supplier(
        id: Annotated[int, Field(description="Identifiant unique du fournisseur.")],
    ) -> str:
        """Récupère le détail d'un fournisseur par son identifiant.
        Retourne les informations complètes (adresse, SIRET, IBAN, conditions de paiement).
        """
        try:
            data = await api_get(f"/suppliers/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un fournisseur ─────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_supplier",
        annotations={
            "title": "Créer un fournisseur",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_supplier(
        name: Annotated[str, Field(description="Nom du fournisseur (raison sociale).")],
        reg_no: Annotated[Optional[str], Field(default=None, description="SIREN (9 chiffres).")] = None,
        establishment_no: Annotated[Optional[str], Field(default=None, description="SIRET (14 chiffres).")] = None,
        vat_number: Annotated[Optional[str], Field(default=None, description="Numéro de TVA intracommunautaire.")] = None,
        address: Annotated[Optional[str], Field(default=None, description="Adresse postale.")] = None,
        postal_code: Annotated[Optional[str], Field(default=None, description="Code postal.")] = None,
        city: Annotated[Optional[str], Field(default=None, description="Ville.")] = None,
        country_alpha2: Annotated[Optional[str], Field(default=None, description="Code pays ISO (ex: 'FR').")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Liste d'emails.")] = None,
        iban: Annotated[Optional[str], Field(default=None, description="IBAN du fournisseur.")] = None,
        payment_method: Annotated[Optional[str], Field(
            default=None,
            description="Méthode de paiement : 'automatic_transfer', 'manual_transfer', "
            "'check', 'cash', 'card'.",
        )] = None,
    ) -> str:
        """Crée un nouveau fournisseur. Le nom est obligatoire."""
        try:
            body: dict = {"name": name}

            postal_address: dict = {}
            if address:
                postal_address["address"] = address
            if postal_code:
                postal_address["postal_code"] = postal_code
            if city:
                postal_address["city"] = city
            if country_alpha2:
                postal_address["country_alpha2"] = country_alpha2
            if postal_address:
                body["postal_address"] = postal_address

            if reg_no:
                body["reg_no"] = reg_no
            if establishment_no:
                body["establishment_no"] = establishment_no
            if vat_number:
                body["vat_number"] = vat_number
            if emails:
                body["emails"] = emails
            if iban:
                body["iban"] = iban
            if payment_method:
                body["supplier_payment_method"] = payment_method

            data = await api_post("/suppliers", body)
            return (
                f"✅ Fournisseur '{data.get('name')}' créé "
                f"(id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour un fournisseur ─────────────────────────────────────────

    @mcp.tool(
        name="pennylane_update_supplier",
        annotations={
            "title": "Modifier un fournisseur",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_supplier(
        id: Annotated[int, Field(description="Identifiant du fournisseur à modifier.")],
        name: Annotated[Optional[str], Field(default=None, description="Nouveau nom.")] = None,
        reg_no: Annotated[Optional[str], Field(default=None, description="SIREN.")] = None,
        establishment_no: Annotated[Optional[str], Field(default=None, description="SIRET.")] = None,
        vat_number: Annotated[Optional[str], Field(default=None, description="Numéro de TVA.")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Emails.")] = None,
        iban: Annotated[Optional[str], Field(default=None, description="IBAN.")] = None,
        payment_method: Annotated[Optional[str], Field(default=None, description="Méthode de paiement.")] = None,
    ) -> str:
        """Modifie un fournisseur existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if name is not None:
                body["name"] = name
            if reg_no is not None:
                body["reg_no"] = reg_no
            if establishment_no is not None:
                body["establishment_no"] = establishment_no
            if vat_number is not None:
                body["vat_number"] = vat_number
            if emails is not None:
                body["emails"] = emails
            if iban is not None:
                body["iban"] = iban
            if payment_method is not None:
                body["supplier_payment_method"] = payment_method

            data = await api_put(f"/suppliers/{id}", body)
            return f"✅ Fournisseur mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
