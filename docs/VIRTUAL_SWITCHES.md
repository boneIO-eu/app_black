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
| `actions` | — | What to run when it changes — see below |

`restore_state` defaults to on because a controller that forgot every mode on
each reboot would be worse than one with no modes at all. Turn it off for a
flag that should always start in a known state.

## Running actions when it changes

A virtual switch does not have to be only a flag other things read. It can act
on its own change:

```yaml
virtual_switch:
  - id: away
    name: Away
    actions:
      on_turn_on:
        - action: output
          boneio_output: out_livingroom
          action_output: "ON"
          conditions:
            mode: and
            list:
              - type: sun
                after: civil_dusk
              - type: time
                before: "21:40"
      on_turn_off:
        - action: output
          boneio_output: out_livingroom
          action_output: "OFF"
```

### Why `on_turn_on` and not `on`

YAML reads bare `on` and `off` as booleans. Written that way the keys would
silently become `true` and `false`, nothing would ever match them, and the
config would load, look right and do nothing. The spelling matches ESPHome,
which hit the same trap first.

### What they are for

Two things, and the second is the one that is easy to miss.

**Cleaning up.** Turning the flag off puts back whatever turning it on changed.
Without this, every action that read the flag as a condition had to be paired
by hand with a second action somewhere else that undid it.

**Catching up.** Someone arms "away" at 22:00, after the dusk schedule that
would have turned the lights on has already fired. A schedule cannot help —
its moment has passed. An action on the flag can, because each action carries
its own condition: "on, but only if it is already dark and not yet bedtime" is
exactly the `conditions:` block above.

### When they do not run

- **Not on the republish after an MQTT reconnect.** States are re-published
  whenever the broker comes back; re-running the actions there would turn the
  lights on every time the network hiccuped.
- **Not on a restored state at startup.** Coming back from a power cut must not
  act on the house. The switch comes up holding the state it had; it does not
  replay reaching it.
- **Not on a config reload.** Saving the page rebuilds every switch and hands
  each new one the state its predecessor held. Renaming one switch must not
  replay every other switch's scenes.
- **Not when the state did not change.** Setting a switch that is already on is
  a publish, not an edge.

### Loops

A switch may set another switch, which is how "away on" can also turn "guest
mode" off. A ring — A sets B, B sets A — is caught at its first repeat: the
second entry is refused and logged as an error rather than recursing until the
stack gives out. A switch whose own actions set *itself* is refused at load
time, because the change that would run those actions is the one they are
trying to make.

Actions are resolved after every switch has been built, so an action may name a
switch defined further down the file.

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

It is an ordinary table with a modal editor, like every other list of entities
in Settings, and the two action lists are **tabs** in that modal — exactly as
`single`/`double`/`long` are on an input. That is the point: a virtual switch
is the same kind of thing as an input, something that happens with a list of
actions per case, so it should not have to be learned twice.

It was briefly a hand-written page with rows that expanded in place. That put
the one entity list in Settings that did not look like the others, and stacked
two action editors inside a table row.

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
| `frontend/src/components/UISettings/tables/VirtualSwitchTable.tsx` | The list |
| `frontend/src/components/UISettings/VirtualSwitchForm.tsx` | The editor, with a tab per edge |
| `tests/unit/core/test_virtual_switch.py` | 29 tests |

## What this replaced

Before it, there was no way to do this at all — not even roundabout:

- a local `binary_sensor` is bound to a GPIO pin
- `remote_input` with `remote_source: mqtt` is accepted by the schema but never
  subscribes to anything; only `esphome_api` registers a state callback
- an `output` would work, but needs a physical channel and would click a relay
- `template` has no generic switch platform

The `remote_source: mqtt` gap is a separate bug — the schema advertises
something the registrar does not implement.

### The `remote_source: mqtt` gap, since fixed

That last point was a real bug and is now closed: `remote_input` with
`remote_source: mqtt` subscribes to a topic and follows it. See
`docs/REMOTE_INPUTS_MQTT.md`.

It solves a different problem, though. A remote input **mirrors** a state that
already exists somewhere else — another boneIO's button, an ESPHome sensor. A
virtual switch **is** the state, owned here. Reach for a remote input to follow
something; reach for a virtual switch to decide something.
