import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '../../hooks/useTranslation';
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
      <DialogContent className="max-w-xl bg-base-100 text-base-content rounded-lg border border-base-300 shadow-2xl p-6">
        <DialogHeader className="mb-4">
          <DialogTitle className="text-xl font-bold flex items-center gap-2">
            {t('modbus_wizard.title') || 'Add Modbus Device'}
          </DialogTitle>
        </DialogHeader>

        {/* Steps visual indicator */}
        <div className="w-full mb-6">
          <ul className="steps w-full text-xs">
            <li className={`step ${step >= 1 ? 'step-primary' : ''}`}>
              {t('modbus_wizard.step1_label') || 'Category'}
            </li>
            <li className={`step ${step >= 2 ? 'step-primary' : ''}`}>
              {t('modbus_wizard.step2_label') || 'Device Model'}
            </li>
            <li className={`step ${step >= 3 ? 'step-primary' : ''}`}>
              {t('modbus_wizard.step3_label') || 'Settings'}
            </li>
          </ul>
        </div>

        {/* Step 1: Category Selection & Search */}
        {step === 1 && (
          <div className="space-y-4">
            {/* Search Input */}
            <div className="form-control w-full relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('modbus_wizard.search_placeholder') || 'Search device by name, model or brand...'}
                className="input input-bordered w-full pl-10"
              />
              <FaSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-base-content/40" />
            </div>

            {searchQuery.trim() === '' ? (
              <>
                <h4 className="text-sm font-semibold mb-2">
                  {t('modbus_wizard.step1_title') || 'Or select device category:'}
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  {MODBUS_CATEGORIES.map((category) => (
                    <button
                      key={category}
                      type="button"
                      onClick={() => handleCategorySelect(category)}
                      className="flex flex-col items-center justify-center p-5 border border-base-300 hover:border-primary bg-base-200/50 hover:bg-primary/5 rounded-xl cursor-pointer transition-all duration-200 group text-center"
                    >
                      <div className="mb-3 transform group-hover:scale-110 transition-transform duration-200">
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
                <h4 className="text-sm font-semibold text-primary">
                  {t('modbus_wizard.search_results') || 'Search Results'} ({searchResults.length})
                </h4>
                <div className="max-h-[250px] overflow-y-auto space-y-2 pr-1 border border-base-300 rounded-lg p-2 bg-base-200/20">
                  {searchResults.map((device) => (
                    <button
                      key={device.modelKey}
                      type="button"
                      onClick={() => handleModelSelect(device)}
                      className="w-full flex items-center justify-between p-3 border border-base-300 hover:border-primary bg-base-100 hover:bg-primary/5 rounded-lg text-left transition-all cursor-pointer"
                    >
                      <div>
                        <div className="font-bold text-sm text-primary flex items-center gap-1.5">
                          {device.displayName}
                          {device.manufacturer && (
                            <span className="text-xs font-normal text-base-content/60">
                              by {device.manufacturer}
                            </span>
                          )}
                          <span className="badge badge-sm badge-ghost ml-1 text-[10px] capitalize">
                            {getCategoryLabel(device.category)}
                          </span>
                        </div>
                        <div className="text-xs text-base-content/70 mt-1 max-w-[400px] truncate">
                          {getDeviceDescription(device)}
                        </div>
                      </div>
                      <FaChevronRight className="text-base-content/30 text-xs" />
                    </button>
                  ))}
                  {searchResults.length === 0 && (
                    <div className="text-center py-6 text-base-content/60 text-sm">
                      {t('modbus_wizard.no_results') || 'No devices found matching your search.'}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Model Selection */}
        {step === 2 && (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-2">
              <h4 className="text-sm font-semibold">
                {t('modbus_wizard.step2_title') || 'Select device model:'}
              </h4>
              <span className="badge badge-secondary badge-outline text-xs">
                {getCategoryLabel(selectedCategory || '')}
              </span>
            </div>
            
            <div className="max-h-[300px] overflow-y-auto space-y-2 pr-1 border border-base-300 rounded-lg p-2 bg-base-200/20">
              {filteredDevices.map((device) => (
                <button
                  key={device.modelKey}
                  type="button"
                  onClick={() => handleModelSelect(device)}
                  className="w-full flex items-center justify-between p-3 border border-base-300 hover:border-primary bg-base-100 hover:bg-primary/5 rounded-lg text-left transition-all cursor-pointer"
                >
                  <div>
                    <div className="font-bold text-sm text-primary flex items-center gap-1.5">
                      {device.displayName}
                      {device.manufacturer && (
                        <span className="text-xs font-normal text-base-content/60">
                          by {device.manufacturer}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-base-content/70 mt-1 max-w-[400px] truncate">
                      {getDeviceDescription(device)}
                    </div>
                  </div>
                  <FaChevronRight className="text-base-content/30 text-xs" />
                </button>
              ))}
              {filteredDevices.length === 0 && (
                <div className="text-center py-6 text-base-content/60 text-sm">
                  {t('modbus_wizard.no_devices') || 'No devices found in this category.'}
                </div>
              )}
            </div>

            <div className="flex justify-start">
              <button
                type="button"
                onClick={handleBack}
                className="btn btn-ghost btn-sm gap-1"
              >
                <FaChevronLeft className="text-xs" />
                {t('modbus_wizard.back') || 'Back'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Parameters Configuration */}
        {step === 3 && selectedModel && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-primary/5 p-3 rounded-lg border border-primary/20 mb-2">
              <div className="text-xs font-semibold text-primary uppercase">
                {t('modbus_wizard.selected_device') || 'Selected Device'}
              </div>
              <div className="font-bold text-base text-base-content">
                {selectedModel.displayName}
              </div>
              <div className="text-xs text-base-content/75 mt-0.5">
                {selectedModel.manufacturer && `Manufacturer: ${selectedModel.manufacturer}`}
              </div>
            </div>

            {/* Address */}
            <div className="form-control w-full">
              <label className="label py-1">
                <span className="label-text font-semibold">
                  {t('modbus_wizard.address') || 'Modbus Address'}
                </span>
                <span className="label-text-alt text-xs">
                  {t('modbus_wizard.address_range') || 'Range: 1 - 247'}
                </span>
              </label>
              <input
                type="number"
                min="1"
                max="247"
                required
                value={address}
                onChange={(e) => setAddress(parseInt(e.target.value) || 1)}
                className={`input input-bordered w-full ${addressConflict ? 'input-error' : ''}`}
              />
              
              {/* Conflict warning */}
              {addressConflict && (
                <div className="text-error text-xs flex items-center gap-1.5 mt-1.5 font-medium animate-pulse">
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
                <div className="text-base-content/60 text-xs mt-1.5 flex items-center gap-1">
                  <span>{t('modbus_wizard.suggested_address_prefix') || 'Suggested free address:'}</span>
                  <button
                    type="button"
                    onClick={() => setAddress(suggestedAddress)}
                    className="link link-primary font-bold text-xs"
                  >
                    {suggestedAddress}
                  </button>
                </div>
              )}
            </div>

            {/* Name */}
            <div className="form-control w-full">
              <label className="label py-1">
                <span className="label-text font-semibold">
                  {t('modbus_wizard.name') || 'Display Name'}
                </span>
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Living Room Recuperator"
                className="input input-bordered w-full"
              />
            </div>

            {/* Area */}
            <div className="form-control w-full">
              <label className="label py-1">
                <span className="label-text font-semibold">
                  {t('modbus_wizard.area') || 'Area'}
                </span>
              </label>
              <select
                value={area}
                onChange={(e) => setArea(e.target.value)}
                className="select select-bordered w-full"
              >
                <option value="">{t('modbus_wizard.select_area') || 'Select area (optional)'}</option>
                {allAreas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Update Interval using SimpleTimePeriodInput */}
            <SimpleTimePeriodInput
              value={updateInterval}
              onChange={setUpdateInterval}
              label={t('modbus_wizard.update_interval') || 'Update Interval'}
              required
              minimum={1000}
            />

            {/* ID */}
            <div className="form-control w-full">
              <label className="label py-1">
                <span className="label-text font-semibold">
                  {t('modbus_wizard.id') || 'Device ID'}
                </span>
                <span className="label-text-alt text-xs text-base-content/60">
                  {t('modbus_wizard.id_help') || 'Unique alphanumeric ID'}
                </span>
              </label>
              <input
                type="text"
                required
                value={customId}
                onChange={(e) => setCustomId(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '_'))}
                placeholder="e.g. recuperator_wanas"
                className="input input-bordered w-full"
              />
            </div>

            {/* Actions */}
            <div className="flex justify-between items-center pt-2 mt-4 border-t border-base-300">
              <button
                type="button"
                onClick={handleBack}
                className="btn btn-ghost btn-sm gap-1"
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
                  className="btn btn-primary btn-sm gap-1.5"
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
