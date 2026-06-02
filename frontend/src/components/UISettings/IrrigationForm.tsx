import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { copyToClipboard } from '@/utils/clipboard';
import { FaChevronUp, FaChevronDown } from 'react-icons/fa';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import OutputSelectDropdown from './OutputSelectDropdown';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import AiAssistantShell from './AiAssistantShell';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { TemplateSubFormProps, Area } from './types/template';
import { SCHEDULE_DAY_OPTIONS } from './types/template';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Convert a value that may be a raw millisecond integer (from Cerberus coercion)
 * back to a human-readable time string like "2s" or "500ms".
 * If the value is already a string, returns it unchanged.
 */
function msToTimeString(val: string | number | undefined): string | undefined {
  if (val === undefined || val === null) return undefined;
  if (typeof val === 'string') return val;
  if (typeof val !== 'number' || val === 0) return undefined;
  const ms = val;
  if (ms >= 3600000 && ms % 3600000 === 0) return `${ms / 3600000}h`;
  if (ms >= 60000 && ms % 60000 === 0) return `${ms / 60000}min`;
  if (ms >= 1000 && ms % 1000 === 0) return `${ms / 1000}s`;
  return `${ms}ms`;
}

/** Fields in WaterSourceData that hold time period values. */
const WS_TIME_FIELDS = [
  'output_start_delay', 'output_stop_delay',
  'pump_start_pump_delay', 'pump_start_valve_delay',
  'pump_stop_pump_delay', 'pump_stop_valve_delay',
] as const;

/** Normalize numeric ms values in a water source to time strings. */
function normalizeWaterSource(ws: any): any {
  const out = { ...ws };
  for (const field of WS_TIME_FIELDS) {
    if (typeof out[field] === 'number') {
      out[field] = msToTimeString(out[field]);
    }
  }
  return out;
}

// ─── Zone sub-form ────────────────────────────────────────────────────────────



interface ZoneData {
  id?: string;
  name?: string;
  valve_id?: string;
  run_duration?: string;
  enabled?: boolean;
  run_every_n?: number;
}

interface ZoneRowProps {
  zone: ZoneData;
  index: number;
  totalZones: number;
  onChange: (index: number, zone: ZoneData) => void;
  onRemove: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  allOutputs: any[];
  allAreas: Area[];
  usedValveIds: string[];
}

function IrrigationZoneRow({ zone, index, totalZones, onChange, onRemove, onMoveUp, onMoveDown, allOutputs, allAreas, usedValveIds }: ZoneRowProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(!zone.name && !zone.valve_id);

  const updateField = (field: string, value: any) => {
    const updated = { ...zone, [field]: value };
    // Auto-generate id from name
    if (field === 'name' && (!zone.id || zone.id === sanitizeId(zone.name || ''))) {
      updated.id = sanitizeId(value);
    }
    onChange(index, updated);
  };

  // Exclude other zones' valve_ids from dropdown, but allow this zone's current selection
  const excludeIds = usedValveIds.filter((id) => id !== zone.valve_id);

  // Find valve output name for summary
  const valveOutput = allOutputs.find((o: any) => (o.id || o.boneio_output) === zone.valve_id);
  const valveName = valveOutput?.name || zone.valve_id || '';

  // Summary line
  const zoneName = zone.name || `${t('irrigation.zone')} #${index + 1}`;
  const isDisabled = zone.enabled === false;

  return (
    <div className={`border rounded-lg overflow-hidden ${isDisabled ? 'border-base-300/50 bg-base-200/20 opacity-60' : 'border-base-300 bg-base-200/30'}`}>
      {/* Accordion header — always visible */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none hover:bg-base-300/30 transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
        {/* Expand indicator */}
        <svg
          className={`w-3 h-3 shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}
          fill="currentColor" viewBox="0 0 20 20"
        >
          <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
        </svg>

        {/* Zone number */}
        <span className="text-xs font-bold text-base-content/40 w-5 text-center shrink-0">#{index + 1}</span>

        {/* Summary text */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm truncate">{zoneName}</span>
            {isDisabled && (
              <span className="badge badge-xs badge-warning">{t('irrigation.zone_disabled')}</span>
            )}
          </div>
          {!isOpen && (
            <div className="flex items-center gap-3 text-xs text-base-content/50 mt-0.5">
              {zone.valve_id ? (
                <span>{t('irrigation.zone_summary_valve')}: {valveName}</span>
              ) : (
                <span className="text-warning">{t('irrigation.zone_no_valve')}</span>
              )}
              <span>⏱ {zone.run_duration || '5min'}</span>
              {(zone.run_every_n || 1) > 1 && (
                <span>🔄 {t('irrigation.run_every_n')}: {zone.run_every_n}</span>
              )}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
          {/* Move up */}
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            disabled={index === 0}
            onClick={() => onMoveUp(index)}
            title={t('irrigation.zone_move_up')}
          >
            <FaChevronUp className="w-3 h-3" />
          </button>
          {/* Move down */}
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            disabled={index === totalZones - 1}
            onClick={() => onMoveDown(index)}
            title={t('irrigation.zone_move_down')}
          >
            <FaChevronDown className="w-3 h-3" />
          </button>
          {/* Remove */}
          <button type="button" className="btn btn-ghost btn-xs text-error" onClick={() => onRemove(index)}>✕</button>
        </div>
      </div>

      {/* Accordion content — edit fields */}
      {isOpen && (
        <div className="px-3 pb-3 space-y-3 border-t border-base-300/50">
          {/* Name */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">{t('irrigation.zone_name')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered input-sm w-full"
              value={zone.name || ''}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder={t('irrigation.zone_name_placeholder')}
            />
          </div>

          {/* ID */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">
                {t('template.entity_id')} <span className="font-normal opacity-50">({t('template.optional')})</span>
              </span>
            </label>
            <input
              type="text"
              className="input input-bordered input-sm w-full"
              value={zone.id || ''}
              onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              placeholder={sanitizeId(zone.name || '') || 'greenhouse'}
            />
          </div>

          {/* Valve Output */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">{t('irrigation.valve_output')}</span>
            </label>
            <OutputSelectDropdown
              value={zone.valve_id || ''}
              onChange={(v) => updateField('valve_id', v)}
              allOutputs={allOutputs}
              allAreas={allAreas}
              placeholder={t('irrigation.select_valve')}
              excludeIds={excludeIds}
              emptyHint={t('irrigation.no_valve_outputs_hint')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Run Duration */}
            <div className="form-control">
              <SimpleTimePeriodInput
                value={zone.run_duration || '5min'}
                onChange={(v) => updateField('run_duration', v)}
                label={t('irrigation.run_duration')}
                required
                allowedUnits={['s', 'min', 'h']}
                unitlessNumberUnit="s"
              />
            </div>

            {/* Run every N scheduled runs */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text text-sm font-semibold">{t('irrigation.run_every_n')}</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={30}
                  className="input input-bordered input-sm w-20 text-center"
                  value={zone.run_every_n || 1}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val) && val >= 1) updateField('run_every_n', val);
                  }}
                />
              </div>
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.run_every_n_hint')}</p>
            </div>
          </div>

          {/* Enabled */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-primary"
              checked={zone.enabled !== false}
              onChange={(e) => updateField('enabled', e.target.checked)}
            />
            <span className="text-sm">{t('irrigation.zone_enabled')}</span>
          </label>
        </div>
      )}
    </div>
  );
}

// ─── Schedule sub-form ────────────────────────────────────────────────────────

interface ScheduleData {
  time?: string;
  days?: string;
}

interface ScheduleRowProps {
  sched: ScheduleData;
  index: number;
  onChange: (index: number, sched: ScheduleData) => void;
  onRemove: (index: number) => void;
}

function IrrigationScheduleRow({ sched, index, onChange, onRemove }: ScheduleRowProps) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-2 border border-base-300 rounded-lg p-2 bg-base-200/30">
      <span className="text-xs font-semibold text-base-content/50 w-6 text-center">#{index + 1}</span>

      {/* Time */}
      <input
        type="time"
        className="input input-bordered input-sm w-28"
        value={sched.time || '06:00'}
        onChange={(e) => onChange(index, { ...sched, time: e.target.value })}
      />

      {/* Days */}
      <Select value={sched.days || 'daily'} onValueChange={(v) => onChange(index, { ...sched, days: v })}>
        <SelectTrigger className="w-28 h-8 text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SCHEDULE_DAY_OPTIONS.map((day) => (
            <SelectItem key={day} value={day}>
              {t(`irrigation.day_${day}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <span className="flex-1" />
      <button type="button" className="btn btn-ghost btn-xs text-error" onClick={() => onRemove(index)}>✕</button>
    </div>
  );
}

// ─── Water Source sub-form ─────────────────────────────────────────────────────

interface WaterSourceData {
  id?: string;
  name?: string;
  outputs?: string[];
  output_start_delay?: string;
  output_stop_delay?: string;
  pump_start_pump_delay?: string;
  pump_start_valve_delay?: string;
  pump_stop_pump_delay?: string;
  pump_stop_valve_delay?: string;
  pump_switch_off_during_valve_open_delay?: boolean;
}

interface WaterSourceRowProps {
  source: WaterSourceData;
  index: number;
  onChange: (index: number, source: WaterSourceData) => void;
  onRemove: (index: number) => void;
  allOutputs: any[];
  allAreas: Area[];
  usedOutputIds: string[];
  hasValveOpenDelay: boolean;
}

function WaterSourceRow({ source, index, onChange, onRemove, allOutputs, allAreas, usedOutputIds, hasValveOpenDelay }: WaterSourceRowProps) {
  const { t } = useTranslation();
  const [showSequentialDelay, setShowSequentialDelay] = useState(
    () => !!(source.output_start_delay || source.output_stop_delay)
  );
  const [showPumpDelays, setShowPumpDelays] = useState(
    () => !!(source.pump_start_pump_delay || source.pump_start_valve_delay ||
             source.pump_stop_pump_delay || source.pump_stop_valve_delay)
  );

  const updateField = (field: string, value: any) => {
    const updated = { ...source, [field]: value };
    if (field === 'name' && (!source.id || source.id === sanitizeId(source.name || ''))) {
      updated.id = sanitizeId(value);
    }
    onChange(index, updated);
  };

  const outputs = source.outputs || [];

  // Exclude other sources' outputs, but allow this source's current selections
  const excludeForSource = usedOutputIds.filter((id) => !outputs.includes(id));

  const addOutput = () => {
    onChange(index, { ...source, outputs: [...outputs, ''] });
  };

  const removeOutput = (oidx: number) => {
    const updated = outputs.filter((_, i) => i !== oidx);
    onChange(index, { ...source, outputs: updated });
  };

  const updateOutput = (oidx: number, value: string) => {
    const updated = [...outputs];
    updated[oidx] = value;
    onChange(index, { ...source, outputs: updated });
  };

  return (
    <div className="border border-base-300 rounded-lg p-3 space-y-3 bg-base-200/30">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">💧 {t('irrigation.water_source')} #{index + 1}</span>
        <button type="button" className="btn btn-ghost btn-xs text-error" onClick={() => onRemove(index)}>✕</button>
      </div>

      {/* Name */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">{t('irrigation.source_name')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          value={source.name || ''}
          onChange={(e) => updateField('name', e.target.value)}
          placeholder={t('irrigation.source_name_placeholder')}
        />
      </div>

      {/* ID */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">
            {t('template.entity_id')} <span className="font-normal opacity-50">({t('template.optional')})</span>
          </span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          value={source.id || ''}
          onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          placeholder={sanitizeId(source.name || '') || 'city_water'}
        />
      </div>

      {/* Outputs */}
      <div className="form-control">
        <div className="flex items-center justify-between">
          <label className="label py-1">
            <span className="label-text text-sm font-semibold">{t('irrigation.source_outputs')}</span>
          </label>
          <button type="button" className="btn btn-xs btn-outline btn-primary" onClick={addOutput}>
            + {t('irrigation.add_output')}
          </button>
        </div>
        <p className="text-xs text-base-content/50 mb-1">{t('irrigation.source_outputs_hint')}</p>
        {outputs.length === 0 && (
          <p className="text-xs text-warning py-1">{t('irrigation.source_no_outputs')}</p>
        )}
        {outputs.map((oid, oidx) => (
          <div key={oidx} className="flex items-center gap-2 mb-1">
            <div className="flex-1">
              <OutputSelectDropdown
                value={oid}
                onChange={(v) => updateOutput(oidx, v)}
                allOutputs={allOutputs}
                allAreas={allAreas}
                placeholder={t('irrigation.select_output')}
                excludeIds={excludeForSource.filter((id) => id !== oid)}
                emptyHint={t('irrigation.no_valve_outputs_hint')}
              />
            </div>
            <button type="button" className="btn btn-ghost btn-xs text-error" onClick={() => removeOutput(oidx)}>✕</button>
          </div>
        ))}
      </div>

      {/* Sequential output activation delay (collapsible) */}
      {(source.outputs?.length || 0) > 1 && (
        <div className="border border-base-300 rounded-lg">
          <button
            type="button"
            className="w-full p-2 flex items-center justify-between text-xs font-semibold hover:bg-base-200/50 rounded-lg transition-colors"
            onClick={() => setShowSequentialDelay(!showSequentialDelay)}
          >
            <span>⏱️ {t('irrigation.sequential_delay')}</span>
            <span className={`transition-transform ${showSequentialDelay ? 'rotate-180' : ''}`}>▾</span>
          </button>
          {showSequentialDelay && (
            <div className="p-2 pt-0 space-y-2">
              <p className="text-xs text-base-content/50">{t('irrigation.sequential_delay_hint')}</p>
              <div className="grid grid-cols-2 gap-2">
                <SimpleTimePeriodInput
                  value={source.output_start_delay || '0s'}
                  onChange={(v) => updateField('output_start_delay', v)}
                  label={t('irrigation.output_start_delay')}
                  allowedUnits={['ms', 's']}
                  unitlessNumberUnit="s"
                />
                <SimpleTimePeriodInput
                  value={source.output_stop_delay || '0s'}
                  onChange={(v) => updateField('output_stop_delay', v)}
                  label={t('irrigation.output_stop_delay')}
                  allowedUnits={['ms', 's']}
                  unitlessNumberUnit="s"
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Per-source pump delays (collapsible) */}
      <div className="border border-base-300 rounded-lg">
        <button
          type="button"
          className="w-full p-2 flex items-center justify-between text-xs font-semibold hover:bg-base-200/50 rounded-lg transition-colors"
          onClick={() => setShowPumpDelays(!showPumpDelays)}
        >
          <span>⏱️ {t('irrigation.pump_delays')}</span>
          <span className={`transition-transform ${showPumpDelays ? 'rotate-180' : ''}`}>▾</span>
        </button>
        {showPumpDelays && (
          <div className="p-2 pt-0 space-y-2">
            {hasValveOpenDelay && (
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={source.pump_switch_off_during_valve_open_delay === true}
                  onChange={(e) => updateField('pump_switch_off_during_valve_open_delay', e.target.checked)}
                />
                <div>
                  <span className="text-sm">{t('irrigation.pump_off_during_delay')}</span>
                  <p className="text-xs text-base-content/50">{t('irrigation.pump_off_during_delay_hint')}</p>
                </div>
              </label>
            )}
            <div className="grid grid-cols-2 gap-2">
              <SimpleTimePeriodInput
                value={source.pump_start_pump_delay || '0s'}
                onChange={(v) => {
                  const updated = { ...source, pump_start_pump_delay: v };
                  if (v && v !== '0s' && v !== '0ms') updated.pump_start_valve_delay = undefined;
                  onChange(index, updated);
                }}
                label={t('irrigation.pump_start_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <SimpleTimePeriodInput
                value={source.pump_start_valve_delay || '0s'}
                onChange={(v) => {
                  const updated = { ...source, pump_start_valve_delay: v };
                  if (v && v !== '0s' && v !== '0ms') updated.pump_start_pump_delay = undefined;
                  onChange(index, updated);
                }}
                label={t('irrigation.pump_start_valve_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <SimpleTimePeriodInput
                value={source.pump_stop_pump_delay || '0s'}
                onChange={(v) => {
                  const updated = { ...source, pump_stop_pump_delay: v };
                  if (v && v !== '0s' && v !== '0ms') updated.pump_stop_valve_delay = undefined;
                  onChange(index, updated);
                }}
                label={t('irrigation.pump_stop_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <SimpleTimePeriodInput
                value={source.pump_stop_valve_delay || '0s'}
                onChange={(v) => {
                  const updated = { ...source, pump_stop_valve_delay: v };
                  if (v && v !== '0s' && v !== '0ms') updated.pump_stop_pump_delay = undefined;
                  onChange(index, updated);
                }}
                label={t('irrigation.pump_stop_valve_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Advanced Valve Timing ────────────────────────────────────────────────────

function AdvancedTimingSection({ data, updateField }: { data: any; updateField: (field: string, value: any) => void }) {
  const { t } = useTranslation();
  // Normalize numeric ms values (backend Cerberus coercion may produce raw ints)
  const voDelay = msToTimeString(data.valve_open_delay) ?? data.valve_open_delay;
  const voOverlap = msToTimeString(data.valve_overlap) ?? data.valve_overlap;
  const [expanded, setExpanded] = useState(
    () => !!(voOverlap || voDelay)
  );

  return (
    <div className="border border-base-300 rounded-lg">
      <button
        type="button"
        className="w-full p-3 flex items-center justify-between text-sm font-semibold hover:bg-base-200/50 rounded-lg transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span>⚙️ {t('irrigation.advanced_timing')}</span>
        <span className={`transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
      </button>
      {expanded && (
        <div className="p-3 pt-0 space-y-3">
          {/* Valve Open Delay vs Valve Overlap — mutually exclusive */}
          <p className="text-xs text-base-content/50">{t('irrigation.timing_mutual_hint')}</p>

          <div className="grid grid-cols-2 gap-3">
            <div className="form-control">
              <SimpleTimePeriodInput
                value={voDelay || '0s'}
                onChange={(v) => {
                  const updates: Record<string, any> = { valve_open_delay: v };
                  if (v && v !== '0s' && v !== '0ms') updates.valve_overlap = undefined;
                  updateField('__batch', updates);
                }}
                label={t('irrigation.valve_open_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.valve_open_delay_hint')}</p>
            </div>
            <div className="form-control">
              <SimpleTimePeriodInput
                value={voOverlap || '0s'}
                onChange={(v) => {
                  const updates: Record<string, any> = { valve_overlap: v };
                  if (v && v !== '0s' && v !== '0ms') updates.valve_open_delay = undefined;
                  updateField('__batch', updates);
                }}
                label={t('irrigation.valve_overlap')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.valve_overlap_hint')}</p>
            </div>
          </div>

          {/* Pause Timeout */}
          <div className="form-control mt-2">
            <SimpleTimePeriodInput
              value={data.pause_timeout || '30min'}
              onChange={(v) => updateField('pause_timeout', v)}
              label={t('irrigation.pause_timeout')}
              allowedUnits={['s', 'min', 'h']}
              unitlessNumberUnit="s"
            />
            <p className="text-xs text-base-content/50 mt-1">{t('irrigation.pause_timeout_hint')}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Form ────────────────────────────────────────────────────────────────

const IrrigationForm: React.FC<TemplateSubFormProps> = ({
  data,
  onChange,
  allOutputs,
  allAreas,
  onValidationChange,
}) => {
  const { t } = useTranslation();

  // Only show valve-type outputs in irrigation zone dropdowns
  const valveOutputs = useMemo(
    () => allOutputs.filter((o: any) => o.output_type === 'valve'),
    [allOutputs]
  );

  // For water sources: show switches and valves (exclude lights and covers)
  const switchableOutputs = useMemo(
    () => allOutputs.filter((o: any) => {
      const t = (o.output_type || '').toLowerCase();
      return t !== 'light' && t !== 'cover';
    }),
    [allOutputs]
  );

  const updateField = (field: string, value: any) => {
    if (field === '__batch' && typeof value === 'object') {
      onChange({ ...data, ...value });
    } else {
      onChange({ ...data, [field]: value });
    }
  };

  // Normalize zone run_duration (backend may send raw ms integers)
  const zones: ZoneData[] = useMemo(
    () => (data.zones || []).map((z: any) => ({
      ...z,
      run_duration: typeof z.run_duration === 'number' ? msToTimeString(z.run_duration) : z.run_duration,
    })),
    [data.zones]
  );
  const schedule: ScheduleData[] = data.schedule || [];
  // Normalize water source time fields (backend may send raw ms integers)
  const waterSources: WaterSourceData[] = useMemo(
    () => (data.water_sources || []).map(normalizeWaterSource),
    [data.water_sources]
  );
  // Also normalize top-level time fields
  const valveOpenDelay = msToTimeString(data.valve_open_delay) ?? data.valve_open_delay;

  const hasValveOpenDelay = Boolean(valveOpenDelay && valveOpenDelay !== '0s' && valveOpenDelay !== '0ms');

  // Collect all used output IDs: zone valve_ids + all water source outputs
  const usedValveIds = useMemo(() => {
    const ids = zones.map((z) => z.valve_id).filter(Boolean) as string[];
    // Add all water source output IDs
    for (const ws of waterSources) {
      if (ws.outputs) {
        for (const oid of ws.outputs) {
          if (oid) ids.push(oid);
        }
      }
    }
    return ids;
  }, [zones, waterSources]);

  // Collect all water source output IDs (for zone dropdown exclusion)
  const allSourceOutputIds = useMemo(() => {
    const ids: string[] = [];
    for (const ws of waterSources) {
      if (ws.outputs) {
        for (const oid of ws.outputs) {
          if (oid) ids.push(oid);
        }
      }
    }
    return ids;
  }, [waterSources]);

  const handleZoneChange = (index: number, zone: ZoneData) => {
    const updated = [...zones];
    updated[index] = zone;
    onChange({ ...data, zones: updated });
  };

  const handleZoneRemove = (index: number) => {
    const updated = zones.filter((_, i) => i !== index);
    onChange({ ...data, zones: updated });
  };

  const handleZoneAdd = () => {
    onChange({ ...data, zones: [...zones, { enabled: true, run_duration: '5min', run_every_n: 1 }] });
  };

  /** Move a zone up (swap with previous). */
  const handleZoneMove = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= zones.length) return;
    const updated = [...zones];
    const [moved] = updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, moved);
    onChange({ ...data, zones: updated });
  };

  const handleScheduleChange = (index: number, sched: ScheduleData) => {
    const updated = [...schedule];
    updated[index] = sched;
    onChange({ ...data, schedule: updated });
  };

  const handleScheduleRemove = (index: number) => {
    const updated = schedule.filter((_, i) => i !== index);
    onChange({ ...data, schedule: updated });
  };

  const handleScheduleAdd = () => {
    onChange({ ...data, schedule: [...schedule, { time: '06:00', days: 'daily' }] });
  };

  const handleWaterSourceChange = (index: number, source: WaterSourceData) => {
    const updated = [...waterSources];
    updated[index] = source;
    onChange({ ...data, water_sources: updated });
  };

  const handleWaterSourceRemove = (index: number) => {
    const updated = waterSources.filter((_, i) => i !== index);
    onChange({ ...data, water_sources: updated });
  };

  const handleWaterSourceAdd = () => {
    onChange({ ...data, water_sources: [...waterSources, { outputs: [] }] });
  };

  // Validation
  useEffect(() => {
    if (!onValidationChange) return;
    const hasId = Boolean(data.id);
    const hasZones = zones.length > 0 && zones.every((z) => z.valve_id);
    onValidationChange(!(hasId && hasZones));
  }, [data.id, zones, onValidationChange]);

  // ── AI Wizard ─────────────────────────────────────────────────────

  /** Build an output list from the outputs we know about. */
  const buildOutputList = useCallback(() => {
    return allOutputs.map((o: any) => {
      const id = o.id || o.boneio_output || '';
      const name = o.name || o.id || '';
      const type = o.output_type || 'switch';
      return `- ${id} ("${name}", type: ${type})`;
    }).join('\n');
  }, [allOutputs]);

  /**
   * Copies the irrigation AI prompt to clipboard.
   * Fetches context from backend for richer data, falls back to local allOutputs.
   */
  const handleCopyPrompt = useCallback(async (): Promise<boolean> => {
    try {
      let outputLines: string;
      let existingLines = 'None configured yet.';
      let deviceName = 'boneIO Black';

      try {
        const resp = await axios.get('/api/irrigation/ai-context');
        const ctx = resp.data;
        deviceName = ctx.device_name || deviceName;

        outputLines = ctx.available_outputs
          .map((o: any) => {
            const status = o.in_use ? `IN USE by ${o.used_by}` : 'available';
            return `- ${o.id} ("${o.name}", type: ${o.type}) \u2014 ${status}`;
          })
          .join('\n');

        if (ctx.existing_controllers?.length > 0) {
          existingLines = ctx.existing_controllers
            .map((c: any) => {
              const zones = c.zones.map((z: any) => `${z.id}(valve:${z.valve})`).join(', ');
              const sources = c.water_sources.map((ws: any) => `${ws.id}(outputs:${ws.outputs.join(',')})`).join(', ');
              return `- "${c.id}" (${c.name}): zones=[${zones}], water_sources=[${sources}]`;
            })
            .join('\n');
        }
      } catch {
        outputLines = buildOutputList();
      }

      const prompt = `You are a boneIO irrigation configuration assistant.

The user has a ${deviceName} device with the following relay outputs:
${outputLines}

Existing irrigation controllers:
${existingLines}

Your job:
1. Ask the user about their irrigation setup in a conversational way:
   - How many irrigation zones? What are they called?
   - Which output controls which zone valve?
   - Do they have a master pump or master valve? Which output?
   - How long should each zone run (in minutes)?
   - How often should each zone run? (every cycle, every 2nd cycle, etc.)
   - What time should irrigation start? Which days?
   - Do they have multiple water sources (e.g., rainwater + city water)?

2. After gathering all information, generate a JSON configuration in this EXACT format:
\`\`\`json
{
  "id": "lowercase_no_spaces",
  "name": "Display Name",
  "schedule": [{"time": "06:00", "days": "daily"}],
  "zones": [
    {
      "id": "zone_id",
      "name": "Zone Name",
      "valve_id": "output_id_from_list_above",
      "run_duration": "10min",
      "run_every_n": 1,
      "enabled": true
    }
  ],
  "water_sources": [
    {
      "id": "source_id",
      "name": "Source Name",
      "outputs": ["output_id"]
    }
  ]
}
\`\`\`

Rules:
- ONLY use output IDs from the available list above.
- ONLY use outputs of type "switch" for valves and pumps. Outputs of type "light" are for lighting and MUST NOT be used for irrigation.
- run_duration uses format like "10min", "30s", "1h".
- run_every_n: 1 = every cycle, 2 = every other cycle, 3 = every 3rd, etc.
- days options: daily, weekdays, weekend, mon, tue, wed, thu, fri, sat, sun.
- water_sources.outputs = the pump/master valve output IDs.
- zone.valve_id = the zone solenoid valve output ID.
- Generate a single controller object (not an array).
- When done, output ONLY the JSON block inside \`\`\`json ... \`\`\` markers.`;

      await copyToClipboard(prompt);
      return true;
    } catch (err) {
      console.error('Failed to copy wizard prompt:', err);
      return false;
    }
  }, [buildOutputList]);

  /**
   * Validates and applies the pasted AI response to the irrigation form.
   * Returns an array of error messages (empty = success).
   */
  const handleApplyResponse = useCallback((responseText: string): string[] => {
    try {
      // Extract JSON from response (may be wrapped in ```json ... ```)
      let jsonStr = responseText.trim();
      const jsonMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (jsonMatch) {
        jsonStr = jsonMatch[1].trim();
      }

      const parsed = JSON.parse(jsonStr);

      // Validate required fields
      if (!parsed.zones || !Array.isArray(parsed.zones) || parsed.zones.length === 0) {
        return [t('irrigation.ai_invalid_json')];
      }

      // Validate output IDs
      const outputIds = new Set(allOutputs.map((o: any) => o.id || o.boneio_output || ''));
      const errors: string[] = [];

      for (const zone of parsed.zones) {
        const valveId = zone.valve_id || zone.valve || '';
        if (valveId && !outputIds.has(valveId)) {
          errors.push(`Zone '${zone.id || '?'}': valve '${valveId}' not found in available outputs.`);
        }
      }

      for (const ws of (parsed.water_sources || [])) {
        for (const outId of (ws.outputs || [])) {
          if (outId && !outputIds.has(outId)) {
            errors.push(`Water source '${ws.id || '?'}': output '${outId}' not found.`);
          }
        }
      }

      if (errors.length > 0) {
        return errors;
      }

      // Build form data
      const newData: any = { ...data };
      if (parsed.id) newData.id = parsed.id;
      if (parsed.name) newData.name = parsed.name;

      newData.zones = parsed.zones.map((z: any) => ({
        id: z.id || sanitizeId(z.name || ''),
        name: z.name || z.id || '',
        valve_id: z.valve_id || z.valve || '',
        run_duration: z.run_duration || '5min',
        run_every_n: z.run_every_n || 1,
        enabled: z.enabled !== false,
      }));

      if (parsed.schedule && Array.isArray(parsed.schedule)) {
        newData.schedule = parsed.schedule.map((s: any) => ({
          time: s.time || '06:00',
          days: s.days || 'daily',
        }));
      }

      if (parsed.water_sources && Array.isArray(parsed.water_sources)) {
        newData.water_sources = parsed.water_sources.map((ws: any) => ({
          id: ws.id || sanitizeId(ws.name || ''),
          name: ws.name || ws.id || '',
          outputs: ws.outputs || [],
        }));
      }

      if (parsed.valve_open_delay) newData.valve_open_delay = parsed.valve_open_delay;
      if (parsed.valve_overlap) newData.valve_overlap = parsed.valve_overlap;
      if (parsed.pause_timeout) newData.pause_timeout = parsed.pause_timeout;

      onChange(newData);
      return [];
    } catch {
      return [t('irrigation.ai_invalid_json')];
    }
  }, [data, allOutputs, onChange, t]);

  return (
    <div className="space-y-4">
      {/* AI Configuration Assistant */}
      <AiAssistantShell
        onCopyPrompt={handleCopyPrompt}
        onApply={handleApplyResponse}
        detailsContent={
          <>
            <p>{t('irrigation.ai_wizard_description')}</p>
            <p>
              <a className="link link-primary" href="https://boneio.eu/docs/black" target="_blank" rel="noreferrer">
                {t('event_form.ai_docs_link')}
              </a>
            </p>
          </>
        }
        dialogDescription={t('irrigation.ai_paste_desc')}
        pastePlaceholder={t('irrigation.ai_paste_placeholder')}
        successMessage={t('irrigation.ai_apply_success')}
      />

      {/* Name */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">{t('template.entity_name')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          value={data.name || ''}
          onChange={(e) => {
            const name = e.target.value;
            const updates: any = { ...data, name };
            if (!data.id || data.id === sanitizeId(data.name || '')) {
              updates.id = sanitizeId(name);
            }
            onChange(updates);
          }}
          placeholder={t('irrigation.controller_name_placeholder')}
        />
      </div>

      {/* ID */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">
            {t('template.entity_id')} <span className="font-normal opacity-50">({t('template.optional')})</span>
          </span>
        </label>
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          value={data.id || ''}
          onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          placeholder={sanitizeId(data.name || '') || 'garden'}
        />
        <p className="text-xs text-base-content/50 mt-1">{t('template.id_hint')}</p>
      </div>

      {/* Area */}
      <AreaSelect
        value={data.area}
        onChange={(v) => updateField('area', v)}
        areas={allAreas}
        compact
        hideHint
      />

      {/* ── Water Sources ──────────────────────────────────────────── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">💧 {t('irrigation.water_sources')}</span>
          <button type="button" className="btn btn-xs btn-primary" onClick={handleWaterSourceAdd}>
            + {t('irrigation.add_water_source')}
          </button>
        </div>
        <p className="text-xs text-base-content/50">{t('irrigation.water_sources_hint')}</p>
        {waterSources.length === 0 && (
          <p className="text-xs text-base-content/50 py-2">{t('irrigation.no_water_sources')}</p>
        )}
        {waterSources.map((source, idx) => (
          <WaterSourceRow
            key={idx}
            source={source}
            index={idx}
            onChange={handleWaterSourceChange}
            onRemove={handleWaterSourceRemove}
            allOutputs={switchableOutputs}
            allAreas={allAreas}
            usedOutputIds={usedValveIds}
            hasValveOpenDelay={hasValveOpenDelay}
          />
        ))}
      </div>

      {/* Runtime settings hint */}
      <div className="alert alert-info py-2 text-xs">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-4 h-4"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        <span>{t('irrigation.runtime_settings_hint')}</span>
      </div>

      {/* ── Advanced Valve Timing ──────────────────────────────────── */}
      <AdvancedTimingSection data={data} updateField={updateField} />

      {/* ── Zones ────────────────────────────────────────────────── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">{t('irrigation.zones')}</span>
          <button type="button" className="btn btn-xs btn-primary" onClick={handleZoneAdd}>
            + {t('irrigation.add_zone')}
          </button>
        </div>
        {zones.length === 0 && (
          <p className="text-xs text-base-content/50 py-2">{t('irrigation.no_zones')}</p>
        )}
        {zones.map((zone, idx) => (
          <IrrigationZoneRow
            key={idx}
            zone={zone}
            index={idx}
            totalZones={zones.length}
            onChange={handleZoneChange}
            onRemove={handleZoneRemove}
            onMoveUp={(i) => handleZoneMove(i, i - 1)}
            onMoveDown={(i) => handleZoneMove(i, i + 1)}
            allOutputs={valveOutputs}
            allAreas={allAreas}
            usedValveIds={[...usedValveIds, ...allSourceOutputIds]}
          />
        ))}
        {zones.length > 0 && (
          <button type="button" className="btn btn-xs btn-outline btn-primary w-full" onClick={handleZoneAdd}>
            + {t('irrigation.add_zone')}
          </button>
        )}
      </div>

      {/* ── Schedule ─────────────────────────────────────────────── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">{t('irrigation.schedules')}</span>
          <button type="button" className="btn btn-xs btn-primary" onClick={handleScheduleAdd}>
            + {t('irrigation.add_schedule')}
          </button>
        </div>
        {schedule.length === 0 && (
          <p className="text-xs text-base-content/50 py-2">{t('irrigation.no_schedules')}</p>
        )}
        {schedule.map((sched, idx) => (
          <IrrigationScheduleRow
            key={idx}
            sched={sched}
            index={idx}
            onChange={handleScheduleChange}
            onRemove={handleScheduleRemove}
          />
        ))}
      </div>

      {/* Validation hint */}
      {(zones.length === 0 || zones.some((z) => !z.valve_id)) && (
        <p className="text-xs text-warning">{t('irrigation.fields_required')}</p>
      )}


    </div>
  );
};

export default IrrigationForm;
