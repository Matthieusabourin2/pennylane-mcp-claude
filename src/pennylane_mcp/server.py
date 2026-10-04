#!/usr/bin/env python3
"""Serveur MCP Pennylane — Point d'entrée principal.

Serveur MCP (Model Context Protocol) complet pour l'API comptable Pennylane.
Conçu pour les experts-comptables, il expose 87 outils couvrant :
  - Plan comptable (CRUD)
  - Journaux comptables
  - Écritures comptables (CRUD + lignes)
  - Lignes d'écriture (lettrage, analytique)
  - Balance générale
  - Exercices fiscaux
  - Clients (entreprises et particuliers)
  - Fournisseurs
  - Factures clients (CRUD, finalisation, paiement)
  - Factures fournisseurs (consultation, mise à jour, paiement)
  - Produits / services (catalogue)
  - Devis (CRUD, envoi par email, statut)
  - Catégories analytiques (groupes et catégories)
  - Exports comptables (FEC, Grand Livre Analytique)
  - Abonnements de facturation récurrente
  - Suivi des modifications (ChangeLogs)
  - Gestion multi-dossiers (v2.0)

Modes de transport :
  - stdio  : usage local (Claude Desktop, Claude Code) — par défaut
  - streamable-http : claude.ai web et mobile, avec OAuth embarqué (MCP_TRANSPORT=streamable-http)
  - sse    : héritage amont, usage distant via URL (MCP_TRANSPORT=sse)

Modes de fonctionnement :
  1. Multi-dossiers : fichier dossiers.json (recommandé pour les cabinets)
  2. Mono-dossier : variable PENNYLANE_API_TOKEN (rétrocompatibilité)

Variables d'environnement :
    PENNYLANE_API_TOKEN   — Token Bearer (mode mono-dossier)
    PENNYLANE_CONFIG_PATH — Chemin vers dossiers.json (optionnel)
    MCP_TRANSPORT         — Transport : 'stdio' (défaut), 'streamable-http' ou 'sse'
    MCP_HOST              — Hôte d'écoute SSE (défaut: 127.0.0.1)
    MCP_PORT              — Port d'écoute SSE (défaut: 8000)
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .api import close_client, init_client
from .constants import SERVER_NAME, SERVER_VERSION
from .dossier_manager import DossierManager, set_manager
from .tools import (
    accounts,
    billing_subscriptions,
    categories,
    changelogs,
    customer_invoices,
    customers,
    dossiers,
    entries,
    entry_lines,
    exports,
    journals,
    me,
    products,
    quotes,
    supplier_invoices,
    suppliers,
    trial_balance,
)


def _find_config_path() -> Path | None:
    """Recherche le fichier dossiers.json dans les emplacements habituels.

    Ordre de priorité :
    1. Variable d'environnement PENNYLANE_CONFIG_PATH
    2. Répertoire courant : ./dossiers.json
    3. Config utilisateur : ~/.config/pennylane-mcp/dossiers.json
    """
    # 1. Variable d'environnement explicite
    env_path = os.environ.get("PENNYLANE_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        # Le chemin est spécifié mais n'existe pas encore → on l'utilisera
        # pour la création par add_dossier
        return p

    # 2. Répertoire courant
    cwd = Path.cwd() / "dossiers.json"
    if cwd.exists():
        return cwd

    # 3. Config utilisateur
    home_config = Path.home() / ".config" / "pennylane-mcp" / "dossiers.json"
    if home_config.exists():
        return home_config

    return None


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Cycle de vie du serveur : initialisation multi-dossiers ou mono-dossier."""

    manager = None
    config_path = _find_config_path()

    # ── Tentative mode multi-dossiers ─────────────────────────────────────
    if config_path and config_path.exists():
        manager = DossierManager(config_path)
        loaded = await manager.load_config()

        if loaded and manager.has_dossiers():
            # Mode multi-dossiers activé
            await manager.init_all_clients()

            # Auto-sélection du premier dossier si aucun n'est défini
            if manager.current_slug is None:
                slugs = manager.list_slugs()
                if slugs:
                    await manager.switch_dossier(slugs[0])

            set_manager(manager)
            print(
                f"🚀 {SERVER_NAME} v{SERVER_VERSION} démarré — "
                f"Mode multi-dossiers ({manager.dossier_count} dossier(s), "
                f"actif: {manager.current_slug})",
                file=sys.stderr,
            )
            try:
                yield {}
            finally:
                await manager.close_all()
                print(f"🛑 {SERVER_NAME} arrêté", file=sys.stderr)
            return

    # ── Fallback : mode mono-dossier (rétrocompatibilité) ─────────────────
    api_token = os.environ.get("PENNYLANE_API_TOKEN", "")

    if not api_token:
        # Aucune configuration trouvée — créer un manager vide pour
        # permettre l'ajout dynamique de dossiers via les outils
        if config_path is None:
            # Définir un chemin par défaut pour la sauvegarde
            config_path = Path.cwd() / "dossiers.json"

        manager = DossierManager(config_path)
        set_manager(manager)

        print(
            f"🚀 {SERVER_NAME} v{SERVER_VERSION} démarré — "
            f"Mode initial (aucun dossier configuré).\n"
            f"   Utilisez pennylane_add_dossier pour ajouter un dossier,\n"
            f"   ou définissez PENNYLANE_API_TOKEN pour le mode mono-dossier.",
            file=sys.stderr,
        )
        try:
            yield {}
        finally:
            if manager.has_dossiers():
                await manager.close_all()
            print(f"🛑 {SERVER_NAME} arrêté", file=sys.stderr)
        return

    # Mode mono-dossier avec PENNYLANE_API_TOKEN
    # On crée quand même un DossierManager pour uniformiser l'accès
    if config_path is None:
        config_path = Path.cwd() / "dossiers.json"

    manager = DossierManager(config_path)
    await manager.add_dossier(
        slug="default",
        name="Dossier principal",
        token=api_token,
        save=False,  # Ne pas sauvegarder en mode legacy
    )
    set_manager(manager)

    print(
        f"🚀 {SERVER_NAME} v{SERVER_VERSION} démarré — Mode mono-dossier",
        file=sys.stderr,
    )
    try:
        yield {}
    finally:
        await manager.close_all()
        await close_client()
        print(f"🛑 {SERVER_NAME} arrêté", file=sys.stderr)


# ─── Création du serveur ─────────────────────────────────────────────────────

# ─── Auth OAuth optionnelle ──────────────────────────────────────────────────
# Si MCP_OAUTH_ENABLED=1 ET MCP_BEARER_TOKEN présent : le serveur FastMCP embarque
# son propre serveur d'autorisation OAuth 2.0 (routes metadata/register/authorize/
# token + protection de /mcp) → connexion possible depuis claude.ai web. Le bearer
# statique reste accepté (Claude Code / Desktop). Sinon (stdio local) : aucune
# auth montée → comportement strictement inchangé.
_oauth_enabled = os.environ.get("MCP_OAUTH_ENABLED", "0").lower() in ("1", "true", "yes")
_bearer = os.environ.get("MCP_BEARER_TOKEN", "")
_oauth_password = os.environ.get("MCP_OAUTH_PASSWORD") or _bearer

oauth_provider = None
_auth_settings = None
if _oauth_enabled and not _bearer:
    # Sans ce garde-fou, /mcp serait exposé sans aucune authentification.
    raise SystemExit("MCP_OAUTH_ENABLED=1 exige MCP_BEARER_TOKEN (générer : openssl rand -base64 32).")
if _oauth_enabled:
    from .oauth import PennylaneOAuthProvider, build_auth_settings

    oauth_provider = PennylaneOAuthProvider(static_bearer=_bearer, password=_oauth_password)
    _auth_settings = build_auth_settings()

mcp = FastMCP(
    SERVER_NAME,
    lifespan=lifespan,
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8000")),
    auth_server_provider=oauth_provider,
    auth=_auth_settings,
)

# ─── Enregistrement de tous les outils ───────────────────────────────────────

me.register(mcp)
accounts.register(mcp)
journals.register(mcp)
entries.register(mcp)
entry_lines.register(mcp)
trial_balance.register(mcp)
customers.register(mcp)
suppliers.register(mcp)
customer_invoices.register(mcp)
supplier_invoices.register(mcp)
products.register(mcp)
quotes.register(mcp)
categories.register(mcp)
exports.register(mcp)
billing_subscriptions.register(mcp)
changelogs.register(mcp)
dossiers.register(mcp)  # Outils multi-dossiers (v2.0)


# ─── Point d'entrée ─────────────────────────────────────────────────────────


def main() -> None:
    """Démarre le serveur MCP.

    Le mode de transport est déterminé par la variable MCP_TRANSPORT :
      - 'stdio' (défaut) : communication locale via stdin/stdout
      - 'sse'            : serveur HTTP avec Server-Sent Events

    En mode SSE, le serveur écoute sur MCP_HOST:MCP_PORT (défaut 127.0.0.1:8000).
    L'authentification est gérée par le middleware McpMiddleware (Bearer token).
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()

    if transport in ("streamable-http", "streamable_http", "http"):
        # Mode cible pour claude.ai web : transport streamable-http (/mcp) + OAuth
        # embarqué (mcp.streamable_http_app() + le SDK monte l'AS OAuth ; on ajoute la
        # page consentement + la route PRM).
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        import uvicorn

        app = mcp.streamable_http_app()
        if oauth_provider is not None:
            for route in oauth_provider.extra_routes():
                app.router.routes.insert(0, route)
            print(
                f"🌐 {SERVER_NAME} v{SERVER_VERSION} — streamable-http + OAuth\n"
                f"   Écoute sur http://{host}:{port}/mcp (claude.ai web + bearer statique)",
                file=sys.stderr,
            )
        else:
            print(
                f"🌐 {SERVER_NAME} v{SERVER_VERSION} — streamable-http (SANS OAuth)\n"
                f"   Écoute sur http://{host}:{port}/mcp",
                file=sys.stderr,
            )
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    if transport == "sse":
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        print(
            f"🌐 {SERVER_NAME} v{SERVER_VERSION} — Mode SSE\n"
            f"   Écoute sur http://{host}:{port}/sse\n"
            f"   Utilisez un reverse proxy (Nginx) avec HTTPS en production.",
            file=sys.stderr,
        )
        import uvicorn
        from mcp.server.fastmcp import FastMCP
        mcp_app = mcp.sse_app()

        # Token d'authentification (optionnel)
        auth_token = os.environ.get("MCP_AUTH_TOKEN", "")

        # Middleware reverse proxy + authentification
        class McpMiddleware:
            def __init__(self, app):
                self.app = app
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    headers_dict = dict(scope.get("headers", []))
                    # Vérifier le token Bearer si configuré
                    if auth_token:
                        auth_header = headers_dict.get(b"authorization", b"").decode()
                        if auth_header != f"Bearer {auth_token}":
                            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
                            await send({"type": "http.response.body", "body": b"Unauthorized"})
                            return
                    # Fix Host header pour Traefik
                    hdrs = [(k, b"localhost:8000" if k == b"host" else v) for k, v in scope.get("headers", [])]
                    scope = dict(scope, headers=hdrs)
                await self.app(scope, receive, send)

        mcp_app = McpMiddleware(mcp_app)
        uvicorn.run(mcp_app, host=host, port=port, log_level="info")
    else:
        print(
            f"🚀 {SERVER_NAME} v{SERVER_VERSION} — Mode stdio",
            file=sys.stderr,
        )
        mcp.run()


if __name__ == "__main__":
    main()
