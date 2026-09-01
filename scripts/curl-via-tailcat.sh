#!/usr/bin/env bash
# Fetch a URL through a tailcat exit-node tunnel.
#
# Starts tailcat's ephemeral SOCKS5 proxy (`tailcat socks`) dialing the given
# connection token, and runs curl against it with 'all_proxy' pointed at that
# proxy - so the request goes out through whatever network the token's
# exit-node server sits on.
#
# Usage: scripts/curl-via-tailcat.sh [token] [url]
#   Prompts for whichever of token/url isn't passed as an argument.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [token] [url]

Fetches a page through a tailcat exit-node tunnel: starts an ephemeral
tailcat SOCKS5 proxy dialing <token> (an addrblob created elsewhere with
'tailcat serve exit-node', or the Tailcat integration's exit-node mode)
and runs curl against <url> with 'all_proxy' pointed at that proxy.

If not passed as arguments, you'll be prompted for the token and URL.
The token is a secret (whoever has it can route traffic through that
exit node), so it's read without echoing it to the terminal.

Set TAILCAT_BIN to use a specific tailcat binary; otherwise this looks
for 'tailcat' on PATH, then for a binary already built into ./dist/.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

find_tailcat() {
  if [[ -n "${TAILCAT_BIN:-}" ]]; then
    echo "$TAILCAT_BIN"
    return
  fi
  if command -v tailcat >/dev/null 2>&1; then
    command -v tailcat
    return
  fi
  local candidate
  for candidate in "$SCRIPT_DIR/../dist/tailcat" "$SCRIPT_DIR/../dist/tailcat-linux-"*; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return
    fi
  done
}

tailcat_bin="$(find_tailcat)"
if [[ -z "$tailcat_bin" ]]; then
  echo "Could not find a tailcat binary. Set TAILCAT_BIN, put 'tailcat' on" \
    "PATH, or build one with scripts/build-tailcat.sh." >&2
  exit 1
fi

token="${1:-}"
if [[ -z "$token" ]]; then
  read -rs -p "Tailcat exit-node token (input hidden): " token
  echo
fi
if [[ -z "$token" ]]; then
  echo "A token is required." >&2
  exit 1
fi

url="${2:-}"
if [[ -z "$url" ]]; then
  read -r -p "URL to fetch: " url
fi
if [[ -z "$url" ]]; then
  echo "A URL is required." >&2
  exit 1
fi

exec "$tailcat_bin" socks "$token" curl -sS -L "$url"
