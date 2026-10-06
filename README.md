# boneIO Black

**boneIO Black** is a DIN-rail home automation controller: relays, inputs and
sensors in one box, ready to wire into a switchboard. This repository is the
software that runs on it — configured from the browser, integrated with
Home Assistant over MQTT, and working on its own when the network or the
server is down.

[boneio.eu](https://boneio.eu) · [Documentation](https://boneio.eu/docs/intro/) · [Releases](https://github.com/boneIO-eu/app_black/releases)

## The controller

- **32x10A** — 32 relay outputs, 10 A each, plus inputs for wall switches.
- **24x16A** — 24 relay outputs, 16 A each, for heavier loads.
- **Cover** and **Cover Mix** — boards made for roller blinds, venetian blinds
  and gates.

Every board has an OLED status screen, a temperature sensor, power
monitoring and RS-485 for Modbus devices. It comes with the system image
installed: power it up, open the panel, pick the board type, done.

## What the software does

- **Web panel** — configure outputs, inputs, covers and devices from the
  browser, with no YAML editing needed (YAML stays available for those who
  want it). Accounts with roles, HTTPS, works as a phone app (PWA).
- **Home Assistant** — every output, input and sensor appears in Home
  Assistant by itself through MQTT discovery. MQTT over TLS is supported.
- **Local logic** — inputs drive outputs directly on the controller, with
  click / double click / long press actions and conditions. Lights still work
  when Home Assistant or the network does not.
- **Covers** — time-based roller blinds, venetian blinds with tilt, gates.
- **Modbus** — ready definitions for energy meters, inverters, HVAC units and
  sensors (SDM630, ORNO, Socomec, Sofar, SHT30, PT100 and more).
- **Templates** — thermostats, alarm panel, irrigation, schedules, presence
  simulation, sunrise / sunset triggers, virtual switches and energy sensors.
- **Remote devices** — ESPHome, WLED and other controllers over MQTT or CAN,
  used as inputs and outputs as if they were local.
- **Updates from the panel** — application and system updates, backups and
  configuration restore without SSH.

## Getting started

The controller ships ready to use. Connect it to the network and open
`https://<controller-ip>:8443`, or plug in USB and open
`http://192.168.7.2:8090`. The first-run wizard creates the administrator
account and asks which board this is.

Full guide: [boneio.eu/docs](https://boneio.eu/docs/intro/).

The supported way to run this software is the boneIO system image on boneIO
hardware. Installing the Python package by hand on another system is not
supported.

## Development

```bash
uv sync
uv run boneio run -c ~/boneio/config.yaml -dd
```

Python 3.13 or newer. Frontend sources are in `frontend/`.

## License

GNU General Public License v3.0.
