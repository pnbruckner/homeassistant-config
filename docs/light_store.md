# Light Store
Save and restore lights, switches and/or groups of these.

The state of the entities, including important attributes (such as brightness and color attributes) will be saved to the State Machine. When restored the information will be deleted from the State Machine.
## Installation
See [Installing and Updating](custom_updater.md) to use Custom Updater. The name of this `"element"` is `"light_store"`.

Alternatively, place a copy of:

[python_scripts/light_store.py](../python_scripts/light_store.py) at `<config>/python_scripts/light_store.py`

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

Then add the following to your configuration:
```yaml
python_script:
```
See [Python Scripts](https://www.home-assistant.io/components/python_script/) for more details.
## Script variables
- **store_name** (*Optional*): The “domain” name to use for the entities created in the State Machine to hold the saved states and attributes. The default is `light_store`.
- **entity_id** (*Optional*): The entity_id(s) of the entities to save/restore. (Currently only entities of the switch, light or group domains are supported. Groups will be expanded recursively into the individual entities they contain.) Can be a single entity_id, a list of entity_id’s, or a string containing a comma separated list of entity_id’s. When saving, the default is to save all existing switch and light entities. When restoring, the default is to restore all previously saved entities.
- **operation** (*Optional*): If specified must be `save` or `restore`. The default is `save`.
- **overwrite** (*Optional*): Only applies to saving. If True will overwrite any previously saved states. If False, will only save current states if they have not already been saved, otherwise will skip saving. The default is True.
- **transition** (*Optional*): Only applies to restoring. If specified sets the number of seconds the lights will take to transition back to the previous state. The default is `1`.
## Operation
When saving, the script will create an entity in the State Machine named `<store_name>.<domain>_<object_id>` for each saved entity (where `<entity_id>` = `<domain>.<object_id>`.) The state will be the state of the entity, and if the entity is a light then appropriate attributes will also be saved (see below.)

So, e.g., if store_name is `light_store`, and `switch.abc` and `light.def` are saved, and `switch.abc` is currently `off`, and `light.def` is currently `on` with a brightness of 128, the following (temporary) entities would be created in the State Machine:

`light_store.switch_abc`, state: `off`  
`light_store.light_def`, state: `on`, attributes: `brightness: 128`
## Light attributes
When saved, if a light entity has any of the following attributes they will be saved: brightness, effect, and one of the following (in order of precedence): white_value, color_temp, hs_color.

Note that when turning on a light, if profile, color_name, rgb_color or xy_color are used, they will get converted to hs_color and that is what will be used. And when the state of the light is updated, although only hs_color is used internally, in addition to hs_color the light component will also add equivalent rgb_color and xy_color attributes to the light.

For color temperature, if kelvin is used when turning on a light it will get converted to color_temp, which is what will be added as an attribute.

The method of choosing which attribute to save and restore was based on the above, as well as the fact that some light platforms seem to support both hs_color and color_temp, although they don’t report the correct hs_color. Note that color_temp can always be converted to an equivalent hs_color, but the reverse is not true (since color temperature is a small subset of all colors.)
## Example usage
```yaml
script:
  lights_on:
    alias: Turn on a given selection of lights, saving current state
    sequence:
      - service: python_script.light_store
        data:
          store_name: flash_store
          entity_id:
            - switch.kitchen_light
            - light.family_room_lamp
            - group.upstairs_lights
      - service: homeassistant.turn_on
      ...

  restore_lights:
    alias: Restore saved lights to the way they were
    sequence:
      - service: python_script.light_store
        data:
          store_name: flash_store
          operation: restore
          transition: 10
```
## Caveats
If you have any light groups (i.e., an entity of the light domain that is actually a group of other lights), then you should not use the default for entity_id (when saving.) Rather, you should specify the list of individual light entity_id’s, or the light group, but not both. Unfortunately, a python_script cannot tell the difference between a light entity that is an actual light and a light entity that is a group of other lights. If both are saved & later restored, the result will not be what you want.
## Release Notes
Date | Version | Notes
-|:-:|-
20181002 | [1.0.0](https://github.com/pnbruckner/homeassistant-config/blob/62e517921e9f48625dbc7c7e3b9d6b4e665749f4/python_scripts/light_store.py) | Initial support for Custom Updater.
20190114 | [1.1.0](https://github.com/pnbruckner/homeassistant-config/blob/c405e9ed1f37a67918d5b43152307aa47e75c094/python_scripts/light_store.py) | Save and restore light effect attribute.
20190204 | [1.2.0](https://github.com/pnbruckner/homeassistant-config/blob/aa04afe8e32777414abb5a9265c00a90efa5d67c/python_scripts/light_store.py) | Add optional `overwrite` parameter.
20191016 | [1.3.0](https://github.com/pnbruckner/homeassistant-config/blob/aa04afe8e32777414abb5a9265c00a90efa5d67c/python_scripts/light_store.py) | Add optional `transition` parameter.