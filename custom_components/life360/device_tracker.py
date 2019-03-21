"""
A Device Tracker platform that retrieves location from Life360.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#life360-device-tracker-platform
"""

from collections import namedtuple
from datetime import timedelta
import logging
import sys

from json.decoder import JSONDecodeError
from requests import HTTPError, ConnectionError, Timeout
import voluptuous as vol

from homeassistant.components.device_tracker import (
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN,
    ENTITY_ID_FORMAT as DT_ENTITY_ID_FORMAT, PLATFORM_SCHEMA)
from homeassistant.components.zone import (
    DEFAULT_PASSIVE, ENTITY_ID_FORMAT as ZN_ENTITY_ID_FORMAT, ENTITY_ID_HOME,
    Zone)
from homeassistant.components.zone.zone import active_zone
from homeassistant.const import (
    ATTR_BATTERY_CHARGING, ATTR_FRIENDLY_NAME, ATTR_LATITUDE, ATTR_LONGITUDE,
    ATTR_NAME, CONF_FILENAME, CONF_PASSWORD, CONF_PREFIX, CONF_USERNAME,
    LENGTH_FEET, LENGTH_KILOMETERS, LENGTH_METERS, LENGTH_MILES, STATE_HOME,
    STATE_UNKNOWN)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.event import track_time_interval
from homeassistant.util import slugify
from homeassistant.util.async_ import run_coroutine_threadsafe
from homeassistant.util.distance import convert
import homeassistant.util.dt as dt_util


__version__ = '2.9.0'

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['zone']
REQUIREMENTS = ['life360==3.0.0', 'timezonefinderL==2.0.1']

DEFAULT_FILENAME = 'life360.conf'
DEFAULT_HOME_PLACE = 'Home'
SPEED_FACTOR_MPH = 2.25
MIN_ZONE_INTERVAL = timedelta(minutes=1)
EVENT_DELAY = timedelta(seconds=30)

DATA_LIFE360 = 'life360'

_API_TOKEN = 'cFJFcXVnYWJSZXRyZTRFc3RldGhlcnVmcmVQdW1hbUV4dWNyRU'\
             'h1YzptM2ZydXBSZXRSZXN3ZXJFQ2hBUHJFOTZxYWtFZHI0Vg=='

CONF_ADD_ZONES = 'add_zones'
CONF_DRIVING_SPEED = 'driving_speed'
CONF_ERROR_THRESHOLD = 'error_threshold'
CONF_HOME_PLACE = 'home_place'
CONF_MAX_GPS_ACCURACY = 'max_gps_accuracy'
CONF_MAX_UPDATE_WAIT = 'max_update_wait'
CONF_MEMBERS = 'members'
CONF_SHOW_AS_STATE = 'show_as_state'
CONF_TIME_AS = 'time_as'
CONF_WARNING_THRESHOLD = 'warning_threshold'
CONF_ZONE_INTERVAL = 'zone_interval'

AZ_EXCEPT_HOME = 'except_home' # Same as True
AZ_ONLY_HOME = 'only_home'
AZ_ALL = 'all'
AZ_OPTS = [AZ_EXCEPT_HOME, AZ_ONLY_HOME, AZ_ALL]
SHOW_DRIVING = 'driving'
SHOW_MOVING = 'moving'
SHOW_PLACES = 'places'
SHOW_AS_STATE_OPTS = [SHOW_DRIVING, SHOW_MOVING, SHOW_PLACES]
TZ_UTC = 'utc'
TZ_LOCAL = 'local'
TZ_DEVICE_UTC = 'device_or_utc'
TZ_DEVICE_LOCAL = 'device_or_local'
# First item in list is default.
TIME_AS_OPTS = [TZ_UTC, TZ_LOCAL, TZ_DEVICE_UTC, TZ_DEVICE_LOCAL]

ATTR_ADDRESS = 'address'
ATTR_AT_LOC_SINCE = 'at_loc_since'
ATTR_DRIVING = SHOW_DRIVING
ATTR_LAST_SEEN = 'last_seen'
ATTR_MOVING = SHOW_MOVING
ATTR_RADIUS = 'radius'
ATTR_RAW_SPEED = 'raw_speed'
ATTR_SPEED = 'speed'
ATTR_TIME_ZONE = 'time_zone'
ATTR_WIFI_ON = 'wifi_on'

SERVICE_ZONES_FROM_PLACES = 'life360_zones_from_places'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_FILENAME, default=DEFAULT_FILENAME): cv.string,
    vol.Optional(CONF_SHOW_AS_STATE, default=[]): vol.All(
        cv.ensure_list_csv, [vol.In(SHOW_AS_STATE_OPTS)]),
    vol.Optional(CONF_HOME_PLACE, default=DEFAULT_HOME_PLACE): cv.string,
    vol.Optional(CONF_MAX_GPS_ACCURACY): vol.Coerce(float),
    vol.Optional(CONF_MAX_UPDATE_WAIT): vol.All(
        cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_PREFIX): cv.string,
    vol.Optional(CONF_MEMBERS): vol.All(
        cv.ensure_list, [cv.string]),
    vol.Optional(CONF_DRIVING_SPEED): vol.Coerce(float),
    vol.Optional(CONF_ADD_ZONES):
        vol.Any(vol.In(AZ_OPTS), cv.boolean),
    vol.Optional(CONF_ZONE_INTERVAL):
        vol.All(cv.time_period, vol.Range(min=MIN_ZONE_INTERVAL)),
    vol.Optional(CONF_TIME_AS, default=TIME_AS_OPTS[0]):
        vol.In(TIME_AS_OPTS),
    vol.Optional(CONF_WARNING_THRESHOLD): cv.positive_int,
    vol.Optional(CONF_ERROR_THRESHOLD, default = 0): cv.positive_int,
})

_API_EXCS = (HTTPError, ConnectionError, Timeout, JSONDecodeError)


def exc_msg(exc):
    return '{}: {}'.format(exc.__class__.__name__, str(exc))

def utc_from_ts(val):
    try:
        return dt_util.utc_from_timestamp(float(val))
    except (TypeError, ValueError):
        return None

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
    interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    try:
        from life360 import life360, LoginError
        api = life360(_API_TOKEN, config[CONF_USERNAME], config[CONF_PASSWORD],
                      interval.total_seconds()-1,
                      hass.config.path(config[CONF_FILENAME]))
        api.get_circles()
    except LoginError as exc:
        _LOGGER.error(exc_msg(exc))
        _LOGGER.error('Aborting setup!')
        return False
    # Ignore other errors at this time. Hopefully they're temporary.
    except Exception as exc:
        _LOGGER.warning('Ignoring: {}'.format(exc_msg(exc)))
    _LOGGER.debug('Setup successful!')

    members = config.get(CONF_MEMBERS)
    _LOGGER.debug('Configured members = {}'.format(
        members if members else 'None specified; will include all'))

    if members:
        _members = []
        for member in members:
            try:
                name = m_name(*member.split(','))
            except (TypeError, ValueError):
                _LOGGER.error(
                    'Ignoring invalid member name: "{}"'.format(member))
                continue
            _members.append(name)
        members = _members
        _LOGGER.debug('Processed members = {}'.format(members))
        if not members:
            _LOGGER.error('No listed member names were valid')
            return False

    home_place_name = config[CONF_HOME_PLACE].lower()
    zone_interval = config.get(CONF_ZONE_INTERVAL)
    # add_zones can be False or one of the values in AZ_OPTS.
    # Default depends on zone_interval.
    # For legacy reasons, allow True, but treat it the same as AZ_EXCEPT_HOME.
    add_zones = config.get(CONF_ADD_ZONES, zone_interval != None)
    if add_zones is True:
        add_zones = AZ_EXCEPT_HOME
    zones = {}

    Place = namedtuple(
        'Place', [ATTR_NAME, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_RADIUS])

    def get_places(api):
        errs = 0
        while True:
            places = set()
            try:
                for circle in api.get_circles():
                    for place in api.get_circle_places(circle['id']):
                        places.add(Place(place['name'],
                                         float(place['latitude']),
                                         float(place['longitude']),
                                         float(place['radius'])))
            except _API_EXCS + (KeyError, TypeError, ValueError) as exc:
                errs += 1
                if errs >= 3:
                    _LOGGER.error('get_places: {}'.format(exc_msg(exc)))
                    return None
            else:
                return places

    def zone_from_place(place, entity_id=None):
        zone = Zone(hass, *place, None, DEFAULT_PASSIVE)
        zone.entity_id = (
            entity_id or
            generate_entity_id(ZN_ENTITY_ID_FORMAT, place.name, None, hass))
        zone.schedule_update_ha_state()
        return zone

    def log_places(msg, places):
        s = 's' if len(places) > 1 else ''
        _LOGGER.debug('{} zone{} from Place{}: {}'.format(
            msg, s, s,
            '; '.join(['{}: {}, {}, {}'.format(*place) for place
                       in sorted(places, key=lambda x: x.name.lower())])))

    def zones_from_places(api, home_place_name, add_zones, zones):
        _LOGGER.debug('Checking Places')
        places = get_places(api)
        if places is None:
            return

        # See if there is a Life360 Place whose name matches CONF_HOME_PLACE.
        # If there is, remove it from set and handle it specially.
        home_place = None
        for place in places.copy():
            if place.name.lower() == home_place_name:
                home_place = place
                places.discard(place)

        # If a "Home Place" was found, and user wants to update zone.home with
        # it, and if it is indeed different, then update zone.home.
        if home_place and add_zones in (AZ_ONLY_HOME, AZ_ALL):
            hz_attrs = hass.states.get(ENTITY_ID_HOME).attributes
            if home_place != Place(hz_attrs[ATTR_FRIENDLY_NAME],
                                   hz_attrs[ATTR_LATITUDE],
                                   hz_attrs[ATTR_LONGITUDE],
                                   hz_attrs[ATTR_RADIUS]):
                log_places('Updating', [home_place])
                zone_from_place(home_place, ENTITY_ID_HOME)

        if add_zones in (AZ_EXCEPT_HOME, AZ_ALL):
            # Do any of the Life360 Places that we created HA zones from no longer
            # exist? If so, remove the corresponding zones.
            remove_places = set(zones.keys()) - places
            if remove_places:
                log_places('Removing', remove_places)
                for remove_place in remove_places:
                    run_coroutine_threadsafe(
                        zones.pop(remove_place).async_remove(),
                        hass.loop).result()

            # Are there any newly defined Life360 Places since the last time we
            # checked? If so, create HA zones for them.
            add_places = places - set(zones.keys())
            if add_places:
                log_places('Adding', add_places)
                for add_place in add_places:
                    zones[add_place] = zone_from_place(add_place)

    def zones_from_places_interval(now=None):
        zones_from_places(api, home_place_name, add_zones, zones)

    def zones_from_places_service(service):
        # Note: Although another thread may append the list while we're
        #       iterating through it, that's ok. We'll just process the new
        #       entry, which will be valid.
        for params in hass.data[DATA_LIFE360]:
            zones_from_places(*params)

    if add_zones:
        zones_from_places_interval()
        if zone_interval:
            _LOGGER.debug('Will check Places every: {}'.format(zone_interval))
            track_time_interval(hass, zones_from_places_interval,
                                zone_interval)
        # Note: dict.setdefault and list.append are both thread-safe, so no
        #       lock required.
        hass.data.setdefault(DATA_LIFE360, []).append(
            (api, home_place_name, add_zones, zones))
        if not hass.services.has_service(DOMAIN, SERVICE_ZONES_FROM_PLACES):
            hass.services.register(
                DOMAIN, SERVICE_ZONES_FROM_PLACES, zones_from_places_service)

    Life360Scanner(hass, config, see, interval, home_place_name, members, api)
    return True

class Life360Scanner:
    def __init__(self, hass, config, see, interval, home_place_name, members,
                 api):
        self._hass = hass
        self._see = see
        self._show_as_state = config[CONF_SHOW_AS_STATE]
        self._home_place_name = home_place_name
        self._max_gps_accuracy = config.get(CONF_MAX_GPS_ACCURACY)
        self._max_update_wait = config.get(CONF_MAX_UPDATE_WAIT)
        prefix = config.get(CONF_PREFIX)
        self._prefix = '' if not prefix else prefix + '_'
        self._members = members
        self._driving_speed = config.get(CONF_DRIVING_SPEED)
        self._time_as = config[CONF_TIME_AS]
        self._api = api

        self._errs = {}
        self._error_threshold = config[CONF_ERROR_THRESHOLD]
        self._warning_threshold = config.get(
            CONF_WARNING_THRESHOLD, self._error_threshold)
        if self._warning_threshold > self._error_threshold:
            _LOGGER.warning('Ignoring {}: ({}) > {} ({})'.format(
                CONF_WARNING_THRESHOLD, self._warning_threshold,
                CONF_ERROR_THRESHOLD, self._error_threshold))

        self._max_errs = self._error_threshold + 2
        self._dev_data = {}
        if self._time_as in [TZ_DEVICE_UTC, TZ_DEVICE_LOCAL]:
            from timezonefinderL import TimezoneFinder
            self._tf = TimezoneFinder()
        self._started = dt_util.utcnow()

        self._update_life360()
        track_time_interval(self._hass, self._update_life360, interval)

    def _ok(self, key):
        if self._errs.get(key, 0) >= self._max_errs:
            _LOGGER.error('{}: OK again'.format(key))
        self._errs[key] = 0

    def _err(self, key, err_msg):
        _errs = self._errs.get(key, 0)
        if _errs < self._max_errs:
            self._errs[key] = _errs = _errs + 1
            msg = '{}: {}'.format(key, err_msg)
            if _errs > self._error_threshold:
                if _errs == self._max_errs:
                    msg = 'Suppressing further errors until OK: ' + msg
                _LOGGER.error(msg)
            elif _errs > self._warning_threshold:
                _LOGGER.warning(msg)

    def _exc(self, key, exc):
        self._err(key, exc_msg(exc))

    def _dt_attr_from_utc(self, utc, tz):
        if self._time_as in [TZ_DEVICE_UTC, TZ_DEVICE_LOCAL] and tz:
            return utc.astimezone(tz)
        if self._time_as in [TZ_LOCAL, TZ_DEVICE_LOCAL]:
            return dt_util.as_local(utc)
        return utc

    def _dt_attr_from_ts(self, ts, tz):
        utc = utc_from_ts(ts)
        if utc:
            return self._dt_attr_from_utc(utc, tz)
        return STATE_UNKNOWN

    def _update_member(self, m, name):
        name = name.replace(',', '_').replace('-', '_')

        dev_id = slugify(self._prefix + name)
        prev_seen, reported = self._dev_data.get(dev_id, (None, False))

        loc = m.get('location')
        try:
            last_seen = utc_from_ts(loc.get('timestamp'))
        except AttributeError:
            last_seen = None

        if self._max_update_wait:
            now = dt_util.utcnow()
            update = last_seen or prev_seen or self._started
            overdue = now - update > self._max_update_wait
            if overdue and not reported and now - self._started > EVENT_DELAY:
                self._hass.bus.fire(
                    'life360_update_overdue',
                    {'entity_id': DT_ENTITY_ID_FORMAT.format(dev_id)})
                reported = True
            elif not overdue and reported:
                self._hass.bus.fire(
                    'life360_update_restored', {
                        'entity_id': DT_ENTITY_ID_FORMAT.format(dev_id),
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
                gps_accuracy=round(
                    convert(float(gps_accuracy), LENGTH_FEET, LENGTH_METERS))
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
                # Make sure Home Place is always seen exactly as home,
                # which is the special device_tracker state for home.
                if loc_name and loc_name.lower() == self._home_place_name:
                    loc_name = STATE_HOME
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
                    speed = convert(speed, LENGTH_MILES, LENGTH_KILOMETERS)
                speed = max(0, round(speed))
            except (TypeError, ValueError):
                speed = STATE_UNKNOWN
            driving = bool_attr_from_int(loc.get('isDriving'))
            if (driving in (STATE_UNKNOWN, False) and
                    self._driving_speed is not None and
                    speed != STATE_UNKNOWN):
                driving = speed >= self._driving_speed
            moving = bool_attr_from_int(loc.get('inTransit'))

            if self._time_as in [TZ_DEVICE_UTC, TZ_DEVICE_LOCAL]:
                # timezone_at will return a string or None.
                tzname = self._tf.timezone_at(lng=lon, lat=lat)
                # get_time_zone will return a tzinfo or None.
                tz = dt_util.get_time_zone(tzname)
                attrs = {ATTR_TIME_ZONE: tzname or STATE_UNKNOWN}
            else:
                tz = None
                attrs = {}

            attrs.update({
                ATTR_ADDRESS: address,
                ATTR_AT_LOC_SINCE:
                    self._dt_attr_from_ts(loc.get('since'), tz),
                ATTR_BATTERY_CHARGING: bool_attr_from_int(loc.get('charge')),
                ATTR_DRIVING: driving,
                ATTR_LAST_SEEN:
                    self._dt_attr_from_utc(last_seen, tz),
                ATTR_MOVING: moving,
                ATTR_RAW_SPEED: raw_speed,
                ATTR_SPEED: speed,
                ATTR_WIFI_ON: bool_attr_from_int(loc.get('wifiState')),
            })

            # If we don't have a location name yet and user wants driving or moving
            # to be shown as state, and current location is not in a HA zone,
            # then update location name accordingly.
            if not loc_name and not active_zone(self._hass, lat, lon, gps_accuracy):
                if SHOW_DRIVING in self._show_as_state and driving is True:
                    loc_name = SHOW_DRIVING.capitalize()
                elif SHOW_MOVING in self._show_as_state and moving is True:
                    loc_name = SHOW_MOVING.capitalize()

            try:
                battery = int(float(loc.get('battery')))
            except (TypeError, ValueError):
                battery = None

            self._see(dev_id=dev_id, location_name=loc_name, gps=(lat, lon),
                      gps_accuracy=gps_accuracy, battery=battery,
                      attributes=attrs, picture=m.get('avatar'))

    def _update_life360(self, now=None):
        checked_ids = []

        err_key = 'get_circles'
        try:
            circles = self._api.get_circles()
        except _API_EXCS as exc:
            self._exc(err_key, exc)
            return
        self._ok(err_key)

        for circle in circles:
            err_key = 'get_circle "{}"'.format(
                circle.get('name') or circle.get('id'))
            try:
                members = self._api.get_circle_members(circle['id'])
            except _API_EXCS as exc:
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
