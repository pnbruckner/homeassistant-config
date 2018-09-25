# Installing and Updating Custom Components
The custom components in this repo can be installed manually or by using [Custom Updater](https://github.com/custom-components/custom_updater).
## Manual Installation
See instructions provided on component's doc page.
## Custom Updater
[custom_components.json](../custom_components.json) provides the details Custom Updater needs. See [Custom Updater Installation](https://github.com/custom-components/custom_updater#installation) to install it.
### Setup
Add the following to your configuration:
```
custom_updater:
  component_urls:
    - https://raw.githubusercontent.com/pnbruckner/homeassistant-config/master/custom_components.json
```
### Installing
To install one of these custom components for the first time, use the `custom_updater.install` service with appropriate service data, such as:
```
{
  "element": "sensor.illuminance"
}
```
### Updating
Once components are installed they can easily be updated using the Tracker card. If you're not using the Tracker card then you can use the `custom_updater.update_all` service. Or a single component can be updated using the `custom_updater.upgrade_single_component` service with appropriate service date, such as:
```
{
  "component": "sensor.illuminance"
}
```
> __NOTE__: If you already have one or more of these custom components from before version numbers were added then they will not show up (by default) on the Tracker card or in `sensor.custom_component_tracker`, and cannot be updated via the `custom_updater.update_all` service. In this case use the `custom_upgrader.upgrade_single_component` service as mentioned above.
