/**
 * A readable sentence from a failed API call.
 *
 * FastAPI's own validation errors (422) carry `detail` as a list of
 * `{type, loc, msg, input}` objects, not a string. Rendered as-is it is an
 * object in JSX, which takes the whole page down instead of showing an error.
 */
export function apiErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const entry = item as { msg?: unknown; loc?: unknown };
        const where = Array.isArray(entry.loc) ? entry.loc.filter((p) => p !== 'body').join('.') : '';
        const msg = typeof entry.msg === 'string' ? entry.msg : JSON.stringify(item);
        return where ? `${where}: ${msg}` : msg;
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail);
  const message = (err as Error)?.message;
  return typeof message === 'string' && message ? message : String(err);
}
