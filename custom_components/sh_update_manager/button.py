"""Button entities for Smarter.Homes Update Manager v2.0.0.

Hub device: 3 buttons (scan_all, start_all, stop_all)
Per-queue device: 5 buttons (scan, start, stop, skip_current, retry_failed)

by Smarter Homes LLC — smarter.homes
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SW_VERSION
from .device_link import hub_link
from .queue_manager import QueueCoordinator, NamedQueue


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: QueueCoordinator = data["coordinator"]

    entities: list[ButtonEntity] = []
    entities.append(ScanAllButton(coordinator, entry))
    entities.append(StartAllButton(coordinator, entry))
    entities.append(StopAllButton(coordinator, entry))

    for queue in coordinator.queues:
        entities.append(QueueScanButton(queue, coordinator, entry))
        entities.append(QueueStartButton(queue, coordinator, entry))
        entities.append(QueueStopButton(queue, coordinator, entry))
        entities.append(QueueSkipCurrentButton(queue, entry))
        entities.append(QueueRetryFailedButton(queue, coordinator, entry))

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


class ScanAllButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:magnify-scan"

    def __init__(self, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_scan_all"
        self._attr_name = "Scan All Queues"
        self._attr_device_info = _hub_device_info(entry)

    async def async_press(self) -> None:
        await self._coordinator.async_scan_all()


class StartAllButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_start_all"
        self._attr_name = "Start All Queues"
        self._attr_device_info = _hub_device_info(entry)

    async def async_press(self) -> None:
        for q in self._coordinator.queues_by_priority:
            if q.pending_count > 0:
                await q.async_start()


class StopAllButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:stop-circle"

    def __init__(self, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_stop_all"
        self._attr_name = "Stop All Queues"
        self._attr_device_info = _hub_device_info(entry)

    async def async_press(self) -> None:
        await self._coordinator.async_stop_all()


class QueueScanButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:magnify"

    def __init__(self, queue: NamedQueue, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._queue = queue
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_scan"
        self._attr_name = "Scan"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_press(self) -> None:
        await self._queue.async_scan()
        await self._coordinator.async_save()


class QueueStartButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:play"

    def __init__(self, queue: NamedQueue, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._queue = queue
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_start"
        self._attr_name = "Start"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_press(self) -> None:
        await self._queue.async_start()
        await self._coordinator.async_save()


class QueueStopButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:stop"

    def __init__(self, queue: NamedQueue, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._queue = queue
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_stop"
        self._attr_name = "Stop"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_press(self) -> None:
        await self._queue.async_stop()
        await self._coordinator.async_save()


class QueueSkipCurrentButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:skip-next"

    def __init__(self, queue: NamedQueue, entry: ConfigEntry) -> None:
        self._queue = queue
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_skip"
        self._attr_name = "Skip Current"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_press(self) -> None:
        await self._queue.async_skip_current()


class QueueRetryFailedButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:replay"

    def __init__(self, queue: NamedQueue, coordinator: QueueCoordinator, entry: ConfigEntry) -> None:
        self._queue = queue
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_{queue.slug}_retry"
        self._attr_name = "Retry Failed"
        self._attr_device_info = _queue_device_info(entry, queue)

    async def async_press(self) -> None:
        await self._queue.async_retry_failed()
        await self._coordinator.async_save()
