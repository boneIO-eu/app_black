import { useState, useCallback, useEffect } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
} from 'react-icons/fa';
import SettingsCard from '../components/SettingsCard';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for viewing and changing the device hostname.
 */
export default function HostnameSection() {
  const { t } = useTranslation();
  const [showHostnameSection, setShowHostnameSection] = useState(false);
  const [currentHostname, setCurrentHostname] = useState<string>('');
  const [newHostname, setNewHostname] = useState<string>('');
  const [isChangingHostname, setIsChangingHostname] = useState(false);
  const [hostnameResult, setHostnameResult] = useState<{ status: string; message: string } | null>(null);

  const fetchHostname = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/hostname');
      setCurrentHostname(data.hostname || '');
      setNewHostname(data.hostname || '');
    } catch (err) {
      console.error('Failed to fetch hostname:', err);
    }
  }, []);

  useEffect(() => {
    fetchHostname();
  }, [fetchHostname]);

  const changeHostname = async () => {
    if (!newHostname.trim()) {
      setHostnameResult({ status: 'error', message: t('settings.hostname_empty') });
      return;
    }

    if (newHostname === currentHostname) {
      setHostnameResult({ status: 'error', message: t('settings.hostname_unchanged') });
      return;
    }

    setIsChangingHostname(true);
    setHostnameResult(null);

    try {
      const { data } = await axios.post('/api/hostname', { hostname: newHostname });
      setCurrentHostname(data.hostname);
      setHostnameResult({ status: 'success', message: t('settings.hostname_changed') });
    } catch (err: any) {
      setHostnameResult({ status: 'error', message: err.message || t('settings.hostname_change_failed') });
    } finally {
      setIsChangingHostname(false);
    }
  };

  return (
    <SettingsCard
      icon={
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
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      }
      title={t('settings.hostname_title')}
      description={t('settings.hostname_description')}
      toggleButtonText={t('settings.show_hostname_section')}
      toggleButtonTextExpanded={t('common.close')}
      isExpanded={showHostnameSection}
      onToggle={() => setShowHostnameSection(!showHostnameSection)}
      expandableContent={
        <div className="space-y-4">
          <div>
            <label className="label">
              <span className="label-text">{t('settings.current_hostname')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={currentHostname}
              disabled
            />
          </div>

          <div>
            <label className="label">
              <span className="label-text">{t('settings.new_hostname')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={newHostname}
              onChange={e => setNewHostname(e.target.value)}
              placeholder={t('settings.hostname_placeholder')}
              disabled={isChangingHostname}
            />
            <label className="label whitespace-normal">
              <span className="label-text-alt wrap-break-word">{t('settings.hostname_hint')}</span>
            </label>
          </div>

          {hostnameResult && (
            <div className={`alert ${hostnameResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
              {hostnameResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{hostnameResult.message}</span>
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={changeHostname}
            disabled={isChangingHostname || !newHostname.trim() || newHostname === currentHostname}
          >
            {isChangingHostname ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('settings.changing_hostname')}
              </>
            ) : (
              <>
                <FaCheck />
                {t('settings.change_hostname')}
              </>
            )}
          </button>
        </div>
      }
    />
  );
}
