/**
 * The debug capture window, shared by everything that shows it.
 *
 * Two controls used to raise the log level: the bug button in the log viewer,
 * which set DEBUG until someone remembered to set it back, and the support
 * card, which opens a window that closes itself. Two buttons for one piece of
 * process-global state disagree the moment either is used, so they are now the
 * same thing — and the one that expires won, because a device left at debug
 * logs roughly twenty MQTT publishes a second and buries the history someone
 * will want tomorrow.
 *
 * The state lives in a module-level store rather than in each hook instance.
 * A hook holding its own useState gives every caller a private copy, so
 * opening the window from the card left the log viewer's button still reading
 * "off" — which is exactly the disagreement this was meant to remove. A store
 * also means no provider to forget: the two components are on one page today
 * and may not be tomorrow.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import api from '@/api/axios';

export interface CaptureState {
  active: boolean;
  seconds_remaining: number;
  started: number | null;
  busy: boolean;
  error: string | null;
}

const CLOSED: CaptureState = {
  active: false,
  seconds_remaining: 0,
  started: null,
  busy: false,
  error: null,
};

let state: CaptureState = CLOSED;
const listeners = new Set<() => void>();
let ticker: ReturnType<typeof setInterval> | null = null;

function emit(next: Partial<CaptureState>): void {
  state = { ...state, ...next };
  listeners.forEach(listener => listener());
  syncTicker();
}

/** Run the countdown only while a window is open, and only once. */
function syncTicker(): void {
  if (state.active && ticker === null) {
    ticker = setInterval(() => {
      const remaining = state.seconds_remaining - 1;
      if (remaining <= 0) {
        emit({ active: false, seconds_remaining: 0, started: null });
      } else {
        emit({ seconds_remaining: remaining });
      }
    }, 1000);
  } else if (!state.active && ticker !== null) {
    clearInterval(ticker);
    ticker = null;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

async function request(
  call: () => Promise<{ data: Omit<CaptureState, 'busy' | 'error'> }>,
): Promise<void> {
  emit({ busy: true, error: null });
  try {
    const { data } = await call();
    emit({ ...data, busy: false });
  } catch {
    emit({ busy: false, error: 'failed' });
  }
}

export async function refreshCapture(): Promise<void> {
  try {
    const { data } = await api.get<Omit<CaptureState, 'busy' | 'error'>>(
      '/api/diagnostics/capture',
    );
    emit({ ...data, error: null });
  } catch {
    emit(CLOSED);
  }
}

export function useCaptureWindow(defaultMinutes = 10) {
  const current = useSyncExternalStore(subscribe, () => state, () => state);

  useEffect(() => {
    // Every mount re-reads it: the window may have been opened from another
    // tab, or have expired while this page was closed.
    void refreshCapture();
  }, []);

  const open = useCallback(
    (minutes: number = defaultMinutes) =>
      request(() => api.post('/api/diagnostics/capture', { minutes })),
    [defaultMinutes],
  );

  const close = useCallback(() => request(() => api.delete('/api/diagnostics/capture')), []);

  const remaining = current.seconds_remaining;
  const clock = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;

  return {
    state: current,
    clock,
    busy: current.busy,
    error: current.error,
    open,
    close,
    refresh: refreshCapture,
  };
}
