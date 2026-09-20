# Virtual switches

A switch with nothing behind it. It holds an on/off state, publishes it, and
accepts commands — and drives no relay at all.

Its purpose is to be **read by a condition**, so an ordinary action can be
qualified:

```yaml
virtual_switch:
  - id: evening_mode
    name: Evening mode
    icon: mdi:weather-night
    restore_state: true

event:
  - boneio_input: in_11
    actions:
      single:
        - action: output
          boneio_output: out_11
          action_output: TOGGLE
          condition:
            type: state
            entity: virtual_switch
            entity_id: evening_mode
            state: is_on
```

IN_11 still drives OUT_11 — but only while evening mode is on, and evening
mode is something a person flips in Home Assistant, in the panel, or from
another button.

## Why boneIO owns the state

The obvious alternative is an `input_boolean` in Home Assistant that boneIO
subscribes to. That was rejected: the controller would forget which mode it is
in whenever the broker restarts or Home Assistant is down — exactly when a
building controller should carry on by itself.

So the state lives here, is persisted across restarts by default, and Home
Assistant is one of several things that can change it rather than the thing
that owns it.

## Why it is a switch and not a binary sensor

In Home Assistant a `binary_sensor` is read-only: nothing can flip it from a
dashboard or an automation. A thing you turn on and off is a `switch`, and that
is what this is discovered as.

Locally it reads like a binary sensor — `is_on` / `is_off` in a condition —
because that is the question a condition asks. Both are true at once; they are
descriptions from different ends of the same object.

## Configuration

| Field | Default | Means |
|---|---|---|
| `id` | required | Used in the MQTT topic, and referenced by conditions and actions |
| `name` | the id | Shown in Home Assistant and in the panel |
| `area` | — | Area for Home Assistant grouping |
| `icon` | — | MDI icon, e.g. `mdi:weather-night` |
| `restore_state` | `true` | Remember the state across a restart |
| `initial` | `false` | What to come up as when there is nothing to restore |
| `show_in_ha` | `true` | Announce it to Home Assistant |

`restore_state` defaults to on because a controller that forgot every mode on
each reboot would be worse than one with no modes at all. Turn it off for a
flag that should always start in a known state.

## Setting one from an action

Any action list can set one, so a long press can arm a mode that other inputs
then obey:

```yaml
event:
  - boneio_input: in_12
    actions:
      long:
        - action: virtual_switch
          boneio_virtual_switch: evening_mode
          action_output: TOGGLE
```

`action_output` is reused rather than given a name of its own: a virtual switch
takes the same three verbs an output does — `ON`, `OFF`, `TOGGLE` — and one
concept beats two near-identical fields.

Schedules can set them too, which is how "evening mode on at dusk, off at
midnight" is written: two schedules and one flag, instead of duplicating a
condition across every action in the house.

## MQTT and Home Assistant

```
state:    boneio/<serial>/virtual_switch/<id>        {"state": "ON"}   retained
command:  boneio/<serial>/cmd/virtual_switch/<id>/set  ON | OFF | TOGGLE
```

The state is retained so Home Assistant restarting does not lose which mode the
house is in. Commands need no extra subscription: the controller already
listens to the whole `cmd/+/+/#` tree.

Every state is re-published on MQTT reconnect. Retained messages usually make
that unnecessary — usually, because a broker that was reinstalled, or one
configured without persistence, comes back with an empty retained set, and a
mode nobody can see is a mode nobody trusts.

## In the panel

**Settings → Control → Virtual switches** defines them. They sit in the logic
half of that group, next to Schedules rather than next to Outputs: the one
thing a virtual switch never does is switch anything.

**The Outputs view** carries them as their own group, with a toggle. That is
where they belong for day-to-day use — a mode gets flipped daily, and looking
for it in Settings would be the same mistake as being able to switch a relay
only from Settings.

## Files

| File | Role |
|---|---|
| `boneio/components/virtual_switch.py` | The entity: state, commands, publishing |
| `boneio/core/manager/virtual_switches.py` | Building, restoring, discovery, reload |
| `boneio/schema/schema.yaml` | The `virtual_switch:` section |
| `boneio/webui/routes/outputs.py` | `POST /api/virtual_switch/{id}/toggle` |
| `tests/unit/core/test_virtual_switch.py` | 19 tests |

## What this replaced

Before it, there was no way to do this at all — not even roundabout:

- a local `binary_sensor` is bound to a GPIO pin
- `remote_input` with `remote_source: mqtt` is accepted by the schema but never
  subscribes to anything; only `esphome_api` registers a state callback
- an `output` would work, but needs a physical channel and would click a relay
- `template` has no generic switch platform

The `remote_source: mqtt` gap is a separate bug — the schema advertises
something the registrar does not implement.
