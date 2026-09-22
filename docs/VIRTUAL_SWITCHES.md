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
| `name` | required | Free text. Shown in Home Assistant and in the panel, and the identifier is made from it |
| `description` | — | A note to yourself. Nothing reads it |
| `id` | made from `name` | Only when the identifier has to survive a rename — see below |
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

## The identifier

Written as:

```yaml
virtual_switch:
  - name: Nie ma nas w domu
    description: Flaga symulacji obecności
```

and the identifier becomes `nie_ma_nas_w_domu`: accents folded, everything that
is not a letter or a digit collapsed to one underscore. That identifier is what
the MQTT topic uses, what Home Assistant's unique_id is built from, what the
saved state is keyed on, and what a condition or another switch's action writes
to refer to this switch.

Which is also the catch. **Renaming a switch changes its identifier**, and with
it all four: the old Home Assistant entity goes unavailable, the flag comes up
off because its saved state was filed under the old name, and every action
pointing at it stops matching. Set an explicit `id` if you expect to rename it:

```yaml
virtual_switch:
  - id: away              # never changes
    name: Nie ma nas w domu
```

Two names that fold to the same identifier — "Salon" and "salon!" — are refused
at load time rather than silently becoming one switch.

## References are checked when the config loads

A condition or an action naming a virtual switch that is not defined stops the
controller from starting, with the name quoted and the defined ones listed
next to it.

Worth being strict about here specifically, because of which way the runtime
fails: a condition whose entity cannot be resolved is logged and **the action
runs anyway**. That is a reasonable default — a broken reference should not
silently stop the lights working — but for a flag that exists to hold things
back it is exactly backwards. One wrong letter in "only while nobody is home"
and everything it was gating runs while somebody is in the house, with a
single warning in the log to say why.

Virtual switches come from exactly one place, which is what makes the check
safe. Outputs, covers and inputs arrive from a board file, an expander or a
remote device as well as from the config, so the same rule on them would
reject configurations that work.

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
in Settings. The modal asks for what a flag is — a name and an id — and then
what it does:

```
[ Name = id ]                 [ Description ]

ON TURN ON                              + Add action
  › Turn on: Living room · conditions: 2      🗑
  › Turn on: Kitchen                          🗑

ON TURN OFF                             + Add action
  › Turn off: Living room                     🗑

› More options — restored · Home Assistant
```

Each action is one line saying what it does, expanding in place to the full
editor. The editor card is about the same height whether an action says one
thing or ten, so a switch that turns on two lights used to be a page of
scrolling with nothing legible at a glance.

The dialog asks for a **name** and a **description**, which is what config.yaml
calls them too. The identifier is shown under the name rather than typed — it
is a consequence, not a decision.

Everything else — `restore_state`, `initial`, `show_in_ha`, the icon, the area
— is behind **More options**, and that row names what is inside so it can be
ruled out without opening it. Each of those has an answer that is right for
almost everybody, and together they were outweighing the two fields that do
not: the area picker alone is nine chips and five rows tall.

The two lists sit under each other rather than behind tabs because they are
usually written as a pair — whatever `on_turn_on` changes, `on_turn_off` is
what puts it back, and checking that from memory across a tab switch is how one
of them ends up forgotten.

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
