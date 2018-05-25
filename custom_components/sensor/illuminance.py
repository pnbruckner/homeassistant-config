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
from homeassistant.components.sensor import PLATFORM_SCHEMA, SCAN_INTERVAL

CONF_QUERY = 'query'
MIN_SCAN_INTERVAL = dt.timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL = dt.timedelta(minutes=5)

ATTR_SUNRISE = 'sunrise'
ATTR_SUNSET  = 'sunset'

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_QUERY): cv.string,
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
    api_key = config[CONF_API_KEY]
    query   = config[CONF_QUERY]

    session = async_get_clientsession(hass)
    if not await _async_get_data(hass, session, api_key, [], query):
        return False

    async_add_entities([IlluminanceSensor(
        config[CONF_NAME], session, api_key, query)], True)

class IlluminanceSensor(Entity):
    def __init__(self, name, session, api_key, query):
        self._name = name
        self._session = session
        self._api_key = api_key
        self._query = query
        self._state = None
        self._sun_data = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def state_attributes(self):
        if self._sun_data:
            attrs = {}
            attrs[ATTR_SUNRISE] = str(self._sun_data[1])
            attrs[ATTR_SUNSET]  = str(self._sun_data[2])
            return attrs
        else:
            return None

    @property
    def unit_of_measurement(self):
        return 'lux'

    async def async_update(self):
        _LOGGER.debug('Updating {}'.format(self._name))

        now = dt.datetime.now()

        features = ['conditions']
        if self._sun_data is None or self._sun_data[0] != now.date():
            features.append('astronomy')
            self._sun_data = None

        resp = await _async_get_data(self.hass, self._session,
                                     self._api_key, features, self._query)
        if not resp:
            return

        if self._sun_data:
            (_, sunrise, sunset,
             sunrise_begin, sunrise_end,
             sunset_begin,  sunset_end) = self._sun_data
        else:
            sunrise = dt.datetime.combine(now.date(),
                dt.time(int(resp['sun_phase']['sunrise']['hour']),
                        int(resp['sun_phase']['sunrise']['minute']),
                        0))
            sunset  = dt.datetime.combine(now.date(),
                dt.time(int(resp['sun_phase']['sunset'] ['hour']),
                        int(resp['sun_phase']['sunset'] ['minute']),
                        0))
            sunrise_begin = sunrise - dt.timedelta(minutes=20)
            sunrise_end   = sunrise + dt.timedelta(minutes=40)
            sunset_begin  = sunset  - dt.timedelta(minutes=40)
            sunset_end    = sunset  + dt.timedelta(minutes=20)
            self._sun_data = (now.date(), sunrise, sunset,
                              sunrise_begin, sunrise_end,
                              sunset_begin,  sunset_end)

        if sunrise_begin <= now <= sunset_end:

            mapping = ((  200, ('tstorms',)),
                       ( 1000, ('cloudy', 'fog', 'rain', 'sleet', 'snow', 'flurries',
                                'chanceflurries', 'chancerain', 'chancesleet', 
                                'chancesnow','chancetstorms')),
                       ( 2500, ('mostlycloudy',)),
                       ( 7500, ('partlysunny', 'partlycloudy', 'mostlysunny', 'hazy')),
                       (10000, ('sunny', 'clear')))

            icon = resp['current_observation']['icon']
            if not icon:
                _LOGGER.error('No current observation icon')
                return

            illuminance = 0
            for i, c in mapping:
                if icon in c:
                    illuminance = i
                    break
            if illuminance == 0:
                _LOGGER.error('Unexpected current observation icon: {}'.format(icon))
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
