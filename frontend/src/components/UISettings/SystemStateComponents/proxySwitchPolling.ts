/**
 * Whether the Caddy switch card keeps polling after a read.
 *
 * The switch recreates Caddy, which the panel is served through, so reads fail
 * while it runs. A failed read therefore must not stop the polling when the
 * last state seen was running (the automatic switch needs no click), nor when
 * the admin has just started one.
 */
export function keepPolling(
  data: { switch?: { running?: boolean } | null } | null,
  lastRunning: boolean,
  started: boolean,
): boolean {
  return data === null ? lastRunning || started : data.switch?.running === true;
}
