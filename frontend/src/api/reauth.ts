/**
 * Asking for the password again, for the requests that want it.
 *
 * A few requests — accounts, replacing the configuration, updates, the
 * certificate — answer 403 `reauth_required` when the session's password was
 * typed too long ago (see REAUTH_WINDOW in boneio/webui/middleware/auth.py).
 * The axios interceptor hands such a failure to retryAfterReauth(), which asks
 * the one dialog mounted at the app root and, once the password is confirmed,
 * sends the same request again with the fresh token.
 *
 * Kept free of axios and React so it can be tested on its own, and so the
 * interceptor can import it without a cycle.
 */

/** How a password prompt ended. */
export type ReauthOutcome =
  | { ok: true }
  /** Dismissed. `message` replaces the server's English detail for callers. */
  | { ok: false; message: string };

type ReauthHandler = () => Promise<ReauthOutcome>;

let handler: ReauthHandler | null = null;
let pending: Promise<ReauthOutcome> | null = null;

/**
 * Register what asks the user. The dialog does this on mount.
 *
 * @param next - Opens the prompt and settles once the user is done with it.
 * @returns Unregisters, if `next` is still the registered handler.
 */
export function setReauthHandler(next: ReauthHandler): () => void {
  handler = next;
  return () => {
    if (handler === next) handler = null;
  };
}

/**
 * Ask for the password, or join the question already on screen.
 *
 * Two requests refused at the same moment — a page that fires several at once
 * — share one prompt instead of stacking two dialogs.
 */
export function requestReauth(): Promise<ReauthOutcome> {
  if (!handler) return Promise.resolve({ ok: false, message: '' });
  if (!pending) {
    pending = handler().finally(() => {
      pending = null;
    });
  }
  return pending;
}

interface ReauthError {
  response?: { status?: number; data?: { code?: string; detail?: string } };
}

/** Whether a failed request was refused for want of a recent password. */
export function isReauthRequired(error: unknown): boolean {
  const response = (error as ReauthError)?.response;
  return response?.status === 403 && response.data?.code === 'reauth_required';
}

/**
 * Get the password confirmed, then send the request again.
 *
 * The caller passes `retry` already marked as a retry, so a second
 * `reauth_required` — a clock the server disagrees with, say — comes back as
 * an error instead of opening the prompt in a loop.
 *
 * @param error - The 403 `reauth_required` failure.
 * @param retry - Sends the original request again.
 * @returns Whatever the retried request resolves to.
 */
export async function retryAfterReauth<T>(error: unknown, retry: () => Promise<T>): Promise<T> {
  const outcome = await requestReauth();
  if (outcome.ok) return retry();

  const data = (error as ReauthError)?.response?.data;
  if (data && outcome.message) data.detail = outcome.message;
  throw error;
}
