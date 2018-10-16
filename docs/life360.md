# Life360
This platform allows you to detect presence using [Life360](http://life360.com/).
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater.

> __NOTE__: Don't forget to also install `life360`.

Alternatively, place a copy of:

[life360.py](../custom_components/life360.py) at `<config>/custom_components/life360.py` and  
[device_tracker/life360.py](../custom_components/device_tracker/life360.py) at `<config>/custom_components/device_tracker/life360.py`

where `<config>` is your Home Assistant configuration directory.

Then add the desired configuration. Here is an example of a typical configuration:
```yaml
device_tracker:
  - platform: life360
    username: !secret life360_username
    password: !secret life360_password
    prefix: life360
    show_as_state: driving, moving, places
    driving_speed: 18
    max_gps_accuracy: 200
    max_update_wait:
      minutes: 45
```
## Configuration variables
- **username**: Your Life360 username.
- **password**: Your Life360 password.
- **prefix** (*Optional*): Default is to name entities `device_tracker.<first_name>_<last_name>`, where `<first_name>` and `<last_name>` are specified by Life360. If a prefix is specified, then entity will be named `device_tracker.<prefix>_<first_name>_<last_name>`. If the member only has a first or last name in Life360, then the underscore that would normally separate the names is left out.
- **show_as_state** (*Optional*): One or more of: `driving`, `moving` and `places`. Default is for Device Tracker Component to determine entity state as normal. When specified these can cause the entity's state to show other statuses according to the States chart below.
- **driving_speed** (*MPH or KPH, depending on HA's unit system configuration, Optional*): The minimum speed at which the device is considered to be "driving" (and which will also set the `driving` attribute to True. See also `Driving` state in chart below.)
- **max_gps_accuracy** (*Meters, Optional*): If specified, and reported GPS accuracy is larger (i.e., *less* accurate), then update is ignored.
- **max_update_wait** (*Optional*): If you specify it, then if Life360 does not provide an update for a member within that maximum time window, the life360 platform will fire an event named `device_tracker.life360_update_overdue` with the entity_id of the corresponding member's device_tracker entity. Once an update does come it will fire an event named `device_tracker.life360_update_restored` with the entity_id of the corresponding member's device_tracker entity and another data item named `wait` that will indicate the amount of time spent waiting for the update. You can use these events in automations to be notified when they occur. See example automations below. 
>Note: If you set the entity to _not_ be tracked via known_devices.yaml then the entity_id will not exist in the state machine. In this case it might be better to exclude the member via the members parameter (see below.)
- **members** (*Optional*): Default is to track all Life360 Members in all Circles. If you'd rather only track a specific set of members, then list them with each member specified as `first,last`, or if they only have one name, then `name`. Names are case insensitive, and extra spaces are ignored (except within a name, like `van Gogh`.) For backwards compatibility, a member with a single name can also be entered as `name,` or `,name`.
- **interval_seconds** (*Optional*): The default is 12. This defines how often the Life360 server will be queried. The resulting device_tracker entities will actually only be updated when the Life360 server provides new location information for each member.
- **filename** (*Optional*): The default is life360.conf. The platform will get an authorization token from the Life360 server using your username and password, and it will save the token in a file in the HA config directory (with limited permissions) so that it can reuse it after restarts (and not have to get a new token every time.) If the token eventually expires, a new one will be acquired as needed.
## States
show_as_state | State | Conditions
-|-|-
`places` | `home` | Place or check-in name (see below) is any form of the word 'home'.
`places` | Place or check-in name | Member is in a Life360 defined "Place" or member has "checked in" via the Life360 app (and name is not any form of the word 'home'.)
N/A | `home` | Device GSP coordinates are located in the HA defined home zone.
N/A | HA zone name | Device GPS coordinates are located in a HA defined zone (other than home.)
`driving` | `Driving` | The Life360 server indicates the device "isDriving", or if `driving_speed` (see above) has been specified and the speed derived from the value provided by the Life360 server is at or above that value.
`moving` | `Moving` | The Life360 server indicates the device is "inTransit".
N/A | `not_home` | None of the above are true.

Order of precedence is from higher to lower.
## Additional attributes
Attribute | Description
-|-
address | Address of current location, or None.
at_loc_since | Date and time when first at current location (in UTC.)
charging | Device is charging (True/False.)
driving | Device movement indicates driving (True/False.)
entity_picture | Member's "avatar" if one is provided by Life360.
last_seen | Date and time when Life360 last updated your location (in UTC.)
moving | Device is moving (True/False.)
raw_speed | "Raw" speed value provided by Life360 server. (Units unknown.)
speed | Estimated speed of device (in MPH or KPH depending on HA's unit system configuration.)
wifi_on | Device WiFi is turned on (True/False.)
## Examples
### Example full configuration
```yaml
device_tracker:
  - platform: life360
    username: !secret life360_username
    password: !secret life360_password
    prefix: life360
    show_as_state: driving, moving, places
    driving_speed: 18
    max_gps_accuracy: 200
    max_update_wait:
      minutes: 45
    members:
      - mike, smith
      - Joe
      - Jones
    interval_seconds: 10
    filename: life360.conf
```
### Example overdue update automations
```yaml
- alias: Life360 Overdue Update
  trigger:
    platform: event
    event_type: device_tracker.life360_update_overdue
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
    event_type: device_tracker.life360_update_restored
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

[Life360 Communications Module Release Notes](life360_lib.md#release-notes)

