"""The Tailcat integration: manage tailcat tunnels from Home Assistant."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import selector

from .const import ATTR_TOKEN, CONF_ENABLED, CONF_NAME, DOMAIN, SERVICE_RESTART_TUNNEL, SERVICE_SHOW_TOKEN
from .process import TailcatProcessManager

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SWITCH, Platform.BUTTON]

SERVICE_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            selector.ConfigEntrySelectorConfig(integration=DOMAIN)
        )
    }
)


def _get_manager(hass: HomeAssistant, entry_id: str) -> TailcatProcessManager:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ValueError(f"Unknown Tailcat config entry: {entry_id}")
    return entry.runtime_data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a tailcat tunnel from a config entry."""
    manager = TailcatProcessManager(hass, entry)
    entry.runtime_data = manager

    if entry.options.get(CONF_ENABLED, True):
        await manager.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a tailcat tunnel."""
    manager: TailcatProcessManager = entry.runtime_data
    await manager.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options: sync the entry title and restart the tunnel."""
    new_name = entry.options.get(CONF_NAME)
    if new_name and new_name != entry.title:
        hass.config_entries.async_update_entry(entry, title=new_name)
        return  # the title update re-triggers this listener; apply options then

    manager: TailcatProcessManager = entry.runtime_data
    await manager.async_stop()
    if entry.options.get(CONF_ENABLED, True):
        await manager.async_start()


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SHOW_TOKEN):
        return

    async def _handle_show_token(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass, call.data["config_entry_id"])
        await manager.async_notify_current_token()
        return {ATTR_TOKEN: manager.last_token}

    async def _handle_restart_tunnel(call: ServiceCall) -> None:
        manager = _get_manager(hass, call.data["config_entry_id"])
        await manager.async_restart()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_TOKEN,
        _handle_show_token,
        schema=SERVICE_ENTRY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESTART_TUNNEL, _handle_restart_tunnel, schema=SERVICE_ENTRY_SCHEMA
    )
