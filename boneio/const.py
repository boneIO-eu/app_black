
from typing import Literal

BONEIO = "boneio"
NONE = "none"

# MISCELLANEOUS CONSTS
LED = "led"
ON = "ON"
OFF = "OFF"
TOGGLE = "TOGGLE"
STATE = "state"
BRIGHTNESS = "brightness"
SET_BRIGHTNESS = "set_brightness"
ENABLED = "enabled"
OUTPUT = "output"
PIN = "pin"
ID = "id"
KIND = "kind"
GPIO = "gpio"
PCA = "pca"
GPIO_MODE = "gpio_mode"
ACTIONS = "actions"
ACTION = "action"
OUTPUT_OVER_MQTT = "output_over_mqtt"
COVER_OVER_MQTT = "cover_over_mqtt"
REMOTE_OUTPUT = "remote_output"
REMOTE_COVER = "remote_cover"
SWITCH = "switch"
LIGHT = "light"
BUTTON = "button"
VALVE = "valve"
CONFIG_PIN = "/usr/bin/config-pin"
UPDATE_INTERVAL = "update_interval"
ADC = "adc"
IP = "ip"
MASK = "mask"
MAC = "mac"
NONE = "none"
MODBUS = "modbus"
MODBUS_SENSOR  = "modbus_sensor"
MODBUS_DEVICE = "modbus_device"
UART = "uart"
RX = "rx"
TX = "tx"
RESTORE_STATE = "restore_state"
MODEL = "model"
UARTS = {
    "uart1": {ID: "/dev/ttyS1", TX: "P9.24", RX: "P9.26"},
    # "uart2": {ID: "/dev/ttyS2", TX: "P9.21", RX: "P9.22"},
    # "uart3": {ID: "/dev/ttyS3", TX: "P9.42", RX: None},
    "uart4": {ID: "/dev/ttyS4", TX: "P9.13", RX: "P9.11"},
    # "uart5": {ID: "/dev/ttyS5", TX: "P8.37", RX: "P8.38"},
}

output_actions = {
    ON: "async_turn_on",
    OFF: "async_turn_off",
    TOGGLE: "async_toggle",
}

# HA CONSTS
HOMEASSISTANT = "homeassistant"
HA_DISCOVERY = "ha_discovery"
OUTPUT_TYPE = "output_type"
SHOW_HA = "show_in_ha"

# OLED CONST
OLED = "oled"
OLED_PIN = "P9_41"
GIGABYTE = 1073741824
MEGABYTE = 1048576
WIDTH = 128
UPTIME = "uptime"
NETWORK = "network"
CPU = "cpu"
DISK = "disk"
MEMORY = "memory"
SWAP = "swap"
WHITE = "white"

# INPUT CONST
INPUT = "input"
SINGLE = "single"
DOUBLE = "double"
TRIPLE = "triple"
LONG = "long"
PRESSED = "pressed"
RELEASED = "released"


# MQTT CONST
PAHO = "paho.mqtt.client"
PYMODBUS = "pymodbus"
MQTT = "mqtt"
HOST = "host"
USERNAME = "username"
PASSWORD = "password"
PORT = "port"
ONLINE = "online"
OFFLINE = "offline"
TOPIC = "topic"
TOPIC_PREFIX = "topic_prefix"

# I2C, PCA and MCP CONST
ADDRESS = "address"
MCP23017 = "mcp23017"
PCF8575 = "pcf8575"
PCA9685 = "pca9685"
MCP = "mcp"
PCF = "pcf"
MCP_ID = "mcp_id"
PCA_ID = "pca_id"
PCF_ID = "pcf_id"
INIT_SLEEP = "init_sleep"
OUTPUT_GROUP = "output_group"
GROUP = "group"

# SENSOR CONST
TEMPERATURE = "temperature"
EVENT_ENTITY = "event"
SENSOR = "sensor"
TEXT_SENSOR = "text_sensor"
SELECT = "select"
CLIMATE = "climate"
NUMERIC = "number"
BINARY_SENSOR = "binary_sensor"
LM75 = "lm75"
MCP_TEMP_9808 = "mcp9808"
INPUT_SENSOR = "inputsensor"
DS2482 = "ds2482"
DALLAS = "dallas"
ONEWIRE = "onewire"

BASE = "base"
LENGTH = "length"
REGISTERS = "registers"

COVER = "cover"
IDLE = "idle"
OPENING = "opening"
CLOSING = "closing"
CLOSED = "closed"
OPEN = "open"
CLOSE = "close"
STOP = "stop"

# TYPING
# Basic click types + sequence aliases
ClickTypes = Literal[
    "single", "double", "triple", "long", "pressed", "released",
    # Sequence aliases
    "double_then_long",   # double click followed by long press
    "single_then_long",   # single click followed by long press
    "double_then_single", # double click followed by single click
]

# Sequence definitions for MultiClickDetector
CLICK_SEQUENCES: dict[tuple[str, str], str] = {
    ("double", "long"): "double_then_long",
    ("single", "long"): "single_then_long",
    ("double", "single"): "double_then_single",
}

# Default window for sequence detection (ms)
DEFAULT_SEQUENCE_WINDOW_MS = 500
BinaryStateTypes = Literal["pressed", "released"]
OledDataTypes = Literal[UPTIME, NETWORK, CPU, DISK, MEMORY, SWAP, OUTPUT]
InputTypes = Literal[INPUT, INPUT_SENSOR]
ExpanderTypes = Literal[MCP23017, PCA9685, PCF8575]
DEVICE_CLASS = "device_class"
DallasBusTypes = Literal[DS2482, DALLAS]
FILTERS = "filters"

cover_actions = {
    "OPEN": "open",
    "CLOSE": "close",
    "TOGGLE": "toggle",
    "STOP": "stop",
    "TOGGLE_OPEN": "toggle_open",
    "TOGGLE_CLOSE": "toggle_close",
    "TILT": "set_tilt",
    'TILT_OPEN': 'tilt_open',
    'TILT_CLOSE': 'tilt_close',
}

INA219 = "ina219"
VIRTUAL_ENERGY_SENSOR = "virtual_energy_sensor"
PINS = {
    # Based on boneio/boards/0.8/input.yaml
    "P8_37": {"chip": 1, "line": 14},
    "P8_38": {"chip": 1, "line": 15},
    "P8_39": {"chip": 1, "line": 12},
    "P8_40": {"chip": 1, "line": 13},
    "P8_41": {"chip": 1, "line": 10},
    "P8_42": {"chip": 1, "line": 11},
    "P8_43": {"chip": 1, "line": 8},
    "P8_44": {"chip": 1, "line": 9},
    "P8_45": {"chip": 1, "line": 6},
    "P8_46": {"chip": 1, "line": 7},
    "P9_42": {"chip": 3, "line": 7},
    "P9_31": {"chip": 2, "line": 14},
    "P9_30": {"chip": 2, "line": 16},
    "P9_29": {"chip": 2, "line": 15},
    "P9_28": {"chip": 2, "line": 17},
    "P9_27": {"chip": 2, "line": 19},
    "P9_25": {"chip": 2, "line": 21},
    "P9_23": {"chip": 0, "line": 17},
    "P9_22": {"chip": 3, "line": 2},
    "P9_21": {"chip": 3, "line": 3},
    "P9_18": {"chip": 3, "line": 4},
    "P9_17": {"chip": 3, "line": 5},
    "P9_16": {"chip": 0, "line": 19},
    "P9_15": {"chip": 0, "line": 16},
    "P9_14": {"chip": 0, "line": 18},
    "P8_7": {"chip": 1, "line": 2},
    "P8_8": {"chip": 1, "line": 3},
    "P8_9": {"chip": 1, "line": 5},
    "P8_36": {"chip": 1, "line": 16},
    "P8_35": {"chip": 3, "line": 8},
    "P8_34": {"chip": 1, "line": 17},
    "P8_33": {"chip": 3, "line": 9},
    "P8_32": {"chip": 3, "line": 11},
    "P8_31": {"chip": 3, "line": 10},
    "P8_30": {"chip": 1, "line": 25},
    "P8_29": {"chip": 1, "line": 23},
    "P8_28": {"chip": 1, "line": 24},
    "P8_27": {"chip": 1, "line": 22},
    "P8_26": {"chip": 0, "line": 29},
    "P8_19": {"chip": 3, "line": 22},
    "P8_18": {"chip": 1, "line": 1},
    "P8_17": {"chip": 3, "line": 27},
    "P8_16": {"chip": 0, "line": 14},
    "P8_15": {"chip": 0, "line": 15},
    "P8_14": {"chip": 3, "line": 26},
    "P8_13": {"chip": 3, "line": 23},
    "P8_12": {"chip": 0, "line": 12},
    "P8_11": {"chip": 0, "line": 13},
    "P8_10": {"chip": 1, "line": 4},
    "P9_41": {"chip": 3, "line": 20},
}
NAME = "name"
