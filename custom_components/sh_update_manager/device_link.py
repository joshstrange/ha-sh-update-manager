"""Link queue devices to the hub device in the device registry.

Home Assistant 2026.8 added DeviceInfo["via_device_id"], which takes the hub's
device registry id, and deprecated "via_device" (an identifier tuple), which
stops working in 2027.8. Older releases only understand "via_device".
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from .const import DOMAIN

_SUPPORTS_VIA_DEVICE_ID = (MAJOR_VERSION, MINOR_VERSION) >= (2026, 8)

_hub_device_ids: dict[str, str] = {}


def register_hub_device_id(entry: ConfigEntry, device_id: str) -> None:
    """Remember the hub's device registry id for this config entry."""
    _hub_device_ids[entry.entry_id] = device_id


def hub_link(entry: ConfigEntry) -> dict[str, Any]:
    """Return the DeviceInfo key linking a queue device to its hub."""
    if _SUPPORTS_VIA_DEVICE_ID and (device_id := _hub_device_ids.get(entry.entry_id)):
        return {"via_device_id": device_id}
    return {"via_device": (DOMAIN, entry.entry_id)}
