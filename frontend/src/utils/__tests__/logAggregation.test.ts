import { describe, it, expect } from 'vitest';
import { aggregateLogs, fingerprint, type LogLine } from '../logAggregation';

/** Builds a line; index doubles as a readable timestamp. */
function line(level: string, message: string, at = '0'): LogLine {
  return { level, message, timestamp: at };
}

const MODBUS_ERROR = (device: number) =>
  `ERROR (modbus_worker_0) [boneio.modbus.client] Error reading registers from device ${device} at address 0: Modbus Error: [Input/Output] ERROR: No response received of the last requests (default: retries+3), CLOSING CONNECTION.`;

const MODBUS_WARNING = (device: number, sleep: string) =>
  `WARNING (MainThread) [boneio.modbus.coordinator] Can't fetch data from modbus device ${device}_boneio-edge-temp (group 0, base=0). Will sleep for ${sleep} seconds`;

describe('aggregateLogs', () => {
  it('folds a run of identical lines into one', () => {
    const result = aggregateLogs([
      line('ERROR', 'boom'),
      line('ERROR', 'boom'),
      line('ERROR', 'boom'),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].count).toBe(3);
  });

  it('folds repeats that are not next to each other', () => {
    // The defect this replaced: an unrelated line between two repeats ended
    // the run, and nothing after it was folded.
    const result = aggregateLogs([
      line('ERROR', 'boom'),
      line('INFO', 'something else entirely'),
      line('ERROR', 'boom'),
      line('INFO', 'another unrelated thing'),
      line('ERROR', 'boom'),
    ]);

    const boom = result.find(entry => entry.message === 'boom');
    expect(boom?.count).toBe(3);
    expect(result).toHaveLength(3);
  });

  it('folds the interleaved pairs from a failing Modbus bus', () => {
    // Two devices failing, alternating, with an INFO through the middle —
    // the screenshot that prompted this. Four distinct messages, nine lines.
    const lines = [
      line('ERROR', MODBUS_ERROR(1)),
      line('WARNING', MODBUS_WARNING(1, '7.5')),
      line('ERROR', MODBUS_ERROR(10)),
      line('WARNING', MODBUS_WARNING(10, '45.0')),
      line('ERROR', MODBUS_ERROR(1)),
      line('INFO', '[boneio.core.auth.store] users.json changed on disk'),
      line('WARNING', MODBUS_WARNING(1, '7.5')),
      line('ERROR', MODBUS_ERROR(10)),
      line('WARNING', MODBUS_WARNING(10, '45.0')),
    ];

    const result = aggregateLogs(lines);

    expect(result).toHaveLength(5);
    expect(result.filter(entry => entry.count === 2)).toHaveLength(4);
  });

  it('keeps different devices apart', () => {
    // "device 1 is failing" and "device 10 is failing" are two problems.
    const result = aggregateLogs([
      line('ERROR', MODBUS_ERROR(1)),
      line('ERROR', MODBUS_ERROR(10)),
    ]);

    expect(result).toHaveLength(2);
  });

  it('ignores the thread name, which changes between identical lines', () => {
    const result = aggregateLogs([
      line('ERROR', 'ERROR (modbus_worker_0) [x] read failed'),
      line('ERROR', 'ERROR (modbus_worker_1) [x] read failed'),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].count).toBe(2);
  });

  it('ignores an elapsed duration', () => {
    const result = aggregateLogs([
      line('WARNING', 'Will sleep for 7.5 seconds'),
      line('WARNING', 'Will sleep for 45.0 seconds'),
    ]);

    expect(result).toHaveLength(1);
  });

  it('does not fold across levels', () => {
    // The same text at ERROR and at WARNING is not the same event.
    const result = aggregateLogs([line('ERROR', 'same text'), line('WARNING', 'same text')]);
    expect(result).toHaveLength(2);
  });

  it('records the first and the last time it was seen', () => {
    const result = aggregateLogs([
      line('ERROR', 'boom', '10:00:00'),
      line('ERROR', 'boom', '10:00:05'),
      line('ERROR', 'boom', '10:00:09'),
    ]);

    expect(result[0].firstTimestamp).toBe('10:00:00');
    // The row sits at the newest occurrence, so that is the time it shows.
    expect(result[0].timestamp).toBe('10:00:09');
  });

  it('keeps the text of the first occurrence', () => {
    // The numbers the fingerprint ignored still have to read as a real line.
    const result = aggregateLogs([
      line('WARNING', 'Will sleep for 7.5 seconds'),
      line('WARNING', 'Will sleep for 45.0 seconds'),
    ]);
    expect(result[0].message).toBe('Will sleep for 7.5 seconds');
  });

  it('places a group at its most recent occurrence, not its first', () => {
    // Anchored at the first, a message that starts repeating would sit
    // halfway up the page ticking a counter while the tail looked dead.
    const result = aggregateLogs([
      line('ERROR', 'old and repeating', '1'),
      line('INFO', 'quiet', '2'),
      line('ERROR', 'old and repeating', '3'),
    ]);

    expect(result.map(entry => entry.message)).toEqual(['quiet', 'old and repeating']);
  });

  it('leaves a window with nothing repeated exactly as it was', () => {
    const lines = [line('INFO', 'a', '1'), line('INFO', 'b', '2'), line('INFO', 'c', '3')];
    const result = aggregateLogs(lines);

    expect(result.map(entry => entry.message)).toEqual(['a', 'b', 'c']);
    expect(result.every(entry => entry.count === 1)).toBe(true);
  });

  it('handles an empty window', () => {
    expect(aggregateLogs([])).toEqual([]);
  });
});

describe('fingerprint', () => {
  it('leaves an ordinary message alone', () => {
    expect(fingerprint('[boneio.modbus.client] read failed')).toBe(
      '[boneio.modbus.client] read failed',
    );
  });

  it('keeps addresses and device numbers', () => {
    const shape = fingerprint(MODBUS_ERROR(10));
    expect(shape).toContain('device 10');
    expect(shape).toContain('address 0');
  });
});
