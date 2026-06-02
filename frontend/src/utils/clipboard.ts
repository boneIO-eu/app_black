/**
 * Clipboard utility with fallback for non-secure contexts (HTTP / iframe).
 *
 * `navigator.clipboard.writeText()` requires a secure context (HTTPS or localhost).
 * When the app runs inside a Home Assistant add-on iframe served over HTTP,
 * the Clipboard API silently fails — the promise resolves but nothing is
 * actually written to the clipboard.
 *
 * This helper tries the modern API first and, if it's unavailable or fails,
 * falls back to the legacy `document.execCommand('copy')` technique using a
 * temporary off-screen `<textarea>`.
 */

/**
 * Copy text to the system clipboard.
 *
 * Tries `navigator.clipboard.writeText` first; if that is not available or
 * throws, uses the legacy `execCommand('copy')` fallback.
 *
 * @param text - The string to copy.
 * @returns `true` if the copy succeeded, `false` otherwise.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // 1. Try modern Clipboard API (requires secure context)
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to legacy method
    }
  }

  // 2. Legacy fallback via temporary textarea + execCommand
  return legacyCopy(text);
}

/**
 * Legacy clipboard copy using a hidden `<textarea>` and `document.execCommand('copy')`.
 *
 * Works in non-secure contexts (HTTP iframes) where the Clipboard API is not available.
 *
 * @param text - The string to copy.
 * @returns `true` if `execCommand` reported success, `false` otherwise.
 */
function legacyCopy(text: string): boolean {
  const textarea = document.createElement('textarea');
  textarea.value = text;

  // Prevent scrolling and keep the element off-screen
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '-9999px';
  textarea.style.opacity = '0';

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  let success = false;
  try {
    success = document.execCommand('copy');
  } catch {
    // execCommand may throw in very restrictive environments
  } finally {
    document.body.removeChild(textarea);
  }
  return success;
}
