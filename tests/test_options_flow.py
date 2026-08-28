"""Tests for the options flow (reconfiguring an existing tunnel).

Regression coverage for a real bug found while building this: current
Home Assistant core makes `OptionsFlow.config_entry` a read-only property
resolved from `self.handler`, so setting `self.config_entry = ...` in
`__init__` (the old, once-common pattern) raises AttributeError.
"""
from __future__ import annotations

import stat

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tailcat.const import (
    CONF_BINARY_PATH,
    CONF_ENABLED,
    CONF_KEY_MODE,
    CONF_MODE,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
    KEY_MODE_EPHEMERAL,
    MODE_PORT,
)


@pytest.fixture
def fake_binary(tmp_path):
    """A tiny executable script that stands in for a real tailcat binary."""
    path = tmp_path / "tailcat"
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


async def test_options_flow_updates_port(hass, fake_binary) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My tunnel",
        options={
            CONF_NAME: "My tunnel",
            CONF_BINARY_PATH: fake_binary,
            CONF_MODE: MODE_PORT,
            CONF_PORT: 8123,
            CONF_KEY_MODE: KEY_MODE_EPHEMERAL,
            CONF_ENABLED: True,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "user"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_NAME: "My tunnel", CONF_BINARY_PATH: fake_binary},
    )
    assert result["step_id"] == "mode"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODE: MODE_PORT}
    )
    assert result["step_id"] == "port"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PORT: 9000}
    )
    assert result["step_id"] == "key"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_KEY_MODE: KEY_MODE_EPHEMERAL}
    )
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PORT] == 9000
