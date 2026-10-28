"""Switch entities for Smarter.Homes Update Manager v2.0.0.

Hub device: 1 switch (pause_all)
Per-queue device: 2 switches (pause, auto_trigger)

by Smarter Homes LLC — smarter.homes
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SW_VERSION, TRIGGER_AUTO, TRIGGER_MANUAL
from .device_link import hub_link
from .queue_manager import QueueCoordinator, NamedQueue


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: QueueCoordinator = data["coordinator"]

    entities: list[SwitchEntity] = []
    entities.append(PauseAllSwitch(coordinator, entry))

    for queue in coordinator.queues:
        entities.append(QueuePauseSwitch(queue, entry))
        entities.append(QueueAutoTriggerSwitch(queue, entry))

    async_add_entities(entities)


def _hub_device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Smarter.Homes Update Manager",
        "manufacturer": "Smarter Homes LLC",
        "model": "Update Manager Hub",
        "sw_version": SW_VERSION,
    }


def _queue_device_info(entry: ConfigEntry, queue: NamedQueue) -> dict:
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
        "name": f"Update Queue: {queue.name}",
        "manufacturer": "Smarter Homes LLC",
        "model": "Update Queue",
        "sw_version": SW_VERSION,
        **hub_link(entry),
    }


class PauseAllSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:pause-circle"

    def __init__(self, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_pause_all"
        self._attr_name = "Pause All"
        self._attr_device_info = _hub_device_info(entry)
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_global_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_global_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        for q in self._coordinator.queues:
            await q.async_pause()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        for q in self._coordinator.queues:
            await q.async_resume()
        self.async_write_ha_state()


class QueuePauseSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:pause"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_pause"
        self._attr_name = "Pause"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._queue.state == "paused"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._queue.async_pause()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._queue.async_resume()


class QueueAutoTriggerSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:auto-fix"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_auto_trigger"
        self._attr_name = "Auto-trigger"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._queue.trigger_mode == TRIGGER_AUTO

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._queue.config["trigger_mode"] = TRIGGER_AUTO
        self._queue._notify()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._queue.config["trigger_mode"] = TRIGGER_MANUAL
        self._queue._notify()
