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
    CONF_PREFIX, STATE_UNKNOWN)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_time_interval
from homeassistant import util

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['zone']

CONF_SHOW_AS_STATE   = 'show_as_state'
CONF_MAX_UPDATE_WAIT = 'max_update_wait'
CONF_MEMBERS         = 'members'

DEFAULT_FILENAME = 'life360.conf'

ATTR_LAST_UPDATE  = 'last_update'
ATTR_AT_LOC_SINCE = 'at_loc_since'
ATTR_MOVING       = 'moving'
ATTR_CHARGING     = 'charging'
ATTR_WIFI_ON      = 'wifi_on'
ATTR_DRIVING      = 'driving'

ATTR_PLACES = 'places'
SHOW_AS_STATE_OPTS = [ATTR_PLACES, ATTR_MOVING, ATTR_DRIVING]

_AUTHORIZATION_TOKEN = 'cFJFcXVnYWJSZXRyZTRFc3RldGhlcnVmcmVQdW1hbUV4dWNyRU'\
                       'h1YzptM2ZydXBSZXRSZXN3ZXJFQ2hBUHJFOTZxYWtFZHI0Vg=='

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_FILENAME, default=DEFAULT_FILENAME): cv.string,
    vol.Optional(CONF_SHOW_AS_STATE, default=[]): vol.All(
        cv.ensure_list_csv, [vol.In(SHOW_AS_STATE_OPTS)]),
    vol.Optional(CONF_MAX_UPDATE_WAIT): vol.All(
        cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_PREFIX): cv.string,
    vol.Optional(CONF_MEMBERS): vol.All(
        cv.ensure_list, [cv.string])
})

def exc_msg(exc, msg=None, extra=None):
    _msg = '{}: {}'.format(exc.__class__.__name__, str(exc))
    if msg:
        _msg = '{}: '.format(msg) + _msg
    if extra:
        _msg += '; {}'.format(extra)
    _LOGGER.error(_msg)

def utc_from_ts(val):
    try:
        return util.dt.utc_from_timestamp(float(val))
    except ValueError:
        return None

def dt_attr_from_utc(val):
    try:
        return str(util.dt.as_local(val))
    except ValueError:
        return STATE_UNKNOWN

def dt_attr_from_ts(val):
    return dt_attr_from_utc(utc_from_ts(val))

def bool_attr_from_int(val):
    try:
        return bool(int(val))
    except ValueError:
        return STATE_UNKNOWN

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
        exc_msg(exc)
    if not ok:
        _LOGGER.error('Life360 communication failed!')
        return False
    _LOGGER.debug('Life360 communication successful!')

    show_as_state = config[CONF_SHOW_AS_STATE]
    max_update_wait = config.get(CONF_MAX_UPDATE_WAIT)
    prefix = config.get(CONF_PREFIX)
    members = config.get(CONF_MEMBERS)
    _LOGGER.debug('members = {}'.format(members))

    if members:
        _members = []
        for member in members:
            try:
                f,l = member.lower().split(',')
            except (ValueError, AttributeError):
                _LOGGER.error('Invalid member name: {}'.format(member))
                return False
            _members.append((f.strip(), l.strip()))
        members = _members
        _LOGGER.debug('processed members = {}'.format(members))

    Life360Scanner(hass, see, interval, show_as_state, max_update_wait, prefix,
                   members, api)
    return True

class Life360Scanner(object):
    def __init__(self, hass, see, interval, show_as_state, max_update_wait,
                 prefix, members, api):
        self._hass = hass
        self._see = see
        self._show_as_state = show_as_state
        self._max_update_wait = max_update_wait
        self._prefix = '' if not prefix else prefix + '_'
        self._members = members
        self._api = api
        self._dev_data = {}
        self._started = util.dt.utcnow()
        track_time_interval(self._hass, self._update_life360, interval)

    def _update_member(self, m):
        f = m['firstName']
        l = m['lastName']
        #_LOGGER.debug('Checking "{}, {}"'.format(f, l))
        m_name = ('_'.join([f, l]) if f and l else f or l).replace('-', '_')

        dev_id = util.slugify(self._prefix + m_name)
        prev_update, reported = self._dev_data.get(dev_id, (None, False))

        loc = m.get('location')
        last_update = None if not loc else utc_from_ts(loc['timestamp'])

        if self._max_update_wait:
            update = last_update or prev_update or self._started
            overdue = util.dt.utcnow() - update > self._max_update_wait
            if overdue and not reported:
                self._hass.bus.fire('device_tracker.life360_update_overdue',
                                    {'entity_id': ENTITY_ID_FORMAT.format(dev_id)})
                reported = True
            elif not overdue and reported:
                self._hass.bus.fire('device_tracker.life360_update_restored',
                                    {'entity_id': ENTITY_ID_FORMAT.format(dev_id),
                                     'wait': str(last_update -
                                                 (prev_update or self._started))
                                             .split('.')[0]})
                reported = False

        if not loc:
            err_msg = m['issues']['title']
            if err_msg:
                if m['issues']['dialog']:
                    err_msg += ': ' + m['issues']['dialog']
            else:
                err_msg = 'Location information missing'
            _LOGGER.error('{}: {}'.format(dev_id, err_msg))

        elif prev_update is None or last_update > prev_update:
            msg = 'Updating {}'.format(dev_id)
            if prev_update is not None:
                msg += '; Time since last update: {}'.format(
                    last_update - prev_update)
            _LOGGER.debug(msg)

            attrs = {
                ATTR_LAST_UPDATE:  dt_attr_from_utc(last_update),
                ATTR_AT_LOC_SINCE: dt_attr_from_ts(loc['since']),
                ATTR_MOVING:       bool_attr_from_int(loc['inTransit']),
                ATTR_CHARGING:     bool_attr_from_int(loc['charge']),
                ATTR_WIFI_ON:      bool_attr_from_int(loc['wifiState']),
                ATTR_DRIVING:      bool_attr_from_int(loc['isDriving'])
            }

            lat = float(loc['latitude'])
            lon = float(loc['longitude'])
            gps_accuracy=round(float(loc['accuracy']))

            # Does user want location name to be shown as state?
            loc_name = loc['name'] if ATTR_PLACES in self._show_as_state else None
            # Make sure Home is always seen as exactly as home,
            # which is the special device_tracker state for home.
            if loc_name is not None and loc_name.lower() == 'home':
                loc_name = 'home'

            # If we don't have a location name yet and user wants driving or moving
            # to be shown as state, and current location is not in a HA zone,
            # then update location name accordingly.
            if not loc_name and not active_zone(self._hass, lat, lon, gps_accuracy):
                if ATTR_DRIVING in self._show_as_state and attrs[ATTR_DRIVING] is True:
                    loc_name = ATTR_DRIVING.capitalize()
                elif ATTR_MOVING in self._show_as_state and attrs[ATTR_MOVING] is True:
                    loc_name = ATTR_MOVING.capitalize()

            self._see(dev_id=dev_id, location_name=loc_name, gps=(lat, lon),
                      gps_accuracy=gps_accuracy,
                      battery=round(float(loc['battery'])),
                      attributes=attrs)

        self._dev_data[dev_id] = last_update or prev_update, reported

    def _update_life360(self, now=None):
        excs = (HTTPError, ConnectionError, Timeout, JSONDecodeError)

        checked_ids = []
        #_LOGGER.debug('Checking members')
        try:
            circles = self._api.get_circles()
        except excs as exc:
            exc_msg(exc, 'get_circles')
            return
        for circle in circles:
            try:
                members = self._api.get_circle(circle['id'])['members']
            except excs as exc:
                exc_msg(exc, 'get_circle')
                continue
            for m in members:
                try:
                    full_name = (m['firstName'].lower(), m['lastName'].lower())
                    m_id = m['id']
                    if ((not self._members or full_name in self._members) and
                            m_id not in checked_ids):
                        checked_ids.append(m_id)
                        self._update_member(m)
                except Exception as exc:
                    #exc_msg(exc, extra='m = {}'.format(m))
                    _LOGGER.debug('m = {}'.format(m))
                    raise
