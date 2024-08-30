"""File Permissions."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE, MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

INTERVAL = timedelta(minutes=5)
IGNORE_GLOBS = [
    "*.log*", "home-assistant*.db*", "core.restore_state", "trace.saved_traces"
]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration."""
    config_path = Path(hass.config.path(""))
    ha_gid = config_path.stat().st_gid
    _LOGGER.info("Config path: %s, gid: %d", config_path, ha_gid)

    def update_files() -> None:
        """Update file permissions & ownership."""
        start = dt_util.now()

        cc_path = config_path / "custom_components"

        updates = []
        for path in config_path.rglob("*"):
            if (
                path.is_relative_to(cc_path)
                or any(path.match(glob) for glob in IGNORE_GLOBS)
            ):
                continue
            stat = path.stat()
            want_perms = 0o070 if path.is_dir() else 0o060
            cur_perms = stat.st_mode
            add_perms = ~cur_perms & want_perms
            chown = stat.st_gid != ha_gid
            if add_perms or chown:
                try:
                    if add_perms:
                        path.chmod(path.stat().st_mode | add_perms)
                    if chown:
                        os.chown(path, -1, ha_gid)
                except Exception as exc:
                    updates.append(f"Error: {exc} processing {path}")
                else:
                    items = []
                    if add_perms:
                        items.append("mode")
                    if chown:
                        items.append("group")
                    updates.append(f"Changed: {', '.join(items)} of {path}")

        if updates:
            with (config_path / "fperms.log").open("a") as f:
                print("=" * 10, start, "=" * 10, file=f)
                for update in updates:
                    print(update, file=f)
                print(dt_util.now() - start, file=f)

    @callback
    def cb(data: Event | datetime) -> None:
        """Create thread to update files."""
        if isinstance(data, Event):
            remove()
        hass.async_add_executor_job(update_files)

    remove = async_track_time_interval(hass, cb, INTERVAL)
    # run_immediately was removed in 2024.5.
    # It's default used to be False, but now it behaves the way True did.
    if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 5):
        hass.bus.async_listen(EVENT_HOMEASSISTANT_CLOSE, cb)
    else:
        hass.bus.async_listen(EVENT_HOMEASSISTANT_CLOSE, cb, run_immediately=True)
    return True
