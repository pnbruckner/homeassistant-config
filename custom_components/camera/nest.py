from homeassistant.components.camera.nest import *
from homeassistant.components.camera.nest import _LOGGER

import asyncio
import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.loader import bind_hass
from homeassistant.components.camera import (
    CAMERA_SERVICE_SCHEMA, STATE_IDLE, STATE_RECORDING, DOMAIN)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import extract_entity_ids

DATA_NEST_CAMS = 'nest_cams'

SERVICE_SET_OPERATION_MODE = 'nest_set_operation_mode'
ATTR_OPERATION_MODE = 'operation_mode'

SET_OPERATION_MODE_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_OPERATION_MODE): vol.In([STATE_IDLE, STATE_RECORDING]),
})


@bind_hass
def set_operation_mode(hass, operation_mode, entity_id=None):
    """Set operation mode."""
    data = {ATTR_OPERATION_MODE: operation_mode}

    if entity_id is not None:
        data[ATTR_ENTITY_ID] = entity_id

    hass.async_add_job(hass.services.async_call(
        DOMAIN, SERVICE_SET_OPERATION_MODE, data))


# Replace setup_platform with a version that adds service to set operation mode.
# Also, use new class derived from NestCamera that adds required methods.
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up a Nest Cam."""
    if discovery_info is None:
        return

    def target_cameras(service):
        if DATA_NEST_CAMS in hass.data:
            if ATTR_ENTITY_ID in service.data:
                entity_ids = extract_entity_ids(hass, service)
            else:
                entity_ids = None
            for camera in hass.data[DATA_NEST_CAMS]:
                if entity_ids is None or camera.entity_id in entity_ids:
                    yield camera

    @asyncio.coroutine
    def async_operation_set_service(service):
        operation_mode = service.data.get(ATTR_OPERATION_MODE)

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_set_operation_mode(operation_mode)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    hass.services.register(
        DOMAIN, SERVICE_SET_OPERATION_MODE, async_operation_set_service,
        schema=SET_OPERATION_MODE_SCHEMA)

    camera_devices = hass.data[nest.DATA_NEST].cameras()
    cameras = [MyNestCamera(structure, device)
               for structure, device in camera_devices]
    add_devices(cameras, True)


class MyNestCamera(NestCamera):
    """Representation of a Nest Camera."""

    @asyncio.coroutine
    def async_added_to_hass(self):
        if DATA_NEST_CAMS not in self.hass.data:
            self.hass.data[DATA_NEST_CAMS] = []
        self.hass.data[DATA_NEST_CAMS].append(self)

    def set_operation_mode(self, operation_mode):
        """Set operation mode in the camera."""
        #self.device.is_streaming = operation_mode != STATE_IDLE
        _LOGGER.debug('set_operation_mode resp = {}'.format(
            self.device._set('devices/cameras',
                {'is_streaming': operation_mode == STATE_RECORDING})))

    def async_set_operation_mode(self, operation_mode):
        return self.hass.async_add_job(self.set_operation_mode, operation_mode)
