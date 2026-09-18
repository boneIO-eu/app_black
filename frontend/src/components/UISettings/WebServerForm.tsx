import { Link } from 'react-router-dom';
import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FaExclamationTriangle, FaInfoCircle, FaCheck, FaSpinner } from 'react-icons/fa';
import { FormInputNumber, FormInputText } from './widgets';
import HelpLabel from './components/HelpLabel';
import { NoticeCallout } from './ui';

interface WebServerFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Web Server section configuration.
 * Fields: port, proxy port, cloud registration, PWA name.
 *
 * Credentials are deliberately absent. From 1.6 accounts live in users.json
 * with hashed passwords and roles, managed by the Accounts section rendered
 * next to this form. The `web.auth` keys stay in the config schema so a
 * pre-1.6 config still parses and the startup migration can move the old pair
 * across — the validator purges unknown keys, so dropping them from the schema
 * would silently strip an upgrading user's credentials before the migration
 * ever saw them.
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


  return (
    <div className="stg-cols">
      {/* Port */}
      <FormInputNumber
        label={t('webserver.port')}
        value={data?.port ?? 8090}
        onChange={(val) => handleChange('port', val === '' ? 8090 : val)}
        placeholder="8090"
        help={t('webserver.port_help')}
      />

      {/* The port Home Assistant is told about. Named after nginx until 1.6,
          which has not been what sits in front of this panel since 1.4.4 —
          and the old wording read as "no proxy unless you fill this in", on a
          device whose built-in proxy is always there. */}
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


      <NoticeCallout
        variant="info"
        title={t('webserver.builtin_proxy_title')}
        message={t('webserver.builtin_proxy')}
      />

      {/* Whether the panel's own port answers on the network at all. The
          Security section offers the same switch with a check that the proxy
          is really serving first; here it is simply the setting, so somebody
          looking for it finds it where the other web settings are. */}
      <div className="form-control flex flex-col gap-2">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            className="toggle toggle-primary shrink-0"
            checked={data?.expose === 'proxy'}
            onChange={(e) =>
              handleChange('expose', e.target.checked ? 'proxy' : 'all')
            }
          />
          <span className="label-text font-medium">{t('webserver.expose_proxy')}</span>
        </label>
        <HelpLabel className="pt-0">{t('webserver.expose_proxy_help')}</HelpLabel>
      </div>

      {/* Where the username/password fields used to be, so nobody hunts for
          the web password that moved to hashed accounts in 1.6. */}
      <div className="divider">{t('webserver.auth')}</div>
      <NoticeCallout
        variant="info"
        message={
          <>
            {t('webserver.accounts_moved')}{' '}
            <Link to="/settings/accounts" className="link font-semibold">
              {t('sections.accounts')}
            </Link>
          </>
        }
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
          <NoticeCallout
            variant="warning"
            title={t('boneio_config.cloud_registration_warning_title')}
            message={t('boneio_config.cloud_registration_warning')}
          />

          {/* Permission error */}
          {!composeWritable && !isHttps && (
            <NoticeCallout
              variant="error"
              title={t('boneio_config.cloud_permission_error_title') || 'Permission error'}
              message={
                <span className="font-mono text-xs break-all">
                  {t('boneio_config.cloud_permission_error') || 'docker-compose.yaml is not writable. Run via SSH: sudo chown $USER ~/docker/nodered/docker-compose.yaml'}
                </span>
              }
            />
          )}

          {/* The compose file is root-owned on purpose: it is what
              `docker compose up` executes, so being able to write it is being
              able to run a container as root. There used to be a button here
              that asked for the sudo password and chowned it back. */}
          {!composeWritable && isHttps && (
            <NoticeCallout
              variant="warning"
              title={t('boneio_config.cloud_permission_managed_title')}
              message={t('boneio_config.cloud_permission_managed')}
            />
          )}

          {/* Cloud error */}
          {cloudError && composeWritable && (
            <NoticeCallout
              variant="error"
              title={t('boneio_config.cloud_error_title') || 'Cloud configuration error'}
              message={<span className="wrap-break-word">{cloudError}</span>}
            />
          )}

          {/* Domain info */}
          <NoticeCallout
            variant="info"
            message={
              <>
                <span className="block">{t('boneio_config.cloud_registration_domain')}</span>
                <span className="block font-mono font-bold mt-1">
                  https://{'<serial>'}.black.boneio.app:8443
                </span>
                <span className="block mt-1 opacity-70">
                  {t('boneio_config.cloud_registration_lan_only')}
                </span>
              </>
            }
          />

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
