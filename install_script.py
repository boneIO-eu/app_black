#!/usr/bin/env python3
import subprocess
import shlex
import sys
import itertools
from collections import namedtuple
from shutil import copyfile
import os
import logging
import yaml
import re


_LOGGER = logging.getLogger(__name__)


def is_root():
    return True if os.geteuid() == 0 else False


def flatten(data):
    return list(itertools.chain.from_iterable(data))


def run_command(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res


Response = namedtuple("Response", "returncode value")


class Whiptail:
    def __init__(self, title="", backtitle="", height=20, width=60, auto_exit=True):
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width
        self.auto_exit = auto_exit

    def run(self, control, msg, extra=(), exit_on=(1, 255)):
        cmd = [
            "whiptail",
            "--title",
            self.title,
            "--backtitle",
            self.backtitle,
            "--" + control,
            msg,
            str(self.height),
            str(self.width),
        ]
        cmd += list(extra)
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if self.auto_exit and p.returncode in exit_on:
            print("User cancelled operation.")
            sys.exit(p.returncode)
        return Response(p.returncode, str(err, "utf-8", "ignore"))

    def prompt(self, msg, default="", password=False):
        control = "passwordbox" if password else "inputbox"
        return self.run(control, msg, [default]).value

    def confirm(self, msg, default="yes"):
        defaultno = "--defaultno" if default == "no" else ""
        return self.run("yesno", msg, [defaultno], [255]).returncode == 0

    def alert(self, msg):
        self.run("msgbox", msg)

    def view_file(self, path):
        self.run("textbox", path, ["--scrolltext"])

    def calc_height(self, msg):
        height_offset = 8 if msg else 7
        return [str(self.height - height_offset)]

    def menu(self, msg="", items=(), prefix=" - "):
        if isinstance(items[0], str):
            items = [(i, "") for i in items]
        else:
            items = [(k, prefix + v) for k, v in items]
        extra = self.calc_height(msg) + flatten(items)
        return self.run("menu", msg, extra).value

    def showlist(self, control, msg, items, prefix):
        if isinstance(items[0], str):
            items = [(tag, "", "OFF") for tag in items]
        else:
            items = [(tag, prefix + value, state) for tag, value, state in items]
        extra = self.calc_height(msg) + flatten(items)
        return shlex.split(self.run(control, msg, extra).value)

    def show_tag_only_list(self, control, msg, items, prefix):
        if isinstance(items[0], str):
            items = [(tag, "", "OFF") for tag in items]
        else:
            items = [(tag, "", state) for tag, value, state in items]
        extra = self.calc_height(msg) + flatten(items)
        return shlex.split(self.run(control, msg, extra).value)

    def radiolist(self, msg="", items=(), prefix=" - "):
        return self.showlist("radiolist", msg, items, prefix)[0]

    def node_radiolist(self, msg="", items=(), prefix=""):
        return self.show_tag_only_list("radiolist", msg, items, prefix)[0]

    def checklist(self, msg="", items=(), prefix=" - "):
        return self.showlist("checklist", msg, items, prefix)


def read_os_release():
    return {
        k.lower(): v.strip("'\"")
        for k, v in (
            line.strip().split("=", 1)
            for line in open("/etc/os-release").read().strip().split("\n")
        )
    }


def check_os():
    if os.path.isfile("/etc/debian_version"):
        os_data = read_os_release()
        if os_data["ID"] == "debian" and int(os_data["VERSION_ID"] == 10):
            return True
        _LOGGER.error("Wrong OS type.")
        return False


def check_arch():
    uname = os.uname()
    if uname.machine == "armv7l":
        return True
    _LOGGER.error(
        "This architecture is not supported. Is it Beaglebone? %s", uname.machine
    )
    return False


class BoneIODumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
    def represent_stringify(self, value):
        # if "!include" in value:
        #     return self.represent_data(value)
        return self.represent_scalar(tag="tag:yaml.org,2002:str", value=str(value))

    def represent_none(self, v):
        return self.represent_scalar(tag="tag:yaml.org,2002:null", value="")


# class Include(yaml.YAMLObject):
#     # yaml_constructor = yaml.RoundTripConstructor
#     # yaml_representer = yaml.RoundTripRepresenter
#     yaml_tag = "!include"

#     def __init__(self, file):
#         self.file = file

#     @classmethod
#     def from_yaml(cls, loader, node):
#         print("Ty nic nie robisz")
#         return cls(loader.construct_scalar(node))

#     @classmethod
#     def to_yaml(cls, dumper, data):

#         # if isinstance(data.file, yaml.scalarstring.ScalarString):
#         #     style = data.file.style  # ruamel.yaml>0.15.8
#         # else:
#         #     style = None
#         print("data", data.file, cls.yaml_tag)
#         return dumper.represent_scalar(cls.yaml_tag, data.file)


def _include_yaml(loader, node):
    """Load another YAML file and embeds it using the !include tag.
    Example:
        device_tracker: !include device_tracker.yaml
    """
    fname = os.path.join(os.path.dirname(loader.name), node.value)
    try:
        return _add_reference(load_yaml(fname, loader.secrets), loader, node)
    except FileNotFoundError as exc:
        raise HomeAssistantError(
            f"{node.start_mark}: Unable to read file {fname}."
        ) from exc


yaml.SafeDumper.add_representer("!include", _include_yaml)

# yaml.add_representer(Include, Include.to_yaml)
BoneIODumper.add_representer(str, BoneIODumper.represent_stringify)

BoneIODumper.add_representer(type(None), BoneIODumper.represent_none)

ON = "ON"
OFF = "OFF"
if __name__ == "__main__":
    # if is_root():
    #     _LOGGER.error("Can't run this script as root!")
    #     sys.exit(1)
    # if not check_os() or not check_arch():
    #     sys.exit(1)
    run_command(cmd=["sudo", "true"])
    whiptail = Whiptail(
        title="BoneIO", backtitle="Installation script", height=39, width=120
    )
    maindir = whiptail.prompt(
        msg="Where would you like to install package? Last part of directory will be created for you",
        default="/home/debian/boneio",
    )
    # try:
    #     os.mkdir(maindir)
    # except FileNotFoundError:
    #     _LOGGER.error("No such path")
    #     sys.exit(1)
    # run_command(
    #     cmd=shlex.split(
    #         "sudo apt-get install libopenjp2-7-dev libatlas-base-dev python3-venv python3-ruamel.yaml"
    #     )
    # )
    # run_command(cmd=shlex.split(f"python3 -m venv {maindir}/venv"))
    # run_command(cmd=shlex.split(f"{maindir}/venv/bin/pip3 install --upgrade boneio"))
    _configure = whiptail.confirm(
        msg="Would you like to give some basic mqtt credentials so we can configure boneio for you?"
    )
    if _configure:
        _boneio_name = whiptail.prompt("Name for this BoneIO", default="myboneio")
        _mqtt_hostname = whiptail.prompt("Type mqtt hostname", default="localhost")
        _mqtt_username = whiptail.prompt("Type mqtt username", default="mqtt")
        _mqtt_password = whiptail.prompt("Type mqtt password", password=True)
        _ha_discovery = whiptail.confirm(msg="Enable HA discovery", default="yes")
        _enabled_modules = whiptail.checklist(
            "Modules chooser",
            items=[
                ("OLED", "Turn on OLED", ON),
                (
                    "Input",
                    "Enable inputs (better to edit them anyway according to your needs later)",
                    ON,
                ),
                ("ADC", "Enable ADC input sensors", OFF),
                ("RB32", "Enable relay board 32x5A", ON),
                (
                    "LM75_RB32",
                    "Enable temperature on Relay board 32x5A",
                    ON,
                ),
                ("RB24", "Enable relay board 24x16A", OFF),
                (
                    "LM75_RB24",
                    "Enable temperature on Relay board 24x16A",
                    OFF,
                ),
            ],
        )
        mqtt_part = {
            "host": _mqtt_hostname,
            "topic_prefix": _boneio_name,
            "ha_discovery": {"enabled": _ha_discovery},
            "username": _mqtt_username,
            "password": _mqtt_password,
        }
        output = {"mqtt": mqtt_part}
        exampled_dir = (
            f"{maindir}/venv/lib/python3.7/site-packages/boneio/example_config/"
        )
        if "OLED" in _enabled_modules:
            output["oled"] = None
        if "RB32" and "RB24" in _enabled_modules:
            ##TODO Add RB24 in future
            copyfile(f"{exampled_dir}")
            output["mcp23017"] = (
                [{"id": "mcp1", "address": 32}, {"id": "mcp2", "address": 33}],
            )
        elif "RB32" in _enabled_modules:
            output["mcp23017"] = [
                {"id": "mcp1", "address": 32},
                {"id": "mcp2", "address": 33},
            ]
        if "LM75_RB32" in _enabled_modules:
            output["lm75"] = {"id": "temp", "address": 72}
        if "Input" in _enabled_modules:
            # TODO copy input file
            output["input"] = "!include input.yaml"
        if "RB32" in _enabled_modules:
            output["output"] = "!include output32x5A.yaml"
        if "ADC" in _enabled_modules:
            output["adc"] = "!include adc.yaml"

        print("ma", maindir)

        with open(f"{maindir}/config.yaml", "w") as file:
            result = re.sub(
                r"(.*): (')(!include.*.yaml)(')",
                "\\1: \\3",
                yaml.dump(
                    output,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    Dumper=BoneIODumper,
                ),
                0,
            )
            file.write(result)
    _configure = whiptail.confirm(
        msg="Would you like to create startup script for you?"
    )
    _configure = whiptail.confirm(msg="Start BoneIO at system startup automatically?")
    sys.exit(0)


# function askQuestion(){
#     Q=$(whiptail --inputbox "$1" 8 39 "$2" --title "$3" 3>&1 1>&2 2>&3)
#     exitstatus=$?
#     if [ $exitstatus == 0 ]; then
#         echo $Q;
#     else
#         echo "Wrong selection."
#         exit 1;
#     fi
# }

# function passwordPrompt(){
#     Q=$(whiptail --passwordbox "Enter mqtt password" 8 78 --title "MQTT password" 3>&1 1>&2 2>&3)
#     exitstatus=$?
#     if [ $exitstatus == 0 ]; then
#         echo $Q
#     else
#         echo $Q
#     fi
# }

# function askYesNoQuestion(){
#     Q=$(whiptail --yesno "$1" 8 39 --title "$2" 3>&1 1>&2 2>&3)
#     exitstatus=$?
#     if [ $exitstatus == 0 ]; then
#         return 0;
#     else
#         return 1;
#     fi
# }
# # function configYaml() {

# # }

# function install() {
#     local INSTALL_PATH=$(askQuestion "Where would you like to install package? Last part of directory will be created for you" "/home/debian/boneio" "Installation PATH")
#     echo "User entered installation path:" $INSTALL_PATH
#         # sudo apt-get install libopenjp2-7-dev libatlas-base-dev python3-venv
#         # mkdir -p $INSTALL_PATH
#         # python3 -m venv $INSTALL_PATH/venv
#         # $INSTALL_PATH/venv/bin/pip3 install --upgrade boneio
#     askYesNoQuestion "Would you like to give some basic mqtt credentials so we can configure boneio for you?" "Auto configuration"
#     local YAML_AUTOCONFIGURE=$?
#     echo "dupa"
#     echo $YAML_AUTOCONFIGURE
#     if [ $YAML_AUTOCONFIGURE == 0 ]; then
#         echo "Configuring YAML file:" $INSTALL_PATH
#         local MQTT_HOST=$(askQuestion "Type mqtt hostname" "localhost" "MQTT hostname")
#         local MQTT_USERNAME=$(askQuestion "Type mqtt username" "mqtt" "MQTT username")
#         local MQTT_PASSWORD=$(passwordPrompt)
#         echo "ask"
#         eval `resize`
#         ASK=$(whiptail --title "Modules chooser" --checklist \
#             "Choose what you want to include in your yaml" $LINES $COLUMNS $(( $LINES - 5 )) \
#             "OLED" "Turn on OLED" ON \
#             "Input" "Enable inputs (better to edit them anyway according to your needs later)" ON \
#             "ADC" "Enable ADC input sensors" OFF \
#             "Relay Board 32 x 5A" "Enable relay board 32x5A" ON \
#             "Temperature sensor on Relay Board 32 x 5A" "Enable temperature on Relay board" ON)
#         echo $ASK

#     fi
#     #     if (whiptail --title "Auto configuration" --yesno "Would you like to give some basic mqtt credentials so we can configure boneio for you?" 8 78); then
#     #         echo "User selected Yes, exit status was $?."
#     #     else
#     #         echo "User selected No, exit status was $?."
#     #     fi

#     # else
#     #     echo "User selected Cancel."
#     # fi

# }

# initialCheck
# # sudo true
# install
