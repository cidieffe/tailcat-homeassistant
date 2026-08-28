"""Tests for the Tailcat config flow."""
from __future__ import annotations

import stat

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tailcat.const import (
    CONF_BINARY_PATH,
    CONF_KEY_MODE,
    CONF_MODE,
    CONF_NAME,
    CONF_PORT,
    CONF_RISK_CONFIRM,
    DOMAIN,
    KEY_MODE_EPHEMERAL,
    MODE_NO_AUTH_SSH,
    MODE_PORT,
)


@pytest.fixture
def fake_binary(tmp_path):
    """A tiny executable script that stands in for a real tailcat binary."""
    path = tmp_path / "tailcat"
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


async def test_full_flow_port_mode(hass, fake_binary) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "My tunnel", CONF_BINARY_PATH: fake_binary}
    )
    assert result["step_id"] == "mode"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODE: MODE_PORT}
    )
    assert result["step_id"] == "port"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 8123}
    )
    assert result["step_id"] == "key"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_KEY_MODE: KEY_MODE_EPHEMERAL}
    )
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "My tunnel"
    assert result["options"][CONF_PORT] == 8123


async def test_binary_not_found_shows_error(hass) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "My tunnel", CONF_BINARY_PATH: "/does/not/exist"},
    )
    assert result["step_id"] == "user"
    assert result["errors"][CONF_BINARY_PATH] == "binary_not_found"


async def test_risky_mode_requires_confirmation(hass, fake_binary) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "My tunnel", CONF_BINARY_PATH: fake_binary}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODE: MODE_NO_AUTH_SSH}
    )
    assert result["step_id"] == "risk_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RISK_CONFIRM: False}
    )
    assert result["step_id"] == "risk_confirm"
    assert result["errors"][CONF_RISK_CONFIRM] == "risk_not_confirmed"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RISK_CONFIRM: True}
    )
    assert result["step_id"] == "key"
