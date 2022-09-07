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
ON = "ON"
OFF = "OFF"
STATE = "state"
ENABLED = "enabled"
OUTPUT = "output"
PIN = "pin"
ID = "id"
KIND = "kind"
GPIO = "gpio"
GPIO_MODE = "gpio_mode"
ACTIONS = "actions"
ACTION = "action"
OUTPUT = "output"
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

relay_actions = {ON: "turn_on", OFF: "turn_off", "TOGGLE": "toggle"}

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

# I2C and MCP CONST
ADDRESS = "address"
MCP23017 = "mcp23017"
MCP = "mcp"
MCP_ID = "mcp_id"
INIT_SLEEP = "init_sleep"

# SENSOR CONST
TEMPERATURE = "temperature"
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
DEVICE_CLASS = "device_class"
DallasBusTypes = Literal[DS2482, DALLAS]
FILTERS = "filters"
