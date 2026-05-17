/**
 * Scan the MQTT broker for topics matching a subscription pattern.
 *
 * Wraps the ``POST /api/mqtt/scan`` endpoint with loading/error state.
 * Cancellation: if a new scan starts while one is in flight, the previous
 * one's result is ignored.
 */
import { useCallback, useRef, useState } from 'react';
import axios from '@/api/axios';

import type { ScanRequest, ScanResponse, ScanResult } from '../types/scan';

export interface UseMqttScanReturn {
  isScanning: boolean;
  results: ScanResult[];
  error: string | null;
  lastPattern: string | null;
  lastDuration: number | null;
  scan: (request: ScanRequest) => Promise<void>;
  reset: () => void;
}

export function useMqttScan(): UseMqttScanReturn {
  const [isScanning, setIsScanning] = useState(false);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastPattern, setLastPattern] = useState<string | null>(null);
  const [lastDuration, setLastDuration] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const scan = useCallback(async (request: ScanRequest) => {
    const myId = ++requestIdRef.current;
    setIsScanning(true);
    setError(null);
    setLastPattern(request.pattern);
    setLastDuration(request.duration_s);
    try {
      const { data } = await axios.post<ScanResponse>(
        '/api/mqtt/scan',
        request,
        // Backend can hold the request open for the full duration_s; allow a buffer.
        { timeout: (request.duration_s + 10) * 1000 },
      );
      if (requestIdRef.current === myId) {
        setResults(data.topics);
      }
    } catch (e: unknown) {
      if (requestIdRef.current === myId) {
        const err = e as { response?: { data?: { detail?: string } }; message?: string };
        setError(err?.response?.data?.detail || err?.message || String(e));
        setResults([]);
      }
    } finally {
      if (requestIdRef.current === myId) {
        setIsScanning(false);
      }
    }
  }, []);

  const reset = useCallback(() => {
    requestIdRef.current++;
    setResults([]);
    setError(null);
    setIsScanning(false);
    setLastPattern(null);
    setLastDuration(null);
  }, []);

  return { isScanning, results, error, lastPattern, lastDuration, scan, reset };
}
