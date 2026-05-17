/**
 * Live Jinja2 template preview against a sample MQTT payload.
 *
 * Debounces backend round-trips by 300ms so each keystroke in the template
 * editor doesn't spam ``/api/mqtt/test-template``. Cancels in-flight requests
 * when the inputs change before the response arrives.
 *
 * Why backend eval? boneIO uses real Jinja2 server-side. Doing the preview
 * on the backend guarantees parity with what ``MQTTGenericInput`` will
 * actually produce at runtime — a JS port (e.g. nunjucks) would risk
 * silent divergence on edge cases.
 */
import { useEffect, useRef, useState } from 'react';
import axios from '@/api/axios';

const DEBOUNCE_MS = 300;

export interface TemplatePreviewResult {
  result: string | null;
  error: string | null;
  /** Parsed JSON if the payload was JSON — convenient for the inspector. */
  valueJson: unknown;
}

export interface UseJinjaPreviewReturn {
  preview: TemplatePreviewResult | null;
  isLoading: boolean;
  /** Network/server failure (distinct from a template error inside `preview.error`). */
  fetchError: string | null;
}

/**
 * Returns the live evaluation of ``template`` against ``payload`` (debounced).
 * Pass empty ``template`` to skip evaluation (returns ``null``).
 */
export function useJinjaPreview(template: string, payload: string): UseJinjaPreviewReturn {
  const [preview, setPreview] = useState<TemplatePreviewResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!template.trim()) {
      setPreview(null);
      setIsLoading(false);
      setFetchError(null);
      return;
    }

    const myId = ++requestIdRef.current;
    setIsLoading(true);
    setFetchError(null);

    const timeoutId = window.setTimeout(async () => {
      try {
        const { data } = await axios.post<{
          result: string | null;
          value_json: unknown;
          error: string | null;
        }>('/api/mqtt/test-template', { template, payload });
        if (requestIdRef.current !== myId) return;
        setPreview({
          result: data.result,
          error: data.error,
          valueJson: data.value_json,
        });
      } catch (e: unknown) {
        if (requestIdRef.current !== myId) return;
        const err = e as { response?: { data?: { detail?: string } }; message?: string };
        setFetchError(err?.response?.data?.detail || err?.message || String(e));
        setPreview(null);
      } finally {
        if (requestIdRef.current === myId) {
          setIsLoading(false);
        }
      }
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [template, payload]);

  return { preview, isLoading, fetchError };
}
