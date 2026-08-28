"""Constants for the Tailcat integration."""
from __future__ import annotations

DOMAIN = "tailcat"

# Config / options keys
CONF_NAME = "name"
CONF_BINARY_PATH = "binary_path"
CONF_MODE = "mode"
CONF_PORT = "port"
CONF_RISK_CONFIRM = "risk_confirm"
CONF_KEY_MODE = "key_mode"
CONF_KEY_NAME = "key_name"
CONF_ALLOW_NODEKEY = "allow_nodekey"
CONF_ENABLED = "enabled"

DEFAULT_BINARY_PATH = "/config/tailcat/tailcat"

# Tunnel modes, mapped 1:1 to the `--serve=` flag of the tailcat CLI.
MODE_PORT = "port"
MODE_ALL = "all"
MODE_NO_AUTH_SSH = "no_auth_ssh"
MODE_EXIT_NODE = "exit_node"

MODES = [MODE_PORT, MODE_ALL, MODE_NO_AUTH_SSH, MODE_EXIT_NODE]
RISKY_MODES = {MODE_NO_AUTH_SSH, MODE_EXIT_NODE}

KEY_MODE_EPHEMERAL = "ephemeral"
KEY_MODE_SAVED = "saved"
KEY_MODES = [KEY_MODE_EPHEMERAL, KEY_MODE_SAVED]

# tailcat prints a line like "# \U0001F408 Server listening with new
# address: tc..." to stderr; verified against a real binary build.
TOKEN_REGEX = r"\btc[0-9A-Za-z_-]{20,}\b"

STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_ERROR = "error"

RESTART_BACKOFF_SECONDS = (5, 15, 30, 60)
MAX_CONSECUTIVE_FAILURES = 5

SERVICE_SHOW_TOKEN = "show_token"
SERVICE_RESTART_TUNNEL = "restart_tunnel"

ATTR_ENTRY_ID = "entry_id"
ATTR_TOKEN = "token"

ISSUE_INVALID_BINARY = "invalid_binary"
ISSUE_CRASH_LOOP = "crash_loop"
