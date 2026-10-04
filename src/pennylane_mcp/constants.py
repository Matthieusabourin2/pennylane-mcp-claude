"""Constantes partagées pour le serveur MCP Pennylane."""

API_BASE_URL = "https://app.pennylane.com/api/external/v2"

CHARACTER_LIMIT = 25_000

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_LIMIT_TRIAL_BALANCE = 1_000
MAX_LIMIT_LEDGER_ACCOUNTS = 1_000

SERVER_NAME = "pennylane_mcp"
SERVER_VERSION = "2.0.0"

# ─── Multi-dossiers ──────────────────────────────────────────────────────────

DOSSIER_CONFIG_VERSION = "1.0"
DOSSIER_SLUG_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
DOSSIER_SLUG_MAX_LENGTH = 50
DOSSIER_NAME_MAX_LENGTH = 200
TOKEN_MIN_LENGTH = 10
