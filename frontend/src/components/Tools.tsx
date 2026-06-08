import { useState, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import { FaNetworkWired, FaMicrochip, FaCopy, FaSearch, FaFileExport } from 'react-icons/fa';
import { copyToClipboard } from '@/utils/clipboard';
import { GiElectric } from 'react-icons/gi';
import { IoWarning } from 'react-icons/io5';
import ModbusHelper from './ModbusHelper';
import CANHelper from './CANHelper';
import CANNetwork from './CANNetwork';
import HaDashboardWizard from './HaDashboardWizard';
import axios from '@/api/axios';

interface I2CDevice {
  address: number;
  address_hex: string;
  known_devices: string[];
  is_boneio: boolean;
}

interface I2CScanResult {
  bus: number;
  devices: I2CDevice[];
  raw_output: string;
  error: string | null;
}

export default function Tools() {
  const { t } = useTranslation();
  const { canSupported, boardVersion } = useConfig();
  const [activeSection, setActiveSection] = useState<'ha_dashboard' | 'modbus' | 'i2c' | 'can' | 'can_network'>('ha_dashboard');

  return (
    <div className="container mx-auto p-4 max-w-4xl">
      <h1 className="text-2xl font-bold mb-6">{t('tools.title')}</h1>

      {/* Section tabs */}
      <div className="tabs tabs-boxed mb-6 flex-wrap">
        <button
          className={`tab tab-lg gap-2 ${activeSection === 'ha_dashboard' ? 'tab-active' : ''}`}
          onClick={() => setActiveSection('ha_dashboard')}
        >
          <FaFileExport /> {t('dashboard_wizard.title')}
        </button>
        <button
          className={`tab tab-lg gap-2 ${activeSection === 'modbus' ? 'tab-active' : ''}`}
          onClick={() => setActiveSection('modbus')}
        >
          <FaNetworkWired /> Modbus
        </button>
        <button
          className={`tab tab-lg gap-2 ${activeSection === 'i2c' ? 'tab-active' : ''}`}
          onClick={() => setActiveSection('i2c')}
        >
          <FaMicrochip /> I2C
        </button>
        <button
          className={`tab tab-lg gap-2 ${activeSection === 'can_network' ? 'tab-active' : ''}`}
          onClick={() => setActiveSection('can_network')}
          disabled={!canSupported}
        >
          <GiElectric /> CAN Network
        </button>
        <button
          className={`tab tab-lg gap-2 ${activeSection === 'can' ? 'tab-active' : ''}`}
          onClick={() => setActiveSection('can')}
          disabled={!canSupported}
        >
          <GiElectric /> CAN Sniffer
        </button>
      </div>

      {activeSection === 'ha_dashboard' && <HaDashboardWizard />}
      {activeSection === 'modbus' && <ModbusHelper />}
      {activeSection === 'i2c' && <I2CSection />}
      {activeSection === 'can' && (canSupported ? <CANHelper /> : <CANNotSupported boardVersion={boardVersion} />)}
      {activeSection === 'can_network' && (canSupported ? <CANNetwork /> : <CANNotSupported boardVersion={boardVersion} />)}
    </div>
  );
}

/** Alert shown when CAN is not supported on the current board version. */
function CANNotSupported({ boardVersion }: { boardVersion: string | null }) {
  const { t } = useTranslation();

  return (
    <div className="alert alert-warning shadow-lg">
      <IoWarning className="w-6 h-6 shrink-0" />
      <div>
        <h3 className="font-bold">{t('tools.can_not_supported_title')}</h3>
        <div className="text-sm">
          {t('tools.can_not_supported_desc', { version: boardVersion || '?' })}
        </div>
      </div>
    </div>
  );
}

function I2CSection() {
  const { t } = useTranslation();
  const [bus, setBus] = useState(2);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<I2CScanResult | null>(null);
  const [copied, setCopied] = useState(false);

  const handleScan = useCallback(async () => {
    setScanning(true);
    setResult(null);
    try {
      const { data } = await axios.get(`/api/i2c/scan?bus=${bus}`, { timeout: 15000 });
      setResult(data);
    } catch (err) {
      setResult({
        bus,
        devices: [],
        raw_output: '',
        error: String(err),
      });
    } finally {
      setScanning(false);
    }
  }, [bus]);

  const handleCopyRaw = () => {
    if (!result?.raw_output) return;
    copyToClipboard(result.raw_output).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div>
      <div className="card bg-base-200 mb-6">
        <div className="card-body">
          <h2 className="card-title text-lg">{t('tools.i2c_scan')}</h2>
          <p className="text-sm text-base-content/70 mb-4">
            {t('tools.i2c_scan_hint')}
          </p>

          <div className="flex items-end gap-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text">{t('tools.i2c_bus')}</span>
              </label>
              <select
                className="select select-bordered"
                value={bus}
                onChange={(e) => setBus(parseInt(e.target.value))}
              >
                <option value={0}>I2C-0</option>
                <option value={1}>I2C-1</option>
                <option value={2}>I2C-2 ({t('tools.i2c_default')})</option>
              </select>
            </div>

            <button
              className={`btn btn-primary gap-2 ${scanning ? 'loading' : ''}`}
              onClick={handleScan}
              disabled={scanning}
            >
              {!scanning && <FaSearch />}
              {scanning ? t('tools.i2c_scanning') : t('tools.i2c_scan_btn')}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {result && (
        <>
          {/* Error */}
          {result.error && (
            <div className="alert alert-error mb-6">
              <span>{result.error}</span>
            </div>
          )}

          {/* Detected devices */}
          {result.devices.length > 0 && (
            <div className="card bg-base-200 mb-6">
              <div className="card-body">
                <h2 className="card-title text-lg">
                  {t('tools.i2c_found', { count: result.devices.length })}
                </h2>
                <div className="overflow-x-auto">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>{t('tools.i2c_address')}</th>
                        <th>{t('tools.i2c_decimal')}</th>
                        <th>{t('tools.i2c_possible_devices')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.devices.map((dev) => (
                        <tr key={dev.address} className="hover">
                          <td className="font-mono font-bold text-primary">{dev.address_hex}</td>
                          <td className="font-mono text-base-content/70">{dev.address}</td>
                          <td>
                            {dev.known_devices.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {dev.known_devices.map((name, idx) => (
                                  <span
                                    key={idx}
                                    className={`badge badge-sm ${dev.is_boneio ? 'badge-success' : 'badge-info'}`}
                                  >
                                    {name}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-base-content/40 italic">{t('tools.i2c_unknown')}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* No devices found */}
          {!result.error && result.devices.length === 0 && (
            <div className="alert alert-warning mb-6">
              <span>{t('tools.i2c_no_devices')}</span>
            </div>
          )}

          {/* Raw output */}
          {result.raw_output && (
            <div className="card bg-base-200 mb-6">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h2 className="card-title text-lg">{t('tools.i2c_raw_output')}</h2>
                  <button
                    className="btn btn-sm btn-ghost gap-1"
                    onClick={handleCopyRaw}
                  >
                    <FaCopy className="w-3 h-3" />
                    {copied ? t('tools.copied') : t('tools.copy')}
                  </button>
                </div>
                <pre className="bg-base-300 rounded-lg p-4 font-mono text-sm overflow-x-auto whitespace-pre select-all">
                  {result.raw_output}
                </pre>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
