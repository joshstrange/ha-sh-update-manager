"""Sensor entities for Smarter.Homes Update Manager v2.0.0.

Hub device: 1 sensor (overview)
Per-queue device: 5 sensors (status, pending, items, last_run_result, history)

by Smarter Homes LLC — smarter.homes
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SW_VERSION
from .device_link import hub_link
from .queue_manager import QueueCoordinator, NamedQueue


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: QueueCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []
    entities.append(GlobalOverviewSensor(coordinator, entry))

    for queue in coordinator.queues:
        entities.append(QueueStatusSensor(queue, entry))
        entities.append(QueuePendingSensor(queue, entry))
        entities.append(QueueItemsSensor(queue, entry))
        entities.append(QueueLastRunResultSensor(queue, entry))
        entities.append(QueueHistorySensor(queue, entry))

    async_add_entities(entities)


class GlobalOverviewSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:update"

    def __init__(self, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_overview"
        self._attr_name = "Overview"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Smarter.Homes Update Manager",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Manager Hub",
            "sw_version": SW_VERSION,
        }

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_global_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_global_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        queues = self._coordinator.queues
        running = [q for q in queues if q.state == "running"]
        if running:
            return f"{len(running)} running"
        total_pending = sum(q.pending_count for q in queues)
        if total_pending > 0:
            return f"{total_pending} pending"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        queues = self._coordinator.queues
        return {
            "queue_count": len(queues),
            "queues": [
                {
                    "name": q.name,
                    "state": q.state,
                    "pending": q.pending_count,
                    "priority": q.priority,
                }
                for q in self._coordinator.queues_by_priority
            ],
        }


class QueueStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:list-status"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_status"
        self._attr_name = "Status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
            "name": f"Update Queue: {queue.name}",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Queue",
            "sw_version": SW_VERSION,
            **hub_link(entry),
        }

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self._queue.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "exec_mode": self._queue.exec_mode,
            "trigger_mode": self._queue.trigger_mode,
            "battery_handling": self._queue.battery_handling,
            "priority": self._queue.priority,
            "match_type": self._queue.match_type,
            "match_value": self._queue.match_value,
            "exclude_pattern": self._queue.exclude_pattern,
            "resume_after_restart": self._queue.resume_after_restart,
        }
        if self._queue.current_item:
            attrs["current_item"] = self._queue.current_item.entity_id
        return attrs


class QueuePendingSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_pending"
        self._attr_name = "Pending Updates"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
            "name": f"Update Queue: {queue.name}",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Queue",
            "sw_version": SW_VERSION,
            **hub_link(entry),
        }

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return self._queue.pending_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "summary": self._queue.pending_summary,
            "completed": self._queue.completed_count,
            "failed": self._queue.failed_count,
        }


class QueueItemsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_items"
        self._attr_name = "Queue Items"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
            "name": f"Update Queue: {queue.name}",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Queue",
            "sw_version": SW_VERSION,
            **hub_link(entry),
        }

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._queue.items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "items": self._queue.items_summary,
            "last_scan": self._queue.last_scan_summary,
        }


class QueueLastRunResultSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:clipboard-check-outline"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_last_run"
        self._attr_name = "Last Run Result"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
            "name": f"Update Queue: {queue.name}",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Queue",
            "sw_version": SW_VERSION,
            **hub_link(entry),
        }

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        lrr = self._queue.last_run_result
        if lrr:
            return lrr.result
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lrr = self._queue.last_run_result
        if not lrr:
            return {}
        return lrr.to_dict()


class QueueHistorySensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:history"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_history"
        self._attr_name = "Update History"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue.slug}")},
            "name": f"Update Queue: {queue.name}",
            "manufacturer": "Smarter Homes LLC",
            "model": "Update Queue",
            "sw_version": SW_VERSION,
            **hub_link(entry),
        }

    async def async_added_to_hass(self) -> None:
        self._queue.register_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._queue.remove_listener(self._on_update)

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._queue.run_history)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "runs": [r.to_dict() for r in reversed(self._queue.run_history)]
        }
