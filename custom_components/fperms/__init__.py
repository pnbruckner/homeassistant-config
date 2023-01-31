"""File Permissions."""

import logging
import os
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration."""
    config_path = Path(hass.config.path(""))
    ha_gid = config_path.stat().st_gid
    _LOGGER.info("Config path: %s, gid: %d", config_path, ha_gid)

    def update_files(event: Event) -> None:
        """Update file permissions & ownership."""
        fperms_path = config_path / "fperms.txt"
        cc_path = config_path / "custom_components"
        with fperms_path.open("w") as f:
            print(start := dt_util.now(), file=f)
            for path in config_path.rglob("*"):
                if path.samefile(fperms_path) or path.is_relative_to(cc_path):
                    continue
                stat = path.stat()
                want_perms = 0o070 if path.is_dir() else 0o060
                cur_perms = stat.st_mode
                add_perms = ~cur_perms & want_perms
                chown = stat.st_gid != ha_gid
                try:
                    if add_perms:
                        path.chmod(path.stat().st_mode | add_perms)
                    if chown:
                        os.chown(path, -1, ha_gid)
                except Exception as exc:
                    print("Error:", exc, ", file:", path, file=f)
                else:
                    print("OK:", "chmod:", bool(add_perms), "chown:", chown, path, file=f)
            print(dt_util.now() - start, file=f)

    @callback
    def cb(event: Event) -> None:
        """Create thread to update files."""
        hass.async_add_executor_job(update_files, event)

    hass.bus.async_listen(EVENT_HOMEASSISTANT_CLOSE, cb, run_immediately=True)
    return True
