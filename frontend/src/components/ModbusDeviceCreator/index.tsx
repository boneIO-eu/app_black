import { useState, useEffect, useRef } from 'react';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';
import { Register, DeviceConfig, CreatorState, generateId, groupRegistersIntoBlocks, parseDeviceConfig, STORAGE_KEY } from './types';
import { useTranslation } from '@/hooks/useTranslation';
import { FaUpload, FaTrash, FaUndo } from 'react-icons/fa';
import DeviceInfoSection from './DeviceInfoSection';
import SetBaseSection from './SetBaseSection';
import RegistersSection from './RegistersSection';
import ActionsSection from './ActionsSection';

export default function ModbusDeviceCreator() {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [modelName, setModelName] = useState('');
  const [fileName, setFileName] = useState('');
  const [category, setCategory] = useState('sensors');
  const [testDeviceAddress, setTestDeviceAddress] = useState(1);
  
  const [enableSetAddress, setEnableSetAddress] = useState(false);
  const [setAddressAddress, setSetAddressAddress] = useState(256);
  const [enableSetBaudrate, setEnableSetBaudrate] = useState(false);
  const [baudrateAddress, setBaudrateAddress] = useState(257);
  const [baudrateMappings, setBaudrateMappings] = useState<Record<string, number>>({
    '9600': 9600,
    '19200': 19200,
  });
  
  const [registers, setRegisters] = useState<Register[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [copied, setCopied] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [hasDraft, setHasDraft] = useState(false);

  // Load draft from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const state: CreatorState = JSON.parse(saved);
        if (state.registers && state.registers.length > 0) {
          setHasDraft(true);
        }
      } catch {
        // Invalid JSON, ignore
      }
    }
  }, []);

  const isInitialMount = useRef(true);

  // Auto-save to localStorage when state changes (skip initial mount)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    const state: CreatorState = {
      modelName,
      fileName,
      category,
      enableSetAddress,
      setAddressAddress,
      enableSetBaudrate,
      baudrateAddress,
      baudrateMappings,
      registers,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [modelName, fileName, category, enableSetAddress, setAddressAddress, enableSetBaudrate, baudrateAddress, baudrateMappings, registers]);

  const loadFromState = (state: Partial<CreatorState>) => {
    if (state.modelName !== undefined) setModelName(state.modelName);
    if (state.fileName !== undefined) setFileName(state.fileName);
    if (state.category !== undefined) setCategory(state.category);
    if (state.enableSetAddress !== undefined) setEnableSetAddress(state.enableSetAddress);
    if (state.setAddressAddress !== undefined) setSetAddressAddress(state.setAddressAddress);
    if (state.enableSetBaudrate !== undefined) setEnableSetBaudrate(state.enableSetBaudrate);
    if (state.baudrateAddress !== undefined) setBaudrateAddress(state.baudrateAddress);
    if (state.baudrateMappings !== undefined) setBaudrateMappings(state.baudrateMappings);
    if (state.registers !== undefined) setRegisters(state.registers);
    setHasDraft(false);
  };

  const loadDraft = () => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const state: CreatorState = JSON.parse(saved);
        loadFromState(state);
      } catch {
        // Invalid JSON, ignore
      }
    }
  };

  const clearDraft = () => {
    localStorage.removeItem(STORAGE_KEY);
    setHasDraft(false);
    setModelName('');
    setFileName('');
    setCategory('sensors');
    setEnableSetAddress(false);
    setSetAddressAddress(256);
    setEnableSetBaudrate(false);
    setBaudrateAddress(257);
    setBaudrateMappings({ '9600': 9600, '19200': 19200 });
    setRegisters([]);
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const config: DeviceConfig = JSON.parse(content);
        const state = parseDeviceConfig(config);
        loadFromState(state);
        // Set filename from uploaded file
        const nameWithoutExt = file.name.replace(/\.json$/, '');
        setFileName(nameWithoutExt);
      } catch (error) {
        alert(t('modbus_creator.invalid_json_file'));
      }
    };
    reader.readAsText(file);
    // Reset input so same file can be selected again
    event.target.value = '';
  };

  const isValid = () => {
    if (!modelName) return false;
    if (registers.length === 0) return false;
    for (const reg of registers) {
      if (!reg.name || !reg.unit_of_measurement) return false;
    }
    return true;
  };

  const addRegister = () => {
    const lastAddress = registers.length > 0 ? Math.max(...registers.map(r => r.address)) + 1 : 0;
    setRegisters([...registers, {
      id: generateId(),
      name: '',
      address: lastAddress,
      register_type: 'holding',
      unit_of_measurement: '',
      state_class: 'measurement',
      device_class: '',
      value_type: 'S_WORD',
      filters: [],
    }]);
  };

  const removeRegister = (registerId: string) => {
    setRegisters(registers.filter(r => r.id !== registerId));
  };

  const updateRegister = (registerId: string, updates: Partial<Register>) => {
    setRegisters(registers.map(r => r.id === registerId ? { ...r, ...updates } : r));
  };

  const testRegister = async (register: Register) => {
    setTesting(register.id);
    
    try {
      const { data: result } = await axios.post('/api/modbus/get', {
        address: testDeviceAddress,
        register_address: register.address,
        register_type: register.register_type,
        value_type: register.value_type,
      });
      
      if (result.success) {
        let displayValue = result.value;
        for (const filter of register.filters) {
          if (filter.multiply) displayValue = displayValue * filter.multiply;
          if (filter.offset) displayValue = displayValue + filter.offset;
        }
        
        updateRegister(register.id, {
          tested: true,
          testResult: `Raw: ${result.value}, Filtered: ${displayValue.toFixed(2)}`,
          testError: undefined,
        });
      } else {
        updateRegister(register.id, {
          tested: false,
          testResult: undefined,
          testError: result.error || 'No response',
        });
      }
    } catch (error) {
      updateRegister(register.id, {
        tested: false,
        testResult: undefined,
        testError: String(error),
      });
    } finally {
      setTesting(null);
    }
  };

  const generateJSON = (): DeviceConfig => {
    const config: DeviceConfig = {
      model: modelName,
      registers_base: groupRegistersIntoBlocks(registers),
    };
    
    if (enableSetAddress || enableSetBaudrate) {
      config.set_base = {};
      if (enableSetAddress) {
        config.set_base.set_address_address = setAddressAddress;
      }
      if (enableSetBaudrate) {
        config.set_base.set_baudrate = {
          address: baudrateAddress,
          possible_baudrates: baudrateMappings,
        };
      }
    }
    
    return config;
  };

  const downloadJSON = () => {
    const json = JSON.stringify(generateJSON(), null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileName || modelName.toLowerCase().replace(/\s+/g, '-')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyJSON = async () => {
    const json = JSON.stringify(generateJSON(), null, 2);
    await copyToClipboard(json);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Draft recovery banner */}
      {hasDraft && registers.length === 0 && (
        <div className="alert alert-info">
          <span>{t('modbus_creator.draft_found')}</span>
          <div className="flex gap-2">
            <button className="btn btn-sm btn-primary" onClick={loadDraft}>
              <FaUndo className="mr-1" /> {t('modbus_creator.restore_draft')}
            </button>
            <button className="btn btn-sm btn-ghost" onClick={clearDraft}>
              <FaTrash className="mr-1" /> {t('modbus_creator.discard_draft')}
            </button>
          </div>
        </div>
      )}

      {/* Load/Clear buttons */}
      <div className="flex gap-2 justify-end">
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleFileUpload}
          className="hidden"
        />
        <button
          className="btn btn-outline btn-sm"
          onClick={() => fileInputRef.current?.click()}
        >
          <FaUpload className="mr-1" /> {t('modbus_creator.load_json')}
        </button>
        {registers.length > 0 && (
          <button
            className="btn btn-outline btn-sm btn-error"
            onClick={clearDraft}
          >
            <FaTrash className="mr-1" /> {t('modbus_creator.clear_all')}
          </button>
        )}
      </div>

      <DeviceInfoSection
        modelName={modelName}
        setModelName={setModelName}
        fileName={fileName}
        setFileName={setFileName}
        category={category}
        setCategory={setCategory}
        testDeviceAddress={testDeviceAddress}
        setTestDeviceAddress={setTestDeviceAddress}
      />

      <SetBaseSection
        enableSetAddress={enableSetAddress}
        setEnableSetAddress={setEnableSetAddress}
        setAddressAddress={setAddressAddress}
        setSetAddressAddress={setSetAddressAddress}
        enableSetBaudrate={enableSetBaudrate}
        setEnableSetBaudrate={setEnableSetBaudrate}
        baudrateAddress={baudrateAddress}
        setBaudrateAddress={setBaudrateAddress}
        baudrateMappings={baudrateMappings}
        setBaudrateMappings={setBaudrateMappings}
      />

      <RegistersSection
        registers={registers}
        testing={testing}
        onAddRegister={addRegister}
        onUpdateRegister={updateRegister}
        onRemoveRegister={removeRegister}
        onTestRegister={testRegister}
      />

      <ActionsSection
        showPreview={showPreview}
        setShowPreview={setShowPreview}
        copied={copied}
        isValid={isValid()}
        generateJSON={generateJSON}
        onCopyJSON={copyJSON}
        onDownloadJSON={downloadJSON}
      />
    </div>
  );
}
