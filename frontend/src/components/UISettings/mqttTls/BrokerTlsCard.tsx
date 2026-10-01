import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FaLock, FaSpinner } from 'react-icons/fa';
import axiosInstance from '@/api/axios';
import { apiErrorMessage } from '@/api/errorMessage';
import { useTranslation } from '@/hooks/useTranslation';
import { FormActions, FormField, MoreOptions, NoticeCallout, SelectableCard, SettingsCard } from '../ui';
import OpenSslGuide from './OpenSslGuide';

type Mode = 'off' | 'optional' | 'required';

interface BrokerCertificate {
  subject: string;
  issuer: string;
  not_after: string;
  days_left: number;
  names: string[];
  uncovered: string[];
  ca_available: boolean;
}

export interface BrokerState {
  supported: boolean;
  mode: Mode | 'custom' | 'missing' | null;
  active: boolean | null;
  has_certificate: boolean;
  certificate: BrokerCertificate | null;
  tls_port: number;
  reached_by: string[];
  app: {
    host: string;
    port: number | null;
    uses_local_broker: boolean;
    tls: boolean;
    blocks_required: boolean;
  };
}

/** A restart of the broker on a BeagleBone, plus the helper's checks. */
const SLOW = { timeout: 120000 };

const errorDetail = apiErrorMessage;

/**
 * TLS for the broker installed on this controller.
 *
 * Everything that changes the broker goes through boneio-system, which
 * restarts it and puts the previous files back if it does not come up — so
 * a failure here is reported as a sentence, with the broker still running.
 */
const BrokerTlsCard: React.FC = () => {
  const { t } = useTranslation();
  const [state, setState] = useState<BrokerState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const certInput = useRef<HTMLInputElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);
  const caInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axiosInstance.get<BrokerState>('/api/mqtt-tls/broker', { timeout: 30000 });
      setState(data);
    } catch (err) {
      setError(errorDetail(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (what: string, run: () => Promise<unknown>, done: string) => {
    setBusy(what);
    setError(null);
    setNotice(null);
    try {
      await run();
      setNotice(done);
    } catch (err) {
      setError(errorDetail(err));
    } finally {
      setBusy(null);
      await load();
    }
  };

  const generate = () => {
    if (state?.has_certificate && !window.confirm(t('mqtt_tls.broker.generate_confirm'))) return;
    void act('generate', () => axiosInstance.post('/api/mqtt-tls/broker/generate', null, SLOW), t('mqtt_tls.broker.generated'));
  };

  const upload = () => {
    const cert = certInput.current?.files?.[0];
    const key = keyInput.current?.files?.[0];
    if (!cert || !key) return;
    const body = new FormData();
    body.append('certificate', cert);
    body.append('key', key);
    const ca = caInput.current?.files?.[0];
    if (ca) body.append('ca', ca);
    void act(
      'upload',
      async () => {
        await axiosInstance.post('/api/mqtt-tls/broker/certificate', body, SLOW);
        for (const input of [certInput, keyInput, caInput]) if (input.current) input.current.value = '';
      },
      t('mqtt_tls.broker.uploaded'),
    );
  };

  const remove = () => {
    if (!window.confirm(t('mqtt_tls.broker.remove_confirm'))) return;
    void act('remove', () => axiosInstance.delete('/api/mqtt-tls/broker/certificate', SLOW), t('mqtt_tls.broker.removed'));
  };

  const setMode = (mode: Mode) => {
    if (!state || state.mode === mode) return;
    const warning = t(`mqtt_tls.broker.confirm_${mode}`);
    if (!window.confirm(warning)) return;
    void act('mode', () => axiosInstance.put('/api/mqtt-tls/broker/mode', { mode }, SLOW), t(`mqtt_tls.broker.mode_set_${mode}`));
  };

  const downloadCa = async () => {
    try {
      const { data } = await axiosInstance.get('/api/mqtt-tls/broker/ca', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'boneio-mqtt-ca.crt';
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorDetail(err));
    }
  };

  if (!state) {
    return (
      <SettingsCard title={t('mqtt_tls.broker.title')} icon={<FaLock />}>
        {error ? <NoticeCallout variant="error" message={error} /> : <span className="loading loading-spinner loading-sm" />}
      </SettingsCard>
    );
  }

  const cert = state.certificate;
  const managed = state.mode === 'off' || state.mode === 'optional' || state.mode === 'required';
  const canChange = state.supported && managed && busy === null;

  const modes: { id: Mode; disabled: boolean }[] = [
    { id: 'off', disabled: false },
    { id: 'optional', disabled: !state.has_certificate },
    { id: 'required', disabled: !state.has_certificate || state.app.blocks_required },
  ];
  // Said under the list rather than in the cards, whose subtitles are cut to
  // one line — and a reason cut in half is no reason at all.
  const reasons = [
    ...(state.has_certificate ? [] : [t('mqtt_tls.broker.needs_certificate')]),
    ...(state.app.blocks_required ? [t('mqtt_tls.broker.blocked_by_app', { host: state.app.host })] : []),
  ];

  return (
    <SettingsCard
      title={t('mqtt_tls.broker.title')}
      icon={<FaLock />}
      description={t('mqtt_tls.broker.description')}
      action={
        state.mode && managed ? (
          <span className={`badge badge-sm ${state.mode === 'off' ? 'badge-ghost' : 'badge-success'}`}>
            {t(`mqtt_tls.broker.badge_${state.mode}`)}
          </span>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {!state.supported && <NoticeCallout variant="warning" message={t('mqtt_tls.broker.unsupported')} />}
        {state.supported && state.mode === 'custom' && (
          <NoticeCallout variant="warning" message={t('mqtt_tls.broker.custom')} />
        )}
        {state.supported && state.mode === 'missing' && (
          <NoticeCallout variant="warning" message={t('mqtt_tls.broker.missing')} />
        )}

        {/* The certificate */}
        <div className="space-y-2">
          <div className="text-[13px] font-medium">{t('mqtt_tls.broker.certificate')}</div>
          {cert ? (
            <dl className="text-xs space-y-0.5 stg-inset p-2">
              <div>
                <dt className="inline font-semibold">{t('mqtt_tls.issuer')}: </dt>
                <dd className="inline break-all">{cert.issuer}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t('mqtt_tls.broker.valid_for')}: </dt>
                <dd className="inline break-all">{cert.names.join(', ') || '—'}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t('mqtt_tls.expires')}: </dt>
                <dd className="inline">
                  {new Date(cert.not_after).toLocaleDateString()} ({cert.days_left} d)
                </dd>
              </div>
              {cert.uncovered.length > 0 && (
                <div className="text-warning">{t('mqtt_tls.broker.uncovered', { names: cert.uncovered.join(', ') })}</div>
              )}
              {cert.days_left < 30 && <div className="text-warning">{t('mqtt_tls.broker.expiring')}</div>}
            </dl>
          ) : (
            <p className="text-xs text-base-content/60">{t('mqtt_tls.broker.no_certificate')}</p>
          )}

          <FormActions>
            <button type="button" className="btn btn-primary btn-sm gap-2" disabled={!canChange} onClick={generate}>
              {busy === 'generate' && <FaSpinner className="animate-spin" />}
              {t('mqtt_tls.broker.generate')}
            </button>
            {cert?.ca_available && (
              <button type="button" className="btn btn-outline btn-sm" onClick={() => void downloadCa()}>
                {t('mqtt_tls.broker.download_ca')}
              </button>
            )}
            {state.has_certificate && state.mode === 'off' && (
              <button type="button" className="btn btn-ghost btn-sm" disabled={!canChange} onClick={remove}>
                {t('mqtt_tls.broker.remove')}
              </button>
            )}
          </FormActions>
          <p className="text-xs text-base-content/60">{t('mqtt_tls.broker.generate_help')}</p>

          <MoreOptions label={t('mqtt_tls.broker.upload_title')} summary={t('mqtt_tls.broker.upload_summary')}>
            <div className="space-y-3 pt-2">
              <FormField label={t('mqtt_tls.broker.file_cert')}>
                <input ref={certInput} type="file" accept=".pem,.crt,.cer" className="file-input file-input-bordered w-full" />
              </FormField>
              <FormField label={t('mqtt_tls.broker.file_key')} help={t('mqtt_tls.broker.file_key_help')}>
                <input ref={keyInput} type="file" accept=".pem,.key" className="file-input file-input-bordered w-full" />
              </FormField>
              <FormField label={t('mqtt_tls.broker.file_ca')} help={t('mqtt_tls.broker.file_ca_help')}>
                <input ref={caInput} type="file" accept=".pem,.crt,.cer" className="file-input file-input-bordered w-full" />
              </FormField>
              <button type="button" className="btn btn-primary btn-sm gap-2" disabled={!canChange} onClick={upload}>
                {busy === 'upload' && <FaSpinner className="animate-spin" />}
                {t('mqtt_tls.broker.upload')}
              </button>
            </div>
          </MoreOptions>
        </div>

        {/* The mode */}
        <div className="space-y-2">
          <div className="text-[13px] font-medium">{t('mqtt_tls.broker.mode')}</div>
          {modes.map(({ id, disabled }) => (
            <SelectableCard
              key={id}
              selected={state.mode === id}
              onToggle={() => setMode(id)}
              disabled={!canChange || disabled}
              title={t(`mqtt_tls.broker.mode_${id}`)}
              subtitle={t(`mqtt_tls.broker.mode_${id}_help`, { port: state.tls_port })}
              badge={busy === 'mode' && state.mode !== id ? <FaSpinner className="animate-spin" /> : undefined}
            />
          ))}
          {canChange && reasons.map((reason) => (
            <p key={reason} className="text-xs text-warning">{reason}</p>
          ))}
          <p className="text-xs text-base-content/60">{t('mqtt_tls.broker.required_note', { port: state.tls_port })}</p>
        </div>

        {state.mode && state.mode !== 'off' && managed && (
          <NoticeCallout
            variant="info"
            title={t('mqtt_tls.broker.clients_title')}
            message={t('mqtt_tls.broker.clients_help', { port: state.tls_port })}
          />
        )}

        {error && <NoticeCallout variant="error" message={error} />}
        {notice && <NoticeCallout variant="success" message={notice} />}

        <OpenSslGuide variant="broker" addresses={state.reached_by} />
      </div>
    </SettingsCard>
  );
};

export default BrokerTlsCard;
