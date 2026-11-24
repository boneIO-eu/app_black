/**
 * Modbus buses as the device list sees them.
 *
 * A device without `bus` is on the first bus. With more than one bus every
 * saved device names its own, so reordering the buses never moves a device.
 */

/** Ids of a `modbus` section's buses, in order; empty for anything that is not a list of buses. */
export function busIdsOf(section: unknown): string[] {
  if (!Array.isArray(section)) return [];
  return section
    .map((bus) => (bus && typeof bus === 'object' ? (bus as { id?: unknown }).id : undefined))
    .filter((id): id is string => typeof id === 'string' && id !== '');
}

/** The device with `bus` set to the first bus when there are several and it names none. */
export function withExplicitBus<T extends Record<string, unknown>>(device: T, busIds: string[]): T {
  if (busIds.length > 1 && !device.bus) return { ...device, bus: busIds[0] };
  return device;
}
