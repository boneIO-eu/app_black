import { useState, useCallback, useEffect } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for viewing and changing the device hostname.
 */
export default function HostnameSection() {
  const { t } = useTranslation();
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
    <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
      <div className="card-body p-4 sm:p-6 space-y-4">
        <div className="space-y-4 max-w-lg">
          <div>
            <label className="label">
              <span className="label-text font-medium">{t('settings.current_hostname')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered input-sm sm:input-md w-full font-mono bg-base-200"
              value={currentHostname}
              disabled
            />
          </div>

          <div>
            <label className="label">
              <span className="label-text font-medium">{t('settings.new_hostname')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered input-sm sm:input-md w-full font-mono"
              value={newHostname}
              onChange={e => setNewHostname(e.target.value)}
              placeholder={t('settings.hostname_placeholder')}
              disabled={isChangingHostname}
            />
            <label className="label whitespace-normal">
              <span className="label-text-alt text-base-content/70">{t('settings.hostname_hint')}</span>
            </label>
          </div>

          {hostnameResult && (
            <div className={`alert ${hostnameResult.status === 'success' ? 'alert-success' : 'alert-error'} text-sm`}>
              {hostnameResult.status === 'success' ? <FaCheck className="shrink-0" /> : <FaExclamationTriangle className="shrink-0" />}
              <span>{hostnameResult.message}</span>
            </div>
          )}

          <button
            className="btn btn-primary btn-sm"
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
      </div>
    </div>
  );
}
