"""File Permissions."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from functools import partial
import logging
import os
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import Event, HomeAssistant
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

    async def do_update(
        data: datetime | Event | None = None,
        /,
        *,
        stop_periodic_update: bool = False,
        wait_time: float | None = None,
    ) -> None:
        """Do an update."""
        if stop_periodic_update:
            remove_periodic_update()
        if wait_time:
            await asyncio.sleep(wait_time)
        await hass.async_add_executor_job(update_files)

    hass.async_create_background_task(do_update(wait_time=3), "First fperms update")
    remove_periodic_update = async_track_time_interval(hass, do_update, INTERVAL)
    hass.bus.async_listen(
        EVENT_HOMEASSISTANT_FINAL_WRITE,
        partial(do_update, stop_periodic_update=True, wait_time=3),
    )
    return True
