/**
 * MqttRemoteInputFields — drop-in replacement for the input_id field
 * when `remote_source === 'mqtt'`.
 *
 * Renders topic / value_template / payload_on / payload_off inputs plus
 * a live preview that evaluates the template against a user-supplied
 * sample payload (or a payload pulled from the MQTT scan dialog).
 *
 * Pure Presentational — state owned by `useJinjaPreview` and the parent
 * form's `data` object. Swappable for an alternative skin.
 */
import React, { useState } from 'react';
import { FaSearch, FaCheck, FaExclamationCircle, FaSync } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

import { useJinjaPreview } from '../hooks/useJinjaPreview';
import { isValidPublicationTopic } from '../helpers/topicValidation';
import MqttScanDialog from './MqttScanDialog';

export interface MqttRemoteInputFieldsData {
  topic?: string;
  value_template?: string;
  payload_on?: string;
  payload_off?: string;
  mode?: string;
}

export interface MqttRemoteInputFieldsProps {
  data: MqttRemoteInputFieldsData;
  onUpdate: (patch: Partial<MqttRemoteInputFieldsData>) => void;
  attemptedSubmit?: boolean;
}

const MqttRemoteInputFields: React.FC<MqttRemoteInputFieldsProps> = ({
  data,
  onUpdate,
  attemptedSubmit,
}) => {
  const { t } = useTranslation();
  const [scanOpen, setScanOpen] = useState(false);
  const [samplePayload, setSamplePayload] = useState('');

  const template = data.value_template || '{{ value }}';
  const preview = useJinjaPreview(template, samplePayload);

  const topicValid = !data.topic || isValidPublicationTopic(data.topic);
  const topicMissing = attemptedSubmit && !data.topic;

  return (
    <div className="space-y-3">
      {/* Topic */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text font-medium">
            {t('remote_mqtt.field_topic') || 'MQTT topic'} <span className="text-error">*</span>
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => setScanOpen(true)}
            title={t('remote_mqtt.scan_button_tooltip') || 'Browse broker'}
          >
            <FaSearch className="mr-1" />
            {t('remote_mqtt.scan_button') || 'Scan broker'}
          </button>
        </label>
        <input
          type="text"
          className={`input input-bordered input-sm font-mono ${!topicValid || topicMissing ? 'input-error' : ''}`}
          value={data.topic || ''}
          onChange={(e) => onUpdate({ topic: e.target.value })}
          placeholder="n64/88/in_1"
        />
        {topicMissing && (
          <span className="label-text-alt text-error text-xs">{t('validation.required') || 'Required'}</span>
        )}
        {!topicValid && (
          <span className="label-text-alt text-error text-xs">
            {t('remote_mqtt.topic_invalid') || 'Invalid topic (no spaces, no `+` or `#` wildcards).'}
          </span>
        )}
      </div>

      {/* Value template */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text font-medium">{t('remote_mqtt.template_label') || 'value_template'}</span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm font-mono text-xs"
          value={data.value_template || ''}
          onChange={(e) => onUpdate({ value_template: e.target.value })}
          placeholder="{{ value }}"
        />
        <span className="label-text-alt text-xs text-base-content/60">
          {t('remote_mqtt.template_hint_input') ||
            'Defaults to `{{ value }}` (raw payload). For JSON: `{{ value_json.fail }}`.'}
        </span>
      </div>

      {/* Optional payload_on / payload_off */}
      <div className="grid grid-cols-2 gap-3">
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text font-medium text-xs">
              {t('remote_mqtt.field_payload_on') || 'payload_on (optional)'}
            </span>
          </label>
          <input
            type="text"
            className="input input-bordered input-sm font-mono text-xs"
            value={data.payload_on || ''}
            onChange={(e) => onUpdate({ payload_on: e.target.value || undefined })}
            placeholder="1"
          />
        </div>
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text font-medium text-xs">
              {t('remote_mqtt.field_payload_off') || 'payload_off (optional)'}
            </span>
          </label>
          <input
            type="text"
            className="input input-bordered input-sm font-mono text-xs"
            value={data.payload_off || ''}
            onChange={(e) => onUpdate({ payload_off: e.target.value || undefined })}
            placeholder="0"
          />
        </div>
      </div>

      {/* Live preview */}
      <div className="card bg-base-200 p-3">
        <div className="text-xs font-medium text-base-content/70 mb-2">
          {t('remote_mqtt.test_payload_label') || 'Test against a sample payload'}
        </div>
        <input
          type="text"
          className="input input-bordered input-sm font-mono text-xs mb-2"
          value={samplePayload}
          onChange={(e) => setSamplePayload(e.target.value)}
          placeholder='{"val":6.5,"fail":0}'
        />
        {samplePayload ? (
          preview.fetchError ? (
            <div className="alert alert-error py-1 text-xs">
              <FaExclamationCircle />
              <span>{preview.fetchError}</span>
            </div>
          ) : preview.preview?.error ? (
            <div className="alert alert-warning py-1 text-xs">
              <FaExclamationCircle />
              <span className="font-mono">{preview.preview.error}</span>
            </div>
          ) : preview.preview?.result != null ? (
            <div className="bg-success/10 border border-success/30 rounded p-2 font-mono text-xs flex items-start gap-2">
              <FaCheck className="text-success mt-0.5 shrink-0" />
              <span className="break-all">
                {preview.preview.result}
                {data.payload_on !== undefined && preview.preview.result === data.payload_on && (
                  <span className="badge badge-success badge-xs ml-2">→ TRUE</span>
                )}
                {data.payload_off !== undefined && preview.preview.result === data.payload_off && (
                  <span className="badge badge-ghost badge-xs ml-2">→ FALSE</span>
                )}
              </span>
            </div>
          ) : preview.isLoading ? (
            <div className="text-xs text-base-content/40">
              <FaSync className="animate-spin inline mr-1" />
              {t('remote_mqtt.preview_pending') || 'Evaluating…'}
            </div>
          ) : null
        ) : (
          <div className="text-xs text-base-content/40">
            {t('remote_mqtt.test_payload_hint') ||
              'Paste a sample payload from your device to verify the template.'}
          </div>
        )}
      </div>

      <MqttScanDialog open={scanOpen} onOpenChange={setScanOpen} />
    </div>
  );
};

export default MqttRemoteInputFields;
