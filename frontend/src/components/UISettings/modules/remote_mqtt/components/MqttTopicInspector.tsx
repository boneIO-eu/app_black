/**
 * MqttTopicInspector — interactive JSON tree + Jinja2 template tester.
 *
 * For a single scan result row, lets the user:
 * - See the payload pretty-printed (JSON tree if applicable, raw otherwise)
 * - Click any JSON value → fills the template editor with the matching
 *   ``{{ value_json.<path> }}`` expression
 * - Edit the template freely and watch the live preview (debounced 300ms,
 *   backend-evaluated for exact parity with runtime)
 *
 * Pure Presentational; all state in ``useJinjaPreview``.
 */
import React, { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { FaSync, FaCheck, FaExclamationCircle } from 'react-icons/fa';

import { useJinjaPreview } from '../hooks/useJinjaPreview';
import { jsonPathToJinja, type JsonPathSegment } from '../helpers/jsonPathToJinja';
import type { ScanResult } from '../types/scan';

export interface MqttTopicInspectorProps {
  result: ScanResult;
  /** Initial template; if omitted, starts with `{{ value_json }}` or `{{ value }}`. */
  initialTemplate?: string;
  /** Notified whenever the user changes the template (useful for parent forms). */
  onTemplateChange?: (template: string) => void;
}

const DEFAULT_JSON_TEMPLATE = '{{ value_json }}';
const DEFAULT_RAW_TEMPLATE = '{{ value }}';

interface JsonNodeProps {
  value: unknown;
  path: JsonPathSegment[];
  onPick: (path: JsonPathSegment[]) => void;
  depth: number;
}

const JsonNode: React.FC<JsonNodeProps> = ({ value, path, onPick, depth }) => {
  const indent = { marginLeft: `${depth * 12}px` };

  if (value === null) {
    return (
      <div style={indent} className="font-mono text-xs">
        <button
          type="button"
          className="text-base-content/50 hover:text-primary hover:underline"
          onClick={() => onPick(path)}
        >
          null
        </button>
      </div>
    );
  }

  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return (
        <div style={indent} className="font-mono text-xs">
          <span className="text-base-content/50">[</span>
          {value.length === 0 ? (
            <span className="text-base-content/50">]</span>
          ) : (
            <>
              {value.map((item, idx) => (
                <div key={idx}>
                  <span className="text-accent">[{idx}]</span>{' '}
                  <JsonNode value={item} path={[...path, idx]} onPick={onPick} depth={depth + 1} />
                </div>
              ))}
              <div style={{ marginLeft: `${depth * 12}px` }}>
                <span className="text-base-content/50">]</span>
              </div>
            </>
          )}
        </div>
      );
    }
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div style={indent} className="font-mono text-xs">
        <span className="text-base-content/50">{'{'}</span>
        {entries.length === 0 ? (
          <span className="text-base-content/50">{'}'}</span>
        ) : (
          <>
            {entries.map(([k, v]) => (
              <div key={k}>
                <span className="text-info">{k}:</span>{' '}
                <JsonNode value={v} path={[...path, k]} onPick={onPick} depth={depth + 1} />
              </div>
            ))}
            <div style={{ marginLeft: `${depth * 12}px` }}>
              <span className="text-base-content/50">{'}'}</span>
            </div>
          </>
        )}
      </div>
    );
  }

  // Primitive — clickable to insert path into template
  const renderedValue =
    typeof value === 'string' ? `"${value}"` : String(value);
  const valueClass =
    typeof value === 'number'
      ? 'text-warning'
      : typeof value === 'boolean'
        ? 'text-success'
        : 'text-base-content';

  return (
    <button
      type="button"
      onClick={() => onPick(path)}
      className={`${valueClass} font-mono text-xs hover:bg-primary/20 hover:underline px-1 rounded`}
      title="Click to use this in the template"
    >
      {renderedValue}
    </button>
  );
};

const MqttTopicInspector: React.FC<MqttTopicInspectorProps> = ({
  result,
  initialTemplate,
  onTemplateChange,
}) => {
  const { t } = useTranslation();
  const isJson = result.payload_type === 'json' && result.parsed_json != null;
  const defaultTemplate = isJson ? DEFAULT_JSON_TEMPLATE : DEFAULT_RAW_TEMPLATE;
  const [template, setTemplate] = useState(initialTemplate ?? defaultTemplate);
  const { preview, isLoading, fetchError } = useJinjaPreview(template, result.last_payload);

  const handleTemplateChange = (next: string) => {
    setTemplate(next);
    onTemplateChange?.(next);
  };

  const handlePick = (path: JsonPathSegment[]) => {
    handleTemplateChange(jsonPathToJinja(path));
  };

  return (
    <div className="bg-base-200 rounded-box p-3 space-y-3">
      {/* Payload viewer */}
      <div>
        <div className="text-xs font-medium text-base-content/70 mb-1">
          {t('remote_mqtt.payload_label') || 'Payload'}
        </div>
        {isJson ? (
          <div className="bg-base-100 rounded p-2 max-h-48 overflow-auto">
            <JsonNode value={result.parsed_json} path={[]} onPick={handlePick} depth={0} />
          </div>
        ) : (
          <pre className="bg-base-100 rounded p-2 text-xs font-mono whitespace-pre-wrap break-all max-h-32 overflow-auto">
            {result.last_payload || <span className="text-base-content/40">(empty)</span>}
          </pre>
        )}
      </div>

      {/* Template editor */}
      <div>
        <label className="label py-1">
          <span className="label-text text-xs font-medium">
            {t('remote_mqtt.template_label') || 'value_template'}
          </span>
          {isJson && (
            <span className="label-text-alt text-xs text-base-content/50">
              {t('remote_mqtt.template_hint') || 'Click any value above to fill in the path'}
            </span>
          )}
        </label>
        <input
          type="text"
          className="input input-bordered input-sm w-full font-mono text-xs"
          value={template}
          onChange={(e) => handleTemplateChange(e.target.value)}
          placeholder="{{ value_json.val }}"
        />
      </div>

      {/* Live preview */}
      <div>
        <div className="text-xs font-medium text-base-content/70 mb-1 flex items-center gap-2">
          {t('remote_mqtt.preview_label') || 'Preview'}
          {isLoading && <FaSync className="animate-spin text-xs" />}
        </div>
        {fetchError ? (
          <div className="alert alert-error py-1 text-xs">
            <FaExclamationCircle />
            <span>{fetchError}</span>
          </div>
        ) : preview?.error ? (
          <div className="alert alert-warning py-1 text-xs">
            <FaExclamationCircle />
            <span className="font-mono">{preview.error}</span>
          </div>
        ) : preview?.result != null ? (
          <div className="bg-success/10 border border-success/30 rounded p-2 font-mono text-xs flex items-start gap-2">
            <FaCheck className="text-success mt-0.5 shrink-0" />
            <span className="break-all">{preview.result}</span>
          </div>
        ) : (
          <div className="text-xs text-base-content/40">
            {template.trim()
              ? t('remote_mqtt.preview_pending') || 'Evaluating…'
              : t('remote_mqtt.preview_empty_template') || 'Enter a template to see the preview'}
          </div>
        )}
      </div>
    </div>
  );
};

export default MqttTopicInspector;
