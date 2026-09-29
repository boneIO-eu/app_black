import { describe, expect, it } from 'vitest';
import {
  INTERRUPTED_AFTER_MS,
  POLL_MS,
  READ_RETRY_MS,
  UNCONFIRMED_POLL_MS,
  assessRun,
  nextPollDelay,
  type RunPhase,
  type RunReport,
} from './osUpdateProgress';

const unit = { running: true, last: { result: 'running' } };
const recordOnly = { running: false, last: { result: 'running' } };
const done = { running: false, last: { result: 'success' } };

/** Feed reads taken at the given browser times; null is a failed read. */
function replay(reads: [number, RunReport | null][], watchUntil = 0) {
  let missingSince: number | null = null;
  let phase: RunPhase = 'idle';
  let failures = 0;
  const out: { phase: RunPhase; delay: number | null }[] = [];
  for (const [now, report] of reads) {
    if (report) {
      failures = 0;
      ({ phase, missingSince } = assessRun(report, now, missingSince));
    } else {
      failures += 1;
    }
    out.push({ phase, delay: nextPollDelay(phase, now < watchUntil, failures) });
  }
  return out;
}

describe('OS update progress', () => {
  it('keeps polling through a moment the unit does not show', () => {
    const out = replay([[0, unit], [3000, recordOnly], [15_000, unit], [18_000, done]]);
    expect(out.map(o => o.phase)).toEqual(['running', 'unconfirmed', 'running', 'idle']);
    expect(out.map(o => o.delay)).toEqual([POLL_MS, UNCONFIRMED_POLL_MS, POLL_MS, null]);
  });

  it('calls a record without its unit interrupted only after a while, and keeps watching', () => {
    const out = replay([
      [0, recordOnly],
      [INTERRUPTED_AFTER_MS - 1, recordOnly],
      [INTERRUPTED_AFTER_MS, recordOnly],
    ]);
    expect(out.map(o => o.phase)).toEqual(['unconfirmed', 'unconfirmed', 'interrupted']);
    expect(out[2].delay).toBe(UNCONFIRMED_POLL_MS);
  });

  it('starts the grace period over when the unit shows again in between', () => {
    const out = replay([[0, recordOnly], [50_000, unit], [60_000, recordOnly], [110_000, recordOnly]]);
    expect(out.map(o => o.phase)).toEqual(['unconfirmed', 'running', 'unconfirmed', 'unconfirmed']);
  });

  it('retries failed reads mid-run with a growing wait', () => {
    const out = replay([[0, unit], [3000, null], [8000, null], [18_000, null], [38_000, null], [68_000, null]]);
    expect(out.slice(1).map(o => o.delay)).toEqual([...READ_RETRY_MS, READ_RETRY_MS[3]]);
    expect(out[5].phase).toBe('running');
  });

  it('stops after a failed read when nothing runs', () => {
    expect(replay([[0, done], [5000, null]])[1].delay).toBeNull();
  });

  it('polls right after a start even before the unit shows', () => {
    expect(replay([[0, done]], 15_000)[0].delay).toBe(POLL_MS);
  });
});
