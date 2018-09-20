"""
A Device Tracker platform that combines one or more GPS based device trackers.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#device_trackercompositepy
"""

import logging
import threading
import voluptuous as vol

from homeassistant.components.device_tracker import (
    ATTR_BATTERY, PLATFORM_SCHEMA)
from homeassistant.const import (
    ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE, CONF_ENTITY_ID,
    CONF_NAME, EVENT_HOMEASSISTANT_START)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_state_change
from homeassistant.util import dt as dt_util

__version__ = '1.0.1'

_LOGGER = logging.getLogger(__name__)

ATTR_LAST_SEEN = 'last_seen'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_ENTITY_ID): cv.entity_ids
})

def setup_scanner(hass, config, see, discovery_info=None):
    def run_setup(event):
        CompositeScanner(hass, config, see)
    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, run_setup)
    return True

class CompositeScanner:
    def __init__(self, hass, config, see):
        self._hass = hass
        self._see = see
        entities = config[CONF_ENTITY_ID]
        self._entities = dict.fromkeys(entities, False)
        self._dev_id = config[CONF_NAME]
        self._lock = threading.Lock()
        self._prev_seen = None

        self._remove = track_state_change(
            hass, entities, self._update_info)

    def _bad_entity(self, entity_id, message):
        msg = "{} {}".format(entity_id, message)
        # Has there already been a warning for this entity?
        if self._entities[entity_id]:
            _LOGGER.error(msg)
            self._remove()
            self._entities.pop(entity_id)
            # Are there still any entities to watch?
            if len(self._entities):
                self._remove = track_state_change(
                    self._hass, self._entities.keys(), self._update_info)
        else:
            _LOGGER.warning(msg)
            self._entities[entity_id] = True

    def _update_info(self, entity_id, old_state, new_state):
        with self._lock:
            # Get time device was last seen, which is the entity's last_seen
            # attribute, or if that doesn't exist, then last_updated from the
            # new state object. Make sure last_seen is timezone aware in UTC.
            # Note that dt_util.as_utc assumes naive datetime is in local
            # timezone.
            last_seen = dt_util.as_utc(
                new_state.attributes.get(ATTR_LAST_SEEN,
                                         new_state.last_updated))

            # Is this newer info than last update?
            if self._prev_seen and self._prev_seen >= last_seen:
                _LOGGER.debug("Skipping: prv({}) >= new({})".format(
                    self._prev_seen, last_seen))
                return

            # GPS coordinates and accuracy are required.
            # Battery level is optional.
            try:
                gps = (new_state.attributes[ATTR_LATITUDE],
                       new_state.attributes[ATTR_LONGITUDE])
            except KeyError:
                self._bad_entity(entity_id, "missing gps attributes")
                return
            try:
                gps_accuracy = new_state.attributes[ATTR_GPS_ACCURACY]
            except KeyError:
                self._bad_entity(entity_id, "missing gps_accuracy attribute")
                return
            battery = new_state.attributes.get(ATTR_BATTERY)

            attrs = {ATTR_LAST_SEEN: last_seen.replace(microsecond=0)}
            self._see(dev_id=self._dev_id, gps=gps, gps_accuracy=gps_accuracy,
                battery=battery, attributes=attrs)

            self._prev_seen = last_seen
