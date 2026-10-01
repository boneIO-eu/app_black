import React, { useCallback, useEffect, useRef, useState } from 'react';
import axiosInstance from '@/api/axios';
import { apiErrorMessage } from '@/api/errorMessage';
import { useTranslation } from '@/hooks/useTranslation';
import { FormField, NoticeCallout, ToggleRow } from '../ui';
import HelpLabel from '../components/HelpLabel';
import OpenSslGuide from './OpenSslGuide';

/** The `mqtt.tls` section. */
export interface MqttTlsConfig {
  [key: string]: unknown;
  enabled?: boolean;
  ca_certs?: string;
  certfile?: string;
  keyfile?: string;
  insecure?: boolean;
}

interface StoredFile {
  path: string;
  subject: string;
  issuer: string;
  not_after: string;
  names: string[];
  count: number;
  key_path?: string;
}

interface ClientTlsState {
  files: { ca: StoredFile | null; client: StoredFile | null };
  tls_error: string | null;
  connected: boolean;
}

type Verify = 'system' | 'custom' | 'insecure';

interface MqttTlsSettingsProps {
  tls: MqttTlsConfig | undefined;
  port: number | undefined;
  /** Apply a change to `mqtt.tls` and, optionally, to the port with it. */
  onChange: (tls: MqttTlsConfig, port?: number) => void;
}

const DEFAULT_PORT = 1883;
const TLS_PORT = 8883;

const errorDetail = apiErrorMessage;

/** Drop keys whose value is undefined, so the saved section stays tidy. */
const clean = (tls: MqttTlsConfig): MqttTlsConfig =>
  Object.fromEntries(Object.entries(tls).filter(([, v]) => v !== undefined)) as MqttTlsConfig;

const FileSummary: React.FC<{ file: StoredFile }> = ({ file }) => {
  const { t } = useTranslation();
  return (
    <dl className="text-xs space-y-0.5 stg-inset p-2">
      <div>
        <dt className="inline font-semibold">{t('mqtt_tls.subject')}: </dt>
        <dd className="inline break-all">{file.subject}</dd>
      </div>
      {file.issuer !== file.subject && (
        <div>
          <dt className="inline font-semibold">{t('mqtt_tls.issuer')}: </dt>
          <dd className="inline break-all">{file.issuer}</dd>
        </div>
      )}
      <div>
        <dt className="inline font-semibold">{t('mqtt_tls.expires')}: </dt>
        <dd className="inline">{new Date(file.not_after).toLocaleDateString()}</dd>
      </div>
      <div className="text-base-content/60 font-mono">{file.path}</div>
    </dl>
  );
};

/**
 * TLS for boneIO's own connection to its broker.
 *
 * Uploads go straight to the device (they are files, not settings); the
 * paths they produce land in the form like any other field and are applied
 * with the section's Save.
 */
const MqttTlsSettings: React.FC<MqttTlsSettingsProps> = ({ tls, port, onChange }) => {
  const { t } = useTranslation();
  const section: MqttTlsConfig = tls ?? {};
  const enabled = section.enabled === true;

  const [state, setState] = useState<ClientTlsState | null>(null);
  // What the section says is the truth; these only remember a choice that
  // has nothing to write yet — "my own CA" or "client certificate" picked
  // before anything was uploaded. Derived from props rather than copied at
  // mount, or Restore (and data arriving after the form) would leave the
  // controls showing a choice the section no longer holds.
  const [pendingCustom, setPendingCustom] = useState(false);
  const [pendingClient, setPendingClient] = useState(false);
  const emitted = useRef<MqttTlsConfig | undefined>(undefined);
  const verify: Verify = section.insecure ? 'insecure' : section.ca_certs || pendingCustom ? 'custom' : 'system';
  const useClientCert = Boolean(section.certfile) || pendingClient;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const caInput = useRef<HTMLInputElement>(null);
  const certInput = useRef<HTMLInputElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axiosInstance.get<ClientTlsState>('/api/mqtt-tls/client');
      setState(data);
    } catch {
      setState(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // A section that changed without us — Restore, or the saved data arriving —
  // drops any unfinished choice.
  useEffect(() => {
    if (tls !== emitted.current) {
      setPendingCustom(false);
      setPendingClient(false);
    }
  }, [tls]);

  const update = (patch: MqttTlsConfig, newPort?: number) => {
    const next = clean({ ...section, ...patch });
    emitted.current = next;
    onChange(next, newPort);
  };

  const toggle = (on: boolean) => {
    // The port follows only while it is still the other mode's default; a
    // broker on a port of its own keeps it.
    const current = port ?? DEFAULT_PORT;
    if (on) update({ enabled: true }, current === DEFAULT_PORT ? TLS_PORT : undefined);
    else update({ enabled: false }, current === TLS_PORT ? DEFAULT_PORT : undefined);
  };

  const chooseVerify = (choice: Verify) => {
    setPendingCustom(choice === 'custom');
    if (choice === 'system') update({ insecure: undefined, ca_certs: undefined });
    if (choice === 'insecure') update({ insecure: true, ca_certs: undefined });
    if (choice === 'custom') {
      // Pointed at the stored CA straight away when there is one; otherwise
      // the path appears once one has been uploaded.
      update({ insecure: undefined, ca_certs: state?.files.ca?.path ?? section.ca_certs });
    }
  };

  const chooseClientCert = (on: boolean) => {
    setPendingClient(on);
    const stored = state?.files.client;
    if (!on) update({ certfile: undefined, keyfile: undefined });
    else if (stored?.key_path) update({ certfile: stored.path, keyfile: stored.key_path });
  };

  const uploadCa = async () => {
    const file = caInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append('certificate', file);
      const { data } = await axiosInstance.post('/api/mqtt-tls/client/ca', body, { timeout: 30000 });
      update({ ca_certs: data.stored.path, insecure: undefined });
      if (caInput.current) caInput.current.value = '';
      await load();
    } catch (err) {
      setError(errorDetail(err));
    } finally {
      setBusy(false);
    }
  };

  const uploadClient = async () => {
    const cert = certInput.current?.files?.[0];
    const key = keyInput.current?.files?.[0];
    if (!cert || !key) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append('certificate', cert);
      body.append('key', key);
      const { data } = await axiosInstance.post('/api/mqtt-tls/client/certificate', body, { timeout: 30000 });
      update({ certfile: data.stored.path, keyfile: data.stored.key_path });
      if (certInput.current) certInput.current.value = '';
      if (keyInput.current) keyInput.current.value = '';
      await load();
    } catch (err) {
      setError(errorDetail(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <ToggleRow
        checked={enabled}
        onChange={toggle}
        label={t('mqtt_tls.enable')}
        description={t('mqtt_tls.enable_help')}
      />

      {enabled && state?.tls_error && (
        <NoticeCallout variant="error" title={t('mqtt_tls.not_working')} message={state.tls_error} />
      )}

      {enabled && (
        <>
          <FormField label={t('mqtt_tls.verify')}>
            <select
              className="select select-bordered w-full"
              value={verify}
              onChange={(e) => chooseVerify(e.target.value as Verify)}
            >
              <option value="system">{t('mqtt_tls.verify_system')}</option>
              <option value="custom">{t('mqtt_tls.verify_custom')}</option>
              <option value="insecure">{t('mqtt_tls.verify_insecure')}</option>
            </select>
            <HelpLabel>
              {verify === 'system'
                ? t('mqtt_tls.verify_system_help')
                : verify === 'custom'
                  ? t('mqtt_tls.verify_custom_help')
                  : t('mqtt_tls.verify_insecure_help')}
            </HelpLabel>
          </FormField>

          {verify === 'insecure' && (
            <NoticeCallout variant="warning" message={t('mqtt_tls.insecure_warning')} />
          )}

          {verify === 'custom' && (
            <div className="space-y-2">
              {state?.files.ca ? (
                <FileSummary file={state.files.ca} />
              ) : (
                <NoticeCallout variant="info" message={t('mqtt_tls.ca_missing')} />
              )}
              {section.ca_certs && state?.files.ca && section.ca_certs !== state.files.ca.path && (
                <p className="text-xs text-base-content/60">
                  {t('mqtt_tls.ca_path_elsewhere', { path: section.ca_certs })}
                </p>
              )}
              <FormField label={t('mqtt_tls.ca_file')} help={t('mqtt_tls.ca_file_help')}>
                <div className="flex gap-2">
                  <input ref={caInput} type="file" accept=".pem,.crt,.cer" className="file-input file-input-bordered w-full" />
                  <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void uploadCa()}>
                    {t('mqtt_tls.upload')}
                  </button>
                </div>
              </FormField>
            </div>
          )}

          <ToggleRow
            checked={useClientCert}
            onChange={chooseClientCert}
            label={t('mqtt_tls.client_cert')}
            description={t('mqtt_tls.client_cert_help')}
          />

          {useClientCert && (
            <div className="space-y-2">
              {state?.files.client ? (
                <FileSummary file={state.files.client} />
              ) : (
                <NoticeCallout variant="info" message={t('mqtt_tls.client_missing')} />
              )}
              <FormField label={t('mqtt_tls.client_cert_file')}>
                <input ref={certInput} type="file" accept=".pem,.crt,.cer" className="file-input file-input-bordered w-full" />
              </FormField>
              <FormField label={t('mqtt_tls.client_key_file')} help={t('mqtt_tls.client_key_file_help')}>
                <input ref={keyInput} type="file" accept=".pem,.key" className="file-input file-input-bordered w-full" />
              </FormField>
              <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void uploadClient()}>
                {t('mqtt_tls.upload_client')}
              </button>
            </div>
          )}

          {error && <NoticeCallout variant="error" message={error} />}

          <p className="text-xs text-base-content/60">{t('mqtt_tls.save_to_apply')}</p>

          <OpenSslGuide variant="client" />
        </>
      )}
    </div>
  );
};

export default MqttTlsSettings;
