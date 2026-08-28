<img src="icon.png" alt="Tailcat icon" width="96" height="96">

# Tailcat for Home Assistant

A [HACS](https://hacs.xyz/) integration that manages one or more
[`tailcat`](https://github.com/tailscale/tailcat) tunnels from the Home
Assistant UI, with no YAML required.

`tailcat` is Tailscale's "netcat over the Tailscale data plane, without the
Tailscale control plane" tool: it opens an end-to-end encrypted, NAT-traversing
tunnel between two machines using a short-lived connection token, without a
Tailscale account, login, or tailnet. It runs entirely in userspace — no root,
no `/dev/net/tun`, no changes to routing or DNS — which is what makes it
practical to run as a plain subprocess from inside the Home Assistant Core
container.

This integration lets you, from **Settings → Devices & Services**:

- Create any number of independent tunnels, each exposing a single port,
  all local ports, an unauthenticated SSH server, or an exit node.
- Change a tunnel's port/mode/key from the options flow, without
  editing files or restarting containers by hand.
- Turn a tunnel on/off with a switch, restart it with a button, and reveal
  its current connection token on demand — without ever storing the token
  as a permanent entity state (it would otherwise end up in the recorder and
  the logbook).

## Requirements

There is no prebuilt `tailcat` binary — you need to build it yourself for
the CPU architecture of the machine actually running Home Assistant
(a container image's architecture is not always the same as your desktop's).

### 1. Find your Home Assistant host's architecture

- Home Assistant OS / Supervised: **Settings → System → Hardware** (or run
  `uname -m` from the *Terminal & SSH* / *Advanced SSH & Web Terminal*
  add-on). `aarch64` → 64-bit ARM (e.g. Raspberry Pi 4/5 with the 64-bit
  image), `armv7l` → 32-bit ARM (e.g. older Raspberry Pi images), `x86_64`
  → amd64.
- Container / Core installs: `uname -m` on the host running the container.

### 2. Cross-compile `tailcat` on any machine with Go installed

Run the helper script with the target architecture (`amd64`, `arm64`,
`armv7`, `armv6`), or `auto` to build for the machine you're running it on:

```bash
scripts/build-tailcat.sh arm64      # e.g. Raspberry Pi 4/5, 64-bit OS
scripts/build-tailcat.sh auto       # build for this machine's own architecture
```

It checks that `go` (and `git`) are installed — printing install
instructions per platform if not — clones `tailcat`, cross-compiles a
static binary (`CGO_ENABLED=0`, so it doesn't matter whether your Home
Assistant host uses glibc or musl), and drops it into `./dist/` along with
its sha256 checksum and the exact next steps to copy it over.

Equivalently, by hand:

```bash
git clone https://github.com/tailscale/tailcat
cd tailcat

# 64-bit ARM (Raspberry Pi 4/5, aarch64)
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o tailcat-arm64 ./cmd/tailcat

# 32-bit ARM (older Raspberry Pi, armv7l)
CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -o tailcat-armv7 ./cmd/tailcat

# amd64 / x86_64
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o tailcat-amd64 ./cmd/tailcat
```

### 3. Copy the binary onto the Home Assistant host

Copy the binary matching your architecture (`dist/tailcat-linux-<arch>` if
you used the script above) into the `config` directory (via Samba, the
*Studio Code Server* add-on, `scp`, etc.), for example to
`/config/tailcat/tailcat`, and make it executable:

```bash
chmod +x /config/tailcat/tailcat
```

`/config` is persistent and survives Home Assistant Core updates, so this
only needs to be done once (unless you want to update `tailcat` itself
later).

## Installing the integration via HACS

This repository is not in the default HACS store, so add it as a custom
repository:

1. HACS → the "⋮" menu → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Install "Tailcat", then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Tailcat**.

## Setting up a tunnel

The config flow walks you through:

1. **Name** and **path to the binary** you copied in step 3 above (e.g.
   `/config/tailcat/tailcat`). The binary is checked for existence and
   executable permission before you can continue.
2. **Mode**: forward a single port, forward all ports, run an
   unauthenticated SSH server, or act as an exit node.
   - The last two are security-sensitive (anyone with the token gets
     unauthenticated SSH access, or routes their traffic through your
     network) and require an explicit "I understand the risk" confirmation.
3. **Port** (only for single-port mode).
4. **Key type**: *ephemeral* generates a new address/token every time the
   tunnel (re)starts; *saved* keeps a stable address across restarts, at
   the cost of the address no longer rotating automatically.
5. **Advanced**: an optional allow-list of client public keys.

All of the above can be changed later from the tunnel's **Configure**
button — changing any option restarts the underlying `tailcat` process.

## Entities and services

Each tunnel is a device with:

- A **binary sensor** reflecting whether the process is currently running.
- A **switch** to enable/disable the tunnel (persisted, survives restarts).
- A **"Restart tunnel" button** — also useful to force a new token on an
  ephemeral-key tunnel.
- A **"Show token" button** — creates a persistent notification with the
  current connection token.

Two services are also available, useful for automations (e.g. sending the
token to your phone via `notify`) without it ever sitting in an entity's
state:

- `tailcat.show_token` — returns `{"token": "..."}` and shows the same
  persistent notification as the button above.
- `tailcat.restart_tunnel`.

## Connecting from another machine

Once a tunnel is running, its token is shown in the persistent notification
(or via `tailcat.show_token`). From another machine with `tailcat` installed:

```bash
tailcat <token> <local-port>   # forward mode
tailcat ssh <token>            # SSH mode
```

## Security notes

- Treat a tunnel's token like a password: whoever has it can connect.
  That's why this integration never keeps it in an entity's state (which
  would land in the recorder/logbook) — only in a dismissable notification
  and in the `show_token` service response.
- `no_auth_ssh` and `exit_node` modes are opt-in and gated behind an
  explicit confirmation in the UI for a reason — only use them on networks
  and hosts you fully trust.

## Development / running the tests

```bash
pip install -r requirements_test.txt
pytest tests/ -q
```

The test suite mocks the `tailcat` subprocess entirely, so it does not
require a real binary. It does **not** replace testing against a real
Home Assistant instance before relying on this in production. The token
extraction regex and CLI flags in `custom_components/tailcat/process.py`
have been checked against a real `tailcat` build's `--help` output and
actual server-mode stderr, but only on Linux/amd64 — worth re-checking if
you see it fail to pick up a token on another architecture.

## Icon

`icon.svg` / `icon.png` / `icon@2x.png` at the repository root are this
project's icon. It's used as-is wherever this repo is displayed (GitHub,
HACS's rendered README). To have it show up inside Home Assistant itself
(the integrations page, HACS's own icon column), it needs to be submitted
separately as a PR to
[home-assistant/brands](https://github.com/home-assistant/brands) under
`custom_integrations/tailcat/` — that's a different, community-reviewed
repository, not something this repo controls on its own.

## License

[MIT](LICENSE)
