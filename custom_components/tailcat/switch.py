"""Switch to enable or disable a tailcat tunnel."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLED
from .entity import tailcat_device_info
from .process import TailcatProcessManager, signal_update


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TailcatTunnelSwitch(entry.runtime_data)])


class TailcatTunnelSwitch(SwitchEntity):
    """Enabling/disabling persists to config entry options.

    The actual start/stop happens in the options update listener in
    __init__.py, so this entity only needs to flip CONF_ENABLED.
    """

    _attr_has_entity_name = True
    _attr_name = "Tunnel enabled"
    _attr_should_poll = False

    def __init__(self, manager: TailcatProcessManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_enabled"
        self._attr_device_info = tailcat_device_info(manager)

    @property
    def is_on(self) -> bool:
        return self._manager.entry.options.get(CONF_ENABLED, True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        entry = self._manager.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_ENABLED: enabled}
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_update(self._manager.entry.entry_id),
                self.async_write_ha_state,
            )
        )
