import React, { useMemo } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import SearchableEntityPicker from './SearchableEntityPicker';
import type { EntityItem } from './EntitySelectDropdown';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { TemplateSubFormProps } from './types/template';
import { GATE_CONTROL_MODES, GATE_DEVICE_CLASSES } from './types/template';

/**
 * GateCoverForm — configuration form for the gate_cover template platform.
 *
 * Impulse-based gate/garage/barrier/wicket control with contact sensors
 * and optional position estimation.
 */
const GateCoverForm: React.FC<TemplateSubFormProps> = ({
  data,
  onChange,
  allOutputs,
  allAreas,
  allInputs,
}) => {
  const { t } = useTranslation();

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const controlMode: string = data.control_mode || 'cycle';
  const deviceClass: string = data.device_class || 'gate';

  /** Build enriched input list from binary sensors only. */
  const allBinarySensors = (allInputs || []).filter(
    (inp: any) => inp.kind === 'binary_sensor' || !inp.kind
  );

  const enrichedInputs = allBinarySensors
    .filter((inp: any) => {
      const id = inp.id || inp.boneio_input || '';
      return Boolean(id);
    })
    .map((inp: any) => {
      const id = inp.id || inp.boneio_input || '';
      const name = inp.name || '';
      const areaObj = allAreas.find((a) => a.id === inp.area);
      const areaName = areaObj?.name || '';
      return { id, name, areaName, boneioInput: inp.boneio_input || '' };
    });

  /** Convert allOutputs to EntityItem[] for SearchableEntityPicker. */
  const outputItems: EntityItem[] = useMemo(
    () =>
      (allOutputs || [])
        .filter((o: any) => o && (o.id || o.boneio_output))
        .map((output: any) => {
          const effectiveId = output.id || output.boneio_output;
          const outputType = output.output_type;
          return {
            id: effectiveId,
            name: output.name || effectiveId,
            area: output.area || '',
            badge: outputType && outputType !== 'none' ? outputType : undefined,
            badgeClass:
              outputType === 'light' ? 'badge-warning'
              : outputType === 'switch' ? 'badge-info'
              : outputType === 'valve' ? 'badge-accent'
              : 'badge-ghost',
          };
        }),
    [allOutputs]
  );

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
          placeholder={t('gate_cover.name_placeholder')}
        />
      </div>

      {/* ID (optional, auto-generated from name) */}
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
          placeholder={sanitizeId(data.name || '') || 'brama_wjazdowa'}
        />
        <p className="text-xs text-base-content/50 mt-1">
          {t('template.id_hint')}
        </p>
      </div>

      {/* Area */}
      <AreaSelect
        value={data.area}
        onChange={(v) => updateField('area', v)}
        areas={allAreas}
        compact
        hideHint
      />

      {/* Device Class */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">{t('gate_cover.device_class')}</span>
        </label>
        <Select value={deviceClass} onValueChange={(v) => updateField('device_class', v)}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GATE_DEVICE_CLASSES.map((dc) => (
              <SelectItem key={dc} value={dc}>
                {t(`gate_cover.device_class_${dc}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Control Mode */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">{t('gate_cover.control_mode')}</span>
        </label>
        <Select value={controlMode} onValueChange={(v) => updateField('control_mode', v)}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GATE_CONTROL_MODES.map((mode) => (
              <SelectItem key={mode} value={mode}>
                {t(`gate_cover.mode_${mode}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-base-content/50 mt-1">
          {t(`gate_cover.mode_${controlMode}_hint`)}
        </p>
      </div>

      {/* --- Outputs section --- */}
      <div className="divider text-xs opacity-50">{t('gate_cover.outputs_section')}</div>

      {controlMode === 'separate' ? (
        <>
          {/* Open Output */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">{t('gate_cover.open_output')}</span>
            </label>
            <SearchableEntityPicker
              value={data.open_output || ''}
              onChange={(v: string) => updateField('open_output', v)}
              items={outputItems}
              allAreas={allAreas}
              placeholder={t('gate_cover.select_output')}
              recentKey="gate-outputs"
            />
          </div>
          {/* Close Output */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">{t('gate_cover.close_output')}</span>
            </label>
            <SearchableEntityPicker
              value={data.close_output || ''}
              onChange={(v: string) => updateField('close_output', v)}
              items={outputItems}
              allAreas={allAreas}
              placeholder={t('gate_cover.select_output')}
              recentKey="gate-outputs"
            />
          </div>
          {/* Stop Output (optional) */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text text-sm font-semibold">
                {t('gate_cover.stop_output')} <span className="font-normal opacity-50">({t('template.optional')})</span>
              </span>
            </label>
            <SearchableEntityPicker
              value={data.stop_output || ''}
              onChange={(v: string) => updateField('stop_output', v || undefined)}
              items={outputItems}
              allAreas={allAreas}
              placeholder={t('gate_cover.select_output')}
              recentKey="gate-outputs"
            />
          </div>
        </>
      ) : (
        /* cycle / open_only — single pulse_output */
        <div className="form-control">
          <label className="label py-1">
            <span className="label-text text-sm font-semibold">{t('gate_cover.pulse_output')}</span>
          </label>
          <SearchableEntityPicker
            value={data.pulse_output || ''}
            onChange={(v: string) => updateField('pulse_output', v)}
            items={outputItems}
            allAreas={allAreas}
            placeholder={t('gate_cover.select_output')}
            recentKey="gate-outputs"
          />
        </div>
      )}

      {/* Pulse Duration */}
      <SimpleTimePeriodInput
        label={controlMode === 'open_only'
          ? `${t('gate_cover.pulse_duration')} (${t('template.optional')})`
          : t('gate_cover.pulse_duration')}
        value={data.pulse_duration || (controlMode !== 'open_only' ? '500ms' : '')}
        onChange={(v: string) => updateField('pulse_duration', v || undefined)}
      />
      {controlMode === 'open_only' && (
        <p className="text-xs text-base-content/50 -mt-2 mb-2">
          {t('gate_cover.pulse_duration_open_only_hint')}
        </p>
      )}

      {/* --- Contact Sensors section --- */}
      <div className="divider text-xs opacity-50">{t('gate_cover.sensors_section')}</div>

      {/* Closed Sensor */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">
            {t('gate_cover.closed_sensor')}
          </span>
        </label>
        <Select
          value={data.closed_sensor || ''}
          onValueChange={(v) => updateField('closed_sensor', v === '__none__' ? undefined : v || undefined)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('gate_cover.select_sensor')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">
              <span className="opacity-50">— {t('gate_cover.no_sensor')} —</span>
            </SelectItem>
            {enrichedInputs.map((inp) => (
              <SelectItem key={inp.id} value={inp.id}>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{inp.name || inp.id}</span>
                  {inp.boneioInput && (
                    <span className="text-xs opacity-60">{inp.boneioInput}</span>
                  )}
                  {inp.areaName && (
                    <span className="text-xs opacity-50">· {inp.areaName}</span>
                  )}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Open Sensor */}
      <div className="form-control">
        <label className="label py-1">
          <span className="label-text text-sm font-semibold">
            {t('gate_cover.open_sensor')} <span className="font-normal opacity-50">({t('template.optional')})</span>
          </span>
        </label>
        <Select
          value={data.open_sensor || ''}
          onValueChange={(v) => updateField('open_sensor', v === '__none__' ? undefined : v || undefined)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('gate_cover.select_sensor')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">
              <span className="opacity-50">— {t('gate_cover.no_sensor')} —</span>
            </SelectItem>
            {enrichedInputs.map((inp) => (
              <SelectItem key={inp.id} value={inp.id}>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{inp.name || inp.id}</span>
                  {inp.boneioInput && (
                    <span className="text-xs opacity-60">{inp.boneioInput}</span>
                  )}
                  {inp.areaName && (
                    <span className="text-xs opacity-50">· {inp.areaName}</span>
                  )}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

    </div>
  );
};

export default GateCoverForm;
