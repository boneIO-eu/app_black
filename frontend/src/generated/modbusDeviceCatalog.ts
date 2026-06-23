// Auto-generated — do NOT edit manually.
// Run: node scripts/generate-modbus-catalog.cjs
// Source: boneio/modbus/devices/**/*.json

export interface ModbusDeviceInfo {
  modelKey: string;
  displayName: string;
  manufacturer: string;
  description: string;
  category: string;
  defaultAddress: number;
  defaultUpdateInterval: string;
  hasSetBase: boolean;
}

export const MODBUS_DEVICE_CATALOG: Record<string, ModbusDeviceInfo> = {
  "dts1964_3f": {
    "modelKey": "dts1964_3f",
    "displayName": "DTS1964 3-phase meter",
    "manufacturer": "DTS",
    "description": "DTS1964 3-phase power & energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "le-03mw": {
    "modelKey": "le-03mw",
    "displayName": "LE-03MW",
    "manufacturer": "F&F",
    "description": "F&F LE-03MW 3-phase energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "le-03mwct": {
    "modelKey": "le-03mwct",
    "displayName": "LE-03MW CT",
    "manufacturer": "F&F",
    "description": "F&F LE-03MW CT 3-phase energy meter with current transformers",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "orno-or-we-517": {
    "modelKey": "orno-or-we-517",
    "displayName": "OR-WE-517",
    "manufacturer": "ORNO",
    "description": "ORNO OR-WE-517 3-phase energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "sdm120": {
    "modelKey": "sdm120",
    "displayName": "SDM120",
    "manufacturer": "Eastron",
    "description": "Eastron SDM120 1-phase energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "sdm630": {
    "modelKey": "sdm630",
    "displayName": "SDM630",
    "manufacturer": "Eastron",
    "description": "Eastron SDM630 3-phase energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "socomec_e03": {
    "modelKey": "socomec_e03",
    "displayName": "Socomec Countis E03",
    "manufacturer": "Socomec",
    "description": "Socomec Countis E03 energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "socomec_e23": {
    "modelKey": "socomec_e23",
    "displayName": "Socomec Countis E23",
    "manufacturer": "Socomec",
    "description": "Socomec Countis E23 energy meter",
    "category": "energy_meters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "eht-topventil-plus": {
    "modelKey": "eht-topventil-plus",
    "displayName": "EHT Topventil Plus",
    "manufacturer": "EHT",
    "description": "EHT Topventil Plus ventilation system",
    "category": "hvac",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "fujitsu-ac": {
    "modelKey": "fujitsu-ac",
    "displayName": "Fujitsu AC",
    "manufacturer": "Fujitsu",
    "description": "Fujitsu Air Conditioning control interface",
    "category": "hvac",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "thessla": {
    "modelKey": "thessla",
    "displayName": "Thessla Green",
    "manufacturer": "Thessla Green",
    "description": "Thessla Green heat recovery ventilation unit",
    "category": "hvac",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "ventclear": {
    "modelKey": "ventclear",
    "displayName": "Ventclear",
    "manufacturer": "Ventclear",
    "description": "Ventclear ventilation system",
    "category": "hvac",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "wanas415": {
    "modelKey": "wanas415",
    "displayName": "Wanas 415",
    "manufacturer": "Wanas",
    "description": "Wanas heat recovery ventilation unit (rekuperator)",
    "category": "hvac",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "sofar": {
    "modelKey": "sofar",
    "displayName": "Sofar Solar Inverter",
    "manufacturer": "Sofar",
    "description": "Sofar Solar PV Inverter",
    "category": "inverters",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "esp32_relay_x4_modbus": {
    "modelKey": "esp32_relay_x4_modbus",
    "displayName": "ESP32 Relay x4 Modbus",
    "manufacturer": "boneIO",
    "description": "boneIO ESP32 4-channel Modbus relay board",
    "category": "other",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": false
  },
  "n4dsc08": {
    "modelKey": "n4dsc08",
    "displayName": "N4DSC08 Relay",
    "manufacturer": "N4",
    "description": "N4DSC08 8-channel Modbus relay board",
    "category": "other",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": true
  },
  "r4dcb08": {
    "modelKey": "r4dcb08",
    "displayName": "R4DCB08 Relay",
    "manufacturer": "R4D",
    "description": "R4DCB08 8-channel Modbus relay board",
    "category": "other",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": true
  },
  "boneio-edge-temp": {
    "modelKey": "boneio-edge-temp",
    "displayName": "boneIO Edge Temp",
    "manufacturer": "boneIO",
    "description": "boneIO temperature sensor extension board",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "cwt": {
    "modelKey": "cwt",
    "displayName": "CWT Soil Sensor",
    "manufacturer": "CWT",
    "description": "CWT Soil moisture, temperature and EC sensor",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "30s",
    "hasSetBase": true
  },
  "dyp-a12-ultrasonic": {
    "modelKey": "dyp-a12-ultrasonic",
    "displayName": "DYP-A12",
    "manufacturer": "DYP",
    "description": "DYP-A12 Ultrasonic distance/level sensor",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "gdfs": {
    "modelKey": "gdfs",
    "displayName": "GDFS Sensor",
    "manufacturer": "GD",
    "description": "GD series flow sensor (GDFS)",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "gdfx": {
    "modelKey": "gdfx",
    "displayName": "GDFX Sensor",
    "manufacturer": "GD",
    "description": "GD series flow sensor (GDFX)",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "liquid-sensor": {
    "modelKey": "liquid-sensor",
    "displayName": "Liquid Level Sensor",
    "manufacturer": "Generic",
    "description": "Generic Modbus liquid level sensor",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "pt100": {
    "modelKey": "pt100",
    "displayName": "PT100 Modbus",
    "manufacturer": "Generic",
    "description": "PT100 RTD temperature transmitter to Modbus",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": false
  },
  "sht20": {
    "modelKey": "sht20",
    "displayName": "SHT20 Sensor",
    "manufacturer": "Sensirion",
    "description": "SHT20 Temperature & humidity sensor",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  },
  "sht30": {
    "modelKey": "sht30",
    "displayName": "SHT30 Sensor",
    "manufacturer": "Sensirion",
    "description": "SHT30 Temperature & humidity sensor",
    "category": "sensors",
    "defaultAddress": 1,
    "defaultUpdateInterval": "10s",
    "hasSetBase": true
  }
} as const;

export const MODBUS_CATEGORIES = [...new Set(Object.values(MODBUS_DEVICE_CATALOG).map(d => d.category))].sort();
