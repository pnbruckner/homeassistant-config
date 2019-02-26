"""Suppoort for Amcrest IP camera binary sensors."""
import asyncio
from datetime import timedelta
import logging
from requests.exceptions import RequestException

from . import DATA_AMCREST, DATA_AMCREST_LOCK, LOCK_TIMEOUT, BINARY_SENSORS
from homeassistant.components.binary_sensor import BinarySensorDevice
from homeassistant.const import CONF_NAME, CONF_BINARY_SENSORS

DEPENDENCIES = ['amcrest']

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up a binary sensor for an Amcrest IP Camera."""
    if discovery_info is None:
        return

    device_name = discovery_info[CONF_NAME]
    binary_sensors = discovery_info[CONF_BINARY_SENSORS]
    amcrest = hass.data[DATA_AMCREST][device_name]
    lock = hass.data[DATA_AMCREST_LOCK][device_name]

    amcrest_binary_sensors = []
    for sensor_type in binary_sensors:
        amcrest_binary_sensors.append(
            AmcrestBinarySensor(amcrest.name, amcrest.device, sensor_type, lock))

    async_add_devices(amcrest_binary_sensors, True)
    return True

class AmcrestBinarySensor(BinarySensorDevice):

    def __init__(self, name, camera, sensor_type, lock):
        self._name = '{} {}'.format(name, BINARY_SENSORS.get(sensor_type))
        self._camera = camera
        self._sensor_type = sensor_type
        self._lock = lock
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    @property
    def device_class(self):
        return 'motion'

    def update(self):
        _LOGGER.debug('Pulling data from {} binary sensor.'.format(self._name))

        if self._lock.acquire(timeout=LOCK_TIMEOUT):
            try:
                if self._sensor_type == 'motion_detected':
                    try:
                        self._state = self._camera.is_motion_detected
                    except RequestException as exc:
                        _LOGGER.error('{}: {}'.format(exc.__class__.__name__, str(exc)))
            finally:
                self._lock.release()
