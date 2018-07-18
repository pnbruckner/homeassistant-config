"""
This component provides basic support for Amcrest IP cameras.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/camera.amcrest/
"""
import asyncio
import logging
from requests import RequestException

import voluptuous as vol

#from homeassistant.components.amcrest import (
#    DATA_AMCREST, STREAM_SOURCE_LIST, TIMEOUT)
from custom_components.amcrest import (
    DATA_AMCREST, STREAM_SOURCE_LIST, TIMEOUT)
from homeassistant.components.camera import (
    Camera, DOMAIN, STATE_RECORDING, STATE_STREAMING, STATE_IDLE,
    CAMERA_SERVICE_SCHEMA)
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_NAME, STATE_ON, STATE_OFF)
from homeassistant.loader import bind_hass
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession, async_aiohttp_proxy_web,
    async_aiohttp_proxy_stream)
from homeassistant.helpers.service import extract_entity_ids

DEPENDENCIES = ['amcrest', 'ffmpeg']

_LOGGER = logging.getLogger(__name__)

DATA_AMCREST_CAMS = 'amcrest_cams'

OPTIMISTIC = True

_BOOL_TO_STATE = {True: STATE_ON, False: STATE_OFF}

SERVICE_SET_OPERATION_MODE = 'amcrest_set_operation_mode'
SERVICE_GOTO_PRESET        = 'amcrest_goto_preset'
SERVICE_SET_COLOR_BW       = 'amcrest_set_color_bw'
SERVICE_AUDIO_ON           = 'amcrest_audio_on'
SERVICE_AUDIO_OFF          = 'amcrest_audio_off'
SERVICE_MASK_ON            = 'amcrest_mask_on'
SERVICE_MASK_OFF           = 'amcrest_mask_off'
SERVICE_TOUR_ON            = 'amcrest_tour_on'
SERVICE_TOUR_OFF           = 'amcrest_tour_off'

ATTR_OPERATION_MODE = 'operation_mode'
ATTR_PRESET         = 'preset'
ATTR_COLOR_BW       = 'color_bw'

CBW_COLOR = 'color'
CBW_AUTO  = 'auto'
CBW_BW    = 'bw'
CBW = [CBW_COLOR, CBW_AUTO, CBW_BW]

SERVICE_SET_OPERATION_MODE_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_OPERATION_MODE):
        vol.In([STATE_IDLE, STATE_STREAMING, STATE_RECORDING]),
})
SERVICE_GOTO_PRESET_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
})
SERVICE_SET_COLOR_BW_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_COLOR_BW): vol.In(CBW),
})
SERVICE_AUDIO_SCHEMA = CAMERA_SERVICE_SCHEMA
SERVICE_MASK_SCHEMA  = CAMERA_SERVICE_SCHEMA
SERVICE_TOUR_SCHEMA  = CAMERA_SERVICE_SCHEMA

_MOT_DET_WINDOW = {False: [{'window': 1, 'sensitive': 75, 'threshold': 12},
                           {'window': 2, 'sensitive': 50, 'threshold': 16}],
                   True:  [{'window': 1, 'sensitive': 75, 'threshold':  6},
                           {'window': 2, 'sensitive': 75, 'threshold':  6}]}


@bind_hass
def set_operation_mode(hass, operation_mode, entity_id=None):
    """Set operation mode."""
    data = {ATTR_OPERATION_MODE: operation_mode}

    if entity_id is not None:
        data[ATTR_ENTITY_ID] = entity_id

    hass.async_add_job(hass.services.async_call(
        DOMAIN, SERVICE_SET_OPERATION_MODE, data))

@bind_hass
def goto_preset(hass, preset, entity_id=None):
    """Goto preset position."""
    data = {ATTR_PRESET: preset}

    if entity_id is not None:
        data[ATTR_ENTITY_ID] = entity_id

    hass.async_add_job(hass.services.async_call(
        DOMAIN, SERVICE_GOTO_PRESET, data))

@bind_hass
def set_color_bw(hass, cbw, entity_id=None):
    """Set DayNight color mode."""
    data = {ATTR_COLOR_BW: cbw}

    if entity_id is not None:
        data[ATTR_ENTITY_ID] = entity_id

    hass.async_add_job(hass.services.async_call(
        DOMAIN, SERVICE_SET_COLOR_BW, data))


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up an Amcrest IP Camera."""
    if discovery_info is None:
        return

    device_name = discovery_info[CONF_NAME]
    amcrest = hass.data[DATA_AMCREST][device_name]

    async_add_devices([AmcrestCam(hass, amcrest)], True)

    def target_cameras(service):
        if DATA_AMCREST_CAMS in hass.data:
            if ATTR_ENTITY_ID in service.data:
                entity_ids = extract_entity_ids(hass, service)
            else:
                entity_ids = None
            for camera in hass.data[DATA_AMCREST_CAMS]:
                if entity_ids is None or camera.entity_id in entity_ids:
                    yield camera

    @asyncio.coroutine
    def async_set_operation_mode(service):
        operation_mode = service.data.get(ATTR_OPERATION_MODE)

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_set_operation_mode(operation_mode)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    @asyncio.coroutine
    def async_goto_preset(service):
        preset = service.data.get(ATTR_PRESET)

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_goto_preset(preset)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    @asyncio.coroutine
    def async_set_color_bw(service):
        cbw = service.data.get(ATTR_COLOR_BW)

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_set_color_bw(cbw)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    @asyncio.coroutine
    def async_set_audio(service):
        enable = service.service == SERVICE_AUDIO_ON

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_set_audio(enable)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    @asyncio.coroutine
    def async_set_mask(service):
        enable = service.service == SERVICE_MASK_ON

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_set_mask(enable)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    @asyncio.coroutine
    def async_tour(service):
        start = service.service == SERVICE_TOUR_ON

        update_tasks = []
        for camera in target_cameras(service):
            yield from camera.async_tour(start)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            yield from asyncio.wait(update_tasks, loop=hass.loop)

    services = (
        (SERVICE_SET_OPERATION_MODE, async_set_operation_mode,
            SERVICE_SET_OPERATION_MODE_SCHEMA),
        (SERVICE_GOTO_PRESET,  async_goto_preset,  SERVICE_GOTO_PRESET_SCHEMA),
        (SERVICE_SET_COLOR_BW, async_set_color_bw, SERVICE_SET_COLOR_BW_SCHEMA),
        (SERVICE_AUDIO_OFF,    async_set_audio,    SERVICE_AUDIO_SCHEMA),
        (SERVICE_AUDIO_ON,     async_set_audio,    SERVICE_AUDIO_SCHEMA),
        (SERVICE_MASK_OFF,     async_set_mask,     SERVICE_MASK_SCHEMA),
        (SERVICE_MASK_ON,      async_set_mask,     SERVICE_MASK_SCHEMA),
        (SERVICE_TOUR_OFF,     async_tour,         SERVICE_TOUR_SCHEMA),
        (SERVICE_TOUR_ON,      async_tour,         SERVICE_TOUR_SCHEMA))
    if not hass.services.has_service(DOMAIN, services[0][0]):
        for service in services:
            hass.services.async_register(DOMAIN, *service)

    return True


class AmcrestCam(Camera):
    """An implementation of an Amcrest IP camera."""

    def __init__(self, hass, amcrest):
        """Initialize an Amcrest camera."""
        super(AmcrestCam, self).__init__()
        self._name = amcrest.name
        self._camera = amcrest.device
        self._ffmpeg = hass.data[DATA_FFMPEG]
        self._ffmpeg_arguments = amcrest.ffmpeg_arguments
        self._stream_source = amcrest.stream_source
        self._resolution = amcrest.resolution
        self._token = self._auth = amcrest.authentication
        self.is_streaming = None
        self._is_recording = None
        self._is_motion_detection_on = None
        self._model = None
        # Amcrest Camera unique state attributes
        self._color_bw = None
        self._is_audio_on = None
        self._is_mask_on = None

    @asyncio.coroutine
    def async_added_to_hass(self):
        if DATA_AMCREST_CAMS not in self.hass.data:
            self.hass.data[DATA_AMCREST_CAMS] = []
        self.hass.data[DATA_AMCREST_CAMS].append(self)

    def camera_image(self):
        """Return a still image response from the camera."""
        # Send the request to snap a picture and return raw jpg data
        try:
            response = self._camera.snapshot(channel=self._resolution)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in camera_image: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
            return None
        else:
            return response.data

    @asyncio.coroutine
    def handle_async_mjpeg_stream(self, request):
        """Return an MJPEG stream."""
        # The snapshot implementation is handled by the parent class
        if self._stream_source == STREAM_SOURCE_LIST['snapshot']:
            yield from super().handle_async_mjpeg_stream(request)
            return

        elif self._stream_source == STREAM_SOURCE_LIST['mjpeg']:
            # stream an MJPEG image stream directly from the camera
            websession = async_get_clientsession(self.hass)
            streaming_url = self._camera.mjpeg_url(typeno=self._resolution)
            stream_coro = websession.get(
                streaming_url, auth=self._token, timeout=TIMEOUT)

            yield from async_aiohttp_proxy_web(self.hass, request, stream_coro)

        else:
            # streaming via fmpeg
            from haffmpeg import CameraMjpeg

            streaming_url = self._camera.rtsp_url(typeno=self._resolution)
            stream = CameraMjpeg(self._ffmpeg.binary, loop=self.hass.loop)
            yield from stream.open_camera(
                streaming_url, extra_cmd=self._ffmpeg_arguments)

            yield from async_aiohttp_proxy_stream(
                self.hass, request, stream,
                'multipart/x-mixed-replace;boundary=ffserver')
            yield from stream.close()

    # Entity property overrides

    @property
    def should_poll(self):
        """Amcrest camera will be polled only if OPTIMISTIC is False."""
        return not OPTIMISTIC

    @property
    def name(self):
        """Return the name of this camera."""
        return self._name

    @property
    def device_state_attributes(self):
        """Return the Amcrest-spectific camera state attributes."""
        attr = {}
        if self.is_motion_detection_on is not None:
            attr['motion_detection'] = _BOOL_TO_STATE.get(
                self.is_motion_detection_on)
        if self.color_bw is not None:
            attr[ATTR_COLOR_BW] = self.color_bw
        if self.is_audio_on is not None:
            attr['audio'] = _BOOL_TO_STATE.get(self.is_audio_on)
        if self.is_mask_on is not None:
            attr['mask'] = _BOOL_TO_STATE.get(self.is_mask_on)
        return attr

    @property
    def assumed_state(self):
        return OPTIMISTIC

    # Camera property overrides

    @property
    def is_recording(self):
        """Return true if the device is recording."""
        return self._is_recording

    @is_recording.setter
    def is_recording(self, enable):
        rec_mode = {'Automatic': 0, 'Manual': 1}
        self._camera.record_mode = rec_mode['Manual' if enable else 'Automatic']
        # Don't update status/state here because this setter is used at the same
        # time as setting is_streaming, and we only need to do the update once.
        # See set_operation_mode below. We'll also catch any exceptions there as well.

    @property
    def brand(self):
        """Return the camera brand."""
        return 'Amcrest'

    # Don't use Camera's motion_detection_enabled method/property because
    # Camera.state_attributes doesn't properly report the 'motion_detection' attribute.
    # See is_motion_detection_on property/setter below.

    @property
    def model(self):
        """Return the camera model."""
        return self._model

    # Additional Amcrest Camera properties

    @property
    def is_motion_detection_on(self):
        """Return the camera motion detection status."""
        return self._is_motion_detection_on

    @is_motion_detection_on.setter
    def is_motion_detection_on(self, enable):
        try:
            self._camera.motion_detection = str(enable).lower()
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in is_motion_detection_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_motion_detection_on = enable
                self.schedule_update_ha_state()

    @property
    def color_bw(self):
        return self._color_bw

    @color_bw.setter
    def color_bw(self, cbw):
        try:
            self._set_color_bw(cbw)
        except (RequestException, ValueError, IndexError) as exc:
            _LOGGER.error('in color_bw setter, cbw={}: {}: {}'.format(
                cbw, exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._color_bw = cbw
                self.schedule_update_ha_state()

    @property
    def is_audio_on(self):
        return self._is_audio_on

    @is_audio_on.setter
    def is_audio_on(self, enable):
        try:
            self._set_audio(enable)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in is_audio_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_audio_on = enable
                self.schedule_update_ha_state()

    @property
    def is_mask_on(self):
        return self._is_mask_on

    @is_mask_on.setter
    def is_mask_on(self, enable):
        try:
            self._set_mask(enable)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in is_mask_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_mask_on = enable
                self.schedule_update_ha_state()

    # Other Entity method overrides

    def update(self):
        _LOGGER.debug('Pulling data from {} camera.'.format(self._name))
        try:
            encode_media = self._camera.encode_media.split()
            self._is_recording = self._camera.record_mode == 'Manual'
            self._is_motion_detection_on = self._camera.is_motion_detector_on()
            # Model should not be changing dynamically so only need to grab once.
            if self._model is None:
                self._model = self._camera.device_type.split('=')[1].strip()
            video_in_options = self._camera.video_in_options.split()
            video_widget_config = self._camera.video_widget_config.split()
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in update: {}: {}'.format(exc.__class__.__name__, str(exc)))
        else:
            self.is_streaming = 'true' in [s.split('=')[-1]
                for s in encode_media if '.VideoEnable=' in s]
            self._color_bw = CBW[int([s.split('=')[-1]
                for s in video_in_options if '].DayNightColor=' in s][0])]
            self._is_audio_on = 'true' in [s.split('=')[-1]
                for s in encode_media if '.AudioEnable=' in s]
            self._is_mask_on = 'true' in [s.split('=')[-1]
                for s in video_widget_config if '.Covers' in s and '.EncodeBlend=' in s]

    def enable_motion_detection(self):
        """Enable motion detection in the camera."""
        self.is_motion_detection_on = True

    def disable_motion_detection(self):
        """Disable motion detection in camera."""
        self.is_motion_detection_on = False

    # Additional Amcrest Camera service methods

    def set_operation_mode(self, operation_mode):
        """Set operation mode in the camera."""
        is_recording_changed = False
        is_streaming_changed = False
        if self.is_recording and operation_mode != STATE_RECORDING:
            try:
                self.is_recording = False
            except (RequestException, ValueError) as exc:
                _LOGGER.error('while changing recording: {}: {}'.format(
                    exc.__class__.__name__, str(exc)))
            else:
                is_recording_changed = True
        new_video = None
        if self.is_streaming and operation_mode == STATE_IDLE:
            new_video = False
        elif not self.is_streaming and operation_mode != STATE_IDLE:
            new_video = True
        if new_video is not None:
            try:
                self._set_video(new_video)
            except (RequestException, ValueError) as exc:
                _LOGGER.error('while changing streaming: {}: {}'.format(
                    exc.__class__.__name__, str(exc)))
            else:
                is_streaming_changed = True
        if not self.is_recording and operation_mode == STATE_RECORDING:
            try:
                self.is_recording = True
            except (RequestException, ValueError) as exc:
                _LOGGER.error('while changing recording: {}: {}'.format(
                    exc.__class__.__name__, str(exc)))
            else:
                is_recording_changed = True
        if OPTIMISTIC and (is_recording_changed or is_streaming_changed):
            self._is_recording = operation_mode == STATE_RECORDING
            self.is_streaming = operation_mode != STATE_IDLE
            self.schedule_update_ha_state()

    def async_set_operation_mode(self, operation_mode):
        return self.hass.async_add_job(self.set_operation_mode, operation_mode)

    def goto_preset(self, preset):
        """Move camera position and zoom to preset."""
        #self.preset = preset
        try:
            self._check_result(
                self._camera.go_to_preset(action='start', preset_point_number=preset),
                'preset={}'.format(preset))
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in goto_preset: {}: {}'.format(
                exc.__class__.__name__, str(exc)))

    @asyncio.coroutine
    def async_goto_preset(self, preset):
        return self.hass.async_add_job(self.goto_preset, preset)

    def set_color_bw(self, cbw):
        self.color_bw = cbw

    @asyncio.coroutine
    def async_set_color_bw(self, cbw):
        return self.hass.async_add_job(self.set_color_bw, cbw)

    def set_audio(self, enable):
        self.is_audio_on = enable

    @asyncio.coroutine
    def async_set_audio(self, enable):
        return self.hass.async_add_job(self.set_audio, enable)

    def set_mask(self, enable):
        self.is_mask_on = enable

    @asyncio.coroutine
    def async_set_mask(self, enable):
        return self.hass.async_add_job(self.set_mask, enable)

    def tour(self, start):
        #self.is_touring = start
        try:
            self._tour(start)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('in tour: {}: {}'.format(exc.__class__.__name__, str(exc)))

    @asyncio.coroutine
    def async_tour(self, start):
        return self.hass.async_add_job(self.tour, start)

    # Methods missing from self._camera.

    def _check_result(self, result, data=None):
        if not result.upper().startswith('OK'):
            msg = 'Camera operation failed'
            if data:
                msg += ': ' + data
            raise ValueError(msg)

    def _set_color_bw(self, cbw):
        self._check_result(
            self._camera.command(
                    'configManager.cgi?action=setConfig'
                    '&VideoInOptions[0].DayNightColor={}'.format(CBW.index(cbw))
                ).content.decode(),
            'cbw = {}'.format(cbw))

    def _set_audio(self, enable):
        self._set_audio_video('Audio', enable)

    def _set_video(self, enable):
        self._set_audio_video('Video', enable)
        self._camera.command(
            'configManager.cgi?action=setConfig'
            '&VideoInOptions[0].InfraRed={}'.format(str(not enable).lower()))

    def _set_audio_video(self, param, enable):
        cmd = 'configManager.cgi?action=setConfig'
        formats = [('Extra', 3), ('Main', 4)]
        if param == 'Video':
            formats.append(('Snap', 3))
        for f, n in formats:
            for i in range(n):
                cmd += '&Encode[0].{}Format[{}].{}Enable={}'.format(
                    f, i, param, str(enable).lower())
        self._camera.command(cmd)

    def _set_mask(self, enable):
        cmd = 'configManager.cgi?action=setConfig'
        for i in range(4):
            cmd += '&VideoWidget[0].Covers[{}].EncodeBlend={}'.format(
                i, str(enable).lower())
        self._camera.command(cmd)
        cmd = 'configManager.cgi?action=setConfig'
        for params in _MOT_DET_WINDOW[enable]:
            cmd += '&MotionDetect[0].MotionDetectWindow[{window}]' \
                   '.Sensitive={sensitive}'.format(**params)
            cmd += '&MotionDetect[0].MotionDetectWindow[{window}]' \
                   '.Threshold={threshold}'.format(**params)
        self._camera.command(cmd)

    def _tour(self, start):
        self._camera.command(
            'ptz.cgi?action=start&channel=0&code={}Tour&arg1=1&arg2=0&arg3=0&arg4=0'.format(
                'Start' if start else 'Stop'))
