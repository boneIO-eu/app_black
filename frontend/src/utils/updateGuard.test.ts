import { describe, expect, it } from 'vitest';
import {
  UPDATE_MARK_TTL_MS,
  alreadyReloadedFor,
  clearUpdateMark,
  noteReloadFor,
  normalizeVersion,
  panelState,
  readUpdateMark,
  scopedKey,
  updateArrived,
  writeUpdateMark,
  type MarkStorage,
  type UpdateMark,
} from './updateGuard';

function fakeStorage(): MarkStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const NOW = 1_790_000_000_000;
const mark = (over: Partial<UpdateMark> = {}): UpdateMark => ({
  startedAt: NOW - 60_000,
  fromVersion: '1.6.0.dev20',
  toVersion: '1.6.0.dev21',
  ...over,
});

describe('panelState', () => {
  it('calls a panel built for another version stale, whatever the mark says', () => {
    expect(panelState({ reachable: true, serverVersion: '1.6.0.dev20', panelVersion: '1.5.5', mark: null }))
      .toBe('stale_panel');
    expect(panelState({ reachable: true, serverVersion: '1.6.0.dev21', panelVersion: '1.6.0.dev20', mark: mark() }))
      .toBe('stale_panel');
  });

  it('is fine when the versions match', () => {
    expect(panelState({ reachable: true, serverVersion: '1.6.0.dev20', panelVersion: '1.6.0.dev20', mark: null }))
      .toBe('ok');
  });

  it('skips the version check without a build version (dev server)', () => {
    expect(panelState({ reachable: true, serverVersion: '1.6.0.dev20', panelVersion: null, mark: null }))
      .toBe('ok');
  });

  it('says an update is running when a silent controller was just told to update', () => {
    expect(panelState({ reachable: false, serverVersion: null, panelVersion: '1.6.0.dev20', mark: mark() }))
      .toBe('updating');
  });

  it('only guesses when nothing is known about an update', () => {
    expect(panelState({ reachable: false, serverVersion: null, panelVersion: '1.6.0.dev20', mark: null }))
      .toBe('probably_updating');
  });

  it('reports a failed update: restarted, and back on the old version', () => {
    expect(panelState({
      reachable: true, serverVersion: '1.6.0.dev20', panelVersion: '1.6.0.dev20', mark: mark({ wentDown: true }),
    })).toBe('update_failed');
  });

  it('does not call an update failed before the controller has restarted', () => {
    // pip is still installing and the old process still answers.
    expect(panelState({
      reachable: true, serverVersion: '1.6.0.dev20', panelVersion: '1.6.0.dev20', mark: mark(),
    })).toBe('ok');
  });
});

describe('update mark', () => {
  it('round-trips and expires after an hour', () => {
    const storage = fakeStorage();
    writeUpdateMark(storage, undefined, mark());
    expect(readUpdateMark(storage, undefined, NOW)).toEqual(mark());
    expect(readUpdateMark(storage, undefined, NOW + UPDATE_MARK_TTL_MS)).toBeNull();
  });

  it('is kept per device behind a proxy', () => {
    const storage = fakeStorage();
    writeUpdateMark(storage, '/api/hassio_ingress/x/proxy/2', mark());
    expect(readUpdateMark(storage, '/api/hassio_ingress/x/proxy/3', NOW)).toBeNull();
    expect(storage.data.has('boneio-update-proxy-2')).toBe(true);
  });

  it('keeps the key the 1.5.x panel writes', () => {
    expect(scopedKey('boneio-update', undefined)).toBe('boneio-update');
  });

  it('treats garbage and a refusing browser as no mark', () => {
    const storage = fakeStorage();
    storage.setItem('boneio-update', '{not json');
    expect(readUpdateMark(storage, undefined, NOW)).toBeNull();
    const refusing: MarkStorage = {
      getItem: () => { throw new Error('denied'); },
      setItem: () => { throw new Error('denied'); },
      removeItem: () => { throw new Error('denied'); },
    };
    expect(readUpdateMark(refusing, undefined, NOW)).toBeNull();
    writeUpdateMark(refusing, undefined, mark());
    clearUpdateMark(refusing, undefined);
  });

  it('is cleared', () => {
    const storage = fakeStorage();
    writeUpdateMark(storage, undefined, mark());
    clearUpdateMark(storage, undefined);
    expect(readUpdateMark(storage, undefined, NOW)).toBeNull();
  });
});

describe('updateArrived', () => {
  it('waits for the version asked for, with or without the tag v', () => {
    expect(updateArrived(mark({ toVersion: 'v1.6.0.dev21' }), '1.6.0.dev21')).toBe(true);
    expect(updateArrived(mark(), '1.6.0.dev20')).toBe(false);
  });

  it('takes any other version when the latest was asked for', () => {
    expect(updateArrived(mark({ toVersion: null }), '1.6.0.dev22')).toBe(true);
    expect(updateArrived(mark({ toVersion: null }), '1.6.0.dev20')).toBe(false);
  });
});

describe('reload once per version', () => {
  it('allows one reload and then stops', () => {
    const session = fakeStorage();
    expect(alreadyReloadedFor(session, '1.6.0.dev21')).toBe(false);
    noteReloadFor(session, '1.6.0.dev21');
    expect(alreadyReloadedFor(session, '1.6.0.dev21')).toBe(true);
    expect(alreadyReloadedFor(session, '1.6.0.dev22')).toBe(false);
  });
});

it('normalizes versions', () => {
  expect(normalizeVersion('v1.6.0')).toBe('1.6.0');
  expect(normalizeVersion(' 1.6.0 ')).toBe('1.6.0');
  expect(normalizeVersion(null)).toBeNull();
});
