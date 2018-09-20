"""
A Device Tracker platform that combines one or more GPS based device trackers.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#device_trackercompositepy
"""

import logging
import threading
import voluptuous as vol

from homeassistant.components.device_tracker import (
    ATTR_BATTERY, ATTR_SOURCE_TYPE, ENTITY_ID_FORMAT, PLATFORM_SCHEMA,
    SOURCE_TYPE_GPS, SOURCE_TYPE_ROUTER)
try:
    from homeassistant.components.zone.zone import active_zone
except ImportError:
    from homeassistant.components.zone import active_zone
from homeassistant.const import (
    ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE,
    CONF_ENTITY_ID, CONF_NAME, EVENT_HOMEASSISTANT_START, STATE_HOME)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_state_change
from homeassistant.util import dt as dt_util

__version__ = '1.1.0'

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

    def _bad_entity(self, entity_id, message, remove_now=False):
        msg = '{} {}'.format(entity_id, message)
        # Has there already been a warning for this entity?
        if self._entities[entity_id] or remove_now:
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
        if new_state is None:
            return

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
                _LOGGER.debug('Skipping: prv({}) >= new({})'.format(
                    self._prev_seen, last_seen))
                return

            # Try to get GPS and battery data.
            try:
                gps = (new_state.attributes[ATTR_LATITUDE],
                       new_state.attributes[ATTR_LONGITUDE])
            except KeyError:
                gps = None
            try:
                gps_accuracy = new_state.attributes[ATTR_GPS_ACCURACY]
            except KeyError:
                gps_accuracy = None
            battery = new_state.attributes.get(ATTR_BATTERY)
            # Don't use location_name unless we have to.
            location_name = None

            # What type of tracker is this?
            source_type = new_state.attributes.get(ATTR_SOURCE_TYPE)

            if source_type == SOURCE_TYPE_GPS:
                # GPS coordinates and accuracy are required.
                if gps is None:
                    self._bad_entity(entity_id, 'missing gps attributes')
                    return
                if gps_accuracy is None:
                    self._bad_entity(entity_id,
                                     'missing gps_accuracy attribute')
                    return

            elif source_type == SOURCE_TYPE_ROUTER:
                # Only use transitions to 'home'.
                if (new_state.state != STATE_HOME or
                        old_state and old_state.state == STATE_HOME):
                    return
                # Don't use new GPS data if it's not complete, or if current
                # composite tracker's state contains GPS data in 'zone.home'.
                if gps is None or gps_accuracy is None:
                    gps = gps_accuracy = None
                else:
                    cur_state = self._hass.states.get(
                        ENTITY_ID_FORMAT.format(self._dev_id))
                    try:
                        cur_lat = cur_state.attributes[ATTR_LATITUDE]
                        cur_lon = cur_state.attributes[ATTR_LONGITUDE]
                        cur_acc = cur_state.attributes[ATTR_GPS_ACCURACY]
                        if (active_zone(self._hass, cur_lat, cur_lon, cur_acc)
                                .entity_id) == 'zone.home':
                            gps = gps_accuracy = None
                    except (AttributeError, KeyError):
                        pass
                # If no GPS data, or not using it, then we need to set
                # location_name to 'home'. Otherwise component level code will
                # get into "stale processing", which we don't want.
                if gps is None or gps_accuracy is None:
                    location_name = STATE_HOME

            else:
                self._bad_entity(
                    entity_id,
                    'unsupported source_type: {}'.format(source_type),
                    remove_now=True)

            attrs = {ATTR_LAST_SEEN: last_seen.replace(microsecond=0)}
            self._see(dev_id=self._dev_id, gps=gps, gps_accuracy=gps_accuracy,
                battery=battery, attributes=attrs, source_type=source_type)

            self._prev_seen = last_seen
