/**
 * Generic sensor history hook.
 * 
 * Tracks value history for any numeric sensor over time, storing data
 * in localStorage for persistence across page reloads.
 * 
 * Can be used for ADC sensors, temperature sensors, INA219, etc.
 */
import { useMemo, useRef } from 'react';
import type { HistoryPoint } from '../components/Sparkline';

/** Sensor-like data shape — minimum fields needed for history tracking. */
export interface HistoryCapableSensor {
  id: string;
  state: number | string | null;
  timestamp: number | null;
  unit?: string | null;
}

const SENSOR_HISTORY_STORAGE_KEY = 'sensorHistory';

function roundValue(value: number): number {
  return Math.round(value * 100) / 100;
}

function isNumericState(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function parseStorage(): Record<string, HistoryPoint[]> {
  if (!canUseStorage()) return {};

  try {
    const raw = window.localStorage.getItem(SENSOR_HISTORY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, HistoryPoint[]>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveStorage(data: Record<string, HistoryPoint[]>): void {
  if (!canUseStorage()) return;

  try {
    window.localStorage.setItem(SENSOR_HISTORY_STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Ignore quota/storage errors
  }
}

function normalizeHistory(
  points: HistoryPoint[],
  maxPoints: number,
  maxAgeSeconds: number,
): HistoryPoint[] {
  if (!points.length) return [];

  const newestTimestamp = points[points.length - 1]?.timestamp || points[0].timestamp;
  const cutoff = newestTimestamp - maxAgeSeconds;
  const pruned = points
    .filter((p) => Number.isFinite(p.timestamp) && Number.isFinite(p.value) && p.timestamp >= cutoff)
    .map((p) => ({
      timestamp: Math.floor(p.timestamp),
      value: roundValue(p.value),
    }));

  return pruned.length <= maxPoints ? pruned : pruned.slice(pruned.length - maxPoints);
}

function loadFromStorage(
  maxPoints: number,
  maxAgeSeconds: number,
): Map<string, HistoryPoint[]> {
  const parsed = parseStorage();
  const result = new Map<string, HistoryPoint[]>();

  Object.entries(parsed).forEach(([id, points]) => {
    const normalized = normalizeHistory(Array.isArray(points) ? points : [], maxPoints, maxAgeSeconds);
    if (normalized.length > 0) {
      result.set(id, normalized);
    }
  });

  return result;
}

function persistToStorage(history: Map<string, HistoryPoint[]>): void {
  const record: Record<string, HistoryPoint[]> = {};
  history.forEach((points, id) => {
    if (points.length > 0) {
      record[id] = points;
    }
  });
  saveStorage(record);
}

/**
 * Hook that tracks value history for an array of sensors.
 * 
 * Returns a Map from sensor ID to an array of HistoryPoint.
 * History is persisted in localStorage and survives page reloads.
 * 
 * @param sensors - Array of sensor data objects
 * @param maxPoints - Maximum number of points to keep per sensor (default: 300)
 * @param maxAgeSeconds - Maximum age in seconds for data points (default: 2 hours)
 */
export function useSensorHistory(
  sensors: HistoryCapableSensor[],
  maxPoints = 300,
  maxAgeSeconds = 2 * 60 * 60,
): Map<string, HistoryPoint[]> {
  const historyRef = useRef<Map<string, HistoryPoint[]>>(
    loadFromStorage(maxPoints, maxAgeSeconds),
  );

  return useMemo(() => {
    const next = new Map(historyRef.current);
    const activeIds = new Set<string>();

    for (const sensor of sensors) {
      activeIds.add(sensor.id);

      if (!sensor.timestamp || !isNumericState(sensor.state)) {
        continue;
      }

      const history = next.get(sensor.id) || [];
      const last = history[history.length - 1];
      const rounded = roundValue(sensor.state);

      // Skip if the point is identical to the last one
      if (last && last.timestamp === sensor.timestamp && last.value === rounded) {
        continue;
      }

      const cutoff = sensor.timestamp - maxAgeSeconds;
      const pruned = history.filter((p) => p.timestamp >= cutoff);
      pruned.push({ timestamp: sensor.timestamp, value: rounded });

      const bounded = pruned.length > maxPoints ? pruned.slice(pruned.length - maxPoints) : pruned;
      next.set(sensor.id, bounded);
    }

    // Remove sensors that are no longer active
    for (const key of next.keys()) {
      if (!activeIds.has(key)) {
        next.delete(key);
      }
    }

    historyRef.current = next;
    persistToStorage(next);
    return next;
  }, [sensors, maxAgeSeconds, maxPoints]);
}
