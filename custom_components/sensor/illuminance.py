"""
A Sensor platform that estimates outdoor illuminance from Weather Underground,
YR or Dark Sky current conditions.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#illuminance-sensor
"""

import asyncio
import datetime as dt
import logging

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN, PLATFORM_SCHEMA, SCAN_INTERVAL)
from homeassistant.components.sensor.darksky import (
    ATTRIBUTION as DSS_ATTRIBUTION)
from homeassistant.components.sensor.yr import (
    CONF_ATTRIBUTION as YRS_ATTRIBUTION)
from homeassistant.components.weather.darksky import (
    ATTRIBUTION as DSW_ATTRIBUTION, MAP_CONDITION as DSW_MAP_CONDITION)
from homeassistant.const import (
    ATTR_ATTRIBUTION, CONF_ENTITY_ID, CONF_API_KEY, CONF_NAME,
    CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_START)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change, async_track_time_change)
from homeassistant.helpers.sun import get_astral_event_date
import homeassistant.util.dt as dt_util

__version__ = '2.0.0'

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

_WU_API_URL = 'http://api.wunderground.com/api/'\
              '{api_key}/{features}/q/{query}.json'

_20_MIN = dt.timedelta(minutes=20)
_40_MIN = dt.timedelta(minutes=40)

async def _async_get_wu_data(hass, session, api_key, features, query):
    try:
        with async_timeout.timeout(9, loop=hass.loop):
            resp = await session.get(_WU_API_URL.format(
                api_key=api_key, features='/'.join(features), query=query))
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
        if not await _async_get_wu_data(
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
        self._init_complete = False
        self._was_changing = False

    async def async_added_to_hass(self):
        if self._using_wu:
            return

        @callback
        def sensor_state_listener(entity, old_state, new_state):
            if new_state and (not old_state or
                              new_state.state != old_state.state):
                self.async_schedule_update_ha_state(True)

        @callback
        def sensor_startup(event):
            self._init_complete = True

            # Update whenever source entity changes.
            async_track_state_change(
                self.hass, self._entity_id, sensor_state_listener)

            # Update now that source entity has had a chance to initialize.
            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, sensor_startup)

    @property
    def should_poll(self):
        # For the system (i.e., EntityPlatform) to configure itself to
        # periodically call our async_update method any call to this method
        # during initializaton must return True. After that, for WU we'll
        # always poll, and for others we'll only need to poll during the ramp
        # up and down periods around sunrise and sunset, and then once more
        # when period is done to make sure ramping is completed.
        if not self._init_complete or self._using_wu:
            return True
        changing = 0 < self.sun_factor(dt_util.now()) < 1
        if changing:
            self._was_changing = True
            return True
        if self._was_changing:
            self._was_changing = False
            return True
        return False

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def device_state_attributes(self):
        if self._using_wu:
            attrs = {ATTR_CONDITIONS: self._conditions}
            return attrs
        else:
            return None

    @property
    def unit_of_measurement(self):
        return 'lx'

    async def async_update(self):
        _LOGGER.debug('Updating {}'.format(self._name))

        sun_factor = self.sun_factor(dt_util.now())

        # No point in getting conditions because estimated illuminance derived
        # from it will just be multiplied by zero. I.e., it's nighttime.
        if sun_factor == 0:
            self._state = 10
            return

        if self._using_wu:
            features = ['conditions']

            resp = await _async_get_wu_data(
                self.hass, self._session, self._api_key, features,
                self._query)
            if not resp:
                return

            raw_conditions = resp['current_observation']['icon']
            conditions = self._conditions = raw_conditions
            mapping = WU_MAPPING
        else:
            state = self.hass.states.get(self._entity_id)
            if state is None:
                # If our initialization happens before the source entity has a
                # chance to initialize then we won't find its state. Don't log
                # that as an error.
                if self._init_complete:
                    _LOGGER.error('State not found: {}'.format(
                        self._entity_id))
                return
            attribution = state.attributes.get(ATTR_ATTRIBUTION)
            if not attribution:
                if self._init_complete:
                    _LOGGER.error('No {} attribute: {}'.format(
                        ATTR_ATTRIBUTION, self._entity_id))
                return
            raw_conditions = state.state
            if attribution in (DSS_ATTRIBUTION, DSW_ATTRIBUTION):
                if state.domain == SENSOR_DOMAIN:
                    conditions = DSW_MAP_CONDITION.get(raw_conditions)
                else:
                    conditions = raw_conditions
                mapping = DARKSKY_MAPPING
            elif attribution == YRS_ATTRIBUTION:
                try:
                    conditions = int(raw_conditions)
                except (TypeError, ValueError):
                    if self._init_complete:
                        _LOGGER.error(
                            'State of YR sensor not a number: {}'
                            .format(self._entity_id))
                    return
                mapping = YR_MAPPING
            else:
                if self._init_complete:
                    _LOGGER.error('Unsupported sensor: {}'.format(
                        self._entity_id))
                return

        illuminance = 0
        for i, c in mapping:
            if conditions in c:
                illuminance = i
                break
        if illuminance == 0:
            if self._init_complete:
                _LOGGER.error('Unexpected current observation: {}'.format(
                    raw_conditions))
            return

        self._state = round(illuminance * sun_factor)

    def sun_factor(self, now):
        now_date = now.date()

        if self._sun_data and self._sun_data[0] == now_date:
            (sunrise_begin, sunrise_end,
             sunset_begin, sunset_end) = self._sun_data[1]
        else:
            sunrise = get_astral_event_date(self.hass, 'sunrise', now_date)
            sunset = get_astral_event_date(self.hass, 'sunset', now_date)
            sunrise_begin = sunrise - _20_MIN
            sunrise_end = sunrise + _40_MIN
            sunset_begin = sunset - _40_MIN
            sunset_end = sunset + _20_MIN
            self._sun_data = (
                now_date,
                (sunrise_begin, sunrise_end, sunset_begin, sunset_end))

        if sunrise_end < now < sunset_begin:
            # Daytime
            return 1
        if now < sunrise_begin or sunset_end < now:
            # Nighttime
            return 0
        if now <= sunrise_end:
            # Sunrise
            return (now-sunrise_begin).total_seconds() / (60*60)
        else:
            # Sunset
            return (sunset_end-now).total_seconds() / (60*60)
