import { useState, useCallback } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
} from 'react-icons/fa';
import SettingsCard from '../components/SettingsCard';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for managing MQTT user passwords.
 */
export default function MqttPasswordsSection() {
  const { t } = useTranslation();
  const [showMqttPasswords, setShowMqttPasswords] = useState(false);
  const [mqttAppUsername, setMqttAppUsername] = useState<string>('boneio');
  const [mqttPasswords, setMqttPasswords] = useState<{
    [key: string]: { password: string; confirm: string };
  }>({
    boneio: { password: '', confirm: '' },
    homeassistant: { password: '', confirm: '' },
    mqtt: { password: '', confirm: '' },
  });
  const [changingPassword, setChangingPassword] = useState<string | null>(null);
  const [passwordResults, setPasswordResults] = useState<{
    [key: string]: { status: string; message: string };
  }>({});

  const fetchMqttUsername = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/mqtt/username');
      if (data.status === 'success' && data.username) {
        setMqttAppUsername(data.username);
      }
    } catch (err) {
      console.error('Failed to fetch MQTT username:', err);
    }
  }, []);

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
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
          />
        </svg>
      }
      title={t('mqtt_passwords.title')}
      description={t('mqtt_passwords.description')}
      toggleButtonText={t('mqtt_passwords.show_section')}
      toggleButtonTextExpanded={t('common.close')}
      isExpanded={showMqttPasswords}
      onToggle={() => {
        if (!showMqttPasswords) {
          fetchMqttUsername();
        }
        setShowMqttPasswords(!showMqttPasswords);
      }}
      expandableContent={
        <>
          {/* Security warning */}
          <div
            className={`alert ${window.location.protocol === 'https:' ? 'alert-success' : 'alert-warning'}`}
          >
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
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <span className="text-sm">
              {window.location.protocol === 'https:'
                ? t('mqtt_passwords.https_secure')
                : t('mqtt_passwords.http_warning')}
            </span>
          </div>

          <div className="space-y-6 mt-6">
            {['boneio', 'homeassistant', 'mqtt'].map(username => (
              <div key={username} className="card bg-base-100 shadow-sm">
                <div className="card-body p-4">
                  <h4 className="font-semibold text-lg mb-3">
                    {t('mqtt_passwords.username')}: {username}
                  </h4>

                  {/* Warning for app's MQTT user */}
                  {username === mqttAppUsername && (
                    <div className="alert alert-warning mb-4">
                      <FaExclamationTriangle />
                      <span className="text-sm">{t('mqtt_passwords.boneio_user_warning')}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <fieldset className="fieldset">
                      <legend className="fieldset-legend">
                        {t('mqtt_passwords.new_password')}
                      </legend>
                      <input
                        type="password"
                        className="input input-bordered"
                        value={mqttPasswords[username].password}
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
                    </fieldset>
                    <fieldset className="fieldset">
                      <legend className="fieldset-legend">
                        {t('mqtt_passwords.confirm_password')}
                      </legend>
                      <input
                        type="password"
                        className="input input-bordered"
                        value={mqttPasswords[username].confirm}
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
                    </fieldset>
                  </div>

                  <button
                    className="btn btn-primary btn-sm mt-4"
                    onClick={() => changeMqttPassword(username)}
                    disabled={
                      changingPassword === username ||
                      !mqttPasswords[username].password ||
                      !mqttPasswords[username].confirm
                    }
                  >
                    {changingPassword === username ? (
                      <>
                        <FaSpinner className="animate-spin mr-2" />
                        {t('mqtt_passwords.changing')}
                      </>
                    ) : (
                      t('mqtt_passwords.change_password')
                    )}
                  </button>

                  {passwordResults[username]?.message && (
                    <div
                      className={`alert ${passwordResults[username].status === 'success' ? 'alert-success' : 'alert-error'} mt-3`}
                    >
                      {passwordResults[username].status === 'success' ? (
                        <FaCheck />
                      ) : (
                        <FaExclamationTriangle />
                      )}
                      <span className="text-sm">{passwordResults[username].message}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      }
    />
  );
}
