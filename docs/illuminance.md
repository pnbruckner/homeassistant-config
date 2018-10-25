# Illuminance Sensor
Estimates outdoor illuminance based on time of day and current weather conditions. The following sources of weather data are supported:

* [Dark Sky Sensor (icon)](https://www.home-assistant.io/components/sensor.darksky/)
* [Dark Sky Weather](https://www.home-assistant.io/components/weather.darksky/)
* Weather Underground
* [YR (symbol)](https://www.home-assistant.io/components/sensor.yr/)
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater.

Alternatively, place a copy of:

[sensor/illuminance.py](../custom_components/sensor/illuminance.py) at `<config>/custom_components/sensor/illuminance.py`

where `<config>` is your Home Assistant configuration directory.

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
- **scan_interval** (*Optional*): Polling interval.  Only useful when using WU. Minimum is 5 minutes. Default is 5 minutes.
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
2018xxxx | [2.0.0]() | Add support for using Dark Sky or YR entity as source of weather conditions.
