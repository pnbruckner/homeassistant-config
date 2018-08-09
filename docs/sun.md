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
