# Home Assistant Configuration
## custom_components.json
Lists custom components that can be managed by the Custom Updater. For more information, see:

https://github.com/custom-components/custom_updater

Add the following to your configuration:
```
custom_updater:
  component_urls: https://raw.githubusercontent.com/pnbruckner/homeassistant-config/master/custom_components.json
```
## custom_components
### amcrest.py, binary_sensor/amcrest.py & camera/amcrest.py
Add several services to Amcrest Camera and create new binary sensor for motion detected. Add thread locking to avoid simultaneous camera commands that lead to constant errors.
### device_tracker/composite.py
[Composite Device Tracker platform](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/composite.md)
### life360.py & device_tracker/life360.py
[Life360 Device Tracker platform](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/life360.md)
### sensor/illuminance.py
Estimate outdoor illuminance based on time of day and current weather conditions from Weather Underground.

See: https://community.home-assistant.io/t/outdoor-illuminance-estimated-from-weather-conditions-reported-by-weather-underground
### sun.py
[Enhanced Sun component](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/sun.md)
## python_scripts
### light_store.py
Save and restore state of switches and lights (and groups of them.)

See: https://community.home-assistant.io/t/python-script-to-save-and-restore-switches-and-lights
## tools
### logcomps.py
Script to generate a list of components that have written to home-assistant.log. Each line of the output is the component's name, the severity level, and the number of lines in the log that match. The list is sorted by the number of lines, and the total number of lines is also output last. This can be used to decide what to exclude from the log (via the logger config parameter) to reduce the size of the log and frequency with which it is written.

Simply place a copy in your configuration directory, then run it like this:
```
python3 logcomps.py
```
The output looks like this:
```
homeassistant.components.zwave.util DEBUG 1888
openzwave DEBUG 670
homeassistant.core INFO 660
homeassistant.components.automation INFO 85
homeassistant.setup INFO 85
homeassistant.util.json DEBUG 64
homeassistant.loader INFO 62
homeassistant.components.automation DEBUG 42
nest.nest DEBUG 26
homeassistant.components.history DEBUG 24
sseclient DEBUG 22
homeassistant.helpers.script INFO 21
homeassistant.components.recorder.util DEBUG 13
homeassistant.components.nest DEBUG 12
homeassistant.components.sensor INFO 11
homeassistant.components.http.view INFO 11
homeassistant.components.zwave DEBUG 7
homeassistant.components.binary_sensor INFO 7
custom_components.device_tracker.life360 DEBUG 6
homeassistant.loader WARNING 6
homeassistant.components.zwave INFO 5
homeassistant.components.switch INFO 4
homeassistant.components.media_player.cast DEBUG 4
homeassistant.components.binary_sensor.ping DEBUG 4
homeassistant.components.light.zwave DEBUG 4
pychromecast.socket_client DEBUG 4
openzwave INFO 3
homeassistant.components.camera INFO 3
homeassistant.components.notify INFO 2
custom_components.camera.amcrest DEBUG 2
homeassistant.components.light INFO 2
custom_components.sensor.illuminance DEBUG 2
homeassistant.helpers.restore_state DEBUG 2
nest.nest INFO 2
pychromecast.controllers DEBUG 2
homeassistant.components.recorder DEBUG 1
homeassistant.bootstrap INFO 1
root DEBUG 1
pychromecast INFO 1
homeassistant.components.device_tracker INFO 1
homeassistant.components.recorder.util ERROR 1
homeassistant.components.climate INFO 1
homeassistant.components.media_player INFO 1
total: 3775
```
