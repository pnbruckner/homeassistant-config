# Composite Device Tracker
This platform creates a composite device tracker from one or more other device trackers. It will update whenever one of the watched entities updates, taking the GPS and last_seen/last_updated (and possibly battery) data from the changing entity. The result can be a more accurate and up-to-date device tracker if the "input" device tracker's update irregularly.
## Installation
See [Installing and Updating](https://github.com/pnbruckner/homeassistant-config/blob/master/docs/custom_updater.md) to use Custom Updater.

Alternatively, place a copy of:

[device_tracker/composite.py](https://github.com/pnbruckner/homeassistant-config/blob/master/custom_components/device_tracker/composite.py) at `<config>/custom_components/device_tracker/composite.py`

where `<config>` is your Home Assistant configuration directory.

Then add the desired configuration. Here is an example of a typical configuration:
```yaml
device_tracker:
  - platform: composite
    name: me
    entity_id:
      - device_tracker.platform1_me
      - device_tracker.platform2_me
```
## Configuration variables
- **name**: Object ID of composite device: `device_tracker.NAME`
- **entity_id**: Watched device tracker devices.
## Watched device requirements
Watched devices must have, at a minimum, the following attributes: `latitude`, `longitude` and `gps_accuracy`. If they don't they will not be used.

If a watched device has a `last_seen` attribute, that will be used in the composite device. If not, then `last_updated` from the entity's state will be used instead.

If a watched device has a `battery` attribute, that will be used to update the composite device.
## known_devices.yaml
The watched devices, and the composite device, should all have `track` set to `true`. It's recommended, as well, to set `hide_if_away` to `true` for the watched devices (but leave it set to `false` for the composite device.) This way the map will only show the composite device (when it is out of the home zone.)
## Release Notes
Date | Version | Notes
-|:-:|-
20180907 | [1.0.0](https://github.com/pnbruckner/homeassistant-config/blob/d767bcce0fdff0c9298dc7a010d27af88817eac2/custom_components/device_tracker/composite.py) | Initial support for Custom Updater.
20180920 | [1.0.1](https://github.com/pnbruckner/homeassistant-config/blob/959a691afb5e2b98e946591b9ff58291f104a74a/custom_components/device_tracker/composite.py) | Add thread locking to protect against multiple entities updating too close together.
