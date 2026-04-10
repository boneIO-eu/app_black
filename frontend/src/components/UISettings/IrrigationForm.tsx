import React, { useEffect, useMemo, useState } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
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

/** Parse "Nd" / "Nh" strings into day count */
function parseDays(val: string | undefined): number {
  if (!val) return 1;
  const m = String(val).match(/^(\d+)\s*(d|h)$/i);
  if (m) {
    const n = parseInt(m[1], 10);
    return m[2].toLowerCase() === 'h' ? Math.max(1, Math.round(n / 24)) : n;
  }
  return 1;
}

interface ZoneData {
  id?: string;
  name?: string;
  valve_id?: string;
  run_duration?: string;
  enabled?: boolean;
  run_every?: string;
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

        {/* Run Every (days) */}
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text text-sm font-semibold">{t('irrigation.run_every')}</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={30}
              className="input input-bordered input-sm w-20 text-center"
              value={parseDays(zone.run_every || '1d')}
              onChange={(e) => {
                const val = parseInt(e.target.value, 10);
                if (!isNaN(val) && val >= 1) updateField('run_every', `${val}d`);
              }}
            />
            <span className="text-sm text-base-content/60">{t('irrigation.days_unit')}</span>
          </div>
          <p className="text-xs text-base-content/50 mt-1">{t('irrigation.run_every_hint')}</p>
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

// ─── Advanced Pump/Valve Timing ───────────────────────────────────────────────

function AdvancedTimingSection({ data, updateField }: { data: any; updateField: (field: string, value: any) => void }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(
    () => !!(data.valve_overlap || data.pump_start_pump_delay || data.pump_start_valve_delay ||
             data.pump_stop_pump_delay || data.pump_stop_valve_delay || data.pump_switch_off_during_valve_open_delay)
  );

  const hasValveOpenDelay = Boolean(data.valve_open_delay && data.valve_open_delay !== '0s' && data.valve_open_delay !== '0ms');

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

          {/* pump_switch_off_during_valve_open_delay — only visible when valve_open_delay is set */}
          {hasValveOpenDelay && data.master_valve && (
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={data.pump_switch_off_during_valve_open_delay === true}
                onChange={(e) => updateField('pump_switch_off_during_valve_open_delay', e.target.checked)}
              />
              <div>
                <span className="text-sm">{t('irrigation.pump_off_during_delay')}</span>
                <p className="text-xs text-base-content/50">{t('irrigation.pump_off_during_delay_hint')}</p>
              </div>
            </label>
          )}

          {/* Pump start delays — mutually exclusive pair */}
          <div className="grid grid-cols-2 gap-3">
            <div className="form-control">
              <SimpleTimePeriodInput
                value={data.pump_start_pump_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_start_pump_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_start_valve_delay', undefined);
                }}
                label={t('irrigation.pump_start_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.pump_start_pump_delay_hint')}</p>
            </div>
            <div className="form-control">
              <SimpleTimePeriodInput
                value={data.pump_start_valve_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_start_valve_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_start_pump_delay', undefined);
                }}
                label={t('irrigation.pump_start_valve_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.pump_start_valve_delay_hint')}</p>
            </div>
          </div>

          {/* Pump stop delays — mutually exclusive pair */}
          <div className="grid grid-cols-2 gap-3">
            <div className="form-control">
              <SimpleTimePeriodInput
                value={data.pump_stop_pump_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_stop_pump_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_stop_valve_delay', undefined);
                }}
                label={t('irrigation.pump_stop_pump_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.pump_stop_pump_delay_hint')}</p>
            </div>
            <div className="form-control">
              <SimpleTimePeriodInput
                value={data.pump_stop_valve_delay || '0s'}
                onChange={(v) => {
                  updateField('pump_stop_valve_delay', v);
                  if (v && v !== '0s' && v !== '0ms') updateField('pump_stop_pump_delay', undefined);
                }}
                label={t('irrigation.pump_stop_valve_delay')}
                allowedUnits={['ms', 's']}
                unitlessNumberUnit="s"
              />
              <p className="text-xs text-base-content/50 mt-1">{t('irrigation.pump_stop_valve_delay_hint')}</p>
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

  // Only show valve-type outputs in irrigation dropdowns
  const valveOutputs = useMemo(
    () => allOutputs.filter((o: any) => o.output_type === 'valve'),
    [allOutputs]
  );

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const zones: ZoneData[] = data.zones || [];
  const schedule: ScheduleData[] = data.schedule || [];

  const usedValveIds = useMemo(() => zones.map((z) => z.valve_id).filter(Boolean) as string[], [zones]);

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
    onChange({ ...data, zones: [...zones, { enabled: true, run_duration: '5min', run_every: '1d' }] });
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
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">{t('outputs.area')}</span>
        </label>
        <Select value={data.area || ''} onValueChange={(v) => updateField('area', v || undefined)}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('outputs.no_area')} />
          </SelectTrigger>
          <SelectContent>
            {allAreas.map((area) => (
              <SelectItem key={area.id} value={area.id}>
                {area.name || area.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Master Valve */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">
            {t('irrigation.master_valve')} <span className="font-normal opacity-50">({t('template.optional')})</span>
          </span>
        </label>
        <OutputSelectDropdown
          value={data.master_valve || ''}
          onChange={(v) => updateField('master_valve', v || undefined)}
          allOutputs={valveOutputs}
          allAreas={allAreas}
          placeholder={t('irrigation.select_master_valve')}
        />
        <p className="text-xs text-base-content/50 mt-1">{t('irrigation.master_valve_hint')}</p>
      </div>

      {/* Multiplier + Repeat row */}
      <div className="grid grid-cols-2 gap-3">
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text text-sm font-semibold">{t('irrigation.multiplier')}</span>
          </label>
          <input
            type="number"
            step={0.1}
            min={0.1}
            max={10}
            className="input input-bordered input-sm w-full"
            value={data.multiplier ?? 1.0}
            onChange={(e) => updateField('multiplier', parseFloat(e.target.value) || 1.0)}
          />
          <p className="text-xs text-base-content/50 mt-1">{t('irrigation.multiplier_hint')}</p>
        </div>
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text text-sm font-semibold">{t('irrigation.repeat')}</span>
          </label>
          <input
            type="number"
            min={0}
            max={10}
            className="input input-bordered input-sm w-full"
            value={data.repeat ?? 0}
            onChange={(e) => updateField('repeat', parseInt(e.target.value, 10) || 0)}
          />
          <p className="text-xs text-base-content/50 mt-1">{t('irrigation.repeat_hint')}</p>
        </div>
      </div>

      {/* Auto-advance + Reverse + Standby toggles */}
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="checkbox checkbox-sm checkbox-primary"
            checked={data.auto_advance !== false}
            onChange={(e) => updateField('auto_advance', e.target.checked)}
          />
          <span className="text-sm">{t('irrigation.auto_advance')}</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="checkbox checkbox-sm"
            checked={data.reverse === true}
            onChange={(e) => updateField('reverse', e.target.checked)}
          />
          <span className="text-sm">{t('irrigation.reverse')}</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="checkbox checkbox-sm checkbox-warning"
            checked={data.standby === true}
            onChange={(e) => updateField('standby', e.target.checked)}
          />
          <span className="text-sm">{t('irrigation.standby')}</span>
        </label>
      </div>
      {data.standby && (
        <p className="text-xs text-warning">{t('irrigation.standby_hint')}</p>
      )}

      {/* ── Advanced Pump/Valve Timing ─────────────────────────── */}
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
            usedValveIds={usedValveIds}
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
