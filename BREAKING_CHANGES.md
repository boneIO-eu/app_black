# Breaking Changes

## Virtual Energy Sensors Refactoring

### Version: TBD

### Summary
The `virtual_power_usage` and `virtual_volume_flow_rate` fields have been **removed** from the `output` schema. They are replaced by a new top-level `virtual_energy_sensor` section that provides more flexibility, including custom naming and area assignment for Home Assistant's Energy panel.

### Migration Guide

#### Old Configuration (no longer supported):
```yaml
output:
  - id: lamp_living_room
    pin: P8_12
    output_type: light
    virtual_power_usage: 60W  # REMOVED
    
  - id: garden_pump
    pin: P8_14
    output_type: switch
    virtual_volume_flow_rate: 500 L/h  # REMOVED
```

#### New Configuration:
```yaml
output:
  - id: lamp_living_room
    pin: P8_12
    output_type: light
    
  - id: garden_pump
    pin: P8_14
    output_type: switch

virtual_energy_sensor:
  - name: "Lampa Salon - Energia"
    output_id: lamp_living_room
    sensor_type: power
    power_usage: 60W
    area: Salon
    
  - name: "Pompa Ogrodowa - Woda"
    output_id: garden_pump
    sensor_type: water
    flow_rate: 500 L/h
    area: Ogród
```

### New Features

1. **Custom Naming**: Each virtual sensor can have a custom `name` that will be displayed in Home Assistant. This is especially useful for the Energy panel where sensors from different areas might have the same base name.

2. **Area Assignment**: The optional `area` field allows grouping sensors by room/area in Home Assistant.

3. **Separate Configuration**: Virtual energy sensors are now configured independently from outputs, making the configuration cleaner and more flexible.

### Schema Details

```yaml
virtual_energy_sensor:
  - id: optional_unique_id        # Optional, auto-generated if not provided
    name: "Custom Sensor Name"    # Required - displayed in HA
    output_id: output_entity_id   # Required - must match an existing output id
    sensor_type: power            # Required - "power" or "water"
    power_usage: 60W              # Required if sensor_type is "power"
    flow_rate: 500 L/h            # Required if sensor_type is "water"
    area: Room Name               # Optional - HA area assignment
```

### Affected Files
- `boneio/schema/schema.yaml` - Schema changes
- `boneio/components/output/basic.py` - Removed old VirtualEnergySensor class
- `boneio/components/sensor/virtual_energy.py` - New VirtualEnergySensor component
- `boneio/core/manager/sensors.py` - New configure_virtual_energy_sensors method
- `boneio/core/manager/outputs.py` - Removed virtual sensor HA autodiscovery
- `boneio/integration/homeassistant.py` - New ha_virtual_energy_sensor_availabilty_message function
