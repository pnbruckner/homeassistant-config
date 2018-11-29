# Illuminance Sensor
Estimates outdoor illuminance based on current weather conditions and time of day. At night the value is 10. From a little before sunrise to a little after the value is ramped up to whatever the current conditions indicate. The same happens around sunset, except the value is ramped down. Below is an example of what that might look like over a three day period.

<p align="center">
  <img src=images/illuminance_history.png>
</p>

The following sources of weather data are supported:

* [Dark Sky Sensor (icon)](https://www.home-assistant.io/components/sensor.darksky/)
* [Dark Sky Weather](https://www.home-assistant.io/components/weather.darksky/)
* Weather Underground
* [YR (symbol)](https://www.home-assistant.io/components/sensor.yr/)
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater. The name of this `"element"` is `"sensor.illuminance"`.

Alternatively, place a copy of:

[sensor/illuminance.py](../custom_components/sensor/illuminance.py) at `<config>/custom_components/sensor/illuminance.py`

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

Then add the desired configuration. Here is an example of a typical configuration:
```yaml
sensor:
  - platform: illuminance
    entity_id: sensor.yr_symbol
```
## Configuration variables
- **api_key**: Weather Underground API key. Required when using WU.
- **entity_id**: Entity ID of Dark Sky or YR entity. See examples below. Required when using Dark Sky or YR.
- **name** (*Optional*): Name of the sensor. Default is `Illuminance`.
- **scan_interval** (*Optional*): Polling interval.  For non-WU configs only applies during ramp up period around sunrise and ramp down period around sunset. Minimum is 5 minutes. Default is 5 minutes.
- **query**: Weather Underground query. See https://www.wunderground.com/weather/api/d/docs?d=data/index. Required when using WU.
## Examples
### Dark Sky Sensor
```
sensor:
  - platform: darksky
    api_key: !secret ds_api_key
    monitored_conditions:
      - icon
  - platform: illuminance
    name: DSS Illuminance
    entity_id: sensor.dark_sky_icon
```
### Dark Sky Weather
```
weather:
  - platform: darksky
    api_key: !secret ds_api_key
sensor:
  - platform: illuminance
    name: DSW Illuminance
    entity_id: weather.dark_sky
```
### YR Sensor
```
sensor:
  - platform: yr
    monitored_conditions:
      - symbol
  - platform: illuminance
    name: YRS Illuminance
    entity_id: sensor.yr_symbol
```
### Weather Underground
```
sensor:
  - platform: illuminance
    name: WU Illuminance
    api_key: !secret wu_api_key
    query: !secret wu_query
    scan_interval:
      minutes: 30
```
## Caveats
Weather Underground no long provides free API keys. In fact, as of this writing they have notified that the REST API will be discontinued.
## Release Notes
Date | Version | Notes
-|:-:|-
20180907 | [1.0.0](https://github.com/pnbruckner/homeassistant-config/blob/d767bcce0fdff0c9298dc7a010d27af88817eac2/custom_components/sensor/illuminance.py) | Initial support for Custom Updater.
20181028 | [2.0.0](https://github.com/pnbruckner/homeassistant-config/blob/e4fbbfe5ccc48cc08045226197c5c27767ec081e/custom_components/sensor/illuminance.py) | Add support for using Dark Sky or YR entity as source of weather conditions. For WU, no longer get sunrise/sunset data from the server, just use HA’s sun data.
