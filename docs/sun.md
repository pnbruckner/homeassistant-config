# Sun
This is an enhanced version of the [standard Sun component](https://www.home-assistant.io/components/sun/). Without configuration additions it behaves exactly as the standard component. With configuration additions you can:

- Select which attributes sun.sun should have from the original set, as well as a few new ones.
- Control how often azimuth and elevation are updated.

To use this custom component, place a copy of:

[sun.py](https://github.com/pnbruckner/homeassistant-config/blob/master/custom_components/sun.py) at `<config>/custom_components/sun.py`

where `<config>` is your Home Assistant configuration directory. Then add the desired configuration. Here is an example of a typical configuration:
```yaml
sun:
  monitored_conditions:
    - elevation
    - next_rising
    - next_setting
    - sunrise
    - sunset
  scan_interval:
    minutes: 10
```
## Configuration variables
- **monitored_conditions** (*Optional*): A list of `sun.sun` attributes to include. Options from the standard component: `azimuth`, `elevation`, `next_dawn`, `next_dusk`, `next_midnight`, `next_noon`, `next_rising` and `next_setting`. New options: `daylight`, `next_daylight`, `prev_daylight`, `sunrise` and `sunset`. The default is to include the options from the standard component.
- **scan_interval** (*Optional*): If `azimuth` or `elevation` are included, then this controls how often they are updated. The default is the same behavior as the standard component (i.e., once a minute on the half minute.)
### New attributes
Attribute | Description
---|---
`daylight` | The amount of time from today's sunrise to today's sunset (in seconds).
`next_daylight` | Same as daylight, except for tomorrow.
`prev_daylight` | Same as daylight, except for yesterday.
`sunrise` | Today's sunrise (in UTC).
`sunset` | Today's sunset (in UTC).
### Caveats
`elevation`, `next_rising` and `next_setting` are used by the frontend. You can choose to exclude these attributes if you don't care about them, especially if don't display `sun.sun` in the frontend. If you do display it in the frontend and choose to exclude one or more of these, nothing will *break*, but obviously the corresponding data will not be available. Specifically, even if you exclude `next_rising` and/or `next_setting`, `sun.sun`'s state will still be correct. (Note that sun.py uses next_rising and next_setting internally to determine sun.sun's state. If you exclude them, they will still be maintained internally; they just won't be exposed as attributes.)
## Example full configuration
```yaml
sun:
  monitored_conditions:
    - azimuth
    - elevation
    - next_dawn
    - next_dusk
    - next_midnight
    - next_noon
    - next_rising
    - next_setting
    - daylight
    - next_daylight
    - prev_daylight
    - sunrise
    - sunset
  scan_interval:
    minutes: 1
```
## Example usage
### Sensors
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
        value_template: "{{ (state_attr('sun.sun', 'daylight')/(60*60))|round(1) }}"
        unit_of_measurement: hr
      daylight_hms:
        friendly_name: "Daylight HH:MM:SS"
        value_template: >
          {{ state_attr('sun.sun', 'daylight')|int|timestamp_custom('%H:%M:%S', false) }}
      daylight_chg:
        friendly_name: Daylight Change from Yesterday
        value_template: >
          {{ (state_attr('sun.sun', 'daylight') - state_attr('sun.sun', 'prev_daylight'))|int }}
        unit_of_measurement: sec
```
