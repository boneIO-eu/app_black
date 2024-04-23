# from typing import Literal
try:
    from Adafruit_BBIO.GPIO import BOTH, FALLING, HIGH, LOW, RISING
except ModuleNotFoundError:
    HIGH = "high"
    LOW = "low"
    BOTH = "both"
    FALLING = "falling"
    RISING = "rising"
    pass
from typing_extensions import Literal

BONEIO = "boneIO"
NONE = "none"

# MISCELLANEOUS CONSTS
RELAY = "relay"
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
SWITCH = "switch"
LIGHT = "light"
BUTTON = "button"
CONFIG_PIN = "/usr/bin/config-pin"
UPDATE_INTERVAL = "update_interval"
ADC = "adc"
IP = "ip"
MASK = "mask"
MAC = "mac"
NONE = "none"
MODBUS = "modbus"
UART = "uart"
RX = "rx"
TX = "tx"
RESTORE_STATE = "restore_state"
MODEL = "model"
UARTS = {
    "uart1": {ID: "/dev/ttyS1", TX: "P9.24", RX: "P9.26"},
    "uart2": {ID: "/dev/ttyS2", TX: "P9.21", RX: "P9.22"},
    "uart3": {ID: "/dev/ttyS3", TX: "P9.42", RX: None},
    "uart4": {ID: "/dev/ttyS4", TX: "P9.13", RX: "P9.11"},
    "uart5": {ID: "/dev/ttyS5", TX: "P8.37", RX: "P8.38"},
}

relay_actions = {ON: "async_turn_on", OFF: "async_turn_off", TOGGLE: "async_toggle"}

# HA CONSTS
HOMEASSISTANT = "homeassistant"
HA_DISCOVERY = "ha_discovery"
OUTPUT_TYPE = "output_type"
SHOW_HA = "show_in_ha"

# OLED CONST
OLED = "oled"
FONTS = "fonts"
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

# SENSOR CONST
TEMPERATURE = "temperature"
EVENT_ENTITY = "event"
SENSOR = "sensor"
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
ClickTypes = Literal[SINGLE, DOUBLE, LONG, PRESSED, RELEASED]
OledDataTypes = Literal[UPTIME, NETWORK, CPU, DISK, MEMORY, SWAP, OUTPUT]
Gpio_States = Literal[HIGH, LOW]
Gpio_Edges = Literal[BOTH, FALLING]
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
}

INA219 = "ina219"
