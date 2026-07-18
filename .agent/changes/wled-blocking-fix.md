# WLED: DNS .local Resolution + Blocking Input Events Fix

## Problem 1: `.local` hostnames not resolved (root cause)
`ping wled-sypialnia.local` works from SSH, but boneIO app gets
`Name or service not known`. 

**Root cause**: aiohttp auto-selects `AsyncResolver` (c-ares) when `aiodns`
is installed. c-ares resolves DNS directly (bypassing NSS/Name Service Switch),
so it **cannot** resolve mDNS `.local` names through Avahi.

**Fix**: Force `ThreadedResolver` which uses system `getaddrinfo()` → NSS → Avahi.

## Problem 2: Unreachable WLED blocks ALL inputs
When a WLED device becomes unreachable (DNS failure or network timeout),
clicking a button that triggers a WLED action **blocks ALL other input events**
for up to 10 seconds (the HTTP timeout duration).

### Root Cause
The event processing chain is:
```
EventBus worker (sequential!) → handle_input_event → execute_actions 
→ _execute_single_action → remote_devices.control_output 
→ WLEDRemoteDevice.control_light → _send_state → session.post() → DNS timeout!
```

The EventBus worker processes events **sequentially** in `_event_worker()`:
```python
async def _event_worker(self):
    while not self._shutting_down:
        event = await self._event_queue.get()
        await self._handle_event(event)  # ← BLOCKS queue until done!
```

When `session.post()` hangs on DNS resolution for a `.local` hostname,
the worker is blocked and no other input events are processed.

### Symptoms from logs
- ~2-5 seconds gap between WLED error and next detected click
- Multiple clicks "queued" and processed in burst after WLED timeout

## Fix

### 1. Reduced WLED HTTP timeout (wled.py)
- `total`: 10s → **3s**
- `connect`: added **2s** limit (DNS + TCP handshake)

### 2. Fire-and-forget pattern for WLED control (remote.py + wled.py)
Instead of `await device.control_light(...)` which blocks the EventBus,
WLED commands are now dispatched as background tasks:

```python
# Before (blocking):
return await cast(Any, device).control_light(...)

# After (non-blocking):
wled_device.control_light_fire_and_forget(...)
return True  # Optimistic
```

`control_light_fire_and_forget()` creates an `asyncio.create_task()`
that runs independently. Failures are logged but don't propagate.

## Files Changed
- `boneio/core/remote/wled.py` — Reduced timeout, added fire-and-forget methods
- `boneio/core/manager/remote.py` — WLED dispatch uses fire-and-forget

## Impact
- WLED commands are "optimistic" — the caller assumes success
- If WLED is unreachable, error is logged but other inputs work normally
- No behavior change when WLED is reachable (3s timeout is still plenty)
