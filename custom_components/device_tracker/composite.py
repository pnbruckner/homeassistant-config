"""
A Device Tracker platform that combines one or more GPS based device trackers.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#device_trackercompositepy
"""

from datetime import datetime
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
    ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_STATE,
    CONF_ENTITY_ID, CONF_NAME, EVENT_HOMEASSISTANT_START, STATE_HOME)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_state_change
from homeassistant.util import dt as dt_util

__version__ = '1.1.0'

_LOGGER = logging.getLogger(__name__)

ATTR_LAST_SEEN = 'last_seen'

WARNED = 'warned'
SOURCE_TYPE = ATTR_SOURCE_TYPE
STATE = ATTR_STATE

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
        self._entities = {}
        for entity_id in entities:
            self._entities[entity_id] = {
                WARNED: False,
                SOURCE_TYPE: None,
                STATE: None}
        self._dev_id = config[CONF_NAME]
        self._lock = threading.Lock()
        self._prev_seen = None

        self._remove = track_state_change(
            hass, entities, self._update_info)

    def _bad_entity(self, entity_id, message, remove_now=False):
        msg = '{} {}'.format(entity_id, message)
        # Has there already been a warning for this entity?
        if self._entities[entity_id][WARNED] or remove_now:
            _LOGGER.error(msg)
            self._remove()
            self._entities.pop(entity_id)
            # Are there still any entities to watch?
            if len(self._entities):
                self._remove = track_state_change(
                    self._hass, self._entities.keys(), self._update_info)
        else:
            _LOGGER.warning(msg)
            self._entities[entity_id][WARNED] = True

    def _good_entity(self, entity_id, source_type, state=None):
        self._entities[entity_id].update({
            WARNED: False,
            SOURCE_TYPE: source_type,
            STATE: state})

    def _use_router_data(self, state):
        if state == STATE_HOME:
            return True
        entities = self._entities.values()
        if any(entity[SOURCE_TYPE] == SOURCE_TYPE_GPS
                for entity in entities):
            return False
        return all(entity[STATE] != STATE_HOME
            for entity in entities
            if entity[SOURCE_TYPE] == SOURCE_TYPE_ROUTER)

    def _update_info(self, entity_id, old_state, new_state):
        if new_state is None:
            return

        with self._lock:
            # Get time device was last seen, which is the entity's last_seen
            # attribute, or if that doesn't exist, then last_updated from the
            # new state object. Make sure last_seen is timezone aware in UTC.
            # Note that dt_util.as_utc assumes naive datetime is in local
            # timezone.
            last_seen = new_state.attributes.get(ATTR_LAST_SEEN)
            if isinstance(last_seen, datetime):
                last_seen = dt_util.as_utc(last_seen)
            else:
                try:
                    last_seen = dt_util.utc_from_timestamp(float(last_seen))
                except (TypeError, ValueError):
                    last_seen = new_state.last_updated

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
            gps_accuracy = new_state.attributes.get(ATTR_GPS_ACCURACY)
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
                self._good_entity(entity_id, SOURCE_TYPE_GPS)

            elif source_type == SOURCE_TYPE_ROUTER:
                self._good_entity(
                    entity_id, SOURCE_TYPE_ROUTER, new_state.state)
                if not self._use_router_data(new_state.state):
                    return

                # Don't use new GPS data if it's not complete.
                if gps is None or gps_accuracy is None:
                    gps = gps_accuracy = None
                # Get current GPS data, if any, and determine if it is in
                # 'zone.home'.
                cur_state = self._hass.states.get(
                    ENTITY_ID_FORMAT.format(self._dev_id))
                try:
                    cur_lat = cur_state.attributes[ATTR_LATITUDE]
                    cur_lon = cur_state.attributes[ATTR_LONGITUDE]
                    cur_acc = cur_state.attributes[ATTR_GPS_ACCURACY]
                    cur_gps_is_home = (
                        active_zone(self._hass, cur_lat, cur_lon, cur_acc)
                        .entity_id == 'zone.home')
                except (AttributeError, KeyError):
                    cur_gps_is_home = False

                # It's important, for this composite tracker, to avoid the
                # component level code's "stale processing." This can be done
                # one of two ways: 1) provide GPS data w/ source_type of gps,
                # or 2) provide a location_name (that will be used as the new
                # state.)

                # If router entity's state is 'home' and current GPS data from
                # composite entity is available and is in 'zone.home',
                # use it and make source_type gps.
                if new_state.state == STATE_HOME and cur_gps_is_home:
                    gps = cur_lat, cur_lon
                    gps_accuracy = cur_acc
                    source_type = SOURCE_TYPE_GPS
                # Otherwise, if new GPS data is valid (which is unlikely if
                # new state is not 'home'),
                # use it and make source_type gps.
                elif gps:
                    source_type = SOURCE_TYPE_GPS
                # Otherwise, don't use any GPS data, but set location_name to
                # new state.
                else:
                    location_name = new_state.state

            else:
                self._bad_entity(
                    entity_id,
                    'unsupported source_type: {}'.format(source_type),
                    remove_now=True)
                return

            attrs = {ATTR_LAST_SEEN: last_seen.replace(microsecond=0)}
            self._see(dev_id=self._dev_id, location_name=location_name,
                gps=gps, gps_accuracy=gps_accuracy, battery=battery,
                attributes=attrs, source_type=source_type)

            self._prev_seen = last_seen
