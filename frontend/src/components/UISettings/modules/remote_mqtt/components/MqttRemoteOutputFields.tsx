/**
 * MqttRemoteOutputFields — drop-in replacement for the output_id field
 * when `remote_source === 'mqtt'`.
 *
 * Renders command topic / command_template / optional state_topic +
 * state_value_template + state payload mapping + qos/retain. Live preview
 * shows what payload will be published for an "ON" or "OFF" command.
 */
import React, { useState } from 'react';
import { FaSearch, FaCheck, FaExclamationCircle, FaSync, FaChevronDown, FaChevronRight } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

import { useJinjaPreview } from '../hooks/useJinjaPreview';
import { isValidPublicationTopic } from '../helpers/topicValidation';
import MqttScanDialog from './MqttScanDialog';

export interface MqttRemoteOutputFieldsData {
  topic?: string;
  command_template?: string;
  state_topic?: string;
  state_value_template?: string;
  state_payload_on?: string;
  state_payload_off?: string;
  qos?: number;
  retain?: boolean;
}

export interface MqttRemoteOutputFieldsProps {
  data: MqttRemoteOutputFieldsData;
  onUpdate: (patch: Partial<MqttRemoteOutputFieldsData>) => void;
  attemptedSubmit?: boolean;
}

const MqttRemoteOutputFields: React.FC<MqttRemoteOutputFieldsProps> = ({
  data,
  onUpdate,
  attemptedSubmit,
}) => {
  const { t } = useTranslation();
  const [scanOpen, setScanOpen] = useState(false);
  const [showStateBlock, setShowStateBlock] = useState(!!data.state_topic);

  const cmdTemplate = data.command_template || '{{ state }}';
  const preview = useJinjaPreview(cmdTemplate, 'ON');

  const topicValid = !data.topic || isValidPublicationTopic(data.topic);
  const stateTopicValid = !data.state_topic || isValidPublicationTopic(data.state_topic);
  const topicMissing = attemptedSubmit && !data.topic;

  return (
    <div className="space-y-3">
      {/* Command Topic */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text font-medium">
            {t('remote_mqtt.field_command_topic') || 'Command topic'} <span className="text-error">*</span>
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
          placeholder="n64/88/out_1/cmd"
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

      {/* Command template */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text font-medium">{t('remote_mqtt.field_command_template') || 'command_template'}</span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm font-mono text-xs"
          value={data.command_template || ''}
          onChange={(e) => onUpdate({ command_template: e.target.value })}
          placeholder="{{ state }}"
        />
        <span className="label-text-alt text-xs text-base-content/60">
          {t('remote_mqtt.command_template_hint') ||
            'Context: `{{ state }}` ("ON"/"OFF"), `{{ brightness }}` (0-255). Default sends "ON"/"OFF" string.'}
        </span>
      </div>

      {/* Preview rendered ON payload */}
      <div className="card bg-base-200 p-2">
        <div className="text-xs font-medium text-base-content/70 mb-1">
          {t('remote_mqtt.preview_label') || 'Preview'} (state="ON")
        </div>
        {preview.fetchError ? (
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
            <span className="break-all">{preview.preview.result}</span>
          </div>
        ) : preview.isLoading ? (
          <FaSync className="animate-spin text-xs" />
        ) : null}
      </div>

      {/* QoS + retain */}
      <div className="grid grid-cols-2 gap-3">
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text font-medium text-xs">QoS</span>
          </label>
          <select
            className="select select-bordered select-sm"
            value={data.qos ?? 0}
            onChange={(e) => onUpdate({ qos: Number(e.target.value) })}
          >
            <option value={0}>0 — at most once</option>
            <option value={1}>1 — at least once</option>
            <option value={2}>2 — exactly once</option>
          </select>
        </div>
        <div className="form-control">
          <label className="label py-1 cursor-pointer">
            <span className="label-text font-medium text-xs">Retain</span>
            <input
              type="checkbox"
              className="toggle toggle-sm"
              checked={!!data.retain}
              onChange={(e) => onUpdate({ retain: e.target.checked })}
            />
          </label>
        </div>
      </div>

      {/* Optional state feedback block (collapsible) */}
      <div className="card bg-base-200">
        <button
          type="button"
          className="flex items-center gap-2 p-3 w-full text-left text-sm font-medium"
          onClick={() => setShowStateBlock(!showStateBlock)}
        >
          {showStateBlock ? <FaChevronDown /> : <FaChevronRight />}
          {t('remote_mqtt.state_feedback_label') || 'State feedback (optional)'}
          {data.state_topic && (
            <span className="badge badge-info badge-xs ml-auto">{data.state_topic}</span>
          )}
        </button>
        {showStateBlock && (
          <div className="p-3 pt-0 space-y-3">
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium text-xs">
                  {t('remote_mqtt.field_state_topic') || 'state_topic'}
                </span>
              </label>
              <input
                type="text"
                className={`input input-bordered input-sm font-mono text-xs ${!stateTopicValid ? 'input-error' : ''}`}
                value={data.state_topic || ''}
                onChange={(e) => onUpdate({ state_topic: e.target.value || undefined })}
                placeholder="n64/88/out_1/state"
              />
              <span className="label-text-alt text-xs text-base-content/60">
                {t('remote_mqtt.state_topic_hint') ||
                  'If set, boneIO subscribes here and updates state from real device. Otherwise uses optimistic local state.'}
              </span>
            </div>

            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium text-xs">
                  {t('remote_mqtt.field_state_value_template') || 'state_value_template'}
                </span>
              </label>
              <input
                type="text"
                className="input input-bordered input-sm font-mono text-xs"
                value={data.state_value_template || ''}
                onChange={(e) => onUpdate({ state_value_template: e.target.value || undefined })}
                placeholder="{{ value }}"
                disabled={!data.state_topic}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text font-medium text-xs">state_payload_on</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered input-sm font-mono text-xs"
                  value={data.state_payload_on || ''}
                  onChange={(e) => onUpdate({ state_payload_on: e.target.value || undefined })}
                  placeholder="1"
                  disabled={!data.state_topic}
                />
              </div>
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text font-medium text-xs">state_payload_off</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered input-sm font-mono text-xs"
                  value={data.state_payload_off || ''}
                  onChange={(e) => onUpdate({ state_payload_off: e.target.value || undefined })}
                  placeholder="0"
                  disabled={!data.state_topic}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <MqttScanDialog open={scanOpen} onOpenChange={setScanOpen} />
    </div>
  );
};

export default MqttRemoteOutputFields;
