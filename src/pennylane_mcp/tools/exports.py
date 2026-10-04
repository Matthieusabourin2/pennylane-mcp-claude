"""Outils MCP : exports comptables (FEC, Grand Livre Analytique)."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field
from mcp.server.fastmcp import FastMCP

from ..api import api_get, api_post
from ..utils import to_json


def register(mcp: FastMCP) -> None:
    """Enregistre les outils d'export comptable."""

    # ── Créer un export FEC ───────────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_create_fec_export",
        annotations={
            "title": "Créer un export FEC",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_fec_export(
        period_start: Annotated[str, Field(description="Début de période (YYYY-MM-DD).")],
        period_end: Annotated[str, Field(description="Fin de période (YYYY-MM-DD).")],
    ) -> str:
        """Crée un export FEC (Fichier des Écritures Comptables) pour une période.
        L'export est asynchrone : utilisez pennylane_get_fec_export pour récupérer
        le fichier une fois le statut 'ready'.
        """
        try:
            body = {"period_start": period_start, "period_end": period_end}
            data = await api_post("/exports/fecs", body)
            return (
                f"✅ Export FEC créé (id: {data.get('id')}, "
                f"statut: {data.get('status')}).\n"
                f"Utilisez pennylane_get_fec_export pour vérifier le statut "
                f"et récupérer l'URL de téléchargement.\n\n{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer un export FEC ───────────────────────────────────────────────

    @mcp.tool(
        name="pennylane_get_fec_export",
        annotations={
            "title": "Récupérer un export FEC",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_fec_export(
        id: Annotated[int, Field(description="Identifiant de l'export FEC.")],
    ) -> str:
        """Récupère le détail d'un export FEC.
        Retourne le statut (pending/ready/error) et l'URL de téléchargement
        si prêt (expire dans 10 minutes).
        """
        try:
            data = await api_get(f"/exports/fecs/{id}")
            status = data.get("status", "unknown")
            file_url = data.get("file_url")
            msg = f"📊 Export FEC (id: {id}) — Statut: {status}"
            if file_url:
                msg += f"\n🔗 URL de téléchargement (expire dans 10 min): {file_url}"
            return f"{msg}\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"

    # ── Créer un export Grand Livre Analytique ────────────────────────────────

    @mcp.tool(
        name="pennylane_create_agl_export",
        annotations={
            "title": "Créer un export Grand Livre Analytique",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def pennylane_create_agl_export(
        period_start: Annotated[str, Field(description="Début de période (YYYY-MM-DD).")],
        period_end: Annotated[str, Field(description="Fin de période (YYYY-MM-DD).")],
        mode: Annotated[Optional[str], Field(
            default=None,
            description="Mode d'export : 'in_line' (défaut) ou 'in_column'.",
        )] = None,
    ) -> str:
        """Crée un export Grand Livre Analytique (AGL) pour une période.
        L'export est asynchrone : utilisez pennylane_get_agl_export pour
        récupérer le fichier.
        """
        try:
            body: dict = {"period_start": period_start, "period_end": period_end}
            if mode:
                body["mode"] = mode

            data = await api_post("/exports/analytical_general_ledgers", body)
            return (
                f"✅ Export AGL créé (id: {data.get('id')}, "
                f"statut: {data.get('status')}).\n"
                f"Utilisez pennylane_get_agl_export pour vérifier le statut.\n\n"
                f"{to_json(data)}"
            )
        except Exception as exc:
            return f"❌ {exc}"

    # ── Récupérer un export Grand Livre Analytique ────────────────────────────

    @mcp.tool(
        name="pennylane_get_agl_export",
        annotations={
            "title": "Récupérer un export Grand Livre Analytique",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_get_agl_export(
        id: Annotated[int, Field(description="Identifiant de l'export AGL.")],
    ) -> str:
        """Récupère le détail d'un export Grand Livre Analytique.
        Retourne le statut et l'URL de téléchargement si prêt.
        """
        try:
            data = await api_get(f"/exports/analytical_general_ledgers/{id}")
            status = data.get("status", "unknown")
            file_url = data.get("file_url")
            msg = f"📊 Export AGL (id: {id}) — Statut: {status}"
            if file_url:
                msg += f"\n🔗 URL de téléchargement (expire dans 10 min): {file_url}"
            return f"{msg}\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
