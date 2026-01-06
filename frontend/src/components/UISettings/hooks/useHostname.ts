import { useState, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface HostnameResult {
  status: string;
  message: string;
}

export const useHostname = () => {
  const { t } = useTranslation();
  const [showHostnameSection, setShowHostnameSection] = useState(false);
  const [currentHostname, setCurrentHostname] = useState<string>('');
  const [newHostname, setNewHostname] = useState<string>('');
  const [isChangingHostname, setIsChangingHostname] = useState(false);
  const [hostnameResult, setHostnameResult] = useState<HostnameResult | null>(null);

  const fetchCurrentHostname = useCallback(async () => {
    try {
      const response = await fetch('/api/hostname');
      const data = await response.json();
      setCurrentHostname(data.hostname || '');
    } catch (err) {
      console.error('Failed to fetch hostname:', err);
    }
  }, []);

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
      const response = await fetch('/api/hostname', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hostname: newHostname }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('settings.hostname_change_failed'));
      }

      const data = await response.json();
      setHostnameResult({ status: 'success', message: data.message || t('settings.hostname_changed') });
      setCurrentHostname(newHostname);
      setNewHostname('');
    } catch (err: any) {
      setHostnameResult({ status: 'error', message: err.message || t('settings.hostname_change_failed') });
    } finally {
      setIsChangingHostname(false);
    }
  };

  return {
    showHostnameSection,
    setShowHostnameSection,
    currentHostname,
    newHostname,
    setNewHostname,
    isChangingHostname,
    hostnameResult,
    fetchCurrentHostname,
    changeHostname,
  };
};
