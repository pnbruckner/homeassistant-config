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

INTERVAL = timedelta(minutes=1)
IGNORE_GLOBS = [
    "*.log*",
    "home-assistant*.db*",
    # "core.restore_state",
    "trace.saved_traces",
    "tmp*",
]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration."""
    config_path = Path(hass.config.path(""))

    def get_config_gid() -> int:
        """Get config path & gid."""
        return config_path.stat().st_gid

    ha_gid = await hass.async_add_executor_job(get_config_gid)
    _LOGGER.info("Config path: %s, gid: %d", config_path, ha_gid)

    mode_chgd: list[str] = []
    grp_chgd: list[str] = []

    def update_files() -> None:
        """Update file permissions & ownership."""
        cc_path = config_path / "custom_components"

        for path in config_path.rglob("*"):
            if (
                path.is_relative_to(cc_path)
                or any(path.match(glob) for glob in IGNORE_GLOBS)
            ):
                continue
            path_str = str(path)
            try:
                stat = path.stat()
            except Exception as exc:
                _LOGGER.error("%s getting stat of %s", exc, path_str)
                continue
            want_perms = 0o070 if path.is_dir() else 0o060
            cur_perms = stat.st_mode
            add_perms = ~cur_perms & want_perms
            chown = stat.st_gid != ha_gid
            if not (add_perms or chown):
                continue
            if add_perms:
                try:
                    path.chmod(path.stat().st_mode | add_perms)
                except Exception as exc:
                    _LOGGER.error("%s changing mode of %s", exc, path_str)
                else:
                    if path_str not in mode_chgd:
                        _LOGGER.info("Changed mode of %s", path_str)
                        mode_chgd.append(path_str)
            if chown:
                try:
                    os.chown(path, -1, ha_gid)
                except Exception as exc:
                    _LOGGER.error("%s changing group of %s", exc, path_str)
                else:
                    if path_str not in grp_chgd:
                        _LOGGER.info("Changed group of %s", path_str)
                        mode_chgd.append(path_str)

    @callback
    def cb(data: Event | datetime) -> None:
        """Create thread to update files."""
        if isinstance(data, Event):
            remove()
        hass.async_add_executor_job(update_files)

    hass.async_add_executor_job(update_files)
    remove = async_track_time_interval(hass, cb, INTERVAL)
    # run_immediately was removed in 2024.5.
    # It's default used to be False, but now it behaves the way True did.
    if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 5):
        hass.bus.async_listen(EVENT_HOMEASSISTANT_CLOSE, cb)
    else:
        hass.bus.async_listen(EVENT_HOMEASSISTANT_CLOSE, cb, run_immediately=True)
    return True
