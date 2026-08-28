"""Subprocess lifecycle management for a single tailcat tunnel."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_ALLOW_NODEKEY,
    CONF_BINARY_PATH,
    CONF_KEY_MODE,
    CONF_KEY_NAME,
    CONF_MODE,
    CONF_PORT,
    DOMAIN,
    ISSUE_CRASH_LOOP,
    ISSUE_INVALID_BINARY,
    ISSUE_KEY_GENERATION_FAILED,
    KEY_MODE_EPHEMERAL,
    KEY_MODE_SAVED,
    MAX_CONSECUTIVE_FAILURES,
    MODE_ALL,
    MODE_EXIT_NODE,
    MODE_NO_AUTH_SSH,
    MODE_PORT,
    RESTART_BACKOFF_SECONDS,
    STABLE_UPTIME_SECONDS,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_STARTING,
    STATUS_STOPPED,
    STDERR_BUFFER_LINES,
    TOKEN_REGEX,
)

_LOGGER = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(TOKEN_REGEX)


def signal_update(entry_id: str) -> str:
    """Return the dispatcher signal name used to notify entities of an update."""
    return f"{DOMAIN}_update_{entry_id}"


def saved_key_path(key_name: str) -> Path:
    """Where tailcat itself looks for a named saved key.

    Mirrors Go's os.UserConfigDir(): $XDG_CONFIG_HOME, or ~/.config.
    """
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "tailcat" / "keys" / f"{key_name}.private.json"


def build_args(options: Mapping[str, Any]) -> list[str]:
    """Translate config entry options into tailcat CLI arguments."""
    args: list[str] = []

    mode = options.get(CONF_MODE)
    if mode == MODE_PORT:
        args.append(f"--serve={options[CONF_PORT]}")
    elif mode == MODE_ALL:
        args.append("--serve=all")
    elif mode == MODE_NO_AUTH_SSH:
        args.append("--serve=no-auth-ssh")
    elif mode == MODE_EXIT_NODE:
        args.append("--serve=exit-node")

    args.append("--full-address")

    if options.get(CONF_KEY_MODE, KEY_MODE_EPHEMERAL) == KEY_MODE_EPHEMERAL:
        args.append("--key=new")
    else:
        args.append(f"--key={options[CONF_KEY_NAME]}")

    allow_nodekey = options.get(CONF_ALLOW_NODEKEY)
    if allow_nodekey:
        args.append(f"--allow={allow_nodekey}")

    return args


class TailcatProcessManager:
    """Runs and supervises a single tailcat subprocess for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.status = STATUS_STOPPED
        self.last_token: str | None = None

        self._process: asyncio.subprocess.Process | None = None
        self._stdio_tasks: list[asyncio.Task] = []
        self._supervisor_task: asyncio.Task | None = None
        self._stopping = False
        self._consecutive_failures = 0
        self._started_at: float | None = None
        self._recent_stderr: deque[str] = deque(maxlen=STDERR_BUFFER_LINES)

    @property
    def name(self) -> str:
        return self.entry.title

    def _notify_update(self) -> None:
        async_dispatcher_send(self.hass, signal_update(self.entry.entry_id))

    def _set_status(self, status: str) -> None:
        self.status = status
        self._notify_update()

    async def async_start(self) -> None:
        """Start (or restart, if already running) the tailcat subprocess."""
        if self._process is not None:
            return

        binary_path = self.entry.options[CONF_BINARY_PATH]
        argv = [binary_path, *build_args(self.entry.options)]
        self._stopping = False
        self._set_status(STATUS_STARTING)

        if self.entry.options.get(CONF_KEY_MODE) == KEY_MODE_SAVED:
            key_name = self.entry.options[CONF_KEY_NAME]
            if not await self._ensure_saved_key(binary_path, key_name):
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{ISSUE_KEY_GENERATION_FAILED}_{self.entry.entry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=ISSUE_KEY_GENERATION_FAILED,
                    translation_placeholders={"name": self.name, "key_name": key_name},
                )
                self._set_status(STATUS_ERROR)
                return
            ir.async_delete_issue(
                self.hass, DOMAIN, f"{ISSUE_KEY_GENERATION_FAILED}_{self.entry.entry_id}"
            )

        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as err:
            _LOGGER.error(
                "Failed to start tailcat tunnel %s using binary %s: %s",
                self.name,
                binary_path,
                err,
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_INVALID_BINARY}_{self.entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_INVALID_BINARY,
                translation_placeholders={"name": self.name, "path": binary_path},
            )
            self._set_status(STATUS_ERROR)
            return

        ir.async_delete_issue(
            self.hass, DOMAIN, f"{ISSUE_INVALID_BINARY}_{self.entry.entry_id}"
        )
        self.last_token = None
        self._started_at = self.hass.loop.time()
        self._recent_stderr.clear()
        self._stdio_tasks = [
            self.hass.async_create_task(self._read_stderr()),
            self.hass.async_create_task(self._drain_stdout()),
        ]
        self._supervisor_task = self.hass.async_create_task(self._supervise())
        self._set_status(STATUS_RUNNING)

    async def _ensure_saved_key(self, binary_path: str, key_name: str) -> bool:
        """Create the named persistent key with `genkey` if it doesn't exist.

        `genkey` refuses to overwrite an existing key (exits non-zero
        without --force), so this only runs it when the file is missing.
        """
        if saved_key_path(key_name).exists():
            return True

        _LOGGER.info(
            "Generating tailcat key '%s' for tunnel %s (not found at %s)",
            key_name,
            self.name,
            saved_key_path(key_name),
        )
        try:
            process = await asyncio.create_subprocess_exec(
                binary_path,
                "genkey",
                f"--key={key_name}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except OSError as err:
            _LOGGER.error(
                "Failed to run 'tailcat genkey --key=%s' for tunnel %s: %s",
                key_name,
                self.name,
                err,
            )
            return False

        if process.returncode != 0:
            _LOGGER.error(
                "'tailcat genkey --key=%s' failed for tunnel %s: %s",
                key_name,
                self.name,
                stderr.decode(errors="replace").strip(),
            )
            return False
        return True

    async def async_stop(self) -> None:
        """Stop the tailcat subprocess, if running."""
        self._stopping = True
        process = self._process
        if process is None:
            self._set_status(STATUS_STOPPED)
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

        await self._cleanup_tasks()
        self._process = None
        self._set_status(STATUS_STOPPED)

    async def async_restart(self) -> None:
        """Restart the tunnel (e.g. to rotate an ephemeral token)."""
        await self.async_stop()
        await self.async_start()

    async def async_shutdown(self) -> None:
        """Stop the process without touching entity/issue state (HA unload)."""
        self._stopping = True
        process = self._process
        if process is not None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        await self._cleanup_tasks()
        self._process = None

    async def _cleanup_tasks(self) -> None:
        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            self._supervisor_task = None
        for task in self._stdio_tasks:
            task.cancel()
        self._stdio_tasks = []

    async def _read_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            _LOGGER.debug("tailcat[%s] stderr: %s", self.name, text)
            self._recent_stderr.append(text)
            if self.last_token is None:
                match = _TOKEN_PATTERN.search(text)
                if match:
                    self.last_token = match.group(0)
                    await self._notify_token_ready()

    async def _drain_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            _LOGGER.debug("tailcat[%s] stdout: %s", self.name, line.decode(errors="replace").rstrip())

    async def _notify_token_ready(self) -> None:
        # Getting a token is not proof the process is stable: some failures
        # (e.g. a broken --serve mode) only surface a couple of seconds
        # later. _supervise() decides whether a run counts as stable.
        await self.async_notify_current_token()

    async def async_notify_current_token(self) -> None:
        """Show a persistent notification with the current token, on demand."""
        if self.last_token is None:
            message = f"Tunnel **{self.name}** has not produced a token yet."
        else:
            message = f"Connection token for tunnel **{self.name}**:\n\n`{self.last_token}`"
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"Tailcat: {self.name} token",
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_token",
        )
        self._notify_update()

    async def _supervise(self) -> None:
        assert self._process is not None
        return_code = await self._process.wait()
        self._process = None

        if self._stopping:
            self._set_status(STATUS_STOPPED)
            return

        uptime = self.hass.loop.time() - self._started_at if self._started_at else 0
        if uptime >= STABLE_UPTIME_SECONDS:
            # It ran long enough that this counts as a fresh problem, not a
            # continuation of a prior crash loop.
            self.reset_failure_count()

        stderr_tail = "\n".join(self._recent_stderr) or "(no output captured)"
        _LOGGER.warning(
            "tailcat tunnel %s exited unexpectedly with code %s after %.1fs. "
            "Its recent output was:\n%s",
            self.name,
            return_code,
            uptime,
            stderr_tail,
        )
        self._consecutive_failures += 1
        self._set_status(STATUS_ERROR)

        if self._consecutive_failures > MAX_CONSECUTIVE_FAILURES:
            last_error = next(
                (line for line in reversed(self._recent_stderr) if line.strip()),
                "(see Home Assistant logs)",
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_CRASH_LOOP}_{self.entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_CRASH_LOOP,
                translation_placeholders={"name": self.name, "error": last_error},
            )
            return

        delay_index = min(self._consecutive_failures - 1, len(RESTART_BACKOFF_SECONDS) - 1)
        delay = RESTART_BACKOFF_SECONDS[delay_index]
        _LOGGER.info("Restarting tailcat tunnel %s in %s seconds", self.name, delay)
        await asyncio.sleep(delay)
        if not self._stopping:
            await self.async_start()

    def reset_failure_count(self) -> None:
        self._consecutive_failures = 0
        ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_CRASH_LOOP}_{self.entry.entry_id}")
