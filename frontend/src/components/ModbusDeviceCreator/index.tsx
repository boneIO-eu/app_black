import { useState } from 'react';
import { Register, DeviceConfig, generateId, groupRegistersIntoBlocks } from './types';
import DeviceInfoSection from './DeviceInfoSection';
import SetBaseSection from './SetBaseSection';
import RegistersSection from './RegistersSection';
import ActionsSection from './ActionsSection';

export default function ModbusDeviceCreator() {
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
      const response = await fetch('/api/modbus/get', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address: testDeviceAddress,
          register_address: register.address,
          register_type: register.register_type,
          value_type: register.value_type,
        }),
      });
      
      const result = await response.json();
      
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
    await navigator.clipboard.writeText(json);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
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
