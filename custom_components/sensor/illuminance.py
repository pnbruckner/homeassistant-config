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

from homeassistant.const import CONF_NAME, CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.components.sensor import PLATFORM_SCHEMA, SCAN_INTERVAL
import homeassistant.util.dt as dt_util

__version__ = '2.0.0b1'

CONF_QUERY = 'query'

DEFAULT_NAME = 'Illuminance'
MIN_SCAN_INTERVAL = dt.timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL = dt.timedelta(minutes=5)

ATTR_SUNRISE = 'sunrise'
ATTR_SUNSET = 'sunset'
ATTR_CONDITIONS = 'conditions'

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Inclusive(CONF_API_KEY, 'wu'): cv.string,
    vol.Inclusive(CONF_QUERY, 'wu'): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
        vol.All(cv.time_period, vol.Range(min=MIN_SCAN_INTERVAL)),
})

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
    name = config[CONF_NAME]
    if CONF_API_KEY in config:
        api_key = config[CONF_API_KEY]
        query   = config[CONF_QUERY]

        session = async_get_clientsession(hass)
        if not await _async_get_data(hass, session, api_key, [], query):
            return False
            
        sensor = IlluminanceSensor(name, session, api_key, query)
    else:
        sensor = IlluminanceSensor(name)

    async_add_entities([sensor], True)

class IlluminanceSensor(Entity):
    def __init__(self, name, session=None, api_key=None, query=None):
        self._name = name
        self._session = session
        self._api_key = api_key
        self._query = query
        self._state = None
        self._sun_data = None
        self._conditions = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def state_attributes(self):
        if self._sun_data and self._api_key:
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

        if self._api_key:
            features = ['conditions']
            if self._sun_data is None:
                features.append('astronomy')

            resp = await _async_get_data(self.hass, self._session,
                                         self._api_key, features, self._query)
            if not resp:
                return

            conditions = self._conditions = resp['current_observation']['icon']
        else:
            try:
                conditions = int(self.hass.states.get('sensor.yr_symbol').state)
            except (AttributeError, TypeError, ValueError):
                _LOGGER.error(
                    'sensor.yr_symbol state not available or not a number')
                return

        if self._sun_data:
            (_, sunrise, sunset,
             sunrise_begin, sunrise_end,
             sunset_begin,  sunset_end) = self._sun_data
        else:
            if self._api_key:
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
            if not conditions:
                _LOGGER.error('No current observation')
                return

            if self._api_key:
                mapping = ((  200, ('tstorms',)),
                           ( 1000, ('cloudy', 'fog', 'rain', 'sleet', 'snow', 'flurries',
                                    'chanceflurries', 'chancerain', 'chancesleet', 
                                    'chancesnow','chancetstorms')),
                           ( 2500, ('mostlycloudy',)),
                           ( 7500, ('partlysunny', 'partlycloudy', 'mostlysunny', 'hazy')),
                           (10000, ('sunny', 'clear')))
            else:
                mapping = ((  200, (6, 11, 14, 20, 21, 22, 23, 24, 25, 26, 27,
                                    28, 29, 30, 31, 32, 33, 34)),
                           ( 1000, (5, 7, 8, 9, 10, 12, 13, 15, 40, 41, 42,
                                    43, 44, 45, 46, 47, 48, 49, 50)),
                           ( 2500, (4, )),
                           ( 7500, (2, 3)),
                           (10000, (1, )))

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
