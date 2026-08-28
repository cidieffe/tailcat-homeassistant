"""Binary sensor reporting whether a tailcat tunnel process is running."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODE, CONF_PORT, STATUS_RUNNING
from .entity import tailcat_device_info
from .process import TailcatProcessManager, signal_update


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TailcatTunnelBinarySensor(entry.runtime_data)])


class TailcatTunnelBinarySensor(BinarySensorEntity):
    """Reflects the manager's running status, pushed via dispatcher signal."""

    _attr_has_entity_name = True
    _attr_name = "Tunnel running"
    _attr_should_poll = False

    def __init__(self, manager: TailcatProcessManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_running"
        self._attr_device_info = tailcat_device_info(manager)

    @property
    def is_on(self) -> bool:
        return self._manager.status == STATUS_RUNNING

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "status": self._manager.status,
            "mode": self._manager.entry.options.get(CONF_MODE),
            "port": self._manager.entry.options.get(CONF_PORT),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_update(self._manager.entry.entry_id),
                self.async_write_ha_state,
            )
        )
