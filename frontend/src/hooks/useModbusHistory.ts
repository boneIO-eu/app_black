import { useMemo, useRef } from 'react';
import { ModbusDeviceState } from './useWebSocket';

export interface ModbusHistoryPoint {
  timestamp: number;
  value: number;
}

const MODBUS_HISTORY_STORAGE_KEY = 'modbusHistory';

function roundHistoryValue(value: number): number {
  return Math.round(value * 100) / 100;
}

function isWriteableEntityType(entityType?: string | null): boolean {
  return entityType?.includes('select') || entityType === 'switch' || entityType === 'number';
}

function isNumericState(value: ModbusDeviceState['state']): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Check if a device should have history tracked and rendered as a sparkline.
 *
 * Shows charts for all numeric, read-only sensors that have a unit of measurement.
 * Writeable entities (select, switch, number) are excluded.
 */
export function shouldRenderHistory(device: ModbusDeviceState): boolean {
  if (isWriteableEntityType(device.entity_type)) {
    return false;
  }

  const hasUnit = typeof device.unit === 'string' && device.unit.trim().length > 0;
  if (!hasUnit) {
    return false;
  }

  return isNumericState(device.state);
}

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function parseStorage(): Record<string, ModbusHistoryPoint[]> {
  if (!canUseStorage()) {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(MODBUS_HISTORY_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw) as Record<string, ModbusHistoryPoint[]>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveStorage(data: Record<string, ModbusHistoryPoint[]>): void {
  if (!canUseStorage()) {
    return;
  }

  try {
    window.localStorage.setItem(MODBUS_HISTORY_STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Ignore quota/storage errors to avoid breaking UI rendering.
  }
}

function normalizeHistory(points: ModbusHistoryPoint[], maxPoints: number, maxAgeSeconds: number): ModbusHistoryPoint[] {
  if (!points.length) {
    return [];
  }

  const newestTimestamp = points[points.length - 1]?.timestamp || points[0].timestamp;
  const cutoff = newestTimestamp - maxAgeSeconds;
  const pruned = points
    .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value) && point.timestamp >= cutoff)
    .map((point) => ({
      timestamp: Math.floor(point.timestamp),
      value: roundHistoryValue(point.value),
    }));

  if (pruned.length <= maxPoints) {
    return pruned;
  }

  return pruned.slice(pruned.length - maxPoints);
}

export function loadModbusHistoryFromStorage(maxPoints = 300, maxAgeSeconds = 2 * 60 * 60): Map<string, ModbusHistoryPoint[]> {
  const parsed = parseStorage();
  const result = new Map<string, ModbusHistoryPoint[]>();

  Object.entries(parsed).forEach(([deviceId, points]) => {
    const normalized = normalizeHistory(Array.isArray(points) ? points : [], maxPoints, maxAgeSeconds);
    if (normalized.length > 0) {
      result.set(deviceId, normalized);
    }
  });

  return result;
}

export function persistModbusHistoryToStorage(history: Map<string, ModbusHistoryPoint[]>): void {
  const record: Record<string, ModbusHistoryPoint[]> = {};
  history.forEach((points, deviceId) => {
    if (points.length > 0) {
      record[deviceId] = points;
    }
  });
  saveStorage(record);
}

export function appendModbusHistoryPointToStorage(
  device: ModbusDeviceState,
  maxPoints = 300,
  maxAgeSeconds = 2 * 60 * 60,
): void {
  if (!shouldRenderHistory(device) || !device.timestamp || !isNumericState(device.state)) {
    return;
  }

  const parsed = parseStorage();
  const currentPoints = Array.isArray(parsed[device.id]) ? parsed[device.id] : [];
  const roundedValue = roundHistoryValue(device.state);
  const last = currentPoints[currentPoints.length - 1];

  if (last && last.timestamp === device.timestamp && last.value === roundedValue) {
    return;
  }

  const updated = [...currentPoints, { timestamp: device.timestamp, value: roundedValue }];
  parsed[device.id] = normalizeHistory(updated, maxPoints, maxAgeSeconds);
  saveStorage(parsed);
}

export function clearModbusHistoryStorage(): void {
  if (!canUseStorage()) {
    return;
  }

  try {
    window.localStorage.removeItem(MODBUS_HISTORY_STORAGE_KEY);
  } catch {
    // Ignore storage errors.
  }
}

export function useModbusHistory(
  devices: ModbusDeviceState[],
  maxPoints = 300,
  maxAgeSeconds = 2 * 60 * 60,
): Map<string, ModbusHistoryPoint[]> {
  const historyRef = useRef<Map<string, ModbusHistoryPoint[]>>(loadModbusHistoryFromStorage(maxPoints, maxAgeSeconds));

  return useMemo(() => {
    const next = new Map(historyRef.current);
    const activeIds = new Set<string>();

    for (const device of devices) {
      activeIds.add(device.id);

      if (!shouldRenderHistory(device) || !device.timestamp || !isNumericState(device.state)) {
        continue;
      }

      const history = next.get(device.id) || [];
      const last = history[history.length - 1];

      const roundedValue = roundHistoryValue(device.state);

      if (last && last.timestamp === device.timestamp && last.value === roundedValue) {
        continue;
      }

      const cutoff = device.timestamp - maxAgeSeconds;
      const pruned = history.filter((point) => point.timestamp >= cutoff);
      pruned.push({ timestamp: device.timestamp, value: roundedValue });

      const bounded = pruned.length > maxPoints ? pruned.slice(pruned.length - maxPoints) : pruned;
      next.set(device.id, bounded);
    }

    for (const key of next.keys()) {
      if (!activeIds.has(key)) {
        next.delete(key);
      }
    }

    historyRef.current = next;
    persistModbusHistoryToStorage(next);
    return next;
  }, [devices, maxAgeSeconds, maxPoints]);
}
