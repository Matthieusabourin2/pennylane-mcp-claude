"""Outil MCP : vérification de connexion Pennylane."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..api import api_get
from ..utils import to_json


def register(mcp: FastMCP) -> None:
    """Enregistre l'outil pennylane_whoami."""

    @mcp.tool(
        name="pennylane_whoami",
        annotations={
            "title": "Vérifier connexion Pennylane",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def pennylane_whoami() -> str:
        """Vérifie la connexion à l'API Pennylane et retourne les infos de
        l'utilisateur et de la société connectée. Utilisez cet outil en premier
        pour valider que le token est fonctionnel.

        Returns:
            str: JSON avec les informations du compte connecté.
        """
        try:
            data = await api_get("/me")
            return f"✅ Connexion Pennylane active.\n\n{to_json(data)}"
        except Exception as exc:
            return f"❌ {exc}"
