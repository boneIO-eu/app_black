import React from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { rgbToHex, hexToRgb, formatActionLabel } from './helpers';
import SimpleTimePeriodInput from '../widgets/SimpleTimePeriodInput';
import RemoteDeviceSelect from '../widgets/RemoteDeviceSelect';
import type { RemoteOutputActionProps, RemoteDevice } from './types';

const STEP_BRIGHTNESS_ACTIONS = ['BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE'];

/**
 * Gets all entities (switches, lights, segments) from a remote device.
 */
const getDeviceEntities = (device: RemoteDevice | undefined): any[] => {
  if (!device) return [];
  
  const isEspHome = device.protocol === 'esphome_api';
  const isWled = device.protocol === 'wled';
  
  if (isEspHome) {
    const switches = (device.esphome_api?.switches || []).map((s: any) => ({ ...s, _type: 'switch' }));
    const lights = (device.esphome_api?.lights || []).map((l: any) => ({ ...l, _type: 'light' }));
    return [...switches, ...lights];
  } else if (isWled) {
    return [
      { id: 'main', name: 'All LEDs', _type: 'wled_main' },
      ...(device.wled?.segments || []).map((s: any) => ({ 
        ...s, 
        id: String(s.id),
        name: s.name || `Segment ${s.id}`,
        _type: 'wled_segment' 
      }))
    ];
  } else {
    return device.mqtt?.outputs || [];
  }
};

/**
 * Remote Output Action component - handles ESPHome, WLED, and MQTT remote outputs.
 */
const RemoteOutputAction: React.FC<RemoteOutputActionProps> = ({
  action,
  onUpdate,
  t,
  allRemoteDevices,
  actionOutputOptions,
}) => {
  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
  const allEntities = getDeviceEntities(selectedDevice);
  const selectedEntity = allEntities.find((o: any) => o.id === action.output_id);
  
  const isEspHome = selectedDevice?.protocol === 'esphome_api';
  const isWled = selectedDevice?.protocol === 'wled';
  
  // ESPHome light detection
  const lights = selectedDevice?.esphome_api?.lights || [];
  const selectedLight = lights.find((l: any) => l.id === action.output_id);
  const isLight = isEspHome && selectedLight;
  
  // ON/OFF-only actions (no brightness/color/cycle support)
  const ON_OFF_ACTIONS = ['TOGGLE', 'ON', 'OFF'];
  
  // Filter action options based on selected entity capabilities:
  // - ESPHome switch → ON/OFF only
  // - ESPHome light without supports_brightness → ON/OFF only
  // - MQTT remote output → ON/OFF only
  // - WLED / ESPHome dimmable light → full list
  const filteredActionOptions = React.useMemo(() => {
    if (!selectedEntity) return actionOutputOptions;
    
    const entityType = selectedEntity._type;
    
    // ESPHome switch — always ON/OFF only
    if (entityType === 'switch') {
      return actionOutputOptions.filter((o: string) => ON_OFF_ACTIONS.includes(o));
    }
    
    // ESPHome light — check supports_brightness
    if (entityType === 'light' && !selectedLight?.supports_brightness) {
      return actionOutputOptions.filter((o: string) => ON_OFF_ACTIONS.includes(o));
    }
    
    // MQTT remote output (no _type or generic) — ON/OFF only
    if (!entityType || (!['light', 'wled_main', 'wled_segment'].includes(entityType))) {
      return actionOutputOptions.filter((o: string) => ON_OFF_ACTIONS.includes(o));
    }
    
    return actionOutputOptions;
  }, [selectedEntity, selectedLight, actionOutputOptions]);
  
  // Default action is TOGGLE
  const effectiveAction = action.action_output || 'TOGGLE';

  return (
    <>
      {/* Remote Device Selection */}
      <RemoteDeviceSelect
        value={action.remote_device || ''}
        onChange={(value) => onUpdate('remote_device', value)}
        allRemoteDevices={allRemoteDevices}
        label={t('event_form.remote_device')}
        placeholder={t('event_form.select_remote_device')}
      />

      {/* Output/Entity Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.output_id')}</span>
        </label>
        <Select
          value={action.output_id || ''}
          onValueChange={(value) => {
            onUpdate('output_id', value);
            // Reset action_output if current action is not valid for new entity
            const newEntity = allEntities.find((o: any) => o.id === value);
            const isOnOffOnly = !newEntity || newEntity._type === 'switch' 
              || (newEntity._type === 'light' && !lights.find((l: any) => l.id === value)?.supports_brightness)
              || !['light', 'wled_main', 'wled_segment'].includes(newEntity._type);
            if (isOnOffOnly && action.action_output && !ON_OFF_ACTIONS.includes(action.action_output)) {
              onUpdate('action_output', 'TOGGLE');
            }
          }}
          disabled={!action.remote_device}
        >
          <SelectTrigger className="w-full input input-bordered h-auto min-h-12 py-2">
            <SelectValue placeholder={t('event_form.select_output_id')}>
              {selectedEntity ? (
                <div className="flex flex-col items-start">
                  <span className="font-medium">{selectedEntity.name || selectedEntity.id}</span>
                  <span className="text-xs opacity-60">
                    {selectedEntity._type === 'light' ? '💡 Light' : 
                     selectedEntity._type === 'switch' ? '🔌 Switch' : 
                     selectedEntity._type === 'wled_main' ? '🌈 WLED All' :
                     selectedEntity._type === 'wled_segment' ? `🌈 Segment ${selectedEntity.len ? `(${selectedEntity.len} LEDs)` : ''}` :
                     `ID: ${selectedEntity.id}`}
                  </span>
                </div>
              ) : (
                <span className="opacity-50">{t('event_form.select_output_id')}</span>
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {allEntities.map((entity: any) => (
              <SelectItem key={entity.id} value={entity.id}>
                <div className="flex flex-col">
                  <span className="font-medium">{entity.name || entity.id}</span>
                  <span className="text-xs opacity-60">
                    {entity._type === 'light' ? (
                      <>💡 Light {entity.supports_brightness && '• Dimmable'}</>
                    ) : entity._type === 'switch' ? (
                      <>🔌 Switch</>
                    ) : entity._type === 'wled_main' ? (
                      <>🌈 Control all LEDs</>
                    ) : entity._type === 'wled_segment' ? (
                      <>🌈 Segment {entity.len ? `• ${entity.len} LEDs` : ''}</>
                    ) : (
                      <>ID: {entity.id}</>
                    )}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!action.remote_device && (
          <label className="label">
            <span className="label-text-alt text-warning">{t('event_form.select_device_first')}</span>
          </label>
        )}
      </div>

      {/* Output Action Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.output_action')}</span>
        </label>
        <Select
          value={action.action_output || 'TOGGLE'}
          onValueChange={(value) => onUpdate('action_output', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {filteredActionOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ESPHome Light Controls (for non-cycle actions) */}
      {isLight && !['CYCLE_COLOR', 'CYCLE_PRESET'].includes(effectiveAction) && (
        <EspHomeLightControls
          action={action}
          onUpdate={onUpdate}
          t={t}
          selectedLight={selectedLight}
          effectiveAction={effectiveAction}
        />
      )}

      {/* WLED Controls (for non-cycle actions) */}
      {isWled && !['CYCLE_COLOR', 'CYCLE_PRESET'].includes(effectiveAction) && (
        <WledControls
          action={action}
          onUpdate={onUpdate}
          t={t}
          selectedDevice={selectedDevice}
          effectiveAction={effectiveAction}
        />
      )}

      {/* Cycle Color Control */}
      {effectiveAction === 'CYCLE_COLOR' && (isLight || isWled) && (
        <CycleColorControl action={action} onUpdate={onUpdate} t={t} />
      )}

      {/* Cycle Preset Control */}
      {effectiveAction === 'CYCLE_PRESET' && (isLight || isWled) && (
        <CyclePresetControl
          action={action}
          onUpdate={onUpdate}
          t={t}
          selectedLight={selectedLight}
          selectedDevice={selectedDevice}
          isEspHome={!!isEspHome}
          isWled={!!isWled}
        />
      )}

      {/* Transition for cycle actions */}
      {['CYCLE_COLOR', 'CYCLE_PRESET'].includes(effectiveAction) && (isLight || isWled) && (
        <TransitionControl action={action} onUpdate={onUpdate} t={t} />
      )}
    </>
  );
};

/**
 * ESPHome Light Controls - brightness, color temp, RGB, transition.
 */
interface EspHomeLightControlsProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
  selectedLight: any;
  effectiveAction: string;
}

const EspHomeLightControls: React.FC<EspHomeLightControlsProps> = ({
  action,
  onUpdate,
  t,
  selectedLight,
  effectiveAction,
}) => {
  const showBrightness = selectedLight?.supports_brightness && 
    ['ON', 'TOGGLE', 'SET_BRIGHTNESS'].includes(effectiveAction);
  const showStepBrightness = selectedLight?.supports_brightness && 
    STEP_BRIGHTNESS_ACTIONS.includes(effectiveAction);
  const showColorTemp = selectedLight?.supports_color_temp && 
    ['ON', 'TOGGLE'].includes(effectiveAction);
  const showRgb = (selectedLight?.supports_rgb || selectedLight?.supports_rgbw) && 
    ['ON', 'TOGGLE'].includes(effectiveAction);

  return (
    <>
      {showBrightness && (
        <BrightnessControl action={action} onUpdate={onUpdate} t={t} />
      )}
      
      {showStepBrightness && (
        <BrightnessStepControl action={action} onUpdate={onUpdate} t={t} />
      )}
      
      {showColorTemp && (
        <ColorTempControl 
          action={action} 
          onUpdate={onUpdate} 
          t={t}
          minMireds={selectedLight?.min_mireds || 153}
          maxMireds={selectedLight?.max_mireds || 500}
        />
      )}
      
      {showRgb && (
        <RgbControl action={action} onUpdate={onUpdate} t={t} />
      )}
      
      <TransitionControl action={action} onUpdate={onUpdate} t={t} />
    </>
  );
};

/**
 * WLED Controls - brightness, RGB, effects, palettes, speed, intensity, transition.
 */
interface WledControlsProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
  selectedDevice: RemoteDevice | undefined;
  effectiveAction: string;
}

const WledControls: React.FC<WledControlsProps> = ({
  action,
  onUpdate,
  t,
  selectedDevice,
  effectiveAction,
}) => {
  const showBrightness = ['ON', 'TOGGLE', 'SET_BRIGHTNESS'].includes(effectiveAction);
  const showStepBrightness = STEP_BRIGHTNESS_ACTIONS.includes(effectiveAction);
  const showRgb = ['ON', 'TOGGLE'].includes(effectiveAction);

  return (
    <>
      {showBrightness && (
        <BrightnessControl action={action} onUpdate={onUpdate} t={t} />
      )}

      {showStepBrightness && (
        <BrightnessStepControl action={action} onUpdate={onUpdate} t={t} />
      )}
      
      {showRgb && (
        <RgbControl action={action} onUpdate={onUpdate} t={t} />
      )}
      
      {/* WLED Effect selector */}
      {selectedDevice?.wled?.effects && selectedDevice.wled.effects.length > 0 && ['ON', 'TOGGLE'].includes(effectiveAction) && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-2 pb-1">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-secondary"
              checked={action.effect !== undefined}
              onChange={(e) => onUpdate('effect', e.target.checked ? 0 : undefined)}
            />
            <span className="label-text font-medium">{t('event_form.wled_effect') || 'Effect'}</span>
          </label>
          {action.effect !== undefined && (
            <div className="pl-7">
              <select
                className="select select-bordered w-full"
                value={action.effect ?? 0}
                onChange={(e) => onUpdate('effect', parseInt(e.target.value))}
              >
                {selectedDevice.wled.effects.map((fx: { id: number; name: string }) => (
                  <option key={fx.id} value={fx.id}>{fx.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}
      
      {/* WLED Palette selector */}
      {selectedDevice?.wled?.palettes && selectedDevice.wled.palettes.length > 0 && action.effect !== undefined && action.effect !== 0 && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-2 pb-1">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-secondary"
              checked={action.palette !== undefined}
              onChange={(e) => onUpdate('palette', e.target.checked ? 0 : undefined)}
            />
            <span className="label-text font-medium">{t('event_form.wled_palette') || 'Color Palette'}</span>
          </label>
          {action.palette !== undefined && (
            <div className="pl-7">
              <select
                className="select select-bordered w-full"
                value={action.palette ?? 0}
                onChange={(e) => onUpdate('palette', parseInt(e.target.value))}
              >
                {selectedDevice.wled.palettes.map((pal: { id: number; name: string }) => (
                  <option key={pal.id} value={pal.id}>{pal.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}
      
      {/* Effect Speed */}
      {action.effect !== undefined && action.effect !== 0 && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-2 pb-1">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-secondary"
              checked={action.effect_speed !== undefined}
              onChange={(e) => onUpdate('effect_speed', e.target.checked ? 128 : undefined)}
            />
            <span className="label-text font-medium">{t('event_form.effect_speed') || 'Effect Speed'}</span>
            {action.effect_speed !== undefined && (
              <span className="label-text-alt ml-auto">{Math.round((action.effect_speed / 255) * 100)}%</span>
            )}
          </label>
          {action.effect_speed !== undefined && (
            <div className="pl-7">
              <input
                type="range"
                min="0"
                max="255"
                value={action.effect_speed}
                onChange={(e) => onUpdate('effect_speed', parseInt(e.target.value))}
                className="range range-secondary range-sm w-full"
              />
            </div>
          )}
        </div>
      )}
      
      {/* Effect Intensity */}
      {action.effect !== undefined && action.effect !== 0 && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-2 pb-1">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-secondary"
              checked={action.effect_intensity !== undefined}
              onChange={(e) => onUpdate('effect_intensity', e.target.checked ? 128 : undefined)}
            />
            <span className="label-text font-medium">{t('event_form.effect_intensity') || 'Effect Intensity'}</span>
            {action.effect_intensity !== undefined && (
              <span className="label-text-alt ml-auto">{Math.round((action.effect_intensity / 255) * 100)}%</span>
            )}
          </label>
          {action.effect_intensity !== undefined && (
            <div className="pl-7">
              <input
                type="range"
                min="0"
                max="255"
                value={action.effect_intensity}
                onChange={(e) => onUpdate('effect_intensity', parseInt(e.target.value))}
                className="range range-secondary range-sm w-full"
              />
            </div>
          )}
        </div>
      )}
      
      <TransitionControl action={action} onUpdate={onUpdate} t={t} />
    </>
  );
};

/**
 * Reusable Brightness Control component.
 */
interface BrightnessControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
}

const BrightnessControl: React.FC<BrightnessControlProps> = ({ action, onUpdate, t }) => (
  <div className="form-control mb-3">
    <label className="label cursor-pointer justify-start gap-2 pb-1">
      <input
        type="checkbox"
        className="checkbox checkbox-sm checkbox-primary"
        checked={action.brightness !== undefined}
        onChange={(e) => onUpdate('brightness', e.target.checked ? 255 : undefined)}
      />
      <span className="label-text font-medium">{t('event_form.brightness') || 'Brightness'}</span>
      {action.brightness !== undefined && (
        <span className="label-text-alt ml-auto">{Math.round((action.brightness / 255) * 100)}%</span>
      )}
    </label>
    {action.brightness !== undefined && (
      <div className="pl-7">
        <input
          type="range"
          min="1"
          max="255"
          value={action.brightness}
          onChange={(e) => onUpdate('brightness', parseInt(e.target.value))}
          className="range range-primary range-sm w-full"
        />
        <div className="w-full flex justify-between text-xs opacity-50">
          <span>1%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
    )}
  </div>
);

/**
 * WLED-specific Brightness Step Control component (1-50%).
 */
const BrightnessStepControl: React.FC<BrightnessControlProps> = ({ action, onUpdate, t }) => (
  <div className="form-control mb-3">
    <label className="label justify-start gap-2 pb-1">
      <span className="label-text font-medium">{t('event_form.brightness_step') || 'Brightness Step'}</span>
      <span className="label-text-alt ml-auto">{action.brightness_step ?? 10}%</span>
    </label>
    <div className="px-1">
      <input
        type="range"
        min="1"
        max="50"
        value={action.brightness_step ?? 10}
        onChange={(e) => {
          const val = parseInt(e.target.value);
          onUpdate('brightness_step', val === 10 ? undefined : val);
        }}
        className="range range-primary range-sm w-full"
      />
      <div className="w-full flex justify-between text-xs opacity-50 px-1">
        <span>1%</span>
        <span>25%</span>
        <span>50%</span>
      </div>
    </div>
  </div>
);

/**
 * Reusable Color Temperature Control component.
 */
interface ColorTempControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
  minMireds: number;
  maxMireds: number;
}

const ColorTempControl: React.FC<ColorTempControlProps> = ({ action, onUpdate, t, minMireds, maxMireds }) => (
  <div className="form-control mb-3">
    <label className="label cursor-pointer justify-start gap-2 pb-1">
      <input
        type="checkbox"
        className="checkbox checkbox-sm checkbox-warning"
        checked={action.color_temp !== undefined}
        onChange={(e) => onUpdate('color_temp', e.target.checked ? minMireds : undefined)}
      />
      <span className="label-text font-medium">{t('event_form.color_temp') || 'Color Temperature'}</span>
      {action.color_temp !== undefined && (
        <span className="label-text-alt ml-auto">{action.color_temp} mireds</span>
      )}
    </label>
    {action.color_temp !== undefined && (
      <div className="pl-7">
        <input
          type="range"
          min={minMireds}
          max={maxMireds}
          value={action.color_temp}
          onChange={(e) => onUpdate('color_temp', parseInt(e.target.value))}
          className="range range-warning range-sm w-full"
        />
        <div className="w-full flex justify-between text-xs opacity-50">
          <span>{t('event_form.color_temp_cool') || 'Cool'}</span>
          <span>{t('event_form.color_temp_warm') || 'Warm'}</span>
        </div>
      </div>
    )}
  </div>
);

/**
 * Reusable RGB Color Control component.
 */
interface RgbControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
}

const RgbControl: React.FC<RgbControlProps> = ({ action, onUpdate, t }) => (
  <div className="form-control mb-3">
    <label className="label cursor-pointer justify-start gap-2 pb-1">
      <input
        type="checkbox"
        className="checkbox checkbox-sm checkbox-accent"
        checked={action.rgb !== undefined}
        onChange={(e) => onUpdate('rgb', e.target.checked ? [255, 255, 255] : undefined)}
      />
      <span className="label-text font-medium">{t('event_form.rgb_color') || 'RGB Color'}</span>
      {action.rgb && (
        <span 
          className="w-6 h-6 rounded border border-base-300 ml-auto"
          style={{ backgroundColor: rgbToHex(action.rgb) }}
        />
      )}
    </label>
    {action.rgb && (
      <div className="pl-7 flex items-center gap-3">
        <input
          type="color"
          value={rgbToHex(action.rgb)}
          onChange={(e) => onUpdate('rgb', hexToRgb(e.target.value))}
          className="w-12 h-10 cursor-pointer rounded border-0"
        />
        <span className="text-sm opacity-70">
          RGB({action.rgb[0]}, {action.rgb[1]}, {action.rgb[2]})
        </span>
      </div>
    )}
  </div>
);

/**
 * Reusable Transition Control component using SimpleTimePeriodInput.
 */
interface TransitionControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
}

const TransitionControl: React.FC<TransitionControlProps> = ({ action, onUpdate, t }) => {
  // Convert legacy float (seconds) to timeperiod string for backward compat
  const transitionValue = React.useMemo(() => {
    const val = action.transition;
    if (val === undefined || val === null) return '';
    if (typeof val === 'number') return val === 0 ? '' : `${val}s`;
    return val;
  }, [action.transition]);

  return (
    <div className="form-control mb-3">
      <SimpleTimePeriodInput
        label={t('event_form.transition') || 'Transition Time'}
        value={transitionValue}
        onChange={(val) => onUpdate('transition', val === '' || val === '0ms' || val === '0s' ? undefined : val)}
        maximum={60000}
        allowedUnits={['ms', 's']}
      />
    </div>
  );
};

/**
 * Cycle Color Control - manage a list of RGB colors to cycle through.
 */
interface CycleColorControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
}

const CycleColorControl: React.FC<CycleColorControlProps> = ({ action, onUpdate, t }) => {
  const colors: number[][] = action.colors || [];

  const addColor = () => {
    const defaultColors = [
      [255, 0, 0], [0, 255, 0], [0, 0, 255],
      [255, 255, 0], [255, 0, 255], [0, 255, 255],
      [255, 128, 0], [128, 0, 255], [255, 255, 255],
    ];
    const newColor = defaultColors[colors.length % defaultColors.length];
    onUpdate('colors', [...colors, newColor]);
  };

  const updateColor = (index: number, rgb: number[]) => {
    const updated = [...colors];
    updated[index] = rgb;
    onUpdate('colors', updated);
  };

  const removeColor = (index: number) => {
    onUpdate('colors', colors.filter((_, i) => i !== index));
  };

  return (
    <div className="form-control mb-3">
      <label className="label">
        <span className="label-text font-medium">{t('event_form.cycle_colors')}</span>
      </label>
      <p className="text-xs opacity-60 mb-2">{t('event_form.cycle_colors_hint')}</p>

      {colors.length === 0 && (
        <div className="text-sm opacity-50 italic mb-2">{t('event_form.cycle_no_colors')}</div>
      )}

      <div className="flex flex-wrap gap-2 mb-2">
        {colors.map((color, idx) => (
          <div key={idx} className="flex items-center gap-1 bg-base-200 rounded-lg px-2 py-1">
            <span className="text-xs font-mono opacity-60 mr-1">{idx + 1}</span>
            <input
              type="color"
              value={rgbToHex(color)}
              onChange={(e) => updateColor(idx, hexToRgb(e.target.value))}
              className="w-8 h-8 cursor-pointer rounded border-0 p-0"
            />
            <button
              type="button"
              className="btn btn-ghost btn-xs text-error"
              onClick={() => removeColor(idx)}
            >
              <FaTrash size={10} />
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="btn btn-outline btn-sm gap-1"
        onClick={addColor}
      >
        <FaPlus size={10} />
        {t('event_form.cycle_add_color')}
      </button>
    </div>
  );
};

/**
 * Cycle Preset Control - manage a list of effects/presets to cycle through.
 * For ESPHome: effect names (strings) from discovered light effects.
 * For WLED: effect IDs (numbers) from discovered WLED effects.
 */
interface CyclePresetControlProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
  t: (key: string) => string;
  selectedLight: any;
  selectedDevice: RemoteDevice | undefined;
  isEspHome: boolean;
  isWled: boolean;
}

const CyclePresetControl: React.FC<CyclePresetControlProps> = ({
  action, onUpdate, t, selectedLight, selectedDevice, isEspHome, isWled,
}) => {
  const presets: (string | number)[] = action.presets || [];

  // Get available effects based on device type
  const availableEffects: { id: string | number; name: string }[] = React.useMemo(() => {
    if (isEspHome && selectedLight?.effects) {
      return selectedLight.effects
        .filter((e: string) => e)
        .map((e: string) => ({ id: e, name: e === 'None' ? `None (${t('event_form.static_color') || 'Static'})` : e }));
    }
    if (isWled && selectedDevice?.wled?.effects) {
      return selectedDevice.wled.effects.map((fx: { id: number; name: string }) => ({
        id: fx.id,
        name: fx.name,
      }));
    }
    return [];
  }, [isEspHome, isWled, selectedLight, selectedDevice]);

  const addPreset = (value: string | number) => {
    if (!presets.includes(value)) {
      onUpdate('presets', [...presets, value]);
    }
  };

  const removePreset = (index: number) => {
    onUpdate('presets', presets.filter((_, i) => i !== index));
  };

  const movePreset = (index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= presets.length) return;
    const updated = [...presets];
    [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
    onUpdate('presets', updated);
  };

  const getPresetName = (preset: string | number): string => {
    const found = availableEffects.find(e => e.id === preset);
    return found ? found.name : String(preset);
  };

  return (
    <div className="form-control mb-3">
      <label className="label">
        <span className="label-text font-medium">{t('event_form.cycle_presets')}</span>
      </label>
      <p className="text-xs opacity-60 mb-2">{t('event_form.cycle_presets_hint')}</p>

      {presets.length === 0 && (
        <div className="text-sm opacity-50 italic mb-2">{t('event_form.cycle_no_presets')}</div>
      )}

      {presets.length > 0 && (
        <div className="space-y-1 mb-2">
          {presets.map((preset, idx) => (
            <div key={idx} className="flex items-center gap-2 bg-base-200 rounded-lg px-3 py-1.5">
              <span className="text-xs font-mono opacity-60 w-5">{idx + 1}.</span>
              <span className="text-sm flex-1">{getPresetName(preset)}</span>
              <div className="flex gap-0.5">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => movePreset(idx, -1)}
                  disabled={idx === 0}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => movePreset(idx, 1)}
                  disabled={idx === presets.length - 1}
                >
                  ▼
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs text-error"
                  onClick={() => removePreset(idx)}
                >
                  <FaTrash size={10} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {availableEffects.length > 0 ? (
        <div className="flex gap-2">
          <select
            className="select select-bordered select-sm flex-1"
            defaultValue=""
            onChange={(e) => {
              const val = e.target.value;
              if (!val) return;
              // WLED effects are numeric IDs
              const parsed = isWled ? parseInt(val) : val;
              addPreset(parsed);
              e.target.value = '';
            }}
          >
            <option value="">{t('event_form.cycle_add_preset')}</option>
            {availableEffects
              .filter(fx => !presets.includes(fx.id))
              .map((fx) => (
                <option key={String(fx.id)} value={String(fx.id)}>{fx.name}</option>
              ))}
          </select>
        </div>
      ) : (
        <div className="text-xs text-warning">
          {isEspHome
            ? 'No effects found on this light. Re-discover the device to load effects.'
            : 'No effects available. Re-discover the device to load effects.'}
        </div>
      )}
    </div>
  );
};

export default RemoteOutputAction;
