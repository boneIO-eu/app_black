import { useState, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { FaPlay, FaSearch, FaCog, FaPlus } from 'react-icons/fa';
import ModbusDeviceCreator from './ModbusDeviceCreator';
import axios from '@/api/axios';

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

/**
 * ModbusHelper - UI component for Modbus operations (GET, SET, SEARCH)
 * Uses the existing Modbus client from the manager.
 */
export default function ModbusHelper() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'get' | 'set' | 'search' | 'configure' | 'creator'>('get');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ModbusResult | null>(null);
  const [config, setConfig] = useState<ModbusConfig | null>(null);

  // Common parameters
  const [address, setAddress] = useState(1);

  // GET parameters
  const [registerAddress, setRegisterAddress] = useState(0);
  const [registerType, setRegisterType] = useState('holding');
  const [valueType, setValueType] = useState('S_WORD');

  // SET parameters
  const [writeRegisterAddress, setWriteRegisterAddress] = useState(0);
  const [writeValue, setWriteValue] = useState<number | ''>('');

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

  // Load config on mount
  useEffect(() => {
    axios.get('/api/modbus/config')
      .then(res => setConfig(res.data))
      .catch(err => console.error('Failed to load modbus config:', err));
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

  // Show warning if Modbus is not configured
  if (config && !config.configured) {
    return (
      <div>
        <div className="alert alert-warning">
          <span>{t('modbus_helper.not_configured')}</span>
        </div>
      </div>
    );
  }

  return (
    <div>

      {/* Tabs */}
      <div className="tabs tabs-boxed mb-6">
        <button
          className={`tab ${activeTab === 'get' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('get')}
        >
          <FaPlay className="mr-2" /> {t('modbus_helper.get')}
        </button>
        <button
          className={`tab ${activeTab === 'set' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('set')}
        >
          <FaCog className="mr-2" /> {t('modbus_helper.set')}
        </button>
        <button
          className={`tab ${activeTab === 'search' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          <FaSearch className="mr-2" /> {t('modbus_helper.search')}
        </button>
        <button
          className={`tab ${activeTab === 'configure' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('configure')}
        >
          <FaCog className="mr-2" /> {t('modbus_helper.configure')}
        </button>
        <button
          className={`tab ${activeTab === 'creator' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('creator')}
        >
          <FaPlus className="mr-2" /> {t('modbus_helper.creator')}
        </button>
      </div>

      {/* GET Tab */}
      {activeTab === 'get' && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <h2 className="card-title text-lg">{t('modbus_helper.read_register')}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Device Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={address}
                  onChange={(e) => setAddress(parseInt(e.target.value) || 1)}
                  min={1}
                  max={247}
                />
              </div>

              {/* Register Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.register_address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={registerAddress}
                  onChange={(e) => setRegisterAddress(parseInt(e.target.value) || 0)}
                  min={0}
                />
              </div>

              {/* Register Type */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.register_type')}</span>
                </label>
                <select
                  className="select select-bordered"
                  value={registerType}
                  onChange={(e) => setRegisterType(e.target.value)}
                >
                  {config?.register_types.map(rt => (
                    <option key={rt} value={rt}>{rt}</option>
                  ))}
                </select>
              </div>

              {/* Value Type */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.value_type')}</span>
                </label>
                <select
                  className="select select-bordered"
                  value={valueType}
                  onChange={(e) => setValueType(e.target.value)}
                >
                  {config?.value_types.map(vt => (
                    <option key={vt} value={vt}>{vt}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="card-actions justify-end mt-4">
              <button
                className={`btn btn-primary ${loading ? 'loading' : ''}`}
                onClick={handleGet}
                disabled={loading}
              >
                <FaPlay className="mr-2" /> {t('modbus_helper.read')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SET Tab */}
      {activeTab === 'set' && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <h2 className="card-title text-lg">{t('modbus_helper.write_register')}</h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Device Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={address}
                  onChange={(e) => setAddress(parseInt(e.target.value) || 1)}
                  min={1}
                  max={247}
                />
              </div>

              {/* Register Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.register_address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={writeRegisterAddress}
                  onChange={(e) => setWriteRegisterAddress(parseInt(e.target.value) || 0)}
                  min={0}
                />
              </div>

              {/* Value */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.custom_value')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={writeValue}
                  onChange={(e) => setWriteValue(e.target.value ? parseFloat(e.target.value) : '')}
                  placeholder="Value to write"
                />
              </div>
            </div>

            <div className="card-actions justify-end mt-4">
              <button
                className={`btn btn-warning ${loading ? 'loading' : ''}`}
                onClick={handleSet}
                disabled={loading || writeValue === ''}
              >
                <FaCog className="mr-2" /> {t('modbus_helper.write')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SEARCH Tab */}
      {activeTab === 'search' && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <h2 className="card-title text-lg">{t('modbus_helper.search_devices')}</h2>
            <p className="text-sm text-base-content/70 mb-4">
              {t('modbus_helper.search_hint')}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              {/* Start Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.start_address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={searchStartAddress}
                  onChange={(e) => setSearchStartAddress(parseInt(e.target.value) || 1)}
                  min={1}
                  max={247}
                />
              </div>

              {/* End Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.end_address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={searchEndAddress}
                  onChange={(e) => setSearchEndAddress(parseInt(e.target.value) || 247)}
                  min={1}
                  max={247}
                />
              </div>

              {/* Register Address */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.register_address')}</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={searchRegisterAddress}
                  onChange={(e) => setSearchRegisterAddress(parseInt(e.target.value) || 0)}
                  min={0}
                />
              </div>

              {/* Register Type */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.register_type')}</span>
                </label>
                <select
                  className="select select-bordered"
                  value={searchRegisterType}
                  onChange={(e) => setSearchRegisterType(e.target.value)}
                >
                  {config?.register_types.map(rt => (
                    <option key={rt} value={rt}>{rt}</option>
                  ))}
                </select>
              </div>

              {/* Timeout */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">{t('modbus_helper.timeout')}</span>
                </label>
                <select
                  className="select select-bordered"
                  value={searchTimeout}
                  onChange={(e) => setSearchTimeout(parseFloat(e.target.value))}
                >
                  <option value={0.2}>0.2s</option>
                  <option value={0.3}>0.3s</option>
                  <option value={0.5}>0.5s</option>
                  <option value={1.0}>1.0s</option>
                </select>
              </div>
            </div>

            <div className="alert alert-info mt-4">
              <span>{t('modbus_helper.search_time_warning')}</span>
            </div>

            <div className="card-actions justify-end mt-4 gap-2">
              {loading && activeTab === 'search' ? (
                <button
                  className="btn btn-error"
                  onClick={handleCancelSearch}
                >
                  {t('modbus_helper.stop')}
                </button>
              ) : (
                <button
                  className={`btn btn-info ${loading ? 'loading' : ''}`}
                  onClick={handleSearch}
                  disabled={loading}
                >
                  <FaSearch className="mr-2" /> {t('modbus_helper.search')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Results - hide during active search */}
      {result && !loading && (
        <div className={`card ${result.success ? 'bg-success/10' : 'bg-error/10'} mb-6`}>
          <div className="card-body">
            <h2 className="card-title text-lg">
              {result.success ? '✅ ' : '❌ '}
              {t('modbus_helper.result')}
            </h2>

            {result.value !== undefined && (
              <div className="stat">
                <div className="stat-title">{t('modbus_helper.value')}</div>
                <div className="stat-value text-primary">{result.value}</div>
                {result.raw_registers && (
                  <div className="stat-desc">
                    Raw: [{result.raw_registers.join(', ')}]
                  </div>
                )}
              </div>
            )}

            {result.message && (
              <p className="text-base-content">{result.message}</p>
            )}

            {result.message_key && (
              <p className="text-base-content">{t(`modbus_helper.${result.message_key}`)}</p>
            )}

            {result.error && (
              <p className="text-error">{result.error}</p>
            )}

            {result.error_key && (
              <p className="text-error">
                {t(`modbus_helper.${result.error_key}`)}
                {result.error_params?.supported && ` ${result.error_params.supported}`}
              </p>
            )}

            {result.cancelled && (
              <div className="alert alert-warning mb-4">
                <span>{t('modbus_helper.search_cancelled')} ({result.scanned}/{result.total})</span>
              </div>
            )}

            {result.devices && result.devices.length > 0 && (
              <div>
                <p className="font-medium mb-2">
                  {t('modbus_helper.found_devices')}: {result.count}
                  {result.scanned !== undefined && result.total !== undefined && (
                    <span className="text-base-content/70 ml-2">
                      ({result.scanned}/{result.total} {t('modbus_helper.scanned')})
                    </span>
                  )}
                </p>
                <div className="flex flex-wrap gap-2">
                  {result.devices.map(addr => (
                    <span key={addr} className="badge badge-primary badge-lg">
                      {t('modbus_helper.address')}: {addr}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {result.devices && result.devices.length === 0 && result.success && !result.cancelled && (
              <p className="text-base-content/70">{t('modbus_helper.no_devices_found')}</p>
            )}
          </div>
        </div>
      )}

      {/* Loading indicator with progress */}
      {loading && activeTab === 'search' && result && result.total && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <div className="flex items-center justify-between mb-2">
              <span>{t('modbus_helper.scanning')}...</span>
              <span className="text-sm">{result.scanned}/{result.total}</span>
            </div>
            <progress
              className="progress progress-primary w-full"
              value={result.scanned || 0}
              max={result.total}
            ></progress>
            {result.devices && result.devices.length > 0 && (
              <div className="mt-4">
                <p className="font-medium mb-2">
                  {t('modbus_helper.found_devices')}: {result.devices.join(', ')}
                </p>
                <div className="flex flex-wrap gap-2">
                  {result.devices.map((addr, idx) => (
                    <span key={idx} className="badge badge-primary badge-lg animate-pulse">
                      {t('modbus_helper.address')}: {addr}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* CONFIGURE Tab */}
      {activeTab === 'configure' && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <h2 className="card-title text-lg">{t('modbus_helper.configure_device')}</h2>
            <div className="alert alert-warning mb-4">
              <span>⚠️ {t('modbus_helper.configure_warning')}</span>
            </div>

            {/* Device Model - First */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-semibold">{t('modbus_helper.device_model')}</span>
                </label>
                <select
                  className="select select-bordered w-full"
                  value={configDevice}
                  onChange={(e) => {
                    setConfigDevice(e.target.value);
                    setConfigBroadcast(false);
                    if (e.target.value === 'dyp-a12-ultrasonic') {
                      setConfigOperation('address');
                      setConfigCurrentBaudrate(9600);
                    } else if (e.target.value === 'boneio-edge-temp') {
                      setConfigCurrentBaudrate(9600);
                    }
                  }}
                >
                  <option value="boneio-edge-temp">boneIO Edge Sensor (Temp & Humidity)</option>
                  <option value="cwt">CWT (Temp & Humidity)</option>
                  <option value="sht30">SHT30 (Temp & Humidity)</option>
                  <option value="dyp-a12-ultrasonic">DYP-A12 (Ultrasonic Distance)</option>
                </select>
              </div>

              {/* UART */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-semibold">{t('modbus_helper.uart')}</span>
                </label>
                <select
                  className="select select-bordered w-full"
                  value={configUart}
                  onChange={(e) => setConfigUart(e.target.value)}
                >
                  <option value="uart1">UART1</option>
                  <option value="uart2">UART2</option>
                  <option value="uart4">UART4</option>
                  <option value="uart5">UART5</option>
                </select>
              </div>
            </div>

            {/* Broadcast mode for edge-temp */}
            {configDevice === 'boneio-edge-temp' && (
              <div className="form-control mb-4">
                <label className="label cursor-pointer justify-start gap-3">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-warning"
                    checked={configBroadcast}
                    onChange={(e) => {
                      setConfigBroadcast(e.target.checked);
                      if (e.target.checked) {
                        setConfigOperation('baudrate');
                        setConfigCurrentAddress(0);
                      } else {
                        setConfigCurrentAddress(1);
                      }
                    }}
                  />
                  <span className="label-text font-semibold">{t('modbus_helper.broadcast_mode') || 'Broadcast Mode (address 0)'}</span>
                </label>
                {configBroadcast && (
                  <div className="alert alert-error mt-2">
                    <span>⚠️ {t('modbus_helper.broadcast_warning') || 'Broadcast mode will change settings on ALL devices connected to this UART bus!'}</span>
                  </div>
                )}
              </div>
            )}

            {/* Operation Type Selection */}
            <div className="form-control mb-4">
              <label className="label">
                <span className="label-text font-semibold">{t('modbus_helper.select_operation')}</span>
              </label>
              <div className="flex gap-4">
                {!configBroadcast && (
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="radio"
                      name="operation"
                      className="radio radio-primary"
                      checked={configOperation === 'address'}
                      onChange={() => setConfigOperation('address')}
                    />
                    <span className="label-text">{t('modbus_helper.change_address')}</span>
                  </label>
                )}
                {configDevice !== 'dyp-a12-ultrasonic' && (
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="radio"
                      name="operation"
                      className="radio radio-primary"
                      checked={configOperation === 'baudrate'}
                      onChange={() => setConfigOperation('baudrate')}
                    />
                    <span className="label-text">{t('modbus_helper.change_baudrate')}</span>
                  </label>
                )}
              </div>
            </div>

            {/* Address change fields */}
            {configOperation === 'address' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.current_address')}</span>
                  </label>
                  <input
                    type="number"
                    className="input input-bordered w-full"
                    value={configCurrentAddress}
                    onChange={(e) => setConfigCurrentAddress(Number(e.target.value))}
                    min={1}
                    max={247}
                  />
                </div>
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.current_baudrate')}</span>
                  </label>
                  {configDevice === 'dyp-a12-ultrasonic' ? (
                    <input
                      type="text"
                      className="input input-bordered w-full"
                      value="9600"
                      disabled
                    />
                  ) : (
                    <select
                      className="select select-bordered w-full"
                      value={configCurrentBaudrate}
                      onChange={(e) => setConfigCurrentBaudrate(Number(e.target.value))}
                    >
                      <option value={2400}>2400</option>
                      <option value={4800}>4800</option>
                      <option value={9600}>9600</option>
                      <option value={19200}>19200</option>
                    </select>
                  )}
                </div>
                <div className="form-control md:col-span-2">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.new_address')} *</span>
                  </label>
                  <input
                    type="number"
                    className="input input-bordered w-full"
                    value={configNewAddress}
                    onChange={(e) => setConfigNewAddress(e.target.value ? Number(e.target.value) : '')}
                    min={1}
                    max={247}
                    placeholder={t('modbus_helper.new_address_placeholder')}
                  />
                </div>
              </div>
            )}

            {/* Baudrate change fields */}
            {configOperation === 'baudrate' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.current_address')}</span>
                  </label>
                  <input
                    type="number"
                    className="input input-bordered w-full"
                    value={configCurrentAddress}
                    onChange={(e) => setConfigCurrentAddress(Number(e.target.value))}
                    min={1}
                    max={247}
                  />
                </div>
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.current_baudrate')}</span>
                  </label>
                  <select
                    className="select select-bordered w-full"
                    value={configCurrentBaudrate}
                    onChange={(e) => setConfigCurrentBaudrate(Number(e.target.value))}
                  >
                    <option value={2400}>2400</option>
                    <option value={4800}>4800</option>
                    <option value={9600}>9600</option>
                    <option value={19200}>19200</option>
                  </select>
                </div>
                <div className="form-control md:col-span-2">
                  <label className="label">
                    <span className="label-text">{t('modbus_helper.new_baudrate')} *</span>
                  </label>
                  <select
                    className="select select-bordered w-full"
                    value={configNewBaudrate}
                    onChange={(e) => setConfigNewBaudrate(e.target.value ? Number(e.target.value) : '')}
                  >
                    <option value="">{t('modbus_helper.new_baudrate_placeholder')}</option>
                    <option value={2400}>2400</option>
                    <option value={4800}>4800</option>
                    <option value={9600}>9600</option>
                    <option value={19200}>19200</option>
                  </select>
                </div>
              </div>
            )}

            <div className="card-actions justify-end mt-4">
              <button
                className="btn btn-primary"
                onClick={handleConfigure}
                disabled={
                  loading ||
                  (configOperation === 'address' && !configNewAddress) ||
                  (configOperation === 'baudrate' && !configNewBaudrate)
                }
              >
                <FaCog className="mr-2" />
                {configOperation === 'address' ? t('modbus_helper.set_new_address') : t('modbus_helper.set_new_baudrate')}
              </button>
            </div>

            <div className="alert alert-info mt-4">
              <div className="flex flex-col gap-1">
                <span className="font-semibold">⚠️ {t('modbus_helper.configure_important')}</span>
                <span>1. {t('modbus_helper.configure_step1')}</span>
                <span>2. {t('modbus_helper.configure_step2')}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CREATOR Tab */}
      {activeTab === 'creator' && (
        <div className="card bg-base-200 mb-6">
          <div className="card-body">
            <h2 className="card-title text-lg">{t('modbus_helper.device_creator')}</h2>
            <ModbusDeviceCreator />
          </div>
        </div>
      )}

      {/* Loading indicator for other operations */}
      {loading && (activeTab !== 'search' && activeTab !== 'creator' || !result?.total) && (
        <div className="flex justify-center items-center py-8">
          <span className="loading loading-spinner loading-lg"></span>
          <span className="ml-4">{t('modbus_helper.loading')}</span>
        </div>
      )}
    </div>
  );
}
