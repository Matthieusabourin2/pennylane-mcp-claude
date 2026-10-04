"""Minimal OAuth 2.0 authorization-server provider for pennylane-mcp.

Lets claude.ai web connect (its custom-connector UI only does OAuth, no static-bearer
field). The /authorize step is gated by a password so the public endpoint stays
protected. The static bearer keeps working for Claude Code because load_access_token()
also accepts it. Tokens persist in MCP_OAUTH_STATE when set (else re-auth after a restart).

Le serveur FastMCP embarque lui-même l'AS OAuth (pas de gateway, pas de JWKS).
MCP_PUBLIC_URL doit être la base publique complète ; toutes les URLs OAuth annoncées
en sont dérivées.
"""
import json
import logging
import os
import secrets
import time

from pydantic import AnyHttpUrl
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import (
    InvalidRedirectUriError,
    OAuthClientInformationFull,
    OAuthToken,
)

PUBLIC_URL = os.getenv("MCP_PUBLIC_URL", "").rstrip("/")
if not PUBLIC_URL.startswith("https://"):
    raise SystemExit(
        "MCP_PUBLIC_URL doit être l'adresse publique HTTPS du serveur, sans slash final "
        "(ex. https://pennylane.mondomaine.fr). Elle est obligatoire avec MCP_OAUTH_ENABLED=1."
    )
SCOPE = "pennylane"

# Destinations de redirection autorisées, séparées par des virgules.
# Le SDK valide normalement le redirect_uri contre les URI enregistrées du client ;
# le modèle no-DCR synthétise un client pour n'importe quel client_id, ce qui
# NEUTRALISAIT cette vérification. Un attaquant pouvait donc forger un lien
# /authorize renvoyant vers son serveur : l'opérateur voyait SA page de consentement
# sur SON domaine, saisissait son mot de passe, et le code partait chez l'attaquant.
# D'où cette liste blanche.
ALLOWED_REDIRECTS = tuple(
    u.strip().rstrip("/")
    for u in os.getenv(
        "MCP_OAUTH_REDIRECTS",
        "https://claude.ai/api/mcp/auth_callback,https://claude.com/api/mcp/auth_callback",
    ).split(",")
    if u.strip()
)
# Chemin d'un fichier JSON où persister les jetons. Sans lui, tout redémarrage
# déconnecte les connecteurs claude.ai, et comme /register renvoie 404, ils ne
# peuvent pas se ré-enregistrer. Volume DÉDIÉ, jamais un dossier servi.
STATE_PATH = os.getenv("MCP_OAUTH_STATE") or None

ACCESS_TTL = 3600
CODE_TTL = 300
PENDING_TTL = 600

import mcp.server.auth.routes as _auth_routes

# --- Patch 1: advertise token_endpoint_auth_methods_supported including "none".
# The SDK hardcodes [client_secret_post, client_secret_basic]; claude.ai is a PUBLIC
# client (PKCE, no secret) and needs "none" advertised (reference no-DCR servers advertise it & work).
if not getattr(_auth_routes, "_pennylane_patched", False):
    _orig_build_metadata = _auth_routes.build_metadata

    def _build_metadata_patched(*args, **kwargs):
        meta = _orig_build_metadata(*args, **kwargs)
        methods = list(meta.token_endpoint_auth_methods_supported or [])
        if "none" not in methods:
            methods.append("none")
        meta.token_endpoint_auth_methods_supported = methods
        return meta

    _auth_routes.build_metadata = _build_metadata_patched

    # --- Patch 2: advertise the protected-resource-metadata URL UNDER the public base
    # (PUBLIC_URL/.well-known/oauth-protected-resource) so it routes back to this server
    # even when a reverse proxy serves this server under a path prefix. A custom route
    # below serves it at this server's root.
    def _build_prm_url_patched(resource_server_url):
        return AnyHttpUrl(PUBLIC_URL + "/.well-known/oauth-protected-resource")

    _auth_routes.build_resource_metadata_url = _build_prm_url_patched
    _auth_routes._pennylane_patched = True


class _AnyRedirectClient(OAuthClientInformationFull):
    """Public client that accepts whatever redirect_uri / scope the caller presents.

    No-DCR model: claude.ai connects without dynamic client
    registration, so we synthesize a client for any client_id and don't strict-validate
    the (Anthropic-controlled) redirect_uri. The real gate is the consent password.
    """

    def validate_redirect_uri(self, redirect_uri):
        if redirect_uri is not None:
            if str(redirect_uri).rstrip("/") not in ALLOWED_REDIRECTS:
                raise InvalidRedirectUriError(
                    f"redirect_uri non autorisé : {redirect_uri}"
                )
            return redirect_uri
        if self.redirect_uris:
            return self.redirect_uris[0]
        from pydantic import AnyUrl
        return AnyUrl("https://claude.ai/api/mcp/auth_callback")

    def validate_scope(self, scope):
        return [SCOPE]


class PennylaneOAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self, static_bearer: str, password: str):
        self.static_bearer = static_bearer
        self.password = password
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.pending: dict[str, dict] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self._load()

    async def get_client(self, client_id: str):
        c = self.clients.get(client_id)
        if c:
            return c
        # No DCR: synthesize a public client for any client_id .
        return _AnyRedirectClient(
            client_id=client_id,
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=SCOPE,
        )

    async def register_client(self, client_info: OAuthClientInformationFull):
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client, params) -> str:
        import logging
        logging.getLogger("pennylane").info(
            "authorize: client=%s redirect_uri=%s", client.client_id, params.redirect_uri
        )
        rid = secrets.token_urlsafe(24)
        self.pending[rid] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "state": params.state,
            "scopes": params.scopes or [SCOPE],
            "resource": params.resource,
            "exp": time.time() + PENDING_TTL,
        }
        return f"{PUBLIC_URL}/consent?rid={rid}"

    async def load_authorization_code(self, client, authorization_code: str):
        ac = self.auth_codes.get(authorization_code)
        if ac and ac.client_id == client.client_id and ac.expires_at > time.time():
            return ac
        return None

    async def exchange_authorization_code(self, client, authorization_code):
        self.auth_codes.pop(authorization_code.code, None)
        return self._issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client, refresh_token: str):
        rt = self.refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        # NON ROTATIF : claude.ai peut rafraîchir depuis deux contextes ou
        # réessayer après une réponse perdue ; la rotation à usage unique les
        # désynchronise → 400 → reconnexion forcée.
        scopes = list(scopes or refresh_token.scopes)
        at = secrets.token_urlsafe(32)
        self.access_tokens[at] = AccessToken(
            token=at, client_id=refresh_token.client_id, scopes=scopes,
            expires_at=int(time.time()) + ACCESS_TTL,
        )
        self._save()
        return OAuthToken(
            access_token=at, token_type="Bearer", expires_in=ACCESS_TTL,
            refresh_token=refresh_token.token,
            scope=" ".join(scopes) if scopes else None,
        )

    # ---- persistance disque des jetons (pilotée par MCP_OAUTH_STATE) ----

    def _load(self) -> None:
        if not STATE_PATH or not os.path.exists(STATE_PATH):
            return
        try:
            with open(STATE_PATH) as fh:
                data = json.load(fh)
        except Exception:
            logging.getLogger(__name__).exception(
                "état OAuth illisible (%s) — on repart à vide", STATE_PATH)
            return
        now = time.time()
        for tok, a in data.get("access", {}).items():
            try:
                at = AccessToken.model_validate(a)
            except Exception:
                continue
            if at.expires_at is None or at.expires_at > now:
                self.access_tokens[tok] = at
        for tok, r in data.get("refresh", {}).items():
            try:
                self.refresh_tokens[tok] = RefreshToken.model_validate(r)
            except Exception:
                continue

    def _save(self) -> None:
        if not STATE_PATH:
            return
        now = time.time()
        data = {
            "access": {t: a.model_dump(mode="json") for t, a in self.access_tokens.items()
                       if a.expires_at is None or a.expires_at > now},
            "refresh": {t: r.model_dump(mode="json") for t, r in self.refresh_tokens.items()},
        }
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, STATE_PATH)
        except Exception:
            # JAMAIS en silence : sinon la persistance est inopérante sans signe.
            logging.getLogger(__name__).exception(
                "échec d'écriture de l'état OAuth (%s) — persistance INOPÉRANTE", STATE_PATH)

    async def load_access_token(self, token: str):
        if self.static_bearer and token == self.static_bearer:
            return AccessToken(token=token, client_id="static-bearer", scopes=[SCOPE], expires_at=None)
        at = self.access_tokens.get(token)
        if at and (at.expires_at is None or at.expires_at > time.time()):
            return at
        if at:
            self.access_tokens.pop(token, None)
            self._save()
        return None

    async def revoke_token(self, token):
        t = getattr(token, "token", None)
        if t:
            self.access_tokens.pop(t, None)
            self.refresh_tokens.pop(t, None)
            self._save()

    def _issue(self, client_id: str, scopes: list[str]) -> OAuthToken:
        at = secrets.token_urlsafe(32)
        rt = secrets.token_urlsafe(32)
        now = int(time.time())
        self.access_tokens[at] = AccessToken(
            token=at, client_id=client_id, scopes=scopes or [SCOPE], expires_at=now + ACCESS_TTL
        )
        self.refresh_tokens[rt] = RefreshToken(token=rt, client_id=client_id, scopes=scopes or [SCOPE])
        self._save()
        return OAuthToken(
            access_token=at, token_type="Bearer", expires_in=ACCESS_TTL,
            scope=" ".join(scopes or [SCOPE]), refresh_token=rt,
        )

    def extra_routes(self) -> list[Route]:
        provider = self

        async def prm(request):
            # Protected-resource metadata, served at this server's root; reached publicly
            # at PUBLIC_URL/.well-known/oauth-protected-resource.
            return JSONResponse({
                "resource": PUBLIC_URL + "/",
                "authorization_servers": [PUBLIC_URL + "/"],
                "scopes_supported": [SCOPE],
                "bearer_methods_supported": ["header"],
            })

        async def consent_get(request):
            rid = request.query_params.get("rid", "")
            pend = provider.pending.get(rid)
            if not pend or pend["exp"] < time.time():
                return PlainTextResponse("Demande d'autorisation invalide ou expirée.", status_code=400)
            html = (
                "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>pennylane-mcp — autorisation</title></head>"
                "<body style='font-family:system-ui,sans-serif;max-width:420px;margin:64px auto;padding:0 16px'>"
                "<h2>pennylane-mcp</h2>"
                "<p>Autoriser ce connecteur à accéder à la comptabilité <b>Pennylane</b> ? "
                "Entrez le mot de passe d'accès.</p>"
                f"<form method='post' action='{PUBLIC_URL}/consent'><input type='hidden' name='rid' value='{rid}'>"
                "<input type='password' name='password' autofocus autocomplete='off' "
                "style='width:100%;padding:10px;font-size:16px;box-sizing:border-box'>"
                "<button type='submit' style='margin-top:14px;padding:10px 18px;font-size:15px'>Autoriser</button>"
                "</form></body></html>"
            )
            return HTMLResponse(html)

        async def consent_post(request):
            form = await request.form()
            rid = str(form.get("rid", ""))
            password = str(form.get("password", ""))
            pend = provider.pending.get(rid)
            if not pend or pend["exp"] < time.time():
                return PlainTextResponse("Demande d'autorisation invalide ou expirée.", status_code=400)
            if not secrets.compare_digest(password, provider.password):
                return HTMLResponse(
                    "<p style='font-family:sans-serif;max-width:420px;margin:64px auto'>"
                    "Mot de passe incorrect. <a href='javascript:history.back()'>Réessayer</a></p>",
                    status_code=403,
                )
            provider.pending.pop(rid, None)
            code = secrets.token_urlsafe(32)
            provider.auth_codes[code] = AuthorizationCode(
                code=code, scopes=pend["scopes"], expires_at=time.time() + CODE_TTL,
                client_id=pend["client_id"], code_challenge=pend["code_challenge"],
                redirect_uri=pend["redirect_uri"],
                redirect_uri_provided_explicitly=pend["redirect_uri_provided_explicitly"],
                resource=pend["resource"],
            )
            target = construct_redirect_uri(pend["redirect_uri"], code=code, state=pend["state"])
            return RedirectResponse(target, status_code=302)

        return [
            Route("/.well-known/oauth-protected-resource", prm, methods=["GET"]),
            Route("/consent", consent_get, methods=["GET"]),
            Route("/consent", consent_post, methods=["POST"]),
        ]


def build_auth_settings() -> AuthSettings:
    return AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=PUBLIC_URL,
        required_scopes=[SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=False, valid_scopes=[SCOPE], default_scopes=[SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
