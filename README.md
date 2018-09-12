# Home Assistant Configuration
## Custom Components
### [Installing and Updating](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/custom_updater.md)
### [Amcrest Camera](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/amcrest.md)
> __NOTE__: The Amcrest Camera components are not supported via Custom Updater.
### [Composite Device Tracker platform](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/composite.md)
### [Life360 Device Tracker platform](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/life360.md)
### [Illuminance Sensor]()
__sensor/illuminance.py__

Estimate outdoor illuminance based on time of day and current weather conditions from Weather Underground.

See: https://community.home-assistant.io/t/outdoor-illuminance-estimated-from-weather-conditions-reported-by-weather-underground
### [Enhanced Sun component](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/sun.md)
## Python Scripts
### light_store.py
Save and restore state of switches and lights (and groups of them.)

See: https://community.home-assistant.io/t/python-script-to-save-and-restore-switches-and-lights
## Tools
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
