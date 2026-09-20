# Schedules

Actions that fire on their own — at a clock time, or at a moment the Sun
defines. Everything else in boneIO starts with a person or an input; this is the
exception, and that is both the point and the reason the runtime is careful.

## Configuration

```yaml
schedule:
  - id: covers_evening
    name: Covers at dusk
    enabled: true
    trigger:
      type: sun            # sun | time
      event: sunset        # a sun anchor — see docs/SUN.md
      offset: "-15min"     # negative is earlier
      jitter: "10min"      # random spread, drawn per firing
      days: daily          # daily | weekdays | weekend | mon…sun
    on_missed: skip        # skip | run
    catch_up: "15min"      # how late a missed firing may still run
    condition:             # optional, same schema as an action's
      type: date
      after: "10-01"
      before: "04-30"
    actions:               # same actions a button can run
      - action: cover
        boneio_cover: living_room
        action_cover: CLOSE
```

A clock trigger uses `at` instead of `event`:

```yaml
    trigger:
      type: time
      at: "23:30"
      days: weekdays
```

Mixing them — `at` on a sun trigger, `event` on a time trigger, a sun event that
does not exist, a schedule with no actions — is rejected when the config loads,
by `condition_shape`'s sibling `schedule_shape` in `yaml_util.py`. The symptom
of getting this wrong at runtime would be a schedule that quietly never fires,
which is the hardest kind of misconfiguration to notice.

A sun trigger needs the `location:` section. See `docs/SUN.md`.

### Holding a sun anchor inside a clock window

`earliest:` and `latest:` clamp a sun trigger, for the months when the anchor
runs away from the hour someone actually meant:

```yaml
trigger:
  type: sun
  event: civil_dusk
  latest: "21:00"     # in Warsaw, dusk is 21:50 on the longest day
  jitter: "25min"
```

Applied after `offset` and before `jitter`. Clamping last would put every
midsummer evening on exactly the same minute, which is the pattern `jitter`
exists to break — so a clamped firing can land up to `jitter` after the bound.

Sun triggers only: a clock trigger already has a fixed time, and clamping it is
either a no-op or the same time written twice. The loader refuses that rather
than accepting it quietly.

## What it refuses to guess at

**A clock that has not been set.** The board has no battery-backed RTC, so
between power-on and the first NTP reply it believes it is 1970. Nothing is
armed until the date is plausible — arming a timer against 1970 would fire
everything at once the moment NTP corrects it. See `docs/TIMEZONE_NTP.md` for
pointing a device with no internet at a local NTP server.

**A day when the Sun does not reach the angle.** Above about 60° of latitude
`sunset` simply does not happen for weeks. The schedule skips forward to a day
that has one rather than inventing a time, and says so once if there is none
within 400 days.

**A firing missed while the device was off.** `on_missed: skip` (the default)
forgets it. `on_missed: run` fires it at startup *if* it was due within
`catch_up` — right for "close the covers", wrong for "sound the doorbell". A
controller that was off all day does not suddenly close the covers at breakfast.

## How the timers stay right

Every schedule's next firing is recomputed **every minute** from the current
wall clock, and the armed timer is replaced only when the instant actually
changed. That is not paranoia:

- NTP steps the clock at boot, and a timer armed before the step points at the
  wrong instant afterwards.
- The local day ticks over, and tomorrow's sunset is not today's.
- A timer can fire late if the loop was busy.

Re-planning is idempotent, which is what makes running it that often safe —
there is a test asserting that five consecutive plans arm exactly one timer.

### Jitter is stable within a day

`jitter` adds a random delay, drawn from a seed of `(schedule id, date)` rather
than freshly each time. With a fresh draw every minute the firing would walk
forwards and never arrive.

It exists for presence simulation: without it, every boneIO on the street closes
its covers in the same second.

### The day filter applies to the day the firing lands on

`at: "23:30"` with `offset: "1h"` on a Friday happens on Saturday, so
`days: weekdays` excludes it. That is what someone reading "weekdays" expects.

## Conditions

A schedule can carry the same `condition` / `conditions` as any action, and each
of its actions can carry its own on top. The schedule's own condition gates the
whole firing; an action's gates just that action.

```yaml
    condition:
      type: sun
      phase: night
```

They also apply to **Run now** in the panel — a manual run that ignored them
would be testing something other than the schedule.

## API

### `GET /api/schedule`

What is armed, and for when. This is the only way to find out: a schedule is the
one thing in boneIO nobody can test by pressing a button.

```json
{
  "schedules": [
    {
      "id": "covers_evening",
      "name": "Covers at dusk",
      "enabled": true,
      "trigger": {"type": "sun", "event": "sunset", "offset": -900.0, "days": "daily"},
      "actions": 1,
      "next_fire": "2026-09-18T18:31:39+02:00",
      "last_fire": null,
      "last_error": null
    }
  ]
}
```

`next_fire` is null for a schedule that is disabled, has no firing in sight, or
is waiting for the clock to be set.

### `POST /api/schedule/{id}/run`

Runs one schedule immediately, conditions included. The armed timer is left
alone, so testing a schedule does not cost you its next real firing.

## The panel

Settings → Control → **Schedules**.

A table with a modal editor, like every other list of entities in Settings. One
row per schedule: name, what triggers it in words ("Sunset −15 min · Every
day"), the action types, and the next firing.

The editor is one scrolling page, headed **When**, **Only if** and **Do**,
because a schedule is a single sentence and the three parts are read together —
you pick an action while looking at the trigger it hangs off. It was briefly
four tabs; that was a mistake. Tabs are right on an input, where `single`,
`double` and `long` are alternatives you never need side by side, and wrong
here, where the parts are clauses of one statement.

**When** is one row: the trigger type, the anchor or the clock time, the days,
and — for a sun trigger only — the offset. On a clock trigger an offset is a
second way to say the same thing ("20:00 minus 15 minutes" is 19:45), so the
field is not offered and switching to a clock trigger drops it. The backend
applies an offset either way, so one written by hand still works and still
shows in the table row; the editor just will not help you create one.

Jitter and `on_missed` are behind **More options** — they have a default that
is right almost always, and they were competing with the fields that decide
when the thing fires.

The first field is the **id**, labelled *Name*: it is the word you type once
and then use everywhere — in the config, in a condition, in "run now". The
friendly `name` is labelled *Description*, because that is what it is next to
the id; Home Assistant shows it, and falls back to the id when it is empty.

**Do** is a list of one-line rows ("Toggle: Living room · conditions: 2"), each
expanding in place to the editor. Same reason as everywhere else: the editor
card is about the same height whether an action says one thing or ten.

The action editor is the same `ActionFields` component the input forms use, and
the condition editor the same `ActionConditions`, so a schedule's actions
support exactly what a button's do.

### The two things a schedule needs that a configuration cannot show

`ScheduleTable` is the only table in Settings that fetches anything, and both
reasons are specific to schedules.

**The next firing.** The configuration says when a schedule *should* fire. Only
the running controller says when it *will*, or why it did not — a stale
timezone, a sun anchor that never resolves at this latitude, a condition that
was false. The column also carries `last_error`.

**Run now.** A schedule is the one thing in Settings nobody can test by pressing
a button; without this the only way to find out whether it works is to wait
until evening. It is disabled while the section has unsaved edits, because it
fires what the controller has loaded, not what is on screen, and disabled for a
schedule the controller has not loaded at all — a newly added one, before the
first save.

A new schedule starts as a clock trigger at 20:00 rather than sunset. A sun
trigger on a device with no coordinates can never resolve, so it would sit there
looking configured and never fire; the sun option is shown greyed out with the
reason instead of being hidden.

## Files

| File | Role |
|---|---|
| `boneio/core/manager/scheduler.py` | The runtime: planning, arming, catching up, firing |
| `boneio/schema/schema.yaml` | The `schedule:` section |
| `boneio/core/config/yaml_util.py` | `_check_with_schedule_shape` |
| `boneio/webui/routes/schedule.py` | Status and run-now |
| `frontend/src/components/UISettings/tables/ScheduleTable.tsx` | The list, with next firing and run-now |
| `frontend/src/components/UISettings/ScheduleForm.tsx` | The editor, four tabs |
| `frontend/src/components/UISettings/helpers/scheduleTrigger.ts` | Offsets, trigger shape, row summary |
| [PRESENCE_SIMULATION.md](PRESENCE_SIMULATION.md) | The wizard that writes a set of these |
| `tests/unit/core/test_scheduler.py` | 28 tests, mostly about when it should *not* fire |
| `tests/unit/webui/test_schedule_routes.py` | The two endpoints |

## Not here yet

- **Sunrise-to-sunset spans.** A schedule is a moment, not an interval. "On at
  dusk, off at dawn" is two schedules, which is also how it reads in the config.
- **A calendar view.** The panel lists the next firing per schedule and nothing
  more.
