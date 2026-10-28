"""Queue devices link to the hub device."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sh_update_manager.const import (
    CONF_QUEUES,
    DEFAULT_QUEUES,
    DOMAIN,
)


async def test_queue_devices_link_to_hub(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_QUEUES: list(DEFAULT_QUEUES)},
        version=6,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    hub = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert hub is not None
    queue_devices = [
        d for d in dr.async_entries_for_config_entry(registry, entry.entry_id)
        if d.id != hub.id
    ]
    assert len(queue_devices) == len(DEFAULT_QUEUES)
    assert all(d.via_device_id == hub.id for d in queue_devices)
