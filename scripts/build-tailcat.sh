#!/usr/bin/env bash
# Cross-compile the tailcat binary for a Home Assistant host's architecture.
#
# Usage: scripts/build-tailcat.sh <arch>
#   arch: auto | amd64 | arm64 | armv7 | armv6
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/../dist"
TAILCAT_REPO="https://github.com/tailscale/tailcat"

usage() {
  cat <<EOF
Usage: $(basename "$0") <arch>

  <arch>  Target architecture for the tailcat binary. One of:
            auto   - autodetect *this* machine's architecture
            amd64  - x86_64 (a generic PC or server)
            arm64  - 64-bit ARM (e.g. Raspberry Pi 4/5 on the 64-bit OS)
            armv7  - 32-bit ARM (e.g. older Raspberry Pi images)
            armv6  - 32-bit ARM, single-core Pi (Pi Zero, Pi 1)

Produces a static Linux binary in ./dist/, ready to copy to your Home
Assistant host's /config directory.
EOF
}

if [[ $# -ne 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 1
fi

requested_arch="$1"

detect_local_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64 | arm64) echo "arm64" ;;
    armv7l) echo "armv7" ;;
    armv6l) echo "armv6" ;;
    *)
      echo "Cannot autodetect: unrecognized 'uname -m' output '$(uname -m)'." >&2
      echo "Pass the target architecture explicitly instead (see --help)." >&2
      exit 1
      ;;
  esac
}

if [[ "$requested_arch" == "auto" ]]; then
  arch="$(detect_local_arch)"
  echo "Autodetected this machine's architecture: $arch (uname -m: $(uname -m))"
else
  arch="$requested_arch"
fi

goarm=""
case "$arch" in
  amd64) goarch="amd64" ;;
  arm64) goarch="arm64" ;;
  armv7)
    goarch="arm"
    goarm="7"
    ;;
  armv6)
    goarch="arm"
    goarm="6"
    ;;
  *)
    echo "Unknown architecture '$arch'." >&2
    usage
    exit 1
    ;;
esac

suggest_install() {
  local tool="$1"
  cat >&2 <<EOF
'$tool' was not found on PATH. Install it, then re-run this script:

  Debian/Ubuntu : sudo apt install $tool
  Fedora        : sudo dnf install $tool
  Arch Linux    : sudo pacman -S $tool
  macOS         : brew install $tool
EOF
}

if ! command -v go >/dev/null 2>&1; then
  cat >&2 <<'EOF'
'go' was not found on PATH. Install Go, then re-run this script:

  Debian/Ubuntu : sudo apt install golang-go
                  (Debian/Ubuntu often ship an older Go; for a current
                   version use https://go.dev/doc/install instead)
  Fedora        : sudo dnf install golang
  Arch Linux    : sudo pacman -S go
  macOS         : brew install go
  Any platform  : https://go.dev/dl/

After installing, open a new shell (so PATH picks it up) and re-run this
script.
EOF
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  suggest_install git
  exit 1
fi

echo "Using $(go version)"

src_dir="$(mktemp -d)"
trap 'rm -rf "$src_dir"' EXIT

echo "Fetching tailcat source from $TAILCAT_REPO ..."
git clone --quiet --depth 1 "$TAILCAT_REPO" "$src_dir"

mkdir -p "$DIST_DIR"
out_file="$DIST_DIR/tailcat-linux-$arch"

echo "Building for linux/$arch${goarm:+ (GOARM=$goarm)}..."
(
  cd "$src_dir"
  export CGO_ENABLED=0
  export GOOS=linux
  export GOARCH="$goarch"
  if [[ -n "$goarm" ]]; then
    export GOARM="$goarm"
  fi
  go build -o "$out_file" ./cmd/tailcat
)
chmod +x "$out_file"

# Also drop a plain "tailcat" copy, matching the path suggested by default
# in the Home Assistant integration's config flow.
cp "$out_file" "$DIST_DIR/tailcat"
chmod +x "$DIST_DIR/tailcat"

echo
echo "Built: $out_file"
echo "sha256: $(sha256sum "$out_file" | cut -d' ' -f1)"
echo
cat <<EOF
Next steps on the Home Assistant host:
  1. Create the target directory and copy the binary into it, e.g.:
       ssh <ha-host> mkdir -p /config/tailcat
       scp "$out_file" <ha-host>:/config/tailcat/tailcat
     (or use Samba / the Studio Code Server add-on instead of scp)
  2. Make sure it is executable on the host:
       ssh <ha-host> chmod +x /config/tailcat/tailcat
  3. In the Tailcat integration's config flow, set the binary path to
     /config/tailcat/tailcat (or wherever you copied it).
EOF
