/**
 * The password prompt behind 403 `reauth_required`.
 *
 * The parts that go wrong quietly: two refused requests stacking two dialogs,
 * a retry that loops, and a dismissed prompt that swallows the error instead
 * of handing it back to the page that asked.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  isReauthRequired,
  requestReauth,
  retryAfterReauth,
  setReauthHandler,
  type ReauthOutcome,
} from '../reauth';

const refusal = () => ({
  response: {
    status: 403,
    data: { code: 'reauth_required', detail: 'Confirm your password to continue.' },
  },
});

let unregister: (() => void) | null = null;

/** A handler that stays open until the test settles it. */
function promptThatWaits() {
  let settle: (outcome: ReauthOutcome) => void = () => {};
  const handler = vi.fn(
    () =>
      new Promise<ReauthOutcome>((resolve) => {
        settle = resolve;
      }),
  );
  unregister = setReauthHandler(handler);
  return { handler, settle: (outcome: ReauthOutcome) => settle(outcome) };
}

afterEach(() => {
  unregister?.();
  unregister = null;
});

describe('isReauthRequired', () => {
  it('recognises the refusal', () => {
    expect(isReauthRequired(refusal())).toBe(true);
  });

  it('leaves every other 403 alone', () => {
    expect(isReauthRequired({ response: { status: 403, data: { code: 'forbidden' } } })).toBe(false);
    expect(isReauthRequired({ response: { status: 403, data: { code: 'reauth_failed' } } })).toBe(false);
  });

  it('is not fooled by a 401 or a network error', () => {
    expect(isReauthRequired({ response: { status: 401, data: { code: 'reauth_required' } } })).toBe(false);
    expect(isReauthRequired(new Error('Network Error'))).toBe(false);
  });
});

describe('retryAfterReauth', () => {
  it('sends the request again once the password is confirmed', async () => {
    const { settle } = promptThatWaits();
    const retry = vi.fn().mockResolvedValue('ok');

    const result = retryAfterReauth(refusal(), retry);
    settle({ ok: true });

    await expect(result).resolves.toBe('ok');
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('asks once for requests refused together', async () => {
    const { handler, settle } = promptThatWaits();
    const first = vi.fn().mockResolvedValue('first');
    const second = vi.fn().mockResolvedValue('second');

    const both = Promise.all([
      retryAfterReauth(refusal(), first),
      retryAfterReauth(refusal(), second),
    ]);
    settle({ ok: true });

    await expect(both).resolves.toEqual(['first', 'second']);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('asks again for the next refusal once the first is settled', async () => {
    const { handler, settle } = promptThatWaits();
    const first = retryAfterReauth(refusal(), vi.fn().mockResolvedValue(1));
    settle({ ok: true });
    await first;

    const second = retryAfterReauth(refusal(), vi.fn().mockResolvedValue(2));
    settle({ ok: true });
    await second;

    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('hands a dismissed prompt back as the original error, in the panel language', async () => {
    const { settle } = promptThatWaits();
    const error = refusal();
    const retry = vi.fn();

    const result = retryAfterReauth(error, retry);
    settle({ ok: false, message: 'Anulowano — ta operacja wymaga potwierdzenia hasłem.' });

    await expect(result).rejects.toBe(error);
    expect(error.response.data.detail).toBe('Anulowano — ta operacja wymaga potwierdzenia hasłem.');
    expect(retry).not.toHaveBeenCalled();
  });

  it('fails the request when nothing is there to ask', async () => {
    const retry = vi.fn();
    const error = refusal();
    await expect(retryAfterReauth(error, retry)).rejects.toBe(error);
    expect(retry).not.toHaveBeenCalled();
    await expect(requestReauth()).resolves.toEqual({ ok: false, message: '' });
  });

  it('lets the retry fail on its own instead of asking again', async () => {
    // The interceptor marks the retry, so a second refusal surfaces here as
    // a plain rejection rather than reopening the prompt.
    const { handler, settle } = promptThatWaits();
    const again = refusal();
    const result = retryAfterReauth(refusal(), () => Promise.reject(again));
    settle({ ok: true });

    await expect(result).rejects.toBe(again);
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
