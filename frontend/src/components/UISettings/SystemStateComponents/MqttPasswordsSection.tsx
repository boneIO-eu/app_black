import { useState, useCallback, useEffect } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaInfoCircle,
  FaSpinner,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for managing MQTT user passwords.
 */
export default function MqttPasswordsSection() {
  const { t } = useTranslation();
  /**
   * Which of these accounts, if any, the application itself connects with.
   *
   * Null until the answer is known, and null is not "boneio": the warning on a
   * row is a claim about this device, and claiming it from a default was the
   * bug this replaced. When boneIO talks to a broker somewhere else — Home
   * Assistant's, usually — no row here belongs to it and none is marked.
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
    [key: string]: { status: string; message: string };
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

  // Fetched on mount now. It used to be fetched when the panel was expanded,
  // which no longer happens because the panel no longer folds.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  return (
    <div className="space-y-6">
      {/* boneIO is pointed at a broker somewhere else — Home Assistant's,
          usually. None of these accounts is the one it signs in with, and
          saying so is the difference between this panel being useful and
          being a trap. */}
      {appAccount && !appAccount.usesLocalBroker && (
        <div className="alert alert-info text-sm">
          <FaInfoCircle className="shrink-0" />
          <span>
            {t('mqtt_passwords.remote_broker_notice', { host: appAccount.host })}
          </span>
        </div>
      )}

      {/* Security warning */}
      <div
        className={`alert ${window.location.protocol === 'https:' ? 'alert-success' : 'alert-warning'} text-sm`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="stroke-current shrink-0 h-5 w-5"
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
        <span>
          {window.location.protocol === 'https:'
            ? t('mqtt_passwords.https_secure')
            : t('mqtt_passwords.http_warning')}
        </span>
      </div>

      <div className="space-y-4">
        {['boneio', 'homeassistant', 'mqtt'].map(username => (
          <div key={username} className="card bg-base-200/50 border border-base-content/10 shadow-sm">
            <div className="card-body p-4 sm:p-5">
              <h4 className="font-semibold text-base mb-3 font-mono">
                {t('mqtt_passwords.username')}: <span className="text-primary">{username}</span>
              </h4>

              {/* Only on the row boneIO actually signs in with, and only
                  when it signs in here at all. */}
              {appAccount?.usesLocalBroker && username === appAccount.username && (
                <div className="alert alert-warning text-xs mb-4">
                  <FaExclamationTriangle className="shrink-0" />
                  <span>{t('mqtt_passwords.boneio_user_warning')}</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-xl">
                <div>
                  <label className="label p-0 pb-1">
                    <span className="label-text font-medium text-xs">
                      {t('mqtt_passwords.new_password')}
                    </span>
                  </label>
                  <input
                    type="password"
                    className="input input-bordered input-sm w-full font-mono"
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
                </div>
                <div>
                  <label className="label p-0 pb-1">
                    <span className="label-text font-medium text-xs">
                      {t('mqtt_passwords.confirm_password')}
                    </span>
                  </label>
                  <input
                    type="password"
                    className="input input-bordered input-sm w-full font-mono"
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
                </div>
              </div>

              <div className="pt-3">
                <button
                  className="btn btn-primary btn-sm"
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
              </div>

              {passwordResults[username]?.message && (
                <div
                  className={`alert ${passwordResults[username].status === 'success' ? 'alert-success' : 'alert-error'} text-sm mt-3`}
                >
                  {passwordResults[username].status === 'success' ? (
                    <FaCheck className="shrink-0" />
                  ) : (
                    <FaExclamationTriangle className="shrink-0" />
                  )}
                  <span>{passwordResults[username].message}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
