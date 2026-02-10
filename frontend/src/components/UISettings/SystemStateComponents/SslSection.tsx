import { useState, useCallback } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for SSL/TLS certificate configuration (currently hidden).
 */
export default function SslSection() {
  const { t } = useTranslation();
  const [showSslSettings, setShowSslSettings] = useState(false);
  const [sslConfig, setSslConfig] = useState<{
    mode: 'self_signed' | 'acme';
    domain: string;
    email: string;
  }>({ mode: 'self_signed', domain: '', email: '' });
  const [sslCertificate, setSslCertificate] = useState<{
    issuer?: string;
    valid_from?: string;
    valid_until?: string;
    is_self_signed: boolean;
  } | null>(null);
  const [isSavingSsl, setIsSavingSsl] = useState(false);
  const [sslResult, setSslResult] = useState<{ status: string; message: string } | null>(null);
  const [caddyRunning, setCaddyRunning] = useState<boolean | null>(null);

  const fetchSslConfig = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/caddy/config');
      if (data.status === 'success') {
        setSslConfig({
          mode: data.config?.mode || 'self_signed',
          domain: data.config?.domain || '',
          email: data.config?.email || '',
        });
        if (data.certificate) {
          setSslCertificate(data.certificate);
        }
      }
    } catch (err) {
      console.error('Failed to fetch SSL config:', err);
    }
  }, []);

  const testCaddyConnection = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/caddy/test');
      setCaddyRunning(data.running === true);
    } catch (err) {
      console.error('Failed to test Caddy connection:', err);
      setCaddyRunning(false);
    }
  }, []);

  const saveSslConfig = async () => {
    if (sslConfig.mode === 'acme' && !sslConfig.domain.trim()) {
      setSslResult({ status: 'error', message: t('ssl_certificates.domain_required') });
      return;
    }

    setIsSavingSsl(true);
    setSslResult(null);

    try {
      const { data } = await axios.post('/api/caddy/config', sslConfig);
      setSslResult({
        status: data.status === 'warning' ? 'warning' : 'success',
        message: data.message || t('ssl_certificates.config_saved'),
      });
      await fetchSslConfig();
    } catch (err: any) {
      setSslResult({ status: 'error', message: err.message || t('ssl_certificates.config_save_failed') });
    } finally {
      setIsSavingSsl(false);
    }
  };

  const handleToggle = () => {
    if (!showSslSettings) {
      fetchSslConfig();
      testCaddyConnection();
    }
    setShowSslSettings(!showSslSettings);
  };

  return (
    <div className="card bg-base-200 hidden">
      <div className="card-body">
        <div className="flex items-center justify-between">
          <h3 className="card-title">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            {t('ssl_certificates.title')}
          </h3>
          <div className="flex items-center gap-2">
            {caddyRunning !== null && (
              <span className={`badge ${caddyRunning ? 'badge-success' : 'badge-error'}`}>
                {caddyRunning ? t('ssl_certificates.caddy_running') : t('ssl_certificates.caddy_not_running')}
              </span>
            )}
            <button
              className="btn btn-outline btn-sm"
              onClick={handleToggle}
            >
              {showSslSettings ? t('common.close') : t('ssl_certificates.show_section')}
            </button>
          </div>
        </div>
        <p className="text-sm opacity-70 mt-2">{t('ssl_certificates.description')}</p>

        {showSslSettings && (
          <div className="mt-4 space-y-4">
            {/* Current Certificate Info */}
            {sslCertificate && (
              <div className={`alert ${sslCertificate.is_self_signed ? 'alert-warning' : 'alert-success'}`}>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                  />
                </svg>
                <div className="text-sm">
                  <p className="font-semibold">{t('ssl_certificates.certificate_status')}</p>
                  <p>{sslCertificate.is_self_signed ? t('ssl_certificates.self_signed_info') : t('ssl_certificates.acme_info')}</p>
                  {sslCertificate.issuer && <p>{t('ssl_certificates.issuer')}: {sslCertificate.issuer}</p>}
                  {sslCertificate.valid_until && <p>{t('ssl_certificates.valid_until')}: {sslCertificate.valid_until}</p>}
                </div>
              </div>
            )}

            {/* Mode Selection */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('ssl_certificates.mode')}</span>
              </label>
              <div className="flex gap-4">
                <label className="label cursor-pointer gap-2">
                  <input
                    type="radio"
                    name="ssl-mode"
                    className="radio radio-primary"
                    checked={sslConfig.mode === 'self_signed'}
                    onChange={() => setSslConfig({ ...sslConfig, mode: 'self_signed' })}
                  />
                  <span className="label-text">{t('ssl_certificates.mode_self_signed')}</span>
                </label>
                <label className="label cursor-pointer gap-2">
                  <input
                    type="radio"
                    name="ssl-mode"
                    className="radio radio-primary"
                    checked={sslConfig.mode === 'acme'}
                    onChange={() => setSslConfig({ ...sslConfig, mode: 'acme' })}
                  />
                  <span className="label-text">{t('ssl_certificates.mode_acme')}</span>
                </label>
              </div>
            </div>

            {/* ACME Settings */}
            {sslConfig.mode === 'acme' && (
              <>
                <div className="alert alert-warning">
                  <FaExclamationTriangle />
                  <span className="text-sm">{t('ssl_certificates.acme_warning')}</span>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('ssl_certificates.domain')}</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered w-full max-w-md"
                    value={sslConfig.domain}
                    onChange={e => setSslConfig({ ...sslConfig, domain: e.target.value })}
                    placeholder={t('ssl_certificates.domain_placeholder')}
                    disabled={isSavingSsl}
                  />
                  <label className="label">
                    <span className="label-text-alt">{t('ssl_certificates.domain_hint')}</span>
                  </label>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">{t('ssl_certificates.email')}</span>
                  </label>
                  <input
                    type="email"
                    className="input input-bordered w-full max-w-md"
                    value={sslConfig.email}
                    onChange={e => setSslConfig({ ...sslConfig, email: e.target.value })}
                    placeholder={t('ssl_certificates.email_placeholder')}
                    disabled={isSavingSsl}
                  />
                  <label className="label">
                    <span className="label-text-alt">{t('ssl_certificates.email_hint')}</span>
                  </label>
                </div>
              </>
            )}

            {/* Result Alert */}
            {sslResult && (
              <div className={`alert ${sslResult.status === 'success' ? 'alert-success' : sslResult.status === 'warning' ? 'alert-warning' : 'alert-error'}`}>
                {sslResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
                <span>{sslResult.message}</span>
              </div>
            )}

            {/* Save Button */}
            <button
              className="btn btn-primary"
              onClick={saveSslConfig}
              disabled={isSavingSsl || (sslConfig.mode === 'acme' && !sslConfig.domain.trim())}
            >
              {isSavingSsl ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('ssl_certificates.saving')}
                </>
              ) : (
                <>
                  <FaCheck />
                  {t('ssl_certificates.save_config')}
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
