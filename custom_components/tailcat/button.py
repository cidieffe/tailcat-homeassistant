"""Buttons to restart a tunnel or reveal its current token on demand."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import tailcat_device_info
from .process import TailcatProcessManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities([TailcatRestartButton(manager), TailcatShowTokenButton(manager)])


class _TailcatButtonBase(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, manager: TailcatProcessManager) -> None:
        self._manager = manager
        self._attr_device_info = tailcat_device_info(manager)


class TailcatRestartButton(_TailcatButtonBase):
    _attr_name = "Restart tunnel"

    def __init__(self, manager: TailcatProcessManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_restart"

    async def async_press(self) -> None:
        await self._manager.async_restart()


class TailcatShowTokenButton(_TailcatButtonBase):
    _attr_name = "Show token"

    def __init__(self, manager: TailcatProcessManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_show_token"

    async def async_press(self) -> None:
        await self._manager.async_notify_current_token()
