"""Tests for setting up/unloading the integration and its services."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tailcat.const import (
    ATTR_TOKEN,
    CONF_BINARY_PATH,
    CONF_ENABLED,
    CONF_MODE,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
    MODE_PORT,
    SERVICE_RESTART_TUNNEL,
    SERVICE_SHOW_TOKEN,
)

from .helpers import FakeProcess


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My tunnel",
        options={
            CONF_NAME: "My tunnel",
            CONF_BINARY_PATH: "/fake/tailcat",
            CONF_MODE: MODE_PORT,
            CONF_PORT: 8123,
            CONF_ENABLED: True,
        },
    )


async def test_setup_unload_and_services(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    # A fresh FakeProcess per spawn, like a real subprocess exec would give us
    # (start is called twice: once on setup, once via the restart service).
    async def _spawn(*args, **kwargs):
        return FakeProcess(stderr_lines=[b"tc" + b"b" * 30 + b"\n"])

    with patch(
        "custom_components.tailcat.process.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=_spawn),
    ):
        # Not hass.async_block_till_done(): the stderr-tailing tasks run for
        # as long as the tunnel is up, so it would wait forever.
        assert await hass.config_entries.async_setup(entry.entry_id)
        await asyncio.sleep(0.05)  # let the stderr reader pick up the token

        assert hass.services.has_service(DOMAIN, SERVICE_SHOW_TOKEN)
        assert hass.services.has_service(DOMAIN, SERVICE_RESTART_TUNNEL)

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SHOW_TOKEN,
            {"config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )
        assert response[ATTR_TOKEN] == "tc" + "b" * 30

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESTART_TUNNEL,
            {"config_entry_id": entry.entry_id},
            blocking=True,
        )
        await asyncio.sleep(0.05)

        assert await hass.config_entries.async_unload(entry.entry_id)
