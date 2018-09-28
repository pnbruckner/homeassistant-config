"""
A Device Tracker platform that retrieves location from Life360.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#life360py--device_trackerlife360py
"""

import sys
import datetime as dt
from requests import HTTPError, ConnectionError, Timeout
from json.decoder import JSONDecodeError
import logging
import voluptuous as vol
try:
    from homeassistant.components.zone.zone import active_zone
except ImportError:
    from homeassistant.components.zone import active_zone
from homeassistant.components.device_tracker import (ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_FILENAME,
    CONF_PREFIX, LENGTH_KILOMETERS, LENGTH_MILES, STATE_UNKNOWN)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_time_interval
from homeassistant import util

__version__ = '1.5.0'

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['zone']

DEFAULT_FILENAME = 'life360.conf'
SPEED_FACTOR_MPH = 2.25

_AUTHORIZATION_TOKEN = 'cFJFcXVnYWJSZXRyZTRFc3RldGhlcnVmcmVQdW1hbUV4dWNyRU'\
                       'h1YzptM2ZydXBSZXRSZXN3ZXJFQ2hBUHJFOTZxYWtFZHI0Vg=='

CONF_DRIVING_SPEED = 'driving_speed'
CONF_MAX_GPS_ACCURACY = 'max_gps_accuracy'
CONF_MAX_UPDATE_WAIT = 'max_update_wait'
CONF_MEMBERS = 'members'
CONF_SHOW_AS_STATE = 'show_as_state'

SHOW_DRIVING = 'driving'
SHOW_MOVING = 'moving'
SHOW_PLACES = 'places'
SHOW_AS_STATE_OPTS = [SHOW_DRIVING, SHOW_MOVING, SHOW_PLACES]

ATTR_ADDRESS = 'address'
ATTR_AT_LOC_SINCE = 'at_loc_since'
ATTR_CHARGING = 'charging'
ATTR_DRIVING = SHOW_DRIVING
ATTR_LAST_SEEN = 'last_seen'
ATTR_MOVING = SHOW_MOVING
ATTR_RAW_SPEED = 'raw_speed'
ATTR_SPEED = 'speed'
ATTR_WIFI_ON = 'wifi_on'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_FILENAME, default=DEFAULT_FILENAME): cv.string,
    vol.Optional(CONF_SHOW_AS_STATE, default=[]): vol.All(
        cv.ensure_list_csv, [vol.In(SHOW_AS_STATE_OPTS)]),
    vol.Optional(CONF_MAX_GPS_ACCURACY): vol.Coerce(float),
    vol.Optional(CONF_MAX_UPDATE_WAIT): vol.All(
        cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_PREFIX): cv.string,
    vol.Optional(CONF_MEMBERS): vol.All(
        cv.ensure_list, [cv.string]),
    vol.Optional(CONF_DRIVING_SPEED): vol.Coerce(float),
})

def exc_msg(exc):
    return '{}: {}'.format(exc.__class__.__name__, str(exc))

def utc_from_ts(val):
    try:
        return util.dt.utc_from_timestamp(float(val))
    except (TypeError, ValueError):
        return None

def utc_attr_from_ts(val):
    res = utc_from_ts(val)
    return res if res else STATE_UNKNOWN

def bool_attr_from_int(val):
    try:
        return bool(int(val))
    except (TypeError, ValueError):
        return STATE_UNKNOWN

def m_name(first, last=None):
    first = first or ''
    last = last or ''
    first = first.strip().lower()
    last = last.strip().lower()
    if first and last:
        return ','.join([first, last])
    if not (first or last):
        raise ValueError('Must have at least first or last name')
    return first or last

def setup_scanner(hass, config, see, discovery_info=None):
    from custom_components.life360 import life360

    def auth_info_callback():
        _LOGGER.debug('Authenticating')
        return (_AUTHORIZATION_TOKEN,
                config[CONF_USERNAME],
                config[CONF_PASSWORD])

    interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    ok = False
    try:
        api = life360(auth_info_callback, interval.total_seconds()-1,
                      hass.config.path(config[CONF_FILENAME]))
        if api.get_circles():
            ok = True
    except Exception as exc:
        _LOGGER.error(exc_msg(exc))
    if not ok:
        _LOGGER.error('Life360 communication failed!')
        return False
    _LOGGER.debug('Life360 communication successful!')

    show_as_state = config[CONF_SHOW_AS_STATE]
    max_gps_accuracy = config.get(CONF_MAX_GPS_ACCURACY)
    max_update_wait = config.get(CONF_MAX_UPDATE_WAIT)
    prefix = config.get(CONF_PREFIX)
    members = config.get(CONF_MEMBERS)
    driving_speed = config.get(CONF_DRIVING_SPEED)
    _LOGGER.debug('members = {}'.format(members))

    if members:
        _members = []
        for member in members:
            try:
                name = m_name(*member.split(','))
            except (TypeError, ValueError):
                _LOGGER.error('Ignoring invalid member name: "{}"'.format(member))
                continue
            _members.append(name)
        members = _members
        _LOGGER.debug('Processed members = {}'.format(members))
        if not members:
            _LOGGER.error('No listed member names were valid')
            return False

    Life360Scanner(hass, see, interval, show_as_state, max_gps_accuracy,
                   max_update_wait, prefix, members, driving_speed, api)
    return True

class Life360Scanner:
    def __init__(self, hass, see, interval, show_as_state, max_gps_accuracy,
                 max_update_wait, prefix, members, driving_speed, api):
        self._hass = hass
        self._see = see
        self._show_as_state = show_as_state
        self._max_gps_accuracy = max_gps_accuracy
        self._max_update_wait = max_update_wait
        self._prefix = '' if not prefix else prefix + '_'
        self._members = members
        self._driving_speed = driving_speed
        self._api = api

        self._errs = {}
        self._max_errs = 2
        self._dev_data = {}
        self._started = util.dt.utcnow()

        track_time_interval(self._hass, self._update_life360, interval)

    def _ok(self, key):
        if self._errs.get(key, 0) >= self._max_errs:
            _LOGGER.error('{}: OK again'.format(key))
        self._errs[key] = 0

    def _err(self, key, err_msg):
        _errs = self._errs.get(key, 0)
        if _errs < self._max_errs:
            self._errs[key] = _errs = _errs + 1
            if _errs == self._max_errs:
                err_msg = 'Suppressing further errors until OK: ' + err_msg
            _LOGGER.error('{}: {}'.format(key, err_msg))

    def _exc(self, key, exc):
        self._err(key, exc_msg(exc))

    def _update_member(self, m, name):
        name = name.replace(',', '_').replace('-', '_')

        dev_id = util.slugify(self._prefix + name)
        prev_seen, reported = self._dev_data.get(dev_id, (None, False))

        loc = m.get('location')
        try:
            last_seen = utc_from_ts(loc.get('timestamp'))
        except AttributeError:
            last_seen = None

        if self._max_update_wait:
            update = last_seen or prev_seen or self._started
            overdue = util.dt.utcnow() - update > self._max_update_wait
            if overdue and not reported:
                self._hass.bus.fire(
                    'device_tracker.life360_update_overdue',
                    {'entity_id': ENTITY_ID_FORMAT.format(dev_id)})
                reported = True
            elif not overdue and reported:
                self._hass.bus.fire(
                    'device_tracker.life360_update_restored', {
                        'entity_id': ENTITY_ID_FORMAT.format(dev_id),
                        'wait':
                            str(last_seen - (prev_seen or self._started))
                            .split('.')[0]})
                reported = False

        self._dev_data[dev_id] = last_seen or prev_seen, reported

        if not loc:
            err_msg = m['issues']['title']
            if err_msg:
                if m['issues']['dialog']:
                    err_msg += ': ' + m['issues']['dialog']
            else:
                err_msg = 'Location information missing'
            self._err(dev_id, err_msg)
            return

        if last_seen and (not prev_seen or last_seen > prev_seen):
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            gps_accuracy = loc.get('accuracy')
            try:
                lat = float(lat)
                lon = float(lon)
                # Life360 reports accuracy in feet, but Device Tracker expects
                # gps_accuracy in meters.
                gps_accuracy=round(float(gps_accuracy)*0.3048)
            except (TypeError, ValueError):
                self._err(dev_id, 'GPS data invalid: {}, {}, {}'.format(
                    lat, lon, gps_accuracy))
                return

            self._ok(dev_id)

            msg = 'Updating {}'.format(dev_id)
            if prev_seen:
                msg += '; Time since last update: {}'.format(
                    last_seen - prev_seen)
            _LOGGER.debug(msg)

            if (self._max_gps_accuracy is not None and
                    gps_accuracy > self._max_gps_accuracy):
                _LOGGER.info(
                    '{}: Ignoring update because expected GPS '
                    'accuracy {} is not met: {}'.format(
                        dev_id, gps_accuracy, self._max_gps_accuracy))
                return

            place_name = loc.get('name') or None

            # Does user want location name to be shown as state?
            if SHOW_PLACES in self._show_as_state:
                loc_name = place_name
                # Make sure Home is always seen as exactly as home,
                # which is the special device_tracker state for home.
                if loc_name and loc_name.lower() == 'home':
                    loc_name = 'home'
            else:
                loc_name = None

            # If a place name is given, then address will just be a copy of
            # it, so don't bother with address. Otherwise, piece address
            # lines together, depending on which are present.
            if place_name:
                address = None
            else:
                address1 = loc.get('address1') or None
                address2 = loc.get('address2') or None
                if address1 and address2:
                    address = ', '.join([address1, address2])
                else:
                    address = address1 or address2

            raw_speed = loc.get('speed')
            try:
                speed = float(raw_speed) * SPEED_FACTOR_MPH
                if self._hass.config.units.is_metric:
                    speed = util.distance.convert(
                        speed, LENGTH_MILES, LENGTH_KILOMETERS)
                speed = round(speed)
            except (TypeError, ValueError):
                speed = STATE_UNKNOWN
            driving = bool_attr_from_int(loc.get('isDriving'))
            if (driving in (STATE_UNKNOWN, False) and
                    self._driving_speed is not None and
                    speed != STATE_UNKNOWN):
                driving = speed >= self._driving_speed
            moving = bool_attr_from_int(loc.get('inTransit'))

            attrs = {
                ATTR_ADDRESS: address,
                ATTR_AT_LOC_SINCE: utc_attr_from_ts(loc.get('since')),
                ATTR_CHARGING: bool_attr_from_int(loc.get('charge')),
                ATTR_DRIVING: driving,
                ATTR_LAST_SEEN: last_seen,
                ATTR_MOVING: moving,
                ATTR_RAW_SPEED: raw_speed,
                ATTR_SPEED: speed,
                ATTR_WIFI_ON: bool_attr_from_int(loc.get('wifiState')),
            }

            # If we don't have a location name yet and user wants driving or moving
            # to be shown as state, and current location is not in a HA zone,
            # then update location name accordingly.
            if not loc_name and not active_zone(self._hass, lat, lon, gps_accuracy):
                if SHOW_DRIVING in self._show_as_state and driving is True:
                    loc_name = SHOW_DRIVING.capitalize()
                elif SHOW_MOVING in self._show_as_state and moving is True:
                    loc_name = SHOW_MOVING.capitalize()

            try:
                battery = float(loc.get('battery'))
            except (TypeError, ValueError):
                battery = None

            self._see(dev_id=dev_id, location_name=loc_name, gps=(lat, lon),
                      gps_accuracy=gps_accuracy, battery=battery,
                      attributes=attrs, picture=m.get('avatar'))

    def _update_life360(self, now=None):
        excs = (HTTPError, ConnectionError, Timeout, JSONDecodeError)

        checked_ids = []

        #_LOGGER.debug('Checking members')
        err_key = 'get_circles'
        try:
            circles = self._api.get_circles()
        except excs as exc:
            self._exc(err_key, exc)
            return
        self._ok(err_key)

        for circle in circles:
            err_key = 'get_circle "{}"'.format(
                circle.get('name') or circle.get('id'))
            try:
                members = self._api.get_circle(circle['id'])['members']
            except excs as exc:
                self._exc(err_key, exc)
                continue
            except KeyError:
                self._err(err_key, circle)
                continue
            self._ok(err_key)

            for m in members:
                err_key = 'Member data'
                try:
                    m_id = m['id']
                    sharing = bool(int(m['features']['shareLocation']))
                    name = m_name(m.get('firstName'), m.get('lastName'))
                except (KeyError, TypeError, ValueError):
                    self._err(err_key, m)
                    continue
                self._ok(err_key)

                if (m_id not in checked_ids and
                        (not self._members or name in self._members) and
                        sharing):
                    checked_ids.append(m_id)
                    self._update_member(m, name)
