import React, { useState, useCallback } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FaExclamationTriangle } from 'react-icons/fa';
import HelpLabel from './components/HelpLabel';
import {
  EXPANDER_BOARDS,
  type ExpanderBoardType,
  generateExpanderOutputEntries,
  detectExpanderBoardType,
  EXPANDER_OUTPUT_PREFIX,
} from './helpers/expanderBoards';
import { DEFAULT_ADDRESSES } from './Mcp23017Form';

interface ExampleFile {
  filename: string;
  category: string;
  path: string;
}

interface ValidationResult {
  compatible: boolean;
  incompatible_outputs: Array<{ boneio_output: string; id: string; name: string }>;
  incompatible_inputs: Array<{ boneio_input: string; id: string; section: string }>;
  available_example_files: ExampleFile[];
  new_device_type: string;
  normalized_type: string;
}

interface BoneIOFormProps {
  data: any;
  onChange: (data: any) => void;
  allOutputs?: any[];
  allEvents?: any[];
  allBinarySensors?: any[];
  /** @deprecated reload is now triggered internally after restart */
  onExpanderAdded?: () => void;
}

/**
 * Custom form for boneIO section configuration.
 * Fields: name, version, device_type
 */
const BoneIOForm: React.FC<BoneIOFormProps> = ({
  data,
  onChange,
  allOutputs = [],
  allEvents = [],
  allBinarySensors = [],
}) => {
  const { t } = useTranslation();
  const [showWarningModal, setShowWarningModal] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [pendingDeviceType, setPendingDeviceType] = useState<string | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [resetResult, setResetResult] = useState<any>(null);

  // Expander state
  const [showAddExpander, setShowAddExpander] = useState(false);
  const [expanderBoardType, setExpanderBoardType] = useState<ExpanderBoardType>('32x10A');
  const [expanderAddresses, setExpanderAddresses] = useState({
    expander_left: DEFAULT_ADDRESSES.expander_left,
    expander_right: DEFAULT_ADDRESSES.expander_right,
  });
  const [expanderBusy, setExpanderBusy] = useState(false);
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);
  const [expanderResult, setExpanderResult] = useState<{ status: string; message?: string } | null>(null);
  const [blockedByInputs, setBlockedByInputs] = useState<string[]>([]);

  const exOutputs = allOutputs.filter(
    (o: any) => (o?.id || o?.boneio_output || '').startsWith(EXPANDER_OUTPUT_PREFIX)
  );
  const hasExpander = exOutputs.length > 0;
  const detectedBoardType = detectExpanderBoardType(exOutputs);

  const ADDRESS_OPTIONS = ['0x20', '0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x27'];

  const restartAndReload = async () => {
    try {
      await axios.post('/api/restart');
    } catch {
      // expected — server is restarting
    }
    // Wait for service to come back, then reload page
    setTimeout(() => window.location.reload(), 4000);
  };

  const handleAddExpander = async () => {
    setExpanderBusy(true);
    setExpanderResult(null);
    try {
      const outputs = generateExpanderOutputEntries(expanderBoardType);
      const res = await axios.post('/api/config/expander', {
        board_type: expanderBoardType,
        outputs,
        expander_left_address: expanderAddresses.expander_left,
        expander_right_address: expanderAddresses.expander_right,
      });
      setExpanderResult({ status: 'success', message: res.data.expansion_file });
      setShowAddExpander(false);
      await restartAndReload();
    } catch (e: any) {
      setExpanderResult({ status: 'error', message: e?.response?.data?.detail || String(e) });
      setExpanderBusy(false);
    }
  };

  const findBlockingInputs = (): string[] => {
    const exIds = new Set(
      exOutputs.flatMap((o: any) => [o.id, o.boneio_output].filter(Boolean))
    );
    const blocked: string[] = [];
    const check = (actions: any, name: string) => {
      if (!actions) return;
      for (const list of Object.values(actions)) {
        if (!Array.isArray(list)) continue;
        for (const action of list) {
          if (
            (action.pin && exIds.has(action.pin)) ||
            (action.boneio_output && exIds.has(action.boneio_output))
          ) {
            if (!blocked.includes(name)) blocked.push(name);
          }
        }
      }
    };
    allEvents.forEach((e: any) => check(e.actions, e.name || e.boneio_input || 'event'));
    allBinarySensors.forEach((s: any) => check(s.actions, s.name || s.boneio_input || 'sensor'));
    return blocked;
  };

  const handleRemoveExpander = async () => {
    const blocking = findBlockingInputs();
    if (blocking.length > 0) {
      setBlockedByInputs(blocking);
      setShowRemoveConfirm(false);
      return;
    }

    setExpanderBusy(true);
    setShowRemoveConfirm(false);
    setExpanderResult(null);
    try {
      await axios.post('/api/config/expander/remove', {
        board_type: detectedBoardType,
      });
      setExpanderResult({ status: 'success' });
      await restartAndReload();
    } catch (e: any) {
      setExpanderResult({ status: 'error', message: e?.response?.data?.detail || String(e) });
      setExpanderBusy(false);
    }
  };

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const validateDeviceTypeChange = useCallback(async (newDeviceType: string) => {
    if (!newDeviceType || newDeviceType === data?.device_type) {
      handleChange('device_type', newDeviceType || undefined);
      return;
    }

    setIsLoading(true);
    try {
      const { data: result } = await axios.post<ValidationResult>('/api/config/validate_device_type_change', {
        new_device_type: newDeviceType,
        version: data?.version || '0.8',
      });

      if (result.compatible) {
        // No conflicts, apply change directly
        handleChange('device_type', newDeviceType);
      } else {
        // Show warning modal
        setValidationResult(result);
        setPendingDeviceType(newDeviceType);
        // Pre-select categories that have example files
        const categories = [...new Set(result.available_example_files.map(f => f.category))];
        const relevantCategories = categories.filter(c => 
          ['output', 'event', 'binary_sensor', 'cover'].includes(c)
        );
        setSelectedCategories(relevantCategories);
        setShowWarningModal(true);
      }
    } catch (error) {
      console.error('Failed to validate device type change:', error);
      // On error, allow the change but warn user
      handleChange('device_type', newDeviceType);
    } finally {
      setIsLoading(false);
    }
  }, [data, handleChange]);

  const handleCancelChange = () => {
    setShowWarningModal(false);
    setValidationResult(null);
    setPendingDeviceType(null);
    setSelectedCategories([]);
    setResetResult(null);
  };

  const handleApplyWithExampleConfig = async () => {
    if (!pendingDeviceType || selectedCategories.length === 0) return;

    setIsLoading(true);
    try {
      const { data: result } = await axios.post('/api/factory_reset/partial', {
        device_type: pendingDeviceType,
        files_to_replace: selectedCategories,
      });
      setResetResult(result);

      if (result.status === 'success') {
        // Apply device type change
        handleChange('device_type', pendingDeviceType);
        // Show success, user needs to restart
      }
    } catch (error) {
      console.error('Failed to apply example config:', error);
      setResetResult({ status: 'error', message: String(error) });
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCategory = (category: string) => {
    setSelectedCategories(prev =>
      prev.includes(category)
        ? prev.filter(c => c !== category)
        : [...prev, category]
    );
  };

  // Check if name is required (when version or device_type is set)
  const hasOtherFields = data?.version || data?.device_type;
  const hasName = data?.name && data.name.trim() !== '';
  const nameError = hasOtherFields && !hasName;

  return (
    <div className="space-y-4">
      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">
            {t('boneio_config.name')}
            {hasOtherFields && <span className="text-error ml-1">*</span>}
          </span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full ${nameError ? 'input-error' : ''}`}
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder={t('boneio_config.name_placeholder')}
        />
        {nameError ? (
          <label className="label whitespace-normal"><span className="label-text-alt text-error wrap-break-word">{t('boneio_config.name_required_error')}</span></label>
        ) : (
          <HelpLabel>{t('boneio_config.name_help')}</HelpLabel>
        )}
      </div>

      {/* Version */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('boneio_config.hardware_version')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.version || ''}
          onChange={(e) => handleChange('version', e.target.value || undefined)}
        >
          <option value="">{t('boneio_config.select_version')}</option>
          <option value="0.2">0.2</option>
          <option value="0.3">0.3</option>
          <option value="0.4">0.4</option>
          <option value="0.5">0.5</option>
          <option value="0.6">0.6</option>
          <option value="0.7">0.7</option>
          <option value="0.8">0.8</option>
        </select>
        <HelpLabel>{t('boneio_config.hardware_version_help')}</HelpLabel>
      </div>

      {/* Device Type */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('boneio_config.device_type')}</span>
        </label>
        <div className="relative">
          <select
            className="select select-bordered w-full"
            value={(data?.device_type || '').toLowerCase()}
            onChange={(e) => validateDeviceTypeChange(e.target.value)}
            disabled={isLoading}
          >
            <option value="">{t('boneio_config.select_device_type')}</option>
            <option value="32x10a">32x10A (32 outputs, 10A each)</option>
            <option value="32x5a">32x5A (32 outputs, 5A each)</option>
            <option value="24x16a">24x16A (24 outputs, 16A each)</option>
            <option value="48x4a">48x4A (48 outputs, 4A each) - DISCONTINUED</option>
            <option value="cover">Cover</option>
            <option value="cover mix">Cover Mix</option>
          </select>
          {isLoading && (
            <span className="absolute right-10 top-1/2 -translate-y-1/2 loading loading-spinner loading-sm"></span>
          )}
        </div>
        <HelpLabel>{t('boneio_config.device_type_help')}</HelpLabel>
      </div>

      {/* Restart overlay (during expander add/remove) */}
      {expanderBusy && expanderResult?.status === 'success' && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body items-center text-center">
              <span className="loading loading-spinner loading-lg text-primary" />
              <p className="font-medium">{t('settings.restarting')}</p>
              <p className="text-sm text-base-content/60">{t('boneio_config.expander_saved')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Expansion board */}
      <div className="divider text-sm">{t('boneio_config.expander_section')}</div>
      <div className="space-y-3">
        {expanderResult && (
          <div className={`alert py-2 text-sm ${expanderResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
            {expanderResult.status === 'success'
              ? t('boneio_config.expander_saved')
              : expanderResult.message}
          </div>
        )}

        {blockedByInputs.length > 0 && (
          <div className="alert alert-error py-2">
            <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="font-medium text-sm">{t('mcp.expander_remove_blocked')}</p>
              <ul className="text-xs mt-1 list-disc list-inside">
                {blockedByInputs.map(n => <li key={n}>{n}</li>)}
              </ul>
            </div>
            <button className="btn btn-xs btn-ghost" onClick={() => setBlockedByInputs([])}>✕</button>
          </div>
        )}

        {hasExpander ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="badge badge-success">{t('boneio_config.expander_active')}</span>
            {detectedBoardType && (
              <span className="badge badge-outline">{EXPANDER_BOARDS[detectedBoardType].label}</span>
            )}
            <span className="text-sm text-base-content/60">{exOutputs.length} {t('mcp.expander_outputs_active')}</span>
            <div className="ml-auto">
              {!showRemoveConfirm ? (
                <button className="btn btn-error btn-outline btn-sm" onClick={() => setShowRemoveConfirm(true)} disabled={expanderBusy}>
                  {t('boneio_config.expander_remove')}
                </button>
              ) : (
                <div className="flex gap-2 items-center">
                  <span className="text-sm text-warning">{t('boneio_config.expander_remove_confirm')}</span>
                  <button className="btn btn-ghost btn-xs" onClick={() => setShowRemoveConfirm(false)}>{t('common.cancel')}</button>
                  <button className="btn btn-error btn-xs" onClick={handleRemoveExpander} disabled={expanderBusy}>
                    {expanderBusy && <span className="loading loading-spinner loading-xs" />}
                    {t('boneio_config.expander_remove')}
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : !showAddExpander ? (
          <button className="btn btn-primary btn-sm" onClick={() => setShowAddExpander(true)}>
            + {t('boneio_config.expander_add')}
          </button>
        ) : (
          <div className="card bg-base-200 shadow-sm">
            <div className="card-body py-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="form-control">
                  <label className="label py-1"><span className="label-text font-medium">{t('mcp.expander_board_type')}</span></label>
                  <select className="select select-bordered select-sm" value={expanderBoardType} onChange={e => setExpanderBoardType(e.target.value as ExpanderBoardType)}>
                    {(Object.keys(EXPANDER_BOARDS) as ExpanderBoardType[]).map(bt => (
                      <option key={bt} value={bt}>{EXPANDER_BOARDS[bt].label}</option>
                    ))}
                  </select>
                </div>
                {(['expander_left', 'expander_right'] as const).map(id => (
                  <div key={id} className="form-control">
                    <label className="label py-1"><span className="label-text font-medium font-mono text-sm">{id}</span></label>
                    <select className="select select-bordered select-sm" value={expanderAddresses[id]} onChange={e => setExpanderAddresses(p => ({ ...p, [id]: e.target.value }))}>
                      {ADDRESS_OPTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div className="text-xs text-base-content/50">
                {t('mcp.expander_outputs_preview')
                  .replace('{count}', String(EXPANDER_BOARDS[expanderBoardType].outputs.length))
                  .replace('{first}', EXPANDER_BOARDS[expanderBoardType].outputs[0]?.slotId ?? '')
                  .replace('{last}', (() => { const o = EXPANDER_BOARDS[expanderBoardType].outputs; return o[o.length - 1]?.slotId ?? ''; })())}
              </div>
              <div className="flex gap-2">
                <button className="btn btn-primary btn-sm" onClick={handleAddExpander} disabled={expanderBusy}>
                  {expanderBusy && <span className="loading loading-spinner loading-xs" />}
                  {t('boneio_config.expander_add')}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowAddExpander(false)}>{t('common.cancel')}</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* HA Child Devices (experimental) */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            className="toggle toggle-warning"
            checked={data?.ha_child_devices || false}
            onChange={(e) => handleChange('ha_child_devices', e.target.checked)}
          />
          <span className="label-text font-medium">
            {t('boneio_config.ha_child_devices')}
          </span>
        </label>
        <HelpLabel>{t('boneio_config.ha_child_devices_help')}</HelpLabel>
      </div>

      {/* HA Child Devices Naming Style (shown only when ha_child_devices is enabled) */}
      {data?.ha_child_devices && (
        <div className="form-control ml-4">
          <label className="label">
            <span className="label-text font-medium">{t('boneio_config.ha_child_devices_naming')}</span>
          </label>
          <select
            className="select select-bordered w-full"
            value={data?.ha_child_devices_naming || 'default'}
            onChange={(e) => handleChange('ha_child_devices_naming', e.target.value)}
          >
            <option value="default">{t('boneio_config.ha_child_devices_naming_default')}</option>
            <option value="device_name">{t('boneio_config.ha_child_devices_naming_device_name')}</option>
            <option value="device_name_area">{t('boneio_config.ha_child_devices_naming_device_name_area')}</option>
          </select>
          <HelpLabel>{t('boneio_config.ha_child_devices_naming_help')}</HelpLabel>
        </div>
      )}

      {/* Device Type Change Warning Modal */}
      {showWarningModal && validationResult && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg flex items-center gap-2">
              <FaExclamationTriangle className="text-warning" />
              {t('boneio_config.device_type_change_warning_title')}
            </h3>
            
            <div className="py-4 space-y-4">
              <p className="text-sm">
                {t('boneio_config.device_type_change_warning_desc')}
              </p>

              {/* Incompatible outputs */}
              {validationResult.incompatible_outputs.length > 0 && (
                <div className="alert alert-warning">
                  <div>
                    <p className="font-semibold">{t('boneio_config.incompatible_outputs')}:</p>
                    <ul className="list-disc list-inside text-sm mt-1">
                      {validationResult.incompatible_outputs.map((out, idx) => (
                        <li key={idx}>
                          <code>{out.boneio_output}</code> ({out.name})
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Incompatible inputs */}
              {validationResult.incompatible_inputs.length > 0 && (
                <div className="alert alert-warning">
                  <div>
                    <p className="font-semibold">{t('boneio_config.incompatible_inputs')}:</p>
                    <ul className="list-disc list-inside text-sm mt-1">
                      {validationResult.incompatible_inputs.map((inp, idx) => (
                        <li key={idx}>
                          <code>{inp.boneio_input}</code> ({inp.section})
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Example config option */}
              <div className="divider">{t('boneio_config.load_example_config')}</div>
              
              <p className="text-sm">
                {t('boneio_config.select_files_to_replace')}
              </p>

              <div className="flex flex-wrap gap-2">
                {['output', 'event', 'binary_sensor', 'cover'].map(category => {
                  const hasFile = validationResult.available_example_files.some(
                    f => f.category === category
                  );
                  if (!hasFile) return null;
                  return (
                    <label key={category} className="label cursor-pointer gap-2">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-primary"
                        checked={selectedCategories.includes(category)}
                        onChange={() => toggleCategory(category)}
                      />
                      <span className="label-text">{category}.yaml</span>
                    </label>
                  );
                })}
              </div>

              {/* Reset result */}
              {resetResult && (
                <div className={`alert ${resetResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
                  <div>
                    <p>{resetResult.message}</p>
                    {resetResult.status === 'success' && (
                      <p className="text-sm mt-1">
                        {t('boneio_config.restart_required')}
                      </p>
                    )}
                    {resetResult.copied_files && (
                      <p className="text-sm mt-1">
                        {t('boneio_config.copied_files')}: {resetResult.copied_files.join(', ')}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-action">
              <button
                className="btn"
                onClick={handleCancelChange}
                disabled={isLoading}
              >
                {t('common.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleApplyWithExampleConfig}
                disabled={isLoading || selectedCategories.length === 0}
              >
                {isLoading ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  t('boneio_config.load_and_apply')
                )}
              </button>
            </div>
          </div>
          <div className="modal-backdrop" onClick={handleCancelChange}></div>
        </div>
      )}
    </div>
  );
};

export default BoneIOForm;
