"""Tests for the tailcat subprocess manager."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.components.persistent_notification import (
    _async_get_or_create_notifications,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tailcat.const import (
    CONF_ALLOW_NODEKEY,
    CONF_BINARY_PATH,
    CONF_KEY_MODE,
    CONF_KEY_NAME,
    CONF_MODE,
    CONF_PORT,
    DOMAIN,
    KEY_MODE_SAVED,
    MODE_ALL,
    MODE_PORT,
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_STOPPED,
)
from custom_components.tailcat.process import TailcatProcessManager, build_args

from .helpers import FakeProcess


def test_build_args_port_mode_ephemeral_key() -> None:
    options = {CONF_MODE: MODE_PORT, CONF_PORT: 8123}
    assert build_args(options) == ["--serve=8123", "--full-address", "--key=new"]


def test_build_args_all_mode_saved_key() -> None:
    options = {
        CONF_MODE: MODE_ALL,
        CONF_KEY_MODE: KEY_MODE_SAVED,
        CONF_KEY_NAME: "home",
    }
    assert build_args(options) == ["--serve=all", "--full-address", "--key=home"]


def test_build_args_allow_nodekey() -> None:
    options = {CONF_MODE: MODE_ALL, CONF_ALLOW_NODEKEY: "abc123"}
    args = build_args(options)
    assert args[-1] == "--allow=abc123"


def _make_entry(options: dict) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test tunnel",
        options={CONF_BINARY_PATH: "/fake/tailcat", **options},
    )


async def test_start_extracts_token_and_notifies(hass) -> None:
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)

    fake_process = FakeProcess(stderr_lines=[b"tc" + b"a" * 30 + b"\n"])
    with patch(
        "custom_components.tailcat.process.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake_process),
    ):
        await manager.async_start()
        await asyncio.sleep(0.05)

    assert manager.status == STATUS_RUNNING
    assert manager.last_token == "tc" + "a" * 30
    notifications = _async_get_or_create_notifications(hass)
    assert f"{DOMAIN}_{entry.entry_id}_token" in notifications

    await manager.async_shutdown()


async def test_unexpected_exit_marks_error_and_retries(hass) -> None:
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)

    fake_process = FakeProcess(stderr_lines=[])
    with patch(
        "custom_components.tailcat.process.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake_process),
    ):
        await manager.async_start()
        await asyncio.sleep(0.05)
        fake_process._exited.set()  # simulate the process dying on its own
        await asyncio.sleep(0.05)

    assert manager.status == STATUS_ERROR
    assert manager._consecutive_failures == 1

    await manager.async_shutdown()


async def test_recent_stderr_is_captured_for_diagnostics(hass) -> None:
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)

    fake_process = FakeProcess(stderr_lines=[b"flag provided but not defined: -bogus\n"])
    with patch(
        "custom_components.tailcat.process.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake_process),
    ):
        await manager.async_start()
        await asyncio.sleep(0.05)
        fake_process._exited.set()
        await asyncio.sleep(0.05)

    assert "flag provided but not defined: -bogus" in manager._recent_stderr

    await manager.async_shutdown()


async def test_repeated_quick_crashes_keep_incrementing_failures(hass) -> None:
    """A run under STABLE_UPTIME_SECONDS never resets the failure count."""
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)

    async def _crash_once() -> None:
        fake_process = FakeProcess(stderr_lines=[])
        with patch(
            "custom_components.tailcat.process.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_process),
        ):
            await manager.async_start()
            await asyncio.sleep(0.02)
            fake_process._exited.set()
            await asyncio.sleep(0.02)

    await _crash_once()
    assert manager._consecutive_failures == 1
    await _crash_once()
    assert manager._consecutive_failures == 2

    await manager.async_shutdown()


async def test_stable_run_resets_failure_count(hass) -> None:
    """A run that stays up past STABLE_UPTIME_SECONDS resets on its next crash."""
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)
    manager._consecutive_failures = 3  # pretend a few quick crashes already happened

    fake_process = FakeProcess(stderr_lines=[])
    with (
        patch(
            "custom_components.tailcat.process.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_process),
        ),
        patch("custom_components.tailcat.process.STABLE_UPTIME_SECONDS", 0),
    ):
        await manager.async_start()
        await asyncio.sleep(0.02)
        fake_process._exited.set()
        await asyncio.sleep(0.02)

    # Reset to 0, then incremented for this crash: back to 1, not 4.
    assert manager._consecutive_failures == 1

    await manager.async_shutdown()


async def test_stop_sets_status_stopped(hass) -> None:
    entry = _make_entry({CONF_MODE: MODE_PORT, CONF_PORT: 8123})
    entry.add_to_hass(hass)
    manager = TailcatProcessManager(hass, entry)

    fake_process = FakeProcess(stderr_lines=[])
    with patch(
        "custom_components.tailcat.process.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=fake_process),
    ):
        await manager.async_start()
        await asyncio.sleep(0.05)
        await manager.async_stop()

    assert manager.status == STATUS_STOPPED
    assert fake_process.terminated
