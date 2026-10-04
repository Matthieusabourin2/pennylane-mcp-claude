"""Outils MCP : balance générale et exercices fiscaux."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get
from ..utils import pagination_summary, to_json, truncate_if_needed


# Libellés des classes comptables françaises (PCG)
_CLASS_LABELS = {
    "1": "Capitaux",
    "2": "Immobilisations",
    "3": "Stocks",
    "4": "Tiers",
    "5": "Financier",
    "6": "Charges",
    "7": "Produits (CA)",
    "8": "Comptes spéciaux",
}


def _build_class_summary(items: list[dict]) -> list[dict]:
    """Agrège les comptes par classe comptable (1er chiffre du numéro).

    Retourne une liste triée par classe avec débits, crédits et solde.
    """
    classes: dict[str, dict] = defaultdict(
        lambda: {"debits": 0.0, "credits": 0.0, "count": 0}
    )

    for item in items:
        number = str(item.get("number", ""))
        if number:
            cls = number[0]
            classes[cls]["debits"] += float(item.get("debits", 0))
            classes[cls]["credits"] += float(item.get("credits", 0))
            classes[cls]["count"] += 1

    result = []
    for cls in sorted(classes.keys()):
        d = classes[cls]
        solde = d["debits"] - d["credits"]
        result.append({
            "classe": cls,
            "label": _CLASS_LABELS.get(cls, "Autre"),
            "debits": f"{d['debits']:.2f}",
            "credits": f"{d['credits']:.2f}",
            "solde": f"{solde:.2f}",
            "nb_comptes": d["count"],
        })

    return result


def _extract_ca(items: list[dict]) -> dict:
    """Extrait le chiffre d'affaires (comptes 70x) depuis la liste brute.

    Retourne un dict avec total CA et détail par sous-compte 70x.
    """
    ca_total = 0.0
    ca_detail: list[dict] = []

    for item in items:
        number = str(item.get("number", ""))
        if number.startswith("70"):
            credits = float(item.get("credits", 0))
            debits = float(item.get("debits", 0))
            solde = credits - debits  # CA = crédits - débits en classe 7
            ca_total += solde
            ca_detail.append({
                "compte": number,
                "label": item.get("label", ""),
                "credits": f"{credits:.2f}",
                "debits": f"{debits:.2f}",
                "solde": f"{solde:.2f}",
            })

    return {
        "total_ca": f"{ca_total:.2f}",
        "nb_comptes_70x": len(ca_detail),
        "detail": ca_detail,
    }


def register(mcp: FastMCP) -> None:
    """Enregistre les 2 outils balance + exercices."""

    @mcp.tool(
        name="pennylane_get_trial_balance",
        annotations={
            "title": "Balance générale",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_trial_balance(
        period_start: Annotated[str, Field(description="Début de période (YYYY-MM-DD).")],
        period_end: Annotated[str, Field(description="Fin de période (YYYY-MM-DD).")],
        is_auxiliary: Annotated[Optional[bool], Field(
            default=None,
            description="Filtre sur le type de compte : "
            "true = uniquement les comptes auxiliaires (détail par tiers 411xxx/401xxx), "
            "false = uniquement les comptes généraux, "
            "Ne pas renseigner (null) = tous les comptes retournés par l'API. "
            "Par défaut null : l'API retourne TOUS les comptes (classes 1 à 7), "
            "le serveur exclut automatiquement les auxiliaires de l'output sauf demande explicite.",
        )] = None,
    ) -> str:
        """Récupère la balance générale pour une période donnée. Retourne chaque
        compte avec ses totaux débit/crédit. Essentiel pour les travaux de
        clôture, la vérification des soldes, et la préparation des états financiers.

        L'outil pagine automatiquement pour récupérer TOUS les comptes
        (classes 1 à 7) afin de garantir des totaux exacts.
        """
        try:
            all_items: list[dict] = []
            cursor: str | None = None
            page = 0
            max_pages = 50  # Sécurité anti-boucle infinie
            PER_PAGE = 100

            while page < max_pages:
                qp: dict = {
                    "period_start": period_start,
                    "period_end": period_end,
                    "limit": PER_PAGE,
                }
                if is_auxiliary is not None:
                    qp["is_auxiliary"] = is_auxiliary

                if cursor:
                    qp["cursor"] = cursor

                data = await api_get("/trial_balance", qp)
                items = data.get("items", [])
                all_items.extend(items)
                page += 1

                if data.get("has_more") and data.get("next_cursor"):
                    cursor = data["next_cursor"]
                else:
                    break

            _AUX_PREFIXES = ("411", "401")
            general_accounts = []
            auxiliary_accounts = []
            for item in all_items:
                number = str(item.get("number", ""))
                is_aux = item.get("is_auxiliary", False)
                if is_aux and number[:3] in _AUX_PREFIXES:
                    auxiliary_accounts.append(item)
                else:
                    general_accounts.append(item)

            if is_auxiliary is True:
                display_accounts = auxiliary_accounts or all_items
                mode = "auxiliaire"
            elif is_auxiliary is False:
                display_accounts = general_accounts or all_items
                mode = "général"
            else:
                display_accounts = general_accounts
                mode = "général (auxiliaires 411/401 exclus de l'affichage)"

            total_debits = sum(float(it.get("debits", 0)) for it in display_accounts)
            total_credits = sum(float(it.get("credits", 0)) for it in display_accounts)

            class_summary = _build_class_summary(display_accounts)
            ca_info = _extract_ca(display_accounts)

            result = {
                "period": {
                    "start": period_start,
                    "end": period_end,
                },
                "mode": mode,
                "summary": {
                    "total_debits": f"{total_debits:.2f}",
                    "total_credits": f"{total_credits:.2f}",
                    "balance": f"{total_debits - total_credits:.2f}",
                    "accounts_count": len(display_accounts),
                    "total_fetched": len(all_items),
                    "general_count": len(general_accounts),
                    "auxiliary_count": len(auxiliary_accounts),
                    "auxiliary_excluded": is_auxiliary is None and len(auxiliary_accounts) > 0,
                    "pages_fetched": page,
                    "is_complete": page < max_pages,
                },
                "chiffre_affaires": ca_info,
                "par_classe": class_summary,
                "comptes": display_accounts,
            }

            return truncate_if_needed(
                to_json(result),
                hint="La balance est complète mais le détail des comptes est tronqué. "
                "Les totaux, le résumé par classe et le chiffre d'affaires "
                "ci-dessus sont EXACTS et COMPLETS.",
            )
        except Exception as exc:
            return f"❌ {exc}"

    @mcp.tool(
        name="pennylane_list_fiscal_years",
        annotations={
            "title": "Exercices fiscaux",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_list_fiscal_years(
        cursor: Annotated[Optional[str], Field(default=None, description="Curseur pour la pagination.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100, description="Nombre de résultats (1-100, défaut: 20).")] = 20,
        sort: Annotated[Optional[str], Field(default=None, description="Tri: 'id', '-id', 'start', '-start'.")] = None,
    ) -> str:
        """Liste les exercices fiscaux avec leurs dates et statuts
        (open, closed, frozen). Utile pour connaître les périodes comptables.
        """
        try:
            qp: dict = {"limit": limit}
            if cursor:
                qp["cursor"] = cursor
            if sort:
                qp["sort"] = sort

            data = await api_get("/fiscal_years", qp)
            items = data.get("items", [])

            status_map = {
                "open": "Ouvert",
                "closed": "Clôturé",
                "frozen": "Gelé",
                "reopen": "Réouvert",
            }

            result = {
                "fiscal_years": [
                    {
                        **fy,
                        "status_fr": status_map.get(fy.get("status", ""), fy.get("status", "")),
                    }
                    for fy in items
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
