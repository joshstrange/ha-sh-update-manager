"""Tests for queue recovery: restarts, stuck installs, Skip and Stop.

Each test drives a NamedQueue against fake update entities and a fake
update.install service whose behaviour the test controls.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from custom_components.sh_update_manager.const import (
    ITEM_STATUS_COMPLETED,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_INSTALLING,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_SKIPPED,
    QUEUE_STATE_IDLE,
    QUEUE_STATE_RUNNING,
    QUEUE_STATE_STOPPED,
    STORAGE_KEY,
)
from custom_components.sh_update_manager.queue_manager import (
    NamedQueue,
    QueueCoordinator,
)

ENTITIES = ["update.dimmer_one", "update.dimmer_two"]


def _queue_config(**overrides: Any) -> dict[str, Any]:
    config = {
        "name": "Test Queue",
        "match_type": "entity",
        "match_value": ",".join(ENTITIES),
        "exec_mode": "sequential",
        "battery_handling": "include",
        "install_delay": 0,
        "install_timeout": 2,
        "max_retries": 2,
    }
    config.update(overrides)
    return config


class FakeInstaller:
    """update.install stand-in: installs at once unless told to hang."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.hang: set[str] = set()
        self.gates: dict[str, asyncio.Event] = {}
        self.calls: list[str] = []
        self.started: dict[str, asyncio.Event] = {e: asyncio.Event() for e in ENTITIES}

    async def handle(self, call: ServiceCall) -> None:
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        for entity_id in entity_ids:
            self.calls.append(entity_id)
            self.started[entity_id].set()
            if entity_id in self.gates:
                await self.gates[entity_id].wait()
            if entity_id in self.hang:
                # Like a Z-Wave install to a sleeping device: never returns.
                await asyncio.Event().wait()
            self.hass.states.async_set(entity_id, "off", {"in_progress": False})


@pytest.fixture
async def installer(hass: HomeAssistant) -> FakeInstaller:
    registry = er.async_get(hass)
    for entity_id in ENTITIES:
        registry.async_get_or_create(
            "update", "test", entity_id, suggested_object_id=entity_id.split(".")[1]
        )
        hass.states.async_set(entity_id, "on", {"in_progress": False})
    fake = FakeInstaller(hass)
    hass.services.async_register("update", "install", fake.handle)
    return fake


def _item(queue: NamedQueue, entity_id: str):
    return next(i for i in queue.items if i.entity_id == entity_id)


async def _wait_idle(queue: NamedQueue) -> None:
    async with asyncio.timeout(10):
        while queue._task is not None and not queue._task.done():
            await asyncio.sleep(0.05)


async def test_restart_loads_running_queue_as_idle(hass: HomeAssistant) -> None:
    """A saved running state and an in-flight item do not survive a restart."""
    queue = NamedQueue(hass, _queue_config())
    queue.load_state({
        "state": QUEUE_STATE_RUNNING,
        "items": [
            {"entity_id": ENTITIES[0], "status": ITEM_STATUS_INSTALLING,
             "started_at": "2026-05-03T13:41:14", "retries": 1},
            {"entity_id": ENTITIES[1], "status": ITEM_STATUS_PENDING},
        ],
    })

    assert queue.state == QUEUE_STATE_IDLE
    item = _item(queue, ENTITIES[0])
    assert item.status == ITEM_STATUS_PENDING
    assert item.started_at is None
    assert item.retries == 0
    assert queue._resume_pending


async def test_interrupted_run_stays_idle_when_resume_is_off(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    queue = NamedQueue(hass, _queue_config())
    queue.load_state({"state": QUEUE_STATE_RUNNING, "items": []})

    await queue.async_resume_if_interrupted()

    assert queue.state == QUEUE_STATE_IDLE
    assert installer.calls == []


async def test_interrupted_run_resumes_when_enabled(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    queue = NamedQueue(hass, _queue_config(resume_after_restart=True))
    queue.load_state({"state": QUEUE_STATE_RUNNING, "items": []})

    await queue.async_resume_if_interrupted()
    await _wait_idle(queue)

    assert sorted(installer.calls) == sorted(ENTITIES)
    assert all(i.status == ITEM_STATUS_COMPLETED for i in queue.items)
    # Resuming is a one-shot: a second call does nothing.
    await queue.async_resume_if_interrupted()
    assert len(installer.calls) == 2


async def test_start_recovers_running_state_without_worker(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    """Start is not ignored when 'running' has no task behind it."""
    queue = NamedQueue(hass, _queue_config())
    queue._state = QUEUE_STATE_RUNNING

    await queue.async_start()
    await _wait_idle(queue)

    assert sorted(installer.calls) == sorted(ENTITIES)


async def test_hung_install_times_out_and_queue_moves_on(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    installer.hang.add(ENTITIES[0])
    queue = NamedQueue(hass, _queue_config(install_timeout=1))

    await queue.async_start()
    await _wait_idle(queue)

    hung = _item(queue, ENTITIES[0])
    assert hung.status == ITEM_STATUS_FAILED
    assert "No result from the device" in hung.error
    # A timed-out install is not retried.
    assert installer.calls.count(ENTITIES[0]) == 1
    assert _item(queue, ENTITIES[1]).status == ITEM_STATUS_COMPLETED
    assert queue.state == QUEUE_STATE_IDLE


async def test_skip_cancels_hung_install(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    installer.hang.add(ENTITIES[0])
    queue = NamedQueue(hass, _queue_config(install_timeout=3600, stop_on_failure=True))

    await queue.async_start()
    async with asyncio.timeout(5):
        await installer.started[ENTITIES[0]].wait()
    await queue.async_skip_current()
    await _wait_idle(queue)

    assert _item(queue, ENTITIES[0]).status == ITEM_STATUS_SKIPPED
    # A skip is not a failure, so stop_on_failure does not halt the queue.
    assert _item(queue, ENTITIES[1]).status == ITEM_STATUS_COMPLETED


async def test_stop_returns_in_flight_item_to_pending(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    installer.hang.add(ENTITIES[0])
    queue = NamedQueue(hass, _queue_config(install_timeout=3600))

    await queue.async_start()
    async with asyncio.timeout(5):
        await installer.started[ENTITIES[0]].wait()
    await queue.async_stop()

    assert queue.state == QUEUE_STATE_STOPPED
    assert _item(queue, ENTITIES[0]).status == ITEM_STATUS_PENDING

    installer.hang.clear()
    await queue.async_start()
    await _wait_idle(queue)
    assert all(i.status == ITEM_STATUS_COMPLETED for i in queue.items)


async def test_cancelled_worker_is_remembered_as_interrupted(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    """HA cancelling the worker at shutdown is saved as an interrupted run."""
    installer.hang.add(ENTITIES[0])
    queue = NamedQueue(hass, _queue_config(install_timeout=3600))

    await queue.async_start()
    async with asyncio.timeout(5):
        await installer.started[ENTITIES[0]].wait()
    queue._task.cancel()
    await _wait_idle(queue)

    saved = queue.to_dict()
    assert saved["interrupted"] is True

    reloaded = NamedQueue(hass, _queue_config())
    reloaded.load_state(saved)
    assert reloaded.state == QUEUE_STATE_IDLE
    assert reloaded._resume_pending
    assert _item(reloaded, ENTITIES[0]).status == ITEM_STATUS_PENDING


async def test_progress_is_saved_without_a_service_call(
    hass: HomeAssistant, hass_storage: dict[str, Any], installer: FakeInstaller
) -> None:
    coordinator = QueueCoordinator(hass, [_queue_config()])
    queue = coordinator.queues[0]

    await queue.async_start()
    await _wait_idle(queue)
    # Flush the debounced save the way HA does at shutdown.
    await coordinator._store._async_handle_write_data()

    saved = hass_storage[STORAGE_KEY]["data"][queue.slug]
    assert [i["status"] for i in saved["items"]] == [ITEM_STATUS_COMPLETED] * 2


async def test_pause_holds_the_run_and_resume_continues_it(
    hass: HomeAssistant, installer: FakeInstaller
) -> None:
    installer.gates[ENTITIES[0]] = asyncio.Event()
    queue = NamedQueue(hass, _queue_config(install_timeout=3600))

    await queue.async_start()
    async with asyncio.timeout(5):
        await installer.started[ENTITIES[0]].wait()
    await queue.async_pause()
    installer.gates[ENTITIES[0]].set()
    async with asyncio.timeout(5):
        while _item(queue, ENTITIES[0]).status != ITEM_STATUS_COMPLETED:
            await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)

    # Paused between items: the worker waits instead of exiting.
    assert _item(queue, ENTITIES[1]).status == ITEM_STATUS_PENDING
    assert queue._task is not None and not queue._task.done()

    await queue.async_resume()
    await _wait_idle(queue)
    assert _item(queue, ENTITIES[1]).status == ITEM_STATUS_COMPLETED
