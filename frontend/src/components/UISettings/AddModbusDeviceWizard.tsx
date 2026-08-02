import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '../../hooks/useTranslation';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  MODBUS_DEVICE_CATALOG,
  MODBUS_CATEGORIES,
  ModbusDeviceInfo
} from '../../generated/modbusDeviceCatalog';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import {
  FaBolt,
  FaWind,
  FaSun,
  FaThermometerHalf,
  FaCogs,
  FaChevronRight,
  FaChevronLeft,
  FaExclamationTriangle,
  FaCheck,
  FaSearch
} from 'react-icons/fa';

interface Area {
  id: string;
  name: string;
}

interface UsedAddress {
  address: number;
  model: string;
  id: string;
  name: string;
}

interface AddModbusDeviceWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allAreas: Area[];
  allModbusDevices: any[];
  onAdd: (deviceConfig: any) => void;
}

export const AddModbusDeviceWizard: React.FC<AddModbusDeviceWizardProps> = ({
  open,
  onOpenChange,
  allAreas,
  allModbusDevices,
  onAdd,
}) => {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);

  /**
   * Get translated device description from i18n.
   * Falls back to the English description from the catalog.
   */
  const getDeviceDescription = (device: ModbusDeviceInfo): string => {
    const translated = t(`modbus_devices.${device.modelKey}.description`);
    // t() returns the key itself when translation is missing
    if (translated !== `modbus_devices.${device.modelKey}.description`) {
      return translated;
    }
    return device.description;
  };

  // Helper to generate dynamic display name suggestions
  const getNameSuggestions = () => {
    if (!selectedModel) return [];
    const isTemp = selectedModel.modelKey.includes('temp') || selectedModel.category === 'sensors';
    const isCover = selectedModel.category === 'covers';
    const isRelay = selectedModel.category === 'relays';

    // Find current area name
    const currentAreaObj = allAreas.find(a => a.id === area);
    const areaName = currentAreaObj ? currentAreaObj.name : '';

    const suggestions: string[] = [];

    if (areaName) {
      if (isTemp) {
        suggestions.push(`Temp ${areaName}`);
        suggestions.push(`${areaName} Temp`);
      } else if (isCover) {
        suggestions.push(`Roleta ${areaName}`);
      } else if (isRelay) {
        suggestions.push(`Światło ${areaName}`);
        suggestions.push(`Gniazdko ${areaName}`);
      }
      suggestions.push(areaName);
    }

    // Add other room suggestions
    const commonRooms = allAreas.length > 0
      ? allAreas.map(a => a.name)
      : ['Salon', 'Kuchnia', 'Sypialnia', 'Łazienka', 'Garaż', 'Korytarz'];

    commonRooms.forEach(room => {
      if (room !== areaName) {
        if (isTemp) {
          suggestions.push(`Temp ${room}`);
        } else if (isCover) {
          suggestions.push(`Roleta ${room}`);
        } else if (isRelay) {
          suggestions.push(`Światło ${room}`);
        } else {
          suggestions.push(room);
        }
      }
    });

    return [...new Set(suggestions)].slice(0, 6);
  };
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<ModbusDeviceInfo | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');

  // Form fields
  const [address, setAddress] = useState<number>(1);
  const [name, setName] = useState<string>('');
  const [area, setArea] = useState<string>('');
  const [updateInterval, setUpdateInterval] = useState<string>('30s');
  const [customId, setCustomId] = useState<string>('');

  // Conflict detection
  const [usedAddresses, setUsedAddresses] = useState<UsedAddress[]>([]);
  const [suggestedAddress, setSuggestedAddress] = useState<number>(1);

  // Load configured addresses from the backend to check for conflicts
  useEffect(() => {
    if (open) {
      axios.get('/api/modbus/used-addresses')
        .then(res => {
          const apiUsed = res.data.used_addresses || [];
          const localUsed: UsedAddress[] = allModbusDevices
            .filter(d => d.address !== undefined)
            .map(d => ({
              address: Number(d.address),
              model: d.model || '',
              id: d.id || '',
              name: d.name || '',
            }));
          // Merge based on address to prevent duplicates
          const mergedMap = new Map<number, UsedAddress>();
          apiUsed.forEach((u: UsedAddress) => mergedMap.set(u.address, u));
          localUsed.forEach((u: UsedAddress) => mergedMap.set(u.address, u));
          setUsedAddresses(Array.from(mergedMap.values()));
        })
        .catch(err => {
          console.error('Failed to fetch used Modbus addresses:', err);
          const localUsed: UsedAddress[] = allModbusDevices
            .filter(d => d.address !== undefined)
            .map(d => ({
              address: Number(d.address),
              model: d.model || '',
              id: d.id || '',
              name: d.name || '',
            }));
          setUsedAddresses(localUsed);
        });
    }
  }, [open, allModbusDevices]);

  // Handle resetting state on open/close
  useEffect(() => {
    if (!open) {
      setStep(1);
      setSelectedCategory(null);
      setSelectedModel(null);
      setSearchQuery('');
      setAddress(1);
      setName('');
      setArea('');
      setUpdateInterval('30s');
      setCustomId('');
    }
  }, [open]);

  // Compute a list of devices in the selected category
  const filteredDevices = Object.values(MODBUS_DEVICE_CATALOG).filter(
    (device) => device.category === selectedCategory
  );

  // Search filter across all devices
  const allDevices = Object.values(MODBUS_DEVICE_CATALOG);
  const searchResults = searchQuery.trim() === ''
    ? []
    : allDevices.filter(device => {
      const q = searchQuery.toLowerCase();
      return (
        device.displayName.toLowerCase().includes(q) ||
        device.modelKey.toLowerCase().includes(q) ||
        device.manufacturer.toLowerCase().includes(q) ||
        device.description.toLowerCase().includes(q) ||
        getDeviceDescription(device).toLowerCase().includes(q)
      );
    });

  // Find conflicts and suggestions when address or model changes
  useEffect(() => {
    if (!open) return;

    const usedSet = new Set(usedAddresses.map(u => u.address));
    let nextFree = 1;
    while (usedSet.has(nextFree)) {
      nextFree++;
    }
    setSuggestedAddress(nextFree);

    if (selectedModel) {
      const defaultAddr = selectedModel.defaultAddress;
      setAddress(usedSet.has(defaultAddr) ? nextFree : defaultAddr);
      setUpdateInterval(selectedModel.defaultUpdateInterval || '30s');
    }
  }, [selectedModel, usedAddresses, open]);

  // Auto-generate ID suffix when address or model changes
  useEffect(() => {
    if (selectedModel) {
      const genId = `${address}_${selectedModel.modelKey}`.toLowerCase().replace(/[^a-z0-9]+/g, '_');
      setCustomId(genId);
    }
  }, [address, selectedModel]);

  const handleCategorySelect = (category: string) => {
    setSelectedCategory(category);
    setStep(2);
  };

  const handleModelSelect = (device: ModbusDeviceInfo) => {
    setSelectedModel(device);
    setName(device.displayName);
    setStep(3);
  };

  const handleBack = () => {
    if (step === 3 && searchQuery.trim() !== '') {
      // If we skipped step 2 via search, go back to step 1
      setStep(1);
    } else if (step > 1) {
      setStep(step - 1);
    }
  };

  const addressConflict = usedAddresses.find(u => u.address === address);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) return;

    if (addressConflict) {
      alert(t('modbus_wizard.address_conflict_alert') || 'This Modbus address is already in use!');
      return;
    }

    const deviceConfig: any = {
      model: selectedModel.modelKey,
      address: Number(address),
      name: name.trim(),
      update_interval: updateInterval,
    };

    if (area) {
      deviceConfig.area = area;
    }
    if (customId) {
      deviceConfig.id = customId.trim();
    }

    onAdd(deviceConfig);
    onOpenChange(false);
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'energy_meters':
        return <FaBolt className="text-warning text-3xl" />;
      case 'hvac':
        return <FaWind className="text-info text-3xl" />;
      case 'inverters':
        return <FaSun className="text-amber-500 text-3xl" />;
      case 'sensors':
        return <FaThermometerHalf className="text-success text-3xl" />;
      default:
        return <FaCogs className="text-neutral-content text-3xl" />;
    }
  };

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'energy_meters':
        return t('modbus_wizard.category_energy_meters') || 'Energy Meters';
      case 'hvac':
        return t('modbus_wizard.category_hvac') || 'HVAC / Ventilation';
      case 'inverters':
        return t('modbus_wizard.category_inverters') || 'Inverters';
      case 'sensors':
        return t('modbus_wizard.category_sensors') || 'Sensors';
      case 'other':
        return t('modbus_wizard.category_other') || 'Other';
      default:
        return category;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col bg-base-100 shadow-2xl p-3.5 sm:p-6 border border-base-300 rounded-lg sm:max-w-xl max-h-[85vh] overflow-hidden text-base-content">
        <DialogHeader className="mb-4">
          <DialogTitle className="flex items-center gap-2 font-bold text-xl">
            {t('modbus_wizard.title') || 'Add Modbus Device'}
          </DialogTitle>
        </DialogHeader>

        {/* Steps visual indicator */}
        <div className="mb-3 w-full">
          <ul className="w-full text-xs steps">
            <li className={`step ${step >= 1 ? 'step-primary' : ''} whitespace-normal wrap-break-word`}>
              {t('modbus_wizard.step1_label') || 'Category'}
            </li>
            <li className={`step ${step >= 2 ? 'step-primary' : ''} whitespace-normal wrap-break-word`}>
              {t('modbus_wizard.step2_label') || 'Device Model'}
            </li>
            <li className={`step ${step >= 3 ? 'step-primary' : ''} whitespace-normal wrap-break-word`}>
              {t('modbus_wizard.step3_label') || 'Settings'}
            </li>
          </ul>
        </div>

        {/* Step 1: Category Selection & Search */}
        {step === 1 && (
          <div className="flex flex-col flex-1 space-y-4 min-h-0">
            {/* Search Input */}
            <div className="relative w-full form-control shrink-0">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('modbus_wizard.search_placeholder') || 'Search device by name, model or brand...'}
                className="pl-10 w-full input input-bordered"
              />
              <FaSearch className="top-1/2 left-3.5 absolute text-base-content/40 -translate-y-1/2" />
            </div>

            <div className="flex-1 pr-3.5 pl-0.5 overflow-y-auto">
              {searchQuery.trim() === '' ? (
                <>
                  <h4 className="mb-2 font-semibold text-sm">
                    {t('modbus_wizard.step1_title') || 'Or select device category:'}
                  </h4>
                  <div className="gap-4 grid grid-cols-2">
                    {MODBUS_CATEGORIES.map((category) => (
                      <button
                        key={category}
                        type="button"
                        onClick={() => handleCategorySelect(category)}
                        className="group flex flex-col justify-center items-center bg-base-200/50 hover:bg-primary/5 p-5 border border-base-300 hover:border-primary rounded-xl text-center transition-all duration-200 cursor-pointer"
                      >
                        <div className="mb-3 group-hover:scale-110 transition-transform duration-200 transform">
                          {getCategoryIcon(category)}
                        </div>
                        <span className="font-medium text-sm">
                          {getCategoryLabel(category)}
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="space-y-3">
                  <h4 className="font-semibold text-primary text-sm">
                    {t('modbus_wizard.search_results') || 'Search Results'} ({searchResults.length})
                  </h4>
                  <div className="bg-base-100 shadow-xs border border-base-300 rounded-lg divide-y divide-base-300 max-h-62.5 overflow-y-auto">
                    {searchResults.map((device) => (
                      <button
                        key={device.modelKey}
                        type="button"
                        onClick={() => handleModelSelect(device)}
                        className="flex justify-between items-center hover:bg-base-200/50 p-3.5 border-none first:rounded-t-lg last:rounded-b-lg w-full text-left transition-all cursor-pointer"
                      >
                        <div>
                          <div className="flex items-center gap-1.5 font-bold text-primary text-sm">
                            {device.displayName}
                            {device.manufacturer && (
                              <span className="font-normal text-xs text-base-content/60">
                                by {device.manufacturer}
                              </span>
                            )}
                            <span className="ml-1 text-[10px] capitalize badge badge-sm badge-ghost">
                              {getCategoryLabel(device.category)}
                            </span>
                          </div>
                          <div className="mt-1 max-w-full text-xs text-base-content/70 truncate">
                            {getDeviceDescription(device)}
                          </div>
                        </div>
                        <FaChevronRight className="text-xs text-base-content/30" />
                      </button>
                    ))}
                    {searchResults.length === 0 && (
                      <div className="py-6 text-sm text-base-content/60 text-center">
                        {t('modbus_wizard.no_results') || 'No devices found matching your search.'}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 2: Model Selection */}
        {step === 2 && (
          <div className="flex flex-col flex-1 space-y-4 min-h-0">
            <div className="flex justify-between items-center mb-1 shrink-0">
              <h4 className="font-semibold text-sm">
                {t('modbus_wizard.step2_title') || 'Select device model:'}
              </h4>
              <span className="badge-outline text-xs badge badge-secondary">
                {getCategoryLabel(selectedCategory || '')}
              </span>
            </div>

            <div className="flex-1 pr-3.5 pl-0.5 overflow-y-auto">
              <div className="bg-base-100 shadow-xs border border-base-300 rounded-lg divide-y divide-base-300">
                {filteredDevices.map((device) => (
                  <button
                    key={device.modelKey}
                    type="button"
                    onClick={() => handleModelSelect(device)}
                    className="flex justify-between items-center hover:bg-base-200/50 p-3.5 border-none first:rounded-t-lg last:rounded-b-lg w-full text-left transition-all cursor-pointer"
                  >
                    <div>
                      <div className="flex items-center gap-1.5 font-bold text-primary text-sm">
                        {device.displayName}
                        {device.manufacturer && (
                          <span className="font-normal text-xs text-base-content/60">
                            by {device.manufacturer}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 max-w-full text-xs text-base-content/70 truncate">
                        {getDeviceDescription(device)}
                      </div>
                    </div>
                    <FaChevronRight className="text-xs text-base-content/30" />
                  </button>
                ))}
                {filteredDevices.length === 0 && (
                  <div className="py-6 text-sm text-base-content/60 text-center">
                    {t('modbus_wizard.no_devices') || 'No devices found in this category.'}
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-start mt-2 pt-2 border-base-300 border-t shrink-0">
              <button
                type="button"
                onClick={handleBack}
                className="gap-1 btn btn-ghost btn-sm"
              >
                <FaChevronLeft className="text-xs" />
                {t('modbus_wizard.back') || 'Back'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Parameters Configuration */}
        {step === 3 && selectedModel && (
          <form onSubmit={handleSubmit} className="flex flex-col flex-1 space-y-4 min-h-0">
            <div className="flex-1 space-y-4 py-1 pr-3.5 pl-0.5 min-h-0 overflow-y-auto">
              <div className="bg-primary/5 mb-1 p-2.5 border border-primary/20 rounded-lg shrink-0">
                <div className="font-semibold text-primary text-xs uppercase">
                  {t('modbus_wizard.selected_device') || 'Selected Device'}
                </div>
                <div className="font-bold text-base text-base-content">
                  {selectedModel.displayName}
                </div>
                <div className="mt-0.5 text-xs text-base-content/75">
                  {selectedModel.manufacturer && `Manufacturer: ${selectedModel.manufacturer}`}
                </div>
              </div>

              <div className="gap-4 grid grid-cols-1 sm:grid-cols-2">
                {/* Display Name */}
                <div className="sm:col-span-2 w-full form-control">
                  <label className="py-1 label">
                    <span className="font-semibold label-text">
                      {t('modbus_wizard.name') || 'Display Name'}
                    </span>
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Living Room Recuperator"
                    className="w-full input input-bordered"
                  />
                  {/* Scrollable Quick suggestions chips */}
                  <div className="flex flex-wrap gap-1.5 mt-2 pb-1 max-w-full overflow-x-auto no-scrollbar">
                    {getNameSuggestions().map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => {
                          setName(s);
                          const genId = `${address}_${s.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`;
                          setCustomId(genId);
                        }}
                        className="border-base-300 hover:border-neutral btn-outline font-normal btn btn-xs btn-neutral"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Modbus Address */}
                <div className="w-full form-control">
                  <label className="flex justify-between items-center py-1 label">
                    <span className="font-semibold label-text">
                      {t('modbus_wizard.address') || 'Modbus Address'}
                    </span>
                    <span className="label-text-alt text-xs text-base-content/60">
                      {t('modbus_wizard.address_range') || '1 - 247'}
                    </span>
                  </label>
                  <NumericInput
                    className={addressConflict ? 'input-error' : ''}
                    value={address}
                    onChange={(v) => setAddress(v === '' ? 1 : v)}
                    min={1}
                    max={247}
                  />

                  {/* Conflict warning */}
                  {addressConflict && (
                    <div className="flex items-center gap-1.5 mt-1.5 font-medium text-error text-xs animate-pulse">
                      <FaExclamationTriangle className="shrink-0" />
                      <span>
                        {t('modbus_wizard.address_in_use', {
                          address,
                          device: addressConflict.name || addressConflict.model
                        }) || `Address ${address} is already in use by ${addressConflict.name || addressConflict.model}`}
                      </span>
                    </div>
                  )}

                  {/* Suggestions */}
                  {!addressConflict && suggestedAddress !== address && (
                    <div className="flex items-center gap-1 mt-1.5 text-xs text-base-content/60">
                      <span>{t('modbus_wizard.suggested_address_prefix') || 'Suggested free:'}</span>
                      <button
                        type="button"
                        onClick={() => setAddress(suggestedAddress)}
                        className="font-bold text-xs link link-primary"
                      >
                        {suggestedAddress}
                      </button>
                    </div>
                  )}
                </div>

                {/* ID */}
                <div className="w-full form-control">
                  <label className="py-1 label">
                    <span className="font-semibold label-text">
                      {t('modbus_wizard.id') || 'Device ID'}
                    </span>
                  </label>
                  <input
                    type="text"
                    required
                    value={customId}
                    onChange={(e) => setCustomId(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '_'))}
                    placeholder="e.g. recuperator_wanas"
                    className="w-full input input-bordered"
                  />
                  <span className="mt-1 pl-1 text-[11px] text-base-content/50">
                    {t('modbus_wizard.id_help') || 'Unique alphanumeric ID'}
                  </span>
                </div>

                {/* Update Interval using SimpleTimePeriodInput */}
                <div className="sm:col-span-2 w-full form-control">
                  <SimpleTimePeriodInput
                    value={updateInterval}
                    onChange={setUpdateInterval}
                    label={t('modbus_wizard.update_interval') || 'Update Interval'}
                    required
                    minimum={1000}
                  />
                </div>

                {/* Area — full width, at the bottom */}
                <div className="sm:col-span-2">
                  <AreaSelect
                    value={area}
                    onChange={(areaId) => setArea(areaId || '')}
                    areas={allAreas}
                    label={t('modbus_wizard.area') || 'Area'}
                    hideHint
                  />
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-between items-center bg-base-100 pt-3 border-base-300 border-t shrink-0">
              <button
                type="button"
                onClick={handleBack}
                className="gap-1 btn btn-ghost btn-sm"
              >
                <FaChevronLeft className="text-xs" />
                {t('modbus_wizard.back') || 'Back'}
              </button>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="btn btn-ghost btn-sm"
                >
                  {t('common.cancel') || 'Cancel'}
                </button>
                <button
                  type="submit"
                  disabled={!!addressConflict}
                  className="gap-1.5 btn btn-primary btn-sm"
                >
                  <FaCheck className="text-xs" />
                  {t('modbus_wizard.add_device') || 'Add Device'}
                </button>
              </div>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};
