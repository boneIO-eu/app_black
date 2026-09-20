# Remote inputs over MQTT

A `remote_input` with `remote_source: mqtt` follows a state published on a
topic and behaves locally like any other input — it can run actions, appear in
Home Assistant, and be read by a condition.

The obvious use is mirroring another boneIO:

```yaml
remote_devices:
  - id: blk8c7df0          # the peer's topic prefix, i.e. its serial
    name: Garage boneIO
    protocol: mqtt

remote_inputs:
  - id: garage_button
    name: Garage button
    remote_source: mqtt
    device_id: blk8c7df0
    input_id: in_04
    actions:
      single:
        - action: output
          boneio_output: out_02
          action_output: TOGGLE
```

No topic is given because the default is exactly where a boneIO publishes its
own inputs: `<device_id>/input/<input_id>`. A button on one controller drives a
relay on another with nothing in between but the broker.

## Anything else that publishes a state

Set `topic` explicitly:

```yaml
remote_inputs:
  - id: front_door
    remote_source: mqtt
    device_id: esp_hall
    input_id: door
    topic: esphome/hall/binary_sensor/door/state
    device_class: door
    show_in_ha: true
```

Payloads understood, case-insensitive and with surrounding quotes stripped:

| Means on | Means off |
|---|---|
| `on`, `true`, `1`, `pressed`, `open`, `opening`, `active` | `off`, `false`, `0`, `released`, `closed`, `closing`, `inactive` |

Three vocabularies, because the three things people point this at do not agree:
boneIO publishes `pressed`/`released`, ESPHome publishes `ON`/`OFF`, and
everything else publishes `true`/`1`.

Anything else is **logged and ignored**, leaving the state as it was. Not
guessed at: a wrong guess here silently drives a relay.

## Clicks, not just states

A boneIO *event* input publishes JSON with an `event_type` — a click it has
already classified. With `mode: event` that is passed straight through as the
click type:

```yaml
  - id: peer_wall_switch
    remote_source: mqtt
    device_id: blk8c7df0
    input_id: in_07
    mode: event
    actions:
      double:
        - action: output
          boneio_output: out_05
          action_output: TOGGLE
```

Re-deriving single/double/long locally would mean inferring them from a press
this side never saw. In `mode: binary_sensor` such a message is ignored with a
note saying which mode it needs.

## Subscriptions and reloads

Subscribed on every MQTT connect, not only the first: a broker restart drops
subscriptions, and an input that silently stopped following its peer is the
kind of fault nobody notices until the light does not come on.

Reloading the `remote_inputs` section unsubscribes before dropping the old
objects. Without that, the topic would still reach the previous callbacks and
one peer press would run both the old actions and the new ones.

A subscription that fails is logged and the rest still go up.

## `remote_source: can`

Not implemented. The value still loads, so a config that has it does not stop
the controller from starting — but the input is **refused at startup** with an
error rather than created.

That is deliberate. Creating it would put an entity in Home Assistant that
never updates, which reads as a wiring fault rather than a missing feature.

## What this is not

A flag you flip by hand from Home Assistant. A remote input *mirrors* something
that already exists elsewhere; it has no command topic and nothing can set it
locally. For a state boneIO owns — evening mode, holiday mode — use a
`virtual_switch`. See `docs/VIRTUAL_SWITCHES.md`.

## Files

| File | Role |
|---|---|
| `boneio/components/input/remote/mqtt.py` | The input: topic, payload parsing, click pass-through |
| `boneio/core/manager/remote_input_registrar.py` | Branching on `remote_source`, subscribe/unsubscribe |
| `boneio/schema/remote_inputs.yaml` | `topic`, and what each source actually does |
| `tests/unit/core/test_remote_input_mqtt.py` | 31 tests |
