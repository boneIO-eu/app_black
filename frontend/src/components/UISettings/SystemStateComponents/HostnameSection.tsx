import { useState, useCallback, useEffect } from 'react';
import { FaCheck, FaSpinner, FaGlobe } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import { SettingsCard, StatusTile, FormField, NoticeCallout } from '../ui';

/**
 * Section for viewing and changing the device hostname.
 */
export default function HostnameSection() {
  const { t } = useTranslation();
  const [currentHostname, setCurrentHostname] = useState<string>('');
  const [newHostname, setNewHostname] = useState<string>('');
  const [isChangingHostname, setIsChangingHostname] = useState(false);
  const [hostnameResult, setHostnameResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null);

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
    <div className="max-w-2xl space-y-6">
      <SettingsCard>
        <div className="space-y-5">
          {/* Current hostname displayed as a clean status tile */}
          <StatusTile
            icon={<FaGlobe />}
            label={t('settings.current_hostname')}
            value={currentHostname || '—'}
            suffix={currentHostname ? '.local' : undefined}
            badge={
              currentHostname ? (
                <span className="badge badge-success badge-sm font-normal gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success"></span>
                  mDNS
                </span>
              ) : undefined
            }
          />

          {/* New hostname input */}
          <FormField
            label={t('settings.new_hostname')}
            help={t('settings.hostname_hint')}
          >
            <div className="flex flex-col sm:flex-row gap-2 mt-1">
              <input
                type="text"
                className="input input-bordered input-sm sm:input-md flex-1 font-mono"
                value={newHostname}
                onChange={e => setNewHostname(e.target.value)}
                placeholder={t('settings.hostname_placeholder')}
                disabled={isChangingHostname}
              />
              <button
                className="btn btn-primary btn-sm sm:btn-md gap-2 shrink-0 font-medium"
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
          </FormField>

          {hostnameResult && (
            <NoticeCallout
              variant={hostnameResult.status}
              message={hostnameResult.message}
            />
          )}
        </div>
      </SettingsCard>
    </div>
  );
}
