"""An interrupted run resumes through the real setup path, at HA startup."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sh_update_manager.const import (
    CONF_QUEUES,
    DOMAIN,
    ITEM_STATUS_INSTALLING,
    ITEM_STATUS_PENDING,
    QUEUE_STATE_RUNNING,
    STORAGE_KEY,
    STORAGE_VERSION,
)

from .test_queue_recovery import ENTITIES, FakeInstaller, _queue_config, installer  # noqa: F401


@pytest.mark.parametrize("resume", [True, False])
async def test_run_interrupted_by_restart_resumes_once_started(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    installer: FakeInstaller,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    resume: bool,
) -> None:
    config = _queue_config(resume_after_restart=resume)
    # What a restart mid-run leaves on disk.
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "test_queue": {
                "config": config,
                "state": QUEUE_STATE_RUNNING,
                "items": [
                    {"entity_id": ENTITIES[0], "status": ITEM_STATUS_INSTALLING},
                    {"entity_id": ENTITIES[1], "status": ITEM_STATUS_PENDING},
                ],
            }
        },
    }
    hass.set_state(CoreState.not_running)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_QUEUES: [config]}, version=6, minor_version=1
    )
    entry.add_to_hass(hass)

    with patch("custom_components.sh_update_manager.RESUME_DELAY_SECONDS", 0):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert installer.calls == []  # nothing runs before HA has started

        hass.set_state(CoreState.running)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done(wait_background_tasks=True)
        async with asyncio.timeout(10):
            while resume and len(installer.calls) < 2:
                await asyncio.sleep(0.05)
        await hass.async_block_till_done(wait_background_tasks=True)

    if resume:
        assert sorted(installer.calls) == sorted(ENTITIES)
    else:
        assert installer.calls == []

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "Task was destroyed but it is pending" not in caplog.text
    assert "Unable to remove unknown job listener" not in caplog.text
