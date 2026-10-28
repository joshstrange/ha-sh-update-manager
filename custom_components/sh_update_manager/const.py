"""Constants for Smarter.Homes Update Manager v2.0.0 — Queue-based architecture.

Device-per-queue design: each queue is a separate HA device with its own
sensors, buttons, and switches. A hub device provides global controls.

by Smarter Homes LLC — smarter.homes
"""

DOMAIN = "sh_update_manager"
SW_VERSION = "2.1.4"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_INSTALL_DELAY = 15  # seconds between installs
DEFAULT_INSTALL_TIMEOUT = 7200  # 2 hours per device
DEFAULT_MAX_RETRIES = 2
DEFAULT_HISTORY_COUNT = 25  # past runs to keep per queue
DEFAULT_PRIORITY = 50  # middle of 1-100 range
DEFAULT_SCAN_INTERVAL_MINUTES = 0  # 0 = disabled (manual scans only)
DEFAULT_RESUME_AFTER_RESTART = False  # restart an interrupted run on startup
RESUME_DELAY_SECONDS = 60  # settle time after HA start before resuming
SAVE_DELAY_SECONDS = 5  # debounce for persisting queue progress

# ---------------------------------------------------------------------------
# Queue states
# ---------------------------------------------------------------------------
QUEUE_STATE_IDLE = "idle"
QUEUE_STATE_RUNNING = "running"
QUEUE_STATE_PAUSED = "paused"
QUEUE_STATE_STOPPED = "stopped"

# ---------------------------------------------------------------------------
# Execution modes — how updates within a queue are processed
# ---------------------------------------------------------------------------
EXEC_MODE_SEQUENTIAL = "sequential"
EXEC_MODE_PARALLEL = "parallel"

EXEC_MODES_LIST = [EXEC_MODE_SEQUENTIAL, EXEC_MODE_PARALLEL]

# ---------------------------------------------------------------------------
# Trigger modes — when a queue runs
# ---------------------------------------------------------------------------
TRIGGER_MANUAL = "manual"
TRIGGER_AUTO = "auto_on_scan"

TRIGGER_MODES_LIST = [TRIGGER_MANUAL, TRIGGER_AUTO]

# ---------------------------------------------------------------------------
# Battery handling modes
# ---------------------------------------------------------------------------
BATTERY_EXCLUDE = "exclude"
BATTERY_DEFER_TO_END = "defer_to_end"
BATTERY_INCLUDE = "include"

BATTERY_MODES_LIST = [BATTERY_EXCLUDE, BATTERY_DEFER_TO_END, BATTERY_INCLUDE]

# ---------------------------------------------------------------------------
# Match rule types — how a queue selects update entities
# ---------------------------------------------------------------------------
MATCH_INTEGRATION = "integration"
MATCH_AREA = "area"
MATCH_LABEL = "label"
MATCH_ENTITY = "entity"
MATCH_DEVICE_NAME = "device_name"
MATCH_MANUFACTURER = "manufacturer"

MATCH_TYPES_LIST = [
    MATCH_INTEGRATION, MATCH_AREA, MATCH_LABEL, MATCH_ENTITY,
    MATCH_DEVICE_NAME, MATCH_MANUFACTURER,
]

# ---------------------------------------------------------------------------
# Update groups — logical groupings by integration type
# ---------------------------------------------------------------------------
GROUP_ZWAVE = "zwave"
GROUP_ESPHOME = "esphome"
GROUP_HACS = "hacs"
GROUP_HA_CORE = "ha_core"
GROUP_HA_OS = "ha_os"
GROUP_ADDONS = "addons"
GROUP_MATTER = "matter"
GROUP_MQTT = "mqtt"
GROUP_OTHER = "other"

# Map HA integration platforms -> group key
INTEGRATION_GROUP_MAP: dict[str, str] = {
    "zwave_js": GROUP_ZWAVE,
    "zwave": GROUP_ZWAVE,
    "esphome": GROUP_ESPHOME,
    "hacs": GROUP_HACS,
    "homeassistant": GROUP_HA_CORE,
    "hassio": GROUP_HA_OS,
    "hassio_addons": GROUP_ADDONS,
    "update": GROUP_HA_CORE,
    "matter": GROUP_MATTER,
    "mqtt": GROUP_MQTT,
}

# Human-friendly display names
GROUP_DISPLAY_NAMES: dict[str, str] = {
    GROUP_ZWAVE: "Z-Wave Firmware",
    GROUP_ESPHOME: "ESPHome Devices",
    GROUP_HACS: "HACS Integrations",
    GROUP_HA_CORE: "Home Assistant Core",
    GROUP_HA_OS: "Home Assistant OS",
    GROUP_ADDONS: "Add-ons",
    GROUP_MATTER: "Matter Devices",
    GROUP_MQTT: "MQTT Devices",
    GROUP_OTHER: "Other Updates",
}

# Which groups MUST be sequential (safety override)
FORCE_SEQUENTIAL_GROUPS = {GROUP_ZWAVE, GROUP_HA_CORE, GROUP_HA_OS}

# Core update entity IDs — these are always handled by the Supervisor (hassio
# platform) on HAOS installations, so they share a platform with regular
# add-on updates.  We identify them by well-known entity ID instead.
CORE_UPDATE_ENTITY_IDS = {
    "update.home_assistant_core_update",
    "update.home_assistant_operating_system_update",
    "update.home_assistant_supervisor_update",
}

# Default auto-created queues
DEFAULT_QUEUES: list[dict] = [
    {
        "name": "Core Updates",
        "match_type": MATCH_ENTITY,
        "match_value": ",".join(sorted(CORE_UPDATE_ENTITY_IDS)),
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": True,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 5,
    },
    {
        "name": "Z-Wave Firmware",
        "match_type": MATCH_INTEGRATION,
        "match_value": "zwave_js,zwave",
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        # v2.1.4: default flipped from exclude → include. Battery Z-Wave
        # sensors (e.g. ZSE44) do get OTA firmware updates, and users
        # reported them being silently filtered out. Users who want the
        # old mains-only behaviour can set battery_handling=exclude
        # (or defer_to_end) on this queue via Options.
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": False,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 10,
    },
    {
        "name": "ESPHome Devices",
        "match_type": MATCH_INTEGRATION,
        "match_value": "esphome",
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": False,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 20,
    },
    {
        "name": "HACS Updates",
        "match_type": MATCH_INTEGRATION,
        "match_value": "hacs",
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": False,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 30,
    },
    {
        "name": "Add-ons",
        "match_type": MATCH_INTEGRATION,
        "match_value": "hassio_addons,hassio",
        "exclude_pattern": "home_assistant_core_update,home_assistant_operating_system_update,home_assistant_supervisor_update",
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": False,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 40,
    },
    {
        "name": "Other Updates",
        "match_type": MATCH_INTEGRATION,
        "match_value": "matter,mqtt",
        "exec_mode": EXEC_MODE_SEQUENTIAL,
        "trigger_mode": TRIGGER_MANUAL,
        "battery_handling": BATTERY_INCLUDE,
        "stop_on_failure": False,
        "skip_unavailable": True,
        "install_delay": DEFAULT_INSTALL_DELAY,
        "install_timeout": DEFAULT_INSTALL_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "history_count": DEFAULT_HISTORY_COUNT,
        "priority": 50,
    },
]

# ---------------------------------------------------------------------------
# Run result states (for last-run-result sensor)
# ---------------------------------------------------------------------------
RUN_RESULT_IDLE = "idle"
RUN_RESULT_COMPLETED = "completed"
RUN_RESULT_COMPLETED_WITH_FAILURES = "completed_with_failures"
RUN_RESULT_FAILED = "failed"

# ---------------------------------------------------------------------------
# Queue-item statuses
# ---------------------------------------------------------------------------
ITEM_STATUS_PENDING = "pending"
ITEM_STATUS_INSTALLING = "installing"
ITEM_STATUS_COMPLETED = "completed"
ITEM_STATUS_FAILED = "failed"
ITEM_STATUS_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Config keys
# ---------------------------------------------------------------------------
CONF_QUEUES = "queues"

# Per-queue config keys
CONF_QUEUE_NAME = "name"
CONF_MATCH_TYPE = "match_type"
CONF_MATCH_VALUE = "match_value"
CONF_EXEC_MODE = "exec_mode"
CONF_TRIGGER_MODE = "trigger_mode"
CONF_BATTERY_HANDLING = "battery_handling"
CONF_STOP_ON_FAILURE = "stop_on_failure"
CONF_SKIP_UNAVAILABLE = "skip_unavailable"
CONF_INSTALL_DELAY = "install_delay"
CONF_INSTALL_TIMEOUT = "install_timeout"
CONF_MAX_RETRIES = "max_retries"
CONF_HISTORY_COUNT = "history_count"
CONF_PRIORITY = "priority"
CONF_EXCLUDE_PATTERN = "exclude_pattern"
CONF_RESUME_AFTER_RESTART = "resume_after_restart"

# Integration-level (global) config keys
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_SCAN_ALL = "scan_all"
SERVICE_START_QUEUE = "start_queue"
SERVICE_STOP_QUEUE = "stop_queue"
SERVICE_PAUSE_QUEUE = "pause_queue"
SERVICE_RESUME_QUEUE = "resume_queue"
SERVICE_SKIP_CURRENT = "skip_current"
SERVICE_CLEAR_QUEUE = "clear_queue"
SERVICE_RETRY_FAILED = "retry_failed"
SERVICE_SCAN_QUEUE = "scan_queue"
SERVICE_ADD_QUEUE = "add_queue"
SERVICE_EDIT_QUEUE = "edit_queue"
SERVICE_DELETE_QUEUE = "delete_queue"

# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------
# Note: PLATFORMS is defined in __init__.py using Platform enum

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
STORAGE_KEY = f"{DOMAIN}.queues"
STORAGE_VERSION = 5

# ---------------------------------------------------------------------------
# Panel / Frontend
# ---------------------------------------------------------------------------
PANEL_URL = "sh-update-manager"
PANEL_TITLE = "Update Manager"
PANEL_ICON = "mdi:update"
URL_BASE = f"/api/{DOMAIN}"
