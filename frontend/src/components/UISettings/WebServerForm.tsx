import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FaExclamationTriangle, FaInfoCircle, FaCheck, FaSpinner } from 'react-icons/fa';
import HelpLabel from './components/HelpLabel';

interface WebServerFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Web Server section configuration.
 * Fields: port, auth (username, password)
 */
const WebServerForm: React.FC<WebServerFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();

  // PWA name state
  const [currentPwaName, setCurrentPwaName] = useState<string>('');
  const [newPwaName, setNewPwaName] = useState<string>('');
  const [pwaNameDefault, setPwaNameDefault] = useState<string>('');
  const [isChangingPwaName, setIsChangingPwaName] = useState(false);
  const [pwaNameResult, setPwaNameResult] = useState<{ status: string; message: string } | null>(null);
  const [showPwaPrivacyDialog, setShowPwaPrivacyDialog] = useState(false);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [isDisablingCloud, setIsDisablingCloud] = useState(false);
  const [cloudActive, setCloudActive] = useState(false);

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleCloudChange = (field: string, value: any) => {
    const cloud = data?.cloud || {};
    onChange({ ...data, cloud: { ...cloud, [field]: value } });
  };

  // Fetch PWA name and cloud status when cloud registration is enabled
  useEffect(() => {
    if (data?.cloud?.enabled) {
      axios.get('/api/pwa_name').then(({ data: res }) => {
        setCurrentPwaName(res.pwa_name || '');
        setNewPwaName(res.pwa_name || '');
        setPwaNameDefault(res.default || '');
      }).catch(() => {});

      axios.get('/api/cloud/status').then(({ data: res }) => {
        setCloudError(res.last_error || null);
        setCloudActive(res.cloud_config_active || false);
      }).catch(() => {});
    }
  }, [data?.cloud?.enabled]);

  const changePwaName = async () => {
    if (!newPwaName.trim()) {
      setPwaNameResult({ status: 'error', message: t('settings.pwa_name_empty') });
      return;
    }
    if (newPwaName === currentPwaName) {
      setPwaNameResult({ status: 'error', message: t('settings.pwa_name_unchanged') });
      return;
    }
    setIsChangingPwaName(true);
    setPwaNameResult(null);
    try {
      const { data: res } = await axios.post('/api/pwa_name', { pwa_name: newPwaName });
      setCurrentPwaName(res.pwa_name);
      setPwaNameResult({ status: 'success', message: t('settings.pwa_name_changed') });
    } catch (err: any) {
      setPwaNameResult({ status: 'error', message: err.message || t('settings.pwa_name_change_failed') });
    } finally {
      setIsChangingPwaName(false);
    }
  };

  const handleAuthChange = (field: string, value: any) => {
    const auth = data?.auth || {};
    const newAuth = { ...auth, [field]: value || undefined };
    
    // Remove auth object if both fields are empty
    if (!newAuth.username && !newAuth.password) {
      const { auth: _, ...rest } = data || {};
      onChange(rest);
    } else {
      onChange({ ...data, auth: newAuth });
    }
  };

  return (
    <div className="space-y-4">
      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.port ?? 8090}
          onChange={(e) => handleChange('port', parseInt(e.target.value) || 8090)}
          placeholder="8090"
        />
        <HelpLabel>{t('webserver.port_help')}</HelpLabel>
      </div>

      {/* Nginx Proxy Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.proxy_port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.proxy_port ?? ''}
          onChange={(e) => {
            const val = e.target.value ? parseInt(e.target.value) : undefined;
            if (val) {
              handleChange('proxy_port', val);
            } else {
              const { proxy_port: _, ...rest } = data || {};
              onChange(rest);
            }
          }}
          placeholder={t('webserver.proxy_port_placeholder')}
        />
        <HelpLabel>{t('webserver.proxy_port_help')}</HelpLabel>
      </div>

      {/* Auth Section */}
      <div className="divider">{t('webserver.auth')}</div>

      {/* Username */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.username')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.auth?.username || ''}
          onChange={(e) => handleAuthChange('username', e.target.value)}
          placeholder="admin"
        />
        <HelpLabel>{t('webserver.username_help')}</HelpLabel>
      </div>

      {/* Password */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('webserver.password')}</span>
        </label>
        <input
          type="password"
          className="input input-bordered w-full"
          value={data?.auth?.password || ''}
          onChange={(e) => handleAuthChange('password', e.target.value)}
          placeholder="••••••••"
        />
        <HelpLabel>{t('webserver.password_help')}</HelpLabel>
      </div>

      {/* Cloud Registration (PWA) */}
      <div className="divider"></div>
      <div className="form-control flex flex-col gap-2">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            className="toggle toggle-primary shrink-0"
            checked={data?.cloud?.enabled || false}
            onChange={async (e) => {
              const enabled = e.target.checked;
              if (!enabled && cloudActive) {
                if (!confirm(t('boneio_config.cloud_disable_confirm') || 'Are you sure? This will restore Caddy to default settings with local IP access and self-signed certificates. The PWA subdomain will stop working.')) {
                  e.preventDefault();
                  return;
                }
                setIsDisablingCloud(true);
                try {
                  await axios.post('/api/cloud/disable');
                  setCloudActive(false);
                } catch (err) {
                  // continue anyway — config change still applies
                } finally {
                  setIsDisablingCloud(false);
                }
              }
              handleCloudChange('enabled', enabled);
              if (enabled) setShowPwaPrivacyDialog(true);
            }}
            disabled={isDisablingCloud}
          />
          <span className="label-text font-medium">{t('boneio_config.cloud_registration')}</span>
        </label>
        <HelpLabel className="pt-0">{t('boneio_config.cloud_registration_help')}</HelpLabel>
      </div>

      {data?.cloud?.enabled && (
        <div className="space-y-3 ml-2">
          {/* DNS Rebinding Warning */}
          <div className="alert alert-warning text-sm">
            <FaExclamationTriangle className="shrink-0" />
            <div>
              <p className="font-semibold">{t('boneio_config.cloud_registration_warning_title')}</p>
              <p className="mt-1">{t('boneio_config.cloud_registration_warning')}</p>
            </div>
          </div>

          {/* Cloud error */}
          {cloudError && (
            <div className="alert alert-error text-sm">
              <FaExclamationTriangle className="shrink-0" />
              <div>
                <p className="font-semibold">{t('boneio_config.cloud_error_title') || 'Cloud configuration error'}</p>
                <p className="mt-1 whitespace-normal wrap-break-word">{cloudError}</p>
              </div>
            </div>
          )}

          {/* Domain info */}
          <div className="alert alert-info text-sm">
            <div>
              <p>{t('boneio_config.cloud_registration_domain')}</p>
              <p className="font-mono font-bold mt-1">https://{'<serial>'}.black.boneio.app:8443</p>
              <p className="mt-1 opacity-70">{t('boneio_config.cloud_registration_lan_only')}</p>
            </div>
          </div>

          {/* PWA App Name */}
          <div className="divider text-xs opacity-60">{t('settings.pwa_name_title')}</div>
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('settings.pwa_name_title')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={newPwaName}
              onChange={e => setNewPwaName(e.target.value.slice(0, 12))}
              placeholder={pwaNameDefault || 'bIO abc123'}
              disabled={isChangingPwaName}
              maxLength={12}
            />
            <HelpLabel>{t('settings.pwa_name_hint')} ({newPwaName.length}/12)</HelpLabel>
          </div>

          {pwaNameResult && (
            <div className={`alert text-sm ${pwaNameResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
              {pwaNameResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{pwaNameResult.message}</span>
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            <button
              className="btn btn-sm btn-primary"
              onClick={changePwaName}
              disabled={isChangingPwaName || !newPwaName.trim() || newPwaName === currentPwaName}
            >
              {isChangingPwaName ? (
                <><FaSpinner className="animate-spin" /> {t('settings.changing_pwa_name')}</>
              ) : (
                <><FaCheck /> {t('settings.change_pwa_name')}</>
              )}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setShowPwaPrivacyDialog(true)}
            >
              <FaInfoCircle className="mr-1" />
              {t('settings.pwa_privacy_info')}
            </button>
          </div>


        </div>
      )}

      {/* PWA Privacy Info Dialog */}
      {showPwaPrivacyDialog && (
        <dialog className="modal modal-open" onClick={() => setShowPwaPrivacyDialog(false)}>
          <div className="modal-box max-w-lg" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold text-lg flex items-center gap-2">
              <FaInfoCircle className="text-info" />
              {t('settings.pwa_privacy_title')}
            </h3>
            <div className="py-4 space-y-3 text-sm">
              <p>{t('settings.pwa_privacy_dns')}</p>
              <p>{t('settings.pwa_privacy_lan_only')}</p>
              <p>{t('settings.pwa_privacy_ssl')}</p>
              <p>{t('settings.pwa_privacy_cf_analytics')}</p>
            </div>
            <div className="modal-action">
              <button
                className="btn btn-primary"
                onClick={() => setShowPwaPrivacyDialog(false)}
              >
                {t('settings.pwa_privacy_understood')}
              </button>
            </div>
          </div>
        </dialog>
      )}
    </div>
  );
};

export default WebServerForm;
