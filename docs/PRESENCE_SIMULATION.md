# Presence simulation

Make an empty house look lived in: as it gets dark a light comes on, later
another one in a different room, and at bedtime everything goes off. Armed and
disarmed by one switch, so leaving is one tap.

**Settings → Control → Schedules → Presence simulation** asks four questions and
writes it.

## It is not a subsystem

What the wizard writes is one virtual switch and one schedule per light —
exactly what you would write by hand. Nothing extra runs. Afterwards they are
ordinary entries on the Schedules and Virtual switches pages: rename them,
retime them, delete one, add a fifth.

That is deliberate. A `presence_simulation:` section would have meant a second
scheduler at runtime with its own catch-up rules, its own state, and its own
bugs, to express something the existing pieces already express.

Everything generated is named `presence_*`. Running the wizard again replaces
those and leaves everything else exactly where it was, so one run plus three
schedules of your own survives a second run.

## What it generates

Four lights, bedtime 23:10:

```
~21:10  Living room on     ← civil dusk, capped
~21:40  Bedroom on         (living room off)
~22:10  Kitchen on         (bedroom off)
~22:40  Study on           (kitchen off)
 23:10  everything off
```

The first light follows **civil dusk**, so the evening starts with the season.
The rest divide the two hours before bedtime evenly. They are not placed
relative to dusk on purpose: in Warsaw dusk is 15:30 in December, and a step
"two hours after dusk" would put the bedroom light on at half past five in the
afternoon.

Each step turns the previous light off as it turns its own on. One room at a
time reads as somebody walking through the house; the whole ground floor lit at
once reads as a timer.

### Why dusk is capped

In Warsaw on the longest day civil dusk is **21:50**. Without a cap, "living
room at dusk" and "bed at 23:10" collapse into eighty minutes — the simulation
becomes absurd in exactly the season the house is empty. So the first schedule
gets `latest:`, set to the start of the evening window.

### The two kinds of randomness

| | `jitter` | `probability` |
|---|---|---|
| Randomises | *when* a step happens | *whether* it happens |
| Without it | every house on the street switches in the same second | the same four steps every night |

Only the second one breaks a pattern. Someone watching for three evenings sees
lights on a timer unless steps sometimes do not happen at all.

The **Calm / Normal / Lively** choice sets both: 15/25/40 minutes of spread,
and a probability of 1 / 0.85 / 0.7.

The final "everything off" never gets a probability. A step that might not
happen is realistic; a light that might not go off burns until morning and
announces that nobody is home.

## The flag

`presence_away`, a virtual switch, discovered by Home Assistant. Every
generated schedule is conditioned on it, so nothing fires while you are home.

It also carries actions of its own:

- **on** — turns the first light on, but only if it is already dark and not yet
  bedtime. This is the catch-up: arm it at 22:00 and the dusk schedule has
  already passed with the flag off. The schedule cannot help — its moment is
  gone — but the flag can, because its action carries its own conditions.
- **off** — turns every light in the simulation off. Coming home puts back what
  the simulation left on, rather than leaving the bedroom lit at noon.

## Doing it by hand

Nothing here needs the wizard. The pieces are `virtual_switch` with
`actions:` (see [VIRTUAL_SWITCHES.md](VIRTUAL_SWITCHES.md)), `schedule` with a
sun trigger and `latest:`/`jitter:` (see [SCHEDULES.md](SCHEDULES.md)), and
`probability:` on an action.

## Still missing

**Which light is never random.** `probability` decides whether a step runs, not
which room it picks. A convincing version would sometimes light the kitchen
instead of the bedroom.

**Nothing models a weekend.** The `days:` filter is per schedule, so "later on
Fridays" means a second set.

## Files

| File | Role |
|---|---|
| `frontend/src/components/UISettings/PresenceSimulationWizard.tsx` | The four questions |
| `frontend/src/components/UISettings/helpers/presenceSimulation.ts` | What they turn into |
| `frontend/src/components/UISettings/helpers/presenceSimulation.test.ts` | 17 tests, mostly about the ordering |
| `boneio/core/manager/scheduler.py` | `_clamp_to_window` for `earliest`/`latest` |
| `boneio/core/manager/manager.py` | `probability` in `execute_actions` |
