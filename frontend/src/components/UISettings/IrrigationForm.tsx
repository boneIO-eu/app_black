import React, { useEffect, useMemo, useState } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import OutputSelectDropdown from './OutputSelectDropdown';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { TemplateSubFormProps, Area } from './types/template';
import { SCHEDULE_DAY_OPTIONS } from './types/template';

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
  onChange: (index: number, zone: ZoneData) => void;
  onRemove: (index: number) => void;
  allOutputs: any[];
  allAreas: Area[];
  usedValveIds: string[];
}

function IrrigationZoneRow({ zone, index, onChange, onRemove, allOutputs, allAreas, usedValveIds }: ZoneRowProps) {
  const { t } = useTranslation();

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

  return (
    <div className="border border-base-300 rounded-lg p-3 space-y-3 bg-base-200/30">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{t('irrigation.zone')} #{index + 1}</span>
        <button type="button" className="btn btn-ghost btn-xs text-error" onClick={() => onRemove(index)}>✕</button>
      </div>

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
                  updateField('pump_start_pump_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_start_valve_delay', undefined);
                }}
                label={t('irrigation.pump_start_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <SimpleTimePeriodInput
                value={source.pump_start_valve_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_start_valve_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_start_pump_delay', undefined);
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
                  updateField('pump_stop_pump_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_stop_valve_delay', undefined);
                }}
                label={t('irrigation.pump_stop_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <SimpleTimePeriodInput
                value={source.pump_stop_valve_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_stop_valve_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_stop_pump_delay', undefined);
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
  const [expanded, setExpanded] = useState(
    () => !!(data.valve_overlap || data.valve_open_delay)
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
                value={data.valve_open_delay || '0s'}
                onChange={(v) => {
                  updateField('valve_open_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('valve_overlap', undefined);
                }}
                label={t('irrigation.valve_open_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.valve_open_delay_hint')}</p>
            </div>
            <div className="form-control">
              <SimpleTimePeriodInput
                value={data.valve_overlap || '0s'}
                onChange={(v) => {
                  updateField('valve_overlap', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('valve_open_delay', undefined);
                }}
                label={t('irrigation.valve_overlap')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.valve_overlap_hint')}</p>
            </div>
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
    onChange({ ...data, [field]: value });
  };

  const zones: ZoneData[] = data.zones || [];
  const schedule: ScheduleData[] = data.schedule || [];
  const waterSources: WaterSourceData[] = data.water_sources || [];

  const hasValveOpenDelay = Boolean(data.valve_open_delay && data.valve_open_delay !== '0s' && data.valve_open_delay !== '0ms');

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

  return (
    <div className="space-y-4">
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
            onChange={handleZoneChange}
            onRemove={handleZoneRemove}
            allOutputs={valveOutputs}
            allAreas={allAreas}
            usedValveIds={[...usedValveIds, ...allSourceOutputIds]}
          />
        ))}
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
