"""Queue manager for Smarter.Homes Update Manager v2.0.0.

Device-per-queue design with history, battery handling, retry, priority.

by Smarter Homes LLC — smarter.homes
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er
from homeassistant.const import STATE_ON

from .const import (
    DOMAIN,
    QUEUE_STATE_IDLE,
    QUEUE_STATE_PAUSED,
    QUEUE_STATE_RUNNING,
    QUEUE_STATE_STOPPED,
    EXEC_MODE_SEQUENTIAL,
    EXEC_MODE_PARALLEL,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_INSTALLING,
    ITEM_STATUS_COMPLETED,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_SKIPPED,
    MATCH_INTEGRATION,
    MATCH_AREA,
    MATCH_LABEL,
    MATCH_ENTITY,
    MATCH_DEVICE_NAME,
    MATCH_MANUFACTURER,
    CONF_EXCLUDE_PATTERN,
    BATTERY_EXCLUDE,
    BATTERY_DEFER_TO_END,
    INTEGRATION_GROUP_MAP,
    FORCE_SEQUENTIAL_GROUPS,
    RUN_RESULT_IDLE,
    RUN_RESULT_COMPLETED,
    RUN_RESULT_COMPLETED_WITH_FAILURES,
    RUN_RESULT_FAILED,
    CONF_MATCH_TYPE,
    CONF_MATCH_VALUE,
    CONF_EXEC_MODE,
    CONF_TRIGGER_MODE,
    CONF_BATTERY_HANDLING,
    CONF_STOP_ON_FAILURE,
    CONF_SKIP_UNAVAILABLE,
    CONF_INSTALL_DELAY,
    CONF_INSTALL_TIMEOUT,
    CONF_MAX_RETRIES,
    CONF_HISTORY_COUNT,
    CONF_PRIORITY,
    CONF_RESUME_AFTER_RESTART,
    DEFAULT_INSTALL_DELAY,
    DEFAULT_INSTALL_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_HISTORY_COUNT,
    DEFAULT_PRIORITY,
    DEFAULT_RESUME_AFTER_RESTART,
    SAVE_DELAY_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class QueueItem:
    """Represents a single update in a queue."""

    def __init__(self, entity_id: str, group: str = "other") -> None:
        self.entity_id = entity_id
        self.group = group
        self.retries = 0
        self.status = ITEM_STATUS_PENDING
        self.error: str | None = None
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.friendly_name: str | None = None
        self.installed_version: str | None = None
        self.latest_version: str | None = None
        self.is_battery: bool = False
        self.duration: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "group": self.group,
            "retries": self.retries,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "friendly_name": self.friendly_name,
            "installed_version": self.installed_version,
            "latest_version": self.latest_version,
            "is_battery": self.is_battery,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItem":
        item = cls(data["entity_id"], data.get("group", "other"))
        item.retries = data.get("retries", 0)
        item.status = data.get("status", ITEM_STATUS_PENDING)
        item.error = data.get("error")
        item.friendly_name = data.get("friendly_name")
        item.installed_version = data.get("installed_version")
        item.latest_version = data.get("latest_version")
        item.is_battery = data.get("is_battery", False)
        item.duration = data.get("duration")
        if data.get("started_at"):
            item.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            item.completed_at = datetime.fromisoformat(data["completed_at"])
        return item


class RunRecord:
    """Record of a single queue run (for history)."""

    def __init__(self) -> None:
        self.run_id: int = 0
        self.started: datetime | None = None
        self.ended: datetime | None = None
        self.total: int = 0
        self.succeeded: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self.result: str = RUN_RESULT_IDLE
        self.failed_items: list[dict[str, Any]] = []
        self.succeeded_items: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        duration = ""
        if self.started and self.ended:
            delta = self.ended - self.started
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            duration = f"{mins}m {secs}s"
        return {
            "run_id": self.run_id,
            "started": self.started.isoformat() if self.started else None,
            "ended": self.ended.isoformat() if self.ended else None,
            "duration": duration,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "result": self.result,
            "failed_items": self.failed_items,
            "succeeded_items": self.succeeded_items,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        rec = cls()
        rec.run_id = data.get("run_id", 0)
        rec.total = data.get("total", 0)
        rec.succeeded = data.get("succeeded", 0)
        rec.failed = data.get("failed", 0)
        rec.skipped = data.get("skipped", 0)
        rec.result = data.get("result", RUN_RESULT_IDLE)
        rec.failed_items = data.get("failed_items", [])
        rec.succeeded_items = data.get("succeeded_items", [])
        if data.get("started"):
            rec.started = datetime.fromisoformat(data["started"])
        if data.get("ended"):
            rec.ended = datetime.fromisoformat(data["ended"])
        return rec


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "queue"


class NamedQueue:
    """A single named update queue with independent config and state."""

    def __init__(self, hass: HomeAssistant, queue_config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = dict(queue_config)
        self.name: str = queue_config.get("name", "Unnamed Queue")
        self.slug = _slugify(self.name)
        self._items: list[QueueItem] = []
        self._state = QUEUE_STATE_IDLE
        self._current_item: QueueItem | None = None
        self._task: asyncio.Task | None = None
        # The install currently in flight (sequential mode), so Skip can
        # cancel it instead of only relabelling the item.
        self._item_task: asyncio.Task | None = None
        # Set when a run was cut short by a restart or reload, so setup can
        # resume it (if resume_after_restart is on) once HA has started.
        self._interrupted = False
        self._resume_pending = False
        self._last_success: str | None = None
        self._last_failure: str | None = None
        self._completed_count = 0
        self._failed_count = 0
        self._listeners: list[Any] = []
        self._run_history: deque[RunRecord] = deque(maxlen=self.history_count)
        self._current_run: RunRecord | None = None
        self._next_run_id = 1
        self._last_run_result: RunRecord | None = None
        # Transient diagnostics from the most recent scan. Not persisted —
        # regenerated on every async_scan() call. Exposed to the UI so users
        # can see *why* a given update entity did not end up in the queue
        # (e.g. battery device excluded, unavailable, no matching integration).
        self._last_scan_at: datetime | None = None
        self._last_scan_counts: dict[str, int] = {}
        self._last_scan_skipped: list[dict[str, Any]] = []
        self._last_scan_candidates: int = 0

    @property
    def priority(self) -> int:
        return self.config.get(CONF_PRIORITY, DEFAULT_PRIORITY)

    @property
    def match_type(self) -> str:
        return self.config.get(CONF_MATCH_TYPE, MATCH_INTEGRATION)

    @property
    def match_value(self) -> str:
        return self.config.get(CONF_MATCH_VALUE, "")

    @property
    def exec_mode(self) -> str:
        mode = self.config.get(CONF_EXEC_MODE, EXEC_MODE_SEQUENTIAL)
        match_vals = {v.strip() for v in self.match_value.split(",")}
        for val in match_vals:
            group = INTEGRATION_GROUP_MAP.get(val, val)
            if group in FORCE_SEQUENTIAL_GROUPS:
                return EXEC_MODE_SEQUENTIAL
        return mode

    @property
    def trigger_mode(self) -> str:
        return self.config.get(CONF_TRIGGER_MODE, "manual")

    @property
    def battery_handling(self) -> str:
        return self.config.get(CONF_BATTERY_HANDLING, BATTERY_EXCLUDE)

    @property
    def stop_on_failure(self) -> bool:
        return self.config.get(CONF_STOP_ON_FAILURE, False)

    @property
    def skip_unavailable(self) -> bool:
        return self.config.get(CONF_SKIP_UNAVAILABLE, True)

    @property
    def install_delay(self) -> int:
        return self.config.get(CONF_INSTALL_DELAY, DEFAULT_INSTALL_DELAY)

    @property
    def install_timeout(self) -> int:
        return self.config.get(CONF_INSTALL_TIMEOUT, DEFAULT_INSTALL_TIMEOUT)

    @property
    def resume_after_restart(self) -> bool:
        return self.config.get(CONF_RESUME_AFTER_RESTART, DEFAULT_RESUME_AFTER_RESTART)

    @property
    def max_retries(self) -> int:
        return self.config.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)

    @property
    def exclude_pattern(self) -> str:
        return self.config.get(CONF_EXCLUDE_PATTERN, "")

    @property
    def history_count(self) -> int:
        return self.config.get(CONF_HISTORY_COUNT, DEFAULT_HISTORY_COUNT)

    @property
    def state(self) -> str:
        return self._state

    @property
    def current_item(self) -> QueueItem | None:
        return self._current_item

    @property
    def items(self) -> list[QueueItem]:
        return list(self._items)

    @property
    def pending_count(self) -> int:
        return len([i for i in self._items if i.status == ITEM_STATUS_PENDING])

    @property
    def completed_count(self) -> int:
        return self._completed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    @property
    def last_success(self) -> str | None:
        return self._last_success

    @property
    def last_failure(self) -> str | None:
        return self._last_failure

    @property
    def last_run_result(self) -> RunRecord | None:
        return self._last_run_result

    @property
    def run_history(self) -> list[RunRecord]:
        return list(self._run_history)

    @property
    def items_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "entity_id": i.entity_id,
                "friendly_name": i.friendly_name,
                "status": i.status,
                "installed_version": i.installed_version,
                "latest_version": i.latest_version,
                "is_battery": i.is_battery,
                "retries": i.retries,
                "error": i.error,
                "duration": i.duration,
            }
            for i in self._items
        ]

    @property
    def last_scan_summary(self) -> dict[str, Any]:
        """Diagnostics from the most recent scan (transient, not persisted).

        Consumed by the sidebar panel and advanced automations that want to
        know *why* an update entity did not end up in this queue.
        """
        return {
            "at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "candidates": self._last_scan_candidates,
            "counts": dict(self._last_scan_counts),
            "skipped": list(self._last_scan_skipped),
        }

    @property
    def pending_summary(self) -> str:
        pending = [i for i in self._items if i.status == ITEM_STATUS_PENDING]
        if not pending:
            return "0 pending"
        mains = len([i for i in pending if not i.is_battery])
        battery = len([i for i in pending if i.is_battery])
        parts = [f"{len(pending)} pending"]
        if battery > 0:
            parts.append(f"({mains} mains, {battery} battery)")
        return " ".join(parts)

    def register_listener(self, listener: Any) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Any) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for ln in self._listeners:
            ln()

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "items": [i.to_dict() for i in self._items],
            "state": self._state,
            "interrupted": self._interrupted or self._state == QUEUE_STATE_RUNNING,
            "last_success": self._last_success,
            "last_failure": self._last_failure,
            "completed_count": self._completed_count,
            "failed_count": self._failed_count,
            "run_history": [r.to_dict() for r in self._run_history],
            "last_run_result": self._last_run_result.to_dict() if self._last_run_result else None,
            "next_run_id": self._next_run_id,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        self._items = [QueueItem.from_dict(d) for d in data.get("items", [])]
        self._state = data.get("state", QUEUE_STATE_IDLE)
        # No worker task survives a restart or reload, so a saved
        # running/paused state is stale: left as-is the queue reports
        # "running" forever and Start ignores it. Load it as idle and put
        # any item that was mid-install back to pending so it is retried
        # (the next scan drops it if the update actually landed).
        self._resume_pending = (
            self._state == QUEUE_STATE_RUNNING or data.get("interrupted", False)
        )
        if self._state in (QUEUE_STATE_RUNNING, QUEUE_STATE_PAUSED):
            _LOGGER.info(
                "Queue '%s': was %s when last saved; no run survives a restart, "
                "loading as idle", self.name, self._state,
            )
            self._state = QUEUE_STATE_IDLE
        for item in self._items:
            if item.status == ITEM_STATUS_INSTALLING:
                item.status = ITEM_STATUS_PENDING
                item.retries = 0
                item.error = None
                item.started_at = None
                item.completed_at = None
                item.duration = None
        self._last_success = data.get("last_success")
        self._last_failure = data.get("last_failure")
        self._completed_count = data.get("completed_count", 0)
        self._failed_count = data.get("failed_count", 0)
        self._next_run_id = data.get("next_run_id", 1)
        for rd in data.get("run_history", []):
            self._run_history.append(RunRecord.from_dict(rd))
        lrr = data.get("last_run_result")
        if lrr:
            self._last_run_result = RunRecord.from_dict(lrr)

    def _get_device_info(self, entity_entry: er.RegistryEntry) -> tuple[str, str, str]:
        """Return (device_name, manufacturer, model) for an entity's parent device."""
        try:
            from homeassistant.helpers import device_registry as dr
            dev_reg = dr.async_get(self.hass)
            if entity_entry.device_id:
                device = dev_reg.async_get(entity_entry.device_id)
                if device:
                    return (
                        device.name or "",
                        device.manufacturer or "",
                        device.model or "",
                    )
        except Exception:
            pass
        return ("", "", "")

    def _matches_exclude_pattern(self, entity_entry: er.RegistryEntry) -> bool:
        """Check if entity matches the exclude pattern (case-insensitive).

        Exclude patterns are comma-separated strings matched against:
        device name, manufacturer, model, entity_id, and friendly_name.
        """
        raw = self.exclude_pattern
        if not raw:
            return False
        patterns = [p.strip().lower() for p in raw.split(",") if p.strip()]
        if not patterns:
            return False
        dev_name, manufacturer, model = self._get_device_info(entity_entry)
        state = self.hass.states.get(entity_entry.entity_id)
        friendly = (state.attributes.get("friendly_name", "") if state else "").lower()
        search_fields = [
            entity_entry.entity_id.lower(),
            dev_name.lower(),
            manufacturer.lower(),
            model.lower(),
            friendly,
        ]
        for pat in patterns:
            for field in search_fields:
                if pat in field:
                    return True
        return False

    def _entity_matches(self, entity_entry: er.RegistryEntry) -> bool:
        targets = {v.strip() for v in self.match_value.split(",") if v.strip()}
        if self.match_type == MATCH_INTEGRATION:
            return entity_entry.platform in targets
        if self.match_type == MATCH_AREA:
            return entity_entry.area_id in targets if entity_entry.area_id else False
        if self.match_type == MATCH_LABEL:
            if hasattr(entity_entry, "labels") and entity_entry.labels:
                return bool(entity_entry.labels.intersection(targets))
            return False
        if self.match_type == MATCH_ENTITY:
            return entity_entry.entity_id in targets
        if self.match_type == MATCH_DEVICE_NAME:
            dev_name, _, model = self._get_device_info(entity_entry)
            combined = f"{dev_name} {model}".lower()
            return any(t.lower() in combined for t in targets)
        if self.match_type == MATCH_MANUFACTURER:
            _, manufacturer, _ = self._get_device_info(entity_entry)
            return manufacturer.lower() in {t.lower() for t in targets}
        return False

    def _is_battery_device(self, entity_entry: er.RegistryEntry) -> bool:
        try:
            from homeassistant.helpers import device_registry as dr
            dev_reg = dr.async_get(self.hass)
            if entity_entry.device_id:
                device = dev_reg.async_get(entity_entry.device_id)
                if device:
                    ent_reg = er.async_get(self.hass)
                    for ent in er.async_entries_for_device(ent_reg, device.id):
                        if ent.entity_id.startswith("sensor.") and "battery" in ent.entity_id:
                            return True
                        st = self.hass.states.get(ent.entity_id)
                        if st and st.attributes.get("device_class") == "battery":
                            return True
        except Exception:
            pass
        return False

    async def async_scan(self) -> int:
        ent_reg = er.async_get(self.hass)
        candidates: list[QueueItem] = []
        skipped_no_update = 0
        skipped_disabled = 0
        skipped_no_match = 0
        skipped_excluded = 0
        skipped_not_on = 0
        skipped_unavailable = 0
        skipped_battery = 0
        # Detailed per-entity skip log for the UI. Only records entities that
        # passed the match rule (otherwise the list would be huge). That means
        # users only see skip reasons for entities that "could have" been in
        # this queue — not every update entity in HA.
        skipped_details: list[dict[str, Any]] = []

        def _record_skip(
            entity_entry: er.RegistryEntry, reason: str, note: str = ""
        ) -> None:
            state = self.hass.states.get(entity_entry.entity_id)
            friendly = (
                state.attributes.get("friendly_name") if state else None
            ) or entity_entry.name or entity_entry.entity_id
            skipped_details.append({
                "entity_id": entity_entry.entity_id,
                "friendly_name": friendly,
                "platform": entity_entry.platform or "",
                "reason": reason,
                "note": note,
            })

        for entity_entry in ent_reg.entities.values():
            if not entity_entry.entity_id.startswith("update."):
                skipped_no_update += 1
                continue
            if not self._entity_matches(entity_entry):
                # Not eligible for THIS queue — don't log per-entity (noise).
                skipped_no_match += 1
                continue
            # Past this point the entity is in-scope for this queue, so any
            # skip is worth surfacing in the UI.
            if entity_entry.disabled:
                skipped_disabled += 1
                _record_skip(
                    entity_entry,
                    "disabled",
                    f"disabled_by={entity_entry.disabled_by}",
                )
                continue
            if self._matches_exclude_pattern(entity_entry):
                skipped_excluded += 1
                _record_skip(
                    entity_entry,
                    "exclude_pattern",
                    f"pattern='{self.exclude_pattern}'",
                )
                _LOGGER.debug(
                    "Queue '%s': skip %s (matches exclude pattern '%s')",
                    self.name, entity_entry.entity_id, self.exclude_pattern,
                )
                continue
            state = self.hass.states.get(entity_entry.entity_id)
            if state is None:
                skipped_not_on += 1
                _record_skip(entity_entry, "no_state", "entity has no state")
                continue
            if self.skip_unavailable and state.state == "unavailable":
                skipped_unavailable += 1
                _record_skip(
                    entity_entry,
                    "unavailable",
                    "entity state=unavailable (skip_unavailable=True)",
                )
                continue
            if state.state != STATE_ON:
                # 'off' = no update available. Not really an error; show in UI
                # so users can confirm "scan saw the entity, no update".
                skipped_not_on += 1
                _record_skip(
                    entity_entry,
                    "up_to_date",
                    f"state={state.state} (no update available)",
                )
                _LOGGER.debug(
                    "Queue '%s': skip %s (state=%s, need 'on')",
                    self.name, entity_entry.entity_id, state.state,
                )
                continue
            group = INTEGRATION_GROUP_MAP.get(entity_entry.platform, "other")
            is_battery = self._is_battery_device(entity_entry)
            if self.battery_handling == BATTERY_EXCLUDE and is_battery:
                skipped_battery += 1
                _record_skip(
                    entity_entry,
                    "battery_excluded",
                    "battery device (battery_handling=exclude on this queue)",
                )
                _LOGGER.debug(
                    "Queue '%s': skip %s (battery device, battery_handling=exclude)",
                    self.name, entity_entry.entity_id,
                )
                continue
            item = QueueItem(entity_entry.entity_id, group)
            item.is_battery = is_battery
            item.friendly_name = (
                state.attributes.get("friendly_name") or entity_entry.entity_id
            )
            item.installed_version = state.attributes.get("installed_version")
            item.latest_version = state.attributes.get("latest_version")
            candidates.append(item)

        if self.battery_handling == BATTERY_DEFER_TO_END:
            candidates.sort(key=lambda c: (1 if c.is_battery else 0))

        existing_map = {i.entity_id: i for i in self._items}
        candidate_ids = {c.entity_id for c in candidates}
        new_count = 0
        requeued_count = 0
        for c in candidates:
            existing = existing_map.get(c.entity_id)
            if existing is None:
                # Brand new candidate — add it.
                self._items.append(c)
                new_count += 1
                continue
            if existing.status in (
                ITEM_STATUS_COMPLETED,
                ITEM_STATUS_FAILED,
                ITEM_STATUS_SKIPPED,
            ):
                # A previously-finalized item has a fresh update available
                # (update entity is 'on' again). This happens when a new
                # version is released for the same entity after a prior run.
                # Reset the item back to pending so Scan/Start will pick it
                # up again. Refresh version/friendly_name from the candidate
                # so the UI reflects the new installed → latest transition.
                version_changed = (
                    existing.installed_version != c.installed_version
                    or existing.latest_version != c.latest_version
                )
                if version_changed:
                    existing.status = ITEM_STATUS_PENDING
                    existing.error = None
                    existing.retries = 0
                    existing.started_at = None
                    existing.completed_at = None
                    existing.duration = None
                    existing.installed_version = c.installed_version
                    existing.latest_version = c.latest_version
                    existing.friendly_name = c.friendly_name
                    existing.is_battery = c.is_battery
                    existing.group = c.group
                    requeued_count += 1
            else:
                # Pending/installing — keep authoritative state but refresh
                # version/display attributes so the UI stays current.
                existing.installed_version = c.installed_version
                existing.latest_version = c.latest_version
                existing.friendly_name = c.friendly_name
        self._items = [
            i for i in self._items
            if i.entity_id in candidate_ids
            or i.status in (ITEM_STATUS_INSTALLING, ITEM_STATUS_COMPLETED, ITEM_STATUS_FAILED)
        ]
        if self.battery_handling == BATTERY_DEFER_TO_END:
            pending = [i for i in self._items if i.status == ITEM_STATUS_PENDING]
            non_pending = [i for i in self._items if i.status != ITEM_STATUS_PENDING]
            pending.sort(key=lambda i: (1 if i.is_battery else 0))
            self._items = pending + non_pending

        self._last_scan_at = datetime.now()
        self._last_scan_candidates = len(candidates)
        self._last_scan_counts = {
            "disabled": skipped_disabled,
            "no_match": skipped_no_match,
            "excluded": skipped_excluded,
            "up_to_date": skipped_not_on,
            "unavailable": skipped_unavailable,
            "battery": skipped_battery,
        }
        # Cap at 200 to keep the sensor attribute payload under HA's state
        # size warning threshold (16 KB). Most installs have << 200 update
        # entities per queue anyway.
        self._last_scan_skipped = skipped_details[:200]

        self._notify()
        _LOGGER.info(
            "Queue '%s': %d candidates, %d new, %d re-queued, %d total "
            "(skipped: %d disabled, %d no-match, %d excluded, %d up-to-date, %d unavail, %d battery)",
            self.name, len(candidates), new_count, requeued_count, len(self._items),
            skipped_disabled, skipped_no_match, skipped_excluded, skipped_not_on,
            skipped_unavailable, skipped_battery,
        )
        return len(self._items)

    async def async_start(self) -> None:
        if self._state == QUEUE_STATE_RUNNING:
            if self._task is not None and not self._task.done():
                return
            _LOGGER.warning(
                "Queue '%s': marked running but has no worker; starting a new run",
                self.name,
            )
        await self.async_scan()
        runnable = [i for i in self._items if i.status == ITEM_STATUS_PENDING]
        if not runnable:
            return
        self._state = QUEUE_STATE_RUNNING
        self._current_run = RunRecord()
        self._current_run.run_id = self._next_run_id
        self._next_run_id += 1
        self._current_run.started = datetime.now()
        self._current_run.total = len(runnable)
        self._notify()
        self._task = self.hass.async_create_background_task(
            self._async_process(), f"{DOMAIN} queue {self.name}"
        )

    async def async_resume_if_interrupted(self) -> None:
        """Restart a run that a restart or reload cut short, if configured."""
        if not self._resume_pending:
            return
        self._resume_pending = False
        if not self.resume_after_restart:
            _LOGGER.info(
                "Queue '%s': a run was interrupted by a restart; "
                "resume_after_restart is off, so it stays idle until started",
                self.name,
            )
            return
        _LOGGER.info("Queue '%s': resuming a run interrupted by a restart", self.name)
        await self.async_start()

    async def async_stop(self) -> None:
        self._state = QUEUE_STATE_STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._current_item = None
        # An install cut short by Stop goes back to pending so the next
        # Start retries it, rather than sitting at "installing" for good.
        for item in self._items:
            if item.status == ITEM_STATUS_INSTALLING:
                item.status = ITEM_STATUS_PENDING
                item.retries = 0
                item.started_at = None
        self._finalize_run()
        self._notify()

    async def async_pause(self) -> None:
        if self._state == QUEUE_STATE_RUNNING:
            self._state = QUEUE_STATE_PAUSED
            self._notify()

    async def async_resume(self) -> None:
        if self._state == QUEUE_STATE_PAUSED:
            self._state = QUEUE_STATE_RUNNING
            self._notify()

    async def async_skip_current(self) -> None:
        if self._current_item:
            self._current_item.status = ITEM_STATUS_SKIPPED
            self._current_item.completed_at = datetime.now()
            if self._current_run:
                self._current_run.skipped += 1
            self._current_item = None
            if self._item_task is not None and not self._item_task.done():
                self._item_task.cancel()
            self._notify()

    async def async_clear(self) -> None:
        self._items.clear()
        self._current_item = None
        self._completed_count = 0
        self._failed_count = 0
        self._state = QUEUE_STATE_IDLE
        self._notify()

    async def async_retry_failed(self) -> None:
        failed = [i for i in self._items if i.status == ITEM_STATUS_FAILED]
        if not failed:
            return
        for item in failed:
            item.status = ITEM_STATUS_PENDING
            item.error = None
            item.retries = 0
            item.started_at = None
            item.completed_at = None
            item.duration = None
        self._notify()
        await self.async_start()

    def _finalize_run(self) -> None:
        if self._current_run is None:
            return
        run = self._current_run
        run.ended = datetime.now()
        for item in self._items:
            if item.status == ITEM_STATUS_COMPLETED:
                d = {"entity_id": item.entity_id, "friendly_name": item.friendly_name}
                if item.duration:
                    d["duration"] = item.duration
                run.succeeded_items.append(d)
            elif item.status == ITEM_STATUS_FAILED:
                run.failed_items.append({
                    "entity_id": item.entity_id,
                    "friendly_name": item.friendly_name,
                    "error": item.error,
                    "retries": item.retries,
                })
        run.succeeded = len(run.succeeded_items)
        run.failed = len(run.failed_items)
        if run.failed == 0 and run.succeeded > 0:
            run.result = RUN_RESULT_COMPLETED
        elif run.failed > 0 and run.succeeded > 0:
            run.result = RUN_RESULT_COMPLETED_WITH_FAILURES
        elif run.failed > 0 and run.succeeded == 0:
            run.result = RUN_RESULT_FAILED
        else:
            run.result = RUN_RESULT_IDLE
        self._last_run_result = run
        self._run_history.append(run)
        self._current_run = None

    async def _async_process(self) -> None:
        try:
            if self.exec_mode == EXEC_MODE_PARALLEL:
                await self._process_parallel()
            else:
                await self._process_sequential()
        except asyncio.CancelledError:
            if self._state == QUEUE_STATE_RUNNING:
                # Cancelled without Stop being pressed (Stop sets STOPPED
                # first): HA is shutting down or the entry is reloading.
                self._interrupted = True
        except Exception:
            _LOGGER.exception("Queue '%s': error", self.name)
        finally:
            if self._state == QUEUE_STATE_RUNNING:
                self._state = QUEUE_STATE_IDLE
            self._current_item = None
            self._finalize_run()
            self._notify()

    async def _process_sequential(self) -> None:
        for item in self._items:
            if self._state != QUEUE_STATE_RUNNING:
                break
            if item.status != ITEM_STATUS_PENDING:
                continue
            while self._state == QUEUE_STATE_PAUSED:
                await asyncio.sleep(1)
            if self._state != QUEUE_STATE_RUNNING:
                break
            self._current_item = item
            self._notify()
            self._item_task = self.hass.async_create_background_task(
                self._install_item(item), f"{DOMAIN} install {item.entity_id}"
            )
            try:
                success = await self._item_task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise  # the queue itself was stopped or shut down
                # Only the install was cancelled: Skip was pressed.
                success = True
            finally:
                self._item_task = None
            self._current_item = None
            if not success and self.stop_on_failure:
                self._state = QUEUE_STATE_STOPPED
                break
            if self.install_delay > 0:
                await asyncio.sleep(self.install_delay)

    async def _process_parallel(self) -> None:
        pending = [i for i in self._items if i.status == ITEM_STATUS_PENDING]
        await asyncio.gather(
            *[self._install_item(i) for i in pending], return_exceptions=True
        )

    async def _install_item(self, item: QueueItem) -> bool:
        item.status = ITEM_STATUS_INSTALLING
        item.started_at = datetime.now()
        self._notify()
        loop = asyncio.get_running_loop()
        for attempt in range(self.max_retries + 1):
            item.retries = attempt
            # install_timeout bounds the whole attempt. A blocking
            # update.install can itself wait indefinitely: Z-Wave JS does not
            # return until the device reports the firmware update finished,
            # which for a sleeping battery device may be days away.
            deadline = loop.time() + self.install_timeout
            try:
                async with asyncio.timeout_at(deadline):
                    await self.hass.services.async_call(
                        "update", "install",
                        {"entity_id": item.entity_id},
                        blocking=True,
                    )
            except TimeoutError:
                # Not retried: the device most likely still has the update
                # pending and would only reject a second install.
                item.error = (
                    f"No result from the device after {self.install_timeout}s "
                    "(it may still apply the update when it next wakes)"
                )
                _LOGGER.warning("Queue '%s': %s: %s", self.name, item.entity_id, item.error)
                break
            except Exception as exc:
                item.error = str(exc)
            else:
                if await self._wait_for_completion(item, deadline):
                    item.status = ITEM_STATUS_COMPLETED
                    item.completed_at = datetime.now()
                    if item.started_at:
                        delta = item.completed_at - item.started_at
                        mins = int(delta.total_seconds() // 60)
                        secs = int(delta.total_seconds() % 60)
                        item.duration = f"{mins}m {secs}s"
                    self._completed_count += 1
                    self._last_success = item.entity_id
                    self._notify()
                    return True
            if attempt < self.max_retries:
                await asyncio.sleep(5)
        item.status = ITEM_STATUS_FAILED
        item.completed_at = datetime.now()
        if item.started_at:
            delta = item.completed_at - item.started_at
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            item.duration = f"{mins}m {secs}s"
        self._failed_count += 1
        self._last_failure = item.entity_id
        self._notify()
        return False

    async def _wait_for_completion(self, item: QueueItem, deadline: float) -> bool:
        loop = asyncio.get_running_loop()
        while loop.time() < deadline:
            state = self.hass.states.get(item.entity_id)
            if state is None:
                return True
            in_progress = state.attributes.get("in_progress")
            if in_progress is False or in_progress is None:
                if state.state != STATE_ON:
                    return True
            await asyncio.sleep(5)
        item.error = f"Timed out after {self.install_timeout}s"
        return False

    async def async_shutdown(self) -> None:
        if self._state in (QUEUE_STATE_RUNNING, QUEUE_STATE_PAUSED):
            self._interrupted = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class QueueCoordinator:
    """Manages all named queues for a config entry."""

    def __init__(
        self, hass: HomeAssistant, queues_config: list[dict[str, Any]]
    ) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._queues: list[NamedQueue] = []
        self._listeners: list[Any] = []
        for qc in queues_config:
            q = NamedQueue(hass, qc)
            q.register_listener(self._schedule_save)
            self._queues.append(q)

    @property
    def queues(self) -> list[NamedQueue]:
        return list(self._queues)

    @property
    def queues_by_priority(self) -> list[NamedQueue]:
        return sorted(self._queues, key=lambda q: q.priority)

    def get_queue(self, name: str) -> NamedQueue | None:
        name_lower = name.lower()
        for q in self._queues:
            if q.name.lower() == name_lower:
                return q
        return None

    def get_queue_by_slug(self, slug: str) -> NamedQueue | None:
        for q in self._queues:
            if q.slug == slug:
                return q
        return None

    def add_queue(self, config: dict[str, Any]) -> NamedQueue:
        q = NamedQueue(self.hass, config)
        q.register_listener(self._schedule_save)
        self._queues.append(q)
        self._notify_global()
        return q

    def remove_queue(self, name: str) -> bool:
        q = self.get_queue(name)
        if q:
            self._queues.remove(q)
            self._notify_global()
            return True
        return False

    def update_queue_config(self, name: str, new_config: dict[str, Any]) -> bool:
        q = self.get_queue(name)
        if q:
            q.config.update(new_config)
            q.name = q.config.get("name", q.name)
            q.slug = _slugify(q.name)
            self._notify_global()
            return True
        return False

    async def async_scan_all(self) -> dict[str, int]:
        results = {}
        for q in self._queues:
            count = await q.async_scan()
            results[q.name] = count
            if q.trigger_mode == "auto_on_scan" and q.pending_count > 0:
                await q.async_start()
        await self.async_save()
        self._notify_global()
        return results

    async def async_stop_all(self) -> None:
        for q in self._queues:
            if q.state == QUEUE_STATE_RUNNING:
                await q.async_stop()
        await self.async_save()

    def register_global_listener(self, listener: Any) -> None:
        self._listeners.append(listener)

    def remove_global_listener(self, listener: Any) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    @callback
    def _notify_global(self) -> None:
        for ln in self._listeners:
            ln()

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and isinstance(data, dict):
            for q in self._queues:
                qdata = data.get(q.slug)
                if qdata:
                    q.load_state(qdata)

    def _data_to_save(self) -> dict[str, Any]:
        return {q.slug: q.to_dict() for q in self._queues}

    @callback
    def _schedule_save(self) -> None:
        # Persist progress as items move, not only on service calls.
        # Store flushes pending delayed saves when HA shuts down, so the
        # stored state reflects where a run actually got to.
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_SECONDS)

    async def async_save(self) -> None:
        await self._store.async_save(self._data_to_save())

    async def async_resume_interrupted(self) -> None:
        for q in self.queues_by_priority:
            await q.async_resume_if_interrupted()

    async def async_shutdown(self) -> None:
        for q in self._queues:
            await q.async_shutdown()
        await self.async_save()

    def get_all_queues_config(self) -> list[dict[str, Any]]:
        return [q.config for q in self._queues]
