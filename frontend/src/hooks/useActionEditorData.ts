import { useEffect, useState } from 'react';
import axios from '@/api/axios';
import { fetchConfig } from '@/api/configCache';
import type { BinarySensorEntity, CoverEntity, OutputEntity } from '@/types/config';
import type { Area, RemoteDevice } from '@/components/UISettings/ActionFields/types';

/** Action types an input can run — mirrors boneio/schema/actions.yaml. */
export const INPUT_ACTION_TYPES = [
  'output', 'cover', 'virtual_switch', 'mqtt',
  'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover',
];

/** Commands for an output action, as the input editor offers them. */
export const ACTION_OUTPUT_OPTIONS = [
  'TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE',
  'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET',
];

/** Commands for a cover action, as the input editor offers them. */
export const ACTION_COVER_OPTIONS = [
  'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE',
  'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE',
];

/** The entity lists ActionFields needs, in the shape Settings passes them. */
export interface ActionEditorData {
  allOutputs: OutputEntity[];
  allOutputGroups: Record<string, unknown>[];
  allCovers: CoverEntity[];
  allAreas: Area[];
  allRemoteDevices: RemoteDevice[];
  allBinarySensors: BinarySensorEntity[];
  allRemoteInputs: Record<string, unknown>[];
  allVirtualSwitches: Record<string, unknown>[];
}

const EMPTY: ActionEditorData = {
  allOutputs: [],
  allOutputGroups: [],
  allCovers: [],
  allAreas: [],
  allRemoteDevices: [],
  allBinarySensors: [],
  allRemoteInputs: [],
  allVirtualSwitches: [],
};

const list = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

/**
 * Add the WLED effects, palettes and segments to each WLED remote device.
 *
 * They live in .wled_cache.json rather than config.yaml, and without them the
 * effect and preset pickers of a remote output action have nothing to offer.
 * Mutates the devices in place. Failing to reach the cache is not an error:
 * the pickers are simply hidden.
 */
export async function enrichRemoteDevicesWithWled(devices: unknown): Promise<void> {
  if (!Array.isArray(devices)) return;
  try {
    const { data: wledCache } = await axios.get<Record<string, Record<string, unknown[]>>>('/api/remote-devices/wled_info');
    if (!wledCache || typeof wledCache !== 'object') return;
    for (const device of devices) {
      if ((device?.protocol === 'wled' || device?.wled) && device?.id && wledCache[device.id]) {
        const cached = wledCache[device.id];
        if (!device.wled) device.wled = {};
        if (cached.effects) device.wled.effects = cached.effects;
        if (cached.palettes) device.wled.palettes = cached.palettes;
        if (cached.segments) device.wled.segments = cached.segments;
      }
    }
  } catch {
    console.debug('WLED cache not available, effect selectors will be hidden');
  }
}

/**
 * Everything the shared action editor needs to pick a target, read from the
 * configuration the way Settings reads it.
 *
 * Teach Mode and the quick action used the live WebSocket lists instead, which
 * carry no output groups, no virtual switches, no remote devices' lights and
 * no condition entities — so they could only ever offer a subset of what the
 * input editor does. Using the same source is what makes the two editors the
 * same editor.
 *
 * @param enabled - Loads when true (the dialog is open); keeps the last data.
 */
export function useActionEditorData(enabled: boolean): { data: ActionEditorData; loading: boolean } {
  const [data, setData] = useState<ActionEditorData>(EMPTY);
  // Loading only until the first answer: a reopen refreshes behind the lists
  // already shown rather than blanking them.
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      const response = (await fetchConfig()) as { config?: Record<string, unknown> };
      const config = response?.config || {};
      // A copy: the WLED enrichment writes into the devices, and the cache
      // object is shared with Settings.
      const remoteDevices = JSON.parse(JSON.stringify(list(config.remote_devices)));
      await enrichRemoteDevicesWithWled(remoteDevices);
      if (cancelled) return;
      setData({
        allOutputs: [...list<OutputEntity>(config.output), ...list<OutputEntity>(config.remote_outputs)],
        allOutputGroups: list(config.output_group),
        allCovers: list<CoverEntity>(config.cover),
        allAreas: list<Area>(config.areas),
        allRemoteDevices: remoteDevices,
        allBinarySensors: list<BinarySensorEntity>(config.binary_sensor),
        allRemoteInputs: list(config.remote_inputs),
        allVirtualSwitches: list(config.virtual_switch),
      });
      setLoaded(true);
    })().catch(() => {
      if (!cancelled) setLoaded(true);
    });
    return () => { cancelled = true; };
  }, [enabled]);

  return { data, loading: enabled && !loaded };
}
