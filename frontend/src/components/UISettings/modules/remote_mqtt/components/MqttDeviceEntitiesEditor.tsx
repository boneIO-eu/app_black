/**
 * MqttDeviceEntitiesEditor — declares per-entity MQTT wiring on a generic
 * MQTT remote device (mirrors how ESPHome devices declare their
 * binary_sensors/switches/lights catalog).
 *
 * Renders two editable tables (Inputs + Outputs) plus a "Scan & import"
 * workflow that opens the scanner with the device's topic_prefix and
 * imports selected topics as inputs (auto-classified by payload type).
 *
 * All state is owned by the parent (RemoteDeviceForm). This component
 * is pure Presentational — value/onChange pattern, swappable.
 */
import React, { useState } from 'react';
import { FaPlus, FaTrash, FaSearch, FaDownload } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

import { useMqttScan } from '../hooks/useMqttScan';
import { isValidPublicationTopic } from '../helpers/topicValidation';
import type { ScanResult, PayloadType } from '../types/scan';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export interface MqttDeviceInputRow {
  id: string;
  name?: string;
  topic?: string;
  value_template?: string;
  payload_on?: string;
  payload_off?: string;
}

export interface MqttDeviceOutputRow {
  id: string;
  name?: string;
  topic?: string;
  command_template?: string;
  state_topic?: string;
  state_value_template?: string;
  state_payload_on?: string;
  state_payload_off?: string;
  qos?: 0 | 1 | 2;
  retain?: boolean;
  output_type?: 'switch' | 'light' | 'valve';
}

export interface MqttDeviceConfig {
  topic_prefix?: string;
  inputs?: MqttDeviceInputRow[];
  outputs?: MqttDeviceOutputRow[];
}

export interface MqttDeviceEntitiesEditorProps {
  value: MqttDeviceConfig;
  onChange: (next: MqttDeviceConfig) => void;
}

const TYPE_BADGE_CLASS: Record<PayloadType, string> = {
  json:    'badge-info',
  binary:  'badge-success',
  numeric: 'badge-warning',
  string:  'badge-ghost',
  empty:   'badge-neutral',
};

/** Derive a sensible value_template + payload_on/off from the scanner classifier. */
function autoTemplateFor(result: ScanResult): { value_template: string; payload_on?: string; payload_off?: string } {
  if (result.payload_type === 'binary') {
    return { value_template: '{{ value }}', payload_on: '1', payload_off: '0' };
  }
  if (result.payload_type === 'json') {
    // Default to whole JSON (user edits to pick a path)
    return { value_template: '{{ value_json }}' };
  }
  return { value_template: '{{ value }}' };
}

/** Derive a short id slug from a topic — the last segment, sanitised. */
function idFromTopic(topic: string): string {
  const last = topic.split('/').filter(Boolean).pop() || topic;
  return last.replace(/[^A-Za-z0-9_]+/g, '_');
}

const MqttDeviceEntitiesEditor: React.FC<MqttDeviceEntitiesEditorProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const [scanOpen, setScanOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const scan = useMqttScan();

  const inputs = value.inputs || [];
  const outputs = value.outputs || [];
  const prefix = value.topic_prefix || '';

  // Build a set of all entity IDs and flag the duplicates (UI warning per row).
  const idCounts = new Map<string, number>();
  for (const it of [...inputs, ...outputs]) {
    if (!it.id) continue;
    idCounts.set(it.id, (idCounts.get(it.id) || 0) + 1);
  }
  const isDuplicateId = (id: string) => !!id && (idCounts.get(id) || 0) > 1;

  // --- Inputs editing ---
  const addInput = () => onChange({
    ...value,
    inputs: [...inputs, { id: `in_${inputs.length + 1}`, topic: prefix ? `${prefix}/` : '' }],
  });
  const updateInput = (idx: number, patch: Partial<MqttDeviceInputRow>) =>
    onChange({ ...value, inputs: inputs.map((it, i) => i === idx ? { ...it, ...patch } : it) });
  const removeInput = (idx: number) =>
    onChange({ ...value, inputs: inputs.filter((_, i) => i !== idx) });

  // --- Outputs editing ---
  const addOutput = () => onChange({
    ...value,
    outputs: [...outputs, { id: `out_${outputs.length + 1}`, topic: prefix ? `${prefix}/` : '', output_type: 'switch' }],
  });
  const updateOutput = (idx: number, patch: Partial<MqttDeviceOutputRow>) =>
    onChange({ ...value, outputs: outputs.map((it, i) => i === idx ? { ...it, ...patch } : it) });
  const removeOutput = (idx: number) =>
    onChange({ ...value, outputs: outputs.filter((_, i) => i !== idx) });

  // --- Scan workflow ---
  const openScan = () => {
    setSelected(new Set());
    setScanOpen(true);
    if (prefix) {
      // Pre-fill pattern and auto-run scan
      void scan.scan({ pattern: `${prefix}/#`, duration_s: 5 });
    }
  };
  const toggleSelected = (topic: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  };
  const selectAll = () => setSelected(new Set(scan.results.map(r => r.topic)));
  const selectNone = () => setSelected(new Set());
  const importSelected = () => {
    const existingTopics = new Set(inputs.map(i => i.topic).filter(Boolean));
    const newRows: MqttDeviceInputRow[] = scan.results
      .filter(r => selected.has(r.topic) && !existingTopics.has(r.topic))
      .map(r => {
        const baseId = idFromTopic(r.topic);
        // Ensure unique id within the device
        let id = baseId;
        let n = 2;
        const allIds = new Set([...inputs.map(i => i.id), ...outputs.map(o => o.id)]);
        while (allIds.has(id)) { id = `${baseId}_${n++}`; }
        const auto = autoTemplateFor(r);
        return { id, name: r.topic, topic: r.topic, ...auto };
      });
    if (newRows.length > 0) {
      onChange({ ...value, inputs: [...inputs, ...newRows] });
    }
    setScanOpen(false);
  };

  return (
    <div className="space-y-4">
      {/* Topic prefix + scan button */}
      <div className="flex items-end gap-2">
        <div className="form-control flex-1">
          <label className="label py-1">
            <span className="label-text font-medium">
              {t('remote_mqtt.field_topic_prefix') || 'Topic prefix (optional)'}
            </span>
          </label>
          <input
            type="text"
            className="input input-bordered input-sm font-mono"
            value={prefix}
            onChange={e => onChange({ ...value, topic_prefix: e.target.value || undefined })}
            placeholder="n64/88"
          />
          <span className="label-text-alt text-xs text-base-content/60">
            {t('remote_mqtt.topic_prefix_hint') ||
              'Used to scope the Scan & import dialog. Per-entity topics still stored individually below.'}
          </span>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={openScan}
          disabled={!prefix}
          title={!prefix ? (t('remote_mqtt.topic_prefix_required') || 'Set a topic prefix first') : undefined}
        >
          <FaSearch className="mr-1" />
          {t('remote_mqtt.scan_and_import') || 'Scan & import'}
        </button>
      </div>

      {/* Inputs table */}
      <div className="collapse collapse-arrow bg-base-200">
        <input type="checkbox" defaultChecked />
        <div className="collapse-title font-medium text-sm">
          {t('remote_mqtt.section_inputs') || 'Inputs'}
          <span className="badge badge-sm ml-2">{inputs.length}</span>
        </div>
        <div className="collapse-content">
          {inputs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table table-xs">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>name</th>
                    <th>topic</th>
                    <th>value_template</th>
                    <th>on</th>
                    <th>off</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {inputs.map((it, idx) => {
                    const topicValid = !it.topic || isValidPublicationTopic(it.topic);
                    const dupId = isDuplicateId(it.id);
                    return (
                      <tr key={idx} className={dupId ? 'bg-error/10' : undefined}>
                        <td>
                          <input
                            type="text"
                            className={`input input-bordered input-xs w-24 font-mono ${dupId ? 'input-error' : ''}`}
                            value={it.id}
                            onChange={e => updateInput(idx, { id: e.target.value })}
                            title={dupId ? (t('remote_mqtt.duplicate_id') || 'Duplicate ID — entity IDs must be unique on a device') : undefined}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="input input-bordered input-xs w-32"
                            value={it.name || ''}
                            onChange={e => updateInput(idx, { name: e.target.value || undefined })}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className={`input input-bordered input-xs w-48 font-mono ${!topicValid ? 'input-error' : ''}`}
                            value={it.topic || ''}
                            onChange={e => updateInput(idx, { topic: e.target.value })}
                            placeholder="n64/88/in1"
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="input input-bordered input-xs w-44 font-mono"
                            value={it.value_template || ''}
                            onChange={e => updateInput(idx, { value_template: e.target.value || undefined })}
                            placeholder="{{ value }}"
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="input input-bordered input-xs w-16 font-mono"
                            value={it.payload_on || ''}
                            onChange={e => updateInput(idx, { payload_on: e.target.value || undefined })}
                            placeholder="1"
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="input input-bordered input-xs w-16 font-mono"
                            value={it.payload_off || ''}
                            onChange={e => updateInput(idx, { payload_off: e.target.value || undefined })}
                            placeholder="0"
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs text-error"
                            onClick={() => removeInput(idx)}
                          >
                            <FaTrash />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <button type="button" className="btn btn-outline btn-xs mt-2" onClick={addInput}>
            <FaPlus className="mr-1" /> {t('remote_mqtt.add_input') || 'Add input'}
          </button>
        </div>
      </div>

      {/* Outputs table */}
      <div className="collapse collapse-arrow bg-base-200">
        <input type="checkbox" />
        <div className="collapse-title font-medium text-sm">
          {t('remote_mqtt.section_outputs') || 'Outputs'}
          <span className="badge badge-sm ml-2">{outputs.length}</span>
        </div>
        <div className="collapse-content">
          {outputs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table table-xs">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>name</th>
                    <th>cmd topic</th>
                    <th>cmd template</th>
                    <th>state topic</th>
                    <th>state template</th>
                    <th>type</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {outputs.map((it, idx) => {
                    const dupId = isDuplicateId(it.id);
                    return (
                    <tr key={idx} className={dupId ? 'bg-error/10' : undefined}>
                      <td>
                        <input
                          type="text"
                          className={`input input-bordered input-xs w-24 font-mono ${dupId ? 'input-error' : ''}`}
                          value={it.id}
                          onChange={e => updateOutput(idx, { id: e.target.value })}
                          title={dupId ? (t('remote_mqtt.duplicate_id') || 'Duplicate ID — entity IDs must be unique on a device') : undefined}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="input input-bordered input-xs w-28"
                          value={it.name || ''}
                          onChange={e => updateOutput(idx, { name: e.target.value || undefined })}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="input input-bordered input-xs w-40 font-mono"
                          value={it.topic || ''}
                          onChange={e => updateOutput(idx, { topic: e.target.value })}
                          placeholder="n64/88/out_1/cmd"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="input input-bordered input-xs w-36 font-mono"
                          value={it.command_template || ''}
                          onChange={e => updateOutput(idx, { command_template: e.target.value || undefined })}
                          placeholder="{{ state }}"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="input input-bordered input-xs w-40 font-mono"
                          value={it.state_topic || ''}
                          onChange={e => updateOutput(idx, { state_topic: e.target.value || undefined })}
                          placeholder="(optional)"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="input input-bordered input-xs w-36 font-mono"
                          value={it.state_value_template || ''}
                          onChange={e => updateOutput(idx, { state_value_template: e.target.value || undefined })}
                          placeholder="{{ value }}"
                          disabled={!it.state_topic}
                        />
                      </td>
                      <td>
                        <select
                          className="select select-bordered select-xs"
                          value={it.output_type || 'switch'}
                          onChange={e => updateOutput(idx, { output_type: e.target.value as MqttDeviceOutputRow['output_type'] })}
                        >
                          <option value="switch">switch</option>
                          <option value="light">light</option>
                          <option value="valve">valve</option>
                        </select>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-error"
                          onClick={() => removeOutput(idx)}
                        >
                          <FaTrash />
                        </button>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <button type="button" className="btn btn-outline btn-xs mt-2" onClick={addOutput}>
            <FaPlus className="mr-1" /> {t('remote_mqtt.add_output') || 'Add output'}
          </button>
        </div>
      </div>

      {/* Scan & import dialog (multi-select) */}
      <Dialog open={scanOpen} onOpenChange={setScanOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{t('remote_mqtt.scan_import_title') || 'Scan broker & import topics'}</DialogTitle>
            <DialogDescription>
              {t('remote_mqtt.scan_import_description') ||
                'Select topics to add as inputs on this device. Templates auto-set from payload type.'}
            </DialogDescription>
          </DialogHeader>

          {scan.isScanning && (
            <div className="alert alert-info py-2 text-sm">
              {(t('remote_mqtt.scanning_status') || 'Listening on `{pattern}` for {duration}s …')
                .replace('{pattern}', scan.lastPattern ?? '')
                .replace('{duration}', String(scan.lastDuration ?? ''))}
            </div>
          )}

          {scan.error && (
            <div className="alert alert-error py-2 text-sm">{scan.error}</div>
          )}

          {scan.results.length > 0 && (
            <>
              <div className="flex items-center justify-between gap-2 my-2">
                <div className="flex gap-1">
                  <button type="button" className="btn btn-ghost btn-xs" onClick={selectAll}>
                    {t('remote_mqtt.select_all') || 'Select all'}
                  </button>
                  <button type="button" className="btn btn-ghost btn-xs" onClick={selectNone}>
                    {t('remote_mqtt.select_none') || 'None'}
                  </button>
                </div>
                <span className="text-xs text-base-content/60">
                  {selected.size} / {scan.results.length}
                </span>
              </div>
              <div className="overflow-auto border border-base-300 rounded-box flex-1">
                <table className="table table-zebra table-sm">
                  <thead className="sticky top-0 bg-base-200">
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          className="checkbox checkbox-xs"
                          checked={selected.size === scan.results.length && scan.results.length > 0}
                          onChange={e => e.target.checked ? selectAll() : selectNone()}
                        />
                      </th>
                      <th>{t('remote_mqtt.col_topic') || 'Topic'}</th>
                      <th>{t('remote_mqtt.col_type') || 'Type'}</th>
                      <th>{t('remote_mqtt.col_payload') || 'Last payload'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scan.results.map(r => (
                      <tr
                        key={r.topic}
                        className="cursor-pointer hover:bg-base-200"
                        onClick={() => toggleSelected(r.topic)}
                      >
                        <td>
                          <input
                            type="checkbox"
                            className="checkbox checkbox-xs"
                            checked={selected.has(r.topic)}
                            onChange={() => toggleSelected(r.topic)}
                            onClick={e => e.stopPropagation()}
                          />
                        </td>
                        <td className="font-mono text-xs break-all">{r.topic}</td>
                        <td>
                          <span className={`badge badge-xs ${TYPE_BADGE_CLASS[r.payload_type]}`}>
                            {r.payload_type}
                          </span>
                        </td>
                        <td className="font-mono text-xs break-all text-base-content/70">
                          {r.last_payload.slice(0, 60)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <DialogFooter>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setScanOpen(false)}>
              {t('common.cancel') || 'Cancel'}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={importSelected}
              disabled={selected.size === 0}
            >
              <FaDownload className="mr-1" />
              {(t('remote_mqtt.import_selected') || 'Import {n} as inputs')
                .replace('{n}', String(selected.size))}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MqttDeviceEntitiesEditor;
