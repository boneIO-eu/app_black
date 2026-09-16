/**
 * Bus scans: what is actually wired to this controller.
 *
 * These were the Tools page, which was neither settings nor a page of its
 * own: nothing here is saved. You click and you find out. That is diagnosis,
 * so they live on the Diagnostics page now, beside the log.
 *
 * The file used to own a tab strip that chose between the scans. The
 * Diagnostics sidebar chooses now, the same way Settings picks a section, so
 * what is left here are the panels themselves.
 *
 * The Home Assistant dashboard export left with them — it generates a
 * configuration for an integration rather than reading hardware, so it is a
 * settings section under Connections.
 */
import { useState, useCallback } from 'react';
import { FaCopy, FaSearch } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { copyToClipboard } from '@/utils/clipboard';
import { IoWarning } from 'react-icons/io5';
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

export function CANNotSupported({ boardVersion }: { boardVersion: string | null }) {
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

export function I2CSection() {
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
      {/* No heading: the page header names the section and says what it is
          for. The bus picker is the whole content. */}
      <div className="stg-card mb-4">
        <div className="card-body p-4 sm:p-5">

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
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-l-[3px] border-error/25 border-l-error bg-error/8 p-3.5 text-[13px]">
              <span>{result.error}</span>
            </div>
          )}

          {/* Detected devices */}
          {result.devices.length > 0 && (
            <div className="stg-card mb-4">
              <div className="card-body p-4 sm:p-5">
                <h2 className="font-semibold text-[15px] tracking-tight mb-2">
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
            <div className="stg-card mb-4">
              <div className="card-body p-4 sm:p-5">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold text-[15px] tracking-tight">{t('tools.i2c_raw_output')}</h2>
                  <button
                    className="btn btn-sm btn-ghost gap-1"
                    onClick={handleCopyRaw}
                  >
                    <FaCopy className="w-3 h-3" />
                    {copied ? t('tools.copied') : t('tools.copy')}
                  </button>
                </div>
                <pre className="stg-inset stg-inset-strong p-3 font-mono text-xs overflow-x-auto whitespace-pre select-all">
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
