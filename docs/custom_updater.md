# Installing & Updating Custom Components & Python Scripts
The custom components and Python scripts in this repo can be installed manually or by using [Custom Updater](https://github.com/custom-components/custom_updater).
## Manual Installation
See instructions provided on custom component's or Python script's doc page.
## Custom Updater
[custom_components.json](../custom_components.json) and [python_scripts.json](../python_scripts.json) provide the details Custom Updater needs. See [Custom Updater Installation](https://github.com/custom-components/custom_updater/wiki/Installation) to install it.
### Setup
Add the following to your configuration:
```
custom_updater:
  track:
    - components
    - python_scripts
  component_urls:
    - https://raw.githubusercontent.com/pnbruckner/homeassistant-config/master/custom_components.json
  python_script_urls
    - https://raw.githubusercontent.com/pnbruckner/homeassistant-config/master/python_scripts.json
```
### Installing
To install one of these custom components or Python scripts for the first time, use the [`custom_updater.install`](https://github.com/custom-components/custom_updater/wiki/Services#install-element-cardcomponentpython_script) service with appropriate service data, such as:
```
{
  "element": "sensor.illuminance"
}
```
### Updating
Once components/scripts are installed they can easily be updated using the Tracker card. If you're not using the Tracker card then you can use the [`custom_updater.update_all`](https://github.com/custom-components/custom_updater/wiki/Services#update-all) service.

> __NOTE__: If you already have one or more of these custom components or Python scripts from before version numbers were added then they cannot be updated via the `custom_updater.update_all` service. In this case you will need to install them following the instructions above (as if they had not yet been installed. There should be no need to remove them first.)
