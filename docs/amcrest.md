# Amcrest Camera
[__`amcrest/__init__.py`__](../custom_components/amcrest/__init__.py)  
[__`amcrest/binary_sensor.py`__](../custom_components/amcrest/binary_sensor.py)  
[__`amcrest/camera.py`__](../custom_components/amcrest/camera.py)  
[__`amcrest/sensor.py`__](../custom_components/amcrest/sensor.py)  
[__`amcrest/switch.py`__](../custom_components/amcrest/switch.py)  
[__`amcrest/manifest.json`__](../custom_components/amcrest/manifest.json)

>Note: If using HA versions before 0.86, only the first three files are needed, and they go here:
```
custom_components/amcrest.py
custom_components/binary_sensor/amcrest.py
custom_components/camera/amcrest.py
```

These custom components are enhanced versions of the standard Amcrest Camera components. They add services and create a new binary sensor for motion detected. They also add thread locking to avoid simultaneous camera commands that lead to constant errors.
