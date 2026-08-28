"""Shared entity helpers for Tailcat platforms."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .process import TailcatProcessManager


def tailcat_device_info(manager: TailcatProcessManager) -> DeviceInfo:
    """Build the DeviceInfo shared by all entities of one tunnel."""
    return DeviceInfo(
        identifiers={(DOMAIN, manager.entry.entry_id)},
        name=manager.name,
        manufacturer="Tailscale",
        model="tailcat",
    )
