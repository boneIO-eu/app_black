import { useState, useCallback, useEffect } from 'react';
import {
  FaSpinner,
  FaKey,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import {
  SettingsPage,
  SettingsCard,
  FormField,
  FormActions,
  NoticeCallout,
} from '../ui';

/**
 * Section for managing MQTT user passwords.
 */
export default function MqttPasswordsSection() {
  const { t } = useTranslation();
  /**
   * Which of these accounts, if any, the application itself connects with.
   */
  const [appAccount, setAppAccount] = useState<{
    username: string;
    host: string;
    usesLocalBroker: boolean;
  } | null>(null);
  const [mqttPasswords, setMqttPasswords] = useState<{
    [key: string]: { password: string; confirm: string };
  }>({
    boneio: { password: '', confirm: '' },
    homeassistant: { password: '', confirm: '' },
    mqtt: { password: '', confirm: '' },
  });
  const [changingPassword, setChangingPassword] = useState<string | null>(null);
  const [passwordResults, setPasswordResults] = useState<{
    [key: string]: { status: 'success' | 'error' | ''; message: string };
  }>({});

  const fetchMqttUsername = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/mqtt/username');
      if (data.status === 'success' && data.known) {
        setAppAccount({
          username: data.username,
          host: data.host,
          usesLocalBroker: Boolean(data.uses_local_broker),
        });
      }
    } catch (err) {
      console.error('Failed to fetch MQTT username:', err);
    }
  }, []);

  useEffect(() => {
    void fetchMqttUsername();
  }, [fetchMqttUsername]);

  const changeMqttPassword = async (username: string) => {
    const passwords = mqttPasswords[username];

    if (passwords.password !== passwords.confirm) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: t('mqtt_passwords.password_mismatch') },
      });
      return;
    }

    if (passwords.password.length < 8) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: t('mqtt_passwords.password_too_short') },
      });
      return;
    }

    setChangingPassword(username);
    setPasswordResults({ ...passwordResults, [username]: { status: '', message: '' } });

    try {
      const { data } = await axios.post('/api/mqtt/change_password', {
        username: username,
        new_password: passwords.password,
      });

      if (data.status === 'success') {
        setPasswordResults({
          ...passwordResults,
          [username]: { status: 'success', message: t('mqtt_passwords.password_changed') },
        });
        setMqttPasswords({
          ...mqttPasswords,
          [username]: { password: '', confirm: '' },
        });
      } else {
        setPasswordResults({
          ...passwordResults,
          [username]: { status: 'error', message: data.message },
        });
      }
    } catch (err) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: String(err) },
      });
    } finally {
      setChangingPassword(null);
    }
  };

  const getUserBadge = (username: string) => {
    switch (username) {
      case 'boneio':
        return <span className="badge badge-primary badge-sm font-semibold">boneIO</span>;
      case 'homeassistant':
        return <span className="badge badge-info badge-sm font-semibold">Home Assistant</span>;
      default:
        return <span className="badge badge-ghost badge-sm font-semibold">MQTT</span>;
    }
  };

  return (
    <SettingsPage>
      {/* Remote broker notice */}
      {appAccount && !appAccount.usesLocalBroker && (
        <NoticeCallout
          variant="info"
          message={t('mqtt_passwords.remote_broker_notice', { host: appAccount.host })}
        />
      )}

      {/* Security warning */}
      <NoticeCallout
        variant={window.location.protocol === 'https:' ? 'success' : 'warning'}
        message={
          window.location.protocol === 'https:'
            ? t('mqtt_passwords.https_secure')
            : t('mqtt_passwords.http_warning')
        }
      />

      {/* Account Cards */}
      {['boneio', 'homeassistant', 'mqtt'].map(username => {
        const isCurrentAppUser = appAccount?.usesLocalBroker && username === appAccount.username;
        const result = passwordResults[username];
        const entry = mqttPasswords[username];
        const canSubmit = Boolean(entry.password && entry.confirm);

        return (
          <SettingsCard
            key={username}
            icon={<FaKey />}
            title={<span className="font-mono">{username}</span>}
            action={getUserBadge(username)}
            footer={
              <FormActions
                hint={
                  entry.password && entry.password.length < 8
                    ? t('mqtt_passwords.password_too_short')
                    : undefined
                }
              >
                <button
                  className="btn btn-primary btn-sm gap-2"
                  onClick={() => changeMqttPassword(username)}
                  disabled={changingPassword === username || !canSubmit}
                >
                  {changingPassword === username ? (
                    <>
                      <FaSpinner className="animate-spin" />
                      {t('mqtt_passwords.changing')}
                    </>
                  ) : (
                    t('mqtt_passwords.change_password')
                  )}
                </button>
              </FormActions>
            }
          >
            <div className="space-y-4">
              {isCurrentAppUser && (
                <NoticeCallout
                  variant="warning"
                  message={t('mqtt_passwords.boneio_user_warning')}
                />
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormField label={t('mqtt_passwords.new_password')}>
                  <input
                    type="password"
                    className="input input-bordered w-full font-mono"
                    autoComplete="new-password"
                    value={entry.password}
                    onChange={e =>
                      setMqttPasswords({
                        ...mqttPasswords,
                        [username]: {
                          ...mqttPasswords[username],
                          password: e.target.value,
                        },
                      })
                    }
                    disabled={changingPassword === username}
                  />
                </FormField>

                <FormField label={t('mqtt_passwords.confirm_password')}>
                  <input
                    type="password"
                    className="input input-bordered w-full font-mono"
                    autoComplete="new-password"
                    value={entry.confirm}
                    onChange={e =>
                      setMqttPasswords({
                        ...mqttPasswords,
                        [username]: {
                          ...mqttPasswords[username],
                          confirm: e.target.value,
                        },
                      })
                    }
                    disabled={changingPassword === username}
                  />
                </FormField>
              </div>

              {result?.message && (
                <NoticeCallout
                  variant={result.status === 'success' ? 'success' : 'error'}
                  message={result.message}
                />
              )}
            </div>
          </SettingsCard>
        );
      })}
    </SettingsPage>
  );
}
