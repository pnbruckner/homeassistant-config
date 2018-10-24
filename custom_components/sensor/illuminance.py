"""
A Sensor platform that estimates outdoor illuminance from Weather Underground
or YR current conditions.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#sensorilluminancepy
"""

import datetime as dt
import asyncio
import aiohttp
import async_timeout
import logging
import voluptuous as vol

from homeassistant.const import (
    ATTR_ATTRIBUTION, CONF_ENTITY_ID, CONF_API_KEY, CONF_NAME,
    CONF_SCAN_INTERVAL)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.components.sensor import PLATFORM_SCHEMA, SCAN_INTERVAL
from homeassistant.components.sensor.darksky import (
    CONF_ATTRIBUTION as DSS_ATTRIBUTION)
from homeassistant.components.sensor.yr import (
    CONF_ATTRIBUTION as YRS_ATTRIBUTION)
from homeassistant.components.weather.darksky import (
    ATTRIBUTION as DSW_ATTRIBUTION, MAP_CONDITION as DSW_MAP_CONDITION)
import homeassistant.util.dt as dt_util

__version__ = '2.0.0b2'

DEFAULT_NAME = 'Illuminance'
MIN_SCAN_INTERVAL = dt.timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL = dt.timedelta(minutes=5)

WU_MAPPING = (
    (  200, ('tstorms',)),
    ( 1000, ('cloudy', 'fog', 'rain', 'sleet', 'snow', 'flurries',
             'chanceflurries', 'chancerain', 'chancesleet', 
             'chancesnow','chancetstorms')),
    ( 2500, ('mostlycloudy',)),
    ( 7500, ('partlysunny', 'partlycloudy', 'mostlysunny', 'hazy')),
    (10000, ('sunny', 'clear')))
YR_MAPPING = (
    (  200, (6, 11, 14, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
             33, 34)),
    ( 1000, (5, 7, 8, 9, 10, 12, 13, 15, 40, 41, 42, 43, 44, 45, 46, 47, 48,
             49, 50)),
    ( 2500, (4, )),
    ( 7500, (2, 3)),
    (10000, (1, )))
DARKSKY_MAPPING = (
    (  200, ('hail', 'lightning')),
    ( 1000, ('fog', 'rainy', 'snowy', 'snowy-rainy')),
    ( 2500, ('cloudy', )),
    ( 7500, ('partlycloudy', )),
    (10000, ('clear-night', 'sunny', 'windy')))

CONF_QUERY = 'query'

ATTR_SUNRISE = 'sunrise'
ATTR_SUNSET = 'sunset'
ATTR_CONDITIONS = 'conditions'

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.All(
    PLATFORM_SCHEMA.extend({
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Exclusive(CONF_API_KEY, 'source'): cv.string,
        vol.Optional(CONF_QUERY): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
            vol.All(cv.time_period, vol.Range(min=MIN_SCAN_INTERVAL)),
        vol.Exclusive(CONF_ENTITY_ID, 'source'): cv.entity_id,
    }),
    cv.has_at_least_one_key(CONF_API_KEY, CONF_ENTITY_ID),
    cv.key_dependency(CONF_API_KEY, CONF_QUERY),
)

_API_URL = 'http://api.wunderground.com/api/{api_key}/{features}/q/{query}.json'

async def _async_get_data(hass, session, api_key, features, query):
    try:
        with async_timeout.timeout(9, loop=hass.loop):
            resp = await session.get(
                _API_URL.format(api_key=api_key, features='/'.join(features),
                                query=query))
        resp.raise_for_status()
        resp = await resp.json()
        if 'error' in resp['response']:
            raise ValueError('Error from api.wunderground.com: {}'.format(
                resp['response']['error']['description']))
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        _LOGGER.error('{}: {}'.format(exc.__class__.__name__, str(exc)))
        return None

    return resp

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    using_wu = CONF_API_KEY in config
    session = None
    if using_wu:
        session = async_get_clientsession(hass)
        if not await _async_get_data(
                hass, session, config[CONF_API_KEY], [], config[CONF_QUERY]):
            return False

    async_add_entities([IlluminanceSensor(using_wu, config, session)], True)

class IlluminanceSensor(Entity):
    def __init__(self, using_wu, config, session):
        self._using_wu = using_wu
        if using_wu:
            self._api_key = config[CONF_API_KEY]
            self._query = config[CONF_QUERY]
            self._session = session
            self._conditions = None
        else:
            self._entity_id = config[CONF_ENTITY_ID]
        self._name = config[CONF_NAME]
        self._state = None
        self._sun_data = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def device_state_attributes(self):
        if self._sun_data and self._using_wu:
            attrs = {}
            attrs[ATTR_SUNRISE] = str(self._sun_data[1])
            attrs[ATTR_SUNSET] = str(self._sun_data[2])
            attrs[ATTR_CONDITIONS] = self._conditions
            return attrs
        else:
            return None

    @property
    def unit_of_measurement(self):
        return 'lx'

    async def async_update(self):
        _LOGGER.debug('Updating {}'.format(self._name))

        now = dt_util.now()
        now_date = now.date()
        if self._sun_data and self._sun_data[0] != now_date:
            self._sun_data = None

        if self._using_wu:
            features = ['conditions']
            if self._sun_data is None:
                features.append('astronomy')

            resp = await _async_get_data(self.hass, self._session,
                                         self._api_key, features, self._query)
            if not resp:
                return

            conditions = self._conditions = resp['current_observation']['icon']
            mapping = WU_MAPPING
        else:
            state = self.hass.states.get(self._entity_id)
            if state is None:
                _LOGGER.error('State not found: {}'.format(self._entity_id))
                return
            attribution = state.attributes.get(ATTR_ATTRIBUTION)
            if not attribution:
                _LOGGER.error('No {} attribute: {}'.format(
                    ATTR_ATTRIBUTION, self._entity_id))
                return
            conditions = state.state
            if attribution in (DSS_ATTRIBUTION, DSW_ATTRIBUTION):
                # In case entity is a darksky icon sensor try mapping to
                # conditions used by darksky weather platform.
                conditions = DSW_MAP_CONDITION.get(conditions, conditions)
                mapping = DARKSKY_MAPPING
            elif attribution == YRS_ATTRIBUTION:
                try:
                    conditions = int(conditions)
                except (TypeError, ValueError):
                    _LOGGER.error(
                        'State of YR sensor not a number: {}'
                        .format(self._entity_id))
                    return
                mapping = YR_MAPPING
            else:
                _LOGGER.error('Unsupported sensor: {}'.format(self._entity_id))
                return

        if self._sun_data:
            (_, sunrise, sunset,
             sunrise_begin, sunrise_end,
             sunset_begin,  sunset_end) = self._sun_data
        else:
            if self._using_wu:
                # Get tz unaware datetimes.
                sunrise = dt.datetime.combine(now_date,
                    dt.time(int(resp['sun_phase']['sunrise']['hour']),
                            int(resp['sun_phase']['sunrise']['minute']),
                            0))
                sunset  = dt.datetime.combine(now_date,
                    dt.time(int(resp['sun_phase']['sunset'] ['hour']),
                            int(resp['sun_phase']['sunset'] ['minute']),
                            0))
                # Convert to tz aware datetimes in local timezone.
                sunrise = dt_util.as_local(dt_util.as_utc(sunrise))
                sunset = dt_util.as_local(dt_util.as_utc(sunset))
            else:
                # UTC times are fine since we won't be displaying them
                sunrise = get_astral_event_date(self.hass, 'sunrise', now_date)
                sunset = get_astral_event_date(self.hass, 'sunset', now_date)

            sunrise_begin = sunrise - dt.timedelta(minutes=20)
            sunrise_end   = sunrise + dt.timedelta(minutes=40)
            sunset_begin  = sunset  - dt.timedelta(minutes=40)
            sunset_end    = sunset  + dt.timedelta(minutes=20)
            self._sun_data = (now_date, sunrise, sunset,
                              sunrise_begin, sunrise_end,
                              sunset_begin,  sunset_end)

        if sunrise_begin <= now <= sunset_end:
            illuminance = 0
            for i, c in mapping:
                if conditions in c:
                    illuminance = i
                    break
            if illuminance == 0:
                _LOGGER.error('Unexpected current observation: {}'.format(conditions))
                return

            if sunrise_begin <= now <= sunrise_end:
                illuminance = 10 + int(
                    (illuminance-10) * (now-sunrise_begin).total_seconds() / (60*60))
            elif sunset_begin <= now <= sunset_end:
                illuminance = 10 + int(
                    (illuminance-10) * (sunset_end-now).total_seconds() / (60*60))

            self._state = illuminance

        else:
            self._state = 10
