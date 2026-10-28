"""Smarter.Homes Update Manager v2.1.4 — integration setup.

Device-per-queue architecture: each queue registers as a separate HA device.
A hub device provides global overview and controls.
Sidebar panel for queue management UI.

by Smarter Homes LLC — smarter.homes
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started

try:
    from homeassistant.components.frontend import async_register_built_in_panel
except ImportError:
    async_register_built_in_panel = None  # type: ignore[assignment]

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None  # type: ignore[assignment,misc]

from .const import (
    DOMAIN,
    CONF_QUEUES,
    CONF_SCAN_INTERVAL_MINUTES,
    SERVICE_SCAN_ALL,
    SERVICE_START_QUEUE,
    SERVICE_STOP_QUEUE,
    SERVICE_PAUSE_QUEUE,
    SERVICE_RESUME_QUEUE,
    SERVICE_SKIP_CURRENT,
    SERVICE_CLEAR_QUEUE,
    SERVICE_RETRY_FAILED,
    SERVICE_SCAN_QUEUE,
    SERVICE_ADD_QUEUE,
    SERVICE_EDIT_QUEUE,
    SERVICE_DELETE_QUEUE,
    DEFAULT_QUEUES,
    DEFAULT_INSTALL_DELAY,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_HISTORY_COUNT,
    DEFAULT_PRIORITY,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_RESUME_AFTER_RESTART,
    RESUME_DELAY_SECONDS,
    EXEC_MODES_LIST,
    TRIGGER_MODES_LIST,
    BATTERY_MODES_LIST,
    MATCH_TYPES_LIST,
    BATTERY_EXCLUDE,
    PANEL_URL,
    PANEL_TITLE,
    PANEL_ICON,
    URL_BASE,
    SW_VERSION,
)
from .queue_manager import QueueCoordinator

_LOGGER = logging.getLogger(__name__)

# Use Platform enum for forward setup
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]

QUEUE_SERVICE_SCHEMA = vol.Schema({
    vol.Required("queue_name"): cv.string,
})


def _hub_device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Smarter.Homes Update Manager",
        "manufacturer": "Smarter Homes LLC",
        "model": "Update Manager Hub",
        "sw_version": SW_VERSION,
    }


def queue_device_info(entry: ConfigEntry, queue_slug: str, queue_name: str) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_{queue_slug}")},
        "name": f"Update Queue: {queue_name}",
        "manufacturer": "Smarter Homes LLC",
        "model": "Update Queue",
        "sw_version": SW_VERSION,
        "via_device": (DOMAIN, entry.entry_id),
    }


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to current version."""
    _LOGGER.info(
        "Migrating Smarter.Homes Update Manager config entry from version %s.%s to 6",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version < 4:
        # Versions 1-3 (v1.x) had completely different data schemas.
        # Reset to defaults — user can reconfigure through options flow.
        new_data = {CONF_QUEUES: list(DEFAULT_QUEUES)}
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=6,
            minor_version=1,
        )
        _LOGGER.info(
            "Migration complete: reset to default queues (version %s -> 6)",
            config_entry.version,
        )
        return True

    if config_entry.version == 4:
        # v2.0.x -> v2.1.0: add Core Updates queue and exclude pattern on Add-ons.
        from .const import CORE_UPDATE_ENTITY_IDS
        queues = list(
            config_entry.options.get(CONF_QUEUES, config_entry.data.get(CONF_QUEUES, []))
        )
        has_core = any(q.get("name", "").lower() == "core updates" for q in queues)
        if not has_core:
            queues.insert(0, DEFAULT_QUEUES[0])  # Core Updates is first default
            _LOGGER.info("Migration v4->v5: added 'Core Updates' queue")
        for q in queues:
            if q.get("name", "").lower() == "add-ons" and not q.get("exclude_pattern"):
                q["exclude_pattern"] = ",".join(sorted(CORE_UPDATE_ENTITY_IDS))
                _LOGGER.info("Migration v4->v5: added exclude_pattern to 'Add-ons' queue")
        hass.config_entries.async_update_entry(
            config_entry,
            data={CONF_QUEUES: queues},
            version=5,
            minor_version=1,
        )
        _LOGGER.info("Migration complete: v4 -> v5 (core/add-on separation)")

    if config_entry.version == 5:
        # v2.1.3 -> v2.1.4: Z-Wave Firmware queue default flipped from
        # battery_handling=exclude to battery_handling=include (users with
        # battery Z-Wave sensors like ZSE44 were seeing them silently
        # skipped). Only flip queues that still look like the stock
        # Z-Wave Firmware default (name + zwave integration match);
        # don't stomp on users who intentionally set exclude.
        queues = list(
            config_entry.options.get(CONF_QUEUES, config_entry.data.get(CONF_QUEUES, []))
        )
        flipped = 0
        for q in queues:
            name = (q.get("name") or "").strip().lower()
            match_value = (q.get("match_value") or "").lower()
            if (
                name == "z-wave firmware"
                and "zwave" in match_value
                and q.get("battery_handling") == "exclude"
            ):
                q["battery_handling"] = "include"
                flipped += 1
        if flipped:
            _LOGGER.info(
                "Migration v5->v6: flipped battery_handling exclude->include "
                "on %d Z-Wave Firmware queue(s)", flipped,
            )
        # Persist to the same slot the value came from (options if present,
        # else data) so we don't accidentally wipe user-set options.
        if CONF_QUEUES in config_entry.options:
            hass.config_entries.async_update_entry(
                config_entry,
                options={**config_entry.options, CONF_QUEUES: queues},
                version=6,
                minor_version=1,
            )
        else:
            hass.config_entries.async_update_entry(
                config_entry,
                data={**config_entry.data, CONF_QUEUES: queues},
                version=6,
                minor_version=1,
            )
        _LOGGER.info("Migration complete: v5 -> v6 (Z-Wave battery default)")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smarter.Homes Update Manager from a config entry."""
    _LOGGER.debug("Setting up Smarter.Homes Update Manager entry %s", entry.entry_id)

    # --- 1. Load queue configuration ---
    try:
        queues_config = entry.options.get(
            CONF_QUEUES, entry.data.get(CONF_QUEUES, DEFAULT_QUEUES)
        )
        if not queues_config or not isinstance(queues_config, list):
            _LOGGER.warning(
                "Invalid queues config (type=%s), falling back to defaults",
                type(queues_config).__name__,
            )
            queues_config = list(DEFAULT_QUEUES)
    except Exception:
        _LOGGER.exception("Error reading queues config, using defaults")
        queues_config = list(DEFAULT_QUEUES)

    # --- 2. Create coordinator ---
    try:
        coordinator = QueueCoordinator(hass, queues_config)
    except Exception:
        _LOGGER.exception("Error creating QueueCoordinator")
        return False

    # --- 3. Load persisted state (non-fatal) ---
    try:
        await coordinator.async_load()
    except Exception:
        _LOGGER.exception("Error loading coordinator state (continuing with fresh state)")

    # --- 4. Store in hass.data ---
    hass.data.setdefault(DOMAIN, {})
    entry_bucket: dict[str, Any] = {
        "coordinator": coordinator,
        "entry": entry,
        "unsub_scan_interval": None,
    }
    hass.data[DOMAIN][entry.entry_id] = entry_bucket

    # --- 4b. Schedule automatic scans if configured ---
    _reschedule_auto_scan(hass, entry, entry_bucket, coordinator)

    # --- 5. Register sidebar panel (non-fatal) ---
    try:
        await _register_panel(hass)
    except Exception:
        _LOGGER.exception("Panel registration failed (non-fatal, continuing)")

    # --- 6. Register services ---
    try:
        _register_services(hass, coordinator)
    except Exception:
        _LOGGER.exception("Error registering services")
        return False

    # --- 7. Forward platform setup ---
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- 8. Register update listener ---
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # --- 9. Resume runs interrupted by a restart or reload ---
    async def _async_resume_interrupted() -> None:
        # Give integrations such as Z-Wave JS time to settle before the
        # resumed run rescans and starts installing.
        await asyncio.sleep(RESUME_DELAY_SECONDS)
        await coordinator.async_resume_interrupted()

    @callback
    def _start_resume(_hass: HomeAssistant) -> None:
        entry.async_create_background_task(
            hass, _async_resume_interrupted(), f"{DOMAIN} resume interrupted runs"
        )

    # Runs now if HA has already started (a reload), otherwise once it has.
    entry.async_on_unload(async_at_started(hass, _start_resume))

    _LOGGER.info(
        "Smarter.Homes Update Manager v%s set up successfully with %d queue(s)",
        SW_VERSION,
        len(queues_config),
    )
    return True


def _persist_queues(hass: HomeAssistant, coordinator: QueueCoordinator) -> None:
    """Persist current queue configs to the config entry options (survives restart)."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if entry_data.get("coordinator") is coordinator:
            entry = entry_data.get("entry")
            if entry:
                hass.config_entries.async_update_entry(
                    entry,
                    options={CONF_QUEUES: coordinator.get_all_queues_config()},
                )
                return


def _register_services(hass: HomeAssistant, coordinator: QueueCoordinator) -> None:
    """Register all domain services."""

    async def handle_scan_all(call: ServiceCall) -> None:
        await coordinator.async_scan_all()
        await coordinator.async_save()

    async def handle_start_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_start()
            await coordinator.async_save()

    async def handle_stop_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_stop()
            await coordinator.async_save()

    async def handle_pause_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_pause()

    async def handle_resume_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_resume()

    async def handle_skip_current(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_skip_current()

    async def handle_clear_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_clear()
            await coordinator.async_save()

    async def handle_retry_failed(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_retry_failed()
            await coordinator.async_save()

    async def handle_scan_queue(call: ServiceCall) -> None:
        q = coordinator.get_queue(call.data["queue_name"])
        if q:
            await q.async_scan()
            await coordinator.async_save()

    # --- Queue CRUD services ---
    async def handle_add_queue(call: ServiceCall) -> None:
        """Add a new queue and persist to config entry."""
        new_config = {
            "name": call.data["queue_name"],
            "match_type": call.data.get("match_type", "integration"),
            "match_value": call.data.get("match_value", ""),
            "exec_mode": call.data.get("exec_mode", "sequential"),
            "trigger_mode": call.data.get("trigger_mode", "manual"),
            "battery_handling": call.data.get("battery_handling", BATTERY_EXCLUDE),
            "stop_on_failure": call.data.get("stop_on_failure", False),
            "skip_unavailable": call.data.get("skip_unavailable", True),
            "install_delay": call.data.get("install_delay", DEFAULT_INSTALL_DELAY),
            "install_timeout": call.data.get("install_timeout", DEFAULT_INSTALL_TIMEOUT),
            "max_retries": call.data.get("max_retries", DEFAULT_MAX_RETRIES),
            "history_count": call.data.get("history_count", DEFAULT_HISTORY_COUNT),
            "priority": call.data.get("priority", DEFAULT_PRIORITY),
            "exclude_pattern": call.data.get("exclude_pattern", ""),
            "resume_after_restart": call.data.get(
                "resume_after_restart", DEFAULT_RESUME_AFTER_RESTART
            ),
        }
        coordinator.add_queue(new_config)
        # Persist to config entry so it survives restarts
        _persist_queues(hass, coordinator)
        await coordinator.async_save()
        _LOGGER.info("Added queue '%s' via service", new_config["name"])

    async def handle_edit_queue(call: ServiceCall) -> None:
        """Edit an existing queue's configuration."""
        queue_name = call.data["queue_name"]
        updates = {}
        for key in ("new_name", "match_type", "match_value", "exec_mode",
                     "trigger_mode", "battery_handling", "stop_on_failure",
                     "skip_unavailable", "install_delay", "install_timeout",
                     "max_retries", "history_count", "priority",
                     "exclude_pattern", "resume_after_restart"):
            if key in call.data:
                # Map new_name -> name for the config dict
                config_key = "name" if key == "new_name" else key
                updates[config_key] = call.data[key]
        if updates:
            coordinator.update_queue_config(queue_name, updates)
            _persist_queues(hass, coordinator)
            await coordinator.async_save()
            _LOGGER.info("Edited queue '%s' via service", queue_name)

    async def handle_delete_queue(call: ServiceCall) -> None:
        """Delete a queue."""
        queue_name = call.data["queue_name"]
        if coordinator.remove_queue(queue_name):
            _persist_queues(hass, coordinator)
            await coordinator.async_save()
            _LOGGER.info("Deleted queue '%s' via service", queue_name)

    ADD_QUEUE_SCHEMA = vol.Schema({
        vol.Required("queue_name"): cv.string,
        vol.Optional("match_type", default="integration"): vol.In(MATCH_TYPES_LIST),
        vol.Optional("match_value", default=""): cv.string,
        vol.Optional("exec_mode", default="sequential"): vol.In(EXEC_MODES_LIST),
        vol.Optional("trigger_mode", default="manual"): vol.In(TRIGGER_MODES_LIST),
        vol.Optional("battery_handling", default=BATTERY_EXCLUDE): vol.In(BATTERY_MODES_LIST),
        vol.Optional("stop_on_failure", default=False): cv.boolean,
        vol.Optional("skip_unavailable", default=True): cv.boolean,
        vol.Optional("install_delay", default=DEFAULT_INSTALL_DELAY): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=300)),
        vol.Optional("install_timeout", default=DEFAULT_INSTALL_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=60, max=14400)),
        vol.Optional("max_retries", default=DEFAULT_MAX_RETRIES): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("history_count", default=DEFAULT_HISTORY_COUNT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("priority", default=DEFAULT_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("exclude_pattern", default=""): cv.string,
        vol.Optional(
            "resume_after_restart", default=DEFAULT_RESUME_AFTER_RESTART
        ): cv.boolean,
    })

    EDIT_QUEUE_SCHEMA = vol.Schema({
        vol.Required("queue_name"): cv.string,
        vol.Optional("new_name"): cv.string,
        vol.Optional("match_type"): vol.In(MATCH_TYPES_LIST),
        vol.Optional("match_value"): cv.string,
        vol.Optional("exec_mode"): vol.In(EXEC_MODES_LIST),
        vol.Optional("trigger_mode"): vol.In(TRIGGER_MODES_LIST),
        vol.Optional("battery_handling"): vol.In(BATTERY_MODES_LIST),
        vol.Optional("stop_on_failure"): cv.boolean,
        vol.Optional("skip_unavailable"): cv.boolean,
        vol.Optional("install_delay"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
        vol.Optional("install_timeout"): vol.All(vol.Coerce(int), vol.Range(min=60, max=14400)),
        vol.Optional("max_retries"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("history_count"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("exclude_pattern"): cv.string,
        vol.Optional("resume_after_restart"): cv.boolean,
    })

    hass.services.async_register(DOMAIN, SERVICE_SCAN_ALL, handle_scan_all)
    hass.services.async_register(DOMAIN, SERVICE_START_QUEUE, handle_start_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_QUEUE, handle_stop_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_QUEUE, handle_pause_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESUME_QUEUE, handle_resume_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SKIP_CURRENT, handle_skip_current, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_QUEUE, handle_clear_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RETRY_FAILED, handle_retry_failed, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SCAN_QUEUE, handle_scan_queue, schema=QUEUE_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_QUEUE, handle_add_queue, schema=ADD_QUEUE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EDIT_QUEUE, handle_edit_queue, schema=EDIT_QUEUE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_QUEUE, handle_delete_queue, schema=QUEUE_SERVICE_SCHEMA)


async def _register_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel with robust fallbacks for different HA versions."""
    if DOMAIN in hass.data.get("panels_registered", set()):
        _LOGGER.debug("Panel already registered, skipping")
        return

    panel_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if not os.path.isdir(panel_dir):
        _LOGGER.warning("Frontend directory not found at %s", panel_dir)
        return

    panel_js = os.path.join(panel_dir, "panel.js")
    if not os.path.isfile(panel_js):
        _LOGGER.warning("panel.js not found at %s", panel_js)
        return

    try:
        # Register static path — try new API first (HA 2024.7+), then old API
        if StaticPathConfig is not None:
            await hass.http.async_register_static_paths([
                StaticPathConfig(URL_BASE, panel_dir, cache_headers=False)
            ])
        elif hasattr(hass.http, "register_static_path"):
            hass.http.register_static_path(URL_BASE, panel_dir, cache_headers=False)
        else:
            _LOGGER.warning("Cannot register static path — no compatible API found")
            return

        # Register panel
        if async_register_built_in_panel is not None:
            async_register_built_in_panel(
                hass,
                component_name="custom",
                sidebar_title=PANEL_TITLE,
                sidebar_icon=PANEL_ICON,
                frontend_url_path=PANEL_URL,
                config={
                    "_panel_custom": {
                        "name": "sh-update-manager-panel",
                        "module_url": f"{URL_BASE}/panel.js?v={SW_VERSION}",
                    }
                },
                require_admin=False,
            )
        else:
            _LOGGER.warning("async_register_built_in_panel not available — no sidebar panel")
            return

        hass.data.setdefault("panels_registered", set())
        hass.data["panels_registered"].add(DOMAIN)
        _LOGGER.info("Smarter.Homes Update Manager sidebar panel registered at /%s", PANEL_URL)
    except Exception:
        _LOGGER.exception("Could not register sidebar panel")


def _reschedule_auto_scan(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entry_bucket: dict[str, Any],
    coordinator: Any,
) -> None:
    """Register or re-register the auto-scan timer based on current config.

    Reads `scan_interval_minutes` from entry.options (falling back to
    entry.data). `0` disables the timer. Any existing timer is cancelled
    first so this is safe to call on every setup/reload.
    """
    # Cancel any existing timer first.
    unsub = entry_bucket.get("unsub_scan_interval")
    if unsub is not None:
        try:
            unsub()
        except Exception:  # pragma: no cover — best effort
            _LOGGER.exception("Failed to cancel previous auto-scan timer")
        entry_bucket["unsub_scan_interval"] = None

    interval_min = int(
        entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES,
            entry.data.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES),
        )
    )
    if interval_min <= 0:
        _LOGGER.info("Auto-scan disabled (scan_interval_minutes=0)")
        return

    async def _scheduled_scan(_now: Any) -> None:
        try:
            await coordinator.async_scan_all()
        except Exception:  # pragma: no cover — log but keep the timer alive
            _LOGGER.exception("Scheduled scan_all failed")

    entry_bucket["unsub_scan_interval"] = async_track_time_interval(
        hass, _scheduled_scan, timedelta(minutes=interval_min)
    )
    _LOGGER.info("Scheduled scan_all every %d minute(s)", interval_min)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if data:
        unsub = data.get("unsub_scan_interval")
        if unsub is not None:
            try:
                unsub()
            except Exception:  # pragma: no cover
                _LOGGER.exception("Failed to cancel auto-scan timer on unload")
            data["unsub_scan_interval"] = None
        coordinator = data.get("coordinator")
        if coordinator:
            await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
