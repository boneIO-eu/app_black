import React, { useState } from 'react';
import { FaWalking, FaDoorOpen, FaBell } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import OutputSelectDropdown from './OutputSelectDropdown';
import SimpleTimePeriodInput from './SimpleTimePeriodInput';
import type { OutputEntity, AreaEntity, BinarySensorEntity } from '@/types/config';

/**
 * Blueprint definition — a pre-configured action template for common use cases.
 */
interface Blueprint {
  id: string;
  icon: React.ReactNode;
  titleKey: string;
  descriptionKey: string;
  deviceClass: string;
  /** Function that generates the config patch from blueprint params */
  generate: (params: BlueprintParams) => Partial<BinarySensorEntity>;
}

interface BlueprintParams {
  outputId: string;
  delay: string;
}

interface BlueprintPickerProps {
  /** Called with the generated config to apply to the form */
  onApply: (patch: Partial<BinarySensorEntity>) => void;
  /** Called to close the picker */
  onClose: () => void;
  allOutputs: OutputEntity[];
  allAreas: AreaEntity[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
}

/**
 * BlueprintPicker — modal dialog offering pre-built action templates
 * for common binary sensor configurations (motion sensor, door sensor, etc.).
 *
 * User selects a blueprint, configures parameters (output, delay time),
 * and the blueprint generates the full action configuration.
 */
const BlueprintPicker: React.FC<BlueprintPickerProps> = ({
  onApply,
  onClose,
  allOutputs,
  allAreas,
  savedOutputs,
  savedOutputGroups,
}) => {
  const { t } = useTranslation();
  const [selectedBlueprint, setSelectedBlueprint] = useState<string | null>(null);
  const [outputId, setOutputId] = useState('');
  const [delay, setDelay] = useState('2min');

  const blueprints: Blueprint[] = [
    {
      id: 'motion_light',
      icon: <FaWalking className="w-6 h-6" />,
      titleKey: 'blueprints.motion_light_title',
      descriptionKey: 'blueprints.motion_light_desc',
      deviceClass: 'motion',
      generate: (params) => ({
        device_class: 'motion',
        actions: {
          pressed: [
            { action: 'output', boneio_output: params.outputId, action_output: 'ON' },
          ],
          released: [
            {
              action: 'output',
              boneio_output: params.outputId,
              action_output: 'OFF',
              delay: params.delay,
              delay_cancel_on: ['pressed'],
            },
          ],
        },
      }),
    },
    {
      id: 'door_sensor',
      icon: <FaDoorOpen className="w-6 h-6" />,
      titleKey: 'blueprints.door_sensor_title',
      descriptionKey: 'blueprints.door_sensor_desc',
      deviceClass: 'door',
      generate: (params) => ({
        device_class: 'door',
        actions: {
          pressed: [
            { action: 'output', boneio_output: params.outputId, action_output: 'ON' },
          ],
          released: [
            { action: 'output', boneio_output: params.outputId, action_output: 'OFF' },
          ],
        },
      }),
    },
    {
      id: 'doorbell',
      icon: <FaBell className="w-6 h-6" />,
      titleKey: 'blueprints.doorbell_title',
      descriptionKey: 'blueprints.doorbell_desc',
      deviceClass: 'sound',
      generate: (params) => ({
        device_class: 'sound',
        actions: {
          pressed: [
            { action: 'output', boneio_output: params.outputId, action_output: 'ON' },
          ],
          released: [
            { action: 'output', boneio_output: params.outputId, action_output: 'OFF' },
          ],
        },
      }),
    },
  ];

  const selected = blueprints.find((b) => b.id === selectedBlueprint);
  const needsDelay = selectedBlueprint === 'motion_light';

  const handleApply = () => {
    if (!selected || !outputId) return;
    const patch = selected.generate({ outputId, delay });
    onApply(patch);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-base-100 rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-base-300 bg-gradient-to-r from-primary/10 to-secondary/10">
          <h3 className="text-lg font-bold flex items-center gap-2">
            📋 {t('blueprints.title')}
          </h3>
          <p className="text-sm opacity-70 mt-1">{t('blueprints.subtitle')}</p>
        </div>

        {/* Blueprint list or config */}
        <div className="p-5 max-h-[60vh] overflow-y-auto">
          {!selectedBlueprint ? (
            <div className="space-y-3">
              {blueprints.map((bp) => (
                <button
                  key={bp.id}
                  type="button"
                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-base-300 hover:border-primary hover:bg-primary/5 transition-all duration-200 text-left group"
                  onClick={() => setSelectedBlueprint(bp.id)}
                >
                  <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-primary/10 text-primary flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                    {bp.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="font-semibold block">{t(bp.titleKey)}</span>
                    <span className="text-xs opacity-60 block mt-0.5">{t(bp.descriptionKey)}</span>
                  </div>
                  <span className="text-base-content/30 group-hover:text-primary transition-colors text-lg">→</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Back button */}
              <button
                type="button"
                className="btn btn-ghost btn-sm gap-1"
                onClick={() => { setSelectedBlueprint(null); setOutputId(''); }}
              >
                ← {t('blueprints.back_to_list')}
              </button>

              {/* Selected blueprint info */}
              <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
                <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                  {selected?.icon}
                </div>
                <div>
                  <span className="font-semibold">{selected && t(selected.titleKey)}</span>
                  <p className="text-xs opacity-60">{selected && t(selected.descriptionKey)}</p>
                </div>
              </div>

              {/* Output selection */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('blueprints.select_output')}</span>
                </label>
                <OutputSelectDropdown
                  value={outputId}
                  onChange={setOutputId}
                  allOutputs={allOutputs}
                  allAreas={allAreas}
                  placeholder={t('blueprints.select_output_placeholder')}
                  savedOutputs={savedOutputs}
                  savedOutputGroups={savedOutputGroups}
                />
              </div>

              {/* Delay — only for motion sensor */}
              {needsDelay && (
                <div className="form-control">
                  <SimpleTimePeriodInput
                    value={delay}
                    onChange={setDelay}
                    label={t('blueprints.off_delay')}
                    minimum={1}
                    allowedUnits={['s', 'min']}
                  />
                  <label className="label">
                    <span className="label-text-alt">{t('blueprints.off_delay_hint')}</span>
                  </label>
                </div>
              )}

              {/* Preview */}
              {outputId && (
                <div className="rounded-lg bg-base-200/50 border border-base-300 p-3">
                  <span className="text-xs font-semibold uppercase tracking-wide opacity-50">{t('blueprints.preview')}</span>
                  <div className="mt-2 text-sm space-y-1">
                    <p>
                      <span className="badge badge-success badge-xs mr-1">ON</span>
                      {t('blueprints.preview_on')}: <code className="text-primary">{outputId}</code> → ON
                    </p>
                    <p>
                      <span className="badge badge-error badge-xs mr-1">OFF</span>
                      {t('blueprints.preview_off')}: <code className="text-primary">{outputId}</code> → OFF
                      {needsDelay && (
                        <span className="text-info ml-1">
                          ({t('blueprints.preview_after')} {delay})
                        </span>
                      )}
                    </p>
                    {needsDelay && (
                      <p className="text-xs opacity-60 mt-1">
                        ↻ {t('blueprints.preview_cancel')}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-base-300 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t('common.cancel')}
          </button>
          {selectedBlueprint && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!outputId}
              onClick={handleApply}
            >
              {t('blueprints.apply')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default BlueprintPicker;
