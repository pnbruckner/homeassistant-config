"""Support for Amcrest IP cameras."""
import asyncio
import logging

from requests import RequestException
from urllib3.exceptions import ReadTimeoutError
import voluptuous as vol

from homeassistant.components.camera import (
    Camera, DOMAIN, SUPPORT_ON_OFF, CAMERA_SERVICE_SCHEMA)
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.core import callback
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_NAME, STATE_ON, STATE_OFF)
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession, async_aiohttp_proxy_web,
    async_aiohttp_proxy_stream)
from homeassistant.helpers.service import extract_entity_ids
try:
    from . import (DATA_AMCREST, STREAM_SOURCE_LIST, TIMEOUT)
except ImportError:
    from custom_components.amcrest import (
        DATA_AMCREST, STREAM_SOURCE_LIST, TIMEOUT)


DEPENDENCIES = ['amcrest', 'ffmpeg']

_LOGGER = logging.getLogger(__name__)

DATA_AMCREST_CAMS = 'amcrest_cams'

OPTIMISTIC = True

_BOOL_TO_STATE = {True: STATE_ON, False: STATE_OFF}

SERVICE_ENABLE_RECORDING = 'amcrest_enable_recording'
SERVICE_DISABLE_RECORDING = 'amcrest_disable_recording'
SERVICE_GOTO_PRESET = 'amcrest_goto_preset'
SERVICE_SET_COLOR_BW = 'amcrest_set_color_bw'
SERVICE_AUDIO_ON = 'amcrest_audio_on'
SERVICE_AUDIO_OFF = 'amcrest_audio_off'
SERVICE_MASK_ON = 'amcrest_mask_on'
SERVICE_MASK_OFF = 'amcrest_mask_off'
SERVICE_TOUR_ON = 'amcrest_tour_on'
SERVICE_TOUR_OFF = 'amcrest_tour_off'

ATTR_PRESET = 'preset'
ATTR_COLOR_BW = 'color_bw'

CBW_COLOR = 'color'
CBW_AUTO = 'auto'
CBW_BW = 'bw'
CBW = [CBW_COLOR, CBW_AUTO, CBW_BW]

SERVICE_GOTO_PRESET_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
})
SERVICE_SET_COLOR_BW_SCHEMA = CAMERA_SERVICE_SCHEMA.extend({
    vol.Required(ATTR_COLOR_BW): vol.In(CBW),
})

_MOT_DET_WINDOW = {False: [{'window': 1, 'sensitive': 75, 'threshold': 12},
                           {'window': 2, 'sensitive': 50, 'threshold': 16}],
                   True:  [{'window': 1, 'sensitive': 75, 'threshold':  6},
                           {'window': 2, 'sensitive': 75, 'threshold':  6}]}


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up an Amcrest IP Camera."""
    # pylint: disable=unused-argument
    # pylint: disable=too-many-statements
    if discovery_info is None:
        return

    device_name = discovery_info[CONF_NAME]
    amcrest = hass.data[DATA_AMCREST][device_name]

    async_add_entities([AmcrestCam(hass, amcrest)], True)

    def target_cameras(service):
        if DATA_AMCREST_CAMS in hass.data:
            if ATTR_ENTITY_ID in service.data:
                entity_ids = extract_entity_ids(hass, service)
            else:
                entity_ids = None
            for camera in hass.data[DATA_AMCREST_CAMS]:
                if entity_ids is None or camera.entity_id in entity_ids:
                    yield camera

    async def async_service_handler(service):
        update_tasks = []
        for camera in target_cameras(service):
            if service.service == SERVICE_ENABLE_RECORDING:
                await camera.async_enable_recording()
            elif service.service == SERVICE_DISABLE_RECORDING:
                await camera.async_disable_recording()
            elif service.service == SERVICE_AUDIO_ON:
                await camera.async_audio_on()
            elif service.service == SERVICE_AUDIO_OFF:
                await camera.async_audio_off()
            elif service.service == SERVICE_MASK_ON:
                await camera.async_mask_on()
            elif service.service == SERVICE_MASK_OFF:
                await camera.async_mask_off()
            elif service.service == SERVICE_TOUR_ON:
                await camera.async_tour_on()
            elif service.service == SERVICE_TOUR_OFF:
                await camera.async_tour_off()
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks, loop=hass.loop)

    async def async_goto_preset(service):
        preset = service.data.get(ATTR_PRESET)

        update_tasks = []
        for camera in target_cameras(service):
            await camera.async_goto_preset(preset)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks, loop=hass.loop)

    async def async_set_color_bw(service):
        cbw = service.data.get(ATTR_COLOR_BW)

        update_tasks = []
        for camera in target_cameras(service):
            await camera.async_set_color_bw(cbw)
            if not camera.should_poll:
                continue
            update_tasks.append(camera.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks, loop=hass.loop)

    services = (
        (SERVICE_ENABLE_RECORDING, async_service_handler,
         CAMERA_SERVICE_SCHEMA),
        (SERVICE_DISABLE_RECORDING, async_service_handler,
         CAMERA_SERVICE_SCHEMA),
        (SERVICE_GOTO_PRESET, async_goto_preset, SERVICE_GOTO_PRESET_SCHEMA),
        (SERVICE_SET_COLOR_BW, async_set_color_bw,
         SERVICE_SET_COLOR_BW_SCHEMA),
        (SERVICE_AUDIO_OFF, async_service_handler, CAMERA_SERVICE_SCHEMA),
        (SERVICE_AUDIO_ON, async_service_handler, CAMERA_SERVICE_SCHEMA),
        (SERVICE_MASK_OFF, async_service_handler, CAMERA_SERVICE_SCHEMA),
        (SERVICE_MASK_ON, async_service_handler, CAMERA_SERVICE_SCHEMA),
        (SERVICE_TOUR_OFF, async_service_handler, CAMERA_SERVICE_SCHEMA),
        (SERVICE_TOUR_ON, async_service_handler, CAMERA_SERVICE_SCHEMA))
    if not hass.services.has_service(DOMAIN, services[0][0]):
        for service in services:
            hass.services.async_register(DOMAIN, *service)

    return True


def _check_result(result, data=None):
    if not result.upper().startswith('OK'):
        msg = 'Camera operation failed'
        if data:
            msg += ': ' + data
        raise ValueError(msg)


class AmcrestCam(Camera):
    """An implementation of an Amcrest IP camera."""

    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-instance-attributes

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
        self._snapshot_lock = asyncio.Lock()

    async def async_added_to_hass(self):
        """Add camera to list."""
        self.hass.data.setdefault(DATA_AMCREST_CAMS, []).append(self)

    async def async_camera_image(self):
        """Return a still image response from the camera."""
        if not self.is_on:
            return None
        async with self._snapshot_lock:
            try:
                # Send the request to snap a picture and return raw jpg data
                response = await self.hass.async_add_executor_job(
                    self._camera.snapshot, self._resolution)
                return response.data
            except (RequestException, ReadTimeoutError, ValueError) as error:
                _LOGGER.error(
                    'Could not get camera image due to error %s', error)
                return None

    async def handle_async_mjpeg_stream(self, request):
        """Return an MJPEG stream."""
        # The snapshot implementation is handled by the parent class
        if self._stream_source == STREAM_SOURCE_LIST['snapshot']:
            return await super().handle_async_mjpeg_stream(request)

        if self._stream_source == STREAM_SOURCE_LIST['mjpeg']:
            # stream an MJPEG image stream directly from the camera
            websession = async_get_clientsession(self.hass)
            streaming_url = self._camera.mjpeg_url(typeno=self._resolution)
            stream_coro = websession.get(
                streaming_url, auth=self._token, timeout=TIMEOUT)

            return await async_aiohttp_proxy_web(
                self.hass, request, stream_coro)

        # streaming via ffmpeg
        from haffmpeg import CameraMjpeg

        streaming_url = self._camera.rtsp_url(typeno=self._resolution)
        stream = CameraMjpeg(self._ffmpeg.binary, loop=self.hass.loop)
        await stream.open_camera(
            streaming_url, extra_cmd=self._ffmpeg_arguments)

        try:
            return await async_aiohttp_proxy_stream(
                self.hass, request, stream,
                self._ffmpeg.ffmpeg_stream_content_type)
        finally:
            await stream.close()

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
        """Return if state is assumed."""
        return OPTIMISTIC

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_ON_OFF

    # Camera property overrides

    @property
    def is_recording(self):
        """Return true if the device is recording."""
        return self._is_recording

    @is_recording.setter
    def is_recording(self, enable):
        """Turn recording on or off."""
        rec_mode = {'Automatic': 0, 'Manual': 1}
        try:
            self._camera.record_mode = rec_mode[
                'Manual' if enable else 'Automatic']
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In is_recording setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_recording = enable
                self.schedule_update_ha_state()

    @property
    def brand(self):
        """Return the camera brand."""
        return 'Amcrest'

    # Don't use Camera's motion_detection_enabled method/property because
    # Camera.state_attributes doesn't properly report the 'motion_detection'
    # attribute.
    # See is_motion_detection_on property/setter below.

    @property
    def model(self):
        """Return the camera model."""
        return self._model

    @property
    def frame_interval(self):
        """Return the interval between frames of the mjpeg stream."""
        return 0

    @property
    def is_on(self):
        """Return true if on."""
        return bool(self.is_streaming_on)

    # Additional Amcrest Camera properties

    @property
    def is_streaming_on(self):
        """Return the camera streaming status."""
        return self.is_streaming

    @is_streaming_on.setter
    def is_streaming_on(self, enable):
        """Enable or disable camera video stream."""
        try:
            self._set_video(enable)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In is_streaming_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self.is_streaming = enable
                self.schedule_update_ha_state()

    @property
    def is_motion_detection_on(self):
        """Return the camera motion detection status."""
        return self._is_motion_detection_on

    @is_motion_detection_on.setter
    def is_motion_detection_on(self, enable):
        """Enable or disable motion detection."""
        try:
            self._camera.motion_detection = str(enable).lower()
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In is_motion_detection_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_motion_detection_on = enable
                self.schedule_update_ha_state()

    @property
    def color_bw(self):
        """Return camera color mode."""
        return self._color_bw

    @color_bw.setter
    def color_bw(self, cbw):
        """Set camera color mode."""
        try:
            self._set_color_bw(cbw)
        except (RequestException, ValueError, IndexError) as exc:
            _LOGGER.error('In color_bw setter, cbw={}: {}: {}'.format(
                cbw, exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._color_bw = cbw
                self.schedule_update_ha_state()

    @property
    def is_audio_on(self):
        """Return if audio stream is enabled."""
        return self._is_audio_on

    @is_audio_on.setter
    def is_audio_on(self, enable):
        """Enable or disable audio stream."""
        try:
            self._set_audio(enable)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In is_audio_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_audio_on = enable
                self.schedule_update_ha_state()

    @property
    def is_mask_on(self):
        """Return if mask is on."""
        return self._is_mask_on

    @is_mask_on.setter
    def is_mask_on(self, enable):
        """Enable or disable camera mask."""
        try:
            self._set_mask(enable)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In is_mask_on setter: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            if OPTIMISTIC:
                self._is_mask_on = enable
                self.schedule_update_ha_state()

    # Other Entity method overrides

    def update(self):
        """Update entity status."""
        _LOGGER.debug('Pulling data from {} camera.'.format(self._name))
        try:
            encode_media = self._camera.encode_media.split()
            self._is_recording = self._camera.record_mode == 'Manual'
            self._is_motion_detection_on = self._camera.is_motion_detector_on()
            # Model should not be changing dynamically so only need to grab
            # once.
            if self._model is None:
                self._model = self._camera.device_type.split('=')[1].strip()
            video_in_options = self._camera.video_in_options.split()
            video_widget_config = self._camera.video_widget_config.split()
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In update: {}: {}'.format(
                exc.__class__.__name__, str(exc)))
        else:
            self.is_streaming = 'true' in [
                s.split('=')[-1] for s in encode_media
                if '.VideoEnable=' in s]
            cbw = [
                s.split('=')[-1] for s in video_in_options
                if '].DayNightColor=' in s][0]
            self._color_bw = CBW[int(cbw)]
            self._is_audio_on = 'true' in [
                s.split('=')[-1] for s in encode_media
                if '.AudioEnable=' in s]
            self._is_mask_on = 'true' in [
                s.split('=')[-1] for s in video_widget_config
                if '.Covers' in s and '.EncodeBlend=' in s]

    # Other Camera method overrides

    def turn_off(self):
        """Turn off camera."""
        self.is_recording = False
        self.is_streaming_on = False

    def turn_on(self):
        """Turn on camera."""
        self.is_streaming_on = True

    def enable_motion_detection(self):
        """Enable motion detection in the camera."""
        self.is_motion_detection_on = True

    def disable_motion_detection(self):
        """Disable motion detection in camera."""
        self.is_motion_detection_on = False

    # Additional Amcrest Camera service methods

    def enable_recording(self):
        """Enable recording in the camera."""
        self.is_recording = True

    @callback
    def async_enable_recording(self):
        """Call the job and enable recording."""
        return self.hass.async_add_job(self.enable_recording)

    def disable_recording(self):
        """Disable recording in the camera."""
        self.is_recording = False

    @callback
    def async_disable_recording(self):
        """Call the job and disable recording."""
        return self.hass.async_add_job(self.disable_recording)

    def goto_preset(self, preset):
        """Move camera position and zoom to preset."""
        try:
            _check_result(
                self._camera.go_to_preset(
                    action='start', preset_point_number=preset),
                'preset={}'.format(preset))
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In goto_preset: {}: {}'.format(
                exc.__class__.__name__, str(exc)))

    @callback
    def async_goto_preset(self, preset):
        """Move camera to preset position."""
        return self.hass.async_add_job(self.goto_preset, preset)

    def set_color_bw(self, cbw):
        """Set camera color mode."""
        self.color_bw = cbw

    @callback
    def async_set_color_bw(self, cbw):
        """Set camera color mode."""
        return self.hass.async_add_job(self.set_color_bw, cbw)

    def audio_on(self):
        """Turn audio on."""
        self.is_audio_on = True

    @callback
    def async_audio_on(self):
        """Turn audio on."""
        return self.hass.async_add_job(self.audio_on)

    def audio_off(self):
        """Turn audio off."""
        self.is_audio_on = False

    @callback
    def async_audio_off(self):
        """Turn audio off."""
        return self.hass.async_add_job(self.audio_off)

    def mask_on(self):
        """Turn mask on."""
        self.is_mask_on = True

    @callback
    def async_mask_on(self):
        """Turn mask on."""
        return self.hass.async_add_job(self.mask_on)

    def mask_off(self):
        """Turn mask off."""
        self.is_mask_on = False

    @callback
    def async_mask_off(self):
        """Turn mask off."""
        return self.hass.async_add_job(self.mask_off)

    def tour_on(self):
        """Start camera tour."""
        try:
            self._tour(True)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In tour_on: {}: {}'.format(
                exc.__class__.__name__, str(exc)))

    @callback
    def async_tour_on(self):
        """Start camera tour."""
        return self.hass.async_add_job(self.tour_on)

    def tour_off(self):
        """Stop camera tour."""
        try:
            self._tour(False)
        except (RequestException, ValueError) as exc:
            _LOGGER.error('In tour_off: {}: {}'.format(
                exc.__class__.__name__, str(exc)))

    @callback
    def async_tour_off(self):
        """Stop camera tour."""
        return self.hass.async_add_job(self.tour_off)

    # Methods missing from self._camera.

    def _set_color_bw(self, cbw):
        cmd = '='.join([
            'configManager.cgi?action',
            'setConfig&VideoInOptions[0].DayNightColor',
            str(CBW.index(cbw))])
        _check_result(
            self._camera.command(cmd).content.decode(),
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
        for fmt, num in formats:
            for i in range(num):
                cmd += '&Encode[0].{}Format[{}].{}Enable={}'.format(
                    fmt, i, param, str(enable).lower())
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
            'ptz.cgi?action=start&channel=0&code={}Tour'
            '&arg1=1&arg2=0&arg3=0&arg4=0'.format(
                'Start' if start else 'Stop'))
