"""Outils MCP : gestion des clients (Customers)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post, api_put
from ..utils import pagination_summary, to_json, truncate_if_needed


def register(mcp: FastMCP) -> None:
    """Enregistre les outils de gestion des clients."""

    # ── Lister les clients ───────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_list_customers",
        annotations={
            "title": "Lister les clients",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_customers(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        customer_type: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par type : 'company' ou 'individual'.",
        )] = None,
        name: Annotated[Optional[str], Field(
            default=None,
            description="Filtrer par nom (recherche partielle).",
        )] = None,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id' (défaut: '-id').")] = None,
    ) -> str:
        """Liste les clients (entreprises et particuliers) avec filtres et pagination.
        Utile pour consulter la base clients, rechercher un client par nom ou type.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            filters: list[dict] = []
            if customer_type:
                filters.append({"field": "customer_type", "operator": "eq", "value": customer_type})
            if name:
                filters.append({"field": "name", "operator": "eq", "value": name})
            if filters:
                qp["filter"] = json.dumps(filters)

            data = await api_get("/customers", qp)
            items = data.get("items", [])
            result = {
                "customers": items,
                "pagination": pagination_summary(
                    data.get("has_more"), data.get("next_cursor"),
                    data.get("total_items"), len(items),
                ),
                "next_cursor": data.get("next_cursor"),
            }
            return truncate_if_needed(to_json(result))
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer un client ──────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_customer",
        annotations={
            "title": "Détail d'un client",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_customer(
        id: Annotated[int, Field(description="Identifiant unique du client.")],
    ) -> str:
        """Récupère le détail d'un client par son identifiant.
        Retourne les informations complètes (adresse, contacts, conditions de paiement).
        """
        try:
            data = await api_get(f"/customers/{id}")
            return to_json(data)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un client entreprise ───────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_company_customer",
        annotations={
            "title": "Créer un client entreprise",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_company_customer(
        name: Annotated[str, Field(description="Raison sociale du client.")],
        address: Annotated[Optional[str], Field(
            default=None,
            description="Adresse postale (ligne 1).",
        )] = None,
        postal_code: Annotated[Optional[str], Field(default=None, description="Code postal.")] = None,
        city: Annotated[Optional[str], Field(default=None, description="Ville.")] = None,
        country_alpha2: Annotated[Optional[str], Field(default=None, description="Code pays ISO (ex: 'FR').")] = None,
        vat_number: Annotated[Optional[str], Field(default=None, description="Numéro de TVA intracommunautaire.")] = None,
        reg_no: Annotated[Optional[str], Field(default=None, description="Numéro SIREN (9 chiffres).")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Liste d'emails du client.")] = None,
        phone: Annotated[Optional[str], Field(default=None, description="Numéro de téléphone.")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Référence interne.")] = None,
        notes: Annotated[Optional[str], Field(default=None, description="Notes libres.")] = None,
    ) -> str:
        """Crée un nouveau client de type entreprise (société).
        Le nom (raison sociale) est obligatoire.
        """
        try:
            body: dict = {"name": name}

            # Adresse de facturation
            billing_address: dict = {}
            if address:
                billing_address["address"] = address
            if postal_code:
                billing_address["postal_code"] = postal_code
            if city:
                billing_address["city"] = city
            if country_alpha2:
                billing_address["country_alpha2"] = country_alpha2
            if billing_address:
                body["billing_address"] = billing_address

            if vat_number:
                body["vat_number"] = vat_number
            if reg_no:
                body["reg_no"] = reg_no
            if emails:
                body["emails"] = emails
            if phone:
                body["phone"] = phone
            if reference:
                body["reference"] = reference
            if notes:
                body["notes"] = notes

            data = await api_post("/company_customers", body)
            return (
                f"✅ Client entreprise '{data.get('name')}' créé "
                f"(id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un client particulier ──────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_individual_customer",
        annotations={
            "title": "Créer un client particulier",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_individual_customer(
        first_name: Annotated[str, Field(description="Prénom du client.")],
        last_name: Annotated[str, Field(description="Nom de famille du client.")],
        address: Annotated[Optional[str], Field(default=None, description="Adresse postale (ligne 1).")] = None,
        postal_code: Annotated[Optional[str], Field(default=None, description="Code postal.")] = None,
        city: Annotated[Optional[str], Field(default=None, description="Ville.")] = None,
        country_alpha2: Annotated[Optional[str], Field(default=None, description="Code pays ISO (ex: 'FR').")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Liste d'emails du client.")] = None,
        phone: Annotated[Optional[str], Field(default=None, description="Numéro de téléphone.")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Référence interne.")] = None,
        notes: Annotated[Optional[str], Field(default=None, description="Notes libres.")] = None,
    ) -> str:
        """Crée un nouveau client de type particulier (personne physique).
        Le prénom et le nom sont obligatoires.
        """
        try:
            body: dict = {"first_name": first_name, "last_name": last_name}

            billing_address: dict = {}
            if address:
                billing_address["address"] = address
            if postal_code:
                billing_address["postal_code"] = postal_code
            if city:
                billing_address["city"] = city
            if country_alpha2:
                billing_address["country_alpha2"] = country_alpha2
            if billing_address:
                body["billing_address"] = billing_address

            if emails:
                body["emails"] = emails
            if phone:
                body["phone"] = phone
            if reference:
                body["reference"] = reference
            if notes:
                body["notes"] = notes

            data = await api_post("/individual_customers", body)
            return (
                f"✅ Client particulier '{data.get('first_name')} {data.get('last_name')}' créé "
                f"(id: {data.get('id')}).\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour un client entreprise ───────────────────────────────────

    @mcp.tool(
        name="pennylane_update_company_customer",
        annotations={
            "title": "Modifier un client entreprise",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_company_customer(
        id: Annotated[int, Field(description="Identifiant du client entreprise à modifier.")],
        name: Annotated[Optional[str], Field(default=None, description="Nouvelle raison sociale.")] = None,
        vat_number: Annotated[Optional[str], Field(default=None, description="Numéro de TVA.")] = None,
        reg_no: Annotated[Optional[str], Field(default=None, description="SIREN.")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Emails mis à jour.")] = None,
        phone: Annotated[Optional[str], Field(default=None, description="Téléphone.")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Référence interne.")] = None,
        notes: Annotated[Optional[str], Field(default=None, description="Notes.")] = None,
    ) -> str:
        """Modifie un client entreprise existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if name is not None:
                body["name"] = name
            if vat_number is not None:
                body["vat_number"] = vat_number
            if reg_no is not None:
                body["reg_no"] = reg_no
            if emails is not None:
                body["emails"] = emails
            if phone is not None:
                body["phone"] = phone
            if reference is not None:
                body["reference"] = reference
            if notes is not None:
                body["notes"] = notes

            data = await api_put(f"/company_customers/{id}", body)
            return f"✅ Client entreprise mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Mettre à jour un client particulier ──────────────────────────────────

    @mcp.tool(
        name="pennylane_update_individual_customer",
        annotations={
            "title": "Modifier un client particulier",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_update_individual_customer(
        id: Annotated[int, Field(description="Identifiant du client particulier à modifier.")],
        first_name: Annotated[Optional[str], Field(default=None, description="Nouveau prénom.")] = None,
        last_name: Annotated[Optional[str], Field(default=None, description="Nouveau nom.")] = None,
        emails: Annotated[Optional[list], Field(default=None, description="Emails mis à jour.")] = None,
        phone: Annotated[Optional[str], Field(default=None, description="Téléphone.")] = None,
        reference: Annotated[Optional[str], Field(default=None, description="Référence interne.")] = None,
        notes: Annotated[Optional[str], Field(default=None, description="Notes.")] = None,
    ) -> str:
        """Modifie un client particulier existant. Seuls les champs fournis sont mis à jour."""
        try:
            body: dict = {}
            if first_name is not None:
                body["first_name"] = first_name
            if last_name is not None:
                body["last_name"] = last_name
            if emails is not None:
                body["emails"] = emails
            if phone is not None:
                body["phone"] = phone
            if reference is not None:
                body["reference"] = reference
            if notes is not None:
                body["notes"] = notes

            data = await api_put(f"/individual_customers/{id}", body)
            return f"✅ Client particulier mis à jour.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
