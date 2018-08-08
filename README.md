# Home Assistant Configuration
## custom_components
### amcrest.py, binary_sensor/amcrest.py & camera/amcrest.py
Add several services to Amcrest Camera and create new binary sensor for motion detected. Add thread locking to avoid simultaneous camera commands that lead to constant errors.
### life360.py & device_tracker/life360.py
Life360 Device Tracker platform.

See: https://community.home-assistant.io/t/life360-device-tracker-platform
### sensor/illuminance.py
Estimate outdoor illuminance based on time of day and current weather conditions from Weather Underground.

See: https://community.home-assistant.io/t/outdoor-illuminance-estimated-from-weather-conditions-reported-by-weather-underground
### sun.py
Add sunrise & sunset attributes updated at midnight. Add monitored_conditions config item to specify which attributes to maintain. If not specified then original set will be used. For elevation and azimuth, add scan_interval (minimum of one minute.) If next_rising or next_setting are not specified they will not be added as attributes. However, they will always be maintained anyway so that sun's state can be determined/maintained.
## python_scripts
### light_store.py
Save and restore state of switches and lights (and groups of them.)

See: https://community.home-assistant.io/t/python-script-to-save-and-restore-switches-and-lights
