# Sun
>__NOTE__: This custom integration, although it may still work, has been replaced with a completely new implementation. You can find it here: https://github.com/pnbruckner/ha-sun2

This is an enhanced version of the [standard Sun component](https://www.home-assistant.io/components/sun/). Without configuration additions it behaves exactly as the standard component. With configuration additions you can:

- Select which attributes sun.sun should have from the original set, as well as a few new ones.
- Control how often azimuth and elevation are updated.
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater. The name of this `"element"` is `"sun"`.

>__NOTE__: You need to use Custom Updater version 4.2.9 or later.

Alternatively, place a copy of:

[`sun/__init__.py`](../custom_components/sun/__init__.py) at `<config>/custom_components/sun/__init__.py`  
[`sun/automation.py`](../custom_components/sun/automation.py) at `<config>/custom_components/sun/automation.py`  
[`sun/manifest.json`](../custom_components/sun/manifest.json) at `<config>/custom_components/sun/manifest.json`

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

Then add the desired configuration. Here is an example of a typical configuration:
```yaml
sun:
  monitored_conditions:
    - elevation
    - sunrise
    - sunset
  scan_interval:
    minutes: 10
```
### Home Assistant before 0.86
For manual installation, place a copy of:

[`sun/__init__.py`](../custom_components/sun/__init__.py) at `<config>/custom_components/sun.py`

`sun/automation.py` is not used.
## Configuration variables
- **monitored_conditions** (*Optional*): A list of `sun.sun` attributes to include. Options from the standard component: `azimuth`, `elevation`, `next_dawn`, `next_dusk`, `next_midnight` and `next_noon`. New options: `daylight`, `max_elevation`, `next_daylight`, `prev_daylight`, `sunrise` and `sunset`. The default is to include the options from the standard component. _Note:_ `next_rising` and `next_setting` are always included.
- **scan_interval** (*Optional*): If `azimuth` or `elevation` are included, then this controls how often they are updated. The default is the same behavior as the standard component (i.e., once a minute on the half minute.)
## New attributes
Attribute | Description
---|---
`daylight` | The amount of time from today's sunrise to today's sunset (in seconds).
`max_elevation` | Maximum value of elevation for today.
`next_daylight` | Same as daylight, except for tomorrow.
`prev_daylight` | Same as daylight, except for yesterday.
`sunrise` | Today's sunrise (in UTC).
`sunset` | Today's sunset (in UTC).
## Caveats
`elevation` is used by the frontend. You can choose to exclude it if you don't care about it, especially if you don't display `sun.sun` in the frontend. If you do display it in the frontend and choose to exclude elevation, then its value will just be blank.
## Examples
### Example full configuration
```yaml
sun:
  monitored_conditions:
    - azimuth
    - elevation
    - max_elevation
    - next_dawn
    - next_dusk
    - next_midnight
    - next_noon
    - daylight
    - next_daylight
    - prev_daylight
    - sunrise
    - sunset
  scan_interval:
    minutes: 1
```
### Example usage
#### Sensors
```yaml

sensor:
  - platform: template
    sensors:
      sunrise:
        friendly_name: Sunrise
        value_template: "{{ as_timestamp(state_attr('sun.sun', 'sunrise'))|timestamp_custom('%X') }}"
      sunset:
        friendly_name: Sunset
        value_template: "{{ as_timestamp(state_attr('sun.sun', 'sunset'))|timestamp_custom('%X') }}"

      daylight_sec:
        friendly_name: Daylight Seconds
        value_template: "{{ state_attr('sun.sun', 'daylight')|int }}"
        unit_of_measurement: sec
      daylight_hr:
        friendly_name: Daylight Hours
        value_template: "{{ (state_attr('sun.sun', 'daylight')/(60*60))|round(2) }}"
        unit_of_measurement: hr
      daylight_hms:
        friendly_name: "Daylight HH:MM:SS"
        value_template: >
          {{ state_attr('sun.sun', 'daylight')|int|timestamp_custom('%X', false) }}

      daylight_chg:
        friendly_name: Daylight Change from Yesterday
        value_template: >
          {{ (state_attr('sun.sun', 'daylight') - state_attr('sun.sun', 'prev_daylight'))|int }}
        unit_of_measurement: sec

      daylight_remaining_min:
        friendly_name: Daylight Remaining Minutes
        entity_id: sensor.time
        value_template: >
          {{ ((as_timestamp(state_attr('sun.sun', 'sunset')) - now().timestamp())/60)|int }}
        unit_of_measurement: min
      daylight_remaining_hm:
        friendly_name: "Daylight Remaining HH:MM"
        entity_id: sensor.time
        value_template: >
          {{ (as_timestamp(state_attr('sun.sun', 'sunset')) - now().timestamp())
             |timestamp_custom('%H:%M', false) }}
```
Note that the last two examples use `now()` in the template. However, this by itself will not cause the template sensors to update when time changes. So we need some way to get them to update. By configuring sensor.time (see [Time & Date](https://www.home-assistant.io/components/sensor.time_date/)), we can use that via the entity_id parameter to force the template sensors to update once a minute.
## Release Notes
Date | Version | Notes
-|:-:|-
20180907 | [1.0.0](https://github.com/pnbruckner/homeassistant-config/blob/d767bcce0fdff0c9298dc7a010d27af88817eac2/custom_components/sun.py) | Initial support for Custom Updater.
20190219 | [1.1.0](https://github.com/pnbruckner/homeassistant-config/blob/493ebce327f85abf489e97f8d4e4e2da5654847b/custom_components/sun.py) | Add `max_elevation`.
20190419 | [1.1.1](https://github.com/pnbruckner/homeassistant-config/blob/4f638d1ac9abd12f7bc1e8080763b545fd2385fa/custom_components/sun/__init__.py) | Add manifest.json required by 0.92.
