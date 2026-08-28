"""Diagnostics support for Tailcat.

The connection token itself never lives in config entry data/options (it is
only held in memory by the process manager), so there is nothing to redact
there; the client allow-list is redacted out of caution since it identifies
specific peers.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ALLOW_NODEKEY

TO_REDACT = {CONF_ALLOW_NODEKEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    manager = entry.runtime_data
    return {
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "status": manager.status,
        "has_token": manager.last_token is not None,
    }
