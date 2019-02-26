"""Suppoort for Amcrest IP camera sensors."""
from homeassistant.components.amcrest.sensor import *
from homeassistant.components.amcrest.sensor import AmcrestSensor as BaseAmcrestSensor
from . import DATA_AMCREST_LOCK, LOCK_TIMEOUT


async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):
    """Set up a sensor for an Amcrest IP Camera."""
    if discovery_info is None:
        return

    device_name = discovery_info[CONF_NAME]
    sensors = discovery_info[CONF_SENSORS]
    amcrest = hass.data[DATA_AMCREST][device_name]
    lock = hass.data[DATA_AMCREST_LOCK][device_name]

    amcrest_sensors = []
    for sensor_type in sensors:
        amcrest_sensors.append(
            AmcrestSensor(amcrest.name, amcrest.device, sensor_type, lock))

    async_add_entities(amcrest_sensors, True)
    return True


class AmcrestSensor(BaseAmcrestSensor):
    """A sensor implementation for Amcrest IP camera."""

    def __init__(self, name, camera, sensor_type, lock):
        """Initialize a sensor for Amcrest camera."""
        self._lock = lock
        super().__init__(name, camera, sensor_type)

    def update(self):
        """Get the latest data and updates the state."""
        if self._lock.acquire(timeout=LOCK_TIMEOUT):
            try:
                super().update()
            finally:
                self._lock.release()
