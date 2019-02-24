# Life360
This platform allows you to detect presence using [Life360](http://life360.com/). It can also automatically create Home Assistant zones based on Life360 Places.
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater. The name of this `"element"` is `"life360.device_tracker"`.

Alternatively, place a copy of:

[life360/device_tracker.py](../custom_components/life360/device_tracker.py) at `<config>/custom_components/life360/device_tracker.py`

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

>__NOTE__: Releases prior to 2.2.0 required two different life360.py files to be installed. That is no longer required. There is just the one indicated above now. The other was moved to [PyPI](https://pypi.org/project/life360/) and will be installed automatically.

Then add the desired configuration. Here is an example of a typical configuration:
```yaml
device_tracker:
  - platform: life360
    username: !secret life360_username
    password: !secret life360_password
    max_gps_accuracy: 200
    prefix: life360
    show_as_state: driving, moving, places
```
### Home Assistant before 0.86
If using Custom Updater the name of this `"element"` is `"device_tracker.life360"`. For manual installation, place a copy of:

[life360/device_tracker.py](../custom_components/life360/device_tracker.py) at `<config>/custom_components/device_tracker/life360.py`
### numpy on Raspberry Pi
To determine time zone from GPS coordinates (see `time_as` configuration variable below) the package [timezonefinderL](https://pypi.org/project/timezonefinderL/) is used. That package requires the package [numpy](https://pypi.org/project/numpy/). These will both be installed automatically by HA. Note, however, that numpy on Pi _usually_ requires libatlas to be installed. (See [this web page](https://www.raspberrypi.org/forums/viewtopic.php?t=207058) for more details.) It can be installed using this command:
```
sudo apt install libatlas3-base
```
>Note: This is the same step that would be required if using a standard HA component that uses numpy (such as the [Trend Binary Sensor](https://www.home-assistant.io/components/binary_sensor.trend/)), and is only required if you use `device_or_utc` or `device_or_local` for `time_as`.
## Configuration variables
- **username**: Your Life360 username.
- **password**: Your Life360 password.
- **add_zones** (*Optional*): One of: `false`, `only_home`, `except_home` or `all`. The default is `false` if `zone_interval` is _not_ specified, or `except_home` if `zone_interval` _is_ specified. If not `false`, create HA zones based on Life360 Places. Life360 Places whose names match `home_place` (case insensitive) will only be used when set to `only_home` or `all`. Other Places will only be used when set to `except_home` or `all`. For legacy reasons, `true` is also accepted and is equivalent to `except_home`.
- **driving_speed** (*MPH or KPH, depending on HA's unit system configuration, Optional*): The minimum speed at which the device is considered to be "driving" (and which will also set the `driving` [attribute](#additional-attributes) to `true`. See also `Driving` state in [chart](#states) below.)
- **error_threshold** (*Optional*): The default is zero. See [Communication Errors](#communication-errors) for a detailed description.
- **filename** (*Optional*): The default is life360.conf. The platform will get an authorization token from the Life360 server using your username and password, and it will save the token in a file in the HA config directory (with limited permissions) so that it can reuse it after restarts (and not have to get a new token every time.) If the token eventually expires, a new one will be acquired as needed.
- **home_place** (*Optional*): Default is `Home`. Name of Life360 Place (if any) that coincides with home location as configured in HA.
- **interval_seconds** (*Optional*): The default is 12. This defines how often the Life360 server will be queried. The resulting device_tracker entities will actually only be updated when the Life360 server provides new location information for each member.
- **max_gps_accuracy** (*Meters, Optional*): If specified, and reported GPS accuracy is larger (i.e., *less* accurate), then update is ignored.
- **max_update_wait** (*Optional*): If specified, then if Life360 does not provide an update for a member within that maximum time window, the life360 platform will fire an event named `life360_update_overdue` with the entity_id of the corresponding member's device_tracker entity. Once an update does come it will fire an event named `life360_update_restored` with the entity_id of the corresponding member's device_tracker entity and another data item named `wait` that will indicate the amount of time spent waiting for the update. You can use these events in automations to be notified when they occur. See [example automations](#example-overdue-update-automations) below. 
- **members** (*Optional*): Default is to track all Life360 Members in all Circles. If you'd rather only track a specific set of members, then list them with each member specified as `first,last`, or if they only have one name, then `name`. Names are case insensitive, and extra spaces are ignored (except within a name, like `van Gogh`.) For backwards compatibility, a member with a single name can also be entered as `name,` or `,name`.
- **prefix** (*Optional*): Default is to name entities `device_tracker.<first_name>_<last_name>`, where `<first_name>` and `<last_name>` are specified by Life360. If a prefix is specified, then entity will be named `device_tracker.<prefix>_<first_name>_<last_name>`. If the member only has a first or last name in Life360, then the underscore that would normally separate the names is left out.
- **show_as_state** (*Optional*): One or more of: `driving`, `moving` and `places`. Default is for Device Tracker Component to determine entity state as normal. When specified these can cause the entity's state to show other statuses according to the [States](#states) chart below.
- **time_as** (*Optional*): One of `utc`, `local`, `device_or_utc` or `device_or_local`. Default is `utc` which shows time attributes in UTC. `local` shows time attributes per HA's `time_zone` configuration. `device_or_utc` and `device_or_local` attempt to determine the time zone in which the device is located based on its GPS coordinates. The name of the time zone (or `unknown`) will be shown in a new [attribute](#additional-attributes) named `time_zone`. If the time zone can be determined, then time attributes will be shown in that time zone. If the time zone cannot be determined, then time attributes will be shown in UTC if `device_or_utc` is selected, or in HA's local time zone if `device_or_local` is selected.
- **warning_threshold** (*Optional*): The default is communication errors will only be logged as ERRORs (not WARNINGs.) See [Communication Errors](#communication-errors) for a detailed description.
- **zone_interval** (*Optional*): The default is only to create HA zones at startup. If specified, will also update HA zones per Life360 Places periodically. Only applies if `add_zones` is not explicitly set to `false`.
## States
Order of precedence is from higher to lower.

show_as_state | State | Conditions
-|-|-
`places` | `home` | Place or check-in name (see below) matches `home_place` setting.
`places` | Place or check-in name | Member is in a Life360 defined "Place" or member has "checked in" via the Life360 app (and name does not match `home_place` setting.)
N/A | `home` | Device GPS coordinates are located in `zone.home`.
N/A | HA zone name | Device GPS coordinates are located in a HA defined zone (other than `zone.home`.)
`driving` | `Driving` | The Life360 server indicates the device "isDriving", or if `driving_speed` (see above) has been specified and the speed derived from the value provided by the Life360 server is at or above that value.
`moving` | `Moving` | The Life360 server indicates the device is "inTransit".
N/A | `not_home` | None of the above are true.
## Additional attributes
Attribute | Description
-|-
address | Address of current location, or `none`.
at_loc_since | Date and time when first at current location (in UTC.)
battery_charging | Device is charging (`true`/`false`.)
driving | Device movement indicates driving (`true`/`false`.)
entity_picture | Member's "avatar" if one is provided by Life360.
last_seen | Date and time when Life360 last updated your location (in UTC.)
moving | Device is moving (`true`/`false`.)
raw_speed | "Raw" speed value provided by Life360 server. (Units unknown.)
speed | Estimated speed of device (in MPH or KPH depending on HA's unit system configuration.)
time_zone | The name of the time zone in which the device is located, or `unknown` if it cannot be determined. Only exists if `device_or_utc` or `device_or_local` is chosen for `time_as`.
wifi_on | Device WiFi is turned on (`true`/`false`.)

>__NOTE__: `entity_picture` will only be set to Member's avatar the _very first time_ the device is seen. This is just how the device_tracker component-level code works. If an avatar is changed later the HA device_tracker entity's picture will not be updated automatically. If you want HA to use the new avatar you will need to manually edit known_devices.yaml.
## Services
Service | Description
-|-
`device_tracker.life360_zones_from_places` | Update HA zones from Life360 Places per `add_zones` configuration. Only available if `add_zones` is not `false`.
## Home - Home Assistant vs Life360
Normally HA device trackers are "Home" when they enter `zone.home`. (See [Zone documentation](https://www.home-assistant.io/components/zone/#home-zone) for details about how this zone is defined.) And Life360 normally considers your device "Home" when it enters the Place that coincides with your home (i.e., the Life360 "Home Place.") Since the definitions of these areas can be different, this can lead to a disagreement between HA and Life360 as to whether or not you're "Home." There are three basic ways to avoid this situation.

The first is to manually make sure these two areas are defined the same -- i.e., same location and radius.

The second is to include `places` in the HA life360 `show_as_state` configuration variable. Whenever Life360 determines you are in its Home Place the corresponding HA device tracker's state will be set to `home` (see `home_place` config variable.) But for this to solve the problem `zone.home` must be entirely contained within Life360's Home Place. If it isn't, and if you enter `zone.home` but not Life360's Home Place, then it is still possible for the two systems to disagree (i.e., HA indicating you're Home, but Life360 showing you're not.)

The third, and probably the easiest and most foolproof way, is to configure this platform to automatically update `zone.home` to be the exact same size, and at the exact same location, as Life360's Home Place. To enable this, set `add_zones` to `only_home` or `all`.
## Communication Errors
It is not uncommon for communication errors to occur between Home Assistant and the Life360 server. This can happen for many reasons, including Internet connection issues, Life360 server load, etc. However, in most cases, they are temporary and do not significantly affect the ability to keep device_tracker entities up to date.

Therefore an optional filtering mechanism has been implemented to prevent inconsequential communication errors from filling the log, while still logging unusual error activity. Two thresholds are defined: `warning_threshold` and `error_threshold`. When a particular type of communication error happens on consecutive update cycles, it will not be logged until the number of occurences exceeds these thresholds. When the number exceeds `warning_threshold` (but does not exceed `error_threshold`, and only if `warning_threshold` is defined) it will be logged as a WARNING. Once the number exceeds `error_threshold` it will be logged as an ERROR. Only two consecutive communication errors of a particular type will be logged as an ERROR, after which it will no longer be logged until it stops occuring.
## Examples
### Example full configuration
```yaml
device_tracker:
  - platform: life360
    username: !secret life360_username
    password: !secret life360_password
    add_zones: all
    # MPH, assuming imperial units.
    # If using metric (KPH), equivalent would be 29
    driving_speed: 18
    filename: life360.conf
    home_place: Home
    interval_seconds: 10
    max_gps_accuracy: 200
    max_update_wait:
      minutes: 45
    members:
      - mike, smith
      - Joe
      - Jones
    prefix: life360
    show_as_state: driving, moving
    time_as: device_or_local
    zone_interval:
      minutes: 15
    # Set comm error thresholds so first is not logged,
    # second is logged as a WARNING, and third and fourth
    # are logged as ERRORs.
    warning_threshold: 1
    error_threshold: 2
```
### Example overdue update automations
```yaml
automation:
  - alias: Life360 Overdue Update
    trigger:
      platform: event
      event_type: life360_update_overdue
    action:
      service: notify.email_me
      data_template:
        title: Life360 update overdue
        message: >
          Update for {{
            state_attr(trigger.event.data.entity_id, 'friendly_name') or
            trigger.event.data.entity_id
          }} is overdue.

  - alias: Life360 Update Restored
    trigger:
      platform: event
      event_type: life360_update_restored
    action:
      service: notify.email_me
      data_template:
        title: Life360 update restored
        message: >
          Update for {{
            state_attr(trigger.event.data.entity_id, 'friendly_name') or
            trigger.event.data.entity_id
          }} restored after {{ trigger.event.data.wait }}.
```
### Time zone examples
This example assumes `time_as` is set to `device_or_utc` or `device_or_local`. It determines the difference between the time zone in which the device is located and the `time_zone` in HA's configuration. A positive value means the device's time zone is ahead of (or later than, or east of) the local time zone.
```yaml
sensor:
  - platform: template
    sensors:
      my_tz_offset:
        friendly_name: My time zone offset
        unit_of_measurement: hr
        value_template: >
          {% set state = states.device_tracker.life360_me %}
          {% if state.attributes is defined and
                state.attributes.time_zone is defined and
                state.attributes.time_zone != 'unknown' %}
            {% set n = now() %}
            {{ (n.astimezone(state.attributes.last_seen.tzinfo).utcoffset() -
                n.utcoffset()).total_seconds()/3600 }}
          {% else %}
            unknown
          {% endif %}
```
This example converts a time attribute to the local time zone. It works no matter which time zone the attribute is in.
```yaml
sensor:
  - platform: template
    sensors:
      my_last_seen_local:
        friendly_name: My last_seen time in local time zone
        value_template: >
          {{ state_attr('device_tracker.life360_me', last_seen').astimezone(now().tzinfo) }}
```
## Disclaimer
Life360 does not apparently officially support its REST API for use with other than its own apps. This integration is based on reverse engineering that has been done by the open source community, and an API token that was somehow discovered by the same community. At any time Life360 could disable that token or otherwise change its REST API such that this custom component would no longer work.
## Release Notes
Date | Version | Notes
-|:-:|-
20180907 | [1.0.0](https://github.com/pnbruckner/homeassistant-config/blob/d767bcce0fdff0c9298dc7a010d27af88817eac2/custom_components/device_tracker/life360.py) | Initial support for Custom Updater.
20180910 | [1.1.0](https://github.com/pnbruckner/homeassistant-config/blob/118178acacafb36c5529e79577dd4eaf4bcfc0b4/custom_components/device_tracker/life360.py) | Add address attribute.
20180912 | [1.2.0](https://github.com/pnbruckner/homeassistant-config/blob/069e75a8d612ae8a75dcda114d79facca9ba9bae/custom_components/device_tracker/life360.py) | Filter excessive errors.
20180912 | [1.3.0](https://github.com/pnbruckner/homeassistant-config/blob/2111accaad47052e4ae73a5528cdf70c7ff00426/custom_components/device_tracker/life360.py) | Allow entries in members configuration variable that only have one name to be entered without comma.
20180918 | [1.4.0](https://github.com/pnbruckner/homeassistant-config/blob/c0431151be81d402eaa25c87bfd069371c3bcd10/custom_components/device_tracker/life360.py) | Handle members that don't share their location in one or more circles.
20180928 | [1.5.0](https://github.com/pnbruckner/homeassistant-config/blob/eb3dc1915c9289e741ba9db0471a271b0edd4677/custom_components/device_tracker/life360.py) | Add raw_speed and speed attributes and `driving_speed` config option. Derive `driving` attribute from speed if possible.
20181002 | [1.5.1](https://github.com/pnbruckner/homeassistant-config/blob/6cf17f0a5e02ef556862247ee632d61ce58c7b09/custom_components/device_tracker/life360.py) | Limit speed attribute to non-negative values.
20181016 | [1.6.0](https://github.com/pnbruckner/homeassistant-config/blob/c24c65a06e78d1ec6b7d11df9f10a7b94a583d12/custom_components/device_tracker/life360.py) | Update as soon as initialization is complete.
20181025 | [1.6.1](https://github.com/pnbruckner/homeassistant-config/blob/4320553f30b40e08b5bed27552b6242ab2908879/custom_components/device_tracker/life360.py) | __BREAKING CHANGE__: Event names were too long. Shorten them by removing `device_tracker.` prefixes.
20181102 | [2.0.0](https://github.com/pnbruckner/homeassistant-config/blob/da9bdcf9923f8e93820f23a49289af35c6371a71/custom_components/device_tracker/life360.py) | Add optional feature to create HA zones based on Life360 Places.
20181109 | [2.1.0](https://github.com/pnbruckner/homeassistant-config/blob/1f97852af12615a8db73c1171551423a7e4be02c/custom_components/device_tracker/life360.py) | __BREAKING CHANGE__: Change charging attribute to the more common battery_charging attribute. Instead of a float, make battery attribute an int like it should have been originally.
20181120 | [2.2.0](https://github.com/pnbruckner/homeassistant-config/blob/3ad096f1c59751f6b7413678418cae19965a47fb/custom_components/device_tracker/life360.py) | Communications module moved to PyPI.
20181130 | [2.3.0](https://github.com/pnbruckner/homeassistant-config/blob/784cbda88eaa3f7010029597afd449d14300a1ea/custom_components/device_tracker/life360.py) | Add optional `home_place` configuration variable.
20181130 | [2.3.1](https://github.com/pnbruckner/homeassistant-config/blob/a568b8e84c3ea20386af8ddd618d878095ee35cb/custom_components/device_tracker/life360.py) | Do not add zone for Life360 Places whose name matches `home_place`.
20190123 | [2.4.0](https://github.com/pnbruckner/homeassistant-config/blob/0f0254c1137255662e1fe53e0d08a8bbf4e2f1b2/custom_components/device_tracker/life360.py) | Add `time_as` option.
20190129 | [2.5.0](https://github.com/pnbruckner/homeassistant-config/blob/93ed07bb61f40dfdc36e970968726ba16a8510a3/custom_components/device_tracker/life360.py) | Add `waring_threshold` and `error_threshold`.
20190208 | [2.6.0](https://github.com/pnbruckner/homeassistant-config/blob/16e275ee7b4ffe8616d3c789abf99420e9323309/custom_components/device_tracker/life360.py) | Add `only_home`, `except_home` and `all` options for `add_zones`, and add `device_tracker.life360_zones_from_places` service. Update life360 package from PyPI to 2.1.0.
20190219 | [2.7.0](https://github.com/pnbruckner/homeassistant-config/blob/eaadca76efe9721d93dc8cee967b1ff819ddc374/custom_components/device_tracker/life360.py) | Treat errors (other than login errors) as warnings during setup and continue. Bump life360 package to 2.2.0.
20190222 | [2.8.0](https://github.com/pnbruckner/homeassistant-config/blob/8b6f2bdbefc2d54632611e212986eb683cf219bc/custom_components/device_tracker/life360.py) | Delay firing events at startup so automations have a chance to get ready.
