import { useState, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import React from 'react';
import {
  FaPlay, FaSearch, FaPlus, FaPause, FaFlask, FaCode, FaCopy, FaCheck, FaImage,
  FaBookOpen, FaPen, FaSlidersH, FaMagic, FaStop, FaTrash, FaCheckCircle, FaTimesCircle,
} from 'react-icons/fa';
import ModbusDeviceCreator from './ModbusDeviceCreator';
import axios from '@/api/axios';
import type { AxiosError } from 'axios';
import { MODBUS_DEVICE_CATALOG } from '../generated/modbusDeviceCatalog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { NumericInput } from '@/components/ui/NumericInput';
import { cn } from '@/lib/utils';
import {
  SettingsPage,
  SettingsCard,
  FormActions,
  FormField,
  NoticeCallout,
  ToggleRow,
} from './UISettings/ui';

type ApiError = AxiosError<{ error?: string }>;

interface ModbusConfig {
  configured: boolean;
  register_types: string[];
  value_types: string[];
}

interface ModbusResult {
  success: boolean;
  value?: number | string;
  raw_registers?: number[];
  message?: string;
  message_key?: string;
  error?: string;
  error_key?: string;
  error_params?: {
    device?: string;
    supported?: string;
  };
  devices?: number[];
  count?: number;
  cancelled?: boolean;
  scanned?: number;
  total?: number;
}

/** Write mode: FC06 = single register, FC16 = multiple registers */
type WriteMode = 'fc06' | 'fc16';

/** One simulated device from `/api/dev/fake-devices`. */
interface FakeDevice {
  device_id: string;
  model: string;
  manufacturer: string;
  category: string;
  entity_count: number;
}

/**
 * ModbusHelper - UI component for Modbus operations (GET, SET, SEARCH)
 * Uses the existing Modbus client from the manager.
 *
 * When this component is mounted, coordinator polling is automatically
 * paused so manual operations don't conflict with background reads on
 * the same UART bus.
 */
export default function ModbusHelper() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'get' | 'set' | 'search' | 'configure' | 'creator' | 'simulator'>('get');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ModbusResult | null>(null);
  const [config, setConfig] = useState<ModbusConfig | null>(null);
  const [suspended, setSuspended] = useState(false);

  // Common parameters
  const [address, setAddress] = useState(1);

  // GET parameters
  const [registerAddress, setRegisterAddress] = useState(0);
  const [registerType, setRegisterType] = useState('holding');
  const [valueType, setValueType] = useState('S_WORD');

  // SET parameters
  const [writeMode, setWriteMode] = useState<WriteMode>('fc06');
  const [writeRegisterAddress, setWriteRegisterAddress] = useState(0);
  const [writeValue, setWriteValue] = useState<number | ''>('');
  const [writeMultipleValues, setWriteMultipleValues] = useState('');

  // SEARCH parameters
  const [searchRegisterAddress, setSearchRegisterAddress] = useState(0);
  const [searchRegisterType, setSearchRegisterType] = useState('input');
  const [searchStartAddress, setSearchStartAddress] = useState(1);
  const [searchEndAddress, setSearchEndAddress] = useState(247);
  const [searchTimeout, setSearchTimeout] = useState(0.3);

  // CONFIGURE parameters
  const [configDevice, setConfigDevice] = useState('boneio-edge-temp');
  const [configUart, setConfigUart] = useState('uart4');
  const [configCurrentAddress, setConfigCurrentAddress] = useState(1);
  const [configCurrentBaudrate, setConfigCurrentBaudrate] = useState(9600);
  const [configOperation, setConfigOperation] = useState<'address' | 'baudrate'>('address');
  const [configNewAddress, setConfigNewAddress] = useState<number | ''>('');
  const [configNewBaudrate, setConfigNewBaudrate] = useState<number | ''>(9600);
  const [configBroadcast, setConfigBroadcast] = useState(false);

  // SIMULATOR parameters
  const [showSimulator, setShowSimulator] = useState(false);
  const [fakeDevices, setFakeDevices] = useState<FakeDevice[]>([]);
  const [selectedSimModel, setSelectedSimModel] = useState('wanas415');
  const [simAddress, setSimAddress] = useState(1);
  const [dashboardYaml, setDashboardYaml] = useState<string | null>(null);
  const [dashboardModel, setDashboardModel] = useState('');
  const [yamlCopied, setYamlCopied] = useState(false);

  const loadFakeDevices = async () => {
    try {
      const { data } = await axios.get('/api/dev/fake-devices');
      if (Array.isArray(data)) {
        setFakeDevices(data);
        setShowSimulator(true);
      } else {
        setFakeDevices([]);
        setShowSimulator(false);
      }
    } catch (err) {
      setFakeDevices([]);
      setShowSimulator(false);
    }
  };

  // Load config on mount
  useEffect(() => {
    axios.get('/api/modbus/config')
      .then(res => setConfig(res.data))
      .catch(err => console.error('Failed to load modbus config:', err));
    loadFakeDevices();
  }, []);

  // Pause coordinator polling on mount, resume on unmount
  useEffect(() => {
    let cancelled = false;

    const pausePolling = async () => {
      try {
        const { data } = await axios.post('/api/modbus/pause');
        if (!cancelled && data.success) {
          setSuspended(true);
        }
      } catch (err) {
        console.error('Failed to pause Modbus polling:', err);
      }
    };

    pausePolling();

    return () => {
      cancelled = true;
      // Fire-and-forget resume on unmount
      axios.post('/api/modbus/resume').catch(() => {});
      setSuspended(false);
    };
  }, []);

  const handleGet = async () => {
    setLoading(true);
    setResult(null);
    try {
      const { data } = await axios.post('/api/modbus/get', {
        address,
        register_address: registerAddress,
        register_type: registerType,
        value_type: valueType,
      });
      setResult(data);
    } catch (err) {
      setResult({ success: false, error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleSet = async () => {
    if (writeValue === '') {
      setResult({ success: false, error: 'Value is required' });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data } = await axios.post('/api/modbus/set', {
        address,
        register_address: writeRegisterAddress,
        value: writeValue,
      });
      setResult(data);
    } catch (err) {
      setResult({ success: false, error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  /**
   * Parse comma-separated values string into array of 16-bit integers.
   * Returns null if any value is invalid.
   */
  const parseMultipleValues = (input: string): number[] | null => {
    const trimmed = input.trim();
    if (!trimmed) return null;
    const parts = trimmed.split(',').map(s => s.trim()).filter(s => s !== '');
    const values: number[] = [];
    for (const part of parts) {
      const num = parseInt(part, 10);
      if (isNaN(num) || num < 0 || num > 65535) return null;
      values.push(num);
    }
    return values.length > 0 ? values : null;
  };

  const handleSetMultiple = async () => {
    const values = parseMultipleValues(writeMultipleValues);
    if (!values) {
      setResult({ success: false, error: t('modbus_helper.fc16_invalid_values') });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data } = await axios.post('/api/modbus/set_multiple', {
        address,
        register_address: writeRegisterAddress,
        values,
      });
      setResult(data);
    } catch (err) {
      setResult({ success: false, error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    setResult(null);

    // Build query params for SSE endpoint
    const params = new URLSearchParams({
      start_address: searchStartAddress.toString(),
      end_address: searchEndAddress.toString(),
      register_address: searchRegisterAddress.toString(),
      register_type: searchRegisterType,
      timeout: searchTimeout.toString(),
    });

    // Add token to query params for SSE (EventSource doesn't support headers)
    const token = localStorage.getItem('token');
    if (token) {
      params.set('token', token);
    }

    try {
      const eventSource = new EventSource(`/api/modbus/search/stream?${params}`);

      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'start':
            setResult({ success: true, devices: [], count: 0, scanned: 0, total: data.total });
            break;
          case 'progress':
            setResult(prev => prev ? { ...prev, scanned: data.scanned, total: data.total } : prev);
            break;
          case 'found':
            // Create new object to ensure React detects the change
            setResult({
              success: true,
              devices: [...data.devices],  // New array reference
              count: data.devices.length,
              scanned: data.scanned,
              total: data.total,
            });
            break;
          case 'complete':
            setResult({
              success: true,
              devices: data.devices,
              count: data.count,
              scanned: data.scanned,
              total: data.total,
              cancelled: false,
            });
            eventSource.close();
            setLoading(false);
            break;
          case 'cancelled':
            setResult({
              success: true,
              devices: data.devices,
              count: data.devices.length,
              scanned: data.scanned,
              total: data.total,
              cancelled: true,
            });
            eventSource.close();
            setLoading(false);
            break;
          case 'error':
            setResult({ success: false, error: data.error });
            eventSource.close();
            setLoading(false);
            break;
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        setLoading(false);
      };

    } catch (err) {
      setResult({ success: false, error: String(err) });
      setLoading(false);
    }
  };

  const handleCancelSearch = async () => {
    try {
      await axios.post('/api/modbus/search/cancel');
    } catch (err) {
      console.error('Failed to cancel search:', err);
    }
  };

  const handleConfigure = async () => {
    setLoading(true);
    setResult(null);
    try {
      const effectiveAddress = configBroadcast ? 0 : configCurrentAddress;
      const { data } = await axios.post('/api/modbus/configure-device', {
        device: configDevice,
        uart: configUart,
        current_address: effectiveAddress,
        current_baudrate: configCurrentBaudrate,
        new_address: configOperation === 'address' && !configBroadcast ? (configNewAddress || null) : null,
        new_baudrate: configOperation === 'baudrate' ? (configNewBaudrate || null) : null,
      });
      setResult(data);
    } catch (err) {
      setResult({ success: false, error: String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateFakeDevice = async () => {
    setLoading(true);
    setResult(null);
    try {
      await axios.post(`/api/dev/fake-device/${selectedSimModel}?address=${simAddress}`);
      await loadFakeDevices();
      setResult({ success: true, message: `Created simulated device ${simAddress}_${selectedSimModel} in HA` });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setResult({ success: false, error: apiErr.response?.data?.error || String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateFakeDevice = async (deviceId: string) => {
    const match = deviceId.match(/^(\d+)_(.+)$/);
    if (!match) return;
    const address = Number(match[1]);
    const model = match[2];
    setLoading(true);
    setResult(null);
    try {
      await axios.post(`/api/dev/fake-device/${model}/update?address=${address}`);
      await loadFakeDevices();
      setResult({ success: true, message: `Sent updated simulated data for ${deviceId}` });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setResult({ success: false, error: apiErr.response?.data?.error || String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFakeDevice = async (deviceId: string) => {
    const match = deviceId.match(/^(\d+)_(.+)$/);
    if (!match) return;
    const address = Number(match[1]);
    const model = match[2];
    setLoading(true);
    setResult(null);
    try {
      await axios.delete(`/api/dev/fake-device/${model}?address=${address}`);
      await loadFakeDevices();
      setResult({ success: true, message: `Removed simulated device ${deviceId} from HA` });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setResult({ success: false, error: apiErr.response?.data?.error || String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleDashboardYaml = async (deviceId: string, style: 'standard' | 'visual' = 'standard') => {
    const match = deviceId.match(/^(\d+)_(.+)$/);
    if (!match) return;
    const address = Number(match[1]);
    const model = match[2];
    setLoading(true);
    setResult(null);
    try {
      const { data } = await axios.get(`/api/dev/fake-device/${model}/dashboard?address=${address}&style=${style}`);
      if (data.error) {
        setResult({ success: false, error: data.error });
      } else {
        setDashboardYaml(data.yaml);
        setDashboardModel(data.model || model);
        setYamlCopied(false);
      }
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setResult({ success: false, error: apiErr.response?.data?.error || String(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleCopyYaml = async () => {
    if (!dashboardYaml) return;
    try {
      await navigator.clipboard.writeText(dashboardYaml);
      setYamlCopied(true);
      setTimeout(() => setYamlCopied(false), 2000);
    } catch {
      // Fallback: select textarea content
      const textarea = document.getElementById('dashboard-yaml-textarea') as HTMLTextAreaElement;
      if (textarea) {
        textarea.select();
        document.execCommand('copy');
        setYamlCopied(true);
        setTimeout(() => setYamlCopied(false), 2000);
      }
    }
  };

  // Show warning if Modbus is not configured
  if (config && !config.configured) {
    return (
      <SettingsPage>
        <NoticeCallout variant="warning" message={t('modbus_helper.not_configured')} />
      </SettingsPage>
    );
  }

  const baudrateItems = (
    <>
      <SelectItem value="2400">2400</SelectItem>
      <SelectItem value="4800">4800</SelectItem>
      <SelectItem value="9600">9600</SelectItem>
      <SelectItem value="19200">19200</SelectItem>
    </>
  );

  const addressField = (
    <FormField label={t('modbus_helper.address')}>
      <NumericInput
        value={address}
        onChange={(v) => setAddress(v === '' ? 1 : v)}
        min={1}
        max={247}
      />
    </FormField>
  );

  const tabs: { id: typeof activeTab; label: string; icon: React.ReactNode }[] = [
    { id: 'get', label: t('modbus_helper.get'), icon: <FaBookOpen /> },
    { id: 'set', label: t('modbus_helper.set'), icon: <FaPen /> },
    { id: 'search', label: t('modbus_helper.search'), icon: <FaSearch /> },
    { id: 'configure', label: t('modbus_helper.configure'), icon: <FaSlidersH /> },
    { id: 'creator', label: t('modbus_helper.creator'), icon: <FaMagic /> },
    ...(showSimulator
      ? [{ id: 'simulator' as const, label: t('modbus_helper.simulator'), icon: <FaFlask /> }]
      : []),
  ];

  return (
    <><SettingsPage>

      {/* Suspended notice — the same callout every other page uses, not a
          solid bar that reads louder than the tools under it. */}
      {suspended && (
        <NoticeCallout
          variant="info"
          icon={<FaPause />}
          message={t('tools.modbus_paused')}
        />
      )}

      {/* Tabs — a segmented control on the canvas, like the rest of the app */}
      <div
        role="tablist"
        className="stg-card flex gap-1 overflow-x-auto no-scrollbar p-1.5"
      >
        {tabs.map(tab => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-base-content/55 hover:bg-base-content/5 hover:text-base-content/85',
              )}
            >
              <span className="text-[12px]">{tab.icon}</span>
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* GET Tab */}
      {activeTab === 'get' && (
        <SettingsCard
          icon={<FaBookOpen />}
          title={t('modbus_helper.read_register')}
          description={t('modbus_helper.read_register_desc')}
          footer={
            <FormActions className="w-full">
              <button
                className="btn btn-primary btn-sm"
                onClick={handleGet}
                disabled={loading}
              >
                {loading ? <span className="loading loading-spinner loading-xs" /> : <FaPlay />}
                {t('modbus_helper.read')}
              </button>
            </FormActions>
          }
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {addressField}

            <FormField label={t('modbus_helper.register_address')}>
              <NumericInput
                value={registerAddress}
                onChange={(v) => setRegisterAddress(v === '' ? 0 : v)}
                min={0}
              />
            </FormField>

            <FormField label={t('modbus_helper.register_type')}>
              <Select value={registerType} onValueChange={setRegisterType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {config?.register_types.map(rt => (
                    <SelectItem key={rt} value={rt}>{rt}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField label={t('modbus_helper.value_type')}>
              <Select value={valueType} onValueChange={setValueType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {config?.value_types.map(vt => (
                    <SelectItem key={vt} value={vt}>{vt}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
          </div>
        </SettingsCard>
      )}

      {/* SET Tab */}
      {activeTab === 'set' && (
        <SettingsCard
          icon={<FaPen />}
          title={t('modbus_helper.write_register')}
          description={t('modbus_helper.write_register_desc')}
          action={
            /* FC06 / FC16 toggle */
            <div className="flex gap-1 rounded-lg bg-base-content/5 p-1">
              {(['fc06', 'fc16'] as const).map(mode => (
                <button
                  key={mode}
                  type="button"
                  className={cn(
                    'rounded-md px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap',
                    writeMode === mode
                      ? 'bg-base-100 text-base-content shadow-sm'
                      : 'text-base-content/55 hover:text-base-content/85',
                  )}
                  onClick={() => setWriteMode(mode)}
                >
                  {mode === 'fc06'
                    ? `FC06 – ${t('modbus_helper.fc06_single')}`
                    : `FC16 – ${t('modbus_helper.fc16_multiple')}`}
                </button>
              ))}
            </div>
          }
          footer={
            <FormActions className="w-full">
              {writeMode === 'fc06' ? (
                <button
                  className="btn btn-warning btn-sm"
                  onClick={handleSet}
                  disabled={loading || writeValue === ''}
                >
                  {loading ? <span className="loading loading-spinner loading-xs" /> : <FaPen />}
                  {t('modbus_helper.write')}
                </button>
              ) : (
                <button
                  className="btn btn-warning btn-sm"
                  onClick={handleSetMultiple}
                  disabled={loading || !parseMultipleValues(writeMultipleValues)}
                >
                  {loading ? <span className="loading loading-spinner loading-xs" /> : <FaPen />}
                  {t('modbus_helper.fc16_write_button')}
                </button>
              )}
            </FormActions>
          }
        >
          {/* FC06 – single register */}
          {writeMode === 'fc06' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {addressField}

              <FormField label={t('modbus_helper.register_address')}>
                <NumericInput
                  value={writeRegisterAddress}
                  onChange={(v) => setWriteRegisterAddress(v === '' ? 0 : v)}
                  min={0}
                />
              </FormField>

              <FormField label={t('modbus_helper.custom_value')}>
                <NumericInput
                  value={writeValue}
                  onChange={(v) => setWriteValue(v)}
                  decimal
                  placeholder={t('modbus_helper.fc06_value_placeholder')}
                />
              </FormField>
            </div>
          )}

          {/* FC16 – multiple registers */}
          {writeMode === 'fc16' && (
            <div className="space-y-4">
              <p className="text-[13px] text-base-content/60 leading-relaxed">
                {t('modbus_helper.fc16_hint')}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {addressField}

                <FormField
                  label={t('modbus_helper.fc16_start_register')}
                  className="md:col-span-2"
                >
                  <NumericInput
                    value={writeRegisterAddress}
                    onChange={(v) => setWriteRegisterAddress(v === '' ? 0 : v)}
                    min={0}
                  />
                </FormField>
              </div>

              <FormField
                label={t('modbus_helper.fc16_values')}
                error={
                  writeMultipleValues && !parseMultipleValues(writeMultipleValues)
                    ? t('modbus_helper.fc16_invalid_values')
                    : undefined
                }
                help={
                  writeMultipleValues && parseMultipleValues(writeMultipleValues)
                    ? `${t('modbus_helper.fc16_registers_count')}: ${parseMultipleValues(writeMultipleValues)!.length}`
                    : t('modbus_helper.fc16_values_hint')
                }
              >
                <input
                  type="text"
                  className="input input-bordered w-full"
                  value={writeMultipleValues}
                  onChange={(e) => setWriteMultipleValues(e.target.value)}
                  placeholder={t('modbus_helper.fc16_values_placeholder')}
                />
              </FormField>
            </div>
          )}
        </SettingsCard>
      )}

      {/* SEARCH Tab */}
      {activeTab === 'search' && (
        <SettingsCard
          icon={<FaSearch />}
          title={t('modbus_helper.search_devices')}
          description={t('modbus_helper.search_hint')}
          footer={
            <FormActions className="w-full" hint={t('modbus_helper.search_time_warning')}>
              {loading ? (
                <button className="btn btn-error btn-sm" onClick={handleCancelSearch}>
                  <FaStop /> {t('modbus_helper.stop')}
                </button>
              ) : (
                <button className="btn btn-primary btn-sm" onClick={handleSearch}>
                  <FaSearch /> {t('modbus_helper.search')}
                </button>
              )}
            </FormActions>
          }
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <FormField label={t('modbus_helper.start_address')}>
              <NumericInput
                value={searchStartAddress}
                onChange={(v) => setSearchStartAddress(v === '' ? 1 : v)}
                min={1}
                max={247}
              />
            </FormField>

            <FormField label={t('modbus_helper.end_address')}>
              <NumericInput
                value={searchEndAddress}
                onChange={(v) => setSearchEndAddress(v === '' ? 247 : v)}
                min={1}
                max={247}
              />
            </FormField>

            <FormField label={t('modbus_helper.register_address')}>
              <NumericInput
                value={searchRegisterAddress}
                onChange={(v) => setSearchRegisterAddress(v === '' ? 0 : v)}
                min={0}
              />
            </FormField>

            <FormField label={t('modbus_helper.register_type')}>
              <Select value={searchRegisterType} onValueChange={setSearchRegisterType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {config?.register_types.map(rt => (
                    <SelectItem key={rt} value={rt}>{rt}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField label={t('modbus_helper.timeout')}>
              <Select value={String(searchTimeout)} onValueChange={(v) => setSearchTimeout(parseFloat(v))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0.2">0.2s</SelectItem>
                  <SelectItem value="0.3">0.3s</SelectItem>
                  <SelectItem value="0.5">0.5s</SelectItem>
                  <SelectItem value="1">1.0s</SelectItem>
                </SelectContent>
              </Select>
            </FormField>
          </div>

          {/* Progress while the scan runs */}
          {loading && result?.total ? (
            <div className="stg-inset mt-4 p-4">
              <div className="flex items-center justify-between mb-2 text-[13px]">
                <span className="font-medium">{t('modbus_helper.scanning')}…</span>
                <span className="font-mono text-base-content/60">{result.scanned}/{result.total}</span>
              </div>
              <progress
                className="progress progress-primary w-full"
                value={result.scanned || 0}
                max={result.total}
              ></progress>
              {result.devices && result.devices.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {result.devices.map((addr, idx) => (
                    <span key={idx} className="badge badge-primary animate-pulse">
                      {t('modbus_helper.address')}: {addr}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </SettingsCard>
      )}

      {/* Results - hide during active search. The failure case gets the
          danger cap, which is how every other page says the same thing. */}
      {result && !loading && (
        <SettingsCard
          variant={result.success ? 'default' : 'danger'}
          icon={result.success ? <FaCheckCircle className="text-success" /> : <FaTimesCircle />}
          title={t('modbus_helper.result')}
        >
          <div className="space-y-3">
            {result.value !== undefined && (
              <div className="stg-inset px-4 py-3">
                <div className="text-xs font-medium text-base-content/55">{t('modbus_helper.value')}</div>
                <div className="text-3xl font-semibold tracking-tight text-primary mt-0.5">{result.value}</div>
                {result.raw_registers && (
                  <div className="text-xs font-mono text-base-content/50 mt-1">
                    Raw: [{result.raw_registers.join(', ')}]
                  </div>
                )}
              </div>
            )}

            {result.message && (
              <p className="text-sm text-base-content">{result.message}</p>
            )}

            {result.message_key && (
              <p className="text-sm text-base-content">{t(`modbus_helper.${result.message_key}`)}</p>
            )}

            {result.error && (
              <p className="text-sm text-error">{result.error}</p>
            )}

            {result.error_key && (
              <p className="text-sm text-error">
                {t(`modbus_helper.${result.error_key}`)}
                {result.error_params?.supported && ` ${result.error_params.supported}`}
              </p>
            )}

            {result.cancelled && (
              <NoticeCallout
                variant="warning"
                message={`${t('modbus_helper.search_cancelled')} (${result.scanned}/${result.total})`}
              />
            )}

            {result.devices && result.devices.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-2">
                  {t('modbus_helper.found_devices')}: {result.count}
                  {result.scanned !== undefined && result.total !== undefined && (
                    <span className="text-base-content/60 font-normal ml-2">
                      ({result.scanned}/{result.total} {t('modbus_helper.scanned')})
                    </span>
                  )}
                </p>
                <div className="flex flex-wrap gap-2">
                  {result.devices.map(addr => (
                    <span key={addr} className="badge badge-primary">
                      {t('modbus_helper.address')}: {addr}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {result.devices && result.devices.length === 0 && result.success && !result.cancelled && (
              <p className="text-sm text-base-content/60">{t('modbus_helper.no_devices_found')}</p>
            )}
          </div>
        </SettingsCard>
      )}

      {/* CONFIGURE Tab */}
      {activeTab === 'configure' && (
        <SettingsCard
          icon={<FaSlidersH />}
          title={t('modbus_helper.configure_device')}
          description={t('modbus_helper.configure_desc')}
          footer={
            <FormActions className="w-full">
              <button
                className="btn btn-primary btn-sm"
                onClick={handleConfigure}
                disabled={
                  loading ||
                  (configOperation === 'address' && !configNewAddress) ||
                  (configOperation === 'baudrate' && !configNewBaudrate)
                }
              >
                {loading ? <span className="loading loading-spinner loading-xs" /> : <FaSlidersH />}
                {configOperation === 'address' ? t('modbus_helper.set_new_address') : t('modbus_helper.set_new_baudrate')}
              </button>
            </FormActions>
          }
        >
          <div className="space-y-4">
            <NoticeCallout variant="warning" message={t('modbus_helper.configure_warning')} />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField label={t('modbus_helper.device_model')}>
                <Select value={configDevice} onValueChange={(v) => {
                    setConfigDevice(v);
                    setConfigBroadcast(false);
                    if (v === 'dyp-a12-ultrasonic') {
                      setConfigOperation('address');
                      setConfigCurrentBaudrate(9600);
                    } else if (v === 'boneio-edge-temp') {
                      setConfigCurrentBaudrate(9600);
                    }
                  }}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="boneio-edge-temp">boneIO Edge Sensor (Temp & Humidity)</SelectItem>
                    <SelectItem value="cwt">CWT (Temp & Humidity)</SelectItem>
                    <SelectItem value="sht30">SHT30 (Temp & Humidity)</SelectItem>
                    <SelectItem value="dyp-a12-ultrasonic">DYP-A12 (Ultrasonic Distance)</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>

              <FormField label={t('modbus_helper.uart')}>
                <Select value={configUart} onValueChange={setConfigUart}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="uart1">UART1</SelectItem>
                    <SelectItem value="uart2">UART2</SelectItem>
                    <SelectItem value="uart4">UART4</SelectItem>
                    <SelectItem value="uart5">UART5</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            </div>

            {/* Broadcast mode for edge-temp */}
            {configDevice === 'boneio-edge-temp' && (
              <div className="space-y-2">
                <ToggleRow
                  checked={configBroadcast}
                  tone="warning"
                  label={t('modbus_helper.broadcast_mode') || 'Broadcast Mode (address 0)'}
                  onChange={(checked) => {
                    setConfigBroadcast(checked);
                    if (checked) {
                      setConfigOperation('baudrate');
                      setConfigCurrentAddress(0);
                    } else {
                      setConfigCurrentAddress(1);
                    }
                  }}
                />
                {configBroadcast && (
                  <NoticeCallout
                    variant="error"
                    message={t('modbus_helper.broadcast_warning') || 'Broadcast mode will change settings on ALL devices connected to this UART bus!'}
                  />
                )}
              </div>
            )}

            {/* Operation Type Selection */}
            <FormField label={t('modbus_helper.select_operation')}>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {!configBroadcast && (
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="radio"
                      name="operation"
                      className="radio radio-primary radio-sm"
                      checked={configOperation === 'address'}
                      onChange={() => setConfigOperation('address')}
                    />
                    {t('modbus_helper.change_address')}
                  </label>
                )}
                {configDevice !== 'dyp-a12-ultrasonic' && (
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="radio"
                      name="operation"
                      className="radio radio-primary radio-sm"
                      checked={configOperation === 'baudrate'}
                      onChange={() => setConfigOperation('baudrate')}
                    />
                    {t('modbus_helper.change_baudrate')}
                  </label>
                )}
              </div>
            </FormField>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField label={t('modbus_helper.current_address')}>
                <NumericInput
                  value={configCurrentAddress}
                  onChange={(v) => setConfigCurrentAddress(v === '' ? 1 : v)}
                  min={1}
                  max={247}
                />
              </FormField>

              <FormField label={t('modbus_helper.current_baudrate')}>
                {configOperation === 'address' && configDevice === 'dyp-a12-ultrasonic' ? (
                  <input
                    type="text"
                    className="input input-bordered w-full"
                    value="9600"
                    disabled
                  />
                ) : (
                  <Select value={String(configCurrentBaudrate)} onValueChange={(v) => setConfigCurrentBaudrate(Number(v))}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>{baudrateItems}</SelectContent>
                  </Select>
                )}
              </FormField>

              {/* Address change */}
              {configOperation === 'address' && (
                <FormField label={t('modbus_helper.new_address')} required className="md:col-span-2">
                  <NumericInput
                    value={configNewAddress}
                    onChange={(v) => setConfigNewAddress(v)}
                    min={1}
                    max={247}
                    placeholder={t('modbus_helper.new_address_placeholder')}
                  />
                </FormField>
              )}

              {/* Baudrate change */}
              {configOperation === 'baudrate' && (
                <FormField label={t('modbus_helper.new_baudrate')} required className="md:col-span-2">
                  <Select value={configNewBaudrate ? String(configNewBaudrate) : undefined} onValueChange={(v) => setConfigNewBaudrate(v ? Number(v) : '')}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('modbus_helper.new_baudrate_placeholder')} />
                    </SelectTrigger>
                    <SelectContent>{baudrateItems}</SelectContent>
                  </Select>
                </FormField>
              )}
            </div>

            <NoticeCallout
              variant="neutral"
              title={t('modbus_helper.configure_important')}
              message={
                <ol className="list-decimal pl-4 space-y-0.5">
                  <li>{t('modbus_helper.configure_step1')}</li>
                  <li>{t('modbus_helper.configure_step2')}</li>
                </ol>
              }
            />
          </div>
        </SettingsCard>
      )}

      {/* CREATOR Tab */}
      {activeTab === 'creator' && (
        <SettingsCard
          icon={<FaMagic />}
          title={t('modbus_helper.device_creator')}
          description={t('modbus_helper.creator_desc')}
        >
          <ModbusDeviceCreator />
        </SettingsCard>
      )}

      {/* SIMULATOR Tab */}
      {activeTab === 'simulator' && showSimulator && (
        <>
          <SettingsCard
            icon={<FaFlask />}
            title={t('modbus_helper.simulator_title')}
            description={t('modbus_helper.simulator_hint')}
          >
            <div className="grid grid-cols-1 md:grid-cols-[1fr_6rem_auto] gap-4 items-end">
              <FormField label={t('modbus_wizard.step2_title')}>
                <Select value={selectedSimModel} onValueChange={setSelectedSimModel}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(MODBUS_DEVICE_CATALOG).map(d => (
                      <SelectItem key={d.modelKey} value={d.modelKey}>
                        {d.displayName} ({d.manufacturer})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>

              <FormField label={t('modbus_wizard.address')}>
                <NumericInput
                  value={simAddress}
                  onChange={(v) => setSimAddress(v === '' ? 1 : v)}
                  min={1}
                  max={247}
                />
              </FormField>

              <button
                className="btn btn-primary w-full md:w-auto whitespace-nowrap"
                onClick={handleCreateFakeDevice}
                disabled={loading}
              >
                {loading ? <span className="loading loading-spinner loading-xs" /> : <FaPlus />}
                {t('modbus_helper.simulator_create')}
              </button>
            </div>
          </SettingsCard>

          {/* Active Simulations — card per device */}
          {Array.isArray(fakeDevices) && fakeDevices.length > 0 && (
            <div className="space-y-3">
              <div className="px-1">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-base-content/50">
                  {t('modbus_helper.active_simulations')}
                </h3>
                <p className="text-xs text-base-content/50 mt-0.5">
                  {t('modbus_helper.active_simulations_desc')}
                </p>
              </div>
              {fakeDevices.map((dev) => (
                <SettingsCard
                  key={dev.device_id}
                  title={dev.model}
                  description={
                    <>
                      {dev.manufacturer}
                      <span className="font-mono text-base-content/45 ml-2">ID: {dev.device_id}</span>
                    </>
                  }
                  action={
                    <>
                      <span className="badge badge-outline badge-sm capitalize">{dev.category}</span>
                      <span className="badge badge-ghost badge-sm font-mono">{dev.entity_count} entities</span>
                    </>
                  }
                  footer={
                    <div className="flex flex-wrap gap-2 w-full">
                      <button
                        className="btn btn-sm btn-primary"
                        onClick={() => handleUpdateFakeDevice(dev.device_id)}
                        disabled={loading}
                      >
                        <FaPlay /> {t('modbus_helper.simulation_send_update')}
                      </button>
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={() => handleDashboardYaml(dev.device_id)}
                        disabled={loading}
                      >
                        <FaCode /> {t('modbus_helper.simulation_dashboard')}
                      </button>
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={() => handleDashboardYaml(dev.device_id, 'visual')}
                        disabled={loading}
                      >
                        <FaImage /> {t('modbus_helper.simulation_visual')}
                      </button>
                      <button
                        className="btn btn-sm btn-ghost text-error sm:ml-auto"
                        onClick={() => handleRemoveFakeDevice(dev.device_id)}
                        disabled={loading}
                      >
                        <FaTrash /> {t('modbus_helper.simulation_delete')}
                      </button>
                    </div>
                  }
                />
              ))}
            </div>
          )}
        </>
      )}
    </SettingsPage>

    {/* Dashboard YAML Modal */}
    {dashboardYaml && (
      <dialog className="modal modal-open" onClick={(e) => { if (e.target === e.currentTarget) setDashboardYaml(null); }}>
        <div className="modal-box max-w-4xl w-full">
          <h3 className="font-bold text-lg mb-2">
            <FaCode className="inline mr-2" />
            {t('modbus_helper.simulation_dashboard_title', { model: dashboardModel })}
          </h3>
          <p className="text-sm text-base-content/70 mb-4">
            {t('modbus_helper.simulation_dashboard_hint')}
          </p>
          <textarea
            id="dashboard-yaml-textarea"
            className="textarea textarea-bordered w-full font-mono text-xs leading-relaxed"
            rows={20}
            readOnly
            value={dashboardYaml}
          />
          <div className="modal-action">
            <button
              className={`btn ${yamlCopied ? 'btn-success' : 'btn-primary'}`}
              onClick={handleCopyYaml}
            >
              {yamlCopied ? (
                <><FaCheck className="mr-2" /> {t('modbus_helper.simulation_dashboard_copied')}</>
              ) : (
                <><FaCopy className="mr-2" /> {t('modbus_helper.simulation_dashboard_copy')}</>
              )}
            </button>
            <button
              className="btn"
              onClick={() => setDashboardYaml(null)}
            >
              {t('modbus_helper.simulation_dashboard_close')}
            </button>
          </div>
        </div>
      </dialog>
    )}
  </>);
}
