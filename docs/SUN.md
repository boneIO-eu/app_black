# Sun: position and event times

`boneio/core/utils/sun.py` answers every question boneIO needs to ask about the
Sun from three inputs: a latitude, a longitude and an instant. It is pure
maths — no config, no I/O, no cached state — so it can be tested exhaustively
and reused by the conditions layer, the sensors and the scheduler without any
of them agreeing on anything but numbers.

> **Status.** All of `SUN_ROADMAP_1.6.md` is done: the engine, the `location:`
> config section, the provider that caches it, `GET /api/sun/today`, the
> Location page with an optional map picker, the `type: sun` action condition,
> the `sun_*` entities, and sun-driven schedules.
>
> For the condition see **`docs/ACTION_CONDITIONS.md`**; for schedules that fire
> on their own, **`docs/SCHEDULES.md`**.
>
> For the condition itself — syntax, the three shapes, and what happens at
> polar latitudes — see **`docs/ACTION_CONDITIONS.md`**.

## Why not `astral`

`astral` is the obvious library for this and it is what the tests measure
against. It is not a runtime dependency, on purpose:

- `pyproject.toml` pins every version exactly. Each package is another link in
  the supply chain of a device sitting on a customer's network, and ~250 lines
  of trigonometry is a poor reason to add one.
- Every threshold boneIO cares about — civil, nautical and astronomical
  twilight, the golden and blue hours — is the same solver with a different
  angle. We need almost none of astral's API.
- Polar behaviour and the per-day caching policy are decisions boneIO has to
  make for itself either way.

The risk that buys is an error in the maths, and that is what
`tests/unit/core/test_sun.py` is for: astral is a **test-only** dependency and
the suite compares against it across a full year and eight cities.

## Two conventions that are easy to mix up

**Geometric elevation** is the true angle of the Sun's centre above the horizon,
ignoring the atmosphere. **Apparent elevation** is what an observer sees —
geometric plus refraction.

Every threshold in this module is geometric, including `SUNRISE_SUNSET =
-0.833°`, which already accounts for mean refraction (34′) and the solar
semi-diameter (16′) by definition. `apparent_elevation()` exists for display
only; feeding it back into `phase_of()` would make the phases disagree with the
event times near the horizon.

## Events are anchored to solar noon, not to the calendar

The civil dusk of a day is the one that follows **that day's solar noon**, even
when it lands after local midnight. At northern latitudes in summer that happens
routinely — Reykjavík's civil dusk is past 00:30 for weeks — and anchoring to
the calendar instead would mean "dusk today" quietly returned yesterday's dusk
for half the year.

This is the one place where boneIO and astral deliberately differ.

## Anchors

`all_anchors()` returns all eighteen for one local day, as aware UTC.

| Anchor | Threshold | Direction |
|---|---|---|
| `astronomical_dawn` / `astronomical_dusk` | −18° | rising / setting |
| `nautical_dawn` / `nautical_dusk` | −12° | rising / setting |
| `civil_dawn` / `civil_dusk` | −6° | rising / setting |
| `blue_hour_morning_start` / `blue_hour_evening_end` | −6° | rising / setting |
| `blue_hour_morning_end` / `blue_hour_evening_start` | −4° | rising / setting |
| `golden_hour_morning_start` / `golden_hour_evening_end` | −4° | rising / setting |
| `sunrise` / `sunset` | −0.833° | rising / setting |
| `golden_hour_morning_end` / `golden_hour_evening_start` | +6° | rising / setting |
| `solar_noon` / `solar_midnight` | — | extremum |

Some anchors share an instant on purpose: the blue hour ends exactly where the
golden hour begins, and its other edge *is* civil twilight. Two names for one
moment is the photographic convention, not a bug.

## Phases

`phase_of()` returns one of five phases that partition the day.
`in_phase()` additionally tests the two photographic bands, which **overlap**
those five — the golden hour straddles the horizon, so it is partly `day` and
partly `civil_twilight`.

| Phase | Geometric elevation |
|---|---|
| `day` | > −0.833° |
| `civil_twilight` | −6° … −0.833° |
| `nautical_twilight` | −12° … −6° |
| `astronomical_twilight` | −18° … −12° |
| `night` | ≤ −18° |
| `golden_hour` *(overlaps)* | −4° … +6° |
| `blue_hour` *(overlaps)* | −6° … −4° |

## API

```python
solar_position(latitude, longitude, when) -> (elevation, azimuth)
apparent_elevation(geometric) -> float
horizon_dip(elevation_m) -> float
solar_noon(longitude, day, tz) -> datetime
event_time(latitude, longitude, day, tz, threshold, *, rising, elevation_m=0.0) -> datetime | None
threshold_state(latitude, longitude, day, tz, threshold, elevation_m=0.0) -> str
all_anchors(latitude, longitude, day, tz, elevation_m=0.0) -> dict[str, datetime | None]
phase_of(elevation) -> str
in_phase(elevation, phase) -> bool
```

`when` must be **aware**; a naive datetime raises rather than being guessed at.
Everything returned is aware UTC. `day` plus `tz` is what defines "a day" —
the timezone is an argument, never read from the process environment.

```python
>>> from datetime import date
>>> from zoneinfo import ZoneInfo
>>> tz = ZoneInfo("Europe/Warsaw")
>>> anchors = all_anchors(52.2297, 21.0122, date(2025, 6, 21), tz)
>>> anchors["sunset"].astimezone(tz).strftime("%H:%M")
'21:01'
>>> anchors["astronomical_dusk"] is None     # white nights: never below -18°
True
```

## Polar day and night

When the Sun does not cross a threshold at all, `event_time()` returns `None`.
`None` on its own is ambiguous — it means "never dark" in June and "never light"
in December — so `threshold_state()` says which:

```python
threshold_state(69.6492, 18.9553, date(2025, 6, 21), OSLO, SUNRISE_SUNSET)
# 'always_above'
```

Callers **must** use it. A `sunrise → sunset` window has to cover the whole day
during polar day and be empty during polar night; getting that backwards leaves
the lights on for a month.

## Accuracy

Measured against astral over a full year for Warsaw, Sydney, Quito, Reykjavík,
Nairobi, Anchorage, Tokyo and Cape Town: every event agrees to within **41
seconds** up to roughly |latitude| 62°.

The exception is a **grazing** event — one where the Sun barely reaches the
threshold, so the crossing happens near solar midnight and is nearly tangential.
There, `dt/dh` blows up and implementations diverge by minutes: Reykjavík's
civil dusk in late May differs from astral's by ~3 minutes, and a day later
astral refuses to compute it at all. No amount of iteration fixes the
conditioning, and nothing that drives a relay cares.

Altitude is applied as a horizon dip of `0.0353·√(metres)`: 110 m lowers the
horizon by 0.37°, which moves sunrise in central Europe by about two minutes —
small, but larger than the algorithm's own error, so worth applying.

## Performance

`all_anchors()` is ~30 trigonometric operations per anchor, called **once per
local day** and cached by the layer above; `solar_position()` is ~10 µs on the
BeagleBone's Cortex-A8. Neither belongs on a button-press path uncached, and
neither is anywhere near expensive enough to need more than a per-day dict.

## Tests

`tests/unit/core/test_sun.py`, in two halves:

- **Physics invariants** that stand on their own — noon elevation equals
  `90 − |latitude − declination|`, the equation of time peaks at +16 min in
  early November and −14 min in mid-February, the equinox day at the equator
  runs ~7 minutes past twelve hours, twilight bands nest, anchors are
  chronological, DST shifts the wall clock but not the Sun.
- **Cross-checks against astral**, skipped automatically when it is not
  installed: five dates for four cities, plus a full year for two of them with a
  60-second budget.

---

# Configuring it: `location:`

The engine is pure maths and knows nothing about this device. Three layers give
it a place, a clock and a way in.

## The config section

```yaml
location:
  latitude: 52.2297      # -90..90,   required
  longitude: 21.0122     # -180..180, required
  elevation: 110         # metres above sea level, optional, default 0
```

Top-level rather than inside `boneio:` — that section describes the hardware,
and this describes where it was installed. It hot-reloads: saving it from the
panel takes effect without a restart.

The timezone is deliberately **not** here. It comes from the system
(`timedatectl`), and a second source of truth for it would drift.

### About the coordinates

Four decimal places is ~11 m and more than the algorithm can use. The value also
ends up in `GET /api/config` and in configuration backups, so the panel rounds
to four places on save rather than storing whatever a phone's GPS produced.

`0, 0` is accepted with a warning. It is a real place in the Gulf of Guinea and
an unfilled form everywhere else; refusing it would be wrong, and saying nothing
would be worse.

## `SunProvider`

`boneio/core/manager/sun.py`. One instance, owned by the manager as
`manager.sun`, built even when `location:` is absent — an unconfigured provider
answers "not ready" and says so once, which every caller has to handle anyway.

```python
provider.configured          # is a usable location set
provider.ready()             # configured *and* the clock has been set
provider.anchors()           # all 18 anchors of today, cached per local day
provider.anchor("sunset")    # one of them
provider.position()          # (elevation, azimuth), cached for 60 s
provider.phase()             # "day" … "night"
provider.in_phase("golden_hour")
provider.threshold_state(-6.0)   # "crosses" | "always_above" | "always_below"
provider.invalidate()        # after a config, timezone or clock change
```

Three things it does that the maths layer cannot:

**It resolves the real timezone.** `datetime.now().astimezone().tzinfo` looks
like the answer and is not: it is the offset in force *right now*, frozen. Ask
it about a day in the other half of the year and it applies today's DST offset,
moving every anchor by an hour twice a year. The provider reads
`/etc/timezone`, falls back to resolving the `/etc/localtime` symlink, and only
then to a fixed offset — with a warning.

**It caches a day.** Anchors are computed once per local date and reused. The
cache key carries the timezone as well as the date, so changing the timezone
from the panel cannot leave yesterday's answers in place. Elevation readings are
reused for 60 s; the Sun moves at most 0.25°/minute, below the resolution of any
threshold worth configuring.

**It refuses to answer while the clock is wrong.** The BeagleBone has no
battery-backed RTC, so between power-on and the first NTP reply it reports
something near the epoch. Below 2025-01-01 the provider returns nothing and logs
once — computing sunset for 1970 and arming something against it would look
exactly like a working feature. See `docs/TIMEZONE_NTP.md` for pointing the
device at an NTP server on the local network, which is what makes this resolve
on an installation with no route to the internet.

# `GET /api/sun/today`

One endpoint on purpose. The panel needs today's anchors *and* the Sun's current
position together — times without a live elevation make a wrong latitude
indistinguishable from a wrong clock — and polling two endpoints to draw one
card is how they drift apart.

```
GET /api/sun/today            # today on the device
GET /api/sun/today?day=2025-06-21
```

```json
{
  "configured": true,
  "ready": true,
  "latitude": 52.2297,
  "longitude": 21.0122,
  "elevation": 110.0,
  "timezone": "Europe/Warsaw",
  "date": "2026-09-17",
  "anchors": {
    "sunrise": "2026-09-17T06:10:55+02:00",
    "astronomical_dusk": null,
    "...": "all 18, as local ISO timestamps"
  },
  "now": {
    "elevation": -16.79, "azimuth": 296.73,
    "phase": "astronomical_twilight",
    "golden_hour": false, "blue_hour": false
  },
  "horizon_state": "crosses"
}
```

Four answers matter and are easy to confuse:

| Answer | Means | The panel should say |
|---|---|---|
| `configured: false`, `reason: "no_location"` | Nothing is set | Fill in the coordinates |
| `ready: false`, `reason: "clock_not_set"` | Coordinates fine, clock is not | Wait for NTP, or configure a local server |
| `anchors.sunrise: null` + `horizon_state: "always_above"` | Polar day | The Sun does not set today |
| `anchors.sunrise: null` + `horizon_state: "always_below"` | Polar night | The Sun does not rise today |

Times come back **in the device's timezone**, not UTC: the panel renders them
verbatim, and handing it UTC would show a clock the operator has to correct in
their head. `null` is a real answer, not a missing one — it is what an anchor
looks like on a day the Sun never reaches that angle.

# The panel

Settings → Device → **Location**
(`frontend/src/components/UISettings/SystemStateComponents/LocationSection.tsx`).

A config section with its own component rather than a generated form. Three
numbers are easy to mistype and impossible to sanity-check on their own, so the
page shows today's times back — which is the only practical way to notice that
the longitude went into the latitude field.

It saves with `PUT /api/config/location` and then `POST /api/config/reload
['location']`, creating the section when config.yaml does not have one yet.

### No "use my location" button

It would need two things this panel does not have. A secure context, which a
panel served over plain HTTP on a LAN is not — `navigator.geolocation` exists
there but never calls back. And the `geolocation` feature itself, which
`webui/security_headers.py` denies outright in `Permissions-Policy`.

A button that silently never answers is worse than no button, and relaxing a
header that was tightened during the pentest remediation is not worth a
convenience. **Fill from timezone** covers the same need offline: a curated
`timezoneCoordinates.ts` table maps the device's IANA zone to a plausible point.
Within one zone the error is minutes of sunrise, not hours, and an unlisted zone
returns nothing rather than a wrong guess.

# Tests

| File | Covers |
|---|---|
| `tests/unit/core/test_sun.py` | The engine: invariants and the astral cross-check |
| `tests/unit/core/test_sun_provider.py` | Readiness, caching, invalidation, polar sides, manager wiring |
| `tests/unit/webui/test_sun_routes.py` | The four answers above, timezone rendering, bad input |
| `tests/unit/core/test_sun_conditions.py` | The three condition shapes, offsets, polar windows, failing open |
| `tests/unit/core/test_action_validation.py` | Save-time refusal of a sun condition with no location, and of malformed shapes |
| `tests/unit/core/test_sun_sensors.py` | Which entities exist, what they publish, what they refuse to publish, and their HA discovery |
| `tests/unit/webui/test_security_headers.py` | That the map switch moves `img-src` and nothing else |

---

# Entities

With a `location:` configured, six entities appear — over MQTT, in Home
Assistant via discovery, and in the panel through the same WebSocket events
every other sensor uses. Without one they are not created at all: an entity that
is permanently unavailable is worse than an absent one.

| Entity | Type | Value |
|---|---|---|
| `sun_elevation` | sensor, `°` | Geometric elevation, `measurement` |
| `sun_azimuth` | sensor, `°` | Bearing clockwise from true north |
| `sun_phase` | sensor | `day` … `night`, with the day's turning points as attributes |
| `sun_above_horizon` | binary_sensor | `on` / `off` |
| `sun_next_sunrise` | sensor, `timestamp` | ISO-8601, rendered by HA as "in 3 hours" |
| `sun_next_sunset` | sensor, `timestamp` | |

`sun_phase` carries `next_sunrise`, `next_sunset`, `next_dawn`, `next_dusk`,
`golden_hour`, `blue_hour` and `elevation` as attributes — what someone asking
"why did this not fire?" wants to see next to the phase, without four more
entities for values that change once a day.

```
boneio/<serial>/sensor/sun_phase
{"state": "night", "golden_hour": false, "blue_hour": false, "elevation": -26.81,
 "next_sunrise": "2026-09-18T04:12:34+00:00", "next_sunset": "2026-09-18T16:46:39+00:00", …}
```

Three behaviours worth knowing:

**They update every 60 seconds.** The Sun moves at most 0.25°/minute, so
anything faster is MQTT traffic for nothing. Each update is six dictionary
lookups — the provider has the day cached.

**Nothing is published when the value is unknowable.** A clock that has not been
set yet, or a polar season where the next sunrise is months away: the sensor
stays quiet and keeps its last value, rather than going unavailable for two
months or reporting a sunset computed for 1970.

**They are not diagnostic.** `ha_sun_sensor_message` deliberately does not set
`entity_category`, unlike the CPU and disk sensors — where the Sun is belongs on
a dashboard, not in a device's diagnostics panel.

Adding coordinates to a device that started without them brings the sensors up
on the next config reload; no restart.

# Picking the location on a map

The Location page can show an OpenStreetMap map, with the centre of the box as
the selection. It is **off by default**:

```yaml
web:
  security:
    map_tiles: true
```

## What that switch costs

Turning it on adds the OpenStreetMap tile servers to the panel's `img-src`
directive. That is a real loosening, not a formality: an image URL is an
outbound channel, so someone who already had script execution in the panel
could encode a few hundred bytes per request into a tile path and read it out of
someone else's access log. `connect-src` stays `'self'`, and nothing else in the
policy moves — there is a test that asserts exactly that.

The map is a convenience. Making it opt-in means nobody pays for it who is not
using it, and the default posture is the one the pentest remediation left.

Tiles are fetched by **your browser**, not by the controller, so this works on a
device with no route to the internet — as long as the computer you open the
panel from has one. When it does not, every tile fails and the component says so
instead of showing a grey void.

openstreetmap.org sees which area you are looking at. Map data ©
[OpenStreetMap contributors](https://www.openstreetmap.org/copyright).

## Why there is no Leaflet

`TilePicker.tsx` is about 200 lines: the Web Mercator tile maths, a drag
handler, and two zoom buttons. Leaflet would be ~45 kB of JavaScript for
markers, popups, layers and a plugin system this page never touches — and one
more dependency on a device whose supply chain is the thing the last release
spent its time on.

The centre of the box is the selection, which removes the marker, the dragging
of the marker, and the question of what happens when you drag the map instead.

## Without the map

Nothing about the page depends on it. The coordinates can be typed in, or filled
from the device's timezone with a bundled lookup table — see
`timezoneCoordinates.ts`. Both work offline and neither needs the CSP change.
