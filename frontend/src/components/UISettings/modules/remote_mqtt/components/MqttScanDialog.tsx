/**
 * MqttScanDialog — modal "scan broker → browse discovered topics" UX.
 *
 * Phase 2 scope: scan + browse + filter. Topic→entity mapping flow lives
 * in Phase 6 (`MqttRemoteInputForm` / `MqttRemoteOutputForm`).
 *
 * All state and fetching is in `useMqttScan` — this component is pure
 * Presentational so an alternative skin can swap it without rewriting logic.
 */
import React, { useMemo, useState } from 'react';
import { FaSync, FaSearch, FaExclamationTriangle, FaChevronRight, FaChevronDown } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { useMqttScan } from '../hooks/useMqttScan';
import { isValidSubscriptionPattern } from '../helpers/topicValidation';
import type { PayloadType, ScanResult } from '../types/scan';
import MqttTopicInspector from './MqttTopicInspector';

const MIN_DURATION_S = 1;
const MAX_DURATION_S = 60;
const DEFAULT_DURATION_S = 10;
const DEFAULT_PATTERN = '#';
const MAX_VISIBLE_RESULTS = 200;
const PAYLOAD_PREVIEW_CHARS = 80;

export interface MqttScanDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional pre-fill for the pattern input (e.g. when called from a device row). */
  initialPattern?: string;
}

const TYPE_BADGE_CLASS: Record<PayloadType, string> = {
  json:    'badge-info',
  binary:  'badge-success',
  numeric: 'badge-warning',
  string:  'badge-ghost',
  empty:   'badge-neutral',
};

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n) + '…';
}

const MqttScanDialog: React.FC<MqttScanDialogProps> = ({ open, onOpenChange, initialPattern }) => {
  const { t } = useTranslation();
  const [pattern, setPattern] = useState(initialPattern ?? DEFAULT_PATTERN);
  const [durationS, setDurationS] = useState<number>(DEFAULT_DURATION_S);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const scan = useMqttScan();

  const toggleExpand = (topic: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  };

  const patternValid = isValidSubscriptionPattern(pattern.trim());
  const durationValid = durationS >= MIN_DURATION_S && durationS <= MAX_DURATION_S;
  const canScan = patternValid && durationValid && !scan.isScanning;

  const handleScan = () => {
    if (!canScan) return;
    void scan.scan({ pattern: pattern.trim(), duration_s: durationS });
  };

  const filteredResults = useMemo<ScanResult[]>(() => {
    if (!filter.trim()) return scan.results;
    const needle = filter.toLowerCase();
    return scan.results.filter(
      (r) =>
        r.topic.toLowerCase().includes(needle) ||
        r.last_payload.toLowerCase().includes(needle),
    );
  }, [scan.results, filter]);

  const visibleResults = filteredResults.slice(0, MAX_VISIBLE_RESULTS);
  const truncatedBy = filteredResults.length - visibleResults.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{t('remote_mqtt.scan_dialog_title') || 'Scan MQTT broker'}</DialogTitle>
          <DialogDescription>
            {t('remote_mqtt.scan_dialog_description') ||
              'Subscribe to a topic pattern for a few seconds to discover what the broker is publishing.'}
          </DialogDescription>
        </DialogHeader>

        {/* Scan controls */}
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px_auto] gap-2 items-end">
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text font-medium">
                {t('remote_mqtt.pattern_label') || 'Topic pattern'}
              </span>
            </label>
            <input
              type="text"
              className={`input input-bordered input-sm font-mono ${!patternValid ? 'input-error' : ''}`}
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="n64/88/#"
              disabled={scan.isScanning}
            />
          </div>
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text font-medium">
                {t('remote_mqtt.duration_label') || 'Duration (s)'}
              </span>
            </label>
            <input
              type="number"
              min={MIN_DURATION_S}
              max={MAX_DURATION_S}
              className={`input input-bordered input-sm ${!durationValid ? 'input-error' : ''}`}
              value={durationS}
              onChange={(e) => setDurationS(Number(e.target.value) || 0)}
              disabled={scan.isScanning}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleScan}
            disabled={!canScan}
          >
            {scan.isScanning ? (
              <FaSync className="animate-spin" />
            ) : (
              <FaSearch />
            )}
            {scan.isScanning
              ? t('remote_mqtt.scanning') || 'Scanning…'
              : t('remote_mqtt.scan_button') || 'Scan'}
          </button>
        </div>

        {!patternValid && (
          <div className="text-xs text-error">
            {t('remote_mqtt.pattern_invalid') ||
              'Invalid MQTT topic pattern (use `/`, `+`, `#` per the spec).'}
          </div>
        )}

        {/* Status / errors */}
        {scan.error && (
          <div className="alert alert-error py-2 text-sm">
            <FaExclamationTriangle />
            <span>{scan.error}</span>
          </div>
        )}

        {scan.isScanning && (
          <div className="alert alert-info py-2 text-sm">
            <FaSync className="animate-spin" />
            <span>
              {(t('remote_mqtt.scanning_status') || 'Listening on `{pattern}` for {duration}s …')
                .replace('{pattern}', scan.lastPattern ?? pattern)
                .replace('{duration}', String(scan.lastDuration ?? durationS))}
            </span>
          </div>
        )}

        {/* Results */}
        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          {scan.results.length > 0 && (
            <>
              <div className="flex items-center justify-between gap-2 mt-2 mb-1">
                <div className="flex-1 max-w-md">
                  <input
                    type="text"
                    className="input input-bordered input-sm w-full"
                    placeholder={t('remote_mqtt.filter_placeholder') || 'Filter topics or payloads…'}
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  />
                </div>
                <span className="text-xs text-base-content/60 whitespace-nowrap">
                  {filteredResults.length === scan.results.length
                    ? `${scan.results.length} topics`
                    : `${filteredResults.length} / ${scan.results.length} topics`}
                </span>
              </div>

              <div className="overflow-auto border border-base-300 rounded-box">
                <table className="table table-zebra table-sm">
                  <thead className="sticky top-0 bg-base-200">
                    <tr>
                      <th>{t('remote_mqtt.col_topic') || 'Topic'}</th>
                      <th>{t('remote_mqtt.col_type') || 'Type'}</th>
                      <th>{t('remote_mqtt.col_payload') || 'Last payload'}</th>
                      <th className="text-right">{t('remote_mqtt.col_updates') || 'Upd.'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleResults.map((r) => {
                      const isOpen = expanded.has(r.topic);
                      return (
                        <React.Fragment key={r.topic}>
                          <tr
                            className="cursor-pointer hover:bg-base-200"
                            onClick={() => toggleExpand(r.topic)}
                          >
                            <td className="font-mono text-xs break-all">
                              <span className="inline-flex items-center gap-1">
                                {isOpen ? (
                                  <FaChevronDown className="text-base-content/40 shrink-0" />
                                ) : (
                                  <FaChevronRight className="text-base-content/40 shrink-0" />
                                )}
                                {r.topic}
                              </span>
                            </td>
                            <td>
                              <span className={`badge badge-xs ${TYPE_BADGE_CLASS[r.payload_type]}`}>
                                {r.payload_type}
                              </span>
                            </td>
                            <td className="font-mono text-xs break-all text-base-content/70">
                              {truncate(r.last_payload, PAYLOAD_PREVIEW_CHARS)}
                            </td>
                            <td className="text-right">{r.update_count}</td>
                          </tr>
                          {isOpen && (
                            <tr>
                              <td colSpan={4} className="p-2">
                                <MqttTopicInspector result={r} />
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
                {truncatedBy > 0 && (
                  <div className="text-xs text-base-content/60 p-2 text-center bg-base-200">
                    {(t('remote_mqtt.results_truncated') || '+{n} more topics — refine the filter to see them.')
                      .replace('{n}', String(truncatedBy))}
                  </div>
                )}
              </div>
            </>
          )}

          {!scan.isScanning && scan.results.length === 0 && scan.lastPattern && !scan.error && (
            <div className="alert alert-warning py-2 text-sm mt-2">
              {(t('remote_mqtt.no_results') || 'No messages received on `{pattern}` in {duration}s.')
                .replace('{pattern}', scan.lastPattern)
                .replace('{duration}', String(scan.lastDuration ?? durationS))}
            </div>
          )}
        </div>

        <DialogFooter className="mt-2 shrink-0">
          <button type="button" className="btn btn-ghost btn-sm" onClick={scan.reset}>
            {t('remote_mqtt.clear_results') || 'Clear'}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpenChange(false)}>
            {t('common.close') || 'Close'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default MqttScanDialog;
