import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FaExclamationTriangle, FaInfoCircle, FaCheck, FaSpinner } from 'react-icons/fa';
import { FormInputNumber, FormInputText } from './widgets';
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
  const [composeWritable, setComposeWritable] = useState(true);
  const [isDisablingCloud, setIsDisablingCloud] = useState(false);
  const [cloudActive, setCloudActive] = useState(false);
  const [sudoPassword, setSudoPassword] = useState('');
  const [isFixingPermissions, setIsFixingPermissions] = useState(false);
  const [fixResult, setFixResult] = useState<{ status: string; message: string } | null>(null);
  const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';

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
        if (res.compose_writable !== undefined) setComposeWritable(res.compose_writable);
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

  const handleFixPermissions = async () => {
    setIsFixingPermissions(true);
    setFixResult(null);
    try {
      const { data: res } = await axios.post('/api/cloud/fix-permissions', { password: sudoPassword });
      setFixResult(res);
      if (res.status === 'success') {
        setComposeWritable(true);
        setSudoPassword('');
      }
    } catch (err: any) {
      setFixResult({ status: 'error', message: err.message || 'Request failed' });
    } finally {
      setIsFixingPermissions(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Port */}
      <FormInputNumber
        label={t('webserver.port')}
        value={data?.port ?? 8090}
        onChange={(val) => handleChange('port', val === '' ? 8090 : val)}
        placeholder="8090"
        help={t('webserver.port_help')}
      />

      {/* Nginx Proxy Port */}
      <FormInputNumber
        label={t('webserver.proxy_port')}
        value={data?.proxy_port ?? ''}
        onChange={(val) => {
          if (val === '') {
            const { proxy_port: _, ...rest } = data || {};
            onChange(rest);
            return;
          }
          handleChange('proxy_port', val);
        }}
        placeholder={t('webserver.proxy_port_placeholder')}
        help={t('webserver.proxy_port_help')}
      />

      {/* Auth Section */}
      <div className="divider">{t('webserver.auth')}</div>

      {/* Username */}
      <FormInputText
        label={t('webserver.username')}
        value={data?.auth?.username || ''}
        onChange={(val) => handleAuthChange('username', val)}
        placeholder="admin"
        help={t('webserver.username_help')}
      />

      {/* Password */}
      <FormInputText
        label={t('webserver.password')}
        value={data?.auth?.password || ''}
        onChange={(val) => handleAuthChange('password', val)}
        placeholder="••••••••"
        help={t('webserver.password_help')}
        type="password"
      />

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

          {/* Permission error */}
          {!composeWritable && !isHttps && (
            <div className="alert alert-error text-sm">
              <FaExclamationTriangle className="shrink-0" />
              <div>
                <p className="font-semibold">{t('boneio_config.cloud_permission_error_title') || 'Permission error'}</p>
                <p className="mt-1 font-mono text-xs">{t('boneio_config.cloud_permission_error') || 'docker-compose.yaml is not writable. Run via SSH: sudo chown $USER ~/docker/nodered/docker-compose.yaml'}</p>
              </div>
            </div>
          )}

          {/* Permission error with sudo fix (HTTPS only) */}
          {!composeWritable && isHttps && (
            <div className="alert alert-error text-sm">
              <FaExclamationTriangle className="shrink-0" />
              <div className="w-full">
                <p className="font-semibold">{t('boneio_config.cloud_permission_error_title') || 'Permission error'}</p>
                <p className="mt-1">{t('boneio_config.cloud_permission_fix_hint') || 'Enter your system password to fix file permissions automatically:'}</p>
                <div className="flex gap-2 mt-2 items-center">
                  <input
                    type="password"
                    className="input input-bordered input-sm flex-1"
                    placeholder={t('boneio_config.cloud_sudo_placeholder') || 'System password'}
                    value={sudoPassword}
                    onChange={(e) => setSudoPassword(e.target.value)}
                    disabled={isFixingPermissions}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && sudoPassword) handleFixPermissions();
                    }}
                  />
                  <button
                    className={`btn btn-sm btn-primary ${isFixingPermissions ? 'loading' : ''}`}
                    onClick={handleFixPermissions}
                    disabled={!sudoPassword || isFixingPermissions}
                  >
                    {isFixingPermissions ? <FaSpinner className="animate-spin" /> : t('boneio_config.cloud_fix_btn') || 'Fix'}
                  </button>
                </div>
                {fixResult && (
                  <p className={`mt-2 text-xs ${fixResult.status === 'success' ? 'text-success' : 'text-error'}`}>
                    {fixResult.status === 'success' ? <FaCheck className="inline mr-1" /> : <FaExclamationTriangle className="inline mr-1" />}
                    {fixResult.message}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Cloud error */}
          {cloudError && composeWritable && (
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
          <FormInputText
            label={t('settings.pwa_name_title')}
            value={newPwaName}
            onChange={(val) => setNewPwaName(val.slice(0, 12))}
            placeholder={pwaNameDefault || 'bIO abc123'}
            help={`${t('settings.pwa_name_hint')} (${newPwaName.length}/12)`}
            maxLength={12}
            disabled={isChangingPwaName}
          />

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
